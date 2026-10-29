import datetime

import polars as pl
import pytest

from ipyvuetable import Table
from ipyvuetable.filters import (
    FilterCombobox,
    FilterDate,
    FilterDateTime,
    FilterListCombobox,
    FilterSlider,
)


def ids(table: Table) -> list:
    return [row["id"] for row in table.items]


def open_filter(table: Table, col: str):
    f = table.filters[col]
    f.menu.v_model = True
    return f


def close_filter(f):
    f.menu.v_model = False


def test_filter_types(df):
    table = Table(df=df)
    assert isinstance(table.filters["id"], FilterCombobox)
    assert isinstance(table.filters["name"], FilterCombobox)
    assert isinstance(table.filters["score"], FilterSlider)
    assert isinstance(table.filters["flag"], FilterCombobox)
    assert isinstance(table.filters["birthday"], FilterDateTime)
    assert isinstance(table.filters["day"], FilterDate)
    assert isinstance(table.filters["duration"], FilterCombobox)
    assert isinstance(table.filters["tags"], FilterListCombobox)


@pytest.mark.parametrize("col", ["id", "name", "score", "flag", "birthday", "day", "duration", "tags", "cat"])
def test_every_filter_opens_and_closes_without_change(df, col):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, col)
    close_filter(f)
    assert f.mask is None
    assert ids(table) == list(range(6))


# --- combobox -------------------------------------------------------------------------------------


def select_values(f: FilterCombobox, values: list):
    # what the frontend does when options are checked: rows carry the row_nr of the filter table
    key = f.name + "__key"
    df = f.filter_obj.df.collect()
    f.filter_obj.v_model = [
        {key: str(row[key]), f.filter_obj.row_nr: row[f.filter_obj.row_nr]}
        for row in df.to_dicts()
        if row[key] in values
    ]


def test_combobox_options(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "cat")
    assert sorted(r["cat"] for r in f.filter_obj.items) == ["x", "y", "z"]


def test_combobox_filter(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "cat")
    select_values(f, ["x", "z"])
    close_filter(f)
    assert ids(table) == [0, 2, 3, 5]
    assert f.filter_icon.color == "primary"
    assert table.actions["undo_filters"]["obj"].disabled is False


def test_combobox_filter_on_null(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "name")
    select_values(f, [None])
    close_filter(f)
    assert ids(table) == [4]


def test_combobox_filter_on_bool(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "flag")
    # option labels go through the boolean repr, keys stay raw
    assert {r["flag"] for r in f.filter_obj.items} >= {"✅", "❌"}
    select_values(f, [False])
    close_filter(f)
    assert ids(table) == [2, 4]


def test_combobox_filter_on_duration(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "duration")
    select_values(f, [datetime.timedelta(hours=1)])
    close_filter(f)
    assert ids(table) == [0]


def test_combobox_filter_with_columns_repr(df):
    repr_ = pl.LazyFrame({"cat": ["x", "y", "z"], "cat__repr": ["X!", "Y!", "Z!"]})
    table = Table(df=df, columns_repr={"cat": repr_}, items_per_page=-1)
    f = open_filter(table, "cat")
    assert sorted(r["cat"] for r in f.filter_obj.items) == ["X!", "Y!", "Z!"]
    select_values(f, ["y"])
    close_filter(f)
    assert ids(table) == [1, 4]


def test_combobox_modify_filter(df):
    table = Table(df=df, items_per_page=-1)
    table.filters["cat"].modify_filter(["y"])
    table._apply_filters()
    assert ids(table) == [1, 4]


def test_combobox_search(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "name")
    f.search.fire_event("input", "JO")
    assert sorted(r["name"] for r in f.filter_obj.items) == ["John", "Joseph"]
    f.search.fire_event("input", "")
    assert len(f.filter_obj.items) == 6


def test_combobox_search_numeric(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "id")
    f.search.fire_event("input", "3")
    assert [r["id"] for r in f.filter_obj.items] == [3]


def test_combobox_undo(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "cat")
    select_values(f, ["x"])
    close_filter(f)
    f.undo_icon.fire_event("click", None)
    assert f.mask is None
    assert f.filter_obj.v_model == []
    table._apply_filters()
    assert ids(table) == list(range(6))


def test_combobox_available_values_listed_first(df):
    table = Table(df=df, items_per_page=-1)
    f_cat = open_filter(table, "cat")
    select_values(f_cat, ["z"])
    close_filter(f_cat)
    # only id 3 has cat == "z"; its name must come first in the name filter
    f_name = open_filter(table, "name")
    assert f_name.filter_obj.items[0]["name"] == "John"


def test_combined_filters(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "cat")
    select_values(f, ["x", "y"])
    close_filter(f)
    s = open_filter(table, "score")
    s.filter_obj.v_model = [3, 5]
    close_filter(s)
    assert ids(table) == [0, 1]


def test_undo_all_filters(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "cat")
    select_values(f, ["x"])
    close_filter(f)
    s = open_filter(table, "score")
    s.filter_obj.v_model = [3, 5]
    close_filter(s)
    table.actions["undo_filters"]["obj"].fire_event("click", None)
    assert ids(table) == list(range(6))
    assert table.actions["undo_filters"]["obj"].disabled is True


def test_filter_keeps_order_on_big_frame(big_df):
    table = Table(df=big_df)
    f = open_filter(table, "grp")
    select_values(f, [3, 5])
    close_filter(f)
    expected = [i for i in range(50_000) if i % 7 in (3, 5)]
    assert table.server_items_length == len(expected)
    assert ids(table) == expected[:10]


# --- slider ---------------------------------------------------------------------------------------


def test_slider_bounds(df):
    table = Table(df=df)
    s = open_filter(table, "score")
    assert (s.filter_obj.min, s.filter_obj.max) == (1, 8)
    assert s.filter_obj.v_model == [1, 8]


def test_slider_full_range_is_no_filter(df):
    table = Table(df=df, items_per_page=-1)
    s = open_filter(table, "score")
    close_filter(s)
    assert s.mask is None


def test_slider_text_fields(df):
    table = Table(df=df, items_per_page=-1)
    s = open_filter(table, "score")
    s.min_field.fire_event("input", "4")
    s.max_field.fire_event("input", "7")
    close_filter(s)
    assert ids(table) == [1, 4]


def test_slider_on_all_null_column():
    table = Table(df=pl.LazyFrame({"x": [None, None]}, schema={"x": pl.Float64}))
    s = open_filter(table, "x")
    close_filter(s)
    assert s.mask is None


def test_slider_undo(df):
    table = Table(df=df, items_per_page=-1)
    s = open_filter(table, "score")
    s.filter_obj.v_model = [3, 5]
    close_filter(s)
    s.undo_icon.fire_event("click", None)
    table._apply_filters()
    assert ids(table) == list(range(6))


# --- dates ----------------------------------------------------------------------------------------


def test_date_filter(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "day")
    assert (f.min_field.v_model, f.max_field.v_model) == ("2020-01-01", "2020-01-06")
    f.min_field.v_model = "2020-01-02"
    f.max_field.v_model = "2020-01-04"
    close_filter(f)
    assert ids(table) == [1, 3]
    f.undo_icon.fire_event("click", None)
    table._apply_filters()
    assert ids(table) == list(range(6))


def test_datetime_filter(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "birthday")
    assert (f.min_field.v_model, f.max_field.v_model) == ("1977-07-24", "2005-07-17")
    f.min_field.v_model = "1990-01-01"
    f.max_field.v_model = "2002-01-01"
    close_filter(f)
    assert ids(table) == [0, 1, 5]


def test_datetime_filter_max_is_inclusive_of_the_day(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "birthday")
    f.min_field.v_model = "1995-03-01"
    f.max_field.v_model = "1995-03-01"
    close_filter(f)
    # 1995-03-01 10:30 is on the selected day
    assert ids(table) == [0]


@pytest.mark.parametrize("col", ["day", "birthday"])
def test_date_filter_on_all_null_column(col):
    dtype = pl.Date if col == "day" else pl.Datetime
    table = Table(df=pl.LazyFrame({col: [None, None]}, schema={col: dtype}))
    f = open_filter(table, col)
    close_filter(f)
    assert f.mask is None


@pytest.mark.parametrize("col", ["day", "birthday"])
def test_date_filter_cleared_field(df, col):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, col)
    f.min_field.v_model = ""
    close_filter(f)
    assert len(table.items) == 6


def test_combobox_modify_filter_before_opening_with_many_values(big_df):
    table = Table(df=big_df)
    # more distinct values than one page of the filter table
    table.filters["id"].modify_filter([123, 45_678])
    assert ids(table) == [123, 45_678]


def test_combobox_modify_filter_raw_values(df):
    table = Table(df=df, items_per_page=-1)
    table.filters["flag"].modify_filter([False, None])
    assert ids(table) == [2, 4, 5]
    table.filters["duration"].modify_filter([datetime.timedelta(minutes=30)])
    assert ids(table) == []
    table.filters["flag"].modify_filter([True])
    assert ids(table) == [1]


def test_filters_survive_df_change_with_reordered_options(big_df):
    table = Table(df=big_df)
    table.filters["grp"].modify_filter([3])
    for _ in range(5):
        table.df = table.df.drop("__row_nr__")
        assert table.server_items_length == len([i for i in range(50_000) if i % 7 == 3])
        assert all(row["grp"] == 3 for row in table.items)


# --- list -----------------------------------------------------------------------------------------


def test_list_filter_options(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "tags")
    assert {r["tags"] for r in f.filter_obj.items} >= {"a", "b", "c"}


def test_list_filter(df):
    table = Table(df=df, items_per_page=-1)
    f = open_filter(table, "tags")
    select_values(f, ["b"])
    close_filter(f)
    assert ids(table) == [1, 5]
    assert table.server_items_length == 2


def test_list_filter_any_of(df):
    table = Table(df=df, items_per_page=-1)
    table.filters["tags"].modify_filter(["a", "b"])
    # row 1 contains both values but is listed once
    assert ids(table) == [0, 1, 5]
    assert table.server_items_length == 3


def test_list_filter_with_columns_repr():
    df = pl.LazyFrame({"id": [0, 1, 2], "tags": [["a"], ["a", "b"], ["c"]]})
    repr_ = pl.LazyFrame({"tags": ["a", "b", "c"], "tags__repr": ["A", "B", "C"]})
    table = Table(df=df, columns_repr={"tags": repr_}, items_per_page=-1)
    f = open_filter(table, "tags")
    assert sorted(r["tags"] for r in f.filter_obj.items) == ["A", "B", "C"]
    f.modify_filter(["c"])
    assert ids(table) == [2]


def test_list_filter_combined_with_other_filter(df):
    table = Table(df=df, items_per_page=-1)
    table.filters["cat"].modify_filter(["x"])
    table.filters["tags"].modify_filter(["a", "b"])
    assert ids(table) == [0, 5]


def test_null_selection_survives_df_change(df):
    table = Table(df=df, items_per_page=-1)
    table.filters["name"].modify_filter([None, "Tom"])
    assert ids(table) == [0, 4]
    table.df = df.with_columns(pl.col("id") + 10)
    assert ids(table) == [10, 14]
