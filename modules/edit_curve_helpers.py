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


# ---------------------------------------------------------------------------
# Curve operator helpers (shared with operators/edit_mesh.py)
# ---------------------------------------------------------------------------

def curve_farthest_pair_targets(targets):
    """Return the two targets that are farthest apart."""
    if len(targets) < 2:
        return None, None
    max_d = -1.0
    ia, ib = 0, 1
    cos = [t.get_co() for t in targets]
    for i in range(len(targets)):
        for j in range(i + 1, len(targets)):
            d = (cos[i] - cos[j]).length_squared
            if d > max_d:
                max_d = d
                ia, ib = i, j
    return targets[ia], targets[ib]


def curve_best_fit_plane_local_vectors(targets):
    """Return (v_a, v_b, v_c) local coords that define the best-fit plane, or None."""
    if len(targets) < 3:
        return None
    cos = [t.get_co() for t in targets]
    max_dist_sq = -1.0
    ia, ib = 0, 1
    for i in range(len(cos)):
        for j in range(i + 1, len(cos)):
            dist_sq = (cos[i] - cos[j]).length_squared
            if dist_sq > max_dist_sq:
                max_dist_sq = dist_sq
                ia, ib = i, j
    v_a, v_b = cos[ia], cos[ib]
    line_vec = v_b - v_a
    if line_vec.length_squared < 1e-9:
        return None
    v_c = None
    max_line_dist_sq = -1.0
    for k, co in enumerate(cos):
        if k == ia or k == ib:
            continue
        dist_sq = (co - v_a).cross(line_vec).length_squared
        if dist_sq > max_line_dist_sq:
            max_line_dist_sq = dist_sq
            v_c = co
    if v_c is None:
        return None
    return v_a, v_b, v_c


def execute_make_collinear_curve(op, context):
    """Run make-collinear on a curve object."""
    obj = context.active_object
    curve = obj.data
    targets = gather_selected_curve_targets(curve)
    if len(targets) < 2:
        op.report({'WARNING'}, "Select at least 2 curve points or handles")
        return {'CANCELLED'}
    if op.mode == 'HISTORY':
        op.report({'WARNING'}, "Last Two Selected is only available in mesh edit mode")
        return {'CANCELLED'}

    ta, tb = curve_farthest_pair_targets(targets)
    if not ta or not tb:
        op.report({'WARNING'}, "Could not determine line endpoints")
        return {'CANCELLED'}

    world_mx = obj.matrix_world
    inv_world_mx = world_mx.inverted()
    line_origin = world_mx @ ta.get_co()
    line_vector = world_mx @ tb.get_co() - line_origin
    if line_vector.length_squared < 1e-9:
        op.report({'WARNING'}, "Line endpoints coincide")
        return {'CANCELLED'}
    line_direction = line_vector.normalized()

    projections = []
    for t in targets:
        vec = world_mx @ t.get_co() - line_origin
        projections.append((vec.dot(line_direction), t))

    if op.distribute and len(projections) > 1:
        projections.sort(key=lambda x: x[0])
        start_dist = projections[0][0]
        end_dist = projections[-1][0]
        total_len = end_dist - start_dist
        for i, (dist, t) in enumerate(projections):
            fraction = i / (len(projections) - 1)
            target_dist = start_dist + total_len * fraction
            target_world = line_origin + line_direction * target_dist
            target_local = inv_world_mx @ target_world
            co = t.get_co()
            t.set_co(co.lerp(target_local, op.factor))
    else:
        for dist, t in projections:
            target_world = line_origin + line_direction * dist
            target_local = inv_world_mx @ target_world
            co = t.get_co()
            t.set_co(co.lerp(target_local, op.factor))

    curve.update_tag()
    return {'FINISHED'}


def execute_make_coplanar_curve(op, context):
    """Run make-coplanar on a curve object."""
    obj = context.active_object
    curve = obj.data
    targets = gather_selected_curve_targets(curve)
    if len(targets) < 3:
        op.report({'WARNING'}, "Select at least 3 curve points or handles")
        return {'CANCELLED'}
    if op.mode != 'BEST_FIT':
        op.report({'WARNING'}, "For curves only Best Fit is supported")
        return {'CANCELLED'}

    plane_locals = curve_best_fit_plane_local_vectors(targets)
    if plane_locals is None:
        op.report({'WARNING'}, "Could not define a plane from selection (collinear?)")
        return {'CANCELLED'}
    v_a, v_b, v_c = plane_locals

    world_mx = obj.matrix_world
    inv_world_mx = world_mx.inverted()
    p1_w = world_mx @ v_a
    p2_w = world_mx @ v_b
    p3_w = world_mx @ v_c
    plane_normal = (p2_w - p1_w).cross(p3_w - p1_w)
    if plane_normal.length_squared < 1e-9:
        op.report({'WARNING'}, "Defining points are collinear")
        return {'CANCELLED'}
    plane_normal.normalize()
    plane_point = p1_w

    for t in targets:
        co = t.get_co()
        v_world = world_mx @ co
        dist = (v_world - plane_point).dot(plane_normal)
        projected_world = v_world - dist * plane_normal
        target_local = inv_world_mx @ projected_world
        t.set_co(co.lerp(target_local, op.factor))

    curve.update_tag()
    return {'FINISHED'}
