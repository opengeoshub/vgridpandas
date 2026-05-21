from typing import Union
from shapely.geometry import (
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
)
import pandas as pd
import geopandas as gpd
from vgrid.conversion.latlon2dggs import latlon2geohash as latlon_to_geohash
from vgrid.conversion.dggs2geo.geohash2geo import geohash2geo as geohash_to_geo
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgridpandas.utils.const import COLUMN_GEOHASH_POLYFILL


AnyDataFrame = Union[DataFrame, GeoDataFrame]


from typing import Union, Set
from vgrid.utils.io import validate_geohash_resolution
from vgrid.conversion.dggscompact.geohashcompact import geohash_compact
from vgrid.generator.geohashgrid import expand_geohash_bbox
from vgrid.utils.constants import INITIAL_GEOHASHES
from vgrid.utils.geometry import check_predicate


MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]


def poly2geohash(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to Geohash grid cells.

    Args:
        resolution (int): Geohash resolution level [1..10]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of geohash ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2geohash(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_geohash_resolution(resolution)
    geohash_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        intersected_geohashes = {
            gh for gh in INITIAL_GEOHASHES if geohash_to_geo(gh).intersects(poly)
        }
        geohashes_bbox = set()
        for gh in intersected_geohashes:
            expand_geohash_bbox(gh, resolution, geohashes_bbox, poly)
        for gh in geohashes_bbox:
            cell_polygon = geohash_to_geo(gh)
            if not check_predicate(cell_polygon, poly, predicate):
                continue
            geohash_ids.append(gh)
    if compact:
        return geohash_compact(geohash_ids)
    return geohash_ids


def polyfill_row(geometry, resolution, predicate=None, compact=False) -> list:
    """Return cell ids covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(poly2geohash(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            poly2geohash(geometry, resolution, predicate="intersect", compact=False)
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
    return list(tokens)


@pd.api.extensions.register_dataframe_accessor("geohash")
class GeohashPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # geohash API
    # These methods simply mirror the Vgrid geohash API and apply geohash functions to all rows

    def latlon2geohash(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds geohash ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            geohash resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with geohash ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with geohash IDs added
        """

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        geohash_ids = [
            latlon_to_geohash(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        # geohash_column = self._format_resolution(resolution)
        geohash_column = "geohash"
        assign_arg = {geohash_column: geohash_ids, "geohash_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(geohash_column)
        return df

    def geohash2geo(self, geohash_col: str = None) -> GeoDataFrame:
        """Add geometry with GEOHASH geometry to the DataFrame."""
        if geohash_col is not None:
            if geohash_col not in self._df.columns:
                raise ValueError(f"Column '{geohash_col}' not found in DataFrame")
            ids = self._df[geohash_col]
        else:
            if "geohash" not in self._df.columns:
                raise ValueError("Column 'geohash' not found in DataFrame")
            ids = self._df["geohash"]
        return dggs_ids_to_geodataframe(self._df, ids, geohash_to_geo)

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
            Geohash resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the Geohash IDs
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(geom, resolution, predicate, compact)
        )

        if not explode:
            assign_args = {COLUMN_GEOHASH_POLYFILL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(COLUMN_GEOHASH_POLYFILL)
        return self._df.join(result)

    def geohashbin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> GeoDataFrame:
        """
        Bin points into geohash cells and compute statistics.
        """
        geohash_col = "geohash"
        df = self.latlon2geohash(resolution, lat_col, lon_col)
        result = aggregate_bin(df, geohash_col, stats, numeric_col, category_col)
        return result.geohash.geohash2geo(geohash_col=geohash_col)

    def _format_resolution(resolution: int) -> str:
        return f"geohash_{str(resolution).zfill(2)}"
