from typing import Union, Iterator
import pandas as pd
import geopandas as gpd
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from shapely.geometry import LineString, MultiLineString
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgridpandas.utils.const import GEOREF_COL
from vgrid.conversion.latlon2dggs import latlon2georef as latlon_to_georef
from vgrid.conversion.dggs2geo.georef2geo import georef2geo as georef_to_geo
from vgrid.conversion.vector2dggs.vector2georef import polyline2georef

AnyDataFrame = Union[DataFrame, GeoDataFrame]
MultiLineOrLine = Union[LineString, MultiLineString]


def linetrace(geometry: MultiLineOrLine, resolution: int) -> Iterator[str]:
    """Trace a (Multi)LineString with GEOREF cells (same walk as ``polyline2georef``)."""
    rows = polyline2georef(geometry, resolution, include_properties=False)
    for row in rows:
        yield row[GEOREF_COL]


@pd.api.extensions.register_dataframe_accessor("georef")
class GEOREFPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # georef API
    # These methods simply mirror the Vgrid georef API and apply georef functions to all rows

    def latlon2georef(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds georef ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            georef resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with georef ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with georef IDs added
        """
        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        georef_ids = [
            latlon_to_georef(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        # georef_col = self._format_resolution(resolution)
        georef_col = GEOREF_COL
        assign_arg = {georef_col: georef_ids, f"{georef_col}_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(georef_col)
        return df

    def georef2geo(self, georef_col: str = None) -> GeoDataFrame:
        """Add geometry with GEOREF geometry to the DataFrame."""
        if georef_col is not None:
            if georef_col not in self._df.columns:
                raise ValueError(f"Column '{georef_col}' not found in DataFrame")
            ids = self._df[georef_col]
        else:
            if GEOREF_COL not in self._df.columns:
                raise ValueError(f"Column '{GEOREF_COL}' not found in DataFrame")
            ids = self._df[GEOREF_COL]
        return dggs_ids_to_geodataframe(self._df, ids, georef_to_geo)

    def linetrace(self, resolution: int, explode: bool = False) -> AnyDataFrame:
        """GEOREF cell representation of a (Multi)LineString traced along its vertices.

        Uses the same walk as ``vgrid.conversion.vector2dggs.vector2georef.polyline2georef``.
        """
        result = self._df.apply(
            lambda row: list(linetrace(row.geometry, resolution)), axis=1
        )
        if not explode:
            return self._df.assign(**{GEOREF_COL: result})
        result = result.explode().to_frame(GEOREF_COL)
        return self._df.join(result)

    def georefbin(
        self,
        resolution: int,
        agg: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> GeoDataFrame:
        """
        Bin points into georef cells and compute statistics.
        """
        georef_col = GEOREF_COL
        df = self.latlon2georef(resolution, lat_col, lon_col)
        result = aggregate_bin(df, georef_col, agg, numeric_col, category_col)
        return result.georef.georef2geo(georef_col=georef_col)
