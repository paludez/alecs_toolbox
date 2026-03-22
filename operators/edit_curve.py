import bpy
from ..modules import edit_curve_helpers as ech


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


classes = (ALEC_OT_coplanar_curve_three_point_plane,)
