"""Center + radius circle on the cursor plane (modal pick + redo panel)."""
from __future__ import annotations

import bpy
import bmesh
import math
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
    _tag_view3d_redraw,
    _three_pt_remove_created_circle,
)

_center_circle_session = None
_tan_tan_circle_session = None
_three_tan_circle_session = None

_EDGE_B_COLOR = (0.15, 0.85, 1.0, 0.95)
_EDGE_THIRD_COLOR = (1.0, 0.35, 0.9, 0.95)
_BISECTOR_COLOR = (1.0, 0.85, 0.2, 0.55)
_EDGE_PICK_RADIUS_PX = 14
_BISECTOR_GUIDE_SPAN_BU = 50.0


def clear_center_circle_session():
    global _center_circle_session
    _center_circle_session = None
    _clear_center_circle_preview()


def clear_tan_tan_radius_circle_session():
    global _tan_tan_circle_session
    _tan_tan_circle_session = None
    _clear_geom_circle_preview()


def clear_three_tan_circle_session():
    global _three_tan_circle_session
    _three_tan_circle_session = None
    _clear_geom_circle_preview()


def _clear_geom_circle_preview():
    draw_state._draw_data.pop('two_pt_circle_preview', None)
    draw_state._draw_data.pop('cursor_plane', None)
    draw_state._draw_data.pop('three_pt_picked_world', None)
    draw_state._draw_data.pop('draw_snap_ring', None)
    draw_state._draw_data.pop('draw_snap_source_screen', None)
    draw_state._draw_data.pop('trim_extend_state', None)
    if not draw_state.has_dim_overlay_data():
        draw_state.refresh_edit_mesh_px_handler(bpy.context)


def _clear_center_circle_preview():
    _clear_geom_circle_preview()


def _center_circle_session_valid(context, session) -> bool:
    if session is None:
        return False
    obj = context.active_object
    if obj is None or obj.type != 'MESH':
        return False
    return (
        obj.name == session.get('object_name')
        and obj.data.name == session.get('mesh_name')
    )


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


def _center_create_circle_ring(
    context,
    bm,
    mw,
    center_w,
    radius_bu: float,
    segments: int,
    session: dict,
) -> bool:
    inv_mw = mw.inverted_safe()
    center_w = _center_on_cursor_plane(context, center_w)
    _u, u_axis, v_axis = _center_circle_axes(context)
    radius_w = max(float(radius_bu), 1e-9)

    ring = []
    for i in range(segments):
        theta = (2.0 * math.pi * i) / segments
        co_w = (
            center_w
            + u_axis * (math.cos(theta) * radius_w)
            + v_axis * (math.sin(theta) * radius_w)
        )
        vert = bm.verts.new(inv_mw @ co_w)
        ring.append(vert)
        session['created_vert_indices'].append(vert.index)

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    for i in range(segments):
        try:
            edge = bm.edges.new((ring[i], ring[(i + 1) % segments]))
            session['created_edge_keys'].append(emh.bm_edge_key(edge))
        except ValueError:
            pass
    return len(session.get('created_edge_keys', [])) > 0


def _tan_tan_session_valid(context, session) -> bool:
    if session is None:
        return False
    obj = context.active_object
    if obj is None or obj.type != 'MESH':
        return False
    return (
        obj.name == session.get('object_name')
        and obj.data.name == session.get('mesh_name')
    )


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


def _create_circle_ring_from_geom(bm, mw, geom, segments: int, session: dict) -> bool:
    inv_mw = mw.inverted_safe()
    center_w = geom['center']
    u_axis = geom['u'].normalized()
    v_axis = geom['v'].normalized()
    radius_w = max(float(geom['radius']), 1e-9)
    ring = []
    for i in range(segments):
        theta = (2.0 * math.pi * i) / segments
        co_w = (
            center_w
            + u_axis * (math.cos(theta) * radius_w)
            + v_axis * (math.sin(theta) * radius_w)
        )
        vert = bm.verts.new(inv_mw @ co_w)
        ring.append(vert)
        session['created_vert_indices'].append(vert.index)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    for i in range(segments):
        try:
            edge = bm.edges.new((ring[i], ring[(i + 1) % segments]))
            session['created_edge_keys'].append(emh.bm_edge_key(edge))
        except ValueError:
            pass
    return len(session.get('created_edge_keys', [])) > 0


def _set_circle_preview(context, obj, center_w, radius_bu, rim_w=None):
    center_w = _center_on_cursor_plane(context, center_w)
    _u, u_axis, v_axis = _center_circle_axes(context)
    radius_w = max(float(radius_bu), 1e-9)
    if rim_w is None:
        rim_w = center_w + u_axis * radius_w
    draw_state._draw_data['object_name'] = obj.name
    draw_state._draw_data['mesh_name'] = obj.data.name
    draw_state._draw_data['two_pt_circle_preview'] = {
        'center': center_w.copy(),
        'u': u_axis.copy(),
        'v': v_axis.copy(),
        'radius': radius_w,
        'segments': 48,
        'p1': center_w.copy(),
        'p2': Vector(rim_w).copy(),
    }
    draw_state._draw_data['three_pt_picked_world'] = [center_w.copy(), Vector(rim_w).copy()]
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
        _clear_center_circle_preview()
        if context is not None:
            status_bar.clear_message(context)
            viewport_header.clear(context)

    def cancel(self, context):
        self._radius_modal_teardown()
        self._reset_live_state(context)
        _tag_view3d_redraw(context)
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
        _tag_view3d_redraw(context)
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
            threshold_px=_THREE_PT_PICK_RADIUS_PX,
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
                                _THREE_PT_SNAP_RING_RADIUS_PX,
                                0,
                            )
                except Exception:
                    pass
            draw_state.register_3d_draw_handler()
            draw_state.refresh_edit_mesh_px_handler(context)
            _tag_view3d_redraw(context)
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
        _tag_view3d_redraw(context)

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
                _THREE_PT_SNAP_RING_RADIUS_PX,
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
        _set_circle_preview(context, self._obj, center_w, self._radius, rim_w=rim_w)
        _tag_view3d_redraw(context)

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
            _tag_view3d_redraw(context)
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
        _clear_center_circle_preview()

        if context.view_layer.objects.active != self._obj:
            context.view_layer.objects.active = self._obj

        result = self.execute(context)
        _tag_view3d_redraw(context)
        return result

    def check(self, context):
        global _center_circle_session
        if _center_circle_session_valid(context, _center_circle_session):
            _center_circle_session['radius'] = float(self.radius)
        self.execute(context)
        return True

    def execute(self, context):
        global _center_circle_session
        if not _center_circle_session_valid(context, _center_circle_session):
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

        _three_pt_remove_created_circle(bm, session)

        if not _center_create_circle_ring(
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
        _clear_geom_circle_preview()
        if context is not None:
            status_bar.clear_message(context)
            viewport_header.clear(context)

    def cancel(self, context):
        self._radius_modal_teardown()
        self._reset_live_state(context)
        _tag_view3d_redraw(context)
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
        _tag_view3d_redraw(context)
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
                _clear_geom_circle_preview()
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
                threshold_px=_EDGE_PICK_RADIUS_PX,
                exclude_edges=[edge_a],
            )
            if edge_b is not None:
                ba = mw @ edge_b.verts[0].co
                bb = mw @ edge_b.verts[1].co
                ref_b = (ba.copy(), bb.copy())
            _push_edge_pick_draw(context, self._obj, ref_a, ref_b)
        _tag_view3d_redraw(context)

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
                _clear_geom_circle_preview()
                status_bar.set_message(context, _tan_tan_pick_status(0))
                _tag_view3d_redraw(context)
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
                threshold_px=_EDGE_PICK_RADIUS_PX,
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
            threshold_px=_EDGE_PICK_RADIUS_PX,
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
        _clear_geom_circle_preview()
        self._phase = 'radius'
        self.number_input = modal_handler.ModalNumberInput()
        self.unit_scale_display_inv = utils.length_bu_to_display_multiplier(context)
        self.unit_scale = utils.display_length_to_bu_multiplier(context)
        self.__class__._radius_modal_instance = self
        status_bar.install_shortcuts(self.__class__)
        self._refresh_radius_preview(context)
        status_bar.set_message(context, _tan_tan_radius_status())
        self._update_radius_header(context)
        _tag_view3d_redraw(context)

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
            _tag_view3d_redraw(context)
            return
        if self.number_input.has_value():
            self.radius = float(self._radius)
        else:
            self._radius = float(geom['radius'])
            self.radius = self._radius
        self.center = tuple(geom['center'])
        center_w = geom['center']
        rim_w = center_w + geom['u'] * geom['radius']
        _set_circle_preview(context, self._obj, center_w, geom['radius'], rim_w=rim_w)
        self._push_tan_tan_guides(context, lines, center_w)
        _tag_view3d_redraw(context)

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
            _tag_view3d_redraw(context)
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
        _clear_geom_circle_preview()

        if context.view_layer.objects.active != self._obj:
            context.view_layer.objects.active = self._obj

        result = self.execute(context)
        _tag_view3d_redraw(context)
        return result

    def check(self, context):
        global _tan_tan_circle_session
        if _tan_tan_session_valid(context, _tan_tan_circle_session):
            _tan_tan_circle_session['radius'] = float(self.radius)
            if self._center_w is not None:
                _tan_tan_circle_session['center_w'] = tuple(self._center_w)
        self.execute(context)
        return True

    def execute(self, context):
        global _tan_tan_circle_session
        if not _tan_tan_session_valid(context, _tan_tan_circle_session):
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

        _three_pt_remove_created_circle(bm, session)

        if not _create_circle_ring_from_geom(
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
        _clear_geom_circle_preview()
        if context is not None:
            status_bar.clear_message(context)

    def cancel(self, context):
        self._reset_live_state(context)
        _tag_view3d_redraw(context)
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
        _tag_view3d_redraw(context)
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
            _clear_geom_circle_preview()
            return

        edge_a = emh.bm_edge_from_key(bm, self._edge_a_key)
        if edge_a is None:
            self._edge_a_key = None
            _clear_geom_circle_preview()
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
            threshold_px=_EDGE_PICK_RADIUS_PX,
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
        _tag_view3d_redraw(context)

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
                _clear_geom_circle_preview()
                status_bar.set_message(context, _three_tan_pick_status(0))
                _tag_view3d_redraw(context)
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
                threshold_px=_EDGE_PICK_RADIUS_PX,
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
                threshold_px=_EDGE_PICK_RADIUS_PX,
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
            threshold_px=_EDGE_PICK_RADIUS_PX,
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
            _tag_view3d_redraw(context)
            return {'CANCELLED'}

        bm.edges.ensure_lookup_table()
        mw = self._obj.matrix_world
        edge_a = emh.bm_edge_from_key(bm, self._edge_a_key)
        edge_b = emh.bm_edge_from_key(bm, self._edge_b_key)
        edge_c = emh.bm_edge_from_key(bm, self._edge_c_key)
        if edge_a is None or edge_b is None or edge_c is None:
            self._reset_live_state(context)
            self.report({'WARNING'}, "Tangent edges are no longer valid")
            _tag_view3d_redraw(context)
            return {'CANCELLED'}

        result_geom = emh.triangle_incircle_from_three_edges(
            edge_a, edge_b, edge_c, mw,
        )
        if result_geom.get('invalid'):
            self.report({'WARNING'}, result_geom.get('reason', 'Could not build incircle'))
            _tag_view3d_redraw(context)
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
        _clear_geom_circle_preview()

        if context.view_layer.objects.active != self._obj:
            context.view_layer.objects.active = self._obj

        result = self.execute(context)
        _tag_view3d_redraw(context)
        return result

    def check(self, context):
        self.execute(context)
        return True

    def execute(self, context):
        global _three_tan_circle_session
        if not _tan_tan_session_valid(context, _three_tan_circle_session):
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

        _three_pt_remove_created_circle(bm, session)

        if not _create_circle_ring_from_geom(
            bm, obj.matrix_world, geom, int(self.segments), session,
        ):
            self.report({'WARNING'}, "Could not create circle edges")
            return {'CANCELLED'}

        session['applied'] = True
        bmesh.update_edit_mesh(obj.data, loop_triangles=True)
        obj.update_tag(refresh={'DATA'})
        return {'FINISHED'}


classes = (
    ALEC_OT_center_circle,
    ALEC_OT_tan_tan_radius_circle,
    ALEC_OT_three_tan_circle,
)
