from typing import Union, Callable, Sequence, Any
import warnings

from typing import Literal

import numpy as np
import shapely
import pandas as pd
import geopandas as gpd

from vgrid.conversion.latlon2dggs import latlon2gars
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame

from .util.functools import wrapped_partial
from .util.geometry import cell_to_boundary
from .util.decorator import catch_invalid_gars_id

AnyDataFrame = Union[DataFrame, GeoDataFrame]


@pd.api.extensions.register_dataframe_accessor("gars")
class GARSPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # gars API
    # These methods simply mirror the Vgrid gars API and apply gars functions to all rows

    def latlon2gars(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = True,
    ) -> AnyDataFrame:
        """Adds gars ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            gars resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with gars ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with gars IDs added     
        """

        if not isinstance(resolution, int) or resolution not in range(1, 5):
            raise ValueError("Resolution must be an integer in range [1, 4]")

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        gars_ids = [
            latlon2gars(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        colname = self._format_resolution(resolution)
        assign_arg = {colname: gars_ids}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(colname)
        return df

    def gars2geo(self) -> GeoDataFrame:
        """Add `geometry` with gars geometry to the DataFrame. Assumes gars ID.

        Returns
        -------
        GeoDataFrame with gars geometry

        Raises
        ------
        ValueError
            When an invalid gars ID is encountered      
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
        func = catch_invalid_gars_id(func)
        result = [processor(func(gars_id)) for gars_id in self._df.index]
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
        func = catch_invalid_gars_id(func)
        result = (
            pd.DataFrame.from_dict(
                {gars_id: processor(func(gars_id)) for gars_id in self._df.index},
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
        return f"gars_{str(resolution).zfill(2)}"
