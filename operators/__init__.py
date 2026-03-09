# This file makes the 'operators' directory a Python package.
# It collects all operator classes from the submodules and provides (un)register functions.
import bpy

from . import object_grouping
from . import object_origin
from . import align
from . import edit_mesh
from . import materials
from . import modifiers
from . import system
from . import uv
from . import bbox

# It is important that the base classes are not included in this list
# as they are not meant to be registered with Blender.
classes = (
    *object_grouping.classes,
    *object_origin.classes,
    *align.classes,
    *edit_mesh.classes,
    *materials.classes,
    *modifiers.classes,
    *system.classes,
    *uv.classes,
    *bbox.classes,
)

_app_handlers = []

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Add app handlers
    depsgraph_handler = edit_mesh.depsgraph_update_handler
    bpy.app.handlers.depsgraph_update_post.append(depsgraph_handler)
    _app_handlers.append((bpy.app.handlers.depsgraph_update_post, depsgraph_handler))

def unregister():
    # Clean up any active draw handlers from edit_mesh to prevent zombies on reload
    edit_mesh.unregister_draw_handler()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    # Remove app handlers
    for handler_list, handler_func in _app_handlers:
        if handler_func in handler_list:
            handler_list.remove(handler_func)
    _app_handlers.clear()
