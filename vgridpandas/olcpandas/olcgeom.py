from typing import Union, Set, Iterator
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.wkt import loads
from shapely.ops import transform
from .decorator import sequential_deduplication
from vgrid.utils import olc

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

def cell_to_boundary(olc_id: str) -> Polygon:
    """olc.olc_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    olc_id : str
        olc ID to convert to a boundary

    Returns
    -------
    Polygon representing the olc cell boundary
    """
    # Base octahedral face definitions
    coord = olc.decode(olc_id)   
    # Create the bounding box coordinates for the polygon
    min_lat, min_lon = coord.latitudeLo, coord.longitudeLo
    max_lat, max_lon = coord.latitudeHi, coord.longitudeHi
    # Define the polygon based on the bounding box
    cell_polygon = Polygon(
        [
            [min_lon, min_lat],  # Bottom-left corner
            [max_lon, min_lat],  # Bottom-right corner
            [max_lon, max_lat],  # Top-right corner
            [min_lon, max_lat],  # Top-left corner
            [min_lon, min_lat],  # Closing the polygon (same as the first point)
        ]
    )
    return cell_polygon

# def polyfill(geometry: MultiPolyOrPoly, resolution: int) -> Set[str]:
#     """olc.polyfill accepting a shapely (Multi)Polygon

#     Parameters
#     ----------
#     geometry : Polygon or Multipolygon
#         Polygon to fill
#     resolution : int
#         olc resolution of the filling cells

#     Returns
#     -------
#     Set of olc addresses

#     Raises
#     ------
#     TypeError if geometry is not a Polygon or MultiPolygon
#     """
#     if isinstance(geometry, (Polygon, MultiPolygon)):
#         qtmshape = olc.geo_to_qtmshape(geometry)
#         return set(olc.polygon_to_cells(qtmshape, resolution))
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")

# @sequential_deduplication
# def linetrace(geometry: MultiLineOrLine, resolution: int) -> Iterator[str]:
#     """olc.polyfill equivalent for shapely (Multi)LineString
#     Does not represent lines with duplicate sequential cells,
#     but cells may repeat non-sequentially to represent
#     self-intersections

#     Parameters
#     ----------
#     geometry : LineString or MultiLineString
#         Line to trace with olc cells
#     resolution : int
#         olc resolution of the tracing cells

#     Returns
#     -------
#     Set of olc addresses

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
#             a = olc.latlng_to_cell(*i[::-1], resolution)
#             b = olc.latlng_to_cell(*j[::-1], resolution)
#             yield from olc.grid_path_cells(a, b)  # inclusive of a and b
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")
