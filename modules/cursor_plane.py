"""Helpers for working on the 3D cursor's XY plane and on arbitrary 2D-in-3D planes.

Used by 2D Drafting tools (Draw Mesh Edges, Trim, Extend, Fillet, Chamfer).
The cursor plane uses the cursor's local Z axis as the normal (its XY plane).
The `to_uv` / `from_uv` / `segment_segment_2d` helpers are generic and work
with any plane defined by `(origin, u_axis, v_axis)`.
"""
from __future__ import annotations

import bpy
from mathutils import Vector

Context = bpy.types.Context


def cursor_plane_axes(context: Context) -> tuple[Vector, Vector, Vector]:
    """Returns (normal, u, v) axes of the cursor's XY plane (Z normal)."""
    M3 = context.scene.cursor.matrix.to_3x3()
    return (M3.col[2].normalized(), M3.col[0].normalized(), M3.col[1].normalized())


def intersect_cursor_plane(
    context: Context,
    origin_w: Vector,
    direction_w: Vector,
) -> Vector | None:
    """Ray vs cursor plane intersection. Returns None if ray is parallel to plane."""
    plane_co = context.scene.cursor.location.copy()
    normal, _u, _v = cursor_plane_axes(context)
    denom = direction_w.dot(normal)
    if abs(denom) < 1e-9:
        return None
    t = (plane_co - origin_w).dot(normal) / denom
    return origin_w + direction_w * t


def project_onto_cursor_plane(context: Context, world_co: Vector) -> Vector:
    """Perpendicular projection of a world point onto the cursor plane."""
    plane_co = context.scene.cursor.location.copy()
    normal, _u, _v = cursor_plane_axes(context)
    return project_onto_plane(world_co, plane_co, normal)


def project_onto_plane(world_co: Vector, plane_co: Vector, plane_n: Vector) -> Vector:
    """Perpendicular projection of a world point onto an arbitrary plane."""
    normal = Vector(plane_n).normalized()
    dist = (Vector(world_co) - Vector(plane_co)).dot(normal)
    return Vector(world_co) - normal * dist


def intersect_plane(
    plane_co: Vector,
    plane_n: Vector,
    origin_w: Vector,
    direction_w: Vector,
) -> Vector | None:
    """Ray vs arbitrary plane intersection. Returns None if ray is parallel to plane."""
    normal = Vector(plane_n).normalized()
    denom = Vector(direction_w).dot(normal)
    if abs(denom) < 1e-9:
        return None
    t = (Vector(plane_co) - Vector(origin_w)).dot(normal) / denom
    return Vector(origin_w) + Vector(direction_w) * t


def to_uv(world_co: Vector, origin: Vector, u_ax: Vector, v_ax: Vector) -> tuple[float, float]:
    """Express a 3D world point as (u, v) coords on a plane (origin, u_ax, v_ax).
    Assumes u_ax and v_ax are orthonormal."""
    delta = world_co - origin
    return (delta.dot(u_ax), delta.dot(v_ax))


def from_uv(uval: float, vval: float, origin: Vector, u_ax: Vector, v_ax: Vector) -> Vector:
    """Convert (u, v) plane coords back to 3D world space.
    Assumes u_ax and v_ax are orthonormal."""
    return origin + u_ax * uval + v_ax * vval


def segment_segment_2d(
    a0: tuple[float, float],
    a1: tuple[float, float],
    b0: tuple[float, float],
    b1: tuple[float, float],
    eps: float = 1e-9,
) -> tuple[float, float] | None:
    """2D segment-segment intersection. Returns (t, s) or None if parallel.

    Caller decides whether to clamp t/s to [0, 1] (segment) or treat as infinite lines.
    """
    da = (a1[0] - a0[0], a1[1] - a0[1])
    db = (b1[0] - b0[0], b1[1] - b0[1])
    denom = da[0] * db[1] - da[1] * db[0]
    if abs(denom) < eps:
        return None
    diff = (b0[0] - a0[0], b0[1] - a0[1])
    t = (diff[0] * db[1] - diff[1] * db[0]) / denom
    s = (diff[0] * da[1] - diff[1] * da[0]) / denom
    return (t, s)