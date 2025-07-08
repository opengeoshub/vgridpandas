from typing import Union, Callable, Any
from shapely.geometry import Polygon, MultiPolygon
from collections import Counter
import pandas as pd
import geopandas as gpd
from vgrid.conversion import latlon2dggs
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.functools import wrapped_partial
from vgridpandas.isea4tpandas.isea4tgeom import cell2boundary, validate_isea4t_resolution, polyfill
from vgridpandas.utils.decorator import catch_invalid_dggs_id, doc_standard
from vgridpandas.utils.const import COLUMN_ISEA4T_POLYFILL

AnyDataFrame = Union[DataFrame, GeoDataFrame]


@pd.api.extensions.register_dataframe_accessor("isea4t")
class ISEA4TPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # ISEA4T API
    # These methods simply mirror the Vgrid ISEA4T API and apply ISEA4T functions to all rows

    def latlon2isea4t(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = True,
    ) -> AnyDataFrame:
        """Adds ISEA4T ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            ISEA4T resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with ISEA4T ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with ISEA4T IDs added     
        """
        resolution = validate_isea4t_resolution(resolution)

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        isea4t_ids = [
            latlon2dggs.latlon2isea4t(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        colname = self._format_resolution(resolution)
        assign_arg = {colname: isea4t_ids}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(colname)
        return df


    def isea4t2geo(self, isea4t_column: str = None) -> GeoDataFrame:
        """Add geometry with isea4t geometry to the DataFrame. Assumes ISEA4T ID.

        Parameters
        ----------
        isea4t_column : str, optional
            Name of the column containing ISEA4T IDs. If None, assumes ISEA4T IDs are in the index.

        Returns
        -------
        GeoDataFrame with ISEA4T geometry

        Raises
        ------
        ValueError
            When an invalid ISEA4T ID is encountered
        """

        if isea4t_column is not None:
            # isea4t IDs are in the specified column
            if isea4t_column not in self._df.columns:
                raise ValueError(f"Column '{isea4t_column}' not found in DataFrame")
            isea4t_ids = self._df[isea4t_column]

            # Handle both single 4t_ids and lists of 4t_ids
            geometries = []
            for i4t_ids in isea4t_ids:
                try:
                    if pd.isna(i4t_ids):
                        # Handle NaN values - create empty geometry
                        geometries.append(Polygon())
                    elif isinstance(i4t_ids, list):
                        # Handle list of 4t_ids - create a MultiPolygon
                        if len(i4t_ids) == 0:
                            # Handle empty list - create empty geometry
                            geometries.append(Polygon())
                        else:
                            cell_geometries = [cell2boundary(i4t_id) for i4t_id in i4t_ids]
                            geometries.append(MultiPolygon(cell_geometries))
                    else:
                        # Handle single id
                        geometries.append(cell2boundary(i4t_ids))
                except (ValueError, TypeError):
                    if isinstance(i4t_ids, list):
                        if len(i4t_ids) == 0:
                            geometries.append(Polygon())
                        else:
                            cell_geometries = [cell2boundary(i4t_id) for i4t_id in i4t_ids]
                            geometries.append(MultiPolygon(cell_geometries))
                    else:
                        # Try to handle as single id
                        try:
                            geometries.append(cell2boundary(i4t_ids))
                        except Exception:
                            # If all else fails, create empty geometry
                            geometries.append(Polygon())

            result_df = self._df.copy()
            result_df['geometry'] = geometries
            return gpd.GeoDataFrame(result_df, crs="epsg:4326")

        else:
            # isea4t 4t_ids are in the index
            return self._apply_index_assign(
                wrapped_partial(cell2boundary),
                "geometry",
                finalizer=lambda x: gpd.GeoDataFrame(x, crs="epsg:4326"),
            )


    @doc_standard(
        COLUMN_ISEA4T_POLYFILL,
        "Returns a list of ISEA4T isea4t_ids representing the input geometry",
    )
    def polyfill(self, resolution: int, predicate: str = None, compact: bool = False, explode: bool = False) -> AnyDataFrame:
        """
        Parameters
        ----------
        resolution : int
            isea4t resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the isea4t IDs
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False       
        """

        def func(row):
            return list(polyfill(row.geometry, resolution, predicate, compact))

        result = self._df.apply(func, axis=1)

        if not explode:
            assign_args = {COLUMN_ISEA4T_POLYFILL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(COLUMN_ISEA4T_POLYFILL)

        return self._df.join(result)

    def isea4tbin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_column: str = None,
        category_column: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
        return_geometry: bool = True,
    ) -> DataFrame:
        """
        Bin points into isea4t cells and compute statistics, optionally grouped by a category column.

        Supports both GeoDataFrame (with point geometry) and DataFrame (with lat/lon columns).

        Parameters
        ----------
        resolution : int
            isea4t resolution
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
            If True, return a GeoDataFrame with isea4t cell geometry
        """
        # Validate inputs and prepare data
        colname = self._format_resolution(resolution)
        df = self.latlon2isea4t(resolution, lat_col, lon_col, False)

        # Validate column existence
        if category_column is not None and category_column not in df.columns:
            raise ValueError(f"Category column '{category_column}' not found in DataFrame")
        if numeric_column is not None and numeric_column not in df.columns:
            raise ValueError(f"Numeric column '{numeric_column}' not found in DataFrame")

        # Prepare grouping columns
        group_cols = [colname]
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
            result = df.groupby(group_cols)[numeric_column].agg(['min', 'max']).reset_index()
            result[stats] = result['max'] - result['min']
            result = result.drop(['min', 'max'], axis=1)
            
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
                all_categories = sorted([str(cat) for cat in df[category_column].unique()])
                result = df.groupby([colname, category_column]).apply(cat_agg_func, include_groups=False).reset_index(name=stats)
                result = result.pivot(index=colname, columns=category_column, values=stats)
                result = result.reindex(columns=all_categories, fill_value=0 if stats == "variety" else None)
                result = result.reset_index()
                result.columns = [colname] + [f"{cat}_{stats}" for cat in all_categories]
            else:
                # Handle categorical aggregation without category grouping
                result = df.groupby([colname]).apply(cat_agg_func, include_groups=False).reset_index(name=stats)
        else:
            raise ValueError(f"Unknown stats: {stats}")

        # Handle column renaming for non-categorical stats
        if len(result.columns) > len(group_cols) and not (category_column and stats in ["minority", "majority", "variety"]):
            result = result.rename(columns={result.columns[-1]: stats})

        # Handle category pivoting for non-categorical stats
        if category_column and stats not in ["minority", "majority", "variety"]:
            if len(result) == 0:
                result = pd.DataFrame(columns=[colname, category_column, stats])
            else:
                try:
                    # Pivot categories to columns
                    result = result.pivot(index=colname, columns=category_column, values=stats)
                    result = result.fillna(0)
                    result = result.reset_index()
                    
                    # Rename columns with category prefixes
                    new_columns = [colname]
                    for col in sorted(result.columns[1:]):
                        if col == "NaN_category":
                            new_columns.append(f"NaN_{stats}")
                        else:
                            new_columns.append(f"{col}_{stats}")
                    result.columns = new_columns
                except Exception:
                    # Fallback to simple count if pivot fails
                    result = df.groupby(colname).size().reset_index(name=stats)

        # Add geometry if requested
        result = result.set_index(colname)
        if return_geometry:
            result = result.isea4t.isea4t2geo()
        return result.reset_index()

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
        func = catch_invalid_dggs_id(func)
        result = [processor(func(isea4t_id)) for isea4t_id in self._df.index]
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
        func = catch_invalid_dggs_id(func)
        result = (
            pd.DataFrame.from_dict(
                {isea4t_id: processor(func(isea4t_id)) for isea4t_id in self._df.index},
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
        return f"ease_{str(resolution).zfill(2)}"
