bl_info = {
    "name": "Thick Bones Overlay",
    "author": "Dan Ulrich", 
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "3D Viewport > Overlays (Pose Mode)",
    "description": "Display selected bones with customizable thickness overlay in pose mode",
    "category": "Rigging",
}

import bpy
import bmesh
import gpu
from gpu_extras.batch import batch_for_shader
from bpy.props import FloatProperty, BoolProperty, EnumProperty
from bpy.types import Panel, Operator
import mathutils
from mathutils import Vector, Matrix
from bpy.app.handlers import persistent


# Global variables
draw_handler = None
bone_batch = None
active_bone_batch = None
shader = None
bone_lines = []
active_bone_lines = []
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
        
        return hash((tuple(sorted(selected_bones)), active_bone_name))
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
        
        # Create hash based on selected bone transforms
        bone_transforms = []
        for bone in armature.pose.bones:
            if bone.bone.select:
                # Get bone matrix for transform comparison
                matrix_tuple = tuple(tuple(row) for row in bone.matrix)
                bone_transforms.append((bone.name, matrix_tuple))
        
        # Include object transform
        obj_matrix = tuple(tuple(row) for row in armature.matrix_world)
        
        return hash((tuple(bone_transforms), obj_matrix))
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
            print("Invalid context detected, cleaning up")
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
            print("Changes detected, updating bone display")
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
    
    print("Starting auto-update timer")
    
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
    print(f"Auto-update timer started: {update_timer}")


def stop_auto_update():
    """Stop the auto-update timer"""
    global update_timer
    
    if update_timer is not None:
        try:
            if bpy.app.timers.is_registered(auto_update_check):
                bpy.app.timers.unregister(auto_update_check)
                print("Auto-update timer stopped")
        except Exception as e:
            print(f"Error stopping timer: {e}")
        update_timer = None


def get_bone_wireframe_lines(bone, armature_obj, thickness_multiplier=1.0):
    """Generate wireframe lines for a bone based on its custom shape or default shape"""
    lines = []
    
    try:
        pose_bone = armature_obj.pose.bones[bone.name]
        
        # Get bone matrices
        bone_matrix = armature_obj.matrix_world @ pose_bone.matrix
        
        if pose_bone.custom_shape:
            # Use custom shape mesh
            custom_shape = pose_bone.custom_shape
            
            # Create temporary bmesh from custom shape
            bm = bmesh.new()
            bm.from_mesh(custom_shape.data)
            
            # Apply custom shape transform if specified
            if pose_bone.custom_shape_transform:
                transform_bone = armature_obj.pose.bones[pose_bone.custom_shape_transform.name]
                shape_matrix = armature_obj.matrix_world @ transform_bone.matrix
            else:
                shape_matrix = bone_matrix
            
            # Scale by bone custom shape scale
            scale_matrix = Matrix.Scale(pose_bone.custom_shape_scale_xyz[0] * thickness_multiplier, 4, Vector((1, 0, 0))) @ \
                          Matrix.Scale(pose_bone.custom_shape_scale_xyz[1] * thickness_multiplier, 4, Vector((0, 1, 0))) @ \
                          Matrix.Scale(pose_bone.custom_shape_scale_xyz[2] * thickness_multiplier, 4, Vector((0, 0, 1)))
            
            final_matrix = shape_matrix @ scale_matrix
            
            # Get edges from custom shape
            for edge in bm.edges:
                v1 = final_matrix @ edge.verts[0].co
                v2 = final_matrix @ edge.verts[1].co
                lines.extend([v1, v2])
            
            bm.free()
            
        else:
            # Generate default bone shape (stick/octahedral)
            bone_length = bone.length
            if bone_length == 0:
                bone_length = 0.1
            
            # Create basic bone shape - stick with head and tail
            head = bone_matrix @ Vector((0, 0, 0))
            tail = bone_matrix @ Vector((0, bone_length, 0))
            
            # Add some width for visibility
            width = bone_length * 0.1 * thickness_multiplier
            
            # Create octahedral shape around bone
            up = bone_matrix @ Vector((0, 0, width)) - head
            down = bone_matrix @ Vector((0, 0, -width)) - head
            left = bone_matrix @ Vector((-width, 0, 0)) - head
            right = bone_matrix @ Vector((width, 0, 0)) - head
            
            # Connect head to corners
            lines.extend([head, head + up])
            lines.extend([head, head + down])
            lines.extend([head, head + left])
            lines.extend([head, head + right])
            
            # Connect corners to tail
            lines.extend([head + up, tail])
            lines.extend([head + down, tail])
            lines.extend([head + left, tail])
            lines.extend([head + right, tail])
            
            # Connect corners to each other
            lines.extend([head + up, head + right])
            lines.extend([head + right, head + down])
            lines.extend([head + down, head + left])
            lines.extend([head + left, head + up])
    
    except Exception as e:
        print(f"Error generating bone wireframe for {bone.name}: {e}")
    
    return lines


def get_selected_bone_lines():
    """Get wireframe lines for selected bones, separating active bone"""
    context = bpy.context
    
    if not is_valid_context():
        return [], []
    
    armature_obj = context.active_object
    armature_data = armature_obj.data
    
    lines = []
    active_lines = []
    
    try:
        # Get thickness multiplier from scene properties
        scene = context.scene
        thickness_mult = scene.thick_bones_props.thickness_multiplier
        active_thickness_mult = scene.thick_bones_props.active_thickness_multiplier
        
        # Get active bone
        active_bone = armature_data.bones.active
        
        # Process selected bones
        for bone in armature_data.bones:
            if bone.select:
                if active_bone and bone == active_bone:
                    # This is the active bone
                    bone_lines = get_bone_wireframe_lines(bone, armature_obj, active_thickness_mult)
                    active_lines.extend(bone_lines)
                else:
                    # Regular selected bone
                    bone_lines = get_bone_wireframe_lines(bone, armature_obj, thickness_mult)
                    lines.extend(bone_lines)
        
        return lines, active_lines
        
    except Exception as e:
        print(f"Error getting bone lines: {e}")
        return [], []


def draw_thick_bones():
    """Draw thick lines for selected bones"""
    global bone_batch, active_bone_batch, shader, is_drawing
    
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
        color = scene.thick_bones_props.color
        active_color = scene.thick_bones_props.active_color
        active_thickness = scene.thick_bones_props.active_line_thickness
        
        # Use cached shader
        shader = get_shader()
        
        # Enable line smooth and blend
        gpu.state.blend_set('ALPHA')
        
        # Draw regular selected bones
        if bone_batch:
            gpu.state.line_width_set(thickness)
            shader.bind()
            shader.uniform_float("color", (color[0], color[1], color[2], 1.0))
            bone_batch.draw(shader)
        
        # Draw active bone with different color/thickness
        if active_bone_batch:
            gpu.state.line_width_set(active_thickness)
            shader.bind()
            shader.uniform_float("color", (active_color[0], active_color[1], active_color[2], 1.0))
            active_bone_batch.draw(shader)
        
        # Restore state
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')
        
    except Exception as e:
        print(f"Draw error: {e}")


def update_bone_display():
    """Update the bone batch with current selection"""
    global bone_batch, active_bone_batch, shader, bone_lines, active_bone_lines
    
    # Check if context is valid
    if not is_valid_context():
        bone_batch = None
        active_bone_batch = None
        return
    
    try:
        # Get current selected bone lines
        bone_lines, active_bone_lines = get_selected_bone_lines()
        
        # Use cached shader
        shader = get_shader()
        
        # Create batch for regular selected bones
        if bone_lines:
            bone_batch = batch_for_shader(
                shader, 'LINES',
                {"pos": bone_lines}
            )
        else:
            bone_batch = None
        
        # Create batch for active bone
        if active_bone_lines:
            active_bone_batch = batch_for_shader(
                shader, 'LINES',
                {"pos": active_bone_lines}
            )
        else:
            active_bone_batch = None
            
    except Exception as e:
        print(f"Error updating bone display: {e}")
        bone_batch = None
        active_bone_batch = None


@persistent
def mode_change_handler(scene, depsgraph):
    """Handler for mode changes and object deletions"""
    global is_drawing
    
    if is_drawing and not is_valid_context():
        print("Mode change detected, cleaning up")
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
    """Toggle thick bone display for selected bones"""
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
            update_bone_display()
            draw_handler = bpy.types.SpaceView3D.draw_handler_add(
                draw_thick_bones, (), 'WINDOW', 'POST_VIEW'
            )
            is_drawing = True
            
            # Set up auto-update using scene property
            scene = context.scene
            auto_update_enabled = scene.thick_bones_props.auto_update
            if auto_update_enabled:
                start_auto_update()
            
            total_bones = len(bone_lines)//2 + len(active_bone_lines)//2
            if total_bones > 0:
                self.report({'INFO'}, f"Thick bones enabled for {total_bones} bone segments")
            else:
                self.report({'WARNING'}, "Thick bones enabled - select bones to see them")
        
        # Refresh viewport
        tag_redraw_all()
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
        
        if bone_lines or active_bone_lines:
            total_bones = len(bone_lines)//2 + len(active_bone_lines)//2
            self.report({'INFO'}, f"Updated thick bones for {total_bones} bone segments")
        else:
            self.report({'WARNING'}, "No bones selected")
        
        # Refresh viewport
        tag_redraw_all()
        return {'FINISHED'}


class ThickBonesProperties(bpy.types.PropertyGroup):
    line_thickness: FloatProperty(
        name="Line Thickness",
        default=3.0,
        min=1.0,
        max=20.0,
        update=lambda self, context: force_redraw_if_active()
    )
    
    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        default=(0.0, 0.8, 1.0),  # Light blue
        min=0.0,
        max=1.0,
        update=lambda self, context: force_redraw_if_active()
    )
    
    active_line_thickness: FloatProperty(
        name="Active Line Thickness",
        default=5.0,
        min=1.0,
        max=20.0,
        update=lambda self, context: force_redraw_if_active()
    )
    
    active_color: bpy.props.FloatVectorProperty(
        name="Active Color",
        subtype='COLOR',
        default=(1.0, 0.8, 0.0),  # Yellow-orange
        min=0.0,
        max=1.0,
        update=lambda self, context: force_redraw_if_active()
    )
    
    thickness_multiplier: FloatProperty(
        name="Shape Scale",
        default=1.0,
        min=0.1,
        max=5.0,
        description="Scale multiplier for bone shapes",
        update=lambda self, context: force_update_if_active()
    )
    
    active_thickness_multiplier: FloatProperty(
        name="Active Shape Scale",
        default=1.2,
        min=0.1,
        max=5.0,
        description="Scale multiplier for active bone shape",
        update=lambda self, context: force_update_if_active()
    )
    
    auto_update: BoolProperty(
        name="Auto Update",
        default=True,
        update=lambda self, context: update_auto_update_setting(self, context)
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
    print(f"Auto-update setting changed to: {auto_update_enabled}")
    
    if auto_update_enabled and is_drawing:
        start_auto_update()
    elif not auto_update_enabled:
        stop_auto_update()


class VIEW3D_PT_thick_bones_overlay(Panel):
    """Thick Bones Overlay Panel"""
    bl_label = "Thick Bones"
    bl_idname = "VIEW3D_PT_thick_bones_overlay"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_parent_id = "VIEW3D_PT_overlay"
    
    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'ARMATURE' and
                context.mode == 'POSE')
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.thick_bones_props
        
        # Main toggle button
        col = layout.column(align=True)
        row = col.row(align=True)
        
        # Toggle button with icon and text
        if is_drawing:
            row.operator("pose.toggle_thick_bones", text="Thick Bones", icon='BONE_DATA', depress=True)
        else:
            row.operator("pose.toggle_thick_bones", text="Thick Bones", icon='BONE_DATA')
        
        # Auto-update toggle
        row.prop(props, "auto_update", text="", icon='FILE_REFRESH')
        
        # Settings section (only when enabled)
        if is_drawing:
            # Selected bones section
            col.separator(factor=0.5)
            box = col.box()
            box_col = box.column(align=True)
            
            # Header for selected bones
            header_row = box_col.row(align=True)
            header_row.label(text="Selected Bones", icon='BONE_DATA')
            
            # Properties
            prop_row = box_col.row(align=True)
            prop_row.prop(props, "line_thickness", text="Line")
            prop_row.prop(props, "color", text="")
            
            shape_row = box_col.row(align=True)
            shape_row.prop(props, "thickness_multiplier", text="Scale")
            
            # Active bone section
            box_col.separator(factor=0.3)
            active_row = box_col.row(align=True)
            active_row.label(text="Active Bone", icon='ARMATURE_DATA')
            
            active_prop_row = box_col.row(align=True)
            active_prop_row.prop(props, "active_line_thickness", text="Line")
            active_prop_row.prop(props, "active_color", text="")
            
            active_shape_row = box_col.row(align=True)
            active_shape_row.prop(props, "active_thickness_multiplier", text="Scale")
            
            # Manual update button (only when auto-update is off)
            if not props.auto_update:
                col.separator(factor=0.5)
                update_row = col.row(align=True)
                update_row.operator("pose.update_thick_bones", text="Update Selection", icon='FILE_REFRESH')


# Clean up function
def cleanup_thick_bones():
    """Clean up the drawing handler and auto-update timer"""
    global draw_handler, is_drawing, bone_batch, active_bone_batch
    
    print("Cleaning up thick bones")
    
    if draw_handler:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(draw_handler, 'WINDOW')
        except Exception as e:
            print(f"Error removing draw handler: {e}")
        draw_handler = None
    
    # Stop auto-update timer
    stop_auto_update()
    
    # Clear batches
    bone_batch = None
    active_bone_batch = None
    
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
