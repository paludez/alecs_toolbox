import bmesh
import bpy

from .mesh_select_expand import _bmesh_select_linked_island

# --- Auto-linked mode state (depsgraph-driven; box select commits on release in Blender) ---
_auto_linked_active = False
_last_sel_hash: tuple | None = None
_applying_linked = False


def _vert_selection_hash(mesh) -> tuple:
    bm = bmesh.from_edit_mesh(mesh)
    try:
        bm.verts.ensure_lookup_table()
        return tuple(sorted(v.index for v in bm.verts if v.select))
    finally:
        bm.free()


def _depsgraph_auto_linked(scene, depsgraph):
    """When selection hash changes (incl. after box-select release), expand to linked."""
    global _last_sel_hash, _applying_linked
    if not _auto_linked_active or _applying_linked:
        return
    ctx = bpy.context
    if ctx.mode != "EDIT_MESH":
        return
    obj = ctx.active_object
    if obj is None or obj.type != "MESH":
        return

    mesh = obj.data
    h = _vert_selection_hash(mesh)
    if h == _last_sel_hash:
        return

    if not h:
        _last_sel_hash = h
        return

    _applying_linked = True
    try:
        _bmesh_select_linked_island(mesh)
        _last_sel_hash = _vert_selection_hash(mesh)
    finally:
        _applying_linked = False

    if ctx.area:
        ctx.area.tag_redraw()


def _register_depsgraph_handler():
    if _depsgraph_auto_linked not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph_auto_linked)


def _unregister_depsgraph_handler():
    h = _depsgraph_auto_linked
    while h in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(h)


def _enter_auto_linked(context):
    global _auto_linked_active, _last_sel_hash
    _auto_linked_active = True
    obj = context.active_object
    if obj and obj.type == "MESH":
        _last_sel_hash = _vert_selection_hash(obj.data)
    else:
        _last_sel_hash = None
    _register_depsgraph_handler()


def _exit_auto_linked():
    global _auto_linked_active, _last_sel_hash
    _auto_linked_active = False
    _last_sel_hash = None
    _unregister_depsgraph_handler()


class ALEC_OT_auto_linked_select_mode(bpy.types.Operator):
    """While active, selection changes expand to linked geometry (toggle with 6 or Esc)."""

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
        _enter_auto_linked(context)
        context.window_manager.modal_handler_add(self)
        self.report({"INFO"}, "Auto linked: 6 or Esc to exit")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.mode != "EDIT_MESH":
            _exit_auto_linked()
            return {"FINISHED"}

        obj = context.active_object
        if obj is None or obj.type != "MESH":
            _exit_auto_linked()
            return {"FINISHED"}

        if event.type in {"ESC"} and event.value == "PRESS":
            _exit_auto_linked()
            self.report({"INFO"}, "Auto linked mode off")
            return {"FINISHED"}

        if event.type == "SIX" and event.value == "PRESS":
            _exit_auto_linked()
            self.report({"INFO"}, "Auto linked mode off")
            return {"FINISHED"}

        return {"PASS_THROUGH"}


classes = (ALEC_OT_auto_linked_select_mode,)
