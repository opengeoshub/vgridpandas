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
from vgrid.conversion.latlon2dggs import latlon2isea4t as latlon_to_isea4t
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgridpandas.utils.const import ISEA4T_COL  
from vgrid.conversion.dggs2geo.isea4t2geo import isea4t2geo as isea4t_to_geo
from vgrid.conversion.dggscompact.isea4tcompact import isea4t_compact
from vgrid.utils.geometry import check_predicate

AnyDataFrame = Union[DataFrame, GeoDataFrame]           

if platform.system() == "Windows":
    from vgrid.dggs.eaggr.enums.shape_string_format import ShapeStringFormat
    from vgrid.dggs.eaggr.eaggr import Eaggr
    from vgrid.dggs.eaggr.enums.model import Model
    from vgrid.generator.isea4tgrid import get_isea4t_children_cells_within_bbox
    from vgrid.utils.io import validate_isea4t_resolution
    from vgrid.utils.constants import ISEA4T_RES_ACCURACY_DICT

    isea4t_dggs = Eaggr(Model.ISEA4T)   


def _isea4t_children_for_bounds(bounds, resolution):
    """Return ISEA4T cell ids covering a geometry bounding box."""
    accuracy = ISEA4T_RES_ACCURACY_DICT.get(resolution)
    bounding_box = box(*bounds)
    bounding_box_wkt = bounding_box.wkt
    shapes = isea4t_dggs.convert_shape_string_to_dggs_shapes(
        bounding_box_wkt, ShapeStringFormat.WKT, accuracy
    )
    shape = shapes[0]
    bbox_cells = shape.get_shape().get_outer_ring().get_cells()
    bounding_cell = isea4t_dggs.get_bounding_dggs_cell(bbox_cells)
    return get_isea4t_children_cells_within_bbox(
        bounding_cell.get_cell_id(), bounding_box, resolution
    )


def poly2isea4t(
    geometry,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
    fix_antimeridian: Optional[str] = None,
) -> list:
    """
    Convert polygon or line geometries to ISEA4T grid cells.

    Mirrors ``polygon2isea4t`` and ``polyline2isea4t`` in vgrid (Windows only).
    Polygons are filtered with ``predicate``; lines use intersection.
    Compact mode applies to polygons after predicate filtering.

    Args:
        resolution (int): ISEA4T resolution level [0..28]
        geometry: Polygon, MultiPolygon, LineString, or MultiLineString
        predicate (str, optional): Spatial predicate for polygons
            ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact (bool, optional): Enable ISEA4T compact mode for polygons
        fix_antimeridian (str, optional): Antimeridian fixing method passed to
            ``isea4t2geo``: shift, shift_balanced, shift_west, shift_east, split, none

    Returns:
        list: List of ISEA4T cell ids
    """
    if platform.system() != "Windows":
        return []

    resolution = validate_isea4t_resolution(resolution)
    isea4t_ids = []
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
        bounding_child_cells = _isea4t_children_for_bounds(poly.bounds, resolution)

        poly_ids = []
        for child in bounding_child_cells:
            isea4t_id = child
            cell_polygon = isea4t_to_geo(
                isea4t_id, fix_antimeridian=fix_antimeridian
            )
            if is_line:
                if not cell_polygon.intersects(poly):
                    continue
            elif not check_predicate(cell_polygon, poly, predicate):
                continue
            poly_ids.append(isea4t_id)

        if compact and poly_ids and not is_line:
            poly_ids = list(isea4t_compact(poly_ids))

        isea4t_ids.extend(poly_ids)

    return list(dict.fromkeys(isea4t_ids))


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
            poly2isea4t(geometry, resolution, predicate, compact, fix_antimeridian)
        )
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            poly2isea4t(
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


@pd.api.extensions.register_dataframe_accessor("isea4t")
class ISEA4TPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    def latlon2isea4t(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds ISEA4T ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            ISEA4T resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with ISEA4T ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with ISEA4T IDs added
        """
        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        isea4t_ids = [
            latlon_to_isea4t(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        isea4t_col = ISEA4T_COL
        assign_arg = {isea4t_col: isea4t_ids, f"{isea4t_col}_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(isea4t_col)         
        return df

    def isea4t2geo(
        self, isea4t_col: str = None, fix_antimeridian: Optional[str] = None
    ) -> GeoDataFrame:
        """Add geometry with ISEA4T geometry to the DataFrame."""
        if isea4t_col is not None:
            if isea4t_col not in self._df.columns:  
                raise ValueError(f"Column '{isea4t_col}' not found in DataFrame")
            ids = self._df[isea4t_col]
        else:       
            if ISEA4T_COL not in self._df.columns:
                raise ValueError(f"Column '{ISEA4T_COL}' not found in DataFrame")
            ids = self._df[ISEA4T_COL]
        return dggs_ids_to_geodataframe(
            self._df, ids, isea4t_to_geo, fix_antimeridian=fix_antimeridian
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
            isea4t resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the isea4t IDs
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        fix_antimeridian : str, optional
            Antimeridian fixing method passed to ``isea4t2geo``
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(
                geom, resolution, predicate, compact, fix_antimeridian
            )
        )

        if not explode:
            assign_args = {ISEA4T_COL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(ISEA4T_COL)
        return self._df.join(result)

    def isea4tbin(
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
        Bin points into isea4t cells and compute statistics.
        """
        isea4t_col = ISEA4T_COL
        df = self.latlon2isea4t(resolution, lat_col, lon_col)
        result = aggregate_bin(df, isea4t_col, stats, numeric_col, category_col)
        return result.isea4t.isea4t2geo(
            isea4t_col=isea4t_col, fix_antimeridian=fix_antimeridian
        )