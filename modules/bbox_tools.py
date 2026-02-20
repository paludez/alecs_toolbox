import bpy
from mathutils import Vector, Matrix
import bmesh

def get_or_create_collection(context, coll_name="BBox_Helpers", color='COLOR_04'):
    if coll_name not in bpy.data.collections:
        bbox_coll = bpy.data.collections.new(coll_name)
        context.scene.collection.children.link(bbox_coll)
        bbox_coll.color_tag = color
        bbox_coll.hide_render = True
    else:
        bbox_coll = bpy.data.collections[coll_name]
    return bbox_coll

def setup_bbox_visibility(bbox, color=(0.0, 1.0, 0.2, 1.0)):
    bbox.display_type = 'WIRE'
    bbox.color = color
    bbox.hide_render = True
    bbox.visible_camera = False
    bbox.visible_shadow = False

def move_to_collection(obj, target_collection):
    for coll in obj.users_collection:
        coll.objects.unlink(obj)
    target_collection.objects.link(obj)

def set_shading_to_object(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.wireframe_color_type = 'OBJECT'

def create_bbox(context, mode='LOCAL'):
    selected_meshes = [o for o in context.selected_objects if o.type == 'MESH']
    active = context.active_object
    if not selected_meshes or not active: 
        return None

    depsgraph = context.evaluated_depsgraph_get()
    inv_matrix = active.matrix_world.inverted()
    
    all_coords_local = []
    all_coords_world = []

    # Colectăm vertecșii tuturor obiectelor selectate
    for obj in selected_meshes:
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()
        mat = obj.matrix_world
        
        for v in mesh.vertices:
            world_co = mat @ v.co
            all_coords_world.append(world_co)
            # Transformăm coordonatele în spațiul local al obiectului activ
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
    setup_bbox_visibility(bbox)
    set_shading_to_object(context)
    
    helpers_coll = get_or_create_collection(context)
    move_to_collection(bbox, helpers_coll)
    
    bpy.ops.object.select_all(action='DESELECT')
    for o in selected_meshes:
        o.select_set(True)
    context.view_layer.objects.active = active
    
    return bbox
def create_offset_bbox(obj, offset=0.1):
    if not obj or obj.type != 'MESH': return None

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.duplicate()
    new_obj = bpy.context.active_object
    
    bm = bmesh.new()
    bm.from_mesh(new_obj.data)
    for v in bm.verts:
        v.co += v.normal * offset
    bm.to_mesh(new_obj.data)
    bm.free()
    
    new_obj.name = f"{obj.name}_offset"
    
    # Setăm vizibilitatea pe Wire și culoarea pe Albastru
    setup_bbox_visibility(new_obj, color=(0.0, 0.5, 1.0, 1.0))
    set_shading_to_object(bpy.context)
    
    move_to_collection(new_obj, get_or_create_collection(bpy.context))
    return new_obj