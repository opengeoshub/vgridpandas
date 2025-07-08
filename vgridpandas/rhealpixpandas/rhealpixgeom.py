from typing import Union, Set
from shapely.geometry import box, Polygon, MultiPolygon, LineString, MultiLineString
from vgrid.utils.rhealpixdggs.dggs import RHEALPixDGGS
from vgrid.utils.rhealpixdggs.utils import my_round
from vgrid.utils.rhealpixdggs.ellipsoids import WGS84_ELLIPSOID
from vgrid.generator.rhealpixgrid import fix_rhealpix_antimeridian_cells
from vgridpandas.utils.geom import check_predicate
from vgrid.conversion.dggscompact import rhealpix_compact

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]
rhealpix_dggs = RHEALPixDGGS(
        ellipsoid=WGS84_ELLIPSOID, north_square=1, south_square=3, N_side=3
    )

def validate_rhealpix_resolution(resolution):
    """
    Validate that rHEALPix resolution is in the valid range [0..15].

    Args:
        resolution: Resolution value to validate

    Returns:
        int: Validated resolution value

    Raises:
        ValueError: If resolution is not in range [0..15]
        TypeError: If resolution is not an integer
    """
    if not isinstance(resolution, int):
        raise TypeError(
            f"Resolution must be an integer, got {type(resolution).__name__}"
        )

    if resolution < 0 or resolution > 15:
        raise ValueError(f"Resolution must be in range [0..15], got {resolution}")

    return resolution


def cell2boundary(rhealpix_id: str) -> Polygon:
    """rhealpix.rhealpix_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    rhealpix_id : str
        rhealpix ID to convert to a boundary

    Returns
    -------
    Polygon representing the rhealpix cell boundary
    """
    rhealpix_uids = (rhealpix_id[0],) + tuple(map(int, rhealpix_id[1:]))
    
    rhealpix_cell = rhealpix_dggs.cell(rhealpix_uids)
    shapely_vertices = [
        tuple(my_round(coord, 14) for coord in vertex)
        for vertex in rhealpix_cell.vertices(plane=False)
    ]
    if shapely_vertices[0] != shapely_vertices[-1]:
        shapely_vertices.append(shapely_vertices[0])
    shapely_vertices = fix_rhealpix_antimeridian_cells(shapely_vertices)
    return Polygon(shapely_vertices)

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
        seed_cell_polygon = cell2boundary(seed_cell_id)
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
                cell_polygon = cell2boundary(current_cell_id)
                if not cell_polygon.intersects(bbox_polygon):
                    continue
                neighbors = current_cell.neighbors(plane=False)
                for _, neighbor in neighbors.items():
                    neighbor_id = str(neighbor)
                    if neighbor_id not in covered_cells:
                        queue.append(neighbor)
            if compact:
                covered_cells = rhealpix_compact(rhealpix_dggs, covered_cells)
            for cell_id in covered_cells:
                cell_polygon = cell2boundary(cell_id)
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

