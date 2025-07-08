from typing import Union, Callable, Any
from collections import Counter
import pandas as pd
import geopandas as gpd
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from shapely.geometry import Polygon, MultiPolygon
from vgrid.conversion import latlon2dggs
from vgridpandas.utils.decorator import catch_invalid_dggs_id, doc_standard
from vgridpandas.utils.functools import wrapped_partial
from vgridpandas.rhealpixpandas.rhealpixgeom import cell2boundary, polyfill, validate_rhealpix_resolution
from vgridpandas.utils.const import COLUMN_RHEALPIX_POLYFILL

AnyDataFrame = Union[DataFrame, GeoDataFrame]


@pd.api.extensions.register_dataframe_accessor("rhealpix")
class rHEALPixPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # rHEALPix API
    # These methods simply mirror the Vgrid RHEALPIX API and apply RHEALPIX functions to all rows

    def latlon2rhealpix(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = True,
    ) -> AnyDataFrame:
        """Adds RHEALPIX ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            rHEALPix resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with rHEALPix ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with rHEALPix rhp_ids added     
        """

        resolution = validate_rhealpix_resolution(resolution)

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        rhealpix_ids = [
            latlon2dggs.latlon2rhealpix(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        colname = self._format_resolution(resolution)
        assign_arg = {colname: rhealpix_ids}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(colname)
        return df

    def rhealpix2geo(self, rhealpix_column: str = None) -> GeoDataFrame:
        """Add geometry with rHEALPix geometry to the DataFrame. Assumes rHEALPix ID.

        Parameters
        ----------
        rhealpix_column : str, optional
            Name of the column containing rHEALPix rhp_ids. If None, assumes rHEALPix rhp_ids are in the index.

        Returns
        -------
        GeoDataFrame with rHEALPix geometry

        Raises
        ------
        ValueError
            When an invalid rHEALPix ID is encountered
        """

        if rhealpix_column is not None:
            # rHEALPix rhp_ids are in the specified column
            if rhealpix_column not in self._df.columns:
                raise ValueError(f"Column '{rhealpix_column}' not found in DataFrame")
            rhealpix_ids = self._df[rhealpix_column]

            # Handle both single rhp_ids and lists of rhp_ids
            geometries = []
            for rhp_ids in rhealpix_ids:
                try:
                    if pd.isna(rhp_ids):
                        # Handle NaN values - create empty geometry
                        geometries.append(Polygon())
                    elif isinstance(rhp_ids, list):
                        # Handle list of rhp_ids - create a MultiPolygon
                        if len(rhp_ids) == 0:
                            # Handle empty list - create empty geometry
                            geometries.append(Polygon())
                        else:
                            cell_geometries = [cell2boundary(rhp_id) for rhp_id in rhp_ids]
                            geometries.append(MultiPolygon(cell_geometries))
                    else:
                        # Handle single id
                        geometries.append(cell2boundary(rhp_ids))
                except (ValueError, TypeError):
                    if isinstance(rhp_ids, list):
                        if len(rhp_ids) == 0:
                            geometries.append(Polygon())
                        else:
                            cell_geometries = [cell2boundary(rhp_id) for rhp_id in rhp_ids]
                            geometries.append(MultiPolygon(cell_geometries))
                    else:
                        # Try to handle as single id
                        try:
                            geometries.append(cell2boundary(rhp_ids))
                        except Exception:
                            # If all else fails, create empty geometry
                            geometries.append(Polygon())

            result_df = self._df.copy()
            result_df['geometry'] = geometries
            return gpd.GeoDataFrame(result_df, crs="epsg:4326")

        else:
            # rHEALPix rhp_ids are in the index
            return self._apply_index_assign(
                wrapped_partial(cell2boundary),
                "geometry",
                finalizer=lambda x: gpd.GeoDataFrame(x, crs="epsg:4326"),
            )

    @doc_standard(
        COLUMN_RHEALPIX_POLYFILL,
        "Returns a list of rHEALPix rhp_ids representing the input geometry",
    )
    def polyfill(self, resolution: int, predicate: str = None, compact: bool = False, explode: bool = False) -> AnyDataFrame:
        """
        Parameters
        ----------
        resolution : int
            rHEALPix resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the rHEALPix IDs
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False       
        """

        def func(row):
            return list(polyfill(row.geometry, resolution, predicate, compact))

        result = self._df.apply(func, axis=1)

        if not explode:
            assign_args = {COLUMN_RHEALPIX_POLYFILL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(COLUMN_RHEALPIX_POLYFILL)

        return self._df.join(result)

    def rhealpixbin(
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
        Bin points into rHEALPix cells and compute statistics, optionally grouped by a category column.

        Supports both GeoDataFrame (with point geometry) and DataFrame (with lat/lon columns).

        Parameters
        ----------
        resolution : int
            rHEALPix resolution
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
            If True, return a GeoDataFrame with rHEALPix cell geometry
        """
        # Validate inputs and prepare data
        colname = self._format_resolution(resolution)
        df = self.latlon2rhealpix(resolution, lat_col, lon_col, False)

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
            result = result.rhealpix.rhealpix2geo()
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
            single-argument function to be applied to each rHEALPix ID
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
        result = [processor(func(rhealpix_id)) for rhealpix_id in self._df.index]
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
            single-argument function to be applied to each rHEALPix ID
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
                {rhealpix_id: processor(func(rhealpix_id)) for rhealpix_id in self._df.index},
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
        return f"rhealpix_{str(resolution).zfill(2)}"
