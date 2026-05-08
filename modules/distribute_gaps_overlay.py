"""Distribute viewport overlay: OBB/AABB wires + gap cotes and/or Positions spacing readout."""

import time

import bpy
import blf
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from . import align_tools
from .drawing_tools import _draw_simple_lines

_PREVIEW_CORNERS: list[list[Vector]] = []
_GAP_LINE_SEGMENTS: list[tuple[Vector, Vector]] = []
_GAP_LABELS: list[tuple[str, Vector]] = []

_draw_handler = None
_draw_handler_px = None
_watch_active = False
_depsgraph_registered = False

_last_alive_monotonic: float | None = None
# After Redo folds, operator.draw/check stop ping-ing; stale clears overlay (was 3s → looked like “permanent” traces).
_STALE_AFTER_SEC = 0.38

_OVERLAY_COLOR = (0.15, 0.85, 0.45, 0.55)
_DIM_COLOR = (0.95, 0.95, 1.0, 0.9)
_DIM_WIDTH = 1.5
_CUBE_EDGES = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 0),
    (4, 5),
    (5, 6),
    (6, 7),
    (7, 4),
    (0, 4),
    (1, 5),
    (2, 6),
    (3, 7),
)


def _tag_view3d_redraw():
    try:
        for window in bpy.context.window_manager.windows:
            # Whole-window refresh helps clear ghost geometry after removing draw handlers.
            tag_win = getattr(window, "tag_redraw", None)
            if callable(tag_win):
                tag_win()
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except Exception:
        pass


def _deferred_view3d_redraw():
    _tag_view3d_redraw()
    return None


def mark_alive() -> None:
    global _last_alive_monotonic
    _last_alive_monotonic = time.monotonic()


def _should_clear_preview() -> bool:
    try:
        ctx = bpy.context
    except (AttributeError, ReferenceError):
        return True

    if getattr(ctx, "mode", "") != "OBJECT":
        return True
    if len(getattr(ctx, "selected_objects", ()) or ()) < 2:
        return True

    if _last_alive_monotonic is None:
        return False
    return time.monotonic() - _last_alive_monotonic > _STALE_AFTER_SEC


def _depsgraph_tag_redraw(scene):
    if not _PREVIEW_CORNERS and not _GAP_LINE_SEGMENTS:
        return
    _tag_view3d_redraw()


def _register_depsgraph():
    global _depsgraph_registered
    if _depsgraph_registered:
        return
    bpy.app.handlers.depsgraph_update_post.append(_depsgraph_tag_redraw)
    _depsgraph_registered = True


def _unregister_depsgraph():
    global _depsgraph_registered
    if not _depsgraph_registered:
        return
    try:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_tag_redraw)
    except ValueError:
        pass
    _depsgraph_registered = False


def _stop_watch_timer():
    global _watch_active
    if not _watch_active:
        return
    try:
        bpy.app.timers.unregister(_lifecycle_watch)
    except (RuntimeError, ValueError):
        pass
    _watch_active = False


def _lifecycle_watch():
    if not _PREVIEW_CORNERS:
        _stop_watch_timer()
        return None
    try:
        if _should_clear_preview():
            clear_preview()
            return None
    except Exception:
        return 0.12
    _tag_view3d_redraw()
    return 0.12


def _start_watch_timer_if_needed():
    global _watch_active
    if _watch_active:
        return
    bpy.app.timers.register(_lifecycle_watch, first_interval=0.05)
    _watch_active = True


def _perp_basis(axis_u: Vector) -> tuple[Vector, Vector]:
    axis_u = axis_u.normalized()
    if abs(axis_u.z) < 0.9:
        aux = Vector((0.0, 0.0, 1.0))
    else:
        aux = Vector((1.0, 0.0, 0.0))
    p1 = axis_u.cross(aux)
    if p1.length < 1e-8:
        p1 = axis_u.cross(Vector((0.0, 1.0, 0.0)))
    p1.normalize()
    p2 = axis_u.cross(p1)
    return p1, p2


def _format_length(context, value: float) -> str:
    """Same unit string as operators/draw_mesh_edges (Set edge length overlay)."""
    v = abs(value)
    try:
        return bpy.utils.units.to_string(
            context.scene.unit_settings.system, "LENGTH", v, precision=4
        )
    except Exception:
        return f"{v:.4f}"


def _gap_label(context, projected_gap_scalar: float) -> str:
    if projected_gap_scalar >= -1e-9:
        return _format_length(context, projected_gap_scalar)
    return "overlap " + _format_length(context, -projected_gap_scalar)


def _rebuild_positions_visual(
    context,
    objects: list,
    axis_dir: Vector,
    ref_point: str,
    corner_boxes: list[list[Vector]],
) -> None:
    """Same gesture as gap cotes: baseline + per-interval line, brackets, BLF length (sorted ref projections)."""
    global _GAP_LINE_SEGMENTS, _GAP_LABELS

    _GAP_LINE_SEGMENTS.clear()
    _GAP_LABELS.clear()

    bpy.context.view_layer.update()
    u = axis_dir.normalized()

    projections: list[tuple[float, object]] = [
        (align_tools.reference_projection_on_axis(o, u, ref_point), o) for o in objects
    ]
    projections.sort(key=lambda x: x[0])
    s_sorted = [p[0] for p in projections]
    if len(s_sorted) < 2:
        return

    s_min, s_max = s_sorted[0], s_sorted[-1]
    if abs(s_max - s_min) < 1e-12:
        return

    perp1, perp2 = _perp_basis(u)
    cen = Vector((0.0, 0.0, 0.0))
    ncorner = 0
    for box in corner_boxes:
        for c in box:
            cen += c
            ncorner += 1
    if ncorner > 0:
        cen /= float(ncorner)
    else:
        for obj in objects:
            cen += obj.matrix_world.translation
        cen /= max(len(objects), 1)

    span = 0.05
    for box in corner_boxes:
        for c in box:
            span = max(span, abs((c - cen).dot(perp1)))
    span = max(span, 1e-4)

    offset_mag = span * 0.4 + 0.025
    line_base = cen + perp1 * offset_mag
    k = line_base.dot(u)

    def at_s(s: float) -> Vector:
        return u * (s - k) + line_base

    _GAP_LINE_SEGMENTS.append((at_s(s_min), at_s(s_max)))

    end_tick_h = max(span * 0.1, 0.032)

    for i in range(len(s_sorted) - 1):
        sa = s_sorted[i]
        sb = s_sorted[i + 1]
        delta = sb - sa
        if abs(delta) < 1e-12:
            continue
        pa = at_s(sa)
        pb = at_s(sb)

        _GAP_LINE_SEGMENTS.append((pa, pb))
        _GAP_LINE_SEGMENTS.append((pa + perp2 * end_tick_h, pa - perp2 * end_tick_h))
        _GAP_LINE_SEGMENTS.append((pb + perp2 * end_tick_h, pb - perp2 * end_tick_h))

        mid_pt = at_s(0.5 * (sa + sb))
        label_anchor = mid_pt + perp1 * (offset_mag * 0.28)
        _GAP_LABELS.append((_gap_label(context, delta), label_anchor))


def _dedupe_object_corner_pairs(
    objects: list, corner_boxes: list[list[Vector]]
) -> tuple[list, list[list[Vector]]]:
    """Stable (object, corners) pairs by object pointer."""
    seen: set[int] = set()
    out_o = []
    out_b = []
    for ob, box in zip(objects, corner_boxes):
        try:
            p = ob.as_pointer()
        except ReferenceError:
            continue
        if p in seen:
            continue
        seen.add(p)
        out_o.append(ob)
        out_b.append(box)
    return out_o, out_b


def _rebuild_gap_visual(
    context,
    objects: list,
    axis_dir: Vector,
    corner_boxes: list[list[Vector]],
) -> None:
    global _GAP_LINE_SEGMENTS, _GAP_LABELS
    _GAP_LINE_SEGMENTS.clear()
    _GAP_LABELS.clear()

    bpy.context.view_layer.update()
    u = axis_dir.normalized()

    objs_u = objects
    intervals: list[tuple[float, float]] = []
    for obj in objs_u:
        mn, mx = align_tools.bbox_axis_interval_world(obj, u)
        if mn > mx:
            mn, mx = mx, mn
        intervals.append((mn, mx))
    intervals.sort(key=lambda x: x[0])

    if len(intervals) < 2:
        return

    perp1, perp2 = _perp_basis(u)

    # Centroid from wire corners (matches green boxes better than pivots-only).
    cen = Vector((0.0, 0.0, 0.0))
    ncorner = 0
    for box in corner_boxes:
        for c in box:
            cen += c
            ncorner += 1
    if ncorner > 0:
        cen /= float(ncorner)
    else:
        for obj in objs_u:
            cen += obj.matrix_world.translation
        cen /= max(len(objs_u), 1)

    span = 0.05
    for box in corner_boxes:
        for c in box:
            span = max(span, abs((c - cen).dot(perp1)))
    span = max(span, 1e-4)

    offset_mag = span * 0.4 + 0.025
    line_base = cen + perp1 * offset_mag
    k = line_base.dot(u)

    def at_s(s: float) -> Vector:
        """Point on dimension line whose dot with u equals s (world projection)."""
        return u * (s - k) + line_base

    _GAP_LINE_SEGMENTS.append((at_s(intervals[0][0]), at_s(intervals[-1][1])))

    end_tick_h = max(span * 0.1, 0.032)

    for i in range(len(intervals) - 1):
        mx_i = intervals[i][1]
        mn_next = intervals[i + 1][0]
        g = mn_next - mx_i
        p_mx = at_s(mx_i)
        p_mn = at_s(mn_next)

        # Segment along projection axis strictly between slab max(prev) … min(next).
        _GAP_LINE_SEGMENTS.append((p_mx, p_mn))

        # Bracket marks exactly at bbox extents on u (avoid reading mid-tick as origin).
        _GAP_LINE_SEGMENTS.append((p_mx + perp2 * end_tick_h, p_mx - perp2 * end_tick_h))
        _GAP_LINE_SEGMENTS.append((p_mn + perp2 * end_tick_h, p_mn - perp2 * end_tick_h))

        mid_pt = at_s(0.5 * (mx_i + mn_next))
        label_anchor = mid_pt + perp1 * (offset_mag * 0.28)
        _GAP_LABELS.append((_gap_label(context, g), label_anchor))


def _draw_preview():
    lines: list[Vector] = []
    for corners in _PREVIEW_CORNERS:
        for i, j in _CUBE_EDGES:
            lines.append(corners[i])
            lines.append(corners[j])
    if lines:
        _draw_simple_lines(lines, _OVERLAY_COLOR, width=1.25)

    gap_pts: list[Vector] = []
    for a, b in _GAP_LINE_SEGMENTS:
        gap_pts.append(a.copy())
        gap_pts.append(b.copy())
    if gap_pts:
        _draw_simple_lines(gap_pts, _DIM_COLOR, width=_DIM_WIDTH)


def _draw_gap_labels_px():
    """POST_PIXEL BLF matching edit_mesh_draw_state.draw_callback_px rubber_band_label + draw_mesh_edges units."""
    if not _GAP_LABELS:
        return
    try:
        ctx = bpy.context
        sp = getattr(ctx, "space_data", None)
    except AttributeError:
        return
    if sp is None or getattr(sp, "type", "") != "VIEW_3D":
        return

    region = getattr(ctx, "region", None)
    rv3d = getattr(sp, "region_3d", None)
    if region is None or rv3d is None:
        return

    font_id = 0
    blf.size(font_id, 12)
    blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 0.8)

    for text, world_pos in _GAP_LABELS:
        pos_2d = location_3d_to_region_2d(region, rv3d, world_pos)
        if pos_2d is None:
            continue
        blf.color(font_id, 1.0, 1.0, 0.3, 1.0)
        w = blf.dimensions(font_id, text)[0]
        blf.position(font_id, int(pos_2d.x - w / 2), int(pos_2d.y + 12), 0)
        blf.draw(font_id, text)
        blf.color(font_id, 1.0, 1.0, 1.0, 1.0)


def _ensure_handler():
    global _draw_handler
    if _draw_handler is not None:
        return
    _draw_handler = bpy.types.SpaceView3D.draw_handler_add(_draw_preview, (), "WINDOW", "POST_VIEW")


def _ensure_px_handler():
    global _draw_handler_px
    if _draw_handler_px is not None:
        return
    _draw_handler_px = bpy.types.SpaceView3D.draw_handler_add(
        _draw_gap_labels_px,
        (),
        "WINDOW",
        "POST_PIXEL",
    )


def _remove_handler():
    global _draw_handler
    if _draw_handler is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, "WINDOW")
        except ValueError:
            pass
        _draw_handler = None


def _remove_px_handler():
    global _draw_handler_px
    if _draw_handler_px is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_draw_handler_px, "WINDOW")
        except ValueError:
            pass
        _draw_handler_px = None


def set_preview_corner_boxes(
    box_corners: list[list[Vector]],
    *,
    context=None,
    gap_objects=None,
    gap_axis_dir=None,
    positions_objects=None,
    positions_axis_dir=None,
    positions_ref_point=None,
) -> None:
    global _PREVIEW_CORNERS
    corners_work = list(box_corners)
    ref_objs = gap_objects if gap_objects is not None else positions_objects
    if ref_objs is not None and corners_work and len(ref_objs) == len(corners_work):
        ref_objs, corners_work = _dedupe_object_corner_pairs(ref_objs, corners_work)

    _PREVIEW_CORNERS = [[v.copy() for v in corners] for corners in corners_work]
    mark_alive()

    _GAP_LINE_SEGMENTS.clear()
    _GAP_LABELS.clear()
    _remove_px_handler()

    if (
        context
        and gap_objects is not None
        and gap_axis_dir is not None
        and ref_objs is not None
        and len(ref_objs) >= 2
    ):
        _rebuild_gap_visual(context, ref_objs, gap_axis_dir, _PREVIEW_CORNERS)
        _ensure_px_handler()
    elif (
        context
        and positions_objects is not None
        and positions_axis_dir is not None
        and positions_ref_point is not None
        and ref_objs is not None
        and len(ref_objs) >= 2
    ):
        _rebuild_positions_visual(
            context,
            list(ref_objs),
            positions_axis_dir,
            positions_ref_point,
            _PREVIEW_CORNERS,
        )
        _ensure_px_handler()

    _ensure_handler()
    _register_depsgraph()
    _start_watch_timer_if_needed()
    _tag_view3d_redraw()


def clear_preview() -> None:
    global _PREVIEW_CORNERS, _last_alive_monotonic
    _stop_watch_timer()
    _unregister_depsgraph()
    _PREVIEW_CORNERS.clear()
    _GAP_LINE_SEGMENTS.clear()
    _GAP_LABELS.clear()
    _last_alive_monotonic = None
    _remove_handler()
    _remove_px_handler()
    _tag_view3d_redraw()
    try:
        bpy.app.timers.register(_deferred_view3d_redraw, first_interval=0.0)
    except Exception:
        pass


def unregister_preview() -> None:
    clear_preview()
