"""Modal operator: Fillet/Chamfer between two mesh edges (one tool).

Workflow:
- All selection is cleared when the tool starts.
- Click first edge (click position fixes the corner-side vertex Va on edge A).
- Click second edge (click position fixes Vb on edge B).
- Move the mouse to size the radius — stable bisector-projection method.
  Radius is clamped so neither tangent point exceeds the outer vertex.
  Wheel adjusts segment count (1 = chamfer).
  Type a number and ENTER to set radius precisely; ENTER or LMB applies.
  ESC clears typed buffer or exits. RMB clears last pick.

Corner selection is derived purely from the two click positions — no separate
quadrant UI needed. The four geometric cases are handled automatically:
  1. Shared vertex (L): Va==Vb, standard arc, shared vertex removed.
  2. Not touching (V): Va extended toward apex if radius small, else split.
  3. Crossing (X): click near an endpoint trims the FAR half (opposite quadrant);
     L/V/shared-apex still use nearest endpoint as corner-side.
  4. Parallel: fixed-radius semicircle; chord from Va/Vb (mid projected),
     bulge faces the corner-intent side (midpoint Va–Vb). Wheel adjusts segments.

r=0 → CORNER mode: extend both edges to apex, weld into a sharp corner.
"""
import math
import bpy
import bmesh
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Vector

from ..modules import edit_mesh_draw_state as draw_state
from ..modules import cursor_plane as cp
from ..modules import edit_mesh_helpers as emh
from ..modules import modal_handler


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


def _intersection_inside_both_segments(
    a0_uv: Vector, a1_uv: Vector, b0_uv: Vector, b1_uv: Vector,
) -> bool:
    """True iff infinite lines through A and B meet strictly inside BOTH
    finite segments (proper X; not touching at an endpoint only).
    """
    d_a = a1_uv - a0_uv
    d_b = b1_uv - b0_uv
    cross_ab = _cross_2d(d_a, d_b)
    if abs(cross_ab) < 1e-9 * max(d_a.length, d_b.length, 1.0):
        return False
    rhs = b0_uv - a0_uv
    s_on_a = _cross_2d(rhs, d_b) / cross_ab
    t_on_b = _cross_2d(rhs, d_a) / cross_ab
    tol = max(_EPS, 1e-8 * max(d_a.length, d_b.length, 1.0))
    return (
        tol < s_on_a < 1.0 - tol and tol < t_on_b < 1.0 - tol
    )


def _classify_pair(edge_a, edge_b, mw, click_a_w=None, click_b_w=None):
    """Return per-edge endpoint roles in 2D working-plane coords.

    *click_a_w* / *click_b_w*: world clicks. Nearer endpoint becomes Va/Vb (L/V).
    When finite segments properly cross (X), the farther endpoint becomes Va/Vb.

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

    if click_a_w is not None:
        pa_near = (
            0 if (a0_w - click_a_w).length_squared <= (a1_w - click_a_w).length_squared else 1
        )
        pa = (1 - pa_near) if is_crossing else pa_near
    else:
        d_a0 = min((a0_w - b0_w).length_squared, (a0_w - b1_w).length_squared)
        d_a1 = min((a1_w - b0_w).length_squared, (a1_w - b1_w).length_squared)
        pa_near = 0 if d_a0 <= d_a1 else 1
        pa = (1 - pa_near) if is_crossing else pa_near

    if click_b_w is not None:
        pb_near = (
            0 if (b0_w - click_b_w).length_squared <= (b1_w - click_b_w).length_squared else 1
        )
        pb = (1 - pb_near) if is_crossing else pb_near
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


def _compute_fillet_data(
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
            return {
                'invalid': False,
                'mode': 'CORNER',
                'apex_w': apex_w,
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


def _avg_edge_length(edge_a, edge_b, mw) -> float:
    a0 = mw @ edge_a.verts[0].co
    a1 = mw @ edge_a.verts[1].co
    b0 = mw @ edge_b.verts[0].co
    b1 = mw @ edge_b.verts[1].co
    return ((a1 - a0).length + (b1 - b0).length) * 0.5


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class ALEC_OT_fillet_edges(bpy.types.Operator):
    """Unified fillet/chamfer: wheel controls segments (1 = chamfer)."""

    bl_idname = 'alec.fillet_edges'
    bl_label = 'Fillet / Chamfer'
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}
    bl_description = (
        'Round or chamfer between two coplanar mesh edges. Click first edge '
        'then second — the click position fixes which corner is filleted. '
        'Move mouse to set radius (clamped to edge length). Wheel: segments. '
        'Type r + Enter to apply. r=0 → sharp corner at apex.'
    )

    @classmethod
    def poll(cls, context):
        if context.area is None or context.area.type != 'VIEW_3D':
            return False
        if context.mode != 'EDIT_MESH':
            return False
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def invoke(self, context, event):
        self._obj = context.active_object
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            self.report({'ERROR'}, 'Could not access edit mesh')
            return {'CANCELLED'}
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        # Clear all selection — corner is determined by click positions only.
        for e in bm.edges:
            e.select = False
        for v in bm.verts:
            v.select = False
        bmesh.update_edit_mesh(self._obj.data)

        self._edge_a = None
        self._edge_b = None
        self._edge_a_key = None
        self._edge_b_key = None
        self._click_a_w: Vector | None = None
        self._click_b_w: Vector | None = None
        self._segments = 3
        self._radius: float | None = None
        self.number_input = modal_handler.ModalNumberInput()
        self._preview = None
        self._last_mouse: tuple[int, int] | None = (
            event.mouse_region_x,
            event.mouse_region_y,
        )

        draw_state._draw_data['object_name'] = self._obj.name
        draw_state._draw_data['mesh_name'] = self._obj.data.name
        draw_state.register_3d_draw_handler()

        self._refresh_ui(context)

        context.window_manager.modal_handler_add(self)
        if context.area is not None:
            context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _both_edges_loaded(self):
        return self._edge_a_key is not None and self._edge_b_key is not None

    def _refresh_ui(self, context):
        self._update_preview(context)
        # Sync displayed radius to clamped effective value from preview.
        if self._preview and not self._preview.get('invalid') and 'radius' in self._preview:
            self._radius = self._preview['radius']
        self._update_visual()
        self._set_status(context)
        self._update_header(context)

    def _ensure_bm_edges(self, bm):
        self._edge_a = emh.bm_edge_from_key(bm, self._edge_a_key) if self._edge_a_key else None
        self._edge_b = emh.bm_edge_from_key(bm, self._edge_b_key) if self._edge_b_key else None

    def _init_defaults(self):
        if self._edge_a is None or self._edge_b is None:
            return
        avg = _avg_edge_length(self._edge_a, self._edge_b, self._obj.matrix_world)
        default_r = max(0.05, avg * 0.25)
        if self._radius is None or self._radius <= _EPS:
            self._radius = default_r

    def _update_radius_from_mouse(self, context):
        """Project mouse onto the angle bisector to get a stable radius."""
        if self.number_input.has_value():
            return
        if context.region is None or context.region_data is None:
            return
        if self._last_mouse is None:
            return
        preview = self._preview
        if preview is None or preview.get('invalid') or 'bis_unit_w' not in preview:
            return  # parallel or no edges yet

        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return
        self._ensure_bm_edges(bm)
        ea, eb = self._edge_a, self._edge_b
        if ea is None or eb is None:
            return

        mw = self._obj.matrix_world
        plane = emh.working_plane_for_edges(ea, eb, mw)
        if plane is None:
            return
        plane_o, plane_n = plane[0], plane[1]

        ray_o = region_2d_to_origin_3d(
            context.region, context.region_data, self._last_mouse
        )
        ray_d = region_2d_to_vector_3d(
            context.region, context.region_data, self._last_mouse
        )
        if ray_d.length_squared < 1e-18:
            return
        hit = _ray_plane_intersect(ray_o, ray_d, plane_o, plane_n)
        if hit is None:
            return

        apex_w = preview['apex_w']
        bis_unit_w = preview['bis_unit_w']
        sin_h = preview['sin_half_angle']

        # Projection of mouse hit onto the bisector ray from the apex.
        # r = d × sin(half_angle), stable for all approach angles.
        d = (hit - apex_w).dot(bis_unit_w)
        self._radius = max(0.0, d * sin_h)

    def _update_header(self, context):
        if context.area is None:
            return
        r = float(self._radius or 0.0)
        prv = getattr(self, '_preview', None) or {}

        unit_sys = context.scene.unit_settings.system

        def _disp_len(length: float, prec: int = 4) -> str:
            try:
                return bpy.utils.units.to_string(unit_sys, 'LENGTH', length, precision=prec)
            except Exception:
                return f'{length:.{prec}f}'

        if (
            self._both_edges_loaded()
            and prv.get('parallel')
            and not prv.get('invalid')
        ):
            r_disp_parallel = _disp_len(float(prv.get('radius') or r), 4)
            if self.number_input.value_str:
                modal_handler.update_modal_header(
                    context,
                    main_label='Parallel r',
                    main_value=float(prv.get('radius') or r),
                    typed_str=self.number_input.value_str,
                    suffix='',
                    secondary_text=f'seg={self._segments}',
                    initial_value=float(prv.get('radius') or r),
                )
                return
            context.area.header_text_set(
                f'Parallel: {r_disp_parallel} (fixed D/2)  |  Segments={self._segments}'
            )
            return

        if r <= _EPS:
            primary = 'Corner'
        elif self._segments == 1:
            primary = 'Chamfer'
        else:
            primary = 'Fillet'

        try:
            r_disp = bpy.utils.units.to_string(unit_sys, 'LENGTH', r, precision=4)
        except Exception:
            r_disp = f'{r:.4f}'

        if self.number_input.value_str:
            modal_handler.update_modal_header(
                context,
                main_label=f'{primary} r',
                main_value=r,
                typed_str=self.number_input.value_str,
                suffix='',
                secondary_text=f'seg={self._segments}',
                initial_value=r,
            )
        else:
            context.area.header_text_set(
                f'{primary}: {r_disp}  |  segments={self._segments}'
            )

    def modal(self, context, event):
        if event.type in {'MIDDLEMOUSE'}:
            return {'PASS_THROUGH'}

        if event.type == 'ESC' and event.value == 'PRESS':
            if self._both_edges_loaded() and self.number_input.has_value():
                self.number_input.reset()
                self._refresh_ui(context)
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            self._cleanup(context)
            return {'CANCELLED'}

        if event.type in {'RET', 'NUMPAD_ENTER'} and self._both_edges_loaded():
            # Swallow RELEASE to avoid double-fire after PRESS.
            if event.value == 'RELEASE':
                return {'RUNNING_MODAL'}
            if event.value not in {'PRESS', 'CLICK'}:
                return {'RUNNING_MODAL'}
            # Commit typed radius then apply immediately.
            if self.number_input.has_value():
                try:
                    val = self.number_input.get_value(initial_value=self._radius)
                    if val >= 0:
                        self._radius = val
                except ValueError:
                    pass
                self.number_input.reset()
            self._update_preview(context)
            if self._preview and not self._preview.get('invalid') and 'radius' in self._preview:
                self._radius = self._preview['radius']
            ret = self._apply_fillet_if_ready(context)
            if ret == 'FINISHED':
                if context.area is not None:
                    context.area.tag_redraw()
                return {'FINISHED'}
            self._refresh_ui(context)
            if context.area is not None:
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        if self._both_edges_loaded() and event.type != 'ESC':
            if self.number_input.handle_event(event):
                self._refresh_ui(context)
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}

        if event.type == 'MOUSEMOVE':
            self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
            if self._both_edges_loaded():
                self._update_radius_from_mouse(context)
            self._refresh_ui(context)
            if context.area is not None:
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            if self._both_edges_loaded():
                if event.type == 'WHEELUPMOUSE':
                    self._segments = min(32, self._segments + 1)
                else:
                    self._segments = max(1, self._segments - 1)
                self._refresh_ui(context)
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            return {'PASS_THROUGH'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            ret = self._on_lmb(context)
            if ret == 'FINISHED':
                if context.area is not None:
                    context.area.tag_redraw()
                return {'FINISHED'}
            if ret is True:
                self._refresh_ui(context)
                if context.area is not None:
                    context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            if self._edge_b_key is not None:
                self._edge_b_key = None
                self._edge_b = None
                self._click_b_w = None
                self._preview = None
                self._refresh_ui(context)
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            if self._edge_a_key is not None:
                self._edge_a_key = None
                self._edge_a = None
                self._click_a_w = None
                self._click_b_w = None
                self._preview = None
                self._refresh_ui(context)
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            self._cleanup(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def _on_lmb(self, context):
        if context.region is None or context.region_data is None:
            return False
        if self._last_mouse is None:
            return False
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return False
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        self._ensure_bm_edges(bm)
        mw = self._obj.matrix_world

        if self._edge_a_key is None:
            edge, t, _d2 = emh.hovered_edge(
                bm, mw, context.region, context.region_data, self._last_mouse,
            )
            if edge is None:
                return False
            self._edge_a = edge
            self._edge_a_key = emh.bm_edge_key(edge)
            # Record where on the edge the user clicked.
            v0_w = mw @ edge.verts[0].co
            v1_w = mw @ edge.verts[1].co
            self._click_a_w = v0_w.lerp(v1_w, t if t is not None else 0.5)
            return True

        if self._edge_b_key is None:
            ea = emh.bm_edge_from_key(bm, self._edge_a_key)
            if ea is None:
                self._edge_a_key = None
                self._edge_a = None
                self._click_a_w = None
                return False
            edge, t, _d2 = emh.hovered_edge(
                bm, mw, context.region, context.region_data, self._last_mouse,
                exclude_edges=[ea],
            )
            if edge is None:
                return False
            self._edge_b = edge
            self._edge_b_key = emh.bm_edge_key(edge)
            v0_w = mw @ edge.verts[0].co
            v1_w = mw @ edge.verts[1].co
            self._click_b_w = v0_w.lerp(v1_w, t if t is not None else 0.5)
            self._ensure_bm_edges(bm)
            self._init_defaults()
            return True

        return self._apply_fillet_if_ready(context)

    def _apply_fillet_if_ready(self, context):
        if self._preview is None or self._preview.get('invalid', True):
            return False
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return False
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        self._ensure_bm_edges(bm)
        ea = emh.bm_edge_from_key(bm, self._edge_a_key)
        eb = emh.bm_edge_from_key(bm, self._edge_b_key)
        if ea is None or eb is None:
            return False
        mw = self._obj.matrix_world
        ok = _apply_arc(bm, ea, eb, self._preview, mw)
        if ok:
            bmesh.update_edit_mesh(self._obj.data)
            self._obj.data.update_tag()
            self._cleanup(context)
            return 'FINISHED'
        return False

    def _update_preview(self, _context):
        if self._edge_a_key is None or self._edge_b_key is None:
            self._preview = None
            return
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            self._preview = None
            return
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        self._ensure_bm_edges(bm)
        ea, eb = self._edge_a, self._edge_b
        if ea is None or eb is None:
            self._preview = None
            return
        mw = self._obj.matrix_world
        try:
            self._preview = _compute_fillet_data(
                ea, eb, mw,
                float(self._radius or 0.0),
                int(self._segments),
                click_a_w=self._click_a_w,
                click_b_w=self._click_b_w,
            )
        except (ReferenceError, AttributeError):
            self._preview = None

    def _update_visual(self):
        state: dict = {}
        mw = self._obj.matrix_world
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
            self._ensure_bm_edges(bm)
        except Exception:
            pass
        try:
            if self._edge_a is not None:
                ra = mw @ self._edge_a.verts[0].co
                rb = mw @ self._edge_a.verts[1].co
                state['ref_edge'] = (ra, rb)
            if self._edge_b is not None:
                ba = mw @ self._edge_b.verts[0].co
                bb = mw @ self._edge_b.verts[1].co
                state.setdefault('extra_lines', []).append(((ba, bb), (0.15, 0.85, 1.0, 0.95)))
        except (ReferenceError, AttributeError):
            pass

        if self._preview and not self._preview.get('invalid', True):
            if self._preview.get('mode') == 'CORNER':
                state['hit_point'] = self._preview.get('apex_w')
            else:
                arc = self._preview.get('arc_points_w')
                if arc and len(arc) >= 2:
                    state['fillet_chamfer_arc'] = arc
                state['hit_point'] = self._preview.get('TA_w')
        elif self._preview and self._preview.get('invalid'):
            try:
                if self._edge_a is not None and self._edge_b is not None:
                    a_a = mw @ self._edge_a.verts[0].co
                    a_b = mw @ self._edge_a.verts[1].co
                    state['warn_segment'] = (a_a, a_b)
            except (ReferenceError, AttributeError):
                pass

        if state:
            draw_state._draw_data['trim_extend_state'] = state
        else:
            draw_state._draw_data.pop('trim_extend_state', None)

    def _set_status(self, context):
        try:
            label = self.bl_label
            if self.number_input.value_str:
                context.workspace.status_text_set(
                    f"{label}: [Enter] apply  [Esc] cancel typing  "
                    f"[Wheel] segments  [RMB] clear edge"
                )
                return
            r = float(self._radius or 0.0)
            if self._edge_a_key is None:
                msg = f"{label}: Click first edge  [Esc] Exit"
            elif self._edge_b_key is None:
                msg = f"{label}: Click second edge  [RMB] Clear  [Esc] Exit"
            else:
                preview = self._preview or {}
                if preview.get('parallel') and not preview.get('invalid'):
                    msg = (
                        f'{label}: Parallel semicircle  '
                        f'segs={self._segments}  '
                        'LMB/Enter apply  [Wheel] segments  '
                        '[RMB] Reset  [Esc] Exit'
                    )
                else:
                    if r <= _EPS:
                        mode_word = 'corner (r=0)'
                    elif self._segments == 1:
                        mode_word = 'chamfer'
                    else:
                        mode_word = 'fillet'
                    if preview.get('invalid'):
                        reason = preview.get('reason', 'Invalid')
                        msg = (
                            f"{label} [{mode_word}]: {reason}  "
                            f"[RMB] Reset second edge  [Esc] Exit"
                        )
                    else:
                        msg = (
                            f"{label} [{mode_word}] segs={self._segments}  "
                            f"Move mouse = radius  Type r [Enter] = apply  "
                            f"[Wheel] segments  [RMB] Reset  [Esc] Exit"
                        )
            context.workspace.status_text_set(msg)
        except Exception:
            pass

    def _cleanup(self, context):
        draw_state._draw_data.pop('trim_extend_state', None)
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        if context.area is not None:
            try:
                context.area.header_text_set(None)
            except Exception:
                pass
            context.area.tag_redraw()


classes = (ALEC_OT_fillet_edges,)
