def check_predicate(cell_polygon, input_geometry, predicate=None):
    """
    Determine whether to keep an H3 cell based on its relationship with the input geometry.

    Args:
        cell_polygon: Shapely Polygon representing the H3 cell
        input_geometry: Shapely geometry (Polygon, LineString, etc.)
        predicate (str or int): Spatial predicate to apply:
            String values:
                None or "intersects": intersects (default)
                "within": within
                "centroid_within": centroid_within
                "largest_overlap": intersection >= 50% of cell area
            Integer values (for backward compatibility):
                None or 0: intersects (default)
                1: within
                2: centroid_within
                3: intersection >= 50% of cell area

    Returns:
        bool: True if cell should be kept, False otherwise
    """
    try:
        # Handle string predicates
        if isinstance(predicate, str):
            predicate_lower = predicate.lower()
            if predicate_lower in ["intersects", "intersect"]:
                return cell_polygon.intersects(input_geometry)
            elif predicate_lower == "within":
                return cell_polygon.within(input_geometry)
            elif predicate_lower in ["centroid_within", "centroid"]:
                return cell_polygon.centroid.within(input_geometry)
            elif predicate_lower in ["largest_overlap", "overlap", "majority"]:
                # intersection >= 50% of cell area
                if cell_polygon.intersects(input_geometry):
                    intersection_geom = cell_polygon.intersection(input_geometry)
                    if intersection_geom and intersection_geom.area > 0:
                        intersection_area = intersection_geom.area
                        cell_area = cell_polygon.area
                        return (intersection_area / cell_area) >= 0.5
                return False
            else:
                # Unknown string predicate, default to intersects
                return cell_polygon.intersects(input_geometry)

        # Handle integer predicates (backward compatibility)
        elif isinstance(predicate, int):
            if predicate == 0:
                # Default: intersects
                return cell_polygon.intersects(input_geometry)
            elif predicate == 1:
                # within
                return cell_polygon.within(input_geometry)
            elif predicate == 2:
                # centroid_within
                return cell_polygon.centroid.within(input_geometry)
            elif predicate == 3:
                # intersection >= 50% of cell area
                if cell_polygon.intersects(input_geometry):
                    intersection_geom = cell_polygon.intersection(input_geometry)
                    if intersection_geom and intersection_geom.area > 0:
                        intersection_area = intersection_geom.area
                        cell_area = cell_polygon.area
                        return (intersection_area / cell_area) >= 0.5
                return False      
        else:
            # None or other types, default to intersects
            return True
    except Exception as e:
        print(f"Error checking predicate: {e}")
        return False
