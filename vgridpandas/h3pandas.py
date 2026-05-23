from typing import Union, Optional, Iterator


import pandas as pd
import geopandas as gpd

import h3
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, box
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin

from vgrid.utils.geometry import check_predicate
from vgrid.utils.io import validate_h3_resolution
from vgridpandas.utils.const import H3_COL
from vgrid.conversion.latlon2dggs import latlon2h3 as latlon_to_h3
from vgrid.conversion.dggs2geo.h32geo import h32geo as h3_to_geo

AnyDataFrame = Union[DataFrame, GeoDataFrame]


MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]


def poly2h3(geometry, resolution, predicate=None, compact=False, fix_antimeridian=None):
    """
    Convert polygon geometries (Polygon, MultiPolygon) to H3 grid cells.

    Args:
        resolution (int): H3 resolution level [0..15]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact (bool): Enable H3 compact mode
        fix_antimeridian (str, optional): 'shift', 'shift_balanced', 'shift_west', 'shift_east', or 'split'
    Returns:
        list: List of H3 IDs intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2h3(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """
    h3_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        bbox = box(*poly.bounds)
        bbox_cells = h3.geo_to_cells(bbox, resolution)
        if compact:
            bbox_cells = h3.compact_cells(bbox_cells)

        for bbox_cell in bbox_cells:
            cell_polygon = h3_to_geo(bbox_cell, fix_antimeridian=fix_antimeridian)
            if not check_predicate(cell_polygon, poly, predicate):
                continue
            h3_ids.append(bbox_cell)

    return h3_ids


def linetrace(geometry: MultiLineOrLine, resolution: int) -> Iterator[str]:
    """h3.polyfill equivalent for shapely (Multi)LineString.

    Cells may repeat at self-intersections or shared vertices.

    Parameters
    ----------
    geometry : LineString or MultiLineString
        Line to trace with H3 cells
    resolution : int
        H3 resolution of the tracing cells

    Returns
    -------
    Set of H3 IDs

    Raises
    ------
    TypeError if geometry is not a LineString or a MultiLineString
    """
    if isinstance(geometry, MultiLineString):
        # Recurse after getting component linestrings from the multiline
        for line in map(lambda geom: linetrace(geom, resolution), geometry.geoms):
            yield from line
    elif isinstance(geometry, LineString):
        coords = zip(geometry.coords, geometry.coords[1:])
        while (vertex_pair := next(coords, None)) is not None:
            i, j = vertex_pair
            a = h3.latlng_to_cell(*i[::-1], resolution)
            b = h3.latlng_to_cell(*j[::-1], resolution)
            yield from h3.grid_path_cells(a, b)  # inclusive of a and b
    else:
        raise TypeError(f"Unknown type {type(geometry)}")


def polyfill_row(
    geometry, resolution, predicate=None, compact=False, fix_antimeridian=None
) -> list:
    """Return cell ids covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(
            poly2h3(geometry, resolution, predicate, compact, fix_antimeridian)
        )
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(linetrace(geometry, resolution))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
    return list(tokens)


@pd.api.extensions.register_dataframe_accessor("h3")
class H3Pandas:
    def __init__(self, df: DataFrame):
        self._df = df

    def latlon2h3(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds H3 index to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            H3 resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the column with H3 ID is set as index, default False

        Returns
        -------
        (Geo)DataFrame with H3 ID added

        See Also
        --------
        geo2h3_aggregate : Extended API method that aggregates points by H3 id

        Examples
        --------
        >>> df = pd.DataFrame({'lat': [50, 51], 'lon':[14, 15]})
        >>> df.h3.latlon2h3(8)
                         lat  lon
        h3
        881e309739fffff   50   14
        881e2659c3fffff   51   15

        >>> df.h3.latlon2h3(8, set_index=False)
           lat  lon            h3
        0   50   14  881e309739fffff
        1   51   15  881e2659c3fffff

        >>> gdf = gpd.GeoDataFrame({'val': [5, 1]},
        >>> geometry=gpd.points_from_xy(x=[14, 15], y=(50, 51)))
        >>> gdf.h3.latlon2h3(8)
                         val                   geometry
        h3
        881e309739fffff    5  POINT (14.00000 50.00000)
        881e2659c3fffff    1  POINT (15.00000 51.00000)

        """
        resolution = validate_h3_resolution(resolution)
        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        h3_ids = [latlon_to_h3(lat, lon, resolution) for lat, lon in zip(lats, lons)]

        h3_col = H3_COL
        assign_arg = {h3_col: h3_ids, f"{h3_col}_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(h3_col)
        return df

    def h32geo(
        self, h3_col: str = None, fix_antimeridian: Optional[str] = None
    ) -> GeoDataFrame:
        """Add geometry with H3 geometry to the DataFrame."""
        if h3_col is not None:
            if h3_col not in self._df.columns:
                raise ValueError(f"Column '{h3_col}' not found in DataFrame")
            ids = self._df[h3_col]
        else:
            if H3_COL not in self._df.columns:
                raise ValueError(f"Column '{H3_COL}' not found in DataFrame")
            ids = self._df[H3_COL]
        return dggs_ids_to_geodataframe(
            self._df, ids, h3_to_geo, fix_antimeridian=fix_antimeridian
        )

    def h3bin(
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
        Bin points into h3 cells and compute statistics.
        """
        h3_col = H3_COL
        df = self.latlon2h3(resolution, lat_col, lon_col)
        result = aggregate_bin(df, h3_col, stats, numeric_col, category_col)
        return result.h3.h32geo(h3_col=h3_col, fix_antimeridian=fix_antimeridian)

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
            H3 resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Enable H3 compact mode
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        fix_antimeridian : str, optional
            Antimeridian fix: 'shift', 'shift_balanced', 'shift_west', 'shift_east', or 'split'
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(
                geom, resolution, predicate, compact, fix_antimeridian
            )
        )

        if not explode:
            return self._df.assign(**{H3_COL: result})

        result = result.explode().to_frame(H3_COL)
        return self._df.join(result)

    def linetrace(self, resolution: int, explode: bool = False) -> AnyDataFrame:
        """An H3 cell representation of a (Multi)LineString traced along its vertices.

        Parameters
        ----------
        resolution : int
            H3 resolution
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False

        Returns
        -------
        (Geo)DataFrame with H3 cells with centroids within the input polygons.

        Examples
        --------
        >>> from shapely.geometry import LineString
        >>> gdf = gpd.GeoDataFrame(geometry=[LineString([[0, 0], [1, 0], [1, 1]])])
        >>> gdf.h3.linetrace(4)
                                                    geometry                                       h3_linetrace
        0  LINESTRING (0.00000 0.00000, 1.00000 0.00000, ...  [83754efffffffff, 83754cfffffffff, 837541fffff...  # noqa E501
        >>> gdf.h3.linetrace(4, explode=True)
                                                    geometry     h3_linetrace
        0  LINESTRING (0.00000 0.00000, 1.00000 0.00000, ...  83754efffffffff
        0  LINESTRING (0.00000 0.00000, 1.00000 0.00000, ...  83754cfffffffff
        0  LINESTRING (0.00000 0.00000, 1.00000 0.00000, ...  837541fffffffff

        """

        result = self._df.apply(
            lambda row: list(linetrace(row.geometry, resolution)), axis=1
        )
        if not explode:
            return self._df.assign(**{H3_COL: result})

        result = result.explode().to_frame(H3_COL)
        return self._df.join(result)
