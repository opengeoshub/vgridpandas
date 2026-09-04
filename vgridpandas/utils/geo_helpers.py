"""Shared helpers for DGGS id to geometry conversion."""

from typing import Callable, Iterator, Optional

import pandas as pd
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon
from vgrid.utils.geometry import strip_duplicate_and_collinear_vertices


def dggs_id_to_polygon(dggs_id, to_geo: Callable, **to_geo_kwargs) -> Polygon:
    geom = to_geo(dggs_id, **to_geo_kwargs)
    if isinstance(geom, list):
        return MultiPolygon(geom) if len(geom) > 1 else geom[0]
    return geom if geom is not None else Polygon()


def dggs_ids_to_geometries(dggs_ids, to_geo: Callable, **to_geo_kwargs) -> list:
    """Process DGGS ids (scalar or list per row) into geometries."""
    geometries = []
    for row_dggs_ids in dggs_ids:
        try:
            if pd.isna(row_dggs_ids):
                geometries.append(Polygon())
            elif isinstance(row_dggs_ids, list):
                if len(row_dggs_ids) == 0:
                    geometries.append(Polygon())
                else:
                    cell_geometries = [
                        dggs_id_to_polygon(dggs_id, to_geo, **to_geo_kwargs)
                        for dggs_id in row_dggs_ids
                    ]
                    geometries.append(MultiPolygon(cell_geometries))
            else:
                geometries.append(
                    dggs_id_to_polygon(row_dggs_ids, to_geo, **to_geo_kwargs)
                )
        except (ValueError, TypeError):
            if isinstance(row_dggs_ids, list):
                if len(row_dggs_ids) == 0:
                    geometries.append(Polygon())
                else:
                    cell_geometries = [
                        dggs_id_to_polygon(dggs_id, to_geo, **to_geo_kwargs)
                        for dggs_id in row_dggs_ids
                    ]
                    geometries.append(MultiPolygon(cell_geometries))
            else:
                try:
                    geometries.append(
                        dggs_id_to_polygon(row_dggs_ids, to_geo, **to_geo_kwargs)
                    )
                except Exception:
                    geometries.append(Polygon())
    return geometries


def dggs_ids_to_geodataframe(
    df,
    dggs_ids,
    to_geo: Callable,
    fix_antimeridian: Optional[str] = None,
    split_antimeridian: Optional[bool] = None,
    to_geo_kwargs: Optional[dict] = None,
):
    """Build a GeoDataFrame from a DGGS id series using ``to_geo``."""
    import geopandas as gpd

    kwargs = dict(to_geo_kwargs or {})
    if fix_antimeridian is not None and "fix_antimeridian" not in kwargs:
        kwargs["fix_antimeridian"] = fix_antimeridian
    if split_antimeridian is not None and "split_antimeridian" not in kwargs:
        kwargs["split_antimeridian"] = split_antimeridian
    geometries = dggs_ids_to_geometries(dggs_ids, to_geo, **kwargs)
    result_df = df.copy()
    result_df["geometry"] = geometries
    return gpd.GeoDataFrame(result_df, crs="epsg:4326")


def linetrace_polyline(geometry, segment_cells_fn) -> Iterator:
    """Yield cell ids along a (Multi)LineString using a vgrid segment walker.

    ``segment_cells_fn(start_xy, end_xy)`` must return an ordered list of cell ids
    for one segment (same contract as ``_s2_segment_cells`` / ``_dggal_segment_cells``).
    Consecutive duplicate ids across segments are skipped.
    """
    if isinstance(geometry, MultiLineString):
        for line in geometry.geoms:
            yield from linetrace_polyline(line, segment_cells_fn)
        return
    if not isinstance(geometry, LineString):
        raise TypeError(f"Unknown type {type(geometry)}")

    coords = strip_duplicate_and_collinear_vertices(geometry)
    if len(coords) < 2:
        return

    last_id = None
    for i in range(len(coords) - 1):
        for cell_id in segment_cells_fn(coords[i], coords[i + 1]):
            if last_id == cell_id:
                continue
            last_id = cell_id
            yield cell_id
