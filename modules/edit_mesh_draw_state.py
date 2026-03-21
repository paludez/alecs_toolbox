"""Viewport draw handlers and shared state for edit_mesh operators."""
import bpy
import bmesh
import blf
import time
from bpy_extras.view3d_utils import location_3d_to_region_2d

_draw_handler_px = None
_draw_handler_3d = None
_falloff_timer = None
_draw_data = {}
_last_falloff_update = 0.0


def clear_falloff_preview():
    """Timer callback to remove the preview sphere after user stops tweaking the slider."""
    global _falloff_timer, _draw_data, _last_falloff_update
    if time.time() - _last_falloff_update >= 1.0:
        if 'falloff_sphere' in _draw_data:
            del _draw_data['falloff_sphere']
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
        _falloff_timer = None
        return None
    return 0.1


def refresh_falloff_timer():
    """Resets the fade-out timer every time the user tweaks the radius slider."""
    global _falloff_timer, _last_falloff_update
    _last_falloff_update = time.time()
    if not _falloff_timer:
        _falloff_timer = bpy.app.timers.register(clear_falloff_preview, first_interval=0.1)


def register_3d_draw_handler():
    global _draw_handler_3d
    if not _draw_handler_3d:
        _draw_handler_3d = bpy.types.SpaceView3D.draw_handler_add(
            draw_callback_3d, (bpy.context,), 'WINDOW', 'POST_VIEW'
        )


def depsgraph_update_handler(scene):
    """Clear draw data if Edit Mode is exited or target object is invalid."""
    global _draw_handler_px, _draw_handler_3d, _draw_data
    if not _draw_data:
        return

    should_clear = False

    if bpy.context.mode != 'EDIT_MESH':
        should_clear = True
    else:
        obj_name = _draw_data.get('object_name')
        mesh_name = _draw_data.get('mesh_name')
        obj = bpy.data.objects.get(obj_name) if obj_name else None

        if not obj or not mesh_name or obj.data.name != mesh_name:
            should_clear = True

    if should_clear:
        if _draw_handler_px:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(_draw_handler_px, 'WINDOW')
            except ValueError:
                pass
            _draw_handler_px = None
        if _draw_handler_3d:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(_draw_handler_3d, 'WINDOW')
            except ValueError:
                pass
            _draw_handler_3d = None
        _draw_data.clear()

        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()


def unregister_draw_handler():
    """Force remove the draw handler when unregistering the addon."""
    global _draw_handler_px, _draw_handler_3d, _falloff_timer
    if _draw_handler_px:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_draw_handler_px, 'WINDOW')
        except ValueError:
            pass
        _draw_handler_px = None
    if _draw_handler_3d:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_draw_handler_3d, 'WINDOW')
        except ValueError:
            pass
        _draw_handler_3d = None
    if _falloff_timer and bpy.app.timers.is_registered(clear_falloff_preview):
        bpy.app.timers.unregister(clear_falloff_preview)
        _falloff_timer = None


def draw_callback_px(context):
    """Draw handler to display edge lengths in the 3D View."""
    if context.mode != 'EDIT_MESH' or not context.edit_object:
        return

    obj = context.edit_object
    if not _draw_data or obj.name != _draw_data.get('object_name') or obj.data.name != _draw_data.get('mesh_name'):
        return

    bm = bmesh.from_edit_mesh(obj.data)
    bm.edges.ensure_lookup_table()

    edge_indices = _draw_data.get('edge_indices', [])
    if not edge_indices:
        return

    world_mx = obj.matrix_world
    region = context.region
    region_3d = context.space_data.region_3d

    font_id = 0
    font_size = 12
    blf.size(font_id, font_size)
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 0.8)

    for idx in edge_indices:
        if idx >= len(bm.edges):
            continue
        edge = bm.edges[idx]

        v1_world = world_mx @ edge.verts[0].co
        v2_world = world_mx @ edge.verts[1].co

        length = (v1_world - v2_world).length
        mid_point_world = (v1_world + v2_world) / 2.0

        pos_2d = location_3d_to_region_2d(region, region_3d, mid_point_world)
        if pos_2d:
            display_length = length * _draw_data.get('unit_inv', 1.0)
            text = f"{display_length:.4f}{_draw_data.get('suffix', '')}"
            blf.position(font_id, pos_2d.x - blf.dimensions(font_id, text)[0] / 2, pos_2d.y, 0)
            blf.draw(font_id, text)


def draw_callback_3d(context):
    """Draw handler to display 3D graphics in the Viewport."""
    if getattr(context, 'mode', '') != 'EDIT_MESH':
        return
    sphere_data = _draw_data.get('falloff_sphere')
    if sphere_data:
        from .drawing_tools import draw_wire_sphere
        center, radius = sphere_data
        draw_wire_sphere(center, radius, color=(1.0, 0.6, 0.1, 1.0))

    pie_data = _draw_data.get('angle_pie')
    if pie_data:
        from .drawing_tools import draw_angle_pie
        center, dir_base, normal, angle, radius = pie_data
        draw_angle_pie(center, dir_base, normal, angle, radius, color=(0.1, 0.6, 1.0, 0.3))


def update_dimension_px_handler(context, has_items):
    """Attach or remove the 2D dimension overlay handler."""
    global _draw_handler_px
    if has_items and not _draw_handler_px:
        _draw_handler_px = bpy.types.SpaceView3D.draw_handler_add(
            draw_callback_px, (context,), 'WINDOW', 'POST_PIXEL'
        )
    elif not has_items and _draw_handler_px:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handler_px, 'WINDOW')
        _draw_handler_px = None
