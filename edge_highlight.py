bl_info = {
    "name": "Thick Edges Overlay",
    "author": "Your Name",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
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


# Global variables to store the drawing handler and batch data
draw_handler = None
edge_batch = None
active_edge_batch = None
shader = None
edge_coords = []
active_edge_coords = []
is_drawing = False
auto_update_enabled = False
update_timer = None
last_selection_hash = None


def get_selection_hash():
    """Get a hash of the current edge selection for comparison"""
    context = bpy.context
    
    if not context.active_object or context.active_object.type != 'MESH':
        return None
    
    if context.mode != 'EDIT_MESH':
        return None
    
    # Get bmesh representation
    bm = bmesh.from_edit_mesh(context.active_object.data)
    
    # Create a hash based on selected edge indices
    selected_edges = [edge.index for edge in bm.edges if edge.select]
    return hash(tuple(sorted(selected_edges)))


def auto_update_check():
    """Timer function to check for selection changes"""
    global last_selection_hash, auto_update_enabled, is_drawing
    
    if not auto_update_enabled or not is_drawing:
        return 0.1  # Continue timer but don't update
    
    current_hash = get_selection_hash()
    
    if current_hash != last_selection_hash:
        last_selection_hash = current_hash
        
        # Update the edge display
        update_edge_display()
        
        # Refresh viewport
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    
    return 0.1  # Check every 0.1 seconds


def start_auto_update():
    """Start the auto-update timer"""
    global update_timer, last_selection_hash
    
    # Stop existing timer if running
    stop_auto_update()
    
    # Set initial selection hash
    last_selection_hash = get_selection_hash()
    
    # Start timer
    update_timer = bpy.app.timers.register(auto_update_check, first_interval=0.1)


def stop_auto_update():
    """Stop the auto-update timer"""
    global update_timer
    
    if update_timer:
        try:
            bpy.app.timers.unregister(auto_update_check)
        except:
            pass
        update_timer = None


def get_selected_edge_coords():
    """Get coordinates of selected edges in world space, separating active edge"""
    context = bpy.context
    
    if not context.active_object or context.active_object.type != 'MESH':
        return [], []
    
    obj = context.active_object
    
    # Ensure we're in edit mode
    if context.mode != 'EDIT_MESH':
        return [], []
    
    # Get bmesh representation
    bm = bmesh.from_edit_mesh(obj.data)
    
    # Ensure indices are valid
    bm.edges.ensure_lookup_table()
    
    coords = []
    active_coords = []
    
    # Get the history to find the active (last selected) edge
    active_edge = None
    if bm.select_history:
        # Get the last selected element from history
        last_selected = bm.select_history[-1]
        if isinstance(last_selected, bmesh.types.BMEdge) and last_selected.select:
            active_edge = last_selected
    
    # If no active edge from history, try to get it from bmesh
    if not active_edge and hasattr(bm.edges, 'active') and bm.edges.active:
        if bm.edges.active.select:
            active_edge = bm.edges.active
    
    # Get selected edges
    for edge in bm.edges:
        if edge.select:
            # Convert local coordinates to world coordinates
            v1_world = obj.matrix_world @ edge.verts[0].co
            v2_world = obj.matrix_world @ edge.verts[1].co
            
            # Check if this is the active edge
            if active_edge and edge == active_edge:
                active_coords.extend([v1_world, v2_world])
            else:
                coords.extend([v1_world, v2_world])
    
    return coords, active_coords


def draw_thick_edges():
    """Draw thick lines for selected edges"""
    global edge_batch, active_edge_batch, shader, is_drawing
    
    if not is_drawing:
        return
    
    # Get settings from scene properties
    scene = bpy.context.scene
    thickness = scene.thick_edges_props.thickness
    color = scene.thick_edges_props.color
    active_color = scene.thick_edges_props.active_color
    active_thickness = scene.thick_edges_props.active_thickness
    
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


def update_edge_display():
    """Update the edge batch with current selection"""
    global edge_batch, active_edge_batch, shader, edge_coords, active_edge_coords
    
    # Get current selected edge coordinates
    edge_coords, active_edge_coords = get_selected_edge_coords()
    
    # Use built-in shader for better compatibility
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
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
            if draw_handler:
                bpy.types.SpaceView3D.draw_handler_remove(draw_handler, 'WINDOW')
                draw_handler = None
            
            # Remove auto-update timer
            stop_auto_update()
            
            is_drawing = False
            self.report({'INFO'}, "Thick edges disabled")
        else:
            # Enable thick edges
            update_edge_display()
            if edge_coords or active_edge_coords:
                draw_handler = bpy.types.SpaceView3D.draw_handler_add(
                    draw_thick_edges, (), 'WINDOW', 'POST_VIEW'
                )
                is_drawing = True
                
                # Set up auto-update if enabled
                scene = context.scene
                auto_update_enabled = scene.thick_edges_props.auto_update
                if auto_update_enabled:
                    start_auto_update()
                
                total_edges = len(edge_coords)//2 + len(active_edge_coords)//2
                self.report({'INFO'}, f"Thick edges enabled for {total_edges} edges")
            else:
                self.report({'WARNING'}, "No edges selected")
        
        # Refresh viewport
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
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
        
        if not context.active_object or context.active_object.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "Please enter Edit Mode")
            return {'CANCELLED'}
        
        # Update the edge display
        update_edge_display()
        
        if edge_coords or active_edge_coords:
            total_edges = len(edge_coords)//2 + len(active_edge_coords)//2
            self.report({'INFO'}, f"Updated thick edges for {total_edges} edges")
        else:
            self.report({'WARNING'}, "No edges selected")
        
        # Refresh viewport
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}


class ThickEdgesProperties(bpy.types.PropertyGroup):
    thickness: FloatProperty(
        name="Thickness",
        default=5.0,
        min=1.0,
        max=20.0
    )
    
    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        default=(1.0, 0.3, 0.0),  # Orange
        min=0.0,
        max=1.0
    )
    
    active_thickness: FloatProperty(
        name="Active Thickness",
        default=8.0,
        min=1.0,
        max=20.0
    )
    
    active_color: bpy.props.FloatVectorProperty(
        name="Active Color",
        subtype='COLOR',
        default=(1.0, 1.0, 0.0),  # Yellow
        min=0.0,
        max=1.0
    )
    
    auto_update: BoolProperty(
        name="Auto Update",
        default=False,
        update=lambda self, context: update_auto_update_setting(self, context)
    )


def update_auto_update_setting(self, context):
    """Handle auto-update setting changes"""
    global auto_update_enabled, is_drawing
    
    auto_update_enabled = self.auto_update
    
    if auto_update_enabled and is_drawing:
        start_auto_update()
    else:
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
        
        # Toggle button
        row = layout.row(align=True)
        if is_drawing:
            row.operator("mesh.toggle_thick_edges", text="", icon='HIDE_ON', depress=True)
        else:
            row.operator("mesh.toggle_thick_edges", text="", icon='HIDE_OFF')
        
        # Regular edge properties
        sub = row.row(align=True)
        sub.enabled = is_drawing
        sub.prop(props, "thickness", text="")
        sub.prop(props, "color", text="")
        
        # Active edge properties
        row = layout.row(align=True)
        row.enabled = is_drawing
        row.label(text="Active:")
        row.prop(props, "active_thickness", text="")
        row.prop(props, "active_color", text="")
        
        # Auto-update and manual update
        row = layout.row(align=True)
        row.enabled = is_drawing
        row.prop(props, "auto_update", text="Auto")
        
        # Manual update button (only when not auto-updating)
        if is_drawing and not props.auto_update:
            row.operator("mesh.update_thick_edges", text="", icon='FILE_REFRESH')


# Clean up function
def cleanup_thick_edges():
    """Clean up the drawing handler and auto-update timer"""
    global draw_handler, is_drawing
    
    if draw_handler:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(draw_handler, 'WINDOW')
        except:
            pass
        draw_handler = None
    
    # Stop auto-update timer
    stop_auto_update()
    
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

def unregister():
    cleanup_thick_edges()
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    if hasattr(bpy.types.Scene, 'thick_edges_props'):
        del bpy.types.Scene.thick_edges_props

if __name__ == "__main__":
    register()
