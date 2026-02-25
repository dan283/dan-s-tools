bl_info = {
    "name": "Export Selected to OBJs (Per-Object)",
    "author": "ChatGPT",
    "version": (1, 1, 0),
    "blender": (2, 93, 0),
    "location": "View3D > Sidebar (N) > Export",
    "description": "Export each selected object as a separate OBJ with simple N-panel UI",
    "category": "Import-Export",
}

import bpy
import os
import re
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import StringProperty, BoolProperty, PointerProperty


def sanitize_filename(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"[<>:\"/\\|?*\x00-\x1F]", "_", name)
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = "object"
    return name[:200]


def obj_export_operator_available():
    """Return a tuple (op_name, callable) for the first available OBJ exporter."""
    # Blender 4.x (new exporter)
    if hasattr(bpy.ops.wm, "obj_export"):
        return ("wm.obj_export", bpy.ops.wm.obj_export)

    # Blender 2.8-3.x (classic exporter, often from io_scene_obj add-on)
    if hasattr(bpy.ops.export_scene, "obj"):
        return ("export_scene.obj", bpy.ops.export_scene.obj)

    return (None, None)


def export_one_obj(filepath: str):
    """
    Call whichever OBJ export operator is available in this Blender.
    Assumes the correct object is selected as the only selection.
    """
    op_name, op = obj_export_operator_available()
    if op is None:
        raise RuntimeError(
            "No OBJ export operator found. "
            "Enable/install the OBJ exporter add-on, or use Blender's built-in exporter for your version."
        )

    # Normalize path for Blender
    filepath = os.path.normpath(filepath)

    # Blender 4.x operator: bpy.ops.wm.obj_export
    if op_name == "wm.obj_export":
        # Keep args minimal and stable across minor changes
        return op(
            filepath=filepath,
            export_selected_objects=True,
            export_uv=True,
            export_normals=True,
            export_materials=True,
        )

    # Classic operator: bpy.ops.export_scene.obj
    return op(
        filepath=filepath,
        use_selection=True,
        use_mesh_modifiers=True,
        use_normals=True,
        use_uvs=True,
        use_materials=True,
        axis_forward='-Z',
        axis_up='Y',
        global_scale=1.0,
    )


class EXPORTSEL_OBJ_Props(PropertyGroup):
    export_dir: StringProperty(
        name="Export Folder",
        description="Directory to export OBJ files into",
        subtype="DIR_PATH",
        default="//",
    )

    use_object_names: BoolProperty(
        name="Use Object Names",
        description="Use each object's name as the filename (otherwise use a numbered name)",
        default=True,
    )


class EXPORTSEL_OT_export_selected_objs(Operator):
    bl_idname = "exportsel.export_selected_objs"
    bl_label = "Export Selected OBJs"
    bl_description = "Export each selected object as an OBJ file into the chosen folder"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.exportsel_obj_props

        # Check exporter availability first
        op_name, _ = obj_export_operator_available()
        if not op_name:
            self.report(
                {"ERROR"},
                "OBJ exporter not found. In Blender: Preferences > Add-ons > enable OBJ (io_scene_obj), "
                "or in Blender 4.x ensure OBJ export is available."
            )
            return {"CANCELLED"}

        export_dir = bpy.path.abspath(props.export_dir)
        export_dir = os.path.normpath(export_dir)

        if not export_dir or export_dir in {".", ""}:
            self.report({"ERROR"}, "Pick a valid export folder.")
            return {"CANCELLED"}

        try:
            os.makedirs(export_dir, exist_ok=True)
        except Exception as e:
            self.report({"ERROR"}, f"Cannot create/access folder:\n{export_dir}\n{e}")
            return {"CANCELLED"}

        # Use context.selected_objects (reliable)
        selected = list(context.selected_objects)
        if not selected:
            self.report({"WARNING"}, "Nothing selected.")
            return {"CANCELLED"}

        # Filter exportables (OBJ really only makes sense for mesh; curves can be exported depending on settings,
        # but many pipelines want mesh only)
        exportables = [o for o in selected if o.type in {"MESH", "CURVE", "SURFACE", "META", "FONT"}]
        if not exportables:
            self.report({"WARNING"}, "No exportable objects selected (mesh/curve/etc).")
            return {"CANCELLED"}

        # Save current state
        view_layer = context.view_layer
        active_orig = view_layer.objects.active
        selected_orig = list(context.selected_objects)

        # Helper to deselect all quickly
        def deselect_all():
            for o in view_layer.objects:
                if o.select_get():
                    o.select_set(False)

        exported = 0
        failed = 0

        for idx, obj in enumerate(exportables, start=1):
            deselect_all()
            obj.select_set(True)
            view_layer.objects.active = obj

            base = sanitize_filename(obj.name) if props.use_object_names else f"object_{idx:03d}"
            filepath = os.path.join(export_dir, base + ".obj")

            # avoid overwriting silently
            if os.path.exists(filepath):
                s = 1
                while True:
                    candidate = os.path.join(export_dir, f"{base}_{s:02d}.obj")
                    if not os.path.exists(candidate):
                        filepath = candidate
                        break
                    s += 1

            try:
                result = export_one_obj(filepath)

                # Operators typically return {'FINISHED'} or {'CANCELLED'}
                if "FINISHED" in result:
                    exported += 1
                else:
                    failed += 1
                    self.report({"WARNING"}, f"Export cancelled for: {obj.name}")
            except Exception as e:
                failed += 1
                self.report({"WARNING"}, f"Failed exporting {obj.name}: {e}")

        # Restore original selection/active
        deselect_all()
        for o in selected_orig:
            if o and o.name in view_layer.objects:
                o.select_set(True)
        if active_orig and active_orig.name in view_layer.objects:
            view_layer.objects.active = active_orig

        if exported == 0:
            self.report({"ERROR"}, f"No files exported. Exporter used: {op_name}. Check folder permissions and selection.")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Exported {exported} OBJ(s) to: {export_dir}  (failed: {failed})")
        return {"FINISHED"}


class EXPORTSEL_PT_obj_panel(Panel):
    bl_label = "Export Selected OBJs"
    bl_idname = "EXPORTSEL_PT_obj_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Export"

    def draw(self, context):
        layout = self.layout
        props = context.scene.exportsel_obj_props

        layout.prop(props, "export_dir")
        layout.prop(props, "use_object_names")
        layout.separator()
        layout.operator("exportsel.export_selected_objs", icon="EXPORT")


classes = (
    EXPORTSEL_OBJ_Props,
    EXPORTSEL_OT_export_selected_objs,
    EXPORTSEL_PT_obj_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.exportsel_obj_props = PointerProperty(type=EXPORTSEL_OBJ_Props)


def unregister():
    del bpy.types.Scene.exportsel_obj_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
