import datetime
import json

import polars as pl
import pytest


@pytest.fixture
def df() -> pl.LazyFrame:
    """A small frame covering every dtype the widget has special handling for, with nulls."""
    return pl.LazyFrame(
        {
            "id": [0, 1, 2, 3, 4, 5],
            "name": ["Tom", "Joseph", "Krish", "John", None, "Bob"],
            "score": [3.5, 4.0, 7.5, 1.0, 6.5, None],
            "flag": [True, True, False, True, False, None],
            "birthday": [
                datetime.datetime(1995, 3, 1, 10, 30),
                datetime.datetime(1999, 1, 27),
                datetime.datetime(1977, 7, 24),
                None,
                datetime.datetime(2005, 7, 17),
                datetime.datetime(2001, 9, 19),
            ],
            "day": [
                datetime.date(2020, 1, 1),
                datetime.date(2020, 1, 2),
                None,
                datetime.date(2020, 1, 4),
                datetime.date(2020, 1, 5),
                datetime.date(2020, 1, 6),
            ],
            "duration": [
                datetime.timedelta(hours=1),
                datetime.timedelta(minutes=30),
                None,
                datetime.timedelta(seconds=5),
                datetime.timedelta(hours=2, minutes=3, seconds=4),
                datetime.timedelta(0),
            ],
            "tags": [["a"], ["a", "b"], [], None, ["c"], ["b"]],
            "cat": ["x", "y", "x", "z", "y", "x"],
        }
    )


@pytest.fixture
def big_df() -> pl.LazyFrame:
    """Large enough for the streaming engine to split work into several morsels."""
    n = 50_000
    return pl.LazyFrame(
        {
            "id": range(n),
            "grp": [i % 7 for i in range(n)],
            "val": [float(i) for i in range(n)],
        }
    )


def assert_json_serializable(items):
    # items are synced to the frontend as JSON
    json.dumps(items)
