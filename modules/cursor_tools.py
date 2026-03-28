import bpy
from .utils import get_bounds_data

def cursor_to_selected(context):
    obj = context.active_object
    context.scene.cursor.location = obj.location.copy()
    context.scene.cursor.rotation_euler = obj.rotation_euler.copy()

def cursor_to_geometry_center(context):
    obj = context.active_object
    context.scene.cursor.location = get_bounds_data(obj, 'CENTER', 'LOCAL')
    context.scene.cursor.rotation_euler = obj.rotation_euler.copy()

def origin_to_cursor(context):
    obj = context.active_object
    context.scene.tool_settings.use_transform_data_origin = True
    bpy.ops.view3d.snap_selected_to_cursor(use_offset=False, use_rotation=True)
    context.scene.tool_settings.use_transform_data_origin = False

def origin_set_to_cursor(context):
    obj = context.active_object
    context.scene.tool_settings.use_transform_data_origin = True
    bpy.ops.view3d.snap_selected_to_cursor(use_offset=False, use_rotation=False)
    context.scene.tool_settings.use_transform_data_origin = False