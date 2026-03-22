"""
View3D sidebar (N) > Alec — Transform obiect (RNA) + selecție Edit Mesh (world, editabil).
"""

import bmesh
import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

_alec_syncing = False
_alec_syncing_world = False
_depsgraph_handler = None
# Panel.draw cannot write Scene RNA; cache selection signature per scene here.
_last_selection_sig_by_scene: dict[int, str] = {}
_sync_selection_timer_pending = False
# id(scene) -> (signature, {vert_index: rest v.co în mesh space})
_selection_rest_by_scene: dict[int, tuple[str, dict[int, Vector]]] = {}
# Scale UI: ultima valoare RNA pentru raport incremental (evită compunerea la drag)
_sel_scale_last_ui_by_scene: dict[int, Vector] = {}
_sel_scale_sig_by_scene: dict[int, str] = {}


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


def _undo_context_overrides(context) -> dict:
    """Context complet pentru bpy.ops în callback-uri RNA (altfel undo_push poate eșua)."""
    o: dict = {}
    win = getattr(context, "window", None)
    if win is None:
        wm = getattr(context, "window_manager", None)
        if wm is not None and len(wm.windows):
            win = wm.windows[0]
    if win is not None:
        o["window"] = win

    screen = getattr(context, "screen", None)
    if screen is not None:
        o["screen"] = screen

    area = getattr(context, "area", None)
    if area is None or getattr(area, "type", None) != "VIEW_3D":
        screen = getattr(context, "screen", None)
        if screen is not None:
            for a in screen.areas:
                if a.type == "VIEW_3D":
                    area = a
                    break
    if area is not None:
        o["area"] = area

    region = getattr(context, "region", None)
    if region is None and area is not None:
        for r in area.regions:
            if r.type == "WINDOW":
                region = r
                break
        if region is None and len(area.regions):
            region = area.regions[0]
    if region is not None:
        o["region"] = region

    scene = getattr(context, "scene", None)
    if scene is not None:
        o["scene"] = scene
    vl = getattr(context, "view_layer", None)
    if vl is not None:
        o["view_layer"] = vl
    ao = getattr(context, "active_object", None)
    if ao is not None:
        o["active_object"] = ao
        o["object"] = ao
    return o


def _undo_push(context, message: str) -> None:
    """Înregistrează pas de undo; necesită VIEW_3D + region + flush în Edit Mesh."""
    overrides = _undo_context_overrides(context)
    mode = getattr(context, "mode", None)

    def _run_push():
        if mode == "EDIT_MESH":
            try:
                bpy.ops.ed.flush_edits()
            except Exception:
                pass
        bpy.ops.ed.undo_push(message=message)

    try:
        if overrides:
            with context.temp_override(**overrides):
                _run_push()
        else:
            _run_push()
    except Exception:
        try:
            _run_push()
        except Exception:
            pass


def _transform_slot_type(context) -> str:
    try:
        return context.scene.transform_orientation_slots[0].type
    except Exception:
        return "GLOBAL"


def _rot3_world(obj) -> Matrix:
    _loc, rot, _sc = obj.matrix_world.decompose()
    return rot.to_matrix()


def _orientation_basis_3x3(context, obj, slot_type: str) -> Matrix:
    """Bază ortonormată (coloane = axe în world) pentru VIEW / CURSOR / CUSTOM."""
    if slot_type == "VIEW":
        space = getattr(context, "space_data", None)
        rv3d = getattr(space, "region_3d", None) if space else None
        if rv3d is None:
            return Matrix.Identity(3)
        vm = rv3d.view_matrix.to_3x3()
        try:
            return vm.inverted()
        except Exception:
            return Matrix.Identity(3)
    if slot_type == "CURSOR":
        cur = getattr(context.scene, "cursor", None)
        if cur is None:
            return Matrix.Identity(3)
        _loc, rot, _sc = cur.matrix.decompose()
        return rot.to_matrix()
    if slot_type == "CUSTOM":
        try:
            slot = context.scene.transform_orientation_slots[0]
            co = slot.custom_orientation
            if co is not None and getattr(co, "matrix", None) is not None:
                return co.matrix.to_3x3()
        except Exception:
            pass
        return Matrix.Identity(3)
    return Matrix.Identity(3)


def _euler_orientation_for_object(context, obj) -> Vector:
    """Euler XYZ pentru coloana „orientare” = Transform Orientation (slot 0)."""
    st = _transform_slot_type(context)
    if st == "GLOBAL":
        return Vector(obj.matrix_world.to_euler("XYZ"))
    if st == "LOCAL":
        return Vector(obj.matrix_local.to_euler("XYZ"))
    if st in ("GIMBAL", "NORMAL"):
        return Vector(obj.matrix_local.to_euler("XYZ"))
    R = _rot3_world(obj)
    O = _orientation_basis_3x3(context, obj, st)
    try:
        R_o = O.transposed() @ R @ O
        return Vector(R_o.to_euler("XYZ"))
    except Exception:
        return Vector(obj.matrix_local.to_euler("XYZ"))


def _apply_euler_orientation(context, obj, euler_new: Vector, slot_type: str) -> None:
    """Aplică rotația în spațiul indicat de Transform Orientation."""
    if slot_type == "GLOBAL":
        mw = obj.matrix_world
        loc = mw.translation
        scale = mw.to_scale()
        obj.matrix_world = Matrix.LocRotScale(loc, Euler(euler_new, "XYZ"), scale)
        return
    if slot_type in ("LOCAL", "GIMBAL", "NORMAL"):
        ml = obj.matrix_local.copy()
        loc = ml.translation
        scale = ml.to_scale()
        new_ml = Matrix.LocRotScale(loc, Euler(euler_new, "XYZ"), scale)
        if obj.parent:
            obj.matrix_world = obj.parent.matrix_world @ new_ml
        else:
            obj.matrix_world = new_ml
        return
    O = _orientation_basis_3x3(context, obj, slot_type)
    R_o_new = Euler(euler_new, "XYZ").to_matrix()
    R_w_new = O @ R_o_new @ O.transposed()
    mw = obj.matrix_world
    loc = mw.translation
    scale = mw.to_scale()
    obj.matrix_world = Matrix.LocRotScale(loc, R_w_new.to_quaternion(), scale)


def _transform_orient_short(context) -> str:
    short = {
        "GLOBAL": "Glob",
        "LOCAL": "Loc",
        "VIEW": "View",
        "GIMBAL": "Gimb",
        "NORMAL": "Nrm",
        "CURSOR": "Curs",
        "CUSTOM": "Cust",
    }
    st = _transform_slot_type(context)
    return short.get(st, st)


def _rot_orient_column_label(context) -> str:
    return f"Rot ({_transform_orient_short(context)})"


def _orientation_matrix_world(context, obj) -> Matrix:
    """Bază 3x3 (coloane = axe orientare în world) pentru slot Transform Orientation 0."""
    st = _transform_slot_type(context)
    if st == "GLOBAL":
        return Matrix.Identity(3)
    if st in ("LOCAL", "GIMBAL", "NORMAL"):
        return _rot3_world(obj)
    return _orientation_basis_3x3(context, obj, st)


def _vec_near(v: Vector, target: Vector, eps: float = 1e-12) -> bool:
    return (v - target).length < eps


def _oriented_bbox_from_selection(
    context,
    obj,
    mesh,
    positions: list[Vector] | None = None,
) -> tuple[Matrix, Vector, Vector, Vector, Vector] | None:
    """min/max în spațiul O^T@w, dims, centru world al bbox-ului aliniat la orientare."""
    O = _orientation_matrix_world(context, obj)
    if positions is None:
        positions = _selected_vert_positions_world(context, obj, mesh)
    if not positions:
        return None
    mn: Vector | None = None
    mx: Vector | None = None
    Ot = O.transposed()
    for w in positions:
        s = Ot @ w
        if mn is None:
            mn = s.copy()
            mx = s.copy()
        else:
            mn = Vector((min(mn.x, s.x), min(mn.y, s.y), min(mn.z, s.z)))
            mx = Vector((max(mx.x, s.x), max(mx.y, s.y), max(mx.z, s.z)))
    assert mn is not None and mx is not None
    dims = mx - mn
    center_s = (mn + mx) * 0.5
    center_w = O @ center_s
    return (O, mn, mx, dims, center_w)


def _apply_oriented_scale_factors(
    context,
    obj,
    mult: Vector,
    ob: tuple[Matrix, Vector, Vector, Vector, Vector] | None = None,
) -> None:
    """Scale pe axele orientării în jurul centrului bbox orientat; ob opțional evită dublu bbox."""
    if _vec_near(mult, Vector((1.0, 1.0, 1.0))):
        return
    mesh = obj.data
    if ob is None:
        ob = _oriented_bbox_from_selection(context, obj, mesh)
    if ob is None:
        return
    O, mn, mx, _dims, _cw = ob
    center_s = (mn + mx) * 0.5
    mat_w = obj.matrix_world
    mat_inv = mat_w.inverted()
    Ot = O.transposed()
    bm = bmesh.from_edit_mesh(mesh)
    try:
        bm.verts.ensure_lookup_table()
        for v in _iter_selected_bmverts(bm):
            wco = mat_w @ v.co
            s = Ot @ wco
            s_new = Vector(
                (
                    center_s.x + mult.x * (s.x - center_s.x),
                    center_s.y + mult.y * (s.y - center_s.y),
                    center_s.z + mult.z * (s.z - center_s.z),
                )
            )
            v.co = mat_inv @ (O @ s_new)
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    finally:
        bm.free()
    _invalidate_sel_rot_after_geom_edit(context)


def _apply_scale_orientation(context, obj, mult: Vector) -> None:
    _apply_oriented_scale_factors(context, obj, mult, ob=None)


def _apply_resize_orientation(context, obj, new_dims: Vector) -> None:
    ob = _oriented_bbox_from_selection(context, obj, obj.data)
    if ob is None:
        return
    _O, _mn, _mx, old_dims, _cw = ob
    mult = Vector((1.0, 1.0, 1.0))
    for i in range(3):
        mult[i] = new_dims[i] / old_dims[i] if old_dims[i] > 1e-12 else 1.0
    _apply_oriented_scale_factors(context, obj, mult, ob=ob)


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


def _mean_local_selected(obj, mesh) -> Vector | None:
    """Centroid în spațiu mesh (v.co) pentru vârfurile selecției curente."""
    bm = bmesh.from_edit_mesh(mesh)
    try:
        bm.verts.ensure_lookup_table()
        verts = _iter_selected_bmverts(bm)
        if not verts:
            return None
        s = Vector((0.0, 0.0, 0.0))
        for v in verts:
            s += v.co
        return s / len(verts)
    finally:
        bm.free()


def _mesh_local_delta_to_world(obj, cur_local: Vector, delta_local: Vector) -> Vector:
    """Translație world echivalentă cu delta_local în spațiul mesh (față de punctul de referință)."""
    mw = obj.matrix_world
    return (mw @ (cur_local + delta_local)) - (mw @ cur_local)


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


def _rebuild_rest_coords_dict(context, obj, mesh) -> dict[int, Vector]:
    bm = bmesh.from_edit_mesh(mesh)
    try:
        bm.verts.ensure_lookup_table()
        out: dict[int, Vector] = {}
        for v in _iter_selected_bmverts(bm):
            out[v.index] = v.co.copy()
        return out
    finally:
        bm.free()


def _euler_from_R_for_orient(context, obj, R: Matrix, st: str) -> Vector:
    """R = rotație world 3x3 (din quaternion). Euler în spațiul orientării."""
    if st == "GLOBAL":
        return Vector(R.to_quaternion().to_euler("XYZ"))
    if st == "LOCAL":
        _loc, rot, _sc = obj.matrix_world.decompose()
        O = rot.to_matrix()
        R_o = O.transposed() @ R @ O
        return Vector(R_o.to_quaternion().to_euler("XYZ"))
    if st in ("GIMBAL", "NORMAL"):
        return _euler_from_R_for_orient(context, obj, R, "LOCAL")
    O = _orientation_basis_3x3(context, obj, st)
    try:
        R_o = O.transposed() @ R @ O
        return Vector(R_o.to_quaternion().to_euler("XYZ"))
    except Exception:
        return Vector(R.to_quaternion().to_euler("XYZ"))


def _sync_sel_rot_eulers_from_quat(context, props) -> None:
    global _alec_syncing
    q = Quaternion(props.sel_rot_quat)
    R = q.to_matrix()
    st = _transform_slot_type(context)
    eu_w = q.to_euler("XYZ")
    eu_o = _euler_from_R_for_orient(context, context.active_object, R, st)
    _alec_syncing = True
    props.sel_rot_world_euler = eu_w
    props.sel_rot_orient_euler = eu_o
    _alec_syncing = False


def _ensure_selection_rotation_rest(context, props, mesh) -> None:
    global _alec_syncing, _selection_rest_by_scene
    scene = context.scene
    sid = id(scene)
    obj = context.active_object
    sig = _selection_vert_signature(context, obj, mesh)
    ent = _selection_rest_by_scene.get(sid)
    if ent is None or ent[0] != sig:
        rest = _rebuild_rest_coords_dict(context, obj, mesh)
        _selection_rest_by_scene[sid] = (sig, rest)
        _alec_syncing = True
        props.sel_rot_quat = (1.0, 0.0, 0.0, 0.0)
        _alec_syncing = False
        _sync_sel_rot_eulers_from_quat(context, props)


def _invalidate_sel_rot_after_geom_edit(context) -> None:
    """După translate/resize pe selecție: rest nou, rot panel reset la identitate."""
    if context.mode != "EDIT_MESH":
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return
    props = getattr(context.scene, "alec_edit_selection", None)
    if props is None:
        return
    mesh = obj.data
    _ensure_selection_rotation_rest(context, props, mesh)


def _apply_selection_rotation_quat(context, obj, quat: Quaternion) -> None:
    scene = context.scene
    sid = id(scene)
    entry = _selection_rest_by_scene.get(sid)
    if entry is None:
        return
    _sig, rest = entry
    if not rest:
        return
    mesh = obj.data
    bm = bmesh.from_edit_mesh(mesh)
    try:
        bm.verts.ensure_lookup_table()
        mat_w = obj.matrix_world
        mat_inv = mat_w.inverted()
        R = quat.to_matrix()
        ws = []
        for _idx, co in rest.items():
            ws.append(mat_w @ co)
        p = sum(ws, Vector((0.0, 0.0, 0.0))) / len(ws)
        for idx, co_rest in rest.items():
            v = bm.verts[idx]
            w = mat_w @ co_rest
            wn = R @ (w - p) + p
            v.co = mat_inv @ wn
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
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
    _invalidate_sel_rot_after_geom_edit(context)


def _sync_selection_props_from_mesh(context, props) -> None:
    global _alec_syncing
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    mesh = obj.data
    positions = _selected_vert_positions_world(context, obj, mesh)
    sid = id(context.scene)
    if not positions:
        _alec_syncing = True
        props.mean_w = (0.0, 0.0, 0.0)
        props.mean_local = (0.0, 0.0, 0.0)
        props.bbox_center_w = (0.0, 0.0, 0.0)
        props.sel_dims_orient = (0.0, 0.0, 0.0)
        props.sel_scale_orient = (1.0, 1.0, 1.0)
        props.sel_rot_quat = (1.0, 0.0, 0.0, 0.0)
        props.sel_rot_world_euler = (0.0, 0.0, 0.0)
        props.sel_rot_orient_euler = (0.0, 0.0, 0.0)
        _alec_syncing = False
        _selection_rest_by_scene.pop(sid, None)
        _sel_scale_last_ui_by_scene.pop(sid, None)
        _sel_scale_sig_by_scene.pop(sid, None)
        return
    mn, mx = _world_aabb_from_corners(positions)
    m = _mean(positions)
    if m is None:
        return
    ml = _mean_local_selected(obj, mesh)
    if ml is None:
        return
    ob = _oriented_bbox_from_selection(context, obj, mesh, positions=positions)
    if ob is None:
        return
    _o, _mn, _mx, d_orient, c_orient = ob
    sig = _selection_vert_signature(context, obj, mesh)
    _alec_syncing = True
    if _sel_scale_sig_by_scene.get(sid) != sig:
        props.sel_scale_orient = (1.0, 1.0, 1.0)
        _sel_scale_last_ui_by_scene[sid] = Vector((1.0, 1.0, 1.0))
        _sel_scale_sig_by_scene[sid] = sig
    props.mean_w = m
    props.mean_local = ml
    props.bbox_center_w = c_orient
    props.sel_dims_orient = d_orient
    _alec_syncing = False
    _ensure_selection_rotation_rest(context, props, mesh)


def _update_alec_object_world(self, context):
    global _alec_syncing_world
    if _alec_syncing_world:
        return
    obj = context.active_object
    if obj is None:
        return
    target = Vector(self.alec_object_world)
    if not _invoke_object_world_translation(context, target):
        _undo_push(context, "Alec: world location")
        mw = obj.matrix_world.copy()
        mw.translation = target
        obj.matrix_world = mw


def _update_alec_rotation_world(self, context):
    global _alec_syncing_world
    if _alec_syncing_world:
        return
    obj = context.active_object
    if obj is None:
        return
    if context.mode == "EDIT_MESH":
        return
    eu = Vector(self.alec_rotation_world)
    if not _invoke_object_rotation_world(context, eu):
        _undo_push(context, "Alec: world rotation")
        mw = obj.matrix_world
        loc = mw.translation
        scale = mw.to_scale()
        euler = Euler(eu, "XYZ")
        obj.matrix_world = Matrix.LocRotScale(loc, euler, scale)


def _update_alec_rotation_local(self, context):
    """Euler XYZ din matrix_local; nu depinde de rotation_mode (quaternion etc.)."""
    global _alec_syncing_world
    if _alec_syncing_world:
        return
    obj = context.active_object
    if obj is None:
        return
    if context.mode == "EDIT_MESH":
        return
    eu = Vector(self.alec_rotation_local)
    st = _transform_slot_type(context)
    if not _invoke_object_rotation_local(context, eu, st):
        _undo_push(context, "Alec: orient rotation")
        _apply_euler_orientation(context, obj, eu, st)
        _sync_object_world_from_active(context)


def _sync_object_world_from_active(context) -> None:
    global _alec_syncing_world
    obj = context.active_object
    if obj is None:
        return
    scene = context.scene
    mw = obj.matrix_world
    t = mw.translation
    eu = mw.to_euler("XYZ")
    eu_orient = _euler_orientation_for_object(context, obj)
    _alec_syncing_world = True
    try:
        scene.alec_object_world = t
        scene.alec_rotation_world = eu
        scene.alec_rotation_local = eu_orient
    finally:
        _alec_syncing_world = False


class ALEC_OT_object_world_translation(bpy.types.Operator):
    bl_idname = "alec.object_world_translation"
    bl_label = "Object world location"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Set object translation in world space"

    translation: bpy.props.FloatVectorProperty(
        name="Translation",
        size=3,
        subtype="TRANSLATION",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        mw = obj.matrix_world.copy()
        mw.translation = Vector(self.translation)
        obj.matrix_world = mw
        _sync_object_world_from_active(context)
        return {"FINISHED"}


class ALEC_OT_object_rotation_world(bpy.types.Operator):
    bl_idname = "alec.object_rotation_world"
    bl_label = "Object world rotation"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Set object Euler XYZ rotation in world space"

    euler_xyz: bpy.props.FloatVectorProperty(
        name="Euler",
        size=3,
        subtype="EULER",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        mw = obj.matrix_world
        loc = mw.translation
        scale = mw.to_scale()
        euler = Euler(Vector(self.euler_xyz), "XYZ")
        obj.matrix_world = Matrix.LocRotScale(loc, euler, scale)
        _sync_object_world_from_active(context)
        return {"FINISHED"}


class ALEC_OT_object_rotation_local(bpy.types.Operator):
    bl_idname = "alec.object_rotation_local"
    bl_label = "Object rotation (orient)"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Set Euler XYZ in active Transform Orientation space"

    euler_xyz: bpy.props.FloatVectorProperty(
        name="Euler",
        size=3,
        subtype="EULER",
        options={"SKIP_SAVE"},
    )
    orient_type: bpy.props.StringProperty(options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        _apply_euler_orientation(
            context, obj, Vector(self.euler_xyz), self.orient_type or "GLOBAL"
        )
        _sync_object_world_from_active(context)
        return {"FINISHED"}


def _invoke_alec_op(context, op_id: str, **kwargs) -> bool:
    """Apel bpy.ops.alec.* cu temp_override; returnează False la eșec."""
    ov = _undo_context_overrides(context)
    parts = op_id.split(".")
    try:
        op = bpy.ops
        for p in parts:
            op = getattr(op, p)
        if ov:
            with context.temp_override(**ov):
                op(**kwargs)
        else:
            op(**kwargs)
        return True
    except Exception:
        return False


def _invoke_object_world_translation(context, translation: Vector) -> bool:
    t = (translation.x, translation.y, translation.z)
    return _invoke_alec_op(context, "alec.object_world_translation", translation=t)


def _invoke_object_rotation_world(context, euler_xyz: Vector) -> bool:
    e = (euler_xyz.x, euler_xyz.y, euler_xyz.z)
    return _invoke_alec_op(context, "alec.object_rotation_world", euler_xyz=e)


def _invoke_object_rotation_local(
    context, euler_xyz: Vector, orient_type: str
) -> bool:
    e = (euler_xyz.x, euler_xyz.y, euler_xyz.z)
    return _invoke_alec_op(
        context, "alec.object_rotation_local", euler_xyz=e, orient_type=orient_type
    )


def _depsgraph_sync_selection(scene, depsgraph):
    ctx = bpy.context
    _sync_object_world_from_active(ctx)
    if ctx.mode != "EDIT_MESH":
        return
    obj = ctx.active_object
    if obj is None or obj.type != "MESH":
        return
    props = getattr(ctx.scene, "alec_edit_selection", None)
    if props is None:
        return
    _sync_selection_props_from_mesh(ctx, props)


class ALEC_OT_selection_translate_delta(bpy.types.Operator):
    """Undo corect în Edit Mesh (REGISTER|UNDO); bmesh direct + undo_push nu e mereu în stivă."""

    bl_idname = "alec.selection_translate_delta"
    bl_label = "Selection translate"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Translate selected geometry in world space"

    delta_w: bpy.props.FloatVectorProperty(
        name="Delta",
        size=3,
        subtype="TRANSLATION",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "EDIT_MESH"
            and context.active_object is not None
            and context.active_object.type == "MESH"
        )

    def execute(self, context):
        obj = context.active_object
        props = context.scene.alec_edit_selection
        delta = Vector(self.delta_w)
        if delta.length < 1e-12:
            return {"CANCELLED"}
        _apply_translation_world(context, obj, delta)
        _sync_selection_props_from_mesh(context, props)
        return {"FINISHED"}


class ALEC_OT_selection_resize_orient(bpy.types.Operator):
    bl_idname = "alec.selection_resize_orient"
    bl_label = "Selection resize (orient)"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Resize selection bbox along active Transform Orientation axes"

    new_dims: bpy.props.FloatVectorProperty(
        name="New dims",
        size=3,
        subtype="XYZ",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "EDIT_MESH"
            and context.active_object is not None
            and context.active_object.type == "MESH"
        )

    def execute(self, context):
        obj = context.active_object
        props = context.scene.alec_edit_selection
        _apply_resize_orientation(context, obj, Vector(self.new_dims))
        _sync_selection_props_from_mesh(context, props)
        return {"FINISHED"}


class ALEC_OT_selection_scale_orient(bpy.types.Operator):
    bl_idname = "alec.selection_scale_orient"
    bl_label = "Selection scale (orient)"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Scale selection around oriented bbox center (multipliers per axis)"

    mult: bpy.props.FloatVectorProperty(
        name="Scale",
        size=3,
        subtype="XYZ",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "EDIT_MESH"
            and context.active_object is not None
            and context.active_object.type == "MESH"
        )

    def execute(self, context):
        obj = context.active_object
        props = context.scene.alec_edit_selection
        _apply_scale_orientation(context, obj, Vector(self.mult))
        _sync_selection_props_from_mesh(context, props)
        return {"FINISHED"}


def _invoke_selection_translate_delta(context, delta: Vector) -> bool:
    dw = (delta.x, delta.y, delta.z)
    return _invoke_alec_op(context, "alec.selection_translate_delta", delta_w=dw)


def _invoke_selection_resize_orient(context, new_dims: Vector) -> bool:
    nd = (new_dims.x, new_dims.y, new_dims.z)
    return _invoke_alec_op(context, "alec.selection_resize_orient", new_dims=nd)


def _invoke_selection_scale_orient(context, mult: Vector) -> bool:
    m = (mult.x, mult.y, mult.z)
    return _invoke_alec_op(context, "alec.selection_scale_orient", mult=m)


def _reset_transform_column(context, col: str) -> str:
    """Reset o coloană: valori 0, scale 1. Returnează 'FINISHED' sau 'CANCELLED'."""
    obj = context.active_object
    if obj is None:
        return "CANCELLED"
    scene = context.scene
    edit_mesh = context.mode == "EDIT_MESH" and obj.type == "MESH"
    props = getattr(scene, "alec_edit_selection", None)
    if edit_mesh and not _selected_vert_positions_world(context, obj, obj.data):
        return "CANCELLED"

    if col == "WORLD_MEAN":
        if edit_mesh and props is not None:
            positions = _selected_vert_positions_world(context, obj, obj.data)
            m = _mean(positions)
            if m is None:
                return "CANCELLED"
            delta = Vector((0.0, 0.0, 0.0)) - m
            if delta.length < 1e-12:
                return "FINISHED"
            _apply_translation_world(context, obj, delta)
            _sync_selection_props_from_mesh(context, props)
            return "FINISHED"
        mw = obj.matrix_world.copy()
        mw.translation = Vector((0.0, 0.0, 0.0))
        obj.matrix_world = mw
        _sync_object_world_from_active(context)
        return "FINISHED"

    if col == "LOCAL_MEAN":
        if edit_mesh and props is not None:
            mesh = obj.data
            cur = _mean_local_selected(obj, mesh)
            if cur is None:
                return "CANCELLED"
            delta_local = Vector((0.0, 0.0, 0.0)) - cur
            if delta_local.length < 1e-12:
                return "FINISHED"
            delta_w = _mesh_local_delta_to_world(obj, cur, delta_local)
            if delta_w.length < 1e-12:
                return "FINISHED"
            _apply_translation_world(context, obj, delta_w)
            _sync_selection_props_from_mesh(context, props)
            return "FINISHED"
        obj.location = Vector((0.0, 0.0, 0.0))
        return "FINISHED"

    if col in ("ROT_WORLD", "ROT_ORIENT"):
        if edit_mesh and props is not None:
            _ensure_selection_rotation_rest(context, props, obj.data)
            q = Quaternion((1.0, 0.0, 0.0, 0.0))
            _apply_selection_rotation_quat(context, obj, q)
            props.sel_rot_quat = (q.w, q.x, q.y, q.z)
            _sync_sel_rot_eulers_from_quat(context, props)
            return "FINISHED"
        if col == "ROT_WORLD":
            mw = obj.matrix_world
            loc = mw.translation
            scale = mw.to_scale()
            obj.matrix_world = Matrix.LocRotScale(
                loc, Euler((0.0, 0.0, 0.0), "XYZ"), scale
            )
            _sync_object_world_from_active(context)
            return "FINISHED"
        st = _transform_slot_type(context)
        _apply_euler_orientation(context, obj, Vector((0.0, 0.0, 0.0)), st)
        _sync_object_world_from_active(context)
        return "FINISHED"

    if col == "SCALE":
        if edit_mesh and props is not None:
            sid = id(scene)
            props.sel_scale_orient = (1.0, 1.0, 1.0)
            _sel_scale_last_ui_by_scene[sid] = Vector((1.0, 1.0, 1.0))
            return "FINISHED"
        obj.scale = (1.0, 1.0, 1.0)
        return "FINISHED"

    if col == "DIMS":
        if edit_mesh and props is not None:
            _apply_resize_orientation(context, obj, Vector((0.0, 0.0, 0.0)))
            _sync_selection_props_from_mesh(context, props)
            return "FINISHED"
        try:
            obj.dimensions = (0.0, 0.0, 0.0)
        except Exception:
            pass
        return "FINISHED"

    return "CANCELLED"


class ALEC_OT_reset_transform_column(bpy.types.Operator):
    bl_idname = "alec.reset_transform_column"
    bl_label = "Reset column"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Pune valorile coloanei la 0 (scale la 1, dimensiuni la 0)"

    column: bpy.props.StringProperty(options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None:
            return False
        if context.mode == "EDIT_MESH" and obj.type == "MESH":
            return bool(_selected_vert_positions_world(context, obj, obj.data))
        return True

    def execute(self, context):
        st = _reset_transform_column(context, self.column)
        return {"FINISHED"} if st == "FINISHED" else {"CANCELLED"}


def _draw_reset_btn(row, column_id: str, enabled: bool = True) -> None:
    op = row.operator(
        "alec.reset_transform_column",
        icon="FILE_ALIAS",
        text="",
        emboss=False,
    )
    op.column = column_id
    try:
        op.enabled = enabled
    except Exception:
        pass


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
    if not _invoke_selection_translate_delta(context, delta):
        _undo_push(context, "Alec: selection mean")
        _apply_translation_world(context, obj, delta)
        _sync_selection_props_from_mesh(context, self)


def _update_mean_local(self, context):
    global _alec_syncing
    if _alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    mesh = obj.data
    cur = _mean_local_selected(obj, mesh)
    if cur is None:
        return
    target = Vector(self.mean_local)
    delta_local = target - cur
    if delta_local.length < 1e-10:
        return
    delta_w = _mesh_local_delta_to_world(obj, cur, delta_local)
    if delta_w.length < 1e-10:
        return
    if not _invoke_selection_translate_delta(context, delta_w):
        _undo_push(context, "Alec: selection local")
        _apply_translation_world(context, obj, delta_w)
        _sync_selection_props_from_mesh(context, self)


def _update_bbox_center_w(self, context):
    global _alec_syncing
    if _alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    mesh = obj.data
    ob = _oriented_bbox_from_selection(context, obj, mesh)
    if ob is None:
        return
    _O, _mn, _mx, _d, cur = ob
    target = Vector(self.bbox_center_w)
    delta = target - cur
    if delta.length < 1e-10:
        return
    if not _invoke_selection_translate_delta(context, delta):
        _undo_push(context, "Alec: bbox center")
        _apply_translation_world(context, obj, delta)
        _sync_selection_props_from_mesh(context, self)


def _update_sel_dims_orient(self, context):
    global _alec_syncing
    if _alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    mesh = obj.data
    ob = _oriented_bbox_from_selection(context, obj, mesh)
    if ob is None:
        return
    _O, _mn, _mx, old_dims, _cw = ob
    new_dims = Vector(self.sel_dims_orient)
    if (new_dims - old_dims).length < 1e-10:
        return
    if not _invoke_selection_resize_orient(context, new_dims):
        _undo_push(context, "Alec: selection dimensions")
        _apply_resize_orientation(context, obj, new_dims)
        _sync_selection_props_from_mesh(context, self)


def _update_sel_scale_orient(self, context):
    global _alec_syncing
    if _alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    if not _selected_vert_positions_world(context, obj, obj.data):
        return
    sid = id(context.scene)
    curr = Vector(self.sel_scale_orient)
    prev = _sel_scale_last_ui_by_scene.get(sid, Vector((1.0, 1.0, 1.0)))
    ratio = Vector(
        (
            curr.x / prev.x if abs(prev.x) > 1e-12 else 1.0,
            curr.y / prev.y if abs(prev.y) > 1e-12 else 1.0,
            curr.z / prev.z if abs(prev.z) > 1e-12 else 1.0,
        )
    )
    if (ratio - Vector((1.0, 1.0, 1.0))).length < 1e-10:
        return
    if not _invoke_selection_scale_orient(context, ratio):
        _undo_push(context, "Alec: selection scale")
        _apply_scale_orientation(context, obj, ratio)
        _sync_selection_props_from_mesh(context, self)
    _sel_scale_last_ui_by_scene[sid] = curr.copy()


class ALEC_OT_selection_rotate(bpy.types.Operator):
    bl_idname = "alec.selection_rotate"
    bl_label = "Selection rotate"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Rotate selected vertices around selection centroid (world)"

    rotation: bpy.props.FloatVectorProperty(
        name="Rotation",
        size=4,
        subtype="QUATERNION",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "EDIT_MESH"
            and context.active_object is not None
            and context.active_object.type == "MESH"
        )

    def execute(self, context):
        obj = context.active_object
        q = Quaternion(self.rotation)
        _apply_selection_rotation_quat(context, obj, q)
        props = context.scene.alec_edit_selection
        props.sel_rot_quat = (q.w, q.x, q.y, q.z)
        _sync_sel_rot_eulers_from_quat(context, props)
        return {"FINISHED"}


def _invoke_selection_rotate(context, q: Quaternion) -> bool:
    r = (q.w, q.x, q.y, q.z)
    return _invoke_alec_op(context, "alec.selection_rotate", rotation=r)


def _update_sel_rot_world_euler(self, context):
    global _alec_syncing
    if _alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    if not _selected_vert_positions_world(context, obj, obj.data):
        return
    _ensure_selection_rotation_rest(context, self, obj.data)
    eu = Vector(self.sel_rot_world_euler)
    q = Euler(eu, "XYZ").to_quaternion()
    if _invoke_selection_rotate(context, q):
        return
    _undo_push(context, "Alec: selection rotate")
    _apply_selection_rotation_quat(context, obj, q)
    self.sel_rot_quat = (q.w, q.x, q.y, q.z)
    _sync_sel_rot_eulers_from_quat(context, self)


def _update_sel_rot_orient_euler(self, context):
    global _alec_syncing
    if _alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    if not _selected_vert_positions_world(context, obj, obj.data):
        return
    _ensure_selection_rotation_rest(context, self, obj.data)
    eu_o = Vector(self.sel_rot_orient_euler)
    st = _transform_slot_type(context)
    R_o = Euler(eu_o, "XYZ").to_matrix()
    if st == "GLOBAL":
        R_w = R_o
    elif st in ("LOCAL", "GIMBAL", "NORMAL"):
        _loc, rot, _sc = obj.matrix_world.decompose()
        O = rot.to_matrix()
        R_w = O @ R_o @ O.transposed()
    else:
        O = _orientation_basis_3x3(context, obj, st)
        R_w = O @ R_o @ O.transposed()
    q = R_w.to_quaternion().normalized()
    if _invoke_selection_rotate(context, q):
        return
    _undo_push(context, "Alec: selection rotate")
    _apply_selection_rotation_quat(context, obj, q)
    self.sel_rot_quat = (q.w, q.x, q.y, q.z)
    _sync_sel_rot_eulers_from_quat(context, self)


class AlecEditSelectionProps(bpy.types.PropertyGroup):
    mean_w: bpy.props.FloatVectorProperty(
        name="Mean",
        description="World-space mean of selected geometry; edit to translate selection",
        size=3,
        subtype="TRANSLATION",
        update=_update_mean_w,
    )
    mean_local: bpy.props.FloatVectorProperty(
        name="Local",
        description="Mesh-space mean of selected geometry; edit to translate selection",
        size=3,
        subtype="TRANSLATION",
        update=_update_mean_local,
    )
    bbox_center_w: bpy.props.FloatVectorProperty(
        name="BBox center",
        description="Centrul world al bbox-ului selecției aliniat la Transform Orientation",
        size=3,
        subtype="TRANSLATION",
        update=_update_bbox_center_w,
    )
    sel_dims_orient: bpy.props.FloatVectorProperty(
        name="Dims (orient)",
        description="Dimensiuni bbox selecție pe axele Transform Orientation (header)",
        size=3,
        subtype="XYZ",
        precision=4,
        update=_update_sel_dims_orient,
    )
    sel_scale_orient: bpy.props.FloatVectorProperty(
        name="Scale (orient)",
        description="Multiplicatori pe axele Transform Orientation față de centrul bbox; revin la 1 după aplicare",
        size=3,
        subtype="XYZ",
        default=(1.0, 1.0, 1.0),
        update=_update_sel_scale_orient,
    )
    sel_rot_quat: bpy.props.FloatVectorProperty(
        name="Selection rot accum",
        description="Quaternion cumulativ (rest selecție); nu edita direct",
        size=4,
        subtype="QUATERNION",
        default=(1.0, 0.0, 0.0, 0.0),
    )
    sel_rot_world_euler: bpy.props.FloatVectorProperty(
        name="Sel rot world",
        description="Euler XYZ world pentru selecție (față de rest la schimbare selecție)",
        size=3,
        subtype="EULER",
        update=_update_sel_rot_world_euler,
    )
    sel_rot_orient_euler: bpy.props.FloatVectorProperty(
        name="Sel rot orient",
        description="Euler în Transform Orientation (slot viewport)",
        size=3,
        subtype="EULER",
        update=_update_sel_rot_orient_euler,
    )


def _draw_object_transform(layout, context, obj):
    scene = context.scene
    layout.use_property_split = True
    layout.use_property_decorate = True

    edit_mesh = context.mode == "EDIT_MESH" and obj.type == "MESH"
    props = scene.alec_edit_selection if edit_mesh else None
    mesh = obj.data if edit_mesh else None
    has_sel = (
        bool(_selected_vert_positions_world(context, obj, mesh))
        if edit_mesh and mesh
        else False
    )

    # Fără property_split pe rând: altfel N-panelul împarte spațiul ciudat între World | Local.
    if edit_mesh:
        layout.label(text="Selection Transform", icon="EDITMODE_HLT")
    else:
        layout.label(text="Object Transform", icon="OBJECT_DATA")
    row = layout.row(align=True)
    split = row.split(factor=0.5)

    col_w = split.column(align=True)
    sub_w = col_w.column(align=True)
    sub_w.use_property_split = True
    sub_w.use_property_decorate = True
    row_w = sub_w.row(align=True)
    row_w.use_property_split = True

    row_wh = row_w.row(align=True)
    row_wh.label(text="World")
    _draw_reset_btn(row_wh, "WORLD_MEAN", enabled=(not edit_mesh) or has_sel)
    # Fără split pe XYZ: în sidebar, split rezervă o coloană lată de etichete (nu există „auto margin”).
    xyz_w = sub_w.column(align=True)
    xyz_w.use_property_split = False
    xyz_w.use_property_decorate = False
    if edit_mesh and props is not None:
        xyz_w.enabled = has_sel
        for i, axis in enumerate(("X", "Y", "Z")):
            xyz_w.prop(props, "mean_w", index=i, text=axis)
    else:
        for i, axis in enumerate(("X", "Y", "Z")):
            xyz_w.prop(scene, "alec_object_world", index=i, text=axis)

    row_wr = sub_w.row(align=True)
    row_wr.use_property_split = True

    row_wrh = row_wr.row(align=True)
    row_wrh.label(text="Rot.World")
    if not edit_mesh:
        _draw_reset_btn(row_wrh, "ROT_WORLD", enabled=True)
    rot_w = sub_w.column(align=True)
    rot_w.use_property_split = False
    rot_w.use_property_decorate = False
    if edit_mesh and props is not None:
        rot_w.enabled = has_sel
        for i, axis in enumerate(("X", "Y", "Z")):
            rot_w.prop(props, "sel_rot_world_euler", index=i, text=axis)
    else:
        for i, axis in enumerate(("X", "Y", "Z")):
            rot_w.prop(scene, "alec_rotation_world", index=i, text=axis)

    col_o = split.column(align=True)
    sub_o = col_o.column(align=True)
    sub_o.use_property_split = True
    sub_o.use_property_decorate = True
    row_o = sub_o.row(align=True)
    row_o.use_property_split = True
    row_oh = row_o.row(align=True)
    row_oh.label(text="Local")
    _draw_reset_btn(row_oh, "LOCAL_MEAN", enabled=(not edit_mesh) or has_sel)

    xyz_o = sub_o.column(align=True)
    xyz_o.use_property_split = False
    xyz_o.use_property_decorate = False
    if edit_mesh and props is not None:
        xyz_o.enabled = has_sel
        for i, axis in enumerate(("X", "Y", "Z")):
            xyz_o.prop(props, "mean_local", index=i, text=axis)
    else:
        for i, axis in enumerate(("X", "Y", "Z")):
            xyz_o.prop(obj, "location", index=i, text=axis)

    row_or = sub_o.row(align=True)
    row_or.use_property_split = True

    row_orh = row_or.row(align=True)
    row_orh.label(text=_rot_orient_column_label(context))
    if not edit_mesh:
        _draw_reset_btn(row_orh, "ROT_ORIENT", enabled=True)
    rot_o = sub_o.column(align=True)
    rot_o.use_property_split = False
    rot_o.use_property_decorate = False
    if edit_mesh and props is not None:
        rot_o.enabled = has_sel
        for i, axis in enumerate(("X", "Y", "Z")):
            rot_o.prop(props, "sel_rot_orient_euler", index=i, text=axis)
    else:
        for i, axis in enumerate(("X", "Y", "Z")):
            rot_o.prop(scene, "alec_rotation_local", index=i, text=axis)


    row_sd = layout.row(align=True)
    row_sd.use_property_split = False
    split_sd = row_sd.split(factor=0.5)
    col_s = split_sd.column(align=True)
    col_d = split_sd.column(align=True)
    oshort = _transform_orient_short(context)
    if edit_mesh and props is not None:
        col_s.label(text=f"Scale ({oshort})")
        sub_s = col_s.column(align=True)
        sub_s.use_property_split = False
        sub_s.use_property_decorate = False
        sub_s.enabled = has_sel
        for i, axis in enumerate(("X", "Y", "Z")):
            sub_s.prop(props, "sel_scale_orient", index=i, text=axis)
        col_d.label(text=f"Dims ({oshort})")
        sub_d = col_d.column(align=True)
        sub_d.use_property_split = False
        sub_d.use_property_decorate = False
        sub_d.enabled = has_sel
        for i, axis in enumerate(("X", "Y", "Z")):
            sub_d.prop(props, "sel_dims_orient", index=i, text=axis)
    else:
        row_sh = col_s.row(align=True)
        row_sh.label(text="Scale")
        _draw_reset_btn(row_sh, "SCALE", enabled=True)
        sub_s = col_s.column(align=True)
        sub_s.use_property_split = False
        sub_s.use_property_decorate = False
        sub_s.prop(obj, "scale", text="")
        col_d.label(text="Dimensions")
        sub_d = col_d.column(align=True)
        sub_d.use_property_split = False
        sub_d.use_property_decorate = False
        sub_d.prop(obj, "dimensions", text="")


class ALEC_PT_alec_transform(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Alec"
    bl_label = "Transform"

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "VIEW_3D"

    def draw_header(self, context):
        layout = self.layout

        layout.label(text="Alec's Tools", icon="EXPERIMENTAL")

    def draw(self, context):
        global _sync_selection_timer_pending
        layout = self.layout
        obj = context.active_object
        if obj is None:
            layout.label(text="No active object")
            return

        if context.mode == "EDIT_MESH" and obj.type == "MESH":
            mesh = obj.data
            edit_positions = _selected_vert_positions_world(context, obj, mesh)
            sig = _selection_vert_signature(context, obj, mesh)
            sid = id(context.scene)
            if sig != _last_selection_sig_by_scene.get(sid):
                _last_selection_sig_by_scene[sid] = sig
                if edit_positions and not _sync_selection_timer_pending:
                    _sync_selection_timer_pending = True
                    bpy.app.timers.register(
                        _deferred_sync_selection_props, first_interval=0.0
                    )

        _draw_object_transform(layout, context, obj)


_classes_operators = (
    ALEC_OT_object_world_translation,
    ALEC_OT_object_rotation_world,
    ALEC_OT_object_rotation_local,
    ALEC_OT_selection_rotate,
    ALEC_OT_selection_translate_delta,
    ALEC_OT_selection_resize_orient,
    ALEC_OT_selection_scale_orient,
    ALEC_OT_reset_transform_column,
)
# Înainte de panel: operatori + PropertyGroup; apoi proprietăți Scene; apoi panel (vezi register).
_classes_pre_panel = (*_classes_operators, AlecEditSelectionProps)

classes = (*_classes_pre_panel, ALEC_PT_alec_transform)


def register():
    global _depsgraph_handler
    for cls in _classes_pre_panel:
        bpy.utils.register_class(cls)
    bpy.types.Scene.alec_edit_selection = bpy.props.PointerProperty(type=AlecEditSelectionProps)
    bpy.types.Scene.alec_object_world = bpy.props.FloatVectorProperty(
        name="World",
        description="Object translation in world space",
        size=3,
        subtype="TRANSLATION",
        update=_update_alec_object_world,
    )
    bpy.types.Scene.alec_rotation_world = bpy.props.FloatVectorProperty(
        name="World rotation",
        description="Euler XYZ = rotație world (ca Transform Orientation Global + R X/Y/Z)",
        size=3,
        subtype="EULER",
        update=_update_alec_rotation_world,
    )
    bpy.types.Scene.alec_rotation_local = bpy.props.FloatVectorProperty(
        name="Orient rotation",
        description="Euler XYZ în spațiul Transform Orientation (header viewport, slot 0)",
        size=3,
        subtype="EULER",
        update=_update_alec_rotation_local,
    )
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
    for cls in reversed(_classes_operators):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.alec_object_world
    del bpy.types.Scene.alec_rotation_world
    del bpy.types.Scene.alec_rotation_local
    del bpy.types.Scene.alec_edit_selection
    bpy.utils.unregister_class(AlecEditSelectionProps)
