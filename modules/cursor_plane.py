"""Helpers for working on the 3D cursor's XY plane and on arbitrary 2D-in-3D planes.

Used by 2D Drafting tools (Draw Mesh Edges, Trim, Extend, Fillet, Chamfer).
The cursor plane uses the cursor's local Z axis as the normal (its XY plane).
The `to_uv` / `from_uv` / `segment_segment_2d` helpers are generic and work
with any plane defined by `(origin, u_axis, v_axis)`.
"""
from mathutils import Vector


def cursor_plane_axes(context) -> tuple[Vector, Vector, Vector]:
    """Returns (normal, u, v) axes of the cursor's XY plane (Z normal)."""
    cursor = context.scene.cursor
    M3 = cursor.matrix.to_3x3()
    cx = Vector((M3[0][0], M3[1][0], M3[2][0])).normalized()
    cy = Vector((M3[0][1], M3[1][1], M3[2][1])).normalized()
    cz = Vector((M3[0][2], M3[1][2], M3[2][2])).normalized()
    return (cz, cx, cy)


def intersect_cursor_plane(context, origin_w: Vector, direction_w: Vector) -> Vector:
    """Ray vs cursor plane intersection. Falls back to plane co if ray is parallel."""
    cursor = context.scene.cursor
    plane_co = cursor.location
    normal, _u, _v = cursor_plane_axes(context)
    denom = direction_w.dot(normal)
    if abs(denom) < 1e-9:
        return plane_co.copy()
    t = (plane_co - origin_w).dot(normal) / denom
    return origin_w + direction_w * t


def project_onto_cursor_plane(context, world_co: Vector) -> Vector:
    """Perpendicular projection of a world point onto the cursor plane."""
    cursor = context.scene.cursor
    plane_co = cursor.location
    normal, _u, _v = cursor_plane_axes(context)
    dist = (world_co - plane_co).dot(normal)
    return world_co - normal * dist


def to_uv(world_co: Vector, origin: Vector, u_ax: Vector, v_ax: Vector) -> tuple[float, float]:
    """Express a 3D world point as (u, v) coords on a plane (origin, u_ax, v_ax)."""
    delta = world_co - origin
    return (delta.dot(u_ax), delta.dot(v_ax))


def from_uv(uval: float, vval: float, origin: Vector, u_ax: Vector, v_ax: Vector) -> Vector:
    """Convert (u, v) plane coords back to 3D world space."""
    return origin + u_ax * uval + v_ax * vval


def segment_segment_2d(
    a0: tuple[float, float],
    a1: tuple[float, float],
    b0: tuple[float, float],
    b1: tuple[float, float],
    eps: float = 1e-9,
) -> tuple[float, float] | None:
    """2D line/segment-segment intersection in parametric form.

    Returns (t, s) where intersection = a0 + t*(a1-a0) = b0 + s*(b1-b0).
    Caller decides whether to clamp t/s to [0, 1] (segment) or treat as
    infinite line. Returns None if the lines are parallel (within eps).
    """
    ax, ay = a0[0], a0[1]
    bx, by = a1[0] - a0[0], a1[1] - a0[1]
    cx, cy = b0[0], b0[1]
    dx, dy = b1[0] - b0[0], b1[1] - b0[1]
    denom = bx * dy - by * dx
    if abs(denom) < eps:
        return None
    t = ((cx - ax) * dy - (cy - ay) * dx) / denom
    s = ((cx - ax) * by - (cy - ay) * bx) / denom
    return (t, s)
