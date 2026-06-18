"""Camera query helpers shared between operators/camera_tools.py and ui/npanel.py."""
import bpy

from .sphere_rig_helpers import object_in_view_layer

ALEC_TARGET_CON_NAME = "Alec Target"


def persp_camera_obj(obj):
    """Return *obj* if it is a perspective Camera object, else None."""
    if obj is None or getattr(obj, "type", None) != "CAMERA":
        return None
    if getattr(obj.data, "type", None) != "PERSP":
        return None
    return obj


def scene_persp_camera(scene):
    """Return scene.camera if it is a perspective Camera object, else None."""
    return persp_camera_obj(getattr(scene, "camera", None))


def focal_edit_camera(context):
    """Perspective camera edited by Focal mm / Crop (viewport, active, then scene)."""
    space = context.space_data
    if space is not None and getattr(space, "type", None) == "VIEW_3D":
        rv3d = getattr(space, "region_3d", None)
        if rv3d is not None and getattr(rv3d, "view_perspective", None) == "CAMERA":
            cam = persp_camera_obj(getattr(space, "camera", None))
            if cam is not None:
                return cam
            return scene_persp_camera(context.scene)
    cam = persp_camera_obj(context.active_object)
    if cam is not None:
        return cam
    return scene_persp_camera(context.scene)


def view3d_camera_rv3d(context):
    """RegionView3D when the active space is 3D View in camera perspective, else None."""
    space = context.space_data
    if space is None or getattr(space, "type", None) != "VIEW_3D":
        return None
    rv3d = getattr(space, "region_3d", None)
    if rv3d is None or getattr(rv3d, "view_perspective", None) != "CAMERA":
        return None
    return rv3d


def camera_data_from_context(context):
    """CameraData from active object or scene camera, or None."""
    obj = context.active_object
    if obj and obj.type == "CAMERA":
        return obj.data
    cam = context.scene.camera
    if cam and cam.type == "CAMERA":
        return cam.data
    return None


def camera_sphere_track_target(cam, context):
    """Empty (or object) targeted by camera's Alec Track To constraint, or None."""
    if cam is None or getattr(cam, "type", None) != "CAMERA":
        return None
    con = cam.constraints.get(ALEC_TARGET_CON_NAME)
    if con is None or con.type != "TRACK_TO":
        return None
    tgt = con.target
    if tgt is None or not object_in_view_layer(tgt, context):
        return None
    return tgt
