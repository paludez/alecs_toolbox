import bpy
from mathutils import Vector

def cursor_to_selected(context):
    obj = context.active_object
    context.scene.cursor.location = obj.location.copy()
    context.scene.cursor.rotation_euler = obj.rotation_euler.copy()

def cursor_to_geometry_center(context):
    obj = context.active_object
    corners = [Vector(c) for c in obj.bound_box]
    min_co = Vector((min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners)))
    max_co = Vector((max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners)))
    center_local = (min_co + max_co) / 2
    center_world = obj.matrix_world @ center_local
    context.scene.cursor.location = center_world
    context.scene.cursor.rotation_euler = obj.rotation_euler.copy()

def origin_to_cursor(context):
    obj = context.active_object
    context.scene.tool_settings.use_transform_data_origin = True
    bpy.ops.view3d.snap_selected_to_cursor(use_offset=False, use_rotation=True)
    context.scene.tool_settings.use_transform_data_origin = False