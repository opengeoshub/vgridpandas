"""DGGALPandas module for DGGAL cell operations on pandas DataFrames and GeoDataFrames."""

from typing import Union, Iterator
from shapely.geometry import (
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
    Point,
    MultiPoint,
)
import pandas as pd
import geopandas as gpd
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe, linetrace_polyline
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgrid.conversion.latlon2dggs import latlon2dggal as latlon_to_dggal
from vgrid.conversion.dggs2geo.dggal2geo import dggal2geo as dggal_to_geo
from dggal import *
from vgrid.utils.geometry import check_predicate
from vgrid.utils.io import validate_dggal_resolution
from vgrid.conversion.dggscompact.dggalcompact import dggal_compact
from vgrid.utils.constants import DGGAL_TYPES
from vgrid.conversion.vector2dggs.vector2dggal import _dggal_segment_cells

AnyDataFrame = Union[DataFrame, GeoDataFrame]
MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]
MultiPointOrPoint = Union[Point, MultiPoint]


def poly2dggal(
    dggs_type,
    geometry,
    resolution,
    predicate=None,
    compact=False,
    split_antimeridian: bool = False,
):
    """Convert polygon geometries to DGGAL grid cells."""
    dggs_class_name = DGGAL_TYPES[dggs_type]["class_name"]
    dggrs = globals()[dggs_class_name]()

    resolution = validate_dggal_resolution(dggs_type, resolution)
    dggal_ids = []
    if isinstance(geometry, Polygon):
        polys = [geometry]
    elif isinstance(geometry, MultiPolygon):
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
            cell_polygon = dggal_to_geo(
                dggs_type, zone_id, split_antimeridian=split_antimeridian
            )
            if not check_predicate(cell_polygon, poly, predicate):
                continue
            dggal_ids.append(zone_id)
    if compact:
        dggal_ids = dggal_compact(dggs_type, dggal_ids)
    return dggal_ids


def linetrace(
    dggs_type: str,
    geometry: MultiLineOrLine,
    resolution: int,
    split_antimeridian: bool = False,
) -> Iterator[str]:
    """Trace a (Multi)LineString with DGGAL cells (same walk as ``polyline2dggal``)."""
    resolution = validate_dggal_resolution(dggs_type, resolution)
    dggs_class_name = DGGAL_TYPES[dggs_type]["class_name"]
    dggrs = globals()[dggs_class_name]()

    def segment_cells(start_xy, end_xy):
        return _dggal_segment_cells(
            dggs_type,
            dggrs,
            resolution,
            start_xy,
            end_xy,
            split_antimeridian=split_antimeridian,
        )

    yield from linetrace_polyline(geometry, segment_cells)


def polyfill_row(
    dggs_type,
    geometry,
    resolution,
    predicate=None,
    compact=False,
    split_antimeridian: bool = False,
) -> list:
    """Return cell ids covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(
            poly2dggal(
                dggs_type,
                geometry,
                resolution,
                predicate,
                compact,
                split_antimeridian,
            )
        )
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            linetrace(
                dggs_type,
                geometry,
                resolution,
                split_antimeridian=split_antimeridian,
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

        dggal_col = f"dggal_{dggs_type}"
        assign_arg = {dggal_col: dggal_ids, f"{dggal_col}_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(dggal_col)
        return df

    def dggal2geo(
        self,
        dggs_type: str,
        dggal_col: str = None,
        split_antimeridian: bool = False,
    ) -> GeoDataFrame:
        """Add geometry with DGGAL geometry to the DataFrame.

        Parameters
        ----------
        split_antimeridian : bool, optional
            Split antimeridian-crossing cells. Default: False
        """
        if dggal_col is None:
            dggal_col = f"dggal_{dggs_type}"
        if dggal_col not in self._df.columns:
            raise ValueError(f"Column '{dggal_col}' not found in DataFrame")

        def to_geo(token):
            return dggal_to_geo(
                dggs_type, token, split_antimeridian=split_antimeridian
            )

        return dggs_ids_to_geodataframe(self._df, self._df[dggal_col], to_geo)

    def polyfill(
        self,
        dggs_type: str,
        resolution: int,
        predicate: str = None,
        compact: bool = False,
        explode: bool = False,
        split_antimeridian: bool = False,
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
        split_antimeridian : bool, optional
            Split antimeridian-crossing cells when converting to geometry.
            Default: False
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(
                dggs_type,
                geom,
                resolution,
                predicate,
                compact,
                split_antimeridian,
            )
        )

        if not explode:
            return self._df.assign(**{f"dggal_{dggs_type}": result})

        result = result.explode().to_frame(f"dggal_{dggs_type}")
        return self._df.join(result)

    def linetrace(
        self,
        dggs_type: str,
        resolution: int,
        explode: bool = False,
        split_antimeridian: bool = False,
    ) -> AnyDataFrame:
        """DGGAL cell representation of a (Multi)LineString traced along its vertices.

        Uses the same neighbor walk as
        ``vgrid.conversion.vector2dggs.vector2dggal.polyline2dggal``.
        """
        result = self._df.apply(
            lambda row: list(
                linetrace(
                    dggs_type,
                    row.geometry,
                    resolution,
                    split_antimeridian=split_antimeridian,
                )
            ),
            axis=1,
        )
        col = f"dggal_{dggs_type}"
        if not explode:
            return self._df.assign(**{col: result})
        result = result.explode().to_frame(col)
        return self._df.join(result)

    def dggalbin(
        self,
        dggs_type: str,
        resolution: int,
        agg: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
        split_antimeridian: bool = False,
    ) -> GeoDataFrame:
        """Bin points into DGGAL cells and compute statistics."""
        dggal_col = f"dggal_{dggs_type}"
        df = self.latlon2dggal(dggs_type, resolution, lat_col, lon_col)
        result = aggregate_bin(df, dggal_col, agg, numeric_col, category_col)
        return result.dggal.dggal2geo(
            dggs_type,
            dggal_col=dggal_col,
            split_antimeridian=split_antimeridian,
        )
