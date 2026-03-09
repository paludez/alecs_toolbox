import bpy
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
    mesh_eval = obj_eval.to_mesh()

    if not mesh_eval.vertices:
        obj_eval.to_mesh_clear()
        # Return a zero vector if there are no vertices
        return (Vector((0,0,0)), Vector((0,0,0)))

    # Matrix to transform from obj's local space to the target space
    transform_matrix = space_matrix.inverted() @ obj_eval.matrix_world

    # Transform all vertices
    coords = [transform_matrix @ v.co for v in mesh_eval.vertices]
    obj_eval.to_mesh_clear()

    # Find min/max in the target space
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
        # Local bounding box (rotates with object)
        local_coords = [Vector(v) for v in obj.bound_box]
        l_min = Vector((min(v.x for v in local_coords), min(v.y for v in local_coords), min(v.z for v in local_coords)))
        l_max = Vector((max(v.x for v in local_coords), max(v.y for v in local_coords), max(v.z for v in local_coords)))
        
        if point_type == 'MIN': target_local = l_min
        elif point_type == 'MAX': target_local = l_max
        else: target_local = (l_min + l_max) / 2
        
        return obj.matrix_world @ target_local

    else:
        # World aligned bounding box (evaluated mesh)
        
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_eval = obj_eval.to_mesh()
        
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