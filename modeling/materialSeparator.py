bl_info = {
    "name": "Separate by Material Tools",
    "author": "ChatGPT",
    "version": (1, 0, 1),
    "blender": (4, 0, 0),
    "category": "Object",
}

import bpy
import bmesh
from bpy.props import BoolProperty, StringProperty


class SBM_Settings(bpy.types.PropertyGroup):
    name_prefix: StringProperty(name="Name Prefix", default="")

    keep_original: BoolProperty(name="Keep Original", default=False)

    copy_modifiers: BoolProperty(name="Copy Modifiers", default=True)

    clean_slots_after: BoolProperty(name="Clean Slots After Split", default=True)

    select_new_objects: BoolProperty(name="Select New Objects", default=True)


def material_safe_name(mat, index):
    if mat:
        return bpy.path.clean_name(mat.name)
    return f"No_Material_{index}"


def clean_unused_material_slots(obj):
    if not obj or obj.type != "MESH":
        return 0

    used_indices = {poly.material_index for poly in obj.data.polygons}
    removed = 0

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    for i in reversed(range(len(obj.material_slots))):
        if i not in used_indices:
            obj.active_material_index = i
            bpy.ops.object.material_slot_remove()
            removed += 1

    return removed


def copy_modifiers_from_source(source, target):
    for mod in source.modifiers:
        try:
            new_mod = target.modifiers.new(mod.name, mod.type)

            for attr in dir(mod):
                if attr.startswith("_"):
                    continue

                try:
                    setattr(new_mod, attr, getattr(mod, attr))
                except Exception:
                    pass

        except Exception:
            pass


def make_mesh_for_material(source, mat_index, face_indices, obj_name):
    source_mesh = source.data

    bm = bmesh.new()
    bm.from_mesh(source_mesh)

    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()

    faces_to_keep = set(face_indices)

    delete_faces = [
        face for face in bm.faces
        if face.index not in faces_to_keep
    ]

    bmesh.ops.delete(
        bm,
        geom=delete_faces,
        context="FACES"
    )

    loose_edges = [edge for edge in bm.edges if not edge.link_faces]

    if loose_edges:
        bmesh.ops.delete(
            bm,
            geom=loose_edges,
            context="EDGES"
        )

    loose_verts = [vert for vert in bm.verts if not vert.link_edges]

    if loose_verts:
        bmesh.ops.delete(
            bm,
            geom=loose_verts,
            context="VERTS"
        )

    new_mesh = bpy.data.meshes.new(obj_name + "_Mesh")
    bm.to_mesh(new_mesh)
    bm.free()

    mat = source_mesh.materials[mat_index] if mat_index < len(source_mesh.materials) else None

    if mat:
        new_mesh.materials.append(mat)

    for poly in new_mesh.polygons:
        poly.material_index = 0

    new_mesh.update()

    return new_mesh


class SBM_OT_clean_material_slots(bpy.types.Operator):
    bl_idname = "object.sbm_clean_material_slots"
    bl_label = "Clean Unused Material Slots"
    bl_description = "Remove material slots that are not assigned to any faces"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objects = [obj for obj in context.selected_objects if obj.type == "MESH"]

        if not objects:
            self.report({"WARNING"}, "Select at least one mesh object.")
            return {"CANCELLED"}

        total_removed = 0

        for obj in objects:
            total_removed += clean_unused_material_slots(obj)

        self.report({"INFO"}, f"Removed {total_removed} unused material slot(s).")
        return {"FINISHED"}


class SBM_OT_separate_by_material(bpy.types.Operator):
    bl_idname = "object.sbm_separate_by_material"
    bl_label = "Separate By Material"
    bl_description = "Create one new object per assigned material"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.sbm_settings
        source = context.object

        if not source or source.type != "MESH":
            self.report({"WARNING"}, "Active object must be a mesh.")
            return {"CANCELLED"}

        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        source_mesh = source.data

        if not source_mesh.polygons:
            self.report({"WARNING"}, "Mesh has no faces.")
            return {"CANCELLED"}

        material_face_map = {}

        for poly in source_mesh.polygons:
            material_face_map.setdefault(poly.material_index, []).append(poly.index)

        created_objects = []

        for mat_index, face_indices in material_face_map.items():
            mat = source_mesh.materials[mat_index] if mat_index < len(source_mesh.materials) else None
            mat_name = material_safe_name(mat, mat_index)
            obj_name = f"{settings.name_prefix}{mat_name}"

            new_mesh = make_mesh_for_material(
                source,
                mat_index,
                face_indices,
                obj_name
            )

            if len(new_mesh.polygons) == 0:
                bpy.data.meshes.remove(new_mesh)
                continue

            new_obj = bpy.data.objects.new(obj_name, new_mesh)
            context.collection.objects.link(new_obj)

            new_obj.matrix_world = source.matrix_world.copy()

            if settings.copy_modifiers:
                copy_modifiers_from_source(source, new_obj)

            if settings.clean_slots_after:
                clean_unused_material_slots(new_obj)

            created_objects.append(new_obj)

        if not settings.keep_original:
            bpy.data.objects.remove(source, do_unlink=True)

        if settings.select_new_objects:
            bpy.ops.object.select_all(action="DESELECT")

            for obj in created_objects:
                obj.select_set(True)

            if created_objects:
                context.view_layer.objects.active = created_objects[0]

        self.report({"INFO"}, f"Created {len(created_objects)} object(s).")
        return {"FINISHED"}


class SBM_PT_panel(bpy.types.Panel):
    bl_label = "Material Separator"
    bl_idname = "SBM_PT_material_separator"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Mat Tools"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.sbm_settings

        layout.label(text="Separate Mesh by Material")
        layout.prop(settings, "name_prefix")
        layout.prop(settings, "keep_original")
        layout.prop(settings, "copy_modifiers")
        layout.prop(settings, "clean_slots_after")
        layout.prop(settings, "select_new_objects")

        layout.separator()
        layout.operator("object.sbm_separate_by_material", icon="MATERIAL")

        layout.separator()
        layout.label(text="Cleanup Selected Meshes")
        layout.operator("object.sbm_clean_material_slots", icon="TRASH")


classes = (
    SBM_Settings,
    SBM_OT_clean_material_slots,
    SBM_OT_separate_by_material,
    SBM_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.sbm_settings = bpy.props.PointerProperty(type=SBM_Settings)


def unregister():
    del bpy.types.Scene.sbm_settings

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
