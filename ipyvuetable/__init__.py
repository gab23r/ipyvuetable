import importlib
from pathlib import Path

from IPython.display import HTML, display

from ipyvuetable.editing_table import EditingTable
from ipyvuetable.table import Table

# load css classes
display(HTML(f"<style>{(Path(__file__).parent / 'custom.css').read_text()}</style>"))

__version__ = importlib.metadata.version(__name__)
__all__ = ["EditingTable", "Table"]
