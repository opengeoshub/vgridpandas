from typing import Union, Callable, Sequence, Any
import warnings

from typing import Literal

import numpy as np
from shapely.geometry import MultiPolygon, Polygon
import pandas as pd
import geopandas as gpd

from vgrid.conversion.latlon2dggs import latlon2s2
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame

from .util.const import COLUMN_S2_POLYFILL 
from .util.decorator import doc_standard
from .util.functools import wrapped_partial
from .util.geometry import cell_to_boundary, polyfill, validate_s2_resolution
from .util.decorator import catch_invalid_s2_token

AnyDataFrame = Union[DataFrame, GeoDataFrame]


@pd.api.extensions.register_dataframe_accessor("s2")
class S2Pandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # S2 API
    # These methods simply mirror the Vgrid S2 API and apply S2 functions to all rows

    def latlon2s2(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = True,
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
            If True, the columns with S2 token is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with S2 IDs added       

        """
        resolution = validate_s2_resolution(resolution)
        
        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        s2_tokens = [
            latlon2s2(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        colname = self._format_resolution(resolution)
        assign_arg = {colname: s2_tokens}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(colname)
        return df

    def s22geo(self, s2_column: str = None) -> GeoDataFrame:
        """Add geometry with S2 geometry to the DataFrame. Assumes S2 token.

        Parameters
        ----------
        s2_column : str, optional
            Name of the column containing S2 tokens. If None, assumes S2 tokens are in the index.

        Returns
        -------
        GeoDataFrame with S2 geometry

        Raises
        ------
        ValueError
            When an invalid S2 token is encountered

      
        """
        if s2_column is not None:
            # S2 tokens are in the specified column
            if s2_column not in self._df.columns:
                raise ValueError(f"Column '{s2_column}' not found in DataFrame")
            s2_tokens = self._df[s2_column]
            
            # Handle both single tokens and lists of tokens
            geometries = []
            for tokens in s2_tokens:
                try:
                    if pd.isna(tokens):
                        # Handle NaN values - create empty geometry
                        geometries.append(Polygon())
                    elif isinstance(tokens, list):
                        # Handle list of tokens - create a MultiPolygon
                        if len(tokens) == 0:
                            # Handle empty list - create empty geometry
                            geometries.append(Polygon())
                        else:
                            cell_geometries = [cell_to_boundary(token) for token in tokens]
                            geometries.append(MultiPolygon(cell_geometries))
                    else:
                        # Handle single token
                        geometries.append(cell_to_boundary(tokens))
                except (ValueError, TypeError):
                    # Handle cases where pd.isna() fails (e.g., with numpy arrays)
                    if isinstance(tokens, list):
                        if len(tokens) == 0:
                            geometries.append(Polygon())
                        else:
                            cell_geometries = [cell_to_boundary(token) for token in tokens]
                            geometries.append(MultiPolygon(cell_geometries))
                    else:
                        # Try to handle as single token
                        try:
                            geometries.append(cell_to_boundary(tokens))
                        except:
                            # If all else fails, create empty geometry
                            geometries.append(Polygon())
            
            result_df = self._df.copy()
            result_df['geometry'] = geometries
            return gpd.GeoDataFrame(result_df, crs="epsg:4326")
        
        else:
            # S2 tokens are in the index
            return self._apply_index_assign(
                wrapped_partial(cell_to_boundary),
                "geometry",
                finalizer=lambda x: gpd.GeoDataFrame(x, crs="epsg:4326"),
            )

    @doc_standard(
        COLUMN_S2_POLYFILL,
        "containing a list S2 ID whose centroid falls into the Polygon",
    )
    def polyfill(self, resolution: int, predicate: str = None, compact: bool = False, explode: bool = False) -> AnyDataFrame:
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
        """

        def func(row):
            return list(polyfill(row.geometry, resolution, predicate, compact))

        result = self._df.apply(func, axis=1)

        if not explode:
            assign_args = {COLUMN_S2_POLYFILL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(COLUMN_S2_POLYFILL)

        return self._df.join(result)


    # # Private methods
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
        func = catch_invalid_s2_token(func)
        result = [processor(func(s2token)) for s2token in self._df.index]
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
        func = catch_invalid_s2_token(func)
        result = (
            pd.DataFrame.from_dict(
                {h3address: processor(func(h3address)) for h3address in self._df.index},
                orient="index",
            )
            .stack()
            .to_frame(column_name)
            .reset_index(level=1, drop=True)
        )
        result = self._df.join(result)
        return finalizer(result)

    # # TODO: types, doc, ..
    # def _multiply_numeric(self, value):
    #     columns_numeric = self._df.select_dtypes(include=["number"]).columns
    #     assign_args = {
    #         column: self._df[column].multiply(value) for column in columns_numeric
    #     }
    #     return self._df.assign(**assign_args)

    @staticmethod
    def _format_resolution(resolution: int) -> str:
        return f"s2_{str(resolution).zfill(2)}"
