"""Modal operator: Fillet/Chamfer between two mesh edges (one tool).

Workflow:
- All selection is cleared when the tool starts.
- Click first edge (click position fixes the corner-side vertex Va on edge A).
- Click second edge (click position fixes Vb on edge B).
- Move the mouse to size the radius â€” stable bisector-projection method.
  Radius is clamped so neither tangent point exceeds the outer vertex.
  Wheel adjusts segment count (1 = chamfer).
  Type a number and ENTER to set radius precisely; ENTER or LMB applies.
  ESC clears typed buffer or exits. RMB clears last pick.

Corner selection is derived purely from the two click positions â€” no separate
quadrant UI needed. The four geometric cases are handled automatically:
  1. Shared vertex (L): Va==Vb, standard arc, shared vertex removed.
  2. Not touching (V): Va extended toward apex if radius small, else split.
  3. Crossing (X): click on a segment half picks that quadrant at the intersection
     (param along edge vs. crossing point, not nearest endpoint).
     L/V/shared-apex still use nearest endpoint as corner-side.
  4. Parallel: fixed-radius semicircle; chord from Va/Vb (mid projected),
     bulge faces the corner-intent side (midpoint Vaâ€“Vb). Wheel adjusts segments.

r=0 â†’ CORNER mode: extend both edges to apex, weld into a sharp corner.
"""
import math
import bpy
import bmesh
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Vector

from ..modules import edit_mesh_draw_state as draw_state
from ..modules import edit_mesh_helpers as emh
from ..modules import modal_handler, status_bar, viewport_header
from ..modules.fillet_geometry import (
    _EPS,
    _ray_plane_intersect,
    compute_fillet_data,
    avg_edge_length,
    _apply_arc,
)


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
        'then second â€” the click position fixes which corner is filleted. '
        'Move mouse to set radius (clamped to edge length). Wheel: segments. '
        'Type r + Enter to apply. r=0 â†’ sharp corner at apex.'
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

        # Clear all selection â€” corner is determined by click positions only.
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
        avg = avg_edge_length(self._edge_a, self._edge_b, self._obj.matrix_world)
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
        # r = d Ã— sin(half_angle), stable for all approach angles.
        d = (hit - apex_w).dot(bis_unit_w)
        self._radius = max(0.0, d * sin_h)

    def _update_header(self, context):
        if context.area is None:
            return
        r = float(self._radius or 0.0)
        prv = getattr(self, '_preview', None) or {}

        if (
            self._both_edges_loaded()
            and prv.get('parallel')
            and not prv.get('invalid')
        ):
            r_val = float(prv.get('radius') or r)
            if self.number_input.value_str:
                viewport_header.set_numeric(
                    context,
                    main_label='Parallel r',
                    main_value=r_val,
                    typed_str=self.number_input.value_str,
                    suffix='',
                    secondary_text=f'seg={self._segments}',
                    initial_value=r_val,
                )
                return
            r_disp_parallel = viewport_header.format_length(context, r_val, precision=4)
            viewport_header.set(
                context,
                f'Parallel: {r_disp_parallel} (fixed D/2)  |  Segments={self._segments}',
            )
            return

        if r <= _EPS:
            primary = 'Corner'
        elif self._segments == 1:
            primary = 'Chamfer'
        else:
            primary = 'Fillet'

        r_disp = viewport_header.format_length(context, r, precision=4)

        if self.number_input.value_str:
            viewport_header.set_numeric(
                context,
                main_label=f'{primary} r',
                main_value=r,
                typed_str=self.number_input.value_str,
                suffix='',
                secondary_text=f'seg={self._segments}',
                initial_value=r,
            )
        else:
            viewport_header.set(
                context,
                f'{primary}: {r_disp}  |  segments={self._segments}',
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
                status_bar.show_toggle_notice("Seg", str(self._segments))
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
            self._preview = compute_fillet_data(
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
                status_bar.set_message(
                    context,
                    f"{label}: [Enter] apply  [Esc] cancel typing  "
                    f"[Wheel] segments  [RMB] clear edge",
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
            status_bar.set_message(context, msg)
        except Exception:
            pass

    def _cleanup(self, context):
        draw_state._draw_data.pop('trim_extend_state', None)
        status_bar.clear_all(context)
        if context.area is not None:
            context.area.tag_redraw()


classes = (ALEC_OT_fillet_edges,)
