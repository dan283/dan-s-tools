bl_info = {
    'name': 'Jewelry Photo Studio',
    'author': 'OpenAI',
    'version': (1, 0, 0),
    'blender': (4, 3, 0),
    'location': 'View3D > Sidebar > Jewelry Photo',
    'description': 'Live five-preset product photography rigs around a selected jewelry object',
    'category': 'Lighting',
}

import bpy
import math
from mathutils import Vector
from bpy.props import PointerProperty, EnumProperty, FloatProperty, BoolProperty

PREFIX = 'JPS | '
COLLECTION_NAME = 'JPS | Photo Rig'

PRESETS = [
    ('WHITE', 'White Studio', 'Two broad softboxes, seamless sweep', 'LIGHT_SUN', 0),
    ('TENT', 'Diffusion Tent', 'Soft all-around catalog light tent', 'SHADING_RENDERED', 1),
    ('BLACK', 'Black Reflection', 'Glossy black acrylic, sculpted highlights', 'MATERIAL', 2),
    ('GEM', 'Gemstone Glow', 'Backlight and rim lighting for transparent stones', 'LIGHT_POINT', 3),
    ('TEXTURE', 'Texture / Engraving', 'Grazing light for surface details', 'LIGHT_AREA', 4),
]


def get_collection(scene):
    coll = bpy.data.collections.get(COLLECTION_NAME)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION_NAME)
    if scene.collection.children.get(coll.name) is None:
        try:
            scene.collection.children.link(coll)
        except RuntimeError:
            pass
    return coll


def cleanup(scene):
    coll = bpy.data.collections.get(COLLECTION_NAME)
    if not coll:
        return
    for obj in list(coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def link_to_rig(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def matte_material(name, color, rough=0.75, metallic=0, transmission=0):
    mat = bpy.data.materials.get(PREFIX + name)
    if mat is None:
        mat = bpy.data.materials.new(PREFIX + name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (*color, 1)
        bsdf.inputs['Roughness'].default_value = rough
        bsdf.inputs['Metallic'].default_value = metallic
        if 'Transmission Weight' in bsdf.inputs:
            bsdf.inputs['Transmission Weight'].default_value = transmission
    return mat


def plane(coll, name, center, dims, material, hide_camera=False):
    mesh = bpy.data.meshes.new(PREFIX + name + ' Mesh')
    dx, dy = dims[0] * 0.5, dims[1] * 0.5
    mesh.from_pydata([(-dx, -dy, 0), (dx, -dy, 0), (dx, dy, 0), (-dx, dy, 0)], [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    coll.objects.link(obj)
    obj.location = center
    obj.data.materials.append(material)
    if hide_camera:
        obj.hide_render = True
    return obj


def aim(obj, at):
    direction = Vector(at) - obj.location
    if direction.length > 1e-9:
        obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def light(coll, name, loc, target, power, size, color=(1, 1, 1), shape='DISK', size_y=None):
    data = bpy.data.lights.new(PREFIX + name, 'AREA')
    data.energy = max(0.0, power)
    data.shape = shape
    data.size = max(0.0001, size)
    if shape == 'RECTANGLE':
        data.size_y = max(0.0001, size_y if size_y else size)
    data.color = color
    obj = bpy.data.objects.new(PREFIX + name, data)
    coll.objects.link(obj)
    obj.location = loc
    aim(obj, target)
    return obj


def bounds_world(obj):
    # Evaluated dimensions are used, preserving the original object and its modifiers.
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    corners = [ev.matrix_world @ Vector(p) for p in ev.bound_box]
    mn = Vector([min(v[i] for v in corners) for i in range(3)])
    mx = Vector([max(v[i] for v in corners) for i in range(3)])
    return mn, mx


def render_world(scene, brightness):
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new(PREFIX + 'World')
        scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get('Background')
    if bg:
        bg.inputs['Color'].default_value = (0.6, 0.63, 0.67, 1)
        bg.inputs['Strength'].default_value = brightness


def update_rig(self, context):
    if not context or not context.scene:
        return
    p = context.scene.jps_props
    if p.live and p.target and not p.updating:
        try:
            p.updating = True
            build_rig(context.scene, p)
        finally:
            p.updating = False


class JPS_Properties(bpy.types.PropertyGroup):
    target: PointerProperty(name='Jewelry', type=bpy.types.Object, description='Original jewelry object; never modified', update=update_rig)
    preset: EnumProperty(name='Setup', items=PRESETS, default='WHITE', update=update_rig)
    orientation: EnumProperty(name='Presentation', items=[
        ('UPRIGHT', 'Standing', 'Jewelry viewed upright with a near-horizontal camera'),
        ('FLAT', 'Lying Flat', 'Camera elevated over jewelry'),
        ('TOP', 'Top Down', 'Direct overhead product image'),
        ('CUSTOM', 'Custom Camera', 'Use independent elevation and azimuth settings'),
    ], default='UPRIGHT', update=update_rig)
    azimuth: FloatProperty(name='Camera Rotation', default=math.radians(35), min=-math.pi, max=math.pi, subtype='ANGLE', update=update_rig,
        description='Orbit camera around jewelry. Blender stores this internally in radians')
    elevation: FloatProperty(name='Camera Elevation', default=math.radians(30), min=math.radians(3), max=math.radians(89), subtype='ANGLE', update=update_rig)
    camera_distance: FloatProperty(name='Framing', default=1.0, min=0.4, max=3.0, update=update_rig)
    light_power: FloatProperty(name='Light Strength', default=1.0, min=0, max=10, update=update_rig)
    light_size: FloatProperty(name='Softness', default=1.0, min=0.1, max=4.0, update=update_rig)
    light_rotation: FloatProperty(name='Light Rotation', default=0.0, min=-math.pi, max=math.pi, subtype='ANGLE', update=update_rig)
    fill_ratio: FloatProperty(name='Fill / Contrast', default=0.55, min=0, max=2, update=update_rig)
    background: EnumProperty(name='Backdrop', items=[('AUTO','Preset Default',''), ('WHITE','White',''), ('GRAY','Gray',''), ('BLACK','Black','')], default='AUTO', update=update_rig)
    world_strength: FloatProperty(name='Ambient Strength', default=0.3, min=0, max=2, update=update_rig)
    surface_gap: FloatProperty(name='Surface Gap', default=0, min=-0.02, max=0.1, precision=4, subtype='DISTANCE', update=update_rig)
    show_helpers: BoolProperty(name='Show Softboxes', default=True, update=update_rig)
    live: BoolProperty(name='Live Update', default=True)
    updating: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'}, default=False)


def camera_angles(p):
    # Angles stored as radians by subtype ANGLE.
    if p.orientation == 'UPRIGHT':
        return math.radians(15), p.azimuth
    if p.orientation == 'FLAT':
        return math.radians(62), p.azimuth
    if p.orientation == 'TOP':
        return math.radians(89), p.azimuth
    return p.elevation, p.azimuth


def build_rig(scene, p):
    target = p.target
    if target is None or target.type not in {'MESH', 'CURVE', 'FONT', 'SURFACE'}:
        return
    if not target.name in bpy.data.objects:
        return
    coll = get_collection(scene)
    cleanup(scene)
    mn, mx = bounds_world(target)
    mid = (mn + mx) * 0.5
    extent = max((mx - mn).length, 0.004)
    r = max(extent * 0.7, 0.01)
    floor_z = mn.z - p.surface_gap
    look = mid.copy()
    rot = p.light_rotation
    def around(x,y,z):
        return Vector((mid.x + math.cos(rot)*x-math.sin(rot)*y,
                       mid.y + math.sin(rot)*x+math.cos(rot)*y, floor_z+z))
    def L(name, xyz, powr, size, color=(1,1,1), fill=1, shape='DISK', sy=None):
        return light(coll, name, around(*xyz), look, powr*p.light_power*fill,
                     size*p.light_size, color, shape, (sy*p.light_size if sy else None))

    bg_name = p.background
    if bg_name == 'AUTO':
        bg_name = 'BLACK' if p.preset in {'BLACK', 'GEM', 'TEXTURE'} else 'WHITE'
    mats = {
        'WHITE': matte_material('Paper White', (0.87, 0.87, 0.87), 0.88),
        'GRAY': matte_material('Neutral Gray', (0.18, 0.18, 0.18), 0.8),
        'BLACK': matte_material('Black Acrylic', (0.006, 0.006, 0.008), 0.09),
    }
    base = plane(coll, 'Surface', (mid.x, mid.y, floor_z), (r*12,r*12), mats[bg_name])
    if bg_name == 'BLACK' and p.preset != 'BLACK':
        base.data.materials.clear()
        base.data.materials.append(matte_material('Black Matte', (0.009, 0.009, 0.012), 0.82))

    # A curved-looking infinite background made from a floor and rear wall,
    # placed well behind the subject; the seam is never in the camera frame.
    rear = plane(coll, 'Backdrop', (mid.x, mid.y+r*5, floor_z+r*3), (r*12, r*7), mats[bg_name])
    rear.rotation_euler.x = math.pi/2
    rear.hide_set(True)  # hidden in solid viewport; still visible in renders
    rear.hide_render = False

    strength = 1400 * (r / 0.10) ** 2  # studio power scales with jewelry size
    if p.preset == 'WHITE':
        L('Key Softbox', (-2.6*r, -2.2*r, 3.5*r), strength, 3*r, shape='RECTANGLE', sy=4*r)
        L('Fill Softbox', (2.5*r, -1.1*r, 2.6*r), strength*0.82, 2.5*r, fill=p.fill_ratio, shape='RECTANGLE', sy=3.2*r)
        L('Top Strip', (0, 1.8*r, 4.1*r), strength*0.55, 3*r)
    elif p.preset == 'TENT':
        L('Tent Left', (-2*r, 0, 2.2*r), strength*0.75, 3.5*r)
        L('Tent Right', (2*r, 0, 2.2*r), strength*0.75, 3.5*r, fill=p.fill_ratio)
        L('Tent Roof', (0, 0.4*r, 3.3*r), strength*0.55, 4*r)
        L('Front Fill', (0, -3*r, 1.7*r), strength*0.26, 2.5*r)
        # Lightweight shell for composition reference, invisible to rays/renders.
        white = matte_material('Tent White', (0.95,0.95,0.95), 0.96)
        for name, pos, dims, xrot in [
            ('Tent Left Guide',(-2.5*r,0,2*r),(4.5*r,4*r),math.pi/2),
            ('Tent Right Guide',(2.5*r,0,2*r),(4.5*r,4*r),math.pi/2),
            ('Tent Roof Guide',(0,0,4*r),(5*r,5*r),0),
        ]:
            # The guide does not block the studio illumination.
            helper = plane(coll, name, around(*pos), dims, white, hide_camera=True)
            helper.hide_render = True
            helper.hide_set(not p.show_helpers)
            if 'Left' in name or 'Right' in name:
                helper.rotation_euler.y = math.pi/2
    elif p.preset == 'BLACK':
        L('White Edge Strip', (-2.0*r, -0.3*r, 3.8*r), strength*0.95, 1.1*r, shape='RECTANGLE', sy=4*r)
        L('Top Reflection', (0, 0.7*r, 4*r), strength*0.85, 3*r, fill=p.fill_ratio, shape='RECTANGLE', sy=1.5*r)
        L('Gold Rim', (2.5*r, 1.8*r, 2*r), strength*0.33, 1.4*r, (1,0.91,0.78))
    elif p.preset == 'GEM':
        L('Rear Transmitted', (0, 2.8*r, 2*r), strength*1.25, 1.2*r)
        L('Side Rim', (2.2*r, 0.8*r, 2.5*r), strength*0.7, 1.5*r)
        L('Front Fill', (-1.6*r,-2.4*r,2.0*r), strength*0.45, 2.2*r, fill=p.fill_ratio)
        L('Upper Sparkle', (0,-0.8*r,4.2*r), strength*0.42, 0.6*r)
    else:  # TEXTURE
        L('Low Grazing Strip', (-3.2*r,0,0.95*r), strength*1.3, 2*r, shape='RECTANGLE', sy=1.0*r)
        L('Soft Controlled Fill', (2.4*r,-1.8*r,2.7*r), strength*0.55, 2*r, fill=p.fill_ratio)
        L('Thin Rim', (0,2.5*r,2*r), strength*0.35, 0.8*r, shape='RECTANGLE', sy=2*r)

    elev, azi = camera_angles(p)
    distance = r * 5.8 * p.camera_distance
    forward = Vector((math.cos(elev)*math.sin(azi), -math.cos(elev)*math.cos(azi), math.sin(elev)))
    cam_data = bpy.data.cameras.new(PREFIX + 'Macro Camera')
    cam = bpy.data.objects.new(PREFIX + 'Macro Camera', cam_data)
    coll.objects.link(cam)
    cam.location = look + forward * distance
    aim(cam, look)
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = r * 2.85 * p.camera_distance
    cam_data.lens = 85
    scene.camera = cam
    render_world(scene, p.world_strength)
    if not scene.render.resolution_x or not scene.render.resolution_y:
        scene.render.resolution_x, scene.render.resolution_y = 1200, 1200
    scene.render.resolution_percentage = 100
    # Camera and rig are recreated, but original object selection is preserved.
    for o in list(bpy.context.selected_objects):
        o.select_set(False)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target


class JPS_OT_create(bpy.types.Operator):
    bl_idname = 'jps.create'
    bl_label = 'Create / Refresh Studio'
    bl_description = 'Generate studio around the chosen jewelry object'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        p = context.scene.jps_props
        if not p.target:
            if context.active_object and not context.active_object.name.startswith(PREFIX):
                p.target = context.active_object
            else:
                self.report({'ERROR'}, 'Select jewelry or choose it in the Object field')
                return {'CANCELLED'}
        if p.target.type not in {'MESH','CURVE','FONT','SURFACE'}:
            self.report({'ERROR'}, 'Jewelry must be a mesh, curve, font, or surface')
            return {'CANCELLED'}
        old = p.updating
        p.updating = True
        try:
            build_rig(context.scene, p)
        finally:
            p.updating = old
        self.report({'INFO'}, 'Jewelry photo rig created; adjust sliders live')
        return {'FINISHED'}


class JPS_OT_use_selected(bpy.types.Operator):
    bl_idname = 'jps.use_selected'
    bl_label = 'Use Selected Jewelry'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.active_object or context.active_object.name.startswith(PREFIX):
            self.report({'WARNING'}, 'Select a jewelry object first')
            return {'CANCELLED'}
        context.scene.jps_props.target = context.active_object
        return {'FINISHED'}


class JPS_OT_view(bpy.types.Operator):
    bl_idname = 'jps.view_camera'
    bl_label = 'View Through Studio Camera'
    def execute(self, context):
        if not context.scene.camera:
            self.report({'WARNING'}, 'Create a studio first')
            return {'CANCELLED'}
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_perspective = 'CAMERA'
                break
        return {'FINISHED'}


class JPS_OT_delete(bpy.types.Operator):
    bl_idname = 'jps.delete'
    bl_label = 'Remove Studio'
    bl_options = {'REGISTER','UNDO'}
    def execute(self, context):
        coll = bpy.data.collections.get(COLLECTION_NAME)
        if coll:
            camera_in_rig = context.scene.camera and context.scene.camera.name in coll.objects
            cleanup(context.scene)
            if camera_in_rig:
                context.scene.camera = None
        return {'FINISHED'}


class JPS_PT_panel(bpy.types.Panel):
    bl_label = 'Jewelry Photo Studio'
    bl_idname = 'JPS_PT_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Jewelry Photo'

    def draw(self, context):
        layout = self.layout
        p = context.scene.jps_props
        box = layout.box()
        box.label(text='01  Jewelry', icon='OBJECT_DATA')
        row = box.row(align=True)
        row.prop(p, 'target', text='')
        row.operator('jps.use_selected', text='', icon='EYEDROPPER')
        box.prop(p,'orientation', text='Placement')
        box = layout.box()
        box.label(text='02  Photography Setup', icon='LIGHT_AREA')
        box.prop(p,'preset', text='')
        box = layout.box()
        box.label(text='03  Camera', icon='CAMERA_DATA')
        box.prop(p,'camera_distance')
        box.prop(p,'azimuth')
        if p.orientation == 'CUSTOM':
            box.prop(p,'elevation')
        box = layout.box()
        box.label(text='04  Lighting', icon='LIGHT')
        box.prop(p,'light_power')
        box.prop(p,'light_size')
        box.prop(p,'light_rotation')
        box.prop(p,'fill_ratio')
        box.prop(p,'world_strength')
        box = layout.box()
        box.label(text='05  Stage', icon='MESH_PLANE')
        box.prop(p,'background')
        box.prop(p,'surface_gap')
        if p.preset == 'TENT':
            box.prop(p,'show_helpers')
        layout.prop(p,'live', toggle=True)
        row = layout.row(align=True)
        row.scale_y = 1.5
        row.operator('jps.create', text='Create / Refresh', icon='OUTLINER_OB_LIGHT')
        row = layout.row(align=True)
        row.operator('jps.view_camera', text='Camera View', icon='CAMERA_DATA')
        row.operator('jps.delete', text='Remove', icon='TRASH')
        layout.label(text='Tip: Z > Rendered for live lighting preview', icon='INFO')
        layout.label(text='The jewelry object is never moved.')


CLASSES = [JPS_Properties, JPS_OT_create, JPS_OT_use_selected, JPS_OT_view, JPS_OT_delete, JPS_PT_panel]

def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.jps_props = PointerProperty(type=JPS_Properties)

def unregister():
    del bpy.types.Scene.jps_props
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

if __name__ == '__main__':
    register()
