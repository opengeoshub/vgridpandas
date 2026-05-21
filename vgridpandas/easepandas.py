from typing import Union
from shapely.geometry import (
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
)
import pandas as pd
import geopandas as gpd
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgridpandas.utils.const import COLUMN_EASE_POLYFILL
from vgrid.conversion.latlon2dggs import latlon2ease as latlon_to_ease
from vgrid.conversion.dggs2geo.ease2geo import ease2geo as ease_to_geo


AnyDataFrame = Union[DataFrame, GeoDataFrame]


from typing import Union, Set
from shapely.geometry import box
from ease_dggs.constants import levels_specs, geo_crs, ease_crs
from ease_dggs.dggs.grid_addressing import (
    grid_ids_to_geos,
    geo_polygon_to_grid_ids,
)
from vgrid.conversion.dggscompact.easecompact import ease_compact
from vgrid.utils.geometry import check_predicate

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]


def validate_ease_resolution(resolution):
    """
    Validate that EASE resolution is in the valid range [0..6].

    Args:
        resolution: Resolution value to validate

    Returns:
        int: Validated resolution value

    Raises:
        ValueError: If resolution is not in range [0..6]
        TypeError: If resolution is not an integer
    """
    if not isinstance(resolution, int):
        raise TypeError(
            f"Resolution must be an integer, got {type(resolution).__name__}"
        )

    if resolution < 0 or resolution > 6:
        raise ValueError(f"Resolution must be in range [0..6], got {resolution}")

    return resolution


def poly2ease(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to ease grid cells.

    Args:
        resolution (int): EASE resolution level [0..6]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of ease ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2ease(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_ease_resolution(resolution)
    ease_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        poly_bbox = box(*poly.bounds)
        polygon_bbox_wkt = poly_bbox.wkt
        cells_bbox = geo_polygon_to_grid_ids(
            polygon_bbox_wkt,
            resolution,
            geo_crs,
            ease_crs,
            levels_specs,
            return_centroids=True,
            wkt_geom=True,
        )
        ease_cells = cells_bbox["result"]["data"]
        if compact:
            ease_cells = ease_compact(ease_cells)
        for ease_cell in ease_cells:
            cell_resolution = int(ease_cell[1])
            level_spec = levels_specs[cell_resolution]
            n_row = level_spec["n_row"]
            n_col = level_spec["n_col"]
            geo = grid_ids_to_geos([ease_cell])
            center_lon, center_lat = geo["result"]["data"][0]
            cell_min_lat = center_lat - (180 / (2 * n_row))
            cell_max_lat = center_lat + (180 / (2 * n_row))
            cell_min_lon = center_lon - (360 / (2 * n_col))
            cell_max_lon = center_lon + (360 / (2 * n_col))
            cell_polygon = Polygon(
                [
                    [cell_min_lon, cell_min_lat],
                    [cell_max_lon, cell_min_lat],
                    [cell_max_lon, cell_max_lat],
                    [cell_min_lon, cell_max_lat],
                    [cell_min_lon, cell_min_lat],
                ]
            )
            if check_predicate(cell_polygon, poly, predicate):
                ease_id = str(ease_cell)
                ease_ids.append(ease_id)
    return ease_ids


def polyfill_row(geometry, resolution, predicate=None, compact=False) -> list:
    """Return cell ids covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(poly2ease(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            poly2ease(geometry, resolution, predicate="intersect", compact=False)
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
    return list(tokens)


@pd.api.extensions.register_dataframe_accessor("ease")
class EASEPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # EASE API
    # These methods simply mirror the Vgrid EASE API and apply EASE functions to all rows

    def latlon2ease(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds EASE ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            EASE resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with EASE ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with EASE IDs added
        """

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        ease_ids = [
            latlon_to_ease(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        # ease_column = self._format_resolution(resolution)
        ease_column = "ease"
        assign_arg = {ease_column: ease_ids, "ease_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(ease_column)
        return df

    def ease2geo(self, ease_col: str = None) -> GeoDataFrame:
        """Add geometry with EASE geometry to the DataFrame."""
        if ease_col is not None:
            if ease_col not in self._df.columns:
                raise ValueError(f"Column '{ease_col}' not found in DataFrame")
            ids = self._df[ease_col]
        else:
            if "ease" not in self._df.columns:
                raise ValueError("Column 'ease' not found in DataFrame")
            ids = self._df["ease"]
        return dggs_ids_to_geodataframe(self._df, ids, ease_to_geo)

    def polyfill(
        self,
        resolution: int,
        predicate: str = None,
        compact: bool = False,
        explode: bool = False,
    ) -> AnyDataFrame:
        """
        Parameters
        ----------
        resolution : int
            EASE resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the EASE IDs
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(geom, resolution, predicate, compact)
        )

        if not explode:
            assign_args = {COLUMN_EASE_POLYFILL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(COLUMN_EASE_POLYFILL)
        return self._df.join(result)

    def easebin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> GeoDataFrame:
        """
        Bin points into ease cells and compute statistics.
        """
        ease_col = "ease"
        df = self.latlon2ease(resolution, lat_col, lon_col)
        result = aggregate_bin(df, ease_col, stats, numeric_col, category_col)
        return result.ease.ease2geo(ease_col=ease_col)

    def _format_resolution(resolution: int) -> str:
        return f"ease_{str(resolution).zfill(2)}"
