import bpy
import numpy as np
from mathutils import Vector

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

def get_unit_scale(context):
    """
    Returns the appropriate scale factor to convert a scene unit value 
    to Blender's internal units (meters).
    """
    settings = context.scene.unit_settings
    
    if settings.system in {'METRIC', 'IMPERIAL'}:
        
        # Conversion factors to meters
        factors = {
            'METRIC': {
                'METERS': 1.0,
                'CENTIMETERS': 0.01,
                'MILLIMETERS': 0.001,
                'KILOMETERS': 1000.0,
                'MICROMETERS': 0.000001,
            },
            'IMPERIAL': {
                'FEET': 0.3048,
                'INCHES': 0.0254,
                'MILES': 1609.34,
                'THOU': 0.0000254,
            }
        }
        
        unit_system_factors = factors.get(settings.system)
        if unit_system_factors:
            factor = unit_system_factors.get(settings.length_unit, 1.0)
            return settings.scale_length * factor

    return settings.scale_length


def find_farthest_vertices(vertices):
    """
    Finds the two most distant vertices from a list of vertices.
    Returns a tuple (v_start, v_end), or (None, None) if not enough vertices.
    """
    if len(vertices) < 2:
        return None, None

    v_start, v_end = None, None
    max_dist_sq = -1.0
    
    for i in range(len(vertices)):
        for j in range(i + 1, len(vertices)):
            v_i = vertices[i]
            v_j = vertices[j]
            dist_sq = (v_i.co - v_j.co).length_squared
            if dist_sq > max_dist_sq:
                max_dist_sq = dist_sq
                v_start = v_i
                v_end = v_j
    
    return v_start, v_end
