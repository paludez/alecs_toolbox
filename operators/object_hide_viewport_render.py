"""Hide in viewport with matching hide_render (Object Mode), mirroring default H / Shift+H / Alt+H.

Uses Object.hide_set / hide_get for the *view-layer* eye icon (same as the H key), not
Object.hide_viewport (monitor = global \"Disable in viewport\").
hide_render matches the render restriction / \"Disable in Renders\" column.
"""

import bpy


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


classes = (
    ALEC_OT_hide_selected_viewport_render,
    ALEC_OT_hide_unselected_viewport_render,
    ALEC_OT_hide_view_clear_viewport_render,
)
