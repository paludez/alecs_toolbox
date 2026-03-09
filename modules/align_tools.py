import bpy
from mathutils import Vector
from .utils import get_bounds_data, apply_align_move, get_bounds_in_space

def align_position(source, target, x=True, y=True, z=True, 
                   source_point='PIVOT', target_point='PIVOT', use_active_orient=False,
                   offset_x=0.0, offset_y=0.0, offset_z=0.0):
    
    if use_active_orient:
        # Get bounds of both objects in the target's local space
        s_min_local, s_max_local = get_bounds_in_space(source, target.matrix_world)
        t_min_local, t_max_local = get_bounds_in_space(target, target.matrix_world)

        # Determine source point in target's local space
        if source_point == 'PIVOT':
            source_pt_local = target.matrix_world.inverted() @ source.matrix_world.translation
        elif source_point == 'MIN':
            source_pt_local = s_min_local
        elif source_point == 'MAX':
            source_pt_local = s_max_local
        else: # CENTER
            source_pt_local = (s_min_local + s_max_local) / 2

        # Determine target point in target's local space
        if target_point == 'PIVOT':
            # Target pivot in its own local space is origin
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
        
        # Transform delta from target's local space to world space for movement
        delta_world = target.matrix_world.to_3x3() @ delta_local
    else:
        # World aligned bounding box (AABB)
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

def align_orientation(source, target, x=True, y=True, z=True):
    src_euler = source.rotation_euler.copy()
    tgt_euler = target.rotation_euler.copy()
    
    if x:
        src_euler.x = tgt_euler.x
    if y:
        src_euler.y = tgt_euler.y
    if z:
        src_euler.z = tgt_euler.z
    
    source.rotation_euler = src_euler 
    
def match_scale(source, target, x=True, y=True, z=True):
    if x:
        source.scale.x = target.scale.x
    if y:
        source.scale.y = target.scale.y
    if z:
        source.scale.z = target.scale.z