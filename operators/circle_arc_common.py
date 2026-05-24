"""Shared helpers for circle/arc construction tools."""
from __future__ import annotations

import math

import bpy
import bmesh
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from ..modules import cursor_plane as cp
from ..modules import edit_mesh_draw_state as draw_state
from ..modules import edit_mesh_helpers as emh

PICK_RADIUS_PX = 12
SNAP_RING_RADIUS_PX = 12.0
EDGE_PICK_RADIUS_PX = 14


def tag_view3d_redraw(context):
    if context is None:
        return
    screen = getattr(context, 'screen', None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def clear_vertex_pick_overlay():
    clear_curve_preview_overlay(clear_picked_world=True)


def clear_curve_preview_overlay(*, clear_picked_world: bool = True):
    draw_state._draw_data.pop('two_pt_circle_preview', None)
    draw_state._draw_data.pop('cursor_plane', None)
    draw_state._draw_data.pop('trim_extend_state', None)
    if clear_picked_world:
        draw_state._draw_data.pop('three_pt_picked_world', None)
    elif draw_state._draw_data.get('three_pt_picked_world') is None:
        draw_state._draw_data.pop('draw_snap_ring', None)
        draw_state._draw_data.pop('draw_snap_source_screen', None)
    if clear_picked_world:
        draw_state._draw_data.pop('draw_snap_ring', None)
        draw_state._draw_data.pop('draw_snap_source_screen', None)
    if not draw_state.has_dim_overlay_data():
        draw_state.refresh_edit_mesh_px_handler(bpy.context)


def refresh_vertex_pick_visual(context, obj, picked_indices, mouse_xy):
    draw_state._draw_data['object_name'] = obj.name
    draw_state._draw_data['mesh_name'] = obj.data.name
    mw = obj.matrix_world

    try:
        bm = bmesh.from_edit_mesh(obj.data)
    except Exception:
        clear_vertex_pick_overlay()
        return
    bm.verts.ensure_lookup_table()

    picked_world = []
    for idx in picked_indices:
        try:
            v = bm.verts[idx]
            if v.is_valid:
                picked_world.append((mw @ v.co).copy())
        except (IndexError, ReferenceError):
            pass
    if picked_world:
        draw_state._draw_data['three_pt_picked_world'] = picked_world
    else:
        draw_state._draw_data.pop('three_pt_picked_world', None)

    region = context.region
    rv3d = context.region_data
    if mouse_xy is not None and region is not None and rv3d is not None:
        vert, _d2 = emh.hovered_vert(
            bm,
            mw,
            region,
            rv3d,
            mouse_xy,
            threshold_px=PICK_RADIUS_PX,
        )
        if vert is not None:
            p2d = location_3d_to_region_2d(region, rv3d, mw @ vert.co)
            if p2d is not None:
                draw_state._draw_data['draw_snap_ring'] = (
                    float(p2d.x),
                    float(p2d.y),
                    SNAP_RING_RADIUS_PX,
                    0,
                )
            else:
                draw_state._draw_data.pop('draw_snap_ring', None)
        else:
            draw_state._draw_data.pop('draw_snap_ring', None)
    else:
        draw_state._draw_data.pop('draw_snap_ring', None)

    draw_state.register_3d_draw_handler()
    draw_state.refresh_edit_mesh_px_handler(context)
    tag_view3d_redraw(context)


def vertex_pick_status(tool: str, picked_count: int, max_pick: int) -> str:
    if picked_count <= 0:
        return f'{tool}: Click first vertex  [RMB] Cancel  [Esc] Cancel'
    if picked_count < max_pick:
        ordinals = ('first', 'second', 'third', 'fourth')
        next_label = ordinals[picked_count] if picked_count < len(ordinals) else 'next'
        return f'{tool}: Click {next_label} vertex  [RMB] Undo  [Esc] Cancel'
    return tool


def mesh_edit_session_valid(context, session) -> bool:
    if session is None:
        return False
    obj = context.active_object
    if obj is None or obj.type != 'MESH':
        return False
    return (
        obj.name == session.get('object_name')
        and obj.data.name == session.get('mesh_name')
    )


def verts_from_session(bm, session, count: int):
    indices = session.get('vert_indices')
    if not indices or len(indices) != count:
        return None
    bm.verts.ensure_lookup_table()
    verts = []
    for idx in indices:
        try:
            v = bm.verts[idx]
            if not v.is_valid:
                return None
            verts.append(v)
        except (IndexError, ReferenceError):
            return None
    return verts


def deselect_all_mesh_elements(bm, obj):
    for e in bm.edges:
        e.select = False
    for v in bm.verts:
        v.select = False
    for f in bm.faces:
        f.select = False
    bmesh.update_edit_mesh(obj.data)


def remove_created_geometry(bm, session):
    if not session.get('applied'):
        return
    src = set(session.get('vert_indices', ()))
    for key in list(session.get('created_edge_keys', [])):
        edge = emh.bm_edge_from_key(bm, key)
        if edge is not None:
            try:
                bm.edges.remove(edge)
            except (ValueError, ReferenceError):
                pass
    session['created_edge_keys'] = []
    bm.verts.ensure_lookup_table()
    for idx in list(session.get('created_vert_indices', [])):
        if idx in src:
            continue
        try:
            if idx < len(bm.verts):
                vert = bm.verts[idx]
                if vert.is_valid and len(vert.link_edges) == 0:
                    bm.verts.remove(vert)
        except (IndexError, ReferenceError, ValueError):
            pass
    session['created_vert_indices'] = []


def append_closed_ring(
    bm,
    inv_mw,
    center_w,
    u_axis,
    v_axis,
    radius_w,
    segments: int,
    phase: float,
    session: dict,
) -> bool:
    ring = []
    for i in range(segments):
        theta = phase + (2.0 * math.pi * i) / segments
        co_w = (
            center_w
            + u_axis * (math.cos(theta) * radius_w)
            + v_axis * (math.sin(theta) * radius_w)
        )
        vert = bm.verts.new(inv_mw @ co_w)
        ring.append(vert)
        session.setdefault('created_vert_indices', []).append(vert.index)

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    for i in range(segments):
        try:
            edge = bm.edges.new((ring[i], ring[(i + 1) % segments]))
            session.setdefault('created_edge_keys', []).append(emh.bm_edge_key(edge))
        except ValueError:
            pass
    return len(session.get('created_edge_keys', [])) > 0


def create_ring_from_three_points(bm, mw, definition_verts, segments, anchor_index, session) -> bool:
    inv_mw = mw.inverted_safe()
    points_w = [mw @ v.co for v in definition_verts]
    circle = emh.circumcircle_from_three_points(points_w[0], points_w[1], points_w[2])
    if circle is None:
        return False
    center_w, radius_w, u_axis, v_axis = circle
    anchor_index = max(0, min(2, int(anchor_index)))
    phase = emh.circle_phase_for_point(center_w, u_axis, v_axis, points_w[anchor_index])
    return append_closed_ring(
        bm, inv_mw, center_w, u_axis, v_axis, radius_w, segments, phase, session,
    )


def two_pt_points_on_cursor_plane(context, mw, v0, v1):
    p1_w = cp.project_onto_cursor_plane(context, mw @ v0.co)
    p2_w = cp.project_onto_cursor_plane(context, mw @ v1.co)
    plane_n, _u, _v = cp.cursor_plane_axes(context)
    return p1_w, p2_w, plane_n


def create_ring_from_two_point_radius(
    context, bm, mw, definition_verts, radius, bisect_sign, segments, anchor_index, session,
) -> bool:
    inv_mw = mw.inverted_safe()
    p1_w, p2_w, plane_n = two_pt_points_on_cursor_plane(
        context, mw, definition_verts[0], definition_verts[1],
    )
    geom = emh.two_point_circle_from_radius(p1_w, p2_w, radius, plane_n, bisect_sign)
    if geom is None:
        return False
    center_w = geom['center']
    u_axis = geom['u']
    v_axis = geom['v']
    radius_w = geom['radius']
    anchor_index = max(0, min(1, int(anchor_index)))
    anchor_w = p1_w if anchor_index == 0 else p2_w
    phase = emh.circle_phase_for_point(center_w, u_axis, v_axis, anchor_w)
    return append_closed_ring(
        bm, inv_mw, center_w, u_axis, v_axis, radius_w, segments, phase, session,
    )


def create_ring_on_cursor_plane(context, bm, mw, center_w, radius_bu, segments, session) -> bool:
    inv_mw = mw.inverted_safe()
    center_w = cp.project_onto_cursor_plane(context, Vector(center_w))
    _plane_n, u_axis, v_axis = cp.cursor_plane_axes(context)
    radius_w = max(float(radius_bu), 1e-9)
    return append_closed_ring(
        bm, inv_mw, center_w, u_axis, v_axis, radius_w, segments, 0.0, session,
    )


def create_ring_from_geom(bm, mw, geom, segments: int, session: dict) -> bool:
    inv_mw = mw.inverted_safe()
    center_w = geom['center']
    u_axis = geom['u'].normalized()
    v_axis = geom['v'].normalized()
    radius_w = max(float(geom['radius']), 1e-9)
    return append_closed_ring(
        bm, inv_mw, center_w, u_axis, v_axis, radius_w, segments, 0.0, session,
    )


def store_circumcircle_in_session(session, mw, definition_verts) -> bool:
    points_w = [mw @ v.co for v in definition_verts]
    circle = emh.circumcircle_from_three_points(points_w[0], points_w[1], points_w[2])
    if circle is None:
        session.pop('center_w', None)
        session.pop('radius_w', None)
        return False
    center_w, radius_w, _u, _v = circle
    session['center_w'] = tuple(center_w)
    session['radius_w'] = float(radius_w)
    return True


def circumcenter_world_from_session(context, session):
    obj = bpy.data.objects.get(session.get('object_name')) or context.active_object
    if obj is None or obj.type != 'MESH':
        return None
    try:
        bm = bmesh.from_edit_mesh(obj.data)
    except Exception:
        return None
    bm.verts.ensure_lookup_table()
    verts = verts_from_session(bm, session, 3)
    if verts is None:
        return None
    mw = obj.matrix_world
    points_w = [mw @ v.co for v in verts]
    circle = emh.circumcircle_from_three_points(points_w[0], points_w[1], points_w[2])
    if circle is None:
        return None
    return circle[0].copy()


def sync_empty_collections_with_mesh(scene, empty, mesh_obj):
    mesh_cols = list(mesh_obj.users_collection)
    if not mesh_cols:
        if empty.name not in scene.collection.objects:
            scene.collection.objects.link(empty)
        return
    for coll in list(empty.users_collection):
        if coll not in mesh_cols:
            try:
                coll.objects.unlink(empty)
            except RuntimeError:
                pass
    for coll in mesh_cols:
        if empty.name not in coll.objects:
            coll.objects.link(empty)


def resolve_circ_center_empty_name(mesh_obj) -> str:
    base_name = f"{mesh_obj.name}_CircCenter"
    if bpy.data.objects.get(base_name) is None:
        return base_name
    i = 1
    while True:
        candidate = f"{base_name}.{i:03d}"
        if bpy.data.objects.get(candidate) is None:
            return candidate
        i += 1


def ensure_empty_at_world(context, mesh_obj, center_w: Vector, display_size: float):
    base_name = f"{mesh_obj.name}_CircCenter"
    empty = bpy.data.objects.get(base_name)
    if empty is not None and empty.type != 'EMPTY':
        empty = None
    if empty is None:
        for i in range(1, 100):
            candidate = f"{base_name}.{i:03d}"
            obj = bpy.data.objects.get(candidate)
            if obj is None:
                break
            if obj.type == 'EMPTY':
                empty = obj
                break

    if empty is None:
        was_edit = mesh_obj.mode == 'EDIT'
        prev_active = context.view_layer.objects.active
        try:
            if was_edit:
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.empty_add(type='PLAIN_AXES', location=tuple(center_w))
            empty = context.view_layer.objects.active
            if empty is None or empty.type != 'EMPTY':
                empty = bpy.data.objects.new(
                    resolve_circ_center_empty_name(mesh_obj),
                    None,
                )
                empty.location = center_w
                sync_empty_collections_with_mesh(context.scene, empty, mesh_obj)
            else:
                empty.name = base_name
        finally:
            if was_edit and prev_active is not None:
                try:
                    prev_active.select_set(True)
                    context.view_layer.objects.active = prev_active
                    bpy.ops.object.mode_set(mode='EDIT')
                except RuntimeError:
                    pass
    else:
        empty.location = center_w.copy()

    empty.empty_display_type = 'PLAIN_AXES'
    empty.empty_display_size = max(float(display_size), 0.05)
    sync_empty_collections_with_mesh(context.scene, empty, mesh_obj)
    empty.hide_set(False)
    empty.hide_viewport = False
    empty.update_tag(refresh={'OBJECT'})
    context.view_layer.update()
    return empty


def set_circle_frame_preview(context, obj, center_w, radius_w, u_axis, v_axis, p1_w, p2_w, *, segments=48):
    draw_state._draw_data['object_name'] = obj.name
    draw_state._draw_data['mesh_name'] = obj.data.name
    draw_state._draw_data['two_pt_circle_preview'] = {
        'center': Vector(center_w).copy(),
        'u': Vector(u_axis).copy(),
        'v': Vector(v_axis).copy(),
        'radius': float(radius_w),
        'segments': int(segments),
        'p1': Vector(p1_w).copy(),
        'p2': Vector(p2_w).copy(),
    }
    draw_state._draw_data['three_pt_picked_world'] = [Vector(p1_w).copy(), Vector(p2_w).copy()]
    try:
        _n, u_ax, v_ax = cp.cursor_plane_axes(context)
        draw_state._draw_data['cursor_plane'] = (
            context.scene.cursor.location.copy(),
            u_ax,
            v_ax,
        )
    except Exception:
        draw_state._draw_data.pop('cursor_plane', None)
    draw_state.register_3d_draw_handler()
    draw_state.refresh_edit_mesh_px_handler(context)


def set_circle_preview_simple(context, obj, center_w, radius_bu, rim_w=None):
    center_w = cp.project_onto_cursor_plane(context, Vector(center_w))
    _plane_n, u_axis, v_axis = cp.cursor_plane_axes(context)
    radius_w = max(float(radius_bu), 1e-9)
    if rim_w is None:
        rim_w = center_w + u_axis * radius_w
    set_circle_frame_preview(
        context, obj, center_w, radius_w, u_axis, v_axis, center_w, rim_w,
    )
    tag_view3d_redraw(context)


def pick_hovered_vert_index(context, obj, mouse_xy, exclude_indices=()):
    if context.region is None or context.region_data is None or mouse_xy is None:
        return None
    try:
        bm = bmesh.from_edit_mesh(obj.data)
    except Exception:
        return None
    bm.verts.ensure_lookup_table()
    vert, _d2 = emh.hovered_vert(
        bm,
        obj.matrix_world,
        context.region,
        context.region_data,
        mouse_xy,
        threshold_px=PICK_RADIUS_PX,
        exclude_indices=exclude_indices,
    )
    return vert.index if vert is not None else None
