import math

import bpy
from mathutils import Vector

_LIGHT_RIG_UPDATING = False

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


def light_rig_world_position(light_obj, context):
    """Sphere around track target: azimuth around world Z from +X, elevation from XY toward +Z."""
    tgt = track_target_object(light_obj, context)
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
    if track_target_object(light_obj, context) is None:
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


def _alec_lt_distance_update(light_obj, context):
    _apply_light_rig_props(light_obj, context)


def _alec_lt_angle_update(light_obj, context):
    _apply_light_rig_props(light_obj, context)


def _alec_lt_elevation_update(light_obj, context):
    _apply_light_rig_props(light_obj, context)


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
        con.name = "Alec Track Target"
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


classes = (
    ALEC_OT_light_add,
    ALEC_OT_light_area_shape,
    ALEC_OT_new_light_rig,
)
