bl_info = {
    "name": "Turntable Camera Text Overlay",
    "author": "OpenAI",
    "version": (1, 5, 1),
    "blender": (4, 0, 0),
    "location": "View3D > N Panel > Turntable Text",
    "description": "Camera-attached text overlays with frame ranges, anchor placement, camera-local offsets, duplication, color, size, and rotation correction.",
    "category": "Animation",
}

import bpy
from bpy.app.handlers import persistent
from bpy.props import (
    StringProperty,
    IntProperty,
    FloatProperty,
    FloatVectorProperty,
    BoolProperty,
    EnumProperty,
    CollectionProperty,
    PointerProperty,
)
from bpy.types import (
    Operator,
    Panel,
    PropertyGroup,
    UIList,
)

ADDON_COLLECTION_NAME = "TT_Text_Overlays"


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def get_overlay_collection(scene):
    coll = bpy.data.collections.get(ADDON_COLLECTION_NAME)
    if coll is None:
        coll = bpy.data.collections.new(ADDON_COLLECTION_NAME)
        scene.collection.children.link(coll)
    return coll


def get_active_camera(scene):
    return scene.camera


def ensure_text_material(item):
    mat_name = f"TT_TextMat_{item.uid}"
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(name=mat_name)

    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links

    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)

    emission = nodes.new("ShaderNodeEmission")
    emission.location = (0, 0)
    emission.inputs["Color"].default_value = (
        item.color[0],
        item.color[1],
        item.color[2],
        1.0,
    )
    emission.inputs["Strength"].default_value = 1.0

    links.new(emission.outputs["Emission"], out.inputs["Surface"])

    if hasattr(mat, "use_backface_culling"):
        mat.use_backface_culling = False

    if hasattr(mat, "blend_method"):
        try:
            mat.blend_method = 'BLEND'
        except Exception:
            pass

    if hasattr(mat, "surface_render_method"):
        try:
            mat.surface_render_method = 'DITHERED'
        except Exception:
            pass

    if hasattr(mat, "shadow_method"):
        try:
            mat.shadow_method = 'NONE'
        except Exception:
            pass

    if hasattr(mat, "use_shadow"):
        try:
            mat.use_shadow = False
        except Exception:
            pass

    return mat


def find_text_object(item):
    if not item.object_name:
        return None
    return bpy.data.objects.get(item.object_name)


def force_text_face_camera(text_obj, settings):
    text_obj.rotation_mode = 'XYZ'
    text_obj.rotation_euler = (
        settings.face_rot_x,
        settings.face_rot_y,
        settings.face_rot_z,
    )


def camera_frame_at_depth(scene, camera_obj, depth):
    """
    Returns min_x, max_x, min_y, max_y in camera local space
    at a given positive depth in front of the camera.
    """
    cam = camera_obj.data
    frame = cam.view_frame(scene=scene)

    z0 = frame[0].z
    if abs(z0) < 1e-8:
        scale = 1.0
    else:
        scale = (-depth / z0)

    pts = [v * scale for v in frame]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]

    return min(xs), max(xs), min(ys), max(ys)


def get_anchor_position(scene, camera_obj, item):
    """
    Base anchor position in camera local coordinates.
    Offset XYZ is added on top of this later.
    """
    depth = 1.0
    min_x, max_x, min_y, max_y = camera_frame_at_depth(scene, camera_obj, depth)

    if item.anchor == 'TOP':
        return 0.0, max_y, -depth
    elif item.anchor == 'BOTTOM':
        return 0.0, min_y, -depth
    elif item.anchor == 'LEFT':
        return min_x, 0.0, -depth
    elif item.anchor == 'RIGHT':
        return max_x, 0.0, -depth
    elif item.anchor == 'CENTER':
        return 0.0, 0.0, -depth

    return 0.0, 0.0, -depth


def position_text_object(scene, camera_obj, text_obj, item, settings):
    if text_obj.parent != camera_obj:
        text_obj.parent = camera_obj
        text_obj.matrix_parent_inverse = camera_obj.matrix_world.inverted()

    font_data = text_obj.data
    font_data.align_y = 'CENTER'

    if item.anchor in {'TOP', 'BOTTOM', 'CENTER'}:
        font_data.align_x = 'CENTER'
    elif item.anchor == 'LEFT':
        font_data.align_x = 'LEFT'
    elif item.anchor == 'RIGHT':
        font_data.align_x = 'RIGHT'

    base_x, base_y, base_z = get_anchor_position(scene, camera_obj, item)

    x = base_x + item.offset_x
    y = base_y + item.offset_y
    z = base_z + item.offset_z

    text_obj.location = (x, y, z)
    text_obj.scale = (1.0, 1.0, 1.0)

    force_text_face_camera(text_obj, settings)


def update_item_visibility(scene, item):
    obj = find_text_object(item)
    if obj is None:
        return

    f = scene.frame_current
    visible = item.enabled and (item.start_frame <= f <= item.end_frame)

    obj.hide_viewport = not visible
    obj.hide_render = not visible


def apply_text_item(scene, item):
    settings = scene.tt_text_settings
    cam = get_active_camera(scene)
    if cam is None or cam.type != 'CAMERA':
        return

    coll = get_overlay_collection(scene)

    obj = find_text_object(item)
    if obj is None:
        curve = bpy.data.curves.new(name=f"TT_Text_{item.uid}", type='FONT')
        obj = bpy.data.objects.new(name=f"TT_Text_{item.uid}", object_data=curve)
        coll.objects.link(obj)
        item.object_name = obj.name

    obj.name = f"TT_Text_{item.uid}"
    item.object_name = obj.name

    font_data = obj.data
    font_data.body = item.text
    font_data.size = item.size
    font_data.extrude = 0.0
    font_data.bevel_depth = 0.0
    font_data.space_character = 1.0
    font_data.align_y = 'CENTER'

    mat = ensure_text_material(item)
    if len(obj.data.materials) == 0:
        obj.data.materials.append(mat)
    else:
        obj.data.materials[0] = mat

    obj.color = (item.color[0], item.color[1], item.color[2], 1.0)
    obj.show_in_front = True

    if hasattr(obj, "visible_shadow"):
        try:
            obj.visible_shadow = False
        except Exception:
            pass

    position_text_object(scene, cam, obj, item, settings)
    update_item_visibility(scene, item)


def apply_all_items(scene):
    for item in scene.tt_text_items:
        apply_text_item(scene, item)


def remove_item_object(item):
    obj = find_text_object(item)
    if obj is not None:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data and data.users == 0:
            bpy.data.curves.remove(data, do_unlink=True)

    item.object_name = ""


def generate_uid(scene):
    settings = scene.tt_text_settings
    settings.uid_counter += 1
    return str(settings.uid_counter)


def copy_item_settings(src, dst):
    dst.enabled = src.enabled
    dst.name_label = f"{src.name_label} Copy"
    dst.text = src.text
    dst.start_frame = src.start_frame
    dst.end_frame = src.end_frame
    dst.anchor = src.anchor
    dst.offset_x = src.offset_x
    dst.offset_y = src.offset_y
    dst.offset_z = src.offset_z
    dst.size = src.size
    dst.color = src.color[:]


# ------------------------------------------------------------
# Property callbacks
# ------------------------------------------------------------

def on_item_changed(self, context):
    scene = context.scene
    if scene is None:
        return
    try:
        apply_text_item(scene, self)
    except Exception as e:
        print(f"[Turntable Text] Update failed: {e}")


def on_settings_changed(self, context):
    scene = context.scene
    if scene is None:
        return
    try:
        apply_all_items(scene)
    except Exception as e:
        print(f"[Turntable Text] Settings update failed: {e}")


# ------------------------------------------------------------
# Properties
# ------------------------------------------------------------

class TT_TextItem(PropertyGroup):
    uid: StringProperty(default="")

    enabled: BoolProperty(
        name="Enabled",
        default=True,
        update=on_item_changed,
    )

    name_label: StringProperty(
        name="Label",
        default="Text",
        update=on_item_changed,
    )

    text: StringProperty(
        name="Text",
        default="Sample Text",
        update=on_item_changed,
    )

    start_frame: IntProperty(
        name="Start",
        default=1,
        update=on_item_changed,
    )

    end_frame: IntProperty(
        name="End",
        default=100,
        update=on_item_changed,
    )

    anchor: EnumProperty(
        name="Placement",
        items=[
            ('TOP', "Top", ""),
            ('BOTTOM', "Bottom", ""),
            ('LEFT', "Left", ""),
            ('RIGHT', "Right", ""),
            ('CENTER', "Center", ""),
        ],
        default='BOTTOM',
        update=on_item_changed,
    )

    offset_x: FloatProperty(
        name="Offset X",
        default=0.0,
        description="Camera local X offset",
        update=on_item_changed,
    )

    offset_y: FloatProperty(
        name="Offset Y",
        default=0.0,
        description="Camera local Y offset",
        update=on_item_changed,
    )

    offset_z: FloatProperty(
        name="Offset Z",
        default=0.0,
        description="Camera local Z offset",
        update=on_item_changed,
    )

    size: FloatProperty(
        name="Size",
        default=0.18,
        min=0.001,
        soft_max=5.0,
        update=on_item_changed,
    )

    color: FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        size=3,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0),
        update=on_item_changed,
    )

    object_name: StringProperty(default="")


class TT_TextSettings(PropertyGroup):
    face_rot_x: FloatProperty(
        name="Face Rot X",
        default=1.57079632679,
        update=on_settings_changed,
        description="Local X rotation correction in radians",
    )

    face_rot_y: FloatProperty(
        name="Face Rot Y",
        default=0.0,
        update=on_settings_changed,
        description="Local Y rotation correction in radians",
    )

    face_rot_z: FloatProperty(
        name="Face Rot Z",
        default=0.0,
        update=on_settings_changed,
        description="Local Z rotation correction in radians",
    )

    active_index: IntProperty(default=0)
    uid_counter: IntProperty(default=0)


# ------------------------------------------------------------
# UI list
# ------------------------------------------------------------

class TT_UL_text_items(UIList):
    def draw_item(
        self, context, layout, data, item, icon, active_data, active_propname, index
    ):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "enabled", text="")
            row.prop(item, "name_label", text="", emboss=False, icon='FONT_DATA')
            row.label(text=f"{item.start_frame}-{item.end_frame}")
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon='FONT_DATA')


# ------------------------------------------------------------
# Operators
# ------------------------------------------------------------

class TT_OT_add_text(Operator):
    bl_idname = "tt_text.add_text"
    bl_label = "Add Text"
    bl_description = "Add a new camera text overlay"

    def execute(self, context):
        scene = context.scene
        item = scene.tt_text_items.add()
        item.uid = generate_uid(scene)
        item.name_label = f"Text {len(scene.tt_text_items)}"
        item.text = "Sample Text"
        item.start_frame = scene.frame_start
        item.end_frame = scene.frame_end
        item.anchor = 'BOTTOM'
        item.offset_x = 0.0
        item.offset_y = 0.0
        item.offset_z = 0.0
        item.size = 0.18
        item.color = (1.0, 1.0, 1.0)

        scene.tt_text_settings.active_index = len(scene.tt_text_items) - 1
        apply_text_item(scene, item)
        return {'FINISHED'}


class TT_OT_duplicate_text(Operator):
    bl_idname = "tt_text.duplicate_text"
    bl_label = "Duplicate Text"
    bl_description = "Duplicate selected text item with same settings"

    @classmethod
    def poll(cls, context):
        scene = context.scene
        idx = scene.tt_text_settings.active_index
        return 0 <= idx < len(scene.tt_text_items)

    def execute(self, context):
        scene = context.scene
        idx = scene.tt_text_settings.active_index
        src = scene.tt_text_items[idx]

        new_item = scene.tt_text_items.add()
        new_item.uid = generate_uid(scene)
        copy_item_settings(src, new_item)
        new_item.object_name = ""

        scene.tt_text_settings.active_index = len(scene.tt_text_items) - 1
        apply_text_item(scene, new_item)
        return {'FINISHED'}


class TT_OT_remove_text(Operator):
    bl_idname = "tt_text.remove_text"
    bl_label = "Remove Text"
    bl_description = "Remove selected camera text overlay"

    @classmethod
    def poll(cls, context):
        return len(context.scene.tt_text_items) > 0

    def execute(self, context):
        scene = context.scene
        idx = scene.tt_text_settings.active_index

        if 0 <= idx < len(scene.tt_text_items):
            item = scene.tt_text_items[idx]
            remove_item_object(item)
            scene.tt_text_items.remove(idx)

            if len(scene.tt_text_items) == 0:
                scene.tt_text_settings.active_index = 0
            else:
                scene.tt_text_settings.active_index = min(idx, len(scene.tt_text_items) - 1)

        return {'FINISHED'}


class TT_OT_sync_all(Operator):
    bl_idname = "tt_text.sync_all"
    bl_label = "Sync All"
    bl_description = "Rebuild/update all text objects"

    def execute(self, context):
        apply_all_items(context.scene)
        return {'FINISHED'}


class TT_OT_move_item(Operator):
    bl_idname = "tt_text.move_item"
    bl_label = "Move Item"

    direction: EnumProperty(
        items=[
            ('UP', "Up", ""),
            ('DOWN', "Down", ""),
        ]
    )

    @classmethod
    def poll(cls, context):
        return len(context.scene.tt_text_items) > 1

    def execute(self, context):
        scene = context.scene
        idx = scene.tt_text_settings.active_index
        items = scene.tt_text_items

        if self.direction == 'UP' and idx > 0:
            items.move(idx, idx - 1)
            scene.tt_text_settings.active_index -= 1
        elif self.direction == 'DOWN' and idx < len(items) - 1:
            items.move(idx, idx + 1)
            scene.tt_text_settings.active_index += 1

        return {'FINISHED'}


class TT_OT_cleanup_missing(Operator):
    bl_idname = "tt_text.cleanup_missing"
    bl_label = "Cleanup Missing"
    bl_description = "Clear broken object references"

    def execute(self, context):
        scene = context.scene
        for item in scene.tt_text_items:
            if item.object_name and bpy.data.objects.get(item.object_name) is None:
                item.object_name = ""
        self.report({'INFO'}, "Missing references cleaned")
        return {'FINISHED'}


# ------------------------------------------------------------
# Panel
# ------------------------------------------------------------

class TT_PT_panel(Panel):
    bl_label = "Turntable Text"
    bl_idname = "TT_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Turntable Text"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.tt_text_settings

        cam = scene.camera
        if cam is None:
            box = layout.box()
            box.label(text="No active camera on scene.", icon='ERROR')
            box.label(text="Set a scene camera first.")
            return

        box = layout.box()
        box.label(text="Global Settings")
        box.prop(settings, "face_rot_x")
        box.prop(settings, "face_rot_y")
        box.prop(settings, "face_rot_z")

        row = layout.row()
        row.template_list(
            "TT_UL_text_items",
            "",
            scene,
            "tt_text_items",
            settings,
            "active_index",
            rows=5,
        )

        btn_col = row.column(align=True)
        btn_col.operator("tt_text.add_text", text="", icon='ADD')
        btn_col.operator("tt_text.remove_text", text="", icon='REMOVE')
        btn_col.operator("tt_text.duplicate_text", text="", icon='DUPLICATE')
        btn_col.separator()
        btn_col.operator("tt_text.move_item", text="", icon='TRIA_UP').direction = 'UP'
        btn_col.operator("tt_text.move_item", text="", icon='TRIA_DOWN').direction = 'DOWN'

        row = layout.row(align=True)
        row.operator("tt_text.sync_all", icon='FILE_REFRESH')
        row.operator("tt_text.cleanup_missing", icon='TRASH')

        if 0 <= settings.active_index < len(scene.tt_text_items):
            item = scene.tt_text_items[settings.active_index]

            box = layout.box()
            box.prop(item, "enabled")
            box.prop(item, "name_label")
            box.prop(item, "text")

            row = box.row(align=True)
            row.prop(item, "start_frame")
            row.prop(item, "end_frame")

            box.prop(item, "anchor", text="Placement")

            col = box.column(align=True)
            col.label(text="Camera Local Offset")
            col.prop(item, "offset_x")
            col.prop(item, "offset_y")
            col.prop(item, "offset_z")

            box.prop(item, "size")
            box.prop(item, "color")


# ------------------------------------------------------------
# Handlers
# ------------------------------------------------------------

@persistent
def tt_frame_change_handler(scene, depsgraph=None):
    if not hasattr(scene, "tt_text_items"):
        return

    settings = getattr(scene, "tt_text_settings", None)
    if settings is None:
        return

    cam = scene.camera
    if cam is None:
        return

    for item in scene.tt_text_items:
        obj = find_text_object(item)
        if obj is None:
            continue

        try:
            position_text_object(scene, cam, obj, item, settings)
        except Exception as e:
            print(f"[Turntable Text] Position update failed: {e}")

        update_item_visibility(scene, item)


def register_handler():
    handlers = bpy.app.handlers.frame_change_post
    if tt_frame_change_handler not in handlers:
        handlers.append(tt_frame_change_handler)


def unregister_handler():
    handlers = bpy.app.handlers.frame_change_post
    while tt_frame_change_handler in handlers:
        handlers.remove(tt_frame_change_handler)


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

classes = (
    TT_TextItem,
    TT_TextSettings,
    TT_UL_text_items,
    TT_OT_add_text,
    TT_OT_duplicate_text,
    TT_OT_remove_text,
    TT_OT_sync_all,
    TT_OT_move_item,
    TT_OT_cleanup_missing,
    TT_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.tt_text_items = CollectionProperty(type=TT_TextItem)
    bpy.types.Scene.tt_text_settings = PointerProperty(type=TT_TextSettings)

    register_handler()


def unregister():
    unregister_handler()

    del bpy.types.Scene.tt_text_settings
    del bpy.types.Scene.tt_text_items

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
