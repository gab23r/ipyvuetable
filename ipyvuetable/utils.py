import ipyvuetify as v
import polars as pl
import traitlets


def string_to_duration(df: pl.LazyFrame) -> pl.LazyFrame:
    """From "07:45:00" (pl.String) to pl.Duration"""
    duration_expr = pl.col.opening_time.str.split_exact(":", 2)
    hours = duration_expr.struct[0]
    minutes = duration_expr.struct[1]
    seconds = duration_expr.struct[2]

    return df.with_columns(
        duration=pl.duration(hours=hours, minutes=minutes, seconds=seconds),
    )


def add_tooltip(obj, str_tooltip):
    obj.v_on = "tooltip.on"
    return v.Tooltip(
        bottom=True,
        v_slots=[{"name": "activator", "variable": "tooltip", "children": obj}],
        children=[str_tooltip],
    )


class IconAlert(v.VuetifyTemplate):  # type: ignore
    """
    custom icon that throw an alert when click
    Only feasible with VuetifyTemplate

    Example:
    delete_icon = IconAlert(
        'mdi-delete', "Delete items", "Are you sure you want to delete these items ?",
         customized_on_click = lambda d: ...,
         disabled = True
    )

    """

    str_tooltip = traitlets.Unicode("").tag(sync=True)
    str_alert = traitlets.Unicode("").tag(sync=True)
    str_icon = traitlets.Unicode("").tag(sync=True)
    disabled = traitlets.Bool(False).tag(sync=True)
    color = traitlets.Unicode("").tag(sync=True)

    def __init__(
        self,
        str_icon,
        str_tooltip,
        str_alert="Are you sure ?",
        customized_on_click=lambda: None,
        *args,
        **kwargs,
    ):
        self.str_tooltip = str_tooltip
        self.str_alert = str_alert
        self.str_icon = str_icon
        self.customized_on_click = customized_on_click
        v.VuetifyTemplate.__init__(self, *args, **kwargs)  # type: ignore

    @traitlets.default("template")
    def _template(self):
        return """
        <template>
          <v-tooltip bottom>
            <template v-slot:activator="tooltip">
                <v-icon v-on="tooltip.on" @click="confirm_and_click" :disabled = "disabled" :color = "color">
                    {{ str_icon}}
                </v-icon>
            </template>
            {{ str_tooltip }}
        </v-tooltip>
        </template>
        <script>
        modules.export  =  {
            methods: {
                confirm_and_click() {
                console.log('deleteItem')
                    if (confirm(this.str_alert)){
                        this.on_click()
                    }
                }
            },
        }
        </script>
        """

    def on_event(self, event, func):
        if event == "click":
            self.vue_on_click = func  # type: ignore

    def vue_on_click(self, args):
        """
        should be overwrite by on_event
        """
