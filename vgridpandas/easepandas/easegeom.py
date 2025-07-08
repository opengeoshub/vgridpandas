from typing import Union, Set, Iterator
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.wkt import loads
from shapely.ops import transform
from .decorator import sequential_deduplication
from vgrid.utils.easedggs.constants import levels_specs
from vgrid.utils.easedggs.dggs.grid_addressing import grid_ids_to_geos

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

def cell_to_boundary(ease_id: str) -> Polygon:
    """ease.ease_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    ease_id : str
        EASE ID to convert to a boundary

    Returns
    -------
    Polygon representing the ease cell boundary
    """
    # Base octahedral face definitions
    level = int(ease_id[1])
    level_spec = levels_specs[level]
    n_row = level_spec["n_row"]
    n_col = level_spec["n_col"]
    geo = grid_ids_to_geos([ease_id])
    center_lon, center_lat = geo["result"]["data"][0]
    cell_min_lat = center_lat - (180 / (2 * n_row))
    cell_max_lat = center_lat + (180 / (2 * n_row))
    cell_min_lon = center_lon - (360 / (2 * n_col))
    cell_max_lon = center_lon + (360 / (2 * n_col))
    cell_polygon = Polygon(
        [
            [cell_min_lon, cell_min_lat],
            [cell_max_lon, cell_min_lat],
            [cell_max_lon, cell_max_lat],
            [cell_min_lon, cell_max_lat],
            [cell_min_lon, cell_min_lat],
        ]
    )
    return cell_polygon

# def polyfill(geometry: MultiPolyOrPoly, resolution: int) -> Set[str]:
#     """ease.polyfill accepting a shapely (Multi)Polygon

#     Parameters
#     ----------
#     geometry : Polygon or Multipolygon
#         Polygon to fill
#     resolution : int
#         ease resolution of the filling cells

#     Returns
#     -------
#     Set of ease addresses

#     Raises
#     ------
#     TypeError if geometry is not a Polygon or MultiPolygon
#     """
#     if isinstance(geometry, (Polygon, MultiPolygon)):
#         qtmshape = ease.geo_to_qtmshape(geometry)
#         return set(ease.polygon_to_cells(qtmshape, resolution))
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")

# @sequential_deduplication
# def linetrace(geometry: MultiLineOrLine, resolution: int) -> Iterator[str]:
#     """ease.polyfill equivalent for shapely (Multi)LineString
#     Does not represent lines with duplicate sequential cells,
#     but cells may repeat non-sequentially to represent
#     self-intersections

#     Parameters
#     ----------
#     geometry : LineString or MultiLineString
#         Line to trace with ease cells
#     resolution : int
#         ease resolution of the tracing cells

#     Returns
#     -------
#     Set of ease addresses

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
#             a = ease.latlng_to_cell(*i[::-1], resolution)
#             b = ease.latlng_to_cell(*j[::-1], resolution)
#             yield from ease.grid_path_cells(a, b)  # inclusive of a and b
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")
