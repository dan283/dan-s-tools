
bl_info = {
    "name": "Promo Dust / Glitter",
    "author": "OpenAI",
    "version": (2, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D View > N Panel > Promo FX",
    "description": "Camera-frustum dust / glitter particles using Geometry Nodes with live updates.",
    "category": "Object",
}

import bpy
import math
from bpy.app.handlers import persistent
from bpy.props import (
    PointerProperty,
    IntProperty,
    FloatProperty,
    FloatVectorProperty,
    BoolProperty,
)
from mathutils import Vector

DUST_OBJ_NAME = "PROMO_Dust"
DUST_MESH_NAME = "PROMO_Dust_Mesh"
DUST_MAT_NAME = "PROMO_Dust_Material"
DUST_GN_NAME = "PROMO_Dust_GN"

# Named GN nodes. We edit their socket defaults directly, avoiding
# modifier-interface socket problems between Blender versions.
NODE_LINE = "PD_Points"
NODE_POS = "PD_RandomPosition"
NODE_SIZE = "PD_RandomSize"
NODE_ICO = "PD_ParticleMesh"
NODE_MAT = "PD_SetMaterial"


# ------------------------------------------------------------
# Material
# ------------------------------------------------------------

def ensure_material():
    mat = bpy.data.materials.get(DUST_MAT_NAME)
    if not mat:
        mat = bpy.data.materials.new(DUST_MAT_NAME)
        mat.use_nodes = True

    mat.use_nodes = True
    nt = mat.node_tree

    output = nt.nodes.get("Material Output")
    bsdf = nt.nodes.get("Principled BSDF")

    if not output:
        output = nt.nodes.new("ShaderNodeOutputMaterial")

    if not bsdf:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    return mat


def update_material(scene):
    s = scene.promo_dust_settings
    mat = ensure_material()
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        return

    rgba = (*s.color, 1.0)

    if "Base Color" in bsdf.inputs:
        bsdf.inputs["Base Color"].default_value = rgba
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = s.roughness
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = s.metallic

    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = rgba
    elif "Emission" in bsdf.inputs:
        bsdf.inputs["Emission"].default_value = rgba

    if "Emission Strength" in bsdf.inputs:
        bsdf.inputs["Emission Strength"].default_value = s.emission_strength


# ------------------------------------------------------------
# Geometry Nodes
# ------------------------------------------------------------

def create_or_rebuild_node_group():
    old = bpy.data.node_groups.get(DUST_GN_NAME)
    if old:
        bpy.data.node_groups.remove(old, do_unlink=True)

    ng = bpy.data.node_groups.new(DUST_GN_NAME, "GeometryNodeTree")
    ng.interface.new_socket(
        name="Geometry",
        in_out="OUTPUT",
        socket_type="NodeSocketGeometry"
    )

    nodes = ng.nodes
    links = ng.links

    out = nodes.new("NodeGroupOutput")
    out.location = (650, 80)

    # A Mesh Line is simply used as N independent points.
    line = nodes.new("GeometryNodeMeshLine")
    line.name = NODE_LINE
    line.label = "Particle Points"
    line.location = (-650, 120)
    line.mode = "OFFSET"
    line.inputs["Count"].default_value = 500
    line.inputs["Start Location"].default_value = (0.0, 0.0, 0.0)
    line.inputs["Offset"].default_value = (0.0, 0.0, 0.0)

    index = nodes.new("GeometryNodeInputIndex")
    index.location = (-650, -120)

    rand_pos = nodes.new("FunctionNodeRandomValue")
    rand_pos.name = NODE_POS
    rand_pos.label = "Random Camera Volume Position"
    rand_pos.location = (-420, -40)
    rand_pos.data_type = "FLOAT_VECTOR"
    rand_pos.inputs["Min"].default_value = (-2.0, -2.0, -6.0)
    rand_pos.inputs["Max"].default_value = ( 2.0,  2.0, -1.0)
    rand_pos.inputs["Seed"].default_value = 1

    set_pos = nodes.new("GeometryNodeSetPosition")
    set_pos.location = (-160, 120)

    ico = nodes.new("GeometryNodeMeshIcoSphere")
    ico.name = NODE_ICO
    ico.label = "Dust Particle"
    ico.location = (-170, -230)
    ico.inputs["Radius"].default_value = 1.0
    ico.inputs["Subdivisions"].default_value = 1

    set_mat = nodes.new("GeometryNodeSetMaterial")
    set_mat.name = NODE_MAT
    set_mat.location = (40, -230)
    set_mat.inputs["Material"].default_value = ensure_material()

    rand_size = nodes.new("FunctionNodeRandomValue")
    rand_size.name = NODE_SIZE
    rand_size.label = "Random Particle Size"
    rand_size.location = (0, -440)
    rand_size.data_type = "FLOAT"
    rand_size.inputs["Min"].default_value = 0.01
    rand_size.inputs["Max"].default_value = 0.04
    rand_size.inputs["Seed"].default_value = 17

    combine = nodes.new("ShaderNodeCombineXYZ")
    combine.location = (210, -390)

    inst = nodes.new("GeometryNodeInstanceOnPoints")
    inst.location = (390, 90)

    links.new(index.outputs["Index"], rand_pos.inputs["ID"])
    links.new(index.outputs["Index"], rand_size.inputs["ID"])

    links.new(line.outputs["Mesh"], set_pos.inputs["Geometry"])
    links.new(rand_pos.outputs["Value"], set_pos.inputs["Position"])

    links.new(ico.outputs["Mesh"], set_mat.inputs["Geometry"])

    links.new(rand_size.outputs["Value"], combine.inputs["X"])
    links.new(rand_size.outputs["Value"], combine.inputs["Y"])
    links.new(rand_size.outputs["Value"], combine.inputs["Z"])

    links.new(set_pos.outputs["Geometry"], inst.inputs["Points"])
    links.new(set_mat.outputs["Geometry"], inst.inputs["Instance"])
    links.new(combine.outputs["Vector"], inst.inputs["Scale"])

    links.new(inst.outputs["Instances"], out.inputs["Geometry"])

    return ng


def ensure_dust_object(scene, rebuild=False):
    obj = bpy.data.objects.get(DUST_OBJ_NAME)

    if not obj:
        mesh = bpy.data.meshes.new(DUST_MESH_NAME)
        obj = bpy.data.objects.new(DUST_OBJ_NAME, mesh)
        scene.collection.objects.link(obj)

    mod = obj.modifiers.get("Promo Dust GN")
    if not mod:
        mod = obj.modifiers.new("Promo Dust GN", "NODES")

    ng = bpy.data.node_groups.get(DUST_GN_NAME)
    if rebuild or not ng:
        ng = create_or_rebuild_node_group()

    mod.node_group = ng

    obj.hide_viewport = False
    obj.hide_render = False
    obj.display_type = "TEXTURED"
    return obj, ng


# ------------------------------------------------------------
# Camera-volume calculation
# ------------------------------------------------------------

def get_camera(scene, settings):
    if settings.camera and settings.camera.type == "CAMERA":
        return settings.camera
    return scene.camera


def target_center_world(target):
    return sum(
        (target.matrix_world @ Vector(corner) for corner in target.bound_box),
        Vector()
    ) / 8.0


def target_radius(target):
    pts = [target.matrix_world @ Vector(c) for c in target.bound_box]
    center = sum(pts, Vector()) / 8.0
    return max((p - center).length for p in pts)


def camera_volume(scene, camera, target, settings):
    """
    Returns local-camera-space min/max coordinates.

    Blender cameras look down local -Z.
    The box is deliberately sized from the FAR depth, so it always covers
    the full camera frame rather than only the target's bounding box.
    """
    center_world = target_center_world(target)
    center_cam = camera.matrix_world.inverted() @ center_world
    subject_distance = max(0.01, -center_cam.z)

    radius = max(0.01, target_radius(target))

    # User depth is added both in front and behind the target.
    front = max(0.01, settings.front_depth)
    back = max(0.01, settings.back_depth)

    near_d = max(camera.data.clip_start * 1.05,
                 subject_distance - radius - front)
    far_d = max(near_d + 0.05,
                subject_distance + radius + back)

    margin = max(1.0, settings.frame_coverage)

    if camera.data.type == "ORTHO":
        aspect = (scene.render.resolution_x * scene.render.pixel_aspect_x) / max(
            1.0, scene.render.resolution_y * scene.render.pixel_aspect_y
        )
        if aspect >= 1.0:
            half_h = camera.data.ortho_scale * 0.5
            half_w = half_h * aspect
        else:
            half_w = camera.data.ortho_scale * 0.5
            half_h = half_w / aspect

        half_w *= margin
        half_h *= margin
    else:
        # Use camera's actual horizontal/vertical field of view.
        half_w = math.tan(camera.data.angle_x * 0.5) * far_d * margin
        half_h = math.tan(camera.data.angle_y * 0.5) * far_d * margin

    box_min = (-half_w, -half_h, -far_d)
    box_max = ( half_w,  half_h, -near_d)

    return box_min, box_max, subject_distance


# ------------------------------------------------------------
# Live update
# ------------------------------------------------------------

_update_lock = False

def update_dust(scene, force=False):
    global _update_lock

    if _update_lock:
        return
    if not hasattr(scene, "promo_dust_settings"):
        return

    s = scene.promo_dust_settings
    if not s.target:
        return

    camera = get_camera(scene, s)
    if not camera:
        return

    obj = bpy.data.objects.get(DUST_OBJ_NAME)
    ng = bpy.data.node_groups.get(DUST_GN_NAME)

    if not obj or not ng:
        if not force:
            return
        obj, ng = ensure_dust_object(scene)

    try:
        _update_lock = True

        # Parent the whole distribution volume to camera coordinates by giving
        # the dust object exactly the camera transform.
        obj.matrix_world = camera.matrix_world.copy()

        box_min, box_max, distance = camera_volume(
            scene, camera, s.target, s
        )

        line = ng.nodes.get(NODE_LINE)
        rand_pos = ng.nodes.get(NODE_POS)
        rand_size = ng.nodes.get(NODE_SIZE)
        set_mat = ng.nodes.get(NODE_MAT)

        if not all((line, rand_pos, rand_size, set_mat)):
            obj, ng = ensure_dust_object(scene, rebuild=True)
            line = ng.nodes[NODE_LINE]
            rand_pos = ng.nodes[NODE_POS]
            rand_size = ng.nodes[NODE_SIZE]
            set_mat = ng.nodes[NODE_MAT]

        line.inputs["Count"].default_value = int(s.count)

        rand_pos.inputs["Min"].default_value = box_min
        rand_pos.inputs["Max"].default_value = box_max
        rand_pos.inputs["Seed"].default_value = int(s.seed)

        size_min = max(0.00001, s.size * (1.0 - s.size_random))
        size_max = max(size_min, s.size * (1.0 + s.size_random))
        rand_size.inputs["Min"].default_value = size_min
        rand_size.inputs["Max"].default_value = size_max
        rand_size.inputs["Seed"].default_value = int(s.seed + 7919)

        set_mat.inputs["Material"].default_value = ensure_material()
        update_material(scene)

        if s.manage_dof:
            camera.data.dof.use_dof = True
            camera.data.dof.focus_object = s.target
            camera.data.dof.aperture_fstop = s.fstop

        # Force dependency graph refresh.
        obj.update_tag()
        ng.update_tag()

    finally:
        _update_lock = False


def settings_update(self, context):
    try:
        if context and context.scene:
            update_dust(context.scene)
    except Exception as exc:
        print("Promo Dust update:", exc)


@persistent
def promo_dust_depsgraph(scene, depsgraph):
    try:
        if not hasattr(scene, "promo_dust_settings"):
            return
        s = scene.promo_dust_settings
        if not s.live_update or not s.target:
            return

        camera = get_camera(scene, s)
        watched = {s.target}
        if camera:
            watched.add(camera)

        if any(update.id in watched for update in depsgraph.updates):
            update_dust(scene)
    except Exception as exc:
        print("Promo Dust live update:", exc)


# ------------------------------------------------------------
# Properties
# ------------------------------------------------------------

class PROMODUST_Settings(bpy.types.PropertyGroup):

    target: PointerProperty(
        name="Target",
        type=bpy.types.Object,
        description="Character / product the camera is focused on",
        update=settings_update,
    )

    camera: PointerProperty(
        name="Camera",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == "CAMERA",
        description="Camera used to build the particle volume",
        update=settings_update,
    )

    count: IntProperty(
        name="Particle Count",
        default=700,
        min=1,
        max=50000,
        update=settings_update,
    )

    size: FloatProperty(
        name="Particle Size",
        default=0.025,
        min=0.0001,
        soft_max=0.25,
        subtype="DISTANCE",
        update=settings_update,
    )

    size_random: FloatProperty(
        name="Size Variation",
        default=0.75,
        min=0.0,
        max=0.99,
        subtype="FACTOR",
        update=settings_update,
    )

    frame_coverage: FloatProperty(
        name="Frame Coverage",
        default=1.15,
        min=1.0,
        max=3.0,
        description="1.0 fills the complete camera frame; larger values extend beyond it",
        update=settings_update,
    )

    front_depth: FloatProperty(
        name="Foreground Depth",
        default=2.0,
        min=0.01,
        soft_max=20.0,
        subtype="DISTANCE",
        description="How far particles extend toward the camera from the subject",
        update=settings_update,
    )

    back_depth: FloatProperty(
        name="Background Depth",
        default=2.5,
        min=0.01,
        soft_max=20.0,
        subtype="DISTANCE",
        description="How far particles extend behind the subject",
        update=settings_update,
    )

    seed: IntProperty(
        name="Seed",
        default=1,
        min=0,
        max=1000000,
        update=settings_update,
    )

    color: FloatVectorProperty(
        name="Color",
        subtype="COLOR",
        size=3,
        default=(1.0, 0.62, 0.22),
        min=0.0,
        max=1.0,
        update=settings_update,
    )

    emission_strength: FloatProperty(
        name="Glow",
        default=3.0,
        min=0.0,
        max=100.0,
        update=settings_update,
    )

    roughness: FloatProperty(
        name="Roughness",
        default=0.25,
        min=0.0,
        max=1.0,
        update=settings_update,
    )

    metallic: FloatProperty(
        name="Metallic",
        default=0.0,
        min=0.0,
        max=1.0,
        update=settings_update,
    )

    manage_dof: BoolProperty(
        name="Manage Camera DOF",
        default=True,
        update=settings_update,
    )

    fstop: FloatProperty(
        name="F-Stop",
        default=1.8,
        min=0.1,
        max=32.0,
        update=settings_update,
    )

    live_update: BoolProperty(
        name="Live Update",
        default=True,
        description="Update when the target or camera moves",
    )


# ------------------------------------------------------------
# Operators
# ------------------------------------------------------------

class PROMODUST_OT_create(bpy.types.Operator):
    bl_idname = "promodust.create"
    bl_label = "Create / Rebuild Dust"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.promo_dust_settings

        if not s.target:
            active = context.active_object
            if active and active.type != "CAMERA":
                s.target = active

        if not s.target:
            self.report({"ERROR"}, "Select or assign a Target object.")
            return {"CANCELLED"}

        camera = get_camera(context.scene, s)
        if not camera:
            self.report({"ERROR"}, "Assign a Camera or set the Scene Camera.")
            return {"CANCELLED"}

        ensure_dust_object(context.scene, rebuild=True)
        update_dust(context.scene, force=True)

        self.report({"INFO"}, "Promo Dust rebuilt and fitted to the camera view.")
        return {"FINISHED"}


class PROMODUST_OT_use_selected(bpy.types.Operator):
    bl_idname = "promodust.use_selected"
    bl_label = "Use Selected as Target"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        active = context.active_object
        if not active or active.type == "CAMERA":
            self.report({"ERROR"}, "Select the character/product object.")
            return {"CANCELLED"}

        context.scene.promo_dust_settings.target = active
        update_dust(context.scene)
        return {"FINISHED"}


class PROMODUST_OT_use_scene_camera(bpy.types.Operator):
    bl_idname = "promodust.use_scene_camera"
    bl_label = "Use Scene Camera"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not context.scene.camera:
            self.report({"ERROR"}, "The scene has no active camera.")
            return {"CANCELLED"}

        context.scene.promo_dust_settings.camera = context.scene.camera
        update_dust(context.scene)
        return {"FINISHED"}


class PROMODUST_OT_delete(bpy.types.Operator):
    bl_idname = "promodust.delete"
    bl_label = "Delete Dust"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = bpy.data.objects.get(DUST_OBJ_NAME)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
        return {"FINISHED"}


# ------------------------------------------------------------
# UI
# ------------------------------------------------------------

class PROMODUST_PT_panel(bpy.types.Panel):
    bl_label = "Promo Dust / Glitter"
    bl_idname = "PROMODUST_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Promo FX"

    def draw(self, context):
        layout = self.layout
        s = context.scene.promo_dust_settings

        box = layout.box()
        box.label(text="Setup", icon="OUTLINER_OB_POINTCLOUD")
        box.prop(s, "target")
        box.operator("promodust.use_selected", icon="EYEDROPPER")
        box.prop(s, "camera")
        box.operator("promodust.use_scene_camera", icon="CAMERA_DATA")

        box = layout.box()
        box.label(text="Camera Coverage", icon="CAMERA_DATA")
        box.prop(s, "frame_coverage")
        box.prop(s, "front_depth")
        box.prop(s, "back_depth")

        box = layout.box()
        box.label(text="Particles", icon="PARTICLES")
        box.prop(s, "count")
        box.prop(s, "size")
        box.prop(s, "size_random")
        box.prop(s, "seed")
        box.prop(s, "live_update")

        box = layout.box()
        box.label(text="Material", icon="MATERIAL")
        box.prop(s, "color")
        box.prop(s, "emission_strength")
        row = box.row(align=True)
        row.prop(s, "roughness")
        row.prop(s, "metallic")

        box = layout.box()
        box.label(text="Depth of Field", icon="CAMERA_DATA")
        box.prop(s, "manage_dof")
        col = box.column()
        col.enabled = s.manage_dof
        col.prop(s, "fstop")

        layout.separator()

        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("promodust.create", icon="FILE_REFRESH")
        row.operator("promodust.delete", icon="TRASH")

        obj = bpy.data.objects.get(DUST_OBJ_NAME)
        if obj:
            layout.label(text="Dust object exists", icon="CHECKMARK")
        else:
            layout.label(text="Press Create / Rebuild Dust", icon="INFO")


classes = (
    PROMODUST_Settings,
    PROMODUST_OT_create,
    PROMODUST_OT_use_selected,
    PROMODUST_OT_use_scene_camera,
    PROMODUST_OT_delete,
    PROMODUST_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.promo_dust_settings = PointerProperty(
        type=PROMODUST_Settings
    )

    if promo_dust_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(promo_dust_depsgraph)


def unregister():
    if promo_dust_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(promo_dust_depsgraph)

    if hasattr(bpy.types.Scene, "promo_dust_settings"):
        del bpy.types.Scene.promo_dust_settings

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
