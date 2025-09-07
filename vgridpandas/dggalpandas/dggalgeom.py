from typing import Union, Set
from shapely.geometry import (
    Point,
    MultiPoint,
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
)
from dggal import *
from vgrid.utils.geometry import check_predicate
from vgrid.conversion.dggs2geo.dggal2geo import dggal2geo
from vgrid.utils.io import validate_dggal_resolution
from vgrid.conversion.dggscompact.dggalcompact import dggal_compact
from vgrid.utils.constants import DGGAL_TYPES

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]
MultiPointOrPoint = Union[Point, MultiPoint]


def poly2dggal(dggs_type, geometry, resolution, predicate=None, compact=False):
    """
    Convert polygon geometries (Polygon, MultiPolygon) to DGGAL grid cells.

    Args:
        dggs_type: str
            DGGAL type
        resolution (int): DGGAL resolution level [0..28]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of DGGAL tokens intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2dggal(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    dggs_class_name = DGGAL_TYPES[dggs_type]["class_name"]
    dggrs = globals()[dggs_class_name]()

    resolution = validate_dggal_resolution(dggs_type, resolution)
    dggal_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        min_lon, min_lat, max_lon, max_lat = poly.bounds
        ll = GeoPoint(min_lat, min_lon)
        ur = GeoPoint(max_lat, max_lon)
        geo_extent = GeoExtent(ll, ur)
        zones = dggrs.listZones(resolution, geo_extent)
        for zone in zones:
            zone_id = dggrs.getZoneTextID(zone)
            cell_polygon = dggal2geo(dggs_type, zone_id)
            if not check_predicate(cell_polygon, poly, predicate):
                continue
            dggal_ids.append(zone_id)
    if compact:
        dggal_ids = dggal_compact(dggs_type, dggal_ids)
    return dggal_ids


def polyfill(
    dggs_type: str,
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """dggal.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        DGGAL resolution of the filling cells

    Returns
    -------
    Set of DGGAL Tokens

    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(poly2dggal(dggs_type, geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(
            poly2dggal(
                dggs_type, geometry, resolution, predicate="intersect", compact=False
            )
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
