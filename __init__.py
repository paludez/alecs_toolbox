import bpy
from . import operators
from . import menus
from . import dialog
from . import dialog_materials

modules = [operators,
           menus,
           dialog,
           dialog_materials]

def register():
    for m in modules:
        m.register()

def unregister():
    for m in reversed(modules):
        m.unregister()