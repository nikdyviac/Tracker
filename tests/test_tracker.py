from datetime import date

import pandas as pd
import pytest

from habit_tracker import Tracker, completion_rates, streaks

D = date


@pytest.fixture
def tracker():
    return Tracker()


def test_set_done_is_idempotent(tracker):
    i = tracker.add_item("Magnesium", "supplement", D(2026, 1, 1))
    for _ in range(2):
        tracker.set_done(i, D(2026, 1, 2), True)
    assert tracker.done_ids(D(2026, 1, 2)) == {i}
    tracker.set_done(i, D(2026, 1, 2), False)
    assert tracker.done_ids(D(2026, 1, 2)) == set()


def test_duplicate_name_and_bad_kind(tracker):
    tracker.add_item("Stretching", "habit")
    with pytest.raises(ValueError):
        tracker.add_item("Stretching", "habit")
    with pytest.raises(ValueError):
        tracker.add_item("X", "chore")


def test_archive_keeps_history(tracker):
    i = tracker.add_item("A", "habit", D(2026, 1, 1))
    tracker.archive_item(i, D(2026, 1, 5))
    assert i in tracker.items(active_on=D(2026, 1, 4))["id"].tolist()
    assert tracker.items(active_on=D(2026, 1, 5)).empty


def test_completion_rates_respect_item_lifetimes(tracker):
    a = tracker.add_item("A", "habit", D(2026, 1, 1))
    b = tracker.add_item("B", "habit", D(2026, 1, 3))
    tracker.set_done(a, D(2026, 1, 1), True)
    tracker.set_done(a, D(2026, 1, 3), True)
    tracker.set_done(b, D(2026, 1, 3), True)
    start, end = D(2026, 1, 1), D(2026, 1, 3)
    rates = completion_rates(
        tracker.items(), tracker.log(start, end), start, end
    )
    assert rates["due"].tolist() == [1, 1, 2]
    assert rates["rate"].tolist() == [1.0, 0.0, 1.0]


def test_completion_rates_empty_log(tracker):
    tracker.add_item("A", "habit", D(2026, 1, 1))
    start, end = D(2026, 1, 1), D(2026, 1, 2)
    rates = completion_rates(
        tracker.items(), tracker.log(start, end), start, end
    )
    assert rates["done"].tolist() == [0, 0]


def test_streaks():
    rates = pd.DataFrame({"rate": [1, 1, 0, 1, 1, 1]})
    assert streaks(rates) == (3, 3)
    open_day = pd.DataFrame({"rate": [1, 1, 0]})
    assert streaks(open_day) == (2, 2)
    assert streaks(open_day, forgive_open_day=False) == (0, 2)
