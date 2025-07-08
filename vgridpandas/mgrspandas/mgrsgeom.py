from typing import Union, Set, Iterator
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.wkt import loads
from shapely.ops import transform
from vgrid.utils import mgrs
import os, json
from shapely.geometry import shape

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

def cell2boundary(mgrs_id: str) -> Polygon:
    """mgrs.mgrs_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    mgrs_id : str
        mgrs ID to convert to a boundary

    Returns
    -------
    Polygon representing the mgrs cell boundary
    """
    min_lat, min_lon, max_lat, max_lon, _ = mgrs.mgrscell(mgrs_id)    
    cell_polygon = Polygon(
        [
            (min_lon, min_lat),
            (max_lon, min_lat),
            (max_lon, max_lat),
            (min_lon, max_lat),
            (min_lon, min_lat),
        ]
    )
    try:
        gzd_json_path = os.path.join(
            os.path.dirname(__file__), "./gzd.geojson"
        )
        with open(gzd_json_path, "r", encoding="utf-8") as f:
            gzd_data = json.load(f)
        gzd_features = gzd_data["features"]
        gzd_feature = [
            feature
            for feature in gzd_features
            if feature["properties"].get("gzd") == mgrs_id[:3]
        ][0]
        gzd_geom = shape(gzd_feature["geometry"])
        if mgrs_id[2] not in {"A", "B", "Y", "Z"}:
            if cell_polygon.intersects(gzd_geom) and not gzd_geom.contains(cell_polygon):
                intersected_polygon = cell_polygon.intersection(gzd_geom)
                if intersected_polygon:
                    return intersected_polygon
    except Exception as e:
        pass  # or handle/log as needed
    return cell_polygon

# def polyfill(geometry: MultiPolyOrPoly, resolution: int) -> Set[str]:
#     """mgrs.polyfill accepting a shapely (Multi)Polygon

#     Parameters
#     ----------
#     geometry : Polygon or Multipolygon
#         Polygon to fill
#     resolution : int
#         mgrs resolution of the filling cells

#     Returns
#     -------
#     Set of mgrs addresses

#     Raises
#     ------
#     TypeError if geometry is not a Polygon or MultiPolygon
#     """
#     if isinstance(geometry, (Polygon, MultiPolygon)):
#         qtmshape = mgrs.geo_to_qtmshape(geometry)
#         return set(mgrs.polygon_to_cells(qtmshape, resolution))
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")

# @sequential_deduplication
# def linetrace(geometry: MultiLineOrLine, resolution: int) -> Iterator[str]:
#     """mgrs.polyfill equivalent for shapely (Multi)LineString
#     Does not represent lines with duplicate sequential cells,
#     but cells may repeat non-sequentially to represent
#     self-intersections

#     Parameters
#     ----------
#     geometry : LineString or MultiLineString
#         Line to trace with mgrs cells
#     resolution : int
#         mgrs resolution of the tracing cells

#     Returns
#     -------
#     Set of mgrs addresses

#     Raises
#     ------
#     TypeError if geometry is not a LineString or a MultiLineString
#     """
#     if isinstance(geometry, MultiLineString):
#         # Recurse after getting component linestrings from the multiline
#         for line in map(lambda geom: linetrace(geom, resolution), geometry.geoms):
#             yield from line
#     elif isinstance(geometry, LineString):
#         coords = zip(geometry.coords, geometry.coords[1:])
#         while (vertex_pair := next(coords, None)) is not None:
#             i, j = vertex_pair
#             a = mgrs.latlng_to_cell(*i[::-1], resolution)
#             b = mgrs.latlng_to_cell(*j[::-1], resolution)
#             yield from mgrs.grid_path_cells(a, b)  # inclusive of a and b
#     else:
#         raise TypeError(f"Unknown type {type(geometry)}")
