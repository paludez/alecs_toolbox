import bpy
import numpy as np
from mathutils import Vector

def get_bounds_data(obj, point_type='CENTER', space='LOCAL'):
    """
    Calculează puncte critice. 
    space='LOCAL' -> Ca în 3ds Max (Centrul volumului propriu, transformat în lume).
    space='WORLD' -> Ca în pozele tale (Centrul cutiei aliniate la grid-ul global).
    """
    bpy.context.view_layer.update()

    if point_type == 'PIVOT':
        return obj.matrix_world.to_translation()

    if space == 'LOCAL':
        # --- LOGICA 3DS MAX ---
        # Folosim bound_box-ul local (cutia gri) care se rotește odată cu obiectul
        local_coords = [Vector(v) for v in obj.bound_box]
        l_min = Vector((min(v.x for v in local_coords), min(v.y for v in local_coords), min(v.z for v in local_coords)))
        l_max = Vector((max(v.x for v in local_coords), max(v.y for v in local_coords), max(v.z for v in local_coords)))
        
        if point_type == 'MIN': target_local = l_min
        elif point_type == 'MAX': target_local = l_max
        else: target_local = (l_min + l_max) / 2 # CENTER
        
        # Transformăm punctul local în locație World
        return obj.matrix_world @ target_local

    else:
        # --- LOGICA PIXEL-PERFECT (WORLD) ---
        # Metoda NumPy (0.45s) pe care am testat-o pe 8 mil vertecși
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
        return Vector((w_min + w_max) / 2) # CENTER

def apply_align_move(obj, delta_world):
    """Aplică mișcarea direct pe matricea de transformare globală."""
    obj.matrix_world.translation += delta_world
    bpy.context.view_layer.update()