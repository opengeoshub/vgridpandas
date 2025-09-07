from typing import Union, Set
from shapely.geometry import (
    Point,
    MultiPoint,
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
)
from vgrid.dggs import s2
from vgrid.utils.geometry import check_predicate
from vgrid.conversion.dggs2geo.s22geo import s22geo
from vgrid.utils.io import validate_s2_resolution

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]
MultiPointOrPoint = Union[Point, MultiPoint]


def poly2s2(geometry, resolution, predicate=None, compact=False):
    """
    Convert polygon geometries (Polygon, MultiPolygon) to S2 grid cells.

    Args:
        resolution (int): S2 resolution level [0..28]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of S2 tokens intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2s2(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_s2_resolution(resolution)
    s2_tokens = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        min_lng, min_lat, max_lng, max_lat = poly.bounds
        level = resolution
        coverer = s2.RegionCoverer()
        coverer.min_level = level
        coverer.max_level = level
        region = s2.LatLngRect(
            s2.LatLng.from_degrees(min_lat, min_lng),
            s2.LatLng.from_degrees(max_lat, max_lng),
        )
        covering = coverer.get_covering(region)
        cell_ids = covering
        if compact:
            covering = s2.CellUnion(covering)
            covering.normalize()
            cell_ids = covering.cell_ids()

        for cell_id in cell_ids:
            cell_token = s2.CellId.to_token(cell_id)
            cell_polygon = s22geo(cell_token)
            if not check_predicate(cell_polygon, poly, predicate):
                continue
            s2_tokens.append(cell_token)

    return s2_tokens


def polyfill(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """s2.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        S2 resolution of the filling cells

    Returns
    -------
    Set of S2 Tokens

    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(poly2s2(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(poly2s2(geometry, resolution, predicate="intersect", compact=False))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
