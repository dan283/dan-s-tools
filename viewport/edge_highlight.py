bl_info = {
    "name": "Thick Edges Overlay",
    "author": "Dan Ulrich",
    "version": (1, 2, 1),
    "blender": (4, 0, 0),
    "location": "3D Viewport > Overlays",
    "description": "Display selected edges with customizable thickness and color in the viewport overlays",
    "category": "Mesh",
}

import bpy
import bmesh
import gpu
from gpu_extras.batch import batch_for_shader
from bpy.props import FloatProperty, BoolProperty
from bpy.types import Panel, Operator
import mathutils
from bpy.app.handlers import persistent


# Global variables to store the drawing handler and batch data
draw_handler = None
edge_batch = None
active_edge_batch = None
shader = None
edge_coords = []
active_edge_coords = []
is_drawing = False
auto_update_enabled = True
update_timer = None
last_selection_hash = None
last_mesh_hash = None
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
    """Get a hash of the current edge selection for comparison"""
    context = bpy.context
    
    if not context.active_object or context.active_object.type != 'MESH':
        return None
    
    if context.mode != 'EDIT_MESH':
        return None
    
    try:
        # Get bmesh representation
        bm = bmesh.from_edit_mesh(context.active_object.data)
        if not bm.is_valid:
            return None
            
        # Ensure face indices are valid
        bm.edges.ensure_lookup_table()
        
        # Create a hash based on selected edge indices and active edge
        selected_edges = [edge.index for edge in bm.edges if edge.select]
        
        # Also include active edge info
        active_edge_idx = -1
        if bm.select_history:
            for elem in reversed(bm.select_history):
                if isinstance(elem, bmesh.types.BMEdge) and elem.select:
                    active_edge_idx = elem.index
                    break
        
        return hash((tuple(sorted(selected_edges)), active_edge_idx))
    except Exception as e:
        print(f"Selection hash error: {e}")
        return None


def get_mesh_hash():
    """Get a lightweight hash of the current mesh for comparison"""
    context = bpy.context
    
    if not context.active_object or context.active_object.type != 'MESH':
        return None
    
    if context.mode != 'EDIT_MESH':
        return None
    
    try:
        # Get bmesh representation for actual mesh data hash
        bm = bmesh.from_edit_mesh(context.active_object.data)
        if not bm.is_valid:
            return None
        
        # Create a simple hash based on vertex count and edge count
        vert_count = len(bm.verts)
        edge_count = len(bm.edges)
        
        # Include object transform as well
        obj = context.active_object
        matrix_tuple = tuple(tuple(row) for row in obj.matrix_world)
        
        return hash((vert_count, edge_count, matrix_tuple))
    except Exception as e:
        print(f"Mesh hash error: {e}")
        return None


def is_valid_context():
    """Check if the current context is valid for thick edges display"""
    context = bpy.context
    
    # Check if we have an active object and it's a mesh
    if not context.active_object or context.active_object.type != 'MESH':
        return False
    
    # Check if we're in edit mode
    if context.mode != 'EDIT_MESH':
        return False
    
    # Check if the object still exists in the scene
    if context.active_object.name not in bpy.data.objects:
        return False
    
    # Check if mesh data is valid
    try:
        bm = bmesh.from_edit_mesh(context.active_object.data)
        return bm.is_valid
    except:
        return False


def auto_update_check():
    """Timer function to check for selection changes and mesh modifications"""
    global last_selection_hash, last_mesh_hash, last_object_name, last_mode
    global auto_update_enabled, is_drawing
    
    try:
        if not auto_update_enabled or not is_drawing:
            return 0.1
        
        context = bpy.context
        
        # Check if context is still valid
        if not is_valid_context():
            print("Invalid context detected, cleaning up")
            cleanup_thick_edges()
            tag_redraw_all()
            return None  # Stop timer
        
        # Check if overlays are disabled
        space_data = get_3d_view_space()
        if space_data and not space_data.overlay.show_overlays:
            return 0.1  # Continue checking but don't update
        
        current_object_name = context.active_object.name
        current_mode = context.mode
        current_selection_hash = get_selection_hash()
        current_mesh_hash = get_mesh_hash()
        
        # Check for changes
        needs_update = False
        
        if (current_selection_hash != last_selection_hash or
            current_mesh_hash != last_mesh_hash or
            current_object_name != last_object_name or
            current_mode != last_mode):
            
            needs_update = True
            
            # Update stored values
            last_selection_hash = current_selection_hash
            last_mesh_hash = current_mesh_hash
            last_object_name = current_object_name
            last_mode = current_mode
        
        if needs_update:
            print("Changes detected, updating edge display")
            update_edge_display()
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
    global update_timer, last_selection_hash, last_mesh_hash, last_object_name, last_mode
    
    print("Starting auto-update timer")
    
    # Stop existing timer if running
    stop_auto_update()
    
    # Set initial values
    last_selection_hash = get_selection_hash()
    last_mesh_hash = get_mesh_hash()
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


def get_selected_edge_coords():
    """Get coordinates of selected edges in world space, separating active edge"""
    context = bpy.context
    
    if not is_valid_context():
        return [], []
    
    obj = context.active_object
    
    try:
        # Get bmesh representation
        bm = bmesh.from_edit_mesh(obj.data)
        if not bm.is_valid:
            return [], []
        
        # Ensure indices are valid
        bm.edges.ensure_lookup_table()
        
        coords = []
        active_coords = []
        
        # Get the active edge from selection history
        active_edge = None
        if bm.select_history:
            for elem in reversed(bm.select_history):
                if isinstance(elem, bmesh.types.BMEdge) and elem.select:
                    active_edge = elem
                    break
        
        # Pre-calculate matrix for better performance
        matrix_world = obj.matrix_world
        
        # Get selected edges
        for edge in bm.edges:
            if edge.select:
                # Convert local coordinates to world coordinates
                v1_world = matrix_world @ edge.verts[0].co
                v2_world = matrix_world @ edge.verts[1].co
                
                # Check if this is the active edge
                if active_edge and edge == active_edge:
                    active_coords.extend([v1_world, v2_world])
                else:
                    coords.extend([v1_world, v2_world])
        
        return coords, active_coords
        
    except Exception as e:
        print(f"Error getting edge coordinates: {e}")
        return [], []


def draw_thick_edges():
    """Draw thick lines for selected edges"""
    global edge_batch, active_edge_batch, shader, is_drawing
    
    if not is_drawing or not is_valid_context():
        return
    
    # Check if overlays are enabled
    space_data = get_3d_view_space()
    if space_data and not space_data.overlay.show_overlays:
        return
    
    try:
        # Get settings from scene properties
        scene = bpy.context.scene
        thickness = scene.thick_edges_props.thickness
        color = scene.thick_edges_props.color
        active_color = scene.thick_edges_props.active_color
        active_thickness = scene.thick_edges_props.active_thickness
        
        # Use cached shader
        shader = get_shader()
        
        # Enable line smooth and blend
        gpu.state.blend_set('ALPHA')
        
        # Draw regular selected edges
        if edge_batch:
            gpu.state.line_width_set(thickness)
            shader.bind()
            shader.uniform_float("color", (color[0], color[1], color[2], 1.0))
            edge_batch.draw(shader)
        
        # Draw active edge with different color/thickness
        if active_edge_batch:
            gpu.state.line_width_set(active_thickness)
            shader.bind()
            shader.uniform_float("color", (active_color[0], active_color[1], active_color[2], 1.0))
            active_edge_batch.draw(shader)
        
        # Restore state
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')
        
    except Exception as e:
        print(f"Draw error: {e}")


def update_edge_display():
    """Update the edge batch with current selection"""
    global edge_batch, active_edge_batch, shader, edge_coords, active_edge_coords
    
    # Check if context is valid
    if not is_valid_context():
        edge_batch = None
        active_edge_batch = None
        return
    
    try:
        # Get current selected edge coordinates
        edge_coords, active_edge_coords = get_selected_edge_coords()
        
        # Use cached shader
        shader = get_shader()
        
        # Create batch for regular selected edges
        if edge_coords:
            edge_batch = batch_for_shader(
                shader, 'LINES',
                {"pos": edge_coords}
            )
        else:
            edge_batch = None
        
        # Create batch for active edge
        if active_edge_coords:
            active_edge_batch = batch_for_shader(
                shader, 'LINES',
                {"pos": active_edge_coords}
            )
        else:
            active_edge_batch = None
            
    except Exception as e:
        print(f"Error updating edge display: {e}")
        edge_batch = None
        active_edge_batch = None


@persistent
def mode_change_handler(scene, depsgraph):
    """Handler for mode changes and object deletions"""
    global is_drawing
    
    if is_drawing and not is_valid_context():
        print("Mode change detected, cleaning up")
        cleanup_thick_edges()
        tag_redraw_all()


@persistent
def selection_change_handler(scene, depsgraph):
    """Handler specifically for selection changes"""
    global is_drawing, auto_update_enabled
    
    if not is_drawing or not auto_update_enabled:
        return
        
    if is_valid_context():
        # Force update on selection change
        update_edge_display()
        tag_redraw_all()


class MESH_OT_toggle_thick_edges(Operator):
    """Toggle thick edge display for selected edges"""
    bl_idname = "mesh.toggle_thick_edges"
    bl_label = "Toggle Thick Edges"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        global draw_handler, is_drawing, auto_update_enabled
        
        if not context.active_object or context.active_object.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "Please enter Edit Mode")
            return {'CANCELLED'}
        
        if is_drawing:
            # Disable thick edges
            cleanup_thick_edges()
            self.report({'INFO'}, "Thick edges disabled")
        else:
            # Enable thick edges
            update_edge_display()
            draw_handler = bpy.types.SpaceView3D.draw_handler_add(
                draw_thick_edges, (), 'WINDOW', 'POST_VIEW'
            )
            is_drawing = True
            
            # Set up auto-update using scene property
            scene = context.scene
            auto_update_enabled = scene.thick_edges_props.auto_update
            if auto_update_enabled:
                start_auto_update()
            
            total_edges = len(edge_coords)//2 + len(active_edge_coords)//2
            if total_edges > 0:
                self.report({'INFO'}, f"Thick edges enabled for {total_edges} edges")
            else:
                self.report({'WARNING'}, "Thick edges enabled - select edges to see them")
        
        # Refresh viewport
        tag_redraw_all()
        return {'FINISHED'}


class MESH_OT_update_thick_edges(Operator):
    """Update thick edge display with current selection"""
    bl_idname = "mesh.update_thick_edges"
    bl_label = "Update Selection"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        global is_drawing
        
        if not is_drawing:
            self.report({'INFO'}, "Thick edges not enabled")
            return {'CANCELLED'}
        
        if not is_valid_context():
            self.report({'ERROR'}, "Invalid context for thick edges")
            cleanup_thick_edges()
            return {'CANCELLED'}
        
        # Update the edge display
        update_edge_display()
        
        if edge_coords or active_edge_coords:
            total_edges = len(edge_coords)//2 + len(active_edge_coords)//2
            self.report({'INFO'}, f"Updated thick edges for {total_edges} edges")
        else:
            self.report({'WARNING'}, "No edges selected")
        
        # Refresh viewport
        tag_redraw_all()
        return {'FINISHED'}


class ThickEdgesProperties(bpy.types.PropertyGroup):
    thickness: FloatProperty(
        name="Thickness",
        default=5.0,
        min=1.0,
        max=20.0,
        update=lambda self, context: force_redraw_if_active()
    )
    
    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        default=(1.0, 0.3, 0.0),  # Orange
        min=0.0,
        max=1.0,
        update=lambda self, context: force_redraw_if_active()
    )
    
    active_thickness: FloatProperty(
        name="Active Thickness",
        default=8.0,
        min=1.0,
        max=20.0,
        update=lambda self, context: force_redraw_if_active()
    )
    
    active_color: bpy.props.FloatVectorProperty(
        name="Active Color",
        subtype='COLOR',
        default=(1.0, 1.0, 0.0),  # Yellow
        min=0.0,
        max=1.0,
        update=lambda self, context: force_redraw_if_active()
    )
    
    auto_update: BoolProperty(
        name="Auto Update",
        default=True,
        update=lambda self, context: update_auto_update_setting(self, context)
    )


def force_redraw_if_active():
    """Force redraw if thick edges are active"""
    global is_drawing
    if is_drawing:
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


class VIEW3D_PT_thick_edges_overlay(Panel):
    """Thick Edges Overlay Panel"""
    bl_label = "Thick Edges"
    bl_idname = "VIEW3D_PT_thick_edges_overlay"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_parent_id = "VIEW3D_PT_overlay"
    
    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'MESH' and
                context.mode == 'EDIT_MESH')
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.thick_edges_props
        
        # Main toggle button with better spacing
        col = layout.column(align=True)
        row = col.row(align=True)
        
        # Toggle button with icon and text
        if is_drawing:
            row.operator("mesh.toggle_thick_edges", text="Thick Edges", icon='HIDE_ON', depress=True)
        else:
            row.operator("mesh.toggle_thick_edges", text="Thick Edges", icon='HIDE_OFF')
        
        # Auto-update toggle (always visible for easy access)
        row.prop(props, "auto_update", text="", icon='FILE_REFRESH')
        
        # Settings section (only when enabled)
        if is_drawing:
            # Selected edges section
            col.separator(factor=0.5)
            box = col.box()
            box_col = box.column(align=True)
            
            # Header for selected edges
            header_row = box_col.row(align=True)
            header_row.label(text="Selected Edges", icon='EDGESEL')
            
            # Properties in a clean grid
            prop_row = box_col.row(align=True)
            prop_row.prop(props, "thickness", text="Width")
            prop_row.prop(props, "color", text="")
            
            # Active edge section
            box_col.separator(factor=0.3)
            active_row = box_col.row(align=True)
            active_row.label(text="Active Edge", icon='PARTICLE_POINT')
            
            active_prop_row = box_col.row(align=True)
            active_prop_row.prop(props, "active_thickness", text="Width")
            active_prop_row.prop(props, "active_color", text="")
            
            # Manual update button (only when auto-update is off)
            if not props.auto_update:
                col.separator(factor=0.5)
                update_row = col.row(align=True)
                update_row.operator("mesh.update_thick_edges", text="Update Selection", icon='FILE_REFRESH')


# Clean up function
def cleanup_thick_edges():
    """Clean up the drawing handler and auto-update timer"""
    global draw_handler, is_drawing, edge_batch, active_edge_batch
    
    print("Cleaning up thick edges")
    
    if draw_handler:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(draw_handler, 'WINDOW')
        except Exception as e:
            print(f"Error removing draw handler: {e}")
        draw_handler = None
    
    # Stop auto-update timer
    stop_auto_update()
    
    # Clear batches
    edge_batch = None
    active_edge_batch = None
    
    is_drawing = False


# Registration
classes = (
    MESH_OT_toggle_thick_edges,
    MESH_OT_update_thick_edges,
    ThickEdgesProperties,
    VIEW3D_PT_thick_edges_overlay,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.thick_edges_props = bpy.props.PointerProperty(
        type=ThickEdgesProperties
    )
    
    # Register handlers
    bpy.app.handlers.depsgraph_update_post.append(mode_change_handler)
    bpy.app.handlers.depsgraph_update_post.append(selection_change_handler)

def unregister():
    cleanup_thick_edges()
    
    # Unregister handlers
    handlers_to_remove = [mode_change_handler, selection_change_handler]
    for handler in handlers_to_remove:
        if handler in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(handler)
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    if hasattr(bpy.types.Scene, 'thick_edges_props'):
        del bpy.types.Scene.thick_edges_props

if __name__ == "__main__":
    register()
