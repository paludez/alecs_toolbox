"""Poll and bmesh helpers for edit-mesh operators."""
import bmesh

from . import edit_curve_helpers as ech


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
