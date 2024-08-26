import datetime
from typing import Any

import ipyvuetify as v
import polars as pl
import traitlets as t
from ipyvuetify import VuetifyWidget

import ipyvuetable.utils as utils
from ipyvuetable.table import Table
from ipyvuetable.widgets import FileInput, VirtualAutocomplete


DialogWidget = VuetifyWidget | FileInput | VirtualAutocomplete


class EditingTable(Table):
    default_dialog_values: dict[str, Any] = {}
    new_items: list[dict[str, Any]] = t.List(
        t.Dict({}), default_value=[{}], allow_none=True
    ).tag(sync=True)  # type: ignore

    def __init__(
        self,
        df: pl.LazyFrame = pl.LazyFrame(),
        hide_dialog_keys: list[str] = [],
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(df, *args, **kwargs)

        self.save_btn = v.Btn(children=["Save"], color="blue darken-1")

        # instantiate the dialog widgets on demand
        self.dialog_widgets: dict[str, DialogWidget] = {}
        self.dialog_values: dict[str, Any] = {}
        self.hide_dialog_keys = hide_dialog_keys
        self.dialog_widgets_container = v.Col()
        self.dialog.children = [
            v.Card(
                children=[
                    v.CardTitle(children=["Edit Item"]),
                    v.CardText(children=[self.dialog_widgets_container]),
                    v.CardActions(children=[v.Spacer(), self.save_btn]),
                ]
            )
        ]

        self.save_btn.on_event("click", self._on_save_dialog)

    def _on_input_table(self, widget, event, data):
        super()._on_input_table()

    def _on_click_edit_item_btn(self, widget, event, data):
        self.dialog_values = {}
        for col, values in self.df_selected.collect().to_dict(as_series=False).items():
            if col == self.row_nr:
                self.dialog_values[col] = values
            elif (
                len(values) == 1
                or len(set(str(v) for v in values)) == 1
                and values[0] is not None
            ):
                self.dialog_values[col] = values[0]
        self._show_dialog()

    def _on_click_new_item_btn(self, widget, event, data):
        self.dialog_values = self.default_dialog_values
        self._show_dialog()

    def _on_click_duplicate_item_btn(self, widget, event, data):
        self.dialog_values = self.df_selected.collect().to_dicts()[0]
        del self.dialog_values[self.row_nr]
        self._show_dialog()

    def _on_click_delete_btn(self, *args):
        self.df = self.df.join(self.df_selected, how="anti", on=self.row_nr)
        self.v_model = []

    def _on_save_dialog(self, widget, event, data):
        self.dialog.v_model = False

        indexes: list[int] | None = self.dialog_values.get(self.row_nr)
        new_item: dict[str, Any] = {
            c: widget.v_model
            for c, widget in self.dialog_widgets.items()
            if indexes is None  # In case of click_new
            or len(indexes) == 1  # In case of click_edit one element
            or len(indexes) > 1
            and widget.v_model is not None  # In case of click_edit multiple elements
        }
        for c, value in new_item.items():
            dtype = self.schema[c]
            # special case of new bool
            # Null is considered False
            if isinstance(dtype, pl.Boolean) and indexes is None:
                new_item[c] = value is True
            if value is not None:
                if dtype in pl.FLOAT_DTYPES:
                    new_item[c] = float(value)
                elif dtype in pl.NUMERIC_DTYPES:
                    new_item[c] = int(value)
                elif isinstance(dtype, pl.List):
                    if dtype.inner in pl.NUMERIC_DTYPES:
                        new_item[c] = [int(i) for i in value]
                    elif dtype.inner in pl.FLOAT_DTYPES:
                        new_item[c] = [float(i) for i in value]
                    else:
                        new_item[c] = value
                elif isinstance(dtype, pl.Datetime):
                    try:
                        date_time = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M")
                    except ValueError:
                        date_time = None
                    new_item[c] = date_time
                elif isinstance(dtype, pl.Duration):
                    try:
                        hours, minutes, *seconds = value.split(":")
                        seconds = int(seconds[0]) if seconds else 0
                        duration = datetime.timedelta(
                            hours=int(hours), minutes=int(minutes), seconds=seconds
                        )
                        print(duration)
                    except ValueError:
                        duration = None
                    new_item[c] = duration
                elif isinstance(dtype, pl.Date):
                    try:
                        date = datetime.datetime.strptime(value, "%Y-%m-%d")
                    except ValueError:
                        date = None
                    new_item[c] = date

        # we use default_new_item only for creation not edition
        if indexes is None:
            default_new_item = {
                k: v
                for k, v in self.get_default_new_item().items()
                if new_item.get(k) is None
            }
        else:
            default_new_item = {}

        new_item_df = (
            pl.LazyFrame([new_item | default_new_item])
            # .with_columns(**default_new_item)
            .cast({k: v for k, v in self.schema.items() if k in new_item})
            .join(
                pl.LazyFrame(indexes or [None], schema={self.row_nr: pl.UInt32}).join(
                    self.df_selected.select({self.item_key, self.row_nr}),
                    how="left",
                    on=self.row_nr,
                ),
                how="cross",
            )
            .pipe(lambda d: d.select([c for c in self.df.collect_schema().names() if c in d.columns]))
        )
        self.previous_items = self.df_selected.collect().rows_by_key(
            self.item_key, unique=True, named=True
        )
        self.new_items = new_item_df.pipe(self.jsonify).collect().to_dicts()

        self.df_updated_rows = new_item_df.update(
            new_item_df.cast(
                {k: v for k, v in self.schema.items() if k in new_item}
            ).cast({self.row_nr: pl.UInt32})
        )

        if indexes is not None:
            self.df = self.df.update(
                self.df_updated_rows, on=self.row_nr, include_nulls=True
            )
        else:
            self.df = pl.concat([self.df, self.df_updated_rows])

    def _get_dialog_widgets(self) -> dict[str, DialogWidget]:
        dialog_widgets = {}
        for col, dtype in self.schema.items():
            column_repr = self.columns_repr.get(col)
            if column_repr is not None:
                single_select = not isinstance(dtype, pl.List)
                column_repr = (
                    column_repr.select(
                        [pl.col(col).name.suffix("__key"), pl.col(f"{col}__repr").alias(col)]
                    )
                    # https://github.com/pola-rs/polars/issues/10982
                    .collect()
                    .lazy()
                )
                widget = VirtualAutocomplete(
                    col,
                    column_repr,
                    single_select=single_select,
                    item_key=f"{col}__key",
                    columns_to_hide=[f"{col}__key"],
                )
            elif col.lower().endswith("_file"):
                widget = FileInput(name=col)
            else:
                if isinstance(dtype, pl.List):
                    widget = v.Combobox(
                        v_model=[],
                        multiple=True,
                        small_chips=True,
                        deletable_chips=True,
                    )
                elif isinstance(dtype, pl.Boolean):
                    widget = v.Checkbox(v_model=None)
                elif isinstance(dtype, pl.Datetime):
                    widget = v.TextField(v_model=None, type="datetime-local")
                elif isinstance(dtype, pl.Date):
                    widget = v.TextField(v_model=None, type="date")
                elif dtype in pl.NUMERIC_DTYPES:
                    widget = v.TextField(v_model=None, type="number")
                else:
                    widget = v.TextField(v_model=None)

                widget.dense = True
                widget.label = col

            dialog_widgets[col] = widget

            if col in self.hide_dialog_keys and not isinstance(
                widget, FileInput
            ):  # hide is not available for FileInput
                widget.hide()

        return dialog_widgets

    def get_default_new_item(self) -> dict[str, Any]:
        return {}

    def _show_dialog(self):
        # init the dialog widget the first time
        if not self.dialog_widgets:
            self.dialog_widgets = self._get_dialog_widgets()
            self.dialog_widgets_container.children = list(self.dialog_widgets.values())

        for c, widget in self.dialog_widgets.items():
            dtype = self.schema[c]
            value = self.dialog_values.get(c)
            if isinstance(dtype, pl.Datetime):
                widget.v_model = value.strftime("%Y-%m-%dT%H:%M") if value else None
            elif isinstance(dtype, pl.Date):
                widget.v_model = value.strftime("%Y-%m-%d") if value else None
            elif isinstance(dtype, pl.Duration):
                if value is not None:
                    total_seconds = value.total_seconds()  # type: ignore
                    widget.v_model = f"{int(total_seconds // 3600)}:{int(total_seconds % 3600 // 60)}:{int(total_seconds % 60)}"
                else:
                    widget.v_model = None
            else:
                widget.v_model = self.dialog_values.get(c)

        self.dialog.v_model = True

    def _get_actions(self):
        actions = super()._get_actions()
        actions["delete"] = {
            "obj": utils.IconAlert(
                "mdi-delete",
                "Delete items",
                "Are you sure you want to delete these items ?",
                disabled=True,
                color="primary",
            ),
            "tooltip": "Delete items",
        }

        actions["edit"] = {
            "obj": v.Icon(children=["mdi-pencil"], color="primary", disabled=True),
            "tooltip": "Edit items",
        }

        actions["duplicate"] = {
            "obj": v.Icon(
                children=["mdi-content-copy"], color="primary", disabled=True
            ),
            "tooltip": "Duplicate item",
        }

        actions["new"] = {
            "obj": v.Icon(children=["mdi-plus-box"], disabled=False, color="primary"),
            "tooltip": "Add new item",
        }

        actions["edit"]["obj"].on_event("click", self._on_click_edit_item_btn)
        actions["new"]["obj"].on_event("click", self._on_click_new_item_btn)
        actions["duplicate"]["obj"].on_event("click", self._on_click_duplicate_item_btn)
        actions["delete"]["obj"].on_event("click", self._on_click_delete_btn)

        return actions

    def _update_action_status(self):
        super()._update_action_status()
        self.actions["delete"]["obj"].disabled = self.nb_selected < 1
        self.actions["edit"]["obj"].disabled = self.nb_selected < 1
        self.actions["duplicate"]["obj"].disabled = self.nb_selected != 1
