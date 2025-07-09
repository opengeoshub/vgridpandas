from typing import Union, Set, Iterator
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from vgrid.utils import maidenhead

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

def validate_maidenhead_resolution(resolution: int) -> int:
    """
    Validate that maidenhead resolution is in the valid range [1..4].

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

def cell2boundary(maidenhead_id: str) -> Polygon:
    """maidenhead.maidenhead_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    maidenhead_id : str
        maidenhead ID to convert to a boundary

    Returns
    -------
    Polygon representing the maidenhead cell boundary
    """
    _, _, min_lat, min_lon, max_lat, max_lon, _ = maidenhead.maidenGrid(maidenhead_id)
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