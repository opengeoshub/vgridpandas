__author__ = """Thang Quach"""
__email__ = "quachdongthang@gmail.com"
__version__ = "1.0.0"

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("vgridpandas")
except PackageNotFoundError:
    # package is not installed
    pass
