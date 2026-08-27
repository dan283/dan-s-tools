bl_info = {
    "name": "Topology Spider Web Generator 0.9.4",
    "author": "OpenAI",
    "version": (0, 9, 4),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Spider Web",
    "description": "Generate topology-aware procedural spider webs inside a selected mesh, with Geometry Nodes rendering and an optional Simulation Nodes settling pass.",
    "category": "Object",
}

import bpy
import bmesh
import math
import random
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
)
from bpy.types import Operator, Panel, PropertyGroup

WEB_TYPES = [
    ('ORB', "Orb", "Radials + capture spiral"),
    ('SHEET', "Sheet", "Planar sheet / mesh web"),
    ('TANGLE', "Tangle", "Irregular 3D network"),
    ('FUNNEL', "Funnel / Tunnel", "Sheet plus supported funnel / tunnel"),
    ('LINE', "Line", "Sparse line web"),
    ('RANDOM', "Random", "Randomize type per generated web"),
]


# ------------------------------------------------------------------------
# Geometry helpers
# ------------------------------------------------------------------------

def _evaluated_bvh(obj, depsgraph):
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    verts = [v.co.copy() for v in mesh.vertices]
    polys = [[i for i in p.vertices] for p in mesh.polygons]
    bvh = BVHTree.FromPolygons(verts, polys, all_triangles=False)
    eval_obj.to_mesh_clear()
    return bvh


def _mesh_center(obj):
    if not obj.data.vertices:
        return Vector((0, 0, 0))
    c = Vector((0, 0, 0))
    for v in obj.data.vertices:
        c += v.co
    return c / len(obj.data.vertices)


def _orthonormal_basis(normal):
    n = normal.normalized()
    helper = Vector((0, 0, 1)) if abs(n.z) < 0.85 else Vector((0, 1, 0))
    u = n.cross(helper).normalized()
    v = n.cross(u).normalized()
    return u, v, n


def _random_basis(rng):
    n = Vector((
        rng.uniform(-1.0, 1.0),
        rng.uniform(-1.0, 1.0),
        rng.uniform(-1.0, 1.0),
    ))
    if n.length < 1e-5:
        n = Vector((0, 0, 1))
    return _orthonormal_basis(n)


def _ray_to_surface(bvh, origin, direction, fallback=1.0):
    d = direction.normalized()
    hit, normal, index, dist = bvh.ray_cast(origin, d, fallback * 1000.0)
    if hit is None:
        return origin + d * fallback
    return hit


def _bbox_radius(obj):
    if not obj.data.vertices:
        return 1.0
    c = _mesh_center(obj)
    return max((v.co - c).length for v in obj.data.vertices) or 1.0


def _jitter_center(center, u, v, n, radius, amount, rng):
    return center + (
        u * rng.uniform(-amount, amount) +
        v * rng.uniform(-amount, amount) +
        n * rng.uniform(-amount * 0.35, amount * 0.35)
    ) * radius


class GraphBuilder:
    def __init__(self):
        self.verts = []
        self.edges = []
        self.pin = []
        self.rest = []

    def add_vert(self, co, pin=0.0):
        idx = len(self.verts)
        self.verts.append(Vector(co))
        self.pin.append(float(max(0.0, min(1.0, pin))))
        self.rest.append(Vector(co))
        return idx

    def add_edge(self, a, b):
        if a != b:
            self.edges.append((a, b))

    def add_polyline(self, coords, pins=None, closed=False):
        if len(coords) < 2:
            return []
        ids = []
        for i, p in enumerate(coords):
            pin = pins[i] if pins and i < len(pins) else 0.0
            ids.append(self.add_vert(p, pin))
        for a, b in zip(ids[:-1], ids[1:]):
            self.add_edge(a, b)
        if closed:
            self.add_edge(ids[-1], ids[0])
        return ids


# ------------------------------------------------------------------------
# Web generators
# ------------------------------------------------------------------------

def build_orb(g, bvh, center, u, v, n, radius, rng, s):
    spokes = max(6, s.spokes)
    rings = max(3, s.rings)

    anchors = []
    hub = g.add_vert(center, 0.85)

    for i in range(spokes):
        a = (i / spokes) * math.tau + rng.uniform(-0.03, 0.03)
        d = (u * math.cos(a) + v * math.sin(a)).normalized()
        hit = _ray_to_surface(bvh, center, d, radius)
        hit = center.lerp(hit, s.web_scale)
        aid = g.add_vert(hit, 1.0)
        anchors.append(hit)
        g.add_edge(hub, aid)

    # Frame perimeter
    frame_ids = [g.add_vert(p, 1.0) for p in anchors]
    for i in range(spokes):
        g.add_edge(frame_ids[i], frame_ids[(i + 1) % spokes])

    # Capture spiral, continuously crossing radial fields.
    spiral_pts = []
    turns = rings
    samples = max(64, spokes * rings * 2)
    for j in range(samples + 1):
        t = j / samples
        ang = t * math.tau * turns
        k = (ang / math.tau) % spokes
        i0 = int(math.floor(k)) % spokes
        i1 = (i0 + 1) % spokes
        frac = k - math.floor(k)
        local_r = anchors[i0].lerp(anchors[i1], frac) - center
        rr = 0.08 + 0.84 * t
        p = center + local_r * rr
        # subtle non-planarity
        p += n * (math.sin(ang * 1.7) * radius * s.irregularity * 0.015)
        spiral_pts.append(p)
    g.add_polyline(spiral_pts, [0.05] * len(spiral_pts), closed=False)


def build_sheet(g, bvh, center, u, v, n, radius, rng, s):
    spokes = max(6, s.spokes)
    rings = max(3, s.rings)
    rim = []
    for i in range(spokes):
        a = i / spokes * math.tau
        d = (u * math.cos(a) + v * math.sin(a)).normalized()
        hit = _ray_to_surface(bvh, center, d, radius)
        rim.append(center.lerp(hit, s.web_scale * 0.85))

    # radial supports
    hub = g.add_vert(center, 0.55)
    for p in rim:
        pi = g.add_vert(p, 1.0)
        g.add_edge(hub, pi)

    # concentric irregular sheet rings
    for r in range(1, rings + 1):
        f = r / rings
        pts = []
        pins = []
        for i, p in enumerate(rim):
            q = center.lerp(p, f)
            q += n * rng.uniform(-1, 1) * radius * s.irregularity * 0.025
            pts.append(q)
            pins.append(0.15 if r < rings else 0.8)
        g.add_polyline(pts, pins, closed=True)

    # extra chords
    for _ in range(max(2, spokes // 2)):
        a = rng.randrange(spokes)
        b = (a + rng.randrange(2, max(3, spokes - 1))) % spokes
        p0 = center.lerp(rim[a], rng.uniform(0.3, 0.95))
        p1 = center.lerp(rim[b], rng.uniform(0.3, 0.95))
        g.add_polyline([p0, p1], [0.25, 0.25])


def build_tangle(g, bvh, center, u, v, n, radius, rng, s):
    count = max(18, s.spokes * 3)
    pts = []
    ids = []
    for _ in range(count):
        d = Vector((rng.uniform(-1,1), rng.uniform(-1,1), rng.uniform(-1,1)))
        if d.length < 1e-4:
            d = u
        d.normalize()
        hit = _ray_to_surface(bvh, center, d, radius)
        f = rng.uniform(0.15, s.web_scale * 0.92)
        p = center.lerp(hit, f)
        pts.append(p)
        ids.append(g.add_vert(p, 0.1))
    # Anchor a handful to the cage
    for _ in range(max(4, count // 8)):
        d = Vector((rng.uniform(-1,1), rng.uniform(-1,1), rng.uniform(-1,1))).normalized()
        hit = _ray_to_surface(bvh, center, d, radius)
        aid = g.add_vert(center.lerp(hit, s.web_scale), 1.0)
        target = min(range(count), key=lambda i: (pts[i] - hit).length)
        g.add_edge(aid, ids[target])

    # K-nearest-like sparse graph
    for i, p in enumerate(pts):
        neighbors = sorted(
            ((pts[j] - p).length, j) for j in range(count) if j != i
        )[:rng.randint(2, 4)]
        for _, j in neighbors:
            if i < j:
                g.add_edge(ids[i], ids[j])


def build_funnel(g, bvh, center, u, v, n, radius, rng, s):
    spokes = max(8, s.spokes)
    rings = max(3, s.rings)
    rim = []
    for i in range(spokes):
        a = i / spokes * math.tau
        d = (u * math.cos(a) + v * math.sin(a)).normalized()
        hit = _ray_to_surface(bvh, center, d, radius)
        rim.append(center.lerp(hit, s.web_scale * 0.78))

    # Outer sheet. Pin outer rim heavily.
    for r in range(1, rings + 1):
        f = r / rings
        pts = []
        pins = []
        for p in rim:
            q = center.lerp(p, f)
            q += n * rng.uniform(-1, 1) * radius * s.irregularity * 0.015
            pts.append(q)
            pins.append(0.45 if r < rings else 1.0)
        g.add_polyline(pts, pins, closed=True)

    # Supported funnel axis extending toward an actual surface hit.
    tunnel_hit = _ray_to_surface(bvh, center, -n, radius)
    tunnel_end = center.lerp(tunnel_hit, min(0.82, s.web_scale))
    axis = tunnel_end - center
    length = axis.length
    if length < radius * 0.1:
        tunnel_end = center - n * radius * 0.5
        axis = tunnel_end - center
        length = axis.length
    axis_n = axis.normalized()

    # Axis/spine is effectively structural cable: fully pinned to preserve tunnel.
    spine_pts = [center.lerp(tunnel_end, i / 5.0) for i in range(6)]
    g.add_polyline(spine_pts, [0.95, 0.95, 1.0, 1.0, 1.0, 1.0])

    # Funnel rings shrink toward the tunnel.
    for r in range(rings + 2):
        t = r / (rings + 1)
        c = center.lerp(tunnel_end, t)
        rad_factor = (1.0 - t) ** 1.45
        pts = []
        pins = []
        for i in range(spokes):
            a = i / spokes * math.tau
            # use initial plane basis, plus slight twist
            twist = t * 0.45
            d = u * math.cos(a + twist) + v * math.sin(a + twist)
            p = c + d * (radius * 0.32 * s.web_scale * rad_factor)
            pts.append(p)
            # tunnel lip and deep tube are strongly supported
            pins.append(0.65 + 0.35 * t)
        g.add_polyline(pts, pins, closed=True)

        # radial/conical supports
        if r > 0:
            prev_t = (r - 1) / (rings + 1)
            pc = center.lerp(tunnel_end, prev_t)
            prev_rad = (1.0 - prev_t) ** 1.45
            for i in range(spokes):
                a = i / spokes * math.tau
                p0 = pc + (u * math.cos(a + prev_t*0.45) + v * math.sin(a + prev_t*0.45)) * (radius * 0.32 * s.web_scale * prev_rad)
                p1 = c  + (u * math.cos(a + t*0.45) + v * math.sin(a + t*0.45)) * (radius * 0.32 * s.web_scale * rad_factor)
                g.add_polyline([p0, p1], [0.7, 0.8])

    # Long guy-lines from sheet perimeter to tunnel entrance resist collapse.
    for i in range(0, spokes, max(1, spokes // 6)):
        g.add_polyline([rim[i], center], [1.0, 0.85])


def build_line(g, bvh, center, u, v, n, radius, rng, s):
    lines = max(1, min(5, s.spokes // 4))
    for _ in range(lines):
        d1 = Vector((rng.uniform(-1,1), rng.uniform(-1,1), rng.uniform(-1,1))).normalized()
        d2 = -d1 + Vector((rng.uniform(-0.25,0.25), rng.uniform(-0.25,0.25), rng.uniform(-0.25,0.25)))
        if d2.length < 1e-4:
            d2 = -d1
        d2.normalize()
        p0 = _ray_to_surface(bvh, center, d1, radius)
        p1 = _ray_to_surface(bvh, center, d2, radius)
        mid = center + Vector((rng.uniform(-1,1), rng.uniform(-1,1), rng.uniform(-1,1))) * radius * 0.08
        g.add_polyline([center.lerp(p0, s.web_scale), mid, center.lerp(p1, s.web_scale)], [1.0, 0.15, 1.0])


# ------------------------------------------------------------------------
# Geometry Nodes
# ------------------------------------------------------------------------

def _new_interface_socket(group, name, in_out, socket_type):
    try:
        return group.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)
    except Exception:
        # Fallback for older APIs
        if in_out == 'INPUT':
            return group.inputs.new(socket_type, name)
        return group.outputs.new(socket_type, name)


def create_geo_group(name="SpiderWeb_GN"):
    ng = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    _new_interface_socket(ng, "Geometry", 'INPUT', 'NodeSocketGeometry')
    _new_interface_socket(ng, "Geometry", 'OUTPUT', 'NodeSocketGeometry')
    _new_interface_socket(ng, "Thickness", 'INPUT', 'NodeSocketFloat')
    _new_interface_socket(ng, "Simulation Strength", 'INPUT', 'NodeSocketFloat')
    _new_interface_socket(ng, "Gravity", 'INPUT', 'NodeSocketFloat')
    _new_interface_socket(ng, "Profile Sides", 'INPUT', 'NodeSocketInt')

    nodes = ng.nodes
    links = ng.links
    nodes.clear()

    inp = nodes.new("NodeGroupInput")
    inp.location = (-900, 0)
    out = nodes.new("NodeGroupOutput")
    out.location = (760, 0)

    # Simulation zone. If unsupported, the group gracefully falls back.
    sim_geom_out = inp.outputs.get("Geometry")
    sim_geom_final = sim_geom_out

    try:
        sim_in = nodes.new("GeometryNodeSimulationInput")
        sim_out = nodes.new("GeometryNodeSimulationOutput")
        sim_in.location = (-680, 120)
        sim_out.location = (-190, 120)
        sim_in.pair_with_output(sim_out)

        links.new(inp.outputs["Geometry"], sim_in.inputs["Geometry"])

        pos = nodes.new("GeometryNodeInputPosition")
        pos.location = (-650, -160)

        rest = nodes.new("GeometryNodeInputNamedAttribute")
        rest.data_type = 'FLOAT_VECTOR'
        rest.inputs["Name"].default_value = "rest_pos"
        rest.location = (-650, -270)

        pin = nodes.new("GeometryNodeInputNamedAttribute")
        pin.data_type = 'FLOAT'
        pin.inputs["Name"].default_value = "web_pin"
        pin.location = (-650, -390)

        spring = nodes.new("ShaderNodeVectorMath")
        spring.operation = 'SUBTRACT'
        spring.location = (-430, -230)
        links.new(rest.outputs["Attribute"], spring.inputs[0])
        links.new(pos.outputs["Position"], spring.inputs[1])

        spring_scale = nodes.new("ShaderNodeVectorMath")
        spring_scale.operation = 'SCALE'
        spring_scale.location = (-230, -230)
        links.new(spring.outputs["Vector"], spring_scale.inputs[0])
        links.new(inp.outputs["Simulation Strength"], spring_scale.inputs["Scale"])

        one_minus_pin = nodes.new("ShaderNodeMath")
        one_minus_pin.operation = 'SUBTRACT'
        one_minus_pin.inputs[0].default_value = 1.0
        one_minus_pin.location = (-430, -410)
        links.new(pin.outputs["Attribute"], one_minus_pin.inputs[1])

        grav_mult = nodes.new("ShaderNodeMath")
        grav_mult.operation = 'MULTIPLY'
        grav_mult.location = (-230, -410)
        links.new(one_minus_pin.outputs[0], grav_mult.inputs[0])
        links.new(inp.outputs["Gravity"], grav_mult.inputs[1])

        combine = nodes.new("ShaderNodeCombineXYZ")
        combine.location = (-40, -410)
        links.new(grav_mult.outputs[0], combine.inputs["Z"])

        add_force = nodes.new("ShaderNodeVectorMath")
        add_force.operation = 'ADD'
        add_force.location = (-20, -230)
        links.new(spring_scale.outputs["Vector"], add_force.inputs[0])
        links.new(combine.outputs["Vector"], add_force.inputs[1])

        unpin = nodes.new("ShaderNodeVectorMath")
        unpin.operation = 'SCALE'
        unpin.location = (140, -230)
        links.new(add_force.outputs["Vector"], unpin.inputs[0])
        links.new(one_minus_pin.outputs[0], unpin.inputs["Scale"])

        setpos = nodes.new("GeometryNodeSetPosition")
        setpos.location = (10, 100)
        links.new(sim_in.outputs["Geometry"], setpos.inputs["Geometry"])
        links.new(unpin.outputs["Vector"], setpos.inputs["Offset"])
        links.new(setpos.outputs["Geometry"], sim_out.inputs["Geometry"])

        sim_geom_final = sim_out.outputs["Geometry"]
    except Exception:
        sim_geom_final = inp.outputs["Geometry"]

    mesh_to_curve = nodes.new("GeometryNodeMeshToCurve")
    mesh_to_curve.location = (250, 80)
    links.new(sim_geom_final, mesh_to_curve.inputs["Mesh"])

    circle = nodes.new("GeometryNodeCurvePrimitiveCircle")
    circle.location = (250, -140)
    circle.mode = 'RADIUS'
    if circle.inputs.get("Radius"):
        links.new(inp.outputs["Thickness"], circle.inputs["Radius"])
    if circle.inputs.get("Resolution"):
        links.new(inp.outputs["Profile Sides"], circle.inputs["Resolution"])

    curve_to_mesh = nodes.new("GeometryNodeCurveToMesh")
    curve_to_mesh.location = (510, 70)
    links.new(mesh_to_curve.outputs["Curve"], curve_to_mesh.inputs["Curve"])
    links.new(circle.outputs["Curve"], curve_to_mesh.inputs["Profile Curve"])

    links.new(curve_to_mesh.outputs["Mesh"], out.inputs["Geometry"])

    return ng


def set_modifier_input(mod, group, socket_name, value):
    """
    Blender 5.2-safe Geometry Nodes modifier input assignment.

    Blender 5.2 no longer supports treating NodesModifier as a generic
    IDProperty mapping, so legacy checks such as `if key in mod` fail.
    We resolve the interface socket identifier and assign it directly.
    """
    identifier = None

    try:
        for item in group.interface.items_tree:
            if (
                getattr(item, "item_type", None) == 'SOCKET'
                and getattr(item, "name", None) == socket_name
                and getattr(item, "in_out", None) == 'INPUT'
            ):
                identifier = getattr(item, "identifier", None)
                if identifier:
                    break
    except Exception:
        identifier = None

    if not identifier:
        return False

    try:
        mod[identifier] = value
        return True
    except Exception:
        # Some Blender 5.2 builds expose GN modifier values through
        # the modifier's RNA property collection rather than dict-like access.
        try:
            setattr(mod, identifier, value)
            return True
        except Exception:
            return False


def create_web_object(context, cage, graph, settings, web_index):
    mesh = bpy.data.meshes.new(f"SpiderWebGraph_{web_index:02d}")
    mesh.from_pydata([tuple(v) for v in graph.verts], graph.edges, [])
    mesh.update()

    # Persistent rest shape and pin attributes used by the Simulation Nodes pass.
    pin_attr = mesh.attributes.new("web_pin", 'FLOAT', 'POINT')
    rest_attr = mesh.attributes.new("rest_pos", 'FLOAT_VECTOR', 'POINT')

    for i, val in enumerate(graph.pin):
        pin_attr.data[i].value = val
    for i, co in enumerate(graph.rest):
        rest_attr.data[i].vector = co

    web = bpy.data.objects.new(f"SpiderWeb_{web_index:02d}", mesh)
    context.collection.objects.link(web)

    # Keep graph in cage local space and inherit cage transform.
    web.matrix_world = cage.matrix_world.copy()

    ng = create_geo_group(f"SpiderWeb_GN_{web_index:02d}")
    mod = web.modifiers.new("Spider Web Geometry + Simulation", 'NODES')
    mod.node_group = ng

    set_modifier_input(mod, ng, "Thickness", settings.thickness)
    set_modifier_input(mod, ng, "Simulation Strength", settings.sim_strength if settings.use_simulation else 0.0)
    # Negative Z offset; tiny values are sufficient because applied each sim step.
    set_modifier_input(mod, ng, "Gravity", -abs(settings.gravity) if settings.use_simulation else 0.0)
    set_modifier_input(mod, ng, "Profile Sides", settings.profile_sides)

    web["spiderweb_generated"] = True
    web["source_cage"] = cage.name
    web["simulation_note"] = (
        "Funnel/tunnel structural strands use high web_pin values and rest-position springs, "
        "so the tunnel remains supported while softer capture strands can settle."
    )
    return web


# ------------------------------------------------------------------------
# UI / Operators
# ------------------------------------------------------------------------

class SpiderWebSettings(PropertyGroup):
    container_object: PointerProperty(
        name="Container Object",
        description="Mesh object that contains the generated spider web",
        type=bpy.types.Object,
        poll=lambda self, obj: obj is not None and obj.type == 'MESH',
    )
    guide_object: PointerProperty(
        name="Guide Object",
        description="Optional object/Empty used as web center and orientation guide",
        type=bpy.types.Object,
    )

    web_type: EnumProperty(
        name="Web Type",
        items=WEB_TYPES,
        default='ORB',
    )
    count: IntProperty(
        name="Web Count",
        default=1,
        min=1,
        max=20,
    )
    seed: IntProperty(
        name="Seed",
        default=1,
        min=0,
        max=999999,
    )
    spokes: IntProperty(
        name="Radials / Density",
        default=14,
        min=4,
        max=64,
    )
    rings: IntProperty(
        name="Rings / Layers",
        default=8,
        min=2,
        max=32,
    )
    web_scale: FloatProperty(
        name="Cage Fill",
        description="Fraction of ray-cast distance to the cage surface",
        default=0.92,
        min=0.1,
        max=1.0,
    )
    center_jitter: FloatProperty(
        name="Center Jitter",
        default=0.12,
        min=0.0,
        max=0.8,
    )
    irregularity: FloatProperty(
        name="Irregularity",
        default=0.35,
        min=0.0,
        max=1.0,
    )
    thickness: FloatProperty(
        name="Silk Thickness",
        default=0.003,
        min=0.0001,
        max=0.1,
        precision=4,
    )
    profile_sides: IntProperty(
        name="Profile Sides",
        default=4,
        min=3,
        max=16,
    )
    use_simulation: BoolProperty(
        name="Use Simulation Nodes",
        default=True,
    )
    sim_strength: FloatProperty(
        name="Rest-Shape Spring",
        description="Higher values pull strands back toward their generated rest topology",
        default=0.08,
        min=0.0,
        max=1.0,
    )
    gravity: FloatProperty(
        name="Sag / Gravity",
        description="Per-step downward settling force on unpinned strands",
        default=0.003,
        min=0.0,
        max=0.05,
        precision=4,
    )


class SPIDERWEB_OT_generate(Operator):
    bl_idname = "spiderweb.generate"
    bl_label = "Generate Spider Web"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.spiderweb_settings
        cage = s.container_object

        if not cage or cage.type != 'MESH':
            self.report({'ERROR'}, "Choose a mesh in Container Object first.")
            return {'CANCELLED'}

        depsgraph = context.evaluated_depsgraph_get()

        try:
            bvh = _evaluated_bvh(cage, depsgraph)
        except Exception as exc:
            self.report({'ERROR'}, f"Could not build cage BVH: {exc}")
            return {'CANCELLED'}

        base_center = _mesh_center(cage)
        radius = _bbox_radius(cage)

        guide_center = None
        guide_basis = None
        guide = s.guide_object

        if guide is not None:
            cage_inv = cage.matrix_world.inverted()
            guide_center = cage_inv @ guide.matrix_world.translation

            cage_rot_inv = cage.matrix_world.to_3x3().inverted()
            gx = (cage_rot_inv @ (guide.matrix_world.to_3x3() @ Vector((1, 0, 0)))).normalized()
            gy = (cage_rot_inv @ (guide.matrix_world.to_3x3() @ Vector((0, 1, 0)))).normalized()
            gz = (cage_rot_inv @ (guide.matrix_world.to_3x3() @ Vector((0, 0, 1)))).normalized()
            guide_basis = (gx, gy, gz)

        rng = random.Random(s.seed)
        created = []

        for wi in range(s.count):
            local_rng = random.Random(rng.randint(0, 2**31 - 1))

            if guide_basis is not None:
                u, v, n = guide_basis
            else:
                u, v, n = _random_basis(local_rng)

            start_center = guide_center if guide_center is not None else base_center
            center = _jitter_center(
                start_center, u, v, n, radius, s.center_jitter, local_rng
            )

            web_type = s.web_type
            if web_type == 'RANDOM':
                web_type = local_rng.choice(['ORB', 'SHEET', 'TANGLE', 'FUNNEL', 'LINE'])

            g = GraphBuilder()

            if web_type == 'ORB':
                build_orb(g, bvh, center, u, v, n, radius, local_rng, s)
            elif web_type == 'SHEET':
                build_sheet(g, bvh, center, u, v, n, radius, local_rng, s)
            elif web_type == 'TANGLE':
                build_tangle(g, bvh, center, u, v, n, radius, local_rng, s)
            elif web_type == 'FUNNEL':
                build_funnel(g, bvh, center, u, v, n, radius, local_rng, s)
            elif web_type == 'LINE':
                build_line(g, bvh, center, u, v, n, radius, local_rng, s)

            if not g.verts or not g.edges:
                continue

            web = create_web_object(context, cage, g, s, wi + 1)
            web["web_type"] = web_type
            created.append(web)

        if not created:
            self.report({'ERROR'}, "No web geometry could be created.")
            return {'CANCELLED'}

        bpy.ops.object.select_all(action='DESELECT')
        for obj in created:
            obj.select_set(True)
        context.view_layer.objects.active = created[-1]

        self.report({'INFO'}, f"Created {len(created)} topology-aware spider web(s).")
        return {'FINISHED'}


class SPIDERWEB_OT_delete_generated(Operator):
    bl_idname = "spiderweb.delete_generated"
    bl_label = "Delete Generated Webs"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        doomed = [o for o in bpy.data.objects if o.get("spiderweb_generated")]
        for o in doomed:
            bpy.data.objects.remove(o, do_unlink=True)
        self.report({'INFO'}, f"Deleted {len(doomed)} generated web object(s).")
        return {'FINISHED'}


class VIEW3D_PT_spiderweb(Panel):
    bl_label = "Spider Web"
    bl_idname = "VIEW3D_PT_spiderweb"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Spider Web"

    def draw(self, context):
        layout = self.layout
        s = context.scene.spiderweb_settings

        placement = layout.box()
        placement.label(text="Placement", icon='OBJECT_DATA')
        placement.prop(s, "container_object", text="Container Mesh")
        placement.prop(s, "guide_object", text="Guide (Optional)")

        layout.separator()

        topology = layout.box()
        topology.label(text="Web Structure")
        topology.prop(s, "web_type")
        topology.prop(s, "count")
        topology.prop(s, "seed")
        topology.prop(s, "spokes")
        topology.prop(s, "rings")
        topology.prop(s, "web_scale")
        topology.prop(s, "center_jitter")
        topology.prop(s, "irregularity")

        silk = layout.box()
        silk.label(text="Silk")
        silk.prop(s, "thickness")
        silk.prop(s, "profile_sides")

        sim = layout.box()
        sim.label(text="Simulation")
        sim.prop(s, "use_simulation")
        sub = sim.column(align=True)
        sub.enabled = s.use_simulation
        sub.prop(s, "sim_strength")
        sub.prop(s, "gravity")

        layout.separator()

        row = layout.row()
        row.scale_y = 1.8
        row.operator("spiderweb.generate", text="CREATE WEB", icon='GEOMETRY_NODES')

        layout.operator(
            "spiderweb.delete_generated",
            text="Delete Generated Webs",
            icon='TRASH'
        )


classes = (
    SpiderWebSettings,
    SPIDERWEB_OT_generate,
    SPIDERWEB_OT_delete_generated,
    VIEW3D_PT_spiderweb,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.spiderweb_settings = PointerProperty(type=SpiderWebSettings)


def unregister():
    if hasattr(bpy.types.Scene, "spiderweb_settings"):
        del bpy.types.Scene.spiderweb_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
