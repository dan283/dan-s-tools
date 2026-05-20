bl_info = {
    "name": "Maya-Style Symmetrize From Seam",
    "author": "ChatGPT",
    "version": (0, 7, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Symmetrize",
    "description": "Maya-style topology-propagated symmetrize from one stored center seam edge.",
    "category": "Mesh",
}

import bpy
import bmesh
from mathutils import Vector
from bpy.props import EnumProperty, FloatProperty, BoolProperty, IntProperty
from collections import deque


SEAM_EDGE_KEY = "symmetrize_stored_single_seam_edge_index"
SEAM_AXIS_KEY = "symmetrize_stored_axis"
SEAM_OFFSET_KEY = "symmetrize_stored_plane_offset"


# ------------------------------------------------------------
# Math
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


def classify_vertex(v, axis: str, offset: float, eps: float):
    d = signed_distance_to_plane(v.co, axis, offset)
    if abs(d) <= eps:
        return "CENTER"
    return "POS" if d > 0.0 else "NEG"


def guess_axis_from_edge(edge):
    # Object axis least aligned with selected seam edge.
    v0, v1 = edge.verts
    d = v1.co - v0.co
    if d.length == 0.0:
        return "X"
    d.normalize()
    comps = {"X": abs(d.x), "Y": abs(d.y), "Z": abs(d.z)}
    return min(comps, key=comps.get)


# ------------------------------------------------------------
# Stored seam
# ------------------------------------------------------------


def store_seam(obj, edge_index, axis, offset):
    obj[SEAM_EDGE_KEY] = int(edge_index)
    obj[SEAM_AXIS_KEY] = axis
    obj[SEAM_OFFSET_KEY] = float(offset)


def clear_stored_seam(obj):
    for key in (SEAM_EDGE_KEY, SEAM_AXIS_KEY, SEAM_OFFSET_KEY):
        if key in obj:
            del obj[key]


def has_stored_seam(obj):
    return SEAM_EDGE_KEY in obj and SEAM_AXIS_KEY in obj and SEAM_OFFSET_KEY in obj


def get_stored_edge_index(obj):
    return int(obj.get(SEAM_EDGE_KEY, -1))


def get_stored_axis(obj):
    return obj.get(SEAM_AXIS_KEY, "X")


def get_stored_offset(obj):
    return float(obj.get(SEAM_OFFSET_KEY, 0.0))


# ------------------------------------------------------------
# Topology correspondence: Maya-style face propagation
# ------------------------------------------------------------


def face_side_score(face, axis, offset):
    if not face.verts:
        return 0.0
    return sum(signed_distance_to_plane(v.co, axis, offset) for v in face.verts) / len(face.verts)


def edge_key_from_verts(v1, v2):
    return tuple(sorted((v1.index, v2.index)))


def find_edge_between(v1, v2):
    for e in v1.link_edges:
        if e.other_vert(v1) == v2:
            return e
    return None


def face_other_across_edge(face, edge):
    for f in edge.link_faces:
        if f != face:
            return f
    return None


def best_vertex_match(src_v, candidates, axis, offset, used_targets):
    """Small local fallback used only inside already-paired faces."""
    best = None
    best_dist = None
    wanted = reflect_across_axis_plane(src_v.co, axis, offset)

    for t in candidates:
        if t in used_targets:
            continue
        d = (t.co - wanted).length
        if best is None or d < best_dist:
            best = t
            best_dist = d
    return best


def rotate_list_to_start(seq, start_index):
    return seq[start_index:] + seq[:start_index]


def mapping_error(candidate_map, axis, offset):
    err = 0.0
    for sv, tv in candidate_map.items():
        wanted = reflect_across_axis_plane(sv.co, axis, offset)
        err += (tv.co - wanted).length
    return err


def complete_face_vertex_map(src_face, tgt_face, current_vmap, axis, offset):
    """
    Complete source->target vertex mapping for paired faces using polygon order.

    This is stricter than nearest-corner matching.
    Given at least a shared mapped edge, map the whole face by loop order.
    Test both winding directions and pick the lower reflection error.

    This prevents the last remaining stray vertices caused by wrong local
    corner choices inside quads/triangles.
    """
    src_verts = list(src_face.verts)
    tgt_verts = list(tgt_face.verts)

    if len(src_verts) != len(tgt_verts):
        return None

    n = len(src_verts)
    anchors = []

    for i, sv in enumerate(src_verts):
        tv = current_vmap.get(sv)
        if tv is not None and tv in tgt_verts:
            anchors.append((i, tgt_verts.index(tv)))

    # Need at least one anchor. Usually there are two: the propagated edge.
    if not anchors:
        return None

    candidates = []

    # Try every anchor as alignment seed, both windings.
    for src_i, tgt_i in anchors:
        src_rot = rotate_list_to_start(src_verts, src_i)

        tgt_forward = rotate_list_to_start(tgt_verts, tgt_i)
        map_forward = {src_rot[k]: tgt_forward[k] for k in range(n)}
        candidates.append(map_forward)

        # Reverse winding but keep anchored target vertex first.
        tgt_rev_raw = list(reversed(tgt_verts))
        tgt_rev_i = tgt_rev_raw.index(tgt_verts[tgt_i])
        tgt_reverse = rotate_list_to_start(tgt_rev_raw, tgt_rev_i)
        map_reverse = {src_rot[k]: tgt_reverse[k] for k in range(n)}
        candidates.append(map_reverse)

    valid = []
    for cand in candidates:
        ok = True
        for sv, tv in cand.items():
            existing = current_vmap.get(sv)
            if existing is not None and existing != tv:
                ok = False
                break
        if ok:
            valid.append(cand)

    if not valid:
        return None

    return min(valid, key=lambda m: mapping_error(m, axis, offset))


def seed_face_pair_from_seam_edge(seam_edge, axis, offset):
    """
    The selected seam edge should have one adjacent face on each side.
    Those two faces are the initial source/target face pair.
    """
    faces = list(seam_edge.link_faces)
    if len(faces) < 2:
        return None, None

    # Pick the two faces with the most opposite side scores.
    best = None
    best_score = None
    for i in range(len(faces)):
        for j in range(i + 1, len(faces)):
            si = face_side_score(faces[i], axis, offset)
            sj = face_side_score(faces[j], axis, offset)
            score = abs(si - sj)
            if best is None or score > best_score:
                best = (faces[i], faces[j])
                best_score = score

    if best is None:
        return None, None

    f1, f2 = best
    if face_side_score(f1, axis, offset) >= face_side_score(f2, axis, offset):
        return f1, f2
    return f2, f1


def build_topology_correspondence(seam_edge, axis, offset, max_faces=200000):
    """
    Build POS->NEG vertex correspondence by propagating paired faces.

    This is the Maya-like part:
    - start from the two faces adjacent to the selected seam edge
    - map seam verts to themselves
    - map remaining first-face verts by local reflected position
    - walk across corresponding edges on both sides
    - each new face pair completes only from its already-known shared edge

    No global nearest-vertex matching is used.
    """

    pos_seed, neg_seed = seed_face_pair_from_seam_edge(seam_edge, axis, offset)
    if pos_seed is None or neg_seed is None:
        return {}, {}, 0

    pos_to_neg = {}
    neg_to_pos = {}
    paired_faces = {}
    used_neg_faces = set()
    queue = deque()

    # Seam vertices map to themselves for the initial edge anchors.
    for v in seam_edge.verts:
        pos_to_neg[v] = v
        neg_to_pos[v] = v

    seed_map = complete_face_vertex_map(pos_seed, neg_seed, pos_to_neg, axis, offset)
    if seed_map is None:
        return {}, {}, 0

    for pv, nv in seed_map.items():
        pos_to_neg[pv] = nv
        neg_to_pos[nv] = pv

    paired_faces[pos_seed] = neg_seed
    used_neg_faces.add(neg_seed)
    queue.append((pos_seed, neg_seed))

    processed = 0

    while queue and processed < max_faces:
        pos_face, neg_face = queue.popleft()
        processed += 1

        # Ensure this face pair has complete local vertex correspondence.
        local_map = complete_face_vertex_map(pos_face, neg_face, pos_to_neg, axis, offset)
        if local_map is None:
            continue

        for pv, nv in local_map.items():
            if pv not in pos_to_neg:
                pos_to_neg[pv] = nv
            if nv not in neg_to_pos:
                neg_to_pos[nv] = pv

        # Propagate across every non-seam edge of the positive face.
        for pe in pos_face.edges:
            pa, pb = pe.verts

            if pa not in pos_to_neg or pb not in pos_to_neg:
                continue

            na = pos_to_neg[pa]
            nb = pos_to_neg[pb]
            ne = find_edge_between(na, nb)
            if ne is None:
                continue

            next_pos_face = face_other_across_edge(pos_face, pe)
            next_neg_face = face_other_across_edge(neg_face, ne)

            if next_pos_face is None or next_neg_face is None:
                continue

            if next_pos_face in paired_faces:
                continue
            if next_neg_face in used_neg_faces:
                continue

            # Do not swap faces here. If topology propagation produces faces on
            # unexpected sides, skip them instead of guessing. Guessing is what
            # creates stray mismatches.
            if face_side_score(next_pos_face, axis, offset) < face_side_score(next_neg_face, axis, offset):
                continue

            if len(next_pos_face.verts) != len(next_neg_face.verts):
                continue

            candidate_map = complete_face_vertex_map(next_pos_face, next_neg_face, pos_to_neg, axis, offset)
            if candidate_map is None:
                continue

            # Conflict check. Never overwrite an existing pair with a different one.
            conflict = False
            for pv, nv in candidate_map.items():
                if pv in pos_to_neg and pos_to_neg[pv] != nv:
                    conflict = True
                    break
                if nv in neg_to_pos and neg_to_pos[nv] != pv:
                    conflict = True
                    break

            if conflict:
                continue

            for pv, nv in candidate_map.items():
                pos_to_neg[pv] = nv
                neg_to_pos[nv] = pv

            paired_faces[next_pos_face] = next_neg_face
            used_neg_faces.add(next_neg_face)
            queue.append((next_pos_face, next_neg_face))

    return pos_to_neg, neg_to_pos, processed


# ------------------------------------------------------------
# Operators
# ------------------------------------------------------------

class MESH_OT_store_symmetrize_seam(bpy.types.Operator):
    """Store one selected center seam edge"""

    bl_idname = "mesh.store_symmetrize_seam"
    bl_label = "Store Seam Edge"
    bl_options = {"REGISTER", "UNDO"}

    axis: EnumProperty(
        name="Mirror Axis",
        items=(
            ("AUTO", "Auto", "Guess axis from selected edge"),
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

        selected_edges = [e for e in bm.edges if e.select]
        if not selected_edges:
            self.report({"ERROR"}, "Select one edge on the center seam first.")
            return {"CANCELLED"}

        edge = selected_edges[0]
        v0, v1 = edge.verts
        axis = guess_axis_from_edge(edge) if self.axis == "AUTO" else self.axis
        offset = (axis_value(v0.co, axis) + axis_value(v1.co, axis)) * 0.5

        store_seam(obj, edge.index, axis, offset)
        self.report({"INFO"}, f"Stored edge {edge.index}; axis {axis}; offset {offset:.6f}")
        return {"FINISHED"}


class MESH_OT_clear_symmetrize_seam(bpy.types.Operator):
    """Clear stored seam"""

    bl_idname = "mesh.clear_symmetrize_seam"
    bl_label = "Clear Seam"
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
    """Maya-style topology symmetrize selected vertices"""

    bl_idname = "mesh.symmetrize_selected_from_stored_seam"
    bl_label = "Symmetrize Selected"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(
        name="Mode",
        items=(
            ("AUTO", "Auto selected side", "Selected vertices on either side are mirrored from their topological opposite"),
            ("POS_TO_NEG", "+ to - only", "Only selected negative-side vertices are moved from positive side"),
            ("NEG_TO_POS", "- to + only", "Only selected positive-side vertices are moved from negative side"),
        ),
        default="AUTO",
    )

    center_tolerance: FloatProperty(
        name="Center Tolerance",
        description="Selected vertices this close to the stored plane can be treated as center vertices",
        default=0.0001,
        min=0.0,
        precision=6,
    )

    snap_selected_center: BoolProperty(
        name="Snap Selected Center",
        description="Project selected center vertices onto the symmetry plane",
        default=False,
    )

    max_faces: IntProperty(
        name="Max Propagated Faces",
        description="Safety limit for topology propagation",
        default=200000,
        min=100,
        max=1000000,
    )

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def execute(self, context):
        obj = context.object
        if not has_stored_seam(obj):
            self.report({"ERROR"}, "No stored seam. Select one center edge and click Store Seam Edge.")
            return {"CANCELLED"}

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        edge_index = get_stored_edge_index(obj)
        if edge_index < 0 or edge_index >= len(bm.edges):
            self.report({"ERROR"}, "Stored seam edge is invalid. Store it again.")
            return {"CANCELLED"}

        seam_edge = bm.edges[edge_index]
        axis = get_stored_axis(obj)
        offset = get_stored_offset(obj)

        selected = [v for v in bm.verts if v.select]
        if not selected:
            self.report({"ERROR"}, "Select vertices to symmetrize.")
            return {"CANCELLED"}

        pos_to_neg, neg_to_pos, face_count = build_topology_correspondence(
            seam_edge,
            axis,
            offset,
            self.max_faces,
        )

        if not pos_to_neg or not neg_to_pos:
            self.report({"ERROR"}, "Could not build topology correspondence from the stored seam edge.")
            return {"CANCELLED"}

        moved = 0
        skipped = 0
        snapped = 0

        # Copy from original coordinates, not progressively modified ones.
        original_positions = {v: v.co.copy() for v in bm.verts}

        for v in selected:
            side = classify_vertex(v, axis, offset, self.center_tolerance)

            if side == "CENTER":
                if self.snap_selected_center:
                    v.co = set_axis_value(v.co, axis, offset)
                    snapped += 1
                continue

            if self.mode == "POS_TO_NEG" and side != "NEG":
                skipped += 1
                continue
            if self.mode == "NEG_TO_POS" and side != "POS":
                skipped += 1
                continue

            if side == "NEG":
                src = neg_to_pos.get(v)
            else:
                src = pos_to_neg.get(v)

            if src is None or src == v:
                skipped += 1
                continue

            v.co = reflect_across_axis_plane(original_positions[src], axis, offset)
            moved += 1

        bmesh.update_edit_mesh(obj.data)
        self.report({"INFO"}, f"Moved {moved}; skipped {skipped}; snapped {snapped}; propagated faces {face_count}")
        return {"FINISHED"}


# ------------------------------------------------------------
# UI
# ------------------------------------------------------------

class VIEW3D_PT_symmetrize_from_stored_seam_clean(bpy.types.Panel):
    bl_label = "Symmetrize"
    bl_idname = "VIEW3D_PT_symmetrize_from_stored_seam_clean"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Symmetrize"

    def draw(self, context):
        layout = self.layout
        obj = context.object

        if obj is None or obj.type != "MESH":
            layout.label(text="Select a mesh object.", icon="INFO")
            return

        if context.mode != "EDIT_MESH":
            layout.label(text="Enter Edit Mode.", icon="INFO")
            return

        box = layout.box()
        box.label(text="1. Store center seam", icon="EDGESEL")
        row = box.row(align=True)
        row.operator("mesh.store_symmetrize_seam", text="Store Selected Edge")
        row.operator("mesh.clear_symmetrize_seam", text="", icon="TRASH")

        if has_stored_seam(obj):
            box.label(text=f"Edge {get_stored_edge_index(obj)} | {get_stored_axis(obj)}={get_stored_offset(obj):.5f}", icon="CHECKMARK")
        else:
            box.label(text="No seam stored", icon="INFO")

        box = layout.box()
        box.label(text="2. Select target vertices", icon="VERTEXSEL")
        box.operator("mesh.symmetrize_selected_from_stored_seam", text="Symmetrize Selected", icon="MOD_MIRROR")

        col = layout.column(align=True)
        col.label(text="Maya-style topology mode:")
        col.label(text="Pairs are propagated face-to-face")
        col.label(text="from the stored seam edge.")
        col.label(text="No global nearest matching.")


classes = (
    MESH_OT_store_symmetrize_seam,
    MESH_OT_clear_symmetrize_seam,
    MESH_OT_symmetrize_selected_from_stored_seam,
    VIEW3D_PT_symmetrize_from_stored_seam_clean,
)

LEGACY_CLASS_NAMES = (
    "VIEW3D_PT_symmetrize_from_seam",
    "VIEW3D_PT_symmetrize_from_stored_seam",
    "MESH_OT_symmetrize_from_seam",
)


def unregister_legacy_classes():
    for name in LEGACY_CLASS_NAMES:
        cls = getattr(bpy.types, name, None)
        if cls is not None:
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                pass


def register():
    unregister_legacy_classes()
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                pass
            bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    unregister_legacy_classes()


if __name__ == "__main__":
    register()
