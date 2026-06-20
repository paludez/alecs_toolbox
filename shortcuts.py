import bpy

from .operators.mesh_edit_shortcuts import classes as _mesh_component_classes
from .operators.mesh_selection_helpers import classes as _mesh_selection_helpers_classes

_mesh_edit_classes = _mesh_component_classes + _mesh_selection_helpers_classes

# ---------------------------------------------------------------------------
# Keymap storage
# ---------------------------------------------------------------------------

_addon_keymaps_core: list[tuple] = []
_addon_keymaps_auto_linked: list[tuple] = []
_addon_keymaps_mesh: list[tuple] = []
_addon_keymaps_toolbar_tools: list[tuple] = []
_addon_keymaps_object_hide: list[tuple] = []
_addon_keymaps_align: list[tuple] = []

_km_auto_linked_mesh = None
_km_object_hide = None
_km_object_align = None
_km_object_mode = None
_km_mesh_edit = None
_mesh_keys_registered = False

# Toolbar keymaps: one entry per edit mode. Accessed by name for special cases.
_TOOLBAR_KM_SPECS = [
    "Object Mode",
    "Mesh",
    "Curve",
    "Curves",
    "UV Editor",  # keymap name is "UV Editor", not "Image" / paint
    "Armature",
    "Pose",
    "Lattice",
    "Surface",
    "Metaball",
]
_toolbar_kms: dict = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _addon_prefs():
    from . import preferences as prefmod

    add = bpy.context.preferences.addons.get(prefmod._addon_id())
    return add.preferences if add else None


def _pref(prefs, attr: str, default: bool = True) -> bool:
    if prefs is None:
        return default
    return bool(getattr(prefs, attr, default))


_disabled_default_kmis: list = []


def _get_addon_km(kc, name: str, space_type: str, region_type: str = "WINDOW"):
    """Reuse existing addon keymap — avoid duplicate maps on prefs refresh."""
    for km in kc.keymaps:
        if km.name == name and km.space_type == space_type and km.region_type == region_type:
            return km
    return kc.keymaps.new(name, space_type=space_type, region_type=region_type)


# Editors where Window-only bindings are not reached (e.g. Outliner focus).
_AREA_UNDER_MOUSE_KM_SPECS = [
    ("Window", "EMPTY"),
    ("Outliner", "OUTLINER"),
    ("3D View", "VIEW_3D"),
    ("Node Editor", "NODE_EDITOR"),
    ("Image", "IMAGE_EDITOR"),
    ("Graph Editor", "GRAPH_EDITOR"),
    ("Dope Sheet", "DOPESHEET_EDITOR"),
    ("Properties", "PROPERTIES"),
    ("File Browser", "FILE_BROWSER"),
    ("Text", "TEXT_EDITOR"),
]


def _register_area_under_mouse_shortcuts(kc, prefs) -> None:
    """Area-under-mouse shortcuts on Window + per-editor keymaps."""
    want = any(
        (
            _pref(prefs, "shortcut_alt_1_view3d_under_mouse"),
            _pref(prefs, "shortcut_alt_2_toggle_shader_object_world_under_mouse"),
            _pref(prefs, "shortcut_alt_3_toggle_uv_image_under_mouse"),
            _pref(prefs, "shortcut_alt_4_toggle_graph_dopesheet_under_mouse"),
            _pref(prefs, "shortcut_alt_f1_join_area_under_mouse"),
        )
    )
    if not want:
        return

    for km_name, space_type in _AREA_UNDER_MOUSE_KM_SPECS:
        km = _get_addon_km(kc, km_name, space_type, "WINDOW")
        head = space_type != "EMPTY"
        if _pref(prefs, "shortcut_alt_1_view3d_under_mouse"):
            _add_core_kmi(
                km, "alec.set_area_view3d_under_mouse", "ONE", alt=True, head=head
            )
        if _pref(prefs, "shortcut_alt_2_toggle_shader_object_world_under_mouse"):
            _add_core_kmi(
                km, "alec.toggle_area_shader_under_mouse", "TWO", alt=True, head=head
            )
        if _pref(prefs, "shortcut_alt_3_toggle_uv_image_under_mouse"):
            _add_core_kmi(
                km, "alec.toggle_area_uv_image_under_mouse", "THREE", alt=True, head=head
            )
        if _pref(prefs, "shortcut_alt_4_toggle_graph_dopesheet_under_mouse"):
            _add_core_kmi(
                km,
                "alec.toggle_area_graph_dopesheet_under_mouse",
                "FOUR",
                alt=True,
                head=head,
            )
        if _pref(prefs, "shortcut_alt_f1_join_area_under_mouse"):
            _add_core_kmi(
                km, "alec.join_area_under_mouse", "F1", alt=True, head=head
            )


_AUTO_KEY_DATA_PATH = "tool_settings.use_keyframe_insert_auto"


def _add_context_toggle_kmi(km, data_path: str, key: str, *, head: bool = False, **modifiers):
    kmi = km.keymap_items.new("wm.context_toggle", key, "PRESS", head=head, **modifiers)
    kmi.properties.data_path = data_path
    _addon_keymaps_core.append((km, kmi))
    return kmi


def _add_op_kmi(km, idname: str, key: str, *, props=None, head: bool = False, **modifiers):
    kmi = km.keymap_items.new(idname, key, "PRESS", head=head, **modifiers)
    if props:
        for name, value in props.items():
            setattr(kmi.properties, name, value)
    _addon_keymaps_core.append((km, kmi))
    return kmi


def _register_auto_key_toggle_keymaps(kc, prefs) -> None:
    if not _pref(prefs, "shortcut_alt_n_auto_key"):
        return
    km_win = _get_addon_km(kc, "Window", "EMPTY", "WINDOW")
    _add_context_toggle_kmi(km_win, _AUTO_KEY_DATA_PATH, "N", alt=True)
    for km_name, space_type in (
        ("Graph Editor", "GRAPH_EDITOR"),
        ("Dope Sheet", "DOPESHEET_EDITOR"),
    ):
        km = _get_addon_km(kc, km_name, space_type, "WINDOW")
        _add_context_toggle_kmi(km, _AUTO_KEY_DATA_PATH, "N", alt=True)


def _register_timeline_nav_keymaps(kc, prefs) -> None:
    if not _pref(prefs, "shortcut_shift_1234_timeline_nav"):
        return
    km = _get_addon_km(kc, "Frames", "EMPTY", "WINDOW")
    _add_op_kmi(
        km,
        "screen.frame_jump",
        "ONE",
        shift=True,
        repeat=True,
        props={"end": False},
    )
    _add_op_kmi(
        km,
        "screen.keyframe_jump",
        "TWO",
        shift=True,
        repeat=True,
        props={"next": False},
    )
    _add_op_kmi(
        km,
        "screen.keyframe_jump",
        "THREE",
        shift=True,
        repeat=True,
        props={"next": True},
    )
    _add_op_kmi(
        km,
        "screen.frame_jump",
        "FOUR",
        shift=True,
        repeat=True,
        props={"end": True},
    )


def _add_core_kmi(km, idname: str, key: str, *, head: bool = False, **modifiers):
    """Register one keymap item; skip exact duplicates on the same keymap."""
    for kmi in km.keymap_items:
        if kmi.idname != idname or kmi.type != key or kmi.value != "PRESS":
            continue
        if bool(kmi.alt) != bool(modifiers.get("alt", False)):
            continue
        if bool(kmi.shift) != bool(modifiers.get("shift", False)):
            continue
        if bool(kmi.ctrl) != bool(modifiers.get("ctrl", False)):
            continue
        if bool(getattr(kmi, "oskey", False)) != bool(modifiers.get("oskey", False)):
            continue
        kmi.active = True
        pair = (km, kmi)
        if pair not in _addon_keymaps_core:
            _addon_keymaps_core.append(pair)
        return kmi
    kmi = km.keymap_items.new(idname, key, "PRESS", head=head, **modifiers)
    _addon_keymaps_core.append((km, kmi))
    return kmi


def _iter_3d_view_keymaps(kc, region_type: str = "WINDOW"):
    """All non-modal 3D View keymaps for the given region (WINDOW, UI, …)."""
    if kc is None:
        return
    find = getattr(kc.keymaps, "find", None)
    if find:
        try:
            km = find("3D View", "VIEW_3D", region_type)
            if km is not None:
                yield km
                return
        except (TypeError, ValueError):
            pass
    for km in kc.keymaps:
        if getattr(km, "modal", False):
            continue
        if km.space_type == "VIEW_3D" and km.region_type == region_type:
            yield km


def _iter_3d_view_window_keymaps(kc):
    """All non-modal 3D View » Window keymaps (Blender may ship more than one name)."""
    yield from _iter_3d_view_keymaps(kc, "WINDOW")


def _is_sidebar_toggle_n(kmi) -> bool:
    """Built-in N that toggles the right sidebar (Tools/N-panel region)."""
    if kmi.type != "N" or kmi.value != "PRESS":
        return False
    if kmi.any or kmi.shift or kmi.ctrl or kmi.alt:
        return False
    if getattr(kmi, "oskey", False):
        return False
    if not kmi.active:
        return False
    if kmi.idname == "wm.context_toggle":
        dp = getattr(kmi.properties, "data_path", "") or ""
        return dp == "space_data.show_region_ui"
    return False


def _disable_default_n_key():
    """Mute Blender's built-in N sidebar toggle (editable prefs keymap, not default-only)."""
    wm = bpy.context.window_manager
    # preferences = merged editable key configuration; 'default' is often not writable
    for store_name in ("preferences", "user"):
        kc = getattr(wm.keyconfigs, store_name, None)
        if kc is None:
            continue
        for region_type in ("WINDOW", "UI"):
            for km in _iter_3d_view_keymaps(kc, region_type):
                for kmi in km.keymap_items:
                    if not _is_sidebar_toggle_n(kmi):
                        continue
                    if kmi in _disabled_default_kmis:
                        continue
                    try:
                        kmi.active = False
                        _disabled_default_kmis.append(kmi)
                    except Exception:
                        pass


def _restore_default_n_key():
    for kmi in _disabled_default_kmis:
        try:
            kmi.active = True
        except Exception:
            pass
    _disabled_default_kmis.clear()


# ---------------------------------------------------------------------------
# Core keymaps (3D View, Node Editor, Outliner, Window)
# ---------------------------------------------------------------------------

def _unregister_core_keymaps():
    seen = set()
    for km, kmi in _addon_keymaps_core:
        pair = (km, kmi)
        if pair in seen:
            continue
        seen.add(pair)
        try:
            km.keymap_items.remove(kmi)
        except RuntimeError:
            pass
    _addon_keymaps_core.clear()
    _restore_default_n_key()


def _register_core_keymaps():
    _restore_default_n_key()  # reset state before re-registering
    prefs = _addon_prefs()
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return

    need_3d = any(
        (
            _pref(prefs, "shortcut_q_alt_menu"),
            _pref(prefs, "shortcut_alt_rmb_quad"),
            _pref(prefs, "shortcut_f1_search"),
            _pref(prefs, "shortcut_f3_wireframe_xray"),
            _pref(prefs, "shortcut_f4_overlay_wireframes"),
            _pref(prefs, "shortcut_ctrl_shift_f3_wireframe_color"),
            _pref(prefs, "shortcut_ctrl_alt_f3_color_type"),
            _pref(prefs, "shortcut_f5_rendered"),
            _pref(prefs, "shortcut_f6_material"),
            _pref(prefs, "shortcut_c_camera"),
            _pref(prefs, "shortcut_grave_isolate"),
            _pref(prefs, "shortcut_alt_grave_orientation"),
            _pref(prefs, "shortcut_ctrl_grave_frame_selected"),
            _pref(prefs, "shortcut_n_alec_panel"),
            _pref(prefs, "shortcut_alt_w_light_energy_modal"),
        )
    )
    km = None
    if need_3d:
        km = _get_addon_km(kc, "3D View", "VIEW_3D", "WINDOW")

    if km is not None and _pref(prefs, "shortcut_q_alt_menu"):
        _add_core_kmi(km, "alec.menu_dispatcher", "Q", alt=True)
        # Edit modes use Mesh/Curve keymaps (EMPTY), not 3D View — duplicate binding.
        km_mesh = _get_addon_km(kc, "Mesh", "EMPTY", "WINDOW")
        _add_core_kmi(km_mesh, "alec.menu_dispatcher", "Q", alt=True, head=True)
        km_curve = _get_addon_km(kc, "Curve", "EMPTY", "WINDOW")
        _add_core_kmi(km_curve, "alec.menu_dispatcher", "Q", alt=True, head=True)

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

    if km is not None and _pref(prefs, "shortcut_ctrl_shift_f3_wireframe_color"):
        kmi_ctrl_shift_f3 = km.keymap_items.new(
            "alec.viewport_cycle_wireframe_color_type",
            "F3",
            "PRESS",
            ctrl=True,
            shift=True,
        )
        _addon_keymaps_core.append((km, kmi_ctrl_shift_f3))

    if km is not None and _pref(prefs, "shortcut_ctrl_alt_f3_color_type"):
        kmi_ctrl_alt_f3 = km.keymap_items.new(
            "alec.viewport_cycle_color_type", "F3", "PRESS", ctrl=True, alt=True
        )
        _addon_keymaps_core.append((km, kmi_ctrl_alt_f3))

    if km is not None and _pref(prefs, "shortcut_f5_rendered"):
        kmi_f5 = km.keymap_items.new(
            "alec.viewport_toggle_shading_rendered", "F5", "PRESS"
        )
        _addon_keymaps_core.append((km, kmi_f5))

    if km is not None and _pref(prefs, "shortcut_f6_material"):
        kmi_f6 = km.keymap_items.new(
            "alec.viewport_toggle_shading_material", "F6", "PRESS"
        )
        _addon_keymaps_core.append((km, kmi_f6))

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

    if _pref(prefs, "shortcut_n_alec_panel"):
        km_n_win = km
        if km_n_win is None:
            km_n_win = _get_addon_km(kc, "3D View", "VIEW_3D", "WINDOW")
        kmi_n = km_n_win.keymap_items.new("alec.open_alec_panel", "N", "PRESS")
        _addon_keymaps_core.append((km_n_win, kmi_n))
        km_n_ui = _get_addon_km(kc, "3D View", "VIEW_3D", "UI")
        kmi_n_ui = km_n_ui.keymap_items.new("alec.open_alec_panel", "N", "PRESS")
        _addon_keymaps_core.append((km_n_ui, kmi_n_ui))
        _disable_default_n_key()

    if km is not None and _pref(prefs, "shortcut_alt_w_light_energy_modal"):
        kmi_light_modal = km.keymap_items.new(
            "alec.light_energy_modal", "W", "PRESS", alt=True
        )
        _addon_keymaps_core.append((km, kmi_light_modal))

    need_window = any(
        (
            _pref(prefs, "shortcut_alt_1_view3d_under_mouse"),
            _pref(prefs, "shortcut_alt_2_toggle_shader_object_world_under_mouse"),
            _pref(prefs, "shortcut_alt_3_toggle_uv_image_under_mouse"),
            _pref(prefs, "shortcut_alt_4_toggle_graph_dopesheet_under_mouse"),
            _pref(prefs, "shortcut_alt_f1_join_area_under_mouse"),
        )
    )
    if need_window:
        _register_area_under_mouse_shortcuts(kc, prefs)

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

    _register_auto_key_toggle_keymaps(kc, prefs)
    _register_timeline_nav_keymaps(kc, prefs)


# ---------------------------------------------------------------------------
# Toolbar tools (W / E / Alt+E)
# ---------------------------------------------------------------------------

def _register_toolbar_tool_keymaps():
    """W → Move, E → Rotate (left toolbar); Alt+E → extrude where applicable."""
    prefs = _addon_prefs()
    need = (
        _pref(prefs, "shortcut_w_move_tool")
        or _pref(prefs, "shortcut_e_rotate_tool")
        or _pref(prefs, "shortcut_alt_e_extrude")
    )
    if not need:
        return

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return

    for name in _TOOLBAR_KM_SPECS:
        if name not in _toolbar_kms:
            _toolbar_kms[name] = kc.keymaps.new(
                name, space_type="EMPTY", region_type="WINDOW"
            )

    if _pref(prefs, "shortcut_w_move_tool"):
        for km in _toolbar_kms.values():
            kmi = km.keymap_items.new("wm.tool_set_by_id", "W", "PRESS")
            kmi.properties.name = "builtin.move"
            _addon_keymaps_toolbar_tools.append((km, kmi))

    if _pref(prefs, "shortcut_e_rotate_tool"):
        for km in _toolbar_kms.values():
            kmi = km.keymap_items.new("wm.tool_set_by_id", "E", "PRESS")
            kmi.properties.name = "builtin.rotate"
            _addon_keymaps_toolbar_tools.append((km, kmi))

    if _pref(prefs, "shortcut_alt_e_extrude"):
        kmi_alt = _toolbar_kms["Mesh"].keymap_items.new(
            "view3d.edit_mesh_extrude_move_normal", "E", "PRESS", alt=True
        )
        _addon_keymaps_toolbar_tools.append((_toolbar_kms["Mesh"], kmi_alt))
        kmi_shift_alt = _toolbar_kms["Mesh"].keymap_items.new(
            "wm.call_menu", "E", "PRESS", alt=True, shift=True
        )
        kmi_shift_alt.properties.name = "VIEW3D_MT_edit_mesh_extrude"
        _addon_keymaps_toolbar_tools.append((_toolbar_kms["Mesh"], kmi_shift_alt))
        kmi_curve_alt = _toolbar_kms["Curve"].keymap_items.new(
            "curve.extrude_move", "E", "PRESS", alt=True
        )
        _addon_keymaps_toolbar_tools.append((_toolbar_kms["Curve"], kmi_curve_alt))
        kmi_curves_alt = _toolbar_kms["Curves"].keymap_items.new(
            "curves.extrude_move", "E", "PRESS", alt=True
        )
        _addon_keymaps_toolbar_tools.append((_toolbar_kms["Curves"], kmi_curves_alt))
        kmi_armature_alt = _toolbar_kms["Armature"].keymap_items.new(
            "armature.extrude_move", "E", "PRESS", alt=True
        )
        _addon_keymaps_toolbar_tools.append((_toolbar_kms["Armature"], kmi_armature_alt))
        kmi_surface_alt = _toolbar_kms["Surface"].keymap_items.new(
            "surface.extrude_move", "E", "PRESS", alt=True
        )
        _addon_keymaps_toolbar_tools.append((_toolbar_kms["Surface"], kmi_surface_alt))


def _unregister_toolbar_tool_keymaps():
    for km, kmi in _addon_keymaps_toolbar_tools:
        km.keymap_items.remove(kmi)
    _addon_keymaps_toolbar_tools.clear()
    _toolbar_kms.clear()


# ---------------------------------------------------------------------------
# Auto-linked mode (key 4, Edit Mesh)
# ---------------------------------------------------------------------------

def _register_auto_linked_keymap():
    """Edit Mesh: 4 toggles auto-linked mode."""
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


# ---------------------------------------------------------------------------
# Object hide sync (H / Shift+H / Alt+H)
# ---------------------------------------------------------------------------

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


def _unregister_object_hide_keymaps():
    for km, kmi in _addon_keymaps_object_hide:
        km.keymap_items.remove(kmi)
    _addon_keymaps_object_hide.clear()


# ---------------------------------------------------------------------------
# Align (Alt+A / Ctrl+Alt+A, Object Mode)
# ---------------------------------------------------------------------------

def _register_align_keymaps():
    prefs = _addon_prefs()
    want_origins = _pref(prefs, "shortcut_alt_a_align_origins", True)
    want_dialog = _pref(prefs, "shortcut_ctrl_alt_a_align_dialog", True)
    if not (want_origins or want_dialog):
        return
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
    global _km_object_align
    if _km_object_align is None:
        _km_object_align = kc.keymaps.new(
            "Object Mode", space_type="EMPTY", region_type="WINDOW"
        )
    if want_origins:
        kmi = _km_object_align.keymap_items.new(
            "alec.align_preset_origins", "A", "PRESS", alt=True
        )
        _addon_keymaps_align.append((_km_object_align, kmi))
    if want_dialog:
        kmi = _km_object_align.keymap_items.new(
            "alec.align_dialog", "A", "PRESS", ctrl=True, alt=True
        )
        _addon_keymaps_align.append((_km_object_align, kmi))


def _unregister_align_keymaps():
    for km, kmi in _addon_keymaps_align:
        km.keymap_items.remove(kmi)
    _addon_keymaps_align.clear()


# ---------------------------------------------------------------------------
# Mesh component keys (1 / 2 / 3 / 5)
# ---------------------------------------------------------------------------

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
        # Must match Blender's "Mesh" keymap name or bindings won't fire in Edit Mesh.
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def refresh_keymaps_from_prefs():
    """Re-apply addon keymaps from preferences (core, toolbar, key 4). Mesh 1–3/5 unchanged."""
    _unregister_core_keymaps()
    _unregister_toolbar_tool_keymaps()
    _unregister_auto_linked_keymap()
    _unregister_object_hide_keymaps()
    _unregister_align_keymaps()
    _register_core_keymaps()
    _register_toolbar_tool_keymaps()
    prefs = _addon_prefs()
    if _pref(prefs, "shortcut_key_4_auto_linked"):
        _register_auto_linked_keymap()
    _register_object_hide_keymaps()
    _register_align_keymaps()


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
    global _km_auto_linked_mesh, _km_object_hide, _km_object_align
    global _km_object_mode, _km_mesh_edit, _mesh_keys_registered

    set_mesh_max_keys(False)
    _unregister_auto_linked_keymap()
    _unregister_object_hide_keymaps()
    _unregister_align_keymaps()
    _unregister_toolbar_tool_keymaps()
    _unregister_core_keymaps()
    _km_auto_linked_mesh = None
    _km_object_hide = None
    _km_object_align = None
    _km_object_mode = None
    _km_mesh_edit = None
    _mesh_keys_registered = False
