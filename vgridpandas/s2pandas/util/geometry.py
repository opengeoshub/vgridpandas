from typing import Union, Set, Iterator
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.ops import transform
from vgrid.utils import s2
from vgrid.utils.antimeridian import fix_polygon

from .decorator import sequential_deduplication

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]


# def polyfill(geometry: MultiPolyOrPoly, resolution: int) -> Set[str]:
#     """s2.polyfill accepting a shapely (Multi)Polygon

#     Parameters
#     ----------
#     geometry : Polygon or Multipolygon
#         Polygon to fill
#     resolution : int
#         s2 resolution of the filling cells

#     Returns
#     -------
#     Set of s2 addresses

#     Raises
#     ------
#     TypeError if geometry is not a Polygon or MultiPolygon
#     """
#     if isinstance(geometry, (Polygon, MultiPolygon)):
#         s2shape = s2.geo_to_s2shape(geometry)
#         return set(s2.polygon_to_cells(s2shape, resolution))
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")


def cell_to_boundary(s2_token: str) -> Polygon:
    """s2.s2_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    s2_id : str
        s2 ID to convert to a boundary

    Returns
    -------
    Polygon representing the s2 cell boundary
    """
    cell_id = s2.CellId.from_token(s2_token)
    cell = s2.Cell(cell_id)
    vertices = [cell.get_vertex(i) for i in range(4)]
    shapely_vertices = []
    for vertex in vertices:
        lat_lng = s2.LatLng.from_point(vertex)
        longitude = lat_lng.lng().degrees
        latitude = lat_lng.lat().degrees
        shapely_vertices.append((longitude, latitude))
    shapely_vertices.append(shapely_vertices[0])
    cell_polygon = fix_polygon(Polygon(shapely_vertices))
    return cell_polygon
        

@sequential_deduplication
def linetrace(geometry: MultiLineOrLine, resolution: int) -> Iterator[str]:
    """s2.polyfill equivalent for shapely (Multi)LineString
    Does not represent lines with duplicate sequential cells,
    but cells may repeat non-sequentially to represent
    self-intersections

    Parameters
    ----------
    geometry : LineString or MultiLineString
        Line to trace with s2 cells
    resolution : int
        s2 resolution of the tracing cells

    Returns
    -------
    Set of s2 addresses

    Raises
    ------
    TypeError if geometry is not a LineString or a MultiLineString
    """
    if isinstance(geometry, MultiLineString):
        # Recurse after getting component linestrings from the multiline
        for line in map(lambda geom: linetrace(geom, resolution), geometry.geoms):
            yield from line
    elif isinstance(geometry, LineString):
        coords = zip(geometry.coords, geometry.coords[1:])
        while (vertex_pair := next(coords, None)) is not None:
            i, j = vertex_pair
            a = s2.latlng_to_cell(*i[::-1], resolution)
            b = s2.latlng_to_cell(*j[::-1], resolution)
            yield from s2.grid_path_cells(a, b)  # inclusive of a and b
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
