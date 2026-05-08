import bpy
from mathutils import Vector, Matrix
from .utils import move_to_collection, get_or_create_collection

# Viewport wire object-color (RGBA) for bbox helper cages
BBOX_HELPER_COLOR = (0.0, 1.0, 0.2, 1.0)
# #00E7FFFF — padded cage (viewport object color RGBA)
BBOX_HELPER_COLOR_PADDED = (0 / 255, 231 / 255, 255 / 255, 1.0)


def _apply_bbox_finish(
    context,
    bbox,
    apply_extras,
    *,
    anchor_obj,
    mesh_objects_restore,
    restore_active,
    wire_color,
):
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    tint = wire_color if wire_color is not None else BBOX_HELPER_COLOR
    if apply_extras:
        setup_bbox_visibility(bbox, color=tint)
        set_shading_to_object(context)

    if apply_extras:
        helpers_coll = get_or_create_collection(context)
        move_to_collection(bbox, helpers_coll)
    else:
        move_to_same_collections(bbox, anchor_obj)

    bpy.ops.object.select_all(action="DESELECT")
    for ob in mesh_objects_restore:
        if ob.name in bpy.data.objects:
            bpy.data.objects[ob.name].select_set(True)
    if restore_active and restore_active.name in bpy.data.objects:
        context.view_layer.objects.active = bpy.data.objects[restore_active.name]

    return bbox

def setup_bbox_visibility(bbox, color=BBOX_HELPER_COLOR):
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


def _pad_min_max(mn: Vector, mx: Vector, margin: float):
    """Expand bounds by margin along each axis; avoid degenerate size."""
    pad = Vector((margin, margin, margin))
    out_min = mn - pad
    out_max = mx + pad
    extent = out_max - out_min
    eps = 1e-7
    for i in range(3):
        if extent[i] < eps:
            c = (out_max[i] + out_min[i]) * 0.5
            out_min[i] = c - eps * 0.5
            out_max[i] = c + eps * 0.5
    return out_min, out_max


def create_bbox(
    context,
    mode='LOCAL',
    apply_extras=True,
    margin=0.0,
    name_suffix='',
    wire_color=None,
):
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
        l_min, l_max = _pad_min_max(l_min, l_max, margin)

        center_local = (l_min + l_max) / 2
        size = l_max - l_min

        bpy.ops.mesh.primitive_cube_add(size=1.0)
        bbox = context.active_object
        bbox.name = f"{active.name}_bbox{name_suffix}"

        local_mat = Matrix.LocRotScale(center_local, None, size)
        bbox.matrix_world = active.matrix_world @ local_mat

    else:  # WORLD
        w_min = Vector((min(v.x for v in all_coords_world), min(v.y for v in all_coords_world), min(v.z for v in all_coords_world)))
        w_max = Vector((max(v.x for v in all_coords_world), max(v.y for v in all_coords_world), max(v.z for v in all_coords_world)))
        w_min, w_max = _pad_min_max(w_min, w_max, margin)

        center_world = (w_min + w_max) / 2
        size_world = w_max - w_min

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=center_world)
        bbox = context.active_object
        bbox.name = f"{active.name}_bbox_w{name_suffix}"
        bbox.dimensions = size_world

    return _apply_bbox_finish(
        context,
        bbox,
        apply_extras,
        anchor_obj=active,
        mesh_objects_restore=selected_meshes,
        restore_active=active,
        wire_color=wire_color,
    )


def create_bbox_for_mesh_object(
    context,
    obj,
    mode,
    apply_extras=True,
    margin=0.0,
    name_suffix="",
    wire_color=None,
    *,
    restore_meshes,
    restore_active,
):
    """
    One cage for a single evaluated mesh object. LOCAL = obj's local axes / mesh space bounds;
    WORLD = world-axis AABB from that object's geometry.
    """
    if obj is None or obj.type != "MESH":
        return None

    depsgraph = context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh = obj_eval.to_mesh()
    if not mesh.vertices:
        obj_eval.to_mesh_clear()
        return None

    mw = obj.matrix_world
    verts_loc = []
    verts_world = []
    for rv in mesh.vertices:
        lc = rv.co.copy()
        verts_loc.append(lc)
        verts_world.append(mw @ lc)

    obj_eval.to_mesh_clear()

    if mode == "LOCAL":
        l_min = Vector(
            (
                min(v.x for v in verts_loc),
                min(v.y for v in verts_loc),
                min(v.z for v in verts_loc),
            )
        )
        l_max = Vector(
            (
                max(v.x for v in verts_loc),
                max(v.y for v in verts_loc),
                max(v.z for v in verts_loc),
            )
        )
        l_min, l_max = _pad_min_max(l_min, l_max, margin)
        center_local = (l_min + l_max) / 2
        size = l_max - l_min

        bpy.ops.mesh.primitive_cube_add(size=1.0)
        bbox = context.active_object
        bbox.name = f"{obj.name}_bbox{name_suffix}"
        bbox.matrix_world = mw @ Matrix.LocRotScale(center_local, None, size)
    else:
        w_min = Vector(
            (
                min(v.x for v in verts_world),
                min(v.y for v in verts_world),
                min(v.z for v in verts_world),
            )
        )
        w_max = Vector(
            (
                max(v.x for v in verts_world),
                max(v.y for v in verts_world),
                max(v.z for v in verts_world),
            )
        )
        w_min, w_max = _pad_min_max(w_min, w_max, margin)

        center_world = (w_min + w_max) / 2
        size_world = w_max - w_min

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=center_world)
        bbox = context.active_object
        bbox.name = f"{obj.name}_bbox_w{name_suffix}"
        bbox.dimensions = size_world

    return _apply_bbox_finish(
        context,
        bbox,
        apply_extras,
        anchor_obj=obj,
        mesh_objects_restore=restore_meshes,
        restore_active=restore_active,
        wire_color=wire_color,
    )


def iter_bbox_helpers_for_selected(
    context,
    *,
    mode,
    apply_extras,
    pad,
    dual,
):
    """Yield cages for each selected mesh (tight, then optionally padded helper). Names follow per-object naming."""
    selected_meshes = [o for o in context.selected_objects if o.type == "MESH"]
    active = context.active_object
    if not selected_meshes or active is None or active.type != "MESH":
        return

    eps = 1e-20
    for mesh_obj in selected_meshes:
        if dual and abs(pad) > eps:
            t = create_bbox_for_mesh_object(
                context,
                mesh_obj,
                mode,
                apply_extras=apply_extras,
                margin=0.0,
                name_suffix="",
                restore_meshes=selected_meshes,
                restore_active=active,
            )
            if t is not None:
                yield t
            o = create_bbox_for_mesh_object(
                context,
                mesh_obj,
                mode,
                apply_extras=apply_extras,
                margin=pad,
                name_suffix="_p",
                wire_color=BBOX_HELPER_COLOR_PADDED,
                restore_meshes=selected_meshes,
                restore_active=active,
            )
            if o is not None:
                yield o
        else:
            b = create_bbox_for_mesh_object(
                context,
                mesh_obj,
                mode,
                apply_extras=apply_extras,
                margin=pad,
                name_suffix="",
                restore_meshes=selected_meshes,
                restore_active=active,
            )
            if b is not None:
                yield b