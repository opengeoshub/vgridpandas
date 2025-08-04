from typing import Union, Callable, Sequence, Any, Counter
import warnings

from typing import Literal

import numpy as np
import shapely
import pandas as pd
import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon

import h3
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame

from vgridpandas.utils.decorator import catch_invalid_dggs_id, doc_standard
from vgridpandas.utils.functools import wrapped_partial
from vgridpandas.h3pandas.h3geom import cell_to_boundary_lng_lat, polyfill, linetrace, _switch_lat_lng
from vgridpandas.utils.const import COLUMN_H3_POLYFILL, COLUMN_H3_LINETRACE

AnyDataFrame = Union[DataFrame, GeoDataFrame]


@pd.api.extensions.register_dataframe_accessor("h3")
class H3Pandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # H3 API
    # These methods simply mirror the H3 API and apply H3 functions to all rows

    def latlon2h3(
        self,
        resolution: int,
        lat_col: str = "lat",
        lng_col: str = "lon",
        set_index: bool = True,
    ) -> AnyDataFrame:
        """Adds H3 index to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lng_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            H3 resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lng_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with H3 ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with H3 ID added

        See Also
        --------
        geo_to_h3_aggregate : Extended API method that aggregates points by H3 id

        Examples
        --------
        >>> df = pd.DataFrame({'lat': [50, 51], 'lng':[14, 15]})
        >>> df.h3.geo_to_h3(8)
                         lat  lng
        h3
        881e309739fffff   50   14
        881e2659c3fffff   51   15

        >>> df.h3.geo_to_h3(8, set_index=False)
           lat  lng            h3
        0   50   14  881e309739fffff
        1   51   15  881e2659c3fffff

        >>> gdf = gpd.GeoDataFrame({'val': [5, 1]},
        >>> geometry=gpd.points_from_xy(x=[14, 15], y=(50, 51)))
        >>> gdf.h3.geo_to_h3(8)
                         val                   geometry
        h3
        881e309739fffff    5  POINT (14.00000 50.00000)
        881e2659c3fffff    1  POINT (15.00000 51.00000)

        """
        if not isinstance(resolution, int) or resolution not in range(0, 16):
            raise ValueError("Resolution must be an integer in range [0, 15]")

        if isinstance(self._df, gpd.GeoDataFrame):
            lngs = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lngs = self._df[lng_col]
            lats = self._df[lat_col]

        h3_id = [
            h3.latlng_to_cell(lat, lng, resolution) for lat, lng in zip(lats, lngs)
        ]

        # h3_column = self._format_resolution(resolution)
        h3_column = "h3"
        assign_arg = {h3_column: h3_id, "h3_res": resolution}   
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(h3_column)
        return df

    def h32latlon(self) -> GeoDataFrame:
        """Add `geometry` with centroid of each H3 id to the DataFrame.
        Assumes H3 index.

        Returns
        -------
        GeoDataFrame with Point geometry

        Raises
        ------
        ValueError
            When an invalid H3 id is encountered

        See Also
        --------
        h3_to_geo_boundary : Adds a hexagonal cell

        Examples
        --------
        >>> df = pd.DataFrame({'val': [5, 1]},
        >>>                   index=['881e309739fffff', '881e2659c3fffff'])
        >>> df.h3.h3_to_geo()
                         val                   geometry
        881e309739fffff    5  POINT (14.00037 50.00055)
        881e2659c3fffff    1  POINT (14.99715 51.00252)

        """
        return self._apply_index_assign(
            h3.cell_to_latlng,
            "geometry",
            lambda x: _switch_lat_lng(shapely.geometry.Point(x)),
            lambda x: gpd.GeoDataFrame(x, crs="epsg:4326"),
        )

    def h32geo(self, h3_column: str = None) -> GeoDataFrame:
        """Add geometry with H3 geometry to the DataFrame. Assumes H3 token.

        Parameters
        ----------
        h3_column : str, optional
            Name of the column containing H3 tokens. If None, assumes H3 tokens are in the index.

        Returns
        -------
        GeoDataFrame with H3 geometry

        Raises
        ------
        ValueError
            When an invalid H3 token is encountered

        Examples
        --------
        >>> df = pd.DataFrame({'val': [5, 1]},
        >>>                   index=['881e309739fffff', '881e2659c3fffff'])
        >>> df.h3.h32geo()
                         val                                           geometry
        881e309739fffff    5  POLYGON ((13.99527 50.00368, 13.99310 49.99929...
        881e2659c3fffff    1  POLYGON ((14.99201 51.00565, 14.98973 51.00133...
        """

        if h3_column is not None:
            # H3 tokens are in the specified column
            if h3_column not in self._df.columns:
                raise ValueError(f"Column '{h3_column}' not found in DataFrame")
            h3_tokens = self._df[h3_column]

            # Handle both single tokens and lists of tokens
            geometries = []
            for tokens in h3_tokens:
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
                            cell_geometries = [cell_to_boundary_lng_lat(token) for token in tokens]
                            geometries.append(MultiPolygon(cell_geometries))
                    else:
                        # Handle single token
                        geometries.append(cell_to_boundary_lng_lat(tokens))
                except (ValueError, TypeError):
                    if isinstance(tokens, list):
                        if len(tokens) == 0:
                            geometries.append(Polygon())
                        else:
                            cell_geometries = [cell_to_boundary_lng_lat(token) for token in tokens]
                            geometries.append(MultiPolygon(cell_geometries))
                    else:
                        # Try to handle as single token
                        try:
                            geometries.append(cell_to_boundary_lng_lat(tokens))
                        except Exception:
                            # If all else fails, create empty geometry
                            geometries.append(Polygon())

            result_df = self._df.copy()
            result_df['geometry'] = geometries
            return gpd.GeoDataFrame(result_df, crs="epsg:4326")

        else:
            # H3 tokens are in the index
            return self._apply_index_assign(
                wrapped_partial(cell_to_boundary_lng_lat),
                "geometry",
                finalizer=lambda x: gpd.GeoDataFrame(x, crs="epsg:4326"),
            )

    def h3bin(
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
        Bin points into H3 cells and compute statistics, optionally grouped by a category column.

        Supports both GeoDataFrame (with point geometry) and DataFrame (with lat/lon columns).

        Parameters
        ----------
        resolution : int
            H3 resolution
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
            If True, return a GeoDataFrame with H3 cell geometry
        """
        # Validate inputs and prepare data
        # h3_column = self._format_resolution(resolution)
        h3_column = "h3"
        df = self.latlon2h3(resolution, lat_col, lon_col, False)

        # Validate column existence
        if category_column is not None and category_column not in df.columns:
            raise ValueError(f"Category column '{category_column}' not found in DataFrame")
        if numeric_column is not None and numeric_column not in df.columns:
            raise ValueError(f"Numeric column '{numeric_column}' not found in DataFrame")

        # Prepare grouping columns
        group_cols = [h3_column]
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
                result = df.groupby([h3_column, category_column]).apply(cat_agg_func, include_groups=False).reset_index(name=stats)
                result = result.pivot(index=h3_column, columns=category_column, values=stats)
                result = result.reindex(columns=all_categories, fill_value=0 if stats == "variety" else None)
                result = result.reset_index()
                result.columns = [h3_column] + [f"{cat}_{stats}" for cat in all_categories]
            else:
                # Handle categorical aggregation without category grouping
                result = df.groupby([h3_column]).apply(cat_agg_func, include_groups=False).reset_index(name=stats)
        else:
            raise ValueError(f"Unknown stats: {stats}")

        # Handle column renaming for non-categorical stats
        if len(result.columns) > len(group_cols) and not (category_column and stats in ["minority", "majority", "variety"]):
            result = result.rename(columns={result.columns[-1]: stats})

        # Handle category pivoting for non-categorical stats
        if category_column and stats not in ["minority", "majority", "variety"]:
            if len(result) == 0:
                result = pd.DataFrame(columns=[h3_column, category_column, stats])
            else:
                try:
                    # Pivot categories to columns
                    result = result.pivot(index=h3_column, columns=category_column, values=stats)
                    result = result.fillna(0)
                    result = result.reset_index()
                    
                    # Rename columns with category prefixes
                    new_columns = [h3_column]
                    for col in sorted(result.columns[1:]):
                        if col == "NaN_category":
                            new_columns.append(f"NaN_{stats}")
                        else:
                            new_columns.append(f"{col}_{stats}")
                    result.columns = new_columns
                except Exception:
                    # Fallback to simple count if pivot fails
                    result = df.groupby(h3_column).size().reset_index(name=stats)

        # Add geometry if requested
        result = result.set_index(h3_column)
        if return_geometry:
            result = result.h3.h32geo()
        return result.reset_index()

    @doc_standard("h3_resolution", "containing the resolution of each H3 id")
    def h3_get_resolution(self) -> AnyDataFrame:
        """
        Examples
        --------
        >>> df = pd.DataFrame({'val': [5, 1]},
        >>>                   index=['881e309739fffff', '881e2659c3fffff'])
        >>> df.h3.h3_get_resolution()
                         val  h3_resolution
        881e309739fffff    5              8
        881e2659c3fffff    1              8
        """
        return self._apply_index_assign(h3.get_resolution, "h3_resolution")

    @doc_standard("h3_base_cell", "containing the base cell of each H3 id")
    def h3_get_base_cell(self):
        """
        Examples
        --------
        >>> df = pd.DataFrame({'val': [5, 1]},
        >>>                   index=['881e309739fffff', '881e2659c3fffff'])
        >>> df.h3.h3_get_base_cell()
                         val  h3_base_cell
        881e309739fffff    5            15
        881e2659c3fffff    1            15
        """
        return self._apply_index_assign(h3.get_base_cell_number, "h3_base_cell")

    @doc_standard("h3_is_valid", "containing the validity of each H3 id")
    def h3_is_valid(self):
        """
        Examples
        --------
        >>> df = pd.DataFrame({'val': [5, 1]}, index=['881e309739fffff', 'INVALID'])
        >>> df.h3.h3_is_valid()
                         val  h3_is_valid
        881e309739fffff    5         True
        INVALID            1        False
        """
        return self._apply_index_assign(h3.is_valid_cell, "h3_is_valid")

    @doc_standard(
        "h3_k_ring", "containing a list H3 ID within a distance of `k`"
    )
    def k_ring(self, k: int = 1, explode: bool = False) -> AnyDataFrame:
        """
        Parameters
        ----------
        k : int
            the distance from the origin H3 id. Default k = 1
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False

        See Also
        --------
        k_ring_smoothing : Extended API method that distributes numeric values
            to the k-ring cells

        Examples
        --------
        >>> df = pd.DataFrame({'val': [5, 1]},
        >>>                   index=['881e309739fffff', '881e2659c3fffff'])
        >>> df.h3.k_ring(1)
                         val                                          h3_k_ring
        881e309739fffff    5  [881e30973dfffff, 881e309703fffff, 881e309707f...
        881e2659c3fffff    1  [881e2659ddfffff, 881e2659c3fffff, 881e2659cbf...

        >>> df.h3.k_ring(1, explode=True)
                         val        h3_k_ring
        881e2659c3fffff    1  881e2659ddfffff
        881e2659c3fffff    1  881e2659c3fffff
        881e2659c3fffff    1  881e2659cbfffff
        881e2659c3fffff    1  881e2659d5fffff
        881e2659c3fffff    1  881e2659c7fffff
        881e2659c3fffff    1  881e265989fffff
        881e2659c3fffff    1  881e2659c1fffff
        881e309739fffff    5  881e30973dfffff
        881e309739fffff    5  881e309703fffff
        881e309739fffff    5  881e309707fffff
        881e309739fffff    5  881e30973bfffff
        881e309739fffff    5  881e309715fffff
        881e309739fffff    5  881e309739fffff
        881e309739fffff    5  881e309731fffff
        """
        func = wrapped_partial(h3.grid_disk, k=k)
        column_name = "h3_k_ring"
        if explode:
            return self._apply_index_explode(func, column_name, list)
        return self._apply_index_assign(func, column_name, list)

    @doc_standard(
        "h3_hex_ring",
        "containing a list H3 ID forming a hollow hexagonal ring"
        "at a distance `k`",
    )
    def hex_ring(self, k: int = 1, explode: bool = False) -> AnyDataFrame:
        """
        Parameters
        ----------
        k : int
            the distance from the origin H3 id. Default k = 1
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False

        Examples
        --------
        >>> df = pd.DataFrame({'val': [5, 1]},
        >>>                   index=['881e309739fffff', '881e2659c3fffff'])
        >>> df.h3.hex_ring(1)
                         val                                        h3_hex_ring
        881e309739fffff    5  [881e30973dfffff, 881e309703fffff, 881e309707f...
        881e2659c3fffff    1  [881e2659ddfffff, 881e2659cbfffff, 881e2659d5f...
        >>> df.h3.hex_ring(1, explode=True)
                         val      h3_hex_ring
        881e2659c3fffff    1  881e2659ddfffff
        881e2659c3fffff    1  881e2659cbfffff
        881e2659c3fffff    1  881e2659d5fffff
        881e2659c3fffff    1  881e2659c7fffff
        881e2659c3fffff    1  881e265989fffff
        881e2659c3fffff    1  881e2659c1fffff
        881e309739fffff    5  881e30973dfffff
        881e309739fffff    5  881e309703fffff
        881e309739fffff    5  881e309707fffff
        881e309739fffff    5  881e30973bfffff
        881e309739fffff    5  881e309715fffff
        881e309739fffff    5  881e309731fffff
        """
        func = wrapped_partial(h3.grid_ring, k=k)
        column_name = "h3_hex_ring"
        if explode:
            return self._apply_index_explode(func, column_name, list)
        return self._apply_index_assign(func, column_name, list)

    @doc_standard("h3_{resolution}", "containing the parent of each H3 id")
    def h32parent(self, resolution: int = None) -> AnyDataFrame:
        """
        Parameters
        ----------
        resolution : int or None
            H3 resolution. If None, then returns the direct parent of each H3 cell.

        See Also
        --------
        h3_to_parent_aggregate : Extended API method that aggregates cells by their
            parent cell

        Examples
        --------
        >>> df = pd.DataFrame({'val': [5, 1]},
        >>>                   index=['881e309739fffff', '881e2659c3fffff'])
        >>> df.h3.h3_to_parent(5)
                         val            h3_05
        881e309739fffff    5  851e3097fffffff
        881e2659c3fffff    1  851e265bfffffff
        """
        # TODO: Test `h3_parent` case
        column = (
            self._format_resolution(resolution)
            if resolution is not None
            else "h3_parent"
        )
        return self._apply_index_assign(
            wrapped_partial(h3.cell_to_parent, res=resolution), column
        )

    @doc_standard("h3_center_child", "containing the center child of each H3 id")
    def h3_to_center_child(self, resolution: int = None) -> AnyDataFrame:
        """
        Parameters
        ----------
        resolution : int or None
            H3 resolution. If none, then returns the child of resolution
            directly below that of each H3 cell

        Examples
        --------
        >>> df = pd.DataFrame({'val': [5, 1]},
        >>>                    index=['881e309739fffff', '881e2659c3fffff'])
        >>> df.h3.h3_to_center_child()
                         val  h3_center_child
        881e309739fffff    5  891e3097383ffff
        881e2659c3fffff    1  891e2659c23ffff
        """
        return self._apply_index_assign(
            wrapped_partial(h3.cell_to_center_child, res=resolution), "h3_center_child"
        )

    @doc_standard(
        "h3",
        "containing a list H3 ID whose centroid falls into the Polygon",
    )
    def polyfill(
        self, 
        resolution: int, 
        explode: bool = False,
        predicate: str = None,
        compact: bool = False
    ) -> AnyDataFrame:
        """
        Parameters
        ----------
        resolution : int
            H3 resolution
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Enable H3 compact mode      
        """

        def func(row):
            return list(polyfill(row.geometry, resolution, predicate, compact))

        result = self._df.apply(func, axis=1)

        if not explode:
            assign_args = {"h3": result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame("h3")

        return self._df.join(result)

    @doc_standard("h3_cell_area", "containing the area of each H3 id")
    def cell_area(
        self, unit: Literal["km^2", "m^2", "rads^2"] = "km^2"
    ) -> AnyDataFrame:
        """
        Parameters
        ----------
        unit : str, options: 'km^2', 'm^2', or 'rads^2'
            Unit for area result. Default: 'km^2`

        Examples
        --------
        >>> df = pd.DataFrame({'val': [5, 1]},
        >>>                   index=['881e309739fffff', '881e2659c3fffff'])
        >>> df.h3.cell_area()
                         val  h3_cell_area
        881e309739fffff    5      0.695651
        881e2659c3fffff    1      0.684242
        """
        return self._apply_index_assign(
            wrapped_partial(h3.cell_area, unit=unit), "h3_cell_area"
        )

    # H3-Pandas Extended API
    # These methods extend the API to provide a convenient way to simplify workflows

    def geo2h3_aggregate(
        self,
        resolution: int,
        operation: Union[dict, str, Callable] = "count",
        lat_col: str = "lat",
        lon_col: str = "lon",
        return_geometry: bool = True,
    ) -> DataFrame:
        """Adds H3 index to DataFrame, groups points with the same index
        and performs `operation`.

        pd.DataFrame: uses `lat_col` and `lng_col` (default `lat` and `lng`)
        gpd.GeoDataFrame: uses `geometry`

        Parameters
        ----------
        resolution : int
            H3 resolution
        operation : Union[dict, str, Callable]
            Argument passed to DataFrame's `agg` method, default 'sum'
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        return_geometry: bool
            (Optional) Whether to add a `geometry` column with the hexagonal cells.
            Default = True

        Returns
        -------
        (Geo)DataFrame aggregated by H3 id into which each row's point falls

        See Also
        --------
        geo_to_h3 : H3 API method upon which this function builds

        Examples
        --------
        >>> df = pd.DataFrame({'lat': [50, 51], 'lng':[14, 15], 'val': [10, 1]})
        >>> df.h3.geo_to_h3(1)
                         lat  lng  val
        h3_01
        811e3ffffffffff   50   14   10
        811e3ffffffffff   51   15    1
        >>> df.h3.geo_to_h3_aggregate(1)
                         val                                           geometry
        h3_01
        811e3ffffffffff   11  POLYGON ((12.34575 50.55428, 12.67732 46.40696...
        >>> df = pd.DataFrame({'lat': [50, 51], 'lng':[14, 15], 'val': [10, 1]})
        >>> df.h3.geo_to_h3_aggregate(1, operation='mean')
                         val                                           geometry
        h3_01
        811e3ffffffffff  5.5  POLYGON ((12.34575 50.55428, 12.67732 46.40696...
        >>> df.h3.geo_to_h3_aggregate(1, return_geometry=False)
                         val
        h3_01
        811e3ffffffffff   11
        """
        grouped = pd.DataFrame(
            self.latlon2h3(resolution, lat_col, lon_col, False)
            .drop(columns=[lat_col, lon_col, "geometry"], errors="ignore")
            # .groupby(self._format_resolution(resolution))
            .groupby("h3")
            .agg(operation)
        )
        return grouped.h3.h32geo() if return_geometry else grouped

    def h32parent_aggregate(
        self,
        resolution: int,
        operation: Union[dict, str, Callable] = "sum",
        return_geometry: bool = True,
    ) -> GeoDataFrame:
        """Assigns parent cell to each row, groups by it and performs `operation`.
        Assumes H3 index.

        Parameters
        ----------
        resolution : int
            H3 resolution
        operation : Union[dict, str, Callable]
            Argument passed to DataFrame's `agg` method, default 'sum'
        return_geometry: bool
            (Optional) Whether to add a `geometry` column with the hexagonal cells.
            Default = True

        Returns
        -------
        (Geo)DataFrame aggregated by the parent of each H3 id

        Raises
        ------
        ValueError
            When an invalid H3 id is encountered

        See Also
        --------
        h3_to_parent : H3 API method upon which this function builds

        Examples
        --------
        >>> df = pd.DataFrame({'val': [5, 1]},
        >>>                   index=['881e309739fffff', '881e2659c3fffff'])
        >>> df.h3.h3_to_parent(1)
                         val            h3_01
        881e309739fffff    5  811e3ffffffffff
        881e2659c3fffff    1  811e3ffffffffff
        >>> df.h3.h3_to_parent_aggregate(1)
                         val                                           geometry
        h3_01
        811e3ffffffffff    6  POLYGON ((12.34575 50.55428, 12.67732 46.40696...
        >>> df.h3.h3_to_parent_aggregate(1, operation='mean')
                         val                                           geometry
        h3_01
        811e3ffffffffff    3  POLYGON ((12.34575 50.55428, 12.67732 46.40696...
        >>> df.h3.h3_to_parent_aggregate(1, return_geometry=False)
                         val
        h3_01
        811e3ffffffffff    6
        """
        parent_h3ID = [
            catch_invalid_dggs_id(h3.cell_to_parent)(h3id, resolution)
            for h3id in self._df.index
        ]
        # h3_parent_column = self._format_resolution(resolution)
        h3_parent_column = "h3"
        kwargs_assign = {h3_parent_column: parent_h3ID}
        grouped = (
            self._df.assign(**kwargs_assign)
            .groupby(h3_parent_column)[[c for c in self._df.columns if c != "geometry"]]
            .agg(operation)
        )

        return grouped.h3.h32geo() if return_geometry else grouped

    # TODO: Needs to allow for handling relative values (e.g. percentage)
    # TODO: Will possibly fail in many cases (what are the existing columns?)
    # TODO: New cell behaviour
    def k_ring_smoothing(
        self,
        k: int = None,
        weights: Sequence[float] = None,
        return_geometry: bool = True,
    ) -> AnyDataFrame:
        """Experimental. Creates a k-ring around each input cell and distributes
        the cell's values.

        The values are distributed either
         - uniformly (by setting `k`) or
         - by weighing their values using `weights`.

        Only numeric columns are modified.

        Parameters
        ----------
        k : int
            The distance from the origin H3 id
        weights : Sequence[float]
            Weighting of the values based on the distance from the origin.
            First weight corresponds to the origin.
            Values are be normalized to add up to 1.
        return_geometry: bool
            (Optional) Whether to add a `geometry` column with the hexagonal cells.
            Default = True

        Returns
        -------
        (Geo)DataFrame with smoothed values

        See Also
        --------
        k_ring : H3 API method upon which this method builds

        Examples
        --------
        >>> df = pd.DataFrame({'val': [5, 1]},
        >>>                   index=['881e309739fffff', '881e2659c3fffff'])
        >>> df.h3.k_ring_smoothing(1)
                              val                                           geometry
        h3_k_ring
        881e265989fffff  0.142857  POLYGON ((14.99488 50.99821, 14.99260 50.99389...
        881e2659c1fffff  0.142857  POLYGON ((14.97944 51.00758, 14.97717 51.00326...
        881e2659c3fffff  0.142857  POLYGON ((14.99201 51.00565, 14.98973 51.00133...
        881e2659c7fffff  0.142857  POLYGON ((14.98231 51.00014, 14.98004 50.99582...
        881e2659cbfffff  0.142857  POLYGON ((14.98914 51.01308, 14.98687 51.00877...
        881e2659d5fffff  0.142857  POLYGON ((15.00458 51.00371, 15.00230 50.99940...
        881e2659ddfffff  0.142857  POLYGON ((15.00171 51.01115, 14.99943 51.00684...
        881e309703fffff  0.714286  POLYGON ((13.99235 50.01119, 13.99017 50.00681...
        881e309707fffff  0.714286  POLYGON ((13.98290 50.00555, 13.98072 50.00116...
        881e309715fffff  0.714286  POLYGON ((14.00473 50.00932, 14.00255 50.00494...
        881e309731fffff  0.714286  POLYGON ((13.99819 49.99617, 13.99602 49.99178...
        881e309739fffff  0.714286  POLYGON ((13.99527 50.00368, 13.99310 49.99929...
        881e30973bfffff  0.714286  POLYGON ((14.00765 50.00181, 14.00547 49.99742...
        881e30973dfffff  0.714286  POLYGON ((13.98582 49.99803, 13.98364 49.99365...
        >>> df.h3.k_ring_smoothing(weights=[2, 1])
                           val                                           geometry
        h3_hex_ring
        881e265989fffff  0.125  POLYGON ((14.99488 50.99821, 14.99260 50.99389...
        881e2659c1fffff  0.125  POLYGON ((14.97944 51.00758, 14.97717 51.00326...
        881e2659c3fffff  0.250  POLYGON ((14.99201 51.00565, 14.98973 51.00133...
        881e2659c7fffff  0.125  POLYGON ((14.98231 51.00014, 14.98004 50.99582...
        881e2659cbfffff  0.125  POLYGON ((14.98914 51.01308, 14.98687 51.00877...
        881e2659d5fffff  0.125  POLYGON ((15.00458 51.00371, 15.00230 50.99940...
        881e2659ddfffff  0.125  POLYGON ((15.00171 51.01115, 14.99943 51.00684...
        881e309703fffff  0.625  POLYGON ((13.99235 50.01119, 13.99017 50.00681...
        881e309707fffff  0.625  POLYGON ((13.98290 50.00555, 13.98072 50.00116...
        881e309715fffff  0.625  POLYGON ((14.00473 50.00932, 14.00255 50.00494...
        881e309731fffff  0.625  POLYGON ((13.99819 49.99617, 13.99602 49.99178...
        881e309739fffff  1.250  POLYGON ((13.99527 50.00368, 13.99310 49.99929...
        881e30973bfffff  0.625  POLYGON ((14.00765 50.00181, 14.00547 49.99742...
        881e30973dfffff  0.625  POLYGON ((13.98582 49.99803, 13.98364 49.99365...
        >>> df.h3.k_ring_smoothing(1, return_geometry=False)
                              val
        h3_k_ring
        881e265989fffff  0.142857
        881e2659c1fffff  0.142857
        881e2659c3fffff  0.142857
        881e2659c7fffff  0.142857
        881e2659cbfffff  0.142857
        881e2659d5fffff  0.142857
        881e2659ddfffff  0.142857
        881e309703fffff  0.714286
        881e309707fffff  0.714286
        881e309715fffff  0.714286
        881e309731fffff  0.714286
        881e309739fffff  0.714286
        881e30973bfffff  0.714286
        881e30973dfffff  0.714286
        """
        # Drop geometry if present
        df = self._df.drop(columns=["geometry"], errors="ignore")

        if sum([weights is None, k is None]) != 1:
            raise ValueError("Exactly one of `k` and `weights` must be set.")

        # If weights are all equal, use the computationally simpler option
        if (weights is not None) and (len(set(weights)) == 1):
            k = len(weights) - 1
            weights = None

        # Unweighted case
        if weights is None:
            result = pd.DataFrame(
                df.h3.k_ring(k, explode=True)
                .groupby("h3_k_ring")
                .sum()
                .divide((1 + 3 * k * (k + 1)))
            )

            return result.h3.h3_to_geo_boundary() if return_geometry else result

        if len(weights) == 0:
            raise ValueError("Weights cannot be empty.")

        # Weighted case
        weights = np.array(weights)
        multipliers = np.array([1] + [i * 6 for i in range(1, len(weights))])
        weights = weights / (weights * multipliers).sum()

        # This should be exploded hex ring
        def weighted_hex_ring(df, k, normalized_weight):
            return df.h3.hex_ring(k, explode=True).h3._multiply_numeric(
                normalized_weight
            )

        result = (
            pd.concat(
                [weighted_hex_ring(df, i, weights[i]) for i in range(len(weights))]
            )
            .groupby("h3_hex_ring")
            .sum()
        )

        return result.h3.h3_to_geo_boundary() if return_geometry else result

    def polyfill_resample(
        self, resolution: int, return_geometry: bool = True
    ) -> AnyDataFrame:
        """Experimental. Currently essentially polyfill(..., explode=True) that
        sets the H3 index and adds the H3 cell geometry.

        Parameters
        ----------
        resolution : int
            H3 resolution
        return_geometry: bool
            (Optional) Whether to add a `geometry` column with the hexagonal cells.
            Default = True

        Returns
        -------
        (Geo)DataFrame with H3 cells with centroids within the input polygons.

        See Also
        --------
        polyfill : H3 API method upon which this method builds

        Examples
        --------
        >>> from shapely.geometry import box
        >>> gdf = gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)])
        >>> gdf.h3.polyfill_resample(4)
                         index                                           geometry
        h3
        84754e3ffffffff      0  POLYGON ((0.33404 -0.11975, 0.42911 0.07901, 0...
        84754c7ffffffff      0  POLYGON ((0.92140 -0.03115, 1.01693 0.16862, 0...
        84754c5ffffffff      0  POLYGON ((0.91569 0.33807, 1.01106 0.53747, 0....
        84754ebffffffff      0  POLYGON ((0.62438 0.10878, 0.71960 0.30787, 0....
        84754edffffffff      0  POLYGON ((0.32478 0.61394, 0.41951 0.81195, 0....
        84754e1ffffffff      0  POLYGON ((0.32940 0.24775, 0.42430 0.44615, 0....
        84754e9ffffffff      0  POLYGON ((0.61922 0.47649, 0.71427 0.67520, 0....
        8475413ffffffff      0  POLYGON ((0.91001 0.70597, 1.00521 0.90497, 0....
        """
        result = self._df.h3.polyfill(resolution, explode=True)
        uncovered_rows = result[COLUMN_H3_POLYFILL].isna()
        n_uncovered_rows = uncovered_rows.sum()
        if n_uncovered_rows > 0:
            warnings.warn(
                f"{n_uncovered_rows} rows did not generate a H3 cell."
                "Consider using a finer resolution."
            )
            result = result.loc[~uncovered_rows]

        result = result.reset_index().set_index(COLUMN_H3_POLYFILL)

        return result.h3.h3_to_geo_boundary() if return_geometry else result

    def linetrace(self, resolution: int, explode: bool = False) -> AnyDataFrame:
        """Experimental. An H3 cell representation of a (Multi)LineString,
        which permits repeated cells, but not if they are repeated in
        immediate sequence.

        Parameters
        ----------
        resolution : int
            H3 resolution
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False

        Returns
        -------
        (Geo)DataFrame with H3 cells with centroids within the input polygons.

        Examples
        --------
        >>> from shapely.geometry import LineString
        >>> gdf = gpd.GeoDataFrame(geometry=[LineString([[0, 0], [1, 0], [1, 1]])])
        >>> gdf.h3.linetrace(4)
                                                    geometry                                       h3_linetrace
        0  LINESTRING (0.00000 0.00000, 1.00000 0.00000, ...  [83754efffffffff, 83754cfffffffff, 837541fffff...  # noqa E501
        >>> gdf.h3.linetrace(4, explode=True)
                                                    geometry     h3_linetrace
        0  LINESTRING (0.00000 0.00000, 1.00000 0.00000, ...  83754efffffffff
        0  LINESTRING (0.00000 0.00000, 1.00000 0.00000, ...  83754cfffffffff
        0  LINESTRING (0.00000 0.00000, 1.00000 0.00000, ...  837541fffffffff

        """

        def func(row):
            return list(linetrace(row.geometry, resolution))

        df = self._df

        result = df.apply(func, axis=1)
        if not explode:
            assign_args = {COLUMN_H3_LINETRACE: result}
            return df.assign(**assign_args)

        result = result.explode().to_frame(COLUMN_H3_LINETRACE)
        return df.join(result)


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
            single-argument function to be applied to each H3 id
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
        result = [processor(func(h3id)) for h3id in self._df.index]
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
            single-argument function to be applied to each H3 id
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
                {h3id: processor(func(h3id)) for h3id in self._df.index},
                orient="index",
            )
            .stack()
            .to_frame(column_name)
            .reset_index(level=1, drop=True)
        )
        result = self._df.join(result)
        return finalizer(result)

    # TODO: types, doc, ..
    def _multiply_numeric(self, value):
        columns_numeric = self._df.select_dtypes(include=["number"]).columns
        assign_args = {
            column: self._df[column].multiply(value) for column in columns_numeric
        }
        return self._df.assign(**assign_args)

    @staticmethod
    def _format_resolution(resolution: int) -> str:
        return f"h3_{str(resolution).zfill(2)}"
