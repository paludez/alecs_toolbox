from mathutils import Vector
import bpy

def get_or_create_collection(context, coll_name="BBox_Helpers", color='COLOR_04'):
    """Asigură existența unei colecții organizate pentru helperi."""
    if coll_name not in bpy.data.collections:
        bbox_coll = bpy.data.collections.new(coll_name)
        context.scene.collection.children.link(bbox_coll)
        # Setează culoarea colecției în Outliner (COLOR_03 este verde)
        bbox_coll.color_tag = color
        bbox_coll.hide_render = True
    else:
        bbox_coll = bpy.data.collections[coll_name]
    return bbox_coll

def setup_bbox_visibility(bbox, color=(0.0, 1.0, 0.2, 1.0)):
    """Configurează aspectul de tip 'Green Ghost' pentru BBox."""
    # Afișare tip Wire
    bbox.display_type = 'WIRE'
    bbox.color = color
    # Setări Randare
    bbox.hide_render = True
    bbox.visible_camera = False
    bbox.visible_shadow = False
    bbox.visible_diffuse = False
    bbox.visible_glossy = False

def move_to_collection(obj, target_collection):
    """Mută obiectul în colecția țintă, eliminându-l din celelalte."""
    for coll in obj.users_collection:
        coll.objects.unlink(obj)
    target_collection.objects.link(obj)

def create_bbox(context, mode='LOCAL'):
    selected_count = len(context.selected_objects)
    active = context.active_object
    if not active:
        return None

    # Masurare prin duplicat temporar
    bpy.ops.object.duplicate()
    temp_obj = context.active_object
    bpy.ops.object.convert(target='MESH')

    if selected_count > 1:
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=True)
        bpy.ops.object.join()

    if mode == 'WORLD':
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    
    dims = temp_obj.dimensions.copy()
    center_world = temp_obj.matrix_world.translation.copy()
    
    bpy.data.objects.remove(temp_obj, do_unlink=True)

    # --- AICI ERA PROBLEMA (am lasat doar o instanta) ---
    bpy.ops.mesh.primitive_cube_add(size=1)
    bbox = context.active_object
    bbox.name = f"{active.name}_bbox"
    
    if mode == 'LOCAL':
        if selected_count == 1:
            bbox.matrix_world = active.matrix_world.copy()
            bbox.dimensions = dims
        else:
            bbox.rotation_euler = active.matrix_world.to_euler()
            bbox.location = center_world
            bbox.dimensions = dims
    else:
        bbox.location = center_world
        bbox.dimensions = dims

    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    helpers_coll = get_or_create_collection(context)
    move_to_collection(bbox, helpers_coll)
    setup_bbox_visibility(bbox)

    # Parenting (Keep Transform)
    if selected_count == 1:
        bbox.parent = active
        bbox.matrix_parent_inverse = active.matrix_world.inverted()

    bpy.ops.object.select_all(action='DESELECT')
    active.select_set(True)
    context.view_layer.objects.active = active
    return bbox

def set_shading_to_object(context):
    """Schimba Wireframe Color Type pe OBJECT daca e nevoie."""
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    if space.shading.wireframe_color_type != 'OBJECT':
                        space.shading.wireframe_color_type = 'OBJECT'

def create_offset_bbox(bbox, offset=0.1):
    if not bbox:
        return None

    bpy.ops.object.select_all(action='DESELECT')
    bbox.select_set(True)
    bpy.context.view_layer.objects.active = bbox
    
    bpy.ops.object.duplicate()
    offset_bbox = bpy.context.active_object
    
    # Nume curat
    base_name = bbox.name.replace("_bbox", "")
    offset_bbox.name = f"{base_name}_bbox_of"
    
    # Umflam dimensiunile
    offset_bbox.dimensions = bbox.dimensions + Vector((offset * 2, offset * 2, offset * 2))
    
    # Aplicam scala ca sa ramana 1,1,1
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Organizare
    helpers_coll = get_or_create_collection(bpy.context)
    move_to_collection(offset_bbox, helpers_coll)
    setup_bbox_visibility(offset_bbox)

    # Copiem parenting-ul de la sursa
    if bbox.parent:
        offset_bbox.parent = bbox.parent
        offset_bbox.matrix_parent_inverse = bbox.matrix_parent_inverse.copy()
    
    return offset_bbox