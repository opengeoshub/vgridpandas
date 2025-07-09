from typing import Union, Set
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from vgrid.utils import mercantile
import os, json, re
from vgridpandas.utils.geom import check_predicate
from vgrid.conversion.dggscompact import tilecode_compact

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

def validate_tilecode_resolution(resolution: int) -> int:
    """
    Validate that tilecode resolution is in the valid range [0..29].

    Args:
        resolution: Resolution value to validate

    Returns:
        int: Validated resolution value

    Raises:
        ValueError: If resolution is not in range [0..29]
        TypeError: If resolution is not an integer
    """
    if not isinstance(resolution, int):
        raise TypeError(
            f"Resolution must be an integer, got {type(resolution).__name__}"
        )

    if resolution < 0 or resolution > 29:
        raise ValueError(f"Resolution must be in range [0..29], got {resolution}")

    return resolution


def cell2boundary(tilecode_id: str) -> Polygon:
    """tilecode.tilecode_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    tilecode_id : str
        tilecode ID to convert to a boundary

    Returns
    -------
    Polygon representing the tilecode cell boundary
    """
    match = re.match(r"z(\d+)x(\d+)y(\d+)", tilecode_id)
    z = int(match.group(1))
    x = int(match.group(2))
    y = int(match.group(3))
    bounds = mercantile.bounds(x, y, z)    
    min_lat, min_lon = bounds.south, bounds.west
    max_lat, max_lon = bounds.north, bounds.east
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

def poly2tilecode(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to Tilecode grid cells.

    Args:
        resolution (int): Tilecode resolution level [1..10]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of tilecode ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2tilecode(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_tilecode_resolution(resolution)    
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    tilecode_ids = []
    for poly in polys:
        tilecode_ids_poly = []
        min_lon, min_lat, max_lon, max_lat = poly.bounds
        tilecodes = mercantile.tiles(min_lon, min_lat, max_lon, max_lat, resolution)
        for tile in tilecodes:
            tilecode_id_poly = f"z{tile.z}x{tile.x}y{tile.y}"
            tilecode_ids_poly.append(tilecode_id_poly)
        for tilecode_id_poly in tilecode_ids_poly:
            match = re.match(r"z(\d+)x(\d+)y(\d+)", tilecode_id_poly)
            if not match:
                raise ValueError("Invalid tilecode format. Expected format: 'zXxYyZ'")
            z = int(match.group(1))
            x = int(match.group(2))
            y = int(match.group(3))
            bounds = mercantile.bounds(x, y, z)
          
            min_lat, min_lon = bounds.south, bounds.west
            max_lat, max_lon = bounds.north, bounds.east
            cell_polygon = Polygon(
                [
                    [min_lon, min_lat],
                    [max_lon, min_lat],
                    [max_lon, max_lat],
                    [min_lon, max_lat],
                    [min_lon, min_lat],
                ]
            )
            if check_predicate(cell_polygon, poly, predicate):
                tilecode_ids.append(tilecode_id_poly)
    if compact:
        return tilecode_compact(tilecode_ids)
    return tilecode_ids


def polyfill(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """tilecode.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        tilecode resolution of the filling cells

    Returns
    -------
    Set of tilecode ids

    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(poly2tilecode(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(poly2tilecode(geometry, resolution, predicate="intersect", compact=False))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
