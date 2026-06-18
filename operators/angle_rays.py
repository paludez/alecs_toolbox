"""Angle Rays: interior subdivision rays from the apex of two coplanar edges.

Click the tool, LMB-pick two edges (live preview while hovering the second edge),
then adjust Divisions / Length / Reflex in the Adjust Last Operation panel.
Rays are created when both edges are picked; adjust in the Last Operation panel.
"""
from __future__ import annotations

import math

import bpy
import bmesh
from mathutils import Matrix, Vector

from ..modules import edit_mesh_draw_state as draw_state
from ..modules import edit_mesh_helpers as emh
from ..modules import status_bar
from .fillet_chamfer import (
    avg_edge_length,
    compute_fillet_data,
)

_PREVIEW_RAY_COLOR = (0.2, 0.85, 1.0, 0.9)
_EDGE_B_COLOR = (0.15, 0.85, 1.0, 0.95)

# Active edge pick between tool start and apply (kept for F9 redo).
_pick_session: dict | None = None
_suppress_prop_update: int = 0


def _tag_view3d_redraw(context):
    if context is None:
        return
    screen = getattr(context, 'screen', None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def _session_clear():
    global _pick_session
    _pick_session = None


def _session_save_from_edges(
    obj,
    edge_a,
    edge_b,
    mw,
    click_a_w: Vector,
    click_b_w: Vector,
) -> bool:
    """Cache edge keys, world geometry, and draw segments (no live BMEdge after this)."""
    global _pick_session
    try:
        corner = _corner_data(edge_a, edge_b, mw, click_a_w, click_b_w)
        if corner is None:
            return False
        ra = mw @ edge_a.verts[0].co
        rb = mw @ edge_a.verts[1].co
        ba = mw @ edge_b.verts[0].co
        bb = mw @ edge_b.verts[1].co
    except ReferenceError:
        return False

    shared_w = _shared_vertex_world(edge_a, edge_b, mw)
    apex_w = shared_w.copy() if shared_w is not None else corner['apex_w'].copy()
    arm_a = corner['arm_a_w'].copy()
    arm_b = corner['arm_b_w'].copy()
    plane_n = corner['plane_normal_w'].copy()
    _pick_session = {
        'object_name': obj.name,
        'mesh_name': obj.data.name,
        'edge_a_key': emh.bm_edge_key(edge_a),
        'edge_b_key': emh.bm_edge_key(edge_b),
        'shared_vertex': shared_w is not None,
        'click_a_w': click_a_w.copy(),
        'click_b_w': click_b_w.copy(),
        'apex_w': apex_w,
        'far_a_w': _far_endpoint_for_edge(edge_a, apex_w, mw),
        'far_b_w': _far_endpoint_for_edge(edge_b, apex_w, mw),
        'arm_a_w': arm_a,
        'arm_b_w': arm_b,
        'plane_normal_w': plane_n,
        'interior_short_sweep': _interior_uses_short_sweep(
            apex_w, arm_a, arm_b, plane_n, click_a_w, click_b_w,
        ),
        'ref_edge_a': (ra.copy(), rb.copy()),
        'ref_edge_b': (ba.copy(), bb.copy()),
        'default_length': max(0.05, avg_edge_length(edge_a, edge_b, mw)),
        'created_edge_keys': [],
    }
    return True


def _shared_vertex_world(edge_a, edge_b, mw) -> Vector | None:
    for va in edge_a.verts:
        for vb in edge_b.verts:
            if va == vb:
                return mw @ va.co
    return None


def _far_endpoint_w(apex_w: Vector, p0_w: Vector, p1_w: Vector) -> Vector:
    """Outer endpoint of a reference edge (opposite the corner / apex)."""
    if _near_world(p0_w, apex_w) and not _near_world(p1_w, apex_w):
        return p1_w.copy()
    if _near_world(p1_w, apex_w) and not _near_world(p0_w, apex_w):
        return p0_w.copy()
    return p0_w.copy() if (p0_w - apex_w).length_squared >= (p1_w - apex_w).length_squared else p1_w.copy()


def _far_endpoint_for_edge(edge, apex_w: Vector, mw) -> Vector:
    v0w = mw @ edge.verts[0].co
    v1w = mw @ edge.verts[1].co
    return _far_endpoint_w(apex_w, v0w, v1w)


def _near_world(p_w: Vector, q_w: Vector, eps: float = 1e-4) -> bool:
    return (p_w - q_w).length_squared <= (eps * 4) ** 2


def _session_pick_eps(session: dict) -> float:
    ra, rb = session['ref_edge_a']
    ba, bb = session['ref_edge_b']
    span = max((ra - rb).length, (ba - bb).length, 0.1)
    return max(1e-5, span * 1e-4)


def _point_on_edge_segment(p_w: Vector, p0_w: Vector, p1_w: Vector, eps: float) -> bool:
    seg = p1_w - p0_w
    len_sq = seg.length_squared
    if len_sq < 1e-12:
        return _near_world(p_w, p0_w, eps)
    t = float((p_w - p0_w).dot(seg) / len_sq)
    if t < -eps or t > 1.0 + eps:
        return False
    proj = p0_w + seg * max(0.0, min(1.0, t))
    return (p_w - proj).length_squared <= (eps * 4.0) ** 2


def _point_on_reference_edges(p_w: Vector, session: dict, eps: float) -> bool:
    ra, rb = session['ref_edge_a']
    ba, bb = session['ref_edge_b']
    return (
        _point_on_edge_segment(p_w, ra, rb, eps)
        or _point_on_edge_segment(p_w, ba, bb, eps)
    )


def _signed_angle_in_plane(from_w: Vector, to_w: Vector, plane_n: Vector) -> float:
    a = from_w.normalized()
    b = to_w.normalized()
    n = plane_n.normalized()
    return math.atan2(a.cross(b).dot(n), a.dot(b))


def _direction_in_ccw_sweep(
    arm_a_w: Vector,
    arm_b_w: Vector,
    plane_n: Vector,
    direction_w: Vector,
) -> bool:
    """True if direction lies in the CCW sweep from arm_a to arm_b (short arc)."""
    sweep = _signed_angle_in_plane(arm_a_w, arm_b_w, plane_n)
    if abs(sweep) < 1e-6:
        return True
    ang = _signed_angle_in_plane(arm_a_w, direction_w, plane_n)
    if sweep > 0.0:
        return 0.0 <= ang <= sweep
    return sweep <= ang <= 0.0


def _interior_uses_short_sweep(
    apex_w: Vector,
    arm_a_w: Vector,
    arm_b_w: Vector,
    plane_n: Vector,
    click_a_w: Vector,
    click_b_w: Vector,
) -> bool:
    """Pick-time: which wedge (short vs long) contains the user's click intent."""
    hint = (click_a_w - apex_w) + (click_b_w - apex_w)
    if hint.length_squared < 1e-12:
        return True
    return _direction_in_ccw_sweep(arm_a_w, arm_b_w, plane_n, hint)


def _session_far_points(session: dict) -> tuple[Vector, Vector]:
    apex_w = session['apex_w']
    far_a = session.get('far_a_w')
    far_b = session.get('far_b_w')
    if far_a is None or far_b is None:
        ra, rb = session['ref_edge_a']
        ba, bb = session['ref_edge_b']
        return _far_endpoint_w(apex_w, ra, rb), _far_endpoint_w(apex_w, ba, bb)
    return far_a.copy(), far_b.copy()


def _is_reference_edge_at_apex(edge, apex_vert, session: dict, mw) -> bool:
    """Keep the two picked edges — critical when they share the apex vertex (L corner)."""
    if apex_vert not in edge.verts:
        return False
    other = edge.other_vert(apex_vert)
    if other is None:
        return False
    ow = mw @ other.co
    far_a, far_b = _session_far_points(session)
    if _near_world(ow, far_a) or _near_world(ow, far_b):
        return True
    key = emh.bm_edge_key(edge)
    if key == session.get('edge_a_key') or key == session.get('edge_b_key'):
        return True
    ra, rb = session['ref_edge_a']
    ba, bb = session['ref_edge_b']
    return (
        _edge_matches_world_segment(edge, mw, ra, rb)
        or _edge_matches_world_segment(edge, mw, ba, bb)
    )


def _edit_mesh_object(context, session: dict | None):
    obj = getattr(context, 'edit_object', None)
    if obj is None:
        obj = getattr(context, 'object', None)
    if obj is None and session is not None:
        obj = bpy.data.objects.get(session.get('object_name', ''))
    return obj


def _vert_at_world(bm, mw, co_w: Vector, eps: float = 1e-5):
    eps_sq = eps * eps
    for v in bm.verts:
        if ((mw @ v.co) - co_w).length_squared <= eps_sq:
            return v
    return None


def _edge_matches_world_segment(
    edge,
    mw,
    p0_w: Vector,
    p1_w: Vector,
    eps: float = 1e-4,
) -> bool:
    """True if this bm edge is the same segment as the stored world endpoints."""
    a = mw @ edge.verts[0].co
    b = mw @ edge.verts[1].co
    eps_sq = (eps * 4) ** 2
    d0 = (a - p0_w).length_squared + (b - p1_w).length_squared
    d1 = (a - p1_w).length_squared + (b - p0_w).length_squared
    return min(d0, d1) <= eps_sq


def _apex_is_ray_hub_only(apex_vert, session: dict, mw) -> bool:
    """True if this vert is our floating fan center, not a corner of a picked edge."""
    far_a, far_b = _session_far_points(session)
    vw = mw @ apex_vert.co
    if _near_world(vw, far_a, eps=1e-3) or _near_world(vw, far_b, eps=1e-3):
        return False
    for edge in apex_vert.link_edges:
        if _is_reference_edge_at_apex(edge, apex_vert, session, mw):
            return False
    return True


def _ensure_session_apex(bm, session: dict, mw, geom: dict):
    """Apex for the ray fan. L-corner: snap to shared vert; open corner: exact intersection."""
    apex_w = geom['apex_w']
    eps = _session_pick_eps(session)

    if session.get('shared_vertex'):
        apex_vert = _vert_at_world(bm, mw, apex_w, eps=eps)
        if apex_vert is not None:
            return apex_vert
    else:
        apex_vert = _vert_at_world(bm, mw, apex_w, eps=eps)
        if apex_vert is not None:
            vw = mw @ apex_vert.co
            on_ref = _point_on_reference_edges(vw, session, eps)
            if not on_ref and _apex_is_ray_hub_only(apex_vert, session, mw):
                return apex_vert

    inv = mw.inverted_safe()
    return bm.verts.new(inv @ apex_w)


def _remove_session_rays(bm, session: dict, mw) -> None:
    """Remove ray edges at apex; keep both reference arms (incl. shared-vertex L corners)."""
    if not session.get('applied'):
        return

    apex_w = session.get('apex_w')
    if apex_w is None:
        session['created_edge_keys'] = []
        return

    apex_vert = _vert_at_world(bm, mw, apex_w)
    if apex_vert is None:
        session['created_edge_keys'] = []
        return

    to_remove = []
    for edge in list(apex_vert.link_edges):
        if _is_reference_edge_at_apex(edge, apex_vert, session, mw):
            continue
        to_remove.append(edge)

    apex_eps_sq = 1e-8
    for edge in to_remove:
        try:
            far = edge.other_vert(apex_vert)
            bm.edges.remove(edge)
            if far is not None and len(far.link_edges) == 0:
                if ((mw @ far.co) - apex_w).length_squared > apex_eps_sq:
                    bm.verts.remove(far)
        except (ReferenceError, ValueError):
            pass
    session['created_edge_keys'] = []


def _apply_angle_rays(context, divisions: int, length: float, reflex: bool) -> int:
    """Create rays from pick session; replaces any rays from an earlier apply."""
    if _pick_session is None:
        return 0

    obj = _edit_mesh_object(context, _pick_session)
    if (
        obj is None
        or obj.type != 'MESH'
        or obj.name != _pick_session['object_name']
        or obj.data.name != _pick_session['mesh_name']
    ):
        return 0

    mw = obj.matrix_world
    geom = _geometry_from_session(divisions, length, reflex)
    if geom is None:
        try:
            bm_tmp = bmesh.from_edit_mesh(obj.data)
            bm_tmp.edges.ensure_lookup_table()
            edge_a = emh.bm_edge_from_key(bm_tmp, _pick_session['edge_a_key'])
            edge_b = emh.bm_edge_from_key(bm_tmp, _pick_session['edge_b_key'])
            if edge_a is not None and edge_b is not None:
                geom = _compute_geometry(
                    edge_a,
                    edge_b,
                    mw,
                    divisions,
                    length,
                    reflex,
                    _pick_session['click_a_w'],
                    _pick_session['click_b_w'],
                )
        except ReferenceError:
            geom = None
    if geom is None:
        return 0

    bm = bmesh.from_edit_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    _remove_session_rays(bm, _pick_session, mw)

    apex_vert = _ensure_session_apex(bm, _pick_session, mw, geom)
    if apex_vert is None:
        return 0

    inv = mw.inverted_safe()
    apex_w = geom['apex_w']
    created = 0
    for direction in geom['directions']:
        end_local = inv @ (apex_w + direction * geom['length'])
        end_vert = bm.verts.new(end_local)
        try:
            bm.edges.new((apex_vert, end_vert))
            created += 1
        except ValueError:
            try:
                bm.verts.remove(end_vert)
            except (ValueError, ReferenceError):
                pass

    _pick_session['created_edge_keys'] = []
    _pick_session['applied'] = True
    bmesh.update_edit_mesh(obj.data)
    _clear_preview()
    return created


def _clear_preview():
    if draw_state._draw_data.get('angle_rays_preview'):
        draw_state._draw_data.pop('trim_extend_state', None)
        draw_state._draw_data.pop('angle_rays_preview', None)
        if not draw_state._draw_data:
            draw_state.unregister_draw_handler()


def _reset_operator_defaults(op) -> None:
    """Fresh tool run — do not inherit Adjust Last Operation values from the previous pick."""
    global _suppress_prop_update
    _suppress_prop_update += 1
    try:
        op.divisions = 2
        op.length = 0.0
        op.reflex = False
    finally:
        _suppress_prop_update -= 1


def _effective_length_from_session(length: float) -> float:
    if length > 1e-9:
        return float(length)
    if _pick_session is not None:
        return float(_pick_session.get('default_length', 0.05))
    return 0.05


def _geometry_from_session(divisions: int, length: float, use_reflex: bool) -> dict | None:
    """Preview/apply directions from cached world-space corner data (no BMEdge)."""
    if _pick_session is None or 'arm_a_w' not in _pick_session:
        return None
    dirs = _ray_directions(
        _pick_session['arm_a_w'],
        _pick_session['arm_b_w'],
        _pick_session['plane_normal_w'],
        divisions,
        use_reflex,
        bool(_pick_session.get('interior_short_sweep', True)),
    )
    if not dirs:
        return None
    apex_w = _pick_session['apex_w']
    ray_len = _effective_length_from_session(length)
    segments = [(apex_w.copy(), apex_w + d * ray_len) for d in dirs]
    return {
        'apex_w': apex_w,
        'segments': segments,
        'directions': dirs,
        'length': ray_len,
    }


def _ray_directions(
    arm_a_w: Vector,
    arm_b_w: Vector,
    plane_n: Vector,
    divisions: int,
    use_reflex: bool,
    interior_short_sweep: bool = True,
) -> list[Vector]:
    if divisions < 2:
        return []
    arm_a = arm_a_w.normalized()
    plane_n = plane_n.normalized()
    short_theta = _signed_angle_in_plane(arm_a_w, arm_b_w, plane_n)
    if abs(short_theta) < 1e-6:
        return []
    long_theta = (
        short_theta - (2.0 * math.pi) if short_theta > 0.0 else short_theta + (2.0 * math.pi)
    )
    use_short = interior_short_sweep if not use_reflex else not interior_short_sweep
    sweep = short_theta if use_short else long_theta

    directions: list[Vector] = []
    for k in range(1, divisions):
        rot = Matrix.Rotation(sweep * (k / divisions), 3, plane_n)
        directions.append((rot @ arm_a).normalized())
    return directions


def _effective_length(length: float, edge_a, edge_b, mw) -> float:
    if length > 1e-9:
        return float(length)
    return max(0.05, avg_edge_length(edge_a, edge_b, mw))


def _corner_data_from_shared_vertex(
    edge_a,
    edge_b,
    mw,
    click_a_w: Vector | None = None,
    click_b_w: Vector | None = None,
) -> dict | None:
    """L-corner (shared vertex): arms along each edge from the common point."""
    shared_w = _shared_vertex_world(edge_a, edge_b, mw)
    if shared_w is None:
        return None

    def _arm_along_edge(edge, click_w: Vector | None) -> Vector | None:
        v0w = mw @ edge.verts[0].co
        v1w = mw @ edge.verts[1].co
        if _near_world(v0w, shared_w) and not _near_world(v1w, shared_w):
            return (v1w - shared_w).normalized()
        if _near_world(v1w, shared_w) and not _near_world(v0w, shared_w):
            return (v0w - shared_w).normalized()
        if click_w is not None:
            outer = v1w if (click_w - v1w).length_squared < (click_w - v0w).length_squared else v0w
            arm = outer - shared_w
            if arm.length_squared > 1e-12:
                return arm.normalized()
        arm = v1w - v0w
        return arm.normalized() if arm.length_squared > 1e-12 else None

    arm_a = _arm_along_edge(edge_a, click_a_w)
    arm_b = _arm_along_edge(edge_b, click_b_w)
    if arm_a is None or arm_b is None:
        return None
    if arm_a.dot(arm_b) > 0.999:
        return None

    plane = emh.working_plane_for_edges(edge_a, edge_b, mw)
    if plane is None:
        return None
    return {
        'mode': 'CORNER',
        'apex_w': shared_w.copy(),
        'arm_a_w': arm_a,
        'arm_b_w': arm_b,
        'plane_normal_w': plane[1].normalized().copy(),
    }


def _corner_data(
    edge_a,
    edge_b,
    mw,
    click_a_w: Vector | None = None,
    click_b_w: Vector | None = None,
) -> dict | None:
    shared = _shared_vertex_world(edge_a, edge_b, mw) is not None
    data = compute_fillet_data(
        edge_a,
        edge_b,
        mw,
        radius=0.0,
        segments=1,
        click_a_w=click_a_w,
        click_b_w=click_b_w,
    )
    if data is not None and not data.get('invalid') and data.get('mode') == 'CORNER':
        if 'arm_a_w' in data and 'arm_b_w' in data and 'plane_normal_w' in data:
            if shared:
                data = dict(data)
                data['apex_w'] = _shared_vertex_world(edge_a, edge_b, mw).copy()
            return data

    if shared:
        return _corner_data_from_shared_vertex(edge_a, edge_b, mw, click_a_w, click_b_w)
    return None


def _compute_geometry(
    edge_a,
    edge_b,
    mw,
    divisions: int,
    length: float,
    use_reflex: bool,
    click_a_w: Vector | None = None,
    click_b_w: Vector | None = None,
) -> dict | None:
    data = _corner_data(edge_a, edge_b, mw, click_a_w, click_b_w)
    if data is None:
        return None

    apex_w = data['apex_w']
    interior_short = True
    if click_a_w is not None and click_b_w is not None:
        interior_short = _interior_uses_short_sweep(
            apex_w,
            data['arm_a_w'],
            data['arm_b_w'],
            data['plane_normal_w'],
            click_a_w,
            click_b_w,
        )

    dirs = _ray_directions(
        data['arm_a_w'],
        data['arm_b_w'],
        data['plane_normal_w'],
        divisions,
        use_reflex,
        interior_short,
    )
    if not dirs:
        return None
    ray_len = _effective_length(length, edge_a, edge_b, mw)
    segments = [(apex_w.copy(), apex_w + d * ray_len) for d in dirs]
    return {
        'apex_w': apex_w,
        'segments': segments,
        'directions': dirs,
        'length': ray_len,
    }


def _push_angle_rays_draw(context, obj, state: dict | None) -> None:
    if state is None:
        _clear_preview()
        _tag_view3d_redraw(context)
        return
    draw_state._draw_data['object_name'] = obj.name
    draw_state._draw_data['mesh_name'] = obj.data.name
    draw_state.register_3d_draw_handler()
    draw_state._draw_data['angle_rays_preview'] = True
    draw_state._draw_data['trim_extend_state'] = state
    _tag_view3d_redraw(context)


def _trim_extend_state_from_geom(
    ref_edge_a: tuple,
    ref_edge_b: tuple | None,
    geom: dict | None,
) -> dict:
    ra, rb = ref_edge_a
    state: dict = {'ref_edge': (ra.copy(), rb.copy())}
    extra: list = []
    if ref_edge_b is not None:
        ba, bb = ref_edge_b
        extra.append(((ba.copy(), bb.copy()), _EDGE_B_COLOR))
    if geom is not None:
        state['hit_point'] = geom['apex_w']
        extra.extend((seg, _PREVIEW_RAY_COLOR) for seg in geom['segments'])
    elif ref_edge_b is not None:
        state['warn_segment'] = (ra.copy(), rb.copy())
    if extra:
        state['extra_lines'] = extra
    return state


def refresh_angle_rays_modal_visual(context, op) -> None:
    """Live preview while picking edges (first edge fixed, second edge from hover)."""
    obj = getattr(op, '_obj', None)
    edge_a_key = getattr(op, '_edge_a_key', None)
    if obj is None or edge_a_key is None:
        _clear_preview()
        _tag_view3d_redraw(context)
        return

    if context.region is None or context.region_data is None:
        return

    last_mouse = getattr(op, '_last_mouse', None)
    if last_mouse is None:
        return

    try:
        bm = bmesh.from_edit_mesh(obj.data)
    except Exception:
        _clear_preview()
        _tag_view3d_redraw(context)
        return
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    mw = obj.matrix_world

    edge_a = emh.bm_edge_from_key(bm, edge_a_key)
    if edge_a is None:
        _clear_preview()
        _tag_view3d_redraw(context)
        return

    ra = mw @ edge_a.verts[0].co
    rb = mw @ edge_a.verts[1].co
    ref_a = (ra.copy(), rb.copy())
    click_a_w = getattr(op, '_click_a_w', None)

    edge_b, t, _d2 = emh.hovered_edge(
        bm, mw, context.region, context.region_data, last_mouse,
        exclude_edges=[edge_a],
    )
    ref_b = None
    click_b_w = None
    geom = None
    if edge_b is not None:
        v0_w = mw @ edge_b.verts[0].co
        v1_w = mw @ edge_b.verts[1].co
        click_b_w = v0_w.lerp(v1_w, t if t is not None else 0.5)
        ba = mw @ edge_b.verts[0].co
        bb = mw @ edge_b.verts[1].co
        ref_b = (ba.copy(), bb.copy())
        if click_a_w is not None:
            geom = _compute_geometry(
                edge_a,
                edge_b,
                mw,
                int(op.divisions),
                float(op.length),
                bool(op.reflex),
                click_a_w,
                click_b_w,
            )

    _push_angle_rays_draw(
        context,
        obj,
        _trim_extend_state_from_geom(ref_a, ref_b, geom),
    )


def refresh_angle_rays_preview(
    context,
    divisions: int,
    length: float,
    reflex: bool,
) -> None:
    if _pick_session is None or 'arm_a_w' not in _pick_session:
        _clear_preview()
        _tag_view3d_redraw(context)
        return

    obj = _edit_mesh_object(context, _pick_session)
    if (
        obj is None
        or obj.name != _pick_session['object_name']
        or obj.data.name != _pick_session['mesh_name']
    ):
        _clear_preview()
        _tag_view3d_redraw(context)
        return

    geom = _geometry_from_session(divisions, length, reflex)
    ra, rb = _pick_session['ref_edge_a']
    ba, bb = _pick_session['ref_edge_b']
    _push_angle_rays_draw(
        context,
        obj,
        _trim_extend_state_from_geom(
            (ra, rb),
            (ba, bb),
            geom,
        ),
    )


def _angle_rays_prop_update(self, context):
    if _pick_session is None or _suppress_prop_update > 0:
        return
    # After apply, Adjust Last Operation re-runs execute(); avoid double remove/create here.
    if _pick_session.get('applied'):
        return
    refresh_angle_rays_preview(
        context,
        int(self.divisions),
        float(self.length),
        bool(self.reflex),
    )


class ALEC_OT_angle_rays(bpy.types.Operator):
    bl_idname = 'alec.angle_rays'
    bl_label = 'Angle Rays'
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = (
        'Create subdivision rays from the apex of two coplanar edges. '
        'Click the tool, LMB-pick two edges, then adjust Divisions, Length, and '
        'Reflex in the Adjust Last Operation panel (live preview). Interior rays only.'
    )

    divisions: bpy.props.IntProperty(
        name='Divisions',
        description='Equal angle divisions between the edges (2 = bisector only)',
        min=2,
        max=32,
        default=2,
        update=_angle_rays_prop_update,
    )  # type: ignore[assignment]
    length: bpy.props.FloatProperty(
        name='Length',
        description='Ray length from apex (0 = average length of the two picked edges)',
        subtype='DISTANCE',
        min=0.0,
        default=0.0,
        update=_angle_rays_prop_update,
    )  # type: ignore[assignment]
    reflex: bpy.props.BoolProperty(
        name='Reflex Angle',
        default=False,
        description='Use the large (reflex) angle instead of the small angle between the edges',
        update=_angle_rays_prop_update,
    )  # type: ignore[assignment]

    @classmethod
    def poll(cls, context):
        if context.area is None or context.area.type != 'VIEW_3D':
            return False
        if context.mode != 'EDIT_MESH':
            return False
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        if _pick_session is None:
            layout.label(text='Pick two edges with the tool first', icon='INFO')
            return
        layout.prop(self, 'divisions')
        layout.prop(self, 'length')
        layout.prop(self, 'reflex')

    def _open_last_operator_panel(self, context):
        """Apply rays and register Adjust Last Operation (redo panel)."""
        self._cleanup_pick(context)
        obj = self._obj
        override: dict = {
            'active_object': obj,
            'object': obj,
            'edit_object': obj,
        }
        if context.window is not None:
            override['window'] = context.window
        if context.area is not None:
            override['area'] = context.area
        if context.region is not None:
            override['region'] = context.region
        with context.temp_override(**override):
            bpy.ops.alec.angle_rays(
                'EXEC_DEFAULT',
                divisions=self.divisions,
                length=self.length,
                reflex=self.reflex,
            )

    def invoke(self, context, event):
        _session_clear()
        _clear_preview()

        self._obj = context.active_object
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            self.report({'ERROR'}, 'Could not access edit mesh')
            return {'CANCELLED'}
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        for e in bm.edges:
            e.select = False
        for v in bm.verts:
            v.select = False
        bmesh.update_edit_mesh(self._obj.data)

        _reset_operator_defaults(self)

        self._edge_a_key = None
        self._edge_b_key = None
        self._click_a_w = None
        self._click_b_w = None
        self._last_mouse = (event.mouse_region_x, event.mouse_region_y)

        draw_state._draw_data['object_name'] = self._obj.name
        draw_state._draw_data['mesh_name'] = self._obj.data.name
        draw_state.register_3d_draw_handler()

        status_bar.set_message(context, 'Angle Rays: Click first edge  [Esc] Cancel')
        context.window_manager.modal_handler_add(self)
        if context.area is not None:
            context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        _clear_preview()
        _session_clear()
        status_bar.clear_message(context)
        return None

    def _cleanup_pick(self, context):
        status_bar.clear_message(context)
        if context.area is not None:
            context.area.tag_redraw()

    def modal(self, context, event):
        if event.type == 'MIDDLEMOUSE':
            return {'PASS_THROUGH'}

        if event.type == 'ESC' and event.value == 'PRESS':
            _clear_preview()
            _session_clear()
            self._cleanup_pick(context)
            return {'CANCELLED'}

        if event.type == 'MOUSEMOVE':
            self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
            refresh_angle_rays_modal_visual(context, self)
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if self._on_lmb_pick(context):
                self._open_last_operator_panel(context)
                return {'FINISHED'}
            return {'RUNNING_MODAL'}

        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            if self._edge_b_key is not None:
                self._edge_b_key = None
                status_bar.set_message(
                    context, 'Angle Rays: Click second edge  [RMB] Undo  [Esc] Cancel',
                )
                refresh_angle_rays_modal_visual(context, self)
                return {'RUNNING_MODAL'}
            if self._edge_a_key is not None:
                self._edge_a_key = None
                self._click_a_w = None
                _clear_preview()
                status_bar.set_message(
                    context, 'Angle Rays: Click first edge  [Esc] Cancel',
                )
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            _clear_preview()
            _session_clear()
            self._cleanup_pick(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def _on_lmb_pick(self, context) -> bool:
        """Pick edges; return True when both edges are chosen (opens Last Op panel)."""
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
        mw = self._obj.matrix_world

        if self._edge_a_key is None:
            edge, t, _d2 = emh.hovered_edge(
                bm, mw, context.region, context.region_data, self._last_mouse,
            )
            if edge is None:
                return False
            self._edge_a_key = emh.bm_edge_key(edge)
            v0_w = mw @ edge.verts[0].co
            v1_w = mw @ edge.verts[1].co
            self._click_a_w = v0_w.lerp(v1_w, t if t is not None else 0.5)
            status_bar.set_message(
                context, 'Angle Rays: Click second edge  [RMB] Undo  [Esc] Cancel',
            )
            refresh_angle_rays_modal_visual(context, self)
            return False

        if self._edge_b_key is None:
            ea = emh.bm_edge_from_key(bm, self._edge_a_key)
            if ea is None:
                self._edge_a_key = None
                return False
            edge, t, _d2 = emh.hovered_edge(
                bm, mw, context.region, context.region_data, self._last_mouse,
                exclude_edges=[ea],
            )
            if edge is None:
                return False
            self._edge_b_key = emh.bm_edge_key(edge)
            v0_w = mw @ edge.verts[0].co
            v1_w = mw @ edge.verts[1].co
            self._click_b_w = v0_w.lerp(v1_w, t if t is not None else 0.5)

            edge_a = emh.bm_edge_from_key(bm, self._edge_a_key)
            edge_b = emh.bm_edge_from_key(bm, self._edge_b_key)
            if edge_a is None or edge_b is None:
                return False
            if not _session_save_from_edges(
                self._obj, edge_a, edge_b, mw, self._click_a_w, self._click_b_w,
            ):
                return False

            global _suppress_prop_update
            _suppress_prop_update += 1
            try:
                if self.length <= 1e-9:
                    self.length = float(_pick_session['default_length'])
            finally:
                _suppress_prop_update -= 1

            refresh_angle_rays_preview(
                context, self.divisions, self.length, self.reflex,
            )
            return True

        return False

    def execute(self, context):
        if _pick_session is None:
            self.report({'WARNING'}, 'Pick two edges with the tool first')
            return {'CANCELLED'}

        created = _apply_angle_rays(
            context,
            int(self.divisions),
            float(self.length),
            bool(self.reflex),
        )
        if created <= 0:
            self.report({'WARNING'}, 'Invalid edge pair for angle rays')
            return {'CANCELLED'}

        self.report({'INFO'}, f'Created {created} ray(s) (divisions={self.divisions})')
        return {'FINISHED'}


classes = (ALEC_OT_angle_rays,)


def post_unregister():
    _session_clear()
    _clear_preview()
