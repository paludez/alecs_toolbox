"""Transform orientation slot 0 → 3×3 basis in world space (used by Draw Mesh Edges, etc.)."""

from mathutils import Matrix


def _transform_slot_type(context) -> str:
    try:
        return context.scene.transform_orientation_slots[0].type
    except Exception:
        return "GLOBAL"


def _rot3_world(obj) -> Matrix:
    _loc, rot, _sc = obj.matrix_world.decompose()
    return rot.to_matrix()


def _orientation_basis_3x3(context, _obj, slot_type: str) -> Matrix:
    """Orthonormal basis (columns = axes in world) for VIEW / CURSOR / CUSTOM."""
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


def orientation_matrix_world(context, obj) -> Matrix:
    """3×3 basis (columns = orientation axes in world) for Transform Orientation slot 0."""
    st = _transform_slot_type(context)
    if st == "GLOBAL":
        return Matrix.Identity(3)
    if st in ("LOCAL", "GIMBAL", "NORMAL"):
        return _rot3_world(obj)
    return _orientation_basis_3x3(context, obj, st)
