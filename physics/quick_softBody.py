bl_info = {
    "name": "Quick Soft Body Presets",
    "author": "ChatGPT Prototype",
    "version": (1, 4),
    "blender": (3, 0, 0),
    "location": "View3D > Tool Shelf > Quick Soft Body",
    "description": "Apply soft body physics with useful presets: rubber, slime, jello.",
    "category": "Physics"
}

import bpy
from bpy.props import EnumProperty

class QuickSoftBodyOperator(bpy.types.Operator):
    bl_idname = "object.quick_softbody"
    bl_label = "Apply Soft Body"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object.")
            return {'CANCELLED'}

        preset = context.scene.quick_softbody_preset

        if not obj.modifiers.get("Softbody"):
            modifier = obj.modifiers.new(name="Softbody", type='SOFT_BODY')

        sb = obj.modifiers["Softbody"].settings

        sb.use_goal = False  # Disable goal by default for natural deformation
        sb.use_edges = True

        if preset == 'RUBBER':
            sb.mass = 0.3
            sb.pull = 0.9
            sb.push = 0.9
            sb.damping = 0.7
            sb.bend = 10
        elif preset == 'SLIME':
            sb.mass = 2
            sb.pull = 0.35
            sb.push = 0.35
            sb.damping = 0.9
            sb.plastic = 100
            sb.bend = 0.6
        elif preset == 'JELLO':
            sb.mass = 0.4
            sb.pull = 0.5
            sb.push = 0.5
            sb.damping = 2.5  # Max damping to prevent bounce
            sb.plastic = 100
            sb.bend = 0.1       # Enough to retain shape

        return {'FINISHED'}

class QuickCollisionOperator(bpy.types.Operator):
    bl_idname = "object.quick_collision"
    bl_label = "Make Collision Object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object.")
            return {'CANCELLED'}

        if not obj.modifiers.get("Collision"):
            obj.modifiers.new(name="Collision", type='COLLISION')

        return {'FINISHED'}

class QuickSoftBodyPanel(bpy.types.Panel):
    bl_label = "Quick Soft Body"
    bl_idname = "VIEW3D_PT_quick_softbody"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Soft Body'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, "quick_softbody_preset", text="Preset")
        layout.operator("object.quick_softbody", text="Apply Soft Body")
        layout.separator()
        layout.operator("object.quick_collision", text="Make Collision")


def register():
    bpy.types.Scene.quick_softbody_preset = EnumProperty(
        name="Soft Body Preset",
        items=[
            ('RUBBER', "Rubber", "Stiff rubbery effect"),
            ('SLIME', "Slime", "Slow, heavy goo"),
            ('JELLO', "Jello", "Wobbly bouncy jello")
        ],
        default='RUBBER'
    )
    bpy.utils.register_class(QuickSoftBodyOperator)
    bpy.utils.register_class(QuickCollisionOperator)
    bpy.utils.register_class(QuickSoftBodyPanel)

def unregister():
    del bpy.types.Scene.quick_softbody_preset
    bpy.utils.unregister_class(QuickSoftBodyOperator)
    bpy.utils.unregister_class(QuickCollisionOperator)
    bpy.utils.unregister_class(QuickSoftBodyPanel)

if __name__ == "__main__":
    register()
