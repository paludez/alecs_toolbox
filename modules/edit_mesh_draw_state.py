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
    """True if 2D overlay: mesh edge dims, corner angles, curve point-pair 3D distances,
    or draw_mesh_edges floating length label."""
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
    if _draw_data.get('draw_rubber_band_label') is not None:
        return True
    if _draw_data.get('draw_snap_ring') is not None:
        return True
    if _draw_data.get('draw_snap_source_screen') is not None:
        return True
    if _draw_data.get('three_pt_picked_world'):
        return True
    if _draw_data.get('two_pt_circle_preview'):
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

    rb_label = _draw_data.get('draw_rubber_band_label')
    if rb_label:
        try:
            mid_world, text = rb_label
            pos_2d = location_3d_to_region_2d(region, region_3d, mid_world)
            if pos_2d:
                blf.color(font_id, 1.0, 1.0, 0.3, 1.0)
                w = blf.dimensions(font_id, text)[0]
                blf.position(font_id, pos_2d.x - w / 2, pos_2d.y + 12, 0)
                blf.draw(font_id, text)
                blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
        except Exception:
            pass

    snap_ring = _draw_data.get('draw_snap_ring')
    if snap_ring and len(snap_ring) >= 3:
        try:
            import gpu.state as gpu_state
            from gpu_extras.presets import draw_circle_2d

            cx, cy = float(snap_ring[0]), float(snap_ring[1])
            rad = float(snap_ring[2])
            snap_kind = snap_ring[3] if len(snap_ring) >= 4 else None
            if snap_kind == -1:
                col = (1.0, 0.55, 0.12, 0.95)
            elif snap_kind == -2:
                col = (1.0, 0.9, 0.15, 0.92)
            elif snap_kind == -3:
                col = (0.85, 0.35, 1.0, 0.9)
            elif snap_kind == -4:
                col = (0.25, 0.85, 1.0, 0.92)
            else:
                col = (0.15, 1.0, 0.45, 0.92)
            gpu_state.blend_set('ALPHA')
            draw_circle_2d((cx, cy), (*col[:3], min(1.0, col[3] + 0.03)), rad + 2.5, segments=48)
            draw_circle_2d((cx, cy), (*col[:3], min(1.0, col[3] + 0.08)), max(5.0, rad * 0.42), segments=36)
            gpu_state.blend_set('NONE')
            if snap_kind == -2:
                label = 'Mid'
            elif snap_kind == -3:
                label = 'World'
            elif snap_kind == -4:
                label = 'Perp'
            elif snap_kind is not None and snap_kind >= 0:
                label = 'Vtx'
            elif snap_kind == -1:
                label = 'Close'
            else:
                label = 'Snap'
            lbl = '[' + label + ']'
            blf.size(font_id, 11)
            blf.color(font_id, col[0], col[1], col[2], 1.0)
            w_label = blf.dimensions(font_id, lbl)[0]
            blf.position(font_id, cx + rad + 10, cy - font_size / 2, 0)
            blf.draw(font_id, lbl)
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
        except Exception:
            pass

    src_xy = _draw_data.get('draw_snap_source_screen')
    if isinstance(src_xy, (tuple, list)) and len(src_xy) >= 2:
        try:
            import gpu.state as gpu_state
            from gpu_extras.presets import draw_circle_2d

            sx, sy = float(src_xy[0]), float(src_xy[1])
            col_src = (0.95, 0.92, 0.25, 0.92)
            gpu_state.blend_set('ALPHA')
            draw_circle_2d((sx, sy), (*col_src[:3], min(1.0, col_src[3] + 0.05)), 5.8, segments=28)
            draw_circle_2d((sx, sy), (0.1, 0.1, 0.06, 0.35), 2.9, segments=28)
            gpu_state.blend_set('NONE')
        except Exception:
            pass


def draw_callback_3d(context):
    """Draw handler to display 3D graphics in the Viewport."""
    if bpy.context.mode != 'EDIT_MESH':
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

    picked_world = _draw_data.get('three_pt_picked_world')
    if picked_world:
        try:
            from .drawing_tools import _draw_simple_points
            _draw_simple_points(
                [p.copy() for p in picked_world],
                (0.15, 1.0, 0.45, 0.9),
                size=9.0,
            )
        except Exception:
            pass

    two_pt = _draw_data.get('two_pt_circle_preview')
    if two_pt:
        try:
            from .drawing_tools import (
                draw_wire_arc_loop,
                draw_wire_circle_loop,
                _draw_simple_lines,
                _draw_simple_points,
            )
            center = two_pt['center']
            sweep = two_pt.get('sweep')
            if sweep is not None and abs(float(sweep)) < (2.0 * math.pi - 1e-4):
                draw_wire_arc_loop(
                    center,
                    two_pt['u'],
                    two_pt['v'],
                    float(two_pt['radius']),
                    float(two_pt['theta_start']),
                    float(sweep),
                    segments=int(two_pt.get('segments', 48)),
                    color=(0.2, 0.85, 1.0, 0.9),
                )
            else:
                draw_wire_circle_loop(
                    center,
                    two_pt['u'],
                    two_pt['v'],
                    float(two_pt['radius']),
                    segments=int(two_pt.get('segments', 48)),
                    color=(0.2, 0.85, 1.0, 0.9),
                )
            if 'p1' in two_pt and 'p2' in two_pt:
                _draw_simple_lines(
                    [two_pt['p1'].copy(), two_pt['p2'].copy()],
                    (1.0, 1.0, 1.0, 0.35),
                    width=1.25,
                )
                _draw_simple_points(
                    [two_pt['p1'].copy(), two_pt['p2'].copy()],
                    (0.15, 1.0, 0.45, 0.95),
                    size=9.0,
                )
        except Exception:
            pass

    cp = _draw_data.get('cursor_plane')
    if cp:
        try:
            from .drawing_tools import _draw_simple_lines
            center, u, v = cp
            SIZE = 4.0
            DIVS = 8
            half = SIZE * 0.5
            step = SIZE / DIVS
            lines = []
            for i in range(DIVS + 1):
                offset = -half + i * step
                lines.append(center + u * (-half) + v * offset)
                lines.append(center + u * half + v * offset)
                lines.append(center + u * offset + v * (-half))
                lines.append(center + u * offset + v * half)
            _draw_simple_lines(lines, (0.4, 0.6, 1.0, 0.18), width=1.0)
        except Exception:
            pass

    rb = _draw_data.get('draw_rubber_band')
    if rb:
        from .drawing_tools import _draw_simple_lines, _draw_simple_points

        snap_anchor_world = None
        if len(rb) >= 7:
            (
                last_world,
                preview_world,
                is_snap,
                snap_idx,
                is_ortho,
                axis_guide,
                snap_anchor_world,
            ) = rb[:7]
        elif len(rb) == 6:
            last_world, preview_world, is_snap, snap_idx, is_ortho, axis_guide = rb
        elif len(rb) == 5:
            last_world, preview_world, is_snap, snap_idx, is_ortho = rb
            axis_guide = None
        else:
            last_world, preview_world, is_snap, snap_idx = rb
            is_ortho = False
            axis_guide = None

        if axis_guide is not None:
            ag_start, ag_end, ag_color = axis_guide
            _draw_simple_lines([ag_start, ag_end], ag_color, width=1.5)
        if preview_world is not None:
            if snap_anchor_world is not None:
                da = preview_world - snap_anchor_world
                if da.length_squared > 5e-7:
                    _draw_simple_lines(
                        [snap_anchor_world.copy(), preview_world.copy()],
                        (1.0, 1.0, 1.0, 0.42),
                        width=1.25,
                    )
                    _draw_simple_points([snap_anchor_world.copy()], (1.0, 1.0, 1.0, 0.55), size=6.0)

            if is_snap:
                color_line = (0.2, 1.0, 0.45, 0.92)
            elif is_ortho:
                color_line = (0.2, 0.8, 1.0, 0.95)
            else:
                color_line = (1.0, 1.0, 1.0, 0.9)
            if snap_idx == -1:
                color_point = (1.0, 0.6, 0.1, 1.0)
            elif snap_idx == -2:
                color_point = (1.0, 0.85, 0.0, 1.0)
            elif snap_idx == -3:
                color_point = (0.8, 0.2, 1.0, 1.0)
            elif snap_idx == -4:
                color_point = (0.2, 0.75, 1.0, 1.0)
            elif is_snap:
                color_point = (0.15, 1.0, 0.52, 1.0)
            else:
                color_point = color_line
            if last_world is not None:
                _draw_simple_lines([last_world.copy(), preview_world.copy()], color_line, width=2.0)
            _draw_simple_points([preview_world.copy()], color_point, size=8.0)

    te = _draw_data.get('trim_extend_state')
    if te:
        try:
            from .drawing_tools import _draw_simple_lines, _draw_simple_points

            ref_edge = te.get('ref_edge')
            if ref_edge is not None:
                ra, rb = ref_edge
                _draw_simple_lines([ra.copy(), rb.copy()], (0.2, 1.0, 0.45, 0.95), width=2.5)
            ref_face_loop = te.get('ref_face_loop')
            if ref_face_loop:
                pts = []
                n = len(ref_face_loop)
                for i in range(n):
                    pts.append(ref_face_loop[i].copy())
                    pts.append(ref_face_loop[(i + 1) % n].copy())
                _draw_simple_lines(pts, (0.15, 0.85, 1.0, 0.9), width=2.0)
            ref_line = te.get('ref_infinite_line')
            if ref_line is not None:
                la, lb = ref_line
                _draw_simple_lines([la.copy(), lb.copy()], (0.2, 1.0, 0.45, 0.45), width=1.0)
            target_remove = te.get('target_remove_segment')
            if target_remove is not None:
                ta, tb = target_remove
                _draw_simple_lines([ta.copy(), tb.copy()], (1.0, 0.2, 0.2, 0.95), width=4.0)
            target_keep = te.get('target_keep_segment')
            if target_keep is not None:
                ta, tb = target_keep
                _draw_simple_lines([ta.copy(), tb.copy()], (0.6, 0.6, 0.6, 0.55), width=1.5)
            extend_preview = te.get('extend_preview')
            if extend_preview is not None:
                ea, eb = extend_preview
                _draw_simple_lines([ea.copy(), eb.copy()], (0.2, 1.0, 0.4, 0.95), width=2.5)
                _draw_simple_points([eb.copy()], (1.0, 0.85, 0.15, 1.0), size=8.0)
            hit_point = te.get('hit_point')
            if hit_point is not None:
                _draw_simple_points([hit_point.copy()], (1.0, 0.85, 0.15, 1.0), size=7.0)
            warn_segment = te.get('warn_segment')
            if warn_segment is not None:
                wa, wb = warn_segment
                _draw_simple_lines([wa.copy(), wb.copy()], (1.0, 0.55, 0.1, 0.85), width=2.5)
            arc_points = te.get('fillet_chamfer_arc')
            if arc_points and len(arc_points) >= 2:
                pts = []
                for i in range(len(arc_points) - 1):
                    pts.append(arc_points[i].copy())
                    pts.append(arc_points[i + 1].copy())
                _draw_simple_lines(pts, (1.0, 1.0, 1.0, 0.95), width=2.5)
            extra_lines = te.get('extra_lines')
            if extra_lines:
                for seg, color in extra_lines:
                    a, b = seg
                    _draw_simple_lines([a.copy(), b.copy()], color, width=2.5)
        except Exception:
            pass


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
