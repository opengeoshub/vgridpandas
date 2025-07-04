from typing import Union, Set, Iterator
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.ops import transform
from vgrid.utils.rhealpixdggs.dggs import RHEALPixDGGS
from vgrid.utils.rhealpixdggs.utils import my_round
from vgrid.utils.rhealpixdggs.ellipsoids import WGS84_ELLIPSOID
from vgrid.utils.antimeridian import fix_polygon
from vgrid.generator.rhealpixgrid import fix_rhealpix_antimeridian_cells

from .decorator import sequential_deduplication

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

def cell_to_boundary(rhealpix_id: str) -> Polygon:
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
    rhealpix_dggs = RHEALPixDGGS(
        ellipsoid=WGS84_ELLIPSOID, north_square=1, south_square=3, N_side=3
    )
    rhealpix_cell = rhealpix_dggs.cell(rhealpix_uids)
    shapely_vertices = [
        tuple(my_round(coord, 14) for coord in vertex)
        for vertex in rhealpix_cell.vertices(plane=False)
    ]
    if shapely_vertices[0] != shapely_vertices[-1]:
        shapely_vertices.append(shapely_vertices[0])
    shapely_vertices = fix_rhealpix_antimeridian_cells(shapely_vertices)
    return Polygon(shapely_vertices)        

# def polyfill(geometry: MultiPolyOrPoly, resolution: int) -> Set[str]:
#     """rhealpix.polyfill accepting a shapely (Multi)Polygon

#     Parameters
#     ----------
#     geometry : Polygon or Multipolygon
#         Polygon to fill
#     resolution : int
#         rhealpix resolution of the filling cells

#     Returns
#     -------
#     Set of rhealpix addresses

#     Raises
#     ------
#     TypeError if geometry is not a Polygon or MultiPolygon
#     """
#     if isinstance(geometry, (Polygon, MultiPolygon)):
#         rhealpixshape = rhealpix.geo_to_rhealpixshape(geometry)
#         return set(rhealpix.polygon_to_cells(rhealpixshape, resolution))
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")

# @sequential_deduplication
# def linetrace(geometry: MultiLineOrLine, resolution: int) -> Iterator[str]:
#     """rhealpix.polyfill equivalent for shapely (Multi)LineString
#     Does not represent lines with duplicate sequential cells,
#     but cells may repeat non-sequentially to represent
#     self-intersections

#     Parameters
#     ----------
#     geometry : LineString or MultiLineString
#         Line to trace with rhealpix cells
#     resolution : int
#         rhealpix resolution of the tracing cells

#     Returns
#     -------
#     Set of rhealpix addresses

#     Raises
#     ------
#     TypeError if geometry is not a LineString or a MultiLineString
#     """
#     if isinstance(geometry, MultiLineString):
#         # Recurse after getting component linestrings from the multiline
#         for line in map(lambda geom: linetrace(geom, resolution), geometry.geoms):
#             yield from line
#     elif isinstance(geometry, LineString):
#         coords = zip(geometry.coords, geometry.coords[1:])
#         while (vertex_pair := next(coords, None)) is not None:
#             i, j = vertex_pair
#             a = rhealpix.latlng_to_cell(*i[::-1], resolution)
#             b = rhealpix.latlng_to_cell(*j[::-1], resolution)
#             yield from rhealpix.grid_path_cells(a, b)  # inclusive of a and b
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")
