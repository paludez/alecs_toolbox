"""Shared sphere-rig math used by both camera and light orbit rigs.

These functions have no Blender class registrations and no side effects.
"""
import math

import bpy
from mathutils import Vector


def object_in_view_layer(obj, context) -> bool:
    """True if obj is non-None and visible in the current view layer."""
    return obj is not None and any(o == obj for o in context.view_layer.objects)


def world_sphere_unit_direction(az: float, el: float) -> Vector:
    """Unit vector on the unit sphere for azimuth *az* and elevation *el* (radians)."""
    c_el = math.cos(el)
    return Vector((c_el * math.cos(az), c_el * math.sin(az), math.sin(el))).normalized()


def world_sphere_offset(az: float, el: float, dist: float) -> Vector:
    """World-space displacement vector for spherical coords (az, el, dist)."""
    return world_sphere_unit_direction(az, el) * max(1e-4, float(dist))


def world_sphere_az_el_dist_from_delta(
    delta: Vector,
    *,
    fallback_az: float = 0.0,
) -> tuple[float, float, float]:
    """Convert a world-space delta vector to (azimuth, elevation, distance)."""
    dsq = delta.length_squared
    if dsq < 1e-20:
        return fallback_az, 0.0, 1e-3
    vz = delta.normalized()
    zn = max(-1.0, min(1.0, vz.z))
    elev = math.asin(zn)
    horiz = math.cos(elev)
    azim = math.atan2(vz.y, vz.x) if abs(horiz) > 1e-6 else fallback_az
    return azim, elev, math.sqrt(dsq)


def object_foot_world_xy(obj: bpy.types.Object) -> Vector:
    """World XY projection of *obj* origin (Z = 0), used as sphere-rig foot."""
    w = obj.matrix_world.translation
    return Vector((w.x, w.y, 0.0))
