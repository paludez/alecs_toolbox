# Operators for adding and managing modifiers
import bpy
from ..modules import utils
from ..modules.modal_handler import ModalNumberInput, update_modal_header
from ..modules.utils import unit_suffixes, draw_modal_status_bar

def get_boolean_collection(context):
    """Helper to get or create the hidden boolean collection."""
    coll_name = "Hidden_Bools"
    if coll_name in bpy.data.collections:
        coll = bpy.data.collections[coll_name]
    else:
        coll = bpy.data.collections.new(coll_name)
        context.scene.collection.children.link(coll)
        coll.color_tag = 'COLOR_01' # Red
    
    if context.view_layer.active_layer_collection.collection != coll:
            coll.hide_viewport = True
    coll.hide_render = True
    return coll

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
        coll = get_boolean_collection(context)

        for target in targets:
            mod = active.modifiers.new(name=f"Bool_{target.name}", type='BOOLEAN')
            mod.operation = self.operation
            mod.object = target
            
            utils.move_to_collection(target, coll)

        return {'FINISHED'}

class ALEC_OT_slice_boolean(bpy.types.Operator):
    """Perform a Slice Boolean (Cut & Separate)"""
    bl_idname = "alec.slice_boolean"
    bl_label = "Slice Boolean"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and len(context.selected_objects) > 1

    def execute(self, context):
        active = context.active_object
        targets = [o for o in context.selected_objects if o != active]

        # Collection setup (reuse existing logic)
        coll = get_boolean_collection(context)

        for target in targets:
            # Add Solidify to cutter to handle planes/open meshes
            # Make it thick enough to cover the active object (create a "box" cutter)
            max_dim = max(active.dimensions) if active.dimensions else 1.0
            mod_solid = target.modifiers.new(name="Slice_Solidify", type='SOLIDIFY')
            mod_solid.thickness = max_dim * 1.5
            mod_solid.offset = 1.0

            # 1. Create the Slice Object (The piece being cut out)
            bpy.ops.object.select_all(action='DESELECT')
            active.select_set(True)
            context.view_layer.objects.active = active
            
            # Duplicate active object
            bpy.ops.object.duplicate(linked=False)
            slice_obj = context.active_object
            slice_obj.name = f"{active.name}_Slice"
            
            # Add Intersect Modifier to Slice (keeps only the overlapping part)
            mod_int = slice_obj.modifiers.new(name=f"Slice_Intersect", type='BOOLEAN')
            mod_int.operation = 'INTERSECT'
            mod_int.object = target
            
            # 2. Add Difference Modifier to Original (cuts the hole)
            mod_diff = active.modifiers.new(name=f"Slice_Diff", type='BOOLEAN')
            mod_diff.operation = 'DIFFERENCE'
            mod_diff.object = target
            
            utils.move_to_collection(target, coll)

        # Restore selection to active
        bpy.ops.object.select_all(action='DESELECT')
        active.select_set(True)
        context.view_layer.objects.active = active

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

        items = [
            ("Axis", "[X]", self.axis_idx == 0),
            ("", "[Y]", self.axis_idx == 1),
            ("", "[Z]", self.axis_idx == 2),
            None,  # Separator
            ("Confirm", "[LMB]"),
            ("Cancel", "[RMB]"),
        ]
        draw_modal_status_bar(panel_self.layout, items)

    def cleanup(self, context):
        ALEC_OT_mirror_control._active_instance = None
        try:
            bpy.types.STATUSBAR_HT_header.remove(ALEC_OT_mirror_control.draw_status_bar)
        except:
            pass # Fails if not found
        context.area.tag_redraw()

    def update_header_text(self, context):
        unit_setting = context.scene.unit_settings.length_unit
        suffix = unit_suffixes.get(unit_setting, '')
        
        distance = self.empty.location[self.axis_idx] - self.initial_loc[self.axis_idx]
        display_dist = distance * self.unit_scale_display_inv

        update_modal_header(context, "Distance", display_dist, self.number_input.value_str, suffix)

    def invoke(self, context, event):
        self.obj = context.active_object
        if not self.obj: return {'CANCELLED'}
        
        self.original_selection = context.selected_objects[:]
        self.active_obj_name = context.active_object.name

        # State
        self.axes = ('X', 'Y', 'Z')
        self.axis_idx = 0
        self.number_input = ModalNumberInput()
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
        self.update_header_text(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        context.area.tag_redraw()

        # --- Finish or Cancel ---
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'}:
            if self.number_input.has_value(): # Apply final typed value
                self.apply_typed_value(event)
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
        if self.number_input.handle_event(event):
            self.apply_typed_value(event)

        # Mouse move resets typing
        elif event.type == 'MOUSEMOVE':
            self.number_input.reset()
            delta_x = event.mouse_x - self.initial_mouse_x
            sens = 0.02
            dist = delta_x * sens
            self.empty.location[self.axis_idx] = self.initial_loc[self.axis_idx] + dist
            
        # Axis change resets typing
        elif event.type in self.axes and event.value == 'PRESS':
            self.number_input.reset()
            self.axis_idx = self.axes.index(event.type)
            self.mod.use_axis = [i == self.axis_idx for i in range(3)]
            # Re-apply mouse delta on new axis
            delta_x = event.mouse_x - self.initial_mouse_x
            sens = 0.02
            dist = delta_x * sens
            self.empty.location = self.initial_loc.copy()
            self.empty.location[self.axis_idx] += dist
        
        self.update_header_text(context)
        return {'RUNNING_MODAL'}

    def apply_typed_value(self, event):
        if not self.number_input.has_value(): return
        try:
            typed_val = self.number_input.get_value()
            typed_dist_abs = abs(typed_val * self.unit_scale)
            delta_x = event.mouse_x - self.initial_mouse_x
            direction = 1 if delta_x >= 0 else -1
            final_dist = typed_dist_abs * direction
            self.empty.location[self.axis_idx] = self.initial_loc[self.axis_idx] + final_dist
        except ValueError:
            pass # Ignore errors from partial input like "-"

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

    _active_instance = None

    mod: bpy.types.Modifier
    number_input: ModalNumberInput
    unit_scale: float
    unit_scale_display_inv: float
    initial_mouse_x: int
    initial_thickness: float

    @staticmethod
    def draw_status_bar(panel_self, context):
        self = ALEC_OT_solidify_modal._active_instance
        if not self:
            return

        items = [
            ("Confirm", "[LMB]"),
            ("Cancel", "[RMB]"),
            ("Reset", "[R]"),
        ]
        draw_modal_status_bar(panel_self.layout, items)

    def cleanup(self, context):
        ALEC_OT_solidify_modal._active_instance = None
        try:
            bpy.types.STATUSBAR_HT_header.remove(ALEC_OT_solidify_modal.draw_status_bar)
        except:
            pass  # Fails if not found
        context.area.header_text_set(None)
        context.area.tag_redraw()

    def update_header_text(self, context):
        unit_setting = context.scene.unit_settings.length_unit
        suffix = unit_suffixes.get(unit_setting, '')
        
        thickness_val = self.mod.thickness * self.unit_scale_display_inv
        
        update_modal_header(context, "Thickness", thickness_val, self.number_input.value_str, suffix)

    def invoke(self, context, event):
        obj = context.active_object
        if not obj:
            return {'CANCELLED'}

        self.mod = obj.modifiers.new(name="Solidify", type='SOLIDIFY')
        self.initial_thickness = self.mod.thickness

        # Switch to modifier tab
        for area in context.screen.areas:
            if area.type == 'PROPERTIES':
                area.spaces[0].context = 'MODIFIER'
        
        # State
        self.number_input = ModalNumberInput()
        self.unit_scale = utils.get_unit_scale(context)
        self.unit_scale_display_inv = 1.0 / self.unit_scale if self.unit_scale != 0 else 1.0

        # Mouse state
        center_x = context.region.x + context.region.width // 2
        center_y = context.region.y + context.region.height // 2
        context.window.cursor_warp(center_x, center_y)
        self.initial_mouse_x = center_x
        
        ALEC_OT_solidify_modal._active_instance = self
        bpy.types.STATUSBAR_HT_header.prepend(ALEC_OT_solidify_modal.draw_status_bar)
        context.window_manager.modal_handler_add(self)
        self.update_header_text(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        context.area.tag_redraw()

        # --- Finish or Cancel ---
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'}:
            self.cleanup(context)
            return {'FINISHED'}

        if event.type in {'RIGHTMOUSE', 'ESC'}:
            # Restore initial thickness and remove modifier
            self.mod.thickness = self.initial_thickness
            context.active_object.modifiers.remove(self.mod)
            self.cleanup(context)
            return {'CANCELLED'}

        # --- Handle Modal Events ---
        if self.number_input.handle_event(event):
            pass  # Handled by number input

        elif event.type == 'R' and event.value == 'PRESS':
            self.number_input.reset()
            self.mod.thickness = self.initial_thickness
            # Reset mouse reference to prevent jumping on next mouse move
            self.initial_mouse_x = event.mouse_x

        elif event.type == 'MOUSEMOVE':
            self.number_input.reset()
            delta_x = event.mouse_x - self.initial_mouse_x
            # Sensitivity - using a smaller factor for thickness
            sens = -0.01 * (0.1 if event.shift else 1.0)
            self.mod.thickness = self.initial_thickness + (delta_x * sens)

        # Apply typed value if it exists
        if self.number_input.has_value():
            try:
                typed_val = self.number_input.get_value()
                self.mod.thickness = typed_val * self.unit_scale
            except ValueError:
                pass  # Ignore errors from partial input like "-"

        self.update_header_text(context)
        return {'RUNNING_MODAL'}

class ALEC_OT_add_subdivision(bpy.types.Operator):
    """Add Subdivision Surface Modifier"""
    bl_idname = "alec.add_subdivision"
    bl_label = "Add Subdivision"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        bpy.ops.object.modifier_add(type='SUBSURF')
        for area in context.screen.areas:
            if area.type == 'PROPERTIES':
                area.spaces[0].context = 'MODIFIER'
        return {'FINISHED'}

class ALEC_OT_modifier_action(bpy.types.Operator):
    """Manage Modifiers: Apply, Delete, Move"""
    bl_idname = "alec.modifier_action"
    bl_label = "Modifier Action"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(
        items=[
            ('APPLY_LAST', "Apply Last", "Apply the last modifier"),
            ('APPLY_ALL', "Apply All", "Apply all modifiers"),
            ('DELETE_LAST', "Delete Last", "Delete the last modifier"),
            ('DELETE_ALL', "Delete All", "Delete all modifiers"),
            ('MOVE_UP', "Move Up", "Move modifier up"),
            ('MOVE_DOWN', "Move Down", "Move modifier down"),
        ]
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        mods = obj.modifiers

        if self.action == 'APPLY_ALL':
            bpy.ops.object.convert(target='MESH')
            self.report({'INFO'}, "Applied all modifiers")
            return {'FINISHED'}
        
        if self.action == 'DELETE_ALL':
            mods.clear()
            self.report({'INFO'}, "Deleted all modifiers")
            return {'FINISHED'}

        # Actions requiring a specific modifier
        if not mods:
            self.report({'WARNING'}, "Object has no modifiers")
            return {'CANCELLED'}
        mod = obj.modifiers.active if obj.modifiers.active else obj.modifiers[-1]

        if self.action == 'APPLY_LAST':
            mod = mods[-1] # Specifically last one
            mod_name = mod.name
            try:
                bpy.ops.object.modifier_apply(modifier=mod_name)
                self.report({'INFO'}, f"Applied: {mod_name}")
            except Exception as e:
                self.report({'WARNING'}, f"Failed: {e}")
                return {'CANCELLED'}
        
        elif self.action == 'DELETE_LAST':
            mod = mods[-1]
            mod_name = mod.name
            mods.remove(mod)
            self.report({'INFO'}, f"Deleted: {mod_name}")
            
        elif self.action == 'MOVE_UP':
            bpy.ops.object.modifier_move_up(modifier=mod.name)
            self.report({'INFO'}, f"Moved '{mod.name}' Up")
            
        elif self.action == 'MOVE_DOWN':
            bpy.ops.object.modifier_move_down(modifier=mod.name)
            self.report({'INFO'}, f"Moved '{mod.name}' Down")

        return {'FINISHED'}

classes = [
    ALEC_OT_boolean_op,
    ALEC_OT_slice_boolean,
    ALEC_OT_mirror_control,
    ALEC_OT_add_mirror,
    ALEC_OT_solidify_modal,
    ALEC_OT_add_subdivision,
    ALEC_OT_modifier_action,
]
