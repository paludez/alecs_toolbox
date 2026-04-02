"""Viewport display toggles bound from shortcuts (F3 / F4 / F5)."""

import bpy
from ..modules.modal_handler import ModalNumberInput

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


class ALEC_OT_light_energy_modal(bpy.types.Operator):
    """Adjust selected Light energy, Empty size, or Camera focal length"""

    bl_idname = "alec.light_energy_modal"
    bl_label = "Light Energy Drag"
    bl_options = {"REGISTER", "UNDO", "BLOCKING"}

    _light_names = None
    _start_energy = None
    _start_mouse_y = 0
    _start_mouse_x = 0
    _base_ref = 1.0
    _typed_base = 0.0
    _number_input = None
    _mode = "LIGHT"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type in {"LIGHT", "EMPTY", "CAMERA"})

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

    def _update_header(self, context):
        if not context.area:
            return
        if self._mode == "EMPTY":
            label = "Empty Size"
        elif self._mode == "CAMERA":
            label = "Focal Length"
        else:
            label = "Light Energy"
        typed = self._number_input.value_str if self._number_input else ""
        if typed:
            text = f"{label}: {typed} | Drag X | Shift=fine | Ctrl=fast | LMB/Enter=Confirm | RMB/Esc=Cancel"
        else:
            active = context.active_object
            current = 0.0
            if active and active.type == self._mode:
                if self._mode == "EMPTY":
                    current = float(active.empty_display_size)
                elif self._mode == "CAMERA" and getattr(active, "data", None):
                    current = float(active.data.lens)
                elif getattr(active, "data", None):
                    current = float(active.data.energy)
            suffix = " mm" if self._mode == "CAMERA" else ""
            text = f"{label}: {current:.3f}{suffix} | Drag X | Type value | LMB/Enter=Confirm | RMB/Esc=Cancel"
        context.area.header_text_set(text)

    def invoke(self, context, event):
        active = context.active_object
        if not active or active.type not in {"LIGHT", "EMPTY", "CAMERA"}:
            self.report({"WARNING"}, "Active selection must be Light, Empty or Camera")
            return {"CANCELLED"}

        self._mode = active.type
        selected_lights = [o for o in context.selected_objects if o.type == self._mode]
        lights = selected_lights or [active]

        self._light_names = [o.name for o in lights]
        self._start_energy = {o.name: self._get_obj_value(o) for o in lights}
        self._start_mouse_x = event.mouse_x
        self._start_mouse_y = event.mouse_y
        self._base_ref = max(max(self._start_energy.values(), default=1.0), 0.1)
        self._typed_base = self._get_obj_value(active)
        self._number_input = ModalNumberInput()

        self._update_header(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            if context.area:
                context.area.header_text_set(None)
            return {"FINISHED"}

        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            for obj in self._iter_lights():
                if obj.name in self._start_energy:
                    self._set_obj_value(obj, self._start_energy[obj.name])
            if context.area:
                context.area.header_text_set(None)
            return {"CANCELLED"}

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


classes = (
    ALEC_OT_viewport_toggle_wireframe_xray,
    ALEC_OT_viewport_toggle_overlay_wireframes,
    ALEC_OT_viewport_toggle_solid_rendered,
    ALEC_OT_light_energy_modal,
    ALEC_OT_toggle_mesh_wire_textured,
    ALEC_OT_toggle_mesh_bounds_textured,
)
