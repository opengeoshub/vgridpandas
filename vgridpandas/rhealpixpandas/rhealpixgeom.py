from typing import Union, Set
from shapely.geometry import box, Polygon, MultiPolygon, LineString, MultiLineString
from vgrid.dggs.rhealpixdggs.dggs import RHEALPixDGGS
from vgrid.dggs.rhealpixdggs.ellipsoids import WGS84_ELLIPSOID
from vgrid.utils.geometry import fix_rhealpix_antimeridian_cells
from vgridpandas.utils.geom import check_predicate
from vgrid.conversion.dggscompact.rhealpixcompact import rhealpix_compact
from vgrid.utils.io import validate_rhealpix_resolution
from vgrid.conversion.dggs2geo.rhealpix2geo import rhealpix2geo as rhp_to_geo

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]
rhealpix_dggs = RHEALPixDGGS(
        ellipsoid=WGS84_ELLIPSOID, north_square=1, south_square=3, N_side=3
    )

def poly2rhealpix(geometry: MultiPolyOrPoly, resolution: int, predicate: str = None, compact: bool = False) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to rhealpix grid cells.

    Args:
        resolution (int): rhealpix resolution level [0..28]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of rhealpix ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2rhealpix(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_rhealpix_resolution(resolution)
    rhealpix_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        minx, miny, maxx, maxy = poly.bounds
        bbox_polygon = box(minx, miny, maxx, maxy)
        bbox_center_lon = bbox_polygon.centroid.x
        bbox_center_lat = bbox_polygon.centroid.y
        seed_point = (bbox_center_lon, bbox_center_lat)
        seed_cell = rhealpix_dggs.cell_from_point(resolution, seed_point, plane=False)
        seed_cell_id = str(seed_cell)
        seed_cell_polygon = rhp_to_geo(seed_cell_id)
        if seed_cell_polygon.contains(bbox_polygon):
            rhealpix_ids.append(seed_cell_id)
            return rhealpix_ids
        else:
            covered_cells = set()
            queue = [seed_cell]
            while queue:
                current_cell = queue.pop()
                current_cell_id = str(current_cell)
                if current_cell_id in covered_cells:
                    continue
                covered_cells.add(current_cell_id)
                cell_polygon = rhp_to_geo(current_cell_id)
                if not cell_polygon.intersects(bbox_polygon):
                    continue
                neighbors = current_cell.neighbors(plane=False)
                for _, neighbor in neighbors.items():
                    neighbor_id = str(neighbor)
                    if neighbor_id not in covered_cells:
                        queue.append(neighbor)
            if compact:
                covered_cells = rhealpix_compact(covered_cells)
            for cell_id in covered_cells:
                cell_polygon = rhp_to_geo(cell_id)
                if not check_predicate(cell_polygon, poly, predicate):
                    continue
                rhealpix_ids.append(cell_id)

    return rhealpix_ids


def polyfill(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """rhealpix.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        rhealpix resolution of the filling cells

    Returns
    -------
    Set of rhealpix ids

    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(poly2rhealpix(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(poly2rhealpix(geometry, resolution, predicate='intersect', compact=False))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")

