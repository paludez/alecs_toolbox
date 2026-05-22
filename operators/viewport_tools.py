"""Viewport-related operators (shading shortcuts, display toggles, align view, Alt+W modal)."""

import bpy
import math
from ..modules.modal_handler import ModalNumberInput
from ..modules import status_bar
from ..modules import viewport_header

def _view3d_space(context):
    area = context.area
    if area is None or area.type != "VIEW_3D":
        return None
    space = area.spaces.active
    if space is None or getattr(space, "type", None) != "VIEW_3D":
        return None
    return space


def _value_modal_subject(context):
    """(LIGHT|EMPTY|CAMERA, active_object) for Alt+W, or (None, None). Active only."""
    active = context.active_object
    if active is None:
        return None, None
    if active.type == "LIGHT" and getattr(active, "data", None):
        return "LIGHT", active
    if active.type == "EMPTY":
        return "EMPTY", active
    if active.type == "CAMERA" and getattr(active, "data", None):
        return "CAMERA", active
    return None, None


def _apply_solid_shading(shading) -> None:
    shading.type = "SOLID"
    shading.show_xray = False
    shading.show_xray_wireframe = False


def _is_f3_wire_xray(shading) -> bool:
    return (
        shading.type == "WIREFRAME"
        and shading.show_xray
        and shading.show_xray_wireframe
    )


def _toggle_shading_or_solid(context, is_active, apply_mode):
    space = _view3d_space(context)
    if space is None:
        return {"CANCELLED"}
    shading = space.shading
    if is_active(shading):
        _apply_solid_shading(shading)
    else:
        apply_mode(shading)
    return {"FINISHED"}


class ALEC_OT_viewport_toggle_wireframe_xray(bpy.types.Operator):
    """Wireframe + X-Ray shading; second press returns to Solid."""

    bl_idname = "alec.viewport_toggle_wireframe_xray"
    bl_label = "Toggle Wireframe + X-Ray"
    bl_description = "Wireframe + X-Ray; press again for Solid"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _view3d_space(context) is not None

    def execute(self, context):
        def apply_wire_xray(sh):
            sh.type = "WIREFRAME"
            sh.show_xray = True
            sh.show_xray_wireframe = True

        return _toggle_shading_or_solid(context, _is_f3_wire_xray, apply_wire_xray)


def _overlay_axes_visible(overlay) -> bool:
    return bool(
        overlay.show_axis_x
        or overlay.show_axis_y
        or overlay.show_axis_z
    )


def _set_overlay_axes_visible(overlay, visible: bool) -> None:
    overlay.show_axis_x = visible
    overlay.show_axis_y = visible
    overlay.show_axis_z = visible


class ALEC_OT_viewport_toggle_overlay_axes(bpy.types.Operator):
    """Toggle viewport axis guide lines (X, Y, Z)."""

    bl_idname = "alec.viewport_toggle_overlay_axes"
    bl_label = "Toggle Axes"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _view3d_space(context) is not None

    def execute(self, context):
        space = _view3d_space(context)
        if space is None:
            return {"CANCELLED"}
        ov = space.overlay
        _set_overlay_axes_visible(ov, not _overlay_axes_visible(ov))
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


class ALEC_OT_viewport_toggle_curve_bezier_handles(bpy.types.Operator):
    """Toggle Bezier handle overlay: hidden, or only for selected control points (SELECTED / NONE)."""

    bl_idname = "alec.viewport_toggle_curve_bezier_handles"
    bl_label = "Toggle Bezier Handles"
    bl_description = "Hide or show Bezier tangents for the selected control points"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if context.mode != "EDIT_CURVE":
            return False
        return _view3d_space(context) is not None

    def execute(self, context):
        space = _view3d_space(context)
        if space is None:
            return {"CANCELLED"}
        ov = space.overlay
        if getattr(ov, "display_handle", "NONE") == "NONE":
            ov.display_handle = "SELECTED"
        else:
            ov.display_handle = "NONE"
        return {"FINISHED"}


class ALEC_OT_viewport_toggle_shading_solid(bpy.types.Operator):
    """Solid shading, then Solid + overlay wireframes; third press clears overlay."""

    bl_idname = "alec.viewport_toggle_shading_solid"
    bl_label = "Toggle Solid Shading"
    bl_description = "Solid, then Solid with overlay wireframes (Alt+F3 toggles overlay in any mode)"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _view3d_space(context) is not None

    def execute(self, context):
        space = _view3d_space(context)
        if space is None:
            return {"CANCELLED"}
        shading = space.shading
        ov = space.overlay
        if shading.type == "SOLID" and ov.show_wireframes:
            ov.show_wireframes = False
            _apply_solid_shading(shading)
        elif shading.type == "SOLID":
            _apply_solid_shading(shading)
            ov.show_wireframes = True
        else:
            _apply_solid_shading(shading)
            ov.show_wireframes = False
        return {"FINISHED"}


class ALEC_OT_viewport_toggle_shading_rendered(bpy.types.Operator):
    """Rendered shading; second press returns to Solid."""

    bl_idname = "alec.viewport_toggle_shading_rendered"
    bl_label = "Toggle Rendered Shading"
    bl_description = "Rendered preview; press again for Solid"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _view3d_space(context) is not None

    def execute(self, context):
        def apply_rendered(sh):
            sh.type = "RENDERED"
            sh.show_xray = False
            sh.show_xray_wireframe = False

        return _toggle_shading_or_solid(
            context,
            lambda sh: sh.type == "RENDERED",
            apply_rendered,
        )


class ALEC_OT_viewport_toggle_shading_material(bpy.types.Operator):
    """Material Preview shading; second press returns to Solid."""

    bl_idname = "alec.viewport_toggle_shading_material"
    bl_label = "Toggle Material Preview"
    bl_description = "Material Preview; press again for Solid"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _view3d_space(context) is not None

    def execute(self, context):
        def apply_material(sh):
            sh.type = "MATERIAL"
            sh.show_xray = False
            sh.show_xray_wireframe = False

        return _toggle_shading_or_solid(
            context,
            lambda sh: sh.type == "MATERIAL",
            apply_material,
        )


class ALEC_OT_light_energy_modal(bpy.types.Operator):
    """Adjust selected Light energy, Empty size, or Camera focal length"""

    bl_idname = "alec.light_energy_modal"
    bl_label = "Adjust Light / Camera / Empty"
    bl_options = {"REGISTER", "UNDO", "BLOCKING"}

    _active_instance = None
    _light_names = None
    _start_energy = None
    _start_mouse_y = 0
    _start_mouse_x = 0
    _base_ref = 1.0
    _typed_base = 0.0
    _number_input = None
    _mode = "LIGHT"
    _modifiers_shift = False
    _modifiers_ctrl = False

    @classmethod
    def draw_status_bar(cls, panel_self, context):
        inst = cls._active_instance
        if inst is None:
            return
        status_bar.draw_shortcuts(panel_self.layout, inst.get_status_bar_items())

    def get_status_bar_items(self):
        return [
            ("Fine", "[Shift]", self._modifiers_shift),
            ("Fast", "[Ctrl]", self._modifiers_ctrl),
            None,
            ("Confirm", "[LMB]"),
            ("Cancel", "[RMB]"),
        ]

    def _header_label(self) -> str:
        if self._mode == "EMPTY":
            return "Empty Size"
        if self._mode == "CAMERA":
            return "Focal Length"
        return "Light Energy"

    @classmethod
    def poll(cls, context):
        _mode, obj = _value_modal_subject(context)
        return obj is not None

    def _iter_lights(self):
        for name in self._light_names or []:
            obj = bpy.data.objects.get(name)
            if obj and obj.type == self._mode:
                if self._mode == "LIGHT" and getattr(obj, "data", None):
                    yield obj
                elif self._mode == "EMPTY":
                    yield obj
                elif self._mode == "CAMERA" and getattr(obj, "data", None):
                    yield obj

    def _get_obj_value(self, obj):
        if self._mode == "EMPTY":
            return float(obj.empty_display_size)
        if self._mode == "CAMERA":
            return float(obj.data.lens)
        return float(obj.data.energy)

    def _set_obj_value(self, obj, value):
        val = max(0.0, float(value))
        if self._mode == "EMPTY":
            obj.empty_display_size = val
        elif self._mode == "CAMERA":
            obj.data.lens = max(1.0, val)
        else:
            obj.data.energy = val

    def _set_energy_all(self, value):
        for obj in self._iter_lights():
            self._set_obj_value(obj, value)

    def _sync_modifiers(self, event) -> None:
        self._modifiers_shift = bool(event.shift)
        self._modifiers_ctrl = bool(event.ctrl)

    def _update_header(self, context):
        if not context.area:
            return
        current = 0.0
        for name in self._light_names or []:
            obj = bpy.data.objects.get(name)
            if obj is not None and obj.type == self._mode:
                current = self._get_obj_value(obj)
                break
        suffix = " mm" if self._mode == "CAMERA" else ""
        typed = self._number_input.value_str if self._number_input else ""
        viewport_header.set_numeric(
            context,
            main_label=self._header_label(),
            main_value=current,
            typed_str=typed,
            suffix=suffix,
            initial_value=self._typed_base,
            precision=3,
        )

    def _modal_cleanup(self, context) -> None:
        self.__class__._active_instance = None
        status_bar.clear_all(context, self.__class__)

    def invoke(self, context, event):
        mode, obj = _value_modal_subject(context)
        if obj is None:
            self.report({"WARNING"}, "Active object must be a Light, Empty, or Camera")
            return {"CANCELLED"}

        self._mode = mode
        self._light_names = [obj.name]
        self._start_energy = {obj.name: self._get_obj_value(obj)}
        self._start_mouse_x = event.mouse_x
        self._start_mouse_y = event.mouse_y
        self._base_ref = max(self._get_obj_value(obj), 0.1)
        self._typed_base = self._get_obj_value(obj)
        self._number_input = ModalNumberInput()
        self._modifiers_shift = bool(event.shift)
        self._modifiers_ctrl = bool(event.ctrl)

        self.__class__._active_instance = self
        status_bar.install_shortcuts(self.__class__)
        self._update_header(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        self._sync_modifiers(event)

        if event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            self._modal_cleanup(context)
            return {"FINISHED"}

        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            for obj in self._iter_lights():
                if obj.name in self._start_energy:
                    self._set_obj_value(obj, self._start_energy[obj.name])
            self._modal_cleanup(context)
            return {"CANCELLED"}

        if event.type in {
            "LEFT_SHIFT",
            "RIGHT_SHIFT",
            "LEFT_CTRL",
            "RIGHT_CTRL",
        } and event.value in {"PRESS", "RELEASE"}:
            self._update_header(context)
            if context.area is not None:
                context.area.tag_redraw()
            return {"RUNNING_MODAL"}

        if self._number_input and self._number_input.handle_event(event):
            if self._number_input.has_value():
                try:
                    val = self._number_input.get_value(initial_value=self._typed_base)
                    self._set_energy_all(val)
                except ValueError:
                    pass
            self._update_header(context)
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            if self._number_input:
                self._number_input.reset()
            dx = event.mouse_x - self._start_mouse_x
            speed = 0.01 * self._base_ref
            if event.shift:
                speed *= 0.2
            if event.ctrl:
                speed *= 5.0
            # Horizontal only: right increases, left decreases.
            delta = dx * speed
            for obj in self._iter_lights():
                start = self._start_energy.get(obj.name, self._get_obj_value(obj))
                self._set_obj_value(obj, start + delta)
            self._update_header(context)
            return {"RUNNING_MODAL"}

        return {"RUNNING_MODAL"}


class ALEC_OT_toggle_mesh_wire_textured(bpy.types.Operator):
    """Toggle selected meshes display between Wire and Textured"""

    bl_idname = "alec.toggle_mesh_wire_textured"
    bl_label = "Toggle Mesh Wire/Textured"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(o.type == "MESH" for o in context.selected_objects)

    def execute(self, context):
        meshes = [o for o in context.selected_objects if o.type == "MESH"]
        if not meshes:
            return {"CANCELLED"}
        target = "TEXTURED" if all(o.display_type == "WIRE" for o in meshes) else "WIRE"
        for obj in meshes:
            obj.display_type = target
        return {"FINISHED"}


class ALEC_OT_toggle_mesh_bounds_textured(bpy.types.Operator):
    """Toggle selected meshes display between Bounds and Textured"""

    bl_idname = "alec.toggle_mesh_bounds_textured"
    bl_label = "Toggle Mesh Bounds/Textured"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(o.type == "MESH" for o in context.selected_objects)

    def execute(self, context):
        meshes = [o for o in context.selected_objects if o.type == "MESH"]
        if not meshes:
            return {"CANCELLED"}
        target = "TEXTURED" if all(o.display_type == "BOUNDS" for o in meshes) else "BOUNDS"
        for obj in meshes:
            obj.display_type = target
        return {"FINISHED"}

_VIEW_AXIS_OPPOSITE = {"TOP": "BOTTOM", "FRONT": "BACK", "RIGHT": "LEFT"}


def _invoke_view_axis(context, event, base_axis: str):
    axis = _VIEW_AXIS_OPPOSITE[base_axis] if event.alt else base_axis
    bpy.ops.view3d.view_axis(type=axis, align_active=True)
    return {'FINISHED'}


class ALEC_OT_view_axis_top(bpy.types.Operator):
    """Align view to Top; Alt for Bottom"""
    bl_idname = "alec.view_axis_top"
    bl_label = "Top"
    bl_description = "Align view to Top (aligned to active object). Hold Alt for Bottom."
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return _invoke_view_axis(context, event, "TOP")


class ALEC_OT_view_axis_front(bpy.types.Operator):
    """Align view to Front; Alt for Back"""
    bl_idname = "alec.view_axis_front"
    bl_label = "Front"
    bl_description = "Align view to Front (aligned to active object). Hold Alt for Back."
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return _invoke_view_axis(context, event, "FRONT")


class ALEC_OT_view_axis_right(bpy.types.Operator):
    """Align view to Right; Alt for Left"""
    bl_idname = "alec.view_axis_right"
    bl_label = "Right"
    bl_description = "Align view to Right (aligned to active object). Hold Alt for Left."
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return _invoke_view_axis(context, event, "RIGHT")


classes = (
    ALEC_OT_viewport_toggle_wireframe_xray,
    ALEC_OT_viewport_toggle_overlay_axes,
    ALEC_OT_viewport_toggle_overlay_wireframes,
    ALEC_OT_viewport_toggle_curve_bezier_handles,
    ALEC_OT_viewport_toggle_shading_solid,
    ALEC_OT_viewport_toggle_shading_rendered,
    ALEC_OT_viewport_toggle_shading_material,
    ALEC_OT_light_energy_modal,
    ALEC_OT_toggle_mesh_wire_textured,
    ALEC_OT_toggle_mesh_bounds_textured,
    ALEC_OT_view_axis_top,
    ALEC_OT_view_axis_front,
    ALEC_OT_view_axis_right,
)
