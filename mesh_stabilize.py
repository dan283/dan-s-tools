import bpy
import bmesh
from mathutils import Vector, Matrix

class StabilizeOperator(bpy.types.Operator):
    """Base class for stabilize operations"""
    bl_idname = "object.stabilize_operator"
    bl_label = "Stabilize Operator"
    operation: bpy.props.EnumProperty(
        items=[
            ('TRANSLATION', "Extract Translation", "Stabilize by translation"),
            ('ROTATION', "Extract Rotation", "Stabilize by rotation")
        ]
    )

    def execute(self, context):
        obj = context.object
        if obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a mesh")
            return {'CANCELLED'}

        # Ensure object is in object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        mesh = obj.data

        # Access selected vertices
        bm = bmesh.new()
        bm.from_mesh(mesh)
        selected_verts = [v for v in bm.verts if v.select]
        if not selected_verts:
            self.report({'ERROR'}, "No vertices selected")
            bm.free()
            return {'CANCELLED'}

        # Frame range
        frame_start = context.scene.frame_start
        frame_end = context.scene.frame_end
        original_frame = context.scene.frame_current

        # Perform operation
        if self.operation == 'TRANSLATION':
            self.stabilize_translation(context, obj, selected_verts, frame_start, frame_end)
        elif self.operation == 'ROTATION':
            self.stabilize_rotation(context, obj, selected_verts, frame_start, frame_end)

        # Cleanup
        bm.free()
        context.scene.frame_set(original_frame)
        return {'FINISHED'}

    def stabilize_translation(self, context, obj, selected_verts, frame_start, frame_end):
        for frame in range(frame_start, frame_end + 1):
            context.scene.frame_set(frame)
            avg_position = sum((obj.matrix_world @ v.co for v in selected_verts), Vector()) / len(selected_verts)
            obj.location -= avg_position
            obj.keyframe_insert(data_path="location", frame=frame)

    def stabilize_rotation(self, context, obj, selected_verts, frame_start, frame_end):
        for frame in range(frame_start, frame_end + 1):
            context.scene.frame_set(frame)
            avg_normal = sum((obj.matrix_world.to_3x3() @ v.normal for v in selected_verts), Vector()) / len(selected_verts)
            avg_normal.normalize()
            rotation = avg_normal.to_track_quat('Z', 'Y').to_matrix().to_4x4()
            obj.matrix_world = rotation @ obj.matrix_world
            obj.keyframe_insert(data_path="rotation_euler", frame=frame)

# UI Panel
class StabilizePanel(bpy.types.Panel):
    bl_label = "Stabilize"
    bl_idname = "OBJECT_PT_stabilize"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Stabilize'

    def draw(self, context):
        layout = self.layout
        layout.operator("object.stabilize_operator", text="Extract Translation").operation = 'TRANSLATION'
        layout.operator("object.stabilize_operator", text="Extract Rotation").operation = 'ROTATION'

# Registration
classes = [StabilizeOperator, StabilizePanel]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
