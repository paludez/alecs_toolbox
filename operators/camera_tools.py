import math

import bpy
from mathutils import Matrix, Vector

_ALEC_TARGET_CON_NAME = "Alec Target"

_CAM_RIG_UPDATING = False
_CAM_SPHERE_PROP_NAMES = (
    "alec_cam_distance",
    "alec_cam_angle",
    "alec_cam_elevation",
)

_msgbus_owner = object()


def _on_lens_changed():
    global _lens_sync_busy
    if _lens_sync_busy:
        return
    scene = bpy.context.scene
    if scene is None:
        return
    cam = scene_persp_camera(scene)
    if cam is None:
        return
    cur_lens = float(cam.data.lens)
    mirror_lens = float(getattr(scene, "alec_focal_lens_ui", cur_lens))
    if abs(mirror_lens - cur_lens) <= 1e-4:
        return
    _lens_sync_busy = True
    try:
        scene.alec_focal_lens_ui = cur_lens
    finally:
        _lens_sync_busy = False


def _subscribe_lens_msgbus():
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.Camera, "lens"),
        owner=_msgbus_owner,
        args=(),
        notify=_on_lens_changed,
    )


def _unsubscribe_lens_msgbus():
    bpy.msgbus.clear_by_owner(_msgbus_owner)


def _object_in_view_layer(obj, context) -> bool:
    return obj is not None and obj.name in context.view_layer.objects


def camera_sphere_track_target(cam, context):
    """Empty (or object) targeted by camera's Alec Track To constraint, or None."""
    if cam is None or getattr(cam, "type", None) != "CAMERA":
        return None
    con = cam.constraints.get(_ALEC_TARGET_CON_NAME)
    if con is None or con.type != "TRACK_TO":
        return None
    tgt = con.target
    if tgt is None or not _object_in_view_layer(tgt, context):
        return None
    return tgt


def camera_orbit_pivot_world(cam, context):
    """Sphere orbit center at Alec Track Target; None if no valid target."""
    tgt = camera_sphere_track_target(cam, context)
    if tgt is None:
        return None
    return tgt.matrix_world.translation.copy()


def camera_rig_world_position(cam_obj, context):
    """Camera origin on world-Z spherical orbit around Alec Target."""
    tw = camera_orbit_pivot_world(cam_obj, context)
    if tw is None:
        return None
    dist = max(1e-4, float(getattr(cam_obj, "alec_cam_distance", 5.0)))
    az = float(getattr(cam_obj, "alec_cam_angle", 0.0))
    el = float(getattr(cam_obj, "alec_cam_elevation", 0.0))
    c_el = math.cos(el)
    ox = c_el * math.cos(az)
    oy = c_el * math.sin(az)
    oz = math.sin(el)
    u = Vector((ox, oy, oz)).normalized()
    return tw + u * dist


def _apply_camera_sphere_props(cam_obj, context):
    global _CAM_RIG_UPDATING
    if _CAM_RIG_UPDATING:
        return
    if cam_obj is None or cam_obj.type != "CAMERA":
        return
    if camera_sphere_track_target(cam_obj, context) is None:
        return
    pos = camera_rig_world_position(cam_obj, context)
    if pos is None:
        return
    _CAM_RIG_UPDATING = True
    try:
        # Track To aims at target; move origin along orbit sphere.
        if cam_obj.parent is None:
            cam_obj.location = pos
        else:
            mw = cam_obj.matrix_world.copy()
            mw.translation = pos
            cam_obj.matrix_world = mw
    finally:
        _CAM_RIG_UPDATING = False


def _sync_camera_sphere_props_from_world(cam_obj, context):
    """Dist / Az / El from camera vs Alec Target — does not move the camera."""
    global _CAM_RIG_UPDATING
    if _CAM_RIG_UPDATING:
        return
    tgt = camera_sphere_track_target(cam_obj, context)
    if tgt is None:
        return
    try:
        context.view_layer.update()
    except Exception:
        pass

    depsgraph = None
    try:
        depsgraph = context.evaluated_depsgraph_get()
    except Exception:
        pass
    if depsgraph is not None:
        try:
            cw = cam_obj.evaluated_get(depsgraph).matrix_world.translation.copy()
        except ReferenceError:
            cw = cam_obj.matrix_world.translation.copy()
    else:
        cw = cam_obj.matrix_world.translation.copy()

    if depsgraph is not None:
        try:
            tw = tgt.evaluated_get(depsgraph).matrix_world.translation.copy()
        except ReferenceError:
            tw = tgt.matrix_world.translation.copy()
    else:
        tw = tgt.matrix_world.translation.copy()

    delta = cw - tw
    dsq = delta.length_squared
    if dsq < 1e-20:
        _CAM_RIG_UPDATING = True
        try:
            cam_obj.alec_cam_distance = 1e-3
            cam_obj.alec_cam_angle = 0.0
            cam_obj.alec_cam_elevation = 0.0
        finally:
            _CAM_RIG_UPDATING = False
        return

    vz = delta.normalized()
    zn = max(-1.0, min(1.0, vz.z))
    elev = math.asin(zn)
    horiz = math.cos(elev)
    azim = (
        math.atan2(vz.y, vz.x)
        if abs(horiz) > 1e-6
        else float(getattr(cam_obj, "alec_cam_angle", 0.0))
    )
    dist = max(1e-4, math.sqrt(dsq))
    _CAM_RIG_UPDATING = True
    try:
        cam_obj.alec_cam_distance = dist
        cam_obj.alec_cam_angle = azim
        cam_obj.alec_cam_elevation = elev
    finally:
        _CAM_RIG_UPDATING = False


def _alec_cam_distance_update(cam_obj, context):
    _apply_camera_sphere_props(cam_obj, context)


def _alec_cam_angle_update(cam_obj, context):
    _apply_camera_sphere_props(cam_obj, context)


def _alec_cam_elevation_update(cam_obj, context):
    _apply_camera_sphere_props(cam_obj, context)


def register_camera_sphere_object_props() -> None:
    for name in _CAM_SPHERE_PROP_NAMES:
        if hasattr(bpy.types.Object, name):
            try:
                delattr(bpy.types.Object, name)
            except Exception:
                pass
    bpy.types.Object.alec_cam_distance = bpy.props.FloatProperty(
        name="Cam orbit distance",
        description="Distance from Alec Track Target along world spherical orbit",
        default=5.0,
        min=1e-4,
        soft_max=5000.0,
        unit="LENGTH",
        update=_alec_cam_distance_update,
    )
    bpy.types.Object.alec_cam_angle = bpy.props.FloatProperty(
        name="Cam azimuth",
        description="Azimuth around world Z from +X (orbit around Alec Target)",
        default=0.0,
        subtype="ANGLE",
        update=_alec_cam_angle_update,
    )
    bpy.types.Object.alec_cam_elevation = bpy.props.FloatProperty(
        name="Cam elevation",
        description="Elevation from world XY toward +Z (orbit around Alec Target)",
        default=0.0,
        subtype="ANGLE",
        update=_alec_cam_elevation_update,
    )


def unregister_camera_sphere_object_props() -> None:
    for name in _CAM_SPHERE_PROP_NAMES:
        if hasattr(bpy.types.Object, name):
            try:
                delattr(bpy.types.Object, name)
            except Exception:
                pass

# ---------------------------------------------------------------------------
# Focal length UI + dolly compensation
# ---------------------------------------------------------------------------

_lens_sync_busy: bool = False

_SCENE_FOCAL_PROP_NAMES = (
    "alec_focal_lens_ui",
    "alec_focal_dolly_compensate",
    "alec_frame_scale",
    "alec_frame_base_lens",
    "alec_frame_base_matrix",
    "alec_frame_base_view_zoom",
    "alec_camera_marker_step",
)

_FRAME_SCALE_EPS = 1e-6
# Blender camera-view display scale: ((sqrt(2)/100)*zoom + 1)^2 (see view3d draw).
_FRAME_ZOOM_SQRT2_OVER_100 = math.sqrt(2.0) / 100.0
_VIEW_CAMERA_ZOOM_MIN = -30.0
_VIEW_CAMERA_ZOOM_MAX = 600.0
_IDENTITY_MATRIX_FLAT = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)
_last_frame_scale: float = 1.0


def scene_persp_camera(scene):
    """Return scene.camera if it is a perspective Camera object, else None."""
    cam = getattr(scene, "camera", None)
    if cam is None or getattr(cam, "type", None) != "CAMERA":
        return None
    if getattr(cam.data, "type", None) != "PERSP":
        return None
    return cam


def view3d_camera_rv3d(context):
    """RegionView3D when the active space is 3D View in camera perspective, else None."""
    space = context.space_data
    if space is None or getattr(space, "type", None) != "VIEW_3D":
        return None
    rv3d = getattr(space, "region_3d", None)
    if rv3d is None or getattr(rv3d, "view_perspective", None) != "CAMERA":
        return None
    return rv3d


def _clamp_view_camera_zoom(zoom: float) -> float:
    return max(_VIEW_CAMERA_ZOOM_MIN, min(_VIEW_CAMERA_ZOOM_MAX, zoom))


def _view_camera_zoom_display_factor(zoom: float) -> float:
    """On-screen scale from RegionView3D.view_camera_zoom in camera view."""
    return (_FRAME_ZOOM_SQRT2_OVER_100 * zoom + 1.0) ** 2


def _view_camera_zoom_from_display_factor(factor: float) -> float:
    factor = max(factor, 1e-9)
    return 100.0 / math.sqrt(2.0) * (math.sqrt(factor) - 1.0)


def _frame_scale_coupled_lens_and_zoom(
    base_lens: float, base_zoom: float, scale: float
) -> tuple[float, float]:
    """Match focal to viewport zoom so picture inside the orange frame stays still."""
    base_factor = _view_camera_zoom_display_factor(base_zoom)
    if base_factor < 1e-9:
        base_factor = 1.0
    target_factor = base_factor * scale
    new_zoom = _clamp_view_camera_zoom(
        _view_camera_zoom_from_display_factor(target_factor)
    )
    actual_factor = _view_camera_zoom_display_factor(new_zoom)
    # Wider FOV when viewport magnifies, so picture inside the frame stays still.
    new_lens = max(1.0, base_lens * (base_factor / actual_factor))
    return new_lens, new_zoom


def _capture_frame_baseline(scene, cam, rv3d) -> None:
    scene.alec_frame_base_lens = float(cam.data.lens)
    scene.alec_frame_base_view_zoom = float(rv3d.view_camera_zoom)


def _apply_frame_scale_update(scene, context) -> None:
    """Overscan: orange frame size in the window + matched focal (camera stays put)."""
    global _lens_sync_busy, _last_frame_scale
    cam = scene_persp_camera(scene)
    if cam is None:
        return
    rv3d = view3d_camera_rv3d(context)
    if rv3d is None:
        return

    scale = max(float(scene.alec_frame_scale), 0.01)
    if (
        abs(_last_frame_scale - 1.0) < _FRAME_SCALE_EPS
        and abs(scale - 1.0) >= _FRAME_SCALE_EPS
    ):
        _capture_frame_baseline(scene, cam, rv3d)

    base_lens = float(scene.alec_frame_base_lens)
    if base_lens < 1e-6:
        _capture_frame_baseline(scene, cam, rv3d)
        base_lens = float(scene.alec_frame_base_lens)
    base_zoom = float(scene.alec_frame_base_view_zoom)

    cam.data.lens = base_lens
    rv3d.view_camera_zoom = base_zoom

    if abs(scale - 1.0) < _FRAME_SCALE_EPS:
        _lens_sync_busy = True
        try:
            scene.alec_focal_lens_ui = float(cam.data.lens)
        finally:
            _lens_sync_busy = False
        _last_frame_scale = scale
        return

    new_lens, new_zoom = _frame_scale_coupled_lens_and_zoom(
        base_lens, base_zoom, scale
    )
    _lens_sync_busy = True
    try:
        cam.data.lens = new_lens
        rv3d.view_camera_zoom = new_zoom
        scene.alec_focal_lens_ui = new_lens
    finally:
        _lens_sync_busy = False
    _last_frame_scale = scale


def _apply_focal_dolly(cam, tgt, old_lens: float, new_lens: float) -> None:
    """Dolly along view axis in world space. Uses matrix_world so parented cameras work."""
    if abs(old_lens) < 1e-6 or abs(new_lens / old_lens - 1.0) < 1e-9:
        return
    mw = cam.matrix_world
    forward = (mw.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    c = mw.translation.copy()
    t = tgt.matrix_world.translation.copy()
    d0 = (t - c).dot(forward)
    if abs(d0) < 1e-6:
        return
    d1 = d0 * (new_lens / old_lens)
    delta_w = forward * (d0 - d1)
    loc, rot, sca = mw.decompose()
    cam.matrix_world = Matrix.LocRotScale(loc + delta_w, rot, sca)


def _alec_focal_lens_ui_update(scene, context):
    global _lens_sync_busy
    if _lens_sync_busy:
        return
    cam = scene_persp_camera(scene)
    if cam is None:
        return
    new_lens = float(scene.alec_focal_lens_ui)
    old_lens = float(cam.data.lens)
    if abs(new_lens - old_lens) < 1e-6:
        return
    cam.data.lens = new_lens
    global _last_frame_scale
    scene.alec_frame_scale = 1.0
    _last_frame_scale = 1.0
    rv3d = view3d_camera_rv3d(context)
    if rv3d is not None:
        _reset_camera_view_display_offsets(rv3d)
        scene.alec_frame_base_view_zoom = 0.0
        _capture_frame_baseline(scene, cam, rv3d)
    else:
        scene.alec_frame_base_lens = float(cam.data.lens)
    if not bool(scene.alec_focal_dolly_compensate):
        return
    tgt = getattr(context, "active_object", None)
    if tgt is None or tgt is cam:
        return
    _apply_focal_dolly(cam, tgt, old_lens, new_lens)


def _alec_focal_dolly_toggle_update(scene, _context):
    """Re-sync mirror on toggle so no jump occurs when turning dolly on."""
    global _lens_sync_busy
    cam = scene_persp_camera(scene)
    if cam is None:
        return
    _lens_sync_busy = True
    try:
        scene.alec_focal_lens_ui = float(cam.data.lens)
    finally:
        _lens_sync_busy = False


def register_focal_lens_scene_props() -> None:
    for name in _SCENE_FOCAL_PROP_NAMES:
        if hasattr(bpy.types.Scene, name):
            try:
                delattr(bpy.types.Scene, name)
            except Exception:
                pass
    bpy.types.Scene.alec_focal_lens_ui = bpy.props.FloatProperty(
        name="Focal (mm)",
        description=(
            "Focal length of the scene camera (Render Properties camera). "
            "Use with \"Dolly focal\" below to move the camera when you change this value"
        ),
        default=50.0,
        min=1.0,
        soft_max=500.0,
        precision=2,
        step=100,
        update=_alec_focal_lens_ui_update,
    )
    bpy.types.Scene.alec_focal_dolly_compensate = bpy.props.BoolProperty(
        name="Dolly focal",
        description=(
            "On: changing \"Focal (mm)\"  changes the scene camera lens and "
            "slides that camera forward or back so the active object (selected in "
            "the viewport) stays about the same size in frame."
        ),
        default=False,
        update=_alec_focal_dolly_toggle_update,
    )
    bpy.types.Scene.alec_frame_base_lens = bpy.props.FloatProperty(
        name="Frame baseline lens",
        default=50.0,
        options={"HIDDEN"},
    )
    bpy.types.Scene.alec_frame_base_view_zoom = bpy.props.FloatProperty(
        name="Frame baseline view zoom",
        default=0.0,
        options={"HIDDEN"},
    )
    bpy.types.Scene.alec_frame_base_matrix = bpy.props.FloatVectorProperty(
        name="Frame baseline matrix",
        size=16,
        subtype="MATRIX",
        default=_IDENTITY_MATRIX_FLAT,
        options={"HIDDEN"},
    )
    bpy.types.Scene.alec_frame_scale = bpy.props.FloatProperty(
        name="Cadru",
        description=(
            "Overscan / underscan in camera view: resizes the orange frame in the "
            "window and adjusts focal so the picture inside does not appear to move. "
            "Camera position is not changed. 1.0 = reference"
        ),
        default=1.0,
        min=0.5,
        max=2.0,
        precision=2,
        step=1,
        update=_apply_frame_scale_update,
    )
    bpy.types.Scene.alec_camera_marker_step = bpy.props.IntProperty(
        name="Camera marker step",
        description=(
            "Frame step between consecutive camera markers added by the "
            "All Cams / Selected Cams timeline buttons"
        ),
        default=1,
        min=1,
        soft_max=1000,
    )
    _subscribe_lens_msgbus()

def unregister_focal_lens_scene_props() -> None:
    _unsubscribe_lens_msgbus()
    for name in _SCENE_FOCAL_PROP_NAMES:
        if hasattr(bpy.types.Scene, name):
            try:
                delattr(bpy.types.Scene, name)
            except Exception:
                pass


def _camera_target_empty_name(cam) -> str:
    """Empty name: <camera name>_Target (one track target per scene camera)."""
    return f"{cam.name}_Target"


def _is_alec_managed_target_empty(cam, obj) -> bool:
    """True for Camera_Target / Camera_Target.001 empties created by Alec camera tools."""
    if obj is None or getattr(obj, "type", None) != "EMPTY":
        return False
    base = _camera_target_empty_name(cam)
    if obj.name == base:
        return True
    return obj.name.startswith(base + ".")


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
    _sync_camera_sphere_props_from_world(cam, context)


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
    return camera_sphere_track_target(cam, context)


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


class ALEC_OT_camera_target_cursor(bpy.types.Operator):
    """Empty at 3D Cursor; scene camera Track To → empty."""

    bl_idname = "alec.camera_target_cursor"
    bl_label = "Target.Curs"
    bl_description = (
        "Place or move <camera name>_Target empty at the 3D Cursor; "
        "same collection(s) as the scene camera; Track To on scene camera"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        cam = context.scene.camera
        return cam is not None and cam.type == "CAMERA"

    def execute(self, context):
        cam = context.scene.camera
        if cam is None or cam.type != "CAMERA":
            return {"CANCELLED"}
        loc = context.scene.cursor.location.copy()
        _ensure_empty_and_camera_track_to(context, cam, loc)
        return {"FINISHED"}


class ALEC_OT_camera_select_track_target(bpy.types.Operator):
    """Select the scene camera's Alec track target (empty from target buttons)."""

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


class ALEC_OT_select_scene_camera(bpy.types.Operator):
    """Select the scene camera object (scene.camera)."""

    bl_idname = "alec.select_scene_camera"
    bl_label = "Select scene camera"
    bl_description = "Select and activate the scene camera (render camera)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        cam = context.scene.camera
        if cam is None or cam.type != "CAMERA":
            return False
        return cam.name in context.view_layer.objects

    def execute(self, context):
        cam = context.scene.camera
        if cam is None:
            return {"CANCELLED"}
        try:
            bpy.ops.object.select_all(action="DESELECT")
        except RuntimeError:
            pass
        cam.select_set(True)
        context.view_layer.objects.active = cam
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


def _last_marker_frame_any(scene, fallback: int) -> int:
    """Frame of the latest timeline marker (any kind), or fallback if none."""
    if not scene.timeline_markers:
        return fallback
    return max(m.frame for m in scene.timeline_markers)


def _last_camera_marker_frame(scene, fallback: int) -> int:
    """Frame of the latest timeline marker that is bound to a camera, else fallback."""
    cam_frames = [m.frame for m in scene.timeline_markers if m.camera is not None]
    return max(cam_frames) if cam_frames else fallback


def _append_camera_markers(scene, cams, start_frame: int, step: int) -> int:
    """Create one camera-bound timeline marker per camera at start_frame, +step, +2*step ..."""
    count = 0
    for i, cam in enumerate(cams):
        m = scene.timeline_markers.new(cam.name, frame=start_frame + i * step)
        m.camera = cam
        count += 1
    return count


class ALEC_OT_cameras_bind_all_to_timeline(bpy.types.Operator):
    """All scene cameras as timeline markers, appended after the last existing marker."""

    bl_idname = "alec.cameras_bind_all_to_timeline"
    bl_label = "All Cams to Timeline"
    bl_description = (
        "Add a camera-bound timeline marker for every camera in the scene, "
        "starting after the last existing marker (any kind), separated by Step frames"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(o.type == "CAMERA" for o in bpy.data.objects)

    def execute(self, context):
        scene = context.scene
        cams = sorted(
            (o for o in bpy.data.objects if o.type == "CAMERA"),
            key=lambda o: o.name,
        )
        if not cams:
            self.report({"WARNING"}, "No cameras in scene")
            return {"CANCELLED"}
        step = int(scene.alec_camera_marker_step)
        last = _last_marker_frame_any(scene, scene.frame_start - step)
        start_frame = last + step
        n = _append_camera_markers(scene, cams, start_frame, step)
        self.report({"INFO"}, f"Added {n} camera marker(s) starting at frame {start_frame}")
        return {"FINISHED"}


class ALEC_OT_cameras_bind_selected_to_end(bpy.types.Operator):
    """Selected cameras as timeline markers, appended after the last camera marker."""

    bl_idname = "alec.cameras_bind_selected_to_end"
    bl_label = "Selected Cams to End"
    bl_description = (
        "Add a camera-bound timeline marker for every selected camera, "
        "starting after the last camera-bound marker, separated by Step frames"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(o.type == "CAMERA" for o in context.selected_objects)

    def execute(self, context):
        scene = context.scene
        cams = sorted(
            (o for o in context.selected_objects if o.type == "CAMERA"),
            key=lambda o: o.name,
        )
        if not cams:
            self.report({"WARNING"}, "No cameras selected")
            return {"CANCELLED"}
        step = int(scene.alec_camera_marker_step)
        last = _last_camera_marker_frame(scene, scene.frame_start - step)
        start_frame = last + step
        n = _append_camera_markers(scene, cams, start_frame, step)
        self.report({"INFO"}, f"Added {n} camera marker(s) starting at frame {start_frame}")
        return {"FINISHED"}


def _camera_view_elevation_from_horizontal_deg(cam_ob) -> float:
    """Signed elevation (deg) of view axis above/below horizontal XY — same «tilt» readout as in Max docs."""
    mw = cam_ob.matrix_world
    fwd = (mw.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    horiz = math.hypot(fwd.x, fwd.y)
    return math.degrees(math.atan2(fwd.z, horiz))


def _world_z_parallel_screen_drift_x(scene, cam_ob, p0: Vector, dz: Vector) -> float | None:
    """Horizontal NDC delta along a segment parallel to world +Z (like Max vertical-only correction).

    When drift is 0, parallel vertical edges in world read vertical on screen (two-point style).
    Uses Blender's own projection (shift, sensor fit, aspect) via world_to_camera_view.
    """
    c0 = world_to_camera_view(scene, cam_ob, p0)
    c1 = world_to_camera_view(scene, cam_ob, p0 + dz)
    if c0.z <= 0.0 or c1.z <= 0.0:
        return None
    return float(c1.x - c0.x)


def _iter_world_z_probe_segments(cam_ob):
    """Candidates for (base, dz) with dz || world Z — try until depth test passes."""
    mw = cam_ob.matrix_world
    fwd = (mw.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    dz = Vector((0.0, 0.0, 150.0))
    for dist in (2.0, 6.0, 15.0, 40.0):
        yield mw.translation + fwd * dist, dz
    yield Vector((0.0, 0.0, 0.0)), dz


def _camera_lens_shift_straighten_world_vertical(
    cam_ob, *, scene=None
) -> tuple[float, float, float] | None:
    """Set lens shift so world +Z lines stay parallel on screen (Physical Camera / Camera Correction goal).

    3ds Max: Physical Camera uses lens shift for perspective control; legacy Camera Correction
    forces two-point perspective — same visual goal. Blender's shift pairs with render viewplane
    (shift uses same viewfac for X/Y in BKE); an analytic pinhole formula with shift_y ~ fl/sensor_h
    does not match that pipeline.

    Here we solve so ``world_to_camera_view`` gives zero horizontal drift along a segment parallel
    to world Z — matching Blender's projection exactly.

    Returns (shift_x, shift_y, elevation_deg) or None if invalid / cannot converge.
    """
    cd = cam_ob.data
    if cd.type != "PERSP" or scene is None:
        return None
    fl = float(cd.lens)
    if fl < 1e-6:
        return None

    elev = _camera_view_elevation_from_horizontal_deg(cam_ob)

    R = cam_ob.matrix_world.to_3x3().normalized()
    u = R.transposed() @ Vector((0.0, 0.0, 1.0))
    if u.length < 1e-12:
        return None
    u.normalize()
    den = -u.z
    if abs(u.z) < 1e-6:
        return 0.0, 0.0, elev

    sw = float(cd.sensor_width)
    if sw < 1e-6:
        return None
    sx = -(u.x / den) * fl / sw
    sy = -(u.y / den) * fl / sw

    def residual_at(p0: Vector, dzv: Vector, sxa: float, sya: float) -> float | None:
        cd.shift_x = sxa
        cd.shift_y = sya
        return _world_z_parallel_screen_drift_x(scene, cam_ob, p0, dzv)

    max_iter = 28
    tol = 2e-5
    eps = 5e-5

    for p0, dz in _iter_world_z_probe_segments(cam_ob):
        sx_i, sy_i = sx, sy
        for _ in range(max_iter):
            r = residual_at(p0, dz, sx_i, sy_i)
            if r is None:
                break
            if abs(r) < tol:
                cd.shift_x = sx_i
                cd.shift_y = sy_i
                return sx_i, sy_i, elev

            rp = residual_at(p0, dz, sx_i + eps, sy_i)
            rq = residual_at(p0, dz, sx_i, sy_i + eps)
            if rp is None or rq is None:
                break
            jx = (rp - r) / eps
            jy = (rq - r) / eps
            denom = jx * jx + jy * jy
            if denom < 1e-22:
                break
            sx_i -= jx * r / denom
            sy_i -= jy * r / denom

    cd.shift_x = sx
    cd.shift_y = sy
    return sx, sy, elev


class ALEC_OT_camera_lens_shift_verticals(bpy.types.Operator):
    """World-Z verticals parallel (two-point perspective) via lens shift — Physical Camera–style."""

    bl_idname = "alec.camera_lens_shift_verticals"
    bl_label = "Verticals"
    bl_description = (
        "Like 3ds Max Physical Camera lens shift: set Shift X/Y so lines parallel to world Z "
        "stay vertical in frame without changing rotation. Scene camera, Perspective only"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        cam = scene_persp_camera(context.scene)
        return cam is not None

    def execute(self, context):
        cam = scene_persp_camera(context.scene)
        if cam is None:
            return {"CANCELLED"}
        result = _camera_lens_shift_straighten_world_vertical(cam, scene=context.scene)
        if result is None:
            self.report(
                {"WARNING"},
                "Scene camera must be Perspective (not ortho/panorama) with valid focal length",
            )
            return {"CANCELLED"}
        sx_raw, sy_raw, elev_deg = result
        cam.data.shift_x = sx_raw
        cam.data.shift_y = sy_raw
        sx = float(cam.data.shift_x)
        sy = float(cam.data.shift_y)
        clamped = abs(sx - sx_raw) > 1e-5 or abs(sy - sy_raw) > 1e-5
        self.report(
            {"INFO"},
            f"Lens shift X={sx:.3f} Y={sy:.3f} (view tilt from horizontal {elev_deg:+.1f} deg)",
        )
        if clamped:
            self.report(
                {"INFO"},
                "Shift hit Blender camera limit - reduce tilt or widen focal if edges still wrong",
            )
        return {"FINISHED"}


class ALEC_OT_camera_rig_read_sphere(bpy.types.Operator):
    """Set Dist/Az./El from scene camera vs Alec Target; camera does not move."""

    bl_idname = "alec.camera_rig_read_sphere"
    bl_label = "Sync cam orbit"
    bl_description = (
        "Recompute Distance, Azimuth, Elevation from the scene camera vs its Alec Target empty"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        cam = context.scene.camera
        if cam is None or cam.type != "CAMERA":
            return False
        return camera_sphere_track_target(cam, context) is not None

    def execute(self, context):
        cam = context.scene.camera
        if cam is None or cam.type != "CAMERA":
            return {"CANCELLED"}
        try:
            context.view_layer.update()
        except Exception:
            pass
        _sync_camera_sphere_props_from_world(cam, context)
        return {"FINISHED"}


def _camera_track_to_constraints_to_clear(cam):
    """Every Track To on camera (orbit tools use Track To — not resolved by constraint name)."""
    return [c for c in cam.constraints if c.type == "TRACK_TO"]


class ALEC_OT_camera_clear_track_target(bpy.types.Operator):
    """Remove Track To constraints from scene camera; freeze pose; delete managed target empties."""

    bl_idname = "alec.camera_clear_track_target"
    bl_label = "Clear target"
    bl_description = (
        "Remove every Track To from scene camera; orientation stays as on screen; "
        "deletes Camera_Target empties when created by Alec (name pattern)"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        cam = context.scene.camera
        if cam is None or cam.type != "CAMERA":
            return False
        return len(_camera_track_to_constraints_to_clear(cam)) > 0

    def execute(self, context):
        cam = context.scene.camera
        if cam is None or cam.type != "CAMERA":
            return {"CANCELLED"}
        to_clear = _camera_track_to_constraints_to_clear(cam)
        if not to_clear:
            return {"CANCELLED"}
        uniq_targets = []
        seen = set()
        for con in to_clear:
            t = getattr(con, "target", None)
            if t is not None and t not in seen:
                seen.add(t)
                uniq_targets.append(t)

        try:
            context.view_layer.update()
        except Exception:
            pass

        depsgraph = None
        try:
            depsgraph = context.evaluated_depsgraph_get()
        except Exception:
            pass
        if depsgraph is not None:
            try:
                mw = cam.evaluated_get(depsgraph).matrix_world.copy()
            except ReferenceError:
                mw = cam.matrix_world.copy()
        else:
            mw = cam.matrix_world.copy()

        for con in to_clear:
            cam.constraints.remove(con)
        cam.matrix_world = mw

        try:
            context.view_layer.update()
        except Exception:
            pass

        for tgt_obj in uniq_targets:
            if _is_alec_managed_target_empty(cam, tgt_obj):
                try:
                    bpy.data.objects.remove(tgt_obj, do_unlink=True)
                except Exception:
                    pass

        return {"FINISHED"}


classes = (
    ALEC_OT_camera_passepartout,
    ALEC_OT_toggle_lock_camera,
    ALEC_OT_view_center_camera,
    ALEC_OT_camera_target_dist,
    ALEC_OT_camera_target_obj,
    ALEC_OT_camera_target_cursor,
    ALEC_OT_camera_clear_track_target,
    ALEC_OT_camera_select_track_target,
    ALEC_OT_select_scene_camera,
    ALEC_OT_new_camera_to_view,
    ALEC_OT_cameras_bind_all_to_timeline,
    ALEC_OT_cameras_bind_selected_to_end,
    ALEC_OT_camera_rig_read_sphere,
    ALEC_OT_camera_lens_shift_verticals,
)
