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
    
    # Culoare obiect (Vizibilă dacă Shading -> Color e setat pe 'Object')
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

    # Logica de măsurare prin duplicat temporar
    bpy.ops.object.duplicate()
    bpy.ops.object.convert(target='MESH')

    if selected_count > 1:
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=True)
        bpy.ops.object.join()

    if mode == 'WORLD':
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    dims = context.active_object.dimensions.copy()
    center = context.active_object.location.copy()
    
    # Ștergem duplicatul temporar
    bpy.data.objects.remove(context.active_object, do_unlink=True)

    # Creăm BBox-ul final
    bpy.ops.mesh.primitive_cube_add(size=1)
    bbox = context.active_object
    
    # Denumire cerută: nume_bbox
    bbox.name = f"{active.name}_bbox"
    
    bbox.dimensions = dims
    bbox.location = center
    
    if mode == 'LOCAL':
        bbox.rotation_euler = active.rotation_euler.copy()

    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Organizare și Aspect
    helpers_coll = get_or_create_collection(context)
    move_to_collection(bbox, helpers_coll)
    setup_bbox_visibility(bbox)

    if selected_count == 1:
        bbox.parent = active
        bbox.matrix_parent_inverse = active.matrix_world.inverted()

    # Revenire la selecția originală
    bpy.ops.object.select_all(action='DESELECT')
    active.select_set(True)
    context.view_layer.objects.active = active
    return bbox

def create_offset_bbox(bbox, offset=0.1):
    bpy.ops.object.select_all(action='DESELECT')
    bbox.select_set(True)
    bpy.context.view_layer.objects.active = bbox
    bpy.ops.object.duplicate()
    
    offset_bbox = bpy.context.active_object
    
    # Denumire cerută: nume_bbox_of (fără dublări)
    base_name = bbox.name.replace("_bbox", "")
    offset_bbox.name = f"{base_name}_bbox_of"
    
    offset_bbox.dimensions = bbox.dimensions + Vector((offset * 2, offset * 2, offset * 2))
    
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Organizare și Aspect (Verde pentru ambele)
    helpers_coll = get_or_create_collection(bpy.context)
    move_to_collection(offset_bbox, helpers_coll)
    setup_bbox_visibility(offset_bbox)

    offset_bbox.parent = bbox.parent
    offset_bbox.matrix_parent_inverse = bbox.matrix_parent_inverse.copy()
    
    bpy.ops.object.select_all(action='DESELECT')
    return offset_bbox