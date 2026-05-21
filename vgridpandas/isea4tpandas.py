from typing import Union
from shapely.geometry import (
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
)
import pandas as pd
import geopandas as gpd
from vgrid.conversion.latlon2dggs import latlon2isea4t as latlon_to_isea4t
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgridpandas.utils.const import COLUMN_ISEA4T_POLYFILL
from vgrid.conversion.dggs2geo.isea4t2geo import isea4t2geo as isea4t_to_geo

AnyDataFrame = Union[DataFrame, GeoDataFrame]


from typing import Union, Set
from shapely.geometry import box
import platform
from vgrid.conversion.dggscompact.isea4tcompact import isea4t_compact
from vgrid.utils.geometry import check_predicate

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

if platform.system() == "Windows":
    from vgrid.dggs.eaggr.enums.shape_string_format import ShapeStringFormat
    from vgrid.dggs.eaggr.eaggr import Eaggr
    from vgrid.dggs.eaggr.shapes.dggs_cell import DggsCell
    from vgrid.dggs.eaggr.enums.model import Model
    from vgrid.generator.isea4tgrid import get_isea4t_children_cells_within_bbox
    from vgrid.utils.geometry import (
        isea4t_cell_to_polygon,
        fix_isea4t_antimeridian_cells,
    )
    from vgrid.utils.io import validate_isea4t_resolution
    from vgrid.utils.constants import ISEA4T_RES_ACCURACY_DICT

    isea4t_dggs = Eaggr(Model.ISEA4T)


def poly2isea4t(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to isea4t grid cells.

    Args:
        resolution (int): ISEA4T resolution level [0..28]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of isea4t ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2isea4t(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """
    if platform.system() == "Windows":
        resolution = validate_isea4t_resolution(resolution)
        isea4t_ids = []
        if isinstance(geometry, (Polygon, LineString)):
            polys = [geometry]
        elif isinstance(geometry, (MultiPolygon, MultiLineString)):
            polys = list(geometry.geoms)
        else:
            return []

        for poly in polys:
            accuracy = ISEA4T_RES_ACCURACY_DICT.get(resolution)
            bounding_box = box(*poly.bounds)
            bounding_box_wkt = bounding_box.wkt
            shapes = isea4t_dggs.convert_shape_string_to_dggs_shapes(
                bounding_box_wkt, ShapeStringFormat.WKT, accuracy
            )
            shape = shapes[0]
            bbox_cells = shape.get_shape().get_outer_ring().get_cells()
            bounding_cell = isea4t_dggs.get_bounding_dggs_cell(bbox_cells)
            bounding_child_cells = get_isea4t_children_cells_within_bbox(
                bounding_cell.get_cell_id(), bounding_box, resolution
            )
            if compact:
                bounding_child_cells = isea4t_compact(bounding_child_cells)
            for child in bounding_child_cells:
                isea4t_cell = DggsCell(child)
                cell_polygon = isea4t_cell_to_polygon(isea4t_cell)
                isea4t_id = isea4t_cell.get_cell_id()
                if isea4t_id.startswith(("00", "09", "14", "04", "19")):
                    cell_polygon = fix_isea4t_antimeridian_cells(cell_polygon)
                if check_predicate(cell_polygon, poly, predicate):
                    isea4t_ids.append(isea4t_id)
        return isea4t_ids


def polyfill_row(geometry, resolution, predicate=None, compact=False) -> list:
    """Return cell ids covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(poly2isea4t(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            poly2isea4t(geometry, resolution, predicate="intersect", compact=False)
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
    return list(tokens)


@pd.api.extensions.register_dataframe_accessor("isea4t")
class ISEA4TPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # ISEA4T API
    # These methods simply mirror the Vgrid ISEA4T API and apply ISEA4T functions to all rows

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

        # isea4t_column = self._format_resolution(resolution)
        isea4t_column = "isea4t"
        assign_arg = {isea4t_column: isea4t_ids, "isea4t_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(isea4t_column)
        return df

    def isea4t2geo(self, isea4t_col: str = None) -> GeoDataFrame:
        """Add geometry with ISEA4T geometry to the DataFrame."""
        if isea4t_col is not None:
            if isea4t_col not in self._df.columns:
                raise ValueError(f"Column '{isea4t_col}' not found in DataFrame")
            ids = self._df[isea4t_col]
        else:
            if "isea4t" not in self._df.columns:
                raise ValueError("Column 'isea4t' not found in DataFrame")
            ids = self._df["isea4t"]
        return dggs_ids_to_geodataframe(self._df, ids, isea4t_to_geo)

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
            isea4t resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the isea4t IDs
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(geom, resolution, predicate, compact)
        )

        if not explode:
            assign_args = {COLUMN_ISEA4T_POLYFILL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(COLUMN_ISEA4T_POLYFILL)
        return self._df.join(result)

    def isea4tbin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> GeoDataFrame:
        """
        Bin points into isea4t cells and compute statistics.
        """
        isea4t_col = "isea4t"
        df = self.latlon2isea4t(resolution, lat_col, lon_col)
        result = aggregate_bin(df, isea4t_col, stats, numeric_col, category_col)
        return result.isea4t.isea4t2geo(isea4t_col=isea4t_col)

    def _format_resolution(resolution: int) -> str:
        return f"ease_{str(resolution).zfill(2)}"
