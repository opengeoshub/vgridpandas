"""S2Pandas module for S2 cell operations on pandas DataFrames and GeoDataFrames."""

from typing import Union, Optional
from shapely.geometry import (
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
)
from vgrid.dggs import s2
from vgrid.utils.geometry import check_predicate
from vgrid.utils.io import validate_s2_resolution
import pandas as pd
import geopandas as gpd
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgrid.conversion.latlon2dggs import latlon2s2 as latlon_to_s2
from vgrid.conversion.dggs2geo.s22geo import s22geo as s2_to_geo
from vgridpandas.utils.const import COLUMN_S2_POLYFILL

AnyDataFrame = Union[DataFrame, GeoDataFrame]


def poly2s2(geometry, resolution, predicate=None, compact=False, fix_antimeridian=None):
    """Convert polygon or line geometries to S2 grid cell tokens."""
    resolution = validate_s2_resolution(resolution)
    s2_tokens = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        min_lon, min_lat, max_lon, max_lat = poly.bounds
        level = resolution
        coverer = s2.RegionCoverer()
        coverer.min_level = level
        coverer.max_level = level
        region = s2.LatLngRect(
            s2.LatLng.from_degrees(min_lat, min_lon),
            s2.LatLng.from_degrees(max_lat, max_lon),
        )
        covering = coverer.get_covering(region)
        cell_ids = covering
        if compact:
            covering = s2.CellUnion(covering)
            covering.normalize()
            cell_ids = covering.cell_ids()

        for cell_id in cell_ids:
            cell_token = s2.CellId.to_token(cell_id)
            cell_polygon = s2_to_geo(cell_token, fix_antimeridian=fix_antimeridian)
            if not check_predicate(cell_polygon, poly, predicate):
                continue
            s2_tokens.append(cell_token)

    return s2_tokens


def polyfill_row(
    geometry,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
    fix_antimeridian: Optional[str] = None,
) -> list:
    """Return S2 tokens covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(
            poly2s2(geometry, resolution, predicate, compact, fix_antimeridian)
        )
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            poly2s2(
                geometry,
                resolution,
                predicate="intersect",
                compact=False,
                fix_antimeridian=fix_antimeridian,
            )
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
    return list(tokens)


@pd.api.extensions.register_dataframe_accessor("s2")
class S2Pandas:
    def __init__(self, df: DataFrame):
        self._df = df

    def latlon2s2(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds S2 token to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            S2 resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the column with S2 token is set as index, default False

        Returns
        -------
        (Geo)DataFrame with S2 token and resolution columns added

        """

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        s2_tokens = [latlon_to_s2(lat, lon, resolution) for lat, lon in zip(lats, lons)]

        s2_col = "s2"
        df = self._df.assign(**{s2_col: s2_tokens, "s2_res": resolution})
        if set_index:
            return df.set_index(s2_col)
        return df

    def s22geo(
        self, s2_col: str = None, fix_antimeridian: Optional[str] = None
    ) -> GeoDataFrame:
        """Add geometry with S2 geometry to the DataFrame."""
        if s2_col is not None:
            if s2_col not in self._df.columns:
                raise ValueError(f"Column '{s2_col}' not found in DataFrame")
            ids = self._df[s2_col]
        else:
            if "s2" not in self._df.columns:
                raise ValueError("Column 's2' not found in DataFrame")
            ids = self._df["s2"]
        return dggs_ids_to_geodataframe(
            self._df, ids, s2_to_geo, fix_antimeridian=fix_antimeridian
        )

    def polyfill(
        self,
        resolution: int,
        predicate: str = None,
        compact: bool = False,
        explode: bool = False,
        fix_antimeridian: Optional[str] = None,
    ) -> AnyDataFrame:
        """
        Parameters
        ----------
        resolution : int
            S2 resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the S2 tokens
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        fix_antimeridian : str, optional
            Antimeridian fix: 'shift', 'shift_balanced', 'shift_west', 'shift_east', or 'split'

        Returns
        -------
        (Geo)DataFrame with S2 tokens in column 's2', exploded to one row per cell if explode=True.
        """
        result = self._df.geometry.apply(
            lambda geom: polyfill_row(
                geom, resolution, predicate, compact, fix_antimeridian
            )
        )

        if not explode:
            return self._df.assign(**{COLUMN_S2_POLYFILL: result})

        result = result.explode().to_frame(COLUMN_S2_POLYFILL)

        return self._df.join(result)

    def s2bin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
        fix_antimeridian: Optional[str] = None,
    ) -> GeoDataFrame:
        """Bin points into S2 cells and compute statistics."""
        s2_col = "s2"
        df = self.latlon2s2(resolution, lat_col, lon_col)
        result = aggregate_bin(df, s2_col, stats, numeric_col, category_col)
        return result.s2.s22geo(s2_col=s2_col, fix_antimeridian=fix_antimeridian)
