"""S2Pandas module for S2 cell operations on pandas DataFrames and GeoDataFrames."""

from typing import Union
from shapely.geometry import Polygon
import pandas as pd
import geopandas as gpd
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgrid.conversion.latlon2dggs import latlon2dggrid as latlon_to_dggrid
from vgrid.conversion.dggs2geo.dggrid2geo import dggrid2geo as dggrid_to_geo

AnyDataFrame = Union[DataFrame, GeoDataFrame]


@pd.api.extensions.register_dataframe_accessor("dggrid")
class DGGRIDPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    def latlon2dggrid(
        self,
        dggrid_instance,
        dggs_type: str,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
        address_type: str = "SEQNUM",
    ) -> AnyDataFrame:
        """Adds dggrid id to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        dggrid_instance : DGGRIDv7
            DGGRID instance
        dggs_type : str
            dggrid type
        resolution : int
            dggrid resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with dggrid id is set as index, default 'True'
        address_type : str
            Address type, default 'SEQNUM'
        Returns
        -------
        (Geo)DataFrame with dggrid ids added

        """

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        dggrid_ids = [
            latlon_to_dggrid(
                dggrid_instance, dggs_type, lat, lon, resolution, address_type
            )
            for lat, lon in zip(lats, lons)
        ]

        dggrid_col = f"dggrid_{dggs_type.lower()}"
        assign_arg = {dggrid_col: dggrid_ids, f"{dggrid_col}_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(dggrid_col)
        return df

    def dggrid2geo(
        self,
        dggrid_instance,
        dggs_type: str,
        resolution: int,
        dggrid_col: str = None,
        address_type: str = "SEQNUM",
    ) -> GeoDataFrame:
        """Add geometry with DGGRID geometry to the DataFrame. Assumes DGGRID id.

        Parameters
        ----------
        dggrid_instance : DGGRIDv7
            DGGRID instance
        dggs_type : str
            DGGRID type
        resolution : int
            DGGRID resolution
        dggrid_col : str, optional
            Name of the column containing DGGRID ids. Defaults to ``dggrid_{dggs_type}``.
        address_type : str
            Address type, default 'SEQNUM'

        Returns
        -------
        GeoDataFrame with DGGRID geometry

        Raises
        ------
        ValueError
            When an invalid DGGRID id is encountered
        """
        if dggrid_col is None:
            dggrid_col = f"dggrid_{dggs_type.lower()}"
        if dggrid_col not in self._df.columns:
            raise ValueError(f"Column '{dggrid_col}' not found in DataFrame")

        def to_geo(token):
            gdf = dggrid_to_geo(
                dggrid_instance, dggs_type, token, resolution, address_type
            )
            return gdf.geometry.iloc[0] if gdf is not None and len(gdf) else Polygon()

        return dggs_ids_to_geodataframe(self._df, self._df[dggrid_col], to_geo)

    def dggridbin(
        self,
        dggrid_instance,
        dggs_type: str,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
        address_type: str = "SEQNUM",
    ) -> GeoDataFrame:
        """Bin points into DGGRID cells and compute statistics."""
        dggrid_col = f"dggrid_{dggs_type.lower()}"
        df = self.latlon2dggrid(
            dggrid_instance,
            dggs_type,
            resolution,
            lat_col,
            lon_col,
            address_type=address_type,
        )
        result = aggregate_bin(df, dggrid_col, stats, numeric_col, category_col)
        return result.dggrid.dggrid2geo(
            dggrid_instance,
            dggs_type,
            resolution,
            dggrid_col=dggrid_col,
            address_type=address_type,
        )
