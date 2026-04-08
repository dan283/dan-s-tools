bl_info = {
    "name": "Transfer UVs Panel",
    "author": "OpenAI",
    "version": (2, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > UV Tools > Transfer UVs",
    "description": "Transfer UVs from one or more source meshes to a target mesh, including different topology workflows",
    "category": "UV",
}

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    PointerProperty,
    CollectionProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup, UIList


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def mesh_obj_poll(self, obj):
    return obj is not None and obj.type == 'MESH'


def collection_has_meshes(coll):
    return bool(coll and any(obj.type == 'MESH' for obj in coll.objects))


def ensure_object_mode():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def enum_items_for_rna(obj, prop_name):
    """Return allowed enum identifiers for an RNA property on this object."""
    try:
        prop = obj.bl_rna.properties[prop_name]
        return [item.identifier for item in prop.enum_items]
    except Exception:
        return []


def set_enum_if_supported(obj, prop_name, preferred_values):
    """
    Set the first supported enum value from preferred_values.
    Returns the value that was set, or None.
    """
    allowed = enum_items_for_rna(obj, prop_name)
    for value in preferred_values:
        if value in allowed:
            try:
                setattr(obj, prop_name, value)
                return value
            except Exception:
                pass
    return None


def get_selected_mesh_sources(context, target=None):
    objs = [o for o in context.selected_objects if o and o.type == 'MESH']
    if target:
        objs = [o for o in objs if o != target]
    return objs


def get_sources_from_list(scene):
    items = scene.uv_transfer_settings.source_items
    result = []
    seen = set()
    for item in items:
        obj = item.obj
        if obj and obj.type == 'MESH' and obj.name not in seen:
            result.append(obj)
            seen.add(obj.name)
    return result


def ensure_uv_layers_on_target(source_obj, target_obj, settings):
    if not settings.create_missing_uvs:
        return

    src_uvs = source_obj.data.uv_layers
    dst_uvs = target_obj.data.uv_layers
    if len(src_uvs) == 0:
        return

    if settings.uv_scope == 'ACTIVE':
        src_active = src_uvs.active
        if src_active is None:
            return

        if len(dst_uvs) == 0:
            dst_uvs.new(name=src_active.name)
        elif settings.dst_layer_behavior == 'BY_NAME':
            if src_active.name not in dst_uvs:
                dst_uvs.new(name=src_active.name)

    else:  # ALL
        if len(dst_uvs) == 0 and len(src_uvs) > 0:
            dst_uvs.new(name=src_uvs[0].name)

        if settings.dst_layer_behavior == 'BY_NAME':
            existing = {uv.name for uv in dst_uvs}
            for uv in src_uvs:
                if uv.name not in existing:
                    dst_uvs.new(name=uv.name)
        elif settings.dst_layer_behavior == 'BY_ORDER':
            while len(dst_uvs) < len(src_uvs):
                dst_uvs.new(name=src_uvs[len(dst_uvs)].name)


def duplicate_sources(context, source_objects):
    view_layer = context.view_layer
    prev_active = view_layer.objects.active
    prev_selection = list(context.selected_objects)

    bpy.ops.object.select_all(action='DESELECT')
    for obj in source_objects:
        obj.select_set(True)
    if source_objects:
        view_layer.objects.active = source_objects[0]

    bpy.ops.object.duplicate(linked=False)
    dupes = list(context.selected_objects)
    return dupes, prev_active, prev_selection


def build_temp_source(context, source_objects):
    dupes, prev_active, prev_selection = duplicate_sources(context, source_objects)
    view_layer = context.view_layer

    if not dupes:
        return None, [], prev_active, prev_selection

    bpy.ops.object.select_all(action='DESELECT')
    for obj in dupes:
        obj.select_set(True)
    view_layer.objects.active = dupes[0]

    if len(dupes) > 1:
        bpy.ops.object.join()
        temp_source = view_layer.objects.active
    else:
        temp_source = dupes[0]

    temp_source.name = "_TEMP_UV_TRANSFER_SOURCE"
    return temp_source, dupes, prev_active, prev_selection


def cleanup_temp_objects(context, all_dupes, prev_active=None, prev_selection=None):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in all_dupes:
        if obj and obj.name in bpy.data.objects:
            obj.select_set(True)
    if any(obj.select_get() for obj in bpy.data.objects):
        bpy.ops.object.delete()

    bpy.ops.object.select_all(action='DESELECT')
    if prev_selection is not None:
        for obj in prev_selection:
            if obj and obj.name in bpy.data.objects:
                obj.select_set(True)

    if prev_active and prev_active.name in bpy.data.objects:
        context.view_layer.objects.active = prev_active


def apply_modifier(context, obj, modifier_name):
    view_layer = context.view_layer
    prev_active = view_layer.objects.active
    prev_selection = list(context.selected_objects)

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier_name)

    bpy.ops.object.select_all(action='DESELECT')
    for o in prev_selection:
        if o and o.name in bpy.data.objects:
            o.select_set(True)
    if prev_active and prev_active.name in bpy.data.objects:
        view_layer.objects.active = prev_active


def configure_uv_layer_selection(mod, settings):
    """
    Blender versions differ here.
    We inspect actual allowed enums and set the closest valid option.
    """

    # Source layer selector
    if hasattr(mod, "layers_uv_select_src"):
        if settings.uv_scope == 'ACTIVE':
            # prefer ACTIVE, else fall back to the first sensible option
            set_enum_if_supported(mod, "layers_uv_select_src", ["ACTIVE", "UVMap", "ALL"])
        else:
            set_enum_if_supported(mod, "layers_uv_select_src", ["ALL", "UVMap", "ACTIVE"])

    # Destination layer selector
    if hasattr(mod, "layers_uv_select_dst"):
        # Some Blender versions expose ACTIVE/NAME/INDEX,
        # but your runtime exposed ('ALL', 'UVMap'), so we adapt.
        if settings.dst_layer_behavior == 'ACTIVE':
            set_enum_if_supported(mod, "layers_uv_select_dst", ["ACTIVE", "UVMap", "ALL", "NAME", "INDEX"])
        elif settings.dst_layer_behavior == 'BY_NAME':
            set_enum_if_supported(mod, "layers_uv_select_dst", ["NAME", "UVMap", "ALL", "INDEX", "ACTIVE"])
        else:  # BY_ORDER
            set_enum_if_supported(mod, "layers_uv_select_dst", ["INDEX", "ALL", "UVMap", "NAME", "ACTIVE"])


def add_and_configure_data_transfer(target_obj, source_obj, settings):
    mod = target_obj.modifiers.new(name="UVTransfer", type='DATA_TRANSFER')
    mod.object = source_obj

    # Enable loop/corner data transfer for UVs.
    if hasattr(mod, "use_loop_data"):
        mod.use_loop_data = True

    # Current API docs show data_types_loops as the loop-domain selector for UV data. :contentReference[oaicite:2]{index=2}
    if hasattr(mod, "data_types_loops"):
        try:
            mod.data_types_loops = {'UV'}
        except Exception:
            pass

    # Older versions may expose this alternate property name.
    if hasattr(mod, "data_types_loops_uv"):
        try:
            mod.data_types_loops_uv = {'UV'}
        except Exception:
            pass

    configure_uv_layer_selection(mod, settings)

    if hasattr(mod, "loop_mapping"):
        allowed = enum_items_for_rna(mod, "loop_mapping")
        if settings.loop_mapping in allowed:
            mod.loop_mapping = settings.loop_mapping
        elif "POLYINTERP_NEAREST" in allowed:
            mod.loop_mapping = "POLYINTERP_NEAREST"

    if hasattr(mod, "poly_mapping"):
        allowed = enum_items_for_rna(mod, "poly_mapping")
        if settings.poly_mapping in allowed:
            mod.poly_mapping = settings.poly_mapping
        elif "NEAREST" in allowed:
            mod.poly_mapping = "NEAREST"

    if hasattr(mod, "use_max_distance"):
        mod.use_max_distance = settings.use_max_distance
    if hasattr(mod, "max_distance"):
        mod.max_distance = settings.max_distance
    if hasattr(mod, "ray_radius"):
        mod.ray_radius = settings.ray_radius
    if hasattr(mod, "islands_precision"):
        mod.islands_precision = settings.islands_precision
    if hasattr(mod, "use_object_transform"):
        mod.use_object_transform = settings.use_object_transform
    if hasattr(mod, "mix_mode"):
        allowed = enum_items_for_rna(mod, "mix_mode")
        if settings.mix_mode in allowed:
            mod.mix_mode = settings.mix_mode
    if hasattr(mod, "mix_factor"):
        mod.mix_factor = settings.mix_factor

    return mod


# ------------------------------------------------------------
# Properties
# ------------------------------------------------------------

class UVTransferSourceItem(PropertyGroup):
    obj: PointerProperty(
        name="Source",
        type=bpy.types.Object,
        poll=mesh_obj_poll,
    )


class UVTransferSettings(PropertyGroup):
    source_mode: EnumProperty(
        name="Source Mode",
        items=[
            ('OBJECT', "Single Source", "Use one source object"),
            ('LIST', "Source List", "Use a custom list of source objects"),
            ('COLLECTION', "Source Collection", "Use all mesh objects in a collection"),
            ('SELECTED', "Selected Meshes", "Use currently selected mesh objects"),
        ],
        default='OBJECT',
    )

    source_object: PointerProperty(
        name="Source Object",
        type=bpy.types.Object,
        poll=mesh_obj_poll,
    )

    source_collection: PointerProperty(
        name="Source Collection",
        type=bpy.types.Collection,
    )

    source_items: CollectionProperty(type=UVTransferSourceItem)
    source_index: IntProperty(default=0)

    target_object: PointerProperty(
        name="Target Object",
        type=bpy.types.Object,
        poll=mesh_obj_poll,
    )

    uv_scope: EnumProperty(
        name="Source UV Maps",
        items=[
            ('ACTIVE', "Active Only", "Transfer only the active UV map"),
            ('ALL', "All UV Maps", "Transfer all UV maps"),
        ],
        default='ACTIVE',
    )

    dst_layer_behavior: EnumProperty(
        name="Destination Handling",
        items=[
            ('ACTIVE', "Active Destination", "Write into the active destination UV map when possible"),
            ('BY_NAME', "Match By Name", "Match/create layers by UV map name"),
            ('BY_ORDER', "Match By Order", "Match/create layers by list order"),
        ],
        default='BY_NAME',
    )

    loop_mapping: EnumProperty(
        name="Corner Mapping",
        items=[
            ('POLYINTERP_NEAREST', "Nearest Face Interpolated", "Usually best for different topology"),
            ('NEAREST_POLY', "Nearest Corner of Nearest Face", "Use nearest corner on nearest face"),
            ('NEAREST_POLYNOR', "Nearest Corner + Face Normal", "Corner matching with face normal bias"),
            ('NEAREST_NORMAL', "Nearest Corner + Normal", "Corner matching with corner normal bias"),
            ('POLYINTERP_LNORPROJ', "Projected Face Interpolated", "Projected interpolation along normals"),
            ('TOPOLOGY', "Topology", "Only for identical topology"),
        ],
        default='POLYINTERP_NEAREST',
    )

    poly_mapping: EnumProperty(
        name="Face Mapping",
        items=[
            ('NEAREST', "Nearest Face", "Use nearest source polygon"),
            ('NORMAL', "Best Normal Match", "Use source polygon with closest normal"),
            ('POLYINTERP_PNORPROJ', "Projected", "Projected polygon matching"),
            ('TOPOLOGY', "Topology", "Only for identical topology"),
        ],
        default='NEAREST',
    )

    use_max_distance: BoolProperty(
        name="Use Max Distance",
        default=False,
    )

    max_distance: FloatProperty(
        name="Max Distance",
        default=0.1,
        min=0.0,
        soft_max=1000.0,
    )

    ray_radius: FloatProperty(
        name="Ray Radius",
        default=0.0,
        min=0.0,
        soft_max=10.0,
    )

    islands_precision: FloatProperty(
        name="Island Precision",
        default=0.1,
        min=0.0,
        max=1.0,
    )

    use_object_transform: BoolProperty(
        name="Use Object Transform",
        default=True,
    )

    mix_mode: EnumProperty(
        name="Mix Mode",
        items=[
            ('REPLACE', "Replace", "Overwrite destination UV data"),
            ('MIX', "Mix", "Mix source into destination"),
            ('ADD', "Add", "Add source values"),
            ('SUB', "Subtract", "Subtract source values"),
            ('MUL', "Multiply", "Multiply source values"),
        ],
        default='REPLACE',
    )

    mix_factor: FloatProperty(
        name="Mix Factor",
        default=1.0,
        min=0.0,
        max=1.0,
    )

    create_missing_uvs: BoolProperty(
        name="Create Missing UV Maps",
        default=True,
    )

    apply_modifier_now: BoolProperty(
        name="Apply Immediately",
        default=True,
    )

    keep_modifier: BoolProperty(
        name="Keep Modifier",
        default=False,
    )


# ------------------------------------------------------------
# UI List Operators
# ------------------------------------------------------------

class OBJECT_OT_uv_transfer_add_selected_sources(Operator):
    bl_idname = "object.uv_transfer_add_selected_sources"
    bl_label = "Add Selected Sources"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.uv_transfer_settings
        target = settings.target_object
        existing = {item.obj.name for item in settings.source_items if item.obj}

        added = 0
        for obj in context.selected_objects:
            if obj.type == 'MESH' and obj != target and obj.name not in existing:
                item = settings.source_items.add()
                item.obj = obj
                existing.add(obj.name)
                added += 1

        self.report({'INFO'}, f"Added {added} source object(s)")
        return {'FINISHED'}


class OBJECT_OT_uv_transfer_remove_source(Operator):
    bl_idname = "object.uv_transfer_remove_source"
    bl_label = "Remove Source"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.uv_transfer_settings
        idx = settings.source_index
        if 0 <= idx < len(settings.source_items):
            settings.source_items.remove(idx)
            settings.source_index = min(max(0, idx - 1), len(settings.source_items) - 1)
        return {'FINISHED'}


class OBJECT_OT_uv_transfer_clear_sources(Operator):
    bl_idname = "object.uv_transfer_clear_sources"
    bl_label = "Clear Sources"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.uv_transfer_settings
        settings.source_items.clear()
        settings.source_index = 0
        return {'FINISHED'}


class VIEW3D_UL_uv_transfer_sources(UIList):
    bl_idname = "VIEW3D_UL_uv_transfer_sources"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            if item.obj:
                layout.prop(item, "obj", text="", emboss=False, icon='MESH_DATA')
            else:
                layout.label(text="Missing Object", icon='ERROR')
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='MESH_DATA')


# ------------------------------------------------------------
# Main Operator
# ------------------------------------------------------------

class OBJECT_OT_transfer_uvs_different_topology(Operator):
    bl_idname = "object.transfer_uvs_different_topology"
    bl_label = "Transfer UVs"
    bl_description = "Transfer UVs from one or more source meshes to a target mesh, even with different topology"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ensure_object_mode()

        settings = context.scene.uv_transfer_settings
        target = settings.target_object

        if target is None or target.type != 'MESH':
            self.report({'ERROR'}, "Please set a valid target mesh")
            return {'CANCELLED'}

        if len(target.data.polygons) == 0:
            self.report({'ERROR'}, "Target mesh has no faces")
            return {'CANCELLED'}

        if settings.source_mode == 'OBJECT':
            if settings.source_object is None or settings.source_object.type != 'MESH':
                self.report({'ERROR'}, "Please set a valid source mesh")
                return {'CANCELLED'}
            source_objects = [settings.source_object]

        elif settings.source_mode == 'LIST':
            source_objects = get_sources_from_list(context.scene)
            if not source_objects:
                self.report({'ERROR'}, "Source list is empty")
                return {'CANCELLED'}

        elif settings.source_mode == 'COLLECTION':
            coll = settings.source_collection
            if coll is None or not collection_has_meshes(coll):
                self.report({'ERROR'}, "Please choose a collection containing at least one mesh")
                return {'CANCELLED'}
            source_objects = [obj for obj in coll.objects if obj.type == 'MESH']

        elif settings.source_mode == 'SELECTED':
            source_objects = get_selected_mesh_sources(context, target=target)
            if not source_objects:
                self.report({'ERROR'}, "No selected mesh sources found (excluding the target)")
                return {'CANCELLED'}
        else:
            self.report({'ERROR'}, "Invalid source mode")
            return {'CANCELLED'}

        source_objects = [obj for obj in source_objects if obj != target]
        if not source_objects:
            self.report({'ERROR'}, "No valid source meshes found after excluding the target")
            return {'CANCELLED'}

        temp_source = None
        dupe_list = []
        prev_active = None
        prev_selection = None

        try:
            temp_source, dupe_list, prev_active, prev_selection = build_temp_source(context, source_objects)

            if temp_source is None or temp_source.type != 'MESH':
                self.report({'ERROR'}, "Failed to build temporary source mesh")
                return {'CANCELLED'}

            if len(temp_source.data.uv_layers) == 0:
                self.report({'ERROR'}, "Source mesh has no UV maps to transfer")
                return {'CANCELLED'}

            ensure_uv_layers_on_target(temp_source, target, settings)

            mod = add_and_configure_data_transfer(target, temp_source, settings)

            if settings.apply_modifier_now:
                apply_modifier(context, target, mod.name)

            self.report({'INFO'}, f"Transferred UVs from {len(source_objects)} source mesh(es) to '{target.name}'")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"UV transfer failed: {e}")
            return {'CANCELLED'}

        finally:
            should_cleanup_temp = settings.apply_modifier_now or not settings.keep_modifier
            if should_cleanup_temp and dupe_list:
                try:
                    cleanup_temp_objects(context, dupe_list, prev_active, prev_selection)
                except Exception:
                    pass
            else:
                bpy.ops.object.select_all(action='DESELECT')
                if prev_selection is not None:
                    for obj in prev_selection:
                        if obj and obj.name in bpy.data.objects:
                            obj.select_set(True)
                if prev_active and prev_active.name in bpy.data.objects:
                    context.view_layer.objects.active = prev_active


# ------------------------------------------------------------
# UI
# ------------------------------------------------------------

class VIEW3D_PT_transfer_uvs_panel(Panel):
    bl_label = "Transfer UVs"
    bl_idname = "VIEW3D_PT_transfer_uvs_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "UV Tools"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.uv_transfer_settings

        col = layout.column(align=True)
        col.prop(settings, "source_mode")

        if settings.source_mode == 'OBJECT':
            col.prop(settings, "source_object")

        elif settings.source_mode == 'COLLECTION':
            col.prop(settings, "source_collection")

        elif settings.source_mode == 'SELECTED':
            col.label(text="Uses selected mesh objects")
            col.label(text="(excluding target)")

        elif settings.source_mode == 'LIST':
            row = col.row()
            row.template_list(
                "VIEW3D_UL_uv_transfer_sources",
                "",
                settings,
                "source_items",
                settings,
                "source_index",
                rows=4,
            )
            buttons = row.column(align=True)
            buttons.operator("object.uv_transfer_add_selected_sources", text="", icon='ADD')
            buttons.operator("object.uv_transfer_remove_source", text="", icon='REMOVE')
            buttons.operator("object.uv_transfer_clear_sources", text="", icon='TRASH')

        col.separator()
        col.prop(settings, "target_object")

        box = layout.box()
        box.label(text="UV Layer Options")
        box.prop(settings, "uv_scope")
        box.prop(settings, "dst_layer_behavior")
        box.prop(settings, "create_missing_uvs")

        box = layout.box()
        box.label(text="Mapping")
        box.prop(settings, "loop_mapping")
        box.prop(settings, "poly_mapping")
        box.prop(settings, "use_object_transform")

        box = layout.box()
        box.label(text="Matching Controls")
        row = box.row(align=True)
        row.prop(settings, "use_max_distance")
        row.prop(settings, "max_distance")
        box.prop(settings, "ray_radius")
        box.prop(settings, "islands_precision")

        box = layout.box()
        box.label(text="Mix / Apply")
        box.prop(settings, "mix_mode")
        box.prop(settings, "mix_factor")
        box.prop(settings, "apply_modifier_now")
        if not settings.apply_modifier_now:
            box.prop(settings, "keep_modifier")

        layout.separator()
        layout.operator("object.transfer_uvs_different_topology", icon='GROUP_UVS')


# ------------------------------------------------------------
# Register
# ------------------------------------------------------------

classes = (
    UVTransferSourceItem,
    UVTransferSettings,
    OBJECT_OT_uv_transfer_add_selected_sources,
    OBJECT_OT_uv_transfer_remove_source,
    OBJECT_OT_uv_transfer_clear_sources,
    VIEW3D_UL_uv_transfer_sources,
    OBJECT_OT_transfer_uvs_different_topology,
    VIEW3D_PT_transfer_uvs_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.uv_transfer_settings = PointerProperty(type=UVTransferSettings)


def unregister():
    del bpy.types.Scene.uv_transfer_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
