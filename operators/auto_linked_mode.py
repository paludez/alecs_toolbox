import bmesh
import bpy
import traceback

from .mesh_selection_helpers import _bmesh_select_linked_island, _bmesh_subtract_linked_islands

# --- Auto-linked mode: timer poll (depsgraph does not run on selection-only edits) ---
_auto_linked_active = False
_last_sel_hash: tuple | None = None
_applying_linked = False
_wm_timer = None
_ctrl_held = False
_pending_ctrl_subtract = False


def _vert_selection_hash(mesh) -> tuple:
    bm = bmesh.from_edit_mesh(mesh)
    try:
        bm.verts.ensure_lookup_table()
        return tuple(sorted(v.index for v in bm.verts if v.select))
    finally:
        bm.free()


def _tick_auto_linked(context):
    """Compare selection to last hash; expand linked, linked-subtract (Ctrl), or keep Blender result."""
    if not _auto_linked_active or _applying_linked:
        return
    try:
        _tick_auto_linked_impl(context)
    except Exception:
        traceback.print_exc()


def _tick_auto_linked_impl(context):
    """Inner tick: bmesh ops can raise if mesh/mode changes mid-frame."""
    global _last_sel_hash, _applying_linked, _pending_ctrl_subtract
    if context.mode != "EDIT_MESH":
        return
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return

    mesh = obj.data
    h = _vert_selection_hash(mesh)
    if h == _last_sel_hash:
        return

    if not h:
        _last_sel_hash = h
        _pending_ctrl_subtract = False
        return

    # Stale pending: only valid for a shrink; discard if selection grew or changed non-monotonically
    if _last_sel_hash is not None and not (set(h) < set(_last_sel_hash)):
        _pending_ctrl_subtract = False

    if _last_sel_hash is not None and set(h) < set(_last_sel_hash):
        _applying_linked = True
        try:
            if _pending_ctrl_subtract or _ctrl_held:
                _bmesh_subtract_linked_islands(mesh, set(_last_sel_hash), set(h))
            _last_sel_hash = _vert_selection_hash(mesh)
        finally:
            _applying_linked = False
        _pending_ctrl_subtract = False
        if context.area:
            context.area.tag_redraw()
        return

    _applying_linked = True
    try:
        _bmesh_select_linked_island(mesh)
        _last_sel_hash = _vert_selection_hash(mesh)
    finally:
        _applying_linked = False
    _pending_ctrl_subtract = False

    if context.area:
        context.area.tag_redraw()


def _timer_start(context):
    global _wm_timer
    if _wm_timer is not None:
        return
    if context.window is None:
        return
    wm = context.window_manager
    _wm_timer = wm.event_timer_add(0.02, window=context.window)


def _timer_stop(context=None):
    global _wm_timer
    if _wm_timer is None:
        return
    ctx = context or bpy.context
    if ctx and getattr(ctx, "window_manager", None):
        try:
            ctx.window_manager.event_timer_remove(_wm_timer)
        except Exception:
            pass
    _wm_timer = None


def _enter_auto_linked(context):
    global _auto_linked_active, _last_sel_hash, _ctrl_held, _pending_ctrl_subtract
    _auto_linked_active = True
    _ctrl_held = False
    _pending_ctrl_subtract = False
    obj = context.active_object
    if obj and obj.type == "MESH":
        try:
            _last_sel_hash = _vert_selection_hash(obj.data)
        except Exception:
            _last_sel_hash = None
    else:
        _last_sel_hash = None


def _exit_auto_linked(context=None):
    global _auto_linked_active, _last_sel_hash, _ctrl_held, _pending_ctrl_subtract
    _auto_linked_active = False
    _last_sel_hash = None
    _ctrl_held = False
    _pending_ctrl_subtract = False
    _timer_stop(context)


class ALEC_OT_auto_linked_select_mode(bpy.types.Operator):
    """Grow: expand to linked. Ctrl+shrink: remove full linked island of subtracted verts from prior selection."""

    bl_idname = "alec.auto_linked_select_mode"
    bl_label = "Auto Linked Select Mode"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def invoke(self, context, event):
        if context.mode != "EDIT_MESH":
            self.report({"WARNING"}, "Use in Edit Mode")
            return {"CANCELLED"}
        if context.window is None:
            self.report({"WARNING"}, "No active window")
            return {"CANCELLED"}
        _enter_auto_linked(context)
        context.window_manager.modal_handler_add(self)
        _timer_start(context)
        self.report({"INFO"}, "Auto linked: 4 or Esc to exit")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        global _ctrl_held, _pending_ctrl_subtract

        if event.type == "TIMER":
            _tick_auto_linked(context)
            return {"RUNNING_MODAL"}

        _ctrl_held = getattr(event, "ctrl", False)
        if event.type in {"LEFTMOUSE", "SELECTMOUSE"} and event.value == "RELEASE" and _ctrl_held:
            _pending_ctrl_subtract = True

        if context.mode != "EDIT_MESH":
            _exit_auto_linked(context)
            return {"FINISHED"}

        obj = context.active_object
        if obj is None or obj.type != "MESH":
            _exit_auto_linked(context)
            return {"FINISHED"}

        if event.type in {"ESC"} and event.value == "PRESS":
            _exit_auto_linked(context)
            self.report({"INFO"}, "Auto linked mode off")
            return {"FINISHED"}

        if event.type == "FOUR" and event.value == "PRESS":
            _exit_auto_linked(context)
            self.report({"INFO"}, "Auto linked mode off")
            return {"FINISHED"}

        return {"PASS_THROUGH"}


classes = (ALEC_OT_auto_linked_select_mode,)
