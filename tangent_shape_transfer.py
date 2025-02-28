import bpy
import mathutils

class DeformationTransferProperties(bpy.types.PropertyGroup):
    neutral_mesh: bpy.props.PointerProperty(
        name="Neutral Mesh",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'MESH'
    )
    
    deformed_mesh: bpy.props.PointerProperty(
        name="Deformed Mesh",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'MESH'
    )

    target_mesh: bpy.props.PointerProperty(
        name="Target Mesh",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'MESH'
    )

class DeformationTransferOperator(bpy.types.Operator):
    """Transfer deformations from deformed to target as shape key"""
    bl_idname = "object.transfer_deformation"
    bl_label = "Transfer Deformation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.deformation_transfer_props
        neutral_mesh = props.neutral_mesh
        deformed_mesh = props.deformed_mesh
        target_mesh = props.target_mesh

        if not neutral_mesh or not deformed_mesh or not target_mesh:
            self.report({'ERROR'}, "Please select all three meshes.")
            return {'CANCELLED'}

        if len(neutral_mesh.data.vertices) != len(deformed_mesh.data.vertices) or \
           len(neutral_mesh.data.vertices) != len(target_mesh.data.vertices):
            self.report({'ERROR'}, "Meshes must have the same vertex count.")
            return {'CANCELLED'}

        self.apply_transfer(neutral_mesh, deformed_mesh, target_mesh)
        return {'FINISHED'}

    def apply_transfer(self, neutral_mesh, deformed_mesh, target_mesh):
        # Ensure the target mesh has a Basis shape key
        if not target_mesh.data.shape_keys:
            target_mesh.shape_key_add(name="Basis")

        # Create a new shape key on the target mesh
        shape_key = target_mesh.shape_key_add(name="Transferred Deformation")

        # Get transformation matrices
        neutral_to_local = neutral_mesh.matrix_world.inverted()
        deformed_to_local = deformed_mesh.matrix_world.inverted()
        target_to_local = target_mesh.matrix_world.inverted()

        # Compute deformation relative to normals
        for i, vert in enumerate(neutral_mesh.data.vertices):
            neutral_pos = neutral_to_local @ neutral_mesh.matrix_world @ vert.co
            deformed_pos = deformed_to_local @ deformed_mesh.matrix_world @ deformed_mesh.data.vertices[i].co

            # Offset in local space
            offset = deformed_pos - neutral_pos  

            # Compute normal-based transformation for correct orientation
            neutral_normal = neutral_mesh.data.vertices[i].normal
            target_normal = target_mesh.data.vertices[i].normal

            # Align offset direction to match the target mesh's normal
            rotation_matrix = neutral_normal.rotation_difference(target_normal).to_matrix()
            rotated_offset = rotation_matrix @ offset

            # Apply the transformed deformation
            target_vert_local = target_to_local @ target_mesh.matrix_world @ target_mesh.data.vertices[i].co
            shape_key.data[i].co = target_vert_local + rotated_offset  # Apply rotation-aware offset

class DeformationTransferPanel(bpy.types.Panel):
    """UI Panel in the N-panel"""
    bl_label = "Deformation Transfer"
    bl_idname = "OBJECT_PT_deformation_transfer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Deformation Transfer"

    def draw(self, context):
        layout = self.layout
        props = context.scene.deformation_transfer_props

        layout.label(text="Select Meshes:")
        layout.prop(props, "neutral_mesh")
        layout.prop(props, "deformed_mesh")
        layout.prop(props, "target_mesh")
        layout.operator("object.transfer_deformation")

classes = [
    DeformationTransferProperties,
    DeformationTransferOperator,
    DeformationTransferPanel
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.deformation_transfer_props = bpy.props.PointerProperty(type=DeformationTransferProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.deformation_transfer_props

if __name__ == "__main__":
    register()
