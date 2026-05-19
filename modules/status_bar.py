"""Status bar UI for modal operators (workflow text + shortcut chips)."""

from __future__ import annotations

from typing import Sequence

import bpy


def set_message(context, text: str | None) -> None:
    try:
        context.workspace.status_text_set(text)
    except Exception:
        pass


def clear_message(context) -> None:
    set_message(context, None)


def draw_shortcuts(layout, items: Sequence) -> None:
    """
    Draw shortcut chips in the status bar header.
    items: list of (label, value, is_active?) or None for separator.
    """
    row = layout.row(align=True)
    row.alignment = "CENTER"

    for item in items:
        if item is None:
            row.separator(factor=2)
            continue

        label, value, *active = item
        is_active = active[0] if active else False

        sub_row = row.row(align=True)
        if is_active:
            sub_row.alert = True

        if label:
            sub_row.label(text=f"{label}:")
        sub_row.label(text=value)


def install_shortcuts(operator_class) -> None:
    bpy.types.STATUSBAR_HT_header.prepend(operator_class.draw_status_bar)


def uninstall_shortcuts(operator_class) -> None:
    try:
        bpy.types.STATUSBAR_HT_header.remove(operator_class.draw_status_bar)
    except Exception:
        pass


def clear_all(context, operator_class=None, *, clear_viewport_header: bool = True) -> None:
    clear_message(context)
    if operator_class is not None:
        uninstall_shortcuts(operator_class)
    if clear_viewport_header:
        from . import viewport_header

        viewport_header.clear(context)
