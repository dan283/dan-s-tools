bl_info = {
    "name": "Maya-Style Symmetrize From Seam",
    "author": "ChatGPT",
    "version": (0, 8, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Symmetrize",
    "description": "Maya-style topology symmetrize from one stored center seam edge, with neighbor-average fallback for asymmetrical topology.",
    "category": "Mesh",
}

import bpy
import bmesh
from mathutils import Vector
from mathutils.kdtree import KDTree
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


def rotate_list_to_start(seq, start_index):
    return seq[start_index:] + seq[:start_index]


def mapping_error(candidate_map, axis, offset):
    err = 0.0
    for sv, tv in candidate_map.items():
        wanted = reflect_across_axis_plane(sv.co, axis, offset)
        err += (tv.co - wanted).length
    return err


def complete_face_vertex_map(src_face, tgt_face, current_vmap, axis, offset):
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

    if not anchors:
        return None

    candidates = []

    for src_i, tgt_i in anchors:
        src_rot = rotate_list_to_start(src_verts, src_i)

        tgt_forward = rotate_list_to_start(tgt_verts, tgt_i)
        candidates.append({src_rot[k]: tgt_forward[k] for k in range(n)})

        tgt_rev_raw = list(reversed(tgt_verts))
        tgt_rev_i = tgt_rev_raw.index(tgt_verts[tgt_i])
        tgt_reverse = rotate_list_to_start(tgt_rev_raw, tgt_rev_i)
        candidates.append({src_rot[k]: tgt_reverse[k] for k in range(n)})

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
    faces = list(seam_edge.link_faces)
    if len(faces) < 2:
        return None, None

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
    pos_seed, neg_seed = seed_face_pair_from_seam_edge(seam_edge, axis, offset)
    if pos_seed is None or neg_seed is None:
        return {}, {}, 0

    pos_to_neg = {}
    neg_to_pos = {}
    paired_faces = {}
    used_neg_faces = set()
    queue = deque()

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

        local_map = complete_face_vertex_map(pos_face, neg_face, pos_to_neg, axis, offset)
        if local_map is None:
            continue

        for pv, nv in local_map.items():
            if pv not in pos_to_neg:
                pos_to_neg[pv] = nv
            if nv not in neg_to_pos:
                neg_to_pos[nv] = pv

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

            if face_side_score(next_pos_face, axis, offset) < face_side_score(next_neg_face, axis, offset):
                continue
            if len(next_pos_face.verts) != len(next_neg_face.verts):
                continue

            candidate_map = complete_face_vertex_map(next_pos_face, next_neg_face, pos_to_neg, axis, offset)
            if candidate_map is None:
                continue

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
# Fallback matching for asymmetrical topology
# ------------------------------------------------------------


def build_fallback_kdtree(source_verts, axis, offset, min_side_distance):
    valid = []
    for v in source_verts:
        if abs(signed_distance_to_plane(v.co, axis, offset)) >= min_side_distance:
            valid.append(v)

    kd = KDTree(len(valid))
    for i, v in enumerate(valid):
        kd.insert(v.co.copy(), i)
    kd.balance()
    return kd, valid


def nearest_reflected_fallback(target_v, source_kd, source_verts, original_positions, axis, offset, count, max_dist):
    if not source_verts:
        return None, None

    wanted = reflect_across_axis_plane(original_positions[target_v], axis, offset)
    n = min(max(1, count), len(source_verts))

    best = None
    best_dist = None

    for co, index, dist in source_kd.find_n(wanted, n):
        if max_dist > 0.0 and dist > max_dist:
            continue
        if best is None or dist < best_dist:
            best = source_verts[index]
            best_dist = dist

    return best, best_dist


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

    asymmetry_fallback: EnumProperty(
        name="Asymmetrical Topology Fallback",
        description="What to do when no topology pair is found for a selected vertex",
        items=(
            ("OFF", "Off", "Skip vertices without a topology pair"),
            ("NEIGHBOR_AVERAGE", "Neighbor Average", "Use already solved neighboring vertices to place unmatched extra-edge vertices"),
            ("NEAREST", "Nearest Reflected", "Use nearest opposite-side vertex after reflection"),
            ("AVERAGED", "Averaged Nearest", "Average several nearest opposite-side reflected candidates"),
            ("NEIGHBOR_THEN_AVERAGED", "Neighbor, Then Averaged", "Try neighbor average first, then averaged nearest if needed"),
        ),
        default="NEIGHBOR_THEN_AVERAGED",
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

    fallback_candidates: IntProperty(
        name="Fallback Candidates",
        description="How many nearest opposite-side vertices to consider for asymmetrical fallback",
        default=4,
        min=1,
        max=32,
    )

    fallback_max_distance: FloatProperty(
        name="Fallback Max Distance",
        description="Reject fallback matches farther than this after reflection. 0 disables the limit.",
        default=0.0,
        min=0.0,
        precision=5,
    )

    fallback_ignore_center: FloatProperty(
        name="Fallback Ignore Center",
        description="Opposite-side fallback source vertices closer than this to the center plane are ignored",
        default=0.001,
        min=0.0,
        precision=5,
    )

    fallback_blend: FloatProperty(
        name="Fallback Blend",
        description="Blend fallback result with current vertex position. 1.0 fully applies fallback.",
        default=1.0,
        min=0.0,
        max=1.0,
        precision=3,
    )

    neighbor_average_iterations: IntProperty(
        name="Neighbor Avg Iterations",
        description="Extra passes for filling unmatched selected verts from solved neighboring verts",
        default=12,
        min=1,
        max=64,
    )

    neighbor_search_depth: IntProperty(
        name="Neighbor Search Depth",
        description="How many edge rings outward to search for solved verts when filling unmatched extra verts",
        default=8,
        min=1,
        max=32,
    )

    neighbor_offset_mode: EnumProperty(
        name="Neighbor Placement",
        description="How unmatched extra-edge vertices are placed from solved neighbors",
        items=(
            ("PURE_AVERAGE", "Pure Average", "Snap to the average of solved neighbor positions"),
            ("PRESERVE_OFFSET", "Preserve Offset", "Average solved neighbor positions while preserving each original neighbor-to-vertex offset"),
        ),
        default="PRESERVE_OFFSET",
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
        fallback_moved = 0
        skipped = 0
        snapped = 0

        original_positions = {v: v.co.copy() for v in bm.verts}
        solved_positions = {}
        unresolved = []

        pos_verts = [v for v in bm.verts if classify_vertex(v, axis, offset, self.center_tolerance) == "POS"]
        neg_verts = [v for v in bm.verts if classify_vertex(v, axis, offset, self.center_tolerance) == "NEG"]

        pos_kd = pos_list = neg_kd = neg_list = None
        if self.asymmetry_fallback in {"NEAREST", "AVERAGED", "NEIGHBOR_THEN_AVERAGED"}:
            pos_kd, pos_list = build_fallback_kdtree(pos_verts, axis, offset, self.fallback_ignore_center)
            neg_kd, neg_list = build_fallback_kdtree(neg_verts, axis, offset, self.fallback_ignore_center)

        for v in selected:
            side = classify_vertex(v, axis, offset, self.center_tolerance)

            if side == "CENTER":
                if self.snap_selected_center:
                    solved_positions[v] = set_axis_value(original_positions[v], axis, offset)
                    snapped += 1
                continue

            if self.mode == "POS_TO_NEG" and side != "NEG":
                skipped += 1
                continue
            if self.mode == "NEG_TO_POS" and side != "POS":
                skipped += 1
                continue

            src = neg_to_pos.get(v) if side == "NEG" else pos_to_neg.get(v)

            if src is not None and src != v:
                solved_positions[v] = reflect_across_axis_plane(original_positions[src], axis, offset)
                moved += 1
            else:
                unresolved.append((v, side))

        def neighbor_average_target(v):
            """
            Fill an unmatched/asymmetrical vertex using the displacement field
            from nearby already-solved vertices.

            This is better than averaging positions directly:
                delta = solved_neighbor_position - original_neighbor_position
                target = original_vertex_position + average(delta)

            That means extra edges/loops inherit the same local transform instead
            of collapsing onto a neighbor. It also searches multiple edge rings,
            so small dangling asymmetric islands do not get left behind.
            """
            visited = {v}
            frontier = [v]
            found = []

            for depth in range(1, self.neighbor_search_depth + 1):
                next_frontier = []

                for cur in frontier:
                    for e in cur.link_edges:
                        n = e.other_vert(cur)
                        if n in visited:
                            continue
                        visited.add(n)
                        next_frontier.append(n)

                        if n in solved_positions:
                            found.append((n, depth))

                if found:
                    break
                frontier = next_frontier

            if not found:
                return None

            total = Vector((0.0, 0.0, 0.0))
            total_w = 0.0

            for n, depth in found:
                if self.neighbor_offset_mode == "PURE_AVERAGE":
                    candidate = solved_positions[n]
                else:
                    delta = solved_positions[n] - original_positions[n]
                    candidate = original_positions[v] + delta

                edge_dist = (original_positions[v] - original_positions[n]).length
                w = 1.0 / max(edge_dist * depth, 0.000001)
                total += candidate * w
                total_w += w

            if total_w <= 0.0:
                return None
            return total / total_w

        still_unresolved = unresolved

        if self.asymmetry_fallback in {"NEIGHBOR_AVERAGE", "NEIGHBOR_THEN_AVERAGED"}:
            for _ in range(self.neighbor_average_iterations):
                if not still_unresolved:
                    break

                next_unresolved = []
                changed = False

                for v, side in still_unresolved:
                    target = neighbor_average_target(v)
                    if target is None:
                        next_unresolved.append((v, side))
                        continue

                    solved_positions[v] = original_positions[v].lerp(target, self.fallback_blend)
                    fallback_moved += 1
                    changed = True

                still_unresolved = next_unresolved
                if not changed:
                    break

        if self.asymmetry_fallback in {"NEAREST", "AVERAGED", "NEIGHBOR_THEN_AVERAGED"}:
            for v, side in still_unresolved:
                source_kd, source_list = (pos_kd, pos_list) if side == "NEG" else (neg_kd, neg_list)

                if not source_list:
                    skipped += 1
                    continue

                if self.asymmetry_fallback == "NEAREST":
                    fb_src, _ = nearest_reflected_fallback(
                        v,
                        source_kd,
                        source_list,
                        original_positions,
                        axis,
                        offset,
                        self.fallback_candidates,
                        self.fallback_max_distance,
                    )
                    if fb_src is None:
                        skipped += 1
                        continue
                    target = reflect_across_axis_plane(original_positions[fb_src], axis, offset)

                else:
                    wanted = reflect_across_axis_plane(original_positions[v], axis, offset)
                    n = min(max(1, self.fallback_candidates), len(source_list))
                    total = Vector((0.0, 0.0, 0.0))
                    total_w = 0.0

                    for co, index, dist in source_kd.find_n(wanted, n):
                        if self.fallback_max_distance > 0.0 and dist > self.fallback_max_distance:
                            continue
                        src_v = source_list[index]
                        w = 1.0 / max(dist, 0.000001)
                        total += reflect_across_axis_plane(original_positions[src_v], axis, offset) * w
                        total_w += w

                    if total_w <= 0.0:
                        skipped += 1
                        continue

                    target = total / total_w

                solved_positions[v] = original_positions[v].lerp(target, self.fallback_blend)
                fallback_moved += 1

        else:
            skipped += len(still_unresolved)

        for v, target in solved_positions.items():
            v.co = target

        bmesh.update_edit_mesh(obj.data)
        self.report({"INFO"}, f"Moved {moved}; fallback {fallback_moved}; skipped {skipped}; snapped {snapped}; propagated faces {face_count}")
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
        col.label(text="Topology first, fallback optional:")
        col.label(text="Use Neighbor Average for")
        col.label(text="extra edges on one side.")


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
