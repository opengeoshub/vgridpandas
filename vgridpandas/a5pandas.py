"""A5Pandas module for A5 cell operations on pandas DataFrames and GeoDataFrames."""

from typing import Union, Iterator
from collections import deque
from shapely.geometry import (
    Point,
    MultiPoint,
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
    box,
)
import pandas as pd
import geopandas as gpd
import a5
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin
from vgrid.conversion.latlon2dggs import latlon2a5 as latlon_to_a5
from vgrid.conversion.dggs2geo.a52geo import a52geo as a5_to_geo, a52geo_u64
from vgrid.conversion.dggscompact.a5compact import a5compact
from vgrid.utils.geometry import check_predicate
from vgrid.utils.io import validate_a5_resolution
from vgridpandas.utils.const import A5_COL

AnyDataFrame = Union[DataFrame, GeoDataFrame]

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]
MultiPointOrPoint = Union[Point, MultiPoint]


def poly2a5(
    geometry, resolution, predicate=None, compact=False, split_antimeridian: bool = False
):
    """
    Convert polygon geometries (Polygon, MultiPolygon) to A5 grid cells.

    Args:
        resolution (int): A5 resolution level [0..29]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        split_antimeridian (bool, optional): Split antimeridian-crossing cells if True.
    Returns:
        list: List of A5 hexes intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2a5(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_a5_resolution(resolution)
    a5_hexes = []
    if isinstance(geometry, Polygon):
        polys = [geometry]
    elif isinstance(geometry, MultiPolygon):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        if poly is None or poly.is_empty:
            continue

        min_lng, min_lat, max_lng, max_lat = poly.bounds
        bbox_polygon = box(min_lng, min_lat, max_lng, max_lat)

        bbox_center_lon = bbox_polygon.centroid.x
        bbox_center_lat = bbox_polygon.centroid.y
        seed_cell_id = a5.lonlat_to_cell((bbox_center_lon, bbox_center_lat), resolution)
        seed_cell_polygon = a52geo_u64(
            seed_cell_id, split_antimeridian=split_antimeridian
        )

        if seed_cell_polygon is not None and seed_cell_polygon.contains(bbox_polygon):
            seed_cell_hex = a5.u64_to_hex(seed_cell_id)
            if check_predicate(seed_cell_polygon, poly, predicate):
                a5_hexes.append(seed_cell_hex)
            continue

        intersecting_cells = {}  # {cell_u64: cell_polygon}
        covered_cells = set()
        queue = deque([seed_cell_id])

        while queue:
            current_cell_id = queue.popleft()
            if current_cell_id in covered_cells:
                continue
            covered_cells.add(current_cell_id)

            cell_polygon = a52geo_u64(
                current_cell_id, split_antimeridian=split_antimeridian
            )
            if cell_polygon is None or cell_polygon.is_empty:
                continue

            if cell_polygon.intersects(bbox_polygon):
                intersecting_cells[current_cell_id] = cell_polygon
                neighbors = a5.uncompact(
                    a5.grid_disk_vertex(current_cell_id, 1), resolution
                )
                for neighbor_id in neighbors:
                    if neighbor_id not in covered_cells:
                        queue.append(neighbor_id)

        for cell_id, cell_polygon in intersecting_cells.items():
            if check_predicate(cell_polygon, poly, predicate):
                a5_hexes.append(a5.u64_to_hex(cell_id))

    a5_hexes = list(dict.fromkeys(a5_hexes))

    if compact and a5_hexes:
        # Create a GeoDataFrame with A5 hex codes and their geometries
        a5_data = []
        for a5_hex in a5_hexes:
            try:
                # Convert A5 hex to geometry
                geometry = a5_to_geo(a5_hex, split_antimeridian=split_antimeridian)
                a5_data.append({"a5": a5_hex, "geometry": geometry})
            except Exception:
                # Skip invalid A5 hex codes
                continue

        if a5_data:
            temp_gdf = gpd.GeoDataFrame(a5_data, crs="EPSG:4326")

            # Use a5compact function directly
            compacted_gdf = a5compact(temp_gdf, a5_hex="a5", output_format="gpd")

            if compacted_gdf is not None:
                # Extract A5 hex codes from compacted result
                a5_hexes = compacted_gdf["a5"].tolist()
            # If compaction failed, keep original results

    return a5_hexes


def linetrace(geometry: MultiLineOrLine, resolution: int) -> Iterator[str]:
    """Trace a (Multi)LineString with A5 cells along great-circle arcs between vertices.

    Uses ``a5.line_string_to_cells`` (same approach as ``polyline2a5`` in vgrid).
    Cells may repeat at self-intersections or shared vertices.
    """
    resolution = validate_a5_resolution(resolution)
    if isinstance(geometry, MultiLineString):
        for line in geometry.geoms:
            yield from linetrace(line, resolution)
    elif isinstance(geometry, LineString):
        coords = list(geometry.coords)
        if len(coords) < 2:
            return
        waypoints = [(lon, lat) for lon, lat in coords]
        try:
            ordered_cell_ids = a5.line_string_to_cells(waypoints, resolution)
        except Exception:
            ordered_cell_ids = []
        for cell_id in ordered_cell_ids:
            yield a5.u64_to_hex(cell_id)
    else:
        raise TypeError(f"Unknown type {type(geometry)}")


def polyfill_row(
    geometry, resolution, predicate=None, compact=False, split_antimeridian: bool = False
) -> list:
    """Return cell ids covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(
            poly2a5(geometry, resolution, predicate, compact, split_antimeridian)
        )
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(linetrace(geometry, resolution))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
    return list(tokens)


@pd.api.extensions.register_dataframe_accessor("a5")
class A5Pandas:
    def __init__(self, df: DataFrame):
        self._df = df

    def latlon2a5(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds A5 hex to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            A5 resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with A5 hex is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with A5 IDs added

        """
        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        a5_hexes = [latlon_to_a5(lat, lon, resolution) for lat, lon in zip(lats, lons)]

        # a5_col = self._format_resolution(resolution)
        a5_col = A5_COL
        assign_arg = {a5_col: a5_hexes, f"{a5_col}_res": resolution}    # a5_res is the resolution of the A5 cells
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(a5_col)
        return df

    def a52geo(
        self, a5_col: str = None, split_antimeridian: bool = False
    ) -> GeoDataFrame:
        """Add geometry with A5 geometry to the DataFrame.

        Parameters
        ----------
        split_antimeridian : bool, optional
            Split antimeridian-crossing cells. Default: False
        """
        if a5_col is not None:
            if a5_col not in self._df.columns:
                raise ValueError(f"Column '{a5_col}' not found in DataFrame")
            ids = self._df[a5_col]
        else:
            if A5_COL not in self._df.columns:
                raise ValueError(f"Column '{A5_COL}' not found in DataFrame")
            ids = self._df[A5_COL]
        return dggs_ids_to_geodataframe(
            self._df,
            ids,
            a5_to_geo,
            to_geo_kwargs={"split_antimeridian": split_antimeridian},
        )

    def polyfill(
        self,
        resolution: int,
        predicate: str = None,
        compact: bool = False,
        explode: bool = False,
        split_antimeridian: bool = False,
    ) -> AnyDataFrame:
        """
        Parameters
        ----------
        resolution : int
            A5 resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the A5 hexes
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        split_antimeridian : bool, optional
            Split antimeridian-crossing cells when converting to geometry.
            Default: False
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(
                geom, resolution, predicate, compact, split_antimeridian
            )
        )

        if not explode:
            return self._df.assign(**{A5_COL: result})

        result = result.explode().to_frame(A5_COL)
        return self._df.join(result)

    def linetrace(self, resolution: int, explode: bool = False) -> AnyDataFrame:
        """A5 cell representation of a (Multi)LineString traced along its vertices.

        Parameters
        ----------
        resolution : int
            A5 resolution
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        """
        result = self._df.apply(
            lambda row: list(linetrace(row.geometry, resolution)), axis=1
        )
        if not explode:
            return self._df.assign(**{A5_COL: result})
        result = result.explode().to_frame(A5_COL)
        return self._df.join(result)

    def a5bin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
        split_antimeridian: bool = False,
    ) -> GeoDataFrame:
        """
        Bin points into a5 cells and compute statistics.
        """
        a5_col = A5_COL
        df = self.latlon2a5(resolution, lat_col, lon_col)
        result = aggregate_bin(df, a5_col, stats, numeric_col, category_col)
        return result.a5.a52geo(a5_col=a5_col, split_antimeridian=split_antimeridian)