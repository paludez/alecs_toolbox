"""Screen-space snap acceleration for draw-mesh-edges (KD-tree + rebuild limits)."""
from __future__ import annotations

from dataclasses import dataclass
from mathutils import Vector
from mathutils.kdtree import KDTree
from bpy_extras.view3d_utils import location_3d_to_region_2d

# Defaults when addon preferences are unavailable.
_DEFAULT_OBJ_SNAP_KDTREE_MIN = 256
_DEFAULT_WORLD_SNAP_MAX_VERTS_PER_OBJECT = 12_000
_DEFAULT_WORLD_SNAP_MAX_VERTS_TOTAL = 40_000


def _snap_prefs():
    try:
        from .. import preferences

        return preferences.prefs()
    except Exception:
        return None


def obj_snap_kdtree_min() -> int:
    p = _snap_prefs()
    if p is not None:
        return max(1, int(p.draw_mesh_snap_kdtree_min_elements))
    return _DEFAULT_OBJ_SNAP_KDTREE_MIN


def world_snap_max_verts_per_object() -> int:
    p = _snap_prefs()
    if p is not None:
        return max(1, int(p.draw_mesh_snap_max_verts_per_object))
    return _DEFAULT_WORLD_SNAP_MAX_VERTS_PER_OBJECT


def world_snap_max_verts_total() -> int:
    p = _snap_prefs()
    if p is not None:
        return max(1, int(p.draw_mesh_snap_max_verts_total))
    return _DEFAULT_WORLD_SNAP_MAX_VERTS_TOTAL


@dataclass(frozen=True)
class SnapHit:
    world: Vector
    snap_idx: int
    raw_world: Vector | None = None


# snap_idx sentinels (draw_mesh_edges / edit_mesh_draw_state)
SNAP_IDX_EDGE_MID = -2
SNAP_IDX_WORLD_VERT = -3
SNAP_IDX_EDGE_PERP = -4


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


def screen_dist_sq(region, rv3d, coord, world_co: Vector) -> float | None:
    p2 = _project(region, rv3d, world_co)
    if p2 is None:
        return None
    mx, my = float(coord[0]), float(coord[1])
    dx = p2.x - mx
    dy = p2.y - my
    return dx * dx + dy * dy


def edge_line_perpendicular_foot(
    prev_world: Vector,
    v0_world: Vector,
    v1_world: Vector,
) -> Vector | None:
    """Foot on the infinite line through v0–v1 closest to prev_world (perpendicular from prev)."""
    d = v1_world - v0_world
    ll = d.length_squared
    if ll < 1e-20:
        return None
    t = (prev_world - v0_world).dot(d) / ll
    return v0_world + d * t


def pick_closer_snap_hit(
    region,
    rv3d,
    coord,
    a: SnapHit | None,
    b: SnapHit | None,
) -> SnapHit | None:
    if a is None:
        return b
    if b is None:
        return a
    da = screen_dist_sq(region, rv3d, coord, a.world)
    db = screen_dist_sq(region, rv3d, coord, b.world)
    if da is None:
        return b
    if db is None:
        return a
    return a if da <= db else b


def best_obj_perpendicular_snap(
    bm,
    matrix_world,
    region,
    rv3d,
    coord,
    radius_px: float,
    prev_world: Vector,
    occludes_fn,
    occlusion_t: float | None,
    origin_w: Vector,
    dir_w: Vector,
    context,
) -> SnapHit | None:
    """Screen-closest perpendicular foot on any mesh edge (from prev_world onto edge line)."""
    radius_sq = radius_px * radius_px
    best_d2 = radius_sq
    best: SnapHit | None = None
    mw = matrix_world

    for e in bm.edges:
        try:
            v0w = mw @ e.verts[0].co
            v1w = mw @ e.verts[1].co
        except Exception:
            continue
        foot = edge_line_perpendicular_foot(prev_world, v0w, v1w)
        if foot is None:
            continue
        if occludes_fn(occlusion_t, origin_w, dir_w, foot, context):
            continue
        d2 = screen_dist_sq(region, rv3d, coord, foot)
        if d2 is None or d2 >= best_d2:
            continue
        best_d2 = d2
        best = SnapHit(foot, SNAP_IDX_EDGE_PERP, None)

    return best


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
                hits.append(SnapHit(mw @ mid, SNAP_IDX_EDGE_MID, None))
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
                if total >= world_snap_max_verts_total():
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
                if n > world_snap_max_verts_per_object():
                    truncated = True
                    continue
                max_total = world_snap_max_verts_total()
                if total + n > max_total:
                    truncated = True
                    n = max_total - total
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
                    hits.append(SnapHit(snap_w, SNAP_IDX_WORLD_VERT, raw))
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
    return n >= obj_snap_kdtree_min()
