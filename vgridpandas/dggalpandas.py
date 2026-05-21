"""S2Pandas module for S2 cell operations on pandas DataFrames and GeoDataFrames."""

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
from vgrid.conversion.latlon2dggs import latlon2dggal as latlon_to_dggal
from vgrid.conversion.dggs2geo.dggal2geo import dggal2geo as dggal_to_geo

AnyDataFrame = Union[DataFrame, GeoDataFrame]


from typing import Union
from shapely.geometry import (
    Point,
    MultiPoint,
)
from dggal import *
from vgrid.utils.geometry import check_predicate
from vgrid.conversion.dggs2geo.dggal2geo import dggal2geo
from vgrid.utils.io import validate_dggal_resolution
from vgrid.conversion.dggscompact.dggalcompact import dggal_compact
from vgrid.utils.constants import DGGAL_TYPES

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]
MultiPointOrPoint = Union[Point, MultiPoint]


def poly2dggal(dggs_type, geometry, resolution, predicate=None, compact=False):
    """
    Convert polygon geometries (Polygon, MultiPolygon) to DGGAL grid cells.

    Args:
        dggs_type: str
            DGGAL type
        resolution (int): DGGAL resolution level [0..28]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of DGGAL tokens intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2dggal(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    dggs_class_name = DGGAL_TYPES[dggs_type]["class_name"]
    dggrs = globals()[dggs_class_name]()

    resolution = validate_dggal_resolution(dggs_type, resolution)
    dggal_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        min_lon, min_lat, max_lon, max_lat = poly.bounds
        ll = GeoPoint(min_lat, min_lon)
        ur = GeoPoint(max_lat, max_lon)
        geo_extent = GeoExtent(ll, ur)
        zones = dggrs.listZones(resolution, geo_extent)
        for zone in zones:
            zone_id = dggrs.getZoneTextID(zone)
            cell_polygon = dggal2geo(dggs_type, zone_id)
            if not check_predicate(cell_polygon, poly, predicate):
                continue
            dggal_ids.append(zone_id)
    if compact:
        dggal_ids = dggal_compact(dggs_type, dggal_ids)
    return dggal_ids


def polyfill_row(
    dggs_type, geometry, resolution, predicate=None, compact=False
) -> list:
    """Return cell ids covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(poly2dggal(dggs_type, geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            poly2dggal(
                dggs_type, geometry, resolution, predicate="intersect", compact=False
            )
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
    return list(tokens)


@pd.api.extensions.register_dataframe_accessor("dggal")
class DGGALPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    def latlon2dggal(
        self,
        dggs_type: str,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds DGGAL id to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        dggs_type : str
            DGGAL type
        resolution : int
            DGGAL resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with DGGAL id is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with DGGAL ids added

        """

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        dggal_ids = [
            latlon_to_dggal(dggs_type, lat, lon, resolution)
            for lat, lon in zip(lats, lons)
        ]

        dggal_column = f"dggal_{dggs_type}"
        assign_arg = {dggal_column: dggal_ids, f"{dggal_column}_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(dggal_column)
        return df

    def dggal2geo(self, dggs_type: str, dggal_col: str = None) -> GeoDataFrame:
        """Add geometry with DGGAL geometry to the DataFrame."""
        if dggal_col is None:
            dggal_col = f"dggal_{dggs_type}"
        if dggal_col not in self._df.columns:
            raise ValueError(f"Column '{dggal_col}' not found in DataFrame")

        def to_geo(token):
            return dggal_to_geo(dggs_type, token)

        return dggs_ids_to_geodataframe(self._df, self._df[dggal_col], to_geo)

    def polyfill(
        self,
        dggs_type: str,
        resolution: int,
        predicate: str = None,
        compact: bool = False,
        explode: bool = False,
    ) -> AnyDataFrame:
        """
        Parameters
        ----------
        resolution : int
            DGGAL resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the DGGAL ids
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(dggs_type, geom, resolution, predicate, compact)
        )

        if not explode:
            return self._df.assign(**{f"dggal_{dggs_type}": result})

        result = result.explode().to_frame(f"dggal_{dggs_type}")
        return self._df.join(result)

    def dggalbin(
        self,
        dggs_type: str,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> GeoDataFrame:
        """Bin points into DGGAL cells and compute statistics."""
        dggal_col = f"dggal_{dggs_type}"
        df = self.latlon2dggal(dggs_type, resolution, lat_col, lon_col)
        result = aggregate_bin(df, dggal_col, stats, numeric_col, category_col)
        return result.dggal.dggal2geo(dggs_type, dggal_col=dggal_col)
