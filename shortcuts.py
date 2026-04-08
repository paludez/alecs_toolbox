import bpy

from .operators.mesh_edit_shortcuts import classes as _mesh_component_classes
from .operators.mesh_selection_helpers import classes as _mesh_selection_helpers_classes

_mesh_edit_classes = _mesh_component_classes + _mesh_selection_helpers_classes

_addon_keymaps_core: list[tuple] = []
_addon_keymaps_auto_linked: list[tuple] = []
_addon_keymaps_mesh: list[tuple] = []
_addon_keymaps_toolbar_tools: list[tuple] = []
_addon_keymaps_object_hide: list[tuple] = []
_km_auto_linked_mesh = None
_km_object_hide = None
_mesh_keys_registered = False
_km_object_mode = None
_km_mesh_edit = None
_km_move_tool_object = None
_km_move_tool_mesh = None
_km_move_tool_curve = None
_km_move_tool_curves = None
_km_move_tool_uv = None


def _addon_prefs():
    from . import preferences as prefmod

    add = bpy.context.preferences.addons.get(prefmod._addon_id())
    return add.preferences if add else None


def _pref(prefs, attr: str, default: bool = True) -> bool:
    if prefs is None:
        return default
    return bool(getattr(prefs, attr, default))


def _unregister_core_keymaps():
    for km, kmi in _addon_keymaps_core:
        km.keymap_items.remove(kmi)
    _addon_keymaps_core.clear()


def _register_core_keymaps():
    prefs = _addon_prefs()
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return

    need_3d = any(
        (
            _pref(prefs, "shortcut_q_alt_menu"),
            _pref(prefs, "shortcut_q_ctrl_alt_browser"),
            _pref(prefs, "shortcut_alt_rmb_quad"),
            _pref(prefs, "shortcut_f1_search"),
            _pref(prefs, "shortcut_f3_wireframe_xray"),
            _pref(prefs, "shortcut_f4_overlay_wireframes"),
            _pref(prefs, "shortcut_f5_solid_rendered"),
            _pref(prefs, "shortcut_c_camera"),
            _pref(prefs, "shortcut_grave_isolate"),
            _pref(prefs, "shortcut_alt_grave_orientation"),
            _pref(prefs, "shortcut_ctrl_grave_frame_selected"),
            _pref(prefs, "shortcut_alt_w_light_energy_modal"),
        )
    )
    km = None
    if need_3d:
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D", region_type="WINDOW")

    if km is not None and _pref(prefs, "shortcut_q_alt_menu"):
        kmi_main = km.keymap_items.new("alec.menu_dispatcher", "Q", "PRESS", alt=True)
        _addon_keymaps_core.append((km, kmi_main))

    if km is not None and _pref(prefs, "shortcut_q_ctrl_alt_browser"):
        kmi_browser = km.keymap_items.new(
            "wm.call_menu", "Q", "PRESS", ctrl=True, alt=True
        )
        kmi_browser.properties.name = "ALEC_MT_alec_browser"
        _addon_keymaps_core.append((km, kmi_browser))

    if km is not None and _pref(prefs, "shortcut_alt_rmb_quad"):
        kmi_quad = km.keymap_items.new(
            "wm.call_menu_pie", "RIGHTMOUSE", "PRESS", alt=True
        )
        kmi_quad.properties.name = "ALEC_MT_quad_menu"
        _addon_keymaps_core.append((km, kmi_quad))

    if km is not None and _pref(prefs, "shortcut_f1_search"):
        kmi_f1 = km.keymap_items.new("wm.search_menu", "F1", "PRESS")
        _addon_keymaps_core.append((km, kmi_f1))

    if km is not None and _pref(prefs, "shortcut_f3_wireframe_xray"):
        kmi_f3 = km.keymap_items.new(
            "alec.viewport_toggle_wireframe_xray", "F3", "PRESS"
        )
        _addon_keymaps_core.append((km, kmi_f3))

    if km is not None and _pref(prefs, "shortcut_f4_overlay_wireframes"):
        kmi_f4 = km.keymap_items.new(
            "alec.viewport_toggle_overlay_wireframes", "F4", "PRESS"
        )
        _addon_keymaps_core.append((km, kmi_f4))

    if km is not None and _pref(prefs, "shortcut_f5_solid_rendered"):
        kmi_f5 = km.keymap_items.new(
            "alec.viewport_toggle_solid_rendered", "F5", "PRESS"
        )
        _addon_keymaps_core.append((km, kmi_f5))

    if km is not None and _pref(prefs, "shortcut_c_camera"):
        kmi_camera_view = km.keymap_items.new(
            "view3d.view_camera", "C", "PRESS"
        )
        _addon_keymaps_core.append((km, kmi_camera_view))

    if km is not None and _pref(prefs, "shortcut_grave_isolate"):
        kmi_isolate_toggle = km.keymap_items.new(
            "view3d.localview", "ACCENT_GRAVE", "PRESS"
        )
        _addon_keymaps_core.append((km, kmi_isolate_toggle))

    if km is not None and _pref(prefs, "shortcut_alt_grave_orientation"):
        kmi_toggle_orient = km.keymap_items.new(
            "alec.toggle_global_local_orientation", "ACCENT_GRAVE", "PRESS", alt=True
        )
        _addon_keymaps_core.append((km, kmi_toggle_orient))

    if km is not None and _pref(prefs, "shortcut_ctrl_grave_frame_selected"):
        kmi_frame_selected = km.keymap_items.new(
            "alec.view_selected_safe", "ACCENT_GRAVE", "PRESS", ctrl=True
        )
        _addon_keymaps_core.append((km, kmi_frame_selected))

    if km is not None and _pref(prefs, "shortcut_alt_w_light_energy_modal"):
        kmi_light_modal = km.keymap_items.new(
            "alec.light_energy_modal", "W", "PRESS", alt=True
        )
        _addon_keymaps_core.append((km, kmi_light_modal))

    if (
        _pref(prefs, "shortcut_q_alt_menu")
        or _pref(prefs, "shortcut_q_ctrl_alt_browser")
        or _pref(prefs, "shortcut_alt_rmb_quad")
    ):
        km_uv = kc.keymaps.new(name="Image", space_type="IMAGE_EDITOR", region_type="WINDOW")
        if _pref(prefs, "shortcut_q_alt_menu"):
            kmi_uv = km_uv.keymap_items.new(
                "alec.menu_dispatcher", "Q", "PRESS", alt=True
            )
            _addon_keymaps_core.append((km_uv, kmi_uv))
        if _pref(prefs, "shortcut_q_ctrl_alt_browser"):
            kmi_uv_browser = km_uv.keymap_items.new(
                "wm.call_menu", "Q", "PRESS", ctrl=True, alt=True
            )
            kmi_uv_browser.properties.name = "ALEC_MT_alec_browser"
            _addon_keymaps_core.append((km_uv, kmi_uv_browser))
        if _pref(prefs, "shortcut_alt_rmb_quad"):
            kmi_uv_pie = km_uv.keymap_items.new(
                "wm.call_menu_pie", "RIGHTMOUSE", "PRESS", alt=True
            )
            kmi_uv_pie.properties.name = "ALEC_MT_uv_menu"
            _addon_keymaps_core.append((km_uv, kmi_uv_pie))

    if _pref(prefs, "shortcut_alt_rmb_quad"):
        km_node = kc.keymaps.new(name="Node Editor", space_type="NODE_EDITOR", region_type="WINDOW")
        kmi_shader_pie = km_node.keymap_items.new(
            "wm.call_menu_pie", "RIGHTMOUSE", "PRESS", alt=True
        )
        kmi_shader_pie.properties.name = "ALEC_MT_shader_edit_pie"
        _addon_keymaps_core.append((km_node, kmi_shader_pie))

        km_outliner = kc.keymaps.new(name="Outliner", space_type="OUTLINER", region_type="WINDOW")
        kmi_outliner_pie = km_outliner.keymap_items.new(
            "wm.call_menu_pie", "RIGHTMOUSE", "PRESS", alt=True
        )
        kmi_outliner_pie.properties.name = "ALEC_MT_outliner_pie"
        _addon_keymaps_core.append((km_outliner, kmi_outliner_pie))

    if _pref(prefs, "shortcut_grave_outliner_show_active"):
        km_outliner = kc.keymaps.new(name="Outliner", space_type="OUTLINER", region_type="WINDOW")
        kmi_outliner_show_active = km_outliner.keymap_items.new(
            "outliner.show_active", "ACCENT_GRAVE", "PRESS"
        )
        _addon_keymaps_core.append((km_outliner, kmi_outliner_show_active))

    need_window = any(
        (
            _pref(prefs, "shortcut_alt_1_view3d_under_mouse"),
            _pref(prefs, "shortcut_alt_2_shader_object_under_mouse"),
            _pref(prefs, "shortcut_alt_3_shader_world_under_mouse"),
            _pref(prefs, "shortcut_alt_4_uv_under_mouse"),
        )
    )
    if need_window:
        km_window = kc.keymaps.new(name="Window", space_type="EMPTY")
        if _pref(prefs, "shortcut_alt_1_view3d_under_mouse"):
            kmi_alt_1 = km_window.keymap_items.new(
                "alec.set_area_view3d_under_mouse", "ONE", "PRESS", alt=True
            )
            _addon_keymaps_core.append((km_window, kmi_alt_1))
        if _pref(prefs, "shortcut_alt_2_shader_object_under_mouse"):
            kmi_alt_2 = km_window.keymap_items.new(
                "alec.set_area_shader_under_mouse", "TWO", "PRESS", alt=True
            )
            kmi_alt_2.properties.mode = "OBJECT"
            _addon_keymaps_core.append((km_window, kmi_alt_2))
        if _pref(prefs, "shortcut_alt_3_shader_world_under_mouse"):
            kmi_alt_3 = km_window.keymap_items.new(
                "alec.set_area_shader_under_mouse", "THREE", "PRESS", alt=True
            )
            kmi_alt_3.properties.mode = "WORLD"
            _addon_keymaps_core.append((km_window, kmi_alt_3))
        if _pref(prefs, "shortcut_alt_4_uv_under_mouse"):
            kmi_alt_4 = km_window.keymap_items.new(
                "alec.set_area_uv_under_mouse", "FOUR", "PRESS", alt=True
            )
            _addon_keymaps_core.append((km_window, kmi_alt_4))


def _register_toolbar_tool_keymaps():
    """W → Move, E → Rotate (left toolbar); Mesh: Alt+E → extrude (was E)."""
    prefs = _addon_prefs()
    need = (
        _pref(prefs, "shortcut_w_move_tool")
        or _pref(prefs, "shortcut_e_rotate_tool")
        or _pref(prefs, "shortcut_alt_e_extrude")
    )
    if not need:
        return

    global _km_move_tool_object, _km_move_tool_mesh
    global _km_move_tool_curve, _km_move_tool_curves
    global _km_move_tool_uv
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
    if _km_move_tool_object is None:
        _km_move_tool_object = kc.keymaps.new(
            "Object Mode", space_type="EMPTY", region_type="WINDOW"
        )
    if _km_move_tool_mesh is None:
        _km_move_tool_mesh = kc.keymaps.new(
            "Mesh", space_type="EMPTY", region_type="WINDOW"
        )
    if _km_move_tool_curve is None:
        _km_move_tool_curve = kc.keymaps.new(
            "Curve", space_type="EMPTY", region_type="WINDOW"
        )
    if _km_move_tool_curves is None:
        _km_move_tool_curves = kc.keymaps.new(
            "Curves", space_type="EMPTY", region_type="WINDOW"
        )
    # UV Edit: keymap „UV Editor” (nu „Image” / paint).
    if _km_move_tool_uv is None:
        _km_move_tool_uv = kc.keymaps.new(
            "UV Editor", space_type="EMPTY", region_type="WINDOW"
        )
    _toolbar_kms = (
        _km_move_tool_object,
        _km_move_tool_mesh,
        _km_move_tool_curve,
        _km_move_tool_curves,
        _km_move_tool_uv,
    )
    if _pref(prefs, "shortcut_w_move_tool"):
        for km in _toolbar_kms:
            kmi = km.keymap_items.new("wm.tool_set_by_id", "W", "PRESS")
            kmi.properties.name = "builtin.move"
            _addon_keymaps_toolbar_tools.append((km, kmi))
    if _pref(prefs, "shortcut_e_rotate_tool"):
        for km in _toolbar_kms:
            kmi = km.keymap_items.new("wm.tool_set_by_id", "E", "PRESS")
            kmi.properties.name = "builtin.rotate"
            _addon_keymaps_toolbar_tools.append((km, kmi))
    if _pref(prefs, "shortcut_alt_e_extrude"):
        kmi_alt = _km_move_tool_mesh.keymap_items.new(
            "view3d.edit_mesh_extrude_move_normal", "E", "PRESS", alt=True
        )
        _addon_keymaps_toolbar_tools.append((_km_move_tool_mesh, kmi_alt))
        kmi_shift_alt = _km_move_tool_mesh.keymap_items.new(
            "wm.call_menu", "E", "PRESS", alt=True, shift=True
        )
        kmi_shift_alt.properties.name = "VIEW3D_MT_edit_mesh_extrude"
        _addon_keymaps_toolbar_tools.append((_km_move_tool_mesh, kmi_shift_alt))


def _unregister_toolbar_tool_keymaps():
    for km, kmi in _addon_keymaps_toolbar_tools:
        km.keymap_items.remove(kmi)
    _addon_keymaps_toolbar_tools.clear()


def _register_auto_linked_keymap():
    """Edit Mesh: 4 toggles auto-linked mode (replaces Max-slot key 4 one-shot linked expand)."""
    prefs = _addon_prefs()
    if not _pref(prefs, "shortcut_key_4_auto_linked"):
        return
    global _km_auto_linked_mesh
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
    if _km_auto_linked_mesh is None:
        _km_auto_linked_mesh = kc.keymaps.new(
            "Mesh", space_type="EMPTY", region_type="WINDOW"
        )
    for existing in _km_auto_linked_mesh.keymap_items:
        if (
            existing.idname == "alec.auto_linked_select_mode"
            and existing.type == "FOUR"
        ):
            break
    else:
        kmi = _km_auto_linked_mesh.keymap_items.new(
            "alec.auto_linked_select_mode", "FOUR", "PRESS"
        )
        _addon_keymaps_auto_linked.append((_km_auto_linked_mesh, kmi))


def _unregister_auto_linked_keymap():
    for km, kmi in _addon_keymaps_auto_linked:
        km.keymap_items.remove(kmi)
    _addon_keymaps_auto_linked.clear()


def _unregister_object_hide_keymaps():
    for km, kmi in _addon_keymaps_object_hide:
        km.keymap_items.remove(kmi)
    _addon_keymaps_object_hide.clear()


def _register_object_hide_keymaps():
    prefs = _addon_prefs()
    if not _pref(prefs, "use_object_hide_sync_render_shortcuts", True):
        return
    want_h = _pref(prefs, "shortcut_hide_h_sync_render", True)
    want_sh = _pref(prefs, "shortcut_hide_shift_h_sync_render", True)
    want_ah = _pref(prefs, "shortcut_hide_alt_h_sync_render", True)
    if not (want_h or want_sh or want_ah):
        return
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
    global _km_object_hide
    if _km_object_hide is None:
        _km_object_hide = kc.keymaps.new(
            "Object Mode", space_type="EMPTY", region_type="WINDOW"
        )
    if want_h:
        kmi = _km_object_hide.keymap_items.new(
            "alec.hide_selected_viewport_render", "H", "PRESS"
        )
        _addon_keymaps_object_hide.append((_km_object_hide, kmi))
    if want_sh:
        kmi = _km_object_hide.keymap_items.new(
            "alec.hide_unselected_viewport_render", "H", "PRESS", shift=True
        )
        _addon_keymaps_object_hide.append((_km_object_hide, kmi))
    if want_ah:
        kmi = _km_object_hide.keymap_items.new(
            "alec.hide_view_clear_viewport_render", "H", "PRESS", alt=True
        )
        _addon_keymaps_object_hide.append((_km_object_hide, kmi))


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
        kmi5 = km.keymap_items.new(
            'alec.mesh_select_open_edges_connected', 'FIVE', 'PRESS'
        )
        _addon_keymaps_mesh.append((km, kmi5))


def _unregister_mesh_keymaps():
    for km, kmi in _addon_keymaps_mesh:
        km.keymap_items.remove(kmi)
    _addon_keymaps_mesh.clear()


def refresh_keymaps_from_prefs():
    """Re-apply addon keymaps from preferences (core, toolbar, key 4). Mesh 1–3/5 unchanged."""
    _unregister_core_keymaps()
    _unregister_toolbar_tool_keymaps()
    _unregister_auto_linked_keymap()
    _unregister_object_hide_keymaps()
    _register_core_keymaps()
    _register_toolbar_tool_keymaps()
    prefs = _addon_prefs()
    if _pref(prefs, "shortcut_key_4_auto_linked"):
        _register_auto_linked_keymap()
    _register_object_hide_keymaps()


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
    refresh_keymaps_from_prefs()
    from . import preferences as prefmod
    add = bpy.context.preferences.addons.get(prefmod._addon_id())
    if add is None:
        set_mesh_max_keys(False)
    else:
        set_mesh_max_keys(add.preferences.use_max_style_mesh_keys)


def unregister():
    set_mesh_max_keys(False)
    _unregister_auto_linked_keymap()
    _unregister_object_hide_keymaps()
    _unregister_toolbar_tool_keymaps()
    _unregister_core_keymaps()
