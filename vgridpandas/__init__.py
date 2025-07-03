from . import h3pandas  # noqa: F401

# Make h3pandas directly accessible
from .h3pandas import H3Accessor  # noqa: F401

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("vgridpandas")
except PackageNotFoundError:
    # package is not installed
    pass
