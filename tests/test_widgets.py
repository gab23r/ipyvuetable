import io

import polars as pl
import pytest

from ipyvuetable.widgets import FileInput, VirtualAutocomplete


class FakeFile:
    def __init__(self, data: bytes):
        self.data = data

    def readall(self):
        return self.data


def fake_upload(widget: FileInput, name: str, data: bytes):
    widget.file_input.get_files = lambda: [{"name": name, "file_obj": FakeFile(data)}]


DF = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})


def to_bytes(fmt: str) -> bytes:
    buf = io.BytesIO()
    getattr(DF, f"write_{fmt}")(buf)
    return buf.getvalue()


@pytest.mark.parametrize("fmt", ["csv", "json", "parquet"])
def test_file_input_formats(fmt):
    w = FileInput("upload")
    fake_upload(w, f"data.{fmt}", to_bytes(fmt))
    assert w.load_dataframes()[0].equals(DF)


@pytest.mark.parametrize("ext", ["xlsx", "xls"])
def test_file_input_excel_extension_is_recognised(ext):
    w = FileInput("upload")
    fake_upload(w, f"data.{ext}", b"not really excel")
    with pytest.raises(Exception) as exc:
        w.load_dataframes()
    assert "is not supported" not in str(exc.value)


def test_file_input_unknown_extension():
    w = FileInput("upload")
    fake_upload(w, "data.txt", b"")
    with pytest.raises(Exception, match="not supported"):
        w.load_dataframes()


def test_file_input_v_model():
    w = FileInput("upload")
    assert w.v_model is None


def autocomplete(single_select: bool) -> VirtualAutocomplete:
    df = pl.LazyFrame({"k__key": [1, 2, 3], "k": ["one", "two", "three"]})
    return VirtualAutocomplete("k", df, single_select=single_select, item_key="k__key")


def test_autocomplete_single():
    w = autocomplete(single_select=True)
    assert w.v_model is None
    w.v_model = 2
    assert w.v_model == 2
    assert w.textfield.v_model == "two"
    w.v_model = None
    assert w.v_model is None
    assert w.textfield.v_model is None


def test_autocomplete_multi():
    w = autocomplete(single_select=False)
    w.v_model = [3, 1]
    assert sorted(w.v_model) == [1, 3]
    assert w.textfield.v_model == "one, three"
    w.v_model = []
    assert w.v_model == []


def test_autocomplete_text_updates_on_menu_close():
    w = autocomplete(single_select=False)
    w.table_select.v_model = [{"k__key": 2, "__row_nr__": 1}]
    w.menu.fire_event("input", False)
    assert w.textfield.v_model == "two"
