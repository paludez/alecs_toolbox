import bpy

from . import transform_panel


def register():
    transform_panel.register()


def unregister():
    transform_panel.unregister()
