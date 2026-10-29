import importlib.metadata

from ipyvuetable.editing_table import EditingTable
from ipyvuetable.table import Table

__version__ = importlib.metadata.version(__name__)
__all__ = ["EditingTable", "Table"]
