"""Light query helpers shared between operators/light_tools.py and ui/npanel.py."""
import bpy

from .sphere_rig_helpers import object_in_view_layer

ALEC_LT_CON_NAME = "Alec Track Target"
LIGHT_TRACK_CON_TYPES_FROZEN = frozenset({"DAMPED_TRACK", "TRACK_TO"})


def track_target_object(obj, context=None):
    """Return the Object targeted by the first Damped Track / Track To, or None."""
    context = context or bpy.context
    if obj is None or getattr(obj, "type", None) != "LIGHT":
        return None
    for con in obj.constraints:
        if con.type not in LIGHT_TRACK_CON_TYPES_FROZEN:
            continue
        t = getattr(con, "target", None)
        if t is None:
            continue
        if object_in_view_layer(t, context):
            return t
    return None


def alec_sphere_track_target(light_obj, context) -> bpy.types.Object | None:
    """Alec named rig constraint if present; else first suitable track constraint."""
    if light_obj is None or getattr(light_obj, "type", None) != "LIGHT":
        return None
    con = light_obj.constraints.get(ALEC_LT_CON_NAME)
    if con is not None and con.type in LIGHT_TRACK_CON_TYPES_FROZEN:
        t = getattr(con, "target", None)
        if t is not None and object_in_view_layer(t, context):
            return t
    return track_target_object(light_obj, context)
