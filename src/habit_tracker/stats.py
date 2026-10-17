"""
Pure statistics helpers (no I/O), operating on the DataFrames returned
by :class:`habit_tracker.db.Tracker`.

Invariant: a completion is only ever logged for an item that is due on
that day, so ``done <= due`` holds for every day.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Sentinel for "never archived"; Timestamp.max would overflow on arithmetic.
_FAR_FUTURE = pd.Timestamp("2262-01-01")


def completion_rates(
    items: pd.DataFrame, log: pd.DataFrame, start: date, end: date
) -> pd.DataFrame:
    """
    Daily completion statistics over ``[start, end]`` (inclusive).

    Parameters
    ----------
    items : pd.DataFrame
        Output of ``Tracker.items()``.
    log : pd.DataFrame
        Output of ``Tracker.log(start, end)``.
    start, end : date
        Window boundaries.

    Returns
    -------
    pd.DataFrame
        Indexed by day with columns ``done``, ``due`` and ``rate``.
        ``rate = done / due`` and is NaN on days where nothing was due.
    """
    days = pd.date_range(start, end, freq="D", name="day")
    grid = days.to_numpy("datetime64[ns]")[:, None]
    created = items["created_on"].to_numpy("datetime64[ns]")[None, :]
    archived = (
        items["archived_on"]
        .fillna(_FAR_FUTURE)
        .to_numpy("datetime64[ns]")[None, :]
    )
    due = pd.Series(((grid >= created) & (grid < archived)).sum(axis=1), days)
    done = log.groupby("day").size().reindex(days, fill_value=0)
    rate = done / due.where(due > 0)
    return pd.DataFrame({"done": done, "due": due, "rate": rate})


def item_summary(
    items: pd.DataFrame, log: pd.DataFrame, start: date, end: date
) -> pd.DataFrame:
    """
    Per-item completion rate over ``[start, end]``, best first.

    Returns
    -------
    pd.DataFrame
        Columns ``name``, ``kind``, ``done``, ``due`` (days the item was
        active in the window) and ``rate``.
    """
    lo = pd.Timestamp(start)
    hi = pd.Timestamp(end) + pd.Timedelta(days=1)
    first = items["created_on"].clip(lower=lo)
    last = items["archived_on"].fillna(_FAR_FUTURE).clip(upper=hi)
    in_window = log[(log["day"] >= lo) & (log["day"] < hi)]

    out = items[["name", "kind"]].copy()
    out["done"] = (
        in_window.groupby("item_id")
        .size()
        .reindex(items["id"], fill_value=0)
        .to_numpy()
    )
    out["due"] = (last - first).dt.days.clip(lower=0).to_numpy()
    out["rate"] = out["done"] / out["due"].where(out["due"] > 0)
    return out.sort_values("rate", ascending=False).reset_index(drop=True)


def heatmap_frame(rates: pd.DataFrame) -> pd.DataFrame:
    """
    Add calendar coordinates (``week`` start date, ``weekday`` name) to the
    output of :func:`completion_rates`, ready for a GitHub-style heatmap.
    """
    out = rates.reset_index()
    weekday_num = out["day"].dt.dayofweek
    out["week"] = out["day"] - pd.to_timedelta(weekday_num, unit="D")
    out["weekday"] = weekday_num.map(dict(enumerate(WEEKDAYS)))
    return out


def streaks(
    rates: pd.DataFrame,
    threshold: float = 1.0,
    forgive_open_day: bool = True,
) -> tuple[int, int]:
    """
    Current and longest streak of days with ``rate >= threshold``.

    Days with nothing due are skipped (they neither extend nor break a
    streak).

    Parameters
    ----------
    rates : pd.DataFrame
        Output of :func:`completion_rates`.
    threshold : float, optional(default=1.0)
        Minimum completion rate for a day to count.
    forgive_open_day : bool, optional(default=True)
        If the most recent day is incomplete, ignore it when computing the
        *current* streak (the day is presumably still in progress).

    Returns
    -------
    current, longest : tuple of int
    """
    hits = (rates["rate"].dropna() >= threshold).to_numpy()

    longest = run = 0
    for hit in hits:
        run = run + 1 if hit else 0
        longest = max(longest, run)

    if forgive_open_day and len(hits) and not hits[-1]:
        hits = hits[:-1]
    current = 0
    for hit in hits[::-1]:
        if not hit:
            break
        current += 1
    return current, longest
