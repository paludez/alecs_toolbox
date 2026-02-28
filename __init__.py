import bpy
from . import operators
from . import menus
from . import dialog


modules = [operators,
           menus,
           dialog]

def register():
    for m in modules:
        m.register()

def unregister():
    for m in reversed(modules):
        m.unregister()