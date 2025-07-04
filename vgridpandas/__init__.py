from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("vgridpandas")
except PackageNotFoundError:
    # package is not installed
    pass
