"""Random filter / sort / pagination / edit sequences checked against plain polars."""

import os
import random

import polars as pl
import pytest

from ipyvuetable import EditingTable


def make_df(rng: random.Random, n: int) -> pl.DataFrame:
    def maybe_null(value):
        return None if rng.random() < 0.1 else value

    return pl.DataFrame(
        {
            "id": list(range(n)),
            "grp": [maybe_null(rng.randint(0, 9)) for _ in range(n)],
            "val": [maybe_null(round(rng.uniform(0, 100), 1)) for _ in range(n)],
            "name": [maybe_null(rng.choice(["a", "b", "c", "d"])) for _ in range(n)],
            "tags": [maybe_null(rng.sample(["x", "y", "z"], rng.randint(0, 2))) for _ in range(n)],
        },
        schema={
            "id": pl.Int64,
            "grp": pl.Int64,
            "val": pl.Float64,
            "name": pl.String,
            "tags": pl.List(pl.String),
        },
    )


def present(df: pl.DataFrame, col: str, values: list | None) -> list | None:
    """like in the UI, only values present in the column can be selected; no value means no filter"""
    if values is None:
        return None
    if col == "tags":
        existing = set(df["tags"].explode().to_list())
    else:
        existing = set(df[col].to_list())
    values = [v for v in values if v in existing]
    return values or None


def expected_ids(df: pl.DataFrame, state: dict) -> list[int]:
    if state["grp"] is not None:
        values = [v for v in state["grp"] if v is not None]
        expr = pl.col("grp").is_in(values)
        if None in state["grp"]:
            expr |= pl.col("grp").is_null()
        df = df.filter(expr)
    if state["val"] is not None:
        df = df.filter(pl.col("val").is_between(*state["val"]))
    if state["tags"] is not None:
        df = df.filter(pl.col("tags").list.eval(pl.element().is_in(state["tags"])).list.any())
    if state["sort_by"]:
        df = df.sort(state["sort_by"], descending=state["sort_desc"], nulls_last=True, maintain_order=True)
    ids = df["id"].to_list()
    page, per_page = state["page"], state["items_per_page"]
    return ids if per_page == -1 else ids[(page - 1) * per_page : page * per_page]


@pytest.mark.parametrize("seed", range(int(os.environ.get("FUZZ_SEEDS", "25"))))
def test_random_operations(seed):
    rng = random.Random(seed)
    df = make_df(rng, rng.choice([1, 20, 3_000, 30_000]))
    table = EditingTable(df=df.lazy(), item_key="id", show_select=True)
    state = {
        "grp": None,
        "val": None,
        "tags": None,
        "sort_by": [],
        "sort_desc": [],
        "page": 1,
        "items_per_page": 10,
    }

    for _ in range(12):
        op = rng.choice(["grp", "val", "tags", "sort", "page", "undo", "edit", "delete"])
        if op == "grp":
            state["grp"] = rng.sample([*range(10), None], rng.randint(1, 4))
            table.filters["grp"].modify_filter(state["grp"])
            state["page"] = 1
        elif op == "val":
            low = rng.randint(0, 80)
            state["val"] = [low, low + rng.randint(1, 20)]
            f = table.filters["val"]
            f.menu.v_model = True
            f.filter_obj.v_model = state["val"]
            f.menu.v_model = False
            if state["val"] == [f.filter_obj.min, f.filter_obj.max]:
                state["val"] = None  # the full range means no filter
            state["page"] = 1
        elif op == "tags":
            state["tags"] = rng.sample(["x", "y", "z"], rng.randint(1, 2))
            table.filters["tags"].modify_filter(state["tags"])
            state["page"] = 1
        elif op == "sort":
            state["sort_by"] = rng.sample(["grp", "val", "name"], rng.randint(0, 2))
            state["sort_desc"] = [rng.random() < 0.5 for _ in state["sort_by"]]
        elif op == "page":
            state["items_per_page"] = rng.choice([5, 10, 50, -1])
            state["page"] = rng.randint(1, 5)
        elif op == "undo":
            table.actions["undo_filters"]["obj"].fire_event("click", None)
            state.update(grp=None, val=None, tags=None, page=1)
        elif op in ("edit", "delete") and table.items:
            row = rng.choice(table.items)
            table.v_model = [row]
            if op == "edit":
                new_val = round(rng.uniform(0, 100), 1)
                table.actions["edit"]["obj"].fire_event("click", None)
                table.dialog_widgets["val"].v_model = str(new_val)
                table.save_btn.fire_event("click", None)
                df = df.with_columns(
                    pl.when(pl.col("id") == row["id"]).then(new_val).otherwise(pl.col("val")).alias("val")
                )
            else:
                table.actions["delete"]["obj"].vue_on_click(None)
                df = df.filter(pl.col("id") != row["id"])
            table.v_model = []

        table.fire_event(
            "update:options",
            {
                "page": state["page"],
                "itemsPerPage": state["items_per_page"],
                "sortBy": state["sort_by"],
                "sortDesc": state["sort_desc"],
            },
        )
        # values whose last row was deleted are dropped from the filters
        state["grp"] = present(df, "grp", state["grp"])
        state["tags"] = present(df, "tags", state["tags"])
        got, exp = [r["id"] for r in table.items], expected_ids(df, state)
        assert got == exp, (op, state, got[:12], exp[:12], len(got), len(exp))
