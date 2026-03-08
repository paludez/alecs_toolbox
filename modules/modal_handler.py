import bpy
from . import utils

class ModalNumberInput:
    """Handles numeric input for modal operators."""
    
    def __init__(self):
        self.value_str = ""
        self.num_map = {
            'ZERO': '0', 'ONE': '1', 'TWO': '2', 'THREE': '3', 'FOUR': '4',
            'FIVE': '5', 'SIX': '6', 'SEVEN': '7', 'EIGHT': '8', 'NINE': '9',
            'NUMPAD_0': '0', 'NUMPAD_1': '1', 'NUMPAD_2': '2', 'NUMPAD_3': '3', 'NUMPAD_4': '4',
            'NUMPAD_5': '5', 'NUMPAD_6': '6', 'NUMPAD_7': '7', 'NUMPAD_8': '8', 'NUMPAD_9': '9'
        }

    def handle_event(self, event):
        """
        Process a keyboard event and update the number string.
        Returns True if the event was handled, False otherwise.
        """
        if event.type == 'BACKSPACE' and event.value == 'PRESS':
            if len(self.value_str) > 0:
                self.value_str = self.value_str[:-1]
            return True
        elif event.type == 'MINUS' and event.value == 'PRESS':
            if self.value_str and self.value_str.startswith('-'):
                self.value_str = self.value_str[1:]
            else:
                self.value_str = '-' + self.value_str
            return True
        elif event.type in self.num_map and event.value == 'PRESS':
            self.value_str += self.num_map[event.type]
            return True
        elif event.type in {'PERIOD', 'NUMPAD_PERIOD'} and event.value == 'PRESS':
            if '.' not in self.value_str:
                self.value_str += '.'
            return True
        
        return False

    def get_value(self):
        """
        Get the float value from the current string.
        Returns 0.0 if the string is empty or invalid.
        """
        if self.value_str:
            try:
                return float(self.value_str)
            except ValueError:
                return 0.0
        return 0.0
    
    def has_value(self):
        return self.value_str != ""
    
    def reset(self):
        self.value_str = ""


def draw_modal_status_bar(layout, message="Confirm: [LMB] | Cancel: [RMB]"):
    """Draws a standard status bar for modal operators."""
    row = layout.row(align=True)
    row.label(text=message)


def update_modal_header(context, base_text="Value", value=0.0, value_str="", unit_suffix=''):
    """
    Updates the header with a formatted value.
    Example: "Offset: 1.25m" or "Segments: 12"
    """
    header_text_val = ""
    if value_str:
        header_text_val = value_str
    else:
        # Round to avoid floating point inaccuracies for display
        display_val = round(value, 4)
        if display_val == -0.0:
            display_val = 0.0
        
        # Display as integer if it's a whole number
        if display_val == int(display_val):
            header_text_val = f"{int(display_val)}"
        else:
            header_text_val = f"{display_val:.4f}".rstrip('0').rstrip('.')

    context.area.header_text_set(f"{base_text}: {header_text_val}{unit_suffix}")
