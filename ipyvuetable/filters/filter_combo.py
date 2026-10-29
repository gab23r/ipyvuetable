import ipyvuetify as v
import polars as pl

import ipyvuetable
from ipyvuetable.filters import Filter


class FilterCombobox(Filter):
    menu_size = "large"  # the menu contains a table

    def __init__(self, name, table, **kwargs):
        super().__init__(name, table, **kwargs)

    def init_filter(self):
        super().init_filter()
        self.row_nr = self.table.row_nr
        self.is_select_all = False
        self.search = v.TextField(
            v_model=None,
            # append_icon="mdi-magnify",
            label="Search ...",
            single_line=True,
            dense=True,
            hide_details=True,
            class_="pa-2",
        )
        self.undo_icon = v.Icon(children=["mdi-filter-remove"], color="grey", class_="mx-1")
        self.filter_obj = ipyvuetable.Table(
            item_key=self.name + "__key",
            actions_to_hide="*",
            show_select=True,
            show_filters=False,
            columns_to_hide=[self.name + "__key"],
            max_height=500,
            class_="extra_dense",
        )

        self.card.children = [
            v.Row(children=[self.search, self.undo_icon], class_="ma-0"),
            self.filter_obj,
        ]

        self.search.on_event("input", lambda widget, event, data: self._on_search(data))
        self.undo_icon.on_event("click", lambda *d: self._undo())

    def _on_search(self, data):
        if data:
            df_search = self.filter_obj.df.filter(
                pl.any_horizontal(
                    pl.exclude([self.row_nr, *self.filter_obj.columns_to_hide])
                    .cast(pl.Utf8)
                    .str.to_lowercase()
                    .str.contains(data.lower(), literal=True)
                )
            ).collect()
        else:
            df_search = self.filter_obj.df.collect()

        self.filter_obj.server_items_length = df_search.height
        self.filter_obj.df_search = df_search.lazy()
        self.filter_obj._update_df_search_sorted()
        self.filter_obj._update_items()

        # dirty fix where table is filtered and is not in the first page
        if self.filter_obj.page != 1:
            self.filter_obj.page = 2
            self.filter_obj.page = 1

    def _get_filter_values(self):
        """
        get the the list of possible values in the filter
        """
        other_filters = [c for c in self.table.filters if c != self.name]
        filter_values = (
            self._explode(self.table._get_df_search(filters=other_filters)[0])
            .unique(subset=[self.name])
            .select(self.name, pl.lit(True).alias("__is_available"))
        )

        return filter_values

    def _update_mask(self):
        self.mask = (
            (
                self._explode(self.table.df)
                .join(
                    self.filter_obj.df_selected,
                    left_on=self.name,
                    right_on=self.name + "__key",
                    nulls_equal=True,
                    how="semi",
                    maintain_order="left",
                )
                .select(pl.col(self.row_nr))
            )
            if self.filter_obj.v_model
            else None
        )

    def _get_df(self):
        # show first options that are not already discarded by the other filter
        filter_df_sorted = (
            self._explode(self.table.df.select([self.name]))
            .unique()
            .join(self._get_filter_values(), on=self.name, how="left")
            .sort("__is_available", nulls_last=True, maintain_order=True)
            .drop("__is_available")
        )

        if self.name in self.table.columns_repr:
            # remove `__repr` prefix and add `__key` suffix to the non repr column
            df = filter_df_sorted.join(
                self.table.columns_repr[self.name], on=self.name, how="left", maintain_order="left"
            ).select(  # left to keep the order
                [
                    pl.col(self.name).name.suffix("__key"),
                    pl.col(self.name + "__repr").fill_null(pl.col(self.name)).alias(self.name),
                ]
            )
        else:
            df = filter_df_sorted.select([pl.col(self.name).name.suffix("__key"), pl.col(self.name)])
        return df

    def _explode(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """one row per filterable value"""
        return df

    def _update_filter(self):
        self.filter_obj.df = self._get_df()

    def _undo(self):
        super()._undo()
        self.search.v_model = None
        self.filter_obj.v_model = []
        self._on_search(None)

    def modify_filter(self, values):
        """
        used to pre-define the filter
        """

        if not self.is_initialized:
            self.init_filter()
            self._update_filter()

        key = pl.col(self.name + "__key")
        is_selected = key.is_in([v for v in values if v is not None])
        if None in values:
            is_selected |= key.is_null()
        # look in the whole filter df, not only in the current page of items
        self.filter_obj.v_model = (
            self.filter_obj.df.filter(is_selected)
            .pipe(self.filter_obj.jsonify)
            .pipe(self.filter_obj.apply_custom_repr)
            .collect()
            .to_dicts()
        )
        self.apply_mask()

        return self


class FilterListCombobox(FilterCombobox):
    """filter on the elements of a list column: keep rows containing any of the selected values"""

    def __init__(self, name, table, **kwargs):
        super().__init__(name, table, **kwargs)

    def _explode(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.explode(self.name)

    def _update_mask(self):
        super()._update_mask()
        if self.mask is not None:
            self.mask = self.mask.unique()
