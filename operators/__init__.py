import bpy

from . import object_grouping
from . import object_origin
from . import align
from . import edit_mesh
from . import edit_curve
from . import materials
from . import batch_materials
from . import modifiers
from . import system
from . import outliner
from . import uv
from . import bbox
from . import auto_linked_mode
from . import camera_tools
from . import light_tools
from . import viewport_shortcuts
from . import object_hide_viewport_render
from . import triplanar_mapping
from . import draw_mesh_edges

classes = (
    *object_grouping.classes,
    *object_origin.classes,
    *align.classes,
    *edit_mesh.classes,
    *edit_curve.classes,
    *materials.classes,
    *batch_materials.classes,
    *modifiers.classes,
    *system.classes,
    *outliner.classes,
    *uv.classes,
    *bbox.classes,
    *auto_linked_mode.classes,
    *camera_tools.classes,
    *light_tools.classes,
    *viewport_shortcuts.classes,
    *object_hide_viewport_render.classes,
    *triplanar_mapping.classes,
    *draw_mesh_edges.classes,
)

_app_handlers = []

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    batch_materials.post_register()
    triplanar_mapping.post_register()
    camera_tools.register_focal_lens_scene_props()
    light_tools.register_light_rig_object_props()

    depsgraph_handler = edit_mesh.depsgraph_update_handler
    bpy.app.handlers.depsgraph_update_post.append(depsgraph_handler)
    _app_handlers.append((bpy.app.handlers.depsgraph_update_post, depsgraph_handler))

    align_handler = align._track_active_object_handler
    bpy.app.handlers.depsgraph_update_post.append(align_handler)
    _app_handlers.append((bpy.app.handlers.depsgraph_update_post, align_handler))

def unregister():
    edit_mesh.unregister_draw_handler()
    auto_linked_mode._exit_auto_linked()
    batch_materials.post_unregister()
    camera_tools.unregister_focal_lens_scene_props()
    light_tools.unregister_light_rig_object_props()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    for handler_list, handler_func in _app_handlers:
        if handler_func in handler_list:
            handler_list.remove(handler_func)
    _app_handlers.clear()
