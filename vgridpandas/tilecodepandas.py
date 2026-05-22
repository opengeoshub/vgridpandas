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

from vgrid.conversion.latlon2dggs import latlon2tilecode as latlon_to_tilecode
from vgrid.conversion.dggs2geo.tilecode2geo import tilecode2geo as tilecode_to_geo
from vgridpandas.utils.const import TILECODE_COL

AnyDataFrame = Union[DataFrame, GeoDataFrame]


from typing import Union, Set
import re
from vgrid.dggs import mercantile
from vgrid.utils.geometry import check_predicate
from vgrid.conversion.dggscompact.tilecodecompact import tilecode_compact
from vgrid.utils.io import validate_tilecode_resolution

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]


def poly2tilecode(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to Tilecode grid cells.

    Args:
        resolution (int): Tilecode resolution level [1..10]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of tilecode ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2tilecode(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_tilecode_resolution(resolution)
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    tilecode_ids = []
    for poly in polys:
        tilecode_ids_poly = []
        min_lon, min_lat, max_lon, max_lat = poly.bounds
        tilecodes = mercantile.tiles(min_lon, min_lat, max_lon, max_lat, resolution)
        for tile in tilecodes:
            tilecode_id_poly = f"z{tile.z}x{tile.x}y{tile.y}"
            tilecode_ids_poly.append(tilecode_id_poly)
        for tilecode_id_poly in tilecode_ids_poly:
            match = re.match(r"z(\d+)x(\d+)y(\d+)", tilecode_id_poly)
            if not match:
                raise ValueError("Invalid tilecode format. Expected format: 'zXxYyZ'")
            z = int(match.group(1))
            x = int(match.group(2))
            y = int(match.group(3))
            bounds = mercantile.bounds(x, y, z)

            min_lat, min_lon = bounds.south, bounds.west
            max_lat, max_lon = bounds.north, bounds.east
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
                tilecode_ids.append(tilecode_id_poly)
    if compact:
        return tilecode_compact(tilecode_ids)
    return tilecode_ids


def polyfill_row(geometry, resolution, predicate=None, compact=False) -> list:
    """Return cell ids covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(poly2tilecode(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            poly2tilecode(geometry, resolution, predicate="intersect", compact=False)
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
    return list(tokens)


@pd.api.extensions.register_dataframe_accessor("tilecode")
class TilecodePandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # tilecode API
    # These methods simply mirror the Vgrid tilecode API and apply tilecode functions to all rows

    def latlon2tilecode(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds tilecode ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            tilecode resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with tilecode ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with tilecode IDs added
        """

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        tilecode_ids = [
            latlon_to_tilecode(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        tilecode_col = TILECODE_COL 
        assign_arg = {tilecode_col: tilecode_ids, f"{tilecode_col}_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(tilecode_col)
        return df

    def tilecode2geo(self, tilecode_col: str = None) -> GeoDataFrame:
        """Add geometry with TILECODE geometry to the DataFrame."""
        if tilecode_col is not None:
            if tilecode_col not in self._df.columns:
                raise ValueError(f"Column '{tilecode_col}' not found in DataFrame")
            ids = self._df[tilecode_col]
        else:
            if TILECODE_COL not in self._df.columns:
                raise ValueError(f"Column '{TILECODE_COL}' not found in DataFrame")
            ids = self._df[TILECODE_COL]
        return dggs_ids_to_geodataframe(self._df, ids, tilecode_to_geo)

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
            Tilecode resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the Tilecode IDs
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(geom, resolution, predicate, compact)
        )

        if not explode:
            assign_args = {TILECODE_COL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(TILECODE_COL)
        return self._df.join(result)

    def tilecodebin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> GeoDataFrame:
        """
        Bin points into tilecode cells and compute statistics.
        """
        tilecode_col = TILECODE_COL
        df = self.latlon2tilecode(resolution, lat_col, lon_col)
        result = aggregate_bin(df, tilecode_col, stats, numeric_col, category_col)
        return result.tilecode.tilecode2geo(tilecode_col=tilecode_col)
