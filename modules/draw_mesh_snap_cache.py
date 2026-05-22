"""Screen-space snap acceleration for draw-mesh-edges (KD-tree + rebuild limits)."""
from __future__ import annotations

from dataclasses import dataclass
from mathutils import Vector
from mathutils.kdtree import KDTree
from bpy_extras.view3d_utils import location_3d_to_region_2d

# Above these counts, rebuild only when the view/mesh changes (not every mousemove).
OBJ_SNAP_KDTREE_MIN = 256
WORLD_SNAP_MAX_VERTS_PER_OBJECT = 12_000
WORLD_SNAP_MAX_VERTS_TOTAL = 40_000


@dataclass(frozen=True)
class SnapHit:
    world: Vector
    snap_idx: int
    raw_world: Vector | None = None


def _view_cache_key(region, rv3d) -> tuple:
    if region is None or rv3d is None:
        return ()
    try:
        vm = tuple(rv3d.view_matrix[i][j] for i in range(4) for j in range(4))
        pm = tuple(rv3d.perspective_matrix[i][j] for i in range(4) for j in range(4))
        return (id(region), vm, pm, region.width, region.height)
    except Exception:
        return (id(region),)


def _project(region, rv3d, world_co: Vector):
    try:
        return location_3d_to_region_2d(region, rv3d, world_co)
    except Exception:
        return None


def _occlusion_test_co(hit: SnapHit) -> Vector:
    """World snap: test depth at the visible vertex, not the plane-projected point."""
    if hit.raw_world is not None:
        return hit.raw_world
    return hit.world


def world_snap_cache_key(context) -> tuple:
    """Rebuild when cursor plane or scene objects change."""
    cur = context.scene.cursor
    loc = tuple(round(c, 5) for c in cur.location)
    try:
        rot = tuple(round(cur.rotation_euler[i], 5) for i in range(3))
    except Exception:
        rot = ()
    return (loc, rot, tuple(context.scene.objects.keys()))


def _build_kdtree(screen_pts: list[tuple[float, float]]) -> KDTree | None:
    """Blender KDTree requires capacity = insert count (set at construction)."""
    n = len(screen_pts)
    if n == 0:
        return None
    tree = KDTree(n)
    for i, (sx, sy) in enumerate(screen_pts):
        tree.insert((sx, sy, 0.0), i)
    tree.balance()
    return tree


class DrawMeshSnapCache:
    """2D KD-trees for object / world snap; invalidated on view or mesh topology change."""

    def __init__(self) -> None:
        self._obj_tree: KDTree | None = None
        self._obj_hits: list[SnapHit] = []
        self._obj_key: tuple = ()
        self._world_tree: KDTree | None = None
        self._world_hits: list[SnapHit] = []
        self._world_key: tuple = ()
        self._world_truncated: bool = False

    @property
    def world_snap_truncated(self) -> bool:
        return self._world_truncated

    def invalidate_all(self) -> None:
        self._obj_tree = None
        self._obj_hits.clear()
        self._obj_key = ()
        self._world_tree = None
        self._world_hits.clear()
        self._world_key = ()
        self._world_truncated = False

    def invalidate_mesh(self) -> None:
        self._obj_tree = None
        self._obj_hits.clear()
        self._obj_key = ()

    def invalidate_world(self) -> None:
        self._world_tree = None
        self._world_hits.clear()
        self._world_key = ()

    def find_best(
        self,
        coord,
        radius_px: float,
        occlusion_t: float | None,
        origin_w: Vector,
        dir_w: Vector,
        context,
        occludes_fn,
        *,
        use_obj: bool,
        use_world: bool,
    ) -> SnapHit | None:
        radius_sq = radius_px * radius_px
        mx, my = float(coord[0]), float(coord[1])
        center = (mx, my, 0.0)
        best_d2 = radius_sq
        best: SnapHit | None = None

        if use_obj and self._obj_tree is not None:
            for _co, idx, dist in self._obj_tree.find_range(center, radius_px):
                d2 = dist * dist
                if d2 >= best_d2:
                    continue
                hit = self._obj_hits[idx]
                if occludes_fn(occlusion_t, origin_w, dir_w, _occlusion_test_co(hit), context):
                    continue
                best_d2 = d2
                best = hit

        if use_world and self._world_tree is not None:
            for _co, idx, dist in self._world_tree.find_range(center, radius_px):
                d2 = dist * dist
                if d2 >= best_d2:
                    continue
                hit = self._world_hits[idx]
                if occludes_fn(occlusion_t, origin_w, dir_w, _occlusion_test_co(hit), context):
                    continue
                best_d2 = d2
                best = hit

        return best

    def ensure_obj(
        self,
        bm,
        matrix_world,
        region,
        rv3d,
        mesh_key: tuple,
        *,
        include_verts: bool,
        include_edge_mids: bool,
    ) -> None:
        view_key = _view_cache_key(region, rv3d)
        key = (view_key, mesh_key, include_verts, include_edge_mids)
        if self._obj_tree is not None and key == self._obj_key:
            return

        hits: list[SnapHit] = []
        screen_pts: list[tuple[float, float]] = []
        mw = matrix_world

        if include_verts:
            for v in bm.verts:
                p2 = _project(region, rv3d, mw @ v.co)
                if p2 is None:
                    continue
                hits.append(SnapHit(mw @ v.co, v.index, None))
                screen_pts.append((p2.x, p2.y))

        if include_edge_mids:
            for e in bm.edges:
                mid = (e.verts[0].co + e.verts[1].co) * 0.5
                p2 = _project(region, rv3d, mw @ mid)
                if p2 is None:
                    continue
                hits.append(SnapHit(mw @ mid, -2, None))
                screen_pts.append((p2.x, p2.y))

        self._obj_tree = _build_kdtree(screen_pts)
        self._obj_hits = hits
        self._obj_key = key

    def ensure_world(
        self,
        context,
        depsgraph,
        region,
        rv3d,
        draw_obj,
        *,
        ignore_draw_plane: bool,
        world_key: tuple,
    ) -> None:
        from . import cursor_plane as cp

        view_key = _view_cache_key(region, rv3d)
        key = (view_key, world_key, ignore_draw_plane, id(draw_obj))
        if self._world_tree is not None and key == self._world_key:
            return

        hits: list[SnapHit] = []
        screen_pts: list[tuple[float, float]] = []
        total = 0
        truncated = False

        if depsgraph is not None:
            for obj_inst in depsgraph.object_instances:
                if total >= WORLD_SNAP_MAX_VERTS_TOTAL:
                    truncated = True
                    break
                obj_eval = obj_inst.object
                if obj_eval is None or obj_eval.type != 'MESH':
                    continue
                try:
                    obj_orig = obj_eval.original
                except Exception:
                    obj_orig = obj_eval
                if obj_orig is draw_obj:
                    continue
                try:
                    vl = getattr(context, 'view_layer', None)
                    if vl is None:
                        vis_ok = obj_orig.visible_get()
                    else:
                        try:
                            vis_ok = obj_orig.visible_get(view_layer=vl)
                        except TypeError:
                            vis_ok = obj_orig.visible_get()
                    if not vis_ok:
                        continue
                except Exception:
                    pass
                try:
                    eval_mesh = obj_eval.data
                except Exception:
                    continue
                if eval_mesh is None:
                    continue
                try:
                    verts = eval_mesh.vertices
                except Exception:
                    continue
                n = len(verts)
                if n > WORLD_SNAP_MAX_VERTS_PER_OBJECT:
                    truncated = True
                    continue
                if total + n > WORLD_SNAP_MAX_VERTS_TOTAL:
                    truncated = True
                    n = WORLD_SNAP_MAX_VERTS_TOTAL - total
                inst_mw = obj_inst.matrix_world
                for i in range(n):
                    v = verts[i]
                    v_world = inst_mw @ v.co
                    if ignore_draw_plane:
                        snap_w = v_world.copy()
                        raw = None
                    else:
                        snap_w = cp.project_onto_cursor_plane(context, v_world)
                        raw = v_world.copy()
                    # KD search by where the vertex appears on screen (not plane projection).
                    p2 = _project(region, rv3d, v_world)
                    if p2 is None:
                        continue
                    hits.append(SnapHit(snap_w, -3, raw))
                    screen_pts.append((p2.x, p2.y))
                total += n

        self._world_tree = _build_kdtree(screen_pts)
        self._world_hits = hits
        self._world_key = key
        self._world_truncated = truncated


def mesh_topology_key(me, bm) -> tuple:
    try:
        return (me.name, len(bm.verts), len(bm.edges))
    except Exception:
        return (getattr(me, 'name', ''), 0, 0)


def should_use_obj_kdtree(bm) -> bool:
    try:
        n = len(bm.verts) + len(bm.edges)
    except Exception:
        return False
    return n >= OBJ_SNAP_KDTREE_MIN
