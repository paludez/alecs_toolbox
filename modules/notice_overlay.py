"""Viewport toast: filleted box + text.
Usage (from any operator):

    from ..modules import notice_overlay

    # Uses DEFAULT_* in this file (colors, timing, font, padding, …)
    notice_overlay.show_notice("Local")

    # Rare override: show_notice("Saved", anchor="center")

anchor (string): "center", "bottom_left", "bottom_center", "bottom_right"

Optional args: anchor, margin, duration, font_size, box_color, text_color,
corner_radius, padding, allcaps. Colors are RGBA 0.0–1.0.

Edit addon-wide defaults: DEFAULT_* block below.

Draw handler only — no timers. The toast is drawn on viewport redraws and
removed on the first redraw after duration (click, orbit, etc.). If the
viewport stays still, it may linger until the next redraw.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Sequence

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

_VALID_ANCHORS = frozenset({"center", "bottom_left", "bottom_center", "bottom_right"})

_CORNER_SEGMENTS = 8

# --- Addon-wide defaults (edit here; used when show_notice omits an argument) ---
DEFAULT_BOX_COLOR = (1.0, 1.0, 1.0, 0.05)
DEFAULT_TEXT_COLOR = (0.5, 0.5, 0.5, 1.0)
DEFAULT_CORNER_RADIUS = 10.0
DEFAULT_PADDING = (25, 25)
DEFAULT_MARGIN = 10
DEFAULT_DURATION = 1.5
DEFAULT_FONT_SIZE = 50
DEFAULT_ANCHOR = "bottom_left"
DEFAULT_ALLCAPS = True

_draw_handler_px = None
_notice: "_Notice | None" = None


@dataclass
class _Notice:
    text: str
    start: float
    duration: float
    anchor: str
    margin: int
    font_size: int
    box_color: tuple[float, float, float, float]
    text_color: tuple[float, float, float, float]
    corner_radius: float
    padding: tuple[int, int]


def _tag_view3d_redraw() -> None:
    try:
        for window in bpy.context.window_manager.windows:
            tag_win = getattr(window, "tag_redraw", None)
            if callable(tag_win):
                tag_win()
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except Exception:
        pass


def _rounded_rect_boundary(
    x: float, y: float, w: float, h: float, radius: float, segments: int = _CORNER_SEGMENTS
) -> list[tuple[float, float]]:
    r = min(max(radius, 0.0), w * 0.5, h * 0.5)
    if r <= 0.0:
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]

    def arc(cx: float, cy: float, angle_start: float, angle_end: float) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        for i in range(segments + 1):
            t = i / segments
            a = angle_start + (angle_end - angle_start) * t
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        return pts

    pts: list[tuple[float, float]] = []
    pts.extend(arc(x + r, y + r, math.pi, 1.5 * math.pi))
    pts.extend(arc(x + w - r, y + r, 1.5 * math.pi, 2.0 * math.pi))
    pts.extend(arc(x + w - r, y + h - r, 0.0, 0.5 * math.pi))
    pts.extend(arc(x + r, y + h - r, 0.5 * math.pi, math.pi))
    return pts


def _draw_rounded_rect_fill(
    x: float, y: float, w: float, h: float, radius: float, color: Sequence[float]
) -> None:
    boundary = _rounded_rect_boundary(x, y, w, h, radius)
    if len(boundary) < 3:
        return
    cx = x + w * 0.5
    cy = y + h * 0.5
    verts = [(cx, cy)] + boundary
    indices = [(0, i, i + 1) for i in range(1, len(verts) - 1)]
    indices.append((0, len(verts) - 1, 1))

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(shader, "TRIS", {"pos": verts}, indices=indices)
    gpu.state.blend_set("ALPHA")
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _layout(
    region,
    text: str,
    font_id: int,
    anchor: str,
    margin: int,
    padding: tuple[int, int],
) -> tuple[float, float, float, float, float, float]:
    tw, th = blf.dimensions(font_id, text)
    pad_x, pad_y = padding
    bw = tw + 2 * pad_x
    bh = th + 2 * pad_y

    if anchor == "bottom_left":
        x0 = float(margin)
        y0 = float(margin)
    elif anchor == "bottom_center":
        x0 = (region.width - bw) * 0.5
        y0 = float(margin)
    elif anchor == "bottom_right":
        x0 = region.width - bw - margin
        y0 = float(margin)
    else:
        cx = region.width * 0.5
        cy = region.height * 0.55
        x0 = cx - bw * 0.5
        y0 = cy - bh * 0.5

    text_x = x0 + pad_x
    text_y = y0 + pad_y
    return x0, y0, bw, bh, text_x, text_y


def _draw_notice() -> None:
    notice = _notice
    if notice is None or not notice.text:
        _remove_draw_handler()
        return
    if time.monotonic() - notice.start >= notice.duration:
        _clear_notice()
        return
    region = bpy.context.region
    if region is None:
        return

    font_id = 0
    blf.size(font_id, notice.font_size)
    x0, y0, bw, bh, text_x, text_y = _layout(
        region, notice.text, font_id, notice.anchor, notice.margin, notice.padding
    )

    text_r, text_g, text_b, text_a = notice.text_color

    try:
        _draw_rounded_rect_fill(x0, y0, bw, bh, notice.corner_radius, notice.box_color)
        blf.color(font_id, text_r, text_g, text_b, text_a)
        blf.position(font_id, int(text_x), int(text_y), 0)
        blf.draw(font_id, notice.text)
    finally:
        gpu.state.blend_set("NONE")


def _ensure_draw_handler() -> None:
    global _draw_handler_px
    if _draw_handler_px is not None:
        return
    _draw_handler_px = bpy.types.SpaceView3D.draw_handler_add(
        _draw_notice, (), "WINDOW", "POST_PIXEL"
    )


def _remove_draw_handler() -> None:
    global _draw_handler_px
    if _draw_handler_px is None:
        return
    try:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handler_px, "WINDOW")
    except Exception:
        pass
    _draw_handler_px = None


def _clear_notice() -> None:
    global _notice
    _notice = None
    _remove_draw_handler()
    _tag_view3d_redraw()


def show_notice(
    text: str,
    *,
    anchor: str = DEFAULT_ANCHOR,
    margin: int = DEFAULT_MARGIN,
    duration: float = DEFAULT_DURATION,
    font_size: int = DEFAULT_FONT_SIZE,
    box_color: tuple[float, float, float, float] = DEFAULT_BOX_COLOR,
    text_color: tuple[float, float, float, float] = DEFAULT_TEXT_COLOR,
    corner_radius: float = DEFAULT_CORNER_RADIUS,
    padding: tuple[int, int] = DEFAULT_PADDING,
    allcaps: bool = DEFAULT_ALLCAPS,
) -> None:
    global _notice

    _notice = _Notice(
        text=text.upper() if allcaps else text,
        start=time.monotonic(),
        duration=max(duration, 0.05),
        anchor=anchor if anchor in _VALID_ANCHORS else "center",
        margin=margin,
        font_size=font_size,
        box_color=box_color,
        text_color=text_color,
        corner_radius=corner_radius,
        padding=padding,
    )

    _ensure_draw_handler()
    _tag_view3d_redraw()


def unregister() -> None:
    """Addon unload: remove draw handler if still attached."""
    _clear_notice()
