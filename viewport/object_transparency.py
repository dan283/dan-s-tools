bl_info = {
    "name": "Viewport Transparency",
    "author": "Dan / ChatGPT",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > View Transparency",
    "description": "Adjust viewport transparency of selected objects",
    "category": "3D View",
}

import bpy
from bpy.props import FloatProperty


# ------------------------------------------------------------
# UPDATE
# ------------------------------------------------------------

def update_transparency(self, context):

    alpha = self.viewport_transparency

    for obj in context.selected_objects:

        # Enable transparency display
        if hasattr(obj, "show_transparent"):
            obj.show_transparent = alpha < 1.0

        # Object viewport color
        color = list(obj.color)
        color[3] = alpha
        obj.color = color

    # Force viewport redraw
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


# ------------------------------------------------------------
# PROPERTIES
# ------------------------------------------------------------

class ViewportTransparencyProperties(bpy.types.PropertyGroup):

    viewport_transparency: FloatProperty(
        name="Opacity",
        description="Viewport opacity of selected objects",
        min=0.0,
        max=1.0,
        default=1.0,
        subtype='FACTOR',
        update=update_transparency,
    )


# ------------------------------------------------------------
# RESET
# ------------------------------------------------------------

class VIEW3D_OT_reset_transparency(bpy.types.Operator):

    bl_idname = "view3d.reset_transparency"
    bl_label = "Reset Opacity"
    bl_description = "Return selected objects to full opacity"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        props = context.scene.viewport_transparency_props
        props.viewport_transparency = 1.0

        for obj in context.selected_objects:
            color = list(obj.color)
            color[3] = 1.0
            obj.color = color

            if hasattr(obj, "show_transparent"):
                obj.show_transparent = False

        return {'FINISHED'}


# ------------------------------------------------------------
# PANEL
# ------------------------------------------------------------

class VIEW3D_PT_viewport_transparency(bpy.types.Panel):

    bl_label = "Viewport Transparency"
    bl_idname = "VIEW3D_PT_viewport_transparency"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "View Transparency"

    def draw(self, context):

        layout = self.layout
        props = context.scene.viewport_transparency_props

        layout.label(text="Selected Objects")

        layout.prop(
            props,
            "viewport_transparency",
            text="Opacity",
            slider=True
        )

        layout.operator(
            "view3d.reset_transparency",
            icon='LOOP_BACK'
        )

        if not context.selected_objects:
            box = layout.box()
            box.label(
                text="No objects selected",
                icon='INFO'
            )


# ------------------------------------------------------------
# REGISTER
# ------------------------------------------------------------

classes = (
    ViewportTransparencyProperties,
    VIEW3D_OT_reset_transparency,
    VIEW3D_PT_viewport_transparency,
)


def register():

    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.viewport_transparency_props = bpy.props.PointerProperty(
        type=ViewportTransparencyProperties
    )


def unregister():

    del bpy.types.Scene.viewport_transparency_props

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
