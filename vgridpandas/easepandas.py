from typing import Union
from shapely.geometry import (
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
    box,
)
import pandas as pd
import geopandas as gpd
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgridpandas.utils.const import EASE_COL
from vgrid.conversion.latlon2dggs import latlon2ease as latlon_to_ease
from vgrid.conversion.dggs2geo.ease2geo import ease2geo as ease_to_geo
from vgrid.conversion.dggscompact.easecompact import ease_compact
from vgrid.utils.geometry import check_predicate
from vgrid.utils.io import validate_ease_resolution
from ease_dggs.constants import levels_specs, geo_crs, ease_crs
from ease_dggs.dggs.grid_addressing import geo_polygon_to_grid_ids

AnyDataFrame = Union[DataFrame, GeoDataFrame]


def poly2ease(
    geometry,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> list:
    """
    Convert polygon or line geometries to EASE grid cells.

    Mirrors ``polygon2ease`` and ``polyline2ease`` in vgrid: bbox discovery via
    ``geo_polygon_to_grid_ids``, then filter with ``ease2geo`` cell polygons.
    Polygons use ``predicate``; lines use intersection.
    Compact mode applies to polygons after predicate filtering only (not lines).

    Args:
        resolution (int): EASE resolution level [0..6]
        geometry: Polygon, MultiPolygon, LineString, or MultiLineString
        predicate (str, optional): Spatial predicate for polygons
            ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact (bool, optional): Enable EASE compact mode for polygons

    Returns:
        list: List of EASE cell ids

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2ease(poly, 4, predicate="intersect", compact=True)
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

    is_line = isinstance(geometry, (LineString, MultiLineString))
    for poly in polys:
        if poly is None or poly.is_empty:
            continue

        poly_bbox = box(*poly.bounds)
        cells_bbox = geo_polygon_to_grid_ids(
            poly_bbox.wkt,
            resolution,
            geo_crs,
            ease_crs,
            levels_specs,
            return_centroids=True,
            wkt_geom=True,
        )
        candidate_ids = cells_bbox["result"]["data"]
        if not candidate_ids:
            continue

        if compact and is_line:
            candidate_ids = ease_compact(candidate_ids)

        poly_ids = []
        for ease_id in candidate_ids:
            ease_id_str = str(ease_id)
            cell_polygon = ease_to_geo(ease_id_str)
            if not cell_polygon:
                continue
            if is_line:
                if cell_polygon.intersects(poly):
                    poly_ids.append(ease_id_str)
            elif check_predicate(cell_polygon, poly, predicate):
                poly_ids.append(ease_id_str)

        if compact and poly_ids and not is_line:
            poly_ids = [str(cell_id) for cell_id in ease_compact(poly_ids)]

        ease_ids.extend(poly_ids)

    return list(dict.fromkeys(ease_ids))


def polyfill_row(geometry, resolution, predicate=None, compact=False) -> list:
    """Return cell ids covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(poly2ease(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            poly2ease(geometry, resolution, predicate="intersect", compact=False)
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
    return list(tokens)


@pd.api.extensions.register_dataframe_accessor("ease")
class EASEPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    def latlon2ease(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds EASE ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            EASE resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with EASE ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with EASE IDs added
        """
        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        ease_ids = [
            latlon_to_ease(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        ease_col = EASE_COL
        assign_arg = {ease_col: ease_ids, f"{ease_col}_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(ease_col)
        return df

    def ease2geo(self, ease_col: str = None) -> GeoDataFrame:
        """Add geometry with EASE geometry to the DataFrame."""
        if ease_col is not None:
            if ease_col not in self._df.columns:
                raise ValueError(f"Column '{ease_col}' not found in DataFrame")
            ids = self._df[ease_col]
        else:
            if EASE_COL not in self._df.columns:
                raise ValueError(f"Column '{EASE_COL}' not found in DataFrame")
            ids = self._df[EASE_COL]
        return dggs_ids_to_geodataframe(self._df, ids, ease_to_geo)

    def polyfill(
        self,
        resolution: int,
        predicate: str = None,
        compact: bool = False,
        explode: bool = False,
    ) -> AnyDataFrame:
        """
        Parameters
        ----------
        resolution : int
            EASE resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the EASE IDs
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        """
        result = self._df.geometry.apply(
            lambda geom: polyfill_row(geom, resolution, predicate, compact)
        )

        if not explode:
            assign_args = {EASE_COL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(EASE_COL)
        return self._df.join(result)

    def easebin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> GeoDataFrame:
        """
        Bin points into ease cells and compute statistics.
        """
        ease_col = EASE_COL
        df = self.latlon2ease(resolution, lat_col, lon_col)
        result = aggregate_bin(df, ease_col, stats, numeric_col, category_col)
        return result.ease.ease2geo(ease_col=ease_col)
