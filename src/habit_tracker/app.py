"""
Streamlit front end.  Run with::

    streamlit run src/habit_tracker/app.py
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from habit_tracker import (
    KINDS,
    PERSONS,
    Tracker,
    completion_rates,
    heatmap_frame,
    item_summary,
    streaks,
)
from habit_tracker.stats import WEEKDAYS

WINDOWS = {"90 days": 90, "6 months": 182, "1 year": 365}


@st.cache_resource
def get_tracker() -> Tracker:
    """Open the database once per server process."""
    path = Path(os.environ.get("HABIT_TRACKER_DB", "data/tracker.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return Tracker(path)


def _toggle(tracker: Tracker, item_id: int, day: date, key: str) -> None:
    tracker.set_done(item_id, day, st.session_state[key])


def render_checklist(tracker: Tracker) -> None:
    """Daily checklist split into two side-by-side columns for Zaira and Pali."""
    day = st.date_input("Day", value=date.today(), max_value=date.today())
    
    col_zaira, col_pali = st.columns(2)
    
    for person, col in zip(PERSONS, [col_zaira, col_pali]):
        with col:
            st.subheader(person)
            items = tracker.items(active_on=day, person=person)
            if items.empty:
                st.info(f"Nothing to track for {person} today.")
                continue

            done = tracker.done_ids(day)
            n_done = len(done & set(items["id"]))
            st.progress(n_done / len(items) if len(items) > 0 else 0, text=f"{n_done} / {len(items)} done")

            for kind in KINDS:
                subset = items[items["kind"] == kind]
                if subset.empty:
                    continue
                st.markdown(f"*{kind.title()}s*")
                for row in subset.itertuples():
                    key = f"chk-{person}-{day}-{row.id}"
                    st.checkbox(
                        row.name,
                        value=row.id in done,
                        key=key,
                        on_change=_toggle,
                        args=(tracker, int(row.id), day, key),
                    )

def heatmap_chart(frame: pd.DataFrame) -> alt.Chart:
    """GitHub-style calendar heatmap with a custom pink/purple color scale."""
    return (
        alt.Chart(frame.dropna(subset=["rate"]))
        .mark_rect(cornerRadius=2, stroke="#262730", strokeWidth=1)
        .encode(
            x=alt.X(
                "yearmonthdate(week):O",
                title=None,
                axis=alt.Axis(format="%d %b", labelAngle=-90),
            ),
            y=alt.Y("weekday:O", sort=WEEKDAYS, title=None),
            color=alt.Color(
                "rate:Q",
                scale=alt.Scale(domain=[0, 1], range=["#6000fa", "#ff00ea"]),
                legend=alt.Legend(title="Completed", format=".0%"),
            ),
            tooltip=[
                alt.Tooltip("day:T", title="Date"),
                alt.Tooltip("done:Q"),
                alt.Tooltip("due:Q"),
                alt.Tooltip("rate:Q", format=".0%"),
            ],
        )
        .properties(height=160)
    )


def _select_items(items: pd.DataFrame) -> pd.DataFrame:
    """Let the user pick a subset: everything, a kind, or one item."""
    options = ["All", *(f"All {k}s" for k in KINDS), *items["name"]]
    choice = st.selectbox("Show", options, key="select_items_box")
    if choice == "All":
        return items
    if choice.startswith("All "):
        return items[items["kind"] == choice[4:-1]]
    return items[items["name"] == choice]



def render_stats(tracker: Tracker) -> None:
    """Heatmap, streaks and per-item completion rates, split by person if 'Both' is selected."""
    person_choice = st.radio("Person", ["Both", *PERSONS], horizontal=True, key="stats_person_radio")
    window = st.radio("Window", list(WINDOWS), horizontal=True, key="stats_window_radio")
    
    end = date.today()
    start = end - timedelta(days=WINDOWS[window] - 1)
    log = tracker.log(start, end)

    if person_choice == "Both":
        for person in PERSONS:
            st.markdown(f"### {person}")
            all_items = tracker.items(person=person)
            if all_items.empty:
                st.info(f"No data yet for {person}.")
                st.divider()
                continue

            items = all_items
            person_log = log[log["item_id"].isin(items["id"])]

            rates = completion_rates(items, person_log, start, end)
            current, longest = streaks(rates)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Current streak", f"{current} d")
            c2.metric("Longest streak", f"{longest} d")
            c3.metric("Mean completion", f"{rates['rate'].mean() if not rates.empty else 0:.0%}")

            st.altair_chart(
                heatmap_chart(heatmap_frame(rates)), use_container_width=True
            )

            summary = item_summary(items, person_log, start, end)
            st.dataframe(
                summary,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "rate": st.column_config.ProgressColumn(
                        "rate", format="percent", min_value=0.0, max_value=1.0
                    )
                },
            )
            st.divider()
    else:
        st.markdown(f"### {person_choice}")
        all_items = tracker.items(person=person_choice)
        if all_items.empty:
            st.info(f"No data yet for {person_choice}.")
            return

        items = _select_items(all_items)
        person_log = log[log["item_id"].isin(items["id"])]

        rates = completion_rates(items, person_log, start, end)
        current, longest = streaks(rates)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Current streak", f"{current} d")
        c2.metric("Longest streak", f"{longest} d")
        c3.metric("Mean completion", f"{rates['rate'].mean() if not rates.empty else 0:.0%}")

        st.altair_chart(
            heatmap_chart(heatmap_frame(rates)), use_container_width=True
        )

        summary = item_summary(items, person_log, start, end)
        st.dataframe(
            summary,
            hide_index=True,
            use_container_width=True,
            column_config={
                "rate": st.column_config.ProgressColumn(
                    "rate", format="percent", min_value=0.0, max_value=1.0
                )
            },
        )


def render_manage(tracker: Tracker) -> None:
    """Add new items for both or individual people, and delete existing ones."""
    with st.form("add_item", clear_on_submit=True):
        name = st.text_input("Name")
        kind = st.radio("Type", KINDS, horizontal=True)
        target_person = st.radio("For who?", ["Both", *PERSONS], horizontal=True)
        if st.form_submit_button("Add") and name.strip():
            try:
                if target_person == "Both":
                    for p in PERSONS:
                        try:
                            tracker.add_item(name, kind, p)
                        except ValueError:
                            pass  # Ignore if it already exists for one of them
                else:
                    tracker.add_item(name, kind, target_person)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    st.divider()
    person_filter = st.selectbox("Manage items for", PERSONS, key="manage_person_select")
    items = tracker.items(person=person_filter)
    if not items.empty:
        target = st.selectbox("Delete item", items["name"], key="delete_item_select")
        confirmed = st.checkbox("Yes, delete this item permanently", key="delete_confirm")
        if st.button("Delete", disabled=not confirmed):
            item_id = int(items.loc[items["name"] == target, "id"].iloc[0])
            tracker.delete_item(item_id)
            st.rerun()

def main() -> None:
    """Entry point."""
    st.set_page_config(page_title="Tracker", page_icon="🩷")
    tracker = get_tracker()
    tab_today, tab_stats, tab_manage = st.tabs(["Today", "Stats", "Manage"])
    with tab_today:
        render_checklist(tracker)
    with tab_stats:
        render_stats(tracker)
    with tab_manage:
        render_manage(tracker)


main()