from typing import Union, Set
from shapely.geometry import (
    Point,
    MultiPoint,
    Polygon,
    MultiPolygon,
    LineString,
    MultiLineString,
)
import a5
import geopandas as gpd
from vgridpandas.utils.geom import check_predicate
from vgrid.utils.io import validate_a5_resolution
from vgrid.conversion.dggs2geo.a52geo import a52geo as a5_to_geo
from vgrid.conversion.dggscompact.a5compact import a5compact
MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]
MultiPointOrPoint = Union[Point, MultiPoint]

def poly2a5(geometry, resolution, predicate=None, compact=False):
    """
    Convert polygon geometries (Polygon, MultiPolygon) to A5 grid cells.

    Args:
        resolution (int): A5 resolution level [0..29]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

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
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        min_lng, min_lat, max_lng, max_lat = poly.bounds        
        # Calculate longitude and latitude width based on resolution
        if resolution == 1:
            lon_width = 20
            lat_width = 20
        elif resolution == 2:
            lon_width = 10
            lat_width = 10
        elif resolution == 3:
            lon_width = 5
            lat_width = 5
        elif resolution > 3:
            base_width = 5  # at resolution 3
            factor = 0.5 ** (resolution - 3)
            lon_width = base_width * factor
            lat_width = base_width * factor
        else:
            # For resolution 0, use larger width
            lon_width = 40
            lat_width = 40
        
        # Generate longitude and latitude arrays
        longitudes = []
        latitudes = []
        
        lon = min_lng
        while lon < max_lng:
            longitudes.append(lon)
            lon += lon_width
        
        lat = min_lat
        while lat < max_lat:
            latitudes.append(lat)
            lat += lat_width
        
        seen_a5_hex = set()  # Track unique A5 hex codes
        
        for lon in longitudes:
            for lat in latitudes:
                min_lon = lon
                min_lat = lat
                max_lon = lon + lon_width
                max_lat = lat + lat_width
                
                # Calculate centroid
                centroid_lat = (min_lat + max_lat) / 2
                centroid_lon = (min_lon + max_lon) / 2
                
                try:
                    # Convert centroid to A5 cell ID using direct A5 functions
                    cell_id = a5.lonlat_to_cell([centroid_lon, centroid_lat], resolution)
                    cell_polygon = a5_to_geo(cell_id)
                    
                    a5_hex = a5.u64_to_hex(cell_id)
                    
                    # Only process if this A5 hex code hasn't been seen before
                    if a5_hex not in seen_a5_hex:
                        seen_a5_hex.add(a5_hex)                        
                        if check_predicate(cell_polygon, poly, predicate):
                            a5_hexes.append(a5_hex)
                except Exception as e:
                    # Skip cells that can't be processed
                    continue
    
    if compact and a5_hexes:
        # Create a GeoDataFrame with A5 hex codes and their geometries
        a5_data = []
        for a5_hex in a5_hexes:
            try:
                # Convert A5 hex to geometry
                cell_id = a5.hex_to_u64(a5_hex)
                geometry = a5_to_geo(cell_id)
                a5_data.append({"a5": a5_hex, "geometry": geometry})
            except Exception as e:
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


def polyfill(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """a5.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        A5 resolution of the filling cells

    Returns
    -------
    Set of A5 Tokens

    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(poly2a5(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(poly2a5(geometry, resolution, predicate='intersect', compact=False))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")

