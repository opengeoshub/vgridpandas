from typing import Union
from shapely.geometry import (
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
)
import pandas as pd
import geopandas as gpd

from vgrid.conversion.latlon2dggs import latlon2qtm as latlon_to_qtm
from vgrid.conversion.dggs2geo.qtm2geo import qtm2geo as qtm_to_geo
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin

from vgridpandas.utils.const import COLUMN_QTM_POLYFILL

AnyDataFrame = Union[DataFrame, GeoDataFrame]


from typing import Union, Set
from vgrid.dggs.qtm import constructGeometry, divideFacet
from vgrid.utils.io import validate_qtm_resolution
from vgrid.utils.geometry import check_predicate
from vgrid.conversion.dggscompact.qtmcompact import qtm_compact

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

p90_n180, p90_n90, p90_p0, p90_p90, p90_p180 = (
    (90.0, -180.0),
    (90.0, -90.0),
    (90.0, 0.0),
    (90.0, 90.0),
    (90.0, 180.0),
)
p0_n180, p0_n90, p0_p0, p0_p90, p0_p180 = (
    (0.0, -180.0),
    (0.0, -90.0),
    (0.0, 0.0),
    (0.0, 90.0),
    (0.0, 180.0),
)
n90_n180, n90_n90, n90_p0, n90_p90, n90_p180 = (
    (-90.0, -180.0),
    (-90.0, -90.0),
    (-90.0, 0.0),
    (-90.0, 90.0),
    (-90.0, 180.0),
)


initial_facets = [
    [p0_n180, p0_n90, p90_n90, p90_n180, p0_n180, True],
    [p0_n90, p0_p0, p90_p0, p90_n90, p0_n90, True],
    [p0_p0, p0_p90, p90_p90, p90_p0, p0_p0, True],
    [p0_p90, p0_p180, p90_p180, p90_p90, p0_p90, True],
    [n90_n180, n90_n90, p0_n90, p0_n180, n90_n180, False],
    [n90_n90, n90_p0, p0_p0, p0_n90, n90_n90, False],
    [n90_p0, n90_p90, p0_p90, p0_p0, n90_p0, False],
    [n90_p90, n90_p180, p0_p180, p0_p90, n90_p90, False],
]


def poly2qtm(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to QTM cells.

    Args:
        resolution (int): QTM resolution level [1..24]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of qtm ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2qtm(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_qtm_resolution(resolution)
    qtm_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        level_facets = {}
        QTMID = {}
        for lvl in range(resolution):
            level_facets[lvl] = []
            QTMID[lvl] = []
            if lvl == 0:
                for i, facet in enumerate(initial_facets):
                    QTMID[0].append(str(i + 1))
                    level_facets[0].append(facet)
                    facet_geom = constructGeometry(facet)
                    if Polygon(facet_geom).intersects(poly) and resolution == 1:
                        qtm_id = QTMID[0][i]
                        qtm_ids.append(qtm_id)
                        return qtm_ids
            else:
                for i, pf in enumerate(level_facets[lvl - 1]):
                    subdivided_facets = divideFacet(pf)
                    for j, subfacet in enumerate(subdivided_facets):
                        subfacet_geom = constructGeometry(subfacet)
                        if Polygon(subfacet_geom).intersects(poly):
                            new_id = QTMID[lvl - 1][i] + str(j)
                            QTMID[lvl].append(new_id)
                            level_facets[lvl].append(subfacet)
                            if lvl == resolution - 1:
                                if not check_predicate(
                                    Polygon(subfacet_geom), poly, predicate
                                ):
                                    continue
                                qtm_ids.append(new_id)
    if compact:
        return qtm_compact(qtm_ids)
    return qtm_ids


def polyfill_row(geometry, resolution, predicate=None, compact=False) -> list:
    """Return cell ids covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(poly2qtm(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            poly2qtm(geometry, resolution, predicate="intersect", compact=False)
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
    return list(tokens)


@pd.api.extensions.register_dataframe_accessor("qtm")
class QTMPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # QTM API
    # These methods simply mirror the Vgrid qtm API and apply QTM functions to all rows

    def latlon2qtm(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds qtm ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            QTM resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with QTM ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with QTM IDs added
        """

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        qtm_ids = [latlon_to_qtm(lat, lon, resolution) for lat, lon in zip(lats, lons)]

        # qtm_column = self._format_resolution(resolution)
        qtm_column = "qtm"
        assign_arg = {qtm_column: qtm_ids, "qtm_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(qtm_column)
        return df

    def qtm2geo(self, qtm_col: str = None) -> GeoDataFrame:
        """Add geometry with QTM geometry to the DataFrame."""
        if qtm_col is not None:
            if qtm_col not in self._df.columns:
                raise ValueError(f"Column '{qtm_col}' not found in DataFrame")
            ids = self._df[qtm_col]
        else:
            if "qtm" not in self._df.columns:
                raise ValueError("Column 'qtm' not found in DataFrame")
            ids = self._df["qtm"]
        return dggs_ids_to_geodataframe(self._df, ids, qtm_to_geo)

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
            QTM resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the QTM IDs
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(geom, resolution, predicate, compact)
        )

        if not explode:
            assign_args = {COLUMN_QTM_POLYFILL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(COLUMN_QTM_POLYFILL)
        return self._df.join(result)

    def qtmbin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> GeoDataFrame:
        """
        Bin points into qtm cells and compute statistics.
        """
        qtm_col = "qtm"
        df = self.latlon2qtm(resolution, lat_col, lon_col)
        result = aggregate_bin(df, qtm_col, stats, numeric_col, category_col)
        return result.qtm.qtm2geo(qtm_col=qtm_col)

    def _format_resolution(resolution: int) -> str:
        return f"qtm_{str(resolution).zfill(2)}"
