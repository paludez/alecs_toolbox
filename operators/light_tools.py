import math

import bpy
from mathutils import Vector

from .camera_tools import _object_bbox_center_world

_LIGHT_RIG_UPDATING = False
_ALEC_LT_CON_NAME = "Alec Track Target"

_LIGHT_RIG_PROP_NAMES = (
    "alec_lt_distance",
    "alec_lt_angle",
    "alec_lt_elevation",
)


def _object_in_view_layer(obj, context) -> bool:
    return any(o == obj for o in context.view_layer.objects)


def track_target_object(obj, context=None):
    """Return the Object targeted by the first Damped Track / Track To, or None."""
    context = context or bpy.context
    if obj is None or getattr(obj, "type", None) != "LIGHT":
        return None
    for con in obj.constraints:
        if con.type not in {"DAMPED_TRACK", "TRACK_TO"}:
            continue
        t = getattr(con, "target", None)
        if t is None:
            continue
        if _object_in_view_layer(t, context):
            return t
    return None


def _alec_sphere_track_target(light_obj, context) -> bpy.types.Object | None:
    """Alecs named rig constraint if present; else first suitable track constraint."""
    if light_obj is None or getattr(light_obj, "type", None) != "LIGHT":
        return None
    con = light_obj.constraints.get(_ALEC_LT_CON_NAME)
    if con is not None and con.type in {"DAMPED_TRACK", "TRACK_TO"}:
        t = getattr(con, "target", None)
        if t is not None and _object_in_view_layer(t, context):
            return t
    return track_target_object(light_obj, context)


def light_rig_world_position(light_obj, context):
    """Sphere around track target: azimuth around world Z from +X, elevation from XY toward +Z."""
    tgt = _alec_sphere_track_target(light_obj, context)
    if tgt is None:
        return None

    tw = tgt.matrix_world.translation
    dist = max(1e-4, float(getattr(light_obj, "alec_lt_distance", 1.0)))
    az = float(getattr(light_obj, "alec_lt_angle", 0.0))
    el = float(getattr(light_obj, "alec_lt_elevation", 0.0))
    c_el = math.cos(el)
    ox = c_el * math.cos(az)
    oy = c_el * math.sin(az)
    oz = math.sin(el)
    light_dir = Vector((ox, oy, oz)).normalized()
    return tw + light_dir * dist


def _apply_light_rig_props(light_obj, context):
    global _LIGHT_RIG_UPDATING
    if _LIGHT_RIG_UPDATING:
        return
    if light_obj is None or light_obj.type != "LIGHT":
        return
    if _alec_sphere_track_target(light_obj, context) is None:
        return
    pos = light_rig_world_position(light_obj, context)
    if pos is None:
        return
    _LIGHT_RIG_UPDATING = True
    try:
        if light_obj.parent is None:
            light_obj.location = pos
        else:
            mw = light_obj.matrix_world.copy()
            mw.translation = pos
            light_obj.matrix_world = mw
    finally:
        _LIGHT_RIG_UPDATING = False


def _sync_light_sphere_props_from_world(light_obj: bpy.types.Object, context) -> None:
    """Rebuild Dist / Azimuth / Elevation from lamp vs sphere target (no reposition)."""
    global _LIGHT_RIG_UPDATING
    if _LIGHT_RIG_UPDATING:
        return
    tgt = _alec_sphere_track_target(light_obj, context)
    if tgt is None:
        return

    lw = light_obj.matrix_world.translation
    tw = tgt.matrix_world.translation
    delta = lw - tw
    dsq = delta.length_squared
    if dsq < 1e-20:
        return

    vz = delta.normalized()
    zn = max(-1.0, min(1.0, vz.z))
    elev = math.asin(zn)
    horiz = math.cos(elev)
    azim = (
        math.atan2(vz.y, vz.x)
        if abs(horiz) > 1e-6
        else float(getattr(light_obj, "alec_lt_angle", 0.0))
    )
    dist = math.sqrt(dsq)

    _LIGHT_RIG_UPDATING = True
    try:
        light_obj.alec_lt_distance = dist
        light_obj.alec_lt_angle = azim
        light_obj.alec_lt_elevation = elev
    finally:
        _LIGHT_RIG_UPDATING = False


def _alec_lt_distance_update(light_obj, context):
    _apply_light_rig_props(light_obj, context)


def _alec_lt_angle_update(light_obj, context):
    _apply_light_rig_props(light_obj, context)


def _alec_lt_elevation_update(light_obj, context):
    _apply_light_rig_props(light_obj, context)


def _sync_empty_collections_with_light(scene, empty, light) -> None:
    """Keep empty in the same collection(s) as the light; unlink from others."""
    light_cols = list(light.users_collection)
    if not light_cols:
        if empty.name not in scene.collection.objects:
            scene.collection.objects.link(empty)
        return
    for coll in list(empty.users_collection):
        if coll not in light_cols:
            try:
                coll.objects.unlink(empty)
            except RuntimeError:
                pass
    for coll in light_cols:
        if empty.name not in coll.objects:
            coll.objects.link(empty)


def _light_track_target_empty_base_name(light) -> str:
    return f"{light.name}_Target"


def _ensure_empty_and_light_damped_track(
    context,
    light_obj,
    loc: Vector,
    *,
    apply_sphere_orbit: bool = False,
) -> None:
    """Empty at world loc; damped-track on light. Sphere orbit reposition only when asked."""
    base_name = _light_track_target_empty_base_name(light_obj)
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
    _sync_empty_collections_with_light(context.scene, empty, light_obj)
    empty.location = loc

    old = light_obj.constraints.get(_ALEC_LT_CON_NAME)
    if old is not None:
        light_obj.constraints.remove(old)

    con = light_obj.constraints.new(type="DAMPED_TRACK")
    con.name = _ALEC_LT_CON_NAME
    con.target = empty
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.influence = 1.0
    context.view_layer.update()
    if apply_sphere_orbit:
        _apply_light_rig_props(light_obj, context)


def _object_ok_for_bbox_target(obj: bpy.types.Object | None) -> bool:
    """Lights must never be bbox source; bound_box corners required."""
    if obj is None or getattr(obj, "type", None) == "LIGHT":
        return False
    try:
        bb = getattr(obj, "bound_box", None)
    except (AttributeError, RuntimeError):
        return False
    return bb is not None and len(bb) >= 8


def _lights_in_selection(context) -> list:
    """All lamp objects currently in selection."""
    return [o for o in context.selected_objects if getattr(o, "type", None) == "LIGHT"]


def _lights_for_cursor_target(context) -> list:
    """Selected lamps, or lone active lamp if selection has no LIGHT types."""
    lights = _lights_in_selection(context)
    if lights:
        return lights
    ao = context.active_object
    if ao is not None and ao.type == "LIGHT":
        return [ao]
    return []


def register_light_rig_object_props() -> None:
    for name in _LIGHT_RIG_PROP_NAMES:
        if hasattr(bpy.types.Object, name):
            try:
                delattr(bpy.types.Object, name)
            except Exception:
                pass
    bpy.types.Object.alec_lt_distance = bpy.props.FloatProperty(
        name="Distance",
        description="Radius from track target (world sphere)",
        default=3.0,
        min=0.01,
        soft_max=500.0,
        unit="LENGTH",
        update=_alec_lt_distance_update,
    )
    bpy.types.Object.alec_lt_angle = bpy.props.FloatProperty(
        name="Azimuth",
        description="Azimuth around world Z from +X (counterclockwise in top view)",
        default=0.0,
        subtype="ANGLE",
        update=_alec_lt_angle_update,
    )
    bpy.types.Object.alec_lt_elevation = bpy.props.FloatProperty(
        name="Elevation",
        description="Elevation from world XY plane toward +Z",
        default=0.0,
        subtype="ANGLE",
        update=_alec_lt_elevation_update,
    )


def unregister_light_rig_object_props() -> None:
    for name in _LIGHT_RIG_PROP_NAMES:
        if hasattr(bpy.types.Object, name):
            try:
                delattr(bpy.types.Object, name)
            except Exception:
                pass


class ALEC_OT_light_add(bpy.types.Operator):
    """Set active light type, or add a lamp at the 3D cursor if no light is active."""

    bl_idname = "alec.light_add"
    bl_label = "Set / Add Light"
    bl_options = {"REGISTER", "UNDO"}

    light_type: bpy.props.EnumProperty(
        name="Light Type",
        items=(
            ("POINT", "Point", "Point light"),
            ("SUN", "Sun", "Sun light"),
            ("SPOT", "Spot", "Spot light"),
            ("AREA", "Area", "Area light"),
        ),
        default="POINT",
    )

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            return False
        if not context.area or context.area.type != "VIEW_3D":
            return False
        obj = context.active_object
        if obj is not None and obj.type == "LIGHT" and obj.data is not None:
            return True
        return bpy.ops.object.light_add.poll()

    def execute(self, context):
        obj = context.active_object
        if obj is not None and obj.type == "LIGHT" and obj.data is not None:
            obj.data.type = self.light_type
            return {"FINISHED"}
        result = bpy.ops.object.light_add(type=self.light_type)
        if result != {"FINISHED"}:
            return result
        return {"FINISHED"}


_AREA_SHAPE_ITEMS = (
    ("SQUARE", "Square", ""),
    ("RECTANGLE", "Rectangle", ""),
    ("DISK", "Disk", ""),
    ("ELLIPSE", "Ellipse", ""),
)


class ALEC_OT_light_area_shape(bpy.types.Operator):
    """Set active Area light shape (matches Light » Area » Shape)."""

    bl_idname = "alec.light_area_shape"
    bl_label = "Area Light Shape"
    bl_options = {"REGISTER", "UNDO"}

    shape: bpy.props.EnumProperty(name="Shape", items=_AREA_SHAPE_ITEMS)

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            return False
        if not context.area or context.area.type != "VIEW_3D":
            return False
        obj = context.active_object
        if obj is None or obj.type != "LIGHT" or obj.data is None:
            return False
        return obj.data.type == "AREA"

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "LIGHT" or obj.data is None:
            return {"CANCELLED"}
        ld = obj.data
        if ld.type != "AREA":
            return {"CANCELLED"}
        ld.shape = self.shape
        return {"FINISHED"}


class ALEC_OT_new_light_rig(bpy.types.Operator):
    """Empty at 3D cursor (target) + Area light with Damped Track; sphere coords in panel."""

    bl_idname = "alec.new_light_rig"
    bl_label = "New Light"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            return False
        if not context.area or context.area.type != "VIEW_3D":
            return False
        if getattr(context.space_data, "region_3d", None) is None:
            return False
        return bpy.ops.object.empty_add.poll() and bpy.ops.object.light_add.poll()

    def execute(self, context):
        cursor = context.scene.cursor
        loc = cursor.location.copy()

        bpy.ops.object.select_all(action="DESELECT")
        bpy.ops.object.empty_add(type="PLAIN_AXES", align="WORLD", location=loc)
        empty = context.active_object
        if empty is None or empty.type != "EMPTY":
            return {"CANCELLED"}
        empty.name = "AlecLightTarget"

        bpy.ops.object.select_all(action="DESELECT")
        bpy.ops.object.light_add(type="AREA", align="WORLD", location=loc)
        light = context.active_object
        if light is None or light.type != "LIGHT":
            return {"CANCELLED"}
        light.name = "AlecAreaRig"

        con = light.constraints.new(type="DAMPED_TRACK")
        con.name = _ALEC_LT_CON_NAME
        con.target = empty
        con.track_axis = "TRACK_NEGATIVE_Z"
        con.influence = 1.0

        light.alec_lt_distance = 3.0
        light.alec_lt_angle = 0.0
        light.alec_lt_elevation = 0.0
        _apply_light_rig_props(light, context)

        light.select_set(True)
        context.view_layer.objects.active = light
        return {"FINISHED"}


class ALEC_OT_light_target_obj(bpy.types.Operator):
    """BBox center of active (non-light) object; damped-track for every lamp in selection."""

    bl_idname = "alec.light_target_obj"
    bl_label = "Target.Obj"
    bl_description = (
        "Active object is the aim target (bbox center). Include one or more lights in "
        "selection — each gets <name>_Target + Damped Track; light position unchanged (no orbit snap)"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            return False
        tgt = context.active_object
        if not _object_ok_for_bbox_target(tgt):
            return False
        return len(_lights_in_selection(context)) > 0

    def execute(self, context):
        tgt = context.active_object
        if not _object_ok_for_bbox_target(tgt):
            self.report({"WARNING"}, "Active object cannot be used as bbox target")
            return {"CANCELLED"}
        lights = _lights_in_selection(context)
        if not lights:
            self.report({"WARNING"}, "Include at least one light in selection")
            return {"CANCELLED"}
        loc = _object_bbox_center_world(tgt)
        for light in lights:
            _ensure_empty_and_light_damped_track(
                context, light, loc, apply_sphere_orbit=False
            )
        return {"FINISHED"}


class ALEC_OT_light_target_cursor(bpy.types.Operator):
    """3D Cursor on each lamp's Target empty — lights are not repositioned on the rig sphere."""

    bl_idname = "alec.light_target_cursor"
    bl_label = "Target.Curs"
    bl_description = (
        "Each selected lamp (or lone active lamp) gets empty at 3D Cursor + Damped Track; "
        "does not relocate the lamp on Distance/Az/El sphere"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            return False
        return len(_lights_for_cursor_target(context)) > 0

    def execute(self, context):
        lights = _lights_for_cursor_target(context)
        if not lights:
            return {"CANCELLED"}
        loc = context.scene.cursor.location.copy()
        for light in lights:
            _ensure_empty_and_light_damped_track(
                context, light, loc, apply_sphere_orbit=False
            )
        return {"FINISHED"}


class ALEC_OT_light_rig_read_sphere(bpy.types.Operator):
    """Set Dist/Az./El from current lamp position vs sphere target (does not move the lamp)."""

    bl_idname = "alec.light_rig_read_sphere"
    bl_label = "Sync sphere sliders"
    bl_description = (
        "Recompute Distance, Azimuth, Elevation from the light's world translation "
        "and the tracked target empty"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            return False
        obj = context.active_object
        if obj is None or obj.type != "LIGHT":
            return False
        return _alec_sphere_track_target(obj, context) is not None

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "LIGHT":
            return {"CANCELLED"}
        if _alec_sphere_track_target(obj, context) is None:
            self.report({"WARNING"}, "No Alec sphere track constraint / target")
            return {"CANCELLED"}
        _sync_light_sphere_props_from_world(obj, context)
        return {"FINISHED"}


classes = (
    ALEC_OT_light_add,
    ALEC_OT_light_area_shape,
    ALEC_OT_new_light_rig,
    ALEC_OT_light_target_obj,
    ALEC_OT_light_target_cursor,
    ALEC_OT_light_rig_read_sphere,
)
