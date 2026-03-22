"""
View3D sidebar (N) > Alec — Transform obiect (RNA) + selecție Edit Mesh (world, editabil).
"""

import bmesh
import bpy
from mathutils import Vector

_alec_syncing = False
_depsgraph_handler = None
# Panel.draw cannot write Scene RNA; cache selection signature per scene here.
_last_selection_sig_by_scene: dict[int, str] = {}
_sync_selection_timer_pending = False


def _deferred_sync_selection_props():
    """Run outside Panel.draw so writing Scene.alec_edit_selection is allowed."""
    global _sync_selection_timer_pending
    _sync_selection_timer_pending = False
    try:
        ctx = bpy.context
        if ctx.mode != "EDIT_MESH":
            return None
        obj = ctx.active_object
        if obj is None or obj.type != "MESH":
            return None
        props = getattr(ctx.scene, "alec_edit_selection", None)
        if props is None:
            return None
        _sync_selection_props_from_mesh(ctx, props)
    except Exception:
        pass
    return None


def _undo_push(context, message: str) -> None:
    try:
        bpy.ops.ed.undo_push(message=message)
    except Exception:
        pass


def _world_aabb_from_corners(corners_world: list[Vector]) -> tuple[Vector, Vector]:
    if not corners_world:
        return Vector(), Vector()
    xs = [c.x for c in corners_world]
    ys = [c.y for c in corners_world]
    zs = [c.z for c in corners_world]
    return (
        Vector((min(xs), min(ys), min(zs))),
        Vector((max(xs), max(ys), max(zs))),
    )


def _selected_vert_positions_world(context, obj, mesh) -> list[Vector]:
    bm = bmesh.from_edit_mesh(mesh)
    try:
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        verts: set = set()
        ts = context.tool_settings.mesh_select_mode
        if ts[0]:
            for v in bm.verts:
                if v.select:
                    verts.add(v)
        elif ts[1]:
            for e in bm.edges:
                if e.select:
                    verts.update(e.verts)
        else:
            for f in bm.faces:
                if f.select:
                    verts.update(f.verts)
        mat = obj.matrix_world
        return [(mat @ v.co).copy() for v in verts]
    finally:
        bm.free()


def _mean(vectors: list[Vector]) -> Vector | None:
    if not vectors:
        return None
    s = Vector((0.0, 0.0, 0.0))
    for v in vectors:
        s += v
    return s / len(vectors)


def _selection_vert_signature(context, obj, mesh) -> str:
    bm = bmesh.from_edit_mesh(mesh)
    try:
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        ts = context.tool_settings.mesh_select_mode
        idx: list = []
        if ts[0]:
            for v in bm.verts:
                if v.select:
                    idx.append(v.index)
        elif ts[1]:
            for e in bm.edges:
                if e.select:
                    for x in e.verts:
                        idx.append(x.index)
        else:
            for f in bm.faces:
                if f.select:
                    for x in f.verts:
                        idx.append(x.index)
        idx = sorted(set(idx))
        return f"{ts[0]}{ts[1]}{ts[2]}:" + ",".join(str(i) for i in idx)
    finally:
        bm.free()


def _iter_selected_bmverts(bm) -> list:
    ts = bpy.context.tool_settings.mesh_select_mode
    out = []
    if ts[0]:
        for v in bm.verts:
            if v.select:
                out.append(v)
    elif ts[1]:
        seen = set()
        for e in bm.edges:
            if e.select:
                for v in e.verts:
                    if v not in seen:
                        seen.add(v)
                        out.append(v)
    else:
        seen = set()
        for f in bm.faces:
            if f.select:
                for v in f.verts:
                    if v not in seen:
                        seen.add(v)
                        out.append(v)
    return out


def _apply_translation_world(context, obj, delta_w: Vector) -> None:
    if delta_w.length < 1e-12:
        return
    mesh = obj.data
    bm = bmesh.from_edit_mesh(mesh)
    try:
        bm.verts.ensure_lookup_table()
        mat_w = obj.matrix_world
        mat_inv = mat_w.inverted()
        for v in _iter_selected_bmverts(bm):
            wco = mat_w @ v.co
            wco_new = wco + delta_w
            v.co = mat_inv @ wco_new
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    finally:
        bm.free()


def _apply_resize_world_aabb(context, obj, center_w: Vector, old_dims: Vector, new_dims: Vector) -> None:
    sx = sy = sz = 1.0
    if old_dims.x > 1e-12:
        sx = new_dims.x / old_dims.x
    if old_dims.y > 1e-12:
        sy = new_dims.y / old_dims.y
    if old_dims.z > 1e-12:
        sz = new_dims.z / old_dims.z
    if abs(sx - 1.0) < 1e-12 and abs(sy - 1.0) < 1e-12 and abs(sz - 1.0) < 1e-12:
        return
    mesh = obj.data
    bm = bmesh.from_edit_mesh(mesh)
    try:
        bm.verts.ensure_lookup_table()
        mat_w = obj.matrix_world
        mat_inv = mat_w.inverted()
        for v in _iter_selected_bmverts(bm):
            wco = mat_w @ v.co
            rel = wco - center_w
            rel_new = Vector((rel.x * sx, rel.y * sy, rel.z * sz))
            wco_new = center_w + rel_new
            v.co = mat_inv @ wco_new
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    finally:
        bm.free()


def _sync_selection_props_from_mesh(context, props) -> None:
    global _alec_syncing
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    mesh = obj.data
    positions = _selected_vert_positions_world(context, obj, mesh)
    if not positions:
        return
    mn, mx = _world_aabb_from_corners(positions)
    m = _mean(positions)
    if m is None:
        return
    c = (mn + mx) * 0.5
    d = mx - mn
    _alec_syncing = True
    props.mean_w = m
    props.bbox_center_w = c
    props.dims_w = d
    _alec_syncing = False


def _depsgraph_sync_selection(scene, depsgraph):
    ctx = bpy.context
    if ctx.mode != "EDIT_MESH":
        return
    obj = ctx.active_object
    if obj is None or obj.type != "MESH":
        return
    props = getattr(ctx.scene, "alec_edit_selection", None)
    if props is None:
        return
    _sync_selection_props_from_mesh(ctx, props)


def _update_mean_w(self, context):
    global _alec_syncing
    if _alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    positions = _selected_vert_positions_world(context, obj, obj.data)
    if not positions:
        return
    cur = _mean(positions)
    if cur is None:
        return
    target = Vector(self.mean_w)
    delta = target - cur
    if delta.length < 1e-10:
        return
    _undo_push(context, "Alec: selection mean")
    _apply_translation_world(context, obj, delta)
    _sync_selection_props_from_mesh(context, self)


def _update_bbox_center_w(self, context):
    global _alec_syncing
    if _alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    positions = _selected_vert_positions_world(context, obj, obj.data)
    if not positions:
        return
    mn, mx = _world_aabb_from_corners(positions)
    cur = (mn + mx) * 0.5
    target = Vector(self.bbox_center_w)
    delta = target - cur
    if delta.length < 1e-10:
        return
    _undo_push(context, "Alec: bbox center")
    _apply_translation_world(context, obj, delta)
    _sync_selection_props_from_mesh(context, self)


def _update_dims_w(self, context):
    global _alec_syncing
    if _alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    positions = _selected_vert_positions_world(context, obj, obj.data)
    if not positions:
        return
    mn, mx = _world_aabb_from_corners(positions)
    old_dims = mx - mn
    center = (mn + mx) * 0.5
    new_dims = Vector(self.dims_w)
    if (new_dims - old_dims).length < 1e-10:
        return
    _undo_push(context, "Alec: selection dimensions")
    _apply_resize_world_aabb(context, obj, center, old_dims, new_dims)
    _sync_selection_props_from_mesh(context, self)


class AlecEditSelectionProps(bpy.types.PropertyGroup):
    mean_w: bpy.props.FloatVectorProperty(
        name="Mean",
        description="World-space mean of selected geometry; edit to translate selection",
        size=3,
        subtype="TRANSLATION",
        update=_update_mean_w,
    )
    bbox_center_w: bpy.props.FloatVectorProperty(
        name="BBox center",
        description="World-space center of selection AABB; edit to translate selection",
        size=3,
        subtype="TRANSLATION",
        update=_update_bbox_center_w,
    )
    dims_w: bpy.props.FloatVectorProperty(
        name="AABB size",
        description="World-axis-aligned size of selection; scale is applied around bbox center",
        size=3,
        subtype="XYZ",
        precision=4,
        update=_update_dims_w,
    )


def _draw_object_transform(layout, obj):
    layout.use_property_split = True
    layout.use_property_decorate = True
    col = layout.column(align=False)
    col.prop(obj, "location")
    if obj.rotation_mode == "QUATERNION":
        col.prop(obj, "rotation_quaternion", text="Rotation")
    elif obj.rotation_mode == "AXIS_ANGLE":
        col.prop(obj, "rotation_axis_angle", text="Rotation")
    else:
        col.prop(obj, "rotation_euler", text="Rotation")
    col.prop(obj, "rotation_mode", text="")
    col.prop(obj, "scale")
    col.prop(obj, "dimensions")


class ALEC_PT_alec_transform(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Alec"
    bl_label = "Transform"

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "VIEW_3D"

    def draw(self, context):
        global _sync_selection_timer_pending
        layout = self.layout
        obj = context.active_object
        if obj is None:
            layout.label(text="No active object")
            return

        _draw_object_transform(layout, obj)

        if context.mode == "EDIT_MESH" and obj.type == "MESH":
            mesh = obj.data
            edit_positions = _selected_vert_positions_world(context, obj, mesh)
            layout.separator()
            box_sel = layout.box()
            box_sel.label(text="Selection (world)")
            props = context.scene.alec_edit_selection
            sig = _selection_vert_signature(context, obj, mesh)
            sid = id(context.scene)
            if sig != _last_selection_sig_by_scene.get(sid):
                _last_selection_sig_by_scene[sid] = sig
                if edit_positions and not _sync_selection_timer_pending:
                    _sync_selection_timer_pending = True
                    bpy.app.timers.register(
                        _deferred_sync_selection_props, first_interval=0.0
                    )
            if not edit_positions:
                box_sel.label(text="No geometry selected")
            else:
                mode = "Vertex" if context.tool_settings.mesh_select_mode[0] else (
                    "Edge" if context.tool_settings.mesh_select_mode[1] else "Face"
                )
                box_sel.label(text=f"Mode: {mode}  |  Verts: {len(edit_positions)}")
                box_sel.use_property_split = True
                box_sel.use_property_decorate = False
                col = box_sel.column(align=False)
                col.prop(props, "mean_w", text="Mean")
                col.prop(props, "bbox_center_w", text="BBox center")
                col.prop(props, "dims_w", text="AABB size")


classes = (
    AlecEditSelectionProps,
    ALEC_PT_alec_transform,
)


def register():
    global _depsgraph_handler
    bpy.utils.register_class(AlecEditSelectionProps)
    bpy.types.Scene.alec_edit_selection = bpy.props.PointerProperty(type=AlecEditSelectionProps)
    bpy.utils.register_class(ALEC_PT_alec_transform)
    _depsgraph_handler = _depsgraph_sync_selection
    if _depsgraph_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph_handler)


def unregister():
    global _depsgraph_handler, _sync_selection_timer_pending
    _sync_selection_timer_pending = False
    if _depsgraph_handler is not None:
        while _depsgraph_handler in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_handler)
        _depsgraph_handler = None
    bpy.utils.unregister_class(ALEC_PT_alec_transform)
    del bpy.types.Scene.alec_edit_selection
    bpy.utils.unregister_class(AlecEditSelectionProps)
