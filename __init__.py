import bpy
from . import preferences
from . import operators
from . import ui
from . import menus
from . import shortcuts

bl_info = {
    "name": "Alec's Toolbox",
    "author": "Alec",
    "version": (0, 5, 1),
    "blender": (5, 0, 1),
    "location": "View3D > Sidebar > Alec",
    "description": "Custom tools for hard surface modeling",
    "warning": "",
    "doc_url": "",
    "category": "3D View",
}

modules = [
    preferences,
    operators,
    ui,
    menus,
    shortcuts,
]

def register():
    for m in modules:
        m.register()

def unregister():
    for m in reversed(modules):
        m.unregister()