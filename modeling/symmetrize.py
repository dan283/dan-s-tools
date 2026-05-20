bl_info = {
    "name": "Symmetrize From Stored Seam",
    "author": "ChatGPT",
    "version": (0, 3, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Symmetrize",
    "description": "Safer topology/spatial symmetrizer using one stored center seam edge and selected affected vertices.",
    "category": "Mesh",
}

import bpy
import bmesh
from mathutils import Vector
from bpy.props import EnumProperty, FloatProperty, BoolProperty, IntProperty
from collections import deque, defaultdict


# ------------------------------------------------------------
# Storage keys
# ------------------------------------------------------------

SEAM_EDGE_KEY = "symmetrize_stored_single_seam_edge_index"
SEAM_AXIS_KEY = "symmetrize_stored_axis"
SEAM_OFFSET_KEY = "symmetrize_stored_plane_offset"
SEAM_DIR_KEY = "symmetrize_stored_seam_direction"


# ------------------------------------------------------------
# Math helpers
# ------------------------------------------------------------


def axis_value(co: Vector, axis: str) -> float:
    if axis == "X":
        return co.x
    if axis == "Y":
        return co.y
    return co.z


def set_axis_value(co: Vector, axis: str, value: float) -> Vector:
    out = co.copy()
    if axis == "X":
        out.x = value
    elif axis == "Y":
        out.y = value
    else:
        out.z = value
    return out


def axis_vector(axis: str) -> Vector:
    if axis == "X":
        return Vector((1.0, 0.0, 0.0))
    if axis == "Y":
        return Vector((0.0, 1.0, 0.0))
    return Vector((0.0, 0.0, 1.0))


def signed_distance_to_plane(co: Vector, axis: str, offset: float) -> float:
    return axis_value(co, axis) - offset


def reflect_across_axis_plane(co: Vector, axis: str, offset: float) -> Vector:
    out = co.copy()
    if axis == "X":
        out.x = 2.0 * offset - out.x
    elif axis == "Y":
        out.y = 2.0 * offset - out.y
    else:
        out.z = 2.0 * offset - out.z
    return out


def project_to_plane(co: Vector, axis: str, offset: float) -> Vector:
    return set_axis_value(co, axis, offset)


def perpendicular_projection(co: Vector, axis: str) -> Vector:
    """Return the coordinate components parallel to the symmetry plane."""
    out = co.copy()
    if axis == "X":
        out.x = 0.0
    elif axis == "Y":
        out.y = 0.0
    else:
        out.z = 0.0
    return out


def classify_vertex(v, axis: str, offset: float, eps: float):
    d = signed_distance_to_plane(v.co, axis, offset)
    if abs(d) <= eps:
        return "CENTER"
    return "POS" if d > 0.0 else "NEG"


def guess_axis_from_edge(edge):
    """
    Guess mirror axis from a selected center edge.
    The mirror axis is the object-space axis most perpendicular to the seam edge.
    For a vertical body seam, the edge points mostly Z, so X/Y are candidates.
    We choose the axis with the smallest edge-direction component.
    """
    v0, v1 = edge.verts
    d = (v1.co - v0.co)
    if d.length == 0.0:
        return "X"
    d.normalize()
    comps = {"X": abs(d.x), "Y": abs(d.y), "Z": abs(d.z)}
    return min(comps, key=comps.get)


# ------------------------------------------------------------
# Stored seam helpers
# ------------------------------------------------------------


def store_seam(obj, edge_index, axis, offset, seam_dir):
    obj[SEAM_EDGE_KEY] = int(edge_index)
    obj[SEAM_AXIS_KEY] = axis
    obj[SEAM_OFFSET_KEY] = float(offset)
    obj[SEAM_DIR_KEY] = [float(seam_dir.x), float(seam_dir.y), float(seam_dir.z)]


def has_stored_seam(obj):
    return SEAM_EDGE_KEY in obj and SEAM_AXIS_KEY in obj and SEAM_OFFSET_KEY in obj


def clear_stored_seam(obj):
    for k in (SEAM_EDGE_KEY, SEAM_AXIS_KEY, SEAM_OFFSET_KEY, SEAM_DIR_KEY):
        if k in obj:
            del obj[k]


def get_stored_axis(obj, fallback="X"):
    return obj.get(SEAM_AXIS_KEY, fallback)


def get_stored_offset(obj):
    return float(obj.get(SEAM_OFFSET_KEY, 0.0))


def get_stored_edge_index(obj):
    return int(obj.get(SEAM_EDGE_KEY, -1))


# ------------------------------------------------------------
# Robust matching helpers
# ------------------------------------------------------------


def get_center_vertices(bm, axis, offset, center_tolerance):
    return [v for v in bm.verts if abs(signed_distance_to_plane(v.co, axis, offset)) <= center_tolerance]


def connected_component_from_vertex(start, allowed_set):
    allowed = set(allowed_set)
    if start not in allowed:
        return set()

    found = set([start])
    q = deque([start])

    while q:
        v = q.popleft()
        for e in v.link_edges:
            n = e.other_vert(v)
            if n in allowed and n not in found:
                found.add(n)
                q.append(n)

    return found


def build_bfs_addresses(seam_verts, side_verts):
    """
    Multi-source BFS from center seam into one side.
    Each vertex gets:
        root seam vertex index
        depth/ring distance from seam
    This gives a stable topology address without greedy pair cascading.
    """
    side_set = set(side_verts)
    address = {}
    q = deque()

    # Seed neighbours of every seam vertex.
    for root in seam_verts:
        for e in root.link_edges:
            n = e.other_vert(root)
            if n in side_set and n not in address:
                address[n] = (root.index, 1)
                q.append((n, root.index, 1))

    while q:
        v, root_index, depth = q.popleft()
        for e in v.link_edges:
            n = e.other_vert(v)
            if n in side_set and n not in address:
                address[n] = (root_index, depth + 1)
                q.append((n, root_index, depth + 1))

    return address


def edge_length_median(bm):
    lengths = sorted(e.calc_length() for e in bm.edges if e.calc_length() > 0.0)
    if not lengths:
        return 1.0
    return lengths[len(lengths) // 2]


def build_source_buckets(source_verts, source_addr):
    buckets = defaultdict(list)
    for v in source_verts:
        if v in source_addr:
            root_index, depth = source_addr[v]
            buckets[(root_index, depth)].append(v)
    return buckets


def match_source_for_target(target_v, target_addr, source_buckets, axis, offset, max_parallel_distance):
    """
    Match a target vertex to a source vertex using:
    1. same seam root
    2. same graph depth from seam
    3. closest position after reflecting target into source space, measured only parallel to plane

    This avoids the old cascading greedy neighbour-pair problem.
    """
    if target_v not in target_addr:
        return None, None

    key = target_addr[target_v]
    candidates = source_buckets.get(key, [])

    # If exact depth bucket is empty, try adjacent depths as a fallback.
    if not candidates:
        root_index, depth = key
        for delta in (1, -1, 2, -2):
            candidates = source_buckets.get((root_index, depth + delta), [])
            if candidates:
                break

    if not candidates:
        return None, None

    reflected_target = reflect_across_axis_plane(target_v.co, axis, offset)
    reflected_parallel = perpendicular_projection(reflected_target, axis)

    best = None
    best_dist = None

    for src in candidates:
        src_parallel = perpendicular_projection(src.co, axis)
        dist = (src_parallel - reflected_parallel).length
        if best is None or dist < best_dist:
            best = src
            best_dist = dist

    if best is None:
        return None, None

    if max_parallel_distance > 0.0 and best_dist > max_parallel_distance:
        return None, best_dist

    return best, best_dist


# ------------------------------------------------------------
# Operators
# ------------------------------------------------------------

class MESH_OT_store_symmetrize_seam(bpy.types.Operator):
    """Store ONE selected center seam edge"""

    bl_idname = "mesh.store_symmetrize_seam"
    bl_label = "Store Selected Seam Edge"
    bl_options = {"REGISTER", "UNDO"}

    axis: EnumProperty(
        name="Mirror Axis",
        description="Axis perpendicular to the symmetry plane. Auto usually works if the seam edge is vertical.",
        items=(
            ("AUTO", "Auto", "Guess from selected edge"),
            ("X", "X", "Mirror across object-space X plane"),
            ("Y", "Y", "Mirror across object-space Y plane"),
            ("Z", "Z", "Mirror across object-space Z plane"),
        ),
        default="X",
    )

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def execute(self, context):
        obj = context.object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()

        selected = [e for e in bm.edges if e.select]
        if not selected:
            self.report({"ERROR"}, "Select one edge on the center seam.")
            return {"CANCELLED"}

        edge = selected[0]
        v0, v1 = edge.verts
        axis = guess_axis_from_edge(edge) if self.axis == "AUTO" else self.axis
        offset = (axis_value(v0.co, axis) + axis_value(v1.co, axis)) * 0.5

        seam_dir = v1.co - v0.co
        if seam_dir.length > 0.0:
            seam_dir.normalize()
        else:
            seam_dir = Vector((0.0, 0.0, 1.0))

        store_seam(obj, edge.index, axis, offset, seam_dir)
        self.report({"INFO"}, f"Stored seam edge {edge.index}, axis {axis}, plane offset {offset:.6f}.")
        return {"FINISHED"}


class MESH_OT_clear_symmetrize_seam(bpy.types.Operator):
    """Clear stored seam"""

    bl_idname = "mesh.clear_symmetrize_seam"
    bl_label = "Clear Stored Seam"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        clear_stored_seam(context.object)
        self.report({"INFO"}, "Stored seam cleared.")
        return {"FINISHED"}


class MESH_OT_symmetrize_selected_from_stored_seam(bpy.types.Operator):
    """Symmetrize only selected vertices using the stored seam edge"""

    bl_idname = "mesh.symmetrize_selected_from_stored_seam"
    bl_label = "Symmetrize Selected"
    bl_options = {"REGISTER", "UNDO"}

    source_side: EnumProperty(
        name="Direction",
        description="Which side is copied onto the selected target side",
        items=(
            ("POS", "+ to -", "Copy positive side to selected negative-side vertices"),
            ("NEG", "- to +", "Copy negative side to selected positive-side vertices"),
        ),
        default="POS",
    )

    center_tolerance: FloatProperty(
        name="Center Tolerance",
        description="How close vertices must be to the stored symmetry plane to count as center seam vertices",
        default=0.001,
        min=0.0,
        precision=6,
    )

    snap_selected_center: BoolProperty(
        name="Snap Selected Center Verts",
        description="Selected center vertices are projected exactly onto the symmetry plane",
        default=True,
    )

    max_match_distance: FloatProperty(
        name="Max Match Distance",
        description="Safety distance for matching parallel coordinates. 0 disables the limit. Increase if many vertices are skipped.",
        default=0.0,
        min=0.0,
        precision=5,
    )

    use_connected_center_component: BoolProperty(
        name="Use Connected Seam Component",
        description="Use the connected center-line component containing the stored edge. Disable if the seam has small breaks.",
        default=True,
    )

    include_unselected_sources: BoolProperty(
        name="Use Unselected Source Side",
        description="Source vertices do not need to be selected. Only target vertices need selection.",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def execute(self, context):
        obj = context.object
        if not has_stored_seam(obj):
            self.report({"ERROR"}, "No stored seam. Select one center seam edge and click Store Selected Seam Edge first.")
            return {"CANCELLED"}

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        edge_index = get_stored_edge_index(obj)
        if edge_index < 0 or edge_index >= len(bm.edges):
            self.report({"ERROR"}, "Stored seam edge index is invalid. Store the seam again.")
            return {"CANCELLED"}

        stored_edge = bm.edges[edge_index]
        axis = get_stored_axis(obj)
        offset = get_stored_offset(obj)

        all_center_verts = get_center_vertices(bm, axis, offset, self.center_tolerance)
        if len(all_center_verts) < 2:
            self.report({"ERROR"}, "Could not infer center seam. Increase Center Tolerance or store the seam again.")
            return {"CANCELLED"}

        stored_edge_verts = set(stored_edge.verts)
        if self.use_connected_center_component:
            # Prefer the continuous center-line connected to the stored edge.
            start = stored_edge.verts[0]
            seam_verts = connected_component_from_vertex(start, set(all_center_verts))
            # If only one end was included by tolerance, fall back to all center verts.
            if len(seam_verts) < 2 or not stored_edge_verts.issubset(seam_verts):
                seam_verts = set(all_center_verts)
        else:
            seam_verts = set(all_center_verts)

        selected = {v for v in bm.verts if v.select}
        if not selected:
            self.report({"ERROR"}, "Select the target vertices you want to symmetrize.")
            return {"CANCELLED"}

        source_label = self.source_side
        target_label = "NEG" if source_label == "POS" else "POS"

        source_verts = []
        target_verts = []
        center_selected = []

        for v in bm.verts:
            cls = classify_vertex(v, axis, offset, self.center_tolerance)
            if cls == source_label:
                source_verts.append(v)
            elif cls == target_label:
                target_verts.append(v)

        if not self.include_unselected_sources:
            source_verts = [v for v in source_verts if v.select]

        selected_targets = [v for v in selected if classify_vertex(v, axis, offset, self.center_tolerance) == target_label]
        center_selected = [v for v in selected if classify_vertex(v, axis, offset, self.center_tolerance) == "CENTER"]

        if not selected_targets and not center_selected:
            self.report({"ERROR"}, "No selected vertices found on the target side or center seam.")
            return {"CANCELLED"}

        # Build stable topological addresses independently on both sides.
        source_addr = build_bfs_addresses(seam_verts, source_verts)
        target_addr = build_bfs_addresses(seam_verts, target_verts)
        source_buckets = build_source_buckets(source_verts, source_addr)

        if not source_buckets:
            self.report({"ERROR"}, "Could not build source-side topology map. Check source direction or center tolerance.")
            return {"CANCELLED"}

        # If no explicit max distance, use a very generous derived value for reporting only.
        median_len = edge_length_median(bm)
        max_dist = self.max_match_distance

        moved = 0
        skipped = 0
        snapped = 0
        worst_match = 0.0

        for tgt in selected_targets:
            src, dist = match_source_for_target(
                tgt,
                target_addr,
                source_buckets,
                axis,
                offset,
                max_dist,
            )

            if src is None:
                skipped += 1
                continue

            if dist is not None:
                worst_match = max(worst_match, dist)

            tgt.co = reflect_across_axis_plane(src.co, axis, offset)
            moved += 1

        if self.snap_selected_center:
            for v in center_selected:
                v.co = project_to_plane(v.co, axis, offset)
                snapped += 1

        bmesh.update_edit_mesh(obj.data)

        self.report(
            {"INFO"},
            f"Moved {moved}, snapped {snapped}, skipped {skipped}. Axis {axis}, seam verts {len(seam_verts)}, worst match {worst_match:.5f}."
        )
        return {"FINISHED"}


# ------------------------------------------------------------
# N-panel UI
# ------------------------------------------------------------

class VIEW3D_PT_symmetrize_from_stored_seam(bpy.types.Panel):
    bl_label = "Symmetrize From Seam"
    bl_idname = "VIEW3D_PT_symmetrize_from_stored_seam"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Symmetrize"

    def draw(self, context):
        layout = self.layout
        obj = context.object

        col = layout.column(align=True)
        col.label(text="1. Store Center Seam")

        if obj is None or obj.type != "MESH":
            col.label(text="Select a mesh object.", icon="INFO")
            return

        row = col.row(align=True)
        row.operator("mesh.store_symmetrize_seam", text="Store Selected Seam Edge", icon="EDGESEL")
        row.operator("mesh.clear_symmetrize_seam", text="", icon="TRASH")

        if has_stored_seam(obj):
            axis = get_stored_axis(obj)
            offset = get_stored_offset(obj)
            edge_index = get_stored_edge_index(obj)
            col.label(text=f"Stored edge: {edge_index} | Axis: {axis} | Offset: {offset:.5f}", icon="CHECKMARK")
        else:
            col.label(text="No seam stored.", icon="INFO")

        layout.separator()
        box = layout.box()
        box.label(text="2. Select Vertices")
        box.label(text="Select only the target-side vertices")
        box.label(text="you want moved.")

        layout.separator()
        col = layout.column(align=True)
        col.label(text="3. Symmetrize")
        col.operator("mesh.symmetrize_selected_from_stored_seam", text="Symmetrize Selected", icon="MOD_MIRROR")

        helpbox = layout.box()
        helpbox.label(text="Important:")
        helpbox.label(text="Use + to - or - to + in redo panel.")
        helpbox.label(text="If vertices are skipped, increase")
        helpbox.label(text="Center Tolerance or Max Match Distance.")


classes = (
    MESH_OT_store_symmetrize_seam,
    MESH_OT_clear_symmetrize_seam,
    MESH_OT_symmetrize_selected_from_stored_seam,
    VIEW3D_PT_symmetrize_from_stored_seam,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
