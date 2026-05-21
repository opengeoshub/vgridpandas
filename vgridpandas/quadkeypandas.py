from typing import Union
from shapely.geometry import (
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
)
import pandas as pd
import geopandas as gpd

from vgrid.conversion.latlon2dggs import latlon2quadkey as latlon_to_quadkey
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin

from vgrid.conversion.dggs2geo.quadkey2geo import quadkey2geo as quadkey_to_geo
from vgridpandas.utils.const import COLUMN_QUADKEY_POLYFILL

AnyDataFrame = Union[DataFrame, GeoDataFrame]


from typing import Union, Set
from vgrid.dggs import mercantile
from vgrid.utils.geometry import check_predicate
from vgrid.conversion.dggscompact.quadkeycompact import quadkey_compact
from vgrid.utils.io import validate_quadkey_resolution

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]


def poly2quadkey(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to Quadkey grid cells.

    Args:
        resolution (int): Quadkey resolution level [1..10]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of quadkey ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2quadkey(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_quadkey_resolution(resolution)
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    quadkey_ids = []
    for poly in polys:
        min_lon, min_lat, max_lon, max_lat = poly.bounds
        tiles = mercantile.tiles(min_lon, min_lat, max_lon, max_lat, resolution)
        for tile in tiles:
            z, x, y = tile.z, tile.x, tile.y
            bounds = mercantile.bounds(x, y, z)
            min_lat, min_lon = bounds.south, bounds.west
            max_lat, max_lon = bounds.north, bounds.east
            quadkey_id = mercantile.quadkey(tile)
            cell_polygon = Polygon(
                [
                    [min_lon, min_lat],
                    [max_lon, min_lat],
                    [max_lon, max_lat],
                    [min_lon, max_lat],
                    [min_lon, min_lat],
                ]
            )
            if check_predicate(cell_polygon, poly, predicate):
                quadkey_ids.append(quadkey_id)

    if compact:
        return quadkey_compact(quadkey_ids)
    return quadkey_ids


def polyfill_row(geometry, resolution, predicate=None, compact=False) -> list:
    """Return cell ids covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(poly2quadkey(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            poly2quadkey(geometry, resolution, predicate="intersect", compact=False)
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
    return list(tokens)


@pd.api.extensions.register_dataframe_accessor("quadkey")
class QuadkeyPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # quadkey API
    # These methods simply mirror the Vgrid quadkey API and apply quadkey functions to all rows

    def latlon2quadkey(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds quadkey ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            quadkey resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with quadkey ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with quadkey IDs added
        """

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        quadkey_ids = [
            latlon_to_quadkey(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        # tilecode_column = self._format_resolution(resolution)
        tilecode_column = "quadkey"
        assign_arg = {tilecode_column: quadkey_ids, "quadkey_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(tilecode_column)
        return df

    def quadkey2geo(self, quadkey_col: str = None) -> GeoDataFrame:
        """Add geometry with QUADKEY geometry to the DataFrame."""
        if quadkey_col is not None:
            if quadkey_col not in self._df.columns:
                raise ValueError(f"Column '{quadkey_col}' not found in DataFrame")
            ids = self._df[quadkey_col]
        else:
            if "quadkey" not in self._df.columns:
                raise ValueError("Column 'quadkey' not found in DataFrame")
            ids = self._df["quadkey"]
        return dggs_ids_to_geodataframe(self._df, ids, quadkey_to_geo)

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
            Quadkey resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the Quadkey IDs
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(geom, resolution, predicate, compact)
        )

        if not explode:
            assign_args = {COLUMN_QUADKEY_POLYFILL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(COLUMN_QUADKEY_POLYFILL)
        return self._df.join(result)

    def quadkeybin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> GeoDataFrame:
        """
        Bin points into quadkey cells and compute statistics.
        """
        quadkey_col = "quadkey"
        df = self.latlon2quadkey(resolution, lat_col, lon_col)
        result = aggregate_bin(df, quadkey_col, stats, numeric_col, category_col)
        return result.quadkey.quadkey2geo(quadkey_col=quadkey_col)

    def _format_resolution(resolution: int) -> str:
        return f"quadkey_{str(resolution).zfill(2)}"
