from typing import Union, Set, Iterator
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.ops import transform
from vgrid.utils.qtm import constructGeometry, qtm_id_to_facet
from .decorator import sequential_deduplication

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

def cell_to_boundary(qtm_id: str) -> Polygon:
    """qtm.qtm_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    qtm_id : str
        QTM ID to convert to a boundary

    Returns
    -------
    Polygon representing the qtm cell boundary
    """
    # Base octahedral face definitions
    facet = qtm_id_to_facet(qtm_id)
    cell_polygon = constructGeometry(facet)
    return cell_polygon

   
# def polyfill(geometry: MultiPolyOrPoly, resolution: int) -> Set[str]:
#     """qtm.polyfill accepting a shapely (Multi)Polygon

#     Parameters
#     ----------
#     geometry : Polygon or Multipolygon
#         Polygon to fill
#     resolution : int
#         qtm resolution of the filling cells

#     Returns
#     -------
#     Set of qtm addresses

#     Raises
#     ------
#     TypeError if geometry is not a Polygon or MultiPolygon
#     """
#     if isinstance(geometry, (Polygon, MultiPolygon)):
#         qtmshape = qtm.geo_to_qtmshape(geometry)
#         return set(qtm.polygon_to_cells(qtmshape, resolution))
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")

# @sequential_deduplication
# def linetrace(geometry: MultiLineOrLine, resolution: int) -> Iterator[str]:
#     """qtm.polyfill equivalent for shapely (Multi)LineString
#     Does not represent lines with duplicate sequential cells,
#     but cells may repeat non-sequentially to represent
#     self-intersections

#     Parameters
#     ----------
#     geometry : LineString or MultiLineString
#         Line to trace with qtm cells
#     resolution : int
#         qtm resolution of the tracing cells

#     Returns
#     -------
#     Set of qtm addresses

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
#             a = qtm.latlng_to_cell(*i[::-1], resolution)
#             b = qtm.latlng_to_cell(*j[::-1], resolution)
#             yield from qtm.grid_path_cells(a, b)  # inclusive of a and b
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")
