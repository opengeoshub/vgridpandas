from typing import Union, Optional
import platform
from shapely.geometry import (
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
    box,
)
import pandas as pd
import geopandas as gpd
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgrid.conversion.latlon2dggs import latlon2isea3h as latlon_to_isea3h
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgridpandas.utils.const import ISEA3H_COL
from vgrid.conversion.dggs2geo.isea3h2geo import isea3h2geo as isea3h_to_geo
from vgrid.conversion.dggscompact.isea3hcompact import isea3h_compact
from vgrid.utils.geometry import check_predicate

AnyDataFrame = Union[DataFrame, GeoDataFrame]

if platform.system() == "Windows":
    from vgrid.dggs.eaggr.eaggr import Eaggr
    from vgrid.dggs.eaggr.shapes.dggs_cell import DggsCell
    from vgrid.dggs.eaggr.enums.model import Model
    from vgrid.dggs.eaggr.enums.shape_string_format import ShapeStringFormat
    from vgrid.generator.isea3hgrid import get_isea3h_children_cells_within_bbox
    from vgrid.utils.io import validate_isea3h_resolution
    from vgrid.utils.constants import ISEA3H_RES_ACCURACY_DICT

    isea3h_dggs = Eaggr(Model.ISEA3H)


def _isea3h_children_for_bounds(bounds, resolution):
    """Return ISEA3H cell ids covering a geometry bounding box."""
    accuracy = ISEA3H_RES_ACCURACY_DICT.get(resolution)
    bounding_box = box(*bounds)
    bounding_box_wkt = bounding_box.wkt
    shapes = isea3h_dggs.convert_shape_string_to_dggs_shapes(
        bounding_box_wkt, ShapeStringFormat.WKT, accuracy
    )
    shape = shapes[0]
    bbox_cells = shape.get_shape().get_outer_ring().get_cells()
    bounding_cell = isea3h_dggs.get_bounding_dggs_cell(bbox_cells)
    return get_isea3h_children_cells_within_bbox(
        bounding_cell.get_cell_id(), bounding_box, resolution
    )


def poly2isea3h(
    geometry,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
    fix_antimeridian: Optional[str] = None,
) -> list:
    """
    Convert polygon or line geometries to ISEA3H grid cells.

    Mirrors ``polygon2isea3h`` and ``polyline2isea3h`` in vgrid (Windows only).
    Polygons are filtered with ``predicate``; lines use intersection.
    Compact mode applies to polygons after predicate filtering.

    Args:
        resolution (int): ISEA3H resolution level [0..32]
        geometry: Polygon, MultiPolygon, LineString, or MultiLineString
        predicate (str, optional): Spatial predicate for polygons
            ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact (bool, optional): Enable ISEA3H compact mode for polygons
        fix_antimeridian (str, optional): Antimeridian fixing method passed to
            ``isea3h2geo``: shift, shift_balanced, shift_west, shift_east, split, none

    Returns:
        list: List of ISEA3H cell ids

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2isea3h(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """
    if platform.system() != "Windows":
        return []

    resolution = validate_isea3h_resolution(resolution)
    isea3h_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        if poly is None or poly.is_empty:
            continue

        is_line = isinstance(poly, LineString)
        bounding_child_cells = _isea3h_children_for_bounds(poly.bounds, resolution)

        poly_ids = []
        for child in bounding_child_cells:
            isea3h_cell = DggsCell(child)
            isea3h_id = isea3h_cell.get_cell_id()
            cell_polygon = isea3h_to_geo(
                isea3h_id, fix_antimeridian=fix_antimeridian
            )
            if is_line:
                if not cell_polygon.intersects(poly):
                    continue
            elif not check_predicate(cell_polygon, poly, predicate):
                continue
            poly_ids.append(isea3h_id)

        if compact and poly_ids and not is_line:
            poly_ids = list(isea3h_compact(poly_ids))

        isea3h_ids.extend(poly_ids)

    return list(dict.fromkeys(isea3h_ids))


def polyfill_row(
    geometry,
    resolution,
    predicate=None,
    compact=False,
    fix_antimeridian: Optional[str] = None,
) -> list:
    """Return cell ids covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(
            poly2isea3h(geometry, resolution, predicate, compact, fix_antimeridian)
        )
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            poly2isea3h(
                geometry,
                resolution,
                predicate="intersect",
                compact=False,
                fix_antimeridian=fix_antimeridian,
            )
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
    return list(tokens)


@pd.api.extensions.register_dataframe_accessor("isea3h")
class ISEA3HPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    def latlon2isea3h(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds isea3h ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            isea3h resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with isea3h ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with isea3h IDs added
        """
        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        isea3h_ids = [
            latlon_to_isea3h(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        isea3h_col = ISEA3H_COL
        assign_arg = {isea3h_col: isea3h_ids, f"{isea3h_col}_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(isea3h_col)
        return df

    def isea3h2geo(
        self, isea3h_col: str = None, fix_antimeridian: Optional[str] = None
    ) -> GeoDataFrame:
        """Add geometry with ISEA3H geometry to the DataFrame."""
        if isea3h_col is not None:
            if isea3h_col not in self._df.columns:
                raise ValueError(f"Column '{isea3h_col}' not found in DataFrame")
            ids = self._df[isea3h_col]
        else:
            if ISEA3H_COL not in self._df.columns:
                raise ValueError(f"Column '{ISEA3H_COL}' not found in DataFrame")
            ids = self._df[ISEA3H_COL]
        return dggs_ids_to_geodataframe(
            self._df, ids, isea3h_to_geo, fix_antimeridian=fix_antimeridian
        )

    def polyfill(
        self,
        resolution: int,
        predicate: str = None,
        compact: bool = False,
        explode: bool = False,
        fix_antimeridian: Optional[str] = None,
    ) -> AnyDataFrame:
        """
        Parameters
        ----------
        resolution : int
            isea3h resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the isea3h IDs
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        fix_antimeridian : str, optional
            Antimeridian fixing method passed to ``isea3h2geo``
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(
                geom, resolution, predicate, compact, fix_antimeridian
            )
        )

        if not explode:
            assign_args = {ISEA3H_COL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(ISEA3H_COL)
        return self._df.join(result)

    def isea3hbin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
        fix_antimeridian: Optional[str] = None,
    ) -> GeoDataFrame:
        """
        Bin points into isea3h cells and compute statistics.
        """
        isea3h_col = ISEA3H_COL
        df = self.latlon2isea3h(resolution, lat_col, lon_col)
        result = aggregate_bin(df, isea3h_col, stats, numeric_col, category_col)
        return result.isea3h.isea3h2geo(
            isea3h_col=isea3h_col, fix_antimeridian=fix_antimeridian
        )