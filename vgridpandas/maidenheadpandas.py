from typing import Union
import pandas as pd
import geopandas as gpd
from vgrid.conversion.latlon2dggs import latlon2maidenhead as latlon_to_maidenhead
from vgrid.conversion.dggs2geo.maidenhead2geo import maidenhead2geo as maidenhead_to_geo
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin

AnyDataFrame = Union[DataFrame, GeoDataFrame]


@pd.api.extensions.register_dataframe_accessor("maidenhead")
class MaidenheadPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # maidenhead API
    # These methods simply mirror the Vgrid maidenhead API and apply maidenhead functions to all rows

    def latlon2maidenhead(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds maidenhead ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            maidenhead resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with maidenhead ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with maidenhead IDs added
        """

        if not isinstance(resolution, int) or resolution not in range(1, 5):
            raise ValueError("Resolution must be an integer in range [1, 4]")

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        maidenhead_ids = [
            latlon_to_maidenhead(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        # maidenhead_column = self._format_resolution(resolution)
        maidenhead_column = "maidenhead"
        assign_arg = {maidenhead_column: maidenhead_ids, "maidenhead_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(maidenhead_column)
        return df

    def maidenhead2geo(self, maidenhead_col: str = None) -> GeoDataFrame:
        """Add geometry with MAIDENHEAD geometry to the DataFrame."""
        if maidenhead_col is not None:
            if maidenhead_col not in self._df.columns:
                raise ValueError(f"Column '{maidenhead_col}' not found in DataFrame")
            ids = self._df[maidenhead_col]
        else:
            if "maidenhead" not in self._df.columns:
                raise ValueError("Column 'maidenhead' not found in DataFrame")
            ids = self._df["maidenhead"]
        return dggs_ids_to_geodataframe(self._df, ids, maidenhead_to_geo)

    def maidenheadbin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> GeoDataFrame:
        """
        Bin points into maidenhead cells and compute statistics.
        """
        maidenhead_col = "maidenhead"
        df = self.latlon2maidenhead(resolution, lat_col, lon_col)
        result = aggregate_bin(df, maidenhead_col, stats, numeric_col, category_col)
        return result.maidenhead.maidenhead2geo(maidenhead_col=maidenhead_col)
