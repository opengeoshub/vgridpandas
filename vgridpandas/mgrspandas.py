from typing import Union
from vgrid.conversion.latlon2dggs import latlon2mgrs as latlon_to_mgrs
from vgrid.conversion.dggs2geo.mgrs2geo import mgrs2geo as mgrs_to_geo
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
import pandas as pd
import geopandas as gpd

AnyDataFrame = Union[DataFrame, GeoDataFrame]


@pd.api.extensions.register_dataframe_accessor("mgrs")
class MGRSPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # MGRS API
    # These methods simply mirror the Vgrid mgrs API and apply mgrs functions to all rows

    def latlon2mgrs(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds MGRS ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            MGRS resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with mgrs ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with mgrs IDs added
        """

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        mgrs_ids = [
            latlon_to_mgrs(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        # mgrs_column = self._format_resolution(resolution)
        mgrs_column = "mgrs"
        assign_arg = {mgrs_column: mgrs_ids, "mgrs_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(mgrs_column)
        return df

    def mgrs2geo(self, mgrs_col: str = None) -> GeoDataFrame:
        """Add geometry with MGRS geometry to the DataFrame."""
        if mgrs_col is not None:
            if mgrs_col not in self._df.columns:
                raise ValueError(f"Column '{mgrs_col}' not found in DataFrame")
            ids = self._df[mgrs_col]
        else:
            if "mgrs" not in self._df.columns:
                raise ValueError("Column 'mgrs' not found in DataFrame")
            ids = self._df["mgrs"]
        return dggs_ids_to_geodataframe(self._df, ids, mgrs_to_geo)

    def mgrsbin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> GeoDataFrame:
        """
        Bin points into mgrs cells and compute statistics.
        """
        mgrs_col = "mgrs"
        df = self.latlon2mgrs(resolution, lat_col, lon_col)
        result = aggregate_bin(df, mgrs_col, stats, numeric_col, category_col)
        return result.mgrs.mgrs2geo(mgrs_col=mgrs_col)
