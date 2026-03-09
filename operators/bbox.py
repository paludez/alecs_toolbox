import bpy
from ..modules import bbox_tools
from ..modules.modal_handler import ModalNumberInput, update_modal_header
from ..modules.utils import unit_suffixes, draw_modal_status_bar, get_unit_scale

class BBoxOperatorBase:
    bl_options = {'REGISTER', 'UNDO'}
    mode: str = ""

    def execute(self, context):
        if not self.mode:
            self.report({'ERROR'}, "Mode not set in BBox operator subclass") # type: ignore
            return {'CANCELLED'}
        
        # Delegate to bbox_tools
        bbox_tools.create_bbox(context, mode=self.mode)
        return {'FINISHED'}
        
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

    unit_scale: float
    unit_scale_display_inv: float
    initial_mouse_x: int
    
    number_input: ModalNumberInput

    @staticmethod
    def draw_status_bar(panel_self, context):
        self = ALEC_OT_bbox_offset_modal._active_instance
        if not self:
            return

        items = [
            ("Confirm", "[LMB]"),
            ("Cancel", "[RMB]"),
            ("Reset", "[R]"),
        ]
        draw_modal_status_bar(panel_self.layout, items)

    def cleanup(self, context):
        """Remove modal state and drawings."""
        ALEC_OT_bbox_offset_modal._active_instance = None
        try:
            bpy.types.STATUSBAR_HT_header.remove(ALEC_OT_bbox_offset_modal.draw_status_bar)
        except:
            pass  # Fails if not found
        context.area.tag_redraw()
        context.area.header_text_set(None)

    def invoke(self, context, event):
        """Setup for the modal operator."""
        self.offset_obj, self.orig_coords, self.orig_normals, self.source_obj = bbox_tools.create_interactive_offset_bbox(context)

        if not self.offset_obj:
            self.report({'WARNING'}, "No valid mesh object selected or object has no vertices.")
            return {'CANCELLED'}

        # Initial State
        self.number_input = ModalNumberInput()
        self.unit_scale = get_unit_scale(context)
        self.unit_scale_display_inv = 1.0 / self.unit_scale if self.unit_scale != 0 else 1.0

        # Mouse State
        center_x = context.region.x + context.region.width // 2
        context.window.cursor_warp(center_x, event.mouse_y)
        self.initial_mouse_x = center_x
        
        # Initial update
        self.update_offset(context, 0.0)

        ALEC_OT_bbox_offset_modal._active_instance = self
        bpy.types.STATUSBAR_HT_header.prepend(ALEC_OT_bbox_offset_modal.draw_status_bar)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        """Handle events during the modal operation."""
        offset = 0.0

        # --- Finish or Cancel ---
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'}:
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
        if self.number_input.handle_event(event):
            # If number input handled the event, we just update the offset
            pass

        elif event.type == 'R' and event.value == 'PRESS':
             self.number_input.reset()
             self.initial_mouse_x = event.mouse_x

        elif event.type == 'MOUSEMOVE':
            self.number_input.reset()
            delta_x = event.mouse_x - self.initial_mouse_x
            sens = 0.005  # Lower sensitivity for smaller offset values
            offset = delta_x * sens

        # --- Apply Offset ---
        if self.number_input.has_value():
            typed_val = self.number_input.get_value()
            offset = typed_val * self.unit_scale
        
        self.update_offset(context, offset)
        
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def update_offset(self, context, offset):
        """Update the object, header, and viewport."""
        bbox_tools.update_interactive_offset_bbox(self.offset_obj, offset, self.orig_coords, self.orig_normals)
        
        display_dist = offset * self.unit_scale_display_inv
        suffix = unit_suffixes.get(context.scene.unit_settings.length_unit, '')
        update_modal_header(context, "Offset", display_dist, self.number_input.value_str, suffix)

class ALEC_OT_bbox_local(BBoxOperatorBase, bpy.types.Operator):
    """Create a bounding box aligned to the object's local axes"""
    bl_idname = "alec.bbox_local"
    bl_label = "LOCAL"
    mode = 'LOCAL'

class ALEC_OT_bbox_world(BBoxOperatorBase, bpy.types.Operator):
    """Create a bounding box aligned to the world axes"""
    bl_idname = "alec.bbox_world"
    bl_label = "WORLD"
    mode = 'WORLD'

classes = [
    ALEC_OT_bbox_offset_modal,
    ALEC_OT_bbox_local,
    ALEC_OT_bbox_world,
]
