from typing import Union, List

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

from vgrid.conversion.latlon2dggs import latlon2qtm as latlon_to_qtm
from vgrid.conversion.dggs2geo.qtm2geo import qtm2geo as qtm_to_geo
from vgrid.conversion.dggscompact.qtmcompact import qtm_compact
from vgrid.dggs.qtm import constructGeometry, divideFacet
from vgrid.utils.io import validate_qtm_resolution
from vgrid.utils.geometry import check_predicate

from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgridpandas.utils.const import QTM_COL

AnyDataFrame = Union[DataFrame, GeoDataFrame]

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

# Initial octahedral facets (same definitions as vgrid.conversion.vector2dggs.vector2qtm)
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

INITIAL_FACETS = [
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
    geometry: Union[MultiPolyOrPoly, MultiLineOrLine],
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> List[str]:
    """
    Convert polygon or line geometries to QTM cells.

    Mirrors ``polygon2qtm`` / ``polyline2qtm`` in vgrid: walk the facet tree at the
    target resolution, then optionally compact the id set (same as ``vector2qtm``).
    """
    resolution = validate_qtm_resolution(resolution)
    qtm_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    is_line = isinstance(geometry, (LineString, MultiLineString))
    for poly in polys:
        level_facets = {}
        qtm_id_by_level = {}
        for lvl in range(resolution):
            level_facets[lvl] = []
            qtm_id_by_level[lvl] = []
            if lvl == 0:
                for i, facet in enumerate(INITIAL_FACETS):
                    qtm_id_by_level[0].append(str(i + 1))
                    level_facets[0].append(facet)
                    facet_geom = constructGeometry(facet)
                    if Polygon(facet_geom).intersects(poly) and resolution == 1:
                        qtm_ids.append(qtm_id_by_level[0][i])
                        break
                if resolution == 1:
                    continue
            else:
                for i, parent_facet in enumerate(level_facets[lvl - 1]):
                    for j, subfacet in enumerate(divideFacet(parent_facet)):
                        subfacet_geom = constructGeometry(subfacet)
                        if not Polygon(subfacet_geom).intersects(poly):
                            continue
                        new_id = qtm_id_by_level[lvl - 1][i] + str(j)
                        qtm_id_by_level[lvl].append(new_id)
                        level_facets[lvl].append(subfacet)
                        if lvl == resolution - 1:
                            if is_line or check_predicate(
                                Polygon(subfacet_geom), poly, predicate
                            ):
                                qtm_ids.append(new_id)

    if compact and qtm_ids:
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
        """
        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        qtm_ids = [latlon_to_qtm(lat, lon, resolution) for lat, lon in zip(lats, lons)]

        qtm_col = QTM_COL
        assign_arg = {qtm_col: qtm_ids, f"{qtm_col}_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(qtm_col)
        return df

    def qtm2geo(self, qtm_col: str = None) -> GeoDataFrame:
        """Add geometry with QTM geometry to the DataFrame."""
        if qtm_col is not None:
            if qtm_col not in self._df.columns:
                raise ValueError(f"Column '{qtm_col}' not found in DataFrame")
            ids = self._df[qtm_col]
        else:
            if QTM_COL not in self._df.columns:
                raise ValueError(f"Column '{QTM_COL}' not found in DataFrame")
            ids = self._df[QTM_COL]
        return dggs_ids_to_geodataframe(self._df, ids, qtm_to_geo)

    def polyfill(
        self,
        resolution: int,
        predicate: str = None,
        compact: bool = False,
        explode: bool = False,
    ) -> AnyDataFrame:
        """
        Fill geometries with QTM cell ids at the target resolution.

        When ``compact=True``, ids may span multiple resolutions after compaction
        (same as ``vector2qtm``). Use ``explode=True`` before ``qtm2geo`` for one
        cell geometry per row.
        """
        result = self._df.geometry.apply(
            lambda geom: polyfill_row(geom, resolution, predicate, compact)
        )

        if not explode:
            assign_args = {QTM_COL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(QTM_COL)
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
        """Bin points into qtm cells and compute statistics."""
        qtm_col = QTM_COL
        df = self.latlon2qtm(resolution, lat_col, lon_col)
        result = aggregate_bin(df, qtm_col, stats, numeric_col, category_col)
        return result.qtm.qtm2geo(qtm_col=qtm_col)
