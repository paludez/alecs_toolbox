import bpy
from mathutils import Vector
from .utils import get_bounds_data, apply_align_move, get_bounds_in_space, bbox_world_axis_interval


def bbox_axis_interval_world(obj, axis_dir):
    """Scalar min/max on axis_dir; uses evaluated mesh + matrix_world (scale/modifiers like Align)."""
    return bbox_world_axis_interval(obj, axis_dir)


def reference_projection_on_axis(obj, axis_dir, ref_point):
    """Scalar coordinate of MIN/CENTER/PIVOT/MAX on normalized axis_dir (world)."""
    if ref_point == "PIVOT":
        return obj.matrix_world.translation @ axis_dir
    if ref_point == "CENTER":
        return get_bounds_data(obj, "CENTER", space="WORLD") @ axis_dir
    mn, mx = bbox_axis_interval_world(obj, axis_dir)
    if ref_point == "MIN":
        return mn
    if ref_point == "MAX":
        return mx
    return get_bounds_data(obj, "CENTER", space="WORLD") @ axis_dir  # fallback


def distribute_objects_positions(objects, axis_dir, ref_point, endpoint_objs=None):
    """
    Evenly space reference points (MIN/CENTER/PIVOT/MAX) along axis_dir.
    If endpoint_objs is a pair (obj_a, obj_b), those two are fixed and everything else
    is distributed between them. Otherwise the positional extremes are used as endpoints.
    Returns (success, message).
    """
    bpy.context.view_layer.update()
    axis_dir = axis_dir.normalized()
    if len(objects) < 2:
        return False, "Select at least 2 objects"

    data = [(obj, reference_projection_on_axis(obj, axis_dir, ref_point)) for obj in objects]

    if endpoint_objs and len(endpoint_objs) == 2:
        ep_a, ep_b = endpoint_objs
        s_a = reference_projection_on_axis(ep_a, axis_dir, ref_point)
        s_b = reference_projection_on_axis(ep_b, axis_dir, ref_point)
        if s_a > s_b:
            s_a, s_b = s_b, s_a
            ep_a, ep_b = ep_b, ep_a
        fixed = {ep_a, ep_b}
        interior = sorted(
            [(obj, s) for obj, s in data if obj not in fixed],
            key=lambda x: x[1],
        )
        n = len(interior) + 1
        for i, (obj, _) in enumerate(interior, start=1):
            new_s = s_a + (s_b - s_a) * i / n
            delta_s = new_s - reference_projection_on_axis(obj, axis_dir, ref_point)
            apply_align_move(obj, axis_dir * delta_s)
    else:
        data.sort(key=lambda x: x[1])
        s_min = data[0][1]
        s_max = data[-1][1]
        if abs(s_max - s_min) < 1e-12:
            return False, "All objects project to the same position on this axis"
        n = len(data)
        for i, (obj, s) in enumerate(data):
            new_s = s_min + (s_max - s_min) * i / (n - 1)
            apply_align_move(obj, axis_dir * (new_s - s))

    return True, ""


def positions_spacing_auto_value(objects, axis_dir, ref_point):
    """Equal subdivision step (last−first)/(n−1) on sorted ref projections; None if degenerate."""
    axis_dir = axis_dir.normalized()
    if len(objects) < 2:
        return None
    scalars = sorted(reference_projection_on_axis(o, axis_dir, ref_point) for o in objects)
    span = scalars[-1] - scalars[0]
    if abs(span) < 1e-12:
        return None
    return span / float(len(objects) - 1)


def distribute_objects_positions_fixed_step(objects, axis_dir, ref_point, spacing, endpoint_objs=None):
    """
    Place references at s0, s0+spacing, s0+2*spacing, … along axis_dir (s0 = lowest sorted projection).
    Returns (success, message).
    """
    if endpoint_objs:
        return False, "Custom spacing is not supported with fixed endpoints"
    bpy.context.view_layer.update()
    axis_dir = axis_dir.normalized()
    if len(objects) < 2:
        return False, "Select at least 2 objects"
    if spacing < 0.0:
        return False, "Spacing cannot be negative"

    data = [(obj, reference_projection_on_axis(obj, axis_dir, ref_point)) for obj in objects]
    data.sort(key=lambda x: x[1])
    s0 = data[0][1]

    for i, (obj, _) in enumerate(data):
        new_s = s0 + spacing * float(i)
        delta_s = new_s - reference_projection_on_axis(obj, axis_dir, ref_point)
        apply_align_move(obj, axis_dir * delta_s)

    return True, ""


def distribute_objects_positions_fixed_step_anchor_active(
    objects, axis_dir, ref_point, spacing, active_obj
):
    """
    Same step between consecutive references after sort, but the active object's reference stays put.
    Targets: s_k = s_active + (k - i_act) * spacing for k in sorted order.
    """
    bpy.context.view_layer.update()
    axis_dir = axis_dir.normalized()
    if active_obj not in objects:
        return False, "Active object must be part of the selection"
    if len(objects) < 2:
        return False, "Select at least 2 objects"
    if spacing < 0.0:
        return False, "Spacing cannot be negative"

    snapshots = [
        (obj, reference_projection_on_axis(obj, axis_dir, ref_point)) for obj in objects
    ]
    snapshots.sort(key=lambda x: x[1])

    ia = None
    for idx, (obj, _) in enumerate(snapshots):
        if obj is active_obj:
            ia = idx
            break
    if ia is None:
        return False, "Active object must be part of the selection"

    s_act = snapshots[ia][1]
    targets = [s_act + (k - ia) * spacing for k in range(len(snapshots))]

    for (obj, s_snap), new_s in zip(snapshots, targets):
        delta_s = new_s - s_snap
        apply_align_move(obj, axis_dir * delta_s)

    return True, ""


def gaps_spacing_auto_value(objects, axis_dir):
    """Equal gap `(span − widths)/(n−1)` like distribute_objects_gaps; None if n<2."""
    axis_dir = axis_dir.normalized()
    if len(objects) < 2:
        return None
    data = []
    for obj in objects:
        mn, mx = bbox_axis_interval_world(obj, axis_dir)
        data.append((mn, mx, mx - mn))
    data.sort(key=lambda x: x[0])
    min_first = data[0][0]
    max_last = data[-1][1]
    total_span = max_last - min_first
    total_width = sum(d[2] for d in data)
    n = len(data)
    if n < 2:
        return None
    return (total_span - total_width) / float(n - 1)


def distribute_objects_gaps_fixed_gap(objects, axis_dir, gap, endpoint_objs=None):
    """
    Same stacking as distribute_objects_gaps but with a caller-chosen gap (can be negative = overlap).
    """
    if endpoint_objs:
        return False, "Custom gap is not supported with fixed endpoints"
    bpy.context.view_layer.update()
    axis_dir = axis_dir.normalized()
    if len(objects) < 2:
        return False, "Select at least 2 objects"

    data = []
    for obj in objects:
        mn, mx = bbox_axis_interval_world(obj, axis_dir)
        data.append((mn, mx, mx - mn, obj))

    data.sort(key=lambda x: x[0])
    current = data[0][0]
    for mn, mx, w, obj in data:
        delta_s = current - mn
        apply_align_move(obj, axis_dir * delta_s)
        current += w + gap

    return True, ""


def distribute_objects_gaps_fixed_gap_anchor_active(objects, axis_dir, gap, active_obj):
    """
    Fixed gap stacking along axis while the active object's bbox projection stays unmoved on that axis:
    slab order is by bbox min (mn); objects left of active pack backward, objects right pack forward.
    """
    bpy.context.view_layer.update()
    axis_dir = axis_dir.normalized()
    if active_obj not in objects:
        return False, "Active object must be part of the selection"
    if len(objects) < 2:
        return False, "Select at least 2 objects"

    data = []
    for obj in objects:
        mn, mx = bbox_axis_interval_world(obj, axis_dir)
        data.append((mn, mx, mx - mn, obj))

    data.sort(key=lambda x: x[0])

    ia = None
    for idx, row in enumerate(data):
        if row[3] is active_obj:
            ia = idx
            break
    if ia is None:
        return False, "Active object must be part of the selection"

    mn_active, _, _, _ = data[ia]

    # Pack toward smaller mn: keep mx_j + gap == mn of slab to the right.
    next_right_mn = mn_active
    for j in range(ia - 1, -1, -1):
        mn_j, mx_j, _w_unused, obj_j = data[j]
        mx_target = next_right_mn - gap
        delta_s = mx_target - mx_j
        apply_align_move(obj_j, axis_dir * delta_s)
        next_right_mn = mn_j + delta_s

    bpy.context.view_layer.update()

    mn_a2, mx_a2 = bbox_axis_interval_world(active_obj, axis_dir)
    current = mx_a2 + gap
    for j in range(ia + 1, len(data)):
        obj_j = data[j][3]
        mn_j, mx_j = bbox_axis_interval_world(obj_j, axis_dir)
        w_j = mx_j - mn_j
        delta_s = current - mn_j
        apply_align_move(obj_j, axis_dir * delta_s)
        current += w_j + gap

    return True, ""


def distribute_objects_gaps(objects, axis_dir, endpoint_objs=None):
    """
    Equal gaps between world bounding-box projections along axis_dir.
    If endpoint_objs is a pair (obj_a, obj_b), those two are fixed endpoints.
    Otherwise the positional extremes are used.
    Returns (success, message).
    """
    bpy.context.view_layer.update()
    axis_dir = axis_dir.normalized()
    if len(objects) < 2:
        return False, "Select at least 2 objects"

    data = []
    for obj in objects:
        mn, mx = bbox_axis_interval_world(obj, axis_dir)
        data.append((mn, mx, mx - mn, obj))

    data.sort(key=lambda x: x[0])

    if endpoint_objs and len(endpoint_objs) == 2:
        ep_a, ep_b = endpoint_objs
        mn_a, mx_a = bbox_axis_interval_world(ep_a, axis_dir)
        mn_b, mx_b = bbox_axis_interval_world(ep_b, axis_dir)
        if mn_a > mn_b:
            mn_a, mx_a, mn_b, mx_b = mn_b, mx_b, mn_a, mx_a
            ep_a, ep_b = ep_b, ep_a
        fixed = {ep_a, ep_b}
        interior = [(mn, mx, w, obj) for mn, mx, w, obj in data if obj not in fixed]
        interior.sort(key=lambda x: x[0])
        total_span = mx_b - mn_a
        total_width = (mx_a - mn_a) + (mx_b - mn_b) + sum(w for _, _, w, _ in interior)
        n_gaps = len(interior) + 1
        gap = (total_span - total_width) / n_gaps
        current = mx_a + gap
        for mn, mx, w, obj in interior:
            delta_s = current - mn
            apply_align_move(obj, axis_dir * delta_s)
            current += w + gap
    else:
        min_first = data[0][0]
        max_last = data[-1][1]
        total_span = max_last - min_first
        total_width = sum(d[2] for d in data)
        n = len(data)
        if n < 2:
            return False, "Select at least 2 objects"
        gap = (total_span - total_width) / (n - 1)
        current = min_first
        for mn, mx, w, obj in data:
            delta_s = current - mn
            apply_align_move(obj, axis_dir * delta_s)
            current += w + gap

    return True, ""

def align_position(source, target, x=True, y=True, z=True, 
                   source_point='PIVOT', target_point='PIVOT', use_active_orient=False,
                   offset_x=0.0, offset_y=0.0, offset_z=0.0):
    
    if use_active_orient:
        s_min_local, s_max_local = get_bounds_in_space(source, target.matrix_world)
        t_min_local, t_max_local = get_bounds_in_space(target, target.matrix_world)

        if source_point == 'PIVOT':
            source_pt_local = target.matrix_world.inverted() @ source.matrix_world.translation
        elif source_point == 'MIN':
            source_pt_local = s_min_local
        elif source_point == 'MAX':
            source_pt_local = s_max_local
        else: # CENTER
            source_pt_local = (s_min_local + s_max_local) / 2

        if target_point == 'PIVOT':
            target_pt_local = Vector((0.0, 0.0, 0.0))
        elif target_point == 'MIN':
            target_pt_local = t_min_local
        elif target_point == 'MAX':
            target_pt_local = t_max_local
        else: # CENTER
            target_pt_local = (t_min_local + t_max_local) / 2
        
        delta_local = target_pt_local - source_pt_local
        
        if not x: delta_local.x = 0
        else: delta_local.x += offset_x
        if not y: delta_local.y = 0
        else: delta_local.y += offset_y
        if not z: delta_local.z = 0
        else: delta_local.z += offset_z

        delta_world = target.matrix_world.to_3x3() @ delta_local
    else:
        source_world = get_bounds_data(source, source_point, space='WORLD')
        target_world = get_bounds_data(target, target_point, space='WORLD')
        delta_world = target_world - source_world
        if not x: delta_world.x = 0
        else: delta_world.x += offset_x
        if not y: delta_world.y = 0
        else: delta_world.y += offset_y
        if not z: delta_world.z = 0
        else: delta_world.z += offset_z
    
    apply_align_move(source, delta_world)

def align_orientation(source, target, x=True, y=True, z=True,
                      offset_x=0.0, offset_y=0.0, offset_z=0.0):
    """Match target Euler per axis when enabled; offsets are radians (added after match)."""
    src_euler = source.rotation_euler.copy()
    tgt_euler = target.rotation_euler.copy()

    if x:
        src_euler.x = tgt_euler.x + offset_x
    if y:
        src_euler.y = tgt_euler.y + offset_y
    if z:
        src_euler.z = tgt_euler.z + offset_z

    source.rotation_euler = src_euler


def match_scale(source, target, x=True, y=True, z=True,
                offset_x=0.0, offset_y=0.0, offset_z=0.0):
    """Match target scale per axis when enabled; offsets added to matched components."""
    if x:
        source.scale.x = target.scale.x + offset_x
    if y:
        source.scale.y = target.scale.y + offset_y
    if z:
        source.scale.z = target.scale.z + offset_z