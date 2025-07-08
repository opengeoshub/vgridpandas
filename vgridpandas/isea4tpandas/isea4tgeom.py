from typing import Union, Set, Iterator
from shapely.geometry import box, Polygon, MultiPolygon, LineString, MultiLineString
from shapely.wkt import loads
import platform
from vgrid.conversion.dggscompact import isea4t_compact
from vgridpandas.utils.geom import check_predicate

MultiPolyOrPoly = Union[Polygon, MultiPolygon]
MultiLineOrLine = Union[LineString, MultiLineString]

if platform.system() == "Windows":
    from vgrid.utils.eaggr.enums.shape_string_format import ShapeStringFormat
    from vgrid.utils.eaggr.eaggr import Eaggr
    from vgrid.utils.eaggr.shapes.dggs_cell import DggsCell
    from vgrid.utils.eaggr.enums.model import Model
    from vgrid.generator.isea4tgrid import (
        isea4t_cell_to_polygon,
        isea4t_res_accuracy_dict,
        fix_isea4t_antimeridian_cells,
        get_isea4t_children_cells_within_bbox,
    )
    from vgrid.generator.isea4tgrid import fix_isea4t_wkt,fix_isea4t_antimeridian_cells
    isea4t_dggs = Eaggr(Model.ISEA4T)


def validate_isea4t_resolution(resolution):
    """
    Validate that ISEA4T resolution is in the valid range [0..27].

    Args:
        resolution: Resolution value to validate

    Returns:
        int: Validated resolution value

    Raises:
        ValueError: If resolution is not in range [0..27]
        TypeError: If resolution is not an integer
    """
    if not isinstance(resolution, int):
        raise TypeError(
            f"Resolution must be an integer, got {type(resolution).__name__}"
        )

    if resolution < 0 or resolution > 27:
        raise ValueError(f"Resolution must be in range [0..27], got {resolution}")

    return resolution


def cell2boundary(isea4t_id: str) -> Polygon:
    """isea4t.isea4t_to_geo_boundary equivalent for shapely

    Parameters
    ----------
    isea4t_id : str
        ISEA4T ID to convert to a boundary

    Returns
    -------
    Polygon representing the isea4t cell boundary
    """
    # Base octahedral face definitions
    if platform.system() == "Windows":
        cell_to_shape = isea4t_dggs.convert_dggs_cell_outline_to_shape_string(
            DggsCell(isea4t_id), ShapeStringFormat.WKT
        )
        cell_to_shape_fixed = loads(fix_isea4t_wkt(cell_to_shape))
        if cell_to_shape_fixed.is_empty:
            return Polygon()
        if (
            isea4t_id.startswith("00")
            or isea4t_id.startswith("09")
            or isea4t_id.startswith("14")
            or isea4t_id.startswith("04")
            or isea4t_id.startswith("19")
        ):
            cell_to_shape_fixed = fix_isea4t_antimeridian_cells(cell_to_shape_fixed)
        
        cell_polygon = Polygon(list(cell_to_shape_fixed.exterior.coords))
        return cell_polygon
   

def poly2isea4t(geometry: MultiPolyOrPoly, resolution: int, predicate: str = None, compact: bool = False) -> Set[str]:
    """
    Convert polygon geometries (Polygon, MultiPolygon) to isea4t grid cells.

    Args:
        resolution (int): ISEA4T resolution level [0..28]
        geometry (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): Polygon geometry to convert
        predicate (str, optional): Spatial predicate to apply ('intersect', 'within', 'centroid_within', 'largest_overlap')

    Returns:
        list: List of isea4t ids intersecting the polygon

    Example:
        >>> from shapely.geometry import Polygon
        >>> poly = Polygon([(-122.5, 37.7), (-122.3, 37.7), (-122.3, 37.9), (-122.5, 37.9)])
        >>> cells = poly2isea4t(poly, 10, predicate="intersect", compact=True)
        >>> len(cells) > 0
        True
    """
    if platform.system() == "Windows":
        resolution = validate_isea4t_resolution(resolution)
        isea4t_ids = []
        if isinstance(geometry, (Polygon, LineString)):
            polys = [geometry]
        elif isinstance(geometry, (MultiPolygon, MultiLineString)):
            polys = list(geometry.geoms)
        else:
            return []

        for poly in polys:
            accuracy = isea4t_res_accuracy_dict.get(resolution)
            bounding_box = box(*poly.bounds)
            bounding_box_wkt = bounding_box.wkt
            shapes = isea4t_dggs.convert_shape_string_to_dggs_shapes(
                bounding_box_wkt, ShapeStringFormat.WKT, accuracy
            )
            shape = shapes[0]
            bbox_cells = shape.get_shape().get_outer_ring().get_cells()
            bounding_cell = isea4t_dggs.get_bounding_dggs_cell(bbox_cells)
            bounding_child_cells = get_isea4t_children_cells_within_bbox(
                isea4t_dggs, bounding_cell.get_cell_id(), bounding_box, resolution
            )
            if compact:
                bounding_child_cells = isea4t_compact(isea4t_dggs, bounding_child_cells)
            for child in bounding_child_cells:
                isea4t_cell = DggsCell(child)
                cell_polygon = isea4t_cell_to_polygon(isea4t_dggs, isea4t_cell)
                isea4t_id = isea4t_cell.get_cell_id()
                if isea4t_id.startswith(("00", "09", "14", "04", "19")):
                    cell_polygon = fix_isea4t_antimeridian_cells(cell_polygon)
                if check_predicate(cell_polygon, poly, predicate):
                   isea4t_ids.append(isea4t_id)
        return isea4t_ids

def polyfill(
    geometry: MultiPolyOrPoly,
    resolution: int,
    predicate: str = None,
    compact: bool = False,
) -> Set[str]:
    """isea4t.polyfill accepting a shapely (Multi)Polygon or (Multi)LineString

    Parameters
    ----------
    geometry : Polygon or Multipolygon
        Polygon to fill
    resolution : int
        isea4t resolution of the filling cells

    Returns
    -------
    Set of isea4t ids

    Raises
    ------
    TypeError if geometry is not a Polygon or MultiPolygon
    """
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return set(poly2isea4t(geometry, resolution, predicate, compact))
    elif isinstance(geometry, (LineString, MultiLineString)):
        return set(poly2isea4t(geometry, resolution, predicate='intersect', compact=False))
    else:
        raise TypeError(f"Unknown type {type(geometry)}")


