from typing import Union, Callable, Sequence, Any
import warnings

from typing import Literal

import numpy as np
import shapely
import pandas as pd
import geopandas as gpd

from vgrid.conversion.latlon2dggs import latlon2maidenhead
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame

from .util.functools import wrapped_partial
from .util.geometry import cell_to_boundary
from .util.decorator import catch_invalid_maidenhead_id

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
        set_index: bool = True,
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
            latlon2maidenhead(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        colname = self._format_resolution(resolution)
        assign_arg = {colname: maidenhead_ids}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(colname)
        return df

    def maidenhead2geo(self) -> GeoDataFrame:
        """Add `geometry` with maidenhead geometry to the DataFrame. Assumes maidenhead ID.

        Returns
        -------
        GeoDataFrame with maidenhead geometry

        Raises
        ------
        ValueError
            When an invalid maidenhead ID is encountered      
        """        
        return self._apply_index_assign(
            wrapped_partial(cell_to_boundary),
            "geometry",
            finalizer=lambda x: gpd.GeoDataFrame(x, crs="epsg:4326"),
        )

    def _apply_index_assign(
        self,
        func: Callable,
        column_name: str,
        processor: Callable = lambda x: x,
        finalizer: Callable = lambda x: x,
    ) -> Any:
        """Helper method. Applies `func` to index and assigns the result to `column`.

        Parameters
        ----------
        func : Callable
            single-argument function to be applied to each S2 Token
        column_name : str
            name of the resulting column
        processor : Callable
            (Optional) further processes the result of func. Default: identity
        finalizer : Callable
            (Optional) further processes the resulting dataframe. Default: identity

        Returns
        -------
        Dataframe with column `column` containing the result of `func`.
        If using `finalizer`, can return anything the `finalizer` returns.
        """
        func = catch_invalid_maidenhead_id(func)
        result = [processor(func(maidenhead_id)) for maidenhead_id in self._df.index]
        assign_args = {column_name: result}
        return finalizer(self._df.assign(**assign_args))

    def _apply_index_explode(
        self,
        func: Callable,
        column_name: str,
        processor: Callable = lambda x: x,
        finalizer: Callable = lambda x: x,
    ) -> Any:
        """Helper method. Applies a list-making `func` to index and performs
        a vertical explode.
        Any additional values are simply copied to all the rows.

        Parameters
        ----------
        func : Callable
            single-argument function to be applied to each S2 Token
        column_name : str
            name of the resulting column
        processor : Callable
            (Optional) further processes the result of func. Default: identity
        finalizer : Callable
            (Optional) further processes the resulting dataframe. Default: identity

        Returns
        -------
        Dataframe with column `column` containing the result of `func`.
        If using `finalizer`, can return anything the `finalizer` returns.
        """
        func = catch_invalid_maidenhead_id(func)
        result = (
            pd.DataFrame.from_dict(
                {maidenhead_id: processor(func(maidenhead_id)) for maidenhead_id in self._df.index},
                orient="index",
            )
            .stack()
            .to_frame(column_name)
            .reset_index(level=1, drop=True)
        )
        result = self._df.join(result)
        return finalizer(result)

    @staticmethod
    def _format_resolution(resolution: int) -> str:
        return f"maidenhead_{str(resolution).zfill(2)}"
