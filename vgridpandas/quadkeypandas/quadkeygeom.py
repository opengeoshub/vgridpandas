from typing import Union, Set
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from vgrid.dggs import mercantile
from vgridpandas.utils.geom import check_predicate
from vgrid.conversion.dggscompact.quadkeycompact import quadkey_compact
from vgrid.utils.io import validate_quadkey_resolution

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

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
