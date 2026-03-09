# modules/modal_handler.py
import bpy
import re

# A restricted list of characters allowed in the math expression
# This is a security measure for using eval()
ALLOWED_CHARS = re.compile(r"^[0-9\.\+\-\*\/\(\)\sEe]+$")

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

        # Security check: only allow safe characters
        if not ALLOWED_CHARS.match(expr):
            raise ValueError("Invalid characters in expression.")
            
        # Use Python's eval to compute the result
        try:
            # The first argument to eval is the source, the others are globals/locals.
            # By providing empty dicts, we restrict the execution environment.
            return float(eval(expr, {"__builtins__": {}}, {}))
        except (SyntaxError, ZeroDivisionError, TypeError, NameError) as e:
            # Catch potential errors from eval and raise a ValueError
            raise ValueError(f"Invalid math expression: {e}")

    def handle_event(self, event):
        """
        Processes a keyboard event and updates the input string.
        Returns True if the event was handled, False otherwise.
        """
        if event.value != 'PRESS':
            return False

        key = event.type
        
        if key in {'ZERO', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE'}:
            self.value_str += event.unicode
            return True
        
        # Numpad numbers
        elif key.startswith('NUMPAD_'):
            if key[7:].isdigit():
                self.value_str += key[7:]
                return True
            elif key == 'NUMPAD_PERIOD':
                if '.' not in self.value_str:
                    self.value_str += '.'
                return True
            # Numpad math operators
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

        # Keyboard math operators
        elif key == 'MINUS':
            self.value_str += '-'
            return True
        elif key == 'PERIOD':
             if '.' not in self.value_str:
                self.value_str += '.'
             return True
        
        # Other operators might need shift, which is harder to check reliably across keyboards.
        # Let's add them by unicode.
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

def update_modal_header(context, main_label, main_value, typed_str, suffix="", secondary_text="", initial_value=None, precision=4):
    """Updates the 3D View header with formatted text for a modal operator."""
    if typed_str:
        if initial_value is not None and typed_str[0] in {'*', '/', '+', '-'}:
            formatted_initial = f"{initial_value:.{precision}f}".rstrip('0').rstrip('.')
            if formatted_initial == '-0': formatted_initial = '0'
            header_text = f"{main_label}: {formatted_initial}{suffix} {typed_str}"
        else:
            header_text = f"{main_label}: {typed_str}"
    else:
        formatted_main = f"{main_value:.{precision}f}".rstrip('0').rstrip('.')
        if formatted_main == '-0': formatted_main = '0'
        header_text = f"{main_label}: {formatted_main}{suffix}"
    
    if secondary_text:
        header_text += f"  |  {secondary_text}"

    context.area.header_text_set(header_text)