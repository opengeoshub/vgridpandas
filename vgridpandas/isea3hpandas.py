from typing import Union
from shapely.geometry import (
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
)
import pandas as pd
import geopandas as gpd
from vgrid.conversion.latlon2dggs import latlon2isea3h as latlon_to_isea3h
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgridpandas.utils.const import COLUMN_ISEA3H_POLYFILL
from vgrid.conversion.dggs2geo.isea3h2geo import isea3h2geo as isea3h_to_geo

AnyDataFrame = Union[DataFrame, GeoDataFrame]


from typing import Union, Set
from shapely.geometry import box
import platform
from vgrid.utils.geometry import check_predicate
from vgrid.utils.io import validate_isea3h_resolution
from vgrid.utils.geometry import isea3h_cell_to_polygon
from vgrid.generator.isea3hgrid import get_isea3h_children_cells_within_bbox

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

if platform.system() == "Windows":
    from vgrid.dggs.eaggr.eaggr import Eaggr
    from vgrid.dggs.eaggr.shapes.dggs_cell import DggsCell
    from vgrid.dggs.eaggr.enums.model import Model
    from vgrid.dggs.eaggr.enums.shape_string_format import ShapeStringFormat
    from vgrid.utils.constants import ISEA3H_RES_ACCURACY_DICT

    isea3h_dggs = Eaggr(Model.ISEA3H)


def poly2isea3h(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to isea3h grid cells.

    Args:
        resolution (int): isea3h resolution level [0..28]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of isea3h ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2isea3h(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """
    if platform.system() == "Windows":
        resolution = validate_isea3h_resolution(resolution)
        isea3h_ids = []
        if isinstance(geometry, (Polygon, LineString)):
            polys = [geometry]
        elif isinstance(geometry, (MultiPolygon, MultiLineString)):
            polys = list(geometry.geoms)
        else:
            return []

        for poly in polys:
            accuracy = ISEA3H_RES_ACCURACY_DICT.get(resolution)
            bounding_box = box(*poly.bounds)
            bounding_box_wkt = bounding_box.wkt
            shapes = isea3h_dggs.convert_shape_string_to_dggs_shapes(
                bounding_box_wkt, ShapeStringFormat.WKT, accuracy
            )
            shape = shapes[0]
            bbox_cells = shape.get_shape().get_outer_ring().get_cells()
            bounding_cell = isea3h_dggs.get_bounding_dggs_cell(bbox_cells)
            bounding_child_cells = get_isea3h_children_cells_within_bbox(
                bounding_cell.get_cell_id(), bounding_box, resolution
            )
            for child in bounding_child_cells:
                isea3h_cell = DggsCell(child)
                cell_polygon = isea3h_cell_to_polygon(isea3h_cell)
                if check_predicate(cell_polygon, poly, predicate):
                    isea3h_ids.append(isea3h_cell.get_cell_id())
        return isea3h_ids


def polyfill_row(geometry, resolution, predicate=None, compact=False) -> list:
    """Return cell ids covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(poly2isea3h(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            poly2isea3h(geometry, resolution, predicate="intersect", compact=False)
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
    return list(tokens)


@pd.api.extensions.register_dataframe_accessor("isea3h")
class ISEA3HPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # isea3h API
    # These methods simply mirror the Vgrid isea3h API and apply isea3h functions to all rows

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

        # isea3h_column = self._format_resolution(resolution)
        isea3h_column = "isea3h"
        assign_arg = {isea3h_column: isea3h_ids, "isea3h_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(isea3h_column)
        return df

    def isea3h2geo(self, isea3h_col: str = None) -> GeoDataFrame:
        """Add geometry with ISEA3H geometry to the DataFrame."""
        if isea3h_col is not None:
            if isea3h_col not in self._df.columns:
                raise ValueError(f"Column '{isea3h_col}' not found in DataFrame")
            ids = self._df[isea3h_col]
        else:
            if "isea3h" not in self._df.columns:
                raise ValueError("Column 'isea3h' not found in DataFrame")
            ids = self._df["isea3h"]
        return dggs_ids_to_geodataframe(self._df, ids, isea3h_to_geo)

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
            isea3h resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the isea3h IDs
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(geom, resolution, predicate, compact)
        )

        if not explode:
            assign_args = {COLUMN_ISEA3H_POLYFILL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(COLUMN_ISEA3H_POLYFILL)
        return self._df.join(result)

    def isea3hbin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> GeoDataFrame:
        """
        Bin points into isea3h cells and compute statistics.
        """
        isea3h_col = "isea3h"
        df = self.latlon2isea3h(resolution, lat_col, lon_col)
        result = aggregate_bin(df, isea3h_col, stats, numeric_col, category_col)
        return result.isea3h.isea3h2geo(isea3h_col=isea3h_col)

    def _format_resolution(resolution: int) -> str:
        return f"ease_{str(resolution).zfill(2)}"
