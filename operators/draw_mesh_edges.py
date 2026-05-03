"""Modal operator: draw polylines as real mesh edges with raycast snap and vertex snap."""
import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras.view3d_utils import (
    region_2d_to_origin_3d,
    region_2d_to_vector_3d,
    region_2d_to_location_3d,
    location_3d_to_region_2d,
)

from ..modules import edit_mesh_draw_state as draw_state
from ..ui.transform.selection_math import _orientation_matrix_world, _transform_orient_short


class ALEC_OT_draw_mesh_edges(bpy.types.Operator):
    """Draw polylines as mesh edges. Raycasts onto surfaces, snaps vertices; [O] ortho auto-axis; [X/Y/Z] lock one orientation axis until next LMB"""
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
        self._bvh: BVHTree | None = None
        self._bvh_obj_name: str | None = None
        self._screen_snap_radius_px = 12
        self._created_object = False
        self._ortho_on: bool = False
        self._axis_lock: str | None = None  # 'X', 'Y', or 'Z' — orientation axes from Transform Orientation slot 0
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

        self._build_bvh()

        draw_state._draw_data['object_name'] = self._obj.name
        draw_state._draw_data['mesh_name'] = self._obj.data.name
        draw_state._draw_data['draw_rubber_band'] = None
        draw_state.register_3d_draw_handler()

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

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self._on_click(context)
            return {'RUNNING_MODAL'}

        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            self._end_chain()
            if self._preview_world_pos is not None:
                draw_state._draw_data['draw_rubber_band'] = (
                    None,
                    self._preview_world_pos,
                    self._preview_is_snap,
                    self._preview_snap_vert_index,
                    False,
                    None,
                )
            else:
                draw_state._draw_data['draw_rubber_band'] = None
            if context.area is not None:
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        if event.type == 'C' and event.value == 'PRESS':
            if len(self._chain_vert_indices) >= 3:
                self._close_chain(context)
            return {'RUNNING_MODAL'}

        if event.type == 'BACK_SPACE' and event.value == 'PRESS':
            self._undo_last_vert(context)
            return {'RUNNING_MODAL'}

        if event.type == 'O' and event.value == 'PRESS':
            self._ortho_on = not self._ortho_on
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

    def _set_status(self, context):
        try:
            orient = _transform_orient_short(context)
            ortho_part = f"[O] Ortho: {'ON' if self._ortho_on else 'OFF'} ({orient})"
            lock_part = (
                f"[X/Y/Z] Axis: {self._axis_lock} ({orient})"
                if self._axis_lock
                else "[X/Y/Z] Axis: —"
            )
            context.workspace.status_text_set(
                f"[LMB] Add  [Bksp] Undo vert  [RMB] End chain  [C] Close chain  {ortho_part}  {lock_part}  [Enter] Exit  [Esc] Exit"
            )
        except Exception:
            pass

    def _refresh_preview(self, context):
        if self._last_event_mouse is None or context.region is None or context.region_data is None:
            return
        pos, is_snap, snap_idx, is_ortho = self._resolve_3d_position(context, self._last_event_mouse)
        self._preview_world_pos = pos
        self._preview_is_snap = is_snap
        self._preview_is_ortho = is_ortho
        self._preview_snap_vert_index = snap_idx
        last_world = self._last_chain_world_pos()
        axis_guide = self._compute_axis_guide(context)
        draw_state._draw_data['draw_rubber_band'] = (last_world, pos, is_snap, snap_idx, is_ortho, axis_guide)
        self._set_status(context)
        if context.area is not None:
            context.area.tag_redraw()

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

    def _build_bvh(self):
        try:
            me = self._obj.data
            bm = bmesh.from_edit_mesh(me)
            self._bvh = BVHTree.FromBMesh(bm)
            self._bvh_obj_name = self._obj.name
        except Exception:
            self._bvh = None

    def _ensure_bvh_fresh(self):
        self._build_bvh()

    def _resolve_3d_position(self, context, coord) -> tuple[Vector, bool, int | None, bool]:
        region = context.region
        rv3d = context.region_data
        origin_w = region_2d_to_origin_3d(region, rv3d, coord)
        direction_w = region_2d_to_vector_3d(region, rv3d, coord).normalized()

        snap_pos, snap_idx = self._screen_snap_to_verts(context, coord)
        if snap_pos is not None:
            return snap_pos, True, snap_idx, False

        depsgraph = context.evaluated_depsgraph_get()
        scene_result = context.scene.ray_cast(depsgraph, origin_w, direction_w)
        hit_scene = scene_result[0]
        loc_scene = scene_result[1] if hit_scene else None
        scene_dist = (loc_scene - origin_w).length if hit_scene else float('inf')

        bvh_loc_w: Vector | None = None
        bvh_dist = float('inf')
        if self._bvh is not None:
            mw = self._obj.matrix_world
            try:
                inv = mw.inverted()
            except Exception:
                inv = None
            if inv is not None:
                origin_l = inv @ origin_w
                dir_l_raw = inv.to_3x3() @ direction_w
                if dir_l_raw.length_squared > 1e-12:
                    direction_l = dir_l_raw.normalized()
                    bvh_loc_l, _normal, _index, _dist = self._bvh.ray_cast(origin_l, direction_l)
                    if bvh_loc_l is not None:
                        bvh_loc_w = mw @ bvh_loc_l
                        bvh_dist = (bvh_loc_w - origin_w).length

        is_snap = False
        if bvh_loc_w is not None and bvh_dist < scene_dist:
            pos = bvh_loc_w
            is_snap = True
        elif hit_scene:
            pos = loc_scene
            is_snap = True
        else:
            pos = region_2d_to_location_3d(region, rv3d, coord, context.scene.cursor.location)

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

        return pos, is_snap, None, is_ortho

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

    def _screen_snap_to_verts(self, context, coord) -> tuple[Vector | None, int | None]:
        region = context.region
        rv3d = context.region_data
        mw = self._obj.matrix_world
        me = self._obj.data
        try:
            bm = bmesh.from_edit_mesh(me)
            bm.verts.ensure_lookup_table()
        except Exception:
            return None, None

        radius_sq = self._screen_snap_radius_px * self._screen_snap_radius_px
        best_d2 = radius_sq
        best_idx: int | None = None
        best_world: Vector | None = None
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

        if best_idx is None or best_world is None:
            return None, None
        if self._chain_vert_indices and best_idx == self._chain_vert_indices[0] and len(self._chain_vert_indices) >= 3:
            return best_world, -1
        return best_world, best_idx

    def _on_click(self, context):
        if self._preview_world_pos is None:
            return
        me = self._obj.data
        try:
            bm = bmesh.from_edit_mesh(me)
        except Exception:
            return
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        if self._preview_snap_vert_index is not None and self._preview_snap_vert_index == -1:
            if len(self._chain_vert_indices) >= 3:
                first_idx = self._chain_vert_indices[0]
                last_idx = self._chain_vert_indices[-1]
                self._safe_new_edge(bm, first_idx, last_idx)
                bmesh.update_edit_mesh(me)
                me.update_tag()
                self._end_chain()
                self._ensure_bvh_fresh()
                self._axis_lock = None
                self._refresh_preview(context)
            return

        if self._preview_snap_vert_index is not None:
            idx = self._preview_snap_vert_index
            if idx >= len(bm.verts):
                return
            new_vert = bm.verts[idx]
        else:
            try:
                inv = self._obj.matrix_world.inverted()
            except Exception:
                return
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
        self._ensure_bvh_fresh()
        self._axis_lock = None
        self._refresh_preview(context)

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
        self._ensure_bvh_fresh()
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
                        self._ensure_bvh_fresh()
                        self._refresh_preview(context)
                        return

        if last_vert.is_valid and len(last_vert.link_edges) == 0:
            bmesh.ops.delete(bm, geom=[last_vert], context='VERTS')

        self._chain_vert_indices.pop()
        bmesh.update_edit_mesh(me)
        me.update_tag()
        self._ensure_bvh_fresh()
        self._refresh_preview(context)

    def _cleanup(self, context, cancelled: bool):
        draw_state._draw_data.pop('draw_rubber_band', None)
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
