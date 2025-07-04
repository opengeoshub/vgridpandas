from typing import Union, Set, Iterator
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.ops import transform
from vgrid.utils.gars import garsgrid

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

def cell_to_boundary(gars_id: str) -> Polygon:
    """gars.gars_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    gars_id : str
        gars ID to convert to a boundary

    Returns
    -------
    Polygon representing the gars cell boundary
    """
    gars_grid = garsgrid.GARSGrid(gars_id)
    wkt_polygon = gars_grid.polygon
    cell_polygon = Polygon(list(wkt_polygon.exterior.coords))
    return cell_polygon
    
# def polyfill(geometry: MultiPolyOrPoly, resolution: int) -> Set[str]:
#     """mgrs.polyfill accepting a shapely (Multi)Polygon

#     Parameters
#     ----------
#     geometry : Polygon or Multipolygon
#         Polygon to fill
#     resolution : int
#         mgrs resolution of the filling cells

#     Returns
#     -------
#     Set of mgrs addresses

#     Raises
#     ------
#     TypeError if geometry is not a Polygon or MultiPolygon
#     """
#     if isinstance(geometry, (Polygon, MultiPolygon)):
#         qtmshape = mgrs.geo_to_qtmshape(geometry)
#         return set(mgrs.polygon_to_cells(qtmshape, resolution))
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")

# @sequential_deduplication
# def linetrace(geometry: MultiLineOrLine, resolution: int) -> Iterator[str]:
#     """mgrs.polyfill equivalent for shapely (Multi)LineString
#     Does not represent lines with duplicate sequential cells,
#     but cells may repeat non-sequentially to represent
#     self-intersections

#     Parameters
#     ----------
#     geometry : LineString or MultiLineString
#         Line to trace with mgrs cells
#     resolution : int
#         mgrs resolution of the tracing cells

#     Returns
#     -------
#     Set of mgrs addresses

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
#             a = mgrs.latlng_to_cell(*i[::-1], resolution)
#             b = mgrs.latlng_to_cell(*j[::-1], resolution)
#             yield from mgrs.grid_path_cells(a, b)  # inclusive of a and b
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")
