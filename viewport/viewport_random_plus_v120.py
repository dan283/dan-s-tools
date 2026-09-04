bl_info = {
    "name": "Viewport Random Colors Plus",
    "author": "OpenAI",
    "version": (1, 2, 0),
    "blender": (4, 0, 0),
    "location": "3D Viewport > Viewport Shading popover",
    "description": "Adds deterministic viewport colors with a hue range plus direct saturation and brightness controls",
    "category": "3D View",
}

import bpy
import colorsys
import hashlib
from bpy.types import Operator, PropertyGroup
from bpy.props import BoolProperty, FloatProperty, IntProperty, PointerProperty


def stable_random_01(text: str, salt: str = "") -> float:
    h = hashlib.sha256((salt + "|" + text).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") / float(2**64 - 1)


def iter_colorable_objects(scene):
    for obj in scene.objects:
        if obj.type in {
            'MESH', 'CURVE', 'SURFACE', 'META', 'FONT',
            'VOLUME', 'GREASEPENCIL', 'POINTCLOUD'
        }:
            yield obj


def apply_random_plus(scene, settings):
    """Assign deterministic HSV colors to object.color.

    Hue is distributed across the requested range. Saturation and Value are
    direct values, not random ranges: 1.0 means fully saturated / fully bright.
    """
    objects = list(iter_colorable_objects(scene))
    if not objects:
        return

    hue_width = max(0.0, min(1.0, settings.hue_range))
    saturation = max(0.0, min(1.0, settings.saturation))
    value = max(0.0, min(1.0, settings.value))

    # Stable order keeps neighboring hues distributed predictably while Seed
    # only changes which object gets which hue.
    objects.sort(key=lambda o: stable_random_01(o.name_full, f"order{settings.seed}"))
    count = len(objects)

    for i, obj in enumerate(objects):
        if hue_width <= 0.0:
            hue = 0.0
        elif count == 1:
            hue = 0.0
        elif hue_width >= 0.999999:
            # Cover the complete HSV wheel starting exactly at red. Dividing by
            # count (rather than count-1) avoids duplicating red at both ends.
            hue = i / count
        else:
            # A true hue interval starting at red and extending clockwise.
            # This makes Hue Range intuitive: 0.1667 reaches yellow, 0.3333
            # reaches green, 0.5 cyan, 0.6667 blue, 0.8333 magenta, 1.0 full wheel.
            hue = (i / max(1, count - 1)) * hue_width

        r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
        obj.color = (r, g, b, 1.0)

    # Object color mode is required to display the generated colors.
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                try:
                    area.spaces.active.shading.color_type = 'OBJECT'
                except Exception:
                    pass

def update_random_plus(self, context):
    if self.enabled and context and context.scene:
        apply_random_plus(context.scene, self)


def update_enabled(self, context):
    if not context or not context.scene:
        return
    if self.enabled:
        apply_random_plus(context.scene, self)


class VRCP_Settings(PropertyGroup):
    enabled: BoolProperty(
        name="Enable Random Colors+",
        description="Enable the extended random viewport color controls",
        default=False,
        update=update_enabled,
    )

    hue_range: FloatProperty(
        name="Hue Range",
        description="Hue interval starting at red. 1.0 covers the complete red-yellow-green-cyan-blue-magenta wheel",
        min=0.0,
        max=1.0,
        default=1.0,
        subtype='FACTOR',
        update=update_random_plus,
    )

    saturation: FloatProperty(
        name="Saturation",
        description="Direct saturation for every generated color. 1.0 = fully saturated",
        min=0.0,
        max=1.0,
        default=1.0,
        subtype='FACTOR',
        update=update_random_plus,
    )

    value: FloatProperty(
        name="Value / Brightness",
        description="Direct HSV value for every generated color. 1.0 = maximum brightness",
        min=0.0,
        max=1.0,
        default=1.0,
        subtype='FACTOR',
        update=update_random_plus,
    )

    seed: IntProperty(
        name="Seed",
        description="Generate a different stable color assignment",
        default=0,
        min=0,
        max=999999,
        update=update_random_plus,
    )


class VIEW3D_OT_random_plus_apply(Operator):
    bl_idname = "view3d.random_plus_apply"
    bl_label = "Apply Random+ Colors"
    bl_description = "Generate wide-range random colors and use Object color mode"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.vrcp_settings
        settings.enabled = True
        apply_random_plus(context.scene, settings)
        return {'FINISHED'}


class VIEW3D_OT_random_plus_new_seed(Operator):
    bl_idname = "view3d.random_plus_new_seed"
    bl_label = "New Random Seed"
    bl_description = "Generate another random color arrangement"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.vrcp_settings
        settings.seed = (settings.seed + 1) % 1000000
        if settings.enabled:
            apply_random_plus(context.scene, settings)
        return {'FINISHED'}


def draw_random_plus(self, context):
    scene = context.scene
    if not scene or not hasattr(scene, "vrcp_settings"):
        return

    settings = scene.vrcp_settings
    layout = self.layout

    shading = getattr(context.space_data, "shading", None)
    if not shading or shading.type != 'SOLID':
        return

    layout.separator()
    box = layout.box()

    # Explicit checkbox, rather than a toggle-style button.
    box.prop(settings, "enabled", text="Enable Random Colors+")

    col = box.column(align=True)
    col.enabled = settings.enabled
    col.prop(settings, "hue_range", slider=True)
    col.prop(settings, "saturation", slider=True)
    col.prop(settings, "value", slider=True)

    row = col.row(align=True)
    row.prop(settings, "seed")
    row.operator("view3d.random_plus_new_seed", text="", icon='FILE_REFRESH')

    if settings.enabled:
        if shading.color_type != 'OBJECT':
            col.operator("view3d.random_plus_apply", text="Use Random+", icon='CHECKMARK')
        else:
            col.label(text="Saturation/Value are direct values", icon='INFO')


classes = (
    VRCP_Settings,
    VIEW3D_OT_random_plus_apply,
    VIEW3D_OT_random_plus_new_seed,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.vrcp_settings = PointerProperty(type=VRCP_Settings)

    if hasattr(bpy.types, "VIEW3D_PT_shading"):
        bpy.types.VIEW3D_PT_shading.append(draw_random_plus)


def unregister():
    if hasattr(bpy.types, "VIEW3D_PT_shading"):
        try:
            bpy.types.VIEW3D_PT_shading.remove(draw_random_plus)
        except Exception:
            pass

    if hasattr(bpy.types.Scene, "vrcp_settings"):
        del bpy.types.Scene.vrcp_settings

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
