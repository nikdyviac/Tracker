# habit-tracker

Single-user daily checklist for supplements and habits, with a GitHub-style
completion heatmap.  Data lives in one SQLite file (`data/tracker.db`,
git-ignored).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
streamlit run src/habit_tracker/app.py
```

Set `HABIT_TRACKER_DB` to store the database elsewhere (e.g. a synced
folder, which doubles as a backup).

## Using it from a phone

```bash
streamlit run src/habit_tracker/app.py --server.address 0.0.0.0
```

There is no authentication by design, so only expose it on a trusted
network (home Wi-Fi, or a VPN such as Tailscale).

## Design notes

* An item is *due* on every day in `[created_on, archived_on)`; the
  denominator of each day's completion rate is the number of due items.
  Archiving therefore never rewrites history.
* `stats.py` is pure pandas/NumPy and is the only module with real logic
  worth testing; `db.py` is a thin repository and `app.py` is UI only.
