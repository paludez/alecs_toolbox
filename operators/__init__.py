# This file makes the 'operators' directory a Python package.
# It collects all operator classes from the submodules and provides (un)register functions.
import bpy

from . import object_grouping
from . import object_origin
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
    *edit_mesh.classes,
    *materials.classes,
    *modifiers.classes,
    *system.classes,
    *uv.classes,
    *bbox.classes,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
