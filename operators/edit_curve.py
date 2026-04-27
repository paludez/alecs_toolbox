import bpy
from ..modules import modal_handler, utils
from ..modules import edit_curve_helpers as ech
from ..modules import edit_mesh_draw_state as draw_state


def _copy_spline_settings(src, dst):
    for name in (
        "material_index",
        "resolution_u",
        "resolution_v",
        "use_smooth",
        "tilt_interpolation",
        "radius_interpolation",
        "order_u",
        "order_v",
        "use_endpoint_u",
        "use_endpoint_v",
        "use_bezier_u",
        "use_bezier_v",
    ):
        if hasattr(src, name) and hasattr(dst, name):
            try:
                setattr(dst, name, getattr(src, name))
            except Exception:
                pass


def _copy_bezier_point(src, dst):
    dst.co = src.co.copy()
    dst.handle_left = src.handle_left.copy()
    dst.handle_right = src.handle_right.copy()
    dst.handle_left_type = src.handle_left_type
    dst.handle_right_type = src.handle_right_type
    dst.radius = src.radius
    dst.tilt = src.tilt
    if hasattr(src, "weight_softbody") and hasattr(dst, "weight_softbody"):
        dst.weight_softbody = src.weight_softbody


def _copy_spline_point(src, dst):
    dst.co = src.co.copy()
    dst.radius = src.radius
    dst.tilt = src.tilt
    if hasattr(src, "weight") and hasattr(dst, "weight"):
        dst.weight = src.weight
    if hasattr(src, "weight_softbody") and hasattr(dst, "weight_softbody"):
        dst.weight_softbody = src.weight_softbody


class ALEC_OT_set_curve_point_length(modal_handler.BaseModalOperator, bpy.types.Operator):
    """
    Set 3D distance between two selected **control points** (Bezier or poly/NURBS),
    not handle length. Straight-line between point positions, like mesh edge set length.
    """
    bl_idname = "alec.set_curve_point_length"
    bl_label = "Set Point Distance"
    bl_options = {'REGISTER', 'UNDO', 'GRAB_CURSOR', 'BLOCKING'}

    def get_status_bar_items(self):
        return [("Anchor", "[A] Active", self.anchor_mode == 'ACTIVE'), ("", "[B] Other", self.anchor_mode == 'OTHER'),
                ("", "[C] Center", self.anchor_mode == 'CENTER'), None, ("Confirm", "[LMB]"), ("Cancel", "[RMB]")]

    def apply_length(self):
        if self.anchor_mode == 'CENTER':
            world_c = (self.world_mx @ self.t1.get_co() + self.world_mx @ self.t2.get_co()) * 0.5
            half = self.current_length * 0.5
            self.t1.set_co(self.inv_world_mx @ (world_c - self.world_direction * half))
            self.t2.set_co(self.inv_world_mx @ (world_c + self.world_direction * half))
        else:
            if self.anchor_mode == 'ACTIVE':
                t_stat, t_mov = self.active_target, self.other_target
            else:
                t_stat, t_mov = self.other_target, self.active_target
            w_stat = self.world_mx @ t_stat.get_co()
            sign = 1.0 if t_stat is self.t1 else -1.0
            t_mov.set_co(self.inv_world_mx @ (w_stat + self.world_direction * sign * self.current_length))
        self.me.update_tag()
        self.obj.update_from_editmode()

    def invoke(self, context, event):
        self.obj = context.active_object
        self.me = self.obj.data
        keys = ech.selected_control_point_keys(self.me)
        if len(keys) != 2:
            self.report({'WARNING'}, "Select exactly 2 control points (not handles)")
            return {'CANCELLED'}
        ts = ech.keys_to_targets(self.me, keys)
        if len(ts) != 2:
            self.report({'WARNING'}, "Could not resolve control points")
            return {'CANCELLED'}
        self.t1, self.t2 = ts[0], ts[1]
        self.initial_t1 = self.t1.get_co().copy()
        self.initial_t2 = self.t2.get_co().copy()
        self.world_mx = self.obj.matrix_world
        self.inv_world_mx = self.world_mx.inverted()
        w1 = self.world_mx @ self.t1.get_co()
        w2 = self.world_mx @ self.t2.get_co()
        dv = w2 - w1
        if dv.length_squared < 1e-20:
            self.report({'WARNING'}, "Points are coincident, cannot set distance")
            return {'CANCELLED'}
        self.world_direction = dv.normalized()
        self.active_target, self.other_target = self.t1, self.t2
        self.initial_length = dv.length
        self.current_length = self.initial_length
        self.anchor_mode = 'ACTIVE'
        return self.base_invoke(context, event)

    def get_header_args(self, context):
        suffix = utils.unit_suffixes.get(context.scene.unit_settings.length_unit, '')
        inv = self.unit_scale_display_inv
        init_v = self.initial_length * inv
        secondary = ""
        if not self.number_input.has_value():
            fi = f"{init_v:.4f}".rstrip('0').rstrip('.')
            if fi == '-0': fi = '0'
            secondary = f"Initial: {fi}{suffix}"
        return {
            "main_label": "Distance",
            "main_value": self.current_length * inv,
            "suffix": suffix,
            "secondary_text": secondary,
            "initial_value": init_v,
        }

    def on_cancel(self, context, event):
        self.t1.set_co(self.initial_t1)
        self.t2.set_co(self.initial_t2)
        self.me.update_tag()
        self.obj.update_from_editmode()

    def on_mouse_move(self, context, event, delta_x):
        sens = 0.01 * (0.1 if event.shift else 1.0)
        self.current_length = max(0.0, self.initial_length + delta_x * sens)
        self.apply_length()

    def on_custom_event(self, context, event):
        if event.type in {'A', 'B', 'C'} and event.value == 'PRESS':
            self.t1.set_co(self.initial_t1)
            self.t2.set_co(self.initial_t2)
            self.current_length = self.initial_length
            self.initial_mouse_x = event.mouse_x
            self.number_input.reset()
            if event.type == 'A':
                self.anchor_mode = 'ACTIVE'
            elif event.type == 'B':
                self.anchor_mode = 'OTHER'
            elif event.type == 'C':
                self.anchor_mode = 'CENTER'
            self.me.update_tag()
            self.obj.update_from_editmode()

    def on_apply_typed_value(self, context, event):
        if not self.number_input.has_value():
            return
        try:
            inv = self.unit_scale_display_inv
            typed = self.number_input.get_value(initial_value=self.initial_length * inv)
            self.current_length = abs(typed * self.unit_scale)
            self.apply_length()
        except ValueError:
            pass


class ALEC_OT_curve_point_dimension(bpy.types.Operator):
    """Show / add / remove 3D point-to-point distance labels in curve edit (control points only)."""
    bl_idname = "alec.curve_point_dimension"
    bl_label = "Curve Point Dimension"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(
        items=[
            ('ADD', "Add", "Add labels for 3D distance between 2 control points (must select exactly 2)"),
            ('REMOVE', "Remove", "Remove labels for pairs touching the current point selection"),
            ('CLEAR', "Clear", "Remove all point-distance labels for this object"),
        ]
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        return ech.poll_active_curve_edit_mode(context)

    def execute(self, context):
        obj = context.active_object
        me = obj.data
        d = draw_state._draw_data
        if self.action == 'CLEAR':
            d.pop('curve_point_pairs', None)
            d.pop('curve_dim_unit_inv', None)
            d.pop('curve_dim_suffix', None)
            draw_state.update_dimension_px_handler(context, draw_state.has_dim_overlay_data())
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            self.report({'INFO'}, "Cleared point distances (curve)")
            return {'FINISHED'}

        if d.get('object_name') != obj.name or d.get('mesh_name') != me.name:
            d.clear()
        d['object_name'] = obj.name
        d['mesh_name'] = me.name

        unit = utils.get_unit_scale(context)
        d['curve_dim_unit_inv'] = 1.0 / unit if unit else 1.0
        d['curve_dim_suffix'] = utils.unit_suffixes.get(context.scene.unit_settings.length_unit, '')

        pairs = list(d.get('curve_point_pairs', []))
        if self.action == 'ADD':
            keys = ech.selected_control_point_keys(me)
            if len(keys) != 2:
                self.report({'WARNING'}, "Select exactly 2 control points")
                return {'CANCELLED'}
            ckey = ech.canonical_point_pair_key(keys[0], keys[1])
            if ckey not in pairs:
                pairs.append(ckey)
            d['curve_point_pairs'] = pairs
            self.report({'INFO'}, "Point distance label added")
        else:
            keys_sel = set(ech.selected_control_point_keys(me))
            if not keys_sel:
                self.report({'WARNING'}, "Select at least one control point to remove a label")
                return {'CANCELLED'}
            new_p = []
            for pr in pairs:
                k0, k1 = pr[0], pr[1]
                if k0 in keys_sel or k1 in keys_sel:
                    continue
                new_p.append(pr)
            d['curve_point_pairs'] = new_p
            self.report({'INFO'}, "Point distance label(s) removed")

        draw_state.update_dimension_px_handler(context, draw_state.has_dim_overlay_data())
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}


class ALEC_OT_curve_split_at_point(bpy.types.Operator):
    """Split active curve spline(s) at selected point(s) (keeps same object)"""
    bl_idname = "alec.curve_split_at_point"
    bl_label = "Split At Point"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return ech.poll_active_curve_edit_mode(context)

    def execute(self, context):
        obj = context.active_object
        curve = obj.data

        selected_by_spline = {}
        for si, spline in enumerate(curve.splines):
            if spline.type == "BEZIER":
                for pi, bp in enumerate(spline.bezier_points):
                    if bp.select_control_point:
                        selected_by_spline.setdefault(si, set()).add(pi)
            else:
                for pi, pt in enumerate(spline.points):
                    if pt.select:
                        selected_by_spline.setdefault(si, set()).add(pi)

        if not selected_by_spline:
            self.report({'WARNING'}, "Select at least one curve point")
            return {'CANCELLED'}

        saved_mode = context.mode
        if saved_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        splits_done = 0
        skipped_cyclic = 0
        skipped_endpoints = 0

        # Descending keeps lower spline indices stable while removing.
        for si in sorted(selected_by_spline.keys(), reverse=True):
            src = curve.splines[si]
            if src.use_cyclic_u:
                skipped_cyclic += 1
                continue

            point_count = len(src.bezier_points) if src.type == "BEZIER" else len(src.points)
            cuts = sorted(
                pi for pi in selected_by_spline[si]
                if 0 < pi < point_count - 1
            )
            skipped_endpoints += len(selected_by_spline[si]) - len(cuts)
            if not cuts:
                continue

            # Build piece ranges [a..b], duplicating each cut point as both
            # end of previous piece and start of next piece.
            boundaries = [0, *cuts, point_count - 1]
            ranges = [
                (boundaries[i], boundaries[i + 1])
                for i in range(len(boundaries) - 1)
            ]

            for start, end in ranges:
                new_spline = curve.splines.new(type=src.type)
                _copy_spline_settings(src, new_spline)
                new_spline.use_cyclic_u = False
                count = end - start + 1

                if src.type == "BEZIER":
                    new_spline.bezier_points.add(count - 1)
                    for j, src_i in enumerate(range(start, end + 1)):
                        _copy_bezier_point(src.bezier_points[src_i], new_spline.bezier_points[j])
                    for bp in new_spline.bezier_points:
                        bp.select_control_point = False
                        bp.select_left_handle = False
                        bp.select_right_handle = False
                else:
                    new_spline.points.add(count - 1)
                    for j, src_i in enumerate(range(start, end + 1)):
                        _copy_spline_point(src.points[src_i], new_spline.points[j])
                    for pt in new_spline.points:
                        pt.select = False

            curve.splines.remove(src)
            splits_done += len(cuts)

        curve.update_tag()

        if saved_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='EDIT')

        if splits_done == 0:
            if skipped_cyclic:
                self.report({'WARNING'}, "No split done (cyclic splines are unsupported)")
            else:
                self.report({'WARNING'}, "No valid interior points selected")
            return {'CANCELLED'}

        info = f"Split at {splits_done} point(s)"
        if skipped_endpoints:
            info += f" ({skipped_endpoints} endpoint(s) skipped)"
        if skipped_cyclic:
            info += f" ({skipped_cyclic} cyclic spline(s) skipped)"
        self.report({'INFO'}, info)
        return {'FINISHED'}


class ALEC_OT_coplanar_curve_three_point_plane(bpy.types.Operator):
    """Snapshot selection, deselect, then select 3 points to define a plane; all snapshotted points are projected onto it."""
    bl_idname = "alec.coplanar_curve_three_point_plane"
    bl_label = "3-Point Plane"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not ech.poll_active_curve_edit_mode(context):
            return False
        obj = context.active_object
        return len(ech.gather_selected_curve_targets(obj.data)) >= 1

    def invoke(self, context, event):
        obj = context.active_object
        curve = obj.data
        self._keys = ech.snapshot_selected_curve_keys(curve)
        if not self._keys:
            self.report({'WARNING'}, "Select at least one point to project")
            return {'CANCELLED'}

        self._colinear_warned = False
        self._timer = None
        self._overlay_space = None
        self._saved_display_handle = None
        space = context.space_data
        if isinstance(space, bpy.types.SpaceView3D):
            self._overlay_space = space
            self._saved_display_handle = space.overlay.display_handle

        bpy.ops.curve.select_all(action='DESELECT')

        if self._overlay_space is not None:
            self._overlay_space.overlay.display_handle = 'ALL'

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)

        context.workspace.status_text_set(
            "Coplanar: select exactly 3 points for the plane (Esc to cancel)"
        )
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            self._cleanup(context)
            self.report({'INFO'}, "Cancelled")
            return {'CANCELLED'}

        if event.type == 'TIMER':
            obj = context.active_object
            if not obj or obj.type != 'CURVE' or context.mode != 'EDIT_CURVE':
                self._cleanup(context)
                return {'CANCELLED'}

            curve = obj.data
            definers = ech.gather_selected_curve_targets(curve)
            n = len(definers)

            if n != 3:
                self._colinear_warned = False
                return {'RUNNING_MODAL'}

            co0 = obj.matrix_world @ definers[0].get_co()
            co1 = obj.matrix_world @ definers[1].get_co()
            co2 = obj.matrix_world @ definers[2].get_co()
            normal = (co1 - co0).cross(co2 - co0)
            if normal.length_squared < 1e-20:
                if not self._colinear_warned:
                    self.report({'WARNING'}, "The 3 points are collinear")
                    self._colinear_warned = True
                return {'RUNNING_MODAL'}

            targets = ech.keys_to_targets(curve, self._keys)
            if len(targets) != len(self._keys):
                self.report({'WARNING'}, "Curve topology changed; aborting")
                self._cleanup(context)
                return {'CANCELLED'}

            ech.project_curve_targets_to_plane(
                targets, obj, co0, normal, factor=1.0
            )
            curve.update_tag()
            self._cleanup(context)
            self.report({'INFO'}, "Projected to plane")
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def _cleanup(self, context):
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        context.workspace.status_text_set(None)

        if self._overlay_space is not None and self._saved_display_handle is not None:
            self._overlay_space.overlay.display_handle = self._saved_display_handle
            self._overlay_space = None
            self._saved_display_handle = None


classes = (
    ALEC_OT_set_curve_point_length,
    ALEC_OT_curve_point_dimension,
    ALEC_OT_curve_split_at_point,
    ALEC_OT_coplanar_curve_three_point_plane,
)
