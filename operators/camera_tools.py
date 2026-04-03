import bpy
from mathutils import Vector

_ALEC_TARGET_CON_NAME = "Alec Target"


def _camera_target_empty_name(cam) -> str:
    """Empty name: <camera name>_Target (one track target per scene camera)."""
    return f"{cam.name}_Target"


def _sync_empty_collections_with_camera(scene, empty, cam) -> None:
    """Keep empty in the same collection(s) as the camera; unlink from others."""
    cam_cols = list(cam.users_collection)
    if not cam_cols:
        if empty.name not in scene.collection.objects:
            scene.collection.objects.link(empty)
        return
    for coll in list(empty.users_collection):
        if coll not in cam_cols:
            try:
                coll.objects.unlink(empty)
            except RuntimeError:
                pass
    for coll in cam_cols:
        if empty.name not in coll.objects:
            coll.objects.link(empty)


def _empty_world_location_on_camera_axis(cam, world_point: Vector) -> Vector:
    """Point on camera view axis ∩ plane ⟂ axis through object (foot of O onto axis)."""
    mw = cam.matrix_world
    c = mw.translation
    f = (mw.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    o = world_point.copy()
    t = (o - c).dot(f)
    if t <= 1e-6:
        return o
    return c + f * t


def _object_bbox_center_world(obj) -> Vector:
    """World-space center of the object's axis-aligned bounding box (local bound_box)."""
    mw = obj.matrix_world
    acc = Vector((0.0, 0.0, 0.0))
    for corner in obj.bound_box:
        acc += mw @ Vector(corner)
    return acc * (1.0 / 8.0)


def _ensure_empty_and_camera_track_to(context, cam, loc: Vector) -> None:
    base_name = _camera_target_empty_name(cam)
    empty_name = base_name
    empty = bpy.data.objects.get(empty_name)
    if empty is not None and empty.type != "EMPTY":
        empty = None
        i = 1
        while True:
            candidate = f"{base_name}.{i:03d}"
            o = bpy.data.objects.get(candidate)
            if o is None:
                empty_name = candidate
                break
            if o.type == "EMPTY":
                empty = o
                empty_name = candidate
                break
            i += 1
    elif empty is None:
        pass
    else:
        empty_name = empty.name
    if empty is None:
        empty = bpy.data.objects.new(empty_name, None)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = 0.5
    _sync_empty_collections_with_camera(context.scene, empty, cam)
    empty.location = loc

    old = cam.constraints.get(_ALEC_TARGET_CON_NAME)
    if old is not None:
        cam.constraints.remove(old)

    con = cam.constraints.new(type="TRACK_TO")
    con.name = _ALEC_TARGET_CON_NAME
    con.target = empty
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    context.view_layer.update()


def _view3d_window_region(context):
    """Region WINDOW for the current 3D View area (not the N-panel / toolbar region)."""
    area = context.area
    if area is None or area.type != "VIEW_3D":
        return None
    return next((r for r in area.regions if r.type == "WINDOW"), None)


def _view3d_window_override(context, win_region, space):
    """Context override for bpy.ops.view3d.* that require the 3D View WINDOW region."""
    return context.temp_override(
        window=context.window,
        screen=context.screen,
        area=context.area,
        region=win_region,
        space_data=space,
    )


def _apply_view3d_focal_to_camera(cam, space) -> None:
    """Copy View tab Focal Length (SpaceView3D.lens, mm) onto a perspective camera."""
    if cam.data.type != "PERSP":
        return
    cam.data.lens = float(space.lens)


def _reset_camera_view_display_offsets(rv3d) -> None:
    """Clear viewport-only zoom/pan from camera view (not the Camera object transform)."""
    if rv3d is None:
        return
    rv3d.view_camera_zoom = 0.0
    rv3d.view_camera_offset = (0.0, 0.0)


def _finish_camera_view_post(context, cam, win_region, space) -> None:
    """Passepartout 1.0, camera view, reset viewport zoom/pan offsets."""
    cam.data.passepartout_alpha = 1.0
    with _view3d_window_override(context, win_region, space):
        rv3d = space.region_3d
        if rv3d is not None and rv3d.view_perspective != "CAMERA":
            bpy.ops.view3d.view_camera()
        _reset_camera_view_display_offsets(rv3d)


def _camera_data_from_context(context):
    obj = context.active_object
    if obj and obj.type == "CAMERA":
        return obj.data
    cam = context.scene.camera
    if cam and cam.type == "CAMERA":
        return cam.data
    return None


def _scene_camera_alec_track_target(context):
    """Object targeted by scene camera's Alec Track To constraint, or None."""
    cam = context.scene.camera
    if cam is None or cam.type != "CAMERA":
        return None
    con = cam.constraints.get(_ALEC_TARGET_CON_NAME)
    if con is None or con.type != "TRACK_TO":
        return None
    tgt = con.target
    if tgt is None:
        return None
    if tgt.name not in context.view_layer.objects:
        return None
    return tgt


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


class ALEC_OT_view_center_camera(bpy.types.Operator):
    """Same as Home: camera view → center frame; perspective/ortho → frame all."""

    bl_idname = "alec.view_center_camera"
    bl_label = "Viewport Home"
    bl_description = (
        "Home key: in camera view center the frame; in perspective/ortho frame all"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not context.area or context.area.type != "VIEW_3D":
            return False
        space = context.space_data
        if space is None or getattr(space, "type", None) != "VIEW_3D":
            return False
        if getattr(space, "region_3d", None) is None:
            return False
        return _view3d_window_region(context) is not None

    def execute(self, context):
        space = context.space_data
        win_region = _view3d_window_region(context)
        if win_region is None:
            return {"CANCELLED"}
        rv3d = space.region_3d if space and space.type == "VIEW_3D" else None
        try:
            with _view3d_window_override(context, win_region, space):
                if rv3d is not None and rv3d.view_perspective == "CAMERA":
                    return bpy.ops.view3d.view_center_camera()
                return bpy.ops.view3d.view_all()
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class ALEC_OT_toggle_lock_camera(bpy.types.Operator):
    """Toggle View3D » Lock Camera to View (space_data.lock_camera)."""

    bl_idname = "alec.toggle_lock_camera"
    bl_label = "Lock Camera to View"
    bl_description = "Lock camera to view (same as header padlock)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        space = context.space_data
        if space is None or getattr(space, "type", None) != "VIEW_3D":
            return False
        return context.area is not None and context.area.type == "VIEW_3D"

    def execute(self, context):
        space = context.space_data
        if space is None or getattr(space, "type", None) != "VIEW_3D":
            return {"CANCELLED"}
        space.lock_camera = not bool(getattr(space, "lock_camera", False))
        return {"FINISHED"}


class ALEC_OT_camera_target_dist(bpy.types.Operator):
    """Empty on camera view axis through active object center; scene camera Track To → empty."""

    bl_idname = "alec.camera_target_dist"
    bl_label = "Targ.Dist"
    bl_description = (
        "Empty <scene camera name>_Target on the camera view axis (closest to object center); "
        "same collection(s) as the camera; Track To on the scene camera"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None:
            return False
        cam = context.scene.camera
        if cam is None or cam.type != "CAMERA":
            return False
        if obj == cam:
            return False
        return True

    def execute(self, context):
        obj = context.active_object
        cam = context.scene.camera
        if obj is None or cam is None or obj == cam:
            return {"CANCELLED"}

        loc = _empty_world_location_on_camera_axis(
            cam, obj.matrix_world.translation
        )
        _ensure_empty_and_camera_track_to(context, cam, loc)
        return {"FINISHED"}


class ALEC_OT_camera_target_obj(bpy.types.Operator):
    """Empty at active object bounding-box center; scene camera Track To → empty."""

    bl_idname = "alec.camera_target_obj"
    bl_label = "Target.Obj"
    bl_description = (
        "Empty <scene camera name>_Target at the active object's bbox center; "
        "same collection(s) as the camera; Track To on the scene camera"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None:
            return False
        cam = context.scene.camera
        if cam is None or cam.type != "CAMERA":
            return False
        if obj == cam:
            return False
        return True

    def execute(self, context):
        obj = context.active_object
        cam = context.scene.camera
        if obj is None or cam is None or obj == cam:
            return {"CANCELLED"}

        loc = _object_bbox_center_world(obj)
        _ensure_empty_and_camera_track_to(context, cam, loc)
        return {"FINISHED"}


class ALEC_OT_camera_select_track_target(bpy.types.Operator):
    """Select the scene camera's Alec track target (empty from Targ.Dist / Target.Obj)."""

    bl_idname = "alec.camera_select_track_target"
    bl_label = "Select camera target"
    bl_description = "Select the object the scene camera tracks (Alec Target constraint)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _scene_camera_alec_track_target(context) is not None

    def execute(self, context):
        tgt = _scene_camera_alec_track_target(context)
        if tgt is None:
            return {"CANCELLED"}
        try:
            bpy.ops.object.select_all(action="DESELECT")
        except RuntimeError:
            pass
        tgt.select_set(True)
        context.view_layer.objects.active = tgt
        return {"FINISHED"}


class ALEC_OT_new_camera_to_view(bpy.types.Operator):
    """Add a camera and match the current 3D View (bpy.ops.object.camera_add + view3d.camera_to_view).

    If the viewport is already in camera view, bpy.ops.view3d.camera_to_view is unreliable;
    we set the camera transform from the view matrix instead (same idea as snapping to view).

    Finishes in camera view: passepartout 1, viewport zoom/pan offsets cleared.
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
        if getattr(space, "region_3d", None) is None:
            return False
        return _view3d_window_region(context) is not None

    def execute(self, context):
        space = context.space_data
        win_region = _view3d_window_region(context)
        if win_region is None:
            self.report({"WARNING"}, "No 3D View window region")
            return {"CANCELLED"}

        rv3d = space.region_3d if space and space.type == "VIEW_3D" else None

        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        bpy.ops.object.camera_add(enter_editmode=False, align="WORLD")
        cam = context.active_object
        if cam is None or cam.type != "CAMERA":
            return {"CANCELLED"}
        context.scene.camera = cam

        if cam.data.type == "PERSP":
            _apply_view3d_focal_to_camera(cam, space)

        if rv3d is not None and rv3d.view_perspective == "CAMERA":
            cam.matrix_world = rv3d.view_matrix.inverted()
        else:
            try:
                with _view3d_window_override(context, win_region, space):
                    ret = bpy.ops.view3d.camera_to_view()
            except RuntimeError as exc:
                self.report({"ERROR"}, f"Align camera to view failed: {exc}")
                return {"CANCELLED"}
            if ret != {"FINISHED"}:
                self.report({"WARNING"}, "Align camera to view did not finish")
                return ret

        _finish_camera_view_post(context, cam, win_region, space)
        return {"FINISHED"}


classes = (
    ALEC_OT_camera_passepartout,
    ALEC_OT_toggle_lock_camera,
    ALEC_OT_view_center_camera,
    ALEC_OT_camera_target_dist,
    ALEC_OT_camera_target_obj,
    ALEC_OT_camera_select_track_target,
    ALEC_OT_new_camera_to_view,
)
