"""Viewport draw handlers and shared state for edit_mesh operators."""
import bpy
import bmesh
import blf
import math
import time
from bpy_extras.view3d_utils import location_3d_to_region_2d

from . import edit_mesh_helpers as emh
from . import edit_curve_helpers as ech

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
    mode = bpy.context.mode
    if mode not in ('EDIT_MESH', 'EDIT_CURVE'):
        should_clear = True
    else:
        obj_name = _draw_data.get('object_name')
        mesh_name = _draw_data.get('mesh_name')
        obj = bpy.data.objects.get(obj_name) if obj_name else None

        if not obj or not mesh_name or obj.data.name != mesh_name:
            should_clear = True
        elif bpy.context.edit_object != obj:
            should_clear = True
        elif mode == 'EDIT_MESH' and obj.type != 'MESH':
            should_clear = True
        elif mode == 'EDIT_CURVE' and obj.type != 'CURVE':
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


def has_dim_overlay_data():
    """True if 2D overlay: mesh edge dims, corner angles, and/or curve point-pair 3D distances."""
    if not _draw_data:
        return False
    if _draw_data.get('edge_indices'):
        return True
    mag = _draw_data.get('measured_angle_edges')
    if mag:
        if isinstance(mag, list):
            if bool(mag):
                return True
        else:
            return True
    cp = _draw_data.get('curve_point_pairs')
    if cp and isinstance(cp, list) and bool(cp):
        return True
    return False


def refresh_edit_mesh_px_handler(context):
    """Register/remove POST_PIXEL draw handler for dimensions + measure angle + curve point distances."""
    update_dimension_px_handler(context, has_dim_overlay_data())


def draw_callback_px(context):
    """2D overlay: mesh edge dimensions, corner angles, curve control-point 3D distances."""
    if not _draw_data or not context.edit_object:
        return

    obj = context.edit_object
    if obj.name != _draw_data.get('object_name') or obj.data.name != _draw_data.get('mesh_name'):
        return

    font_id = 0
    font_size = 12
    blf.size(font_id, font_size)
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 0.8)
    world_mx = obj.matrix_world
    region = context.region
    region_3d = context.space_data.region_3d

    if context.mode == 'EDIT_MESH' and obj.type == 'MESH':
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        edge_indices = _draw_data.get('edge_indices', [])
        raw_angles = _draw_data.get('measured_angle_edges')
        if raw_angles is None:
            angle_entries = []
        elif isinstance(raw_angles, tuple) and len(raw_angles) == 2 and isinstance(
            raw_angles[0], int
        ):
            angle_entries = [raw_angles]
        else:
            angle_entries = list(raw_angles)
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

        for angle_pair in angle_entries:
            if not angle_pair or len(angle_pair) != 2:
                continue
            i_mov, i_stat = int(angle_pair[0]), int(angle_pair[1])
            if 0 <= i_mov < len(bm.edges) and 0 <= i_stat < len(bm.edges):
                e_mov, e_stat = bm.edges[i_mov], bm.edges[i_stat]
                pivot, angle_rad, _t = emh.angle_pivot_for_edge_pair(e_stat, e_mov)
                if pivot is not None and angle_rad is not None:
                    p_world = world_mx @ pivot
                    pos_2d = location_3d_to_region_2d(region, region_3d, p_world)
                    if pos_2d:
                        text = f"{math.degrees(angle_rad):.2f}°"
                        w = blf.dimensions(font_id, text)[0]
                        blf.position(font_id, pos_2d.x - w / 2, pos_2d.y - 32, 0)
                        blf.draw(font_id, text)

    if context.mode == 'EDIT_CURVE' and obj.type == 'CURVE':
        me = obj.data
        for pr in _draw_data.get('curve_point_pairs', []) or []:
            if not pr or len(pr) != 2:
                continue
            k0, k1 = pr[0], pr[1]
            t0 = ech.resolve_curve_target(me, *k0)
            t1 = ech.resolve_curve_target(me, *k1)
            if t0 is None or t1 is None:
                continue
            w0 = world_mx @ t0.get_co()
            w1 = world_mx @ t1.get_co()
            d = (w0 - w1).length
            mid = (w0 + w1) * 0.5
            pos_2d = location_3d_to_region_2d(region, region_3d, mid)
            if pos_2d:
                u = _draw_data.get('curve_dim_unit_inv', 1.0)
                text = f"{d * u:.4f}{_draw_data.get('curve_dim_suffix', '')}"
                blf.position(
                    font_id, pos_2d.x - blf.dimensions(font_id, text)[0] / 2, pos_2d.y, 0
                )
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
