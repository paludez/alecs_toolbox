import bpy
import numpy as np  # <--- ADAUGĂ ASTA LA ÎNCEPUT
from mathutils import Vector
from .utils import get_bounds_data, apply_align_move

def align_position(source, target, x=True, y=True, z=True, 
                   source_point='PIVOT', target_point='PIVOT'):
    
    # Folosim space='LOCAL' pentru a ignora "umflarea" BBox-ului la rotație
    source_world = get_bounds_data(source, source_point, space='LOCAL')
    target_world = get_bounds_data(target, target_point, space='LOCAL')
    
    delta_world = target_world - source_world
    
    if not x: delta_world.x = 0
    if not y: delta_world.y = 0
    if not z: delta_world.z = 0
    
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