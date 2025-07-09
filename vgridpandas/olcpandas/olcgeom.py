from typing import Union, Set
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from vgrid.generator.olcgrid import generate_grid, refine_cell
from vgrid.utils import olc
from vgrid.conversion.dggscompact import olc_compact
from vgridpandas.utils.geom import check_predicate

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]


def validate_olc_resolution(resolution):
    """
    Validate that OLC resolution is in the valid range [2,4,6,8,10,11,12,13,14,15].

    Args:
        resolution: Resolution value to validate

    Returns:
        int: Validated resolution value

    Raises:
        ValueError: If resolution is not in range [2,4,6,8,10,11,12,13,14,15]
        TypeError: If resolution is not an integer
    """
    if not isinstance(resolution, int):
        raise TypeError(
            f"Resolution must be an integer, got {type(resolution).__name__}"
        )

    if resolution not in [2, 4, 6, 8, 10, 11, 12, 13, 14, 15]:
        raise ValueError(
            f"Resolution must be in range [2,4,6,8,10,11,12,13,14,15], got {resolution}"
        )

    return resolution


def cell2boundary(olc_id: str) -> Polygon:
    """olc.olc_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    olc_id : str
        OLC ID to convert to a boundary

    Returns
    -------
    Polygon representing the olc cell boundary
    """
    # Base octahedral face definitions
    coord = olc.decode(olc_id)
    # Create the bounding box coordinates for the polygon
    min_lat, min_lon = coord.latitudeLo, coord.longitudeLo
    max_lat, max_lon = coord.latitudeHi, coord.longitudeHi
    # Define the polygon based on the bounding box
    cell_polygon = Polygon(
        [
            [min_lon, min_lat],  # Bottom-left corner
            [max_lon, min_lat],  # Bottom-right corner
            [max_lon, max_lat],  # Top-right corner
            [min_lon, max_lat],  # Top-left corner
            [min_lon, min_lat],  # Closing the polygon (same as the first point)
        ]
    )
    return cell_polygon


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
        base_cells = generate_grid(base_resolution)
        seed_cells = []
        for base_cell in base_cells["features"]:
            base_cell_poly = Polygon(base_cell["geometry"]["coordinates"][0])
            if poly.intersects(base_cell_poly):
                seed_cells.append(base_cell)
        refined_features = []
        for seed_cell in seed_cells:
            seed_cell_poly = Polygon(seed_cell["geometry"]["coordinates"][0])
            if seed_cell_poly.contains(poly) and resolution == base_resolution:
                refined_features.append(seed_cell)
            else:
                refined_features.extend(
                    refine_cell(
                        seed_cell_poly.bounds, base_resolution, resolution, poly
                    )
                )
        resolution_features = [
            refined_feature
            for refined_feature in refined_features
            if refined_feature["properties"]["resolution"] == resolution
        ]
        seen_olc_ids = set()
        for resolution_feature in resolution_features:
            olc_id = resolution_feature["properties"]["olc"]
            if olc_id not in seen_olc_ids:
                cell_geom = Polygon(resolution_feature["geometry"]["coordinates"][0])
                if not check_predicate(cell_geom, poly, predicate):
                    continue
                olc_ids.append(olc_id)  # Only append the OLC code string
                seen_olc_ids.add(olc_id)
    if compact:
        return olc_compact(olc_ids)
    return olc_ids


def polyfill(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """olc.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        olc resolution of the filling cells

    Returns
    -------
    Set of olc ids

    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(poly2olc(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(poly2olc(geometry, resolution, predicate="intersect", compact=False))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
