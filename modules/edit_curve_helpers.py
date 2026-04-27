"""Edit-mode curve: selected control points, handles, and NURBS/Poly points."""

from mathutils import Vector


def poll_active_curve_edit_mode(context):
    return (
        context.active_object is not None
        and context.active_object.type == "CURVE"
        and context.mode == "EDIT_CURVE"
    )


class _BezierControl:
    __slots__ = ("bp",)

    def __init__(self, bp):
        self.bp = bp

    def get_co(self):
        return self.bp.co.copy()

    def set_co(self, v):
        self.bp.co = v


class _BezierHandleLeft:
    __slots__ = ("bp",)

    def __init__(self, bp):
        self.bp = bp

    def get_co(self):
        return self.bp.handle_left.copy()

    def set_co(self, v):
        self.bp.handle_left = v


class _BezierHandleRight:
    __slots__ = ("bp",)

    def __init__(self, bp):
        self.bp = bp

    def get_co(self):
        return self.bp.handle_right.copy()

    def set_co(self, v):
        self.bp.handle_right = v


class _NurbsPolyPoint:
    __slots__ = ("pt",)

    def __init__(self, pt):
        self.pt = pt

    def get_co(self):
        c = self.pt.co
        return Vector((c.x, c.y, c.z))

    def set_co(self, v):
        self.pt.co.x = v.x
        self.pt.co.y = v.y
        self.pt.co.z = v.z


def selected_control_point_keys(curve):
    """
    Bezier control points and NURBS/poly points only (no handles).
    """
    keys = []
    for si, spline in enumerate(curve.splines):
        if spline.type == "BEZIER":
            for pi, bp in enumerate(spline.bezier_points):
                if getattr(bp, "hide", False):
                    continue
                if bp.select_control_point:
                    keys.append((si, pi, "CONTROL"))
        else:
            for pi, pt in enumerate(spline.points):
                if getattr(pt, "hide", False):
                    continue
                if pt.select:
                    keys.append((si, pi, "POINT"))
    return keys


def canonical_point_pair_key(key_a, key_b):
    """Stable key for a pair of control-point keys (for de-dupe)."""
    return tuple(sorted((key_a, key_b), key=lambda k: (k[0], k[1], k[2])))


def gather_selected_curve_targets(curve):
    """Bezier (control + handles) and NURBS / Poly / Path-style splines (points)."""
    targets = []
    for spline in curve.splines:
        if spline.type == "BEZIER":
            for bp in spline.bezier_points:
                if getattr(bp, "hide", False):
                    continue
                if bp.select_control_point:
                    targets.append(_BezierControl(bp))
                if bp.select_left_handle:
                    targets.append(_BezierHandleLeft(bp))
                if bp.select_right_handle:
                    targets.append(_BezierHandleRight(bp))
        else:
            for pt in spline.points:
                if getattr(pt, "hide", False):
                    continue
                if pt.select:
                    targets.append(_NurbsPolyPoint(pt))
    return targets


def snapshot_selected_curve_keys(curve):
    """Stable (spline_index, point_index, kind) for each selected curve element."""
    keys = []
    for si, spline in enumerate(curve.splines):
        if spline.type == "BEZIER":
            for pi, bp in enumerate(spline.bezier_points):
                if getattr(bp, "hide", False):
                    continue
                if bp.select_control_point:
                    keys.append((si, pi, "CONTROL"))
                if bp.select_left_handle:
                    keys.append((si, pi, "LEFT"))
                if bp.select_right_handle:
                    keys.append((si, pi, "RIGHT"))
        else:
            for pi, pt in enumerate(spline.points):
                if getattr(pt, "hide", False):
                    continue
                if pt.select:
                    keys.append((si, pi, "POINT"))
    return keys


def resolve_curve_target(curve, si, pi, kind):
    if si < 0 or si >= len(curve.splines):
        return None
    spline = curve.splines[si]
    if kind == "POINT":
        if spline.type == "BEZIER":
            return None
        if pi < 0 or pi >= len(spline.points):
            return None
        return _NurbsPolyPoint(spline.points[pi])
    if spline.type != "BEZIER":
        return None
    if pi < 0 or pi >= len(spline.bezier_points):
        return None
    bp = spline.bezier_points[pi]
    if kind == "CONTROL":
        return _BezierControl(bp)
    if kind == "LEFT":
        return _BezierHandleLeft(bp)
    if kind == "RIGHT":
        return _BezierHandleRight(bp)
    return None


def keys_to_targets(curve, keys):
    out = []
    for key in keys:
        t = resolve_curve_target(curve, *key)
        if t is not None:
            out.append(t)
    return out


def project_curve_targets_to_plane(targets, obj, plane_point_world, plane_normal_world, factor=1.0):
    """Move each target toward the plane through plane_point with given normal (world)."""
    if plane_normal_world.length_squared < 1e-20:
        return False
    plane_normal_world = plane_normal_world.normalized()
    world_mx = obj.matrix_world
    inv_world_mx = world_mx.inverted()
    for t in targets:
        co = t.get_co()
        v_world = world_mx @ co
        dist = (v_world - plane_point_world).dot(plane_normal_world)
        projected_world = v_world - dist * plane_normal_world
        target_local = inv_world_mx @ projected_world
        t.set_co(co.lerp(target_local, factor))
    return True
