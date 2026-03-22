"""BMesh helpers for auto-linked selection and the open-edge grow operator."""
import bmesh
import bpy
from collections import deque


def _collect_seed_verts(bm: bmesh.types.BMesh) -> set:
    """Vertss implied by current edit selection (verts, edges, or faces)."""
    seeds: set = set()
    for v in bm.verts:
        if v.select:
            seeds.add(v)
    for e in bm.edges:
        if e.select:
            seeds.update(e.verts)
    for f in bm.faces:
        if f.select:
            seeds.update(f.verts)
    return seeds


def _bmesh_select_linked_island(mesh) -> bool:
    """
    Select the full connected geometry island(s) containing the current selection.
    Does not depend on mesh_select_mode (unlike bpy.ops.mesh.select_linked).
    """
    bm = bmesh.from_edit_mesh(mesh)
    try:
        seeds = _collect_seed_verts(bm)
        if not seeds:
            return False
        visited: set = set()
        dq = deque(seeds)
        while dq:
            v = dq.popleft()
            if v in visited:
                continue
            visited.add(v)
            for e in v.link_edges:
                ov = e.other_vert(v)
                if ov not in visited:
                    dq.append(ov)
        for v in bm.verts:
            v.select_set(v in visited)
        for e in bm.edges:
            e.select_set(e.verts[0] in visited and e.verts[1] in visited)
        for f in bm.faces:
            f.select_set(all(v in visited for v in f.verts))
        bm.select_flush_mode()
        bmesh.update_edit_mesh(mesh)
        return True
    finally:
        bm.free()


def _bmesh_subtract_linked_islands(mesh, old_vert_indices: set, new_vert_indices: set) -> bool:
    """
    After a subtract (new ⊂ old), remove the full mesh-connected region of verts in (old - new)
    from the previous selection: final = old - flood_fill(old - new).
    """
    removed = old_vert_indices - new_vert_indices
    if not removed:
        return False
    bm = bmesh.from_edit_mesh(mesh)
    try:
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        seeds = [bm.verts[i] for i in removed if 0 <= i < len(bm.verts)]
        if not seeds:
            return False
        visited: set = set()
        dq = deque(seeds)
        while dq:
            v = dq.popleft()
            if v in visited:
                continue
            visited.add(v)
            for e in v.link_edges:
                ov = e.other_vert(v)
                if ov not in visited:
                    dq.append(ov)
        remove_idx = {v.index for v in visited}
        sel_idx = old_vert_indices - remove_idx
        for v in bm.verts:
            v.select_set(v.index in sel_idx)
        for e in bm.edges:
            e.select_set(e.verts[0].index in sel_idx and e.verts[1].index in sel_idx)
        for f in bm.faces:
            f.select_set(all(v.index in sel_idx for v in f.verts))
        bm.select_flush_mode()
        bmesh.update_edit_mesh(mesh)
        return True
    finally:
        bm.free()


def _boundary_edge_seeds(bm: bmesh.types.BMesh) -> list:
    """Open/boundary edges touched by the current selection (edge, vert, or boundary face)."""
    seeds = []
    for e in bm.edges:
        if len(e.link_faces) != 1:
            continue
        if e.select:
            seeds.append(e)
            continue
        if any(v.select for v in e.verts):
            seeds.append(e)
            continue
        if e.link_faces[0].select:
            seeds.append(e)
    return seeds


def _expand_boundary_component(bm: bmesh.types.BMesh, seeds: list) -> set:
    """Return set of BMEdge; BFS uses identity only while the same `bm` is active."""
    visited: set = set()
    dq = deque(seeds)
    while dq:
        e = dq.popleft()
        if e in visited:
            continue
        if len(e.link_faces) != 1:
            continue
        visited.add(e)
        for v in e.verts:
            for le in v.link_edges:
                if le in visited or len(le.link_faces) != 1:
                    continue
                dq.append(le)
    return visited


def _apply_edge_component_selection(bm: bmesh.types.BMesh, component: set) -> None:
    """Apply edge (and endpoint vert) selection by index — BMEdge `in set` can mismatch `bm.edges` iteration."""
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    edge_idx = {e.index for e in component}
    vert_idx: set = set()
    for e in component:
        for v in e.verts:
            vert_idx.add(v.index)
    # In bmesh, deselecting faces after edges are selected clears edge/vert selection; clear faces first.
    for f in bm.faces:
        f.select_set(False)
    for v in bm.verts:
        v.select_set(v.index in vert_idx)
    for e in bm.edges:
        e.select_set(e.index in edge_idx)


class ALEC_OT_mesh_select_open_edges_connected(bpy.types.Operator):
    """Expand selection along connected open (boundary) edges."""
    bl_idname = "alec.mesh_select_open_edges_connected"
    bl_label = "Select Connected Open Edges"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, "Select an active mesh object")
            return {'CANCELLED'}
        if context.mode != 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')

        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        seeds = _boundary_edge_seeds(bm)
        if not seeds:
            bm.free()
            self.report({'WARNING'}, "Select at least one open (boundary) edge")
            return {'CANCELLED'}

        component = _expand_boundary_component(bm, seeds)
        _apply_edge_component_selection(bm, component)

        context.tool_settings.mesh_select_mode = (False, True, False)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(mesh)
        bm.free()

        return {'FINISHED'}


classes = (ALEC_OT_mesh_select_open_edges_connected,)
