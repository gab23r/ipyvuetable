import ipyvuetify as v
import polars as pl

import ipyvuetable


class Filter:
    def __init__(self, name, table):
        self.table: ipyvuetable.Table = table
        self.name: str = name
        self.mask: pl.LazyFrame | None = None
        self.is_initialized = False

        self.filter_icon = v.Icon(
            v_bind="menus.attrs", v_on="menus.on", children=["mdi-filter"], color="grey"
        )
        self.card = v.Card()
        self.menu = v.Menu(
            v_model=False,
            close_on_content_click=False,
            # style_="width: 30%",  # background-color: white
            transition="scale-transition",
            offset_y=True,
            children=[self.card],
            v_slots=[
                {"name": "activator", "variable": "menus", "children": self.filter_icon}
            ],
        )

        self.menu.observe(self._update_selection, "v_model")

    def _update_mask(self): ...

    def _update_filter(self): ...

    def init_filter(self):
        self.is_initialized = True

    def apply_mask(self):
        self._update_mask()
        self.filter_icon.color = "grey" if self.mask is None else "primary"
        self.table._apply_filters()

    def _update_selection(self, change):
        if change["new"]:  # menu is open
            if not self.is_initialized:
                self.init_filter()
                self._update_filter()
        else:  # Menu is close
            self.apply_mask()

    def _undo(self):
        self.filter_icon.color = "grey"
        self.mask = None
