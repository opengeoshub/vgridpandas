from typing import Union, Iterator
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, MultiLineString
from vgrid.conversion.latlon2dggs import latlon2gars as latlon_to_gars
from vgrid.conversion.dggs2geo.gars2geo import gars2geo as gars_to_geo
from vgrid.conversion.vector2dggs.vector2gars import polyline2gars
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgridpandas.utils.const import GARS_COL

AnyDataFrame = Union[DataFrame, GeoDataFrame]
MultiLineOrLine = Union[LineString, MultiLineString]


def linetrace(geometry: MultiLineOrLine, resolution: int) -> Iterator[str]:
    """Trace a (Multi)LineString with GARS cells (same walk as ``polyline2gars``)."""
    rows = polyline2gars(geometry, resolution, include_properties=False)
    for row in rows:
        yield row[GARS_COL]


@pd.api.extensions.register_dataframe_accessor("gars")
class GARSPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # gars API
    # These methods simply mirror the Vgrid gars API and apply gars functions to all rows

    def latlon2gars(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds gars ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            gars resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with gars ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with gars IDs added
        """

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        gars_ids = [
            latlon_to_gars(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        gars_col = GARS_COL
        assign_arg = {gars_col: gars_ids, f"{gars_col}_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(gars_col)
        return df

    def gars2geo(self, gars_col: str = None) -> GeoDataFrame:
        """Add geometry with GARS geometry to the DataFrame."""
        if gars_col is not None:
            if gars_col not in self._df.columns:
                raise ValueError(f"Column '{gars_col}' not found in DataFrame")
            ids = self._df[gars_col]
        else:
            if GARS_COL not in self._df.columns:
                raise ValueError(f"Column '{GARS_COL}' not found in DataFrame")
            ids = self._df[GARS_COL]
        return dggs_ids_to_geodataframe(self._df, ids, gars_to_geo)

    def linetrace(self, resolution: int, explode: bool = False) -> AnyDataFrame:
        """GARS cell representation of a (Multi)LineString traced along its vertices.

        Uses the same walk as ``vgrid.conversion.vector2dggs.vector2gars.polyline2gars``.
        """
        result = self._df.apply(
            lambda row: list(linetrace(row.geometry, resolution)), axis=1
        )
        if not explode:
            return self._df.assign(**{GARS_COL: result})
        result = result.explode().to_frame(GARS_COL)
        return self._df.join(result)

    def garsbin(
        self,
        resolution: int,
        agg: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> GeoDataFrame:
        """
        Bin points into gars cells and compute statistics.
        """
        gars_col = GARS_COL
        df = self.latlon2gars(resolution, lat_col, lon_col)
        result = aggregate_bin(df, gars_col, agg, numeric_col, category_col)
        return result.gars.gars2geo(gars_col=gars_col)
