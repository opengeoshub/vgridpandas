from typing import Union, Set
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from vgrid.utils import mercantile
from vgridpandas.utils.geom import check_predicate
from vgrid.conversion.dggscompact import quadkey_compact

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

def validate_quadkey_resolution(resolution: int) -> int:
    """
    Validate that quadkey resolution is in the valid range [0..29].

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

def cell2boundary(quadkey_id: str) -> Polygon:
    """quadkey.quadkey_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    quadkey_id : str
        quadkey ID to convert to a boundary

    Returns
    -------
    Polygon representing the quadkey cell boundary
    """
    tile = mercantile.quadkey_to_tile(quadkey_id)
    z = tile.z
    x = tile.x
    y = tile.y
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

def poly2quadkey(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to Quadkey grid cells.

    Args:
        resolution (int): Quadkey resolution level [1..10]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of quadkey ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2quadkey(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_quadkey_resolution(resolution)    
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    quadkey_ids = []
    for poly in polys:
        min_lon, min_lat, max_lon, max_lat = poly.bounds
        tiles = mercantile.tiles(min_lon, min_lat, max_lon, max_lat, resolution)
        for tile in tiles:
            z, x, y = tile.z, tile.x, tile.y
            bounds = mercantile.bounds(x, y, z)
            min_lat, min_lon = bounds.south, bounds.west
            max_lat, max_lon = bounds.north, bounds.east
            quadkey_id = mercantile.quadkey(tile)
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
                quadkey_ids.append(quadkey_id)

    if compact:
        return quadkey_compact(quadkey_ids)
    return quadkey_ids


def polyfill(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """quadkey.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        quadkey resolution of the filling cells

    Returns
    -------
    Set of quadkey ids

    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(poly2quadkey(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(poly2quadkey(geometry, resolution, predicate="intersect", compact=False))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
