from typing import Union, Set
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from vgrid.utils import geohash
from vgrid.conversion.dggscompact import geohash_compact
from vgrid.generator.geohashgrid import (
    initial_geohashes,
    geohash_to_polygon,
    expand_geohash_bbox,
)
from vgridpandas.utils.geom import check_predicate


MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

def validate_geohash_resolution(resolution: int) -> int:
    """
    Validate that geohash resolution is in the valid range [1..10].

    Args:
        resolution: Resolution value to validate

    Returns:
        int: Validated resolution value

    Raises:
        ValueError: If resolution is not in range [1..10]
        TypeError: If resolution is not an integer
    """
    if not isinstance(resolution, int):
        raise TypeError(
            f"Resolution must be an integer, got {type(resolution).__name__}"
        )

    if resolution < 1 or resolution > 10:
        raise ValueError(f"Resolution must be in range [1..10], got {resolution}")

    return resolution

def cell2boundary(geohash_id: str) -> Polygon:
    """geohash.geohash_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    geohash_id : str
        geohash ID to convert to a boundary

    Returns
    -------
    Polygon representing the geohash cell boundary
    """
    # Base octahedral face definitions
    bbox = geohash.bbox(geohash_id)
    min_lat, min_lon = bbox["s"], bbox["w"]
    max_lat, max_lon = bbox["n"], bbox["e"]
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

def poly2geohash(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to Geohash grid cells.

    Args:
        resolution (int): Geohash resolution level [1..10]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of geohash ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2geohash(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_geohash_resolution(resolution)
    geohash_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        intersected_geohashes = {
            gh for gh in initial_geohashes if geohash_to_polygon(gh).intersects(poly)
        }
        geohashes_bbox = set()
        for gh in intersected_geohashes:
            expand_geohash_bbox(gh, resolution, geohashes_bbox, poly)
        for gh in geohashes_bbox:
            cell_polygon = geohash_to_polygon(gh)
            if not check_predicate(cell_polygon, poly, predicate):
                continue
            geohash_ids.append(gh)
    if compact:
        return geohash_compact(geohash_ids)
    return geohash_ids


def polyfill(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """geohash.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        geohash resolution of the filling cells

    Returns
    -------
    Set of geohash ids

    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(poly2geohash(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(poly2geohash(geometry, resolution, predicate="intersect", compact=False))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
