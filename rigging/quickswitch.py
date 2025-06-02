import bpy

class QuickSwitchProperties(bpy.types.PropertyGroup):
    object_a: bpy.props.PointerProperty(name="Object A", type=bpy.types.Object)
    object_b: bpy.props.PointerProperty(name="Object B (Armature)", type=bpy.types.Object)

class OBJECT_OT_quick_switch(bpy.types.Operator):
    bl_idname = "object.quick_switch"
    bl_label = "Switch"
    bl_description = "Switch between Object A (edit mode) and Object B (pose mode)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.quick_switch_props
        obj_a = props.object_a
        obj_b = props.object_b

        if not obj_a or not obj_b:
            self.report({'ERROR'}, "Both objects must be assigned.")
            return {'CANCELLED'}

        active_obj = context.active_object

        if active_obj == obj_a:
            bpy.ops.object.mode_set(mode='OBJECT')
            context.view_layer.objects.active = obj_b
            bpy.ops.object.mode_set(mode='EDIT')
        else:
            bpy.ops.object.mode_set(mode='OBJECT')
            context.view_layer.objects.active = obj_a
            bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}

class OBJECT_PT_quick_switch_panel(bpy.types.Panel):
    bl_label = "QuickSwitch"
    bl_idname = "OBJECT_PT_quick_switch_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "QuickSwitch"

    def draw(self, context):
        layout = self.layout
        props = context.scene.quick_switch_props

        layout.prop(props, "object_a")
        layout.prop(props, "object_b")
        layout.operator("object.quick_switch")

classes = [
    QuickSwitchProperties,
    OBJECT_OT_quick_switch,
    OBJECT_PT_quick_switch_panel
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.quick_switch_props = bpy.props.PointerProperty(type=QuickSwitchProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.quick_switch_props

if __name__ == "__main__":
    register()
