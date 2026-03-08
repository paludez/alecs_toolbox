import bpy
from . import utils

class ModalNumberInput:
    """Handles numeric input for modal operators."""
    
    def __init__(self):
        self.value_str = ""

    def handle_event(self, event):
        """
        Process a keyboard event and update the number string.
        Returns True if the event was handled, False otherwise.
        """
        # Handle Backspace on release
        if event.type == 'BACK_SPACE' and event.value == 'RELEASE':
            if len(self.value_str) > 0:
                self.value_str = self.value_str[:-1]
            return True

        if event.value == 'PRESS':
            if event.type in {'MINUS', 'NUMPAD_MINUS'}:
                if self.value_str and self.value_str.startswith('-'):
                    self.value_str = self.value_str[1:]
                else:
                    self.value_str = '-' + self.value_str
                return True
            elif event.type in {'PERIOD', 'NUMPAD_PERIOD'}:
                if '.' not in self.value_str:
                    self.value_str += '.'
                return True
            elif event.unicode and event.unicode.isdigit():
                self.value_str += event.unicode
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


def update_modal_header(context, base_text="Value", value=0.0, value_str="", unit_suffix='', secondary_text=""):
    """
    Updates the header with a formatted value.
    Can also include secondary information like "Length: 1.5m / Initial: 1.0m"
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

    final_text = f"{base_text}: {header_text_val}{unit_suffix}"
    if secondary_text:
        final_text += f" / {secondary_text}"

    context.area.header_text_set(final_text)
