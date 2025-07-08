from typing import Union, Set, Iterator
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.wkt import loads
from shapely.ops import transform
from .decorator import sequential_deduplication
from vgrid.utils import geohash

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

def cell_to_boundary(geohash_id: str) -> Polygon:
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

# def polyfill(geometry: MultiPolyOrPoly, resolution: int) -> Set[str]:
#     """geohash.polyfill accepting a shapely (Multi)Polygon

#     Parameters
#     ----------
#     geometry : Polygon or Multipolygon
#         Polygon to fill
#     resolution : int
#         geohash resolution of the filling cells

#     Returns
#     -------
#     Set of geohash addresses

#     Raises
#     ------
#     TypeError if geometry is not a Polygon or MultiPolygon
#     """
#     if isinstance(geometry, (Polygon, MultiPolygon)):
#         qtmshape = geohash.geo_to_qtmshape(geometry)
#         return set(geohash.polygon_to_cells(qtmshape, resolution))
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")

# @sequential_deduplication
# def linetrace(geometry: MultiLineOrLine, resolution: int) -> Iterator[str]:
#     """geohash.polyfill equivalent for shapely (Multi)LineString
#     Does not represent lines with duplicate sequential cells,
#     but cells may repeat non-sequentially to represent
#     self-intersections

#     Parameters
#     ----------
#     geometry : LineString or MultiLineString
#         Line to trace with geohash cells
#     resolution : int
#         geohash resolution of the tracing cells

#     Returns
#     -------
#     Set of geohash addresses

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
#             a = geohash.latlng_to_cell(*i[::-1], resolution)
#             b = geohash.latlng_to_cell(*j[::-1], resolution)
#             yield from geohash.grid_path_cells(a, b)  # inclusive of a and b
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")
