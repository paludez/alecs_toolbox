"""Poll and bmesh helpers for edit-mesh operators."""
import bmesh
from mathutils import Vector, Matrix

from . import edit_curve_helpers as ech


def edit_mesh_transform_pivot_world(context, obj, bm):
    """
    World-space pivot matching Tool Settings → Transform Pivot Point (Edit Mesh).
    INDIVIDUAL_ORIGINS is approximated with the median of the current selection
    (full per-island pivots would require loose-part detection).
    """
    pivot_type = context.scene.tool_settings.transform_pivot_point
    mw = obj.matrix_world
    sel_verts = [v for v in bm.verts if v.select]

    if pivot_type == 'CURSOR':
        return context.scene.cursor.location.copy()

    if pivot_type == 'ACTIVE_ELEMENT':
        active = bm.select_history.active
        if isinstance(active, bmesh.types.BMVert):
            return mw @ active.co
        if isinstance(active, bmesh.types.BMEdge):
            v0, v1 = active.verts
            return (mw @ v0.co + mw @ v1.co) * 0.5
        if isinstance(active, bmesh.types.BMFace):
            return mw @ active.calc_center_median()
        if sel_verts:
            acc = Vector((0.0, 0.0, 0.0))
            for v in sel_verts:
                acc += mw @ v.co
            return acc / len(sel_verts)
        return mw.translation.copy()

    if pivot_type == 'BOUNDING_BOX_CENTER':
        if not sel_verts:
            return mw.translation.copy()
        ws = [mw @ v.co for v in sel_verts]
        xs = [p.x for p in ws]
        ys = [p.y for p in ws]
        zs = [p.z for p in ws]
        return Vector(
            (
                (min(xs) + max(xs)) * 0.5,
                (min(ys) + max(ys)) * 0.5,
                (min(zs) + max(zs)) * 0.5,
            )
        )

    if pivot_type in {'MEDIAN_POINT', 'INDIVIDUAL_ORIGINS'}:
        if not sel_verts:
            return mw.translation.copy()
        acc = Vector((0.0, 0.0, 0.0))
        for v in sel_verts:
            acc += mw @ v.co
        return acc / len(sel_verts)

    return mw.translation.copy()


def scale_object_uniform_world_around_pivot(obj, factor, pivot_world):
    """Apply uniform world-space scale factor around pivot via matrix_world."""
    k = factor
    S = Matrix.Identity(4)
    S[0][0] = S[1][1] = S[2][2] = k
    T = Matrix.Translation(pivot_world)
    Ti = Matrix.Translation(-pivot_world)
    obj.matrix_world = T @ S @ Ti @ obj.matrix_world


def select_history_edges(bm):
    return [elem for elem in bm.select_history if isinstance(elem, bmesh.types.BMEdge)]


def select_history_verts(bm):
    return [elem for elem in bm.select_history if isinstance(elem, bmesh.types.BMVert)]


def get_active_or_latest_selected_edge(bm):
    """Active edge from select history, else last selected edge, else None."""
    active_edge = bm.select_history.active
    if isinstance(active_edge, bmesh.types.BMEdge):
        return active_edge
    selected_edges = [e for e in bm.edges if e.select]
    if selected_edges:
        return selected_edges[-1]
    return None


def get_equalize_reference_edge(bm):
    """Edge used as length reference for equalize (active in history or sole selected edge)."""
    active_elem = bm.select_history.active
    if isinstance(active_elem, bmesh.types.BMEdge):
        return active_elem
    sel_edges = [e for e in bm.edges if e.select]
    if len(sel_edges) == 1:
        return sel_edges[0]
    return None


def poll_two_edges_in_select_history(context):
    if not (context.active_object and context.mode == 'EDIT_MESH'):
        return False
    try:
        bm = bmesh.from_edit_mesh(context.active_object.data)
        return len(select_history_edges(bm)) >= 2
    except:  # noqa: E722 — match prior operator poll (any failure -> disabled)
        return False


def edge_pair_from_select_history(bm):
    """
    Return (edge_moving, edge_stationary) from select history, or (None, None) if invalid.
    Last selected edge is stationary; previous is moving (same convention as set_edge_angle).
    """
    history = select_history_edges(bm)
    if len(history) < 2:
        return None, None
    return history[-2], history[-1]


def angle_pivot_for_edge_pair(stationary_edge, moving_edge):
    """
    Common vertex, angle in radians between edge directions, or (None, None, None) if not measurable.
    """
    common_verts = set(stationary_edge.verts) & set(moving_edge.verts)
    if not common_verts:
        return None, None, None
    pivot = common_verts.pop()
    v_stat = [v for v in stationary_edge.verts if v != pivot][0]
    v_mov = [v for v in moving_edge.verts if v != pivot][0]
    t0 = (v_stat.co - pivot.co).normalized()
    t1 = (v_mov.co - pivot.co).normalized()
    if t0.length < 1e-9 or t1.length < 1e-9:
        return None, None, None
    if t0.cross(t1).length < 1e-6:
        return None, None, None
    return pivot.co.copy(), t0.angle(t1), (moving_edge.index, stationary_edge.index)


def poll_active_mesh_edit_mode(context):
    return (
        context.active_object is not None
        and context.active_object.type == 'MESH'
        and context.mode == 'EDIT_MESH'
    )


def poll_mesh_or_curve_collinear_coplanar(context):
    return poll_active_mesh_edit_mode(context) or ech.poll_active_curve_edit_mode(context)


def poll_edit_mesh_mode_only(context):
    return context.mode == 'EDIT_MESH'


def poll_clean_mesh(context):
    return bool(context.active_object and context.mode == 'EDIT_MESH')


def poll_extract_and_solidify(context):
    return context.mode == 'EDIT_MESH' and context.active_object


def poll_make_circle(context):
    return bool(
        context.active_object
        and context.active_object.type == 'MESH'
        and context.mode == 'EDIT_MESH'
    )
