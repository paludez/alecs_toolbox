"""Poll and bmesh helpers for edit-mesh operators."""
import math

import bmesh
from mathutils import Vector, Matrix
from bpy_extras.view3d_utils import location_3d_to_region_2d

from . import edit_curve_helpers as ech


DRAFT_EPS = 1e-6
DRAFT_PLANAR_EPS = 1e-4


def edit_mesh_transform_pivot_world(context, obj, bm):
    """
    World-space pivot matching Tool Settings → Transform Pivot Point (Edit Mesh).
    INDIVIDUAL_ORIGINS is approximated with the median of the current selection
    (full per-island pivots would require loose-part detection).
    """
    pivot_type = context.scene.tool_settings.transform_pivot_point
    mw = obj.matrix_world
    sel_verts = [v for v in bm.verts if v.select]

    if pivot_type == 'CURSOR':
        return context.scene.cursor.location.copy()

    if pivot_type == 'ACTIVE_ELEMENT':
        active = bm.select_history.active
        if isinstance(active, bmesh.types.BMVert):
            return mw @ active.co
        if isinstance(active, bmesh.types.BMEdge):
            v0, v1 = active.verts
            return (mw @ v0.co + mw @ v1.co) * 0.5
        if isinstance(active, bmesh.types.BMFace):
            return mw @ active.calc_center_median()
        if sel_verts:
            acc = Vector((0.0, 0.0, 0.0))
            for v in sel_verts:
                acc += mw @ v.co
            return acc / len(sel_verts)
        return mw.translation.copy()

    if pivot_type == 'BOUNDING_BOX_CENTER':
        if not sel_verts:
            return mw.translation.copy()
        ws = [mw @ v.co for v in sel_verts]
        xs = [p.x for p in ws]
        ys = [p.y for p in ws]
        zs = [p.z for p in ws]
        return Vector(
            (
                (min(xs) + max(xs)) * 0.5,
                (min(ys) + max(ys)) * 0.5,
                (min(zs) + max(zs)) * 0.5,
            )
        )

    if pivot_type in {'MEDIAN_POINT', 'INDIVIDUAL_ORIGINS'}:
        if not sel_verts:
            return mw.translation.copy()
        acc = Vector((0.0, 0.0, 0.0))
        for v in sel_verts:
            acc += mw @ v.co
        return acc / len(sel_verts)

    return mw.translation.copy()


def scale_object_uniform_world_around_pivot(obj, factor, pivot_world):
    """Apply uniform world-space scale factor around pivot via matrix_world."""
    k = factor
    S = Matrix.Identity(4)
    S[0][0] = S[1][1] = S[2][2] = k
    T = Matrix.Translation(pivot_world)
    Ti = Matrix.Translation(-pivot_world)
    obj.matrix_world = T @ S @ Ti @ obj.matrix_world


def select_history_edges(bm):
    return [elem for elem in bm.select_history if isinstance(elem, bmesh.types.BMEdge)]


def select_history_verts(bm):
    return [elem for elem in bm.select_history if isinstance(elem, bmesh.types.BMVert)]


def get_active_or_latest_selected_edge(bm):
    """Active edge from select history, else last selected edge, else None."""
    active_edge = bm.select_history.active
    if isinstance(active_edge, bmesh.types.BMEdge):
        return active_edge
    selected_edges = [e for e in bm.edges if e.select]
    if selected_edges:
        return selected_edges[-1]
    return None


def get_equalize_reference_edge(bm):
    """Edge used as length reference for equalize (active in history or sole selected edge)."""
    active_elem = bm.select_history.active
    if isinstance(active_elem, bmesh.types.BMEdge):
        return active_elem
    sel_edges = [e for e in bm.edges if e.select]
    if len(sel_edges) == 1:
        return sel_edges[0]
    return None


def poll_active_mesh_edit_mode(context):
    obj = context.active_object
    return (
        obj is not None
        and obj.type == 'MESH'
        and context.mode == 'EDIT_MESH'
    )


def poll_two_edges_in_select_history(context):
    if not poll_active_mesh_edit_mode(context):
        return False
    try:
        bm = bmesh.from_edit_mesh(context.active_object.data)
        return len(select_history_edges(bm)) >= 2
    except:  # noqa: E722 — match prior operator poll (any failure -> disabled)
        return False


def edge_pair_from_select_history(bm):
    """
    Return (edge_moving, edge_stationary) from select history, or (None, None) if invalid.
    Last selected edge is stationary; previous is moving (same convention as set_edge_angle).
    """
    history = select_history_edges(bm)
    if len(history) < 2:
        return None, None
    return history[-2], history[-1]


def angle_pivot_for_edge_pair(stationary_edge, moving_edge):
    """
    Common vertex, angle in radians between edge directions, or (None, None, None) if not measurable.
    """
    common_verts = set(stationary_edge.verts) & set(moving_edge.verts)
    if not common_verts:
        return None, None, None
    pivot = common_verts.pop()
    v_stat = [v for v in stationary_edge.verts if v != pivot][0]
    v_mov = [v for v in moving_edge.verts if v != pivot][0]
    t0 = (v_stat.co - pivot.co).normalized()
    t1 = (v_mov.co - pivot.co).normalized()
    if t0.length < 1e-9 or t1.length < 1e-9:
        return None, None, None
    if t0.cross(t1).length < 1e-6:
        return None, None, None
    return pivot.co.copy(), t0.angle(t1), (moving_edge.index, stationary_edge.index)


def poll_mesh_or_curve_collinear_coplanar(context):
    return poll_active_mesh_edit_mode(context) or ech.poll_active_curve_edit_mode(context)


def bm_edge_key(edge):
    """Stable unordered key for lookup after bmesh/topology edits."""
    a, b = edge.verts[0].index, edge.verts[1].index
    return (a, b) if a <= b else (b, a)


def bm_face_key(face):
    return frozenset(v.index for v in face.verts)


def bm_edge_from_key(bm, key):
    if key is None:
        return None
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    i0, i1 = key
    try:
        v0 = bm.verts[i0]
        v1 = bm.verts[i1]
        if not v0.is_valid or not v1.is_valid:
            return None
    except (IndexError, ReferenceError):
        return None
    for ed in v0.link_edges:
        ov = ed.other_vert(v0)
        if ov.is_valid and ov.index == i1:
            return ed
    return None


def bm_face_from_key(bm, key):  # key = frozenset of vert indices
    if key is None:
        return None
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        if not f.is_valid:
            continue
        try:
            if frozenset(v.index for v in f.verts) == key:
                return f
        except ReferenceError:
            continue
    return None


def bmesh_edge_split_normalized(edge, v_from, fac):
    """bmesh.utils.edge_split with defensive (edge, vert) typing.

    Blender doc order is (BMEdge, BMVert); some builds / edge cases behave
    otherwise — normalize so callers always get (new_edge_fragment, split_vert).
    """
    tup = bmesh.utils.edge_split(edge, v_from, fac)
    a, b = tup
    if isinstance(a, bmesh.types.BMVert):
        split_vert, split_edge_piece = a, b
        return split_edge_piece, split_vert
    split_edge_piece, split_vert = a, b
    return split_edge_piece, split_vert


def hovered_edge(bm, mw, region, rv3d, mouse_xy, threshold_px=14, exclude_edges=None):
    """Pick edge under mouse_xy in screen space.

    Returns (edge, t_along, hover_d2_px) or (None, None, None) if no edge is
    within threshold_px.
    """
    if region is None or rv3d is None:
        return None, None, None
    bm.edges.ensure_lookup_table()
    excluded = set()
    if exclude_edges:
        for e in exclude_edges:
            if e is not None:
                excluded.add(e)
    best_d2 = float(threshold_px) * float(threshold_px)
    best_edge = None
    best_t = 0.0
    for e in bm.edges:
        if e in excluded:
            continue
        v0w = mw @ e.verts[0].co
        v1w = mw @ e.verts[1].co
        p0 = location_3d_to_region_2d(region, rv3d, v0w)
        p1 = location_3d_to_region_2d(region, rv3d, v1w)
        if p0 is None or p1 is None:
            continue
        ax, ay = p0.x, p0.y
        bx, by = p1.x, p1.y
        dx = bx - ax
        dy = by - ay
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq < 1e-6:
            continue
        mx = float(mouse_xy[0])
        my = float(mouse_xy[1])
        t = ((mx - ax) * dx + (my - ay) * dy) / seg_len_sq
        t_clamped = max(0.0, min(1.0, t))
        cx = ax + t_clamped * dx
        cy = ay + t_clamped * dy
        ex = mx - cx
        ey = my - cy
        d2 = ex * ex + ey * ey
        if d2 < best_d2:
            best_d2 = d2
            best_edge = e
            best_t = t_clamped
    if best_edge is None:
        return None, None, None
    return best_edge, best_t, best_d2


def working_plane_for_edges(edge_a, edge_b, mw):
    """4-point coplanar working plane from two BMEdges.

    Returns (origin, normal, u_ax, v_ax) or None if the four endpoints are not
    coplanar within DRAFT_PLANAR_EPS, or are fully collinear.
    """
    pa0 = mw @ edge_a.verts[0].co
    pa1 = mw @ edge_a.verts[1].co
    pb0 = mw @ edge_b.verts[0].co
    pb1 = mw @ edge_b.verts[1].co
    pts = (pa0, pa1, pb0, pb1)
    d1 = pa1 - pa0
    if d1.length_squared < 1e-12:
        return None
    normal: Vector | None = None
    for p in (pb0, pb1):
        cross = d1.cross(p - pa0)
        if cross.length_squared > 1e-14:
            normal = cross.normalized()
            break
    if normal is None:
        return None
    for p in pts:
        if abs((p - pa0).dot(normal)) > DRAFT_PLANAR_EPS:
            return None
    u_ax = d1.normalized()
    v_ax = normal.cross(u_ax).normalized()
    return (pa0.copy(), normal, u_ax, v_ax)


def resolve_three_definition_verts(bm):
    """Last three verts in select history, else last three selected."""
    history = select_history_verts(bm)
    if len(history) >= 3:
        return history[-3:]
    selected = [v for v in bm.verts if v.select]
    if len(selected) >= 3:
        return selected[-3:]
    return None


def circumcircle_from_three_points(p0, p1, p2, eps=1e-10):
    """Circumcircle through three world-space points.

    Returns (center, radius, u_axis, v_axis) with u/v an orthonormal basis in the
  plane, or None when the points are collinear.
    """
    ab = p1 - p0
    ac = p2 - p0
    n = ab.cross(ac)
    n_len_sq = n.length_squared
    if n_len_sq < eps * eps:
        return None
    denom = 2.0 * n_len_sq
    center = p0 + (ab.length_squared * ac.cross(n) + ac.length_squared * n.cross(ab)) / denom
    radius = (p0 - center).length
    if radius < eps:
        return None
    u = p0 - center
    u.normalize()
    v = n.normalized().cross(u)
    v.normalize()
    return center, radius, u, v


def circle_phase_for_point(center, u_axis, v_axis, point):
    """Angle on the (u, v) circle parameterization for a point on the circumference."""
    offset = point - center
    return math.atan2(offset.dot(v_axis), offset.dot(u_axis))
