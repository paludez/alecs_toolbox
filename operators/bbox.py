import bpy
from ..modules import bbox_tools, utils

class ALEC_OT_bbox_offset_modal(bpy.types.Operator):
    """Create an offset of a mesh object with interactive mouse and keyboard control."""
    bl_idname = "alec.bbox_offset_modal"
    bl_label = "Interactive BBox Offset"
    bl_options = {'REGISTER', 'UNDO', 'GRAB_CURSOR', 'BLOCKING'}

    _active_instance = None

    offset_obj: bpy.types.Object
    source_obj: bpy.types.Object
    orig_coords: list
    orig_normals: list

    value_str: str
    unit_scale: float
    unit_scale_display_inv: float
    initial_mouse_x: int

    # Map keyboard events to numbers
    num_map = {
        'ZERO': '0', 'ONE': '1', 'TWO': '2', 'THREE': '3', 'FOUR': '4',
        'FIVE': '5', 'SIX': '6', 'SEVEN': '7', 'EIGHT': '8', 'NINE': '9',
        'NUMPAD_0': '0', 'NUMPAD_1': '1', 'NUMPAD_2': '2', 'NUMPAD_3': '3', 'NUMPAD_4': '4',
        'NUMPAD_5': '5', 'NUMPAD_6': '6', 'NUMPAD_7': '7', 'NUMPAD_8': '8', 'NUMPAD_9': '9'
    }

    @staticmethod
    def draw_status_bar(panel_self, context):
        self = ALEC_OT_bbox_offset_modal._active_instance
        if not self: return
        layout = panel_self.layout
        row = layout.row(align=True)
        row.label(text="Confirm: [LMB] | Cancel: [RMB] | Reset: [R]")

    def cleanup(self, context):
        """Remove modal state and drawings."""
        ALEC_OT_bbox_offset_modal._active_instance = None
        try:
            bpy.types.STATUSBAR_HT_header.remove(ALEC_OT_bbox_offset_modal.draw_status_bar)
        except:
            pass  # Fails if not found
        context.area.tag_redraw()
        context.area.header_text_set(None)

    def update_header(self, context, offset_val=0.0):
        """Update the header with the current offset value."""
        unit_setting = context.scene.unit_settings.length_unit
        unit_suffixes = {
            'METERS': 'm', 'CENTIMETERS': 'cm', 'MILLIMETERS': 'mm', 'KILOMETERS': 'km',
            'MICROMETERS': 'μm', 'FEET': "'", 'INCHES': '"', 'MILES': 'mi', 'THOU': 'thou'
        }
        suffix = unit_suffixes.get(unit_setting, '')

        header_text_val = ""
        if self.value_str:
            header_text_val = self.value_str
        else:
            display_dist = offset_val * self.unit_scale_display_inv
            display_dist = round(display_dist, 4)
            if display_dist == -0.0:
                display_dist = 0.0
            
            if display_dist == int(display_dist):
                header_text_val = f"{display_dist:.1f}"
            else:
                header_text_val = str(display_dist)
        
        context.area.header_text_set(f"Offset: {header_text_val}{suffix}")

    def invoke(self, context, event):
        """Setup for the modal operator."""
        self.offset_obj, self.orig_coords, self.orig_normals, self.source_obj = bbox_tools.create_interactive_offset_bbox(context)

        if not self.offset_obj:
            self.report({'WARNING'}, "No valid mesh object selected or object has no vertices.")
            return {'CANCELLED'}

        # Initial State
        self.value_str = ""
        self.unit_scale = utils.get_unit_scale(context)
        self.unit_scale_display_inv = 1.0 / self.unit_scale if self.unit_scale != 0 else 1.0

        # Mouse State
        center_x = context.region.x + context.region.width // 2
        context.window.cursor_warp(center_x, event.mouse_y)
        self.initial_mouse_x = center_x
        
        # Initial update
        bbox_tools.update_interactive_offset_bbox(self.offset_obj, 0.0, self.orig_coords, self.orig_normals)
        self.update_header(context, 0.0)

        ALEC_OT_bbox_offset_modal._active_instance = self
        bpy.types.STATUSBAR_HT_header.prepend(ALEC_OT_bbox_offset_modal.draw_status_bar)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        """Handle events during the modal operation."""
        offset = 0.0

        # --- Finish or Cancel ---
        if event.type in {'LEFTMOUSE', 'ENTER'}:
            self.cleanup(context)
            # Final selection setup
            bpy.ops.object.select_all(action='DESELECT')
            self.offset_obj.select_set(True)
            context.view_layer.objects.active = self.offset_obj
            return {'FINISHED'}

        if event.type in {'RIGHTMOUSE', 'ESC'}:
            # On cancel, remove the newly created offset object
            if self.offset_obj:
                bpy.data.objects.remove(self.offset_obj, do_unlink=True)
            self.cleanup(context)
            # Restore selection to the original object
            if self.source_obj:
                bpy.ops.object.select_all(action='DESELECT')
                self.source_obj.select_set(True)
                context.view_layer.objects.active = self.source_obj
            return {'CANCELLED'}
            
        # --- Handle Modal Events ---
        if event.type == 'R' and event.value == 'PRESS':
             self.value_str = ""
             self.initial_mouse_x = event.mouse_x

        elif event.type == 'MOUSEMOVE':
            self.value_str = ""
            delta_x = event.mouse_x - self.initial_mouse_x
            sens = 0.005  # Lower sensitivity for smaller offset values
            offset = delta_x * sens

        # --- Keyboard Input for Numbers ---
        elif event.type == 'BACKSPACE' and event.value == 'PRESS':
            if len(self.value_str) > 0:
                self.value_str = self.value_str[:-1]
        elif event.type == 'MINUS' and event.value == 'PRESS':
            if self.value_str and self.value_str.startswith('-'):
                self.value_str = self.value_str[1:]
            else:
                self.value_str = '-' + self.value_str
        elif event.type in self.num_map and event.value == 'PRESS':
            self.value_str += self.num_map[event.type]
        elif event.type in {'PERIOD', 'NUMPAD_PERIOD'} and event.value == 'PRESS':
            if '.' not in self.value_str:
                self.value_str += '.'

        # --- Apply Offset ---
        # Get offset from typed string if it exists
        if self.value_str:
            try:
                # Convert user-typed value from scene units to Blender units
                typed_val = float(self.value_str)
                offset = typed_val * self.unit_scale
            except ValueError:
                offset = 0.0  # Use 0 if string is invalid (e.g., just "-")
        
        # Update the object and header
        bbox_tools.update_interactive_offset_bbox(self.offset_obj, offset, self.orig_coords, self.orig_normals)
        self.update_header(context, offset)
        
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

classes = [
    ALEC_OT_bbox_offset_modal,
]
