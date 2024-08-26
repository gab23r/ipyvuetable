from functools import reduce
from typing import Any

import ipyvuetify as v
import ipywidgets as ipw
import polars as pl
import traitlets as t

try:
    from ipyevents import Event  # type: ignore
except ModuleNotFoundError:
    Event = None

import ipyvuetable.utils as utils
from ipyvuetable.filters import (
    Filter,
    FilterCombobox,
    FilterDateTime,
    FilterDate,
    FilterListCombobox,
    FilterSlider,
)


class DataTableEnhanced(v.DataTable):
    def __init__(
        self, max_height: int | None = 500, show_filters: bool = True, **kwargs: Any
    ):
        super().__init__(**kwargs)
        self.max_height = max_height
        self.show_filters = show_filters
        self.items_per_page = kwargs.pop("items_per_page", 10)

        self.on_event("update:options", self._on_change_option_data_table)
        self.observe(self._on_change_items, "items")

    def _update_items(self):
        # In case of paginated Table _update_items need to be update and _on_change_items will be triggered automatically
        # In non-paginated cases, items is not modified, we need to call _on_change_items "by hand"
        self._on_change_items()

    def _update_df_search_sorted(self):
        # need only if paginated
        ...

    def _on_change_option_data_table(self, widget, event, data):
        # keep track of previous values to know if we need to update
        previous_sort_by = self.sort_by
        previous_sort_desc = self.sort_desc

        # ipyvuetify does not update these values
        # we update them manually to keep things align
        # we use __dict__['_trait_values'] so that this does'nt trigger this function again
        self.__dict__["_trait_values"]["page"] = data["page"]
        self.__dict__["_trait_values"]["items_per_page"] = data["itemsPerPage"]
        self.__dict__["_trait_values"]["sort_by"] = data["sortBy"]
        self.__dict__["_trait_values"]["sort_desc"] = data["sortDesc"]

        # sort if needed
        if previous_sort_by != data["sortBy"] or previous_sort_desc != data["sortDesc"]:
            self._update_df_search_sorted()

        self._update_items()

    def _on_change_items(self, *change):
        if self.max_height is not None:
            items_per_page = (
                int(self.items_per_page) if self.items_per_page is not None else None
            )
            h = self._get_current_height(len(self.items[:items_per_page]))
            self.height = None if h <= self.max_height else self.max_height

    def _get_current_height(self, nrow):
        if self.dense:
            row_height = filter_height = 25
            header_height = 32
        else:
            row_height = filter_height = header_height = 48
        return nrow * row_height + filter_height * self.show_filters + header_height


class Table(DataTableEnhanced):
    df_height: int
    df_search: pl.LazyFrame  # dataframe resulting of the filters
    df_search_sorted: pl.LazyFrame  # dataframe resulting of the sort
    df_paginated: pl.LazyFrame  # dataframe rendered based on the panigation
    nb_selected = t.Int(0).tag(sync=True)
    selected_keys = []  # not trait as it can be any python object ex date
    last_selected_key = None

    def __init__(
        self,
        df: pl.LazyFrame = pl.LazyFrame(),
        *,
        title: str | None = None,
        item_key: str | None = None,
        columns_repr: dict[str, pl.LazyFrame] = {},
        columns_to_hide: list[str] = [],
        show_actions: bool = True,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.columns_repr = columns_repr
        self.show_actions = show_actions
        self.columns_to_hide = columns_to_hide

        self.page = kwargs.pop("page", 1)
        self.dense = kwargs.pop("dense", True)
        self.footer_props = {
            "items-per-page-options": [5, 10, 15, 25, 50, 100, -1],
            "show-first-last-page": True,
        } | kwargs.pop("footer_props", {})

        self.style_ = kwargs.pop("style_", "white-space: nowrap")
        self.add_class("ipyvuetable")
        self.v_model: list[dict[str, Any]] = []

        self.row_nr = "__row_nr__"
        self.item_key = self.row_nr if item_key is None else item_key
        self.is_select_all = False
        self.filter_on_selected = False

        self.toolbar_title = v.ToolbarTitle(children=[title] if title else [])
        self.filters_row = v.Html(tag="tr")  # type: ignore
        self.unselect = v.Icon(
            children=["mdi-close"], color="primary", disabled=True, class_="pt-1"
        )
        self.badge = v.Badge(
            v_model=not kwargs.get("single_select", False),
            inline=True,
            children=[self.unselect],
            dot=True,
        )  # count the number of selected items
        self.dialog = v.Dialog(max_width="700px", v_model=False)
        self.columns_to_display_search = v.TextField(
            v_model=None,
            label="Search ...",
            single_line=True,
            dense=True,
            hide_details=True,
            class_="pa-2",
        )
        self.columns_to_display_table = DataTableEnhanced(
            headers=[{"text": "Columns", "value": "col"}],
            item_key="col",
            show_select=True,
            dense=True,
            max_height=500,
        )

        self.filters: dict[str, Filter] = {}
        self.schema: dict[str, pl.DataType] = {}
        self.custom_actions = (
            self._get_custom_actions()
        )  # could be defined be subclasses
        self.actions = self._get_actions()
        self.v_slots = self._get_slots()

        self._update_df(df)

        # create variables to handle ipyevents events
        self.event: dict[str, Any] = {}  # used to store the last event state
        self.click_event = (
            Event(
                source=self,
                watched_events=["mousemove"],
                prevent_default_action=True,
                throttle_or_debounce="throttle",
                wait=100,
            )
            if Event is not None
            else None
        )
        self.selected_indices: set[int] = set()
        self.last_selected_index: int = -1

        # ipyevents only works with ipywidgets not ipyvuetify
        # if you want to activate ipyevents features, use the `ui` attribute
        # https://github.com/widgetti/ipyvuetify/issues/216
        self.ui = ipw.VBox(children=[self])

        ipw.jslink(
            (self.columns_to_display_search, "v_model"),
            (self.columns_to_display_table, "search"),
        )

        self.on_event("input", self._on_input_table)
        self.unselect.on_event("click", self._on_click_unselect)
        self.actions["undo_filters"]["obj"].on_event("click", self._undo_all_filters)
        self.actions["multi_sort"]["obj"].on_event("click", self._toggle_multi_sort)
        self.observe(self.on_nb_selected, "nb_selected")
        self.actions["select_column"]["obj"].observe(
            self._update_columns_to_hide, "v_model"
        )
        self.actions["filter_on_selected"]["obj"].on_event(
            "click", self._fiter_on_selected
        )
        if self.click_event:
            self.click_event.on_dom_event(self._update_event)

    def _update_event(self, event):
        self.event = event

    def _get_custom_actions(self) -> dict[str, dict[str, Any]]:
        return {}

    def _get_actions(self) -> dict[str, dict[str, Any]]:
        actions = {}
        actions["undo_filters"] = {
            "obj": v.Icon(children=["mdi-filter-remove"]),
            "tooltip": "Undo all filters",
        }
        actions["multi_sort"] = {
            "obj": v.Icon(children=["mdi-swap-vertical"], disabled=False),
            "tooltip": "Toggle multi sort",
        }

        actions["select_column"] = {
            "obj": v.Menu(
                v_model=False,
                left=True,
                close_on_content_click=False,
                transition="scale-transition",
                offset_y=True,
                children=[
                    v.Card(
                        children=[
                            self.columns_to_display_search,
                            self.columns_to_display_table,
                        ]
                    )
                ],
                v_slots=[
                    {
                        "name": "activator",
                        "variable": "menus",
                        "children": v.Icon(
                            v_bind="menus.attrs",
                            v_on="menus.on",
                            children=["mdi-table-column-plus-after"],
                            color="primary",
                        ),
                    }
                ],
            ),
            "tooltip": "Select columns to hide/show",
        }
        actions["filter_on_selected"] = {
            "obj": v.Icon(
                children=["mdi-checkbox-marked-circle-outline"],
                disabled=False,
                color="primary",
            ),
            "tooltip": "Filter on selected rows",
        }

        return actions

    @property
    def df(self) -> pl.LazyFrame:
        return self._df

    @df.setter
    def df(self, df: pl.LazyFrame) -> None:
        self._update_df(df)
        self.on_df_change()

    @property
    def df_selected(self) -> pl.LazyFrame:
        if any(row[self.row_nr] is None for row in self.v_model):
            filter_expr = (
                pl.col(self.row_nr).is_in(
                    [
                        row[self.row_nr]
                        for row in self.v_model
                        if row[self.row_nr] is not None
                    ]
                )
                | pl.col(self.row_nr).is_null()
            )

        else:
            filter_expr = pl.col(self.row_nr).is_in(
                [row[self.row_nr] for row in self.v_model]
            )
        return self.df.filter(filter_expr)

    def _update_schema(self, schema):
        self.schema = schema
        self.columns_to_display_table.v_model = [
            {"col": c} for c in schema if c not in self.columns_to_hide
        ]
        self.columns_to_display_table.items = [{"col": c} for c in self.schema]

        self._update_headers()
        self._update_filters()
        self._update_filters_row()

    def _on_input_table(self, *args):
        previous_selected_keys = self.selected_keys or []
        selected_rows = [i[self.row_nr] for i in self.v_model]
        self.selected_keys = (
            self.df.filter(pl.col(self.row_nr).is_in(selected_rows))
            .select(self.item_key)
            .collect()
            .to_series()
            .to_list()
        )
        self.last_selected_key = next(
            (k for k in self.selected_keys if k not in previous_selected_keys), None
        )
        # if ipyevents is installed
        if Event is not None:
            self._manage_shift_click()

        self.nb_selected = len(self.v_model)

        # update the badge
        if not self.single_select:
            self.badge.v_slots = [
                {"name": "badge", "children": [str(self.nb_selected)]}
            ]
            self.badge.dot = not bool(self.nb_selected)
        self.unselect.disabled = self.nb_selected == 0

        # reset filter_on_selected widget
        if self.filter_on_selected:
            self._apply_filters()

    def _update_df(self, df):
        # row_nr will be generated on the fly and should not be present at init
        df = df.select(pl.exclude(self.row_nr))
        
        schema = df.collect_schema()
        if schema != self.schema:
            self._update_schema(schema)

        # df will be modify over and over
        # so it's a good thing to cache the result when df change
        # Moreover we need to have the height of df
        eager_df = df.with_row_count(self.row_nr).collect()

        self.df_height = eager_df.height
        self._df = eager_df.lazy()

        # align v_model, selected_keys and nb_selected
        if self.selected_keys:
            # If no item_key was given it is safer to erase v_model
            if self.item_key == self.row_nr:
                self.v_model = []
                self.selected_keys = []
                self.nb_selected = 0
            else:
                # realign row_rn
                df_selected = eager_df.filter(
                    pl.col(self.item_key).is_in(self.selected_keys)
                )
                self.v_model = df_selected.pipe(self.jsonify).pipe(self.apply_custom_repr).to_dicts()
                self.selected_keys = df_selected[self.item_key].to_list()
                self.nb_selected = len(self.selected_keys)

        self._update_all_filters()
        self._update_df_search()
        self._update_items()

    def on_nb_selected(self, *change):
        self._update_action_status()

    def on_df_change(self):
        # used by subclasses
        ...

    def _update_action_status(self):
        # used by subclasses
        ...

    def _update_columns_to_hide(self, change):
        if not change["new"]:  # menu is close
            columns_to_show = [i["col"] for i in self.columns_to_display_table.v_model]
            self.columns_to_hide = [c for c in self.schema if c not in columns_to_show]

            self._update_filters_row()
            self._update_headers()

    def _on_click_unselect(self, *args):
        self.v_model = []

    def _manage_shift_click(self):
        selected_indices = set(i[self.row_nr] for i in self.v_model)
        new_selected_indices = selected_indices - self.selected_indices

        if new_selected_indices:
            last_selected_index = new_selected_indices.pop()

            if self.event.get("shiftKey") and self.last_selected_index != -1:
                rows_in_beetween = (
                    self.df_search_sorted.filter(
                        pl.col(self.row_nr)
                        .is_in([self.last_selected_index, last_selected_index])
                        .cum_sum()
                        == 1
                    )
                    # exclude already selected lines
                    .filter(~pl.col(self.row_nr).is_in(selected_indices))
                    .select(self.row_nr)
                )
                new_v_model = (
                    self.jsonify(self.df.join(rows_in_beetween, on=self.row_nr))
                    .collect()
                    .to_dicts()
                )
                self.v_model = self.v_model + new_v_model
        else:
            last_selected_index = -1

        self.selected_indices = selected_indices
        self.last_selected_index = last_selected_index

    def _get_df_paginated(self):
        if self.items_per_page != -1:
            index_start = int((self.page - 1) * self.items_per_page)

            df_paginated = self.df_search_sorted.slice(
                index_start, int(self.items_per_page)
            )
        else:
            df_paginated = self.df_search_sorted

        df_paginated = self.jsonify(df_paginated).pipe(self.apply_custom_repr)

        return df_paginated

    def jsonify(self, df: pl.LazyFrame) -> pl.LazyFrame:
        df = (
            df.with_columns(
                pl.col(pl.DATETIME_DTYPES)
                .exclude("^*__key$")
                .dt.strftime("%Y-%m-%d %H:%M:%S"),
                pl.col(pl.Date).exclude("^*__key$").dt.strftime("%Y-%m-%d"),
            ).pipe(utils.duration_to_string)
        )

        return df

    def apply_custom_repr(self, df: pl.LazyFrame) -> pl.LazyFrame:
        df = df.with_columns(
            pl.col(pl.Boolean)
            .replace_strict({True: "✅", False: "❌"}, return_dtype=pl.Utf8, default=None),
        )

        fill_null_repr_exprs = []
        for c, df_repr in self.columns_repr.items():
            if c in self.schema:
                if not isinstance(self.schema[c], pl.List):
                    df = df.join(df_repr, on=c, how="left")
                    fill_null_repr_exprs.append(
                        pl.col(c + "__repr").fill_null(pl.col(c).cast(pl.Utf8)).alias(c)
                    )

        df = df.with_columns(fill_null_repr_exprs).select(self.row_nr, *self.schema)
        return df

    def _update_df_search(self) -> None:
        self.df_search, self.server_items_length = self._get_df_search()
        self._update_df_search_sorted()

    def _update_df_search_sorted(self) -> None:
        if self.sort_by and self.sort_desc and all(c in self.df for c in self.sort_by):
            self.df_search_sorted = self.df_search.sort(
                self.sort_by,
                descending=self.sort_desc,
                maintain_order=True,
                nulls_last=True,
            )
        else:
            # sort to the initial order
            self.df_search_sorted = self.df_search.sort(self.row_nr)

    def _update_items(self) -> None:
        self.df_paginated = self._get_df_paginated().collect().lazy()

        self.items = self.df_paginated.collect().to_dicts()

    def _get_slots(self) -> list[dict[str, Any]]:
        tooltip_actions = (
            [
                utils.add_tooltip(action_d["obj"], action_d["tooltip"])
                if "tooltip" in action_d
                else action_d["obj"]
                for action_d in self.actions.values()
            ]
            if self.show_actions
            else []
        )

        tooltip_custom_actions = [
            utils.add_tooltip(action_d["obj"], action_d["tooltip"])
            if "tooltip" in action_d
            else action_d["obj"]
            for action_d in self.custom_actions.values()
        ]

        toolbar = v.Toolbar(
            class_="md-2",
            flat=True,
            children=[
                self.toolbar_title,
                *([v.Divider(vertical=True, class_="mx-5")] if tooltip_actions else []),
                *tooltip_actions,
                *(
                    [v.Divider(vertical=True, class_="mx-5")]
                    if tooltip_custom_actions
                    else []
                ),
                *tooltip_custom_actions,
                self.dialog,
            ],
        )
        if not self.toolbar_title.children and not tooltip_actions:
            toolbar.hide()

        slots = [
            {"name": "top", "variable": "top", "children": toolbar},
            {"name": "body.prepend", "children": [self.filters_row]},
        ]
        return slots

    def _update_filters(self) -> None:
        self.filters.clear()
        for col, dtype in self.schema.items():
            if isinstance(dtype, pl.List):
                self.filters[col] = FilterListCombobox(col, self)
            elif dtype in [pl.Float32, pl.Float64]:  # type: ignore
                self.filters[col] = FilterSlider(col, self)
            elif isinstance(dtype, pl.Datetime):
                self.filters[col] = FilterDateTime(col, self)
            elif isinstance(dtype, pl.Date):
                self.filters[col] = FilterDate(col, self)
            else:
                self.filters[col] = FilterCombobox(col, self)

    def _update_headers(self):
        self.headers = [
            {"text": c, "value": c}
            for c in self.schema
            if c not in self.columns_to_hide
        ]

    def _update_filters_row(self):
        if self.show_filters:
            filters_child = [
                v.Html(tag="td", children=[self.filters[c].menu])  # type: ignore
                for c in self.schema
                if c not in self.columns_to_hide
            ]

            if self.show_select:
                filters_child = [
                    v.Html(tag="td", class_="pr-8", children=[self.badge]),  # type: ignore
                    *filters_child,
                ]

            self.filters_row.children = filters_child

    def _get_df_search(
        self,
        filters: None | list[str] = None,
    ) -> tuple[pl.LazyFrame, int]:
        """
        return a lazy filtered version of df and the its height,
        you can either given a custom list of `masks` or
        you can use the mask of each filter spcified in `filters`
        """
        masks: list[pl.LazyFrame] = [
            class_.mask.select(pl.col(self.row_nr))
            for name, class_ in self.filters.items()
            if (filters is None or name in filters) and class_.mask is not None
        ]

        # update undo_filters obj
        self.actions["undo_filters"]["obj"].disabled = not masks
        self.actions["undo_filters"]["obj"].color = "primary" if masks else None

        if self.filter_on_selected:
            masks.append(self.df_selected.select(self.row_nr))

        # apply all masks
        if masks:
            mask = reduce(
                lambda lhs, rhs: lhs.join(rhs, on=self.row_nr, how="semi"), masks
            ).collect()
            search_height = mask.height
            df_search = self.df.join(mask.lazy(), on=self.row_nr, how="semi")

        else:
            df_search = self.df
            search_height = self.df_height

        return df_search, search_height

    def _apply_filters(self) -> None:
        self._update_df_search()
        self._update_items()

        # dirty fix where table is filtered and is not in the first page
        if self.page != 1:
            self.page = 2
            self.page = 1

    def _update_all_filters(self) -> None:
        for class_ in self.filters.values():
            if class_.is_initialized:
                class_._update_filter()
                if class_.mask is not None:
                    class_._update_mask()

    def _undo_all_filters(self, *args: Any) -> None:
        for f in self.filters.values():
            if f.is_initialized:
                f._undo()

        self._update_df_search()
        self._update_items()

    def _toggle_multi_sort(self, widget, event, data):
        self.multi_sort: bool = not self.multi_sort
        widget.color = "primary" if self.multi_sort else None

    def _fiter_on_selected(self, widget, event, data):
        if widget.children[0] == "mdi-checkbox-marked-circle-outline":
            self.filter_on_selected = True
            widget.children = ["mdi-checkbox-marked-circle"]
        else:
            self.filter_on_selected = False
            widget.children = ["mdi-checkbox-marked-circle-outline"]
        self._apply_filters()
