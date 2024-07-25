from typing import Any, cast

import ipyvuetify as v
import polars as pl

from ipyvuetable.table import Table
from ipyvuetify.extra.file_input import FileInput as _FileInput


class VirtualAutocomplete(v.Content):
    """
    Class that creates a custom widget made to select a value out of several possibilities
    It combines a v.TextField with a Table in a Menu display fashion
    Clicking on the text field opens a table, an item can be selected and will be reported in a
    readable way in the text field. The widget is able to communicate the index of the selected value
    for its later usage
    """

    def __init__(self, name, df, **kwargs):
        self.name = name
        self.textfield = v.TextField(
            v_model=None,
            placeholder="Please select a value",
            label=self.name,
            readonly=True,
            v_on="menus.on",
            v_bind="menus.attrs",
        )
        kwargs["show_select"] = True
        kwargs["show_actions"] = False
        self.table_select = Table(df=df, **kwargs)
        self.menu = v.Menu(
            close_on_content_click=False,
            transition="scale-transition",
            v_slots=[
                {
                    "name": "activator",
                    "variable": "menus",
                    "children": self.textfield,
                }
            ],
            children=[v.Card(children=[self.table_select])],
        )

        super().__init__(class_="pa-0", children=[self.menu])

        self.menu.on_event("input", self._on_menu_toggled)

    @property
    def v_model(self):
        v_model: list[Any] | None = [
            item[self.table_select.item_key] for item in self.table_select.v_model
        ]
        if self.table_select.single_select:
            if v_model:
                v_model = v_model[0]
            else:
                v_model = None
        return v_model

    @v_model.setter
    def v_model(self, value):
        self.table_select.v_model = (
            self.table_select.df.filter(
                pl.col(self.name + "__key").is_in(pl.lit(value))
            )
            .select(self.table_select.item_key)
            .collect()
            .to_dicts()
        )
        self._update_text_field()

    def _on_menu_toggled(self, widget, event, data):
        if not data:  # Menu is close
            self._update_text_field()

    def _update_text_field(self):
        values = (
            self.table_select.df_selected.select(self.name)
            .collect()[self.name]
            .to_list()
        )
        self.textfield.v_model = ", ".join(values) if values else None


class FileInput(v.Flex):
    def __init__(self, name, **kwargs):
        self.name = name
        self.file_input = _FileInput()
        super().__init__(
            children=[
                v.Html(tag="div", children=[name]),  # type: ignore
                self.file_input,
            ],
            **kwargs,
        )

    @property
    def v_model(self) -> str | None:
        file_info = next(iter(self.file_input.file_info), {})
        return file_info.get("name")

    @v_model.setter
    def v_model(self, value): ...  # it is not possible to modify v_model from the back

    def load_dataframes(self) -> list[pl.DataFrame]:
        dfs = []
        for file_info in self.file_input.get_files():
            extension = file_info["name"].split(".")[-1]
            bytes_data = cast(bytes, file_info["file_obj"].readall())
            match extension:
                case "json":
                    data = pl.read_json(bytes_data)
                case "csv":
                    data = pl.read_csv(bytes_data)
                case "parquet":
                    data = pl.read_parquet(bytes_data)
                case ("xlsx", "xls"):
                    data = pl.read_excel(bytes_data)
                case _:
                    raise Exception(f"Extension {extension} is not supported, ")

            dfs.append(data)

        return dfs
