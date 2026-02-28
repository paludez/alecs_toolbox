import bpy
from mathutils import Vector
from .utils import get_bounds_data

def group_objects(context):
    objects = context.selected_objects
    if not objects:
        return

    min_co = Vector((float('inf'), float('inf'), float('inf')))
    max_co = Vector((float('-inf'), float('-inf'), float('-inf')))

    for obj in objects:
        if obj.type == 'MESH':
            w_min = get_bounds_data(obj, 'MIN', space='WORLD')
            w_max = get_bounds_data(obj, 'MAX', space='WORLD')
        else:
            w_min = w_max = obj.matrix_world.translation

        for i in range(3):
            min_co[i] = min(min_co[i], w_min[i])
            max_co[i] = max(max_co[i], w_max[i])

    if min_co.x == float('inf'):
        center = sum((o.matrix_world.translation for o in objects), Vector()) / len(objects)
    else:
        center = (min_co + max_co) / 2

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=center)
    empty = context.active_object
    empty.name = "Group"

    for obj in objects:
        obj.parent = empty
        obj.matrix_parent_inverse = empty.matrix_world.inverted()

    bpy.ops.object.select_all(action='DESELECT')
    empty.select_set(True)
    context.view_layer.objects.active = empty

def group_active(context):
    selected = context.selected_objects
    active = context.active_object
    if not active:
        return

    # Calculate world space bounds center
    corners = [Vector(c) for c in active.bound_box]
    center_local = (Vector((min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners))) +
                    Vector((max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners)))) / 2
    center_world = active.matrix_world @ center_local

    # Create Empty
    bpy.ops.object.empty_add(type='ARROWS', location=center_world)
    empty = context.active_object
    empty.name = f"Group_{active.name}"
    empty.rotation_euler = active.rotation_euler.copy()
    
    # Update matrix_world
    context.view_layer.update()

    # Parent selected to Empty
    for obj in selected:
        obj.parent = empty
        obj.matrix_parent_inverse = empty.matrix_world.inverted()

    bpy.ops.object.select_all(action='DESELECT')
    empty.select_set(True)
    context.view_layer.objects.active = empty

def ungroup_objects(context):
    selected = context.selected_objects
    if not selected:
        return

    parents_to_delete = set()

    # Find parent Empties
    for obj in selected:
        if obj.parent and obj.parent.type == 'EMPTY':
            parents_to_delete.add(obj.parent)
        elif obj.type == 'EMPTY':
            # Handle direct Empty selection
            parents_to_delete.add(obj)

    # Process groups
    for empty in parents_to_delete:
        children = empty.children
        for child in children:
            # Preserve global transform
            matrix_copy = child.matrix_world.copy()
            child.parent = None
            child.matrix_world = matrix_copy
        
        # Remove Empty
        bpy.data.objects.remove(empty, do_unlink=True)

def manage_grouping(context, action):
    if action == 'GROUP':
        group_objects(context)
    elif action == 'GROUP_ACTIVE':
        group_active(context)
    elif action == 'UNGROUP':
        ungroup_objects(context)