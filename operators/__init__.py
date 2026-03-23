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
from . import uv
from . import bbox
from . import auto_linked_mode
from . import camera_tools
from . import viewport_shortcuts

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
    *uv.classes,
    *bbox.classes,
    *auto_linked_mode.classes,
    *camera_tools.classes,
    *viewport_shortcuts.classes,
)

_app_handlers = []

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    depsgraph_handler = edit_mesh.depsgraph_update_handler
    bpy.app.handlers.depsgraph_update_post.append(depsgraph_handler)
    _app_handlers.append((bpy.app.handlers.depsgraph_update_post, depsgraph_handler))

def unregister():
    edit_mesh.unregister_draw_handler()
    auto_linked_mode._exit_auto_linked()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    for handler_list, handler_func in _app_handlers:
        if handler_func in handler_list:
            handler_list.remove(handler_func)
    _app_handlers.clear()
