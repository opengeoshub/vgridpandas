from typing import Union
from shapely.geometry import (
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
)
import pandas as pd
import geopandas as gpd
from vgrid.conversion.latlon2dggs import latlon2olc as latlon_to_olc
from pandas.core.frame import DataFrame
from geopandas.geodataframe import GeoDataFrame
from vgridpandas.utils.geo_helpers import dggs_ids_to_geodataframe
from vgridpandas.utils.bin_helpers import aggregate_bin

from vgrid.conversion.dggs2geo.olc2geo import olc2geo as olc_to_geo
from vgridpandas.utils.const import OLC_COL

AnyDataFrame = Union[DataFrame, GeoDataFrame]


from typing import Union, Set
from vgrid.generator.olcgrid import olc_grid, olc_refine_cell
from vgrid.utils.io import validate_olc_resolution
from vgrid.conversion.dggscompact.olccompact import olc_compact
from vgrid.utils.geometry import check_predicate

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]


def poly2olc(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to OLC grid cells.

    Args:
        resolution (int): OLC resolution level [2,4,6,8,10,11,12,13,14,15]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of olc ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2olc(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_olc_resolution(resolution)
    olc_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        base_resolution = 2
        base_cells_gdf = olc_grid(base_resolution, verbose=False)
        seed_cells = []
        for idx, base_cell in base_cells_gdf.iterrows():
            base_cell_poly = base_cell["geometry"]
            if poly.intersects(base_cell_poly):
                seed_cells.append(base_cell)
        refined_features = []
        for seed_cell in seed_cells:
            seed_cell_poly = seed_cell["geometry"]
            if seed_cell_poly.contains(poly) and resolution == base_resolution:
                refined_features.append(seed_cell)
            else:
                refined_features.extend(
                    olc_refine_cell(
                        seed_cell_poly.bounds, base_resolution, resolution, poly
                    )
                )
        resolution_features = [
            refined_feature
            for refined_feature in refined_features
            if refined_feature["resolution"] == resolution
        ]
        seen_olc_ids = set()
        for resolution_feature in resolution_features:
            olc_id = resolution_feature["olc"]
            if olc_id not in seen_olc_ids:
                cell_geom = resolution_feature["geometry"]
                if not check_predicate(cell_geom, poly, predicate):
                    continue
                olc_ids.append(olc_id)  # Only append the OLC code string
                seen_olc_ids.add(olc_id)
    if compact:
        return olc_compact(olc_ids)
    return olc_ids


def polyfill_row(geometry, resolution, predicate=None, compact=False) -> list:
    """Return cell ids covering a single row geometry."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        tokens = set(poly2olc(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        tokens = set(
            poly2olc(geometry, resolution, predicate="intersect", compact=False)
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
    return list(tokens)


@pd.api.extensions.register_dataframe_accessor("olc")
class OLCPandas:
    def __init__(self, df: DataFrame):
        self._df = df

    # olc API
    # These methods simply mirror the Vgrid olc API and apply olc functions to all rows

    def latlon2olc(
        self,
        resolution: int,
        lat_col: str = "lat",
        lon_col: str = "lon",
        set_index: bool = False,
    ) -> AnyDataFrame:
        """Adds OLC ID to (Geo)DataFrame.

        pd.DataFrame: uses `lat_col` and `lon_col` (default `lat` and `lon`)
        gpd.GeoDataFrame: uses `geometry`

        Assumes coordinates in epsg=4326.

        Parameters
        ----------
        resolution : int
            OLC resolution
        lat_col : str
            Name of the latitude column (if used), default 'lat'
        lon_col : str
            Name of the longitude column (if used), default 'lon'
        set_index : bool
            If True, the columns with OLC ID is set as index, default 'True'

        Returns
        -------
        (Geo)DataFrame with OLC IDs added
        """

        if isinstance(self._df, gpd.GeoDataFrame):
            lons = self._df.geometry.x
            lats = self._df.geometry.y
        else:
            lons = self._df[lon_col]
            lats = self._df[lat_col]

        olc_ids = [latlon_to_olc(lat, lon, resolution) for lat, lon in zip(lats, lons)]

        olc_col = OLC_COL
        assign_arg = {olc_col: olc_ids, f"{olc_col}_res": resolution}
        df = self._df.assign(**assign_arg)
        if set_index:
            return df.set_index(olc_col)
        return df

    def olc2geo(self, olc_col: str = None) -> GeoDataFrame:
        """Add geometry with OLC geometry to the DataFrame."""
        if olc_col is not None:
            if olc_col not in self._df.columns:
                raise ValueError(f"Column '{olc_col}' not found in DataFrame")
            ids = self._df[olc_col]
        else:
            if OLC_COL not in self._df.columns:
                raise ValueError(f"Column '{OLC_COL}' not found in DataFrame")
            ids = self._df[OLC_COL]
        return dggs_ids_to_geodataframe(self._df, ids, olc_to_geo)

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
            OLC resolution
        predicate : str, optional
            Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')
        compact : bool, optional
            Whether to compact the OLC IDs
        explode : bool
            If True, will explode the resulting list vertically.
            All other columns' values are copied.
            Default: False
        """

        result = self._df.geometry.apply(
            lambda geom: polyfill_row(geom, resolution, predicate, compact)
        )

        if not explode:
            assign_args = {OLC_COL: result}
            return self._df.assign(**assign_args)

        result = result.explode().to_frame(OLC_COL)
        return self._df.join(result)

    def olcbin(
        self,
        resolution: int,
        stats: str = "count",
        numeric_col: str = None,
        category_col: str = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> GeoDataFrame:
        """
        Bin points into olc cells and compute statistics.
        """
        olc_col = OLC_COL
        df = self.latlon2olc(resolution, lat_col, lon_col)
        result = aggregate_bin(df, olc_col, stats, numeric_col, category_col)
        return result.olc.olc2geo(olc_col=olc_col)
