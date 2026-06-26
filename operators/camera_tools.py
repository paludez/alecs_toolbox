import math
from contextlib import contextmanager

import bpy
from mathutils import Matrix, Vector

from ..modules import modal_handler
from ..modules.utils import empty_world_location_on_camera_axis, object_bbox_center_world
from ..modules.sphere_rig_helpers import (
    object_in_view_layer as _object_in_view_layer,
    world_sphere_offset as _world_sphere_offset,
    world_sphere_az_el_dist_from_delta as _world_sphere_az_el_dist_from_delta,
    object_foot_world_xy as _camera_foot_world_xy,
)
from ..modules.camera_helpers import (
    ALEC_TARGET_CON_NAME as _ALEC_TARGET_CON_NAME,
    persp_camera_obj as _persp_camera_obj,
    scene_persp_camera,
    focal_edit_camera,
    view3d_camera_rv3d,
    camera_data_from_context as _camera_data_from_context,
    camera_sphere_track_target,
)

_CAM_RIG_UPDATING = False
_CAM_SPHERE_PROP_NAMES = (
    "alec_cam_distance",
    "alec_cam_angle",
    "alec_cam_elevation",
    "alec_cam_tgt_distance",
    "alec_cam_tgt_angle",
    "alec_cam_tgt_elevation",
)


def camera_target_foot_world_position(cam_obj: bpy.types.Object) -> Vector | None:
    """Alec track target on world sphere around camera foot (Cx, Cy, 0) — same model as lights."""
    if cam_obj is None or cam_obj.type != "CAMERA":
        return None
    foot = _camera_foot_world_xy(cam_obj)
    dist = float(getattr(cam_obj, "alec_cam_tgt_distance", 3.0))
    az = float(getattr(cam_obj, "alec_cam_tgt_angle", 0.0))
    el = float(getattr(cam_obj, "alec_cam_tgt_elevation", 0.0))
    return foot + _world_sphere_offset(az, el, dist)

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
    dist = float(getattr(cam_obj, "alec_cam_distance", 5.0))
    az = float(getattr(cam_obj, "alec_cam_angle", 0.0))
    el = float(getattr(cam_obj, "alec_cam_elevation", 0.0))
    return tw + _world_sphere_offset(az, el, dist)


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
    azim, elev, dist = _world_sphere_az_el_dist_from_delta(
        delta,
        fallback_az=float(getattr(cam_obj, "alec_cam_angle", 0.0)),
    )
    if delta.length_squared < 1e-20:
        _CAM_RIG_UPDATING = True
        try:
            cam_obj.alec_cam_distance = 1e-3
            cam_obj.alec_cam_angle = 0.0
            cam_obj.alec_cam_elevation = 0.0
        finally:
            _CAM_RIG_UPDATING = False
        return

    _CAM_RIG_UPDATING = True
    try:
        cam_obj.alec_cam_distance = max(1e-4, dist)
        cam_obj.alec_cam_angle = azim
        cam_obj.alec_cam_elevation = elev
    finally:
        _CAM_RIG_UPDATING = False


def _apply_camera_target_foot_sphere(cam_obj, context) -> None:
    global _CAM_RIG_UPDATING
    if _CAM_RIG_UPDATING:
        return
    if cam_obj is None or cam_obj.type != "CAMERA":
        return
    tgt = camera_sphere_track_target(cam_obj, context)
    if tgt is None:
        return
    pos = camera_target_foot_world_position(cam_obj)
    if pos is None:
        return
    _CAM_RIG_UPDATING = True
    try:
        if tgt.parent is None:
            tgt.location = pos
        else:
            mw = tgt.matrix_world.copy()
            mw.translation = pos
            tgt.matrix_world = mw
    finally:
        _CAM_RIG_UPDATING = False
    try:
        context.view_layer.update()
    except Exception:
        pass


def _sync_camera_target_foot_sphere_from_world(
    cam_obj: bpy.types.Object, context
) -> None:
    """Rebuild target Dist / Az / El from track empty vs camera foot on world XY."""
    global _CAM_RIG_UPDATING
    if _CAM_RIG_UPDATING:
        return
    tgt = camera_sphere_track_target(cam_obj, context)
    if tgt is None:
        return
    tw = tgt.matrix_world.translation.copy()
    foot = _camera_foot_world_xy(cam_obj)
    delta = tw - foot
    azim, elev, dist = _world_sphere_az_el_dist_from_delta(
        delta,
        fallback_az=float(getattr(cam_obj, "alec_cam_tgt_angle", 0.0)),
    )
    if delta.length_squared < 1e-20:
        return
    _CAM_RIG_UPDATING = True
    try:
        cam_obj.alec_cam_tgt_distance = max(1e-4, dist)
        cam_obj.alec_cam_tgt_angle = azim
        cam_obj.alec_cam_tgt_elevation = elev
    finally:
        _CAM_RIG_UPDATING = False


def _alec_cam_sphere_prop_update(cam_obj, context):
    _apply_camera_sphere_props(cam_obj, context)


def _alec_cam_tgt_distance_update(cam_obj, context):
    _apply_camera_target_foot_sphere(cam_obj, context)


def _alec_cam_tgt_angle_update(cam_obj, context):
    _apply_camera_target_foot_sphere(cam_obj, context)


def _alec_cam_tgt_elevation_update(cam_obj, context):
    _apply_camera_target_foot_sphere(cam_obj, context)


_LEGACY_CAM_TGT_PROP_NAMES = ("alec_cam_tgt_height",)


def register_camera_sphere_object_props() -> None:
    for name in _LEGACY_CAM_TGT_PROP_NAMES + _CAM_SPHERE_PROP_NAMES:
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
        update=_alec_cam_sphere_prop_update,
    )
    bpy.types.Object.alec_cam_angle = bpy.props.FloatProperty(
        name="Cam azimuth",
        description="Azimuth around world Z from +X (orbit around Alec Target)",
        default=0.0,
        subtype="ANGLE",
        update=_alec_cam_sphere_prop_update,
    )
    bpy.types.Object.alec_cam_elevation = bpy.props.FloatProperty(
        name="Cam elevation",
        description="Elevation from world XY toward +Z (orbit around Alec Target)",
        default=0.0,
        subtype="ANGLE",
        update=_alec_cam_sphere_prop_update,
    )
    bpy.types.Object.alec_cam_tgt_distance = bpy.props.FloatProperty(
        name="Target distance",
        description=(
            "Distance from camera XY foot on world Z=0 to Alec track target "
            "(same sphere model as light target rig)"
        ),
        default=3.0,
        min=0.01,
        soft_max=500.0,
        unit="LENGTH",
        update=_alec_cam_tgt_distance_update,
    )
    bpy.types.Object.alec_cam_tgt_angle = bpy.props.FloatProperty(
        name="Target azimuth",
        description="Azimuth around world Z from +X (target sphere around camera foot)",
        default=0.0,
        subtype="ANGLE",
        update=_alec_cam_tgt_angle_update,
    )
    bpy.types.Object.alec_cam_tgt_elevation = bpy.props.FloatProperty(
        name="Target elevation",
        description="Elevation from world XY toward +Z (target sphere around camera foot)",
        default=0.0,
        subtype="ANGLE",
        update=_alec_cam_tgt_elevation_update,
    )


def unregister_camera_sphere_object_props() -> None:
    for name in _LEGACY_CAM_TGT_PROP_NAMES + _CAM_SPHERE_PROP_NAMES:
        if hasattr(bpy.types.Object, name):
            try:
                delattr(bpy.types.Object, name)
            except Exception:
                pass

# ---------------------------------------------------------------------------
# Focal length UI + dolly compensation
# ---------------------------------------------------------------------------

_lens_sync_busy: bool = False
_msgbus_owner = object()
_prev_lens_by_cam_data_ptr: dict[int, float] = {}

_SCENE_FOCAL_PROP_NAMES = (
    "alec_focal_dolly_compensate",
    "alec_frame_base_lens",
    "alec_frame_base_cam_name",
    "alec_frame_base_view_zoom",
    "alec_camera_marker_step",
)

# Blender camera-view display scale: ((sqrt(2)/100)*zoom + 1)^2 (see view3d draw).
_FRAME_ZOOM_SQRT2_OVER_100 = math.sqrt(2.0) / 100.0
_VIEW_CAMERA_ZOOM_MIN = -30.0
_VIEW_CAMERA_ZOOM_MAX = 600.0
_CROP_SCALE_MIN = 0.5
_CROP_SCALE_MAX = 2.0
_CROP_MODAL_DRAG_SENS = 0.002


@contextmanager
def _lens_sync_guard():
    global _lens_sync_busy
    _lens_sync_busy = True
    try:
        yield
    finally:
        _lens_sync_busy = False


def crop_cam_and_rv3d(context):
    """(camera, rv3d) for crop / focal in camera view, or (None, None)."""
    return focal_edit_camera(context), view3d_camera_rv3d(context)


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
    scene.alec_frame_base_cam_name = cam.name


def _ensure_frame_baseline(scene, cam, rv3d) -> None:
    if (
        getattr(scene, "alec_frame_base_cam_name", "") != cam.name
        or float(scene.alec_frame_base_lens) < 1e-6
    ):
        _capture_frame_baseline(scene, cam, rv3d)


def _clamp_crop_scale(scale: float) -> float:
    return max(_CROP_SCALE_MIN, min(_CROP_SCALE_MAX, scale))


def _restore_frame_baseline(scene, cam, rv3d) -> None:
    _ensure_frame_baseline(scene, cam, rv3d)
    with _lens_sync_guard():
        cam.data.lens = float(scene.alec_frame_base_lens)
        rv3d.view_camera_zoom = float(scene.alec_frame_base_view_zoom)


def _apply_crop_scale(scene, context, scale: float) -> bool:
    """Apply crop multiplier from stored baseline; camera position unchanged."""
    cam, rv3d = crop_cam_and_rv3d(context)
    if cam is None or rv3d is None:
        return False
    _ensure_frame_baseline(scene, cam, rv3d)
    new_lens, new_zoom = _frame_scale_coupled_lens_and_zoom(
        float(scene.alec_frame_base_lens),
        float(scene.alec_frame_base_view_zoom),
        _clamp_crop_scale(scale),
    )
    with _lens_sync_guard():
        cam.data.lens = new_lens
        rv3d.view_camera_zoom = new_zoom
        _prev_lens_by_cam_data_ptr[cam.data.as_pointer()] = new_lens
    return True


def _commit_crop_baseline(scene, cam, rv3d) -> None:
    """Keep current lens/zoom as the new crop reference (multiplier back to 1.0)."""
    _capture_frame_baseline(scene, cam, rv3d)


class ALEC_OT_camera_crop_modal(modal_handler.BaseModalOperator, bpy.types.Operator):
    """Crop overscan in camera view: type a multiplier or drag horizontally (like Set Edge Length)."""

    bl_idname = "alec.camera_crop_modal"
    bl_label = "Crop"
    bl_description = (
        "Camera view: drag horizontally or type a crop multiplier (1.0 = current). "
        "Widens/narrows the orange frame; picture inside stays still. LMB or Enter to confirm"
    )
    bl_options = {"REGISTER", "UNDO", "GRAB_CURSOR", "BLOCKING"}

    _initial_scale: float = 1.0
    _current_scale: float = 1.0
    _snap_lens: float = 0.0
    _snap_zoom: float = 0.0

    @classmethod
    def poll(cls, context):
        cam, rv3d = crop_cam_and_rv3d(context)
        return cam is not None and rv3d is not None

    def invoke(self, context, event):
        cam, rv3d = crop_cam_and_rv3d(context)
        if cam is None or rv3d is None:
            self.report({"WARNING"}, "Scene camera and camera view required")
            return {"CANCELLED"}
        _ensure_frame_baseline(context.scene, cam, rv3d)
        self._initial_scale = 1.0
        self._current_scale = 1.0
        self._snap_lens = float(cam.data.lens)
        self._snap_zoom = float(rv3d.view_camera_zoom)
        return self.base_invoke(context, event)

    def get_status_bar_items(self):
        return [("Confirm", "[LMB]"), ("Cancel", "[RMB]"), ("Reset", "[R]")]

    def get_header_args(self, context):
        return {
            "main_label": "Crop",
            "main_value": self._current_scale,
            "suffix": "×",
            "secondary_text": "1.0 = baseline",
            "initial_value": self._initial_scale,
            "precision": 3,
        }

    def _apply_current(self, context) -> None:
        _apply_crop_scale(context.scene, context, self._current_scale)

    def on_mouse_move(self, context, event, delta_x):
        sens = _CROP_MODAL_DRAG_SENS * (0.1 if event.shift else 1.0)
        self._current_scale = _clamp_crop_scale(
            self._initial_scale + delta_x * sens
        )
        self._apply_current(context)

    def on_apply_typed_value(self, context, event):
        if not self.number_input.has_value():
            return
        try:
            typed = self.number_input.get_value(initial_value=self._initial_scale)
            self._current_scale = _clamp_crop_scale(typed)
            self._apply_current(context)
        except ValueError:
            pass

    def on_reset(self, context, event):
        self._current_scale = self._initial_scale
        cam, rv3d = crop_cam_and_rv3d(context)
        if cam is not None:
            _restore_frame_baseline(context.scene, cam, rv3d)

    def on_confirm(self, context, event):
        cam, rv3d = crop_cam_and_rv3d(context)
        if cam is None:
            return
        _commit_crop_baseline(context.scene, cam, rv3d)
        self.report({"INFO"}, f"Crop {self._current_scale:.3f}× committed")

    def on_cancel(self, context, event):
        cam, rv3d = crop_cam_and_rv3d(context)
        if cam is None:
            return
        with _lens_sync_guard():
            cam.data.lens = self._snap_lens
            rv3d.view_camera_zoom = self._snap_zoom
            _prev_lens_by_cam_data_ptr[cam.data.as_pointer()] = self._snap_lens


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


def _on_camera_lens_changed() -> None:
    """Dolly only: runs when a Camera.lens RNA value changes (not a timer)."""
    global _lens_sync_busy
    if _lens_sync_busy:
        return
    ctx = bpy.context
    scene = getattr(ctx, "scene", None)
    if scene is None:
        return
    cam = focal_edit_camera(ctx)
    if cam is None:
        return
    data = cam.data
    key = data.as_pointer()
    new_lens = float(data.lens)
    old_lens = _prev_lens_by_cam_data_ptr.get(key, new_lens)
    _prev_lens_by_cam_data_ptr[key] = new_lens
    if abs(new_lens - old_lens) < 1e-4:
        return
    if float(scene.alec_frame_base_lens) >= 1e-6:
        scene.alec_frame_base_lens = new_lens
    if not bool(scene.alec_focal_dolly_compensate):
        return
    tgt = getattr(ctx, "active_object", None)
    if tgt is None or tgt is cam:
        return
    _apply_focal_dolly(cam, tgt, old_lens, new_lens)


def _subscribe_focal_dolly_msgbus() -> None:
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.Camera, "lens"),
        owner=_msgbus_owner,
        args=(),
        notify=_on_camera_lens_changed,
    )


def _unsubscribe_focal_dolly_msgbus() -> None:
    bpy.msgbus.clear_by_owner(_msgbus_owner)


@bpy.app.handlers.persistent
def _on_load_post(*_):
    _unsubscribe_focal_dolly_msgbus()
    _prev_lens_by_cam_data_ptr.clear()
    for scene in bpy.data.scenes:
        try:
            scene.alec_focal_dolly_compensate = False
        except Exception:
            pass


def _on_dolly_compensate_update(self, context):
    if self.alec_focal_dolly_compensate:
        _unsubscribe_focal_dolly_msgbus()
        _subscribe_focal_dolly_msgbus()
    else:
        _unsubscribe_focal_dolly_msgbus()


def register_focal_lens_scene_props() -> None:
    for name in _SCENE_FOCAL_PROP_NAMES:
        if hasattr(bpy.types.Scene, name):
            try:
                delattr(bpy.types.Scene, name)
            except Exception:
                pass
    bpy.types.Scene.alec_focal_dolly_compensate = bpy.props.BoolProperty(
        name="Dolly focal",
        description=(
            "On: changing focal length slides the edited camera forward or back "
            "so the active object stays about the same size in frame"
        ),
        default=False,
        update=_on_dolly_compensate_update,
    )
    bpy.types.Scene.alec_frame_base_cam_name = bpy.props.StringProperty(
        name="Frame baseline camera",
        default="",
        options={"HIDDEN"},
    )
    bpy.types.Scene.alec_frame_base_lens = bpy.props.FloatProperty(
        name="Frame baseline lens",
        default=0.0,
        options={"HIDDEN"},
    )
    bpy.types.Scene.alec_frame_base_view_zoom = bpy.props.FloatProperty(
        name="Frame baseline view zoom",
        default=0.0,
        options={"HIDDEN"},
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
    _subscribe_focal_dolly_msgbus()
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)


def unregister_focal_lens_scene_props() -> None:
    _unsubscribe_focal_dolly_msgbus()
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    _prev_lens_by_cam_data_ptr.clear()
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
    _sync_camera_target_foot_sphere_from_world(cam, context)


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

        loc = empty_world_location_on_camera_axis(
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

        loc = object_bbox_center_world(obj)
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


class ALEC_OT_camera_target_read_foot_sphere(bpy.types.Operator):
    """Set target Dist/Az/El from track empty vs camera foot on world XY (does not move objects)."""

    bl_idname = "alec.camera_target_read_foot_sphere"
    bl_label = "Sync target foot sphere"
    bl_description = (
        "Recompute target distance, azimuth, and elevation from the tracked empty "
        "and the scene camera projection on world Z=0 (same as lights)"
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
        if camera_sphere_track_target(cam, context) is None:
            self.report({"WARNING"}, "No Alec track target on scene camera")
            return {"CANCELLED"}
        try:
            context.view_layer.update()
        except Exception:
            pass
        _sync_camera_target_foot_sphere_from_world(cam, context)
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
    ALEC_OT_camera_target_read_foot_sphere,
    ALEC_OT_camera_rig_read_sphere,
    ALEC_OT_camera_crop_modal,
)
