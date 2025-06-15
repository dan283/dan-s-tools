bl_info = {
    "name": "Thick Bones Overlay",
    "author": "Your Name", 
    "version": (1, 0, 9),
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
import math


# Global variables
draw_handler = None
bone_batches = {}
shader = None
is_drawing = False
_cached_shader = None
_last_selection_state = None
_last_transform_state = None
_last_overlay_state = None


def get_shader():
    """Get cached shader for better performance"""
    global _cached_shader
    if _cached_shader is None:
        _cached_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    return _cached_shader


def is_valid_context():
    """Check if the current context is valid for thick bones display"""
    context = bpy.context
    
    if not context.active_object or context.active_object.type != 'ARMATURE':
        return False
    
    if context.mode != 'POSE':
        return False
    
    if context.active_object.name not in bpy.data.objects:
        return False
    
    return True


def should_display_in_front():
    """Check if armature should display in front"""
    context = bpy.context
    if not context.active_object:
        return False
    
    armature_obj = context.active_object
    return armature_obj.show_in_front


def are_overlays_enabled():
    """Check if overlays are enabled in any 3D viewport"""
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            space_data = area.spaces.active
            if space_data and space_data.overlay.show_overlays:
                return True
    return False


def get_bone_color(bone, armature_obj):
    """Get the color from BoneColor properties, else default theme colors"""
    context = bpy.context
    
    try:
        armature_data = armature_obj.data
        pose_bone = armature_obj.pose.bones.get(bone.name)
        active_bone = armature_data.bones.active
        is_active = active_bone and bone == active_bone
        
        # Check pose bone color first
        if pose_bone and hasattr(pose_bone, 'color'):
            if pose_bone.color.palette != 'DEFAULT':
                if pose_bone.color.palette == 'CUSTOM':
                    base_color = pose_bone.color.custom.normal[:3]
                    if is_active:
                        return tuple(min(1.0, c * 1.3) for c in base_color)
                    else:
                        return base_color
                else:
                    theme_color = get_bone_color_palette(pose_bone.color.palette, is_active)
                    if theme_color:
                        return theme_color
        
        # Fallback to armature bone color
        if hasattr(bone, 'color'):
            if bone.color.palette != 'DEFAULT':
                if bone.color.palette == 'CUSTOM':
                    base_color = bone.color.custom.normal[:3]
                    if is_active:
                        return tuple(min(1.0, c * 1.3) for c in base_color)
                    else:
                        return base_color
                else:
                    theme_color = get_bone_color_palette(bone.color.palette, is_active)
                    if theme_color:
                        return theme_color
        
        # Check bone collections for color
        if hasattr(bone, 'collections') and bone.collections:
            for collection in bone.collections:
                if hasattr(collection, 'color_set') and collection.color_set != 'DEFAULT':
                    collection_color = get_collection_color_set(collection.color_set, is_active)
                    if collection_color:
                        return collection_color
        
        # Final fallback: default theme colors
        theme = context.preferences.themes[0]
        
        if is_active:
            return theme.view_3d.bone_pose_active[:3]
        elif bone.select:
            return theme.view_3d.bone_pose[:3]
        else:
            return theme.view_3d.bone_solid[:3]
            
    except Exception:
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
        'THEME01': (0.957, 0.043, 0.059),    # Red
        'THEME02': (0.949, 0.431, 0.008),    # Orange  
        'THEME03': (0.345, 0.710, 0.047),    # Green
        'THEME04': (0.0, 0.502, 1.0),        # Blue
        'THEME05': (0.776, 0.247, 0.408),    # Purple
        'THEME06': (1.0, 0.0, 0.753),        # Pink/Magenta
        'THEME07': (0.0, 0.753, 0.753),      # Teal/Cyan
        'THEME08': (0.424, 0.525, 0.584),    # Dark Gray
        'THEME09': (0.914, 0.765, 0.196),    # Yellow
        'THEME10': (0.286, 0.298, 0.325),    # White
        'THEME11': (0.612, 0.255, 0.753),    # Magenta
        'THEME12': (0.486, 0.694, 0.137),    # Light Yellow-Green
        'THEME13': (0.659, 0.694, 0.675),    # Pale Green
        'THEME14': (0.541, 0.341, 0.086),    # Orange
        'THEME15': (0.110, 0.263, 0.039),    # Forest Green
        'THEME16': (0.0, 0.0, 0.0),          # Black
        'THEME17': (0.0, 0.0, 0.0),          # Black
        'THEME18': (0.0, 0.0, 0.0),          # Black
        'THEME19': (0.0, 0.0, 0.0),          # Black
        'THEME20': (0.0, 0.0, 0.0),          # Black
    }
    
    color = collection_colors.get(color_set, (0.5, 0.5, 0.5))
    
    if is_active:
        return tuple(min(1.0, c * 1.3) for c in color)
    
    return color


def get_bone_color_palette(palette, is_active=False):
    """Get color from bone color palette"""
    palette_colors = {
        'THEME01': (0.957, 0.043, 0.059),    # Red
        'THEME02': (0.949, 0.431, 0.008),    # Orange  
        'THEME03': (0.345, 0.710, 0.047),    # Green
        'THEME04': (0.0, 0.502, 1.0),        # Blue
        'THEME05': (0.776, 0.247, 0.408),    # Purple
        'THEME06': (1.0, 0.0, 0.753),        # Pink/Magenta
        'THEME07': (0.0, 0.753, 0.753),      # Teal/Cyan
        'THEME08': (0.424, 0.525, 0.584),    # Dark Gray
        'THEME09': (0.914, 0.765, 0.196),    # Yellow
        'THEME10': (0.286, 0.298, 0.325),    # White
        'THEME11': (0.612, 0.255, 0.753),    # Magenta
        'THEME12': (0.486, 0.694, 0.137),    # Light Yellow-Green
        'THEME13': (0.659, 0.694, 0.675),    # Pale Green
        'THEME14': (0.541, 0.341, 0.086),    # Orange
        'THEME15': (0.110, 0.263, 0.039),    # Forest Green
        'THEME16': (0.0, 0.0, 0.0),          # Black
        'THEME17': (0.0, 0.0, 0.0),          # Black
        'THEME18': (0.0, 0.0, 0.0),          # Black
        'THEME19': (0.0, 0.0, 0.0),          # Black
        'THEME20': (0.0, 0.0, 0.0),          # Black
    }
    
    color = palette_colors.get(palette, (0.5, 0.5, 0.5))
    
    if is_active:
        return tuple(min(1.0, c * 1.3) for c in color)
    
    return color


def is_bone_collection_visible(bone, armature_obj):
    """Check if bone is visible based on bone collection visibility"""
    try:
        if not hasattr(bone, 'collections'):
            return True
        
        if not bone.collections:
            return True
        
        for collection in bone.collections:
            if hasattr(collection, 'is_visible') and collection.is_visible:
                return True
        
        return False
        
    except Exception:
        return True


def get_custom_shape_wireframe_lines(bone, armature_obj):
    """Generate wireframe lines for a bone's custom shape"""
    lines = []
    
    try:
        pose_bone = armature_obj.pose.bones[bone.name]
        
        if not pose_bone.custom_shape:
            return lines
        
        if not is_bone_collection_visible(bone, armature_obj):
            return lines
        
        custom_shape = pose_bone.custom_shape
        
        if custom_shape.type == 'MESH':
            # Create temporary bmesh from custom shape mesh
            bm = bmesh.new()
            bm.from_mesh(custom_shape.data)
            
            # Calculate transform matrix
            armature_matrix = armature_obj.matrix_world
            
            if pose_bone.custom_shape_transform:
                transform_bone = armature_obj.pose.bones[pose_bone.custom_shape_transform.name]
                bone_matrix = transform_bone.matrix
            else:
                bone_matrix = pose_bone.matrix
            
            # Create the custom shape transformation matrix
            bone_length = bone.length if bone.length > 0 else 1.0
            scale_xyz = pose_bone.custom_shape_scale_xyz
            
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
            
            # Transform all vertices and create edge lines
            for edge in bm.edges:
                v1_world = final_matrix @ edge.verts[0].co
                v2_world = final_matrix @ edge.verts[1].co
                lines.extend([v1_world, v2_world])
            
            bm.free()
            
        elif custom_shape.type == 'EMPTY':
            empty_lines = get_empty_wireframe_lines(custom_shape, bone, armature_obj, pose_bone)
            lines.extend(empty_lines)
    
    except Exception as e:
        print(f"Error generating custom shape wireframe for {bone.name}: {e}")
    
    return lines


def get_empty_wireframe_lines(empty_obj, bone, armature_obj, pose_bone):
    """Generate wireframe lines for empty objects used as custom shapes"""
    lines = []
    
    try:
        armature_matrix = armature_obj.matrix_world
        
        if pose_bone.custom_shape_transform:
            transform_bone = armature_obj.pose.bones[pose_bone.custom_shape_transform.name]
            bone_matrix = transform_bone.matrix
        else:
            bone_matrix = pose_bone.matrix
        
        bone_length = bone.length if bone.length > 0 else 1.0
        scale_xyz = pose_bone.custom_shape_scale_xyz
        
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
        
        empty_size = empty_obj.empty_display_size
        
        if empty_obj.empty_display_type == 'PLAIN_AXES':
            axes_lines = [
                Vector((0, 0, 0)), Vector((empty_size, 0, 0)),
                Vector((0, 0, 0)), Vector((0, empty_size, 0)),
                Vector((0, 0, 0)), Vector((0, 0, empty_size))
            ]
            
        elif empty_obj.empty_display_type == 'CIRCLE':
            axes_lines = []
            segments = 16
            for i in range(segments):
                angle1 = (i / segments) * 2 * math.pi
                angle2 = ((i + 1) / segments) * 2 * math.pi
                v1 = Vector((math.cos(angle1) * empty_size, math.sin(angle1) * empty_size, 0))
                v2 = Vector((math.cos(angle2) * empty_size, math.sin(angle2) * empty_size, 0))
                axes_lines.extend([v1, v2])
                
        elif empty_obj.empty_display_type == 'SPHERE':
            # Generate sphere wireframe
            axes_lines = []
            segments = 12
            
            # Create three circles for sphere wireframe (XY, XZ, YZ planes)
            for plane in ['XY', 'XZ', 'YZ']:
                for i in range(segments):
                    angle1 = (i / segments) * 2 * math.pi
                    angle2 = ((i + 1) / segments) * 2 * math.pi
                    
                    if plane == 'XY':
                        v1 = Vector((math.cos(angle1) * empty_size, math.sin(angle1) * empty_size, 0))
                        v2 = Vector((math.cos(angle2) * empty_size, math.sin(angle2) * empty_size, 0))
                    elif plane == 'XZ':
                        v1 = Vector((math.cos(angle1) * empty_size, 0, math.sin(angle1) * empty_size))
                        v2 = Vector((math.cos(angle2) * empty_size, 0, math.sin(angle2) * empty_size))
                    else:  # YZ
                        v1 = Vector((0, math.cos(angle1) * empty_size, math.sin(angle1) * empty_size))
                        v2 = Vector((0, math.cos(angle2) * empty_size, math.sin(angle2) * empty_size))
                    
                    axes_lines.extend([v1, v2])
                
        elif empty_obj.empty_display_type == 'CUBE':
            s = empty_size
            vertices = [
                Vector((-s, -s, -s)), Vector((s, -s, -s)), Vector((s, s, -s)), Vector((-s, s, -s)),
                Vector((-s, -s, s)), Vector((s, -s, s)), Vector((s, s, s)), Vector((-s, s, s))
            ]
            edges = [
                (0, 1), (1, 2), (2, 3), (3, 0),
                (4, 5), (5, 6), (6, 7), (7, 4),
                (0, 4), (1, 5), (2, 6), (3, 7)
            ]
            axes_lines = []
            for edge in edges:
                axes_lines.extend([vertices[edge[0]], vertices[edge[1]]])
                
        else:
            # Default to plain axes
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


def get_selection_state(armature_obj):
    """Get current selection state for change detection"""
    try:
        armature_data = armature_obj.data
        selection_state = []
        
        for bone in armature_data.bones:
            selection_state.append((bone.name, bone.select, bone == armature_data.bones.active))
        
        return tuple(selection_state)
    except:
        return None


def get_transform_state(armature_obj):
    """Get current transform state for change detection to prevent ghosting"""
    try:
        transform_state = []
        
        for pose_bone in armature_obj.pose.bones:
            # Get the current pose bone matrix
            transform_state.append((pose_bone.name, tuple(pose_bone.matrix.flatten())))
        
        return tuple(transform_state)
    except:
        return None


def get_selected_bone_data():
    """Get wireframe lines and colors for bones with custom shapes"""
    context = bpy.context
    
    if not is_valid_context():
        return {}
    
    armature_obj = context.active_object
    armature_data = armature_obj.data
    
    bone_data = {}
    
    try:
        scene = context.scene
        enable_all = scene.thick_bones_props.enable_all
        
        for bone in armature_data.bones:
            # Fixed logic: show if "enable_all" is True OR bone is selected
            should_process = enable_all or bone.select
            
            if should_process:
                pose_bone = armature_obj.pose.bones[bone.name]
                if pose_bone.custom_shape:
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


def draw_thick_bones():
    """Draw thick lines for selected bones with custom shapes - updates every frame"""
    global bone_batches, shader, is_drawing, _last_transform_state, _last_overlay_state
    
    if not is_drawing or not is_valid_context():
        return
    
    # Check if overlays are enabled - if not, clear the overlay and return
    current_overlay_state = are_overlays_enabled()
    overlay_changed = current_overlay_state != _last_overlay_state
    
    if overlay_changed:
        _last_overlay_state = current_overlay_state
        if not current_overlay_state:
            # Clear any cached batches when overlays are disabled
            bone_batches.clear()
            # Force a redraw to clear the overlay
            tag_redraw_all()
    
    # Don't draw if overlays are disabled
    if not current_overlay_state:
        return
    
    try:
        context = bpy.context
        armature_obj = context.active_object
        
        # Check if transforms have changed to clear ghost artifacts
        current_transform_state = get_transform_state(armature_obj)
        transform_changed = current_transform_state != _last_transform_state
        
        if transform_changed:
            _last_transform_state = current_transform_state
            # Clear any cached batches when transforms change
            bone_batches.clear()
        
        scene = bpy.context.scene
        thickness = scene.thick_bones_props.line_thickness
        
        # Get fresh bone data every frame for responsiveness
        bone_data = get_selected_bone_data()
        
        if not bone_data:
            return
        
        shader = get_shader()
        
        # Determine depth testing based on armature display settings
        display_in_front = should_display_in_front()
        
        # Set up drawing state
        if display_in_front:
            # Disable depth testing to draw in front of everything
            gpu.state.depth_test_set('NONE')
        else:
            # Use normal depth testing
            gpu.state.depth_test_set('LESS_EQUAL')
        
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(thickness)
        gpu.state.depth_mask_set(True)
        
        # Create and draw batches on the fly for maximum responsiveness
        for bone_name, data in bone_data.items():
            if data['lines']:
                # Always create fresh batches to prevent ghosting
                batch = batch_for_shader(
                    shader, 'LINES',
                    {"pos": data['lines']}
                )
                
                shader.bind()
                color = data['color']
                shader.uniform_float("color", (color[0], color[1], color[2], 1.0))
                batch.draw(shader)
        
        # Clean up drawing state properly
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(True)
        
    except Exception as e:
        print(f"Draw error: {e}")
        # Ensure we clean up on error
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(True)


def enable_thick_bones():
    """Enable thick bones display"""
    global draw_handler, is_drawing, _last_overlay_state
    
    if is_drawing:
        return
    
    draw_handler = bpy.types.SpaceView3D.draw_handler_add(
        draw_thick_bones, (), 'WINDOW', 'POST_VIEW'
    )
    is_drawing = True
    _last_overlay_state = are_overlays_enabled()
    
    # Force immediate redraw to clear any residual state
    tag_redraw_all()
    
    # Set up a timer to ensure continuous updates during transforms
    if not bpy.app.timers.is_registered(update_overlay_timer):
        bpy.app.timers.register(update_overlay_timer, first_interval=0.01, persistent=True)


def update_overlay_timer():
    """Timer function to ensure overlay updates during bone transforms"""
    if is_drawing and is_valid_context():
        tag_redraw_all()
        return 0.016  # ~60 FPS updates
    return None  # Stop timer if overlay is disabled


def cleanup_thick_bones():
    """Clean up the drawing handler"""
    global draw_handler, is_drawing, bone_batches, _last_selection_state, _last_transform_state, _last_overlay_state
    
    # Stop the update timer
    if bpy.app.timers.is_registered(update_overlay_timer):
        bpy.app.timers.unregister(update_overlay_timer)
    
    if draw_handler:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(draw_handler, 'WINDOW')
        except Exception as e:
            print(f"Error removing draw handler: {e}")
        draw_handler = None
    
    bone_batches = {}
    _last_selection_state = None
    _last_transform_state = None
    _last_overlay_state = None
    is_drawing = False
    
    # Force final redraw to clear any remaining overlay
    tag_redraw_all()


@persistent
def mode_change_handler(scene, depsgraph):
    """Handler for mode changes"""
    global is_drawing
    
    # If we're leaving pose mode or context is invalid, cleanup
    if is_drawing and not is_valid_context():
        cleanup_thick_bones()
        tag_redraw_all()


class POSE_OT_toggle_thick_bones(Operator):
    """Toggle thick bone display for selected bones with custom shapes"""
    bl_idname = "pose.toggle_thick_bones"
    bl_label = "Toggle Thick Bones"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        global is_drawing
        
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
            
            # Get current bone data to report count
            bone_data = get_selected_bone_data()
            total_bones = len(bone_data)
            
            if total_bones > 0:
                self.report({'INFO'}, f"Thick bones enabled for {total_bones} custom shapes")
            else:
                scene = context.scene
                if scene.thick_bones_props.enable_all:
                    self.report({'WARNING'}, "Thick bones enabled - no custom shapes found on armature")
                else:
                    self.report({'WARNING'}, "Thick bones enabled - select bones with custom shapes to see them")
        
        tag_redraw_all()
        return {'FINISHED'}


class ThickBonesProperties(bpy.types.PropertyGroup):
    line_thickness: FloatProperty(
        name="Line Thickness",
        default=3.0,
        min=1.0,
        max=20.0,
        description="Thickness of the wireframe lines",
        update=lambda self, context: tag_redraw_all() if is_drawing else None
    )
    
    enable_all: BoolProperty(
        name="All Custom Shapes",
        default=False,
        description="Display thick bones for all bones with custom shapes (not just selected ones)",
        update=lambda self, context: tag_redraw_all() if is_drawing else None
    )


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
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.thick_bones_props
        
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        # Main toggle
        col = layout.column()
        
        if is_drawing:
            col.operator("pose.toggle_thick_bones", text="Disable", icon='BONE_DATA')
        else:
            col.operator("pose.toggle_thick_bones", text="Enable", icon='BONE_DATA')
        
        # Settings (only when enabled)
        if is_drawing:
            col.separator()
            col.prop(props, "line_thickness")
            col.prop(props, "enable_all")


# Registration
classes = (
    POSE_OT_toggle_thick_bones,
    ThickBonesProperties,
    VIEW3D_PT_thick_bones_overlay,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.thick_bones_props = bpy.props.PointerProperty(
        type=ThickBonesProperties
    )
    
    # Register handler
    bpy.app.handlers.depsgraph_update_post.append(mode_change_handler)

def unregister():
    cleanup_thick_bones()
    
    # Unregister handler
    if mode_change_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(mode_change_handler)
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    if hasattr(bpy.types.Scene, 'thick_bones_props'):
        del bpy.types.Scene.thick_bones_props

if __name__ == "__main__":
    register()
