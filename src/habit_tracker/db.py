"""
SQLite persistence layer.

Two tables are used:

- ``items`` -- things to track (supplements or habits) for a specific person.
- ``log`` -- one row per (item, day) completion.  Presence of a row means
  "done"; absence means "not data".
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

KINDS = ("supplement", "habit")
PERSONS = ("Zaira", "Pali")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('supplement', 'habit')),
    person      TEXT NOT NULL CHECK (person IN ('Zaira', 'Pali')),
    created_on  TEXT NOT NULL,
    archived_on TEXT,
    UNIQUE(name, person)
);
CREATE TABLE IF NOT EXISTS log (
    item_id INTEGER NOT NULL REFERENCES items (id),
    day     TEXT NOT NULL,
    PRIMARY KEY (item_id, day)
);
"""


class Tracker:
    """
    Thin repository around a SQLite database with multi-person support.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------
    def add_item(
        self, name: str, kind: str, person: str, created_on: date | None = None
    ) -> int:
        """
        Create a new item for a specific person and return its id.

        Raises
        ------
        ValueError
            If ``kind`` or ``person`` is invalid, or if the item already exists for that person.
        """
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
        if person not in PERSONS:
            raise ValueError(f"person must be one of {PERSONS}, got {person!r}")
            
        created_on = created_on or date.today()
        try:
            with self._conn:
                cur = self._conn.execute(
                    "INSERT INTO items (name, kind, person, created_on) "
                    "VALUES (?, ?, ?, ?)",
                    (name.strip(), kind, person, created_on.isoformat()),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Item {name!r} already exists for {person}.") from exc
        return int(cur.lastrowid)

    def delete_item(self, item_id: int) -> None:
        """
        Permanently delete an item together with its completion history.

        Parameters
        ----------
        item_id : int
            Id of the item to remove.
        """
        # ``log.item_id`` references ``items.id`` and foreign keys are enforced,
        # so the child rows must be removed first.
        with self._conn:
            self._conn.execute("DELETE FROM log WHERE item_id = ?", (item_id,))
            self._conn.execute("DELETE FROM items WHERE id = ?", (item_id,))

    def archive_item(self, item_id: int, on: date | None = None) -> None:
        """Stop tracking an item from day ``on`` (default today) onwards."""
        on = on or date.today()
        with self._conn:
            self._conn.execute(
                "UPDATE items SET archived_on = ? WHERE id = ?",
                (on.isoformat(), item_id),
            )

    def items(self, active_on: date | None = None, person: str | None = None) -> pd.DataFrame:
        """
        Return items as a DataFrame, optionally filtered by person.
        """
        query = "SELECT id, name, kind, person, created_on, archived_on FROM items"
        conditions = []
        params: list[str] = []

        if active_on is not None:
            day = active_on.isoformat()
            conditions.append("created_on <= ? AND (archived_on IS NULL OR archived_on > ?)")
            params.extend([day, day])

        if person is not None:
            conditions.append("person = ?")
            params.append(person)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY id"
        return pd.read_sql_query(
            query,
            self._conn,
            params=tuple(params),
            parse_dates=["created_on", "archived_on"],
        )

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------
    def set_done(self, item_id: int, day: date, done: bool) -> None:
        """Mark an item as done (or not done) on ``day``; idempotent."""
        sql = (
            "INSERT OR IGNORE INTO log (item_id, day) VALUES (?, ?)"
            if done
            else "DELETE FROM log WHERE item_id = ? AND day = ?"
        )
        with self._conn:
            self._conn.execute(sql, (item_id, day.isoformat()))

    def done_ids(self, day: date) -> set[int]:
        """Return the ids of all items completed on ``day``."""
        rows = self._conn.execute(
            "SELECT item_id FROM log WHERE day = ?", (day.isoformat(),)
        )
        return {int(r[0]) for r in rows}

    def log(self, start: date, end: date) -> pd.DataFrame:
        """Return completions with ``start <= day <= end``."""
        return pd.read_sql_query(
            "SELECT item_id, day FROM log WHERE day BETWEEN ? AND ?",
            self._conn,
            params=(start.isoformat(), end.isoformat()),
            parse_dates=["day"],
        )