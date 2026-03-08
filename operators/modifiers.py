# Operators for adding and managing modifiers
import bpy
from ..modules import utils

class ALEC_OT_boolean_op(bpy.types.Operator):
    """Add Boolean Modifier and hide target in 'Hidden_Bools'"""
    bl_idname = "alec.boolean_op"
    bl_label = "Boolean Operation"
    bl_options = {'REGISTER', 'UNDO'}

    operation: bpy.props.EnumProperty(
        items=[('UNION', "Union", ""), ('INTERSECT', "Intersect", ""), ('DIFFERENCE', "Difference", "")]
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        return context.active_object and len(context.selected_objects) > 1

    def execute(self, context):
        active = context.active_object
        targets = [o for o in context.selected_objects if o != active]

        # Collection setup
        coll_name = "Hidden_Bools"
        if coll_name in bpy.data.collections:
            coll = bpy.data.collections[coll_name]
        else:
            coll = bpy.data.collections.new(coll_name)
            context.scene.collection.children.link(coll)
        
        # Ensure collection is hidden
        if context.view_layer.active_layer_collection.collection != coll:
             coll.hide_viewport = True

        coll.hide_render = True
        coll.color_tag = 'COLOR_01' # Red

        for target in targets:
            mod = active.modifiers.new(name=f"Bool_{target.name}", type='BOOLEAN')
            mod.operation = self.operation
            mod.object = target
            
            # Move to collection
            for c in target.users_collection:
                c.objects.unlink(target)
            if target.name not in coll.objects:
                coll.objects.link(target)

        return {'FINISHED'}

class ALEC_OT_mirror_control(bpy.types.Operator):
    """Add Mirror Modifier controlled by a new Empty with interactive placement.
    X,Y,Z to change axis.
    """
    bl_idname = "alec.mirror_control"
    bl_label = "Mirror with Control"
    bl_options = {'REGISTER', 'UNDO', 'GRAB_CURSOR', 'BLOCKING'}

    _active_instance = None

    @staticmethod
    def draw_status_bar(panel_self, context):
        self = ALEC_OT_mirror_control._active_instance
        if not self:
            return

        layout = panel_self.layout
        row = layout.row(align=True)

        row.label(text="Axis:")
        
        axis_row = row.row(align=True)
        
        sub = axis_row.row(align=True)
        sub.alert = self.axis_idx == 0
        sub.label(text="[X]")

        sub = axis_row.row(align=True)
        sub.alert = self.axis_idx == 1
        sub.label(text="[Y]")

        sub = axis_row.row(align=True)
        sub.alert = self.axis_idx == 2
        sub.label(text="[Z]")
        
        row.separator()
        row.label(text="Confirm: [LMB] | Cancel: [RMB]")

    def cleanup(self, context):
        ALEC_OT_mirror_control._active_instance = None
        try:
            bpy.types.STATUSBAR_HT_header.remove(ALEC_OT_mirror_control.draw_status_bar)
        except:
            pass # Fails if not found
        context.area.tag_redraw()

    def update_header(self, context):
        unit_setting = context.scene.unit_settings.length_unit
        unit_suffixes = {
            'METERS': 'm', 'CENTIMETERS': 'cm', 'MILLIMETERS': 'mm', 'KILOMETERS': 'km',
            'MICROMETERS': 'μm',
            'FEET': "'", 'INCHES': '"', 'MILES': 'mi', 'THOU': 'thou'
        }
        suffix = unit_suffixes.get(unit_setting, '')

        header_text_val = ""
        if self.value_str:
            header_text_val = self.value_str
        else:
            distance = self.empty.location[self.axis_idx] - self.initial_loc[self.axis_idx]
            display_dist = distance * self.unit_scale_display_inv
            
            # Round to a reasonable precision for display
            display_dist = round(display_dist, 4)
            if display_dist == -0.0:
                display_dist = 0.0
            
            # Ensure at least one decimal place for whole numbers
            if display_dist == int(display_dist):
                header_text_val = f"{display_dist:.1f}"
            else:
                header_text_val = str(display_dist)
            
        header_text = f"Distance: {header_text_val}{suffix}"
        context.area.header_text_set(header_text)

    def invoke(self, context, event):
        self.obj = context.active_object
        if not self.obj: return {'CANCELLED'}
        
        self.original_selection = context.selected_objects[:]
        self.active_obj_name = context.active_object.name

        # State
        self.axes = ('X', 'Y', 'Z')
        self.axis_idx = 0
        self.value_str = ""
        self.unit_scale = utils.get_unit_scale(context)
        self.unit_scale_display_inv = 1.0 / self.unit_scale if self.unit_scale != 0 else 1.0

        # Start at object center
        start_loc = self.obj.matrix_world.translation
        
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=start_loc)
        self.empty = context.active_object
        self.empty.name = f"Mirror_Ctrl_{self.obj.name}"
        
        self.mod = self.obj.modifiers.new(name="Mirror_Ctrl", type='MIRROR')
        self.mod.mirror_object = self.empty
        
        self.mod.use_axis = [i == self.axis_idx for i in range(3)]
        self.initial_loc = start_loc.copy()
        
        # Mouse state
        center_x = context.region.x + context.region.width // 2
        center_y = context.region.y + context.region.height // 2
        context.window.cursor_warp(center_x, center_y)
        self.initial_mouse_x = center_x
        
        ALEC_OT_mirror_control._active_instance = self
        bpy.types.STATUSBAR_HT_header.prepend(ALEC_OT_mirror_control.draw_status_bar)
        context.window_manager.modal_handler_add(self)
        self.update_header(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        self.update_header(context)
        context.area.tag_redraw()

        # --- Finish or Cancel ---
        if event.type in {'LEFTMOUSE', 'ENTER'}:
            if self.value_str: # Apply final typed value
                try:
                    typed_val = float(self.value_str)
                    typed_dist_abs = abs(typed_val * self.unit_scale)
                    delta_x = event.mouse_x - self.initial_mouse_x
                    direction = 1 if delta_x >= 0 else -1
                    final_dist = typed_dist_abs * direction
                    self.empty.location[self.axis_idx] = self.initial_loc[self.axis_idx] + final_dist
                except ValueError:
                    pass # Ignore invalid final string
            self.cleanup(context)
            context.area.header_text_set(None)
            bpy.ops.object.select_all(action='DESELECT')
            self.obj.select_set(True)
            self.empty.select_set(True)
            context.view_layer.objects.active = self.obj
            return {'FINISHED'}

        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self.cleanup(context)
            context.area.header_text_set(None)
            # Restore original location before cancelling
            self.empty.location = self.initial_loc
            self.obj.modifiers.remove(self.mod)
            bpy.data.objects.remove(self.empty, do_unlink=True)
            bpy.ops.object.select_all(action='DESELECT')
            for obj in self.original_selection:
                obj.select_set(True)
            context.view_layer.objects.active = bpy.data.objects[self.active_obj_name]
            return {'CANCELLED'}
        
        # --- Handle modal events ---
        
        # Mouse move resets typing
        if event.type == 'MOUSEMOVE':
            self.value_str = ""
            delta_x = event.mouse_x - self.initial_mouse_x
            sens = 0.02
            dist = delta_x * sens
            self.empty.location[self.axis_idx] = self.initial_loc[self.axis_idx] + dist
            
        # Axis change resets typing
        elif event.type in self.axes and event.value == 'PRESS':
            self.value_str = ""
            self.axis_idx = self.axes.index(event.type)
            self.mod.use_axis = [i == self.axis_idx for i in range(3)]
            # Re-apply mouse delta on new axis
            delta_x = event.mouse_x - self.initial_mouse_x
            sens = 0.02
            dist = delta_x * sens
            self.empty.location = self.initial_loc.copy()
            self.empty.location[self.axis_idx] += dist

        # --- Keyboard Input ---
        elif event.type == 'BACKSPACE' and event.value == 'PRESS':
            if len(self.value_str) > 0:
                self.value_str = self.value_str[:-1]

        elif event.type == 'MINUS' and event.value == 'PRESS':
            if self.value_str and self.value_str.startswith('-'):
                self.value_str = self.value_str[1:]
            else:
                self.value_str = '-' + self.value_str
        
        elif event.value == 'PRESS' and event.unicode:
            if event.unicode.isdigit():
                self.value_str += event.unicode
            elif event.unicode == '.':
                if '.' not in self.value_str:
                    self.value_str += '.'

        # Apply typed value if it exists
        if self.value_str:
            try:
                typed_val = float(self.value_str)
                typed_dist_abs = abs(typed_val * self.unit_scale)
                delta_x = event.mouse_x - self.initial_mouse_x
                direction = 1 if delta_x >= 0 else -1
                final_dist = typed_dist_abs * direction
                self.empty.location[self.axis_idx] = self.initial_loc[self.axis_idx] + final_dist
            except ValueError:
                pass # Ignore errors from partial input like "-"

        return {'RUNNING_MODAL'}


class ALEC_OT_add_mirror(bpy.types.Operator):
    """Add Mirror Modifier and switch to Modifiers tab"""
    bl_idname = "alec.add_mirror"
    bl_label = "Add Mirror"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        bpy.ops.object.modifier_add(type='MIRROR')
        for area in context.screen.areas:
            if area.type == 'PROPERTIES':
                area.spaces[0].context = 'MODIFIER'
        return {'FINISHED'}

class ALEC_OT_solidify_modal(bpy.types.Operator):
    """Add Solidify Modifier and adjust thickness interactively"""
    bl_idname = "alec.solidify_modal"
    bl_label = "Solidify Interactive"
    bl_options = {'REGISTER', 'UNDO', 'GRAB_CURSOR', 'BLOCKING'}

    def invoke(self, context, event):
        obj = context.active_object
        if not obj: return {'CANCELLED'}

        self.mod = obj.modifiers.new(name="Solidify", type='SOLIDIFY')
        
        # Switch to modifier tab
        for area in context.screen.areas:
            if area.type == 'PROPERTIES':
                area.spaces[0].context = 'MODIFIER'

        center_x = context.region.x + context.region.width // 2
        center_y = context.region.y + context.region.height // 2
        context.window.cursor_warp(center_x, center_y)
        self.initial_mouse_y = center_y
        
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            delta = event.mouse_y - self.initial_mouse_y
            self.mod.thickness = -delta * 0.01
            return {'RUNNING_MODAL'}

        elif event.type in {'LEFTMOUSE', 'ENTER'}:
            return {'FINISHED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            context.active_object.modifiers.remove(self.mod)
            return {'CANCELLED'}

        return {'PASS_THROUGH'}

classes = [
    ALEC_OT_boolean_op,
    ALEC_OT_mirror_control,
    ALEC_OT_add_mirror,
    ALEC_OT_solidify_modal,
]
