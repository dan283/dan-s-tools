import bpy
import bmesh
from mathutils import Matrix, Vector
import json

bl_info = {
    "name": "Face Normal Align to World Space",
    "author": "Assistant",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > N-Panel > Face Align",
    "description": "Align object to world space based on selected face normal",
    "category": "Mesh",
}

class MESH_OT_align_to_world_space(bpy.types.Operator):
    """Align object to world space based on selected face normal"""
    bl_idname = "mesh.align_to_world_space"
    bl_label = "Align to World Space"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and 
                context.active_object.type == 'MESH' and
                context.mode == 'EDIT_MESH')
    
    def execute(self, context):
        obj = context.active_object
        
        # Check if object is already aligned (toggle functionality)
        if "original_matrix_stored" in obj and obj["original_matrix_stored"]:
            return self.restore_original_transform(context)
        else:
            return self.align_to_face_normal(context)
    
    def align_to_face_normal(self, context):
        obj = context.active_object
        
        # Store original transformation matrix
        obj["original_matrix"] = [list(row) for row in obj.matrix_world]
        obj["original_matrix_stored"] = True
        
        # Get bmesh representation from edit mode
        bm = bmesh.from_edit_mesh(obj.data)
        
        # Get selected faces
        selected_faces = [f for f in bm.faces if f.select]
        
        if not selected_faces:
            self.report({'WARNING'}, "No faces selected")
            return {'CANCELLED'}
        
        # Use the first selected face
        face = selected_faces[0]
        face_normal = face.normal.copy()
        face_center = face.calc_center_median()
        
        # Get face edge to determine tangent direction
        face_edges = face.edges
        if len(face_edges) > 0:
            edge_vec = (face_edges[0].verts[1].co - face_edges[0].verts[0].co).normalized()
        else:
            # Fallback if no edges (shouldn't happen for normal faces)
            edge_vec = Vector((1, 0, 0))
        
        # Create local coordinate system from face
        # Z-axis = face normal
        local_z = face_normal.normalized()
        
        # X-axis = edge direction projected onto face plane
        local_x = (edge_vec - edge_vec.project(local_z)).normalized()
        
        # Y-axis = cross product to complete right-handed system
        local_y = local_z.cross(local_x).normalized()
        
        # Transform to world space
        world_matrix = obj.matrix_world.to_3x3()
        world_z = (world_matrix @ local_z).normalized()
        world_x = (world_matrix @ local_x).normalized() 
        world_y = (world_matrix @ local_y).normalized()
        
        # Create rotation matrix to align face coordinate system with world axes
        # Face Z -> World Z, Face X -> World X, Face Y -> World Y
        target_x = Vector((1, 0, 0))  # World X
        target_y = Vector((0, 1, 0))  # World Y  
        target_z = Vector((0, 0, 1))  # World Z
        
        # Build rotation matrix from current face orientation to world orientation
        current_matrix = Matrix((
            world_x,
            world_y, 
            world_z
        )).transposed()
        
        target_matrix = Matrix((
            target_x,
            target_y,
            target_z
        )).transposed()
        
        # Calculate rotation needed
        rotation_matrix = target_matrix @ current_matrix.inverted()
        
        # Apply the rotation to the object
        rotation_4x4 = rotation_matrix.to_4x4()
        obj.matrix_world = rotation_4x4 @ obj.matrix_world
        
        # Update edit mesh
        bmesh.update_edit_mesh(obj.data)
        
        # Update scene
        context.view_layer.update()
        
        self.report({'INFO'}, "Object aligned to world space based on face normal")
        return {'FINISHED'}
    
    def restore_original_transform(self, context):
        obj = context.active_object
        
        # Restore original matrix
        if "original_matrix" in obj:
            original_matrix_data = obj["original_matrix"]
            original_matrix = Matrix([
                original_matrix_data[0],
                original_matrix_data[1], 
                original_matrix_data[2],
                original_matrix_data[3]
            ])
            obj.matrix_world = original_matrix
            
            # Clean up stored data
            del obj["original_matrix"]
            del obj["original_matrix_stored"]
            
            # Update scene
            context.view_layer.update()
            
            self.report({'INFO'}, "Object restored to original orientation")
        else:
            self.report({'WARNING'}, "No original transformation stored")
        
        return {'FINISHED'}

class VIEW3D_PT_face_align_panel(bpy.types.Panel):
    """Panel for Face Normal Align tools"""
    bl_label = "Face Align"
    bl_idname = "VIEW3D_PT_face_align"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Face Align"
    
    def draw(self, context):
        layout = self.layout
        
        obj = context.active_object
        
        if obj and obj.type == 'MESH' and context.mode == 'EDIT_MESH':
            # Check if object has stored transformation
            is_aligned = "original_matrix_stored" in obj and obj["original_matrix_stored"]
            
            if is_aligned:
                layout.operator("mesh.align_to_world_space", 
                              text="Restore Original", 
                              icon='LOOP_BACK')
                layout.label(text="Status: Aligned", icon='CHECKMARK')
            else:
                layout.operator("mesh.align_to_world_space", 
                              text="Align to World Space", 
                              icon='ORIENTATION_GLOBAL')
                layout.label(text="Status: Original", icon='ORIENTATION_LOCAL')
            
            layout.separator()
            layout.label(text="Instructions:")
            layout.label(text="1. Select a face in Edit mode")
            layout.label(text="2. Click align button")
            layout.label(text="3. Click again to restore")
        else:
            layout.label(text="Enter Edit mode and")
            layout.label(text="select a mesh object")

# Registration
classes = [
    MESH_OT_align_to_world_space,
    VIEW3D_PT_face_align_panel,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
