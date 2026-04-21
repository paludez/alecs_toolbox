import bpy
import math
import hashlib
import collections
import mathutils
import numpy as np
from mathutils import Vector

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
    Returns the scale factor to convert from the current display unit to Blender's internal meters.
    e.g., if scene is in 'CM', returns 0.01.
    """
    return context.scene.unit_settings.scale_length

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

def draw_modal_status_bar(layout, items):
    """
    Draws a consistent status bar for modal operators.
    'items' is a list of tuples: (label, value, is_active_flag) or None for a separator.
    """
    row = layout.row(align=True)
    row.alignment = 'CENTER'
    
    for item in items:
        if item is None:
            row.separator(factor=2)
            continue
            
        label, value, *active = item
        is_active = active[0] if active else False
        
        sub_row = row.row(align=True)
        if is_active:
            sub_row.alert = True
        
        if label:
            sub_row.label(text=f"{label}:")
        sub_row.label(text=value)

def find_layer_collection(layer_coll, target_coll):
    """Recursively find a LayerCollection wrapping target_coll."""
    if layer_coll.collection == target_coll:
        return layer_coll
    for child in layer_coll.children:
        found = find_layer_collection(child, target_coll)
        if found:
            return found
    return None


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