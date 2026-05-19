"""Modal operators: Trim and Extend mesh edges (unified operator), AutoCAD-style.

Workflow:
- A reference (cutting/boundary) is picked first. It can be:
  - preselected before invoking the tool: a single face wins, or a single edge
    if no face is selected (face beats edge);
  - clicked after invoking: first LMB sets the reference edge.
- Hover a target edge: trim if the infinite boundary cuts the segment; otherwise
  extend to meet the boundary along the shorter ray from an endpoint.
- LMB applies the hovered action. Esc / Space / RMB cancel or clear the reference.

The reference edge is treated as an infinite line; the reference face is
treated as an infinite plane.

Edge-edge mode requires the four involved vertices to be coplanar. Edge-face
mode just requires the target edge to actually cross (Trim) or lie in a pose
extendable toward the boundary. Extend resolves the correct open end toward
the infinite reference automatically (sometimes only one ray hits ahead).
"""
import bpy
import bmesh
from mathutils import Vector

from ..modules import edit_mesh_draw_state as draw_state
from ..modules import status_bar
from ..modules import cursor_plane as cp
from ..modules import edit_mesh_helpers as emh


_EPS = emh.DRAFT_EPS
_PLANAR_EPS = emh.DRAFT_PLANAR_EPS


def _selected_reference(bm) -> tuple[str | None, object]:
    """Returns ('FACE', face) | ('EDGE', edge) | (None, None) per priority rules."""
    selected_faces = [f for f in bm.faces if f.select]
    if len(selected_faces) == 1:
        return 'FACE', selected_faces[0]
    if len(selected_faces) == 0:
        selected_edges = [e for e in bm.edges if e.select]
        if len(selected_edges) == 1:
            return 'EDGE', selected_edges[0]
    return None, None


def _world_face_normal(face, mw):
    nm = (mw.to_3x3().inverted_safe().transposed() @ face.normal)
    if nm.length_squared < 1e-18:
        return Vector((0.0, 0.0, 1.0))
    return nm.normalized()


def _world_face_origin(face, mw) -> Vector:
    return mw @ face.calc_center_median()


def _world_face_loop(face, mw) -> list[Vector]:
    return [mw @ v.co for v in face.verts]


def _working_plane_for_line_vs_edge(
    cut_w0: Vector, cut_w1: Vector, target_edge, mw
):
    """Same coplanarity test as emh.working_plane_for_edges, cutters as world pts."""
    r0_w = cut_w0
    r1_w = cut_w1
    pb0 = mw @ target_edge.verts[0].co
    pb1 = mw @ target_edge.verts[1].co
    d1 = r1_w - r0_w
    if d1.length_squared < 1e-12:
        return None
    pts = (r0_w, r1_w, pb0, pb1)
    normal = None
    for p in (pb0, pb1):
        cross = d1.cross(p - r0_w)
        if cross.length_squared > 1e-14:
            normal = cross.normalized()
            break
    if normal is None:
        return None
    for p in pts:
        if abs((p - r0_w).dot(normal)) > _PLANAR_EPS:
            return None
    u_ax = d1.normalized()
    v_ax = normal.cross(u_ax).normalized()
    return (r0_w.copy(), normal, u_ax, v_ax)


def _segment_dir_world(edge, mw) -> Vector:
    return (mw @ edge.verts[1].co) - (mw @ edge.verts[0].co)


def _compute_trim_preview(
    target_edge,
    t_mouse,
    ref_kind,
    mw,
    *,
    edge_ref=None,
    face_ref=None,
    edge_cut_w0: Vector | None = None,
    edge_cut_w1: Vector | None = None,
):
    p0 = mw @ target_edge.verts[0].co
    p1 = mw @ target_edge.verts[1].co

    if ref_kind == 'EDGE':
        plane = None
        cw0 = cw1 = None
        if edge_ref is not None:
            plane = emh.working_plane_for_edges(edge_ref, target_edge, mw)
            if plane is not None:
                cw0 = mw @ edge_ref.verts[0].co
                cw1 = mw @ edge_ref.verts[1].co
        if plane is None and edge_cut_w0 is not None and edge_cut_w1 is not None:
            plane = _working_plane_for_line_vs_edge(edge_cut_w0, edge_cut_w1, target_edge, mw)
            cw0 = edge_cut_w0.copy()
            cw1 = edge_cut_w1.copy()
        if plane is None:
            return {'invalid': True, 'reason': 'Edges not coplanar'}
        origin, _normal, u_ax, v_ax = plane
        a0 = cp.to_uv(p0, origin, u_ax, v_ax)
        a1 = cp.to_uv(p1, origin, u_ax, v_ax)
        cv0 = cp.to_uv(cw0, origin, u_ax, v_ax)
        cv1 = cp.to_uv(cw1, origin, u_ax, v_ax)
        result = cp.segment_segment_2d(a0, a1, cv0, cv1)
        if result is None:
            return {'invalid': True, 'reason': 'Parallel to cutting edge'}
        t_hit, _s = result
    elif ref_kind == 'FACE':
        if face_ref is None:
            return None
        normal_w = _world_face_normal(face_ref, mw)
        face_co_w = _world_face_origin(face_ref, mw)
        denom = (p1 - p0).dot(normal_w)
        if abs(denom) < 1e-9:
            return {'invalid': True, 'reason': 'Edge parallel to face plane'}
        t_hit = (face_co_w - p0).dot(normal_w) / denom
    else:
        return None

    if not (_EPS < t_hit < 1.0 - _EPS):
        return {'invalid': True, 'reason': 'Cutting line does not cross target'}

    hit_world = p0 + (p1 - p0) * t_hit
    if t_mouse <= t_hit:
        remove = (p0.copy(), hit_world.copy())
        keep = (hit_world.copy(), p1.copy())
        remove_first_half = True
    else:
        remove = (hit_world.copy(), p1.copy())
        keep = (p0.copy(), hit_world.copy())
        remove_first_half = False

    return {
        'invalid': False,
        't_hit': float(t_hit),
        'remove_first_half': remove_first_half,
        'hit_world': hit_world,
        'remove': remove,
        'keep': keep,
    }


def _extend_ray_vs_ref(
    origin_w: Vector,
    dir_unit: Vector,
    ref_kind: str,
    mw,
    target_edge,
    edge_ref=None,
    face_ref=None,
    edge_cut_w0: Vector | None = None,
    edge_cut_w1: Vector | None = None,
) -> float | None:
    """Positive t along ray origin_w + t*dir_unit intersects ref; None if ray misses boundary ahead."""
    if dir_unit.length_squared < 1e-18:
        return None

    direction = dir_unit.normalized()

    if ref_kind == 'EDGE':
        plane = None
        bw0 = bw1 = None
        if edge_ref is not None:
            plane = emh.working_plane_for_edges(edge_ref, target_edge, mw)
            if plane is not None:
                bw0 = mw @ edge_ref.verts[0].co
                bw1 = mw @ edge_ref.verts[1].co
        if plane is None and edge_cut_w0 is not None and edge_cut_w1 is not None:
            plane = _working_plane_for_line_vs_edge(
                edge_cut_w0, edge_cut_w1, target_edge, mw
            )
            bw0 = edge_cut_w0.copy()
            bw1 = edge_cut_w1.copy()
        if plane is None or bw0 is None:
            return None
        origin, _normal, u_ax, v_ax = plane
        ouv = cp.to_uv(origin_w, origin, u_ax, v_ax)
        oplus_uv = cp.to_uv(origin_w + direction, origin, u_ax, v_ax)
        bv0 = cp.to_uv(bw0, origin, u_ax, v_ax)
        bv1 = cp.to_uv(bw1, origin, u_ax, v_ax)
        result = cp.segment_segment_2d(ouv, oplus_uv, bv0, bv1)
        if result is None:
            return None
        t_ray, _s = result
    elif ref_kind == 'FACE':
        if face_ref is None:
            return None
        normal_w = _world_face_normal(face_ref, mw)
        face_co_w = _world_face_origin(face_ref, mw)
        denom = direction.dot(normal_w)
        if abs(denom) < 1e-9:
            return None
        t_ray = (face_co_w - origin_w).dot(normal_w) / denom
    else:
        return None

    if t_ray < _EPS:
        return None
    return float(t_ray)


def _compute_extend_preview(
    target_edge,
    ref_kind,
    mw,
    *,
    edge_ref=None,
    face_ref=None,
    edge_cut_w0: Vector | None = None,
    edge_cut_w1: Vector | None = None,
):
    """One extend direction toward the infinite boundary lies along each open end; pick the valid hit."""
    v0_bm = target_edge.verts[0]
    v1_bm = target_edge.verts[1]
    p0 = mw @ v0_bm.co
    p1 = mw @ v1_bm.co
    seg = p1 - p0
    if seg.length_squared < 1e-12:
        return {'invalid': True, 'reason': 'Zero-length edge'}
    d_hat = seg.normalized()
    ta = _extend_ray_vs_ref(
        p0,
        -d_hat,
        ref_kind,
        mw,
        target_edge,
        edge_ref=edge_ref,
        face_ref=face_ref,
        edge_cut_w0=edge_cut_w0,
        edge_cut_w1=edge_cut_w1,
    )
    tb = _extend_ray_vs_ref(
        p1,
        d_hat,
        ref_kind,
        mw,
        target_edge,
        edge_ref=edge_ref,
        face_ref=face_ref,
        edge_cut_w0=edge_cut_w0,
        edge_cut_w1=edge_cut_w1,
    )

    if ta is None and tb is None:
        return {'invalid': True, 'reason': 'Does not extend to boundary on this edge'}
    if ta is not None and tb is None:
        t_ray = ta
        end_world = p0
        v_chosen = v0_bm
        direction = (-d_hat)
    elif tb is not None and ta is None:
        t_ray = tb
        end_world = p1
        v_chosen = v1_bm
        direction = d_hat
    else:
        if ta <= tb:
            t_ray = ta
            end_world = p0
            v_chosen = v0_bm
            direction = (-d_hat)
        else:
            t_ray = tb
            end_world = p1
            v_chosen = v1_bm
            direction = d_hat

    du = direction.normalized()
    hit_world = end_world + du * t_ray
    return {
        'invalid': False,
        'hit_world': hit_world,
        'end_world': end_world,
        'preview': (end_world.copy(), hit_world.copy()),
        'v_chosen_index': v_chosen.index,
    }


def _apply_trim(bm, target_edge, t_hit: float, remove_first_half: bool, hit_world: Vector, mw) -> bool:
    v0 = target_edge.verts[0]
    v1 = target_edge.verts[1]
    inv = mw.inverted_safe()
    hit_local = inv @ hit_world

    try:
        _split_other, new_vert = emh.bmesh_edge_split_normalized(target_edge, v0, t_hit)
    except (RuntimeError, ValueError):
        return False
    new_vert.co = hit_local
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    # After split, Python references target_edge/new_edge don't reliably map to
    # geometric v0–hit vs hit–v1; pick halves by verts on the subdivided segment.
    edge_v0_half = None
    edge_v1_half = None
    for ed in new_vert.link_edges:
        try:
            if not ed.is_valid:
                continue
            ov = ed.other_vert(new_vert)
            if ov == v0:
                edge_v0_half = ed
            elif ov == v1:
                edge_v1_half = ed
        except ReferenceError:
            continue
    if edge_v0_half is None or edge_v1_half is None:
        return False

    # remove_first_half True = erase v0→hit portion (CAD: click picked that side)
    if remove_first_half:
        edge_to_remove = edge_v0_half
        v_potential_orphan = v0
    else:
        edge_to_remove = edge_v1_half
        v_potential_orphan = v1

    try:
        bm.edges.remove(edge_to_remove)
    except (ValueError, ReferenceError):
        return False
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    if v_potential_orphan.is_valid and len(v_potential_orphan.link_edges) == 0:
        try:
            bm.verts.remove(v_potential_orphan)
        except (ValueError, ReferenceError):
            pass
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
    return True


def _apply_extend(bm, v_chosen_index: int, hit_world: Vector, mw) -> bool:
    bm.verts.ensure_lookup_table()
    if v_chosen_index < 0 or v_chosen_index >= len(bm.verts):
        return False
    v = bm.verts[v_chosen_index]
    if not v.is_valid:
        return False
    inv = mw.inverted_safe()
    v.co = inv @ hit_world
    return True


class _TrimExtendBase:
    """Modal logic: auto trim vs extend from geometry."""

    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

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
        bm.faces.ensure_lookup_table()

        ref_kind, ref_elem = _selected_reference(bm)
        self._ref_kind = ref_kind
        self._ref_was_preselected = ref_kind is not None
        self._ref_edge_key = None
        self._ref_face_key = None
        if ref_kind == 'EDGE' and ref_elem is not None:
            self._ref_edge_key = emh.bm_edge_key(ref_elem)
        elif ref_kind == 'FACE' and ref_elem is not None:
            self._ref_face_key = emh.bm_face_key(ref_elem)
        self._ref_edge_w0 = None
        self._ref_edge_w1 = None
        if self._ref_kind == 'EDGE' and self._ref_edge_key is not None:
            e0 = emh.bm_edge_from_key(bm, self._ref_edge_key)
            if e0 is not None:
                mw_inv = self._obj.matrix_world
                self._ref_edge_w0 = (mw_inv @ e0.verts[0].co).copy()
                self._ref_edge_w1 = (mw_inv @ e0.verts[1].co).copy()
        self._target_edge = None
        self._target_edge_key = None
        self._target_t = 0.0
        self._preview = None
        self._last_event_mouse: tuple[int, int] | None = None
        self._effective_extend = False

        draw_state._draw_data['object_name'] = self._obj.name
        draw_state._draw_data['mesh_name'] = self._obj.data.name
        draw_state.register_3d_draw_handler()

        self._update_visual(context)
        self._set_status(context)

        context.window_manager.modal_handler_add(self)
        if context.area is not None:
            context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}

        if event.type == 'MOUSEMOVE':
            self._last_event_mouse = (event.mouse_region_x, event.mouse_region_y)
            self._update_hover(context)
            self._update_visual(context)
            self._set_status(context)
            if context.area is not None:
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            handled = self._on_lmb(context, event)
            if handled is True:
                self._update_hover(context)
                self._update_visual(context)
                self._set_status(context)
                if context.area is not None:
                    context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            if self._ref_kind is not None and not self._ref_was_preselected:
                self._ref_kind = None
                self._ref_edge_key = None
                self._ref_face_key = None
                self._ref_edge_w0 = None
                self._ref_edge_w1 = None
                self._target_edge = None
                self._target_edge_key = None
                self._preview = None
                self._update_visual(context)
                self._set_status(context)
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            self._cleanup(context)
            return {'CANCELLED'}

        if event.type in {'ESC', 'SPACE'} and event.value == 'PRESS':
            self._cleanup(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def _resolved_reference(self, bm):
        """Fresh BM refs from stable keys after bmesh.update_edit_mesh."""
        if self._ref_kind == 'EDGE' and self._ref_edge_key is not None:
            e = emh.bm_edge_from_key(bm, self._ref_edge_key)
            return ('EDGE', e)
        if self._ref_kind == 'FACE' and self._ref_face_key is not None:
            f = emh.bm_face_from_key(bm, self._ref_face_key)
            return ('FACE', f)
        return (None, None)

    def _sync_ref_edge_world_from_bm(self, bm, mw):
        """Refresh cutter line from live mesh edge; keep last coords if BM edge is gone."""
        if self._ref_kind != 'EDGE' or self._ref_edge_key is None:
            return
        e = emh.bm_edge_from_key(bm, self._ref_edge_key)
        if e is not None:
            try:
                self._ref_edge_w0 = (mw @ e.verts[0].co).copy()
                self._ref_edge_w1 = (mw @ e.verts[1].co).copy()
            except ReferenceError:
                pass

    def _on_lmb(self, context, event) -> bool:
        if context.region is None or context.region_data is None:
            return False
        if self._last_event_mouse is None:
            return False

        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return False
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        if self._ref_kind is None:
            edge, _t, _d2 = emh.hovered_edge(
                bm,
                self._obj.matrix_world,
                context.region,
                context.region_data,
                self._last_event_mouse,
            )
            if edge is None:
                return False
            self._ref_kind = 'EDGE'
            self._ref_edge_key = emh.bm_edge_key(edge)
            self._ref_face_key = None
            self._ref_was_preselected = False
            self._sync_ref_edge_world_from_bm(bm, self._obj.matrix_world)
            return True

        self._update_hover(context)

        if (
            self._target_edge_key is None
            or self._preview is None
            or self._preview.get('invalid', True)
        ):
            return False

        target_edge = emh.bm_edge_from_key(bm, self._target_edge_key)
        if target_edge is None:
            self._target_edge_key = None
            self._target_edge = None
            self._preview = None
            return False

        mw = self._obj.matrix_world
        applied = False
        if not self._effective_extend:
            applied = _apply_trim(
                bm,
                target_edge,
                self._preview['t_hit'],
                self._preview['remove_first_half'],
                self._preview['hit_world'],
                mw,
            )
        else:
            applied = _apply_extend(
                bm,
                int(self._preview['v_chosen_index']),
                self._preview['hit_world'],
                mw,
            )

        if applied:
            bmesh.update_edit_mesh(self._obj.data)
            self._obj.data.update_tag()
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            self._target_edge = None
            self._target_edge_key = None
            self._preview = None
        return applied

    def _update_hover(self, context):
        self._target_edge = None
        self._target_edge_key = None
        self._preview = None
        if self._last_event_mouse is None:
            return
        if context.region is None or context.region_data is None:
            return
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return
        bm.edges.ensure_lookup_table()

        mw_h = self._obj.matrix_world
        self._sync_ref_edge_world_from_bm(bm, mw_h)

        _, face_or_edge_bm = self._resolved_reference(bm)
        if self._ref_kind == 'FACE':
            if face_or_edge_bm is None:
                self._ref_kind = None
                self._ref_face_key = None
                self._ref_edge_key = None
                self._ref_edge_w0 = None
                self._ref_edge_w1 = None
                return
            rk = 'FACE'
            face_ref_bm = face_or_edge_bm
            edge_ref_bm = None
        elif self._ref_kind == 'EDGE':
            rk = 'EDGE'
            face_ref_bm = None
            edge_ref_bm = face_or_edge_bm
            if self._ref_edge_w0 is None or self._ref_edge_w1 is None:
                return
        else:
            rk = None
            face_ref_bm = None
            edge_ref_bm = None

        exclude = []
        if rk == 'EDGE' and edge_ref_bm is not None:
            exclude.append(edge_ref_bm)
        elif rk == 'FACE' and face_ref_bm is not None:
            try:
                exclude.extend(face_ref_bm.edges)
            except (ReferenceError, AttributeError):
                pass

        edge, t_along, _d2 = emh.hovered_edge(
            bm,
            self._obj.matrix_world,
            context.region,
            context.region_data,
            self._last_event_mouse,
            exclude_edges=exclude,
        )
        if edge is None:
            return

        self._target_edge = edge
        self._target_edge_key = emh.bm_edge_key(edge)
        self._target_t = float(t_along)

        if rk is None:
            return

        mw = mw_h
        trim_pv = _compute_trim_preview(
            edge,
            self._target_t,
            rk,
            mw,
            edge_ref=edge_ref_bm,
            face_ref=face_ref_bm,
            edge_cut_w0=self._ref_edge_w0,
            edge_cut_w1=self._ref_edge_w1,
        )
        extend_pv = _compute_extend_preview(
            edge,
            rk,
            mw,
            edge_ref=edge_ref_bm,
            face_ref=face_ref_bm,
            edge_cut_w0=self._ref_edge_w0,
            edge_cut_w1=self._ref_edge_w1,
        )

        trim_ok = bool(trim_pv is not None and not trim_pv.get('invalid', True))
        ext_ok = bool(extend_pv is not None and not extend_pv.get('invalid', True))
        if trim_ok:
            self._effective_extend = False
            self._preview = trim_pv
        elif ext_ok:
            self._effective_extend = True
            self._preview = extend_pv
        else:
            self._effective_extend = False
            if trim_pv is not None:
                self._preview = trim_pv
            elif extend_pv is not None:
                self._preview = extend_pv
            else:
                self._preview = {'invalid': True, 'reason': 'Invalid target'}

    def _update_visual(self, context):
        state: dict = {}
        mw = self._obj.matrix_world
        bm = None
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            bm = None
        rk, ref_data = (None, None)
        if bm is not None:
            rk, ref_data = self._resolved_reference(bm)

        if rk == 'EDGE':
            ra = rb = None
            if ref_data is not None:
                try:
                    ra = mw @ ref_data.verts[0].co
                    rb = mw @ ref_data.verts[1].co
                except (ReferenceError, AttributeError):
                    pass
            if ra is None and self._ref_edge_w0 is not None and self._ref_edge_w1 is not None:
                ra = self._ref_edge_w0.copy()
                rb = self._ref_edge_w1.copy()
            if ra is not None and rb is not None:
                state['ref_edge'] = (ra, rb)
                d = rb - ra
                if d.length_squared > 1e-12:
                    d = d.normalized()
                    state['ref_infinite_line'] = (
                        ((ra + rb) * 0.5) - d * 1000.0,
                        ((ra + rb) * 0.5) + d * 1000.0,
                    )
        elif rk == 'FACE' and ref_data is not None:
            try:
                state['ref_face_loop'] = _world_face_loop(ref_data, mw)
            except (ReferenceError, AttributeError):
                pass

        preview = self._preview
        target = None
        if bm is not None and self._target_edge_key is not None:
            target = emh.bm_edge_from_key(bm, self._target_edge_key)
        elif self._target_edge is not None:
            target = self._target_edge
        if target is not None and preview is not None:
            try:
                p0 = mw @ target.verts[0].co
                p1 = mw @ target.verts[1].co
                if preview.get('invalid'):
                    state['warn_segment'] = (p0, p1)
                else:
                    if not self._effective_extend:
                        state['target_remove_segment'] = preview['remove']
                        state['target_keep_segment'] = preview['keep']
                        state['hit_point'] = preview['hit_world']
                    else:
                        state['extend_preview'] = preview['preview']
                        state['hit_point'] = preview['hit_world']
            except (ReferenceError, AttributeError):
                pass

        if state:
            draw_state._draw_data['trim_extend_state'] = state
        else:
            draw_state._draw_data.pop('trim_extend_state', None)

    def _set_status(self, context):
        try:
            label = self.bl_label if hasattr(self, 'bl_label') else 'Trim / Extend'
            if self._ref_kind is None:
                msg = f"{label}: Click cutting/boundary edge  [Esc/Space] Exit"
            else:
                ref_str = 'face' if self._ref_kind == 'FACE' else 'edge'
                if self._target_edge_key is None:
                    msg = (
                        f"{label} [Reference: {ref_str}] Hover target edge"
                        f"  [RMB]{'Clear' if not self._ref_was_preselected else 'Exit'}  [Esc/Space] Exit"
                    )
                else:
                    preview = self._preview or {}
                    if preview.get('invalid'):
                        reason = preview.get('reason', 'Invalid target')
                        msg = (
                            f"{label} [{ref_str}] {reason}"
                            f"  [RMB]{'Clear' if not self._ref_was_preselected else 'Exit'}  [Esc/Space] Exit"
                        )
                    else:
                        action = 'Extend' if self._effective_extend else 'Trim'
                        msg = (
                            f"{label} [{ref_str}] [LMB] {action}"
                            f"  [RMB]{'Clear' if not self._ref_was_preselected else 'Exit'}  [Esc/Space] Exit"
                        )
            status_bar.set_message(context, msg)
        except Exception:
            pass

    def _cleanup(self, context):
        draw_state._draw_data.pop('trim_extend_state', None)
        status_bar.clear_message(context)
        if context.area is not None:
            context.area.tag_redraw()


class ALEC_OT_trim_extend_edges(_TrimExtendBase, bpy.types.Operator):
    bl_idname = 'alec.trim_extend_edges'
    bl_label = 'Trim / Extend'
    bl_description = (
        'Trim or extend mesh edges against a reference. Pick a cutting/boundary '
        'reference first (selection or first click): a single selected face beats '
        'a single edge. Hover a target edge: trim if the cut crosses the segment, '
        'otherwise extend. [LMB] applies; Esc / Space exit.'
    )


classes = (ALEC_OT_trim_extend_edges,)
