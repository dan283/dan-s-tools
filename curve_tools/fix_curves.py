import bpy
import bmesh
from mathutils import Vector
import math

bl_info = {
    "name": "Cycles Curves Tools",
    "author": "Assistant",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > N-Panel > Cycles Curves",
    "description": "Tools for selecting and fixing cycles curves",
    "category": "Curve",
}

class CURVE_OT_select_cycles_curves(bpy.types.Operator):
    """Select all curve objects with cyclic splines"""
    bl_idname = "curve.select_cycles_curves"
    bl_label = "Select Cycles Curves"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'
    
    def execute(self, context):
        # Deselect all objects first
        bpy.ops.object.select_all(action='DESELECT')
        
        selected_curves = 0
        total_cyclic_splines = 0
        
        for obj in context.scene.objects:
            if obj.type == 'CURVE':
                curve = obj.data
                cyclic_count = 0
                
                for spline in curve.splines:
                    if spline.use_cyclic_u:
                        cyclic_count += 1
                
                if cyclic_count > 0:
                    obj.select_set(True)
                    selected_curves += 1
                    total_cyclic_splines += cyclic_count
        
        if selected_curves > 0:
            self.report({'INFO'}, f"Selected {selected_curves} curve objects with {total_cyclic_splines} cyclic splines")
        else:
            self.report({'INFO'}, "No curve objects with cyclic splines found")
        
        return {'FINISHED'}

class CURVE_OT_fix_cycles_curves(bpy.types.Operator):
    """Fix cycles curves by reordering points to connect to nearest neighbors"""
    bl_idname = "curve.fix_cycles_curves"
    bl_label = "Fix Cycles Curves"
    bl_options = {'REGISTER', 'UNDO'}
    
    process_all: bpy.props.BoolProperty(
        name="Process All Splines",
        description="Process all splines in the curve, not just selected ones",
        default=True
    )
    
    @classmethod
    def poll(cls, context):
        return any(obj.type == 'CURVE' for obj in context.selected_objects)
    
    def execute(self, context):
        # Get all selected curve objects
        selected_curves = [obj for obj in context.selected_objects if obj.type == 'CURVE']
        
        if not selected_curves:
            self.report({'WARNING'}, "No curve objects selected")
            return {'CANCELLED'}
        
        original_active = context.active_object
        original_mode = context.mode
        total_fixed_splines = 0
        processed_objects = 0
        
        # Process each selected curve object
        for obj in selected_curves:
            # Make this object active
            context.view_layer.objects.active = obj
            
            # Switch to object mode first, then to edit mode
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            
            # Select only this object
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            
            # Switch to edit mode
            bpy.ops.object.mode_set(mode='EDIT')
            
            curve = obj.data
            fixed_splines = 0
            
            for spline in curve.splines:
                # Process all splines if process_all is True, or only those with selected points
                should_process = self.process_all
                
                if not should_process:
                    # Check if this spline has selected points
                    if spline.type == 'BEZIER':
                        for point in spline.bezier_points:
                            if point.select_control_point:
                                should_process = True
                                break
                    else:  # NURBS or POLY
                        for point in spline.points:
                            if point.select:
                                should_process = True
                                break
                
                if should_process and len(self.get_spline_points(spline)) >= 3:
                    if self.fix_spline_order(spline):
                        fixed_splines += 1
            
            if fixed_splines > 0:
                processed_objects += 1
                total_fixed_splines += fixed_splines
            
            # Return to object mode
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Restore original selection and active object
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_curves:
            obj.select_set(True)
        
        if original_active:
            context.view_layer.objects.active = original_active
        
        # Restore original mode if possible
        if original_mode == 'EDIT_CURVE' and original_active and original_active.type == 'CURVE':
            bpy.ops.object.mode_set(mode='EDIT')
        
        if total_fixed_splines == 0:
            if self.process_all:
                self.report({'WARNING'}, f"No splines with 3+ points found in {len(selected_curves)} selected curves")
            else:
                self.report({'WARNING'}, "No splines were fixed. Select points in the splines you want to fix, or enable 'Process All Splines'")
        else:
            self.report({'INFO'}, f"Fixed {total_fixed_splines} splines in {processed_objects} curve objects")
        
        return {'FINISHED'}
    
    def get_spline_points(self, spline):
        """Get all points from a spline regardless of selection"""
        if spline.type == 'BEZIER':
            return list(spline.bezier_points)
        else:  # NURBS or POLY
            return list(spline.points)
    
    def fix_spline_order(self, spline):
        """Reorder points in a spline to connect nearest neighbors"""
        # Get all points and their data
        points_data = []
        
        if spline.type == 'BEZIER':
            for i, point in enumerate(spline.bezier_points):
                points_data.append({
                    'index': i,
                    'co': point.co.copy(),
                    'handle_left': point.handle_left.copy(),
                    'handle_right': point.handle_right.copy(),
                    'handle_left_type': point.handle_left_type,
                    'handle_right_type': point.handle_right_type,
                    'select_control_point': point.select_control_point,
                    'select_left_handle': point.select_left_handle,
                    'select_right_handle': point.select_right_handle
                })
        elif spline.type in ['NURBS', 'POLY']:
            for i, point in enumerate(spline.points):
                points_data.append({
                    'index': i,
                    'co': Vector((point.co[0], point.co[1], point.co[2])),
                    'weight': point.weight if spline.type == 'NURBS' else 1.0,
                    'select': point.select
                })
        
        if len(points_data) < 3:
            return False  # Need at least 3 points for a meaningful cycle
        
        # Order points by proximity
        ordered_data = self.order_points_by_proximity(points_data)
        
        # Apply the new order back to the spline
        if spline.type == 'BEZIER':
            for i, point_data in enumerate(ordered_data):
                point = spline.bezier_points[i]
                point.co = point_data['co']
                point.handle_left = point_data['handle_left']
                point.handle_right = point_data['handle_right']
                point.handle_left_type = point_data['handle_left_type']
                point.handle_right_type = point_data['handle_right_type']
                point.select_control_point = point_data['select_control_point']
                point.select_left_handle = point_data['select_left_handle']
                point.select_right_handle = point_data['select_right_handle']
        elif spline.type in ['NURBS', 'POLY']:
            for i, point_data in enumerate(ordered_data):
                point = spline.points[i]
                point.co = (point_data['co'].x, point_data['co'].y, point_data['co'].z, point_data['weight'])
                point.select = point_data['select']
        
        # Make sure the spline is cyclic
        spline.use_cyclic_u = True
        
        return True
    
    def order_points_by_proximity(self, points_data):
        """Order points to form a proper cycle based on proximity and shape analysis"""
        if len(points_data) < 3:
            return points_data
        
        # First, try angular sorting around centroid - this is most reliable
        angular_ordered = self.optimize_point_order(points_data)
        
        # If angular sorting fails or gives poor results, fall back to improved proximity
        if len(angular_ordered) < 3 or self.has_crossings(angular_ordered):
            # Use improved proximity algorithm with crossing detection
            proximity_ordered = self.proximity_with_crossing_avoidance(points_data)
            
            # Choose the better result
            if not self.has_crossings(proximity_ordered):
                return proximity_ordered
            elif not self.has_crossings(angular_ordered):
                return angular_ordered
            else:
                # Both have issues, choose the one with shorter total perimeter
                if self.calculate_perimeter(proximity_ordered) < self.calculate_perimeter(angular_ordered):
                    return proximity_ordered
                else:
                    return angular_ordered
        
        return angular_ordered
    
    def proximity_with_crossing_avoidance(self, points_data):
        """Improved proximity algorithm that tries to avoid crossings"""
        if len(points_data) < 3:
            return points_data
        
        # Start with the point that's most likely to be on the "edge" of the shape
        start_point = self.find_edge_point(points_data)
        ordered = [start_point]
        remaining = [p for p in points_data if p != start_point]
        
        while remaining:
            current_point = ordered[-1]
            best_point = None
            best_score = float('inf')
            
            for candidate in remaining:
                # Calculate multiple factors for choosing next point
                distance = (current_point['co'] - candidate['co']).length
                
                # Check if adding this point would create crossings
                crossing_penalty = 0
                if len(ordered) >= 2:
                    crossing_penalty = self.calculate_crossing_penalty(ordered, candidate, remaining)
                
                # Prefer points that maintain consistent direction
                direction_bonus = 0
                if len(ordered) >= 2:
                    direction_bonus = self.calculate_direction_consistency(ordered[-2:] + [candidate])
                
                # Combined score: distance + crossing penalty - direction bonus
                score = distance + crossing_penalty * 2.0 - direction_bonus * 0.5
                
                if score < best_score:
                    best_score = score
                    best_point = candidate
            
            if best_point:
                ordered.append(best_point)
                remaining.remove(best_point)
        
        return ordered
    
    def find_edge_point(self, points_data):
        """Find a point that's likely on the edge of the shape (leftmost, then bottommost)"""
        min_x = min(p['co'].x for p in points_data)
        leftmost_points = [p for p in points_data if abs(p['co'].x - min_x) < 0.001]
        
        if len(leftmost_points) == 1:
            return leftmost_points[0]
        else:
            # Among leftmost points, choose the bottommost
            return min(leftmost_points, key=lambda p: p['co'].y)
    
    def calculate_crossing_penalty(self, ordered_points, candidate, remaining):
        """Calculate penalty for potential line crossings"""
        if len(ordered_points) < 2:
            return 0
        
        penalty = 0
        current_pos = ordered_points[-1]['co']
        candidate_pos = candidate['co']
        
        # Check if the line from current to candidate crosses any existing edges
        for i in range(len(ordered_points) - 1):
            p1 = ordered_points[i]['co']
            p2 = ordered_points[i + 1]['co']
            
            if self.lines_intersect_2d(current_pos, candidate_pos, p1, p2):
                penalty += 10.0  # Heavy penalty for crossings
        
        return penalty
    
    def calculate_direction_consistency(self, last_three_points):
        """Calculate bonus for maintaining consistent turning direction"""
        if len(last_three_points) < 3:
            return 0
        
        p1, p2, p3 = [p['co'] for p in last_three_points]
        
        # Calculate cross product to determine turn direction
        v1 = p2 - p1
        v2 = p3 - p2
        cross = v1.x * v2.y - v1.y * v2.x
        
        # Positive cross product means left turn, negative means right turn
        # Consistent direction gets a bonus
        return abs(cross) * 0.1
    
    def lines_intersect_2d(self, p1, p2, p3, p4):
        """Check if two line segments intersect in 2D (using X,Y coordinates)"""
        def ccw(A, B, C):
            return (C.y - A.y) * (B.x - A.x) > (B.y - A.y) * (C.x - A.x)
        
        # Check if segments are the same or share endpoints
        if (p1 - p3).length < 0.001 or (p1 - p4).length < 0.001 or \
           (p2 - p3).length < 0.001 or (p2 - p4).length < 0.001:
            return False
        
        return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)
    
    def has_crossings(self, points_data):
        """Check if the current point order creates crossing edges"""
        if len(points_data) < 4:
            return False
        
        positions = [p['co'] for p in points_data]
        
        # Check each edge against all non-adjacent edges
        for i in range(len(positions)):
            p1 = positions[i]
            p2 = positions[(i + 1) % len(positions)]
            
            # Check against all non-adjacent edges
            for j in range(i + 2, len(positions)):
                if j == len(positions) - 1 and i == 0:
                    continue  # Skip the closing edge comparison
                
                p3 = positions[j]
                p4 = positions[(j + 1) % len(positions)]
                
                if self.lines_intersect_2d(p1, p2, p3, p4):
                    return True
        
        return False
    
    def calculate_perimeter(self, points_data):
        """Calculate total perimeter of the point sequence"""
        if len(points_data) < 2:
            return 0
        
        total = 0
        positions = [p['co'] for p in points_data]
        
        for i in range(len(positions)):
            p1 = positions[i]
            p2 = positions[(i + 1) % len(positions)]
            total += (p1 - p2).length
        
        return total
    
    def optimize_point_order(self, points_data):
        """Optimize point order using angular sorting around centroid"""
        if len(points_data) < 4:
            return points_data
        
        # Calculate centroid
        centroid = Vector((0, 0, 0))
        for point in points_data:
            centroid += point['co']
        centroid /= len(points_data)
        
        # Determine the best plane for projection
        if len(points_data) >= 3:
            # Use PCA-like approach to find the best plane
            best_normal = self.find_best_plane_normal(points_data, centroid)
            
            if best_normal.length > 0.001:
                # Create a coordinate system on the plane
                # Use the vector from centroid to first point as one axis
                first_vec = (points_data[0]['co'] - centroid).normalized()
                # Remove component along normal to project onto plane
                u_axis = (first_vec - first_vec.dot(best_normal) * best_normal).normalized()
                v_axis = best_normal.cross(u_axis).normalized()
                
                def angle_in_plane(point):
                    vec = point['co'] - centroid
                    # Project onto the plane
                    u_comp = vec.dot(u_axis)
                    v_comp = vec.dot(v_axis)
                    return math.atan2(v_comp, u_comp)
                
                sorted_points = sorted(points_data, key=angle_in_plane)
            else:
                # Fall back to XY plane
                def angle_from_centroid(point):
                    vec = point['co'] - centroid
                    return math.atan2(vec.y, vec.x)
                
                sorted_points = sorted(points_data, key=angle_from_centroid)
        else:
            # Simple XY plane sorting
            def angle_from_centroid(point):
                vec = point['co'] - centroid
                return math.atan2(vec.y, vec.x)
            
            sorted_points = sorted(points_data, key=angle_from_centroid)
        
        return sorted_points
    
    def find_best_plane_normal(self, points_data, centroid):
        """Find the normal of the best-fit plane using a simplified PCA approach"""
        if len(points_data) < 3:
            return Vector((0, 0, 1))
        
        # Calculate covariance matrix components
        xx = xy = xz = yy = yz = zz = 0
        
        for point in points_data:
            vec = point['co'] - centroid
            xx += vec.x * vec.x
            xy += vec.x * vec.y
            xz += vec.x * vec.z
            yy += vec.y * vec.y
            yz += vec.y * vec.z
            zz += vec.z * vec.z
        
        # Try different candidate normals and see which gives the most planar result
        candidates = [
            Vector((1, 0, 0)),  # YZ plane
            Vector((0, 1, 0)),  # XZ plane  
            Vector((0, 0, 1)),  # XY plane
        ]
        
        best_normal = Vector((0, 0, 1))
        min_variance = float('inf')
        
        for normal in candidates:
            # Calculate variance of distances from plane
            variance = 0
            for point in points_data:
                vec = point['co'] - centroid
                dist_from_plane = abs(vec.dot(normal))
                variance += dist_from_plane * dist_from_plane
            
            if variance < min_variance:
                min_variance = variance
                best_normal = normal
        
        # Also try the normal from the first three points
        if len(points_data) >= 3:
            v1 = points_data[1]['co'] - points_data[0]['co']
            v2 = points_data[2]['co'] - points_data[0]['co']
            cross_normal = v1.cross(v2)
            
            if cross_normal.length > 0.001:
                cross_normal = cross_normal.normalized()
                
                # Test this normal too
                variance = 0
                for point in points_data:
                    vec = point['co'] - centroid
                    dist_from_plane = abs(vec.dot(cross_normal))
                    variance += dist_from_plane * dist_from_plane
                
                if variance < min_variance:
                    best_normal = cross_normal
        
        return best_normal

class VIEW3D_PT_cycles_curves_panel(bpy.types.Panel):
    """N-Panel for Cycles Curves tools"""
    bl_label = "Cycles Curves"
    bl_idname = "VIEW3D_PT_cycles_curves"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Cycles Curves"
    
    def draw(self, context):
        layout = self.layout
        
        # Select Cycles Curves works in Object mode
        col = layout.column(align=True)
        col.operator("curve.select_cycles_curves", text="Select Cycles Curves")
        
        # Fix Cycles Curves needs curve objects selected
        if any(obj.type == 'CURVE' for obj in context.selected_objects):
            col.operator("curve.fix_cycles_curves", text="Fix Cycles Curves")
            
            # Show info about selected curves
            selected_curves = [obj for obj in context.selected_objects if obj.type == 'CURVE']
            layout.separator()
            
            if len(selected_curves) == 1:
                curve = selected_curves[0].data
                layout.label(text=f"Active: {selected_curves[0].name}")
                layout.label(text=f"Splines: {len(curve.splines)}")
                cyclic_count = sum(1 for s in curve.splines if s.use_cyclic_u)
                layout.label(text=f"Cyclic: {cyclic_count}")
            else:
                layout.label(text=f"Selected: {len(selected_curves)} curves")
                total_splines = sum(len(obj.data.splines) for obj in selected_curves)
                total_cyclic = sum(sum(1 for s in obj.data.splines if s.use_cyclic_u) for obj in selected_curves)
                layout.label(text=f"Total splines: {total_splines}")
                layout.label(text=f"Total cyclic: {total_cyclic}")
            
        else:
            # Disable the fix button if no curves are selected
            col.enabled = False
            col.operator("curve.fix_cycles_curves", text="Fix Cycles Curves")
            layout.separator()
            layout.label(text="Select curve objects")
            layout.label(text="to fix cycles")

# Registration
classes = [
    CURVE_OT_select_cycles_curves,
    CURVE_OT_fix_cycles_curves,
    VIEW3D_PT_cycles_curves_panel,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
