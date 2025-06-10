import bpy
import bmesh
from mathutils import Vector
from bpy.props import BoolProperty, StringProperty
from bpy.types import Panel, Operator

bl_info = {
    "name": "Edge to Curve Converter",
    "author": "Your Name",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > N Panel > Edge to Curve",
    "description": "Convert selected edges to curves and hide them",
    "category": "Mesh",
}

class MESH_OT_edge_to_curve(Operator):
    """Convert selected edges to linear curves"""
    bl_idname = "mesh.edge_to_curve"
    bl_label = "Convert Edges to Curves"
    bl_options = {'REGISTER', 'UNDO'}
    
    hide_original: BoolProperty(
        name="Hide Original Edges",
        description="Hide the original edges after conversion",
        default=True
    )
    
    collection_name: StringProperty(
        name="Collection Name",
        description="Name of the collection to store curves",
        default="Curves"
    )
    
    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and 
                context.active_object.type == 'MESH' and 
                context.mode == 'EDIT_MESH')
    
    def execute(self, context):
        try:
            # Get the active mesh object
            obj = context.active_object
            mesh = obj.data
            
            # Switch to object mode temporarily
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Create bmesh from mesh
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bm.edges.ensure_lookup_table()
            bm.verts.ensure_lookup_table()
            
            # Get selected edges
            selected_edges = [e for e in bm.edges if e.select]
            
            if not selected_edges:
                self.report({'WARNING'}, "No edges selected")
                bm.free()
                bpy.ops.object.mode_set(mode='EDIT')
                return {'CANCELLED'}
            
            # Get or create collection
            collection = self.get_or_create_collection(self.collection_name)
            
            # Group edges into chains/loops
            edge_chains = self.get_edge_chains(selected_edges)
            
            created_curves = []
            
            # Convert each chain to a curve
            for i, chain in enumerate(edge_chains):
                curve_name = "{}_curve_{:03d}".format(obj.name, i + 1)
                curve_obj = self.create_curve_from_edges(chain, curve_name, obj)
                
                if curve_obj:
                    # Add to collection
                    collection.objects.link(curve_obj)
                    created_curves.append(curve_obj)
            
            # Hide original edges if requested
            if self.hide_original:
                for edge in selected_edges:
                    edge.hide = True
            
            # Update mesh
            bm.to_mesh(mesh)
            bm.free()
            
            # Switch back to edit mode
            bpy.ops.object.mode_set(mode='EDIT')
            
            # Report results
            self.report({'INFO'}, "Created {} curves from {} edges".format(
                len(created_curves), len(selected_edges)))
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, "Error: {}".format(str(e)))
            return {'CANCELLED'}
    
    def get_or_create_collection(self, name):
        """Get existing collection or create new one"""
        collection = bpy.data.collections.get(name)
        if collection is None:
            collection = bpy.data.collections.new(name)
            bpy.context.scene.collection.children.link(collection)
        return collection
    
    def get_edge_chains(self, edges):
        """Group connected edges into chains/loops"""
        chains = []
        remaining_edges = edges[:]
        
        while remaining_edges:
            # Start new chain
            current_chain = [remaining_edges.pop(0)]
            chain_changed = True
            
            # Keep adding connected edges
            while chain_changed:
                chain_changed = False
                
                # Get vertices at chain endpoints
                chain_start_verts = set(current_chain[0].verts)
                chain_end_verts = set(current_chain[-1].verts)
                
                # Look for connecting edges
                for edge in remaining_edges[:]:
                    edge_verts = set(edge.verts)
                    
                    # Check connection to start
                    if edge_verts.intersection(chain_start_verts):
                        current_chain.insert(0, edge)
                        remaining_edges.remove(edge)
                        chain_changed = True
                        break
                    # Check connection to end
                    elif edge_verts.intersection(chain_end_verts):
                        current_chain.append(edge)
                        remaining_edges.remove(edge)
                        chain_changed = True
                        break
            
            chains.append(current_chain)
        
        return chains
    
    def is_chain_closed(self, chain):
        """Check if edge chain forms a closed loop"""
        if len(chain) < 3:
            return False
        
        first_verts = set(chain[0].verts)
        last_verts = set(chain[-1].verts)
        
        return bool(first_verts.intersection(last_verts))
    
    def get_chain_vertices_ordered(self, chain):
        """Get vertices in correct order for the chain"""
        if not chain:
            return []
        
        ordered_verts = []
        
        # Start with first edge
        current_edge = chain[0]
        ordered_verts.extend(current_edge.verts)
        
        # Process remaining edges
        for edge in chain[1:]:
            edge_verts = list(edge.verts)
            
            # Find which vertex connects to the last vertex in our list
            last_vert = ordered_verts[-1]
            
            if edge_verts[0] == last_vert:
                ordered_verts.append(edge_verts[1])
            elif edge_verts[1] == last_vert:
                ordered_verts.append(edge_verts[0])
            else:
                # Edge doesn't connect properly, add both verts
                ordered_verts.extend(edge_verts)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_verts = []
        for vert in ordered_verts:
            if vert not in seen:
                unique_verts.append(vert)
                seen.add(vert)
        
        return unique_verts
    
    def create_curve_from_edges(self, edge_chain, name, source_obj):
        """Create a curve object from an edge chain"""
        try:
            # Get ordered vertices
            vertices = self.get_chain_vertices_ordered(edge_chain)
            
            if len(vertices) < 2:
                return None
            
            # Get world positions
            world_positions = []
            for vert in vertices:
                world_pos = source_obj.matrix_world @ vert.co
                world_positions.append(world_pos)
            
            # Create curve data
            curve_data = bpy.data.curves.new(name, type='CURVE')
            curve_data.dimensions = '3D'
            
            # Create spline
            spline = curve_data.splines.new('POLY')  # Linear curve
            spline.points.add(len(world_positions) - 1)  # -1 because one point exists by default
            
            # Set point coordinates
            for i, pos in enumerate(world_positions):
                spline.points[i].co = (pos.x, pos.y, pos.z, 1.0)  # x, y, z, weight
            
            # Check if should be cyclic
            if self.is_chain_closed(edge_chain):
                spline.use_cyclic_u = True
            
            # Create curve object
            curve_obj = bpy.data.objects.new(name, curve_data)
            
            return curve_obj
            
        except Exception as e:
            print("Error creating curve: {}".format(e))
            return None


class MESH_PT_edge_to_curve_panel(Panel):
    """Panel in the N-panel for edge to curve conversion"""
    bl_label = "Edge to Curve"
    bl_idname = "MESH_PT_edge_to_curve"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Edge to Curve"
    bl_context = "mesh_edit"
    
    def draw(self, context):
        layout = self.layout
        
        # Main conversion button
        layout.operator("mesh.edge_to_curve", text="Convert Edges to Curves", icon='CURVE_BEZCURVE')
        
        layout.separator()
        
        # Settings
        box = layout.box()
        box.label(text="Settings:", icon='SETTINGS')
        
        # Collection name
        row = box.row()
        row.label(text="Collection:")
        row.prop(context.scene, "edge_to_curve_collection", text="")
        
        # Hide original option
        row = box.row()
        row.prop(context.scene, "edge_to_curve_hide_original", text="Hide Original Edges")
        
        layout.separator()
        
        # Instructions
        box = layout.box()
        box.label(text="Instructions:", icon='INFO')
        col = box.column(align=True)
        col.label(text="1. Select edges in Edit Mode")
        col.label(text="2. Click 'Convert Edges to Curves'")
        col.label(text="3. Curves will be linear")
        col.label(text="4. Closed loops become cyclic")


class MESH_OT_edge_to_curve_with_settings(Operator):
    """Convert edges to curves using panel settings"""
    bl_idname = "mesh.edge_to_curve_with_settings"
    bl_label = "Convert Edges to Curves"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and 
                context.active_object.type == 'MESH' and 
                context.mode == 'EDIT_MESH')
    
    def execute(self, context):
        # Get settings from scene properties
        hide_original = context.scene.edge_to_curve_hide_original
        collection_name = context.scene.edge_to_curve_collection
        
        # Call the main operator with settings
        return bpy.ops.mesh.edge_to_curve(
            hide_original=hide_original,
            collection_name=collection_name
        )


def register():
    # Register scene properties
    bpy.types.Scene.edge_to_curve_collection = StringProperty(
        name="Collection Name",
        description="Collection to store converted curves",
        default="Curves"
    )
    
    bpy.types.Scene.edge_to_curve_hide_original = BoolProperty(
        name="Hide Original",
        description="Hide original edges after conversion",
        default=True
    )
    
    # Register classes
    bpy.utils.register_class(MESH_OT_edge_to_curve)
    bpy.utils.register_class(MESH_OT_edge_to_curve_with_settings)
    bpy.utils.register_class(MESH_PT_edge_to_curve_panel)
    
    # Update panel operator to use settings version
    MESH_PT_edge_to_curve_panel.draw = draw_panel_with_settings


def draw_panel_with_settings(self, context):
    layout = self.layout
    
    # Main conversion button
    layout.operator("mesh.edge_to_curve_with_settings", text="Convert Edges to Curves", icon='CURVE_BEZCURVE')
    
    layout.separator()
    
    # Settings
    box = layout.box()
    box.label(text="Settings:", icon='SETTINGS')
    
    # Collection name
    row = box.row()
    row.label(text="Collection:")
    row.prop(context.scene, "edge_to_curve_collection", text="")
    
    # Hide original option
    row = box.row()
    row.prop(context.scene, "edge_to_curve_hide_original", text="Hide Original Edges")
    
    layout.separator()
    
    # Instructions
    box = layout.box()
    box.label(text="Instructions:", icon='INFO')
    col = box.column(align=True)
    col.label(text="1. Select edges in Edit Mode")
    col.label(text="2. Click 'Convert Edges to Curves'")
    col.label(text="3. Curves will be linear")
    col.label(text="4. Closed loops become cyclic")


def unregister():
    # Unregister classes
    bpy.utils.unregister_class(MESH_PT_edge_to_curve_panel)
    bpy.utils.unregister_class(MESH_OT_edge_to_curve_with_settings)
    bpy.utils.unregister_class(MESH_OT_edge_to_curve)
    
    # Remove scene properties
    del bpy.types.Scene.edge_to_curve_collection
    del bpy.types.Scene.edge_to_curve_hide_original


if __name__ == "__main__":
    register()
