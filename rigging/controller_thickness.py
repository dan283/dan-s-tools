bl_info = {
    "name": "Thick Bones Overlay",
    "author": "Your Name", 
    "version": (1, 0, 3),
    "blender": (3, 0, 0),
    "location": "3D Viewport > Overlays > Armature (Pose Mode)",
    "description": "Display selected bones with customizable thickness overlay for custom shapes in pose mode",
    "category": "Rigging",
}

import bpy
import bmesh
import gpu
from gpu_extras.batch import batch_for_shader
from bpy.props import FloatProperty, BoolProperty
from bpy.types import Panel, Operator
import mathutils
from mathutils import Vector, Matrix
from bpy.app.handlers import persistent


# Global variables
draw_handler = None
bone_batches = {}  # Dictionary to store batches for each bone with its color
shader = None
is_drawing = False
auto_update_enabled = True
update_timer = None
last_selection_hash = None
last_pose_hash = None
last_object_name = None
last_mode = None

# Performance optimization: cache shader
_cached_shader = None


def get_shader():
    """Get cached shader for better performance"""
    global _cached_shader
    if _cached_shader is None:
        _cached_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    return _cached_shader


def get_selection_hash():
    """Get a hash of the current bone selection for comparison"""
    context = bpy.context
    
    if not context.active_object or context.active_object.type != 'ARMATURE':
        return None
    
    if context.mode != 'POSE':
        return None
    
    try:
        armature = context.active_object
        selected_bones = []
        active_bone_name = None
        
        # Get selected bone names
        for bone in armature.pose.bones:
            if bone.bone.select:
                selected_bones.append(bone.name)
        
        # Get active bone
        if armature.data.bones.active:
            active_bone_name = armature.data.bones.active.name
        
        # Include enable_all state in hash
        scene = context.scene
        enable_all = scene.thick_bones_props.enable_all
        
        return hash((tuple(sorted(selected_bones)), active_bone_name, enable_all))
    except Exception as e:
        print(f"Selection hash error: {e}")
        return None


def get_pose_hash():
    """Get a lightweight hash of the current pose for comparison"""
    context = bpy.context
    
    if not context.active_object or context.active_object.type != 'ARMATURE':
        return None
    
    if context.mode != 'POSE':
        return None
    
    try:
        armature = context.active_object
        scene = context.scene
        enable_all = scene.thick_bones_props.enable_all
        
        # Create hash based on bone transforms (selected or all based on enable_all)
        bone_transforms = []
        for bone in armature.pose.bones:
            should_include = enable_all and bone.custom_shape or (bone.bone.select and bone.custom_shape)
            if should_include:
                # Get bone matrix for transform comparison
                matrix_tuple = tuple(tuple(row) for row in bone.matrix)
                # Include custom shape transform properties
                shape_props = (
                    tuple(bone.custom_shape_scale_xyz),
                    tuple(bone.custom_shape_rotation_euler),
                    tuple(bone.custom_shape_translation)
                )
                bone_transforms.append((bone.name, matrix_tuple, shape_props))
        
        # Include object transform
        obj_matrix = tuple(tuple(row) for row in armature.matrix_world)
        
        return hash((tuple(bone_transforms), obj_matrix, enable_all))
    except Exception as e:
        print(f"Pose hash error: {e}")
        return None


def is_valid_context():
    """Check if the current context is valid for thick bones display"""
    context = bpy.context
    
    # Check if we have an active object and it's an armature
    if not context.active_object or context.active_object.type != 'ARMATURE':
        return False
    
    # Check if we're in pose mode
    if context.mode != 'POSE':
        return False
    
    # Check if the object still exists in the scene
    if context.active_object.name not in bpy.data.objects:
        return False
    
    return True


def should_auto_enable():
    """Check if we should auto-enable when entering pose mode"""
    context = bpy.context
    scene = context.scene
    
    # Check if auto-enable is turned on and we're in valid context
    return (hasattr(scene, 'thick_bones_props') and 
            scene.thick_bones_props.auto_enable and 
            is_valid_context())


def get_bone_color(bone, armature_obj):
    """Get the color from BoneColor properties, else default theme colors"""
    context = bpy.context
    
    try:
        armature_data = armature_obj.data
        pose_bone = armature_obj.pose.bones.get(bone.name)
        active_bone = armature_data.bones.active
        is_active = active_bone and bone == active_bone
        
        # Check pose bone color first
        if pose_bone and hasattr(pose_bone, 'color') and pose_bone.color.palette != 'DEFAULT':
            if pose_bone.color.palette == 'CUSTOM':
                # Use custom color
                base_color = pose_bone.color.custom.normal[:3]
                if is_active:
                    return tuple(min(1.0, c * 1.3) for c in base_color)
                else:
                    return base_color
            else:
                # Use theme color palette
                theme_color = get_bone_color_palette(pose_bone.color.palette, is_active)
                if theme_color:
                    return theme_color
        
        # Fallback to armature bone color
        if hasattr(bone, 'color') and bone.color.palette != 'DEFAULT':
            if bone.color.palette == 'CUSTOM':
                # Use custom color
                base_color = bone.color.custom.normal[:3]
                if is_active:
                    return tuple(min(1.0, c * 1.3) for c in base_color)
                else:
                    return base_color
            else:
                # Use theme color palette
                theme_color = get_bone_color_palette(bone.color.palette, is_active)
                if theme_color:
                    return theme_color
        
        # Final fallback: default theme colors based on bone state
        theme = context.preferences.themes[0]
        
        if is_active:
            return theme.view_3d.bone_pose_active[:3]  # Active bone color
        elif bone.select:
            return theme.view_3d.bone_pose[:3]  # Selected bone color
        else:
            return theme.view_3d.bone_solid[:3]  # Normal bone color
            
    except Exception as e:
        print(f"Error getting bone color for {bone.name}: {e}")
        # Hard fallback to simple colors
        armature_data = armature_obj.data
        active_bone = armature_data.bones.active
        
        if active_bone and bone == active_bone:
            return (1.0, 1.0, 0.0)  # Yellow for active
        elif bone.select:
            return (0.0, 0.8, 1.0)  # Light blue for selected
        else:
            return (0.5, 0.5, 0.5)  # Gray for normal

def get_collection_color_set(color_set, is_active=False):
    """Get color from bone collection color set"""
    collection_colors = {
        'THEME01': (0.8, 0.2, 0.2),    # Red
        'THEME02': (0.2, 0.8, 0.2),    # Green  
        'THEME03': (0.2, 0.2, 0.8),    # Blue
        'THEME04': (0.8, 0.8, 0.2),    # Yellow
        'THEME05': (0.8, 0.2, 0.8),    # Magenta
        'THEME06': (0.2, 0.8, 0.8),    # Cyan
        'THEME07': (0.8, 0.5, 0.2),    # Orange
        'THEME08': (0.5, 0.2, 0.8),    # Purple
        'THEME09': (0.5, 0.8, 0.2),    # Light Green
        'THEME10': (0.8, 0.2, 0.5),    # Pink
        'THEME11': (0.2, 0.5, 0.8),    # Light Blue
        'THEME12': (0.5, 0.5, 0.5),    # Gray
        'THEME13': (0.7, 0.7, 0.7),    # Light Gray
        'THEME14': (0.3, 0.3, 0.3),    # Dark Gray
        'THEME15': (0.7, 0.4, 0.2),    # Brown
        'THEME16': (0.4, 0.7, 0.2),    # Lime
        'THEME17': (0.2, 0.4, 0.7),    # Navy
        'THEME18': (0.7, 0.2, 0.4),    # Maroon
        'THEME19': (0.6, 0.3, 0.7),    # Violet
        'THEME20': (0.3, 0.7, 0.6),    # Teal
    }
    
    color = collection_colors.get(color_set, (0.5, 0.5, 0.5))
    
    if is_active:
        # Brighten active bone
        return tuple(min(1.0, c * 1.3) for c in color)
    
    return color


def get_bone_color_palette(palette, is_active=False):
    """Get color from bone color palette"""
    palette_colors = {
        'THEME01': (1.0, 0.0, 0.0),    # Red
        'THEME02': (0.0, 1.0, 0.0),    # Green
        'THEME03': (0.0, 0.0, 1.0),    # Blue
        'THEME04': (1.0, 1.0, 0.0),    # Yellow
        'THEME05': (1.0, 0.0, 1.0),    # Magenta
        'THEME06': (0.0, 1.0, 1.0),    # Cyan
        'THEME07': (1.0, 0.5, 0.0),    # Orange
        'THEME08': (0.5, 0.0, 1.0),    # Purple
        'THEME09': (0.5, 1.0, 0.0),    # Light Green
        'THEME10': (1.0, 0.0, 0.5),    # Pink
        'THEME11': (0.0, 0.5, 1.0),    # Light Blue
        'THEME12': (0.5, 0.5, 0.5),    # Gray
        'THEME13': (0.8, 0.8, 0.8),    # Light Gray
        'THEME14': (0.2, 0.2, 0.2),    # Dark Gray
        'THEME15': (0.8, 0.4, 0.2),    # Brown
        'THEME16': (0.4, 0.8, 0.2),    # Lime
        'THEME17': (0.2, 0.4, 0.8),    # Navy
        'THEME18': (0.8, 0.2, 0.4),    # Maroon
        'THEME19': (0.6, 0.3, 0.8),    # Violet
        'THEME20': (0.3, 0.8, 0.6),    # Teal
    }
    
    color = palette_colors.get(palette, (0.5, 0.5, 0.5))
    
    if is_active:
        # Brighten active bone
        return tuple(min(1.0, c * 1.3) for c in color)
    
    return color


def is_bone_collection_visible(bone, armature_obj):
    """Check if bone is visible based on bone collection visibility"""
    try:
        # Check if bone collections exist (Blender 3.0+)
        if not hasattr(bone, 'collections'):
            return True
        
        # If bone has no collections, it's visible by default
        if not bone.collections:
            return True
        
        # Check if any of the bone's collections are visible
        for collection in bone.collections:
            if hasattr(collection, 'is_visible') and collection.is_visible:
                return True
        
        # If no collections are visible, bone is hidden
        return False
        
    except Exception as e:
        print(f"Error checking bone collection visibility for {bone.name}: {e}")
        return True  # Default to visible on error


def get_custom_shape_wireframe_lines(bone, armature_obj):
    """Generate wireframe lines for a bone's custom shape using exact Blender transforms"""
    lines = []
    
    try:
        pose_bone = armature_obj.pose.bones[bone.name]
        
        # Only process bones with custom shapes
        if not pose_bone.custom_shape:
            return lines
        
        # Check if bone is visible (bone collection visibility)
        if not is_bone_collection_visible(bone, armature_obj):
            return lines
        
        # Use custom shape mesh
        custom_shape = pose_bone.custom_shape
        
        # Handle both mesh objects and empties used as custom shapes
        if custom_shape.type == 'MESH':
            # Create temporary bmesh from custom shape mesh
            bm = bmesh.new()
            bm.from_mesh(custom_shape.data)
            
            # FIXED: Calculate the exact transform matrix that matches Blender's custom shape rendering
            
            # Get armature object's world matrix
            armature_matrix = armature_obj.matrix_world
            
            # Get the transform bone matrix (or pose bone matrix if no custom transform)
            if pose_bone.custom_shape_transform:
                transform_bone = armature_obj.pose.bones[pose_bone.custom_shape_transform.name]
                bone_matrix = transform_bone.matrix
            else:
                bone_matrix = pose_bone.matrix
            
            # Create the custom shape transformation matrix
            # This follows Blender's exact transformation order and scaling
            
            # 1. Create scale matrix from custom_shape_scale_xyz
            # NOTE: Blender applies bone length scaling here, which we need to account for
            bone_length = bone.length if bone.length > 0 else 1.0
            scale_xyz = pose_bone.custom_shape_scale_xyz
            
            # Apply bone length scaling to the custom shape scale (this is the key fix!)
            effective_scale = Vector((
                scale_xyz[0] * bone_length,
                scale_xyz[1] * bone_length, 
                scale_xyz[2] * bone_length
            ))
            
            scale_matrix = Matrix.Diagonal((*effective_scale, 1.0))
            
            # 2. Create rotation matrix from custom_shape_rotation_euler
            rotation_matrix = pose_bone.custom_shape_rotation_euler.to_matrix().to_4x4()
            
            # 3. Create translation matrix from custom_shape_translation
            translation_matrix = Matrix.Translation(pose_bone.custom_shape_translation)
            
            # 4. Combine all transforms in the correct order
            # Order: Translation * Rotation * Scale (applied right to left)
            shape_local_matrix = translation_matrix @ rotation_matrix @ scale_matrix
            
            # 5. Apply to world space
            final_matrix = armature_matrix @ bone_matrix @ shape_local_matrix
            
            # Transform all vertices and create edge lines
            for edge in bm.edges:
                v1_world = final_matrix @ edge.verts[0].co
                v2_world = final_matrix @ edge.verts[1].co
                lines.extend([v1_world, v2_world])
            
            bm.free()
            
        elif custom_shape.type == 'EMPTY':
            # Handle empties used as custom shapes
            # Get the empty's wireframe representation based on its display type
            empty_lines = get_empty_wireframe_lines(custom_shape, bone, armature_obj, pose_bone)
            lines.extend(empty_lines)
    
    except Exception as e:
        print(f"Error generating custom shape wireframe for {bone.name}: {e}")
    
    return lines


def get_empty_wireframe_lines(empty_obj, bone, armature_obj, pose_bone):
    """Generate wireframe lines for empty objects used as custom shapes"""
    lines = []
    
    try:
        # Get armature object's world matrix
        armature_matrix = armature_obj.matrix_world
        
        # Get the transform bone matrix (or pose bone matrix if no custom transform)
        if pose_bone.custom_shape_transform:
            transform_bone = armature_obj.pose.bones[pose_bone.custom_shape_transform.name]
            bone_matrix = transform_bone.matrix
        else:
            bone_matrix = pose_bone.matrix
        
        # Create the custom shape transformation matrix
        bone_length = bone.length if bone.length > 0 else 1.0
        scale_xyz = pose_bone.custom_shape_scale_xyz
        
        # Apply bone length scaling
        effective_scale = Vector((
            scale_xyz[0] * bone_length,
            scale_xyz[1] * bone_length, 
            scale_xyz[2] * bone_length
        ))
        
        scale_matrix = Matrix.Diagonal((*effective_scale, 1.0))
        rotation_matrix = pose_bone.custom_shape_rotation_euler.to_matrix().to_4x4()
        translation_matrix = Matrix.Translation(pose_bone.custom_shape_translation)
        
        shape_local_matrix = translation_matrix @ rotation_matrix @ scale_matrix
        final_matrix = armature_matrix @ bone_matrix @ shape_local_matrix
        
        # Generate wireframe based on empty display type
        empty_size = empty_obj.empty_display_size
        
        if empty_obj.empty_display_type == 'PLAIN_AXES':
            # Three axes lines
            axes_lines = [
                Vector((0, 0, 0)), Vector((empty_size, 0, 0)),  # X axis
                Vector((0, 0, 0)), Vector((0, empty_size, 0)),  # Y axis  
                Vector((0, 0, 0)), Vector((0, 0, empty_size))   # Z axis
            ]
            
        elif empty_obj.empty_display_type == 'ARROWS':
            # Arrow wireframe
            axes_lines = []
            # X arrow
            axes_lines.extend([Vector((0, 0, 0)), Vector((empty_size, 0, 0))])
            axes_lines.extend([Vector((empty_size, 0, 0)), Vector((empty_size * 0.8, empty_size * 0.1, 0))])
            axes_lines.extend([Vector((empty_size, 0, 0)), Vector((empty_size * 0.8, -empty_size * 0.1, 0))])
            # Y arrow
            axes_lines.extend([Vector((0, 0, 0)), Vector((0, empty_size, 0))])
            axes_lines.extend([Vector((0, empty_size, 0)), Vector((empty_size * 0.1, empty_size * 0.8, 0))])
            axes_lines.extend([Vector((0, empty_size, 0)), Vector((-empty_size * 0.1, empty_size * 0.8, 0))])
            # Z arrow  
            axes_lines.extend([Vector((0, 0, 0)), Vector((0, 0, empty_size))])
            axes_lines.extend([Vector((0, 0, empty_size)), Vector((0, empty_size * 0.1, empty_size * 0.8))])
            axes_lines.extend([Vector((0, 0, empty_size)), Vector((0, -empty_size * 0.1, empty_size * 0.8))])
            
        elif empty_obj.empty_display_type == 'SINGLE_ARROW':
            # Single Z-axis arrow
            axes_lines = [
                Vector((0, 0, 0)), Vector((0, 0, empty_size)),
                Vector((0, 0, empty_size)), Vector((empty_size * 0.1, 0, empty_size * 0.8)),
                Vector((0, 0, empty_size)), Vector((-empty_size * 0.1, 0, empty_size * 0.8)),
                Vector((0, 0, empty_size)), Vector((0, empty_size * 0.1, empty_size * 0.8)),
                Vector((0, 0, empty_size)), Vector((0, -empty_size * 0.1, empty_size * 0.8))
            ]
            
        elif empty_obj.empty_display_type == 'CIRCLE':
            # Circle in XY plane
            import math
            axes_lines = []
            segments = 16
            for i in range(segments):
                angle1 = (i / segments) * 2 * math.pi
                angle2 = ((i + 1) / segments) * 2 * math.pi
                v1 = Vector((math.cos(angle1) * empty_size, math.sin(angle1) * empty_size, 0))
                v2 = Vector((math.cos(angle2) * empty_size, math.sin(angle2) * empty_size, 0))
                axes_lines.extend([v1, v2])
                
        elif empty_obj.empty_display_type == 'CUBE':
            # Cube wireframe
            s = empty_size
            vertices = [
                Vector((-s, -s, -s)), Vector((s, -s, -s)), Vector((s, s, -s)), Vector((-s, s, -s)),
                Vector((-s, -s, s)), Vector((s, -s, s)), Vector((s, s, s)), Vector((-s, s, s))
            ]
            # Cube edges
            edges = [
                (0, 1), (1, 2), (2, 3), (3, 0),  # Bottom face
                (4, 5), (5, 6), (6, 7), (7, 4),  # Top face
                (0, 4), (1, 5), (2, 6), (3, 7)   # Vertical edges
            ]
            axes_lines = []
            for edge in edges:
                axes_lines.extend([vertices[edge[0]], vertices[edge[1]]])
                
        elif empty_obj.empty_display_type == 'SPHERE':
            # Sphere wireframe (3 circles)
            import math
            axes_lines = []
            segments = 16
            # XY circle
            for i in range(segments):
                angle1 = (i / segments) * 2 * math.pi
                angle2 = ((i + 1) / segments) * 2 * math.pi
                v1 = Vector((math.cos(angle1) * empty_size, math.sin(angle1) * empty_size, 0))
                v2 = Vector((math.cos(angle2) * empty_size, math.sin(angle2) * empty_size, 0))
                axes_lines.extend([v1, v2])
            # XZ circle
            for i in range(segments):
                angle1 = (i / segments) * 2 * math.pi
                angle2 = ((i + 1) / segments) * 2 * math.pi
                v1 = Vector((math.cos(angle1) * empty_size, 0, math.sin(angle1) * empty_size))
                v2 = Vector((math.cos(angle2) * empty_size, 0, math.sin(angle2) * empty_size))
                axes_lines.extend([v1, v2])
            # YZ circle
            for i in range(segments):
                angle1 = (i / segments) * 2 * math.pi
                angle2 = ((i + 1) / segments) * 2 * math.pi
                v1 = Vector((0, math.cos(angle1) * empty_size, math.sin(angle1) * empty_size))
                v2 = Vector((0, math.cos(angle2) * empty_size, math.sin(angle2) * empty_size))
                axes_lines.extend([v1, v2])
        else:
            # Default to plain axes for unknown types
            axes_lines = [
                Vector((0, 0, 0)), Vector((empty_size, 0, 0)),
                Vector((0, 0, 0)), Vector((0, empty_size, 0)),
                Vector((0, 0, 0)), Vector((0, 0, empty_size))
            ]
        
        # Transform all points to world space
        for i in range(0, len(axes_lines), 2):
            v1_world = final_matrix @ axes_lines[i]
            v2_world = final_matrix @ axes_lines[i + 1]
            lines.extend([v1_world, v2_world])
        
    except Exception as e:
        print(f"Error generating empty wireframe for {bone.name}: {e}")
    
    return lines


def get_selected_bone_data():
    """Get wireframe lines and colors for bones with custom shapes (selected or all based on enable_all)"""
    context = bpy.context
    
    if not is_valid_context():
        return {}
    
    armature_obj = context.active_object
    armature_data = armature_obj.data
    
    bone_data = {}
    
    try:
        # Get enable_all setting from scene properties
        scene = context.scene
        enable_all = scene.thick_bones_props.enable_all
        
        # Process bones with custom shapes (selected or all based on enable_all)
        for bone in armature_data.bones:
            should_process = enable_all or bone.select
            
            if should_process:
                pose_bone = armature_obj.pose.bones[bone.name]
                if pose_bone.custom_shape:
                    # Check bone collection visibility
                    if not is_bone_collection_visible(bone, armature_obj):
                        continue
                        
                    bone_lines = get_custom_shape_wireframe_lines(bone, armature_obj)
                    if bone_lines:
                        bone_color = get_bone_color(bone, armature_obj)
                        bone_data[bone.name] = {
                            'lines': bone_lines,
                            'color': bone_color
                        }
        
        return bone_data
        
    except Exception as e:
        print(f"Error getting bone data: {e}")
        return {}


def auto_update_check():
    """Timer function to check for selection changes and pose modifications"""
    global last_selection_hash, last_pose_hash, last_object_name, last_mode
    global auto_update_enabled, is_drawing
    
    try:
        if not auto_update_enabled or not is_drawing:
            return 0.1
        
        context = bpy.context
        
        # Check if context is still valid
        if not is_valid_context():
            cleanup_thick_bones()
            tag_redraw_all()
            return None  # Stop timer
        
        # Check if overlays are disabled
        space_data = get_3d_view_space()
        if space_data and not space_data.overlay.show_overlays:
            return 0.1  # Continue checking but don't update
        
        current_object_name = context.active_object.name
        current_mode = context.mode
        current_selection_hash = get_selection_hash()
        current_pose_hash = get_pose_hash()
        
        # Check for changes
        needs_update = False
        
        if (current_selection_hash != last_selection_hash or
            current_pose_hash != last_pose_hash or
            current_object_name != last_object_name or
            current_mode != last_mode):
            
            needs_update = True
            
            # Update stored values
            last_selection_hash = current_selection_hash
            last_pose_hash = current_pose_hash
            last_object_name = current_object_name
            last_mode = current_mode
        
        if needs_update:
            update_bone_display()
            tag_redraw_all()
        
        return 0.1  # Continue timer
        
    except Exception as e:
        print(f"Auto-update error: {e}")
        return 0.1


def get_3d_view_space():
    """Get the 3D view space data"""
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            return area.spaces.active
    return None


def tag_redraw_all():
    """Tag all 3D viewports for redraw"""
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def start_auto_update():
    """Start the auto-update timer"""
    global update_timer, last_selection_hash, last_pose_hash, last_object_name, last_mode
    
    # Stop existing timer if running
    stop_auto_update()
    
    # Set initial values
    last_selection_hash = get_selection_hash()
    last_pose_hash = get_pose_hash()
    last_object_name = bpy.context.active_object.name if bpy.context.active_object else None
    last_mode = bpy.context.mode
    
    # Start timer with reasonable interval
    if bpy.app.timers.is_registered(auto_update_check):
        bpy.app.timers.unregister(auto_update_check)
    
    update_timer = bpy.app.timers.register(auto_update_check, first_interval=0.1)


def stop_auto_update():
    """Stop the auto-update timer"""
    global update_timer
    
    if update_timer is not None:
        try:
            if bpy.app.timers.is_registered(auto_update_check):
                bpy.app.timers.unregister(auto_update_check)
        except Exception as e:
            print(f"Error stopping timer: {e}")
        update_timer = None


def draw_thick_bones():
    """Draw thick lines for selected bones with custom shapes"""
    global bone_batches, shader, is_drawing
    
    if not is_drawing or not is_valid_context():
        return
    
    # Check if overlays are enabled
    space_data = get_3d_view_space()
    if space_data and not space_data.overlay.show_overlays:
        return
    
    try:
        # Get settings from scene properties
        scene = bpy.context.scene
        thickness = scene.thick_bones_props.line_thickness
        
        # Use cached shader
        shader = get_shader()
        
        # Enable line smooth and blend
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(thickness)
        
        # Draw each bone batch with its color
        for bone_name, batch_data in bone_batches.items():
            if batch_data['batch']:
                shader.bind()
                color = batch_data['color']
                shader.uniform_float("color", (color[0], color[1], color[2], 1.0))
                batch_data['batch'].draw(shader)
        
        # Restore state
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')
        
    except Exception as e:
        print(f"Draw error: {e}")


def update_bone_display():
    """Update the bone batches with current selection"""
    global bone_batches, shader
    
    # Check if context is valid
    if not is_valid_context():
        bone_batches = {}
        return
    
    try:
        # Get current selected bone data
        bone_data = get_selected_bone_data()
        
        # Use cached shader
        shader = get_shader()
        
        # Clear old batches
        bone_batches = {}
        
        # Create batch for each bone
        for bone_name, data in bone_data.items():
            if data['lines']:
                batch = batch_for_shader(
                    shader, 'LINES',
                    {"pos": data['lines']}
                )
                bone_batches[bone_name] = {
                    'batch': batch,
                    'color': data['color']
                }
            
    except Exception as e:
        print(f"Error updating bone display: {e}")
        bone_batches = {}


def enable_thick_bones():
    """Enable thick bones display"""
    global draw_handler, is_drawing, auto_update_enabled
    
    if is_drawing:
        return
    
    update_bone_display()
    draw_handler = bpy.types.SpaceView3D.draw_handler_add(
        draw_thick_bones, (), 'WINDOW', 'POST_VIEW'
    )
    is_drawing = True
    
    # Set up auto-update using scene property
    scene = bpy.context.scene
    auto_update_enabled = scene.thick_bones_props.auto_update
    if auto_update_enabled:
        start_auto_update()
    
    tag_redraw_all()


@persistent
def mode_change_handler(scene, depsgraph):
    """FIXED: Handler for mode changes - auto-enable when entering pose mode"""
    global is_drawing
    
    context = bpy.context
    
    # If we're entering pose mode and auto-enable is on, enable thick bones
    if should_auto_enable() and not is_drawing:
        enable_thick_bones()
    
    # If we're leaving pose mode or context is invalid, cleanup
    elif is_drawing and not is_valid_context():
        cleanup_thick_bones()
        tag_redraw_all()


@persistent
def selection_change_handler(scene, depsgraph):
    """Handler specifically for selection changes"""
    global is_drawing, auto_update_enabled
    
    if not is_drawing or not auto_update_enabled:
        return
        
    if is_valid_context():
        # Force update on selection change
        update_bone_display()
        tag_redraw_all()


class POSE_OT_toggle_thick_bones(Operator):
    """Toggle thick bone display for selected bones with custom shapes"""
    bl_idname = "pose.toggle_thick_bones"
    bl_label = "Toggle Thick Bones"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        global draw_handler, is_drawing, auto_update_enabled
        
        if not context.active_object or context.active_object.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select an armature object")
            return {'CANCELLED'}
        
        if context.mode != 'POSE':
            self.report({'ERROR'}, "Please enter Pose Mode")
            return {'CANCELLED'}
        
        if is_drawing:
            # Disable thick bones
            cleanup_thick_bones()
            self.report({'INFO'}, "Thick bones disabled")
        else:
            # Enable thick bones
            enable_thick_bones()
            
            total_bones = len(bone_batches)
            if total_bones > 0:
                self.report({'INFO'}, f"Thick bones enabled for {total_bones} custom shapes")
            else:
                scene = context.scene
                if scene.thick_bones_props.enable_all:
                    self.report({'WARNING'}, "Thick bones enabled - no custom shapes found on armature")
                else:
                    self.report({'WARNING'}, "Thick bones enabled - select bones with custom shapes to see them")
        
        return {'FINISHED'}


class POSE_OT_update_thick_bones(Operator):
    """Update thick bone display with current selection"""
    bl_idname = "pose.update_thick_bones"
    bl_label = "Update Selection"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        global is_drawing
        
        if not is_drawing:
            self.report({'INFO'}, "Thick bones not enabled")
            return {'CANCELLED'}
        
        if not is_valid_context():
            self.report({'ERROR'}, "Invalid context for thick bones")
            cleanup_thick_bones()
            return {'CANCELLED'}
        
        # Update the bone display
        update_bone_display()
        
        total_bones = len(bone_batches)
        if total_bones > 0:
            self.report({'INFO'}, f"Updated thick bones for {total_bones} custom shapes")
        else:
            scene = context.scene
            if scene.thick_bones_props.enable_all:
                self.report({'WARNING'}, "No custom shapes found on armature")
            else:
                self.report({'WARNING'}, "No bones with custom shapes selected")
        
        # Refresh viewport
        tag_redraw_all()
        return {'FINISHED'}


class ThickBonesProperties(bpy.types.PropertyGroup):
    line_thickness: FloatProperty(
        name="Line Thickness",
        default=3.0,
        min=1.0,
        max=20.0,
        description="Thickness of the wireframe lines",
        update=lambda self, context: force_redraw_if_active()
    )
    
    auto_update: BoolProperty(
        name="Auto Update",
        default=True,
        update=lambda self, context: update_auto_update_setting(self, context)
    )
    
    auto_enable: BoolProperty(
        name="Auto Enable",
        default=False,
        description="Automatically enable thick bones when entering pose mode"
    )
    
    enable_all: BoolProperty(
        name="Enable All",
        default=False,
        description="Display thick bones for all bones with custom shapes (not just selected ones)",
        update=lambda self, context: force_update_if_active()
    )


def force_redraw_if_active():
    """Force redraw if thick bones are active"""
    global is_drawing
    if is_drawing:
        tag_redraw_all()


def force_update_if_active():
    """Force update and redraw if thick bones are active"""
    global is_drawing
    if is_drawing:
        update_bone_display()
        tag_redraw_all()


def update_auto_update_setting(self, context):
    """Handle auto-update setting changes"""
    global auto_update_enabled, is_drawing
    
    auto_update_enabled = self.auto_update
    
    if auto_update_enabled and is_drawing:
        start_auto_update()
    elif not auto_update_enabled:
        stop_auto_update()


class VIEW3D_PT_thick_bones_overlay(Panel):
    """Thick Bones Overlay Panel in Armature section"""
    bl_label = "Thick Bones"
    bl_idname = "VIEW3D_PT_thick_bones_overlay"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_parent_id = "VIEW3D_PT_overlay_bones"
    
    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'ARMATURE' and
                context.mode == 'POSE')
    
    def draw_header(self, context):
        layout = self.layout
        layout.prop(context.scene.thick_bones_props, "auto_update", text="")
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.thick_bones_props
        
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        # Main toggle
        col = layout.column()
        
        if is_drawing:
            col.operator("pose.toggle_thick_bones", text="Disable Thick Bones", icon='BONE_DATA')
        else:
            col.operator("pose.toggle_thick_bones", text="Enable Thick Bones", icon='BONE_DATA')
        
        # Enable All checkbox
        col.separator()
        col.prop(props, "enable_all")
        
        # Settings (only when enabled)
        if is_drawing:
            col.separator()
            col.prop(props, "line_thickness")
            
            # Manual update button (only when auto-update is off)
            if not props.auto_update:
                col.separator()
                col.operator("pose.update_thick_bones", text="Update Selection", icon='FILE_REFRESH')
        
        # Auto-enable option (always visible)
        col.separator()
        col.prop(props, "auto_enable")


# Clean up function
def cleanup_thick_bones():
    """Clean up the drawing handler and auto-update timer"""
    global draw_handler, is_drawing, bone_batches
    
    if draw_handler:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(draw_handler, 'WINDOW')
        except Exception as e:
            print(f"Error removing draw handler: {e}")
        draw_handler = None
    
    # Stop auto-update timer
    stop_auto_update()
    
    # Clear batches
    bone_batches = {}
    
    is_drawing = False


# Registration
classes = (
    POSE_OT_toggle_thick_bones,
    POSE_OT_update_thick_bones,
    ThickBonesProperties,
    VIEW3D_PT_thick_bones_overlay,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.thick_bones_props = bpy.props.PointerProperty(
        type=ThickBonesProperties
    )
    
    # Register handlers
    bpy.app.handlers.depsgraph_update_post.append(mode_change_handler)
    bpy.app.handlers.depsgraph_update_post.append(selection_change_handler)

def unregister():
    cleanup_thick_bones()
    
    # Unregister handlers
    handlers_to_remove = [mode_change_handler, selection_change_handler]
    for handler in handlers_to_remove:
        if handler in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(handler)
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    if hasattr(bpy.types.Scene, 'thick_bones_props'):
        del bpy.types.Scene.thick_bones_props

if __name__ == "__main__":
    register()
