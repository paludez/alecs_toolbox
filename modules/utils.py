import bpy
import math
import hashlib
import collections
import mathutils
import numpy as np
from mathutils import Vector


def safe_operator_props(op, **kwargs):
    """Set RNA props on a layout.operator() result; no-op if poll failed (None or stub)."""
    if op is None:
        return
    for key, value in kwargs.items():
        try:
            setattr(op, key, value)
        except (AttributeError, TypeError):
            pass


def get_bounds_in_space(obj, space_matrix):
    """
    Calculates the min/max bounds of an object's vertices within a given coordinate space.
    'space_matrix' is the world matrix of the coordinate space (e.g., target.matrix_world).
    Returns (min_bound, max_bound) in that space's local coordinates.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    try:
        mesh_eval = obj_eval.to_mesh()
    except RuntimeError:
        # Objects like EMPTY do not provide geometry data.
        zero = Vector((0, 0, 0))
        return (zero, zero)

    if not mesh_eval.vertices:
        obj_eval.to_mesh_clear()
        return (Vector((0,0,0)), Vector((0,0,0)))

    transform_matrix = space_matrix.inverted() @ obj_eval.matrix_world

    coords = [transform_matrix @ v.co for v in mesh_eval.vertices]
    obj_eval.to_mesh_clear()

    min_bound = Vector((min(v.x for v in coords), min(v.y for v in coords), min(v.z for v in coords)))
    max_bound = Vector((max(v.x for v in coords), max(v.y for v in coords), max(v.z for v in coords)))
    
    return (min_bound, max_bound)

def get_bounds_data(obj, point_type='CENTER', space='LOCAL'):
    """
    Calculates critical points based on local or world space bounding boxes.
    """
    bpy.context.view_layer.update()

    if point_type == 'PIVOT':
        return obj.matrix_world.to_translation()

    if space == 'LOCAL':
        local_coords = [Vector(v) for v in obj.bound_box]
        l_min = Vector((min(v.x for v in local_coords), min(v.y for v in local_coords), min(v.z for v in local_coords)))
        l_max = Vector((max(v.x for v in local_coords), max(v.y for v in local_coords), max(v.z for v in local_coords)))
        
        if point_type == 'MIN': target_local = l_min
        elif point_type == 'MAX': target_local = l_max
        else: target_local = (l_min + l_max) / 2
        
        return obj.matrix_world @ target_local

    else:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        try:
            mesh_eval = obj_eval.to_mesh()
        except RuntimeError:
            # Non-geometry objects (e.g. EMPTY) should align by pivot location.
            return obj.matrix_world.to_translation()
        
        verts_count = len(mesh_eval.vertices)
        if verts_count == 0:
            obj_eval.to_mesh_clear()
            return obj.matrix_world.to_translation()

        coords = np.empty(verts_count * 3, dtype=np.float32)
        mesh_eval.vertices.foreach_get("co", coords)
        coords.shape = (verts_count, 3)
        
        matrix = np.array(obj_eval.matrix_world)
        world_coords = np.dot(coords, matrix[:3, :3].T) + matrix[:3, 3]
        
        w_min = world_coords.min(axis=0)
        w_max = world_coords.max(axis=0)
        
        obj_eval.to_mesh_clear()

        if point_type == 'MIN': return Vector(w_min)
        if point_type == 'MAX': return Vector(w_max)
        return Vector((w_min + w_max) / 2)


def bbox_world_axis_interval(obj, axis_dir):
    """
    Min/max scalar projection of the object's evaluated mesh bounds onto axis_dir (world space).
    Matches get_bounds_data(WORLD) geometry (evaluated mesh + matrix_world), so scale and
    modifiers are included. Falls back to bound_box @ matrix_world for non-mesh objects.
    """
    axis_dir = axis_dir.normalized()
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    try:
        mesh_eval = obj_eval.to_mesh()
    except RuntimeError:
        mw = obj.matrix_world
        dots = [(mw @ Vector(corner)) @ axis_dir for corner in obj.bound_box]
        return min(dots), max(dots)

    verts_count = len(mesh_eval.vertices)
    if verts_count == 0:
        obj_eval.to_mesh_clear()
        mw = obj.matrix_world
        dots = [(mw @ Vector(corner)) @ axis_dir for corner in obj.bound_box]
        return min(dots), max(dots)

    coords = np.empty(verts_count * 3, dtype=np.float32)
    mesh_eval.vertices.foreach_get("co", coords)
    coords.shape = (verts_count, 3)
    matrix = np.array(obj_eval.matrix_world)
    world_coords = np.dot(coords, matrix[:3, :3].T) + matrix[:3, 3]
    ax = np.array((axis_dir.x, axis_dir.y, axis_dir.z), dtype=np.float64)
    dots = world_coords @ ax
    mn = float(dots.min())
    mx = float(dots.max())
    obj_eval.to_mesh_clear()
    return mn, mx


def _world_aabb_from_bound_box_world(mw, bound_box) -> tuple[Vector, Vector]:
    corners = [mw @ Vector(c) for c in bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return (
        Vector((min(xs), min(ys), min(zs))),
        Vector((max(xs), max(ys), max(zs))),
    )


def world_aabb_evaluated_bounds(obj) -> tuple[Vector, Vector]:
    """
    World-space AABB corners (min, max) for evaluated geometry.
    Matches the vertex set implied by bbox_world_axis_interval / gap distribution.
    """
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    try:
        mesh_eval = obj_eval.to_mesh()
    except RuntimeError:
        return _world_aabb_from_bound_box_world(obj.matrix_world, obj.bound_box)

    verts_count = len(mesh_eval.vertices)
    if verts_count == 0:
        obj_eval.to_mesh_clear()
        return _world_aabb_from_bound_box_world(obj.matrix_world, obj.bound_box)

    coords = np.empty(verts_count * 3, dtype=np.float32)
    mesh_eval.vertices.foreach_get("co", coords)
    coords.shape = (verts_count, 3)
    matrix = np.array(obj_eval.matrix_world)
    world_coords = np.dot(coords, matrix[:3, :3].T) + matrix[:3, 3]
    wm = world_coords.min(axis=0)
    wx = world_coords.max(axis=0)
    obj_eval.to_mesh_clear()
    return (
        Vector((float(wm[0]), float(wm[1]), float(wm[2]))),
        Vector((float(wx[0]), float(wx[1]), float(wx[2]))),
    )


def eight_corners_world_aabb(mn: Vector, mx: Vector) -> list[Vector]:
    """World-space axis-aligned box: eight corners (same winding as gap overlay)."""
    return [
        Vector((mn.x, mn.y, mn.z)),
        Vector((mx.x, mn.y, mn.z)),
        Vector((mx.x, mx.y, mn.z)),
        Vector((mn.x, mx.y, mn.z)),
        Vector((mn.x, mn.y, mx.z)),
        Vector((mx.x, mn.y, mx.z)),
        Vector((mx.x, mx.y, mx.z)),
        Vector((mn.x, mx.y, mx.z)),
    ]


def world_aabb_evaluated_corner_vectors(obj) -> list[Vector]:
    """Evaluated mesh world AABB as eight world corners (for viewport wire)."""
    mn, mx = world_aabb_evaluated_bounds(obj)
    return eight_corners_world_aabb(mn, mx)


def _obb_world_corners_from_active_local_minmax(mw_active, mn_l: Vector, mx_l: Vector) -> list[Vector]:
    loc = eight_corners_world_aabb(mn_l, mx_l)
    return [mw_active @ c for c in loc]


def _points_minmax_in_active_local(inv_active, world_xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """world_xyz: (N,3) → min/max per axis in active local space."""
    n = world_xyz.shape[0]
    if n == 0:
        z = np.zeros(3, dtype=np.float64)
        return z.copy(), z.copy()
    inv = np.array(inv_active, dtype=np.float64)
    ones = np.ones((n, 1), dtype=np.float64)
    hw = np.hstack([world_xyz.astype(np.float64), ones])
    loc_h = inv @ hw.T
    loc = loc_h[:3, :].T
    return loc.min(axis=0), loc.max(axis=0)


def world_obb_evaluated_corners_wrt_active(active, obj) -> list[Vector]:
    """
    Eight world corners of the evaluated mesh bounds, axis-aligned in *active* local space
    (edges parallel to active local X/Y/Z). Matches LOCAL_* distribute axis frame.
    """
    bpy.context.view_layer.update()
    inv_a = active.matrix_world.inverted()
    mw_a = active.matrix_world

    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    try:
        mesh_eval = obj_eval.to_mesh()
    except RuntimeError:
        corners_w = np.array([[*(obj.matrix_world @ Vector(c))] for c in obj.bound_box], dtype=np.float64)
        lmin, lmax = _points_minmax_in_active_local(inv_a, corners_w)
        return _obb_world_corners_from_active_local_minmax(
            mw_a,
            Vector((float(lmin[0]), float(lmin[1]), float(lmin[2]))),
            Vector((float(lmax[0]), float(lmax[1]), float(lmax[2]))),
        )

    verts_count = len(mesh_eval.vertices)
    if verts_count == 0:
        obj_eval.to_mesh_clear()
        corners_w = np.array([[*(obj.matrix_world @ Vector(c))] for c in obj.bound_box], dtype=np.float64)
        lmin, lmax = _points_minmax_in_active_local(inv_a, corners_w)
        return _obb_world_corners_from_active_local_minmax(
            mw_a,
            Vector((float(lmin[0]), float(lmin[1]), float(lmin[2]))),
            Vector((float(lmax[0]), float(lmax[1]), float(lmax[2]))),
        )

    coords = np.empty(verts_count * 3, dtype=np.float32)
    mesh_eval.vertices.foreach_get("co", coords)
    coords.shape = (verts_count, 3)
    matrix = np.array(obj_eval.matrix_world)
    world_coords = np.dot(coords, matrix[:3, :3].T) + matrix[:3, 3]
    obj_eval.to_mesh_clear()

    lmin, lmax = _points_minmax_in_active_local(inv_a, world_coords)
    return _obb_world_corners_from_active_local_minmax(
        mw_a,
        Vector((float(lmin[0]), float(lmin[1]), float(lmin[2]))),
        Vector((float(lmax[0]), float(lmax[1]), float(lmax[2]))),
    )


def apply_align_move(obj, delta_world):
    """Applies movement directly to the global matrix."""
    obj.matrix_world.translation += delta_world
    bpy.context.view_layer.update()

unit_suffixes = {
    'NONE': '',
    'METERS': 'm',
    'CENTIMETERS': 'cm',
    'MILLIMETERS': 'mm',
    'MICROMETERS': 'μm',
    'KILOMETERS': 'km',
    'MILES': 'mi',
    'FEET': 'ft',
    'INCHES': '"',
    'THOU': 'thou',
}

def get_unit_scale(context):
    """
    Meters per Blender Unit (Scene.unit_settings.scale_length).
    Real-world meters = length_in_BU * scale_length.
    """
    return context.scene.unit_settings.scale_length


_LEN_UNIT_METERS = {
    'METERS': 1.0,
    'CENTIMETERS': 0.01,
    'MILLIMETERS': 0.001,
    'MICROMETERS': 1e-6,
    'DECIMETERS': 0.1,
    'DEKAMETERS': 10.0,
    'HECTOMETERS': 100.0,
    'KILOMETERS': 1000.0,
    'MILES': 1609.344,
    'FEET': 0.3048,
    'YARDS': 0.9144,
    'INCHES': 0.0254,
    'THOU': 0.0254 / 1000.0,
}


def _length_unit_identifier(us):
    """Stable string RNA identifier for length_unit (handles int enum indices)."""
    lu = getattr(us, 'length_unit', None)
    if isinstance(lu, int):
        try:
            prop = us.bl_rna.properties['length_unit']
            items = prop.enum_items
            if 0 <= lu < len(items):
                return items[lu].identifier
        except (AttributeError, KeyError, IndexError, TypeError):
            pass
    if lu is None:
        return 'DEFAULT'
    return str(lu)


def _length_unit_meters_per_display_step(length_unit_key):
    """Meters represented by one increment of the given length_unit (Metric/Imperial)."""
    return _LEN_UNIT_METERS.get(length_unit_key)


def _effective_length_unit_key(us):
    """
    Map DEFAULT / ADAPTIVE (and unknowns) to a fixed unit key we can convert.
    ADAPTIVE cannot match Blender exactly with one scalar; meters is a stable fallback.
    """
    key = _length_unit_identifier(us)
    sys = getattr(us, 'system', 'NONE')
    if sys == 'NONE':
        return None
    if key == 'DEFAULT':
        return 'METERS' if sys == 'METRIC' else 'FEET'
    if key == 'ADAPTIVE':
        return 'METERS'
    return key


def length_bu_to_display_multiplier(context):
    """
    Multiply a length in Blender Units (mesh space, modifiers, etc.) to match the number
    Blender shows for lengths - same idea as the transform panel / scene units.
    """
    try:
        scene = getattr(context, 'scene', None)
        if scene is None:
            return 1.0
        us = scene.unit_settings
        if getattr(us, 'system', 'NONE') == 'NONE':
            return 1.0

        eff = _effective_length_unit_key(us)
        if eff is None:
            return 1.0
        base = _length_unit_meters_per_display_step(eff)
        if base is None or base == 0.0:
            return 1.0

        sl = float(getattr(us, 'scale_length', 1.0) or 0.0)
        if sl <= 0.0:
            sl = 1.0
        return sl / base
    except Exception:
        return 1.0


def display_length_to_bu_multiplier(context):
    """Multiply a typed or UI length (current scene unit) into Blender Units."""
    try:
        scene = getattr(context, 'scene', None)
        if scene is None:
            return 1.0
        us = scene.unit_settings
        if getattr(us, 'system', 'NONE') == 'NONE':
            return 1.0

        eff = _effective_length_unit_key(us)
        if eff is None:
            return 1.0
        base = _length_unit_meters_per_display_step(eff)
        if base is None or base == 0.0:
            return 1.0

        sl = float(getattr(us, 'scale_length', 1.0) or 0.0)
        if sl <= 0.0:
            sl = 1.0
        return base / sl
    except Exception:
        return 1.0

def find_farthest_vertices(verts):
    """
    Finds the two most distant vertices from a list of bmesh vertices.
    Returns a tuple (v1, v2).
    """
    if len(verts) < 2:
        return None, None

    v_a, v_b = None, None
    max_dist_sq = -1.0

    for i in range(len(verts)):
        for j in range(i + 1, len(verts)):
            dist_sq = (verts[i].co - verts[j].co).length_squared
            if dist_sq > max_dist_sq:
                max_dist_sq = dist_sq
                v_a, v_b = verts[i], verts[j]
    
    return v_a, v_b

def find_layer_collection(layer_coll, target_coll):
    """Recursively find a LayerCollection wrapping target_coll."""
    if layer_coll.collection == target_coll:
        return layer_coll
    for child in layer_coll.children:
        found = find_layer_collection(child, target_coll)
        if found:
            return found
    return None


def bbox_helpers_collection_name(scene):
    """Per-scene collection name used by BBox helper cages (see get_or_create_collection)."""
    return _per_scene_helpers_collection_name(scene, "bbox_helpers")


def draw_hidden_coll_toggle(layout, context, coll_name, text, icon='HIDE_ON'):
    """Draw a toggle button for a hidden auxiliary collection's View Layer exclude state."""
    coll = bpy.data.collections.get(coll_name)
    if coll is not None:
        layer_coll = find_layer_collection(context.view_layer.layer_collection, coll)
        if layer_coll is not None:
            layout.prop(layer_coll, "exclude", text=text, toggle=True, icon=icon)
            return
    op = layout.operator("alec.hidden_collection_visibility", text=text, icon=icon)
    op.coll_name = coll_name
    op.action = 'TOGGLE'


def draw_bbox_helpers_coll_toggle(layout, context, text="BBox Layer", icon='MESH_CUBE'):
    """Toggle View Layer exclude for the scene's bbox_helpers collection."""
    coll = bpy.data.collections.get(bbox_helpers_collection_name(context.scene))
    if coll is not None:
        layer_coll = find_layer_collection(context.view_layer.layer_collection, coll)
        if layer_coll is not None:
            layout.prop(layer_coll, "exclude", text=text, toggle=True, icon=icon)
            return
    layout.operator("alec.toggle_bbox_helpers_collection", text=text, icon=icon)


def move_to_collection(obj, target_collection):
    source_collections = list(obj.users_collection)

    if target_collection in source_collections:
        for coll in source_collections:
            if coll != target_collection:
                coll.objects.unlink(obj)
    else:
        for coll in source_collections:
            coll.objects.unlink(obj)
        target_collection.objects.link(obj)

def collection_in_subtree(root, coll):
    if root == coll:
        return True
    for child in root.children:
        if collection_in_subtree(child, coll):
            return True
    return False


def _per_scene_helpers_collection_name(scene, coll_name):
    safe_scene = bpy.path.clean_name(scene.name) or "Scene"
    full = f"{coll_name}_{safe_scene}"
    if len(full) <= 63:
        return full
    short_hash = hashlib.sha1(scene.name.encode("utf-8")).hexdigest()[:12]
    full = f"{coll_name}_{short_hash}"
    return full[:63]


def get_or_create_collection(context, coll_name="bbox_helpers", color='COLOR_04', hide_render=True):
    scene = context.scene
    full_name = _per_scene_helpers_collection_name(scene, coll_name)

    if full_name not in bpy.data.collections:
        coll = bpy.data.collections.new(full_name)
        scene.collection.children.link(coll)
        coll.color_tag = color
        coll.hide_render = hide_render
    else:
        coll = bpy.data.collections[full_name]
        if not collection_in_subtree(scene.collection, coll):
            scene.collection.children.link(coll)

    return coll

def switch_to_modifier_tab(context):
    for area in context.screen.areas:
        if area.type == 'PROPERTIES':
            area.spaces[0].context = 'MODIFIER'

def apply_soft_falloff(bm, old_coords, moved_coords, radius, falloff_type='SMOOTH', world_mx=None, connected_only=False, connected_depth=0):
    """
    Proportional falloff for unselected vertices from moved vertices (KDTree distance queries).
    """
    if radius <= 0.0:
        return

    unselected_verts = [v for v in bm.verts if v not in moved_coords]
    if not unselected_verts:
        return

    if connected_only:
        visited = set(moved_coords.keys())
        valid_unselected = set()
        queue = collections.deque([(v, 0) for v in moved_coords.keys()])

        while queue:
            curr_v, depth = queue.popleft()
            
            if connected_depth > 0 and depth >= connected_depth:
                continue
                
            for edge in curr_v.link_edges:
                neighbor = edge.other_vert(curr_v)
                if neighbor not in visited:
                    visited.add(neighbor)
                    if neighbor not in moved_coords:
                        valid_unselected.add(neighbor)
                    queue.append((neighbor, depth + 1))
        
        unselected_verts = [v for v in unselected_verts if v in valid_unselected]
        if not unselected_verts:
            return

    moved_deltas = {}
    for v, new_co in moved_coords.items():
        old_co = old_coords[v]
        delta = new_co - old_co
        if delta.length_squared > 1e-8:
            moved_deltas[v] = delta

    if not moved_deltas:
        return

    size = len(moved_deltas)
    kd = mathutils.kdtree.KDTree(size)
    
    delta_list = []
    for i, (v, delta) in enumerate(moved_deltas.items()):
        co = old_coords[v]
        if world_mx:
            co = world_mx @ co
        kd.insert(co, i)
        delta_list.append(delta)
        
    kd.balance()

    for v_u in unselected_verts:
        u_old_co = old_coords[v_u]
        search_co = world_mx @ u_old_co if world_mx else u_old_co

        in_range = kd.find_range(search_co, radius)
        if not in_range:
            continue
            
        sum_delta = Vector((0, 0, 0))
        sum_weight = 0.0
        max_falloff = 0.0

        for (co, index, dist) in in_range:
            ratio = dist / radius
            if ratio >= 1.0:
                falloff = 0.0
            elif falloff_type == 'SPHERE':
                falloff = math.sqrt(max(0.0, 1.0 - ratio * ratio))
            elif falloff_type == 'ROOT':
                falloff = math.sqrt(max(0.0, 1.0 - ratio))
            elif falloff_type == 'LINEAR':
                falloff = 1.0 - ratio
            elif falloff_type == 'SHARP':
                falloff = (1.0 - ratio) ** 2
            else: # SMOOTH
                falloff = (1.0 - ratio * ratio) ** 2
            
            sum_delta += delta_list[index] * falloff
            sum_weight += falloff
            if falloff > max_falloff:
                max_falloff = falloff
        
        if sum_weight > 0:
            blended_delta = sum_delta / sum_weight
            v_u.co = u_old_co + blended_delta * max_falloff


# ---------------------------------------------------------------------------
# Redraw helpers
# ---------------------------------------------------------------------------

def tag_view3d_redraw(context) -> None:
    """Redraw all View3D areas in the current screen (use inside operators/modals)."""
    if context is None:
        return
    screen = getattr(context, 'screen', None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def tag_view3d_redraw_all_windows() -> None:
    """Redraw all View3D areas across all windows (use from background handlers/timers)."""
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


# ---------------------------------------------------------------------------
# Object geometry helpers  (moved from operators/camera_tools.py)
# ---------------------------------------------------------------------------

def empty_world_location_on_camera_axis(cam, world_point: Vector) -> Vector:
    """Point on camera view axis ∩ plane ⟂ axis through object (foot of O onto axis)."""
    mw = cam.matrix_world
    c = mw.translation
    f = (mw.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    o = world_point.copy()
    t = (o - c).dot(f)
    if t <= 1e-6:
        return o
    return c + f * t


def object_bbox_center_world(obj) -> Vector:
    """World-space center of the object's axis-aligned bounding box (local bound_box)."""
    mw = obj.matrix_world
    acc = Vector((0.0, 0.0, 0.0))
    for corner in obj.bound_box:
        acc += mw @ Vector(corner)
    return acc * (1.0 / 8.0)