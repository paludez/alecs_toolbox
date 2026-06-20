import bpy


def _area_under_mouse(context, event):
    win = context.window
    if not win or not win.screen:
        return None
    mx, my = event.mouse_x, event.mouse_y
    for area in win.screen.areas:
        if area.x <= mx < area.x + area.width and area.y <= my < area.y + area.height:
            return area
    return None


def _schedule_area_update(fn) -> None:
    """Run area type/ui_type changes next frame (avoids HUD region assert on switch)."""

    def _deferred():
        fn()
        return None

    bpy.app.timers.register(_deferred, first_interval=0.0)


def _set_area_view3d(area) -> None:
    if area.type != "VIEW_3D":
        area.type = "VIEW_3D"


def _set_area_shader(area, mode: str, context) -> None:
    if area.type != "NODE_EDITOR":
        area.type = "NODE_EDITOR"
    if getattr(area, "ui_type", None) != "ShaderNodeTree":
        area.ui_type = "ShaderNodeTree"
    space = area.spaces.active
    if space and space.type == "NODE_EDITOR":
        space.shader_type = mode
    if mode == "WORLD":
        world = context.scene.world
        if not world:
            world = bpy.data.worlds.new("World")
            context.scene.world = world
        if not world.use_nodes:
            world.use_nodes = True


def _set_area_uv(area) -> None:
    if area.type != "IMAGE_EDITOR":
        area.type = "IMAGE_EDITOR"
    if getattr(area, "ui_type", None) != "UV":
        area.ui_type = "UV"


def _set_area_image_viewer(area) -> None:
    if area.type != "IMAGE_EDITOR":
        area.type = "IMAGE_EDITOR"
    if getattr(area, "ui_type", None) != "IMAGE_EDITOR":
        area.ui_type = "IMAGE_EDITOR"


def _set_area_graph_fcurves(area) -> None:
    if area.type != "GRAPH_EDITOR":
        area.type = "GRAPH_EDITOR"
    if getattr(area, "ui_type", None) != "FCURVES":
        area.ui_type = "FCURVES"


def _set_area_dopesheet(area) -> None:
    if area.type != "DOPESHEET_EDITOR":
        area.type = "DOPESHEET_EDITOR"
    if getattr(area, "ui_type", None) != "DOPESHEET":
        area.ui_type = "DOPESHEET"


def _is_area_shader_object(area) -> bool:
    if area.type != "NODE_EDITOR":
        return False
    if getattr(area, "ui_type", None) != "ShaderNodeTree":
        return False
    space = area.spaces.active
    return bool(space and space.type == "NODE_EDITOR" and space.shader_type == "OBJECT")


def _is_area_uv(area) -> bool:
    return area.type == "IMAGE_EDITOR" and getattr(area, "ui_type", None) == "UV"


def _is_area_graph_fcurves(area) -> bool:
    return area.type == "GRAPH_EDITOR" and getattr(area, "ui_type", None) == "FCURVES"


def _toggle_shader_editor(area, context) -> None:
    if _is_area_shader_object(area):
        _set_area_shader(area, "WORLD", context)
    else:
        _set_area_shader(area, "OBJECT", context)


def _toggle_uv_image_viewer(area) -> None:
    if _is_area_uv(area):
        _set_area_image_viewer(area)
    else:
        _set_area_uv(area)


def _toggle_animation_editor(area) -> None:
    if _is_area_graph_fcurves(area):
        _set_area_dopesheet(area)
    else:
        _set_area_graph_fcurves(area)


def _invoke_area_under_mouse(self, context, event, deferred_fn):
    if not context.window or not context.window.screen:
        self.report({"WARNING"}, "No active window/screen")
        return {"CANCELLED"}
    target_area = _area_under_mouse(context, event)
    if target_area is None:
        self.report({"WARNING"}, "No area under mouse")
        return {"CANCELLED"}
    area_ref = target_area
    _schedule_area_update(lambda: deferred_fn(area_ref))
    return {"FINISHED"}


class ALEC_OT_set_area_view3d_under_mouse(bpy.types.Operator):
    """Set the editor under mouse to 3D View"""

    bl_idname = "alec.set_area_view3d_under_mouse"
    bl_label = "Set Area To 3D View"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if not context.window or not context.window.screen:
            self.report({"WARNING"}, "No active window/screen")
            return {"CANCELLED"}
        target_area = _area_under_mouse(context, event)
        if target_area is None:
            self.report({"WARNING"}, "No area under mouse")
            return {"CANCELLED"}
        area_ref = target_area
        _schedule_area_update(lambda: _set_area_view3d(area_ref))
        return {"FINISHED"}


class ALEC_OT_toggle_area_shader_under_mouse(bpy.types.Operator):
    """Toggle area under mouse between Shader Editor (Object) and Shader Editor (World)"""

    bl_idname = "alec.toggle_area_shader_under_mouse"
    bl_label = "Toggle Area Shader Object/World"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return _invoke_area_under_mouse(
            self,
            context,
            event,
            lambda area: _toggle_shader_editor(area, context),
        )


class ALEC_OT_toggle_area_uv_image_under_mouse(bpy.types.Operator):
    """Toggle area under mouse between UV Editor and Image Viewer"""

    bl_idname = "alec.toggle_area_uv_image_under_mouse"
    bl_label = "Toggle Area UV/Image Viewer"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return _invoke_area_under_mouse(
            self, context, event, _toggle_uv_image_viewer
        )


class ALEC_OT_toggle_area_graph_dopesheet_under_mouse(bpy.types.Operator):
    """Toggle area under mouse between Graph Editor (F-Curves) and Dope Sheet"""

    bl_idname = "alec.toggle_area_graph_dopesheet_under_mouse"
    bl_label = "Toggle Area Graph/Dope Sheet"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return _invoke_area_under_mouse(
            self, context, event, _toggle_animation_editor
        )


class ALEC_OT_join_area_under_mouse(bpy.types.Operator):
    """Join area under mouse with a neighbor (interactive drag)"""

    bl_idname = "alec.join_area_under_mouse"
    bl_label = "Join Area Under Mouse"
    bl_options = set()

    def invoke(self, context, event):
        win = context.window
        screen = context.screen
        if not win or not screen:
            self.report({"WARNING"}, "No active window/screen")
            return {"CANCELLED"}

        target_area = _area_under_mouse(context, event)
        if target_area is None:
            self.report({"WARNING"}, "No area under mouse")
            return {"CANCELLED"}

        if len(screen.areas) < 2:
            self.report({"WARNING"}, "Need at least two areas to join")
            return {"CANCELLED"}

        region = next((r for r in target_area.regions if r.type == "WINDOW"), None)
        if region is None:
            self.report({"WARNING"}, "No window region in target area")
            return {"CANCELLED"}

        try:
            with bpy.context.temp_override(
                window=win,
                screen=screen,
                area=target_area,
                region=region,
            ):
                bpy.ops.screen.area_join(
                    "INVOKE_DEFAULT",
                    source_xy=(event.mouse_x, event.mouse_y),
                )
        except RuntimeError as exc:
            self.report({"WARNING"}, f"Area join failed: {exc}")
            return {"CANCELLED"}
        # area_join is modal; do not propagate RUNNING_MODAL from a non-modal wrapper.
        return {"FINISHED"}


classes = (
    ALEC_OT_set_area_view3d_under_mouse,
    ALEC_OT_toggle_area_shader_under_mouse,
    ALEC_OT_toggle_area_uv_image_under_mouse,
    ALEC_OT_toggle_area_graph_dopesheet_under_mouse,
    ALEC_OT_join_area_under_mouse,
)
