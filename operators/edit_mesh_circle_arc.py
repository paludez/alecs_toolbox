"""Circle and arc construction tools (vertex pick, cursor plane, tangents)."""
from __future__ import annotations

import math

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
from .circle_arc_common import (
    EDGE_PICK_RADIUS_PX,
    PICK_RADIUS_PX,
    SNAP_RING_RADIUS_PX,
    append_closed_ring,
    circumcenter_world_from_session,
    clear_curve_preview_overlay,
    clear_vertex_pick_overlay,
    create_ring_from_geom,
    create_ring_from_three_points,
    create_ring_from_two_point_radius,
    create_ring_on_cursor_plane,
    deselect_all_mesh_elements,
    ensure_empty_at_world,
    mesh_edit_session_valid,
    pick_hovered_vert_index,
    refresh_vertex_pick_visual,
    remove_created_geometry,
    resolve_circ_center_empty_name,
    set_circle_frame_preview,
    set_circle_preview_simple,
    store_circumcircle_in_session,
    sync_empty_collections_with_mesh,
    tag_view3d_redraw,
    two_pt_points_on_cursor_plane,
    vertex_pick_status,
    verts_from_session,
)


# --- session state ---
_three_pt_circle_session = None
_three_pt_pick_session = None
_two_pt_circle_session = None
_two_pt_pick_session = None
_three_pt_arc_session = None
_three_pt_arc_pick_session = None
_two_pt_arc_session = None
_two_pt_arc_pick_session = None
_center_circle_session = None
_tan_tan_circle_session = None
_three_tan_circle_session = None

_EDGE_B_COLOR = (0.15, 0.85, 1.0, 0.95)
_EDGE_THIRD_COLOR = (1.0, 0.35, 0.9, 0.95)
_BISECTOR_COLOR = (1.0, 0.85, 0.2, 0.55)
_BISECTOR_GUIDE_SPAN_BU = 50.0


def clear_three_point_circle_session():
    global _three_pt_circle_session, _three_pt_pick_session
    _three_pt_circle_session = None
    _three_pt_pick_session = None
    clear_vertex_pick_overlay()


def clear_two_point_circle_session():
    global _two_pt_circle_session, _two_pt_pick_session
    _two_pt_circle_session = None
    _two_pt_pick_session = None
    clear_curve_preview_overlay(clear_picked_world=False)


def clear_three_point_arc_session():
    global _three_pt_arc_session, _three_pt_arc_pick_session
    _three_pt_arc_session = None
    _three_pt_arc_pick_session = None
    clear_vertex_pick_overlay()


def clear_center_circle_session():
    global _center_circle_session
    _center_circle_session = None
    clear_curve_preview_overlay()


def clear_tan_tan_radius_circle_session():
    global _tan_tan_circle_session
    _tan_tan_circle_session = None
    clear_curve_preview_overlay()


def clear_three_tan_circle_session():
    global _three_tan_circle_session
    _three_tan_circle_session = None
    clear_curve_preview_overlay()


def _reset_two_pt_arc_live_state(context=None):
    """Drop sessions, overlays, header/status so a new invoke can start clean."""
    global _two_pt_arc_session, _two_pt_arc_pick_session
    _two_pt_arc_session = None
    _two_pt_arc_pick_session = None
    clear_curve_preview_overlay()
    if context is not None:
        status_bar.clear_message(context)
        viewport_header.clear(context)


def clear_two_point_arc_session():
    _reset_two_pt_arc_live_state(bpy.context if bpy.context else None)


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
    verts = verts_from_session(bm, session, 2)
    if verts is None:
        return None
    p1_w, p2_w, plane_n = two_pt_points_on_cursor_plane(
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
    p1_w, p2_w, plane_n = two_pt_points_on_cursor_plane(
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
        refresh_vertex_pick_visual(context, obj, [], self._last_mouse)
        status_bar.set_message(context, vertex_pick_status('3pt Arc', 0, 3))
        context.window_manager.modal_handler_add(self)
        tag_view3d_redraw(context)
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
            clear_vertex_pick_overlay()
            status_bar.clear_message(context)
            tag_view3d_redraw(context)
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
            refresh_vertex_pick_visual(
                context, self._obj, _three_pt_arc_pick_session['picked_indices'], self._last_mouse,
            )
            return {'RUNNING_MODAL'}
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            picked = _three_pt_arc_pick_session['picked_indices']
            if picked:
                picked.pop()
                status_bar.set_message(context, vertex_pick_status('3pt Arc', len(picked), 3))
                refresh_vertex_pick_visual(context, self._obj, picked, self._last_mouse)
                return {'RUNNING_MODAL'}
            _three_pt_arc_pick_session = None
            clear_vertex_pick_overlay()
            status_bar.clear_message(context)
            tag_view3d_redraw(context)
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
            threshold_px=PICK_RADIUS_PX, exclude_indices=picked,
        )
        if vert is None:
            return False
        picked.append(vert.index)
        status_bar.set_message(context, vertex_pick_status('3pt Arc', len(picked), 3))
        refresh_vertex_pick_visual(context, self._obj, picked, self._last_mouse)
        return len(picked) >= 3

    def _finish_pick_and_apply(self, context):
        global _three_pt_arc_pick_session, _three_pt_arc_session
        picked = list(_three_pt_arc_pick_session['picked_indices']) if _three_pt_arc_pick_session else []
        _three_pt_arc_pick_session = None
        clear_vertex_pick_overlay()
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
        if not mesh_edit_session_valid(context, _three_pt_arc_session):
            self.report({'WARNING'}, "Run the tool and pick three vertices first")
            return {'CANCELLED'}
        session = _three_pt_arc_session
        obj = bpy.data.objects.get(session['object_name']) or context.edit_object or context.active_object
        if obj is None or obj.type != 'MESH':
            return {'CANCELLED'}
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        verts = verts_from_session(bm, session, 3)
        if verts is None:
            self.report({'WARNING'}, "Definition vertices are no longer valid")
            return {'CANCELLED'}
        remove_created_geometry(bm, session)
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
        tag_view3d_redraw(context)
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
        refresh_vertex_pick_visual(context, obj, [], self._last_mouse)
        status_bar.set_message(context, vertex_pick_status('2pt Arc', 0, 2))
        context.window_manager.modal_handler_add(self)
        tag_view3d_redraw(context)
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
            refresh_vertex_pick_visual(
                context, self._obj, _two_pt_arc_pick_session['picked_indices'], self._last_mouse,
            )
            return {'RUNNING_MODAL'}
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            picked = _two_pt_arc_pick_session['picked_indices']
            if picked:
                picked.pop()
                status_bar.set_message(context, vertex_pick_status('2pt Arc', len(picked), 2))
                refresh_vertex_pick_visual(context, self._obj, picked, self._last_mouse)
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
            threshold_px=PICK_RADIUS_PX, exclude_indices=picked,
        )
        if vert is None:
            return False
        picked.append(vert.index)
        status_bar.set_message(context, vertex_pick_status('2pt Arc', len(picked), 2))
        refresh_vertex_pick_visual(context, self._obj, picked, self._last_mouse)
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
        p1_w, p2_w, plane_n = two_pt_points_on_cursor_plane(context, mw, v0, v1)
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
        tag_view3d_redraw(context)

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
            threshold_px=PICK_RADIUS_PX,
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
                SNAP_RING_RADIUS_PX,
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
                    threshold_px=PICK_RADIUS_PX,
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
        return two_pt_points_on_cursor_plane(context, mw, v0, v1)

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
        tag_view3d_redraw(context)

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
            tag_view3d_redraw(context)
            return {'CANCELLED'}
        bulge_hint = self._bulge_side_hint(context)
        if bulge_hint is None:
            return {'CANCELLED'}
        if self.number_input.has_value():
            self._apply_typed_numeric(context)
        geom, p1_w, p2_w, _plane_n = self._current_bulge_geom(context)
        if geom is not None:
            self._sync_dims_from_geom(geom, p1_w, p2_w)
        clear_curve_preview_overlay()
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
        tag_view3d_redraw(context)
        if 'CANCELLED' in result:
            return {'CANCELLED'}
        return {'FINISHED'}

    def check(self, context):
        self.execute(context)
        return True

    def execute(self, context):
        global _two_pt_arc_session
        if not mesh_edit_session_valid(context, _two_pt_arc_session):
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
        verts = verts_from_session(bm, session, 2)
        if verts is None:
            self.report({'WARNING'}, "Definition vertices are no longer valid")
            return {'CANCELLED'}
        mw = obj.matrix_world
        remove_created_geometry(bm, session)
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




# --- vertex-pick circles ---

def _two_pt_radius_status_message() -> str:
    return (
        '2pt Circle: Move mouse or type radius  [LMB] Confirm  '
        '[RMB] Cancel  [Esc] Cancel  [R] Reset'
    )


class ALEC_OT_two_point_circle(bpy.types.Operator):
    """Pick two vertices, set radius, then build the circle (live tweak in redo panel)"""
    bl_idname = "alec.two_point_circle"
    bl_label = "2pt Circle"
    bl_options = {'REGISTER', 'UNDO'}

    radius: bpy.props.FloatProperty(
        name="Radius",
        description="Circle radius (minimum is half the distance between the two points)",
        min=0.0,
        default=1.0,
        unit='LENGTH',
    )  # type: ignore

    segments: bpy.props.IntProperty(
        name="Edges",
        description="Number of edges on the circle",
        min=3,
        max=256,
        default=32,
    )  # type: ignore

    anchor_point: bpy.props.IntProperty(
        name="Snap to Pick",
        description="Which picked vertex gets a circle vertex (1 = first, 2 = second)",
        min=1,
        max=2,
        default=1,
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        return emh.poll_active_mesh_edit_mode(context)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "radius")
        layout.prop(self, "segments")
        layout.prop(self, "anchor_point", slider=True)

    def invoke(self, context, event):
        global _two_pt_pick_session, _two_pt_circle_session
        _two_pt_circle_session = None

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

        _two_pt_pick_session = {
            'object_name': obj.name,
            'mesh_name': obj.data.name,
            'picked_indices': [],
        }

        self._obj = obj
        self._phase = 'pick'
        self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
        self._plane_n = Vector((0.0, 0.0, 1.0))
        self._bisect_sign = 1.0

        refresh_vertex_pick_visual(context, obj, [], self._last_mouse)
        status_bar.set_message(context, vertex_pick_status('2pt Circle', 0, 2))
        context.window_manager.modal_handler_add(self)
        tag_view3d_redraw(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MIDDLEMOUSE':
            return {'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}

        if self._phase == 'pick':
            return self._modal_pick(context, event)
        return self._modal_radius(context, event)

    def _modal_pick(self, context, event):
        global _two_pt_pick_session

        if _two_pt_pick_session is None:
            return {'CANCELLED'}

        if event.type == 'ESC' and event.value == 'PRESS':
            _two_pt_pick_session = None
            clear_curve_preview_overlay()
            draw_state._draw_data.pop('three_pt_picked_world', None)
            status_bar.clear_message(context)
            tag_view3d_redraw(context)
            return {'CANCELLED'}

        if event.type == 'MOUSEMOVE':
            self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
            refresh_vertex_pick_visual(
                context,
                self._obj,
                _two_pt_pick_session['picked_indices'],
                self._last_mouse,
            )
            return {'RUNNING_MODAL'}

        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            picked = _two_pt_pick_session['picked_indices']
            if picked:
                picked.pop()
                status_bar.set_message(
                    context, vertex_pick_status('2pt Circle', len(picked), 2),
                )
                refresh_vertex_pick_visual(
                    context, self._obj, picked, self._last_mouse,
                )
                return {'RUNNING_MODAL'}
            _two_pt_pick_session = None
            clear_curve_preview_overlay()
            draw_state._draw_data.pop('three_pt_picked_world', None)
            status_bar.clear_message(context)
            tag_view3d_redraw(context)
            return {'CANCELLED'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if self._on_pick_lmb(context):
                self._enter_radius_phase(context)
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    def _on_pick_lmb(self, context) -> bool:
        global _two_pt_pick_session
        if _two_pt_pick_session is None or context.region is None or context.region_data is None:
            return False
        if self._last_mouse is None:
            return False

        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return False
        bm.verts.ensure_lookup_table()
        mw = self._obj.matrix_world
        picked = _two_pt_pick_session['picked_indices']
        if len(picked) >= 2:
            return True

        vert, _d2 = emh.hovered_vert(
            bm,
            mw,
            context.region,
            context.region_data,
            self._last_mouse,
            threshold_px=PICK_RADIUS_PX,
            exclude_indices=picked,
        )
        if vert is None:
            return False

        picked.append(vert.index)
        status_bar.set_message(
            context, vertex_pick_status('2pt Circle', len(picked), 2),
        )
        refresh_vertex_pick_visual(context, self._obj, picked, self._last_mouse)
        return len(picked) >= 2

    def _enter_radius_phase(self, context):
        global _two_pt_pick_session

        picked = list(_two_pt_pick_session['picked_indices']) if _two_pt_pick_session else []
        _two_pt_pick_session = None
        draw_state._draw_data.pop('draw_snap_ring', None)
        draw_state._draw_data.pop('draw_snap_source_screen', None)

        if len(picked) != 2:
            return

        self._picked_indices = picked
        self._phase = 'radius'
        self.number_input = modal_handler.ModalNumberInput()
        self.unit_scale_display_inv = utils.length_bu_to_display_multiplier(context)
        self.unit_scale = utils.display_length_to_bu_multiplier(context)

        bm = bmesh.from_edit_mesh(self._obj.data)
        v0 = bm.verts[picked[0]]
        v1 = bm.verts[picked[1]]
        mw = self._obj.matrix_world
        p1_w, p2_w, plane_n = two_pt_points_on_cursor_plane(context, mw, v0, v1)
        self._plane_n = plane_n

        chord = (p2_w - p1_w).length
        if chord < 1e-9:
            self.report({'WARNING'}, "Points coincide on the cursor plane")
            self._phase = 'pick'
            return
        r_min = chord * 0.5
        self._radius = max(r_min * 1.25, r_min + 1e-6)
        self._bisect_sign = 1.0
        self._update_radius_from_mouse(context)
        if self._radius < r_min + 1e-9:
            self._radius = r_min + 1e-6
        self.radius = float(self._radius)

        status_bar.set_message(context, _two_pt_radius_status_message())
        self._update_two_pt_header(context)
        self._refresh_radius_preview(context)
        tag_view3d_redraw(context)

    def _mouse_hit_on_plane(self, context):
        if context.region is None or context.region_data is None or self._last_mouse is None:
            return None
        ray_o = region_2d_to_origin_3d(
            context.region, context.region_data, self._last_mouse,
        )
        ray_d = region_2d_to_vector_3d(
            context.region, context.region_data, self._last_mouse,
        )
        if ray_d.length_squared < 1e-18:
            return None
        return cp.intersect_cursor_plane(context, ray_o, ray_d)

    def _update_radius_from_mouse(self, context):
        hit = self._mouse_hit_on_plane(context)
        if hit is None:
            return
        bm = bmesh.from_edit_mesh(self._obj.data)
        v0 = bm.verts[self._picked_indices[0]]
        v1 = bm.verts[self._picked_indices[1]]
        mw = self._obj.matrix_world
        p1_w, p2_w, plane_n = two_pt_points_on_cursor_plane(context, mw, v0, v1)
        self._plane_n = plane_n
        result = emh.radius_from_plane_hit(p1_w, p2_w, hit, plane_n)
        if result[0] is None:
            return
        self._radius, self._bisect_sign = result
        self.radius = float(self._radius)
        self._refresh_radius_preview(context)

    def _refresh_radius_preview(self, context):
        bm = bmesh.from_edit_mesh(self._obj.data)
        v0 = bm.verts[self._picked_indices[0]]
        v1 = bm.verts[self._picked_indices[1]]
        mw = self._obj.matrix_world
        p1_w, p2_w, plane_n = two_pt_points_on_cursor_plane(context, mw, v0, v1)
        self._plane_n = plane_n
        radius_bu = float(getattr(self, '_radius', self.radius))
        geom = emh.two_point_circle_from_radius(
            p1_w, p2_w, radius_bu, plane_n, self._bisect_sign,
        )
        if geom is None:
            draw_state._draw_data.pop('two_pt_circle_preview', None)
            return

        draw_state._draw_data['object_name'] = self._obj.name
        draw_state._draw_data['mesh_name'] = self._obj.data.name
        draw_state._draw_data['two_pt_circle_preview'] = {
            'center': geom['center'].copy(),
            'u': geom['u'].copy(),
            'v': geom['v'].copy(),
            'radius': float(geom['radius']),
            'segments': 48,
            'p1': p1_w.copy(),
            'p2': p2_w.copy(),
        }
        draw_state._draw_data['three_pt_picked_world'] = [p1_w.copy(), p2_w.copy()]
        try:
            _n, u_ax, v_ax = cp.cursor_plane_axes(context)
            draw_state._draw_data['cursor_plane'] = (
                context.scene.cursor.location.copy(),
                u_ax,
                v_ax,
            )
        except Exception:
            draw_state._draw_data.pop('cursor_plane', None)
        draw_state.register_3d_draw_handler()
        draw_state.refresh_edit_mesh_px_handler(context)
        tag_view3d_redraw(context)

    def _update_two_pt_header(self, context):
        suffix = utils.unit_suffixes.get(context.scene.unit_settings.length_unit, '')
        radius_bu = float(getattr(self, '_radius', self.radius))
        viewport_header.set_numeric(
            context,
            main_label='Radius',
            main_value=radius_bu * self.unit_scale_display_inv,
            typed_str=self.number_input.value_str,
            suffix=suffix,
        )

    def _modal_radius(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            clear_curve_preview_overlay()
            draw_state._draw_data.pop('three_pt_picked_world', None)
            status_bar.clear_message(context)
            viewport_header.clear(context)
            tag_view3d_redraw(context)
            return {'CANCELLED'}

        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            clear_curve_preview_overlay()
            draw_state._draw_data.pop('three_pt_picked_world', None)
            status_bar.clear_message(context)
            viewport_header.clear(context)
            tag_view3d_redraw(context)
            return {'CANCELLED'}

        if event.type in {'RET', 'NUMPAD_ENTER', 'LEFTMOUSE'} and event.value == 'PRESS':
            return self._finish_radius_and_apply(context)

        if self.number_input.handle_event(event):
            try:
                typed = self.number_input.get_value(
                    initial_value=float(getattr(self, '_radius', self.radius))
                    * self.unit_scale_display_inv,
                )
                self._radius = max(float(typed) * self.unit_scale, 1e-9)
                self.radius = float(self._radius)
            except ValueError:
                pass
            self._refresh_radius_preview(context)
            self._update_two_pt_header(context)
            return {'RUNNING_MODAL'}

        if event.type == 'R' and event.value == 'PRESS':
            self.number_input.reset()
            self._update_radius_from_mouse(context)
            self._update_two_pt_header(context)
            return {'RUNNING_MODAL'}

        if event.type == 'MOUSEMOVE':
            self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
            if not self.number_input.has_value():
                self._update_radius_from_mouse(context)
            self._update_two_pt_header(context)
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    def _finish_radius_and_apply(self, context):
        global _two_pt_circle_session

        picked = list(self._picked_indices)
        clear_curve_preview_overlay()
        draw_state._draw_data.pop('three_pt_picked_world', None)
        status_bar.clear_message(context)
        viewport_header.clear(context)

        if len(picked) != 2:
            return {'CANCELLED'}

        radius_bu = float(getattr(self, '_radius', self.radius))
        self.radius = radius_bu

        _two_pt_circle_session = {
            'object_name': self._obj.name,
            'mesh_name': self._obj.data.name,
            'vert_indices': tuple(picked),
            'radius': radius_bu,
            'bisect_sign': float(self._bisect_sign),
            'created_vert_indices': [],
            'created_edge_keys': [],
            'applied': False,
        }

        if context.view_layer.objects.active != self._obj:
            context.view_layer.objects.active = self._obj

        result = self.execute(context)
        tag_view3d_redraw(context)
        return result

    def check(self, context):
        global _two_pt_circle_session
        if mesh_edit_session_valid(context, _two_pt_circle_session):
            _two_pt_circle_session['radius'] = float(self.radius)
            _two_pt_circle_session['bisect_sign'] = float(
                _two_pt_circle_session.get('bisect_sign', 1.0)
            )
        self.execute(context)
        return True

    def execute(self, context):
        global _two_pt_circle_session
        if not mesh_edit_session_valid(context, _two_pt_circle_session):
            self.report({'WARNING'}, "Run the tool and pick two vertices first")
            return {'CANCELLED'}

        session = _two_pt_circle_session
        obj = bpy.data.objects.get(session['object_name']) or context.edit_object or context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, "Target mesh is no longer available")
            return {'CANCELLED'}

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        definition_verts = verts_from_session(bm, session, 2)
        if definition_verts is None:
            self.report({'WARNING'}, "Definition vertices are no longer valid")
            return {'CANCELLED'}

        mw = obj.matrix_world
        p1_w, p2_w, _plane_n = two_pt_points_on_cursor_plane(
            context, mw, definition_verts[0], definition_verts[1],
        )
        r_min = (p2_w - p1_w).length * 0.5
        radius = max(float(self.radius), r_min + 1e-9)
        self.radius = radius
        session['radius'] = radius

        remove_created_geometry(bm, session)

        bisect_sign = float(session.get('bisect_sign', 1.0))

        if not create_ring_from_two_point_radius(
            context,
            bm,
            obj.matrix_world,
            definition_verts,
            radius,
            bisect_sign,
            int(self.segments),
            int(self.anchor_point) - 1,
            session,
        ):
            self.report({'WARNING'}, "Could not build circle from the two points")
            return {'CANCELLED'}

        session['applied'] = True
        bmesh.update_edit_mesh(obj.data, loop_triangles=True)
        obj.update_tag(refresh={'DATA'})
        return {'FINISHED'}


class ALEC_OT_three_point_circle(bpy.types.Operator):
    """Pick three vertices, then build the circumcircle (live tweak in redo panel)"""
    bl_idname = "alec.three_point_circle"
    bl_label = "3pt to Circle"
    bl_options = {'REGISTER', 'UNDO'}

    radius: bpy.props.FloatProperty(
        name="Raza",
        description="Circumcircle radius from the three picked vertices",
        min=0.0,
        default=0.0,
        unit='LENGTH',
    )  # type: ignore

    segments: bpy.props.IntProperty(
        name="Edges",
        description="Number of edges on the circumcircle",
        min=3,
        max=256,
        default=32,
    )  # type: ignore

    anchor_point: bpy.props.IntProperty(
        name="Snap to Pick",
        description=(
            "Which of the three picked vertices gets a circle vertex placed on it "
            "(1 = first picked, 2 = second, 3 = third)"
        ),
        min=1,
        max=3,
        default=1,
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        return emh.poll_active_mesh_edit_mode(context)

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.enabled = False
        row.prop(self, "radius")
        layout.prop(self, "segments")
        layout.prop(self, "anchor_point", slider=True)
        layout.operator(
            "alec.three_point_circle_empty_at_center",
            text="Empty at Center",
            icon='EMPTY_AXIS',
        )

    @staticmethod
    def _circumradius_from_session(bm, mw, session) -> float | None:
        verts = verts_from_session(bm, session, 3)
        if verts is None:
            return None
        points_w = [mw @ v.co for v in verts]
        circle = emh.circumcircle_from_three_points(points_w[0], points_w[1], points_w[2])
        if circle is None:
            return None
        return float(circle[1])

    def invoke(self, context, event):
        global _three_pt_pick_session, _three_pt_circle_session
        _three_pt_circle_session = None

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

        _three_pt_pick_session = {
            'object_name': obj.name,
            'mesh_name': obj.data.name,
            'picked_indices': [],
        }

        self._obj = obj
        self._last_mouse = (event.mouse_region_x, event.mouse_region_y)

        refresh_vertex_pick_visual(context, obj, [], self._last_mouse)
        status_bar.set_message(
            context, vertex_pick_status('3pt Circle', 0, 3),
        )
        context.window_manager.modal_handler_add(self)
        tag_view3d_redraw(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        global _three_pt_pick_session

        if event.type == 'MIDDLEMOUSE':
            return {'PASS_THROUGH'}

        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}

        if _three_pt_pick_session is None:
            return {'CANCELLED'}

        if event.type == 'ESC' and event.value == 'PRESS':
            _three_pt_pick_session = None
            clear_vertex_pick_overlay()
            status_bar.clear_message(context)
            tag_view3d_redraw(context)
            return {'CANCELLED'}

        if event.type == 'MOUSEMOVE':
            self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
            refresh_vertex_pick_visual(
                context,
                self._obj,
                _three_pt_pick_session['picked_indices'],
                self._last_mouse,
            )
            return {'RUNNING_MODAL'}

        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            picked = _three_pt_pick_session['picked_indices']
            if picked:
                picked.pop()
                status_bar.set_message(
                    context, vertex_pick_status('3pt Circle', len(picked), 3),
                )
                refresh_vertex_pick_visual(
                    context, self._obj, picked, self._last_mouse,
                )
                return {'RUNNING_MODAL'}
            _three_pt_pick_session = None
            clear_vertex_pick_overlay()
            status_bar.clear_message(context)
            tag_view3d_redraw(context)
            return {'CANCELLED'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if self._on_lmb_pick(context):
                return self._finish_pick_and_apply(context)
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    def _on_lmb_pick(self, context) -> bool:
        """Add hovered vertex to pick list. True when three points are chosen."""
        global _three_pt_pick_session
        if _three_pt_pick_session is None:
            return False
        if context.region is None or context.region_data is None:
            return False
        if self._last_mouse is None:
            return False

        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return False
        bm.verts.ensure_lookup_table()
        mw = self._obj.matrix_world

        picked = _three_pt_pick_session['picked_indices']
        if len(picked) >= 3:
            return True

        vert, _d2 = emh.hovered_vert(
            bm,
            mw,
            context.region,
            context.region_data,
            self._last_mouse,
            threshold_px=PICK_RADIUS_PX,
            exclude_indices=picked,
        )
        if vert is None:
            return False

        picked.append(vert.index)
        status_bar.set_message(
            context, vertex_pick_status('3pt Circle', len(picked), 3),
        )
        refresh_vertex_pick_visual(context, self._obj, picked, self._last_mouse)
        return len(picked) >= 3

    def _finish_pick_and_apply(self, context):
        global _three_pt_pick_session, _three_pt_circle_session

        picked = list(_three_pt_pick_session['picked_indices']) if _three_pt_pick_session else []
        _three_pt_pick_session = None
        clear_vertex_pick_overlay()
        status_bar.clear_message(context)

        if len(picked) != 3:
            return {'CANCELLED'}

        obj = self._obj
        _three_pt_circle_session = {
            'object_name': obj.name,
            'mesh_name': obj.data.name,
            'vert_indices': tuple(picked),
            'created_vert_indices': [],
            'created_edge_keys': [],
            'applied': False,
        }

        result = self.execute(context)
        tag_view3d_redraw(context)
        return result

    def check(self, context):
        self.execute(context)
        return True

    def execute(self, context):
        global _three_pt_circle_session
        if not mesh_edit_session_valid(context, _three_pt_circle_session):
            self.report(
                {'WARNING'},
                "Run the tool and pick three vertices first",
            )
            return {'CANCELLED'}

        session = _three_pt_circle_session
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        definition_verts = verts_from_session(bm, session, 3)
        if definition_verts is None:
            self.report({'WARNING'}, "Definition vertices are no longer valid")
            return {'CANCELLED'}

        radius_w = self._circumradius_from_session(bm, obj.matrix_world, session)
        if radius_w is not None:
            self.radius = radius_w

        remove_created_geometry(bm, session)

        if not create_ring_from_three_points(
            bm,
            obj.matrix_world,
            definition_verts,
            int(self.segments),
            int(self.anchor_point) - 1,
            session,
        ):
            self.report({'WARNING'}, "The three points are collinear")
            return {'CANCELLED'}

        if not store_circumcircle_in_session(
            session, obj.matrix_world, definition_verts,
        ):
            self.report({'WARNING'}, "The three points are collinear")
            return {'CANCELLED'}

        session['applied'] = True
        bmesh.update_edit_mesh(obj.data)
        return {'FINISHED'}


class ALEC_OT_three_point_circle_empty_at_center(bpy.types.Operator):
    """Place an empty at the circumcenter of the 3pt circle (redo panel)."""
    bl_idname = "alec.three_point_circle_empty_at_center"
    bl_label = "Empty at Center"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        session = _three_pt_circle_session
        if session is None or not session.get('applied'):
            return False
        if not emh.poll_active_mesh_edit_mode(context):
            return False
        return mesh_edit_session_valid(context, session)

    def execute(self, context):
        global _three_pt_circle_session
        session = _three_pt_circle_session
        if session is None or not session.get('applied'):
            self.report({'WARNING'}, "Run 3pt to Circle and pick three vertices first")
            return {'CANCELLED'}
        if not mesh_edit_session_valid(context, session):
            self.report({'WARNING'}, "Circle session is no longer valid for this mesh")
            return {'CANCELLED'}

        stored = session.get('center_w')
        if stored is not None:
            center_w = Vector(stored)
        else:
            center_w = circumcenter_world_from_session(context, session)
        if center_w is None:
            self.report({'WARNING'}, "The three points are collinear")
            return {'CANCELLED'}

        mesh_obj = bpy.data.objects.get(session['object_name']) or context.active_object
        if mesh_obj is None:
            return {'CANCELLED'}

        radius_w = float(session.get('radius_w') or 0.25)
        display_size = max(0.15, radius_w * 0.12)

        try:
            empty = ensure_empty_at_world(
                context, mesh_obj, center_w, display_size,
            )
        except RuntimeError as exc:
            self.report({'ERROR'}, f"Could not create empty: {exc}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Empty '{empty.name}' at circle center")
        return {'FINISHED'}






# --- cursor-plane / tangent circles ---

def _center_pick_status_message() -> str:
    return (
        'Center Circle: Click center (vertex or plane)  '
        '[RMB] Cancel  [Esc] Cancel'
    )


def _center_radius_status_message() -> str:
    return (
        'Center Circle: Move mouse or type radius  [R] Radius  [V] Snap  '
        '[LMB] Confirm  [RMB] Cancel  [Esc] Cancel'
    )


def _center_circle_axes(context):
    plane_n, u_axis, v_axis = cp.cursor_plane_axes(context)
    return plane_n, u_axis, v_axis


def _center_on_cursor_plane(context, center_w) -> Vector:
    return cp.project_onto_cursor_plane(context, Vector(center_w))


def _edge_lines_on_cursor_plane(context, mw, edge_a, edge_b, click_a_w=None, click_b_w=None):
    return emh.tan_tan_oriented_lines(
        context, mw, edge_a, edge_b, click_a_w=click_a_w, click_b_w=click_b_w,
    )


def _push_edge_pick_draw(context, obj, ref_a, ref_b=None):
    state = {'ref_edge': (ref_a[0].copy(), ref_a[1].copy())}
    extra = []
    if ref_b is not None:
        extra.append(((ref_b[0].copy(), ref_b[1].copy()), _EDGE_B_COLOR))
        state['extra_lines'] = extra
    draw_state._draw_data['object_name'] = obj.name
    draw_state._draw_data['mesh_name'] = obj.data.name
    draw_state._draw_data['trim_extend_state'] = state
    draw_state.register_3d_draw_handler()
    draw_state.refresh_edit_mesh_px_handler(context)


class ALEC_OT_center_circle(bpy.types.Operator):
    """Pick center on the cursor plane, then set radius with mouse or numeric input"""
    bl_idname = "alec.center_circle"
    bl_label = "Center Circle"
    bl_options = {'REGISTER', 'UNDO'}

    _radius_modal_instance = None

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
        min=3,
        max=256,
        default=32,
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        return emh.poll_active_mesh_edit_mode(context)

    @classmethod
    def draw_status_bar(cls, panel, context):
        inst = cls._radius_modal_instance
        if inst is None or getattr(inst, '_phase', '') != 'radius':
            return
        status_bar.draw_shortcuts(panel.layout, inst._radius_status_items())

    def _radius_status_items(self):
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
        col.prop(self, "center")
        col.prop(self, "radius")
        layout.prop(self, "segments")

    def _reset_live_state(self, context):
        global _center_circle_session
        _center_circle_session = None
        clear_curve_preview_overlay()
        if context is not None:
            status_bar.clear_message(context)
            viewport_header.clear(context)

    def cancel(self, context):
        self._radius_modal_teardown()
        self._reset_live_state(context)
        tag_view3d_redraw(context)
        return {'CANCELLED'}

    def _radius_modal_teardown(self):
        if self.__class__._radius_modal_instance is self:
            self.__class__._radius_modal_instance = None
        try:
            status_bar.uninstall_shortcuts(self.__class__)
        except Exception:
            pass

    def invoke(self, context, event):
        self._reset_live_state(context)
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

        self._obj = obj
        self._phase = 'center'
        self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
        self._center_w = None
        self._center_vert_index = None
        self._radius = 1.0
        self._snap_verts = True
        self._hover_center_w = None

        status_bar.set_message(context, _center_pick_status_message())
        context.window_manager.modal_handler_add(self)
        tag_view3d_redraw(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MIDDLEMOUSE':
            return {'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if self._phase == 'center':
            return self._modal_center(context, event)
        return self._modal_radius(context, event)

    def _mouse_hit_on_plane(self, context):
        if context.region is None or context.region_data is None or self._last_mouse is None:
            return None
        ray_o = region_2d_to_origin_3d(
            context.region, context.region_data, self._last_mouse,
        )
        ray_d = region_2d_to_vector_3d(
            context.region, context.region_data, self._last_mouse,
        )
        if ray_d.length_squared < 1e-18:
            return None
        return cp.intersect_cursor_plane(context, ray_o, ray_d)

    def _hovered_vert(self, context, bm):
        if context.region is None or context.region_data is None or self._last_mouse is None:
            return None
        vert, _d2 = emh.hovered_vert(
            bm,
            self._obj.matrix_world,
            context.region,
            context.region_data,
            self._last_mouse,
            threshold_px=PICK_RADIUS_PX,
        )
        return vert

    def _resolve_center_hit(self, context, bm=None):
        if context.region is None or context.region_data is None or self._last_mouse is None:
            return None, None
        if bm is None:
            try:
                bm = bmesh.from_edit_mesh(self._obj.data)
            except Exception:
                bm = None
        if bm is not None:
            bm.verts.ensure_lookup_table()
            vert = self._hovered_vert(context, bm)
            if vert is not None:
                co_w = cp.project_onto_cursor_plane(
                    context, self._obj.matrix_world @ vert.co,
                )
                return co_w, vert.index
        hit = self._mouse_hit_on_plane(context)
        if hit is not None:
            return hit, None
        return None, None

    def _modal_center(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            return self.cancel(context)
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            return self.cancel(context)
        if event.type == 'MOUSEMOVE':
            self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
            hit, _idx = self._resolve_center_hit(context)
            self._hover_center_w = hit.copy() if hit is not None else None
            draw_state._draw_data.pop('draw_snap_ring', None)
            if self._hover_center_w is not None:
                draw_state._draw_data['three_pt_picked_world'] = [self._hover_center_w.copy()]
            else:
                draw_state._draw_data.pop('three_pt_picked_world', None)
            if context.region is not None and context.region_data is not None:
                try:
                    bm = bmesh.from_edit_mesh(self._obj.data)
                    bm.verts.ensure_lookup_table()
                    vert = self._hovered_vert(context, bm)
                    if vert is not None:
                        p2d = location_3d_to_region_2d(
                            context.region,
                            context.region_data,
                            self._obj.matrix_world @ vert.co,
                        )
                        if p2d is not None:
                            draw_state._draw_data['draw_snap_ring'] = (
                                float(p2d.x),
                                float(p2d.y),
                                SNAP_RING_RADIUS_PX,
                                0,
                            )
                except Exception:
                    pass
            draw_state.register_3d_draw_handler()
            draw_state.refresh_edit_mesh_px_handler(context)
            tag_view3d_redraw(context)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            try:
                bm = bmesh.from_edit_mesh(self._obj.data)
            except Exception:
                return {'RUNNING_MODAL'}
            hit, vert_idx = self._resolve_center_hit(context, bm)
            if hit is not None:
                self._center_w = hit.copy()
                self._center_vert_index = vert_idx
                self._enter_radius_phase(context)
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}

    def _enter_radius_phase(self, context):
        draw_state._draw_data.pop('draw_snap_ring', None)
        draw_state._draw_data.pop('draw_snap_source_screen', None)
        self._phase = 'radius'
        self.number_input = modal_handler.ModalNumberInput()
        self.unit_scale_display_inv = utils.length_bu_to_display_multiplier(context)
        self.unit_scale = utils.display_length_to_bu_multiplier(context)
        self._snap_verts = True
        self.__class__._radius_modal_instance = self
        status_bar.install_shortcuts(self.__class__)
        self._update_radius_from_mouse(context)
        if self._radius < 1e-6:
            self._radius = 1.0
        self.radius = float(self._radius)
        self.center = tuple(self._center_w)
        status_bar.set_message(context, _center_radius_status_message())
        self._update_radius_header(context)
        self._refresh_radius_preview(context)
        tag_view3d_redraw(context)

    def _update_radius_snap_ring(self, context):
        draw_state._draw_data.pop('draw_snap_ring', None)
        if not self._snap_verts or context.region is None or context.region_data is None:
            return
        if self._last_mouse is None:
            return
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return
        bm.verts.ensure_lookup_table()
        vert = self._hovered_vert(context, bm)
        if vert is None:
            return
        p2d = location_3d_to_region_2d(
            context.region, context.region_data, self._obj.matrix_world @ vert.co,
        )
        if p2d is not None:
            draw_state._draw_data['draw_snap_ring'] = (
                float(p2d.x),
                float(p2d.y),
                SNAP_RING_RADIUS_PX,
                0,
            )

    def _resolve_radius_hit(self, context):
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
                vert = self._hovered_vert(context, bm)
                if vert is not None:
                    return cp.project_onto_cursor_plane(
                        context, self._obj.matrix_world @ vert.co,
                    )
        return self._mouse_hit_on_plane(context)

    def _update_radius_from_mouse(self, context):
        if self._center_w is None:
            return
        hit = self._resolve_radius_hit(context)
        if hit is None:
            return
        center_w = _center_on_cursor_plane(context, self._center_w)
        self._radius = max((Vector(hit) - center_w).length, 1e-9)
        self.radius = float(self._radius)

    def _refresh_radius_preview(self, context):
        if self._center_w is None:
            return
        self._update_radius_snap_ring(context)
        center_w = _center_on_cursor_plane(context, self._center_w)
        hit = self._resolve_radius_hit(context)
        rim_w = hit if hit is not None else center_w + Vector((1.0, 0.0, 0.0))
        set_circle_preview_simple(context, self._obj, center_w, self._radius, rim_w=rim_w)
        tag_view3d_redraw(context)

    def _update_radius_header(self, context):
        suffix = utils.unit_suffixes.get(context.scene.unit_settings.length_unit, '')
        viewport_header.set_numeric(
            context,
            main_label='Radius',
            main_value=float(self._radius) * self.unit_scale_display_inv,
            typed_str=self.number_input.value_str,
            suffix=suffix,
        )

    def _modal_radius(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            return self.cancel(context)
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            return self.cancel(context)
        if event.type in {'RET', 'NUMPAD_ENTER', 'LEFTMOUSE'} and event.value == 'PRESS':
            return self._finish_radius_and_apply(context)
        if event.type == 'R' and event.value == 'PRESS':
            self.number_input.reset()
            status_bar.show_toggle_notice('Type', 'Radius')
            self._update_radius_from_mouse(context)
            self._refresh_radius_preview(context)
            self._update_radius_header(context)
            return {'RUNNING_MODAL'}
        if event.type == 'V' and event.value == 'PRESS':
            self._snap_verts = not self._snap_verts
            status_bar.show_toggle_notice('Snap', 'ON' if self._snap_verts else 'OFF')
            if not self.number_input.has_value():
                self._update_radius_from_mouse(context)
            self._refresh_radius_preview(context)
            return {'RUNNING_MODAL'}
        if self.number_input.handle_event(event):
            try:
                typed = self.number_input.get_value(
                    initial_value=float(self._radius) * self.unit_scale_display_inv,
                )
                self._radius = max(float(typed) * self.unit_scale, 1e-9)
                self.radius = float(self._radius)
            except ValueError:
                pass
            self._refresh_radius_preview(context)
            self._update_radius_header(context)
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE':
            self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
            if not self.number_input.has_value():
                self._update_radius_from_mouse(context)
                self._refresh_radius_preview(context)
            self._update_radius_header(context)
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}

    def _finish_radius_and_apply(self, context):
        global _center_circle_session
        self._radius_modal_teardown()
        status_bar.clear_message(context)
        viewport_header.clear(context)

        if self._center_w is None:
            self._reset_live_state(context)
            tag_view3d_redraw(context)
            return {'CANCELLED'}

        center_w = _center_on_cursor_plane(context, self._center_w)
        radius_bu = max(float(self._radius), 1e-9)
        self.radius = radius_bu
        self.center = tuple(center_w)

        vert_indices = ()
        if self._center_vert_index is not None:
            vert_indices = (int(self._center_vert_index),)

        _center_circle_session = {
            'object_name': self._obj.name,
            'mesh_name': self._obj.data.name,
            'center_w': tuple(center_w),
            'radius': radius_bu,
            'vert_indices': vert_indices,
            'created_vert_indices': [],
            'created_edge_keys': [],
            'applied': False,
        }
        clear_curve_preview_overlay()

        if context.view_layer.objects.active != self._obj:
            context.view_layer.objects.active = self._obj

        result = self.execute(context)
        tag_view3d_redraw(context)
        return result

    def check(self, context):
        global _center_circle_session
        if mesh_edit_session_valid(context, _center_circle_session):
            _center_circle_session['radius'] = float(self.radius)
        self.execute(context)
        return True

    def execute(self, context):
        global _center_circle_session
        if not mesh_edit_session_valid(context, _center_circle_session):
            self.report({'WARNING'}, "Run the tool and set center and radius first")
            return {'CANCELLED'}

        session = _center_circle_session
        obj = bpy.data.objects.get(session['object_name']) or context.edit_object or context.active_object
        if obj is None or obj.type != 'MESH':
            return {'CANCELLED'}

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        center_w = _center_on_cursor_plane(context, Vector(session['center_w']))
        radius_bu = max(float(self.radius), 1e-9)
        self.radius = radius_bu
        session['radius'] = radius_bu
        self.center = tuple(center_w)
        session['center_w'] = tuple(center_w)

        remove_created_geometry(bm, session)

        if not create_ring_on_cursor_plane(
            context,
            bm,
            obj.matrix_world,
            center_w,
            radius_bu,
            int(self.segments),
            session,
        ):
            self.report({'WARNING'}, "Could not build circle")
            return {'CANCELLED'}

        session['applied'] = True
        bmesh.update_edit_mesh(obj.data, loop_triangles=True)
        obj.update_tag(refresh={'DATA'})
        return {'FINISHED'}


def _tan_tan_pick_status(n: int) -> str:
    if n <= 0:
        return 'Tan Tan Circle: Click first tangent edge  [RMB] Cancel  [Esc] Cancel'
    if n == 1:
        return 'Tan Tan Circle: Click second tangent edge  [RMB] Undo  [Esc] Cancel'
    return 'Tan Tan Circle'


def _tan_tan_radius_status() -> str:
    return (
        'Tan Tan Circle: Move mouse or type radius  [R] Radius  '
        '[LMB] Confirm  [RMB] Cancel  [Esc] Cancel'
    )


class ALEC_OT_tan_tan_radius_circle(bpy.types.Operator):
    """Pick two edges as tangents, then set circle radius (cursor plane)"""
    bl_idname = "alec.tan_tan_radius_circle"
    bl_label = "Tan Tan Circle"
    bl_options = {'REGISTER', 'UNDO'}

    _radius_modal_instance = None

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
        min=3,
        max=256,
        default=32,
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        return emh.poll_active_mesh_edit_mode(context)

    @classmethod
    def draw_status_bar(cls, panel, context):
        inst = cls._radius_modal_instance
        if inst is None or getattr(inst, '_phase', '') != 'radius':
            return
        status_bar.draw_shortcuts(panel.layout, inst._radius_status_items())

    def _radius_status_items(self):
        return [
            ("Radius", "[R]", self.number_input.has_value()),
            None,
            ("Confirm", "[LMB]"),
            ("Cancel", "[Esc]"),
        ]

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.enabled = False
        col.prop(self, "center")
        col.prop(self, "radius")
        layout.prop(self, "segments")

    def _reset_live_state(self, context):
        global _tan_tan_circle_session
        _tan_tan_circle_session = None
        clear_curve_preview_overlay()
        if context is not None:
            status_bar.clear_message(context)
            viewport_header.clear(context)

    def cancel(self, context):
        self._radius_modal_teardown()
        self._reset_live_state(context)
        tag_view3d_redraw(context)
        return {'CANCELLED'}

    def _radius_modal_teardown(self):
        if self.__class__._radius_modal_instance is self:
            self.__class__._radius_modal_instance = None
        try:
            status_bar.uninstall_shortcuts(self.__class__)
        except Exception:
            pass

    def invoke(self, context, event):
        self._reset_live_state(context)
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

        self._obj = obj
        self._phase = 'pick'
        self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
        self._edge_a_key = None
        self._edge_b_key = None
        self._click_a_w = None
        self._click_b_w = None
        self._center_w = None
        self._hint_w = None
        self._radius = 1.0

        status_bar.set_message(context, _tan_tan_pick_status(0))
        context.window_manager.modal_handler_add(self)
        tag_view3d_redraw(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MIDDLEMOUSE':
            return {'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if self._phase == 'pick':
            return self._modal_pick(context, event)
        return self._modal_radius(context, event)

    def _refresh_pick_visual(self, context):
        if context.region is None or context.region_data is None or self._last_mouse is None:
            return
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return
        bm.edges.ensure_lookup_table()
        mw = self._obj.matrix_world

        ref_b = None
        if self._edge_a_key is not None:
            edge_a = emh.bm_edge_from_key(bm, self._edge_a_key)
            if edge_a is None:
                self._edge_a_key = None
                clear_curve_preview_overlay()
                return
            ra = mw @ edge_a.verts[0].co
            rb = mw @ edge_a.verts[1].co
            ref_a = (ra.copy(), rb.copy())
            edge_b, _t, _d2 = emh.hovered_edge(
                bm,
                mw,
                context.region,
                context.region_data,
                self._last_mouse,
                threshold_px=EDGE_PICK_RADIUS_PX,
                exclude_edges=[edge_a],
            )
            if edge_b is not None:
                ba = mw @ edge_b.verts[0].co
                bb = mw @ edge_b.verts[1].co
                ref_b = (ba.copy(), bb.copy())
            _push_edge_pick_draw(context, self._obj, ref_a, ref_b)
        tag_view3d_redraw(context)

    def _modal_pick(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            return self.cancel(context)
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            if self._edge_b_key is not None:
                self._edge_b_key = None
                self._click_b_w = None
                status_bar.set_message(context, _tan_tan_pick_status(1))
                self._refresh_pick_visual(context)
                return {'RUNNING_MODAL'}
            if self._edge_a_key is not None:
                self._edge_a_key = None
                self._click_a_w = None
                clear_curve_preview_overlay()
                status_bar.set_message(context, _tan_tan_pick_status(0))
                tag_view3d_redraw(context)
                return {'RUNNING_MODAL'}
            return self.cancel(context)
        if event.type == 'MOUSEMOVE':
            self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
            self._refresh_pick_visual(context)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if self._on_pick_lmb(context):
                self._enter_radius_phase(context)
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}

    def _on_pick_lmb(self, context) -> bool:
        if context.region is None or context.region_data is None or self._last_mouse is None:
            return False
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return False
        bm.edges.ensure_lookup_table()
        mw = self._obj.matrix_world

        if self._edge_a_key is None:
            edge, t, _d2 = emh.hovered_edge(
                bm,
                mw,
                context.region,
                context.region_data,
                self._last_mouse,
                threshold_px=EDGE_PICK_RADIUS_PX,
            )
            if edge is None:
                return False
            self._edge_a_key = emh.bm_edge_key(edge)
            v0_w = mw @ edge.verts[0].co
            v1_w = mw @ edge.verts[1].co
            self._click_a_w = v0_w.lerp(v1_w, t if t is not None else 0.5)
            status_bar.set_message(context, _tan_tan_pick_status(1))
            self._refresh_pick_visual(context)
            return False

        edge_a = emh.bm_edge_from_key(bm, self._edge_a_key)
        if edge_a is None:
            self._edge_a_key = None
            return False
        edge, t, _d2 = emh.hovered_edge(
            bm,
            mw,
            context.region,
            context.region_data,
            self._last_mouse,
            threshold_px=EDGE_PICK_RADIUS_PX,
            exclude_edges=[edge_a],
        )
        if edge is None:
            return False
        self._edge_b_key = emh.bm_edge_key(edge)
        v0_w = mw @ edge.verts[0].co
        v1_w = mw @ edge.verts[1].co
        self._click_b_w = v0_w.lerp(v1_w, t if t is not None else 0.5)
        return True

    def _edge_pair_lines(self, context):
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return None
        bm.edges.ensure_lookup_table()
        edge_a = emh.bm_edge_from_key(bm, self._edge_a_key)
        edge_b = emh.bm_edge_from_key(bm, self._edge_b_key)
        if edge_a is None or edge_b is None:
            return None
        return _edge_lines_on_cursor_plane(
            context,
            self._obj.matrix_world,
            edge_a,
            edge_b,
            click_a_w=self._click_a_w,
            click_b_w=self._click_b_w,
        )

    def _enter_radius_phase(self, context):
        clear_curve_preview_overlay()
        self._phase = 'radius'
        self.number_input = modal_handler.ModalNumberInput()
        self.unit_scale_display_inv = utils.length_bu_to_display_multiplier(context)
        self.unit_scale = utils.display_length_to_bu_multiplier(context)
        self.__class__._radius_modal_instance = self
        status_bar.install_shortcuts(self.__class__)
        self._refresh_radius_preview(context)
        status_bar.set_message(context, _tan_tan_radius_status())
        self._update_radius_header(context)
        tag_view3d_redraw(context)

    def _mouse_hit_on_plane(self, context):
        if context.region is None or context.region_data is None or self._last_mouse is None:
            return None
        ray_o = region_2d_to_origin_3d(
            context.region, context.region_data, self._last_mouse,
        )
        ray_d = region_2d_to_vector_3d(
            context.region, context.region_data, self._last_mouse,
        )
        if ray_d.length_squared < 1e-18:
            return None
        return cp.intersect_cursor_plane(context, ray_o, ray_d)

    def _mouse_hint_on_plane(self, context):
        hit = self._mouse_hit_on_plane(context)
        if hit is None:
            return None
        return cp.project_onto_cursor_plane(context, Vector(hit))

    def _resolve_hint_w(self, context, for_confirm: bool = False):
        if for_confirm and self._hint_w is not None:
            return self._hint_w.copy()
        hint = self._mouse_hint_on_plane(context)
        if hint is not None:
            self._hint_w = hint.copy()
        return hint

    def _build_geom(self, context, for_confirm: bool = False):
        lines = self._edge_pair_lines(context)
        hint = self._resolve_hint_w(context, for_confirm=for_confirm)
        if lines is None or hint is None:
            return None
        plane_n, o1, d1, o2, d2 = lines
        r_min = emh.min_radius_circle_tangent_two_lines(o1, d1, o2, d2, plane_n)

        if self.number_input.has_value():
            radius_bu = max(float(self._radius), r_min)
            geom = emh.tan_tan_circle_geom(
                o1, d1, o2, d2, plane_n, hint, radius_bu=radius_bu,
            )
            if geom is None and float(self._radius) < r_min:
                radius_bu = r_min
                self._radius = r_min
                geom = emh.tan_tan_circle_geom(
                    o1, d1, o2, d2, plane_n, hint, radius_bu=radius_bu,
                )
        elif for_confirm and self._center_w is not None:
            geom = emh.tan_tan_circle_geom(
                o1, d1, o2, d2, plane_n, hint, center_w=self._center_w,
            )
        else:
            geom = emh.tan_tan_circle_geom(o1, d1, o2, d2, plane_n, hint)

        if geom is not None:
            self._center_w = geom['center'].copy()
        return geom

    def _push_tan_tan_guides(self, context, lines, center_w=None):
        if lines is None:
            return
        plane_n, o1, d1, o2, d2 = lines
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return
        bm.edges.ensure_lookup_table()
        mw = self._obj.matrix_world
        edge_a = emh.bm_edge_from_key(bm, self._edge_a_key)
        edge_b = emh.bm_edge_from_key(bm, self._edge_b_key)
        if edge_a is None or edge_b is None:
            return
        ra = mw @ edge_a.verts[0].co
        rb = mw @ edge_a.verts[1].co
        ba = mw @ edge_b.verts[0].co
        bb = mw @ edge_b.verts[1].co
        extra = [((ba.copy(), bb.copy()), _EDGE_B_COLOR)]
        for seg in emh.tan_tan_bisector_segments(
            o1, d1, o2, d2, plane_n, span=_BISECTOR_GUIDE_SPAN_BU,
        ):
            extra.append((seg, _BISECTOR_COLOR))
        state = {
            'ref_edge': (ra.copy(), rb.copy()),
            'extra_lines': extra,
        }
        if center_w is not None:
            state['hit_point'] = Vector(center_w).copy()
        draw_state._draw_data['object_name'] = self._obj.name
        draw_state._draw_data['mesh_name'] = self._obj.data.name
        draw_state._draw_data['trim_extend_state'] = state
        draw_state.register_3d_draw_handler()
        draw_state.refresh_edit_mesh_px_handler(context)

    def _refresh_radius_preview(self, context):
        lines = self._edge_pair_lines(context)
        geom = self._build_geom(context)
        if geom is None:
            draw_state._draw_data.pop('two_pt_circle_preview', None)
            self._push_tan_tan_guides(context, lines, self._center_w)
            tag_view3d_redraw(context)
            return
        if self.number_input.has_value():
            self.radius = float(self._radius)
        else:
            self._radius = float(geom['radius'])
            self.radius = self._radius
        self.center = tuple(geom['center'])
        center_w = geom['center']
        rim_w = center_w + geom['u'] * geom['radius']
        set_circle_preview_simple(context, self._obj, center_w, geom['radius'], rim_w=rim_w)
        self._push_tan_tan_guides(context, lines, center_w)
        tag_view3d_redraw(context)

    def _update_radius_header(self, context):
        suffix = utils.unit_suffixes.get(context.scene.unit_settings.length_unit, '')
        viewport_header.set_numeric(
            context,
            main_label='Radius',
            main_value=float(self._radius) * self.unit_scale_display_inv,
            typed_str=self.number_input.value_str,
            suffix=suffix,
        )

    def _modal_radius(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            return self.cancel(context)
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            return self.cancel(context)
        if event.type in {'RET', 'NUMPAD_ENTER', 'LEFTMOUSE'} and event.value == 'PRESS':
            return self._finish_radius_and_apply(context)
        if event.type == 'R' and event.value == 'PRESS':
            self.number_input.reset()
            status_bar.show_toggle_notice('Type', 'Radius')
            self._refresh_radius_preview(context)
            self._update_radius_header(context)
            return {'RUNNING_MODAL'}
        if self.number_input.handle_event(event):
            try:
                typed = self.number_input.get_value(
                    initial_value=float(self._radius) * self.unit_scale_display_inv,
                )
                self._radius = max(float(typed) * self.unit_scale, 1e-9)
                self.radius = float(self._radius)
            except ValueError:
                pass
            self._refresh_radius_preview(context)
            self._update_radius_header(context)
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE':
            self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
            self._refresh_radius_preview(context)
            self._update_radius_header(context)
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}

    def _finish_radius_and_apply(self, context):
        global _tan_tan_circle_session
        self._radius_modal_teardown()
        status_bar.clear_message(context)
        viewport_header.clear(context)

        geom = self._build_geom(context, for_confirm=True)
        if geom is None:
            self._reset_live_state(context)
            self.report({'WARNING'}, "Could not build circle from the two edges")
            tag_view3d_redraw(context)
            return {'CANCELLED'}

        if self.number_input.has_value():
            self.radius = float(self._radius)
        else:
            self._radius = float(geom['radius'])
            self.radius = self._radius
        self.center = tuple(geom['center'])
        hint_w = self._hint_w if self._hint_w is not None else geom['center']

        _tan_tan_circle_session = {
            'object_name': self._obj.name,
            'mesh_name': self._obj.data.name,
            'edge_a_key': self._edge_a_key,
            'edge_b_key': self._edge_b_key,
            'center_w': tuple(geom['center']),
            'hint_w': tuple(hint_w),
            'radius': float(self.radius),
            'vert_indices': (),
            'created_vert_indices': [],
            'created_edge_keys': [],
            'applied': False,
        }
        clear_curve_preview_overlay()

        if context.view_layer.objects.active != self._obj:
            context.view_layer.objects.active = self._obj

        result = self.execute(context)
        tag_view3d_redraw(context)
        return result

    def check(self, context):
        global _tan_tan_circle_session
        if mesh_edit_session_valid(context, _tan_tan_circle_session):
            _tan_tan_circle_session['radius'] = float(self.radius)
            if self._center_w is not None:
                _tan_tan_circle_session['center_w'] = tuple(self._center_w)
        self.execute(context)
        return True

    def execute(self, context):
        global _tan_tan_circle_session
        if not mesh_edit_session_valid(context, _tan_tan_circle_session):
            self.report({'WARNING'}, "Run the tool and pick two tangent edges first")
            return {'CANCELLED'}

        session = _tan_tan_circle_session
        obj = bpy.data.objects.get(session['object_name']) or context.edit_object or context.active_object
        if obj is None or obj.type != 'MESH':
            return {'CANCELLED'}

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        edge_a = emh.bm_edge_from_key(bm, session.get('edge_a_key'))
        edge_b = emh.bm_edge_from_key(bm, session.get('edge_b_key'))
        if edge_a is None or edge_b is None:
            self.report({'WARNING'}, "Tangent edges are no longer valid")
            return {'CANCELLED'}

        lines = _edge_lines_on_cursor_plane(context, obj.matrix_world, edge_a, edge_b)
        if lines is None:
            self.report({'WARNING'}, "Edges are degenerate on the cursor plane")
            return {'CANCELLED'}

        plane_n, o1, d1, o2, d2 = lines
        hint_w = cp.project_onto_cursor_plane(
            context,
            Vector(session.get('hint_w') or session.get('center_w') or (0.0, 0.0, 0.0)),
        )
        center_w = cp.project_onto_cursor_plane(
            context, Vector(session.get('center_w') or hint_w),
        )
        r_min = emh.min_radius_circle_tangent_two_lines(o1, d1, o2, d2, plane_n)
        radius_bu = max(float(self.radius), r_min)

        geom = emh.tan_tan_circle_geom(
            o1, d1, o2, d2, plane_n, hint_w, radius_bu=radius_bu,
        )
        if geom is None:
            geom = emh.tan_tan_circle_geom(o1, d1, o2, d2, plane_n, hint_w)
        if geom is None:
            self.report({'WARNING'}, "Could not build circle tangent to both edges")
            return {'CANCELLED'}

        self.radius = float(geom['radius'])
        session['radius'] = float(geom['radius'])
        self.center = tuple(geom['center'])
        session['center_w'] = tuple(geom['center'])
        session['hint_w'] = tuple(hint_w)

        remove_created_geometry(bm, session)

        if not create_ring_from_geom(
            bm, obj.matrix_world, geom, int(self.segments), session,
        ):
            self.report({'WARNING'}, "Could not create circle edges")
            return {'CANCELLED'}

        session['applied'] = True
        bmesh.update_edit_mesh(obj.data, loop_triangles=True)
        obj.update_tag(refresh={'DATA'})
        return {'FINISHED'}


def _three_tan_pick_status(n: int) -> str:
    if n <= 0:
        return '3Tan Circle: Click edge 1  [RMB] Cancel  [Esc] Cancel'
    if n == 1:
        return '3Tan Circle: Click edge 2  [RMB] Undo  [Esc] Cancel'
    if n == 2:
        return '3Tan Circle: Click edge 3  [RMB] Undo  [Esc] Cancel'
    return '3Tan Circle'


class ALEC_OT_three_tan_circle(bpy.types.Operator):
    """Pick three edges; incircle in their plane is created automatically."""
    bl_idname = "alec.three_tan_circle"
    bl_label = "3Tan Circle"
    bl_options = {'REGISTER', 'UNDO'}

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
        min=3,
        max=256,
        default=32,
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        return emh.poll_active_mesh_edit_mode(context)

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.enabled = False
        col.prop(self, "center")
        col.prop(self, "radius")
        layout.prop(self, "segments")

    def _reset_live_state(self, context):
        global _three_tan_circle_session
        _three_tan_circle_session = None
        clear_curve_preview_overlay()
        if context is not None:
            status_bar.clear_message(context)

    def cancel(self, context):
        self._reset_live_state(context)
        tag_view3d_redraw(context)
        return {'CANCELLED'}

    def invoke(self, context, event):
        self._reset_live_state(context)
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

        self._obj = obj
        self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
        self._edge_a_key = None
        self._edge_b_key = None
        self._edge_c_key = None

        status_bar.set_message(context, _three_tan_pick_status(0))
        context.window_manager.modal_handler_add(self)
        tag_view3d_redraw(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MIDDLEMOUSE':
            return {'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        return self._modal_pick(context, event)

    def _refresh_pick_visual(self, context):
        if context.region is None or context.region_data is None or self._last_mouse is None:
            return
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return
        bm.edges.ensure_lookup_table()
        mw = self._obj.matrix_world

        if self._edge_a_key is None:
            clear_curve_preview_overlay()
            return

        edge_a = emh.bm_edge_from_key(bm, self._edge_a_key)
        if edge_a is None:
            self._edge_a_key = None
            clear_curve_preview_overlay()
            return
        ra = mw @ edge_a.verts[0].co
        rb = mw @ edge_a.verts[1].co
        ref_a = (ra.copy(), rb.copy())
        extra = []
        exclude = [edge_a]

        if self._edge_b_key is not None:
            edge_b = emh.bm_edge_from_key(bm, self._edge_b_key)
            if edge_b is not None:
                ba = mw @ edge_b.verts[0].co
                bb = mw @ edge_b.verts[1].co
                extra.append(((ba.copy(), bb.copy()), _EDGE_B_COLOR))
                exclude.append(edge_b)

        if self._edge_c_key is not None:
            edge_c = emh.bm_edge_from_key(bm, self._edge_c_key)
            if edge_c is not None:
                ca = mw @ edge_c.verts[0].co
                cb = mw @ edge_c.verts[1].co
                extra.append(((ca.copy(), cb.copy()), _EDGE_THIRD_COLOR))
                exclude.append(edge_c)

        hover, _t, _d2 = emh.hovered_edge(
            bm,
            mw,
            context.region,
            context.region_data,
            self._last_mouse,
            threshold_px=EDGE_PICK_RADIUS_PX,
            exclude_edges=exclude,
        )
        if hover is not None:
            ha = mw @ hover.verts[0].co
            hb = mw @ hover.verts[1].co
            color = _EDGE_THIRD_COLOR if len(exclude) >= 3 else _EDGE_B_COLOR
            extra.append(((ha.copy(), hb.copy()), color))

        draw_state._draw_data['object_name'] = self._obj.name
        draw_state._draw_data['mesh_name'] = self._obj.data.name
        draw_state._draw_data['trim_extend_state'] = {
            'ref_edge': (ref_a[0].copy(), ref_a[1].copy()),
            'extra_lines': extra,
        }
        draw_state.register_3d_draw_handler()
        draw_state.refresh_edit_mesh_px_handler(context)
        tag_view3d_redraw(context)

    def _modal_pick(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            return self.cancel(context)
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            if self._edge_c_key is not None:
                self._edge_c_key = None
                status_bar.set_message(context, _three_tan_pick_status(2))
                self._refresh_pick_visual(context)
                return {'RUNNING_MODAL'}
            if self._edge_b_key is not None:
                self._edge_b_key = None
                status_bar.set_message(context, _three_tan_pick_status(1))
                self._refresh_pick_visual(context)
                return {'RUNNING_MODAL'}
            if self._edge_a_key is not None:
                self._edge_a_key = None
                clear_curve_preview_overlay()
                status_bar.set_message(context, _three_tan_pick_status(0))
                tag_view3d_redraw(context)
                return {'RUNNING_MODAL'}
            return self.cancel(context)
        if event.type == 'MOUSEMOVE':
            self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
            self._refresh_pick_visual(context)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if self._on_pick_lmb(context):
                return self._finish_and_apply(context)
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}

    def _on_pick_lmb(self, context) -> bool:
        if context.region is None or context.region_data is None or self._last_mouse is None:
            return False
        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            return False
        bm.edges.ensure_lookup_table()
        mw = self._obj.matrix_world

        if self._edge_a_key is None:
            edge, _t, _d2 = emh.hovered_edge(
                bm, mw, context.region, context.region_data, self._last_mouse,
                threshold_px=EDGE_PICK_RADIUS_PX,
            )
            if edge is None:
                return False
            self._edge_a_key = emh.bm_edge_key(edge)
            status_bar.set_message(context, _three_tan_pick_status(1))
            self._refresh_pick_visual(context)
            return False

        if self._edge_b_key is None:
            edge_a = emh.bm_edge_from_key(bm, self._edge_a_key)
            if edge_a is None:
                self._edge_a_key = None
                return False
            edge, _t, _d2 = emh.hovered_edge(
                bm, mw, context.region, context.region_data, self._last_mouse,
                threshold_px=EDGE_PICK_RADIUS_PX,
                exclude_edges=[edge_a],
            )
            if edge is None:
                return False
            self._edge_b_key = emh.bm_edge_key(edge)
            status_bar.set_message(context, _three_tan_pick_status(2))
            self._refresh_pick_visual(context)
            return False

        edge_a = emh.bm_edge_from_key(bm, self._edge_a_key)
        edge_b = emh.bm_edge_from_key(bm, self._edge_b_key)
        if edge_a is None or edge_b is None:
            return False
        edge, _t, _d2 = emh.hovered_edge(
            bm, mw, context.region, context.region_data, self._last_mouse,
            threshold_px=EDGE_PICK_RADIUS_PX,
            exclude_edges=[edge_a, edge_b],
        )
        if edge is None:
            return False
        self._edge_c_key = emh.bm_edge_key(edge)
        return True

    def _finish_and_apply(self, context):
        global _three_tan_circle_session
        status_bar.clear_message(context)

        try:
            bm = bmesh.from_edit_mesh(self._obj.data)
        except Exception:
            self._reset_live_state(context)
            self.report({'ERROR'}, "Could not access edit mesh")
            tag_view3d_redraw(context)
            return {'CANCELLED'}

        bm.edges.ensure_lookup_table()
        mw = self._obj.matrix_world
        edge_a = emh.bm_edge_from_key(bm, self._edge_a_key)
        edge_b = emh.bm_edge_from_key(bm, self._edge_b_key)
        edge_c = emh.bm_edge_from_key(bm, self._edge_c_key)
        if edge_a is None or edge_b is None or edge_c is None:
            self._reset_live_state(context)
            self.report({'WARNING'}, "Tangent edges are no longer valid")
            tag_view3d_redraw(context)
            return {'CANCELLED'}

        result_geom = emh.triangle_incircle_from_three_edges(
            edge_a, edge_b, edge_c, mw,
        )
        if result_geom.get('invalid'):
            self.report({'WARNING'}, result_geom.get('reason', 'Could not build incircle'))
            tag_view3d_redraw(context)
            return {'RUNNING_MODAL'}

        geom = result_geom
        self.radius = float(geom['radius'])
        self.center = tuple(geom['center'])

        _three_tan_circle_session = {
            'object_name': self._obj.name,
            'mesh_name': self._obj.data.name,
            'edge_a_key': self._edge_a_key,
            'edge_b_key': self._edge_b_key,
            'edge_c_key': self._edge_c_key,
            'geom': {
                'center': tuple(geom['center']),
                'radius': float(geom['radius']),
                'u': tuple(geom['u']),
                'v': tuple(geom['v']),
                'plane_n': tuple(geom['plane_n']),
            },
            'vert_indices': (),
            'created_vert_indices': [],
            'created_edge_keys': [],
            'applied': False,
        }
        clear_curve_preview_overlay()

        if context.view_layer.objects.active != self._obj:
            context.view_layer.objects.active = self._obj

        result = self.execute(context)
        tag_view3d_redraw(context)
        return result

    def check(self, context):
        self.execute(context)
        return True

    def execute(self, context):
        global _three_tan_circle_session
        if not mesh_edit_session_valid(context, _three_tan_circle_session):
            self.report({'WARNING'}, "Run the tool and pick three tangent edges first")
            return {'CANCELLED'}

        session = _three_tan_circle_session
        obj = bpy.data.objects.get(session['object_name']) or context.edit_object or context.active_object
        if obj is None or obj.type != 'MESH':
            return {'CANCELLED'}

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        edge_a = emh.bm_edge_from_key(bm, session.get('edge_a_key'))
        edge_b = emh.bm_edge_from_key(bm, session.get('edge_b_key'))
        edge_c = emh.bm_edge_from_key(bm, session.get('edge_c_key'))
        if edge_a is None or edge_b is None or edge_c is None:
            self.report({'WARNING'}, "Tangent edges are no longer valid")
            return {'CANCELLED'}

        result_geom = emh.triangle_incircle_from_three_edges(
            edge_a, edge_b, edge_c, obj.matrix_world,
        )
        if result_geom.get('invalid'):
            stored = session.get('geom')
            if stored is None:
                self.report({'WARNING'}, result_geom.get('reason', 'Could not build incircle'))
                return {'CANCELLED'}
            geom = {
                'center': Vector(stored['center']),
                'radius': float(stored['radius']),
                'u': Vector(stored['u']),
                'v': Vector(stored['v']),
                'plane_n': Vector(stored['plane_n']),
            }
        else:
            geom = result_geom
            session['geom'] = {
                'center': tuple(geom['center']),
                'radius': float(geom['radius']),
                'u': tuple(geom['u']),
                'v': tuple(geom['v']),
                'plane_n': tuple(geom['plane_n']),
            }

        self.radius = float(geom['radius'])
        self.center = tuple(geom['center'])

        remove_created_geometry(bm, session)

        if not create_ring_from_geom(
            bm, obj.matrix_world, geom, int(self.segments), session,
        ):
            self.report({'WARNING'}, "Could not create circle edges")
            return {'CANCELLED'}

        session['applied'] = True
        bmesh.update_edit_mesh(obj.data, loop_triangles=True)
        obj.update_tag(refresh={'DATA'})
        return {'FINISHED'}



classes = (
    ALEC_OT_two_point_arc,
    ALEC_OT_three_point_arc,
    ALEC_OT_two_point_circle,
    ALEC_OT_three_point_circle,
    ALEC_OT_three_point_circle_empty_at_center,
    ALEC_OT_center_circle,
    ALEC_OT_tan_tan_radius_circle,
    ALEC_OT_three_tan_circle,
)
