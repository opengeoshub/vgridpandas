from typing import Union, Set
import pandas as pd
import geopandas as gpd
from shapely.geometry import (
    Point,
    MultiPoint,
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
    box,
)
from vgrid.utils.geometry import check_predicate
from vgrid.utils.io import validate_dggrid_resolution

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]
MultiPointOrPoint = Union[Point, MultiPoint]


def poly2dggrid(
    dggrid_instance,
    dggs_type,
    geometry,
    resolution,
    predicate=None,
    compact=False,
    output_address_type=None,
):
    """
    Convert polygon geometries (Polygon, MultiPolygon) to DGGRID grid cells.

    Args:
        dggs_type: str
            DGGRID type
        resolution (int): DGGAL resolution level [0..28]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of DGGRID tokens intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2dggrid(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """
    resolution = validate_dggrid_resolution(dggs_type, resolution)
    merged_grids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        bounding_box = box(*poly.bounds)
        dggrid_gdf = dggrid_instance.grid_cell_polygons_for_extent(
            dggs_type,
            resolution,
            clip_geom=bounding_box,
            split_dateline=True,
            output_address_type=output_address_type,
        )

        # Keep only grid cells that satisfy predicate (defaults to intersects)
        if predicate:
            dggrid_gdf = dggrid_gdf[
                dggrid_gdf.geometry.apply(
                    lambda cell: check_predicate(cell, poly, predicate)
                )
            ]
        else:
            dggrid_gdf = dggrid_gdf[dggrid_gdf.intersects(poly)]
        try:
            if output_address_type != "SEQNUM":

                def address_transform(
                    dggrid_seqnum, dggs_type, resolution, address_type
                ):
                    address_type_transform = dggrid_instance.address_transform(
                        [dggrid_seqnum],
                        dggs_type=dggs_type,
                        resolution=resolution,
                        mixed_aperture_level=None,
                        input_address_type="SEQNUM",
                        output_address_type=output_address_type,
                    )
                    return address_type_transform.loc[0, address_type]

                dggrid_gdf["name"] = dggrid_gdf["name"].astype(str)
                dggrid_gdf["name"] = dggrid_gdf["name"].apply(
                    lambda val: address_transform(
                        val, dggs_type, resolution, output_address_type
                    )
                )
                dggrid_gdf = dggrid_gdf.rename(
                    columns={"name": output_address_type.lower()}
                )
            else:
                dggrid_gdf = dggrid_gdf.rename(columns={"name": "seqnum"})

        except Exception:
            pass

        merged_grids.append(dggrid_gdf)

        # Merge all filtered grids into one GeoDataFrame
        if merged_grids:
            final_grid = gpd.GeoDataFrame(
                pd.concat(merged_grids, ignore_index=True), crs=merged_grids[0].crs
            )
        else:
            final_grid = gpd.GeoDataFrame(columns=["geometry"], crs="EPSG:4326")

        dggrid_ids = final_grid[f"dggrid_{dggs_type}"].tolist()

    return dggrid_ids


def polyfill(
    dggrid_instance,
    dggs_type: str,
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
    address_type: str = "SEQNUM",
) -> Set[str]:
    """dggrid.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        DGGRID resolution of the filling cells

    Returns
    -------
    Set of DGGRID Tokens

    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(
            poly2dggrid(
                dggrid_instance,
                dggs_type,
                geometry,
                resolution,
                predicate,
                compact,
                address_type,
            )
        )
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(
            poly2dggrid(
                dggrid_instance,
                dggs_type,
                geometry,
                resolution,
                predicate="intersect",
                compact=False,
                address_type=address_type,
            )
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
