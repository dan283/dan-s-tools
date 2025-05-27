import bpy

class CopyTransformsProperties(bpy.types.PropertyGroup):
    source_prefix: bpy.props.StringProperty(name="Source Prefix")
    target_prefix: bpy.props.StringProperty(name="Target Prefix")

class COPYTRANSFORMS_PT_panel(bpy.types.Panel):
    bl_label = "Copy Transforms"
    bl_idname = "COPYTRANSFORMS_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CopyTools"

    def draw(self, context):
        layout = self.layout
        props = context.scene.copy_transforms_props

        layout.prop(props, "source_prefix")
        layout.prop(props, "target_prefix")
        layout.operator("object.copy_transforms_constraints")

class OBJECT_OT_CopyTransformsOperator(bpy.types.Operator):
    bl_idname = "object.copy_transforms_constraints"
    bl_label = "Copy Transforms"
    bl_description = "Add Copy Transforms constraint to bones with matching suffixes"

    def execute(self, context):
        props = context.scene.copy_transforms_props
        source_prefix = props.source_prefix
        target_prefix = props.target_prefix

        obj = context.object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Select an armature object in Pose Mode.")
            return {'CANCELLED'}

        if context.mode != 'POSE':
            self.report({'ERROR'}, "Must be in Pose Mode.")
            return {'CANCELLED'}

        for bone in obj.pose.bones:
            if not bone.name.startswith(target_prefix):
                continue

            suffix = bone.name[len(target_prefix):]
            source_bone_name = source_prefix + suffix

            constraint = bone.constraints.get("Copy Transforms")
            if not constraint:
                constraint = bone.constraints.new('COPY_TRANSFORMS')
                constraint.name = "Copy Transforms"

            constraint.target = obj
            constraint.subtarget = source_bone_name

        self.report({'INFO'}, "Constraints added.")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CopyTransformsProperties)
    bpy.utils.register_class(COPYTRANSFORMS_PT_panel)
    bpy.utils.register_class(OBJECT_OT_CopyTransformsOperator)
    bpy.types.Scene.copy_transforms_props = bpy.props.PointerProperty(type=CopyTransformsProperties)

def unregister():
    bpy.utils.unregister_class(CopyTransformsProperties)
    bpy.utils.unregister_class(COPYTRANSFORMS_PT_panel)
    bpy.utils.unregister_class(OBJECT_OT_CopyTransformsOperator)
    del bpy.types.Scene.copy_transforms_props

if __name__ == "__main__":
    register()
