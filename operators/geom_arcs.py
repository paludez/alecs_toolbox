"""2pt / 3pt arc tools (modal pick + redo panel), matching the circle workflow."""
from __future__ import annotations

import bpy
import bmesh
from bpy_extras.view3d_utils import (
    location_3d_to_region_2d,
    region_2d_to_origin_3d,
    region_2d_to_vector_3d,
)
from mathutils import Vector

from ..modules import cursor_plane as cp
from ..modules import edit_mesh_draw_state as draw_state
from ..modules import edit_mesh_helpers as emh
from ..modules import modal_handler, status_bar, utils, viewport_header
from .edit_mesh import (
    _THREE_PT_PICK_RADIUS_PX,
    _THREE_PT_SNAP_RING_RADIUS_PX,
    _clear_three_pt_pick_preview,
    _refresh_three_pt_pick_visual,
    _tag_view3d_redraw,
    _three_pt_circle_session_valid,
    _three_pt_remove_created_circle,
    _three_pt_verts_from_session,
    _two_pt_circle_session_valid,
    _two_pt_points_on_cursor_plane,
    _two_pt_verts_from_session,
)

_three_pt_arc_session = None
_three_pt_arc_pick_session = None

_two_pt_arc_session = None
_two_pt_arc_pick_session = None


def clear_three_point_arc_session():
    global _three_pt_arc_session, _three_pt_arc_pick_session
    _three_pt_arc_session = None
    _three_pt_arc_pick_session = None
    _clear_three_pt_pick_preview()


def _reset_two_pt_arc_live_state(context=None):
    """Drop sessions, overlays, header/status so a new invoke can start clean."""
    global _two_pt_arc_session, _two_pt_arc_pick_session
    _two_pt_arc_session = None
    _two_pt_arc_pick_session = None
    _clear_two_pt_arc_preview()
    if context is not None:
        status_bar.clear_message(context)
        viewport_header.clear(context)


def clear_two_point_arc_session():
    _reset_two_pt_arc_live_state(bpy.context if bpy.context else None)


def _clear_two_pt_arc_preview():
    draw_state._draw_data.pop('two_pt_circle_preview', None)
    draw_state._draw_data.pop('cursor_plane', None)
    draw_state._draw_data.pop('three_pt_picked_world', None)
    draw_state._draw_data.pop('draw_snap_ring', None)
    draw_state._draw_data.pop('draw_snap_source_screen', None)
    if not draw_state.has_dim_overlay_data():
        draw_state.refresh_edit_mesh_px_handler(bpy.context)


def _three_pt_arc_pick_msg(n: int) -> str:
    if n <= 0:
        return '3pt Arc: Click first vertex  [RMB] Cancel  [Esc] Cancel'
    if n == 1:
        return '3pt Arc: Click second vertex  [RMB] Undo  [Esc] Cancel'
    if n == 2:
        return '3pt Arc: Click third vertex  [RMB] Undo  [Esc] Cancel'
    return '3pt Arc'


def _two_pt_arc_pick_msg(n: int) -> str:
    if n <= 0:
        return '2pt Arc: Click first vertex  [RMB] Cancel  [Esc] Cancel'
    if n == 1:
        return '2pt Arc: Click second vertex  [RMB] Undo  [Esc] Cancel'
    return '2pt Arc'


def _two_pt_arc_bulge_msg() -> str:
    return (
        '2pt Arc: Move mouse or type radius  [R] Radius  [V] Snap  '
        '[LMB] Confirm  [RMB] Cancel  [Esc] Cancel'
    )


def _session_preview_geom(context, session):
    """Rebuild arc frame from a finished session (for redo display)."""
    obj = bpy.data.objects.get(session.get('object_name'))
    if obj is None or obj.type != 'MESH':
        return None
    try:
        bm = bmesh.from_edit_mesh(obj.data)
    except Exception:
        return None
    verts = _two_pt_verts_from_session(bm, session)
    if verts is None:
        return None
    p1_w, p2_w, plane_n = _two_pt_points_on_cursor_plane(
        context, obj.matrix_world, verts[0], verts[1],
    )
    fixed_radius = session.get('fixed_radius')
    if fixed_radius is not None:
        hint = cp.project_onto_cursor_plane(
            context, Vector(session.get('bulge_hint_w') or (0.0, 0.0, 0.0)),
        )
        return emh.two_pt_arc_frame(p1_w, p2_w, hint, float(fixed_radius), plane_n)
    bulge_w = session.get('bulge_w')
    if bulge_w is None:
        return None
    bulge_w = cp.project_onto_cursor_plane(context, Vector(bulge_w))
    return emh.two_pt_arc_geom_from_bulge(p1_w, p2_w, bulge_w, plane_n)


def _three_pt_arc_start_sweep(thetas: list[float], anchor_index: int) -> tuple[float, float]:
    """Start angle and sweep for open arc through three picks in order."""
    t0, t1, t2 = thetas
    sweep_base = emh.arc_sweep_3pt_ordered(t0, t1, t2)
    anchor_index = max(0, min(2, int(anchor_index)))
    if anchor_index == 0:
        return t0, sweep_base
    if anchor_index == 2:
        return t2, -sweep_base
    d12 = emh.normalize_angle_pi(t2 - t1)
    if sweep_base > 0.0:
        sweep_mid = d12 if 0.0 < d12 <= sweep_base + 1e-9 else emh.normalize_angle_pi(t0 - t1)
    else:
        sweep_mid = d12 if sweep_base - 1e-9 <= d12 < 0.0 else emh.normalize_angle_pi(t0 - t1)
    return t1, sweep_mid


def _three_pt_create_arc(
    bm,
    mw,
    definition_verts,
    segments: int,
    anchor_index: int,
    session: dict,
) -> bool:
    inv_mw = mw.inverted_safe()
    points_w = [mw @ v.co for v in definition_verts]
    circle = emh.circumcircle_from_three_points(points_w[0], points_w[1], points_w[2])
    if circle is None:
        return False
    center_w, radius_w, u_axis, v_axis = circle
    thetas = [
        emh.circle_phase_for_point(center_w, u_axis, v_axis, pw)
        for pw in points_w
    ]
    theta_start, sweep = _three_pt_arc_start_sweep(thetas, anchor_index)
    return emh.bmesh_append_arc_edges(
        session, bm, inv_mw, center_w, u_axis, v_axis, radius_w, theta_start, sweep, segments,
    )


def _two_pt_create_arc(
    context,
    bm,
    mw,
    definition_verts,
    session: dict,
    segments: int,
) -> bool:
    inv_mw = mw.inverted_safe()
    p1_w, p2_w, plane_n = _two_pt_points_on_cursor_plane(
        context, mw, definition_verts[0], definition_verts[1],
    )
    fixed_radius = session.get('fixed_radius')
    if fixed_radius is not None:
        hint = cp.project_onto_cursor_plane(
            context, Vector(session.get('bulge_hint_w') or session['bulge_w']),
        )
        geom = emh.two_pt_arc_frame(p1_w, p2_w, hint, float(fixed_radius), plane_n)
    else:
        bulge_w = cp.project_onto_cursor_plane(context, Vector(session['bulge_w']))
        geom = emh.two_pt_arc_geom_from_bulge(p1_w, p2_w, bulge_w, plane_n)
    if geom is None:
        return False
    return emh.bmesh_append_arc_edges(
        session,
        bm,
        inv_mw,
        geom['center'],
        geom['u'],
        geom['v'],
        geom['radius'],
        geom['theta_start'],
        geom['sweep'],
        segments,
    )


def _arc_preview_from_geom(geom, p1_w, p2_w, sweep, segments, context):
    draw_state._draw_data['two_pt_circle_preview'] = {
        'center': geom['center'].copy(),
        'u': geom['u'].copy(),
        'v': geom['v'].copy(),
        'radius': float(geom['radius']),
        'theta_start': float(geom.get('theta_start', 0.0)),
        'sweep': float(sweep),
        'segments': int(segments),
        'p1': p1_w.copy(),
        'p2': p2_w.copy(),
    }
    try:
        _n, u_ax, v_ax = cp.cursor_plane_axes(context)
        draw_state._draw_data['cursor_plane'] = (
            context.scene.cursor.location.copy(),
            u_ax,
            v_ax,
        )
    except Exception:
        draw_state._draw_data.pop('cursor_plane', None)


class ALEC_OT_three_point_arc(bpy.types.Operator):
    """Pick three vertices; arc through them in pick order (live tweak in redo panel)"""
    bl_idname = "alec.three_point_arc"
    bl_label = "3pt Arc"
    bl_options = {'REGISTER', 'UNDO'}

    segments: bpy.props.IntProperty(
        name="Edges",
        description="Number of edges along the arc",
        min=1,
        max=256,
        default=16,
    )  # type: ignore

    anchor_point: bpy.props.IntProperty(
        name="Start at Pick",
        description="Which picked vertex is the arc start (1–3)",
        min=1,
        max=3,
        default=1,
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        return emh.poll_active_mesh_edit_mode(context)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "segments")
        layout.prop(self, "anchor_point", slider=True)

    def invoke(self, context, event):
        global _three_pt_arc_pick_session, _three_pt_arc_session
        _three_pt_arc_session = None
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            return {'CANCELLED'}
        try:
            bm = bmesh.from_edit_mesh(obj.data)
        except Exception:
            self.report({'ERROR'}, "Could not access edit mesh")
            return {'CANCELLED'}
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        for e in bm.edges:
            e.select = False
        for v in bm.verts:
            v.select = False
        for f in bm.faces:
            f.select = False
        bmesh.update_edit_mesh(obj.data)

        _three_pt_arc_pick_session = {
            'object_name': obj.name,
            'mesh_name': obj.data.name,
            'picked_indices': [],
        }
        self._obj = obj
        self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
        _refresh_three_pt_pick_visual(context, obj, [], self._last_mouse)
        status_bar.set_message(context, _three_pt_arc_pick_msg(0))
        context.window_manager.modal_handler_add(self)
        _tag_view3d_redraw(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        global _three_pt_arc_pick_session
        if event.type == 'MIDDLEMOUSE':
            return {'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if _three_pt_arc_pick_session is None:
            return {'CANCELLED'}
        if event.type == 'ESC' and event.value == 'PRESS':
            _three_pt_arc_pick_session = None
            _clear_three_pt_pick_preview()
            status_bar.clear_message(context)
            _tag_view3d_redraw(context)
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
            _refresh_three_pt_pick_visual(
                context, self._obj, _three_pt_arc_pick_session['picked_indices'], self._last_mouse,
            )
            return {'RUNNING_MODAL'}
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            picked = _three_pt_arc_pick_session['picked_indices']
            if picked:
                picked.pop()
                status_bar.set_message(context, _three_pt_arc_pick_msg(len(picked)))
                _refresh_three_pt_pick_visual(context, self._obj, picked, self._last_mouse)
                return {'RUNNING_MODAL'}
            _three_pt_arc_pick_session = None
            _clear_three_pt_pick_preview()
            status_bar.clear_message(context)
            _tag_view3d_redraw(context)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if self._on_lmb_pick(context):
                return self._finish_pick_and_apply(context)
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}

    def _on_lmb_pick(self, context) -> bool:
        global _three_pt_arc_pick_session
        if _three_pt_arc_pick_session is None or context.region is None or context.region_data is None:
            return False
        if self._last_mouse is None:
            return False
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return False
        bm.verts.ensure_lookup_table()
        mw = self._obj.matrix_world
        picked = _three_pt_arc_pick_session['picked_indices']
        if len(picked) >= 3:
            return True
        vert, _d2 = emh.hovered_vert(
            bm, mw, context.region, context.region_data, self._last_mouse,
            threshold_px=_THREE_PT_PICK_RADIUS_PX, exclude_indices=picked,
        )
        if vert is None:
            return False
        picked.append(vert.index)
        status_bar.set_message(context, _three_pt_arc_pick_msg(len(picked)))
        _refresh_three_pt_pick_visual(context, self._obj, picked, self._last_mouse)
        return len(picked) >= 3

    def _finish_pick_and_apply(self, context):
        global _three_pt_arc_pick_session, _three_pt_arc_session
        picked = list(_three_pt_arc_pick_session['picked_indices']) if _three_pt_arc_pick_session else []
        _three_pt_arc_pick_session = None
        _clear_three_pt_pick_preview()
        status_bar.clear_message(context)
        if len(picked) != 3:
            return {'CANCELLED'}
        _three_pt_arc_session = {
            'object_name': self._obj.name,
            'mesh_name': self._obj.data.name,
            'vert_indices': tuple(picked),
            'created_vert_indices': [],
            'created_edge_keys': [],
            'applied': False,
        }
        return self.execute(context)

    def check(self, context):
        self.execute(context)
        return True

    def execute(self, context):
        global _three_pt_arc_session
        if not _three_pt_circle_session_valid(context, _three_pt_arc_session):
            self.report({'WARNING'}, "Run the tool and pick three vertices first")
            return {'CANCELLED'}
        session = _three_pt_arc_session
        obj = bpy.data.objects.get(session['object_name']) or context.edit_object or context.active_object
        if obj is None or obj.type != 'MESH':
            return {'CANCELLED'}
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        verts = _three_pt_verts_from_session(bm, session)
        if verts is None:
            self.report({'WARNING'}, "Definition vertices are no longer valid")
            return {'CANCELLED'}
        _three_pt_remove_created_circle(bm, session)
        if not _three_pt_create_arc(
            bm, obj.matrix_world, verts, int(self.segments), int(self.anchor_point) - 1, session,
        ):
            self.report({'WARNING'}, "The three points are collinear")
            return {'CANCELLED'}
        session['applied'] = True
        bmesh.update_edit_mesh(obj.data, loop_triangles=True)
        obj.update_tag(refresh={'DATA'})
        return {'FINISHED'}


class ALEC_OT_two_point_arc(bpy.types.Operator):
    """Pick two vertices, move mouse as third arc point on the cursor plane"""
    bl_idname = "alec.two_point_arc"
    bl_label = "2pt Arc"
    bl_options = {'REGISTER', 'UNDO'}

    _bulge_modal_instance = None

    radius: bpy.props.FloatProperty(
        name="Raza",
        min=0.0,
        default=0.0,
        unit='LENGTH',
    )  # type: ignore

    center: bpy.props.FloatVectorProperty(
        name="Center",
        size=3,
        subtype='TRANSLATION',
        default=(0.0, 0.0, 0.0),
    )  # type: ignore

    segments: bpy.props.IntProperty(
        name="Edges",
        min=1,
        max=256,
        default=16,
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        return emh.poll_active_mesh_edit_mode(context)

    @classmethod
    def draw_status_bar(cls, panel, context):
        inst = cls._bulge_modal_instance
        if inst is None or getattr(inst, '_phase', '') != 'bulge':
            return
        status_bar.draw_shortcuts(panel.layout, inst._bulge_status_items())

    def _bulge_status_items(self):
        return [
            ("Radius", "[R]", self.number_input.has_value()),
            ("Snap", "[V]", self._snap_verts),
            None,
            ("Confirm", "[LMB]"),
            ("Cancel", "[Esc]"),
        ]

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.enabled = False
        col.prop(self, "radius")
        col.prop(self, "center")
        layout.prop(self, "segments")

    def cancel(self, context):
        self._bulge_modal_teardown()
        _reset_two_pt_arc_live_state(context)
        _tag_view3d_redraw(context)
        return {'CANCELLED'}

    def _bulge_modal_teardown(self):
        if self.__class__._bulge_modal_instance is self:
            self.__class__._bulge_modal_instance = None
        try:
            status_bar.uninstall_shortcuts(self.__class__)
        except Exception:
            pass

    def invoke(self, context, event):
        global _two_pt_arc_pick_session
        _reset_two_pt_arc_live_state(context)
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            return {'CANCELLED'}
        try:
            bm = bmesh.from_edit_mesh(obj.data)
        except Exception:
            self.report({'ERROR'}, "Could not access edit mesh")
            return {'CANCELLED'}
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        for e in bm.edges:
            e.select = False
        for v in bm.verts:
            v.select = False
        for f in bm.faces:
            f.select = False
        bmesh.update_edit_mesh(obj.data)

        _two_pt_arc_pick_session = {
            'object_name': obj.name,
            'mesh_name': obj.data.name,
            'picked_indices': [],
        }
        self._obj = obj
        self._phase = 'pick'
        self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
        self._bulge_w = None
        self._bulge_hint_w = None
        self._plane_n = Vector((0.0, 0.0, 1.0))
        self._radius = 1.0
        self._center_w = Vector((0.0, 0.0, 0.0))
        self._snap_verts = True
        _refresh_three_pt_pick_visual(context, obj, [], self._last_mouse)
        status_bar.set_message(context, _two_pt_arc_pick_msg(0))
        context.window_manager.modal_handler_add(self)
        _tag_view3d_redraw(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MIDDLEMOUSE':
            return {'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if self._phase == 'pick':
            return self._modal_pick(context, event)
        return self._modal_bulge(context, event)

    def _modal_pick(self, context, event):
        global _two_pt_arc_pick_session
        if _two_pt_arc_pick_session is None:
            return self.cancel(context)
        if event.type == 'ESC' and event.value == 'PRESS':
            return self.cancel(context)
        if event.type == 'MOUSEMOVE':
            self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
            _refresh_three_pt_pick_visual(
                context, self._obj, _two_pt_arc_pick_session['picked_indices'], self._last_mouse,
            )
            return {'RUNNING_MODAL'}
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            picked = _two_pt_arc_pick_session['picked_indices']
            if picked:
                picked.pop()
                status_bar.set_message(context, _two_pt_arc_pick_msg(len(picked)))
                _refresh_three_pt_pick_visual(context, self._obj, picked, self._last_mouse)
                return {'RUNNING_MODAL'}
            return self.cancel(context)
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if self._on_pick_lmb(context):
                self._enter_bulge_phase(context)
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}

    def _on_pick_lmb(self, context) -> bool:
        global _two_pt_arc_pick_session
        if _two_pt_arc_pick_session is None or context.region is None or context.region_data is None:
            return False
        if self._last_mouse is None:
            return False
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return False
        bm.verts.ensure_lookup_table()
        mw = self._obj.matrix_world
        picked = _two_pt_arc_pick_session['picked_indices']
        if len(picked) >= 2:
            return True
        vert, _d2 = emh.hovered_vert(
            bm, mw, context.region, context.region_data, self._last_mouse,
            threshold_px=_THREE_PT_PICK_RADIUS_PX, exclude_indices=picked,
        )
        if vert is None:
            return False
        picked.append(vert.index)
        status_bar.set_message(context, _two_pt_arc_pick_msg(len(picked)))
        _refresh_three_pt_pick_visual(context, self._obj, picked, self._last_mouse)
        return len(picked) >= 2

    def _enter_bulge_phase(self, context):
        global _two_pt_arc_pick_session
        picked = list(_two_pt_arc_pick_session['picked_indices']) if _two_pt_arc_pick_session else []
        _two_pt_arc_pick_session = None
        draw_state._draw_data.pop('draw_snap_ring', None)
        draw_state._draw_data.pop('draw_snap_source_screen', None)
        if len(picked) != 2:
            return
        self._picked_indices = picked
        self._phase = 'bulge'
        self.number_input = modal_handler.ModalNumberInput()
        self.unit_scale_display_inv = utils.length_bu_to_display_multiplier(context)
        self.unit_scale = utils.display_length_to_bu_multiplier(context)
        bm = bmesh.from_edit_mesh(self._obj.data)
        v0, v1 = bm.verts[picked[0]], bm.verts[picked[1]]
        mw = self._obj.matrix_world
        p1_w, p2_w, plane_n = _two_pt_points_on_cursor_plane(context, mw, v0, v1)
        self._plane_n = plane_n
        if (p2_w - p1_w).length < 1e-9:
            self.report({'WARNING'}, "Points coincide on the cursor plane")
            self._phase = 'pick'
            return
        self._snap_verts = True
        self.__class__._bulge_modal_instance = self
        status_bar.install_shortcuts(self.__class__)
        self._update_bulge_from_mouse(context)
        status_bar.set_message(context, _two_pt_arc_bulge_msg())
        self._update_bulge_header(context)
        self._refresh_bulge_preview(context)
        _tag_view3d_redraw(context)

    def _update_bulge_snap_ring(self, context):
        draw_state._draw_data.pop('draw_snap_ring', None)
        draw_state._draw_data.pop('draw_snap_source_screen', None)
        if not self._snap_verts or context.region is None or context.region_data is None:
            return
        if self._last_mouse is None:
            return
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return
        bm.verts.ensure_lookup_table()
        vert, _d2 = emh.hovered_vert(
            bm,
            self._obj.matrix_world,
            context.region,
            context.region_data,
            self._last_mouse,
            threshold_px=_THREE_PT_PICK_RADIUS_PX,
            exclude_indices=self._picked_indices,
        )
        if vert is None:
            return
        p2d = location_3d_to_region_2d(
            context.region, context.region_data, self._obj.matrix_world @ vert.co,
        )
        if p2d is not None:
            draw_state._draw_data['draw_snap_ring'] = (
                float(p2d.x),
                float(p2d.y),
                _THREE_PT_SNAP_RING_RADIUS_PX,
                0,
            )

    def _resolve_bulge_hit(self, context):
        if (
            self._snap_verts
            and context.region is not None
            and context.region_data is not None
            and self._last_mouse is not None
        ):
            try:
                bm = bmesh.from_edit_mesh(self._obj.data)
            except Exception:
                bm = None
            if bm is not None:
                bm.verts.ensure_lookup_table()
                vert, _d2 = emh.hovered_vert(
                    bm,
                    self._obj.matrix_world,
                    context.region,
                    context.region_data,
                    self._last_mouse,
                    threshold_px=_THREE_PT_PICK_RADIUS_PX,
                    exclude_indices=self._picked_indices,
                )
                if vert is not None:
                    return cp.project_onto_cursor_plane(
                        context, self._obj.matrix_world @ vert.co,
                    )
        if context.region is None or context.region_data is None or self._last_mouse is None:
            return None
        ray_o = region_2d_to_origin_3d(context.region, context.region_data, self._last_mouse)
        ray_d = region_2d_to_vector_3d(context.region, context.region_data, self._last_mouse)
        if ray_d.length_squared < 1e-18:
            return None
        return cp.intersect_cursor_plane(context, ray_o, ray_d)

    def _bulge_plane_points(self, context):
        bm = bmesh.from_edit_mesh(self._obj.data)
        v0 = bm.verts[self._picked_indices[0]]
        v1 = bm.verts[self._picked_indices[1]]
        mw = self._obj.matrix_world
        return _two_pt_points_on_cursor_plane(context, mw, v0, v1)

    def _min_radius_bu(self, p1_w, p2_w) -> float:
        return (p2_w - p1_w).length * 0.5 + 1e-6

    def _current_bulge_geom(self, context):
        p1_w, p2_w, plane_n = self._bulge_plane_points(context)
        bulge_hint = self._bulge_side_hint(context)
        if bulge_hint is None:
            return None, p1_w, p2_w, plane_n
        if self.number_input.has_value():
            geom = emh.two_pt_arc_frame(
                p1_w, p2_w, bulge_hint, float(self._radius), plane_n,
            )
        else:
            bulge_w = cp.project_onto_cursor_plane(context, Vector(self._bulge_w))
            geom = emh.two_pt_arc_geom_from_bulge(p1_w, p2_w, bulge_w, plane_n)
        return geom, p1_w, p2_w, plane_n

    def _sync_dims_from_geom(self, geom, p1_w, p2_w):
        if geom is None:
            return
        self._radius = float(geom['radius'])
        self._center_w = Vector(geom['center'])
        self.radius = self._radius
        self.center = tuple(self._center_w)

    def _update_bulge_from_mouse(self, context):
        hit = self._resolve_bulge_hit(context)
        if hit is None:
            return
        self._bulge_hint_w = hit.copy()
        self._bulge_w = hit.copy()
        p1_w, p2_w, plane_n = self._bulge_plane_points(context)
        self._plane_n = plane_n
        geom, p1_w, p2_w, plane_n = self._current_bulge_geom(context)
        self._sync_dims_from_geom(geom, p1_w, p2_w)

    def _apply_typed_numeric(self, context):
        p1_w, p2_w, plane_n = self._bulge_plane_points(context)
        r_min = self._min_radius_bu(p1_w, p2_w)
        self._radius = max(float(self._radius), r_min)
        geom, p1_w, p2_w, plane_n = self._current_bulge_geom(context)
        self._sync_dims_from_geom(geom, p1_w, p2_w)

    def _bulge_side_hint(self, context):
        hint = self._bulge_hint_w or self._bulge_w
        if hint is None:
            return None
        return cp.project_onto_cursor_plane(context, Vector(hint))

    def _update_bulge_header(self, context):
        suffix = utils.unit_suffixes.get(context.scene.unit_settings.length_unit, '')
        viewport_header.set_numeric(
            context,
            main_label='Radius',
            main_value=float(self._radius) * self.unit_scale_display_inv,
            typed_str=self.number_input.value_str,
            suffix=suffix,
        )

    def _refresh_bulge_preview(self, context):
        if self._bulge_w is None:
            return
        self._update_bulge_snap_ring(context)
        if self.number_input.has_value():
            self._apply_typed_numeric(context)
        geom, p1_w, p2_w, plane_n = self._current_bulge_geom(context)
        bulge_hint = self._bulge_side_hint(context)
        if geom is None or bulge_hint is None:
            draw_state._draw_data.pop('two_pt_circle_preview', None)
            return
        self._sync_dims_from_geom(geom, p1_w, p2_w)
        draw_state._draw_data['object_name'] = self._obj.name
        draw_state._draw_data['mesh_name'] = self._obj.data.name
        _arc_preview_from_geom(geom, p1_w, p2_w, geom['sweep'], 48, context)
        draw_state._draw_data['three_pt_picked_world'] = [
            p1_w.copy(),
            p2_w.copy(),
            bulge_hint.copy(),
        ]
        draw_state.register_3d_draw_handler()
        draw_state.refresh_edit_mesh_px_handler(context)
        _tag_view3d_redraw(context)

    def _modal_bulge(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            return self.cancel(context)
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            return self.cancel(context)
        if event.type in {'RET', 'NUMPAD_ENTER', 'LEFTMOUSE'} and event.value == 'PRESS':
            return self._finish_bulge_and_apply(context)
        if event.type == 'R' and event.value == 'PRESS':
            self.number_input.reset()
            status_bar.show_toggle_notice('Type', 'Radius')
            self._update_bulge_from_mouse(context)
            self._refresh_bulge_preview(context)
            self._update_bulge_header(context)
            return {'RUNNING_MODAL'}
        if event.type == 'V' and event.value == 'PRESS':
            self._snap_verts = not self._snap_verts
            status_bar.show_toggle_notice('Snap', 'ON' if self._snap_verts else 'OFF')
            if not self.number_input.has_value():
                self._update_bulge_from_mouse(context)
            self._refresh_bulge_preview(context)
            return {'RUNNING_MODAL'}
        if self.number_input.handle_event(event):
            try:
                typed = self.number_input.get_value(
                    initial_value=float(self._radius) * self.unit_scale_display_inv,
                )
                self._radius = max(float(typed) * self.unit_scale, 1e-9)
                self._apply_typed_numeric(context)
            except ValueError:
                pass
            self._refresh_bulge_preview(context)
            self._update_bulge_header(context)
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE':
            self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
            if not self.number_input.has_value():
                self._update_bulge_from_mouse(context)
                self._refresh_bulge_preview(context)
            self._update_bulge_header(context)
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}

    def _finish_bulge_and_apply(self, context):
        global _two_pt_arc_session
        picked = list(self._picked_indices)
        self._bulge_modal_teardown()
        status_bar.clear_message(context)
        viewport_header.clear(context)
        if len(picked) != 2 or self._bulge_w is None:
            _reset_two_pt_arc_live_state(context)
            _tag_view3d_redraw(context)
            return {'CANCELLED'}
        bulge_hint = self._bulge_side_hint(context)
        if bulge_hint is None:
            return {'CANCELLED'}
        if self.number_input.has_value():
            self._apply_typed_numeric(context)
        geom, p1_w, p2_w, _plane_n = self._current_bulge_geom(context)
        if geom is not None:
            self._sync_dims_from_geom(geom, p1_w, p2_w)
        _clear_two_pt_arc_preview()
        session_data = {
            'object_name': self._obj.name,
            'mesh_name': self._obj.data.name,
            'vert_indices': tuple(picked),
            'bulge_hint_w': tuple(bulge_hint),
            'center_w': tuple(self._center_w),
            'radius': float(self._radius),
            'created_vert_indices': [],
            'created_edge_keys': [],
            'applied': False,
        }
        if self.number_input.has_value():
            session_data['fixed_radius'] = float(self._radius)
        else:
            session_data['bulge_w'] = tuple(
                cp.project_onto_cursor_plane(context, Vector(self._bulge_w)),
            )
        _two_pt_arc_session = session_data
        if context.view_layer.objects.active != self._obj:
            context.view_layer.objects.active = self._obj
        result = self.execute(context)
        _tag_view3d_redraw(context)
        if 'CANCELLED' in result:
            return {'CANCELLED'}
        return {'FINISHED'}

    def check(self, context):
        self.execute(context)
        return True

    def execute(self, context):
        global _two_pt_arc_session
        if not _two_pt_circle_session_valid(context, _two_pt_arc_session):
            self.report({'WARNING'}, "Run the tool and pick two vertices first")
            return {'CANCELLED'}
        session = _two_pt_arc_session
        has_fixed = session.get('fixed_radius') is not None
        if has_fixed:
            if session.get('bulge_hint_w') is None:
                self.report({'WARNING'}, "Run the tool and set arc bulge first")
                return {'CANCELLED'}
        elif session.get('bulge_w') is None:
            self.report({'WARNING'}, "Run the tool and set arc bulge first")
            return {'CANCELLED'}
        obj = bpy.data.objects.get(session['object_name']) or context.edit_object or context.active_object
        if obj is None or obj.type != 'MESH':
            return {'CANCELLED'}
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        verts = _two_pt_verts_from_session(bm, session)
        if verts is None:
            self.report({'WARNING'}, "Definition vertices are no longer valid")
            return {'CANCELLED'}
        mw = obj.matrix_world
        _three_pt_remove_created_circle(bm, session)
        if not _two_pt_create_arc(
            context,
            bm,
            mw,
            verts,
            session,
            int(self.segments),
        ):
            self.report({'WARNING'}, "Could not build arc from the two points")
            return {'CANCELLED'}
        session['applied'] = True
        geom = _session_preview_geom(context, session)
        if geom is not None:
            self.radius = float(geom['radius'])
            self.center = tuple(geom['center'])
        elif session.get('radius') is not None and session.get('center_w') is not None:
            self.radius = float(session['radius'])
            self.center = tuple(session['center_w'])
        bmesh.update_edit_mesh(obj.data, loop_triangles=True)
        obj.update_tag(refresh={'DATA'})
        return {'FINISHED'}


classes = (
    ALEC_OT_two_point_arc,
    ALEC_OT_three_point_arc,
)
