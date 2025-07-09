from typing import Union, Set, Iterator
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, box
from vgrid.utils.qtm import constructGeometry, qtm_id_to_facet, divideFacet
from vgridpandas.utils.geom import check_predicate
from vgrid.conversion.dggscompact import qtm_compact

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

p90_n180, p90_n90, p90_p0, p90_p90, p90_p180 = (
    (90.0, -180.0),
    (90.0, -90.0),
    (90.0, 0.0),
    (90.0, 90.0),
    (90.0, 180.0),
)
p0_n180, p0_n90, p0_p0, p0_p90, p0_p180 = (
    (0.0, -180.0),
    (0.0, -90.0),
    (0.0, 0.0),
    (0.0, 90.0),
    (0.0, 180.0),
)
n90_n180, n90_n90, n90_p0, n90_p90, n90_p180 = (
    (-90.0, -180.0),
    (-90.0, -90.0),
    (-90.0, 0.0),
    (-90.0, 90.0),
    (-90.0, 180.0),
)


initial_facets = [
                    [p0_n180, p0_n90, p90_n90, p90_n180, p0_n180, True],
                    [p0_n90, p0_p0, p90_p0, p90_n90, p0_n90, True],
                    [p0_p0, p0_p90, p90_p90, p90_p0, p0_p0, True],
                    [p0_p90, p0_p180, p90_p180, p90_p90, p0_p90, True],
                    [n90_n180, n90_n90, p0_n90, p0_n180, n90_n180, False],
                    [n90_n90, n90_p0, p0_p0, p0_n90, n90_n90, False],
                    [n90_p0, n90_p90, p0_p90, p0_p0, n90_p0, False],
                    [n90_p90, n90_p180, p0_p180, p0_p90, n90_p90, False],
                ]

def validate_qtm_resolution(resolution: int) -> int:
    """
    Validate that QTM resolution is in the valid range [1..24].

    Args:
        resolution: Resolution value to validate

    Returns:
        int: Validated resolution value

    Raises:
        ValueError: If resolution is not in range [1..24]
        TypeError: If resolution is not an integer
    """
    if not isinstance(resolution, int):
        raise TypeError(
            f"Resolution must be an integer, got {type(resolution).__name__}"
        )

    if resolution < 1 or resolution > 24:
        raise ValueError(f"Resolution must be in range [1..24], got {resolution}")

    return resolution

def cell2boundary(qtm_id: str) -> Polygon:
    """qtm.qtm_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    qtm_id : str
        QTM ID to convert to a boundary

    Returns
    -------
    Polygon representing the qtm cell boundary
    """
    # Base octahedral face definitions
    facet = qtm_id_to_facet(qtm_id)
    cell_polygon = constructGeometry(facet)
    return cell_polygon

def poly2qtm(geometry: MultiPolyOrPoly, resolution: int, predicate: str = None, compact: bool = False) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to QTM cells.

    Args:
        resolution (int): QTM resolution level [1..24]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of qtm ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2qtm(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """

    resolution = validate_qtm_resolution(resolution)
    qtm_ids = []
    if isinstance(geometry, (Polygon, LineString)):
        polys = [geometry]
    elif isinstance(geometry, (MultiPolygon, MultiLineString)):
        polys = list(geometry.geoms)
    else:
        return []

    for poly in polys:
        level_facets = {}
        QTMID = {}
        for lvl in range(resolution):
            level_facets[lvl] = []
            QTMID[lvl] = []
            if lvl == 0:               
                for i, facet in enumerate(initial_facets):
                    QTMID[0].append(str(i + 1))
                    level_facets[0].append(facet)
                    facet_geom = constructGeometry(facet)
                    if Polygon(facet_geom).intersects(poly) and resolution == 1:
                        qtm_id = QTMID[0][i]
                        qtm_ids.append(qtm_id)
                        return qtm_ids
            else:
                for i, pf in enumerate(level_facets[lvl - 1]):
                    subdivided_facets = divideFacet(pf)
                    for j, subfacet in enumerate(subdivided_facets):
                        subfacet_geom = constructGeometry(subfacet)
                        if Polygon(subfacet_geom).intersects(poly):
                            new_id = QTMID[lvl - 1][i] + str(j)
                            QTMID[lvl].append(new_id)
                            level_facets[lvl].append(subfacet)
                            if lvl == resolution - 1:
                                if not check_predicate(
                                    Polygon(subfacet_geom), poly, predicate
                                ):
                                    continue
                                qtm_ids.append(new_id)
    if compact:
        return qtm_compact(qtm_ids)
    return qtm_ids

def polyfill(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """qtm.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        QTM resolution of the filling cells

    Returns
    -------
    Set of QTM IDs
    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(poly2qtm(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(poly2qtm(geometry, resolution, predicate='intersect', compact=False))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")

