"""Shared helpers for DGGS id to geometry conversion."""

from typing import Callable, Optional

import pandas as pd
from shapely.geometry import MultiPolygon, Polygon


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
    to_geo_kwargs: Optional[dict] = None,
):
    """Build a GeoDataFrame from a DGGS id series using ``to_geo``."""
    import geopandas as gpd

    kwargs = dict(to_geo_kwargs or {})
    if fix_antimeridian is not None and "fix_antimeridian" not in kwargs:
        kwargs["fix_antimeridian"] = fix_antimeridian
    geometries = dggs_ids_to_geometries(dggs_ids, to_geo, **kwargs)
    result_df = df.copy()
    result_df["geometry"] = geometries
    return gpd.GeoDataFrame(result_df, crs="epsg:4326")
