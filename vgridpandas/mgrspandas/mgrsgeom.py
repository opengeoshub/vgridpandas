from typing import Union, Set, Iterator
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.wkt import loads
from shapely.ops import transform
from vgrid.utils import mgrs
import os, json
from shapely.geometry import shape

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

def validate_mgrs_resolution(resolution: int) -> int:
    """
    Validate that mgrs resolution is in the valid range [0..5].

    Args:
        resolution: Resolution value to validate

    Returns:
        int: Validated resolution value

    Raises:
        ValueError: If resolution is not in range [0..5]
        TypeError: If resolution is not an integer
    """
    if not isinstance(resolution, int):
        raise TypeError(
            f"Resolution must be an integer, got {type(resolution).__name__}"
        )

    if resolution < 0 or resolution > 5:
        raise ValueError(f"Resolution must be in range [0..5], got {resolution}")

    return resolution

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
