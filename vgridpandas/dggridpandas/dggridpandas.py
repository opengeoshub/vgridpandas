"""S2Pandas module for S2 cell operations on pandas DataFrames and GeoDataFrames."""

from collections import Counter
from typing import Union, Any, Callable
from shapely.geometry import MultiPolygon, Polygon
import pandas as pd
import geopandas as gpd
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgrid.conversion.latlon2dggs import latlon2dggrid as latlon_to_dggrid
from vgridpandas.utils.decorator import catch_invalid_dggs_id
from vgridpandas.utils.functools import wrapped_partial
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

        dggrid_column = f"dggrid_{dggs_type.lower()}"
        assign_arg = {dggrid_column: dggrid_ids, f"{dggrid_column}_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(dggrid_column)
        return df

    def dggrid2geo(
        self,
        dggrid_instance,
        dggs_type: str,
        resolution: int = None,
        dggrid_column: str = None,
        address_type: str = "SEQNUM"
    ) -> GeoDataFrame:
        """Add geometry with DGGRID geometry to the DataFrame. Assumes DGGRID id.

        Parameters
        ----------
        dggrid_instance : DGGRIDv7
            DGGRID instance
        dggs_type : str
            DGGRID type
        resolution : int, optional
            DGGRID resolution
        dggrid_column : str, optional
            Name of the column containing DGGRID ids. If None, assumes DGGRID ids are in the index.
        address_type : str
            Address type, default 'SEQNUM'
        Returns
        -------
        GeoDataFrame with DGGRID geometry ids

        Raises
        ------
        ValueError
            When an invalid DGGRID id is encountered
        """
   
        # Handle backward compatibility: if resolution is passed as positional argument
        # and dggrid_column is None, then the third argument is resolution
        if resolution is None and dggrid_column is not None and isinstance(dggrid_column, int):
            # If dggrid_column is an integer, it's actually the resolution parameter
            resolution = dggrid_column
            dggrid_column = None

        if dggrid_column is not None:
            # DGGRID ids are in the specified column
            if dggrid_column not in self._df.columns:
                raise ValueError(f"Column '{dggrid_column}' not found in DataFrame")
            dggrid_ids = self._df[dggrid_column]

            # Handle both single dggrid_ids and lists of dggrid_ids
            geometries = self._dggrid_ids_to_geometries(
                dggrid_instance, dggs_type, dggrid_ids, resolution, address_type
            )

            result_df = self._df.copy()
            result_df["geometry"] = geometries
            return gpd.GeoDataFrame(result_df, crs="epsg:4326")

        else:
            if f"dggrid_{dggs_type.lower()}" in self._df.columns:
                # A5 hexes are in the 'a5' column
                dggrid_ids = self._df[f"dggrid_{dggs_type.lower()}"]

                # Handle both single hexes and lists of hexes
                geometries = self._dggrid_ids_to_geometries(
                    dggrid_instance, dggs_type, dggrid_ids, resolution, address_type,
                )

                result_df = self._df.copy()
                result_df["geometry"] = geometries
                return gpd.GeoDataFrame(result_df, crs="epsg:4326")
            else:
                # DGGRID ids are in the index
                def dggrid_id_to_geometry(dggrid_id):
                    return dggrid_to_geo(dggrid_instance, dggs_type, dggrid_id, resolution, address_type)
                
                return self._apply_index_assign(
                    dggrid_id_to_geometry,
                    "geometry",
                    finalizer=lambda x: gpd.GeoDataFrame(x, crs="epsg:4326"),
                )

    def dggridbin(
        self,
        dggrid_instance,
        dggs_type: str,
        resolution: int,
        stats: str = "count",
        numeric_column: str = None,
        category_column: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
        return_geometry: bool = True,
        address_type: str = "SEQNUM",
    ) -> DataFrame:
        """
        Bin points into DGGRID cells and compute statistics, optionally grouped by a category column.

        Supports both GeoDataFrame (with point geometry) and DataFrame (with lat/lon columns).

        Parameters
        ----------
        resolution : int
            DGGRID resolution
        stats : str
            Statistic to compute: count, sum, min, max, mean, median, std, var, range, minority, majority, variety
        numeric_column : str, optional
            Name of the numeric column to aggregate (for sum, min, max, etc.) or the value column for minority/majority/variety stats
        category_column : str, optional
            Name of the category column to group by. Required for minority, majority, and variety stats when grouping by category.
        lat_col : str, optional
            Name of the latitude column (only used for DataFrame input, ignored for GeoDataFrame)
        lon_col : str, optional
            Name of the longitude column (only used for DataFrame input, ignored for GeoDataFrame)
        return_geometry : bool
            If True, return a GeoDataFrame with DGGRID cell geometry
        """
        # Validate inputs and prepare data
        dggrid_column = f"dggrid_{dggs_type.lower()}"
        df = self.latlon2dggrid(
            dggrid_instance,
            dggs_type,
            resolution,
            lat_col,
            lon_col,
            False,
            address_type,
        )

        # Validate column existence
        if category_column is not None and category_column not in df.columns:
            raise ValueError(
                f"Category column '{category_column}' not found in DataFrame"
            )
        if numeric_column is not None and numeric_column not in df.columns:
            raise ValueError(
                f"Numeric column '{numeric_column}' not found in DataFrame"
            )

        # Prepare grouping columns
        group_cols = [dggrid_column]
        if category_column:
            df[category_column] = df[category_column].fillna("NaN_category")
            group_cols.append(category_column)

        # Perform aggregation based on stats type
        if stats == "count":
            result = df.groupby(group_cols).size().reset_index(name=stats)

        elif stats in ["sum", "min", "max", "mean", "median", "std", "var"]:
            if not numeric_column:
                raise ValueError(f"numeric_column must be provided for stats='{stats}'")
            result = df.groupby(group_cols)[numeric_column].agg(stats).reset_index()

        elif stats == "range":
            if not numeric_column:
                raise ValueError(f"numeric_column must be provided for stats='{stats}'")
            result = (
                df.groupby(group_cols)[numeric_column].agg(["min", "max"]).reset_index()
            )
            result[stats] = result["max"] - result["min"]
            result = result.drop(["min", "max"], axis=1)

        elif stats in ["minority", "majority", "variety"]:
            if not numeric_column:
                raise ValueError(f"numeric_column must be provided for stats='{stats}'")

            # Define categorical aggregation function
            def cat_agg_func(x):
                values = x[numeric_column].dropna()
                freq = Counter(values)
                if not freq:
                    return None
                if stats == "minority":
                    return min(freq.items(), key=lambda y: y[1])[0]
                elif stats == "majority":
                    return max(freq.items(), key=lambda y: y[1])[0]
                elif stats == "variety":
                    return values.nunique()

            if category_column:
                # Handle categorical aggregation with category grouping
                all_categories = sorted(
                    [str(cat) for cat in df[category_column].unique()]
                )
                result = (
                    df.groupby([dggrid_column, category_column])
                    .apply(cat_agg_func, include_groups=False)
                    .reset_index(name=stats)
                )
                result = result.pivot(
                    index=dggrid_column, columns=category_column, values=stats
                )
                result = result.reindex(
                    columns=all_categories, fill_value=0 if stats == "variety" else None
                )
                result = result.reset_index()
                result.columns = [dggrid_column] + [
                    f"{cat}_{stats}" for cat in all_categories
                ]
            else:
                # Handle categorical aggregation without category grouping
                result = (
                    df.groupby([dggrid_column])
                    .apply(cat_agg_func, include_groups=False)
                    .reset_index(name=stats)
                )
        else:
            raise ValueError(f"Unknown stats: {stats}")

        # Handle column renaming for non-categorical stats
        if len(result.columns) > len(group_cols) and not (
            category_column and stats in ["minority", "majority", "variety"]
        ):
            result = result.rename(columns={result.columns[-1]: stats})

        # Handle category pivoting for non-categorical stats
        if category_column and stats not in ["minority", "majority", "variety"]:
            if len(result) == 0:
                result = pd.DataFrame(columns=[dggrid_column, category_column, stats])
            else:
                try:
                    # Pivot categories to columns
                    result = result.pivot(
                        index=dggrid_column, columns=category_column, values=stats
                    )
                    # Fill NaN values but avoid geometry columns to prevent GeoPandas warning
                    numeric_cols = result.select_dtypes(include=["number"]).columns
                    result[numeric_cols] = result[numeric_cols].fillna(0)
                    result = result.reset_index()

                    # Rename columns with category prefixes
                    new_columns = [dggrid_column]
                    for col in sorted(result.columns[1:]):
                        if col == "NaN_category":
                            new_columns.append(f"NaN_{stats}")
                        else:
                            new_columns.append(f"{col}_{stats}")
                    result.columns = new_columns
                except Exception:
                    # Fallback to simple count if pivot fails
                    result = df.groupby(dggrid_column).size().reset_index(name=stats)

        # Add geometry if requested
        result = result.set_index(dggrid_column)
        if return_geometry:
            result = result.dggrid.dggrid2geo(dggrid_instance, dggs_type, resolution=resolution, dggrid_column=None, address_type=address_type)              
        return result.reset_index()

    def _dggrid_ids_to_geometries(
        self, dggrid_instance, dggs_type, dggrid_ids,resolution, address_type
    ) -> list:
        """Helper method to process dggrid IDs into geometries.

        Parameters
        ----------
        dggrid_instance : DGGRIDv7
            DGGRID instance
        dggrid_ids : pandas.Series or list
            DGGRID IDs to process
        dggs_type : str
            DGGRID type for geometry conversion
        resolution : int
            DGGRID resolution
        address_type : str
            Address type, default 'SEQNUM'

        Returns
        -------
        list
            List of geometries (Polygon or MultiPolygon objects)
        """
        geometries = []
        for ids in dggrid_ids:
            try:
                if pd.isna(ids):
                    # Handle NaN values - create empty geometry
                    geometries.append(Polygon())
                elif isinstance(ids, list):
                    # Handle list of dggrid_ids - create a MultiPolygon
                    if len(ids) == 0:
                        # Handle empty list - create empty geometry
                        geometries.append(Polygon())
                    else:
                        cell_geometries = []
                        for id in ids:
                            gdf = dggrid_to_geo(dggrid_instance, dggs_type, id, resolution, address_type)
                            # Extract geometry from GeoDataFrame
                            if len(gdf) > 0:
                                cell_geometries.append(gdf.geometry.iloc[0])
                            else:
                                cell_geometries.append(Polygon())
                        geometries.append(MultiPolygon(cell_geometries))
                else:
                    # Handle single dggrid_id
                    gdf = dggrid_to_geo(dggrid_instance, dggs_type, ids, resolution, address_type)
                    # Extract geometry from GeoDataFrame
                    if len(gdf) > 0:
                        geometries.append(gdf.geometry.iloc[0])
                    else:
                        geometries.append(Polygon())
            except (ValueError, TypeError):
                if isinstance(ids, list):
                    if len(ids) == 0:
                        geometries.append(Polygon())
                    else:
                        cell_geometries = []
                        for id in ids:
                            try:
                                gdf = dggrid_to_geo(dggrid_instance, dggs_type, id, resolution, address_type)
                                # Extract geometry from GeoDataFrame
                                if len(gdf) > 0:
                                    cell_geometries.append(gdf.geometry.iloc[0])
                                else:
                                    cell_geometries.append(Polygon())
                            except Exception:
                                cell_geometries.append(Polygon())
                        geometries.append(MultiPolygon(cell_geometries))
                else:
                    # Try to handle as single dggrid_id
                    try:
                        gdf = dggrid_to_geo(dggrid_instance, dggs_type, ids, resolution, address_type)
                        # Extract geometry from GeoDataFrame
                        if len(gdf) > 0:
                            geometries.append(gdf.geometry.iloc[0])
                        else:
                            geometries.append(Polygon())
                    except Exception:
                        # If all else fails, create empty geometry
                        geometries.append(Polygon())
        return geometries

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
            single-argument function to be applied to each DGGRID ID
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
        func = catch_invalid_dggs_id(func)
        result = [processor(func(dggrid_id)) for dggrid_id in self._df.index]
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
            single-argument function to be applied to each DGGRID ID
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
        func = catch_invalid_dggs_id(func)
        result = (
            pd.DataFrame.from_dict(
                {dggrid_id: processor(func(dggrid_id)) for dggrid_id in self._df.index},
                orient="index",
            )
            .stack()
            .to_frame(column_name)
            .reset_index(level=1, drop=True)
        )
        result = self._df.join(result)
        return finalizer(result)
