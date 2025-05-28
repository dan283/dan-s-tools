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
shader = None
edge_coords = []
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
    """Get coordinates of selected edges in world space"""
    context = bpy.context
    
    if not context.active_object or context.active_object.type != 'MESH':
        return []
    
    obj = context.active_object
    
    # Ensure we're in edit mode
    if context.mode != 'EDIT_MESH':
        return []
    
    # Get bmesh representation
    bm = bmesh.from_edit_mesh(obj.data)
    
    coords = []
    
    # Get selected edges
    for edge in bm.edges:
        if edge.select:
            # Convert local coordinates to world coordinates
            v1_world = obj.matrix_world @ edge.verts[0].co
            v2_world = obj.matrix_world @ edge.verts[1].co
            coords.extend([v1_world, v2_world])
    
    return coords
    """Get coordinates of selected edges in world space"""
    context = bpy.context
    
    if not context.active_object or context.active_object.type != 'MESH':
        return []
    
    obj = context.active_object
    
    # Ensure we're in edit mode
    if context.mode != 'EDIT_MESH':
        return []
    
    # Get bmesh representation
    bm = bmesh.from_edit_mesh(obj.data)
    
    coords = []
    
    # Get selected edges
    for edge in bm.edges:
        if edge.select:
            # Convert local coordinates to world coordinates
            v1_world = obj.matrix_world @ edge.verts[0].co
            v2_world = obj.matrix_world @ edge.verts[1].co
            coords.extend([v1_world, v2_world])
    
    return coords


def draw_thick_edges():
    """Draw thick lines for selected edges"""
    global edge_batch, shader, is_drawing
    
    if not is_drawing or not edge_batch:
        return
    
    # Get thickness from scene properties
    scene = bpy.context.scene
    thickness = scene.thick_edges_props.thickness
    color = scene.thick_edges_props.color
    
    # Enable line smooth and set line width
    gpu.state.line_width_set(thickness)
    gpu.state.blend_set('ALPHA')
    
    # Draw the edges with color
    shader.bind()
    shader.uniform_float("color", (color[0], color[1], color[2], 1.0))
    edge_batch.draw(shader)
    
    # Restore state
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def update_edge_display():
    """Update the edge batch with current selection"""
    global edge_batch, shader, edge_coords
    
    # Get current selected edge coordinates
    edge_coords = get_selected_edge_coords()
    
    if not edge_coords:
        edge_batch = None
        return
    
    # Use built-in shader for better compatibility
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    # Create batch for lines
    edge_batch = batch_for_shader(
        shader, 'LINES',
        {"pos": edge_coords}
    )


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
            if edge_coords:
                draw_handler = bpy.types.SpaceView3D.draw_handler_add(
                    draw_thick_edges, (), 'WINDOW', 'POST_VIEW'
                )
                is_drawing = True
                
                # Set up auto-update if enabled
                scene = context.scene
                auto_update_enabled = scene.thick_edges_props.auto_update
                if auto_update_enabled:
                    start_auto_update()
                
                self.report({'INFO'}, f"Thick edges enabled for {len(edge_coords)//2} edges")
            else:
                self.report({'WARNING'}, "No edges selected")
        
        # Refresh viewport
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}


class MESH_OT_toggle_auto_update(Operator):
    """Toggle automatic update of thick edges when selection changes"""
    bl_idname = "mesh.toggle_auto_update"
    bl_label = "Toggle Auto Update"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        global auto_update_enabled, is_drawing
        
        scene = context.scene
        auto_update_enabled = scene.thick_edges_props.auto_update
        
        if auto_update_enabled and is_drawing:
            # Enable auto-update
            start_auto_update()
            self.report({'INFO'}, "Auto-update enabled")
        else:
            # Disable auto-update
            stop_auto_update()
            if auto_update_enabled:
                self.report({'INFO'}, "Auto-update disabled (thick edges not active)")
            else:
                self.report({'INFO'}, "Auto-update disabled")
        
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
        
        if edge_coords:
            self.report({'INFO'}, f"Updated thick edges for {len(edge_coords)//2} edges")
        else:
            self.report({'WARNING'}, "No edges selected")
        
        # Refresh viewport
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}
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
        
        if edge_coords:
            self.report({'INFO'}, f"Updated thick edges for {len(edge_coords)//2} edges")
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
        description="Thickness of selected edges",
        default=5.0,
        min=1.0,
        max=20.0
    )
    
    color: bpy.props.FloatVectorProperty(
        name="Color",
        description="Color of thick edges",
        subtype='COLOR',
        default=(1.0, 0.3, 0.0),  # Orange
        min=0.0,
        max=1.0
    )
    
    auto_update: BoolProperty(
        name="Auto Update Selection",
        description="Automatically update thick edges when selection changes",
        default=False,
        update=lambda self, context: bpy.ops.mesh.toggle_auto_update()
    )


class VIEW3D_PT_thick_edges(Panel):
    """Thick Edges Panel"""
    bl_label = "Thick Edges"
    bl_idname = "VIEW3D_PT_thick_edges"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"
    bl_context = "mesh_edit"
    
    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'MESH' and
                context.mode == 'EDIT_MESH')
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.thick_edges_props
        
        # Properties
        col = layout.column(align=True)
        col.prop(props, "thickness")
        col.prop(props, "color")
        
        # Auto-update checkbox
        layout.separator()
        row = layout.row()
        row.prop(props, "auto_update")
        
        # Buttons
        layout.separator()
        
        # Toggle button
        row = layout.row()
        if is_drawing:
            row.operator("mesh.toggle_thick_edges", text="Disable Thick Edges", icon='HIDE_ON')
        else:
            row.operator("mesh.toggle_thick_edges", text="Enable Thick Edges", icon='HIDE_OFF')
        
        # Update button (only show when enabled and auto-update is off)
        if is_drawing and not props.auto_update:
            row = layout.row()
            row.operator("mesh.update_thick_edges", text="Update Selection", icon='FILE_REFRESH')
        
        # Info
        layout.separator()
        box = layout.box()
        box.label(text="Info:", icon='INFO')
        box.label(text="Select edges and click Enable")
        if not props.auto_update:
            box.label(text="Use Update Selection after")
            box.label(text="changing edge selection")
        else:
            box.label(text="Selection updates automatically")
        
        if is_drawing:
            box.label(text=f"Displaying: {len(edge_coords)//2} edges", icon='CHECKMARK')
        
        if props.auto_update and is_drawing:
            box.label(text="Auto-update: ON", icon='PLAY')


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
    MESH_OT_toggle_auto_update,
    MESH_OT_update_thick_edges,
    ThickEdgesProperties,
    VIEW3D_PT_thick_edges,
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
