"""Viewport display toggles bound from shortcuts (F3 / F4 / F5)."""

import bpy

# Per 3D View area: saved shading when F3 wireframe+xray mode is active.
_f3_wire_xray_saved: dict[int, dict] = {}


def _view3d_space(context):
    area = context.area
    if area is None or area.type != "VIEW_3D":
        return None
    space = area.spaces.active
    if space is None or getattr(space, "type", None) != "VIEW_3D":
        return None
    return space


def _space_view3d_for_shading(context):
    """SpaceView3D for shading RNA; prefers space_data, falls back to area.spaces.active."""
    space = getattr(context, "space_data", None)
    if space is not None and getattr(space, "type", None) == "VIEW_3D":
        return space
    area = getattr(context, "area", None)
    if area is not None and area.type == "VIEW_3D":
        s = area.spaces.active
        if s is not None and getattr(s, "type", None) == "VIEW_3D":
            return s
    return None


class ALEC_OT_viewport_toggle_wireframe_xray(bpy.types.Operator):
    """Toggle wireframe + X-Ray; restores previous shading on second press (per viewport)."""

    bl_idname = "alec.viewport_toggle_wireframe_xray"
    bl_label = "Toggle Wireframe + X-Ray"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _view3d_space(context) is not None

    def execute(self, context):
        space = _view3d_space(context)
        if space is None:
            return {"CANCELLED"}
        area = context.area
        key = area.as_pointer()
        shading = space.shading

        if key in _f3_wire_xray_saved:
            s = _f3_wire_xray_saved.pop(key)
            shading.type = s["type"]
            shading.show_xray = s["show_xray"]
            shading.show_xray_wireframe = s["show_xray_wireframe"]
        else:
            _f3_wire_xray_saved[key] = {
                "type": shading.type,
                "show_xray": shading.show_xray,
                "show_xray_wireframe": shading.show_xray_wireframe,
            }
            shading.type = "WIREFRAME"
            shading.show_xray = True
            shading.show_xray_wireframe = True

        return {"FINISHED"}


class ALEC_OT_viewport_toggle_overlay_wireframes(bpy.types.Operator):
    """Toggle overlay wireframes (Viewport Overlays » Wireframe)."""

    bl_idname = "alec.viewport_toggle_overlay_wireframes"
    bl_label = "Toggle Overlay Wireframes"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _view3d_space(context) is not None

    def execute(self, context):
        space = _view3d_space(context)
        if space is None:
            return {"CANCELLED"}
        ov = space.overlay
        ov.show_wireframes = not bool(ov.show_wireframes)
        return {"FINISHED"}


class ALEC_OT_viewport_toggle_solid_rendered(bpy.types.Operator):
    """Toggle viewport shading Solid ↔ Rendered (space_data.shading.type)."""

    bl_idname = "alec.viewport_toggle_solid_rendered"
    bl_label = "Toggle Solid / Rendered"
    bl_description = "Switch viewport shading between Solid and Rendered preview"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _space_view3d_for_shading(context) is not None

    def execute(self, context):
        space = _space_view3d_for_shading(context)
        if space is None:
            return {"CANCELLED"}
        sh = space.shading
        sh.type = "SOLID" if sh.type == "RENDERED" else "RENDERED"
        return {"FINISHED"}


classes = (
    ALEC_OT_viewport_toggle_wireframe_xray,
    ALEC_OT_viewport_toggle_overlay_wireframes,
    ALEC_OT_viewport_toggle_solid_rendered,
)
