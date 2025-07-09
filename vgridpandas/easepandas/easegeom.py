from typing import Union, Set, Iterator
from shapely.geometry import box, Polygon, MultiPolygon, LineString, MultiLineString
from vgrid.utils.easedggs.constants import levels_specs, geo_crs, ease_crs
from vgrid.utils.easedggs.dggs.grid_addressing import (
    grid_ids_to_geos,
    geos_to_grid_ids,
    geo_polygon_to_grid_ids,
)
from vgrid.conversion.dggscompact import ease_compact
from vgridpandas.utils.geom import check_predicate

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

def validate_ease_resolution(resolution):
    """
    Validate that EASE resolution is in the valid range [0..6].

    Args:
        resolution: Resolution value to validate

    Returns:
        int: Validated resolution value

    Raises:
        ValueError: If resolution is not in range [0..6]
        TypeError: If resolution is not an integer
    """
    if not isinstance(resolution, int):
        raise TypeError(
            f"Resolution must be an integer, got {type(resolution).__name__}"
        )

    if resolution < 0 or resolution > 6:
        raise ValueError(f"Resolution must be in range [0..6], got {resolution}")

    return resolution

def cell2boundary(ease_id: str) -> Polygon:
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

def poly2ease(geometry: MultiPolyOrPoly, resolution: int, predicate: str = None, compact: bool = False) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to ease grid cells.

    Args:
        resolution (int): EASE resolution level [0..6]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of ease ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2ease(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_ease_resolution(resolution)
    ease_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        poly_bbox = box(*poly.bounds)
        polygon_bbox_wkt = poly_bbox.wkt
        cells_bbox = geo_polygon_to_grid_ids(
            polygon_bbox_wkt,
            resolution,
            geo_crs,
            ease_crs,
            levels_specs,
            return_centroids=True,
            wkt_geom=True,
        )
        ease_cells = cells_bbox["result"]["data"]
        if compact:
            ease_cells = ease_compact(ease_cells)
        for ease_cell in ease_cells:
            cell_resolution = int(ease_cell[1])
            level_spec = levels_specs[cell_resolution]
            n_row = level_spec["n_row"]
            n_col = level_spec["n_col"]
            geo = grid_ids_to_geos([ease_cell])
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
            if check_predicate(cell_polygon, poly, predicate):
                ease_id  = str(ease_cell)
                ease_ids.append(ease_id)
    return ease_ids

def polyfill(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """ease.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        ease resolution of the filling cells

    Returns
    -------
    Set of ease ids

    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(poly2ease(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(poly2ease(geometry, resolution, predicate='intersect', compact=False))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
