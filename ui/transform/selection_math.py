"""Transform: math, bmesh, invokes, reset column logic."""

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


def _invoke_selection_rotate(context, q: Quaternion) -> bool:
    r = (q.w, q.x, q.y, q.z)
    return _invoke_alec_op(context, "alec.selection_rotate", rotation=r)
