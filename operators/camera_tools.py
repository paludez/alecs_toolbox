import bpy


def _view3d_window_region(context):
    """Region WINDOW for the current 3D View area (not the N-panel / toolbar region)."""
    area = context.area
    if area is None or area.type != "VIEW_3D":
        return None
    return next((r for r in area.regions if r.type == "WINDOW"), None)


def _camera_data_from_context(context):
    obj = context.active_object
    if obj and obj.type == "CAMERA":
        return obj.data
    cam = context.scene.camera
    if cam and cam.type == "CAMERA":
        return cam.data
    return None


class ALEC_OT_camera_passepartout(bpy.types.Operator):
    """Toggle camera passepartout alpha between 1.0 and 0.5."""

    bl_idname = "alec.camera_passepartout"
    bl_label = "Passepartout"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _camera_data_from_context(context) is not None

    def execute(self, context):
        space = context.space_data
        if space is not None and hasattr(space, "context"):
            try:
                space.context = "DATA"
            except (TypeError, AttributeError):
                pass
        cam_data = _camera_data_from_context(context)
        if cam_data is None:
            return {"CANCELLED"}
        a = cam_data.passepartout_alpha
        # comută între „plin” (1) și „jumătate” (0.5)
        if a >= 0.75:
            cam_data.passepartout_alpha = 0.7
        else:
            cam_data.passepartout_alpha = 1.0
        return {"FINISHED"}


class ALEC_OT_new_camera_to_view(bpy.types.Operator):
    """New scene camera, then match it to the current viewport (Ctrl+Alt+Numpad 0).

    `view3d.camera_to_view` must run with the 3D View WINDOW region. From the
    sidebar, `context.region` is the panel region, so framing is wrong unless we
    override — that is why it did not feel like 3ds Max “camera from view”.
    """

    bl_idname = "alec.new_camera_to_view"
    bl_label = "New Cam."
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not context.area or context.area.type != "VIEW_3D":
            return False
        space = context.space_data
        if space is None or getattr(space, "type", None) != "VIEW_3D":
            return False
        return getattr(space, "region_3d", None) is not None

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        # Default placement; real pose comes from camera_to_view (same as add + align to view).
        bpy.ops.object.camera_add(enter_editmode=False, align="WORLD")
        cam = context.active_object
        if cam is None or cam.type != "CAMERA":
            return {"CANCELLED"}
        context.scene.camera = cam
        win_region = _view3d_window_region(context)
        if win_region is None:
            return {"CANCELLED"}
        with context.temp_override(
            window=context.window,
            screen=context.screen,
            area=context.area,
            region=win_region,
            space_data=context.space_data,
        ):
            return bpy.ops.view3d.camera_to_view()


classes = (
    ALEC_OT_camera_passepartout,
    ALEC_OT_new_camera_to_view,
)
