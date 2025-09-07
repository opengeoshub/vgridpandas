from typing import Union, Set
from shapely.geometry import box, Polygon, MultiPolygon, LineString, MultiLineString
import platform
from vgrid.utils.geometry import check_predicate
from vgrid.utils.io import validate_isea3h_resolution
from vgrid.utils.geometry import isea3h_cell_to_polygon
from vgrid.generator.isea3hgrid import get_isea3h_children_cells_within_bbox

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

if platform.system() == "Windows":
    from vgrid.dggs.eaggr.eaggr import Eaggr
    from vgrid.dggs.eaggr.shapes.dggs_cell import DggsCell
    from vgrid.dggs.eaggr.enums.model import Model
    from vgrid.dggs.eaggr.enums.shape_string_format import ShapeStringFormat
    from vgrid.utils.constants import ISEA3H_RES_ACCURACY_DICT

    isea3h_dggs = Eaggr(Model.ISEA3H)


def poly2isea3h(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to isea3h grid cells.

    Args:
        resolution (int): isea3h resolution level [0..28]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of isea3h ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2isea3h(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """
    if platform.system() == "Windows":
        resolution = validate_isea3h_resolution(resolution)
        isea3h_ids = []
        if isinstance(geometry, (Polygon, LineString)):
            polys = [geometry]
        elif isinstance(geometry, (MultiPolygon, MultiLineString)):
            polys = list(geometry.geoms)
        else:
            return []

        for poly in polys:
            accuracy = ISEA3H_RES_ACCURACY_DICT.get(resolution)
            bounding_box = box(*poly.bounds)
            bounding_box_wkt = bounding_box.wkt
            shapes = isea3h_dggs.convert_shape_string_to_dggs_shapes(
                bounding_box_wkt, ShapeStringFormat.WKT, accuracy
            )
            shape = shapes[0]
            bbox_cells = shape.get_shape().get_outer_ring().get_cells()
            bounding_cell = isea3h_dggs.get_bounding_dggs_cell(bbox_cells)
            bounding_child_cells = get_isea3h_children_cells_within_bbox(
                bounding_cell.get_cell_id(), bounding_box, resolution
            )
            for child in bounding_child_cells:
                isea3h_cell = DggsCell(child)
                cell_polygon = isea3h_cell_to_polygon(isea3h_cell)
                if check_predicate(cell_polygon, poly, predicate):
                    isea3h_ids.append(isea3h_cell.get_cell_id())
        return isea3h_ids


def polyfill(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """isea3h.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        isea3h resolution of the filling cells

    Returns
    -------
    Set of isea3h ids

    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(poly2isea3h(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(
            poly2isea3h(geometry, resolution, predicate="intersect", compact=False)
        )
    else:
        raise TypeError(f"Unknown type {type(geometry)}")
