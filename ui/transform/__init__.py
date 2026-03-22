"""Transform: operators, RNA, depsgraph (N-panel shell lives in npanel.py)."""

import bpy

from . import props
from . import selection_math as sm
from .operators import (
    ALEC_OT_object_rotation_world,
    ALEC_OT_object_world_translation,
    ALEC_OT_object_rotation_local,
    ALEC_OT_reset_transform_column,
    ALEC_OT_selection_resize_orient,
    ALEC_OT_selection_rotate,
    ALEC_OT_selection_scale_orient,
    ALEC_OT_selection_translate_delta,
)

_classes_operators = (
    ALEC_OT_object_world_translation,
    ALEC_OT_object_rotation_world,
    ALEC_OT_object_rotation_local,
    ALEC_OT_selection_rotate,
    ALEC_OT_selection_translate_delta,
    ALEC_OT_selection_resize_orient,
    ALEC_OT_selection_scale_orient,
    ALEC_OT_reset_transform_column,
)
_classes_pre_panel = (*_classes_operators, props.AlecEditSelectionProps)


def register():
    for cls in _classes_pre_panel:
        bpy.utils.register_class(cls)
    bpy.types.Scene.alec_edit_selection = bpy.props.PointerProperty(type=props.AlecEditSelectionProps)
    bpy.types.Scene.alec_object_world = bpy.props.FloatVectorProperty(
        name="World",
        description="Object translation in world space",
        size=3,
        subtype="TRANSLATION",
        update=props._update_alec_object_world,
    )
    bpy.types.Scene.alec_rotation_world = bpy.props.FloatVectorProperty(
        name="World rotation",
        description="Euler XYZ = rotație world (ca Transform Orientation Global + R X/Y/Z)",
        size=3,
        subtype="EULER",
        update=props._update_alec_rotation_world,
    )
    bpy.types.Scene.alec_rotation_local = bpy.props.FloatVectorProperty(
        name="Orient rotation",
        description="Euler XYZ în spațiul Transform Orientation (header viewport, slot 0)",
        size=3,
        subtype="EULER",
        update=props._update_alec_rotation_local,
    )
    sm._depsgraph_handler = sm._depsgraph_sync_selection
    if sm._depsgraph_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(sm._depsgraph_handler)


def unregister():
    sm._sync_selection_timer_pending = False
    if sm._depsgraph_handler is not None:
        while sm._depsgraph_handler in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(sm._depsgraph_handler)
        sm._depsgraph_handler = None
    for cls in reversed(_classes_operators):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.alec_object_world
    del bpy.types.Scene.alec_rotation_world
    del bpy.types.Scene.alec_rotation_local
    del bpy.types.Scene.alec_edit_selection
    bpy.utils.unregister_class(props.AlecEditSelectionProps)
