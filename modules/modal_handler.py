"""Modal operator base: numeric input, status bar shortcuts, viewport header.

UI drawing: modules.status_bar, modules.viewport_header
"""

import bpy
import re

from . import status_bar
from . import viewport_header

ALLOWED_CHARS = re.compile(r"^[0-9\.\+\-\*\/\(\)\sEe]+$")

_KEY_TO_DIGIT = {
    'ZERO': '0',
    'ONE': '1',
    'TWO': '2',
    'THREE': '3',
    'FOUR': '4',
    'FIVE': '5',
    'SIX': '6',
    'SEVEN': '7',
    'EIGHT': '8',
    'NINE': '9',
}


class ModalNumberInput:
    """
    A helper class to handle numeric input during a modal operation.
    Supports basic math evaluation.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        """Resets the input string."""
        self.value_str = ""

    def has_value(self):
        """Returns True if there is an active input string."""
        return self.value_str != ""

    def get_value(self, initial_value=None):
        """
        Evaluates the input string as a number or a mathematical expression.
        Raises ValueError if the expression is invalid.
        If initial_value is provided and input starts with an operator, it is prepended.
        """
        if not self.value_str:
            raise ValueError("No value to get.")

        expr = self.value_str
        if initial_value is not None and expr and expr[0] in {'*', '/', '+', '-'}:
            expr = f"{initial_value}{expr}"

        if not ALLOWED_CHARS.match(expr):
            raise ValueError("Invalid characters in expression.")

        try:
            return float(eval(expr, {"__builtins__": {}}, {}))
        except (SyntaxError, ZeroDivisionError, TypeError, NameError) as e:
            raise ValueError(f"Invalid math expression: {e}") from None

    def handle_event(self, event):
        """
        Processes a keyboard event and updates the input string.
        Returns True if the event was handled, False otherwise.
        """
        if event.value != 'PRESS':
            return False

        key = event.type

        if key in _KEY_TO_DIGIT:
            u = event.unicode or ''
            if len(u) == 1 and u.isdigit():
                self.value_str += u
            else:
                self.value_str += _KEY_TO_DIGIT[key]
            return True

        elif key.startswith('NUMPAD_'):
            if key[7:].isdigit():
                self.value_str += key[7:]
                return True
            elif key == 'NUMPAD_PERIOD':
                if '.' not in self.value_str:
                    self.value_str += '.'
                return True
            elif key == 'NUMPAD_PLUS':
                self.value_str += '+'
                return True
            elif key == 'NUMPAD_MINUS':
                self.value_str += '-'
                return True
            elif key == 'NUMPAD_ASTERIX':
                self.value_str += '*'
                return True
            elif key == 'NUMPAD_SLASH':
                self.value_str += '/'
                return True

        elif key == 'MINUS':
            self.value_str += '-'
            return True
        elif key == 'PERIOD':
             if '.' not in self.value_str:
                self.value_str += '.'
             return True

        elif event.unicode in {'+', '*', '/'}:
            self.value_str += event.unicode
            return True

        elif key == 'BACK_SPACE':
            if self.value_str:
                self.value_str = self.value_str[:-1]
            return True

        elif key == 'ESC':
            self.reset()
            return True

        return False


class BaseModalOperator:
    """Base class to handle boilerplate for interactive modal operators."""
    _active_instance = None

    @classmethod
    def draw_status_bar(cls, panel_self, context):
        self = cls._active_instance
        if not self:
            return
        status_bar.draw_shortcuts(panel_self.layout, self.get_status_bar_items())

    def base_invoke(self, context, event):
        self.__class__._active_instance = self
        self.number_input = ModalNumberInput()

        from .utils import display_length_to_bu_multiplier, length_bu_to_display_multiplier
        self.unit_scale_display_inv = length_bu_to_display_multiplier(context)
        self.unit_scale = display_length_to_bu_multiplier(context)

        center_x = context.region.x + context.region.width // 2
        center_y = context.region.y + context.region.height // 2
        context.window.cursor_warp(center_x, center_y)
        self.initial_mouse_x = center_x

        status_bar.install_shortcuts(self.__class__)
        context.window_manager.modal_handler_add(self)
        self.base_update_header(context)
        return {'RUNNING_MODAL'}

    def base_cleanup(self, context):
        self.__class__._active_instance = None
        status_bar.clear_all(context, self.__class__)
        self.on_cleanup(context)
        if context.area is not None:
            context.area.tag_redraw()

    def base_update_header(self, context):
        args = self.get_header_args(context)
        if args is not None:
            args['typed_str'] = self.number_input.value_str
            viewport_header.set_numeric(context, **args)

    def modal(self, context, event):
        context.area.tag_redraw()

        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            self.on_confirm(context, event)
            self.base_cleanup(context)
            return {'FINISHED'}
        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            self.on_cancel(context, event)
            self.base_cleanup(context)
            return {'CANCELLED'}
        if self.number_input.handle_event(event):
            self.on_apply_typed_value(context, event)
        elif event.type == 'R' and event.value == 'PRESS':
            self.number_input.reset()
            self.initial_mouse_x = event.mouse_x
            self.on_reset(context, event)
        elif event.type == 'MOUSEMOVE':
            self.number_input.reset()
            delta_x = event.mouse_x - self.initial_mouse_x
            self.on_mouse_move(context, event, delta_x)

        self.on_custom_event(context, event)
        self.base_update_header(context)
        return {'RUNNING_MODAL'}

    def get_status_bar_items(self): return [("Confirm", "[LMB]"), ("Cancel", "[RMB]"), ("Reset", "[R]")]
    def get_header_args(self, context): return None
    def on_confirm(self, context, event): pass
    def on_cancel(self, context, event): pass
    def on_reset(self, context, event): pass
    def on_cleanup(self, context): pass
    def on_mouse_move(self, context, event, delta_x): pass
    def on_apply_typed_value(self, context, event): pass
    def on_custom_event(self, context, event): pass
