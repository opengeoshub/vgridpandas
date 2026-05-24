from typing import Union, Optional
from collections import deque
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
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgrid.conversion.latlon2dggs import latlon2rhealpix as latlon_to_rhealpix
from vgrid.conversion.dggs2geo.rhealpix2geo import rhealpix2geo as rhealpix_to_geo
from vgrid.conversion.dggscompact.rhealpixcompact import rhealpix_compact
from vgrid.utils.geometry import check_predicate
from vgrid.utils.io import validate_rhealpix_resolution
from vgridpandas.utils.const import RHEALPIX_COL
from vgrid.dggs.rhealpixdggs.dggs import RHEALPixDGGS
from vgrid.dggs.rhealpixdggs.ellipsoids import WGS84_ELLIPSOID

AnyDataFrame = Union[DataFrame, GeoDataFrame]

rhealpix_dggs = RHEALPixDGGS(
    ellipsoid=WGS84_ELLIPSOID, north_square=1, south_square=3, N_side=3
)


def poly2rhealpix(
    geometry,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
    fix_antimeridian: Optional[str] = None,
) -> list:
    """Convert polygon or line geometries to rHEALPix grid cells."""
    resolution = validate_rhealpix_resolution(resolution)
    rhealpix_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        if poly is None or poly.is_empty:
            continue

        minx, miny, maxx, maxy = poly.bounds
        bbox_polygon = box(minx, miny, maxx, maxy)
        bbox_center_lon = bbox_polygon.centroid.x
        bbox_center_lat = bbox_polygon.centroid.y
        seed_point = (bbox_center_lon, bbox_center_lat)
        seed_cell = rhealpix_dggs.cell_from_point(resolution, seed_point, plane=False)
        seed_cell_id = str(seed_cell)
        seed_cell_polygon = rhealpix_to_geo(
            seed_cell_id, fix_antimeridian=fix_antimeridian
        )

        if seed_cell_polygon.contains(bbox_polygon):
            if check_predicate(seed_cell_polygon, poly, predicate):
                rhealpix_ids.append(seed_cell_id)
            continue

        covered_cells = set()
        queue = deque([seed_cell])
        while queue:
            current_cell = queue.popleft()
            current_cell_id = str(current_cell)
            if current_cell_id in covered_cells:
                continue
            covered_cells.add(current_cell_id)

            cell_polygon = rhealpix_to_geo(
                current_cell_id, fix_antimeridian=fix_antimeridian
            )
            if not cell_polygon.intersects(bbox_polygon):
                continue

            neighbors = current_cell.neighbors(plane=False)
            for _, neighbor in neighbors.items():
                neighbor_id = str(neighbor)
                if neighbor_id not in covered_cells:
                    queue.append(neighbor)

        poly_ids = []
        for cell_id in covered_cells:
            cell_polygon = rhealpix_to_geo(cell_id, fix_antimeridian=fix_antimeridian)
            if not check_predicate(cell_polygon, poly, predicate):
                continue
            poly_ids.append(cell_id)

        if compact and poly_ids:
            poly_ids = list(rhealpix_compact(poly_ids))

        rhealpix_ids.extend(poly_ids)

    return list(dict.fromkeys(rhealpix_ids))


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
            poly2rhealpix(
                geometry, resolution, predicate, compact, fix_antimeridian
            )
        )
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            poly2rhealpix(
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


@pd.api.extensions.register_dataframe_accessor("rhealpix")
class rHEALPixPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    def latlon2rhealpix(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds RHEALPIX ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            rHEALPix resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with rHEALPix ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with rHEALPix rhp_ids added
        """
        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        rhealpix_ids = [
            latlon_to_rhealpix(lat, lon, resolution) for lat, lon in zip(lats, lons)
        ]

        rhealpix_col = RHEALPIX_COL
        assign_arg = {rhealpix_col: rhealpix_ids, f"{rhealpix_col}_res": resolution}

        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(rhealpix_col)
        return df

    def rhealpix2geo(
        self, rhealpix_col: str = None, fix_antimeridian: Optional[str] = None
    ) -> GeoDataFrame:
        """Add geometry with RHEALPIX geometry to the DataFrame."""
        if rhealpix_col is not None:
            if rhealpix_col not in self._df.columns:
                raise ValueError(f"Column '{rhealpix_col}' not found in DataFrame")
            ids = self._df[rhealpix_col]
        else:
            if RHEALPIX_COL not in self._df.columns:
                raise ValueError(f"Column '{RHEALPIX_COL}' not found in DataFrame")
            ids = self._df[RHEALPIX_COL]
        return dggs_ids_to_geodataframe(
            self._df, ids, rhealpix_to_geo, fix_antimeridian=fix_antimeridian
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
            rHEALPix resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the rHEALPix IDs
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        fix_antimeridian : str, optional
            Antimeridian fixing method: shift, shift_balanced, shift_west, shift_east, split, none
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(
                geom, resolution, predicate, compact, fix_antimeridian
            )
        )

        if not explode:
            assign_args = {RHEALPIX_COL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(RHEALPIX_COL)
        return self._df.join(result)

    def rhealpixbin(
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
        Bin points into rhealpix cells and compute statistics.
        """
        rhealpix_col = RHEALPIX_COL
        df = self.latlon2rhealpix(resolution, lat_col, lon_col)
        result = aggregate_bin(df, rhealpix_col, stats, numeric_col, category_col)
        return result.rhealpix.rhealpix2geo(
            rhealpix_col=rhealpix_col, fix_antimeridian=fix_antimeridian
        )