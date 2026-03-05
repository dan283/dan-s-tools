bl_info = {
    "name": "Portrait / Model Lighting + Camera + Backdrop Presets",
    "author": "ChatGPT",
    "version": (1, 6, 3),
    "blender": (3, 6, 0),
    "location": "View3D > N Panel > Lighting",
    "description": "Studio lighting presets with auto HDRI apply, optional auto-update, camera presets, and a robust cyclorama backdrop (procedural curved strip, no bevel op).",
    "category": "Lighting",
}

import bpy
import math
import bmesh
from mathutils import Vector


RIG_COLLECTION_NAME = "PortraitLightRig"
CAMERA_NAME = "PLP_Camera"
TARGET_NAME = "PLP_Target"

BACKDROP_NAME = "PLP_Backdrop"
BACKDROP_MESH_NAME = "PLP_Backdrop_Mesh"
BACKDROP_MAT_NAME = "PLP_Backdrop_Mat"


# ---------------------------
# Utilities
# ---------------------------

def ensure_collection(scene, name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    if col.name not in scene.collection.children:
        scene.collection.children.link(col)
    return col


def unlink_from_all_collections(obj):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)


def link_to_collection(obj, col):
    if obj.name not in col.objects:
        col.objects.link(obj)


def collection_objects_recursive(col):
    out = []
    if not col:
        return out
    out.extend(list(col.objects))
    for ch in col.children:
        out.extend(collection_objects_recursive(ch))
    return out


def compute_collection_bbox(col):
    objs = [
        o for o in collection_objects_recursive(col)
        if o.type in {"MESH", "CURVE", "SURFACE", "FONT", "META"} and o.visible_get()
    ]
    if not objs:
        return Vector((0, 0, 0)), Vector((1, 1, 1)), 1.0

    min_v = Vector((1e18, 1e18, 1e18))
    max_v = Vector((-1e18, -1e18, -1e18))

    for o in objs:
        for corner in o.bound_box:
            w = o.matrix_world @ Vector(corner)
            min_v.x = min(min_v.x, w.x)
            min_v.y = min(min_v.y, w.y)
            min_v.z = min(min_v.z, w.z)
            max_v.x = max(max_v.x, w.x)
            max_v.y = max(max_v.y, w.y)
            max_v.z = max(max_v.z, w.z)

    center = (min_v + max_v) * 0.5
    dims = (max_v - min_v)
    dims = Vector((max(dims.x, 0.5), max(dims.y, 0.5), max(dims.z, 0.5)))
    radius = max(dims.x, dims.y, dims.z) * 0.5
    radius = max(radius, 0.25)
    return center, dims, radius


def set_scene_color_management(scene, use_filmic=True, look="Medium High Contrast", exposure=0.0):
    vs = scene.view_settings
    if use_filmic:
        vs.view_transform = "Filmic"
        if look in vs.bl_rna.properties["look"].enum_items.keys():
            vs.look = look
    vs.exposure = exposure


def ensure_renderer_defaults(scene, engine, use_denoise=True):
    scene.render.engine = engine

    if engine == "CYCLES":
        cy = scene.cycles
        # Blender 3.x had feature_set; Blender 4.x removed it.
        if hasattr(cy, "feature_set"):
            try:
                cy.feature_set = "SUPPORTED"
            except Exception:
                pass
        if hasattr(cy, "samples"):
            cy.samples = max(int(cy.samples), 128)
        if hasattr(cy, "use_denoising"):
            cy.use_denoising = bool(use_denoise)
        try:
            view_layer = scene.view_layers[0] if scene.view_layers else None
            if view_layer and hasattr(view_layer, "cycles"):
                vlc = view_layer.cycles
                if hasattr(vlc, "use_denoising"):
                    vlc.use_denoising = bool(use_denoise)
        except Exception:
            pass

    elif engine == "BLENDER_EEVEE":
        ee = scene.eevee
        for attr, val in (
            ("use_gtao", True),
            ("use_bloom", False),
            ("use_ssr", True),
            ("use_soft_shadows", True),
        ):
            if hasattr(ee, attr):
                try:
                    setattr(ee, attr, val)
                except Exception:
                    pass


def polar_offset(distance, azimuth_deg, elevation_deg):
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    x = math.sin(az) * math.cos(el)
    y = math.cos(az) * math.cos(el)
    z = math.sin(el)
    return Vector((x, y, z)) * distance


def create_empty_target(name, location, rig_col):
    empty = bpy.data.objects.get(name)
    if empty is None:
        empty = bpy.data.objects.new(name, None)
        empty.empty_display_type = "SPHERE"
        empty.empty_display_size = 0.2
    empty.location = location
    unlink_from_all_collections(empty)
    link_to_collection(empty, rig_col)
    return empty


def create_light(name, light_type, rig_col):
    obj = bpy.data.objects.get(name)
    if obj and obj.type == "LIGHT":
        obj.data.type = light_type
        unlink_from_all_collections(obj)
        link_to_collection(obj, rig_col)
        return obj

    light_data = bpy.data.lights.new(name=name + "_DATA", type=light_type)
    obj = bpy.data.objects.new(name, light_data)
    unlink_from_all_collections(obj)
    link_to_collection(obj, rig_col)
    return obj


def add_track_to(obj, target):
    for c in list(obj.constraints):
        if c.type == "TRACK_TO" and c.name.startswith("PLP_"):
            obj.constraints.remove(c)
    con = obj.constraints.new(type="TRACK_TO")
    con.name = "PLP_TrackTo"
    con.target = target
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return con


def set_area_softness(light_obj, softness_size):
    ld = light_obj.data
    ld.type = "AREA"
    ld.shape = "RECTANGLE"
    ld.size = float(softness_size)
    ld.size_y = float(softness_size) * 0.75


def set_light_common(scene, light_obj, strength, shadow_soft=0.0):
    ld = light_obj.data
    ld.energy = float(strength)
    if scene.render.engine == "BLENDER_EEVEE":
        if hasattr(ld, "use_shadow"):
            ld.use_shadow = True
        if hasattr(ld, "shadow_soft_size"):
            ld.shadow_soft_size = float(shadow_soft)


def remove_rig(scene):
    col = bpy.data.collections.get(RIG_COLLECTION_NAME)
    if not col:
        return
    for obj in list(col.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    if col.name in scene.collection.children:
        scene.collection.children.unlink(col)
    bpy.data.collections.remove(col)


# ---------------------------
# HDRI (auto-apply)
# ---------------------------

def ensure_hdri_nodes(scene):
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world

    world.use_nodes = True
    nt = world.node_tree
    nodes = nt.nodes
    links = nt.links

    out = nodes.get("World Output")
    if out is None:
        out = nodes.new("ShaderNodeOutputWorld")
        out.location = (500, 0)

    bg = nodes.get("PLP_Background")
    if bg is None:
        bg = nodes.new("ShaderNodeBackground")
        bg.name = "PLP_Background"
        bg.location = (200, 0)

    env = nodes.get("PLP_EnvironmentTexture")
    if env is None:
        env = nodes.new("ShaderNodeTexEnvironment")
        env.name = "PLP_EnvironmentTexture"
        env.location = (-500, 0)

    mapping = nodes.get("PLP_Mapping")
    if mapping is None:
        mapping = nodes.new("ShaderNodeMapping")
        mapping.name = "PLP_Mapping"
        mapping.location = (-850, 0)

    texcoord = nodes.get("PLP_TexCoord")
    if texcoord is None:
        texcoord = nodes.new("ShaderNodeTexCoord")
        texcoord.name = "PLP_TexCoord"
        texcoord.location = (-1100, 0)

    def clear_socket(input_socket):
        for l in list(input_socket.links):
            links.remove(l)

    clear_socket(mapping.inputs["Vector"])
    links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])

    clear_socket(env.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])

    clear_socket(bg.inputs["Color"])
    links.new(env.outputs["Color"], bg.inputs["Color"])

    clear_socket(out.inputs["Surface"])
    links.new(bg.outputs["Background"], out.inputs["Surface"])

    return env, mapping, bg


def apply_hdri(scene, settings):
    if not scene or not settings.use_hdri:
        return
    env, mapping, bg = ensure_hdri_nodes(scene)
    if settings.hdri_image:
        env.image = settings.hdri_image
    bg.inputs["Strength"].default_value = float(settings.hdri_strength)
    mapping.inputs["Rotation"].default_value[2] = math.radians(float(settings.hdri_rotation_deg))


def apply_viewport_shading(context, settings):
    if not context or not context.window:
        return
    scr = context.window.screen
    if not scr:
        return
    for area in scr.areas:
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    shading = space.shading
                    if hasattr(shading, "use_scene_world"):
                        shading.use_scene_world = settings.vp_use_scene_world
                    if hasattr(shading, "use_scene_lights"):
                        shading.use_scene_lights = settings.vp_use_scene_lights


# ---------------------------
# Lighting Presets
# ---------------------------

PRESETS = [
    ("THREE_POINT", "3-Point (Key/Fill/Rim)", "Classic studio 3-point setup"),
    ("CLAMSHELL", "Clamshell (Beauty)", "Key above + fill below for beauty lighting"),
    ("REMBRANDT", "Rembrandt", "Key 45° with subtle fill for drama"),
    ("RIM_STRONG", "Strong Rim / Silhouette", "Strong back/rim + soft front fill"),
    ("HIGH_KEY", "High Key", "Bright, soft, low-contrast studio look"),
    ("LOW_KEY", "Low Key", "Darker mood, strong key, minimal fill"),
    ("PRODUCT_SOFTBOX", "Product Softbox", "Large soft sources, even reflections"),
]


def build_lighting(scene, subject_col, preset_id, settings):
    rig_col = ensure_collection(scene, RIG_COLLECTION_NAME)
    center, dims, radius = compute_collection_bbox(subject_col)
    target = create_empty_target(TARGET_NAME, center, rig_col)

    dist = radius * settings.distance_mult
    height = radius * settings.height_mult
    soft = max(radius * settings.softness_mult, 0.25)

    scale = max(radius, 0.01) ** 2 if settings.auto_energy else 1.0
    key_strength = (settings.base_key_energy * scale) * settings.all_lights_mult
    fill_strength = (settings.base_fill_energy * scale) * settings.all_lights_mult
    rim_strength = (settings.base_rim_energy * scale) * settings.all_lights_mult
    bg_strength = (settings.base_bg_energy * scale) * settings.all_lights_mult

    key = create_light("PLP_Key", "AREA", rig_col)
    fill = create_light("PLP_Fill", "AREA", rig_col)
    rim = create_light("PLP_Rim", "AREA", rig_col)
    bg = create_light("PLP_BG", "AREA", rig_col)

    for L in (key, fill, rim, bg):
        add_track_to(L, target)
        L.data.use_nodes = False

    if preset_id == "THREE_POINT":
        key.location = center + polar_offset(dist, 320, 35) + Vector((0, 0, height))
        fill.location = center + polar_offset(dist * 0.9, 40, 15) + Vector((0, 0, height * 0.4))
        rim.location = center + polar_offset(dist * 1.1, 180, 50) + Vector((0, 0, height * 0.8))
        bg.location = center + polar_offset(dist * 1.4, 180, 10) + Vector((0, 0, height * 0.2))

        set_area_softness(key, soft * 1.0)
        set_area_softness(fill, soft * 1.2)
        set_area_softness(rim, soft * 0.6)
        set_area_softness(bg, soft * 2.0)

        set_light_common(scene, key, key_strength, shadow_soft=soft * 0.02)
        set_light_common(scene, fill, fill_strength, shadow_soft=soft * 0.02)
        set_light_common(scene, rim, rim_strength, shadow_soft=soft * 0.02)
        set_light_common(scene, bg, bg_strength, shadow_soft=soft * 0.02)

    elif preset_id == "CLAMSHELL":
        key.location = center + polar_offset(dist * 0.9, 0, 55) + Vector((0, 0, height * 0.6))
        fill.location = center + polar_offset(dist * 0.7, 0, -25) + Vector((0, 0, -height * 0.2))
        rim.location = center + polar_offset(dist * 1.1, 180, 35) + Vector((0, 0, height * 0.5))
        bg.location = center + polar_offset(dist * 1.6, 180, 0)

        set_area_softness(key, soft * 1.4)
        set_area_softness(fill, soft * 1.6)
        set_area_softness(rim, soft * 0.7)
        set_area_softness(bg, soft * 2.2)

        set_light_common(scene, key, key_strength * 1.1, shadow_soft=soft * 0.02)
        set_light_common(scene, fill, fill_strength * 0.9, shadow_soft=soft * 0.02)
        set_light_common(scene, rim, rim_strength * 0.6, shadow_soft=soft * 0.02)
        set_light_common(scene, bg, bg_strength * 0.8, shadow_soft=soft * 0.02)

    elif preset_id == "REMBRANDT":
        key.location = center + polar_offset(dist, 315, 45) + Vector((0, 0, height * 0.6))
        fill.location = center + polar_offset(dist * 1.1, 30, 10) + Vector((0, 0, height * 0.2))
        rim.location = center + polar_offset(dist * 1.2, 190, 55) + Vector((0, 0, height * 0.7))
        bg.location = center + polar_offset(dist * 1.6, 180, 0)

        set_area_softness(key, soft * 0.8)
        set_area_softness(fill, soft * 1.3)
        set_area_softness(rim, soft * 0.6)
        set_area_softness(bg, soft * 2.0)

        set_light_common(scene, key, key_strength * 1.2, shadow_soft=soft * 0.02)
        set_light_common(scene, fill, fill_strength * 0.5, shadow_soft=soft * 0.02)
        set_light_common(scene, rim, rim_strength * 0.7, shadow_soft=soft * 0.02)
        set_light_common(scene, bg, bg_strength * 0.6, shadow_soft=soft * 0.02)

    elif preset_id == "RIM_STRONG":
        key.location = center + polar_offset(dist * 1.25, 180, 50) + Vector((0, 0, height * 0.8))
        fill.location = center + polar_offset(dist * 0.8, 0, 10) + Vector((0, 0, height * 0.2))
        rim.location = center + polar_offset(dist * 1.1, 200, 30) + Vector((0, 0, height * 0.6))
        bg.location = center + polar_offset(dist * 1.8, 180, 0)

        set_area_softness(key, soft * 0.9)
        set_area_softness(fill, soft * 1.5)
        set_area_softness(rim, soft * 0.6)
        set_area_softness(bg, soft * 2.4)

        set_light_common(scene, key, key_strength * 1.4, shadow_soft=soft * 0.02)
        set_light_common(scene, fill, fill_strength * 0.6, shadow_soft=soft * 0.02)
        set_light_common(scene, rim, rim_strength * 1.2, shadow_soft=soft * 0.02)
        set_light_common(scene, bg, bg_strength * 0.5, shadow_soft=soft * 0.02)

    elif preset_id == "HIGH_KEY":
        key.location = center + polar_offset(dist * 0.85, 330, 35) + Vector((0, 0, height * 0.4))
        fill.location = center + polar_offset(dist * 0.85, 30, 25) + Vector((0, 0, height * 0.2))
        rim.location = center + polar_offset(dist * 1.1, 180, 35) + Vector((0, 0, height * 0.5))
        bg.location = center + polar_offset(dist * 1.3, 180, 0)

        set_area_softness(key, soft * 1.8)
        set_area_softness(fill, soft * 2.0)
        set_area_softness(rim, soft * 1.2)
        set_area_softness(bg, soft * 3.0)

        set_light_common(scene, key, key_strength * 1.0, shadow_soft=soft * 0.02)
        set_light_common(scene, fill, fill_strength * 1.1, shadow_soft=soft * 0.02)
        set_light_common(scene, rim, rim_strength * 0.4, shadow_soft=soft * 0.02)
        set_light_common(scene, bg, bg_strength * 1.2, shadow_soft=soft * 0.02)

    elif preset_id == "LOW_KEY":
        key.location = center + polar_offset(dist, 320, 40) + Vector((0, 0, height * 0.6))
        fill.location = center + polar_offset(dist * 1.2, 30, 10) + Vector((0, 0, height * 0.2))
        rim.location = center + polar_offset(dist * 1.2, 190, 55) + Vector((0, 0, height * 0.7))
        bg.location = center + polar_offset(dist * 1.8, 180, 0)

        set_area_softness(key, soft * 0.7)
        set_area_softness(fill, soft * 1.0)
        set_area_softness(rim, soft * 0.6)
        set_area_softness(bg, soft * 1.8)

        set_light_common(scene, key, key_strength * 1.3, shadow_soft=soft * 0.02)
        set_light_common(scene, fill, fill_strength * 0.25, shadow_soft=soft * 0.02)
        set_light_common(scene, rim, rim_strength * 0.9, shadow_soft=soft * 0.02)
        set_light_common(scene, bg, bg_strength * 0.2, shadow_soft=soft * 0.02)

    elif preset_id == "PRODUCT_SOFTBOX":
        key.location = center + polar_offset(dist * 0.9, 315, 20) + Vector((0, 0, height * 0.2))
        fill.location = center + polar_offset(dist * 0.9, 45, 20) + Vector((0, 0, height * 0.2))
        rim.location = center + polar_offset(dist * 1.1, 180, 30) + Vector((0, 0, height * 0.4))
        bg.location = center + polar_offset(dist * 1.4, 180, 0)

        set_area_softness(key, soft * 2.4)
        set_area_softness(fill, soft * 2.4)
        set_area_softness(rim, soft * 1.2)
        set_area_softness(bg, soft * 2.6)

        set_light_common(scene, key, key_strength * 1.0, shadow_soft=soft * 0.02)
        set_light_common(scene, fill, fill_strength * 0.95, shadow_soft=soft * 0.02)
        set_light_common(scene, rim, rim_strength * 0.35, shadow_soft=soft * 0.02)
        set_light_common(scene, bg, bg_strength * 0.9, shadow_soft=soft * 0.02)

    if settings.set_color_management:
        set_scene_color_management(scene, use_filmic=True, look=settings.filmic_look, exposure=settings.exposure)
    if settings.set_engine:
        ensure_renderer_defaults(scene, settings.render_engine, use_denoise=settings.cycles_denoise)
    if settings.use_hdri:
        apply_hdri(scene, settings)

    return rig_col, target, (center, dims, radius)


# ---------------------------
# Camera
# ---------------------------

ASPECTS = [
    ("1_1", "1:1", ""),
    ("4_3", "4:3", ""),
    ("3_2", "3:2", ""),
    ("16_9", "16:9", ""),
    ("9_16", "9:16 (Portrait)", ""),
    ("2_3", "2:3 (Portrait)", ""),
]

def aspect_to_xy(aspect_id, base=1080):
    if aspect_id == "1_1":
        return base, base
    if aspect_id == "4_3":
        return int(base * 4/3), base
    if aspect_id == "3_2":
        return int(base * 3/2), base
    if aspect_id == "16_9":
        return int(base * 16/9), base
    if aspect_id == "9_16":
        return base, int(base * 16/9)
    if aspect_id == "2_3":
        return base, int(base * 3/2)
    return int(base * 16/9), base


def create_or_update_camera(scene, rig_col, target_obj, bbox_info, settings):
    center, dims, radius = bbox_info

    cam = bpy.data.objects.get(CAMERA_NAME)
    if cam and cam.type == "CAMERA":
        unlink_from_all_collections(cam)
        link_to_collection(cam, rig_col)
    else:
        cam_data = bpy.data.cameras.new(CAMERA_NAME + "_DATA")
        cam = bpy.data.objects.new(CAMERA_NAME, cam_data)
        unlink_from_all_collections(cam)
        link_to_collection(cam, rig_col)

    if settings.camera_set_active:
        scene.camera = cam

    cam.data.type = "PERSP"
    cam.data.lens_unit = "MILLIMETERS"
    cam.data.lens = settings.camera_lens_mm
    cam.data.sensor_fit = "AUTO"

    fov_v = 2.0 * math.atan((cam.data.sensor_height) / (2.0 * cam.data.lens))
    fit_h = max(dims.z, radius * 1.6) * settings.camera_fit_height_mult
    dist = (fit_h * 0.5) / max(math.tan(fov_v * 0.5), 1e-6)
    dist = max(dist, radius * 1.5) * settings.camera_distance_mult

    cam.location = center + Vector((0, dist, radius * settings.camera_elevation_mult))

    for c in list(cam.constraints):
        if c.type == "TRACK_TO" and c.name.startswith("PLP_"):
            cam.constraints.remove(c)
    con = cam.constraints.new(type="TRACK_TO")
    con.name = "PLP_CamTrack"
    con.target = target_obj
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"

    res_x, res_y = aspect_to_xy(settings.camera_aspect, base=settings.camera_base_res)
    scene.render.resolution_x = res_x
    scene.render.resolution_y = res_y
    scene.render.resolution_percentage = 100

    cam.data.dof.use_dof = settings.camera_use_dof
    if settings.camera_use_dof:
        cam.data.dof.focus_object = target_obj
        cam.data.dof.aperture_fstop = settings.camera_fstop

    return cam


# ---------------------------
# Backdrop (ROBUST CURVE STRIP; no bevel op)
# ---------------------------

def ensure_backdrop_material():
    mat = bpy.data.materials.get(BACKDROP_MAT_NAME)
    if mat is None:
        mat = bpy.data.materials.new(BACKDROP_MAT_NAME)
        mat.use_nodes = True
        nt = mat.node_tree
        nodes = nt.nodes
        links = nt.links
        nodes.clear()

        out = nodes.new("ShaderNodeOutputMaterial")
        out.location = (300, 0)
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 0)
        bsdf.inputs["Roughness"].default_value = 0.6
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def ensure_backdrop_object(scene, rig_col):
    obj = bpy.data.objects.get(BACKDROP_NAME)
    if obj and obj.type != "MESH":
        bpy.data.objects.remove(obj, do_unlink=True)
        obj = None

    if obj is None:
        mesh = bpy.data.meshes.get(BACKDROP_MESH_NAME)
        if mesh is None:
            mesh = bpy.data.meshes.new(BACKDROP_MESH_NAME)
        obj = bpy.data.objects.new(BACKDROP_NAME, mesh)

    unlink_from_all_collections(obj)
    link_to_collection(obj, rig_col)
    obj.display_type = 'TEXTURED'
    return obj


def rebuild_backdrop_mesh(obj, width, floor_forward, floor_back, wall_height, curve_radius, curve_segments):
    """
    Cyclorama:
    - Wall plane at Y = -floor_back (behind subject), from Z=curve_radius up to wall_height.
    - Floor plane at Z = 0, from Y = (-floor_back + curve_radius) forward to +floor_forward.
    - Curved strip (quarter-circle) connects wall to floor with perfectly clean quads.
      This avoids bmesh bevel artifacts/crisscross completely.
    """
    me = obj.data
    me.clear_geometry()

    bm = bmesh.new()

    w2 = width * 0.5
    y_back = -float(floor_back)           # behind subject (negative Y)
    y_front = float(floor_forward)        # in front of subject (positive Y)

    r = max(float(curve_radius), 0.0)
    segs = max(int(curve_segments), 1)

    # If radius is too big for available dimensions, clamp it.
    # Need room for:
    # - wall: wall_height >= r
    # - floor start: y_back + r must be <= y_front (otherwise floor would invert)
    r = min(r, float(wall_height) * 0.95)
    r = min(r, max((y_front - y_back) * 0.45, 0.0))
    # Also keep r smaller than floor_back itself to avoid weirdness
    r = min(r, float(floor_back) * 0.95)

    # Helper to create a vertex
    def v(x, y, z):
        return bm.verts.new((x, y, z))

    # --- Create curve rings (two verts per ring: left/right) ---
    # Quarter circle center at (y_back + r, z = r)
    # Param t: 0..pi/2
    # point(y,z) = (center_y - r*cos t, center_z - r*sin t)
    curve_L = []
    curve_R = []
    center_y = y_back + r
    center_z = r

    if r > 1e-6:
        for i in range(segs + 1):
            t = (math.pi * 0.5) * (i / segs)
            y = center_y - r * math.cos(t)     # t=0 -> y_back ; t=pi/2 -> y_back+r
            z = center_z - r * math.sin(t)     # t=0 -> r      ; t=pi/2 -> 0
            curve_L.append(v(-w2, y, z))
            curve_R.append(v( w2, y, z))
    else:
        # No curve: just a sharp edge, create seam line at y_back, z=0
        curve_L = [v(-w2, y_back, 0.0)]
        curve_R = [v( w2, y_back, 0.0)]
        segs = 0  # no faces for curve strip

    # --- Floor plane (starts where curve ends on floor) ---
    floor_start_y = (y_back + r) if r > 1e-6 else y_back
    fL0 = v(-w2, floor_start_y, 0.0)
    fR0 = v( w2, floor_start_y, 0.0)
    fL1 = v(-w2, y_front, 0.0)
    fR1 = v( w2, y_front, 0.0)

    # Floor face (quad)
    # order chosen to keep normals consistent (upwards-ish)
    bm.faces.new((fL0, fR0, fR1, fL1))

    # Connect curve to floor (if curved)
    if r > 1e-6:
        # last curve ring should match floor start position (y_back+r, z=0)
        # create faces between last ring and floor edge (fL0/fR0)
        lastL = curve_L[-1]
        lastR = curve_R[-1]
        # Make sure we connect: curve -> floor (same y,z)
        bm.faces.new((lastL, lastR, fR0, fL0))

    # --- Wall plane (starts where curve ends on wall) ---
    wall_start_z = r if r > 1e-6 else 0.0
    wL0 = v(-w2, y_back, wall_start_z)
    wR0 = v( w2, y_back, wall_start_z)
    wL1 = v(-w2, y_back, float(wall_height))
    wR1 = v( w2, y_back, float(wall_height))

    bm.faces.new((wL0, wR0, wR1, wL1))

    # Connect curve to wall (if curved)
    if r > 1e-6:
        firstL = curve_L[0]  # (y_back, z=r)
        firstR = curve_R[0]
        bm.faces.new((wL0, wR0, firstR, firstL))

    # --- Curve strip faces (between curve rings) ---
    if r > 1e-6:
        for i in range(segs):
            aL = curve_L[i]
            aR = curve_R[i]
            bR = curve_R[i + 1]
            bL = curve_L[i + 1]
            bm.faces.new((aL, aR, bR, bL))

    # Clean up & normals
    bm.normal_update()
    try:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    except Exception:
        pass

    bm.to_mesh(me)
    bm.free()
    me.update()


def create_or_update_backdrop(scene, rig_col, bbox_info, settings):
    center, dims, radius = bbox_info
    obj = ensure_backdrop_object(scene, rig_col)

    cam = bpy.data.objects.get(CAMERA_NAME)
    cam_dist = (cam.location - center).length if cam and cam.type == "CAMERA" else radius * 4.0

    width = max(radius * settings.backdrop_width_mult, cam_dist * settings.backdrop_cam_width_mult)

    # floor extents: under subject, extends forward and backward; wall at back
    floor_forward = max(radius * settings.backdrop_floor_forward_mult, radius * 2.0)
    floor_back = max(radius * settings.backdrop_floor_back_mult, cam_dist * settings.backdrop_cam_depth_mult)
    wall_height = max(radius * settings.backdrop_height_mult, radius * 2.0)

    # Reuse existing "bevel" controls as curve radius controls (UI text stays "Bevel Curve")
    curve_r = max(radius * settings.backdrop_bevel_mult, settings.backdrop_bevel_min)
    curve_r = min(curve_r, min(floor_back, wall_height) * 0.45)

    rebuild_backdrop_mesh(
        obj=obj,
        width=float(width),
        floor_forward=float(floor_forward),
        floor_back=float(floor_back),
        wall_height=float(wall_height),
        curve_radius=float(curve_r),
        curve_segments=int(settings.backdrop_bevel_segments),
    )

    # Put floor under subject feet plane
    obj.location = Vector((center.x, center.y, center.z - dims.z * 0.5))
    obj.rotation_euler = (0.0, 0.0, 0.0)

    mat = ensure_backdrop_material()
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    if mat.use_nodes:
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (
                settings.backdrop_color[0],
                settings.backdrop_color[1],
                settings.backdrop_color[2],
                1.0
            )
            bsdf.inputs["Roughness"].default_value = float(settings.backdrop_roughness)

    obj.hide_viewport = not settings.backdrop_viewport_visible
    obj.hide_render = not settings.backdrop_render_visible
    return obj


# ---------------------------
# Auto-update callbacks
# ---------------------------

def _maybe_auto_update_lights(self, context):
    if not context or not context.scene:
        return
    st = context.scene.plp_settings
    if not st.auto_update_lights or not st.subject_collection:
        return
    build_lighting(context.scene, st.subject_collection, st.preset, st)


def _on_hdri_update(self, context):
    if not context or not context.scene:
        return
    apply_hdri(context.scene, context.scene.plp_settings)


def _on_viewport_update(self, context):
    if not context:
        return
    apply_viewport_shading(context, context.scene.plp_settings)


def _on_backdrop_update(self, context):
    if not context or not context.scene:
        return
    st = context.scene.plp_settings
    if not st.backdrop_live_update or not st.subject_collection:
        return
    rig_col = ensure_collection(context.scene, RIG_COLLECTION_NAME)
    center, dims, radius = compute_collection_bbox(st.subject_collection)
    create_empty_target(TARGET_NAME, center, rig_col)
    create_or_update_backdrop(context.scene, rig_col, (center, dims, radius), st)


# ---------------------------
# Properties
# ---------------------------

class PLP_Settings(bpy.types.PropertyGroup):
    subject_collection: bpy.props.PointerProperty(name="Subject Collection", type=bpy.types.Collection)

    # Lighting
    preset: bpy.props.EnumProperty(name="Light Preset", items=PRESETS, default="THREE_POINT", update=_maybe_auto_update_lights)
    auto_update_lights: bpy.props.BoolProperty(name="Auto Update Lights", default=True)

    distance_mult: bpy.props.FloatProperty(name="Distance Mult", default=2.0, min=0.2, max=10.0, update=_maybe_auto_update_lights)
    height_mult: bpy.props.FloatProperty(name="Height Mult", default=0.6, min=-2.0, max=5.0, update=_maybe_auto_update_lights)
    softness_mult: bpy.props.FloatProperty(name="Softness Mult", default=0.8, min=0.05, max=10.0, update=_maybe_auto_update_lights)

    all_lights_mult: bpy.props.FloatProperty(name="All Lights Mult", default=1.0, min=0.0, max=50.0, update=_maybe_auto_update_lights)
    auto_energy: bpy.props.BoolProperty(name="Auto Energy From Scale", default=True, update=_maybe_auto_update_lights)
    base_key_energy: bpy.props.FloatProperty(name="Base Key", default=80.0, min=0.0, max=100000.0, update=_maybe_auto_update_lights)
    base_fill_energy: bpy.props.FloatProperty(name="Base Fill", default=30.0, min=0.0, max=100000.0, update=_maybe_auto_update_lights)
    base_rim_energy: bpy.props.FloatProperty(name="Base Rim", default=45.0, min=0.0, max=100000.0, update=_maybe_auto_update_lights)
    base_bg_energy: bpy.props.FloatProperty(name="Base BG", default=0.0, min=0.0, max=100000.0, update=_maybe_auto_update_lights)

    set_engine: bpy.props.BoolProperty(name="Set Render Engine Defaults", default=True, update=_maybe_auto_update_lights)
    render_engine: bpy.props.EnumProperty(name="Engine", items=[("CYCLES", "Cycles", ""), ("BLENDER_EEVEE", "Eevee", "")], default="CYCLES", update=_maybe_auto_update_lights)
    cycles_denoise: bpy.props.BoolProperty(name="Cycles Denoise", default=True, update=_maybe_auto_update_lights)

    set_color_management: bpy.props.BoolProperty(name="Set Color Management", default=True, update=_maybe_auto_update_lights)
    filmic_look: bpy.props.EnumProperty(
        name="Filmic Look",
        items=[
            ("None", "None", ""),
            ("Medium Contrast", "Medium Contrast", ""),
            ("Medium High Contrast", "Medium High Contrast", ""),
            ("High Contrast", "High Contrast", ""),
            ("Very High Contrast", "Very High Contrast", ""),
        ],
        default="Medium High Contrast",
        update=_maybe_auto_update_lights
    )
    exposure: bpy.props.FloatProperty(name="Exposure", default=0.0, min=-10.0, max=10.0, update=_maybe_auto_update_lights)

    # HDRI
    use_hdri: bpy.props.BoolProperty(name="Use HDRI", default=False, update=_on_hdri_update)
    hdri_image: bpy.props.PointerProperty(name="HDRI Image", type=bpy.types.Image, update=_on_hdri_update)
    hdri_strength: bpy.props.FloatProperty(name="HDRI Strength", default=1.0, min=0.0, max=50.0, update=_on_hdri_update)
    hdri_rotation_deg: bpy.props.FloatProperty(name="HDRI Rotation (deg)", default=0.0, min=-360.0, max=360.0, update=_on_hdri_update)

    # Viewport
    vp_use_scene_world: bpy.props.BoolProperty(name="Viewport: Use Scene World", default=True, update=_on_viewport_update)
    vp_use_scene_lights: bpy.props.BoolProperty(name="Viewport: Use Scene Lights", default=True, update=_on_viewport_update)

    # Camera
    camera_set_active: bpy.props.BoolProperty(name="Set as Active Camera", default=True)
    camera_aspect: bpy.props.EnumProperty(name="Aspect", items=ASPECTS, default="16_9")
    camera_base_res: bpy.props.IntProperty(name="Base Res (short side)", default=1080, min=240, max=7680)
    camera_lens_mm: bpy.props.FloatProperty(name="Lens (mm)", default=50.0, min=10.0, max=200.0)
    camera_fit_height_mult: bpy.props.FloatProperty(name="Fit Height Mult", default=1.35, min=0.8, max=3.0)
    camera_distance_mult: bpy.props.FloatProperty(name="Distance Mult", default=1.20, min=0.5, max=5.0)
    camera_elevation_mult: bpy.props.FloatProperty(name="Elevation Mult", default=0.45, min=-1.0, max=2.0)
    camera_use_dof: bpy.props.BoolProperty(name="Use DOF", default=False)
    camera_fstop: bpy.props.FloatProperty(name="F-Stop", default=2.8, min=0.7, max=22.0)

    # Backdrop
    backdrop_live_update: bpy.props.BoolProperty(name="Backdrop Live Update", default=True)

    backdrop_width_mult: bpy.props.FloatProperty(name="Width Mult (radius)", default=8.0, min=1.0, max=50.0, update=_on_backdrop_update)
    backdrop_floor_forward_mult: bpy.props.FloatProperty(name="Floor Forward Mult (radius)", default=4.0, min=0.5, max=80.0, update=_on_backdrop_update)
    backdrop_floor_back_mult: bpy.props.FloatProperty(name="Floor Back Mult (radius)", default=10.0, min=1.0, max=200.0, update=_on_backdrop_update)
    backdrop_height_mult: bpy.props.FloatProperty(name="Wall Height Mult (radius)", default=5.0, min=1.0, max=50.0, update=_on_backdrop_update)

    backdrop_cam_width_mult: bpy.props.FloatProperty(name="Min Width vs Camera", default=1.1, min=0.5, max=5.0, update=_on_backdrop_update)
    backdrop_cam_depth_mult: bpy.props.FloatProperty(name="Min Back Depth vs Camera", default=1.4, min=0.5, max=8.0, update=_on_backdrop_update)

    # Kept names for compatibility; now used as CURVE radius controls
    backdrop_bevel_mult: bpy.props.FloatProperty(name="Bevel Mult (radius)", default=0.35, min=0.0, max=5.0, update=_on_backdrop_update)
    backdrop_bevel_min: bpy.props.FloatProperty(name="Bevel Min", default=0.03, min=0.0, max=10.0, update=_on_backdrop_update)
    backdrop_bevel_segments: bpy.props.IntProperty(name="Bevel Segments", default=12, min=1, max=64, update=_on_backdrop_update)

    backdrop_color: bpy.props.FloatVectorProperty(name="Color", subtype='COLOR', size=3, min=0.0, max=1.0, default=(0.18, 0.18, 0.20), update=_on_backdrop_update)
    backdrop_roughness: bpy.props.FloatProperty(name="Roughness", default=0.6, min=0.0, max=1.0, update=_on_backdrop_update)

    backdrop_viewport_visible: bpy.props.BoolProperty(name="Viewport Visible", default=True, update=_on_backdrop_update)
    backdrop_render_visible: bpy.props.BoolProperty(name="Render Visible", default=True, update=_on_backdrop_update)


# ---------------------------
# Operators
# ---------------------------

class PLP_OT_update_lighting(bpy.types.Operator):
    bl_idname = "plp.update_lighting"
    bl_label = "Update Lighting"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        st = context.scene.plp_settings
        if not st.subject_collection:
            self.report({"ERROR"}, "Pick a Subject Collection first.")
            return {"CANCELLED"}
        build_lighting(context.scene, st.subject_collection, st.preset, st)
        apply_viewport_shading(context, st)
        return {"FINISHED"}


class PLP_OT_update_camera(bpy.types.Operator):
    bl_idname = "plp.update_camera"
    bl_label = "Create / Update Camera"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        st = context.scene.plp_settings
        if not st.subject_collection:
            self.report({"ERROR"}, "Pick a Subject Collection first.")
            return {"CANCELLED"}

        rig_col = ensure_collection(context.scene, RIG_COLLECTION_NAME)
        center, dims, radius = compute_collection_bbox(st.subject_collection)
        target = create_empty_target(TARGET_NAME, center, rig_col)
        create_or_update_camera(context.scene, rig_col, target, (center, dims, radius), st)
        return {"FINISHED"}


class PLP_OT_create_backdrop(bpy.types.Operator):
    bl_idname = "plp.create_backdrop"
    bl_label = "Create / Update Backdrop"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        st = context.scene.plp_settings
        if not st.subject_collection:
            self.report({"ERROR"}, "Pick a Subject Collection first.")
            return {"CANCELLED"}

        rig_col = ensure_collection(context.scene, RIG_COLLECTION_NAME)
        center, dims, radius = compute_collection_bbox(st.subject_collection)
        create_empty_target(TARGET_NAME, center, rig_col)
        create_or_update_backdrop(context.scene, rig_col, (center, dims, radius), st)
        return {"FINISHED"}


class PLP_OT_remove_rig(bpy.types.Operator):
    bl_idname = "plp.remove_rig"
    bl_label = "Remove Rig"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        remove_rig(context.scene)
        return {"FINISHED"}


class PLP_OT_load_hdri(bpy.types.Operator):
    bl_idname = "plp.load_hdri"
    bl_label = "Load HDRI..."
    bl_options = {"REGISTER", "UNDO"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        st = context.scene.plp_settings
        try:
            img = bpy.data.images.load(self.filepath, check_existing=True)
            st.hdri_image = img
            st.use_hdri = True
            st.vp_use_scene_world = True
            apply_viewport_shading(context, st)
            return {"FINISHED"}
        except Exception as e:
            self.report({"ERROR"}, f"Failed to load HDRI: {e}")
            return {"CANCELLED"}


# ---------------------------
# UI
# ---------------------------

class PLP_PT_panel(bpy.types.Panel):
    bl_label = "Portrait Lighting Presets"
    bl_idname = "PLP_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lighting"

    def draw(self, context):
        layout = self.layout
        st = context.scene.plp_settings

        layout.prop(st, "subject_collection")

        box = layout.box()
        box.label(text="Lighting")
        row = box.row(align=True)
        row.prop(st, "preset")
        row.prop(st, "auto_update_lights")
        col = box.column(align=True)
        col.prop(st, "distance_mult")
        col.prop(st, "height_mult")
        col.prop(st, "softness_mult")
        col.separator()
        col.prop(st, "auto_energy")
        col.prop(st, "all_lights_mult")
        col.label(text="Base Energies (radius=1)")
        r = col.row(align=True)
        r.prop(st, "base_key_energy")
        r.prop(st, "base_fill_energy")
        r = col.row(align=True)
        r.prop(st, "base_rim_energy")
        r.prop(st, "base_bg_energy")
        col.separator()
        col.prop(st, "set_engine")
        if st.set_engine:
            col.prop(st, "render_engine")
            if st.render_engine == "CYCLES":
                col.prop(st, "cycles_denoise")
        col.prop(st, "set_color_management")
        if st.set_color_management:
            col.prop(st, "filmic_look")
            col.prop(st, "exposure")
        box.operator("plp.update_lighting", icon="LIGHT_AREA")

        box = layout.box()
        box.label(text="HDRI (auto-applies)")
        box.prop(st, "use_hdri")
        row = box.row(align=True)
        row.prop(st, "hdri_image")
        row.operator("plp.load_hdri", text="", icon="FILE_FOLDER")
        if st.use_hdri:
            box.prop(st, "hdri_strength")
            box.prop(st, "hdri_rotation_deg")

        box = layout.box()
        box.label(text="Viewport (auto-applies)")
        row = box.row(align=True)
        row.prop(st, "vp_use_scene_world")
        row.prop(st, "vp_use_scene_lights")

        box = layout.box()
        box.label(text="Camera")
        row = box.row(align=True)
        row.prop(st, "camera_set_active")
        row.prop(st, "camera_use_dof")
        box.prop(st, "camera_aspect")
        box.prop(st, "camera_base_res")
        box.prop(st, "camera_lens_mm")
        row = box.row(align=True)
        row.prop(st, "camera_fit_height_mult")
        row.prop(st, "camera_distance_mult")
        box.prop(st, "camera_elevation_mult")
        if st.camera_use_dof:
            box.prop(st, "camera_fstop")
        box.operator("plp.update_camera", icon="CAMERA_DATA")

        box = layout.box()
        box.label(text="Backdrop (Robust Curve)")
        row = box.row(align=True)
        row.prop(st, "backdrop_live_update")
        box.operator("plp.create_backdrop", icon="MESH_PLANE")
        col = box.column(align=True)
        col.label(text="Size")
        col.prop(st, "backdrop_width_mult")
        col.prop(st, "backdrop_floor_forward_mult")
        col.prop(st, "backdrop_floor_back_mult")
        col.prop(st, "backdrop_height_mult")
        col.separator()
        col.label(text="Min size vs camera")
        col.prop(st, "backdrop_cam_width_mult")
        col.prop(st, "backdrop_cam_depth_mult")
        col.separator()
        col.label(text="Curve (formerly bevel)")
        col.prop(st, "backdrop_bevel_mult")
        col.prop(st, "backdrop_bevel_min")
        col.prop(st, "backdrop_bevel_segments")
        col.separator()
        col.label(text="Material / visibility")
        col.prop(st, "backdrop_color")
        col.prop(st, "backdrop_roughness")
        r = col.row(align=True)
        r.prop(st, "backdrop_viewport_visible")
        r.prop(st, "backdrop_render_visible")

        layout.separator()
        layout.operator("plp.remove_rig", icon="TRASH")


# ---------------------------
# Registration
# ---------------------------

classes = (
    PLP_Settings,
    PLP_OT_update_lighting,
    PLP_OT_update_camera,
    PLP_OT_create_backdrop,
    PLP_OT_remove_rig,
    PLP_OT_load_hdri,
    PLP_PT_panel,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.plp_settings = bpy.props.PointerProperty(type=PLP_Settings)

def unregister():
    if hasattr(bpy.types.Scene, "plp_settings"):
        del bpy.types.Scene.plp_settings
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
