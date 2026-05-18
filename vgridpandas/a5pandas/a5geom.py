from typing import Union, Set
from shapely.geometry import (
    Point,
    MultiPoint,
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
    box,
)
from collections import deque
import geopandas as gpd
import a5
from vgrid.utils.geometry import check_predicate
from vgrid.utils.io import validate_a5_resolution
from vgrid.conversion.dggs2geo.a52geo import a52geo, a52geo_u64
from vgrid.conversion.dggscompact.a5compact import a5compact

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]
MultiPointOrPoint = Union[Point, MultiPoint]


def poly2a5(geometry, resolution, predicate=None, compact=False, fix_antimeridian=False):
    """
    Convert polygon geometries (Polygon, MultiPolygon) to A5 grid cells.

    Args:
        resolution (int): A5 resolution level [0..29]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        fix_antimeridian (bool, optional): Fix antimeridian cells if True.
    Returns:
        list: List of A5 hexes intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2a5(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_a5_resolution(resolution)
    a5_hexes = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        if poly is None or poly.is_empty:
            continue

        min_lng, min_lat, max_lng, max_lat = poly.bounds
        bbox_polygon = box(min_lng, min_lat, max_lng, max_lat)

        bbox_center_lon = bbox_polygon.centroid.x
        bbox_center_lat = bbox_polygon.centroid.y
        seed_cell_id = a5.lonlat_to_cell((bbox_center_lon, bbox_center_lat), resolution)
        seed_cell_polygon = a52geo_u64(
            seed_cell_id, split_antimeridian=fix_antimeridian
        )

        if seed_cell_polygon is not None and seed_cell_polygon.contains(bbox_polygon):
            seed_cell_hex = a5.u64_to_hex(seed_cell_id)
            if check_predicate(seed_cell_polygon, poly, predicate):
                a5_hexes.append(seed_cell_hex)
            continue

        intersecting_cells = {}  # {cell_u64: cell_polygon}
        covered_cells = set()
        queue = deque([seed_cell_id])

        while queue:
            current_cell_id = queue.popleft()
            if current_cell_id in covered_cells:
                continue
            covered_cells.add(current_cell_id)

            cell_polygon = a52geo_u64(
                current_cell_id, split_antimeridian=fix_antimeridian
            )
            if cell_polygon is None or cell_polygon.is_empty:
                continue

            if cell_polygon.intersects(bbox_polygon):
                intersecting_cells[current_cell_id] = cell_polygon
                neighbors = a5.uncompact(
                    a5.grid_disk_vertex(current_cell_id, 1), resolution
                )
                for neighbor_id in neighbors:
                    if neighbor_id not in covered_cells:
                        queue.append(neighbor_id)

        for cell_id, cell_polygon in intersecting_cells.items():
            if check_predicate(cell_polygon, poly, predicate):
                a5_hexes.append(a5.u64_to_hex(cell_id))

    a5_hexes = list(dict.fromkeys(a5_hexes))

    if compact and a5_hexes:
        # Create a GeoDataFrame with A5 hex codes and their geometries
        a5_data = []
        for a5_hex in a5_hexes:
            try:
                # Convert A5 hex to geometry
                geometry = a52geo(a5_hex, fix_antimeridian=fix_antimeridian)        
                a5_data.append({"a5": a5_hex, "geometry": geometry})
            except Exception:
                # Skip invalid A5 hex codes
                continue

        if a5_data:
            temp_gdf = gpd.GeoDataFrame(a5_data, crs="EPSG:4326")

            # Use a5compact function directly
            compacted_gdf = a5compact(temp_gdf, a5_hex="a5", output_format="gpd")

            if compacted_gdf is not None:
                # Extract A5 hex codes from compacted result
                a5_hexes = compacted_gdf["a5"].tolist()
            # If compaction failed, keep original results

    return a5_hexes


def polyfill(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
    fix_antimeridian: bool = False,
) -> Set[str]:
    """a5.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        A5 resolution of the filling cells
    fix_antimeridian : bool, optional
        Fix antimeridian cells if True.
    Returns
    -------
    Set of A5 Tokens

    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(poly2a5(geometry, resolution, predicate, compact, fix_antimeridian))
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(poly2a5(geometry, resolution, predicate="intersect", compact=False, fix_antimeridian=fix_antimeridian))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
