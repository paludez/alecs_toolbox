"""Apply/revert Blender global preferences from addon workflow settings."""

from __future__ import annotations

from typing import Any

import bpy

_THEME_WCOL_BOX_INNER_KEY = "__theme.wcol_box.inner"

_snapshot_globals: dict[str, Any] = {}


def _blender_prefs():
    return getattr(bpy.context, "preferences", None)


def _addon_prefs():
    from .. import preferences as prefmod

    add = bpy.context.preferences.addons.get(prefmod._addon_id())
    return add.preferences if add else None


def _snapshot_global(key: str, value: Any) -> None:
    if key not in _snapshot_globals:
        _snapshot_globals[key] = value


def _set_pref(key: str, obj: Any, prop: str, value: Any) -> None:
    _snapshot_global(key, getattr(obj, prop))
    setattr(obj, prop, value)


def _apply_theme_interface(addon_prefs, bp) -> None:
    key = _THEME_WCOL_BOX_INNER_KEY
    try:
        wcol = bp.themes[0].user_interface.wcol_box
    except (IndexError, AttributeError):
        return

    if not addon_prefs.wf_theme_box_inner_alpha_one:
        return

    _snapshot_global(
        key,
        (float(wcol.inner[0]), float(wcol.inner[1]), float(wcol.inner[2]), float(wcol.inner[3])),
    )
    if wcol.inner[3] != 1.0:
        wcol.inner[3] = 1.0


def _apply_interface(addon_prefs, bp) -> None:
    view = bp.view

    if addon_prefs.wf_hide_splash:
        _set_pref("view.show_splash", view, "show_splash", False)
    if addon_prefs.wf_show_tooltips_python:
        _set_pref("view.show_tooltips_python", view, "show_tooltips_python", True)
    if addon_prefs.wf_show_number_arrows:
        _set_pref("view.show_number_arrows", view, "show_number_arrows", True)
    if addon_prefs.wf_show_statusbar_stats:
        _set_pref("view.show_statusbar_stats", view, "show_statusbar_stats", True)
    if addon_prefs.wf_use_mouse_over_open:
        _set_pref("view.use_mouse_over_open", view, "use_mouse_over_open", True)
    if addon_prefs.wf_open_toplevel_delay_one:
        _set_pref("view.open_toplevel_delay", view, "open_toplevel_delay", 1)
    if addon_prefs.wf_open_sublevel_delay_one:
        _set_pref("view.open_sublevel_delay", view, "open_sublevel_delay", 1)
    if addon_prefs.wf_pie_animation_timeout_zero:
        _set_pref("view.pie_animation_timeout", view, "pie_animation_timeout", 0)


def _apply_editing_objects(addon_prefs, bp) -> None:
    if not addon_prefs.wf_object_align_cursor:
        return
    _set_pref("edit.object_align", bp.edit, "object_align", "CURSOR")


def _apply_editing_animation_globals(addon_prefs, bp) -> None:
    edit = bp.edit

    if addon_prefs.wf_show_only_selected_curve_keyframes:
        _set_pref(
            "edit.show_only_selected_curve_keyframes",
            edit,
            "show_only_selected_curve_keyframes",
            True,
        )
    if addon_prefs.wf_disable_fcurve_high_quality:
        _set_pref(
            "edit.use_fcurve_high_quality_drawing",
            edit,
            "use_fcurve_high_quality_drawing",
            False,
        )
    if addon_prefs.wf_fcurve_unselected_alpha:
        _set_pref(
            "edit.fcurve_unselected_alpha",
            edit,
            "fcurve_unselected_alpha",
            0.0,
        )


def _apply_input(addon_prefs, bp) -> None:
    if not addon_prefs.wf_use_numeric_input_advanced:
        return
    _set_pref(
        "inputs.use_numeric_input_advanced",
        bp.inputs,
        "use_numeric_input_advanced",
        True,
    )


def _apply_navigation(addon_prefs, bp) -> None:
    inputs = bp.inputs

    if addon_prefs.wf_orbit_around_selection:
        _set_pref(
            "inputs.use_rotate_around_active",
            inputs,
            "use_rotate_around_active",
            True,
        )
    if addon_prefs.wf_disable_auto_perspective:
        _set_pref("inputs.use_auto_perspective", inputs, "use_auto_perspective", False)
    if addon_prefs.wf_use_mouse_depth_navigate:
        _set_pref(
            "inputs.use_mouse_depth_navigate",
            inputs,
            "use_mouse_depth_navigate",
            True,
        )
    if addon_prefs.wf_use_zoom_to_mouse:
        _set_pref("inputs.use_zoom_to_mouse", inputs, "use_zoom_to_mouse", True)


def apply_workflow_preferences() -> None:
    addon_prefs = _addon_prefs()
    bp = _blender_prefs()
    if addon_prefs is None or bp is None:
        return

    _apply_interface(addon_prefs, bp)
    _apply_editing_objects(addon_prefs, bp)
    _apply_editing_animation_globals(addon_prefs, bp)
    _apply_input(addon_prefs, bp)
    _apply_navigation(addon_prefs, bp)
    _apply_theme_interface(addon_prefs, bp)


def revert_workflow_preferences() -> None:
    if not _snapshot_globals:
        return

    bp = _blender_prefs()
    if bp is None:
        _snapshot_globals.clear()
        return

    for key, value in list(_snapshot_globals.items()):
        if key == _THEME_WCOL_BOX_INNER_KEY:
            try:
                bp.themes[0].user_interface.wcol_box.inner = value
            except (IndexError, AttributeError, TypeError):
                pass
            continue
        try:
            obj_name, prop_name = key.split(".", 1)
            setattr(getattr(bp, obj_name), prop_name, value)
        except (AttributeError, ValueError, TypeError):
            pass
    _snapshot_globals.clear()


def refresh_workflow_preferences() -> None:
    """Re-apply while master toggle is on (after changing a sub-option)."""
    revert_workflow_preferences()
    apply_workflow_preferences()
