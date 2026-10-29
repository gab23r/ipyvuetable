import datetime

import polars as pl
import pytest
from conftest import assert_json_serializable

from ipyvuetable import EditingTable


def select(table: EditingTable, keys: list):
    rows = [r for r in table.df.collect().to_dicts() if r[table.item_key] in keys]
    rows = [{table.row_nr: r[table.row_nr], table.item_key: r[table.item_key]} for r in rows]
    table.v_model = rows


def rows(table: EditingTable) -> list[dict]:
    return table.df.drop(table.row_nr).collect().to_dicts()


def save(table: EditingTable, **values):
    for col, value in values.items():
        table.dialog_widgets[col].v_model = value
    table.save_btn.fire_event("click", None)


@pytest.fixture
def table(df) -> EditingTable:
    return EditingTable(df=df, item_key="id", show_select=True)


def test_action_status(table):
    assert table.actions["edit"]["obj"].disabled
    select(table, [1])
    assert not table.actions["edit"]["obj"].disabled
    assert not table.actions["duplicate"]["obj"].disabled
    assert not table.actions["delete"]["obj"].disabled
    select(table, [1, 2])
    assert table.actions["duplicate"]["obj"].disabled


def test_delete(table):
    select(table, [1, 3])
    table.actions["delete"]["obj"].vue_on_click(None)
    assert [r["id"] for r in rows(table)] == [0, 2, 4, 5]
    assert table.df.collect()[table.row_nr].to_list() == [0, 1, 2, 3]
    assert table.v_model == []
    assert table.nb_selected == 0
    assert table.actions["delete"]["obj"].disabled


def test_delete_keeps_order_on_big_frame(big_df):
    table = EditingTable(df=big_df, item_key="id", show_select=True)
    select(table, [5, 7])
    table.actions["delete"]["obj"].vue_on_click(None)
    assert table.df.collect()["id"].to_list() == [i for i in range(50_000) if i not in (5, 7)]


def test_delete_everything(table):
    select(table, list(range(6)))
    table.actions["delete"]["obj"].vue_on_click(None)
    assert table.items == []


def test_edit_dialog_prefill(table):
    select(table, [0])
    table.actions["edit"]["obj"].fire_event("click", None)
    w = table.dialog_widgets
    assert table.dialog.v_model is True
    assert w["name"].v_model == "Tom"
    assert w["birthday"].v_model == "1995-03-01T10:30"
    assert w["day"].v_model == "2020-01-01"
    assert w["duration"].v_model == "1:0:0"
    assert w["tags"].v_model == ["a"]
    assert w["flag"].v_model is True


def test_edit_every_dtype(table):
    select(table, [0])
    table.actions["edit"]["obj"].fire_event("click", None)
    save(
        table,
        name="Tommy",
        score="9.25",
        flag=False,
        birthday="2000-02-03T04:05",
        day="2021-12-31",
        duration="1:02:03",
        tags=["z", "y"],
    )
    row = rows(table)[0]
    assert row == {
        "id": 0,
        "name": "Tommy",
        "score": 9.25,
        "flag": False,
        "birthday": datetime.datetime(2000, 2, 3, 4, 5),
        "day": datetime.date(2021, 12, 31),
        "duration": datetime.timedelta(hours=1, minutes=2, seconds=3),
        "tags": ["z", "y"],
        "cat": "x",
    }
    # the rest is untouched
    assert [r["id"] for r in rows(table)] == list(range(6))
    assert_json_serializable(table.new_items)
    assert table.previous_items[0]["name"] == "Tom"


def test_edit_set_values_to_null(table):
    select(table, [0])
    table.actions["edit"]["obj"].fire_event("click", None)
    save(table, name=None, score=None, birthday=None, day=None, duration=None)
    row = rows(table)[0]
    assert row["name"] is None
    assert row["score"] is None
    assert row["birthday"] is None


def test_edit_integer_column(table):
    select(table, [2])
    table.actions["edit"]["obj"].fire_event("click", None)
    save(table, id="42")
    assert rows(table)[2]["id"] == 42


def test_edit_invalid_temporal_values_become_null(table):
    select(table, [0])
    table.actions["edit"]["obj"].fire_event("click", None)
    save(table, birthday="garbage", day="garbage", duration="garbage")
    row = rows(table)[0]
    assert (row["birthday"], row["day"], row["duration"]) == (None, None, None)


def test_multi_edit_only_touches_filled_fields(table):
    select(table, [0, 1])
    table.actions["edit"]["obj"].fire_event("click", None)
    w = table.dialog_widgets
    # values that differ are left blank
    assert w["name"].v_model is None
    assert w["cat"].v_model is None
    save(table, cat="new")
    out = rows(table)
    assert [r["cat"] for r in out[:2]] == ["new", "new"]
    assert [r["name"] for r in out[:2]] == ["Tom", "Joseph"]
    assert out[2]["cat"] == "x"


def test_create(table):
    table.actions["new"]["obj"].fire_event("click", None)
    save(table, id="6", name="New", score="1.5", flag=True, tags=["q"])
    out = rows(table)
    assert len(out) == 7
    assert out[-1]["id"] == 6
    assert out[-1]["name"] == "New"
    assert out[-1]["tags"] == ["q"]
    assert out[-1]["birthday"] is None


def test_create_bool_defaults_to_false(table):
    table.actions["new"]["obj"].fire_event("click", None)
    save(table, id="6")
    assert rows(table)[-1]["flag"] is False


def test_create_with_default_values(df):
    class MyTable(EditingTable):
        def get_default_new_item(self):
            return {"cat": "default", "name": "ignored"}

    table = MyTable(df=df, item_key="id", default_dialog_values={"score": 2.0})
    table.actions["new"]["obj"].fire_event("click", None)
    assert table.dialog_widgets["score"].v_model == 2.0
    save(table, id="6", name="mine")
    row = rows(table)[-1]
    assert (row["cat"], row["name"], row["score"]) == ("default", "mine", 2.0)


def test_create_on_empty_table():
    table = EditingTable(df=pl.LazyFrame(schema={"id": pl.Int64, "name": pl.String}), item_key="id")
    table.actions["new"]["obj"].fire_event("click", None)
    save(table, id="1", name="first")
    assert rows(table) == [{"id": 1, "name": "first"}]


def test_duplicate(table):
    select(table, [2])
    table.actions["duplicate"]["obj"].fire_event("click", None)
    assert table.dialog_widgets["name"].v_model == "Krish"
    save(table, id="10")
    out = rows(table)
    assert len(out) == 7
    assert out[-1] | {"id": 2} == out[2]


def test_edit_with_columns_repr(df):
    repr_ = pl.LazyFrame({"cat": ["x", "y", "z"], "cat__repr": ["X!", "Y!", "Z!"]})
    table = EditingTable(df=df, item_key="id", columns_repr={"cat": repr_})
    select(table, [0])
    table.actions["edit"]["obj"].fire_event("click", None)
    widget = table.dialog_widgets["cat"]
    assert widget.v_model == "x"
    assert widget.textfield.v_model == "X!"
    widget.v_model = "z"
    table.save_btn.fire_event("click", None)
    assert rows(table)[0]["cat"] == "z"
    assert table.items[0]["cat"] == "Z!"


def test_edit_list_column_with_columns_repr():
    df = pl.LazyFrame({"id": [0, 1], "tags": [["a"], ["a", "b"]]})
    repr_ = pl.LazyFrame({"tags": ["a", "b"], "tags__repr": ["A", "B"]})
    table = EditingTable(df=df, item_key="id", columns_repr={"tags": repr_})
    select(table, [1])
    table.actions["edit"]["obj"].fire_event("click", None)
    widget = table.dialog_widgets["tags"]
    assert sorted(widget.v_model) == ["a", "b"]
    widget.v_model = ["b"]
    table.save_btn.fire_event("click", None)
    assert rows(table)[1]["tags"] == ["b"]


def test_edit_float_list():
    df = pl.LazyFrame({"id": [0], "xs": [[1.5, 2.5]]})
    table = EditingTable(df=df, item_key="id")
    select(table, [0])
    table.actions["edit"]["obj"].fire_event("click", None)
    save(table, xs=["1.25", "3"])
    assert rows(table)[0]["xs"] == [1.25, 3.0]


def test_edit_int_list():
    df = pl.LazyFrame({"id": [0], "xs": [[1, 2]]})
    table = EditingTable(df=df, item_key="id")
    select(table, [0])
    table.actions["edit"]["obj"].fire_event("click", None)
    save(table, xs=["4", "5"])
    assert rows(table)[0]["xs"] == [4, 5]


def test_hide_dialog_keys(df):
    table = EditingTable(df=df, item_key="id", hide_dialog_keys=["id"])
    table.actions["new"]["obj"].fire_event("click", None)
    assert "d-none" in (table.dialog_widgets["id"].class_ or "")


def test_edit_keeps_selection(table):
    select(table, [3])
    table.actions["edit"]["obj"].fire_event("click", None)
    save(table, name="Johnny")
    assert table.selected_keys == [3]
    assert table.df_selected.collect()["name"].to_list() == ["Johnny"]


def test_edit_after_filter(table):
    f = table.filters["cat"]
    f.menu.v_model = True
    f.modify_filter(["y"])
    f.menu.v_model = False
    select(table, [4])
    table.actions["edit"]["obj"].fire_event("click", None)
    save(table, name="Edited")
    # filter is still applied after the df change
    assert [r["id"] for r in table.items] == [1, 4]
    assert rows(table)[4]["name"] == "Edited"


def test_autocomplete_menu_in_dialog_makes_room(df):
    repr_ = pl.LazyFrame({"cat": ["x", "y", "z"], "cat__repr": ["X!", "Y!", "Z!"]})
    table = EditingTable(df=df, item_key="id", columns_repr={"cat": repr_})
    table.actions["new"]["obj"].fire_event("click", None)
    menu = table.dialog_widgets["cat"].menu
    menu.v_model = True
    assert "ipyvuetable--menu-large" in table.class_.split()
    menu.v_model = False
    assert "ipyvuetable--menu-large" not in (table.class_ or "").split()
