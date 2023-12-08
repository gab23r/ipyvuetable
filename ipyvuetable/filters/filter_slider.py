import ipyvuetify as v
import polars as pl

from ipyvuetable.filters import Filter


class FilterSlider(Filter):
    def __init__(self, name, table, **kwargs):
        super().__init__(name, table, **kwargs)

    def init_filter(self):
        super().init_filter()
        self.max_field = v.TextField(
            v_model=None, class_="pa-2", label="max", type="number"
        )
        self.min_field = v.TextField(
            v_model=None, class_="pa-2", label="min", type="number"
        )
        self.undo_icon = v.Icon(children=["mdi-undo-variant"], color="grey")
        self.filter_obj = v.RangeSlider(v_model=None, class_="align-center")

        self.card.children = [
            v.Row(
                children=[
                    v.Col(cols=3, children=[self.min_field]),
                    v.Col(cols=4, children=[self.filter_obj]),
                    v.Col(cols=3, children=[self.max_field]),
                    v.Col(children=[self.undo_icon]),
                ]
            )
        ]

        self.max_field.on_event("input", self.__on_max_change)
        self.min_field.on_event("input", self.__on_min_change)
        self.filter_obj.observe(
            self.__on_change_filter_obj_v_model, names="v_model", type="change"
        )
        self.undo_icon.on_event("click", lambda *d: self._undo())

    def __on_change_filter_obj_v_model(self, change):
        if isinstance(change["new"], list):
            self.min_field.v_model, self.max_field.v_model = change["new"]
        else:
            self.filter_obj.v_model = [self.filter_obj.min, self.filter_obj.max]

    def __on_min_change(self, widget, event, data):
        if isinstance(data, (float, int, str)) and data != "":
            if self.filter_obj.v_model is None:
                self.filter_obj.v_model = [int(data), self.filter_obj.max]
            else:
                self.filter_obj.v_model[0] = int(data)

    def __on_max_change(self, widget, event, data):
        if isinstance(data, (float, int, str)) and data != "":
            if self.filter_obj.v_model is None:
                self.filter_obj.v_model = [self.filter_obj.min, int(data)]
            else:
                self.filter_obj.v_model[1] = int(data)

    def _update_mask(self):
        self.mask = (
            (
                self.table.df.filter(
                    pl.col(self.name).is_between(*self.filter_obj.v_model)
                ).select(self.table.row_nr)
            )
            if self.filter_obj.v_model
            and self.filter_obj.v_model != [self.filter_obj.min, self.filter_obj.max]
            else None
        )

        self.undo_icon.color = "grey" if self.mask is None else "primary"

    def _update_filter(self):
        self.filter_obj.min = (
            self.table.df.select(pl.col(self.name).min().floor()).collect().item()
        )
        self.filter_obj.max = (
            self.table.df.select(pl.col(self.name).max().ceil()).collect().item()
        )

        if self.filter_obj.v_model is None:
            self.filter_obj.v_model = [self.filter_obj.min, self.filter_obj.max]

    def _undo(self):
        super()._undo()
        self.filter_obj.v_model = None
