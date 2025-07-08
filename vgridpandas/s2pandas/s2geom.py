from typing import Union, Set
from shapely.geometry import (
    Point,
    MultiPoint,
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
)
from vgrid.utils import s2
from vgrid.utils.antimeridian import fix_polygon
from vgridpandas.utils.geom import check_predicate

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]
MultiPointOrPoint = Union[Point, MultiPoint]

def validate_s2_resolution(resolution):
    """
    Validate that S2 resolution is in the valid range [0..28].

    Args:
        resolution: Resolution value to validate

    Returns:
        int: Validated resolution value

    Raises:
        ValueError: If resolution is not in range [0..28]
        TypeError: If resolution is not an integer
    """
    if not isinstance(resolution, int):
        raise TypeError(
            f"Resolution must be an integer, got {type(resolution).__name__}"
        )

    if resolution < 0 or resolution > 28:
        raise ValueError(f"Resolution must be in range [0..28], got {resolution}")

    return resolution

def cell2boundary(s2_token) -> Polygon:
    """s2.s2_to_geo_boundary equivalent for shapely"""
    try:
        # If already a CellId, use as is; else, convert from token
        if isinstance(s2_token, s2.CellId):
            cell_id = s2_token
        else:
            cell_id = s2.CellId.from_token(s2_token)

        cell = s2.Cell(cell_id)
        vertices = [cell.get_vertex(i) for i in range(4)]
        shapely_vertices = []
        for vertex in vertices:
            lat_lng = s2.LatLng.from_point(vertex)
            longitude = lat_lng.lng().degrees
            latitude = lat_lng.lat().degrees
            shapely_vertices.append((longitude, latitude))
        shapely_vertices.append(shapely_vertices[0])
        cell_polygon = fix_polygon(Polygon(shapely_vertices))
        return cell_polygon
    except Exception as e:
        print(f"Error converting S2 token to polygon: {e}")
        return None


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
            cell_polygon = cell2boundary(cell_id)
            if not check_predicate(cell_polygon, poly, predicate):
                continue
            cell_token = s2.CellId.to_token(cell_id)
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
        return set(poly2s2(geometry, resolution, predicate='intersect', compact=False))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")

