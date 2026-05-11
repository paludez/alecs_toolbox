import bpy
import math
from ..modules import misc_tools

def _objects_in_view_layer(context):
    return set(context.view_layer.objects)


def _is_object_editable(ob):
    return bool(getattr(ob, "is_editable", True))


def _hide_get(ob, view_layer):
    try:
        return bool(ob.hide_get(view_layer))
    except TypeError:
        return bool(ob.hide_get())


def _hide_set(ob, hide: bool, view_layer):
    try:
        ob.hide_set(hide, view_layer=view_layer)
    except TypeError:
        ob.hide_set(hide)


def _poll_hide_set(context):
    if context.mode != "OBJECT":
        return False
    if not context.selected_objects:
        return False
    layer = _objects_in_view_layer(context)
    for ob in context.selected_objects:
        if ob in layer and _is_object_editable(ob):
            return True
    return False


def _poll_hide_clear(context):
    return context.mode == "OBJECT"


class ALEC_OT_track_to_active(bpy.types.Operator):
    bl_idname = "alec.track_to_active"
    bl_label = "Track To Active"
    bl_description = "Add a Track To constraint on each selected object, targeting the active object"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            return False
        target = context.active_object
        if target is None:
            return False
        return any(o is not target for o in context.selected_objects)

    def execute(self, context):
        target = context.active_object
        if target is None:
            return {"CANCELLED"}

        added = 0
        for obj in context.selected_objects:
            if obj is target:
                continue
            if obj.library is not None:
                self.report(
                    {"WARNING"},
                    'Skipped "{}" (linked datablock cannot be edited here)'.format(obj.name),
                )
                continue
            con = obj.constraints.new(type="TRACK_TO")
            con.target = target
            con.track_axis = "TRACK_NEGATIVE_Y"
            con.up_axis = "UP_Z"
            added += 1

        if added == 0:
            self.report({"ERROR"}, "No constraints added")
            return {"CANCELLED"}

        context.view_layer.update()
        return {"FINISHED"}


class ALEC_OT_group(bpy.types.Operator):
    """Group selected objects under a new Empty at the world origin"""
    bl_idname = "alec.group"
    bl_label = "Group"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        misc_tools.manage_grouping(context, 'GROUP')
        return {'FINISHED'}


class ALEC_OT_group_active(bpy.types.Operator):
    """Group selected objects under a new Empty at the active object's center"""
    bl_idname = "alec.group_active"
    bl_label = "Group Active"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        misc_tools.manage_grouping(context, 'GROUP_ACTIVE')
        return {'FINISHED'}


class ALEC_OT_ungroup(bpy.types.Operator):
    """Ungroup the selected Empty, releasing all children"""
    bl_idname = "alec.ungroup"
    bl_label = "Ungroup"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        misc_tools.manage_grouping(context, 'UNGROUP')
        return {'FINISHED'}


class ALEC_OT_hide_selected_viewport_render(bpy.types.Operator):
    """Hide selected in viewport (eye) and set hide_render on those objects."""

    bl_idname = "alec.hide_selected_viewport_render"
    bl_label = "Hide Selected (Viewport + Render)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _poll_hide_set(context)

    def execute(self, context):
        vl = context.view_layer
        layer = _objects_in_view_layer(context)
        for ob in context.selected_objects:
            if ob not in layer or not _is_object_editable(ob):
                continue
            _hide_set(ob, True, vl)
            ob.hide_render = True
        return {"FINISHED"}


class ALEC_OT_hide_unselected_viewport_render(bpy.types.Operator):
    """Hide unselected (visible) objects in viewport (eye) and set hide_render."""

    bl_idname = "alec.hide_unselected_viewport_render"
    bl_label = "Hide Unselected (Viewport + Render)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _poll_hide_set(context)

    def execute(self, context):
        vl = context.view_layer
        selected = set(context.selected_objects)
        for ob in vl.objects:
            if ob in selected:
                continue
            if not _is_object_editable(ob):
                continue
            if _hide_get(ob, vl):
                continue
            _hide_set(ob, True, vl)
            ob.hide_render = True
        return {"FINISHED"}


class ALEC_OT_hide_view_clear_viewport_render(bpy.types.Operator):
    """Reveal objects hidden in viewport (eye) and clear hide_render on them."""

    bl_idname = "alec.hide_view_clear_viewport_render"
    bl_label = "Reveal Hidden (Viewport + Render)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _poll_hide_clear(context)

    def execute(self, context):
        vl = context.view_layer
        hidden = [
            ob
            for ob in vl.objects
            if _hide_get(ob, vl) and _is_object_editable(ob)
        ]
        for ob in hidden:
            _hide_set(ob, False, vl)
            ob.hide_render = False
        return {"FINISHED"}


class ALEC_OT_selection_rotate_presets(bpy.types.Operator):
    """Rotate selection — X/Y/Z for axis, move mouse for direction/angle preview, click to confirm, ESC to cancel."""
    bl_idname = "alec.selection_rotate_presets"
    bl_label = "Rotate Selection"
    bl_options = {'REGISTER', 'UNDO'}

    angle_degrees: bpy.props.FloatProperty(default=90.0)

    _start_x: int = 0
    _axis: str = None
    _last_angle: float = 0.0

    @classmethod
    def poll(cls, context):
        mode = context.mode
        if mode == 'OBJECT':
            return bool(context.selected_objects)
        if mode in {'EDIT_MESH', 'EDIT_CURVE', 'EDIT_CURVES'}:
            return context.edit_object is not None
        return False

    def _apply_rotation(self, context, angle_deg):
        try:
            bpy.ops.transform.rotate(
                value=math.radians(angle_deg),
                orient_axis=self._axis,
                orient_type=context.scene.transform_orientation_slots[0].type,
            )
        except RuntimeError:
            pass

    def _cancel_last(self, context):
        if abs(self._last_angle) > 1e-6:
            self._apply_rotation(context, -self._last_angle)
            self._last_angle = 0.0

    def invoke(self, context, event):
        self._start_x = event.mouse_x
        self._axis = None
        self._last_angle = 0.0
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'X', 'Y', 'Z'} and event.value == 'PRESS':
            self._cancel_last(context)
            self._axis = event.type
            self._start_x = event.mouse_x

        elif event.type == 'MOUSEMOVE':
            if self._axis is None:
                return {'RUNNING_MODAL'}
            delta = event.mouse_x - self._start_x
            direction = 1.0 if delta >= 0 else -1.0
            new_angle = direction * self.angle_degrees
            if abs(new_angle - self._last_angle) > 1e-6:
                self._cancel_last(context)
                self._apply_rotation(context, new_angle)
                self._last_angle = new_angle

        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            return {'FINISHED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            self._cancel_last(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

classes = (
    ALEC_OT_track_to_active,
    ALEC_OT_group,
    ALEC_OT_group_active,
    ALEC_OT_ungroup,
    ALEC_OT_hide_selected_viewport_render,
    ALEC_OT_hide_unselected_viewport_render,
    ALEC_OT_hide_view_clear_viewport_render,
    ALEC_OT_selection_rotate_presets,
)
