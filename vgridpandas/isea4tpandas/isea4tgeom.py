from typing import Union, Set, Iterator
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.wkt import loads
from shapely.ops import transform
from .decorator import sequential_deduplication
import platform
MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

if platform.system() == "Windows":
    from vgrid.utils.eaggr.enums.shape_string_format import ShapeStringFormat
    from vgrid.utils.eaggr.eaggr import Eaggr
    from vgrid.utils.eaggr.shapes.dggs_cell import DggsCell
    from vgrid.utils.eaggr.enums.model import Model
    from vgrid.generator.isea4tgrid import fix_isea4t_wkt, fix_isea4t_antimeridian_cells


def cell_to_boundary(isea4t_id: str) -> Polygon:
    """isea4t.isea4t_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    isea4t_id : str
        ISEA4T ID to convert to a boundary

    Returns
    -------
    Polygon representing the isea4t cell boundary
    """
    # Base octahedral face definitions
    if platform.system() == "Windows":       
        isea4t_dggs = Eaggr(Model.ISEA4T)
        cell_to_shape = isea4t_dggs.convert_dggs_cell_outline_to_shape_string(
            DggsCell(isea4t_id), ShapeStringFormat.WKT
        )
        cell_to_shape_fixed = loads(fix_isea4t_wkt(cell_to_shape))
        if (
            isea4t_id.startswith("00")
            or isea4t_id.startswith("09")
            or isea4t_id.startswith("14")
            or isea4t_id.startswith("04")
            or isea4t_id.startswith("19")
        ):
            cell_to_shape_fixed = fix_isea4t_antimeridian_cells(cell_to_shape_fixed)
        
        cell_polygon = Polygon(list(cell_to_shape_fixed.exterior.coords))
        return cell_polygon
   
# def polyfill(geometry: MultiPolyOrPoly, resolution: int) -> Set[str]:
#     """isea4t.polyfill accepting a shapely (Multi)Polygon

#     Parameters
#     ----------
#     geometry : Polygon or Multipolygon
#         Polygon to fill
#     resolution : int
#         isea4t resolution of the filling cells

#     Returns
#     -------
#     Set of isea4t addresses

#     Raises
#     ------
#     TypeError if geometry is not a Polygon or MultiPolygon
#     """
#     if isinstance(geometry, (Polygon, MultiPolygon)):
#         qtmshape = isea4t.geo_to_qtmshape(geometry)
#         return set(isea4t.polygon_to_cells(qtmshape, resolution))
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")

# @sequential_deduplication
# def linetrace(geometry: MultiLineOrLine, resolution: int) -> Iterator[str]:
#     """isea4t.polyfill equivalent for shapely (Multi)LineString
#     Does not represent lines with duplicate sequential cells,
#     but cells may repeat non-sequentially to represent
#     self-intersections

#     Parameters
#     ----------
#     geometry : LineString or MultiLineString
#         Line to trace with isea4t cells
#     resolution : int
#         isea4t resolution of the tracing cells

#     Returns
#     -------
#     Set of isea4t addresses

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
#             a = isea4t.latlng_to_cell(*i[::-1], resolution)
#             b = isea4t.latlng_to_cell(*j[::-1], resolution)
#             yield from isea4t.grid_path_cells(a, b)  # inclusive of a and b
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")
