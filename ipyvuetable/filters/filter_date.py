import datetime

import ipyvuetify as v
import polars as pl

from ipyvuetable.filters import Filter


class FilterDate(Filter):
    def __init__(self, name, table, **kwargs):
        super().__init__(name, table, **kwargs)

    def init_filter(self):
        super().init_filter()
        self.default_range: list[datetime.date] | None = None

        self.max_field = v.TextField(
            v_model=None, class_="pa-2", label="max", type="date"
        )
        self.min_field = v.TextField(
            v_model=None, class_="pa-2", label="min", type="date"
        )
        self.undo_icon = v.Icon(children=["mdi-undo-variant"], color="grey")

        self.card.children = [
            v.Row(
                style_="background-color: white;",
                dense=True,
                children=[
                    v.Col(children=[self.min_field]),
                    v.Col(children=[self.max_field]),
                    v.Col(children=[self.undo_icon]),
                ],
            )
        ]
        self.undo_icon.on_event("click", lambda *d: self._undo())

    def _update_mask(self):
        if self.default_range:
            min_date, max_date = str_to_date(
                [self.min_field.v_model, self.max_field.v_model]
            )

            if (
                min_date
                and max_date
                and self.default_range
                and (
                    self.default_range[0] < min_date
                    or self.default_range[1] > max_date + datetime.timedelta(days=1)
                )
            ):
                self.mask = self.table.df.filter(
                    pl.col(self.name).is_between(min_date, max_date, closed="both")
                ).select(self.table.row_nr)
                self.undo_icon.color = "primary"
                return

        self.mask = None
        self.undo_icon.color = "grey"

    def _update_filter(self):
        min = self.table.df.select(self.name).min().collect().item()
        max = self.table.df.select(self.name).max().collect().item()

        self.default_range = [min, max] if min is not None else None

        # set default values if needed
        if self.min_field.v_model is None and self.max_field.v_model is None:
            if self.default_range:
                self.min_field.v_model, self.max_field.v_model = date_to_str(
                    self.default_range
                )

    def _undo(self):
        super()._undo()
        if self.default_range:
            self.min_field.v_model, self.max_field.v_model = date_to_str(
                self.default_range
            )
        else:
            self.min_field.v_model = self.max_field.v_model = None


def date_to_str(list_date: list[datetime.date]) -> list[str]:
    list_str = [datetime.date.strftime(d, "%Y-%m-%d") for d in list_date]
    return list_str


def str_to_date(list_str: list[str]) -> list[datetime.date]:
    list_date = [datetime.datetime.strptime(d, "%Y-%m-%d").date() for d in list_str]
    return list_date
