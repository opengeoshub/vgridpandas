from typing import Union, Set
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from vgrid.utils.gars import garsgrid

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

def validate_gars_resolution(resolution: int) -> int:
    """
    Validate that gars resolution is in the valid range [1..4].

    Args:
        resolution: Resolution value to validate

    Returns:
        int: Validated resolution value

    Raises:
        ValueError: If resolution is not in range [1..4]
        TypeError: If resolution is not an integer
    """
    if not isinstance(resolution, int):
        raise TypeError(
            f"Resolution must be an integer, got {type(resolution).__name__}"
        )

    if resolution < 1 or resolution > 4:
        raise ValueError(f"Resolution must be in range [1..4], got {resolution}")

    return resolution


def cell2boundary(gars_id: str) -> Polygon:
    """gars.gars_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    gars_id : str
        gars ID to convert to a boundary

    Returns
    -------
    Polygon representing the gars cell boundary
    """
    gars_grid = garsgrid.GARSGrid(gars_id)
    wkt_polygon = gars_grid.polygon
    cell_polygon = Polygon(list(wkt_polygon.exterior.coords))
    return cell_polygon