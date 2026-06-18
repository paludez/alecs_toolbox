from . import preferences
from . import operators
from . import properties
from . import ui
from .ui import npanel
from . import menus
from . import shortcuts

modules = [
    preferences,
    operators,
    properties,
    ui,
    npanel,
    menus,
    shortcuts,
]

def register():
    for m in modules:
        m.register()

def unregister():
    for m in reversed(modules):
        m.unregister()