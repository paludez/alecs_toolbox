"""Viewport wireframe overlay for Gaps-mode distribute preview.

Each box is eight world-space corners (world AABB or OBB w.r.t. active local axes).
Clears when Redo no longer drives the operator (heartbeat)."""

import time

import bpy
from mathutils import Vector

from .drawing_tools import _draw_simple_lines

_PREVIEW_CORNERS: list[list[Vector]] = []
_draw_handler = None
_watch_active = False
_depsgraph_registered = False

_last_alive_monotonic: float | None = None
_STALE_AFTER_SEC = 3.0

_OVERLAY_COLOR = (0.15, 0.85, 0.45, 0.55)
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
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except Exception:
        pass


def mark_alive() -> None:
    """Refresh heartbeat (Distribute.execute / draw, or preview update)."""
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
    if not _PREVIEW_CORNERS:
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


def _draw_preview():
    if not _PREVIEW_CORNERS:
        return
    lines: list[Vector] = []
    for corners in _PREVIEW_CORNERS:
        for i, j in _CUBE_EDGES:
            lines.append(corners[i])
            lines.append(corners[j])
    _draw_simple_lines(lines, _OVERLAY_COLOR, width=1.25)


def _ensure_handler():
    global _draw_handler
    if _draw_handler is not None:
        return
    _draw_handler = bpy.types.SpaceView3D.draw_handler_add(_draw_preview, (), "WINDOW", "POST_VIEW")


def _remove_handler():
    global _draw_handler
    if _draw_handler is None:
        return
    try:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, "WINDOW")
    except ValueError:
        pass
    _draw_handler = None


def set_preview_corner_boxes(box_corners: list[list[Vector]]) -> None:
    """wireframe cuboids: each inner list is eight world corners (matching _CUBE_EDGES order)."""
    global _PREVIEW_CORNERS
    _PREVIEW_CORNERS = [[v.copy() for v in corners] for corners in box_corners]
    mark_alive()
    _ensure_handler()
    _register_depsgraph()
    _start_watch_timer_if_needed()
    _tag_view3d_redraw()


def clear_preview() -> None:
    global _PREVIEW_CORNERS, _last_alive_monotonic
    _stop_watch_timer()
    _unregister_depsgraph()
    _PREVIEW_CORNERS.clear()
    _last_alive_monotonic = None
    _remove_handler()
    _tag_view3d_redraw()


def unregister_preview() -> None:
    """Remove draw handler when addon disables."""
    clear_preview()
