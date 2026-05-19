"""3D View area header text for modal operators (above the viewport)."""

from __future__ import annotations

import bpy


def set(context, text: str | None) -> None:
    area = getattr(context, "area", None)
    if area is None:
        return
    try:
        area.header_text_set(text)
    except Exception:
        pass


def clear(context) -> None:
    set(context, None)


def set_numeric(
    context,
    *,
    main_label: str,
    main_value: float,
    typed_str: str = "",
    suffix: str = "",
    secondary_text: str = "",
    initial_value: float | None = None,
    precision: int = 4,
) -> None:
    if typed_str:
        if initial_value is not None and typed_str and typed_str[0] in {"*", "/", "+", "-"}:
            formatted_initial = f"{initial_value:.{precision}f}".rstrip("0").rstrip(".")
            if formatted_initial == "-0":
                formatted_initial = "0"
            header_text = f"{main_label}: {formatted_initial}{suffix} {typed_str}"
        else:
            header_text = f"{main_label}: {typed_str}"
    else:
        formatted_main = f"{main_value:.{precision}f}".rstrip("0").rstrip(".")
        if formatted_main == "-0":
            formatted_main = "0"
        header_text = f"{main_label}: {formatted_main}{suffix}"

    if secondary_text:
        header_text += f"  |  {secondary_text}"

    set(context, header_text)


def format_length(context, value_bu: float, *, precision: int = 4) -> str:
    unit_sys = context.scene.unit_settings
    try:
        return bpy.utils.units.to_string(unit_sys, "LENGTH", value_bu, precision=precision)
    except Exception:
        return f"{value_bu:.{precision}f}"
