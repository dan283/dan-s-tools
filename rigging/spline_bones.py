bl_info = {
    "name": "Spline Bones",
    "author": "Assistant",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > N-Panel > Spline Bones",
    "description": "Create bone chains along selected edges with adjustable parameters",
    "category": "Rigging",
}

import bpy
import bmesh
from mathutils import Vector
from bpy.props import IntProperty, FloatProperty, BoolProperty
from bpy.types import Panel, Operator, PropertyGroup

class SplineBonesProperties(PropertyGroup):
    bone_count: IntProperty(
        name="Number of Bones",
        description="Number of bones to create along the edge chain",
        default=5,
        min=1,
        max=50,
        update=lambda self, context: update_bones(self, context)
    )
    
    normal_offset: FloatProperty(
        name="Normal Offset",
        description="Offset bones along face normals",
        default=0.0,
        min=-10.0,
        max=10.0,
        step=0.1,
        precision=3,
        update=lambda self, context: update_bones(self, context)
    )
    
    auto_update: BoolProperty(
        name="Auto Update",
        description="Automatically update bones when parameters change",
        default=True
    )
    
    flip_direction: BoolProperty(
        name="Flip Direction",
        description="Reverse the direction of the bone chain",
        default=False,
        update=lambda self, context: update_bones(self, context)
    )
    
    armature_name: bpy.props.StringProperty(
        name="Armature Name",
        default="SplineBones_Armature"
    )

def get_edge_chain_from_selection(mesh_obj):
    """Extract ordered edge chain from selected edges"""
    bpy.context.view_layer.objects.active = mesh_obj
    bpy.ops.object.mode_set(mode='EDIT')
    
    # Get bmesh representation
    bm = bmesh.new()
    bm.from_mesh(mesh_obj.data)
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    
    # Get selected edges
    selected_edges = [e for e in bm.edges if e.select]
    
    if not selected_edges:
        bm.free()
        return []
    
    # Build adjacency list
    edge_dict = {}
    for edge in selected_edges:
        v1, v2 = edge.verts
        if v1.index not in edge_dict:
            edge_dict[v1.index] = []
        if v2.index not in edge_dict:
            edge_dict[v2.index] = []
        edge_dict[v1.index].append((v2.index, edge))
        edge_dict[v2.index].append((v1.index, edge))
    
    # Find start vertex (vertex with only one connection, or any vertex if loop)
    start_vert = None
    for vert_idx, connections in edge_dict.items():
        if len(connections) == 1:
            start_vert = vert_idx
            break
    
    if start_vert is None:  # Closed loop
        start_vert = list(edge_dict.keys())[0]
    
    # Build ordered chain
    chain = []
    current_vert = start_vert
    prev_vert = None
    
    while current_vert in edge_dict:
        connections = edge_dict[current_vert]
        next_vert = None
        
        for vert_idx, edge in connections:
            if vert_idx != prev_vert:
                next_vert = vert_idx
                # Store vertex position and normal
                vert = bm.verts[current_vert]
                world_pos = mesh_obj.matrix_world @ vert.co
                world_normal = mesh_obj.matrix_world.to_3x3() @ vert.normal
                world_normal.normalize()
                chain.append((world_pos, world_normal))
                break
        
        if next_vert is None or next_vert == start_vert:  # End of chain or closed loop
            if next_vert == start_vert and len(chain) > 2:  # Closed loop, don't duplicate start
                break
            # Add final vertex if not a closed loop
            if next_vert != start_vert:
                vert = bm.verts[current_vert]
                world_pos = mesh_obj.matrix_world @ vert.co
                world_normal = mesh_obj.matrix_world.to_3x3() @ vert.normal
                world_normal.normalize()
                if len(chain) == 0 or (world_pos - chain[-1][0]).length > 0.001:
                    chain.append((world_pos, world_normal))
            break
        
        prev_vert = current_vert
        current_vert = next_vert
    
    # Add final vertex
    if current_vert in bm.verts:
        vert = bm.verts[current_vert]
        world_pos = mesh_obj.matrix_world @ vert.co
        world_normal = mesh_obj.matrix_world.to_3x3() @ vert.normal
        world_normal.normalize()
        chain.append((world_pos, world_normal))
    
    bm.free()
    return chain

def create_bones_along_chain(chain, bone_count, normal_offset, armature_name, flip_direction=False):
    """Create armature with bones along the chain"""
    if len(chain) < 2:
        return None
    
    # Flip the chain if requested
    if flip_direction:
        chain = list(reversed(chain))
    
    # Remove existing armature if it exists
    if armature_name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[armature_name], do_unlink=True)
    
    # Create armature
    armature = bpy.data.armatures.new(armature_name)
    armature_obj = bpy.data.objects.new(armature_name, armature)
    bpy.context.collection.objects.link(armature_obj)
    
    # Enter edit mode for armature
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='EDIT')
    
    # Calculate positions along chain
    total_length = 0
    for i in range(len(chain) - 1):
        total_length += (chain[i+1][0] - chain[i][0]).length
    
    if total_length == 0:
        return armature_obj
    
    # Create bones - create exactly the number requested
    for i in range(bone_count):
        bone = armature.edit_bones.new(f"Bone.{i+1:03d}")
        
        # Calculate head position along chain
        t_head = i / max(1, bone_count - 1) if bone_count > 1 else 0
        target_length_head = t_head * total_length
        
        # Find head position along chain
        current_length = 0
        head_pos = chain[0][0]
        head_normal = chain[0][1]
        
        for j in range(len(chain) - 1):
            segment_length = (chain[j+1][0] - chain[j][0]).length
            if current_length + segment_length >= target_length_head:
                # Interpolate within this segment
                segment_t = (target_length_head - current_length) / segment_length if segment_length > 0 else 0
                head_pos = chain[j][0].lerp(chain[j+1][0], segment_t)
                head_normal = chain[j][1].lerp(chain[j+1][1], segment_t).normalized()
                break
            current_length += segment_length
        
        # Apply normal offset to head
        bone.head = head_pos + head_normal * normal_offset
        
        # Calculate tail position
        if i < bone_count - 1:
            # Not the last bone - tail goes to next bone position
            t_tail = (i + 1) / max(1, bone_count - 1) if bone_count > 1 else 1
            target_length_tail = t_tail * total_length
            
            # Find tail position along chain
            current_length = 0
            tail_pos = chain[0][0]
            tail_normal = chain[0][1]
            
            for j in range(len(chain) - 1):
                segment_length = (chain[j+1][0] - chain[j][0]).length
                if current_length + segment_length >= target_length_tail:
                    # Interpolate within this segment
                    segment_t = (target_length_tail - current_length) / segment_length if segment_length > 0 else 0
                    tail_pos = chain[j][0].lerp(chain[j+1][0], segment_t)
                    tail_normal = chain[j][1].lerp(chain[j+1][1], segment_t).normalized()
                    break
                current_length += segment_length
            
            bone.tail = tail_pos + tail_normal * normal_offset
        else:
            # Last bone - extend in the direction of the chain
            if len(chain) >= 2:
                # Use the direction from second-to-last to last point
                direction = (chain[-1][0] - chain[-2][0]).normalized()
                bone_length = (chain[-1][0] - chain[-2][0]).length / max(1, bone_count - 1) if bone_count > 1 else 0.1
                bone.tail = bone.head + direction * bone_length
            else:
                # Fallback for single point
                bone.tail = bone.head + Vector((0, 0, 0.1))
        
        # Parent to previous bone
        if i > 0:
            bone.parent = armature.edit_bones[f"Bone.{i:03d}"]
    
    bpy.ops.object.mode_set(mode='OBJECT')
    return armature_obj

def update_bones(self, context):
    """Update bones when properties change"""
    if not self.auto_update:
        return
    
    # Get the current armature and its stored chain data
    props = context.scene.spline_bones_props
    armature_name = props.armature_name
    
    if not hasattr(bpy.types.Scene, '_spline_bones_data_dict'):
        return
    
    if armature_name not in bpy.types.Scene._spline_bones_data_dict:
        return
    
    chain_data = bpy.types.Scene._spline_bones_data_dict[armature_name]
    create_bones_along_chain(
        chain_data, 
        props.bone_count, 
        props.normal_offset, 
        armature_name,
        props.flip_direction
    )

class MESH_OT_create_spline_bones(Operator):
    """Create bones along selected edges"""
    bl_idname = "mesh.create_spline_bones"
    bl_label = "Create Spline Bones"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        if context.active_object is None or context.active_object.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        mesh_obj = context.active_object
        props = context.scene.spline_bones_props
        
        # Auto-increment armature name if it already exists
        base_name = "SplineBones_Armature"
        armature_name = base_name
        counter = 1
        while armature_name in bpy.data.objects:
            counter += 1
            armature_name = f"{base_name}_{counter:03d}"
        
        # Update the armature name in properties
        props.armature_name = armature_name
        
        # Get edge chain
        chain = get_edge_chain_from_selection(mesh_obj)
        
        if not chain:
            self.report({'ERROR'}, "No edges selected or invalid edge selection")
            return {'CANCELLED'}
        
        # Store chain for updates (per armature name)
        if not hasattr(bpy.types.Scene, '_spline_bones_data_dict'):
            bpy.types.Scene._spline_bones_data_dict = {}
        bpy.types.Scene._spline_bones_data_dict[armature_name] = chain
        
        # Create bones
        armature_obj = create_bones_along_chain(
            chain, 
            props.bone_count, 
            props.normal_offset, 
            armature_name,
            props.flip_direction
        )
        
        if armature_obj:
            self.report({'INFO'}, f"Created {props.bone_count} bones along edge chain as '{armature_name}'")
        else:
            self.report({'ERROR'}, "Failed to create bones")
        
        return {'FINISHED'}

class MESH_OT_update_spline_bones(Operator):
    """Update existing spline bones"""
    bl_idname = "mesh.update_spline_bones"
    bl_label = "Update Bones"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.spline_bones_props
        armature_name = props.armature_name
        
        if not hasattr(bpy.types.Scene, '_spline_bones_data_dict'):
            self.report({'ERROR'}, "No bone chain data found. Create bones first.")
            return {'CANCELLED'}
            
        if armature_name not in bpy.types.Scene._spline_bones_data_dict:
            self.report({'ERROR'}, f"No chain data found for armature '{armature_name}'. Create bones first.")
            return {'CANCELLED'}
        
        chain_data = bpy.types.Scene._spline_bones_data_dict[armature_name]
        armature_obj = create_bones_along_chain(
            chain_data, 
            props.bone_count, 
            props.normal_offset, 
            armature_name,
            props.flip_direction
        )
        
        if armature_obj:
            self.report({'INFO'}, f"Updated {props.bone_count} bones")
        else:
            self.report({'ERROR'}, "Failed to update bones")
        
        return {'FINISHED'}

class VIEW3D_PT_spline_bones(Panel):
    """Spline Bones Panel"""
    bl_label = "Spline Bones"
    bl_idname = "VIEW3D_PT_spline_bones"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Spline Bones"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.spline_bones_props
        
        # Instructions
        box = layout.box()
        box.label(text="Instructions:", icon='INFO')
        box.label(text="1. Select edges/edge loops")
        box.label(text="2. Click 'Create Spline Bones'")
        box.label(text="3. Adjust parameters below")
        
        layout.separator()
        
        # Parameters
        layout.prop(props, "armature_name")
        layout.prop(props, "bone_count")
        layout.prop(props, "normal_offset")
        layout.prop(props, "flip_direction")
        layout.prop(props, "auto_update")
        
        layout.separator()
        
        # Buttons
        col = layout.column(align=True)
        col.operator("mesh.create_spline_bones", icon='BONE_DATA')
        if not props.auto_update:
            col.operator("mesh.update_spline_bones", icon='FILE_REFRESH')

classes = (
    SplineBonesProperties,
    MESH_OT_create_spline_bones,
    MESH_OT_update_spline_bones,
    VIEW3D_PT_spline_bones,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.spline_bones_props = bpy.props.PointerProperty(type=SplineBonesProperties)
    # Initialize dictionary to store chain data per armature
    bpy.types.Scene._spline_bones_data_dict = {}

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.spline_bones_props
    # Clean up chain data dictionary
    if hasattr(bpy.types.Scene, '_spline_bones_data_dict'):
        del bpy.types.Scene._spline_bones_data_dict

if __name__ == "__main__":
    register()
