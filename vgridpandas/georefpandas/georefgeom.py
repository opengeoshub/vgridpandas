from typing import Union, Set, Iterator
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.wkt import loads
from shapely.ops import transform
from vgrid.utils import georef
import os, json
from shapely.geometry import shape

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]


def validate_georef_resolution(resolution: int) -> int:
    """
    Validate that georef resolution is in the valid range [0..4].

    Args:
        resolution: Resolution value to validate

    Returns:
        int: Validated resolution value

    Raises:
        ValueError: If resolution is not in range [0..4]
        TypeError: If resolution is not an integer
    """
    if not isinstance(resolution, int):
        raise TypeError(
            f"Resolution must be an integer, got {type(resolution).__name__}"
        )

    if resolution < 0 or resolution > 4:
        raise ValueError(f"Resolution must be in range [0..4], got {resolution}")

    return resolution

def cell2boundary(georef_id: str) -> Polygon:
    """georef.georef_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    georef_id : str
        georef ID to convert to a boundary

    Returns
    -------
    Polygon representing the georef cell boundary
    """
    _, _, min_lat, min_lon, max_lat, max_lon, _ = georef.georefcell(georef_id)
    cell_polygon = Polygon(
        [
            [min_lon, min_lat],
            [max_lon, min_lat],
            [max_lon, max_lat],
            [min_lon, max_lat],
            [min_lon, min_lat],
        ]
    )
    return cell_polygon
