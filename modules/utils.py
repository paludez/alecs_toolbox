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