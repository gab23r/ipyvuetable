import base64
import io

import polars as pl
import pytest
from conftest import assert_json_serializable

from ipyvuetable import Table
from ipyvuetable.table import Event

requires_ipyevents = pytest.mark.skipif(Event is None, reason="shift click needs the ipyevents extra")


def options(page=1, items_per_page=10, sort_by=(), sort_desc=()):
    """Payload sent by the frontend on `update:options`."""
    return {
        "page": page,
        "itemsPerPage": items_per_page,
        "sortBy": list(sort_by),
        "sortDesc": list(sort_desc),
    }


def ids(table: Table, col: str = "id") -> list:
    return [row[col] for row in table.items]


def select(table: Table, rows: list[dict]):
    # what the frontend does when rows are (un)checked
    table.v_model = rows


# --- construction ---------------------------------------------------------------------------------


def test_default_empty_table():
    table = Table()
    assert table.items == []
    assert not table.headers


def test_empty_table_with_schema():
    table = Table(df=pl.LazyFrame(schema={"a": pl.Int64, "b": pl.String}))
    assert table.items == []
    assert [h["value"] for h in table.headers] == ["a", "b"]


def test_all_dtypes_are_json_serializable(df):
    table = Table(df=df, items_per_page=-1)
    assert len(table.items) == 6
    assert_json_serializable(table.items)


def test_eager_dataframe_is_accepted(df):
    table = Table(df=df.collect())
    assert len(table.items) == 6


def test_row_nr_column_in_input_is_ignored(df):
    table = Table(df=df.with_row_index("__row_nr__", offset=100))
    assert table.items[0]["__row_nr__"] == 0


def test_boolean_repr(df):
    table = Table(df=df, items_per_page=-1)
    assert [r["flag"] for r in table.items] == ["✅", "✅", "❌", "✅", "❌", None]


def test_temporal_repr(df):
    table = Table(df=df, items_per_page=-1)
    first = table.items[0]
    assert first["birthday"] == "1995-03-01 10:30:00.000000"
    assert first["day"] == "2020-01-01"
    assert first["duration"] == "1h"


def test_columns_to_hide(df):
    table = Table(df=df, columns_to_hide=["id", "tags"])
    assert "id" not in [h["value"] for h in table.headers]
    assert "tags" not in [h["value"] for h in table.headers]
    # hidden columns are still available in items (used for item_key, ...)
    assert "id" in table.items[0]


def test_columns_to_hide_via_menu(df):
    table = Table(df=df)
    menu = table.actions["select_column"]["obj"]
    table.columns_to_display_table.v_model = [{"col": "id"}, {"col": "name"}]
    menu.v_model = True
    menu.v_model = False
    assert [h["value"] for h in table.headers] == ["id", "name"]


# --- pagination -----------------------------------------------------------------------------------


def test_pagination(big_df):
    table = Table(df=big_df)
    assert ids(table) == list(range(10))
    table.fire_event("update:options", options(page=3))
    assert ids(table) == list(range(20, 30))
    table.fire_event("update:options", options(page=2, items_per_page=25))
    assert ids(table) == list(range(25, 50))


def test_pagination_all(df):
    table = Table(df=df)
    table.fire_event("update:options", options(items_per_page=-1))
    assert len(table.items) == 6


def test_pagination_past_the_end(df):
    table = Table(df=df)
    table.fire_event("update:options", options(page=10))
    assert table.items == []


# --- sorting --------------------------------------------------------------------------------------


def test_sort(df):
    table = Table(df=df, items_per_page=-1)
    table.fire_event("update:options", options(items_per_page=-1, sort_by=["score"], sort_desc=[False]))
    # nulls last
    assert ids(table) == [3, 0, 1, 4, 2, 5]
    table.fire_event("update:options", options(items_per_page=-1, sort_by=["score"], sort_desc=[True]))
    assert ids(table) == [2, 4, 1, 0, 3, 5]


def test_sort_is_stable(big_df):
    table = Table(df=big_df)
    table.fire_event("update:options", options(sort_by=["grp"], sort_desc=[True]))
    assert ids(table) == [i for i in range(50_000) if i % 7 == 6][:10]


def test_multi_sort(df):
    table = Table(df=df, items_per_page=-1)
    table.fire_event(
        "update:options", options(items_per_page=-1, sort_by=["cat", "id"], sort_desc=[False, True])
    )
    assert ids(table) == [5, 2, 0, 4, 1, 3]


def test_unsort_restores_original_order(df):
    table = Table(df=df, items_per_page=-1)
    table.fire_event("update:options", options(items_per_page=-1, sort_by=["score"], sort_desc=[True]))
    table.fire_event("update:options", options(items_per_page=-1))
    assert ids(table) == list(range(6))


def test_sort_on_column_removed_by_df_change(df):
    table = Table(df=df, items_per_page=-1)
    table.fire_event("update:options", options(items_per_page=-1, sort_by=["score"], sort_desc=[True]))
    table.df = df.drop("score")
    assert ids(table) == list(range(6))


def test_sort_by_column_with_repr_sorts_on_raw_value():
    df = pl.LazyFrame({"k": [2, 1, 3]})
    repr_ = pl.LazyFrame({"k": [1, 2, 3], "k__repr": ["c", "b", "a"]})
    table = Table(df=df, columns_repr={"k": repr_})
    table.fire_event("update:options", options(sort_by=["k"], sort_desc=[False]))
    assert ids(table, "k") == ["c", "b", "a"]


# --- columns_repr ---------------------------------------------------------------------------------


def test_columns_repr(df):
    repr_ = pl.LazyFrame({"cat": ["x", "y"], "cat__repr": ["X!", "Y!"]})
    table = Table(df=df, columns_repr={"cat": repr_}, items_per_page=-1)
    # unmapped values fall back to their raw value
    assert ids(table, "cat") == ["X!", "Y!", "X!", "z", "Y!", "X!"]


def test_columns_repr_keeps_row_order(big_df):
    repr_ = pl.LazyFrame({"grp": list(range(7)), "grp__repr": [f"g{i}" for i in range(7)]})
    table = Table(df=big_df, columns_repr={"grp": repr_}, items_per_page=100)
    for page in (1, 50, 500):
        table.fire_event("update:options", options(page=page, items_per_page=100))
        expected = list(range((page - 1) * 100, page * 100))
        assert ids(table) == expected
        assert ids(table, "grp") == [f"g{i % 7}" for i in expected]


def test_columns_repr_for_missing_column_is_ignored(df):
    repr_ = pl.LazyFrame({"nope": [1], "nope__repr": ["one"]})
    table = Table(df=df, columns_repr={"nope": repr_})
    assert len(table.items) == 6


# --- selection ------------------------------------------------------------------------------------


def test_selection(df):
    table = Table(df=df, item_key="id", show_select=True)
    select(table, table.items[1:3])
    assert table.selected_keys == [1, 2]
    assert table.nb_selected == 2
    assert table.df_selected.collect()["id"].to_list() == [1, 2]
    assert table.unselect.disabled is False

    table.unselect.fire_event("click", None)
    assert table.v_model == []
    assert table.nb_selected == 0
    assert table.selected_keys == []
    assert table.unselect.disabled is True


def test_selection_realigned_on_df_change(df):
    table = Table(df=df, item_key="id", show_select=True)
    select(table, [r for r in table.items if r["id"] in (3, 4)])
    # rows move: id 3 and 4 are now at the top
    table.df = df.sort("id", descending=True)
    assert table.selected_keys == [4, 3]
    assert sorted(r["__row_nr__"] for r in table.v_model) == [1, 2]
    assert sorted(table.df_selected.collect()["id"].to_list()) == [3, 4]


def test_selection_dropped_on_df_change_without_item_key(df):
    table = Table(df=df, show_select=True)
    select(table, table.items[:2])
    table.df = df
    assert table.v_model == []
    assert table.nb_selected == 0


def test_selection_key_removed_by_df_change(df):
    table = Table(df=df, item_key="id", show_select=True)
    select(table, table.items[:2])
    table.df = df.filter(pl.col("id") != 0)
    assert table.selected_keys == [1]


def test_filter_on_selected(df):
    table = Table(df=df, item_key="id", show_select=True)
    select(table, [table.items[1], table.items[4]])
    btn = table.actions["filter_on_selected"]["obj"]
    btn.fire_event("click", None)
    assert ids(table) == [1, 4]
    btn.fire_event("click", None)
    assert ids(table) == list(range(6))


# --- download -------------------------------------------------------------------------------------


def downloaded(table: Table) -> pl.DataFrame:
    table.download_btn.fire_event("click", None)
    attributes = table.download_btn.attributes
    assert attributes["download"] == f"{table.title}.parquet"
    header, payload = attributes["href"].split(",", 1)
    assert header == "data:application/vnd.apache.parquet;base64"
    return pl.read_parquet(io.BytesIO(base64.b64decode(payload)))


def test_download(df):
    table = Table(df=df, title="t")
    # every dtype round-trips, including lists, durations and nulls
    assert downloaded(table).equals(df.collect())
    # second click resets the button
    table.download_btn.fire_event("click", None)
    assert table.payload is None
    assert table.download_btn.attributes == {}


def test_download_deeply_nested():
    df = pl.LazyFrame({"ll": [[[1], [2, 3]]], "s": [{"a": 1}]})
    assert downloaded(Table(df=df, title="t")).equals(df.collect())


def test_download_ignores_filters_and_sort(df):
    table = Table(df=df, title="t")
    table.filters["cat"].modify_filter(["x"])
    table.fire_event("update:options", options(sort_by=["score"], sort_desc=[True]))
    assert downloaded(table).equals(df.collect())


# --- misc -----------------------------------------------------------------------------------------


def test_custom_actions_and_hidden_actions(df):
    class MyTable(Table):
        def _get_custom_actions(self):
            import ipyvuetify as v

            return {"hello": {"obj": v.Btn(children=["hi"])}}

    table = MyTable(df=df, actions_to_hide="*")
    assert len(table.items) == 6


def test_toggle_multi_sort(df):
    table = Table(df=df)
    btn = table.actions["multi_sort"]["obj"]
    assert not table.multi_sort
    btn.fire_event("click", None)
    assert table.multi_sort
    assert btn.color == "primary"


def test_height_follows_rows(df):
    table = Table(df=df, max_height=100)
    assert table.height == 100
    table = Table(df=df.head(1), max_height=500)
    assert table.height is None


def test_df_change_keeps_working_filters(df):
    table = Table(df=df, items_per_page=-1)
    f = table.filters["cat"]
    f.menu.v_model = True
    f.modify_filter(["x"])
    f.menu.v_model = False
    assert ids(table) == [0, 2, 5]
    table.df = df.with_columns(pl.col("id") + 10)
    assert ids(table) == [10, 12, 15]


@requires_ipyevents
def test_shift_click_selects_range(df):
    table = Table(df=df, item_key="id", show_select=True, items_per_page=-1)
    select(table, [table.items[1]])
    table.event = {"shiftKey": True}
    select(table, [table.items[1], table.items[4]])
    assert sorted(table.selected_keys) == [1, 2, 3, 4]
    assert table.nb_selected == 4
    # a new click without shift does not extend the selection
    table.event = {}
    select(table, [*table.v_model, table.items[0]])
    assert table.nb_selected == 5


@requires_ipyevents
def test_shift_click_follows_sort(df):
    table = Table(df=df, item_key="id", show_select=True, items_per_page=-1)
    table.fire_event("update:options", options(items_per_page=-1, sort_by=["score"], sort_desc=[False]))
    # sorted ids: [3, 0, 1, 4, 2, 5]
    first, last = table.items[0], table.items[3]
    select(table, [first])
    table.event = {"shiftKey": True}
    select(table, [first, last])
    assert sorted(table.selected_keys) == [0, 1, 3, 4]


def test_programmatic_selection(df):
    table = Table(df=df, item_key="id", show_select=True)
    table.v_model = table.items[:3]
    assert table.nb_selected == 3
    assert table.selected_keys == [0, 1, 2]
    table.df = df.sort("id", descending=True)
    assert sorted(table.df_selected.collect()["id"].to_list()) == [0, 1, 2]


@requires_ipyevents
def test_shift_click_does_bookkeeping_once(df):
    table = Table(df=df, item_key="id", show_select=True, items_per_page=-1)
    select(table, [table.items[1]])
    calls = []
    original = table._get_selected_keys
    table._get_selected_keys = lambda: calls.append(1) or original()
    table.event = {"shiftKey": True}
    select(table, [table.items[1], table.items[4]])
    # one call for the click, one after adding the rows in between; the nested notification is skipped
    assert len(calls) == 2
    assert table.selected_keys == [1, 2, 3, 4]
    assert table.last_selected_key == 4


@pytest.mark.parametrize("cls", ["Table", "EditingTable"])
def test_slots_are_in_initial_state(monkeypatch, df, cls):
    # slots received by the frontend after the first render are never displayed
    import ipywidgets

    import ipyvuetable

    initial_slots = {}
    original_open = ipywidgets.Widget.open

    def open_(self):
        if isinstance(self, ipyvuetable.Table):
            initial_slots[id(self)] = self.get_state().get("v_slots")
        original_open(self)

    monkeypatch.setattr(ipywidgets.Widget, "open", open_)
    table = getattr(ipyvuetable, cls)(df=df, title="t")
    slots = initial_slots[id(table)]
    assert [slot["name"] for slot in slots] == ["top", "body.prepend"]
