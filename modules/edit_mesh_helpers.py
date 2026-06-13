"""Poll and bmesh helpers for edit-mesh operators."""
import math

import bmesh
from mathutils import Vector, Matrix
from bpy_extras.view3d_utils import location_3d_to_region_2d

from . import cursor_plane as cp
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


def hovered_vert(bm, mw, region, rv3d, mouse_xy, threshold_px=14, exclude_indices=None):
    """Pick vertex under mouse_xy in screen space.

    Returns (vert, hover_d2_px) or (None, None) if none within threshold_px.
    """
    if region is None or rv3d is None:
        return None, None
    bm.verts.ensure_lookup_table()
    excluded = set(exclude_indices or ())
    best_d2 = float(threshold_px) * float(threshold_px)
    best_vert = None
    mx = float(mouse_xy[0])
    my = float(mouse_xy[1])
    for v in bm.verts:
        if not v.is_valid or v.index in excluded:
            continue
        p = location_3d_to_region_2d(region, rv3d, mw @ v.co)
        if p is None:
            continue
        ex = mx - p.x
        ey = my - p.y
        d2 = ex * ex + ey * ey
        if d2 < best_d2:
            best_d2 = d2
            best_vert = v
    if best_vert is None:
        return None, None
    return best_vert, best_d2


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


def normalize_angle_pi(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def arc_sweep_2pt(theta_start: float, theta_end: float, major_arc: bool) -> float:
    """Signed sweep from start to end; major_arc selects the longer arc."""
    d = normalize_angle_pi(theta_end - theta_start)
    if not major_arc:
        return d
    if d > 0.0:
        return d - 2.0 * math.pi
    if d < 0.0:
        return d + 2.0 * math.pi
    return 2.0 * math.pi


def arc_sweep_3pt_ordered(theta0: float, theta1: float, theta2: float) -> float:
    """Sweep from point 0 to point 2 that passes through point 1 (pick order)."""
    d02 = normalize_angle_pi(theta2 - theta0)
    d01 = normalize_angle_pi(theta1 - theta0)
    if abs(d02) < 1e-12:
        return 2.0 * math.pi
    if d02 > 0.0:
        on_short = 0.0 <= d01 <= d02
    else:
        on_short = d02 <= d01 <= 0.0
    if on_short:
        return d02
    if d02 > 0.0:
        return d02 - 2.0 * math.pi
    return d02 + 2.0 * math.pi


def arc_sweep_p1_to_p2_toward_bulge(
    p1_w,
    p2_w,
    bulge_w,
    center_w,
    u_axis,
    v_axis,
    radius_w,
    plane_n,
):
    """Signed sweep from p1 to p2 on the circle arc on the same side of the chord as bulge_w."""
    t1 = circle_phase_for_point(center_w, u_axis, v_axis, p1_w)
    t2 = circle_phase_for_point(center_w, u_axis, v_axis, p2_w)
    d_short = arc_sweep_2pt(t1, t2, False)
    d_long = arc_sweep_2pt(t1, t2, True)

    chord = Vector(p2_w) - Vector(p1_w)
    c_len = chord.length
    if c_len < 1e-10:
        return t1, d_short

    mid = (Vector(p1_w) + Vector(p2_w)) * 0.5
    n = Vector(plane_n).normalized()
    bisect = n.cross(chord / c_len)
    if bisect.length_squared < 1e-12:
        return t1, d_short
    bisect.normalize()

    bulge_s = (Vector(bulge_w) - mid).dot(bisect)
    r = float(radius_w)
    u = u_axis.normalized()
    v = v_axis.normalized()

    def arc_midpoint(sweep):
        theta = t1 + sweep * 0.5
        return Vector(center_w) + u * (math.cos(theta) * r) + v * (math.sin(theta) * r)

    mid_short = arc_midpoint(d_short)
    short_s = (mid_short - mid).dot(bisect)
    if abs(bulge_s) < 1e-12:
        return t1, d_short
    if short_s * bulge_s >= 0.0:
        return t1, d_short
    return t1, d_long


def bmesh_append_arc_edges(
    session: dict,
    bm,
    inv_mw,
    center_w,
    u_axis,
    v_axis,
    radius: float,
    theta_start: float,
    sweep: float,
    segments: int,
) -> bool:
    """Open arc polyline: segments edges, segments+1 vertices."""
    n = max(1, int(segments))
    if abs(sweep) < 1e-12:
        return False
    u = u_axis.normalized()
    v = v_axis.normalized()
    r = float(radius)
    ring = []
    for i in range(n + 1):
        t = i / n
        theta = theta_start + sweep * t
        co_w = center_w + u * (math.cos(theta) * r) + v * (math.sin(theta) * r)
        vert = bm.verts.new(inv_mw @ co_w)
        ring.append(vert)
        session['created_vert_indices'].append(vert.index)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    for i in range(n):
        try:
            edge = bm.edges.new((ring[i], ring[i + 1]))
            session['created_edge_keys'].append(bm_edge_key(edge))
        except ValueError:
            pass
    return len(session.get('created_edge_keys', [])) > 0


def view_plane_normal_for_two_points(rv3d, p1_w, p2_w):
    """Plane containing the chord and roughly facing the viewport."""
    chord = p2_w - p1_w
    if chord.length_squared < 1e-12:
        return None
    if rv3d is not None:
        view_z = rv3d.view_rotation @ Vector((0.0, 0.0, 1.0))
        n = chord.cross(view_z)
        if n.length_squared < 1e-12:
            n = chord.cross(Vector((0.0, 1.0, 0.0)))
    else:
        n = chord.cross(Vector((0.0, 0.0, 1.0)))
    if n.length_squared < 1e-12:
        return None
    return n.normalized()


def ray_plane_intersect(ray_o, ray_d, plane_o, plane_n, eps=1e-10):
    """Ray/plane intersection (allows hits behind the ray origin, like fillet/chamfer)."""
    dn = Vector(ray_d)
    if dn.length_squared < eps * eps:
        return None
    dn.normalize()
    n = Vector(plane_n).normalized()
    denom = dn.dot(n)
    if abs(denom) < eps:
        return None
    t = (plane_o - ray_o).dot(n) / denom
    return ray_o + dn * t


def two_point_circle_from_radius(p1_w, p2_w, radius, plane_n, bisect_sign=1.0):
    """Circle through two points with the given radius (>= chord / 2).

    Center lies on the perpendicular bisector; bisect_sign picks the side (+1 / -1).
    Returns dict with center, radius, u, v, plane_n or None.
    """
    chord = p2_w - p1_w
    c_len = chord.length
    if c_len < 1e-10:
        return None
    half = c_len * 0.5
    r_min = half
    radius = max(float(radius), r_min + 1e-9)

    plane_n = Vector(plane_n).normalized()
    chord_dir = chord / c_len
    bisect = plane_n.cross(chord_dir)
    if bisect.length_squared < 1e-12:
        return None
    bisect.normalize()

    h = math.sqrt(max(radius * radius - half * half, 0.0))
    mid = (p1_w + p2_w) * 0.5
    sign = 1.0 if float(bisect_sign) >= 0.0 else -1.0
    center = mid + bisect * (sign * h)

    u = p1_w - center
    if u.length_squared < 1e-12:
        u = chord_dir.copy()
    else:
        u.normalize()
    v = plane_n.cross(u).normalized()
    return {
        'center': center,
        'radius': radius,
        'u': u,
        'v': v,
        'plane_n': plane_n,
        'bisect_sign': sign,
    }


def chord_bisect_axis(p1_w, p2_w, plane_n):
    """Unit vector along the chord perpendicular in plane_n (pick-order independent)."""
    chord = Vector(p2_w) - Vector(p1_w)
    c_len = chord.length
    if c_len < 1e-10:
        return None
    n = Vector(plane_n).normalized()
    bisect = n.cross(chord / c_len)
    if bisect.length_squared < 1e-12:
        return None
    bisect.normalize()
    return bisect


def plane_normal_toward_bulge(p1_w, p2_w, bulge_w, plane_n):
    """Keep plane_n on the cursor plane but flip so (p2-p1)×(bulge-p1) agrees with it."""
    n = Vector(plane_n).normalized()
    ref = (Vector(p2_w) - Vector(p1_w)).cross(Vector(bulge_w) - Vector(p1_w))
    if ref.length_squared > 1e-12 and ref.dot(n) < 0.0:
        n = -n
    return n


def bisect_sign_for_arc_bulge(p1_w, p2_w, bulge_w, plane_n):
    """Center side for two_point_circle_from_radius so the arc bulges toward bulge_w."""
    chord = p2_w - p1_w
    c_len = chord.length
    if c_len < 1e-10:
        return 1.0
    mid = (p1_w + p2_w) * 0.5
    bisect = chord_bisect_axis(p1_w, p2_w, plane_n)
    if bisect is None:
        return 1.0
    bulge_side = 1.0 if (Vector(bulge_w) - mid).dot(bisect) >= 0.0 else -1.0
    return -bulge_side


def two_point_circle_matching_bulge(p1_w, p2_w, radius, plane_n, bulge_hint_w):
    """Circle through p1/p2 at radius; pick the center matching the mouse circumcircle side.

    Two circles share the same radius and endpoints; choose the one whose center
    matches circumcircle(p1, p2, bulge_hint) — same side as the arc under the cursor.
    """
    chord = Vector(p2_w) - Vector(p1_w)
    c_len = chord.length
    if c_len < 1e-10:
        return None
    half = c_len * 0.5
    radius = max(float(radius), half + 1e-9)
    plane_n = Vector(plane_n).normalized()
    bisect = chord_bisect_axis(p1_w, p2_w, plane_n)
    if bisect is None:
        return None
    h = math.sqrt(max(radius * radius - half * half, 0.0))
    mid = (Vector(p1_w) + Vector(p2_w)) * 0.5
    center_a = mid + bisect * h
    center_b = mid - bisect * h

    ref = circumcircle_from_three_points(p1_w, p2_w, bulge_hint_w)
    if ref is not None:
        ref_center = Vector(ref[0])
        if (center_a - ref_center).length_squared <= (center_b - ref_center).length_squared:
            center = center_a
        else:
            center = center_b
    else:
        hint_side = (Vector(bulge_hint_w) - mid).dot(bisect)
        side_a = (center_a - mid).dot(bisect)
        center = center_a if hint_side * side_a < 0.0 else center_b

    u = Vector(p1_w) - center
    if u.length_squared < 1e-12:
        u = chord / c_len
    else:
        u.normalize()
    v = plane_n.cross(u).normalized()
    return {
        'center': center,
        'radius': radius,
        'u': u,
        'v': v,
        'plane_n': plane_n,
    }


def arc_uv_axes_for_bulge(p1_w, p2_w, bulge_w, center_w, plane_n):
    """(u, v) on the work plane: u from center toward p1, v toward the bulge side."""
    u = Vector(p1_w) - Vector(center_w)
    if u.length_squared < 1e-12:
        chord = Vector(p2_w) - Vector(p1_w)
        if chord.length_squared < 1e-12:
            return None, None
        u = Vector(plane_n).cross(chord)
        if u.length_squared < 1e-12:
            return None, None
    u.normalize()
    n = Vector(plane_n).normalized()
    v = n.cross(u)
    if v.length_squared < 1e-12:
        return None, None
    v.normalize()
    if (Vector(bulge_w) - Vector(center_w)).dot(v) < 0.0:
        v = -v
    return u, v


def two_pt_arc_geom_from_bulge(p1_w, p2_w, bulge_w, plane_n):
    """Arc through p1, p2, and bulge_w on the cursor plane (bulge side from plane_n)."""
    plane_n = plane_normal_toward_bulge(p1_w, p2_w, bulge_w, plane_n)
    circle = circumcircle_from_three_points(p1_w, p2_w, bulge_w)
    if circle is None:
        return None
    center_w, radius_w, _u, _v = circle
    u_axis, v_axis = arc_uv_axes_for_bulge(p1_w, p2_w, bulge_w, center_w, plane_n)
    if u_axis is None:
        return None
    t1, sweep = arc_sweep_p1_to_p2_toward_bulge(
        p1_w, p2_w, bulge_w, center_w, u_axis, v_axis, radius_w, plane_n,
    )
    return {
        'center': center_w,
        'radius': radius_w,
        'u': u_axis,
        'v': v_axis,
        'theta_start': t1,
        'sweep': sweep,
    }


def two_pt_arc_frame(p1_w, p2_w, bulge_w, radius, plane_n):
    """Circle at radius through p1/p2; same center side as circumcircle(p1, p2, bulge_w)."""
    plane_n = plane_normal_toward_bulge(p1_w, p2_w, bulge_w, plane_n)
    base = two_point_circle_matching_bulge(p1_w, p2_w, radius, plane_n, bulge_w)
    if base is None:
        return None
    center_w = base['center']
    radius_w = base['radius']
    u_axis, v_axis = arc_uv_axes_for_bulge(p1_w, p2_w, bulge_w, center_w, plane_n)
    if u_axis is None:
        return None
    theta_start, sweep = arc_sweep_p1_to_p2_toward_bulge(
        p1_w, p2_w, bulge_w, center_w, u_axis, v_axis, radius_w, plane_n,
    )
    return {
        'center': center_w,
        'radius': radius_w,
        'u': u_axis,
        'v': v_axis,
        'theta_start': theta_start,
        'sweep': sweep,
    }


def arc_midpoint_world_from_geom(geom):
    """World-space point at the middle of an arc frame dict from two_pt_arc_frame / geom_from_bulge."""
    theta = float(geom['theta_start']) + float(geom['sweep']) * 0.5
    r = float(geom['radius'])
    u = Vector(geom['u']).normalized()
    v = Vector(geom['v']).normalized()
    c = Vector(geom['center'])
    return c + u * (math.cos(theta) * r) + v * (math.sin(theta) * r)


def bulge_point_for_radius(p1_w, p2_w, bulge_hint_w, radius, plane_n):
    """Peak of the arc on the same side of the chord as bulge_hint_w for the given circumradius."""
    chord = Vector(p2_w) - Vector(p1_w)
    c_len = chord.length
    if c_len < 1e-10:
        return None
    half = c_len * 0.5
    radius = max(float(radius), half + 1e-9)
    mid = (Vector(p1_w) + Vector(p2_w)) * 0.5
    plane_n = plane_normal_toward_bulge(p1_w, p2_w, bulge_hint_w, plane_n)
    bisect = chord_bisect_axis(p1_w, p2_w, plane_n)
    if bisect is None:
        return None
    side = 1.0 if (Vector(bulge_hint_w) - mid).dot(bisect) >= 0.0 else -1.0
    apothem = math.sqrt(max(radius * radius - half * half, 0.0))
    sagitta = max(radius - apothem, 1e-9)
    return mid + bisect * (side * sagitta)


def radius_from_plane_hit(p1_w, p2_w, hit_w, plane_n, center_away_from_hit=True):
    """Radius and bisector sign from a mouse hit on the circle plane.

    When center_away_from_hit is True (default), the center lies on the side of the
    chord opposite the hit — the arc bulges toward the cursor.
    """
    chord = p2_w - p1_w
    c_len = chord.length
    if c_len < 1e-10:
        return None, None
    half = c_len * 0.5
    mid = (p1_w + p2_w) * 0.5
    plane_n = Vector(plane_n).normalized()
    chord_dir = chord / c_len
    bisect = plane_n.cross(chord_dir)
    if bisect.length_squared < 1e-12:
        return None, None
    bisect.normalize()
    t = (hit_w - mid).dot(bisect)
    h = abs(t)
    radius = math.sqrt(h * h + half * half)
    hit_side = 1.0 if t >= 0.0 else -1.0
    sign = -hit_side if center_away_from_hit else hit_side
    return max(radius, half), sign


def line_signed_distance(point, origin, direction, plane_n) -> float:
    """Signed perpendicular distance to an infinite line in plane_n's plane."""
    direction = Vector(direction).normalized()
    plane_n = Vector(plane_n).normalized()
    return (Vector(point) - Vector(origin)).cross(direction).dot(plane_n)


def edge_line_on_plane(p0_w, p1_w, plane_n):
    """Unit direction and origin for an edge projected into plane_n (degenerate → None)."""
    plane_n = Vector(plane_n).normalized()
    p0_w = Vector(p0_w)
    p1_w = Vector(p1_w)
    d = p1_w - p0_w
    d -= plane_n * d.dot(plane_n)
    if d.length_squared < 1e-12:
        return None, None
    d.normalize()
    return p0_w, d


def _plane_cross_2d(vec_a, vec_b, plane_n) -> float:
    return Vector(vec_a).cross(Vector(vec_b)).dot(Vector(plane_n).normalized())


def segments_intersection_params_plane(
    p0: Vector,
    p1: Vector,
    q0: Vector,
    q1: Vector,
    plane_n,
    eps: float = 1e-9,
) -> tuple[float, float] | None:
    """Parametric intersection of infinite lines through p0–p1 and q0–q1. Returns (s, t) or None."""
    plane_n = Vector(plane_n).normalized()
    d_a = Vector(p1) - Vector(p0)
    d_b = Vector(q1) - Vector(q0)
    cross_ab = _plane_cross_2d(d_a, d_b, plane_n)
    if abs(cross_ab) < eps * max(d_a.length, d_b.length, 1.0):
        return None
    rhs = Vector(q0) - Vector(p0)
    s_on_a = _plane_cross_2d(rhs, d_b, plane_n) / cross_ab
    t_on_b = _plane_cross_2d(rhs, d_a, plane_n) / cross_ab
    return float(s_on_a), float(t_on_b)


def segments_cross_inside_plane(
    p0: Vector,
    p1: Vector,
    q0: Vector,
    q1: Vector,
    plane_n,
    eps: float = 1e-9,
) -> bool:
    """True when infinite lines through both segments meet strictly inside both."""
    params = segments_intersection_params_plane(p0, p1, q0, q1, plane_n, eps)
    if params is None:
        return False
    s_on_a, t_on_b = params
    d_a = Vector(p1) - Vector(p0)
    d_b = Vector(q1) - Vector(q0)
    tol = max(eps, 1e-8 * max(d_a.length, d_b.length, 1.0))
    return tol < s_on_a < 1.0 - tol and tol < t_on_b < 1.0 - tol


def crossing_endpoint_from_click_plane(
    p0: Vector,
    p1: Vector,
    click: Vector,
    s_intersection: float,
) -> int:
    """Endpoint index for Va when segments cross: fillet opens toward the clicked half."""
    d = Vector(p1) - Vector(p0)
    len_sq = d.length_squared
    if len_sq < 1e-18:
        return 0
    t_click = (Vector(click) - Vector(p0)).dot(d) / len_sq
    if t_click <= s_intersection:
        return 1
    return 0


def tan_tan_side_signs(point, origin_a, dir_a, origin_b, dir_b, plane_n):
    """Which side of each directed line *point* lies on (+1 / -1), or None on a line."""
    plane_n = Vector(plane_n).normalized()
    s1 = line_signed_distance(point, origin_a, dir_a, plane_n)
    s2 = line_signed_distance(point, origin_b, dir_b, plane_n)
    if abs(s1) < 1e-9 or abs(s2) < 1e-9:
        return None
    return (1 if s1 > 0.0 else -1, 1 if s2 > 0.0 else -1)


def tan_tan_oriented_lines(context, mw, edge_a, edge_b, click_a_w=None, click_b_w=None):
    """Edge lines on the cursor plane, oriented like fillet (X + click handling).

    Returns (plane_n, origin_a, dir_a, origin_b, dir_b) or None.
    """
    plane_n, _u, _v = cp.cursor_plane_axes(context)
    plane_n = plane_n.normalized()

    def _proj(co_w):
        return cp.project_onto_cursor_plane(context, co_w)

    a0_w = mw @ edge_a.verts[0].co
    a1_w = mw @ edge_a.verts[1].co
    b0_w = mw @ edge_b.verts[0].co
    b1_w = mw @ edge_b.verts[1].co
    a0, a1 = _proj(a0_w), _proj(a1_w)
    b0, b1 = _proj(b0_w), _proj(b1_w)

    is_crossing = segments_cross_inside_plane(a0, a1, b0, b1, plane_n)
    # Compute intersection params for ALL non-parallel cases — used for X, V/T and L.
    ix_params = segments_intersection_params_plane(a0, a1, b0, b1, plane_n)

    if click_a_w is not None:
        click_a_w = Vector(click_a_w)
        if ix_params is not None:
            click_a_p = cp.project_onto_cursor_plane(context, click_a_w)
            pa = crossing_endpoint_from_click_plane(a0, a1, click_a_p, ix_params[0])
        else:
            pa = (
                0
                if (a0_w - click_a_w).length_squared <= (a1_w - click_a_w).length_squared
                else 1
            )
    else:
        d_a0 = min((a0 - b0).length_squared, (a0 - b1).length_squared)
        d_a1 = min((a1 - b0).length_squared, (a1 - b1).length_squared)
        pa_near = 0 if d_a0 <= d_a1 else 1
        pa = (1 - pa_near) if is_crossing else pa_near

    if click_b_w is not None:
        click_b_w = Vector(click_b_w)
        if ix_params is not None:
            click_b_p = cp.project_onto_cursor_plane(context, click_b_w)
            pb = crossing_endpoint_from_click_plane(b0, b1, click_b_p, ix_params[1])
        else:
            pb = (
                0
                if (b0_w - click_b_w).length_squared <= (b1_w - click_b_w).length_squared
                else 1
            )
    else:
        d_b0 = min((b0 - a0).length_squared, (b0 - a1).length_squared)
        d_b1 = min((b1 - a0).length_squared, (b1 - a1).length_squared)
        pb_near = 0 if d_b0 <= d_b1 else 1
        pb = (1 - pb_near) if is_crossing else pb_near

    va = a0 if pa == 0 else a1
    wa = a1 if pa == 0 else a0
    vb = b0 if pb == 0 else b1
    wb = b1 if pb == 0 else b0
    o1, d1 = edge_line_on_plane(va, wa, plane_n)
    o2, d2 = edge_line_on_plane(vb, wb, plane_n)
    if o1 is None or o2 is None:
        return None
    return plane_n, o1, d1, o2, d2


def _intersect_lines_in_plane(origin_a, dir_a, origin_b, dir_b, plane_n, eps=1e-10):
    dir_a = Vector(dir_a).normalized()
    dir_b = Vector(dir_b).normalized()
    plane_n = Vector(plane_n).normalized()
    denom = dir_a.cross(dir_b).dot(plane_n)
    if abs(denom) < eps:
        return None
    t = (Vector(origin_b) - Vector(origin_a)).cross(dir_b).dot(plane_n) / denom
    return Vector(origin_a) + dir_a * t


def min_radius_circle_tangent_two_lines(origin_a, dir_a, origin_b, dir_b, plane_n) -> float:
    """Smallest radius for a circle tangent to both lines on the plane."""
    plane_n = Vector(plane_n).normalized()
    dir_a = Vector(dir_a).normalized()
    dir_b = Vector(dir_b).normalized()
    if abs(dir_a.cross(dir_b).dot(plane_n)) < 1e-8:
        sep = abs(line_signed_distance(origin_b, origin_a, dir_a, plane_n))
        return sep * 0.5 + 1e-9
    return 1e-9


def circle_tangent_two_lines(
    origin_a,
    dir_a,
    origin_b,
    dir_b,
    plane_n,
    radius,
    hint_w,
    eps=1e-9,
):
    """Circle of given radius tangent to two infinite coplanar lines; hint picks the solution.

    Returns dict center, radius, u, v, plane_n or None.
    """
    plane_n = Vector(plane_n).normalized()
    o1, d1 = Vector(origin_a), Vector(dir_a).normalized()
    o2, d2 = Vector(origin_b), Vector(dir_b).normalized()
    r = max(float(radius), min_radius_circle_tangent_two_lines(o1, d1, o2, d2, plane_n))
    hint_w = Vector(hint_w)
    perp1 = plane_n.cross(d1)
    perp2 = plane_n.cross(d2)
    if perp1.length_squared < 1e-12 or perp2.length_squared < 1e-12:
        return None
    perp1.normalize()
    perp2.normalize()

    parallel = abs(d1.cross(d2).dot(plane_n)) < 1e-8
    if parallel:
        sep = line_signed_distance(o2, o1, d1, plane_n)
        if abs(sep) < 2.0 * r - eps:
            return None
        mid_off = perp1 * (sep * 0.5)
        base = o1 + mid_off
        t = (hint_w - base).dot(d1)
        center = base + d1 * t
    else:
        hint_sides = tan_tan_side_signs(hint_w, o1, d1, o2, d2, plane_n)
        best_center = None
        best_d2 = None
        fallback_center = None
        fallback_d2 = None
        for s1 in (1.0, -1.0):
            for s2 in (1.0, -1.0):
                a1 = o1 + perp1 * (s1 * r)
                a2 = o2 + perp2 * (s2 * r)
                center = _intersect_lines_in_plane(a1, d1, a2, d2, plane_n, eps)
                if center is None:
                    continue
                tol = max(1e-6, r * 0.02)
                d_a = abs(abs(line_signed_distance(center, o1, d1, plane_n)) - r)
                d_b = abs(abs(line_signed_distance(center, o2, d2, plane_n)) - r)
                if d_a > tol or d_b > tol:
                    continue
                hd2 = (center - hint_w).length_squared
                if fallback_d2 is None or hd2 < fallback_d2:
                    fallback_d2 = hd2
                    fallback_center = center
                if hint_sides is not None:
                    center_sides = tan_tan_side_signs(center, o1, d1, o2, d2, plane_n)
                    if center_sides != hint_sides:
                        continue
                if best_d2 is None or hd2 < best_d2:
                    best_d2 = hd2
                    best_center = center
        if best_center is None:
            best_center = fallback_center
        if best_center is None:
            return None
        center = best_center

    u = d1 - plane_n * d1.dot(plane_n)
    if u.length_squared < 1e-12:
        u = perp1.copy()
    else:
        u.normalize()
    v = plane_n.cross(u).normalized()
    return {
        'center': center,
        'radius': r,
        'u': u,
        'v': v,
        'plane_n': plane_n,
    }


def _closest_point_on_infinite_line(point, origin, direction):
    direction = Vector(direction).normalized()
    t = (Vector(point) - Vector(origin)).dot(direction)
    return Vector(origin) + direction * t


def tan_tan_bisector_segments(origin_a, dir_a, origin_b, dir_b, plane_n, span: float = 50.0):
    """Guide segments for angle bisectors (intersecting) or midline (parallel)."""
    plane_n = Vector(plane_n).normalized()
    o1, d1 = Vector(origin_a), Vector(dir_a).normalized()
    o2, d2 = Vector(origin_b), Vector(dir_b).normalized()
    span = max(float(span), 1.0)
    ix = _intersect_lines_in_plane(o1, d1, o2, d2, plane_n)
    if ix is None:
        perp = plane_n.cross(d1)
        if perp.length_squared < 1e-12:
            return []
        perp.normalize()
        sep = line_signed_distance(o2, o1, d1, plane_n)
        mid = o1 + perp * (sep * 0.5)
        return [(mid - d1 * span, mid + d1 * span)]
    u1, u2 = d1, d2
    segments = []
    for comb in (u1 + u2, u1 - u2):
        if comb.length_squared < 1e-12:
            continue
        bdir = comb.normalized()
        segments.append((ix - bdir * span, ix + bdir * span))
    return segments


def _intersect_segment_line_in_plane(p0, p1, line_o, line_d, plane_n, eps=1e-10):
    """Intersection of segment p0–p1 with infinite line (line_o, line_d) in plane_n, or None."""
    p0, p1 = Vector(p0), Vector(p1)
    line_o, line_d = Vector(line_o), Vector(line_d).normalized()
    plane_n = Vector(plane_n).normalized()
    seg = p1 - p0
    if seg.length_squared < eps * eps:
        return None
    denom = seg.cross(line_d).dot(plane_n)
    if abs(denom) < eps:
        return None
    t = (line_o - p0).cross(line_d).dot(plane_n) / denom
    if t < -eps or t > 1.0 + eps:
        return None
    return p0 + seg * max(0.0, min(1.0, t))


def _tan_tan_bisector_rays(origin_a, dir_a, origin_b, dir_b, plane_n):
    """(origin, unit_direction) for each bisector guide ray."""
    plane_n = Vector(plane_n).normalized()
    o1, d1 = Vector(origin_a), Vector(dir_a).normalized()
    o2, d2 = Vector(origin_b), Vector(dir_b).normalized()
    ix = _intersect_lines_in_plane(o1, d1, o2, d2, plane_n)
    if ix is None:
        perp = plane_n.cross(d1)
        if perp.length_squared < 1e-12:
            return []
        perp.normalize()
        sep = line_signed_distance(o2, o1, d1, plane_n)
        mid = o1 + perp * (sep * 0.5)
        return [(mid, d1)]
    rays = []
    for comb in (d1 + d2, d1 - d2):
        if comb.length_squared < 1e-12:
            continue
        rays.append((ix, comb.normalized()))
    return rays


def _dedupe_world_points(points, eps=1e-5):
    unique = []
    eps_sq = float(eps) * float(eps)
    for p in points:
        pv = Vector(p)
        if any((pv - Vector(u)).length_squared < eps_sq for u in unique):
            continue
        unique.append(pv)
    return unique


def point_on_tan_tan_bisector(point, origin_a, dir_a, origin_b, dir_b, plane_n, tol=1e-4) -> bool:
    cp = project_point_to_tan_tan_bisector(
        point, origin_a, dir_a, origin_b, dir_b, plane_n,
    )
    return (Vector(point) - cp).length_squared <= float(tol) * float(tol)


def tan_tan_bisector_snap_points(
    origin_a,
    dir_a,
    origin_b,
    dir_b,
    plane_n,
    edge_segments=None,
):
    """World points on the tan-tan bisector worth snapping to (corners, edge crossings)."""
    plane_n = Vector(plane_n).normalized()
    points = []
    ix = _intersect_lines_in_plane(
        Vector(origin_a), Vector(dir_a).normalized(),
        Vector(origin_b), Vector(dir_b).normalized(),
        plane_n,
    )
    if ix is not None:
        points.append(ix)
    for line_o, line_d in _tan_tan_bisector_rays(origin_a, dir_a, origin_b, dir_b, plane_n):
        if edge_segments:
            for p0, p1 in edge_segments:
                hit = _intersect_segment_line_in_plane(p0, p1, line_o, line_d, plane_n)
                if hit is not None:
                    points.append(hit)
    return _dedupe_world_points(points)


def nearest_world_point_screen(region, rv3d, mouse_xy, points_w, threshold_px=14):
    """Pick closest world point to mouse_xy in screen space within threshold_px."""
    if region is None or rv3d is None or not points_w:
        return None
    best = None
    best_d2 = float(threshold_px) * float(threshold_px)
    mx, my = float(mouse_xy[0]), float(mouse_xy[1])
    for pw in points_w:
        p2d = location_3d_to_region_2d(region, rv3d, Vector(pw))
        if p2d is None:
            continue
        ex, ey = mx - p2d.x, my - p2d.y
        d2 = ex * ex + ey * ey
        if d2 < best_d2:
            best_d2 = d2
            best = Vector(pw)
    return best


def project_point_to_tan_tan_bisector(point, origin_a, dir_a, origin_b, dir_b, plane_n):
    """Closest point on a tan-tan bisector (or parallel midline) to point."""
    point = Vector(point)
    if not tan_tan_bisector_segments(origin_a, dir_a, origin_b, dir_b, plane_n, span=1.0):
        return point
    best = None
    best_d2 = None
    for a, b in tan_tan_bisector_segments(origin_a, dir_a, origin_b, dir_b, plane_n, span=1e6):
        origin = Vector(a)
        direction = (Vector(b) - Vector(a)).normalized()
        if direction.length_squared < 1e-12:
            continue
        cp = _closest_point_on_infinite_line(point, origin, direction)
        d2 = (cp - point).length_squared
        if best_d2 is None or d2 < best_d2:
            best_d2 = d2
            best = cp
    return best if best is not None else point


def tan_tan_nudge_hint(hint_w, origin_a, dir_a, origin_b, dir_b, plane_n, radius_bu: float):
    """If hint sits on the line intersection, offset along the bisector toward a valid wedge."""
    hint_w = Vector(hint_w)
    plane_n = Vector(plane_n).normalized()
    o1, d1 = Vector(origin_a), Vector(dir_a).normalized()
    o2, d2 = Vector(origin_b), Vector(dir_b).normalized()
    ix = _intersect_lines_in_plane(o1, d1, o2, d2, plane_n)
    if ix is None or (hint_w - ix).length > max(float(radius_bu), 1e-6) * 0.25:
        return hint_w
    rays = _tan_tan_bisector_rays(o1, d1, o2, d2, plane_n)
    step = max(float(radius_bu), 1e-6)
    hint_sides = tan_tan_side_signs(hint_w, o1, d1, o2, d2, plane_n)
    for origin, bdir in rays:
        test = origin + bdir * step
        if hint_sides is not None:
            if tan_tan_side_signs(test, o1, d1, o2, d2, plane_n) == hint_sides:
                return test
        else:
            s1 = line_signed_distance(test, o1, d1, plane_n)
            s2 = line_signed_distance(test, o2, d2, plane_n)
            if s1 * s2 > 0.0:
                return test
    if rays:
        origin, bdir = rays[0]
        return origin + bdir * step
    return hint_w


def circle_geom_at_center(center_w, radius_bu, dir_a, plane_n):
    """Circle frame at center with explicit radius (skip tangent distance checks)."""
    plane_n = Vector(plane_n).normalized()
    center_w = Vector(center_w)
    d1 = Vector(dir_a).normalized()
    u = d1 - plane_n * d1.dot(plane_n)
    if u.length_squared < 1e-12:
        return None
    u.normalize()
    v = plane_n.cross(u).normalized()
    r = max(float(radius_bu), 1e-9)
    return {
        'center': center_w,
        'radius': r,
        'u': u,
        'v': v,
        'plane_n': plane_n,
    }


def tan_tan_center_from_hint(hint_w, origin_a, dir_a, origin_b, dir_b, plane_n):
    """Circle center on bisector/midline in the same wedge as hint_w."""
    hint_w = Vector(hint_w)
    plane_n = Vector(plane_n).normalized()
    o1, d1 = Vector(origin_a), Vector(dir_a).normalized()
    o2, d2 = Vector(origin_b), Vector(dir_b).normalized()
    hint_sides = tan_tan_side_signs(hint_w, o1, d1, o2, d2, plane_n)
    candidates = []
    for a, b in tan_tan_bisector_segments(origin_a, dir_a, origin_b, dir_b, plane_n, span=1e6):
        origin = Vector(a)
        direction = (Vector(b) - origin).normalized()
        if direction.length_squared < 1e-12:
            continue
        cp_pt = _closest_point_on_infinite_line(hint_w, origin, direction)
        if hint_sides is not None:
            cp_sides = tan_tan_side_signs(cp_pt, o1, d1, o2, d2, plane_n)
            if cp_sides != hint_sides:
                continue
        candidates.append(cp_pt)
    if candidates:
        return min(candidates, key=lambda c: (c - hint_w).length_squared)
    cp_pt = project_point_to_tan_tan_bisector(hint_w, o1, d1, o2, d2, plane_n)
    if hint_sides is not None:
        cp_sides = tan_tan_side_signs(cp_pt, o1, d1, o2, d2, plane_n)
        if cp_sides != hint_sides:
            return None
    return cp_pt


def tan_tan_circle_geom(
    origin_a,
    dir_a,
    origin_b,
    dir_b,
    plane_n,
    hint_w,
    radius_bu=None,
    center_w=None,
):
    """Tan-tan circle: typed radius + hint, or center from hint / stored center."""
    plane_n = Vector(plane_n).normalized()
    o1, d1 = Vector(origin_a), Vector(dir_a).normalized()
    o2, d2 = Vector(origin_b), Vector(dir_b).normalized()
    hint_w = Vector(hint_w)
    r_min = min_radius_circle_tangent_two_lines(o1, d1, o2, d2, plane_n)

    if radius_bu is not None:
        r = max(float(radius_bu), r_min)
        hint_w = tan_tan_nudge_hint(hint_w, o1, d1, o2, d2, plane_n, r)
        geom = circle_tangent_two_lines(o1, d1, o2, d2, plane_n, r, hint_w)
        if geom is not None:
            return geom
        center = center_on_bisector_for_radius(o1, d1, o2, d2, plane_n, r, hint_w)
        if center is not None:
            geom = circle_geom_at_center(center, r, d1, plane_n)
            if geom is not None:
                return geom
        return None

    if center_w is not None:
        geom = circle_from_center_tangent_two_lines(center_w, o1, d1, o2, d2, plane_n)
        if geom is not None:
            return geom

    center = tan_tan_center_from_hint(hint_w, o1, d1, o2, d2, plane_n)
    if center is None:
        return None
    return circle_from_center_tangent_two_lines(center, o1, d1, o2, d2, plane_n)


def circle_from_center_tangent_two_lines(center_w, origin_a, dir_a, origin_b, dir_b, plane_n):
    """Circle centered at center_w tangent to two lines (radius = perp. distance)."""
    plane_n = Vector(plane_n).normalized()
    center_w = Vector(center_w)
    o1, d1 = Vector(origin_a), Vector(dir_a).normalized()
    o2, d2 = Vector(origin_b), Vector(dir_b).normalized()
    s1 = line_signed_distance(center_w, o1, d1, plane_n)
    s2 = line_signed_distance(center_w, o2, d2, plane_n)
    if abs(s1) < 1e-9 or abs(s2) < 1e-9:
        return None
    r = 0.5 * (abs(s1) + abs(s2))
    if abs(abs(s1) - abs(s2)) > max(1e-6, r * 0.02):
        return None
    r = max(r, 1e-9)
    u = d1 - plane_n * d1.dot(plane_n)
    if u.length_squared < 1e-12:
        u = plane_n.cross(d2)
    if u.length_squared < 1e-12:
        return None
    u.normalize()
    v = plane_n.cross(u).normalized()
    return {
        'center': center_w,
        'radius': r,
        'u': u,
        'v': v,
        'plane_n': plane_n,
    }


def center_on_bisector_for_radius(origin_a, dir_a, origin_b, dir_b, plane_n, radius, hint_w):
    """Point on bisector / midline whose perpendicular distance to the lines equals radius."""
    plane_n = Vector(plane_n).normalized()
    o1, d1 = Vector(origin_a), Vector(dir_a).normalized()
    o2, d2 = Vector(origin_b), Vector(dir_b).normalized()
    r = max(float(radius), 1e-9)
    hint_w = Vector(hint_w)
    parallel = abs(d1.cross(d2).dot(plane_n)) < 1e-6
    ix = _intersect_lines_in_plane(o1, d1, o2, d2, plane_n)
    if parallel or ix is None:
        return None

    cos_a = max(-1.0, min(1.0, d1.dot(d2)))
    half_angle = math.acos(cos_a) * 0.5
    sin_half = math.sin(half_angle)
    if sin_half < 1e-9:
        return None
    dist = r / sin_half
    tol = max(1e-6, r * 0.02)
    hint_sides = tan_tan_side_signs(hint_w, o1, d1, o2, d2, plane_n)
    best = None
    best_d2 = None
    fallback = None
    fallback_d2 = None
    for comb in (d1 + d2, d1 - d2):
        if comb.length_squared < 1e-12:
            continue
        bdir = comb.normalized()
        along = (hint_w - ix).dot(bdir)
        if along >= 0.0:
            cand = ix + bdir * dist
        else:
            cand = ix - bdir * dist
        s1 = line_signed_distance(cand, o1, d1, plane_n)
        s2 = line_signed_distance(cand, o2, d2, plane_n)
        if abs(abs(s1) - r) > tol or abs(abs(s2) - r) > tol:
            continue
        hd2 = (cand - hint_w).length_squared
        if fallback_d2 is None or hd2 < fallback_d2:
            fallback_d2 = hd2
            fallback = cand
        if hint_sides is not None:
            cand_sides = tan_tan_side_signs(cand, o1, d1, o2, d2, plane_n)
            if cand_sides != hint_sides:
                continue
        if best_d2 is None or hd2 < best_d2:
            best_d2 = hd2
            best = cand
    return best if best is not None else fallback


def working_plane_for_three_edges(edge_a, edge_b, edge_c, mw):
    """6-point coplanar working plane from three BMEdges.

    Returns (origin, normal, u_ax, v_ax) or None if not coplanar / collinear.
    """
    pts = []
    for edge in (edge_a, edge_b, edge_c):
        pts.append(mw @ edge.verts[0].co)
        pts.append(mw @ edge.verts[1].co)
    origin = pts[0].copy()
    normal: Vector | None = None
    for i in range(1, len(pts)):
        for j in range(i + 1, len(pts)):
            cross = (pts[i] - origin).cross(pts[j] - origin)
            if cross.length_squared > 1e-14:
                normal = cross.normalized()
                break
        if normal is not None:
            break
    if normal is None:
        return None
    for p in pts:
        if abs((p - origin).dot(normal)) > DRAFT_PLANAR_EPS:
            return None
    u_ax: Vector | None = None
    for i in range(1, len(pts)):
        d = pts[i] - origin
        if d.length_squared > 1e-12:
            u_ax = d.normalized()
            break
    if u_ax is None:
        return None
    v_ax = normal.cross(u_ax).normalized()
    return (origin, normal, u_ax, v_ax)


def _uv_cross_2d(a, b) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _uv_line_from_edge(p0_uv, p1_uv, eps=1e-12):
    dx = p1_uv[0] - p0_uv[0]
    dy = p1_uv[1] - p0_uv[1]
    length = math.hypot(dx, dy)
    if length < eps:
        return None
    return (p0_uv, (dx / length, dy / length))


def _uv_lines_parallel(dir_a, dir_b, eps=1e-9) -> bool:
    return abs(_uv_cross_2d(dir_a, dir_b)) < eps


def _uv_signed_dist(point, origin, direction) -> float:
    px, py = point
    ox, oy = origin
    dx, dy = direction
    return (px - ox) * dy - (py - oy) * dx


def _uv_line_intersect(origin_a, dir_a, origin_b, dir_b, eps=1e-9):
    denom = _uv_cross_2d(dir_a, dir_b)
    if abs(denom) < eps:
        return None
    ox, oy = origin_a
    bx, by = origin_b
    dx, dy = dir_a
    diff_x = bx - ox
    diff_y = by - oy
    t = (diff_x * dir_b[1] - diff_y * dir_b[0]) / denom
    return (ox + dx * t, oy + dy * t)


def _incircle_geom_from_triangle_uv(
    vert_a_uv,
    vert_b_uv,
    vert_c_uv,
    origin_w,
    normal,
    u_ax,
    v_ax,
    eps=1e-9,
):
    ax, ay = vert_a_uv
    bx, by = vert_b_uv
    cx, cy = vert_c_uv
    a_len = math.hypot(bx - cx, by - cy)
    b_len = math.hypot(cx - ax, cy - ay)
    c_len = math.hypot(ax - bx, ay - by)
    perim = a_len + b_len + c_len
    if perim < eps:
        return None
    cross = _uv_cross_2d(
        (bx - ax, by - ay),
        (cx - ax, cy - ay),
    )
    area2 = abs(cross)
    if area2 < eps * perim:
        return None
    s = perim * 0.5
    area = area2 * 0.5
    r = area / s
    if r < eps:
        return None
    ix = (a_len * ax + b_len * bx + c_len * cx) / perim
    iy = (a_len * ay + b_len * by + c_len * cy) / perim
    center_w = cp.from_uv(ix, iy, origin_w, u_ax, v_ax)
    return {
        'center': center_w,
        'radius': max(float(r), 1e-9),
        'u': u_ax.copy(),
        'v': v_ax.copy(),
        'plane_n': normal.copy(),
    }


def _incircle_geom_two_parallel_uv(lines, origin_w, normal, u_ax, v_ax, eps=1e-9):
    """Incircle when two of three infinite edge lines are parallel (wedge / strip)."""
    parallel_pairs = []
    for i in range(3):
        for j in range(i + 1, 3):
            if _uv_lines_parallel(lines[i][1], lines[j][1], eps):
                parallel_pairs.append((i, j))
    if len(parallel_pairs) != 1:
        return None
    i_par, j_par = parallel_pairs[0]
    k = 3 - i_par - j_par
    o0, d0 = lines[i_par]
    o1, _d1 = lines[j_par]
    o2, d2 = lines[k]
    perp_dist = _uv_signed_dist(o1, o0, d0)
    if abs(perp_dist) < eps:
        return None
    r = abs(perp_dist) * 0.5
    nx = -d0[1]
    ny = d0[0]
    n_len = math.hypot(nx, ny)
    if n_len < eps:
        return None
    nx /= n_len
    ny /= n_len
    mid_o = (o0[0] + nx * perp_dist * 0.5, o0[1] + ny * perp_dist * 0.5)

    def center_at_t(t_val: float):
        return (mid_o[0] + d0[0] * t_val, mid_o[1] + d0[1] * t_val)

    def dist_err(t_val: float) -> float:
        c = center_at_t(t_val)
        return abs(abs(_uv_signed_dist(c, o2, d2)) - r)

    t_candidates = [0.0]
    denom = _uv_cross_2d(d0, d2)
    if abs(denom) > eps:
        for sign in (1.0, -1.0):
            offset = sign * r
            ox, oy = o2
            ox2 = ox + (-d2[1]) * offset / max(math.hypot(d2[0], d2[1]), eps)
            oy2 = oy + (d2[0]) * offset / max(math.hypot(d2[0], d2[1]), eps)
            hit = _uv_line_intersect(mid_o, d0, (ox2, oy2), d2, eps)
            if hit is not None:
                t_candidates.append(
                    (hit[0] - mid_o[0]) * d0[0] + (hit[1] - mid_o[1]) * d0[1],
                )

    best_center = None
    best_err = None
    for t_val in t_candidates:
        c = center_at_t(t_val)
        err = dist_err(t_val)
        d0s = _uv_signed_dist(c, o0, d0)
        d1s = _uv_signed_dist(c, o1, d0)
        if d0s * d1s >= -eps:
            continue
        if best_err is None or err < best_err:
            best_err = err
            best_center = c
    if best_center is None or best_err is None or best_err > max(1e-6, r * 0.05):
        return None
    center_w = cp.from_uv(best_center[0], best_center[1], origin_w, u_ax, v_ax)
    return {
        'center': center_w,
        'radius': max(float(r), 1e-9),
        'u': u_ax.copy(),
        'v': v_ax.copy(),
        'plane_n': normal.copy(),
    }


def triangle_incircle_from_three_edges(edge_a, edge_b, edge_c, mw, eps=1e-9):
    """Incircle tangent to three infinite edge lines in their common plane.

    Returns geom dict (center, radius, u, v, plane_n) or
    {'invalid': True, 'reason': str}.
    """
    plane = working_plane_for_three_edges(edge_a, edge_b, edge_c, mw)
    if plane is None:
        return {'invalid': True, 'reason': 'Edges are not coplanar or are degenerate'}

    origin_w, normal, u_ax, v_ax = plane
    edges = (edge_a, edge_b, edge_c)
    lines_uv = []
    for edge in edges:
        p0_w = mw @ edge.verts[0].co
        p1_w = mw @ edge.verts[1].co
        p0_uv = cp.to_uv(p0_w, origin_w, u_ax, v_ax)
        p1_uv = cp.to_uv(p1_w, origin_w, u_ax, v_ax)
        line = _uv_line_from_edge(p0_uv, p1_uv, eps)
        if line is None:
            return {'invalid': True, 'reason': 'One or more edges are too short'}
        lines_uv.append(line)

    parallel_count = sum(
        1
        for i in range(3)
        for j in range(i + 1, 3)
        if _uv_lines_parallel(lines_uv[i][1], lines_uv[j][1], eps)
    )
    if parallel_count >= 3:
        return {'invalid': True, 'reason': 'All three edges are parallel'}

    if parallel_count >= 1:
        geom = _incircle_geom_two_parallel_uv(
            lines_uv, origin_w, normal, u_ax, v_ax, eps,
        )
        if geom is None:
            return {'invalid': True, 'reason': 'Could not place incircle (parallel edges)'}
        return geom

    verts = []
    for i in range(3):
        j = (i + 1) % 3
        vert = _uv_line_intersect(
            lines_uv[i][0], lines_uv[i][1],
            lines_uv[j][0], lines_uv[j][1],
            eps,
        )
        if vert is None:
            return {'invalid': True, 'reason': 'Edge lines do not form a triangle'}
        verts.append(vert)

    geom = _incircle_geom_from_triangle_uv(
        verts[0], verts[1], verts[2],
        origin_w, normal, u_ax, v_ax, eps,
    )
    if geom is None:
        return {'invalid': True, 'reason': 'Triangle is degenerate (zero area)'}
    return geom
