import math

import bpy
from mathutils import Vector

from .camera_tools import (
    _empty_world_location_on_camera_axis,
    _object_bbox_center_world,
)

_LIGHT_RIG_UPDATING = False
_ALEC_LT_CON_NAME = "Alec Track Target"
_LIGHT_TRACK_CON_TYPES_FROZEN = frozenset({"DAMPED_TRACK", "TRACK_TO"})

_LIGHT_RIG_PROP_NAMES = (
    "alec_lt_distance",
    "alec_lt_angle",
    "alec_lt_elevation",
    "alec_lt_tgt_distance",
    "alec_lt_tgt_angle",
    "alec_lt_tgt_elevation",
)


def _world_sphere_direction(az: float, el: float) -> Vector:
    c_el = math.cos(el)
    return Vector((c_el * math.cos(az), c_el * math.sin(az), math.sin(el))).normalized()


def _world_sphere_offset(az: float, el: float, dist: float) -> Vector:
    return _world_sphere_direction(az, el) * max(1e-4, float(dist))


def _world_sphere_az_el_dist_from_delta(
    delta: Vector,
    *,
    fallback_az: float = 0.0,
) -> tuple[float, float, float]:
    dsq = delta.length_squared
    if dsq < 1e-20:
        return fallback_az, 0.0, 1e-3
    vz = delta.normalized()
    zn = max(-1.0, min(1.0, vz.z))
    elev = math.asin(zn)
    horiz = math.cos(elev)
    azim = math.atan2(vz.y, vz.x) if abs(horiz) > 1e-6 else fallback_az
    return azim, elev, math.sqrt(dsq)

_ID_ALEC_LT_MANAGED_TRACK_EMPTY = "alec_lt_track_target"


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


alec_sphere_track_target = _alec_sphere_track_target


def _light_foot_world_xy(light_obj: bpy.types.Object) -> Vector:
    """World XY projection of the lamp (Z = 0)."""
    lw = light_obj.matrix_world.translation
    return Vector((lw.x, lw.y, 0.0))


def light_rig_world_position(light_obj, context):
    """Sphere around track target: azimuth around world Z from +X, elevation from XY toward +Z."""
    tgt = _alec_sphere_track_target(light_obj, context)
    if tgt is None:
        return None

    tw = tgt.matrix_world.translation
    dist = float(getattr(light_obj, "alec_lt_distance", 1.0))
    az = float(getattr(light_obj, "alec_lt_angle", 0.0))
    el = float(getattr(light_obj, "alec_lt_elevation", 0.0))
    return tw + _world_sphere_offset(az, el, dist)


def light_target_foot_world_position(light_obj: bpy.types.Object) -> Vector | None:
    """Track target on world sphere around lamp foot (Lx, Ly, 0)."""
    if light_obj is None or light_obj.type != "LIGHT":
        return None
    foot = _light_foot_world_xy(light_obj)
    dist = float(getattr(light_obj, "alec_lt_tgt_distance", 1.0))
    az = float(getattr(light_obj, "alec_lt_tgt_angle", 0.0))
    el = float(getattr(light_obj, "alec_lt_tgt_elevation", 0.0))
    return foot + _world_sphere_offset(az, el, dist)


def _upgrade_light_track_constraint(light_obj) -> bpy.types.Constraint | None:
    """Orbit rig uses Track To (like scene camera); upgrade legacy Damped Track."""
    con = light_obj.constraints.get(_ALEC_LT_CON_NAME)
    if con is None:
        for c in light_obj.constraints:
            if c.type in _LIGHT_TRACK_CON_TYPES_FROZEN:
                con = c
                break
    if con is None:
        return None
    if con.type == "DAMPED_TRACK":
        tgt = con.target
        name = con.name
        light_obj.constraints.remove(con)
        con = light_obj.constraints.new(type="TRACK_TO")
        con.name = name
        con.target = tgt
    if con.type != "TRACK_TO":
        return None
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return con


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
    con = _upgrade_light_track_constraint(light_obj)
    saved_inf = None
    _LIGHT_RIG_UPDATING = True
    try:
        if con is not None:
            saved_inf = con.influence
            con.influence = 0.0
        # Move on orbit sphere first (Damped Track used to spin in place here).
        if light_obj.parent is None:
            light_obj.location = pos
        else:
            mw = light_obj.matrix_world.copy()
            mw.translation = pos
            light_obj.matrix_world = mw
        if con is not None and saved_inf is not None:
            con.influence = saved_inf
    finally:
        _LIGHT_RIG_UPDATING = False
    try:
        context.view_layer.update()
    except Exception:
        pass


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
    azim, elev, dist = _world_sphere_az_el_dist_from_delta(
        delta,
        fallback_az=float(getattr(light_obj, "alec_lt_angle", 0.0)),
    )
    if delta.length_squared < 1e-20:
        return

    _LIGHT_RIG_UPDATING = True
    try:
        light_obj.alec_lt_distance = dist
        light_obj.alec_lt_angle = azim
        light_obj.alec_lt_elevation = elev
    finally:
        _LIGHT_RIG_UPDATING = False


def _apply_light_target_foot_sphere(light_obj, context) -> None:
    global _LIGHT_RIG_UPDATING
    if _LIGHT_RIG_UPDATING:
        return
    if light_obj is None or light_obj.type != "LIGHT":
        return
    tgt = _alec_sphere_track_target(light_obj, context)
    if tgt is None:
        return
    pos = light_target_foot_world_position(light_obj)
    if pos is None:
        return
    _LIGHT_RIG_UPDATING = True
    try:
        if tgt.parent is None:
            tgt.location = pos
        else:
            mw = tgt.matrix_world.copy()
            mw.translation = pos
            tgt.matrix_world = mw
    finally:
        _LIGHT_RIG_UPDATING = False
    try:
        context.view_layer.update()
    except Exception:
        pass


def _sync_light_target_foot_sphere_from_world(
    light_obj: bpy.types.Object, context
) -> None:
    """Rebuild target Dist / Az / El from track empty vs lamp foot on world XY."""
    global _LIGHT_RIG_UPDATING
    if _LIGHT_RIG_UPDATING:
        return
    tgt = _alec_sphere_track_target(light_obj, context)
    if tgt is None:
        return

    tw = tgt.matrix_world.translation
    foot = _light_foot_world_xy(light_obj)
    delta = tw - foot
    azim, elev, dist = _world_sphere_az_el_dist_from_delta(
        delta,
        fallback_az=float(getattr(light_obj, "alec_lt_tgt_angle", 0.0)),
    )
    if delta.length_squared < 1e-20:
        return

    _LIGHT_RIG_UPDATING = True
    try:
        light_obj.alec_lt_tgt_distance = dist
        light_obj.alec_lt_tgt_angle = azim
        light_obj.alec_lt_tgt_elevation = elev
    finally:
        _LIGHT_RIG_UPDATING = False


def _alec_lt_distance_update(light_obj, context):
    _apply_light_rig_props(light_obj, context)


def _alec_lt_angle_update(light_obj, context):
    _apply_light_rig_props(light_obj, context)


def _alec_lt_elevation_update(light_obj, context):
    _apply_light_rig_props(light_obj, context)


def _alec_lt_tgt_distance_update(light_obj, context):
    _apply_light_target_foot_sphere(light_obj, context)


def _alec_lt_tgt_angle_update(light_obj, context):
    _apply_light_target_foot_sphere(light_obj, context)


def _alec_lt_tgt_elevation_update(light_obj, context):
    _apply_light_target_foot_sphere(light_obj, context)


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


_ALEC_NEW_LIGHT_RIG_EMPTY_BASE = "AlecLightTarget"


def _tag_alec_light_track_target_empty(empty) -> None:
    """Mark empty as created for Alec Track Target — clear uses this instead of guessing by name."""
    if empty is not None:
        empty[_ID_ALEC_LT_MANAGED_TRACK_EMPTY] = True


def _is_idprop_alec_managed_light_track_target(obj) -> bool:
    """True if this EMPTY was wired by our tools for Alec Track Target (persisted ID prop)."""
    if obj is None or getattr(obj, "type", None) != "EMPTY":
        return False
    try:
        v = obj.get(_ID_ALEC_LT_MANAGED_TRACK_EMPTY)
    except AttributeError:
        return False
    return bool(v)


def _should_delete_light_constraint_target_empty(light, tgt_obj) -> bool:
    """Unsafe to drop every con.target EMPTY — only strips ours (tagged) or legacy name patterns."""
    if tgt_obj is None or getattr(tgt_obj, "type", None) != "EMPTY":
        return False
    if _is_idprop_alec_managed_light_track_target(tgt_obj):
        return True
    return _is_alec_managed_light_target_empty(light, tgt_obj) or _is_alec_new_light_rig_target_empty(
        tgt_obj
    )


def _is_alec_managed_light_target_empty(light, obj) -> bool:
    """True for LightName_Target / LightName_Target.001 empties from Alec light tools."""
    if obj is None or getattr(obj, "type", None) != "EMPTY":
        return False
    base = _light_track_target_empty_base_name(light)
    if obj.name == base:
        return True
    return obj.name.startswith(base + ".")


def _is_alec_new_light_rig_target_empty(obj) -> bool:
    """True for empties named AlecLightTarget from alec.new_light_rig (incl. .001 duplicates)."""
    if obj is None or getattr(obj, "type", None) != "EMPTY":
        return False
    base = _ALEC_NEW_LIGHT_RIG_EMPTY_BASE
    if obj.name == base:
        return True
    return obj.name.startswith(base + ".")


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

    con = light_obj.constraints.new(type="TRACK_TO")
    con.name = _ALEC_LT_CON_NAME
    con.target = empty
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    _tag_alec_light_track_target_empty(empty)
    context.view_layer.update()
    if apply_sphere_orbit:
        _apply_light_rig_props(light_obj, context)
    _sync_light_target_foot_sphere_from_world(light_obj, context)


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
    bpy.types.Object.alec_lt_tgt_distance = bpy.props.FloatProperty(
        name="Target Distance",
        description="Distance from lamp XY foot on world Z=0 plane to track target",
        default=3.0,
        min=0.01,
        soft_max=500.0,
        unit="LENGTH",
        update=_alec_lt_tgt_distance_update,
    )
    bpy.types.Object.alec_lt_tgt_angle = bpy.props.FloatProperty(
        name="Target Azimuth",
        description="Azimuth around world Z from +X (target sphere around lamp foot)",
        default=0.0,
        subtype="ANGLE",
        update=_alec_lt_tgt_angle_update,
    )
    bpy.types.Object.alec_lt_tgt_elevation = bpy.props.FloatProperty(
        name="Target Elevation",
        description="Elevation from world XY toward +Z (target sphere around lamp foot)",
        default=0.0,
        subtype="ANGLE",
        update=_alec_lt_tgt_elevation_update,
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
    """Set active Area light Square, Rectangle, Disk, Ellipse"""

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
    """Empty at 3D cursor (target) + Area light with Track To; sphere coords in panel."""

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
        empty.name = _ALEC_NEW_LIGHT_RIG_EMPTY_BASE

        bpy.ops.object.select_all(action="DESELECT")
        bpy.ops.object.light_add(type="AREA", align="WORLD", location=loc)
        light = context.active_object
        if light is None or light.type != "LIGHT":
            return {"CANCELLED"}
        light.name = "AlecAreaRig"

        con = light.constraints.new(type="TRACK_TO")
        con.name = _ALEC_LT_CON_NAME
        con.target = empty
        con.track_axis = "TRACK_NEGATIVE_Z"
        con.up_axis = "UP_Y"

        _tag_alec_light_track_target_empty(empty)

        light.alec_lt_distance = 3.0
        light.alec_lt_angle = 0.0
        light.alec_lt_elevation = 0.0
        _apply_light_rig_props(light, context)
        _sync_light_target_foot_sphere_from_world(light, context)

        light.select_set(True)
        context.view_layer.objects.active = light
        return {"FINISHED"}


class ALEC_OT_light_target_dist(bpy.types.Operator):
    """Empty on each selected lamp axis through active object origin (like camera Targ.Dist)."""

    bl_idname = "alec.light_target_dist"
    bl_label = "Targ.Dist"
    bl_description = (
        "Each selected lamp: <name>_Target on the lamp axis through the active "
        "object origin; Track To; lamp position unchanged (no orbit snap)"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            return False
        obj = context.active_object
        if obj is None or obj.type == "LIGHT":
            return False
        return len(_lights_in_selection(context)) > 0

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type == "LIGHT":
            return {"CANCELLED"}
        lights = _lights_in_selection(context)
        if not lights:
            self.report({"WARNING"}, "Include at least one light in selection")
            return {"CANCELLED"}
        pt = obj.matrix_world.translation.copy()
        for light in lights:
            loc = _empty_world_location_on_camera_axis(light, pt)
            _ensure_empty_and_light_damped_track(
                context, light, loc, apply_sphere_orbit=False
            )
        return {"FINISHED"}


class ALEC_OT_light_target_obj(bpy.types.Operator):
    """BBox center of active (non-light) object; damped-track for every lamp in selection."""

    bl_idname = "alec.light_target_obj"
    bl_label = "Target.Obj"
    bl_description = (
        "Active object is the aim target (bbox center). Include one or more lights in "
        "selection — each gets <name>_Target + Track To; light position unchanged (no orbit snap)"
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


class ALEC_OT_light_target_read_foot_sphere(bpy.types.Operator):
    """Set target Dist/Az/El from track empty vs lamp foot on world XY (does not move objects)."""

    bl_idname = "alec.light_target_read_foot_sphere"
    bl_label = "Sync target foot sphere"
    bl_description = (
        "Recompute target Distance, Azimuth, Elevation from the tracked empty "
        "and the lamp's projection on world Z=0"
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
            self.report({"WARNING"}, "No Alec track constraint / target")
            return {"CANCELLED"}
        _sync_light_target_foot_sphere_from_world(obj, context)
        return {"FINISHED"}


def _light_track_constraints_to_clear(light):
    """All damped/track constraints on lamp (same types Alec orbit uses — not keyed by constraint name)."""
    return [c for c in light.constraints if c.type in _LIGHT_TRACK_CON_TYPES_FROZEN]


class ALEC_OT_light_clear_track_target(bpy.types.Operator):
    """Remove track aim constraints on lamp; freeze pose; delete managed target empties."""

    bl_idname = "alec.light_clear_track_target"
    bl_label = "Clear target"
    bl_description = (
        "Remove every Track To / Damped Track on active lamp (not by name); transform stays put; "
        "removes Alec-created targets (tagged) or legacy empty names LightName_Target / AlecLightTarget"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            return False
        obj = context.active_object
        if obj is None or obj.type != "LIGHT":
            return False
        return len(_light_track_constraints_to_clear(obj)) > 0

    def execute(self, context):
        light = context.active_object
        if light is None or light.type != "LIGHT":
            return {"CANCELLED"}
        to_clear = _light_track_constraints_to_clear(light)
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
                mw = light.evaluated_get(depsgraph).matrix_world.copy()
            except ReferenceError:
                mw = light.matrix_world.copy()
        else:
            mw = light.matrix_world.copy()

        for con in to_clear:
            light.constraints.remove(con)
        light.matrix_world = mw

        try:
            context.view_layer.update()
        except Exception:
            pass

        for tgt_obj in uniq_targets:
            if _should_delete_light_constraint_target_empty(light, tgt_obj):
                try:
                    bpy.data.objects.remove(tgt_obj, do_unlink=True)
                except Exception:
                    pass

        return {"FINISHED"}


class ALEC_OT_light_select_track_target(bpy.types.Operator):
    """Select the active lamp's track target (empty from target buttons)."""

    bl_idname = "alec.light_select_track_target"
    bl_label = "Select light target"
    bl_description = "Select the object the active lamp tracks (Alec track constraint)"
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
        light = context.active_object
        if light is None or light.type != "LIGHT":
            return {"CANCELLED"}
        tgt = _alec_sphere_track_target(light, context)
        if tgt is None:
            return {"CANCELLED"}
        try:
            bpy.ops.object.select_all(action="DESELECT")
        except RuntimeError:
            pass
        tgt.select_set(True)
        context.view_layer.objects.active = tgt
        return {"FINISHED"}


classes = (
    ALEC_OT_light_add,
    ALEC_OT_light_area_shape,
    ALEC_OT_new_light_rig,
    ALEC_OT_light_target_dist,
    ALEC_OT_light_target_obj,
    ALEC_OT_light_target_cursor,
    ALEC_OT_light_clear_track_target,
    ALEC_OT_light_select_track_target,
    ALEC_OT_light_rig_read_sphere,
    ALEC_OT_light_target_read_foot_sphere,
)
