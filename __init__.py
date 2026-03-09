import bpy
from . import operators
from . import menus


modules = [operators,
           menus]

def register():
    for m in modules:
        m.register()

def unregister():
    for m in reversed(modules):
        m.unregister()