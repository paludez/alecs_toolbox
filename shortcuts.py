import bpy

from .operators.mesh_edit_shortcuts import classes as _mesh_component_classes
from .operators.mesh_selection_helpers import classes as _mesh_selection_helpers_classes

_mesh_edit_classes = _mesh_component_classes + _mesh_selection_helpers_classes

_addon_keymaps_core: list[tuple] = []
_addon_keymaps_auto_linked: list[tuple] = []
_addon_keymaps_mesh: list[tuple] = []
_km_auto_linked_mesh = None
_mesh_keys_registered = False
_km_object_mode = None
_km_mesh_edit = None


def _register_core_keymaps():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
    km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
    kmi_main = km.keymap_items.new('alec.menu_dispatcher', 'Q', 'PRESS', alt=True)
    _addon_keymaps_core.append((km, kmi_main))

    kmi_browser = km.keymap_items.new('wm.call_menu', 'Q', 'PRESS', ctrl=True, alt=True)
    kmi_browser.properties.name = "ALEC_MT_alec_browser"
    _addon_keymaps_core.append((km, kmi_browser))

    km_uv = kc.keymaps.new(name='Image', space_type='IMAGE_EDITOR')
    kmi_uv = km_uv.keymap_items.new('alec.menu_dispatcher', 'Q', 'PRESS', alt=True)
    _addon_keymaps_core.append((km_uv, kmi_uv))

    kmi_uv_browser = km_uv.keymap_items.new('wm.call_menu', 'Q', 'PRESS', ctrl=True, alt=True)
    kmi_uv_browser.properties.name = "ALEC_MT_alec_browser"
    _addon_keymaps_core.append((km_uv, kmi_uv_browser))

    kmi_quad = km.keymap_items.new('wm.call_menu_pie', 'RIGHTMOUSE', 'PRESS', alt=True)
    kmi_quad.properties.name = "ALEC_MT_quad_menu"
    _addon_keymaps_core.append((km, kmi_quad))


def _register_auto_linked_keymap():
    """Edit Mesh: 4 / Numpad 4 toggle auto-linked mode (replaces Max-slot key 4 one-shot linked expand)."""
    global _km_auto_linked_mesh
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
    if _km_auto_linked_mesh is None:
        _km_auto_linked_mesh = kc.keymaps.new(
            "Mesh", space_type="EMPTY", region_type="WINDOW"
        )
    for key in ("FOUR", "NUMPAD_4"):
        for existing in _km_auto_linked_mesh.keymap_items:
            if (
                existing.idname == "alec.auto_linked_select_mode"
                and existing.type == key
            ):
                break
        else:
            kmi = _km_auto_linked_mesh.keymap_items.new(
                "alec.auto_linked_select_mode", key, "PRESS"
            )
            _addon_keymaps_auto_linked.append((_km_auto_linked_mesh, kmi))


def _unregister_auto_linked_keymap():
    for km, kmi in _addon_keymaps_auto_linked:
        km.keymap_items.remove(kmi)
    _addon_keymaps_auto_linked.clear()


def _register_mesh_keymaps():
    global _km_object_mode, _km_mesh_edit
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
    op = 'alec.mesh_edit_component'
    if _km_object_mode is None:
        _km_object_mode = kc.keymaps.new('Object Mode', space_type='EMPTY', region_type='WINDOW')
    if _km_mesh_edit is None:
        # Match Blender's default "Mesh" keymap (km_edit_mesh) or bindings won't run in Edit Mesh.
        _km_mesh_edit = kc.keymaps.new('Mesh', space_type='EMPTY', region_type='WINDOW')
    for key, comp in (('ONE', 'VERT'), ('TWO', 'EDGE'), ('THREE', 'FACE')):
        kmi = _km_object_mode.keymap_items.new(op, key, 'PRESS')
        kmi.properties.component = comp
        _addon_keymaps_mesh.append((_km_object_mode, kmi))
    for key, comp in (('ONE', 'VERT'), ('TWO', 'EDGE'), ('THREE', 'FACE')):
        kmi = _km_mesh_edit.keymap_items.new(op, key, 'PRESS')
        kmi.properties.component = comp
        _addon_keymaps_mesh.append((_km_mesh_edit, kmi))

    for km in (_km_object_mode, _km_mesh_edit):
        for key in ('FIVE', 'NUMPAD_5'):
            kmi5 = km.keymap_items.new('alec.mesh_select_open_edges_connected', key, 'PRESS')
            _addon_keymaps_mesh.append((km, kmi5))


def _unregister_mesh_keymaps():
    for km, kmi in _addon_keymaps_mesh:
        km.keymap_items.remove(kmi)
    _addon_keymaps_mesh.clear()


def set_mesh_max_keys(want: bool):
    global _mesh_keys_registered
    if want == _mesh_keys_registered:
        return
    if want:
        for cls in _mesh_edit_classes:
            bpy.utils.register_class(cls)
        _register_mesh_keymaps()
        _mesh_keys_registered = True
    else:
        _unregister_mesh_keymaps()
        for cls in reversed(_mesh_edit_classes):
            bpy.utils.unregister_class(cls)
        _mesh_keys_registered = False


def register():
    _register_core_keymaps()
    _register_auto_linked_keymap()
    from . import preferences as prefmod
    add = bpy.context.preferences.addons.get(prefmod._addon_id())
    if add is None:
        set_mesh_max_keys(False)
    else:
        set_mesh_max_keys(add.preferences.use_max_style_mesh_keys)


def unregister():
    set_mesh_max_keys(False)
    _unregister_auto_linked_keymap()
    for km, kmi in _addon_keymaps_core:
        km.keymap_items.remove(kmi)
    _addon_keymaps_core.clear()
