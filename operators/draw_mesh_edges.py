"""Modal operator: draw polylines as real mesh edges on the 3D cursor work plane."""
import bpy
import bmesh
from mathutils import Vector
from bpy_extras.view3d_utils import (
    region_2d_to_origin_3d,
    region_2d_to_vector_3d,
    location_3d_to_region_2d,
)

from ..modules import edit_mesh_draw_state as draw_state
from ..ui.transform.selection_math import _orientation_matrix_world


class ALEC_OT_draw_mesh_edges(bpy.types.Operator):
    """Draw polylines on the 3D cursor work plane. [RMB]/close snap ends session — run again from N-panel for another line. Snaps verts/mids; [Shift] ortho; [X/Y/Z] axis; [V]/[W] snap; [Tab] numeric; [C] close poly; [Enter/Esc] exit."""
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
        self._numeric_mode: bool = False
        self._numeric_str: str = ""
        self._last_event_mouse: tuple[int, int] | None = None

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

        context.window_manager.modal_handler_add(self)
        if context.area is not None:
            context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}

        if event.type == 'MOUSEMOVE':
            if context.region is None or context.region_data is None:
                return {'RUNNING_MODAL'}
            self._last_event_mouse = (event.mouse_region_x, event.mouse_region_y)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if self._numeric_mode:
            return self._modal_numeric(context, event)

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
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

        if event.type == 'BACK_SPACE' and event.value == 'PRESS':
            self._undo_last_vert(context)
            return {'RUNNING_MODAL'}

        if event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT'} and event.value == 'PRESS':
            self._ortho_on = not self._ortho_on
            self._set_status(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if event.type == 'V' and event.value == 'PRESS':
            self._snap_verts_on = not self._snap_verts_on
            self._set_status(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if event.type == 'W' and event.value == 'PRESS':
            self._snap_other_on = not self._snap_other_on
            self._set_status(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if event.type == 'TAB' and event.value == 'PRESS':
            if self._chain_vert_indices:
                self._numeric_mode = True
                self._numeric_str = ""
                self._set_status(context)
                self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if event.type in {'X', 'Y', 'Z'} and event.value == 'PRESS':
            key = event.type
            if self._axis_lock == key:
                self._axis_lock = None
            else:
                self._axis_lock = key
            self._set_status(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            self._cleanup(context, cancelled=False)
            return {'FINISHED'}

        if event.type == 'ESC' and event.value == 'PRESS':
            cancelled = self._created_object and not self._chain_vert_indices and not self._chains_history
            self._cleanup(context, cancelled=cancelled)
            return {'CANCELLED'} if cancelled else {'FINISHED'}

        return {'RUNNING_MODAL'}

    def _modal_numeric(self, context, event):
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}

        if event.type == 'ESC' or event.type == 'TAB':
            self._numeric_mode = False
            self._numeric_str = ""
            self._set_status(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        if event.type in {'RET', 'NUMPAD_ENTER'}:
            applied = self._on_click_numeric(context)
            self._numeric_mode = False
            self._numeric_str = ""
            self._set_status(context)
            self._refresh_preview(context)
            if applied:
                return {'RUNNING_MODAL'}
            return {'RUNNING_MODAL'}

        if event.type == 'BACK_SPACE':
            if self._numeric_str:
                self._numeric_str = self._numeric_str[:-1]
            self._set_status(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        digit_keys = {
            'ZERO': '0', 'ONE': '1', 'TWO': '2', 'THREE': '3', 'FOUR': '4',
            'FIVE': '5', 'SIX': '6', 'SEVEN': '7', 'EIGHT': '8', 'NINE': '9',
            'NUMPAD_0': '0', 'NUMPAD_1': '1', 'NUMPAD_2': '2', 'NUMPAD_3': '3',
            'NUMPAD_4': '4', 'NUMPAD_5': '5', 'NUMPAD_6': '6', 'NUMPAD_7': '7',
            'NUMPAD_8': '8', 'NUMPAD_9': '9',
            'PERIOD': '.', 'NUMPAD_PERIOD': '.', 'COMMA': '.',
            'MINUS': '-', 'NUMPAD_MINUS': '-',
        }
        ch = digit_keys.get(event.type)
        if ch is not None:
            if ch == '.' and '.' in self._numeric_str:
                pass
            elif ch == '-':
                if self._numeric_str.startswith('-'):
                    self._numeric_str = self._numeric_str[1:]
                else:
                    self._numeric_str = '-' + self._numeric_str
            else:
                self._numeric_str += ch
            self._set_status(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    def _set_status(self, context):
        try:
            ortho = "ON" if self._ortho_on else "OFF"
            v_snap = "ON" if self._snap_verts_on else "OFF"
            w_snap = "ON" if self._snap_other_on else "OFF"
            axis = self._axis_lock if self._axis_lock else "—"
            if self._numeric_mode:
                num_part = f"[Tab]Num:{self._numeric_str or '_'}"
            else:
                num_part = "[Tab]Num"
            context.workspace.status_text_set(
                f"[LMB]Add [Bksp]Undo [RMB]Finish [C]Close "
                f"[Shift]Ortho:{ortho} [V]ObjSnap:{v_snap} [W]WorldSnap:{w_snap} "
                f"[X/Y/Z]Axis:{axis} {num_part} [Enter/Esc]Exit"
            )
        except Exception:
            pass

    def _refresh_preview(self, context):
        if self._last_event_mouse is None or context.region is None or context.region_data is None:
            return

        last_world = self._last_chain_world_pos()

        if self._numeric_mode and last_world is not None:
            raw_pos, _is_snap, _snap_idx, _is_ortho, _snap_anchor = self._resolve_3d_position(
                context, self._last_event_mouse
            )
            direction = raw_pos - last_world
            if direction.length_squared > 1e-12:
                direction = direction.normalized()
            else:
                direction = Vector((1.0, 0.0, 0.0))
            try:
                dist = float(self._numeric_str) if self._numeric_str not in ("", "-", ".", "-.") else 0.0
            except ValueError:
                dist = 0.0
            pos = last_world + direction * dist
            self._preview_world_pos = pos
            self._preview_is_snap = False
            self._preview_is_ortho = bool(self._ortho_on or self._axis_lock)
            self._preview_snap_vert_index = None
            snap_idx_for_draw: int | None = None
            is_snap_for_draw = False
            is_ortho_for_draw = self._preview_is_ortho
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
            snap_anchor_for_draw if not self._numeric_mode else None,
        )
        if (
            is_snap_for_draw
            and pos is not None
            and not self._numeric_mode
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
            else:
                draw_state._draw_data.pop('draw_snap_ring', None)
        else:
            draw_state._draw_data.pop('draw_snap_ring', None)
        self._update_length_label(context, last_world, pos)
        draw_state.refresh_edit_mesh_px_handler(context)
        self._update_cursor_plane_visual(context)
        self._set_status(context)
        if context.area is not None:
            context.area.tag_redraw()

    def _update_length_label(self, context, last_world: Vector | None, pos: Vector | None):
        if last_world is None or pos is None:
            draw_state._draw_data.pop('draw_rubber_band_label', None)
            return
        try:
            length = (pos - last_world).length
            mid = (last_world + pos) * 0.5
            if self._numeric_mode:
                text = f"> {self._numeric_str or ''}"
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
            O = _orientation_matrix_world(context, self._obj)
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

    def _cursor_plane_axes(self, context) -> tuple[Vector, Vector, Vector]:
        """Returns (normal, u, v) axes of the cursor's XY plane (Z normal)."""
        cursor = context.scene.cursor
        M3 = cursor.matrix.to_3x3()
        cx = Vector((M3[0][0], M3[1][0], M3[2][0])).normalized()
        cy = Vector((M3[0][1], M3[1][1], M3[2][1])).normalized()
        cz = Vector((M3[0][2], M3[1][2], M3[2][2])).normalized()
        return (cz, cx, cy)

    def _intersect_cursor_plane(self, context, origin_w: Vector, direction_w: Vector) -> Vector:
        cursor = context.scene.cursor
        plane_co = cursor.location
        normal, _u, _v = self._cursor_plane_axes(context)
        denom = direction_w.dot(normal)
        if abs(denom) < 1e-9:
            return plane_co.copy()
        t = (plane_co - origin_w).dot(normal) / denom
        return origin_w + direction_w * t

    def _project_onto_cursor_plane(self, context, world_co: Vector) -> Vector:
        cursor = context.scene.cursor
        plane_co = cursor.location
        normal, _u, _v = self._cursor_plane_axes(context)
        dist = (world_co - plane_co).dot(normal)
        return world_co - normal * dist

    def _update_cursor_plane_visual(self, context):
        try:
            cursor = context.scene.cursor
            center = cursor.location.copy()
            _n, u, v = self._cursor_plane_axes(context)
            draw_state._draw_data['cursor_plane'] = (center, u, v)
        except Exception:
            draw_state._draw_data.pop('cursor_plane', None)

    def _resolve_3d_position(
        self,
        context,
        coord,
    ) -> tuple[Vector, bool, int | None, bool, Vector | None]:
        """Returns (world_pos, hit_snap, snap_idx, constrained_ortho, snap_anchor_world).

        snap_anchor_world is the raw discrete snap target in world space, or None.
        Preview may differ after ortho/axis projection; anchor is drawn for feedback."""
        region = context.region
        rv3d = context.region_data
        origin_w = region_2d_to_origin_3d(region, rv3d, coord)
        direction_w = region_2d_to_vector_3d(region, rv3d, coord).normalized()

        snap_pos, snap_idx = self._screen_snap_discrete(context, coord)
        if snap_pos is not None:
            anchor = snap_pos.copy()
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
                        return constrained, True, None, True, anchor
            return snap_pos, True, snap_idx, False, anchor

        pos = self._intersect_cursor_plane(context, origin_w, direction_w)

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

        return pos, False, None, is_ortho, None

    def _apply_ortho_constraint(
        self,
        context,
        prev_world: Vector,
        target_world: Vector,
        locked_axis: str | None = None,
    ) -> Vector | None:
        try:
            O = _orientation_matrix_world(context, self._obj)
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

    def _screen_snap_discrete(self, context, coord) -> tuple[Vector | None, int | None]:
        if not self._snap_verts_on and not self._snap_other_on:
            return None, None

        region = context.region
        rv3d = context.region_data
        radius_sq = self._screen_snap_radius_px * self._screen_snap_radius_px
        best_d2 = radius_sq
        best_idx: int | None = None
        best_world: Vector | None = None

        if self._snap_verts_on:
            mw = self._obj.matrix_world
            me = self._obj.data
            try:
                bm = bmesh.from_edit_mesh(me)
                bm.verts.ensure_lookup_table()
                bm.edges.ensure_lookup_table()
            except Exception:
                bm = None

            if bm is not None:
                for v in bm.verts:
                    world_co = mw @ v.co
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

                for e in bm.edges:
                    mid_local = (e.verts[0].co + e.verts[1].co) * 0.5
                    mid_w = mw @ mid_local
                    p2 = location_3d_to_region_2d(region, rv3d, mid_w)
                    if p2 is None:
                        continue
                    dx = p2.x - coord[0]
                    dy = p2.y - coord[1]
                    d2 = dx * dx + dy * dy
                    if d2 < best_d2:
                        best_d2 = d2
                        best_idx = -2
                        best_world = mid_w

        if self._snap_other_on:
            try:
                depsgraph = context.evaluated_depsgraph_get()
            except Exception:
                depsgraph = None
            if depsgraph is not None:
                for obj_inst in depsgraph.object_instances:
                    obj_eval = obj_inst.object
                    if obj_eval is None or obj_eval.type != 'MESH':
                        continue
                    try:
                        obj_orig = obj_eval.original
                    except Exception:
                        obj_orig = obj_eval
                    if obj_orig is self._obj:
                        continue
                    try:
                        if not obj_orig.visible_get():
                            continue
                    except Exception:
                        pass
                    inst_mw = obj_inst.matrix_world
                    try:
                        eval_mesh = obj_eval.data
                    except Exception:
                        continue
                    if eval_mesh is None:
                        continue
                    try:
                        verts = eval_mesh.vertices
                    except Exception:
                        continue
                    for v in verts:
                        v_world = inst_mw @ v.co
                        p2 = location_3d_to_region_2d(region, rv3d, v_world)
                        if p2 is None:
                            continue
                        dx = p2.x - coord[0]
                        dy = p2.y - coord[1]
                        d2 = dx * dx + dy * dy
                        if d2 < best_d2:
                            best_d2 = d2
                            best_idx = -3
                            best_world = self._project_onto_cursor_plane(context, v_world)

        if best_idx is None or best_world is None:
            return None, None
        if (
            best_idx >= 0
            and self._chain_vert_indices
            and best_idx == self._chain_vert_indices[0]
            and len(self._chain_vert_indices) >= 3
            and not self._ortho_on
            and self._axis_lock is None
        ):
            return best_world, -1
        return best_world, best_idx

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
                self._end_chain()
                self._axis_lock = None
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
        self._axis_lock = None
        self._refresh_preview(context)
        return False

    def _on_click_numeric(self, context) -> bool:
        if self._preview_world_pos is None or not self._chain_vert_indices:
            return False
        try:
            float(self._numeric_str)
        except (ValueError, TypeError):
            return False
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
        local = inv @ self._preview_world_pos
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
        self._axis_lock = None
        return True

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
        self._end_chain()
        self._axis_lock = None
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
        self._refresh_preview(context)

    def _cleanup(self, context, cancelled: bool):
        draw_state._draw_data.pop('draw_rubber_band', None)
        draw_state._draw_data.pop('draw_rubber_band_label', None)
        draw_state._draw_data.pop('draw_snap_ring', None)
        draw_state._draw_data.pop('cursor_plane', None)
        try:
            draw_state.refresh_edit_mesh_px_handler(context)
        except Exception:
            pass
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
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


classes = [
    ALEC_OT_draw_mesh_edges,
]
