"""PropertyGroup + RNA update callbacks for Transform."""

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from . import selection_math as sm

def _update_alec_object_world(self, context):
    if sm._alec_syncing_world:
        return
    obj = context.active_object
    if obj is None:
        return
    target = Vector(self.alec_object_world)
    if not sm._invoke_object_world_translation(context, target):
        sm._undo_push(context, "Alec: world location")
        mw = obj.matrix_world.copy()
        mw.translation = target
        obj.matrix_world = mw


def _update_alec_rotation_world(self, context):
    if sm._alec_syncing_world:
        return
    obj = context.active_object
    if obj is None:
        return
    if context.mode == "EDIT_MESH":
        return
    eu = Vector(self.alec_rotation_world)
    if not sm._invoke_object_rotation_world(context, eu):
        sm._undo_push(context, "Alec: world rotation")
        mw = obj.matrix_world
        loc = mw.translation
        scale = mw.to_scale()
        euler = Euler(eu, "XYZ")
        obj.matrix_world = Matrix.LocRotScale(loc, euler, scale)


def _update_alec_rotation_local(self, context):
    """Euler XYZ din matrix_local; nu depinde de rotation_mode (quaternion etc.)."""
    if sm._alec_syncing_world:
        return
    obj = context.active_object
    if obj is None:
        return
    if context.mode == "EDIT_MESH":
        return
    eu = Vector(self.alec_rotation_local)
    st = sm._transform_slot_type(context)
    if not sm._invoke_object_rotation_local(context, eu, st):
        sm._undo_push(context, "Alec: orient rotation")
        sm._apply_euler_orientation(context, obj, eu, st)
        sm._sync_object_world_from_active(context)


def _update_mean_w(self, context):
    if sm._alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    positions = sm._selected_vert_positions_world(context, obj, obj.data)
    if not positions:
        return
    cur = sm._mean(positions)
    if cur is None:
        return
    target = Vector(self.mean_w)
    delta = target - cur
    if delta.length < 1e-10:
        return
    if not sm._invoke_selection_translate_delta(context, delta):
        sm._undo_push(context, "Alec: selection mean")
        sm._apply_translation_world(context, obj, delta)
        sm._sync_selection_props_from_mesh(context, self)


def _update_mean_local(self, context):
    if sm._alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    mesh = obj.data
    cur = sm._mean_local_selected(obj, mesh)
    if cur is None:
        return
    target = Vector(self.mean_local)
    delta_local = target - cur
    if delta_local.length < 1e-10:
        return
    delta_w = sm._mesh_local_delta_to_world(obj, cur, delta_local)
    if delta_w.length < 1e-10:
        return
    if not sm._invoke_selection_translate_delta(context, delta_w):
        sm._undo_push(context, "Alec: selection local")
        sm._apply_translation_world(context, obj, delta_w)
        sm._sync_selection_props_from_mesh(context, self)


def _update_bbox_center_w(self, context):
    if sm._alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    mesh = obj.data
    ob = sm._oriented_bbox_from_selection(context, obj, mesh)
    if ob is None:
        return
    _O, _mn, _mx, _d, cur = ob
    target = Vector(self.bbox_center_w)
    delta = target - cur
    if delta.length < 1e-10:
        return
    if not sm._invoke_selection_translate_delta(context, delta):
        sm._undo_push(context, "Alec: bbox center")
        sm._apply_translation_world(context, obj, delta)
        sm._sync_selection_props_from_mesh(context, self)


def _update_sel_dims_orient(self, context):
    if sm._alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    mesh = obj.data
    ob = sm._oriented_bbox_from_selection(context, obj, mesh)
    if ob is None:
        return
    _O, _mn, _mx, old_dims, _cw = ob
    new_dims = Vector(self.sel_dims_orient)
    if (new_dims - old_dims).length < 1e-10:
        return
    if not sm._invoke_selection_resize_orient(context, new_dims):
        sm._undo_push(context, "Alec: selection dimensions")
        sm._apply_resize_orientation(context, obj, new_dims)
        sm._sync_selection_props_from_mesh(context, self)


def _update_sel_scale_orient(self, context):
    if sm._alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    if not sm._selected_vert_positions_world(context, obj, obj.data):
        return
    sid = id(context.scene)
    curr = Vector(self.sel_scale_orient)
    prev = sm._sel_scale_last_ui_by_scene.get(sid, Vector((1.0, 1.0, 1.0)))
    ratio = Vector(
        (
            curr.x / prev.x if abs(prev.x) > 1e-12 else 1.0,
            curr.y / prev.y if abs(prev.y) > 1e-12 else 1.0,
            curr.z / prev.z if abs(prev.z) > 1e-12 else 1.0,
        )
    )
    if (ratio - Vector((1.0, 1.0, 1.0))).length < 1e-10:
        return
    if not sm._invoke_selection_scale_orient(context, ratio):
        sm._undo_push(context, "Alec: selection scale")
        sm._apply_scale_orientation(context, obj, ratio)
        sm._sync_selection_props_from_mesh(context, self)
    sm._sel_scale_last_ui_by_scene[sid] = curr.copy()


def _update_sel_rot_world_euler(self, context):
    if sm._alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    if not sm._selected_vert_positions_world(context, obj, obj.data):
        return
    sm._ensure_selection_rotation_rest(context, self, obj.data)
    eu = Vector(self.sel_rot_world_euler)
    q = Euler(eu, "XYZ").to_quaternion()
    if sm._invoke_selection_rotate(context, q):
        return
    sm._undo_push(context, "Alec: selection rotate")
    sm._apply_selection_rotation_quat(context, obj, q)
    self.sel_rot_quat = (q.w, q.x, q.y, q.z)
    sm._sync_sel_rot_eulers_from_quat(context, self)


def _update_sel_rot_orient_euler(self, context):
    if sm._alec_syncing:
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH" or context.mode != "EDIT_MESH":
        return
    if not sm._selected_vert_positions_world(context, obj, obj.data):
        return
    sm._ensure_selection_rotation_rest(context, self, obj.data)
    eu_o = Vector(self.sel_rot_orient_euler)
    st = sm._transform_slot_type(context)
    R_o = Euler(eu_o, "XYZ").to_matrix()
    if st == "GLOBAL":
        R_w = R_o
    elif st in ("LOCAL", "GIMBAL", "NORMAL"):
        _loc, rot, _sc = obj.matrix_world.decompose()
        O = rot.to_matrix()
        R_w = O @ R_o @ O.transposed()
    else:
        O = sm._orientation_basis_3x3(context, obj, st)
        R_w = O @ R_o @ O.transposed()
    q = R_w.to_quaternion().normalized()
    if sm._invoke_selection_rotate(context, q):
        return
    sm._undo_push(context, "Alec: selection rotate")
    sm._apply_selection_rotation_quat(context, obj, q)
    self.sel_rot_quat = (q.w, q.x, q.y, q.z)
    sm._sync_sel_rot_eulers_from_quat(context, self)


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
