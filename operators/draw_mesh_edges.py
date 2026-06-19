"""Modal operator: draw polylines as real mesh edges on the 3D cursor work plane."""
import math
import time
import bpy
import bmesh
from mathutils import Matrix, Vector
from bpy_extras.view3d_utils import (
    region_2d_to_origin_3d,
    region_2d_to_vector_3d,
    location_3d_to_region_2d,
)

from ..modules import edit_mesh_draw_state as draw_state
from ..modules import cursor_plane as cp
from ..modules import draw_mesh_snap_cache as snap_cache
from ..modules import modal_handler, status_bar, viewport_header
from ..modules.transform_orientation import orientation_matrix_world

_PREVIEW_MIN_INTERVAL = 1.0 / 60.0


class ALEC_OT_draw_mesh_edges(bpy.types.Operator):
    """Draw polylines on the 3D cursor work plane. Snaps verts/mids/perp (from chain); [Shift] ortho;
    [A] type angle vs last edge (Enter locks); [B] toggle 90° vs last edge (needs 2+ chain verts).
    [Q] toggles free 3D preview (viewport ray vs mesh, else depth through chain, else plane).
    Outside X-ray / wire shading, snaps skip geometry behind first viewport-ray hit (opaque depth).
    [X/Y/Z] axis; [V]/[W] snap; type length like edge-length (mouse when no digits,
    digits + Enter commits); [C] close; [Bksp] undoes vert or clears typing; [RMB]
    / close snap finishes; plain [Enter] exits; [Esc] clears typing or exits."""
    bl_idname = "alec.draw_mesh_edges"
    bl_label = "Draw Mesh Edges"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        self._chain_vert_indices: list[int] = []
        self._chains_history: list[list[int]] = []
        self._preview_world_pos: Vector | None = None
        self._preview_is_snap: bool = False
        self._preview_is_ortho: bool = False
        self._preview_snap_vert_index: int | None = None
        self._screen_snap_radius_px = 12
        self._created_object = False
        self._ortho_on: bool = False
        self._axis_lock: str | None = None
        self._snap_verts_on: bool = True
        self._snap_other_on: bool = False
        self._ignore_draw_plane: bool = False
        self.number_input = modal_handler.ModalNumberInput()
        self.angle_input = modal_handler.ModalNumberInput()
        self._edge_angle_deg: float | None = None
        self._typing_angle: bool = False
        self._last_event_mouse: tuple[int, int] | None = (
            event.mouse_region_x,
            event.mouse_region_y,
        )
        self._snap_cache = snap_cache.DrawMeshSnapCache()
        self._last_preview_time = 0.0
        self._world_snap_warned = False

        if context.mode == "EDIT_MESH" and context.active_object is not None and context.active_object.type == "MESH":
            self._obj = context.active_object
        else:
            me = bpy.data.meshes.new("AlecDrawnEdges")
            obj = bpy.data.objects.new(me.name, me)
            context.collection.objects.link(obj)
            for o in context.selected_objects:
                o.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
            if context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.mode_set(mode='EDIT')
            self._obj = obj
            self._created_object = True

        draw_state._draw_data['object_name'] = self._obj.name
        draw_state._draw_data['mesh_name'] = self._obj.data.name
        draw_state._draw_data['draw_rubber_band'] = None
        draw_state.register_3d_draw_handler()
        draw_state.refresh_edit_mesh_px_handler(context)

        self._update_cursor_plane_visual(context)
        self._set_status(context)
        self._update_area_header(context)

        context.window_manager.modal_handler_add(self)
        if context.area is not None:
            context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        _nav_pass_types = {
            'MIDDLEMOUSE',
            'WHEELUPMOUSE',
            'WHEELDOWNMOUSE',
            'TRACKPADPAN',
            'TRACKPADZOOM',
            'TRACKPADSCROLL',
        }
        if event.type in _nav_pass_types:
            refresh_after_nav = False
            if event.type == 'MIDDLEMOUSE' and event.value == 'RELEASE':
                refresh_after_nav = True
            elif (
                event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}
                and event.value == 'PRESS'
            ):
                refresh_after_nav = True
            elif event.type == 'TRACKPADSCROLL' and event.value == 'PRESS':
                refresh_after_nav = True
            elif event.type == 'TRACKPADPAN' and event.value == 'RELEASE':
                refresh_after_nav = True
            elif event.type == 'TRACKPADZOOM' and event.value == 'RELEASE':
                refresh_after_nav = True
            if refresh_after_nav and self._last_event_mouse is not None:
                self._refresh_preview(context)
            return {'PASS_THROUGH'}

        if event.type == 'ESC' and event.value == 'PRESS':
            if self._chain_vert_indices and (
                self.number_input.has_value()
                or self.angle_input.has_value()
                or self._typing_angle
            ):
                self.number_input.reset()
                self.angle_input.reset()
                self._typing_angle = False
                self._refresh_preview(context)
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            if self._chain_vert_indices and self._edge_angle_deg is not None:
                self._edge_angle_deg = None
                self._refresh_preview(context)
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            cancelled = (
                self._created_object
                and not self._chain_vert_indices
                and not self._chains_history
            )
            self._cleanup(context, cancelled=cancelled)
            return {'CANCELLED'} if cancelled else {'FINISHED'}

        if (
            event.type in {'RET', 'NUMPAD_ENTER'}
            and event.value == 'PRESS'
            and self._chain_vert_indices
        ):
            if self.angle_input.has_value() or self._typing_angle:
                if self._apply_typed_angle(context):
                    status_bar.show_toggle_notice("Angle", f"{self._edge_angle_deg:g}°")
                self._refresh_preview(context)
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            if self.number_input.has_value():
                if self._apply_typed_vertex(context):
                    self.number_input.reset()
                self._refresh_preview(context)
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}

        if event.type == 'MOUSEMOVE':
            if context.region is None or context.region_data is None:
                return {'RUNNING_MODAL'}
            if self._chain_vert_indices and (
                self.number_input.has_value()
                or self.angle_input.has_value()
                or self._typing_angle
            ):
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            new_mouse = (event.mouse_region_x, event.mouse_region_y)
            if new_mouse == self._last_event_mouse:
                return {'RUNNING_MODAL'}
            self._last_event_mouse = new_mouse
            now = time.monotonic()
            if now - self._last_preview_time < _PREVIEW_MIN_INTERVAL:
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            self._last_preview_time = now
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if event.type == 'BACK_SPACE' and event.value == 'PRESS':
            if self._chain_vert_indices and (
                self.angle_input.has_value() or self._typing_angle
            ):
                self.angle_input.value_str = self.angle_input.value_str[:-1]
                if not self.angle_input.value_str:
                    self._typing_angle = False
                self._refresh_preview(context)
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            if self._chain_vert_indices and self.number_input.has_value():
                self.number_input.value_str = self.number_input.value_str[:-1]
                self._refresh_preview(context)
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            self._undo_last_vert(context)
            return {'RUNNING_MODAL'}

        _modal_reserved = {
            'ESC',
            'RET',
            'NUMPAD_ENTER',
            'BACK_SPACE',
            'LEFTMOUSE',
            'RIGHTMOUSE',
            'LEFT_SHIFT',
            'RIGHT_SHIFT',
            'C',
            'V',
            'W',
            'Q',
            'X',
            'Y',
            'Z',
            'A',
            'B',
            'MIDDLEMOUSE',
            'WHEELUPMOUSE',
            'WHEELDOWNMOUSE',
            'TRACKPADPAN',
            'TRACKPADZOOM',
            'TRACKPADSCROLL',
            'MOUSEMOVE',
            'TAB',
            'INBETWEEN_MOUSEMOVE',
        }
        if (
            event.value == 'PRESS'
            and self._chain_vert_indices
            and context.area is not None
            and event.type not in _modal_reserved
        ):
            if self._typing_angle:
                if self.angle_input.handle_event(event):
                    self._refresh_preview(context)
                    if context.area is not None:
                        context.area.tag_redraw()
                    return {'RUNNING_MODAL'}
            elif self.number_input.handle_event(event):
                self._refresh_preview(context)
                if context.area is not None:
                    context.area.tag_redraw()
                return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if context.region is not None and context.region_data is not None:
                self._last_event_mouse = (event.mouse_region_x, event.mouse_region_y)
                self._refresh_preview(context)
            if self._on_click(context):
                self._cleanup(context, cancelled=False)
                return {'FINISHED'}
            return {'RUNNING_MODAL'}

        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            self._end_chain()
            self._cleanup(context, cancelled=False)
            return {'FINISHED'}

        if event.type == 'C' and event.value == 'PRESS':
            if len(self._chain_vert_indices) >= 3:
                self._close_chain(context)
                self._cleanup(context, cancelled=False)
                return {'FINISHED'}
            return {'RUNNING_MODAL'}

        if event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT'} and event.value == 'PRESS':
            self._ortho_on = not self._ortho_on
            status_bar.show_toggle_notice("Ortho", "ON" if self._ortho_on else "OFF")
            self._set_status(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if event.type == 'V' and event.value == 'PRESS':
            self._snap_verts_on = not self._snap_verts_on
            status_bar.show_toggle_notice("Obj Snap", "ON" if self._snap_verts_on else "OFF")
            self._set_status(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if event.type == 'W' and event.value == 'PRESS':
            self._snap_other_on = not self._snap_other_on
            status_bar.show_toggle_notice("World Snap", "ON" if self._snap_other_on else "OFF")
            self._set_status(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if event.type == 'Q' and event.value == 'PRESS':
            self._ignore_draw_plane = not self._ignore_draw_plane
            status_bar.show_toggle_notice("Draw", "3D" if self._ignore_draw_plane else "Plane")
            self._update_cursor_plane_visual(context)
            self._set_status(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if event.type == 'A' and event.value == 'PRESS':
            if len(self._chain_vert_indices) < 2:
                status_bar.show_toggle_notice("Angle", "need 2 verts")
                return {'RUNNING_MODAL'}
            self._typing_angle = True
            self._edge_angle_deg = None
            self.angle_input.reset()
            self.number_input.reset()
            status_bar.show_toggle_notice("Angle", "type °")
            self._set_status(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if event.type == 'B' and event.value == 'PRESS':
            if len(self._chain_vert_indices) < 2:
                status_bar.show_toggle_notice("90°", "need 2 verts")
                return {'RUNNING_MODAL'}
            if self._edge_angle_deg == 90.0:
                self._edge_angle_deg = None
                status_bar.show_toggle_notice("90°", "OFF")
            else:
                self._edge_angle_deg = 90.0
                self._typing_angle = False
                self.angle_input.reset()
                self.number_input.reset()
                status_bar.show_toggle_notice("90°", "ON")
            self._set_status(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if event.type in {'X', 'Y', 'Z'} and event.value == 'PRESS':
            key = event.type
            if self._axis_lock == key:
                self._axis_lock = None
                status_bar.show_toggle_notice("Axis", "off")
            else:
                self._axis_lock = key
                status_bar.show_toggle_notice("Axis", key)
            self._set_status(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            self._cleanup(context, cancelled=False)
            return {'FINISHED'}

        return {'RUNNING_MODAL'}

    def _mouse_segment_geometry(
        self, context
    ) -> tuple[Vector, Vector, Vector, float] | None:
        last_world = self._last_chain_world_pos()
        if last_world is None or self._last_event_mouse is None:
            return None
        raw_pos, _s, _i, _o, _a = self._resolve_3d_position(
            context, self._last_event_mouse
        )
        delta = raw_pos - last_world
        if delta.length_squared < 1e-12:
            direction = Vector((1.0, 0.0, 0.0))
            mouse_len = 0.0
        else:
            direction = delta.normalized()
            mouse_len = delta.length
        return last_world, raw_pos, direction, mouse_len

    def _apply_typed_vertex(self, context) -> bool:
        geom = self._mouse_segment_geometry(context)
        if geom is None:
            return False
        last_world, _raw_pos, direction, mouse_len = geom
        try:
            dist = self.number_input.get_value(initial_value=mouse_len)
        except ValueError:
            return False
        if dist <= 1e-9:
            return False
        world_pos = last_world + direction * dist

        me = self._obj.data
        try:
            bm = bmesh.from_edit_mesh(me)
        except Exception:
            return False
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        try:
            inv = self._obj.matrix_world.inverted()
        except Exception:
            return False
        local = inv @ world_pos
        new_vert = bm.verts.new(local)
        bm.verts.index_update()
        bm.verts.ensure_lookup_table()
        prev_idx = self._chain_vert_indices[-1]
        if prev_idx < len(bm.verts):
            prev_vert = bm.verts[prev_idx]
            self._safe_new_edge_objs(bm, prev_vert, new_vert)
        bm.verts.index_update()
        self._chain_vert_indices.append(new_vert.index)
        bmesh.update_edit_mesh(me)
        me.update_tag()
        self._invalidate_snap_cache()
        self._axis_lock = None
        return True

    def _apply_typed_angle(self, context) -> bool:
        if len(self._chain_vert_indices) < 2:
            return False
        try:
            ang = self.angle_input.get_value(
                initial_value=self._mouse_edge_angle_deg(context)
            )
        except ValueError:
            return False
        self._edge_angle_deg = ang
        self._typing_angle = False
        self.angle_input.reset()
        return True

    def _chain_world_pos_at(self, chain_index: int) -> Vector | None:
        if not self._chain_vert_indices:
            return None
        try:
            vert_idx = self._chain_vert_indices[chain_index]
        except IndexError:
            return None
        try:
            me = self._obj.data
            bm = bmesh.from_edit_mesh(me)
            bm.verts.ensure_lookup_table()
            if vert_idx >= len(bm.verts):
                return None
            return self._obj.matrix_world @ bm.verts[vert_idx].co
        except Exception:
            return None

    def _last_edge_direction_world(self) -> Vector | None:
        if len(self._chain_vert_indices) < 2:
            return None
        prev = self._chain_world_pos_at(-1)
        prev_prev = self._chain_world_pos_at(-2)
        if prev is None or prev_prev is None:
            return None
        d = prev - prev_prev
        if d.length_squared < 1e-12:
            return None
        return d.normalized()

    def _draw_plane_normal(self, context) -> Vector:
        if self._ignore_draw_plane:
            rv3d = context.region_data
            if rv3d is not None:
                try:
                    return rv3d.view_rotation @ Vector((0.0, 0.0, 1.0))
                except Exception:
                    pass
            return Vector((0.0, 0.0, 1.0))
        n, _u, _v = cp.cursor_plane_axes(context)
        return n

    def _edge_angle_directions(
        self,
        context,
        last_dir: Vector,
        angle_deg: float,
    ) -> tuple[Vector, Vector] | None:
        n = self._draw_plane_normal(context)
        last_in = last_dir - n * last_dir.dot(n)
        if last_in.length_squared < 1e-20:
            ref = last_dir.cross(n)
            if ref.length_squared < 1e-20:
                ref = Vector((1.0, 0.0, 0.0))
            last_in = ref
        last_in.normalize()
        rad = math.radians(angle_deg)
        d_plus = (Matrix.Rotation(rad, 4, n) @ last_in).normalized()
        d_minus = (Matrix.Rotation(-rad, 4, n) @ last_in).normalized()
        return d_plus, d_minus

    def _pick_edge_angle_direction(
        self,
        context,
        prev_world: Vector,
        target_world: Vector,
        angle_deg: float,
    ) -> Vector | None:
        last_dir = self._last_edge_direction_world()
        if last_dir is None:
            return None
        dirs = self._edge_angle_directions(context, last_dir, angle_deg)
        if dirs is None:
            return None
        d_plus, d_minus = dirs
        delta = target_world - prev_world
        if delta.length_squared < 1e-12:
            return d_plus
        return d_plus if d_plus.dot(delta) >= d_minus.dot(delta) else d_minus

    def _apply_edge_angle_to_position(
        self,
        context,
        prev_world: Vector,
        target_world: Vector,
        angle_deg: float,
    ) -> Vector:
        d = self._pick_edge_angle_direction(context, prev_world, target_world, angle_deg)
        if d is None:
            return target_world
        dist = (target_world - prev_world).length
        if dist < 1e-9:
            dist = 1.0
        return prev_world + d * dist

    def _effective_edge_angle_deg(self, context) -> float | None:
        if self.angle_input.has_value():
            try:
                return self.angle_input.get_value(
                    initial_value=self._mouse_edge_angle_deg(context)
                )
            except ValueError:
                pass
        if self._edge_angle_deg is not None:
            return self._edge_angle_deg
        if self._typing_angle:
            return self._mouse_edge_angle_deg(context)
        return None

    def _mouse_edge_angle_deg(self, context) -> float:
        last_dir = self._last_edge_direction_world()
        prev = self._last_chain_world_pos()
        if (
            last_dir is None
            or prev is None
            or self._last_event_mouse is None
            or context.region is None
            or context.region_data is None
        ):
            return 90.0
        raw_pos, _s, _i, _o, _a = self._resolve_3d_position(
            context, self._last_event_mouse, apply_edge_angle=False
        )
        delta = raw_pos - prev
        if delta.length_squared < 1e-12:
            return 90.0
        n = self._draw_plane_normal(context)
        ld = last_dir - n * last_dir.dot(n)
        dd = delta - n * delta.dot(n)
        if ld.length_squared < 1e-20 or dd.length_squared < 1e-20:
            return 90.0
        ld.normalize()
        dd.normalize()
        cos_a = max(-1.0, min(1.0, ld.dot(dd)))
        return math.degrees(math.acos(cos_a))

    def _constrain_with_edge_angle(
        self,
        context,
        pos: Vector,
        is_ortho: bool,
    ) -> tuple[Vector, bool]:
        if len(self._chain_vert_indices) < 2:
            return pos, is_ortho
        angle = self._effective_edge_angle_deg(context)
        if angle is None:
            return pos, is_ortho
        prev = self._last_chain_world_pos()
        if prev is None:
            return pos, is_ortho
        return self._apply_edge_angle_to_position(context, prev, pos, angle), True

    def _update_area_header(self, context):
        if (
            not self._chain_vert_indices
            or self._last_event_mouse is None
            or context.region is None
        ):
            viewport_header.clear(context)
            return

        lw = self._last_chain_world_pos()
        pp = self._preview_world_pos
        if lw is None or pp is None:
            viewport_header.clear(context)
            return
        seg_len = (pp - lw).length
        if self.angle_input.value_str or self._typing_angle:
            try:
                ang_val = self.angle_input.get_value(
                    initial_value=self._mouse_edge_angle_deg(context)
                )
            except ValueError:
                ang_val = self._mouse_edge_angle_deg(context)
            viewport_header.set_numeric(
                context,
                main_label='Angle',
                main_value=float(ang_val),
                typed_str=self.angle_input.value_str,
                suffix='°',
                secondary_text='',
                initial_value=float(ang_val),
            )
            return
        if self._edge_angle_deg is not None:
            viewport_header.set(context, f'Angle: {self._edge_angle_deg:g}°')
            return
        if self.number_input.value_str:
            viewport_header.set_numeric(
                context,
                main_label='Length',
                main_value=float(seg_len),
                typed_str=self.number_input.value_str,
                suffix='',
                secondary_text='',
                initial_value=float(seg_len),
            )
            return
        disp = viewport_header.format_length(context, seg_len, precision=4)
        viewport_header.set(context, f'Length: {disp}')

    def _set_status(self, context):
        try:
            ortho = "ON" if self._ortho_on else "OFF"
            v_snap = "ON" if self._snap_verts_on else "OFF"
            w_snap = "ON" if self._snap_other_on else "OFF"
            plc = '3D' if self._ignore_draw_plane else 'Plane'
            axis = self._axis_lock if self._axis_lock else "—"
            ang = (
                f"{self._edge_angle_deg:g}°"
                if self._edge_angle_deg is not None
                else ("type" if self._typing_angle or self.angle_input.has_value() else "—")
            )
            if self._chain_vert_indices and (
                self.angle_input.has_value() or self._typing_angle
            ):
                num_part = "typing angle"
            elif self._chain_vert_indices and self.number_input.has_value():
                num_part = "typing length"
            elif self._chain_vert_indices:
                num_part = "[A]angle [B]90° • digits=length"
            else:
                num_part = ""
            sep = " " if num_part else ""
            status_bar.set_message(
                context,
                f"[LMB]Add [Bksp]Undo/buffer [RMB]Finish [C]Close "
                f"[Shift]Ortho:{ortho} [V]ObjSnap:{v_snap} [W]WorldSnap:{w_snap} "
                f"[Q]{plc}"
                f" [X/Y/Z]Axis:{axis} [A]Ang:{ang} [B]90°{sep}{num_part} [Enter/Esc]Exit",
            )
        except Exception:
            pass

    def _refresh_preview(self, context):
        if self._last_event_mouse is None or context.region is None or context.region_data is None:
            return

        last_world = self._last_chain_world_pos()

        if self._chain_vert_indices and self.number_input.has_value() and last_world is not None:
            raw_pos, _is_snap, _snap_idx, _is_ortho, _snap_anchor = self._resolve_3d_position(
                context, self._last_event_mouse
            )
            direction = raw_pos - last_world
            if direction.length_squared > 1e-12:
                direction = direction.normalized()
                mouse_len = (raw_pos - last_world).length
            else:
                direction = Vector((1.0, 0.0, 0.0))
                mouse_len = 0.0
            try:
                dist = self.number_input.get_value(initial_value=mouse_len)
            except ValueError:
                dist = mouse_len
            pos = last_world + direction * dist
            self._preview_world_pos = pos
            self._preview_is_snap = False
            self._preview_is_ortho = bool(self._ortho_on or self._axis_lock)
            self._preview_snap_vert_index = None
            snap_idx_for_draw: int | None = None
            is_snap_for_draw = False
            is_ortho_for_draw = self._preview_is_ortho
            snap_anchor_for_draw = None
        else:
            pos, is_snap, snap_idx, is_ortho, snap_anchor = self._resolve_3d_position(
                context, self._last_event_mouse
            )
            self._preview_world_pos = pos
            self._preview_is_snap = is_snap
            self._preview_is_ortho = is_ortho
            self._preview_snap_vert_index = snap_idx
            snap_idx_for_draw = snap_idx
            is_snap_for_draw = is_snap
            is_ortho_for_draw = is_ortho
            snap_anchor_for_draw = snap_anchor

        axis_guide = self._compute_axis_guide(context)
        draw_state._draw_data['draw_rubber_band'] = (
            last_world,
            pos,
            is_snap_for_draw,
            snap_idx_for_draw,
            is_ortho_for_draw,
            axis_guide,
            snap_anchor_for_draw if not self.number_input.has_value() else None,
        )
        if (
            is_snap_for_draw
            and pos is not None
            and not self.number_input.has_value()
            and context.region is not None
            and context.region_data is not None
        ):
            try:
                p2 = location_3d_to_region_2d(context.region, context.region_data, pos)
            except Exception:
                p2 = None
            if p2 is not None:
                draw_state._draw_data['draw_snap_ring'] = (
                    float(p2.x),
                    float(p2.y),
                    float(self._screen_snap_radius_px),
                    snap_idx_for_draw,
                )
                if snap_idx_for_draw == snap_cache.SNAP_IDX_WORLD_VERT and snap_anchor_for_draw is not None:
                    p_src = location_3d_to_region_2d(
                        context.region, context.region_data, snap_anchor_for_draw
                    )
                    dx = float(p_src.x - p2.x) if p_src else 0.0
                    dy = float(p_src.y - p2.y) if p_src else 0.0
                    # Second marker only when projected snap point separates from vtx on screen.
                    if p_src is not None and (dx * dx + dy * dy) > 225.0:
                        draw_state._draw_data['draw_snap_source_screen'] = (
                            float(p_src.x),
                            float(p_src.y),
                        )
                    else:
                        draw_state._draw_data.pop('draw_snap_source_screen', None)
                else:
                    draw_state._draw_data.pop('draw_snap_source_screen', None)
            else:
                draw_state._draw_data.pop('draw_snap_ring', None)
                draw_state._draw_data.pop('draw_snap_source_screen', None)
        else:
            draw_state._draw_data.pop('draw_snap_ring', None)
            draw_state._draw_data.pop('draw_snap_source_screen', None)
        self._update_length_label(context, last_world, pos)
        draw_state.refresh_edit_mesh_px_handler(context)
        self._update_cursor_plane_visual(context)
        self._set_status(context)
        self._update_area_header(context)
        if context.area is not None:
            context.area.tag_redraw()

    def _update_length_label(self, context, last_world: Vector | None, pos: Vector | None):
        if last_world is None or pos is None:
            draw_state._draw_data.pop('draw_rubber_band_label', None)
            return
        try:
            length = (pos - last_world).length
            mid = (last_world + pos) * 0.5
            if self.angle_input.has_value() or self._typing_angle:
                try:
                    ang = self.angle_input.get_value(
                        initial_value=self._mouse_edge_angle_deg(context)
                    )
                except ValueError:
                    ang = self._mouse_edge_angle_deg(context)
                text = f'> {self.angle_input.value_str}  →  {ang:.2f}°'
            elif self._edge_angle_deg is not None:
                text = f'{self._edge_angle_deg:g}°'
            elif self.number_input.has_value():
                unit_system = context.scene.unit_settings.system
                try:
                    lens = bpy.utils.units.to_string(unit_system, 'LENGTH', length, precision=4)
                except Exception:
                    lens = f'{length:.4f}'
                text = f'> {self.number_input.value_str}  →  {lens}'
            else:
                unit_system = context.scene.unit_settings.system
                try:
                    text = bpy.utils.units.to_string(unit_system, 'LENGTH', length, precision=4)
                except Exception:
                    text = f"{length:.4f}"
            draw_state._draw_data['draw_rubber_band_label'] = (mid, text)
        except Exception:
            draw_state._draw_data.pop('draw_rubber_band_label', None)

    def _compute_axis_guide(self, context):
        if not self._axis_lock or not self._chain_vert_indices:
            return None
        prev_world = self._last_chain_world_pos()
        if prev_world is None:
            return None
        try:
            O = orientation_matrix_world(context, self._obj)
            col = {'X': 0, 'Y': 1, 'Z': 2}[self._axis_lock]
            axis = Vector((O[0][col], O[1][col], O[2][col]))
            if axis.length_squared < 1e-12:
                return None
            axis = axis.normalized()
            colors = {
                'X': (1.0, 0.15, 0.15, 0.7),
                'Y': (0.15, 1.0, 0.15, 0.7),
                'Z': (0.15, 0.45, 1.0, 0.7),
            }
            color = colors[self._axis_lock]
            return (prev_world - axis * 1000.0, prev_world + axis * 1000.0, color)
        except Exception:
            return None

    def _last_chain_world_pos(self) -> Vector | None:
        if not self._chain_vert_indices:
            return None
        try:
            me = self._obj.data
            bm = bmesh.from_edit_mesh(me)
            bm.verts.ensure_lookup_table()
            idx = self._chain_vert_indices[-1]
            if idx >= len(bm.verts):
                return None
            return self._obj.matrix_world @ bm.verts[idx].co
        except Exception:
            return None

    def _update_cursor_plane_visual(self, context):
        if getattr(self, '_ignore_draw_plane', False):
            draw_state._draw_data.pop('cursor_plane', None)
            return
        try:
            cursor = context.scene.cursor
            center = cursor.location.copy()
            _n, u, v = cp.cursor_plane_axes(context)
            draw_state._draw_data['cursor_plane'] = (center, u, v)
        except Exception:
            draw_state._draw_data.pop('cursor_plane', None)
        if self._snap_other_on and not self._ignore_draw_plane:
            self._snap_cache.invalidate_world()

    def _resolve_3d_position(
        self,
        context,
        coord,
        *,
        apply_edge_angle: bool = True,
    ) -> tuple[Vector, bool, int | None, bool, Vector | None]:
        """Returns (world_pos, hit_snap, snap_idx, constrained_ortho, snap_anchor_world).

        snap_anchor_world is the snapped point in world space for feedback (same as preview
        for on-plane snaps; for WorldSnap (-3), the vertex before projection onto the plane)."""
        region = context.region
        rv3d = context.region_data
        origin_w = region_2d_to_origin_3d(region, rv3d, coord)
        direction_w = region_2d_to_vector_3d(region, rv3d, coord).normalized()

        need_ray = (
            self._ignore_draw_plane
            or self._viewport_snap_respects_opaque_depth(context)
        )
        depsgraph_rp = None
        ray_hit_world = None
        ray_t = None
        if need_ray:
            try:
                depsgraph_rp = context.evaluated_depsgraph_get()
            except Exception:
                depsgraph_rp = None
            ray_t, ray_hit_world = self._viewport_ray_pick(
                context, depsgraph_rp, origin_w, direction_w
            )
        occlusion_t = (
            ray_t
            if self._viewport_snap_respects_opaque_depth(context)
            else None
        )

        snap_pos, snap_idx, snap_raw_world = self._screen_snap_discrete(
            context, coord, occlusion_t, origin_w, direction_w
        )
        if snap_pos is not None:
            anchor = (
                snap_raw_world.copy()
                if snap_raw_world is not None
                else snap_pos.copy()
            )
            use_auto_ortho = self._ortho_on and self._axis_lock is None
            use_axis_lock = self._axis_lock is not None
            if (use_auto_ortho or use_axis_lock) and self._chain_vert_indices:
                prev_world = self._last_chain_world_pos()
                if prev_world is not None:
                    constrained = self._apply_ortho_constraint(
                        context,
                        prev_world,
                        snap_pos,
                        locked_axis=self._axis_lock if use_axis_lock else None,
                    )
                    if constrained is not None:
                        pos = constrained
                        is_ortho = True
                        if apply_edge_angle:
                            pos, is_ortho = self._constrain_with_edge_angle(
                                context, pos, is_ortho
                            )
                        return pos, True, None, is_ortho, anchor
            pos = snap_pos
            is_ortho = False
            if apply_edge_angle:
                pos, is_ortho = self._constrain_with_edge_angle(context, pos, is_ortho)
            return pos, True, snap_idx, is_ortho, anchor

        if self._ignore_draw_plane:
            pos = self._free_preview_world(origin_w, direction_w, ray_hit_world, context)
        else:
            pos = cp.intersect_cursor_plane(context, origin_w, direction_w)

        is_ortho = False
        use_auto_ortho = self._ortho_on and self._axis_lock is None
        use_axis_lock = self._axis_lock is not None
        if (use_auto_ortho or use_axis_lock) and self._chain_vert_indices:
            prev_world = self._last_chain_world_pos()
            if prev_world is not None:
                constrained = self._apply_ortho_constraint(
                    context,
                    prev_world,
                    pos,
                    locked_axis=self._axis_lock if use_axis_lock else None,
                )
                if constrained is not None:
                    pos = constrained
                    is_ortho = True

        if apply_edge_angle:
            pos, is_ortho = self._constrain_with_edge_angle(context, pos, is_ortho)
        return pos, False, None, is_ortho, None

    def _apply_ortho_constraint(
        self,
        context,
        prev_world: Vector,
        target_world: Vector,
        locked_axis: str | None = None,
    ) -> Vector | None:
        try:
            O = orientation_matrix_world(context, self._obj)
        except Exception:
            return None
        delta = target_world - prev_world
        if delta.length_squared < 1e-12:
            return None

        if locked_axis in {'X', 'Y', 'Z'}:
            col = {'X': 0, 'Y': 1, 'Z': 2}[locked_axis]
            axis = Vector((O[0][col], O[1][col], O[2][col]))
            if axis.length_squared < 1e-12:
                return None
            axis = axis.normalized()
            proj = delta.dot(axis)
            return prev_world + axis * proj

        best_proj = 0.0
        best_axis: Vector | None = None
        best_abs = -1.0
        for i in range(3):
            axis = Vector((O[0][i], O[1][i], O[2][i]))
            if axis.length_squared < 1e-12:
                continue
            axis = axis.normalized()
            proj = delta.dot(axis)
            if abs(proj) > best_abs:
                best_abs = abs(proj)
                best_proj = proj
                best_axis = axis
        if best_axis is None:
            return None
        return prev_world + best_axis * best_proj

    def _viewport_snap_respects_opaque_depth(self, context) -> bool:
        """When False, snapping uses screen-distance only (sees verts through solid meshes)."""
        space = getattr(context, 'space_data', None)
        if space is None or getattr(space, 'type', '') != 'VIEW_3D':
            return False
        shading = getattr(space, 'shading', None)
        if shading is None:
            return False
        if getattr(shading, 'show_xray', False):
            return False
        if getattr(shading, 'type', '') == 'WIREFRAME':
            return False
        return True

    def _viewport_ray_pick(
        self,
        context,
        depsgraph,
        origin_w: Vector,
        dir_w: Vector,
    ) -> tuple[float | None, Vector | None]:
        """First depsgraph ray hit depth (along dir) and world location; ignores shading mode."""
        if depsgraph is None:
            return None, None
        try:
            rc = context.scene.ray_cast(depsgraph, origin_w, dir_w)
        except Exception:
            return None, None
        if rc is None or not rc[0]:
            return None, None
        hit_loc = rc[1]
        if not isinstance(hit_loc, Vector):
            hit_loc = Vector(hit_loc)
        t_ray = (hit_loc - origin_w).dot(dir_w)
        return t_ray, hit_loc

    def _free_preview_world(
        self,
        origin_w: Vector,
        dir_w: Vector,
        ray_hit_world: Vector | None,
        context,
    ) -> Vector:
        """3D placement when not locked to cursor plane: mesh hit → depth through chain → plane."""
        if ray_hit_world is not None:
            return ray_hit_world.copy()
        last_w = self._last_chain_world_pos()
        if last_w is not None:
            td = (last_w - origin_w).dot(dir_w)
            if td > 1e-12:
                return origin_w + dir_w * td
        return cp.intersect_cursor_plane(context, origin_w, dir_w)

    def _snap_occludes_candidate(
        self,
        occlusion_t: float | None,
        origin_w: Vector,
        dir_w: Vector,
        world_co: Vector,
        context,
    ) -> bool:
        """True if world_co is farther along the viewport ray than the first surface hit (+ slack)."""
        if occlusion_t is None:
            return False
        t = (world_co - origin_w).dot(dir_w)
        scl = getattr(context.scene.unit_settings, 'scale_length', 1.0) or 1.0
        slack = max(scl * 1e-4, 1e-5, abs(occlusion_t) * 1e-6 + abs(t) * 1e-6)
        return t > occlusion_t + slack

    def _screen_snap_discrete(
        self,
        context,
        coord,
        occlusion_t: float | None,
        origin_w: Vector,
        dir_w: Vector,
    ) -> tuple[Vector | None, int | None, Vector | None]:
        """Projected plane hit, sentinel index, optional raw snap point (world) for projected snaps."""
        if not self._snap_verts_on and not self._snap_other_on:
            return None, None, None

        region = context.region
        rv3d = context.region_data
        hit = self._query_snap_cache(context, coord, occlusion_t, origin_w, dir_w)
        if hit is None:
            return None, None, None
        best_idx = hit.snap_idx
        best_world = hit.world
        raw_snap_world = hit.raw_world
        if (
            best_idx >= 0
            and self._chain_vert_indices
            and best_idx == self._chain_vert_indices[0]
            and len(self._chain_vert_indices) >= 3
            and not self._ortho_on
            and self._axis_lock is None
        ):
            return best_world, -1, None
        return best_world, best_idx, raw_snap_world

    def _merge_obj_perpendicular_snap(
        self,
        hit: snap_cache.SnapHit | None,
        bm,
        region,
        rv3d,
        coord,
        occlusion_t: float | None,
        origin_w: Vector,
        dir_w: Vector,
        context,
    ) -> snap_cache.SnapHit | None:
        if not self._snap_verts_on:
            return hit
        prev_world = self._last_chain_world_pos()
        if prev_world is None:
            return hit
        perp = snap_cache.best_obj_perpendicular_snap(
            bm,
            self._obj.matrix_world,
            region,
            rv3d,
            coord,
            float(self._screen_snap_radius_px),
            prev_world,
            self._snap_occludes_candidate,
            occlusion_t,
            origin_w,
            dir_w,
            context,
        )
        return snap_cache.pick_closer_snap_hit(region, rv3d, coord, hit, perp)

    def _query_snap_cache(
        self,
        context,
        coord,
        occlusion_t: float | None,
        origin_w: Vector,
        dir_w: Vector,
    ):
        region = context.region
        rv3d = context.region_data
        me = self._obj.data
        bm = None
        try:
            bm = bmesh.from_edit_mesh(me)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
        except Exception:
            return None

        use_kd = snap_cache.should_use_obj_kdtree(bm)
        if use_kd or self._snap_other_on:
            if self._snap_verts_on:
                self._snap_cache.ensure_obj(
                    bm,
                    self._obj.matrix_world,
                    region,
                    rv3d,
                    snap_cache.mesh_topology_key(me, bm),
                    include_verts=True,
                    include_edge_mids=True,
                )
            if self._snap_other_on:
                depsgraph = None
                try:
                    depsgraph = context.evaluated_depsgraph_get()
                except Exception:
                    depsgraph = None
                self._snap_cache.ensure_world(
                    context,
                    depsgraph,
                    region,
                    rv3d,
                    self._obj,
                    ignore_draw_plane=self._ignore_draw_plane,
                    world_key=snap_cache.world_snap_cache_key(context),
                )
                if self._snap_cache.world_snap_truncated and not self._world_snap_warned:
                    self._world_snap_warned = True
                    status_bar.show_toggle_notice(
                        "World snap",
                        "limited (dense scene)",
                    )
            hit = self._snap_cache.find_best(
                coord,
                float(self._screen_snap_radius_px),
                occlusion_t,
                origin_w,
                dir_w,
                context,
                self._snap_occludes_candidate,
                use_obj=self._snap_verts_on,
                use_world=self._snap_other_on,
            )
            hit = self._merge_obj_perpendicular_snap(
                hit, bm, region, rv3d, coord, occlusion_t, origin_w, dir_w, context
            )
            if hit is not None:
                return hit

        if not self._snap_verts_on:
            return None

        return self._screen_snap_brute(
            bm, me, region, rv3d, coord, occlusion_t, origin_w, dir_w, context
        )

    def _screen_snap_brute(
        self,
        bm,
        me,
        region,
        rv3d,
        coord,
        occlusion_t,
        origin_w,
        dir_w,
        context,
    ):
        """Linear scan for small meshes (cheaper than building a KD-tree)."""
        radius_sq = self._screen_snap_radius_px * self._screen_snap_radius_px
        best_d2 = radius_sq
        best_idx = None
        best_world = None
        raw_snap_world = None
        mw = self._obj.matrix_world

        if self._snap_verts_on:
            for v in bm.verts:
                world_co = mw @ v.co
                if self._snap_occludes_candidate(occlusion_t, origin_w, dir_w, world_co, context):
                    continue
                p2 = location_3d_to_region_2d(region, rv3d, world_co)
                if p2 is None:
                    continue
                dx = p2.x - coord[0]
                dy = p2.y - coord[1]
                d2 = dx * dx + dy * dy
                if d2 < best_d2:
                    best_d2 = d2
                    best_idx = v.index
                    best_world = world_co
                    raw_snap_world = None

            for e in bm.edges:
                mid_local = (e.verts[0].co + e.verts[1].co) * 0.5
                mid_w = mw @ mid_local
                if self._snap_occludes_candidate(occlusion_t, origin_w, dir_w, mid_w, context):
                    continue
                p2 = location_3d_to_region_2d(region, rv3d, mid_w)
                if p2 is None:
                    continue
                dx = p2.x - coord[0]
                dy = p2.y - coord[1]
                d2 = dx * dx + dy * dy
                if d2 < best_d2:
                    best_d2 = d2
                    best_idx = snap_cache.SNAP_IDX_EDGE_MID
                    best_world = mid_w
                    raw_snap_world = None

        hit = None
        if best_idx is not None and best_world is not None:
            hit = snap_cache.SnapHit(best_world, best_idx, raw_snap_world)
        prev_world = self._last_chain_world_pos()
        if prev_world is not None:
            perp = snap_cache.best_obj_perpendicular_snap(
                bm,
                mw,
                region,
                rv3d,
                coord,
                float(self._screen_snap_radius_px),
                prev_world,
                self._snap_occludes_candidate,
                occlusion_t,
                origin_w,
                dir_w,
                context,
            )
            hit = snap_cache.pick_closer_snap_hit(region, rv3d, coord, hit, perp)
        return hit

    def _invalidate_snap_cache(self) -> None:
        self._snap_cache.invalidate_mesh()

    def _on_click(self, context) -> bool:
        """Returns True when the polyline was closed via snap sentinel (operator should exit)."""
        if self._preview_world_pos is None:
            return False
        me = self._obj.data
        try:
            bm = bmesh.from_edit_mesh(me)
        except Exception:
            return False
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        snap_idx = self._preview_snap_vert_index

        if snap_idx == -1:
            if len(self._chain_vert_indices) >= 3:
                first_idx = self._chain_vert_indices[0]
                last_idx = self._chain_vert_indices[-1]
                self._safe_new_edge(bm, first_idx, last_idx)
                bmesh.update_edit_mesh(me)
                me.update_tag()
                self._invalidate_snap_cache()
                self._end_chain()
                self._axis_lock = None
                self._edge_angle_deg = None
                self._typing_angle = False
                self.number_input.reset()
                self.angle_input.reset()
                self._refresh_preview(context)
                return True
            return False

        reuse_existing = snap_idx is not None and snap_idx >= 0
        if reuse_existing:
            idx = snap_idx
            if idx >= len(bm.verts):
                return False
            new_vert = bm.verts[idx]
        else:
            try:
                inv = self._obj.matrix_world.inverted()
            except Exception:
                return False
            local = inv @ self._preview_world_pos
            new_vert = bm.verts.new(local)
            bm.verts.index_update()
            bm.verts.ensure_lookup_table()

        if self._chain_vert_indices:
            prev_idx = self._chain_vert_indices[-1]
            if prev_idx < len(bm.verts):
                prev_vert = bm.verts[prev_idx]
                self._safe_new_edge_objs(bm, prev_vert, new_vert)

        bm.verts.index_update()
        self._chain_vert_indices.append(new_vert.index)
        bmesh.update_edit_mesh(me)
        me.update_tag()
        self._invalidate_snap_cache()
        self._axis_lock = None
        self.number_input.reset()
        self._typing_angle = False
        self.angle_input.reset()
        self._refresh_preview(context)
        return False

    def _safe_new_edge_objs(self, bm, va, vb):
        if va is vb:
            return
        if bm.edges.get((va, vb)) is not None:
            return
        try:
            bm.edges.new((va, vb))
        except ValueError:
            pass

    def _safe_new_edge(self, bm, idx_a, idx_b):
        bm.verts.ensure_lookup_table()
        if idx_a >= len(bm.verts) or idx_b >= len(bm.verts):
            return
        self._safe_new_edge_objs(bm, bm.verts[idx_a], bm.verts[idx_b])

    def _end_chain(self):
        if self._chain_vert_indices:
            self._chains_history.append(self._chain_vert_indices)
            self._chain_vert_indices = []

    def _close_chain(self, context):
        if len(self._chain_vert_indices) < 3:
            return
        me = self._obj.data
        try:
            bm = bmesh.from_edit_mesh(me)
        except Exception:
            return
        self._safe_new_edge(bm, self._chain_vert_indices[0], self._chain_vert_indices[-1])
        bmesh.update_edit_mesh(me)
        me.update_tag()
        self._invalidate_snap_cache()
        self._end_chain()
        self._axis_lock = None
        self._edge_angle_deg = None
        self._typing_angle = False
        self.number_input.reset()
        self.angle_input.reset()
        self._refresh_preview(context)

    def _undo_last_vert(self, context):
        if not self._chain_vert_indices:
            return
        me = self._obj.data
        try:
            bm = bmesh.from_edit_mesh(me)
        except Exception:
            return
        bm.verts.ensure_lookup_table()

        last_idx = self._chain_vert_indices[-1]
        if last_idx >= len(bm.verts):
            self._chain_vert_indices.pop()
            self._refresh_preview(context)
            return

        last_vert = bm.verts[last_idx]

        if len(self._chain_vert_indices) >= 2:
            prev_idx = self._chain_vert_indices[-2]
            if prev_idx < len(bm.verts):
                prev_vert = bm.verts[prev_idx]
                edge = bm.edges.get((prev_vert, last_vert))
                if edge is not None:
                    bmesh.ops.delete(bm, geom=[edge], context='EDGES')
                    bm.verts.ensure_lookup_table()
                    if last_idx < len(bm.verts):
                        last_vert = bm.verts[last_idx]
                    else:
                        self._chain_vert_indices.pop()
                        bmesh.update_edit_mesh(me)
                        me.update_tag()
                        self._refresh_preview(context)
                        return

        if last_vert.is_valid and len(last_vert.link_edges) == 0:
            bmesh.ops.delete(bm, geom=[last_vert], context='VERTS')

        self._chain_vert_indices.pop()
        bmesh.update_edit_mesh(me)
        me.update_tag()
        self._invalidate_snap_cache()
        self._refresh_preview(context)

    def _cleanup(self, context, cancelled: bool):
        self._snap_cache.invalidate_all()
        draw_state._draw_data.pop('draw_rubber_band', None)
        draw_state._draw_data.pop('draw_rubber_band_label', None)
        draw_state._draw_data.pop('draw_snap_ring', None)
        draw_state._draw_data.pop('draw_snap_source_screen', None)
        draw_state._draw_data.pop('cursor_plane', None)
        try:
            draw_state.refresh_edit_mesh_px_handler(context)
        except Exception:
            pass
        status_bar.clear_all(context)
        if context.area is not None:
            context.area.tag_redraw()

        if cancelled and self._created_object:
            obj = self._obj
            try:
                if context.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass
            try:
                me = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if me is not None and me.users == 0:
                    bpy.data.meshes.remove(me)
            except Exception:
                pass


classes = (
    ALEC_OT_draw_mesh_edges,
)
