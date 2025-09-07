from typing import Union, Set, Iterator
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, box
from shapely.ops import transform
import h3
from vgridpandas.utils.decorator import sequential_deduplication
from vgrid.utils.geometry import fix_h3_antimeridian_cells
from vgrid.utils.geometry import check_predicate
from vgrid.conversion.dggs2geo.h32geo import h32geo
from vgrid.utils.geometry import geodesic_buffer

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]


def poly2h3(geometry, resolution, predicate=None, compact=False):
    """
    Convert polygon geometries (Polygon, MultiPolygon) to H3 grid cells.

    Args:
        resolution (int): H3 resolution level [0..15]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact (bool): Enable H3 compact mode

    Returns:
        list: List of H3 IDs intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2h3(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """
    h3_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        bbox = box(*poly.bounds)
        distance = h3.average_hexagon_edge_length(resolution, unit="m") * 2
        bbox_buffer = geodesic_buffer(bbox, distance)
        bbox_buffer_cells = h3.geo_to_cells(bbox_buffer, resolution)
        if compact:
            bbox_buffer_cells = h3.compact_cells(bbox_buffer_cells)

        for bbox_buffer_cell in bbox_buffer_cells:
            cell_polygon = h32geo(bbox_buffer_cell)
            if not check_predicate(cell_polygon, poly, predicate):
                continue
            h3_ids.append(bbox_buffer_cell)

    return h3_ids


def polyfill(
    geometry: Union[MultiPolyOrPoly, MultiLineOrLine],
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """h3.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon, MultiPolygon, LineString, or MultiLineString
        Geometry to fill
    resolution : int
        H3 resolution of the filling cells
    predicate : str, optional
        Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
    compact : bool, optional
        Enable H3 compact mode

    Returns
    -------
    Set of H3 IDs

    Raises
    ------
    TypeError if geometry is not a supported type
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(poly2h3(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(poly2h3(geometry, resolution, predicate="intersect", compact=False))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")


def polyfill_native(geometry: MultiPolyOrPoly, resolution: int) -> Set[str]:
    """h3.polyfill accepting a shapely (Multi)Polygon

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        H3 resolution of the filling cells

    Returns
    -------
    Set of H3 IDs

    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        h3shape = h3.geo_to_h3shape(geometry)
        return set(h3.polygon_to_cells(h3shape, resolution))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")


def cell_to_boundary_lng_lat(h3_id: str) -> Polygon:
    """h3.h3_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    h3_id : str
        H3 ID to convert to a boundary

    Returns
    -------
    Polygon representing the H3 cell boundary
    """
    boundary = h3.cell_to_boundary(h3_id)
    fixed_boundary = fix_h3_antimeridian_cells(boundary)
    return _switch_lat_lng(Polygon(fixed_boundary))


def _switch_lat_lng(geometry: MultiPolyOrPoly) -> MultiPolyOrPoly:
    """Switches the order of coordinates in a Polygon or MultiPolygon

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to switch coordinates

    Returns
    -------
    Polygon or Multipolygon with switched coordinates
    """
    return transform(lambda x, y: (y, x), geometry)


@sequential_deduplication
def linetrace(geometry: MultiLineOrLine, resolution: int) -> Iterator[str]:
    """h3.polyfill equivalent for shapely (Multi)LineString
    Does not represent lines with duplicate sequential cells,
    but cells may repeat non-sequentially to represent
    self-intersections

    Parameters
    ----------
    geometry : LineString or MultiLineString
        Line to trace with H3 cells
    resolution : int
        H3 resolution of the tracing cells

    Returns
    -------
    Set of H3 IDs

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
            a = h3.latlng_to_cell(*i[::-1], resolution)
            b = h3.latlng_to_cell(*j[::-1], resolution)
            yield from h3.grid_path_cells(a, b)  # inclusive of a and b
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
