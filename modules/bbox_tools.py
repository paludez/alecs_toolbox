import bpy
from mathutils import Vector, Matrix
import bmesh
from .utils import move_to_collection, get_or_create_collection

def setup_bbox_visibility(bbox, color=(0.0, 1.0, 0.2, 1.0)):
    bbox.display_type = 'WIRE'
    bbox.color = color
    bbox.hide_render = True
    bbox.visible_camera = False
    bbox.visible_shadow = False
    bbox.visible_diffuse = False
    bbox.visible_glossy = False
    bbox.visible_transmission = False
    bbox.visible_volume_scatter = False
    bbox.display.show_shadows = False

def set_shading_to_object(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.wireframe_color_type = 'OBJECT'


def move_to_same_collections(obj, source_obj):
    source_collections = list(source_obj.users_collection)
    if not source_collections:
        return

    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)

    for coll in source_collections:
        if obj.name not in coll.objects:
            coll.objects.link(obj)

def create_bbox(context, mode='LOCAL', apply_extras=True):
    selected_meshes = [o for o in context.selected_objects if o.type == 'MESH']
    active = context.active_object
    if not selected_meshes or not active: 
        return None

    depsgraph = context.evaluated_depsgraph_get()
    inv_matrix = active.matrix_world.inverted()
    
    all_coords_local = []
    all_coords_world = []

    for obj in selected_meshes:
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()
        mat = obj.matrix_world
        
        for v in mesh.vertices:
            world_co = mat @ v.co
            all_coords_world.append(world_co)
            all_coords_local.append(inv_matrix @ world_co)
            
        obj_eval.to_mesh_clear()

    if not all_coords_world: 
        return None

    if mode == 'LOCAL':
        l_min = Vector((min(v.x for v in all_coords_local), min(v.y for v in all_coords_local), min(v.z for v in all_coords_local)))
        l_max = Vector((max(v.x for v in all_coords_local), max(v.y for v in all_coords_local), max(v.z for v in all_coords_local)))
        
        center_local = (l_min + l_max) / 2
        size = l_max - l_min
        
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        bbox = context.active_object
        bbox.name = f"{active.name}_bbox"
        
        local_mat = Matrix.LocRotScale(center_local, None, size)
        bbox.matrix_world = active.matrix_world @ local_mat
        
    else: # WORLD
        w_min = Vector((min(v.x for v in all_coords_world), min(v.y for v in all_coords_world), min(v.z for v in all_coords_world)))
        w_max = Vector((max(v.x for v in all_coords_world), max(v.y for v in all_coords_world), max(v.z for v in all_coords_world)))
        
        center_world = (w_min + w_max) / 2
        size_world = w_max - w_min
        
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=center_world)
        bbox = context.active_object
        bbox.name = f"{active.name}_bbox_w"
        bbox.dimensions = size_world

    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if apply_extras:
        setup_bbox_visibility(bbox)
        set_shading_to_object(context)
    
    if apply_extras:
        helpers_coll = get_or_create_collection(context)
        move_to_collection(bbox, helpers_coll)
    else:
        move_to_same_collections(bbox, active)
    
    bpy.ops.object.select_all(action='DESELECT')
    for o in selected_meshes:
        o.select_set(True)
    context.view_layer.objects.active = active
    
    return bbox