"""2D / plane geometry helpers and BMesh apply logic for fillet / chamfer.

Shared by operators/fillet_chamfer.py (operator) and operators/angle_rays.py
(preview radius estimation). Nothing in here registers Blender classes.
"""
import math
import bmesh
from mathutils import Vector

from . import cursor_plane as cp
from . import edit_mesh_helpers as emh


_EPS = emh.DRAFT_EPS
# Safety margin so clamped tangent point never coincides exactly with Wa/Wb.
_CLAMP_MARGIN = 1.0 - 1e-4


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _cross_2d(a: Vector, b: Vector) -> float:
    return a.x * b.y - a.y * b.x


def _perp_2d(v: Vector) -> Vector:
    return Vector((-v.y, v.x))


def _segment_intersection_params_uv(
    a0_uv: Vector, a1_uv: Vector, b0_uv: Vector, b1_uv: Vector,
) -> tuple[float, float] | None:
    """Intersection of infinite lines through both segments in UV. Returns (s_on_a, t_on_b)."""
    d_a = a1_uv - a0_uv
    d_b = b1_uv - b0_uv
    cross_ab = _cross_2d(d_a, d_b)
    if abs(cross_ab) < 1e-9 * max(d_a.length, d_b.length, 1.0):
        return None
    rhs = b0_uv - a0_uv
    s_on_a = _cross_2d(rhs, d_b) / cross_ab
    t_on_b = _cross_2d(rhs, d_a) / cross_ab
    return float(s_on_a), float(t_on_b)


def _intersection_inside_both_segments(
    a0_uv: Vector, a1_uv: Vector, b0_uv: Vector, b1_uv: Vector,
) -> bool:
    """True iff infinite lines through A and B meet strictly inside BOTH
    finite segments (proper X; not touching at an endpoint only).
    """
    params = _segment_intersection_params_uv(a0_uv, a1_uv, b0_uv, b1_uv)
    if params is None:
        return False
    s_on_a, t_on_b = params
    d_a = a1_uv - a0_uv
    d_b = b1_uv - b0_uv
    tol = max(_EPS, 1e-8 * max(d_a.length, d_b.length, 1.0))
    return (
        tol < s_on_a < 1.0 - tol and tol < t_on_b < 1.0 - tol
    )


def _crossing_va_endpoint_uv(
    a0_uv: Vector,
    a1_uv: Vector,
    click_uv: Vector,
    s_intersection: float,
) -> int:
    """Endpoint index for Va when segments cross: fillet opens toward the clicked half."""
    d = a1_uv - a0_uv
    len_sq = d.length_squared
    if len_sq < 1e-18:
        return 0
    t_click = (click_uv - a0_uv).dot(d) / len_sq
    # Click on the a0 side of the intersection -> Va is a1 (rays aim toward a0).
    if t_click <= s_intersection:
        return 1
    return 0


def _classify_pair(edge_a, edge_b, mw, click_a_w=None, click_b_w=None):
    """Return per-edge endpoint roles in 2D working-plane coords.

    *click_a_w* / *click_b_w*: world clicks. Nearer endpoint becomes Va/Vb (L/V).
    When finite segments properly cross (X), the click's position along each edge
    relative to the intersection picks the fillet quadrant.

    Returns a dict with keys:
        'plane', 'Va_uv', 'Wa_uv', 'Vb_uv', 'Wb_uv',
        'va_is_v0_in_a', 'vb_is_v0_in_b'
    or None if edges are not coplanar.
    """
    plane = emh.working_plane_for_edges(edge_a, edge_b, mw)
    if plane is None:
        return None
    origin, normal, u_ax, v_ax = plane

    a0_w = mw @ edge_a.verts[0].co
    a1_w = mw @ edge_a.verts[1].co
    b0_w = mw @ edge_b.verts[0].co
    b1_w = mw @ edge_b.verts[1].co

    a0 = Vector(cp.to_uv(a0_w, origin, u_ax, v_ax))
    a1 = Vector(cp.to_uv(a1_w, origin, u_ax, v_ax))
    b0 = Vector(cp.to_uv(b0_w, origin, u_ax, v_ax))
    b1 = Vector(cp.to_uv(b1_w, origin, u_ax, v_ax))

    is_crossing = _intersection_inside_both_segments(a0, a1, b0, b1)
    # Compute intersection params for ALL non-parallel cases — used for both X and V/T.
    ix_params = _segment_intersection_params_uv(a0, a1, b0, b1)

    if click_a_w is not None:
        if ix_params is not None:
            # Use param-based side: compare click position along edge vs intersection param.
            # Works for X, V, T and L — parallel (ix_params=None) falls through to distance.
            click_a_uv = Vector(cp.to_uv(Vector(click_a_w), origin, u_ax, v_ax))
            pa = _crossing_va_endpoint_uv(a0, a1, click_a_uv, ix_params[0])
        else:
            pa = (
                0
                if (a0_w - click_a_w).length_squared <= (a1_w - click_a_w).length_squared
                else 1
            )
    else:
        d_a0 = min((a0_w - b0_w).length_squared, (a0_w - b1_w).length_squared)
        d_a1 = min((a1_w - b0_w).length_squared, (a1_w - b1_w).length_squared)
        pa_near = 0 if d_a0 <= d_a1 else 1
        pa = (1 - pa_near) if is_crossing else pa_near

    if click_b_w is not None:
        if ix_params is not None:
            click_b_uv = Vector(cp.to_uv(Vector(click_b_w), origin, u_ax, v_ax))
            pb = _crossing_va_endpoint_uv(b0, b1, click_b_uv, ix_params[1])
        else:
            pb = (
                0
                if (b0_w - click_b_w).length_squared <= (b1_w - click_b_w).length_squared
                else 1
            )
    else:
        d_b0 = min((b0_w - a0_w).length_squared, (b0_w - a1_w).length_squared)
        d_b1 = min((b1_w - a0_w).length_squared, (b1_w - a1_w).length_squared)
        pb_near = 0 if d_b0 <= d_b1 else 1
        pb = (1 - pb_near) if is_crossing else pb_near

    Va = a0 if pa == 0 else a1
    Wa = a1 if pa == 0 else a0
    Vb = b0 if pb == 0 else b1
    Wb = b1 if pb == 0 else b0
    return {
        'plane': plane,
        'Va_uv': Va, 'Wa_uv': Wa, 'Vb_uv': Vb, 'Wb_uv': Wb,
        'va_is_v0_in_a': pa == 0,
        'vb_is_v0_in_b': pb == 0,
    }


def _ray_plane_intersect(
    ray_orig: Vector,
    ray_dir: Vector,
    plane_pt: Vector,
    plane_n: Vector,
) -> Vector | None:
    dn = ray_dir.normalized()
    n = plane_n.normalized()
    denom = dn.dot(n)
    if abs(denom) < 1e-12:
        return None
    t = (plane_pt - ray_orig).dot(n) / denom
    return ray_orig + dn * t


def _parallel_perp_geometry(Va: Vector, Wa: Vector, Vb: Vector, Wb: Vector) -> dict:
    """Canonical bridge from rail A toward rail B: TB = TA + perp_dir * D (unique shortest span).

    Negating ``perp_dir`` would move TB off the finite parallel rail."""
    dA_vec = Wa - Va
    la = dA_vec.length
    if la < 1e-12:
        return {'invalid': True, 'reason': 'Zero-length edge'}
    dA_unit = dA_vec / la
    perpA = _perp_2d(dA_unit)
    rel = Vb - Va
    perp_signed = rel.dot(perpA)
    dist = abs(perp_signed)
    if dist < _EPS:
        return {'invalid': True, 'reason': 'Edges coincident'}
    perp_dir = perpA if perp_signed > 0 else -perpA
    return {
        'dA_unit': dA_unit,
        'LA': float(la),
        'perp_dir': perp_dir,
        'D': float(dist),
        'radius_eff': float(dist * 0.5),
    }


def _parallel_proj_feasible_range(
    Va: Vector,
    Wa: Vector,
    Vb: Vector,
    Wb: Vector,
    dA_unit: Vector,
    perp_dir: Vector,
    dist: float,
) -> tuple[float, float] | None:
    """Scalar ``proj`` on edge A such that TA = Va + proj*dA_unit and TB on segment B.

    Used to clamp default chord position so both tangent points stay on the segments.
    """
    la = float((Wa - Va).length)
    dB = Wb - Vb
    lb_sq = float(dB.length_squared)
    if la < 1e-12 or lb_sq < 1e-12:
        return None
    frac_tol = max(_EPS, 1e-10 * max(1.0, la, math.sqrt(lb_sq)))
    lo_a = 0.0
    hi_a = la
    b_lo = -frac_tol
    b_hi = 1.0 + frac_tol
    c_vec = Va - Vb + perp_dir * dist
    coef0 = float(c_vec.dot(dB) / lb_sq)
    coef1 = float(dA_unit.dot(dB) / lb_sq)
    if abs(coef1) < 1e-15:
        if not (b_lo <= coef0 <= b_hi):
            return None
        return (lo_a, hi_a)
    j_lo = (b_lo - coef0) / coef1
    j_hi = (b_hi - coef0) / coef1
    if j_lo > j_hi:
        j_lo, j_hi = j_hi, j_lo
    lo = max(lo_a, j_lo)
    hi = min(hi_a, j_hi)
    if lo > hi + 1e-12 * max(la, 1.0):
        return None
    return (lo, hi)


def compute_fillet_data(
    edge_a,
    edge_b,
    mw,
    radius: float,
    segments: int,
    click_a_w=None,
    click_b_w=None,
):
    """Compute geometry for preview and apply.

    radius == 0  →  mode='CORNER': extend both edges to apex and weld.
    radius  > 0  →  mode='ARC': standard fillet/chamfer arc.  Radius is
                     clamped so tangent points stay within the outer vertices.
                     s_TA / s_TB < 0 means auto-extend (V-shape, small r).

    Return dict always includes 'apex_w', 'bis_unit_w', 'sin_half_angle' for
    the bisector-projection radius method, even in CORNER mode.
    Parallel edges omit bisector keys (fixed radius = D/2).
    """
    if edge_a is edge_b or segments < 1:
        return {'invalid': True, 'reason': 'Invalid input'}

    info = _classify_pair(edge_a, edge_b, mw, click_a_w, click_b_w)
    if info is None:
        return {'invalid': True, 'reason': 'Edges not coplanar'}
    origin, _normal, u_ax, v_ax = info['plane']
    Va = info['Va_uv']
    Wa = info['Wa_uv']
    Vb = info['Vb_uv']
    Wb = info['Wb_uv']

    dA = Wa - Va
    dB = Wb - Vb
    if dA.length_squared < 1e-12 or dB.length_squared < 1e-12:
        return {'invalid': True, 'reason': 'Zero-length edge'}

    cross_2d = _cross_2d(dA, dB)
    parallel = abs(cross_2d) < 1e-9 * max(dA.length, dB.length, 1.0)

    # -------------------------------------------------------------------
    # Shared geometry for CORNER and ARC modes (non-parallel)
    # -------------------------------------------------------------------
    if not parallel:
        if abs(cross_2d) < 1e-18:
            return {'invalid': True, 'reason': 'Degenerate geometry'}
        rhs = Vb - Va
        s_apex = (rhs.x * dB.y - rhs.y * dB.x) / cross_2d
        C_uv = Va + dA * s_apex
        apex_w = cp.from_uv(C_uv.x, C_uv.y, origin, u_ax, v_ax)

        e_A = Wa - C_uv
        e_B = Wb - C_uv
        if e_A.length_squared < 1e-12 or e_B.length_squared < 1e-12:
            return {'invalid': True, 'reason': 'Degenerate corner'}
        e_A_unit = e_A.normalized()
        e_B_unit = e_B.normalized()

        cos_full = max(-1.0, min(1.0, e_A_unit.dot(e_B_unit)))
        full_angle = math.acos(cos_full)
        if full_angle < 1e-4 or abs(math.pi - full_angle) < 1e-4:
            return {'invalid': True, 'reason': 'Edges nearly collinear'}
        half_angle = full_angle * 0.5
        sin_h = math.sin(half_angle)

        bis = e_A_unit + e_B_unit
        if bis.length_squared < 1e-12:
            return {'invalid': True, 'reason': 'Edges nearly collinear'}
        bis_unit = bis.normalized()
        # Bisector in world space: bis_unit is in UV plane, convert via axes.
        bis_unit_w = (bis_unit.x * u_ax + bis_unit.y * v_ax).normalized()

        # CORNER mode (r == 0)
        if radius <= _EPS:
            arm_a_w = (e_A_unit.x * u_ax + e_A_unit.y * v_ax).normalized()
            arm_b_w = (e_B_unit.x * u_ax + e_B_unit.y * v_ax).normalized()
            return {
                'invalid': False,
                'mode': 'CORNER',
                'apex_w': apex_w,
                'arm_a_w': arm_a_w,
                'arm_b_w': arm_b_w,
                'plane_normal_w': _normal.copy(),
                'bis_unit_w': bis_unit_w,
                'sin_half_angle': sin_h,
                'radius': 0.0,
                'va_is_v0_in_a': info['va_is_v0_in_a'],
                'vb_is_v0_in_b': info['vb_is_v0_in_b'],
            }

        # ARC mode: clamp radius to outer vertices.
        t_dist_max = min(e_A.length, e_B.length) * _CLAMP_MARGIN
        t_dist = radius / math.tan(half_angle)
        if t_dist > t_dist_max:
            t_dist = max(t_dist_max, _EPS)
        radius = t_dist * math.tan(half_angle)

        TA_uv = C_uv + e_A_unit * t_dist
        TB_uv = C_uv + e_B_unit * t_dist
        center_uv = C_uv + bis_unit * (radius / sin_h)

        s_TA = (TA_uv - Va).dot(dA) / dA.length_squared
        s_TB = (TB_uv - Vb).dot(dB) / dB.length_squared

        ang_a = math.atan2(TA_uv.y - center_uv.y, TA_uv.x - center_uv.x)
        ang_b = math.atan2(TB_uv.y - center_uv.y, TB_uv.x - center_uv.x)
        delta = ang_b - ang_a
        while delta > math.pi:
            delta -= 2 * math.pi
        while delta < -math.pi:
            delta += 2 * math.pi
        if abs(delta) < 1e-6:
            return {'invalid': True, 'reason': 'Degenerate arc'}

        arc_points_uv = []
        for i in range(segments + 1):
            t = i / segments
            ang = ang_a + delta * t
            arc_points_uv.append(
                center_uv + Vector((math.cos(ang) * radius, math.sin(ang) * radius))
            )

        arc_points_w = [cp.from_uv(p.x, p.y, origin, u_ax, v_ax) for p in arc_points_uv]
        TA_w = cp.from_uv(TA_uv.x, TA_uv.y, origin, u_ax, v_ax)
        TB_w = cp.from_uv(TB_uv.x, TB_uv.y, origin, u_ax, v_ax)
        center_w = cp.from_uv(center_uv.x, center_uv.y, origin, u_ax, v_ax)

        return {
            'invalid': False,
            'mode': 'ARC',
            'parallel': False,
            's_TA': float(s_TA),
            's_TB': float(s_TB),
            'TA_w': TA_w,
            'TB_w': TB_w,
            'center_w': center_w,
            'arc_points_w': arc_points_w,
            'apex_w': apex_w,
            'bis_unit_w': bis_unit_w,
            'sin_half_angle': sin_h,
            'radius': radius,
            'va_is_v0_in_a': info['va_is_v0_in_a'],
            'vb_is_v0_in_b': info['vb_is_v0_in_b'],
        }

    # -------------------------------------------------------------------
    # Parallel edges — fixed semicircle; bulge toward (Va+Vb)/2 relative to chord
    # -------------------------------------------------------------------
    geo = _parallel_perp_geometry(Va, Wa, Vb, Wb)
    if geo.get('invalid'):
        return {'invalid': True, 'reason': geo['reason']}
    dA_unit = geo['dA_unit']
    perp_dir = geo['perp_dir']
    dist_para = geo['D']
    radius_eff = geo['radius_eff']
    rng = _parallel_proj_feasible_range(
        Va, Wa, Vb, Wb, dA_unit, perp_dir, dist_para,
    )
    if rng is None:
        return {'invalid': True, 'reason': 'Cannot place semicircle on edges'}
    lo_p, hi_p = rng
    mid = (Va + Vb) * 0.5
    mid_proj = float((mid - Va).dot(dA_unit))
    proj = min(max(mid_proj, lo_p), hi_p)
    TA_uv = Va + dA_unit * proj
    TB_uv = TA_uv + perp_dir * dist_para
    center_uv = TA_uv + perp_dir * radius_eff
    s_TA = proj / dA.length
    dB_wb = Wb - Vb
    s_TB = (TB_uv - Vb).dot(dB_wb) / dB_wb.length_squared
    para_tol = max(_EPS, 1e-10 * max(1.0, dA.length, dB_wb.length))
    if not (
        -para_tol <= s_TA <= 1.0 + para_tol
        and -para_tol <= s_TB <= 1.0 + para_tol
    ):
        return {'invalid': True, 'reason': 'Cannot place semicircle on edges'}

    ang_a = math.atan2(TA_uv.y - center_uv.y, TA_uv.x - center_uv.x)
    chord_vec = TB_uv - TA_uv
    if chord_vec.length_squared < 1e-18:
        return {'invalid': True, 'reason': 'Degenerate chord'}
    # Semicircle half: same side of chord as the click-near corner side of the strip.
    # corner_mid often lies ON chord (e.g. both Va,Vb left, chord vertical at left) so
    # cross(chord, corner_mid - TA) == 0 and tie-breaks pick the inward semicircle.
    # (Va+Vb)-(Wa+Wb) is along the rail toward corners, never parallel to chord.
    corner_mid = (Va + Vb) * 0.5
    bulge_mid_ang_pos = ang_a + math.pi * 0.5
    bulge_mid_ang_neg = ang_a - math.pi * 0.5
    p_pos = center_uv + Vector(
        (math.cos(bulge_mid_ang_pos) * radius_eff, math.sin(bulge_mid_ang_pos) * radius_eff)
    )
    p_neg = center_uv + Vector(
        (math.cos(bulge_mid_ang_neg) * radius_eff, math.sin(bulge_mid_ang_neg) * radius_eff)
    )
    chord_side_tol = max(1e-18, 1e-12 * chord_vec.length * max(corner_mid.length, TA_uv.length, 1.0))
    ref_side = float(_cross_2d(chord_vec, (Va + Vb) - (Wa + Wb)))
    cs = ref_side
    if abs(cs) < chord_side_tol:
        cs = float(_cross_2d(chord_vec, corner_mid - TA_uv))
    if abs(cs) < chord_side_tol:
        cs = float(_cross_2d(chord_vec, Va - TA_uv))
    sp = float(_cross_2d(chord_vec, p_pos - TA_uv))
    sn = float(_cross_2d(chord_vec, p_neg - TA_uv))
    if cs * sp > 0:
        arc_sign = 1
    elif cs * sn > 0:
        arc_sign = -1
    else:
        arc_sign = 1 if abs(sp) >= abs(sn) else -1
    arc_delta = math.pi * arc_sign
    arc_points_uv = []
    for i in range(segments + 1):
        t = i / segments
        ang = ang_a + arc_delta * t
        arc_points_uv.append(
            center_uv + Vector((math.cos(ang) * radius_eff, math.sin(ang) * radius_eff))
        )

    arc_points_w = [cp.from_uv(p.x, p.y, origin, u_ax, v_ax) for p in arc_points_uv]
    TA_w = cp.from_uv(TA_uv.x, TA_uv.y, origin, u_ax, v_ax)
    TB_w = cp.from_uv(TB_uv.x, TB_uv.y, origin, u_ax, v_ax)

    return {
        'invalid': False,
        'mode': 'ARC',
        'parallel': True,
        's_TA': float(s_TA),
        's_TB': float(s_TB),
        'TA_w': TA_w,
        'TB_w': TB_w,
        'arc_points_w': arc_points_w,
        'radius': radius_eff,
        'va_is_v0_in_a': info['va_is_v0_in_a'],
        'vb_is_v0_in_b': info['vb_is_v0_in_b'],
    }


# ---------------------------------------------------------------------------
# BMesh apply helpers
# ---------------------------------------------------------------------------

def _ensure_vertex_at_apex_on_edge(bm, edge, apex_w, mw):
    """Move or split edge so a vertex lands exactly at apex_w.

    t <= 0: move v0 toward apex (extend past v0).
    t >= 1: move v1.
    else:   subdivide at apex.
    Returns the BMVert at apex_w, or None on failure.
    """
    inv = mw.inverted_safe()
    apex_local = inv @ apex_w
    v0, v1 = edge.verts[0], edge.verts[1]
    a_w = mw @ v0.co
    b_w = mw @ v1.co
    d_w = b_w - a_w
    len2 = d_w.length_squared
    if len2 < 1e-18:
        return None
    t = float((apex_w - a_w).dot(d_w) / len2)
    seg_len = math.sqrt(len2)
    rtol = max(1e-10, min(seg_len * 1e-9, 1e-4))

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    if t <= rtol:
        v0.co = apex_local
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        return v0
    if t >= 1.0 - rtol:
        v1.co = apex_local
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        return v1

    fac = float(max(_EPS, min(1.0 - _EPS, t)))
    try:
        _frag, new_v = emh.bmesh_edge_split_normalized(edge, v0, fac)
    except (RuntimeError, ValueError, ReferenceError):
        return None
    new_v.co = apex_local
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    return new_v


def _move_edge_endpoint_world(bm, edge, target_world, mw, va_is_v0_in_edge: bool):
    """Move the corner-side vertex (Va) to target_world (auto-extend)."""
    inv = mw.inverted_safe()
    corner_v = edge.verts[0] if va_is_v0_in_edge else edge.verts[1]
    corner_v.co = inv @ target_world
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    return corner_v


def _split_at_world(bm, edge, point_world, mw, va_is_v0_in_edge: bool):
    """Split edge at point_world; remove the Va-side fragment. Returns new_vert."""
    inv = mw.inverted_safe()
    point_local = inv @ point_world
    v0 = edge.verts[0]
    v1 = edge.verts[1]
    a_w = mw @ v0.co
    b_w = mw @ v1.co
    seg = b_w - a_w
    seg_len_sq = seg.length_squared
    if seg_len_sq < 1e-12:
        return None
    fac = (point_world - a_w).dot(seg) / seg_len_sq
    fac = max(_EPS, min(1.0 - _EPS, fac))

    try:
        _frag, new_vert = emh.bmesh_edge_split_normalized(edge, v0, fac)
    except (RuntimeError, ValueError):
        return None
    new_vert.co = point_local
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    corner_v = v0 if va_is_v0_in_edge else v1
    edge_to_remove = None
    try:
        for ed in tuple(new_vert.link_edges):
            if not ed.is_valid:
                continue
            if ed.other_vert(new_vert) == corner_v:
                edge_to_remove = ed
                break
    except ReferenceError:
        return None

    if edge_to_remove is None:
        return None

    try:
        bm.edges.remove(edge_to_remove)
    except (ValueError, ReferenceError):
        return None
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    if corner_v.is_valid and len(corner_v.link_edges) == 0:
        try:
            bm.verts.remove(corner_v)
        except (ValueError, ReferenceError):
            pass
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
    return new_vert


def _apply_corner(bm, edge_a, edge_b, data, mw) -> bool:
    """Extend/split both edges to the apex and weld the corner vertices."""
    apex_w = data['apex_w']
    eb_key = emh.bm_edge_key(edge_b)

    va = _ensure_vertex_at_apex_on_edge(bm, edge_a, apex_w, mw)
    if va is None:
        return False

    eb = emh.bm_edge_from_key(bm, eb_key)
    if eb is None:
        return False
    vb = _ensure_vertex_at_apex_on_edge(bm, eb, apex_w, mw)
    if vb is None:
        return False

    inv = mw.inverted_safe()
    apex_local = inv @ apex_w
    va.co = apex_local
    vb.co = apex_local
    if va is vb:
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        return True

    try:
        bmesh.ops.pointmerge(bm, verts=[va, vb], merge_co=apex_local)
    except (ReferenceError, TypeError, ValueError):
        return False

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    return True


def apply_arc_only(bm, data, mw) -> bool:
    """Insert arc as new floating edges without modifying source edges."""
    if data.get('mode') == 'CORNER':
        apex_w = data.get('apex_w')
        if apex_w is None:
            return False
        bm.verts.new(mw.inverted_safe() @ apex_w)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        return True

    arc_w = data.get('arc_points_w')
    if not arc_w or len(arc_w) < 2:
        return False
    inv = mw.inverted_safe()
    verts = [bm.verts.new(inv @ point_w) for point_w in arc_w]
    for i in range(len(verts) - 1):
        try:
            bm.edges.new((verts[i], verts[i + 1]))
        except ValueError:
            return False
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    return True


def _apply_arc(bm, edge_a, edge_b, data, mw) -> bool:
    """Apply fillet/chamfer: trim or extend each edge to the tangent point,
    then stitch arc vertices between them.
    """
    if data.get('mode') == 'CORNER':
        return _apply_corner(bm, edge_a, edge_b, data, mw)

    arc_w = data.get('arc_points_w')
    if not arc_w or len(arc_w) < 2:
        return False

    inv = mw.inverted_safe()

    s_TA = data['s_TA']
    if _EPS < s_TA < 1.0 - _EPS:
        new_a = _split_at_world(bm, edge_a, data['TA_w'], mw, data['va_is_v0_in_a'])
    else:
        new_a = _move_edge_endpoint_world(bm, edge_a, data['TA_w'], mw, data['va_is_v0_in_a'])
    if new_a is None:
        return False

    s_TB = data['s_TB']
    if _EPS < s_TB < 1.0 - _EPS:
        new_b = _split_at_world(bm, edge_b, data['TB_w'], mw, data['vb_is_v0_in_b'])
    else:
        new_b = _move_edge_endpoint_world(bm, edge_b, data['TB_w'], mw, data['vb_is_v0_in_b'])
    if new_b is None:
        return False

    prev = new_a
    for i in range(1, len(arc_w) - 1):
        v_mid = bm.verts.new(inv @ arc_w[i])
        bm.edges.new((prev, v_mid))
        prev = v_mid
    if prev is not new_b:
        try:
            bm.edges.new((prev, new_b))
        except ValueError:
            pass
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    return True


def avg_edge_length(edge_a, edge_b, mw) -> float:
    a0 = mw @ edge_a.verts[0].co
    a1 = mw @ edge_a.verts[1].co
    b0 = mw @ edge_b.verts[0].co
    b1 = mw @ edge_b.verts[1].co
    return ((a1 - a0).length + (b1 - b0).length) * 0.5
