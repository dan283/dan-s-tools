import bpy
import mathutils
from mathutils import Vector
import itertools

def reorder_closest_chain(points):
    """Given 3 points, return them reordered so each connects to its nearest neighbor in sequence."""
    best_order = None
    min_total_dist = float('inf')

    for perm in itertools.permutations(points):
        dist = (perm[0] - perm[1]).length + (perm[1] - perm[2]).length
        if dist < min_total_dist:
            best_order = perm
            min_total_dist = dist

    return best_order

def fix_curve_endpoints(obj):
    if obj.type != 'CURVE':
        return

    for spline in obj.data.splines:
        if spline.type != 'POLY' or spline.use_cyclic_u:
            continue  # Skip non-poly or cyclic curves

        num_points = len(spline.points)
        if num_points < 6:
            continue  # Not enough points to fix both ends

        # Convert points to Vectors
        points = [Vector((p.co.x, p.co.y, p.co.z)) for p in spline.points]

        # Fix start 3
        start_fixed = reorder_closest_chain(points[:3])

        # Fix end 3
        end_fixed = reorder_closest_chain(points[-3:])

        # Combine new full point list
        new_points = list(start_fixed) + points[3:-3] + list(end_fixed)

        # Apply new order back to spline
        for i, p in enumerate(spline.points):
            vec = new_points[i]
            p.co = (vec.x, vec.y, vec.z, 1.0)

def main():
    for obj in bpy.context.selected_objects:
        fix_curve_endpoints(obj)

main()
