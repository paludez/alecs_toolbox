import bpy
from mathutils import Vector
from .utils import get_bounds_data # <--- Importă noua funcție

#
def group_objects(context):
    objects = context.selected_objects
    if not objects:
        return

    # calculeaza AABB pentru toate obiectele selectate
    center = get_bounds_data(objects, 'CENTER')
    # creaza empty la centrul AABB
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=center)
    empty = context.active_object
    empty.name = "Group"

    # parenteaza toate obiectele la empty
    for obj in objects:
        obj.parent = empty
        obj.matrix_parent_inverse = empty.matrix_world.inverted()

    # reselecteaza empty
    bpy.ops.object.select_all(action='DESELECT')
    empty.select_set(True)
    context.view_layer.objects.active = empty

def group_active(context):
    selected = context.selected_objects
    active = context.active_object
    if not active:
        return

    # centrul bounds al activului in world space
    corners = [Vector(c) for c in active.bound_box]
    center_local = (Vector((min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners))) +
                    Vector((max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners)))) / 2
    center_world = active.matrix_world @ center_local

# creaza empty
    bpy.ops.object.empty_add(type='ARROWS', location=center_world)
    empty = context.active_object
    empty.name = f"Group_{active.name}"
    empty.rotation_euler = active.rotation_euler.copy()
    
    # forteaza update matrix_world inainte de parenting
    context.view_layer.update()

    # parenteaza toate obiectele selectate la empty
    for obj in selected:
        obj.parent = empty
        obj.matrix_parent_inverse = empty.matrix_world.inverted()

    bpy.ops.object.select_all(action='DESELECT')
    empty.select_set(True)
    context.view_layer.objects.active = empty

def ungroup_objects(context):
    empty = context.active_object
    bpy.ops.object.select_more()
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    bpy.data.objects.remove(empty, do_unlink=True)

