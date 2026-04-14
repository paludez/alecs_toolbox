import bpy
from ..modules.modal_handler import BaseModalOperator
from ..modules.utils import unit_suffixes, draw_modal_status_bar, get_unit_scale, move_to_collection, switch_to_modifier_tab

def _find_layer_collection(layer_coll, target_coll):
    if layer_coll.collection == target_coll:
        return layer_coll
    for child in layer_coll.children:
        found = _find_layer_collection(child, target_coll)
        if found:
            return found
    return None


def _collection_contains(root, target):
    if root == target:
        return True
    for child in root.children:
        if _collection_contains(child, target):
            return True
    return False


def _selected_outliner_collections(context):
    result = []
    for item in getattr(context, "selected_ids", []):
        if isinstance(item, bpy.types.Collection):
            result.append(item)
    return result

def get_boolean_collection(context):
    """Helper to get or create the hidden boolean collection."""
    coll_name = "Hidden_Bools"
    if coll_name in bpy.data.collections:
        coll = bpy.data.collections[coll_name]
    else:
        coll = bpy.data.collections.new(coll_name)
        context.scene.collection.children.link(coll)
        coll.color_tag = 'COLOR_01'

    # Keep collection visible in viewport flags, but excluded from current View Layer.
    coll.hide_viewport = False
    coll.hide_render = True

    layer_coll = _find_layer_collection(context.view_layer.layer_collection, coll)
    if layer_coll:
        layer_coll.exclude = True

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

        coll = get_boolean_collection(context)

        for target in targets:
            mod = active.modifiers.new(name=f"Bool_{target.name}", type='BOOLEAN')
            mod.operation = self.operation
            mod.object = target
            
            move_to_collection(target, coll)

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

        coll = get_boolean_collection(context)

        for target in targets:
            max_dim = max(active.dimensions) if active.dimensions else 1.0
            mod_solid = target.modifiers.new(name="Slice_Solidify", type='SOLIDIFY')
            mod_solid.thickness = max_dim * 1.5
            mod_solid.offset = 1.0

            bpy.ops.object.select_all(action='DESELECT')
            active.select_set(True)
            context.view_layer.objects.active = active

            bpy.ops.object.duplicate(linked=False)
            slice_obj = context.active_object
            slice_obj.name = f"{active.name}_Slice"
            
            mod_int = slice_obj.modifiers.new(name=f"Slice_Intersect", type='BOOLEAN')
            mod_int.operation = 'INTERSECT'
            mod_int.object = target
            
            mod_diff = active.modifiers.new(name=f"Slice_Diff", type='BOOLEAN')
            mod_diff.operation = 'DIFFERENCE'
            mod_diff.object = target
            
            move_to_collection(target, coll)

        bpy.ops.object.select_all(action='DESELECT')
        active.select_set(True)
        context.view_layer.objects.active = active

        return {'FINISHED'}

class ALEC_OT_mirror_control(BaseModalOperator, bpy.types.Operator):
    """Add Mirror Modifier controlled by a new Empty with interactive placement.
    X,Y,Z to change axis.
    """
    bl_idname = "alec.mirror_control"
    bl_label = "Mirror with Control"
    bl_options = {'REGISTER', 'UNDO', 'GRAB_CURSOR', 'BLOCKING'}

    def invoke(self, context, event):
        self.obj = context.active_object
        if not self.obj: return {'CANCELLED'}
        
        self.original_selection = context.selected_objects[:]
        self.active_obj_name = context.active_object.name

        self.axes = ('X', 'Y', 'Z')
        self.axis_idx = 0

        start_loc = self.obj.matrix_world.translation
        
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=start_loc)
        self.empty = context.active_object
        self.empty.name = f"Mirror_Ctrl_{self.obj.name}"
        
        self.mod = self.obj.modifiers.new(name="Mirror_Ctrl", type='MIRROR')
        self.mod.mirror_object = self.empty
        
        self.mod.use_axis = [i == self.axis_idx for i in range(3)]
        self.initial_loc = start_loc.copy()

        return self.base_invoke(context, event)

    def get_status_bar_items(self):
        return [("Axis", "[X]", self.axis_idx == 0), ("", "[Y]", self.axis_idx == 1), ("", "[Z]", self.axis_idx == 2),
                None, ("Confirm", "[LMB]"), ("Cancel", "[RMB]")]

    def get_header_args(self, context):
        dist = self.empty.location[self.axis_idx] - self.initial_loc[self.axis_idx]
        return {"main_label": "Distance", "main_value": dist * self.unit_scale_display_inv,
                "suffix": unit_suffixes.get(context.scene.unit_settings.length_unit, '')}

    def on_confirm(self, context, event):
        if self.number_input.has_value():
            self.on_apply_typed_value(context, event)
        bpy.ops.object.select_all(action='DESELECT')
        self.obj.select_set(True)
        self.empty.select_set(True)
        context.view_layer.objects.active = self.obj

    def on_cancel(self, context, event):
        self.empty.location = self.initial_loc
        self.obj.modifiers.remove(self.mod)
        bpy.data.objects.remove(self.empty, do_unlink=True)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in self.original_selection:
            obj.select_set(True)
        context.view_layer.objects.active = bpy.data.objects[self.active_obj_name]

    def on_mouse_move(self, context, event, delta_x):
        self.empty.location[self.axis_idx] = self.initial_loc[self.axis_idx] + delta_x * 0.02

    def on_custom_event(self, context, event):
        if event.type in self.axes and event.value == 'PRESS':
            self.number_input.reset()
            self.axis_idx = self.axes.index(event.type)
            self.mod.use_axis = [i == self.axis_idx for i in range(3)]
            delta_x = event.mouse_x - self.initial_mouse_x
            self.empty.location = self.initial_loc.copy()
            self.empty.location[self.axis_idx] += delta_x * 0.02

    def on_apply_typed_value(self, context, event):
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

class ALEC_OT_add_simple_modifier(bpy.types.Operator):
    """Add a specific Modifier and switch to Modifiers tab"""
    bl_idname = "alec.add_simple_modifier"
    bl_label = "Add Modifier"
    bl_options = {'REGISTER', 'UNDO'}

    mod_type: bpy.props.StringProperty() # type: ignore

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        if self.mod_type:
            bpy.ops.object.modifier_add(type=self.mod_type)
        switch_to_modifier_tab(context)
        return {'FINISHED'}

class ALEC_OT_solidify_modal(BaseModalOperator, bpy.types.Operator):
    """Add Solidify Modifier and adjust thickness interactively"""
    bl_idname = "alec.solidify_modal"
    bl_label = "Solidify Interactive"
    bl_options = {'REGISTER', 'UNDO', 'GRAB_CURSOR', 'BLOCKING'}

    def invoke(self, context, event):
        obj = context.active_object
        if not obj:
            return {'CANCELLED'}

        self.mod = obj.modifiers.new(name="Solidify", type='SOLIDIFY')
        self.initial_thickness = self.mod.thickness

        switch_to_modifier_tab(context)
        return self.base_invoke(context, event)

    def get_header_args(self, context):
        return {"main_label": "Thickness", "main_value": self.mod.thickness * self.unit_scale_display_inv,
                "suffix": unit_suffixes.get(context.scene.unit_settings.length_unit, ''),
                "initial_value": self.initial_thickness * self.unit_scale_display_inv}

    def on_cancel(self, context, event):
        self.mod.thickness = self.initial_thickness
        context.active_object.modifiers.remove(self.mod)

    def on_reset(self, context, event):
        self.mod.thickness = self.initial_thickness

    def on_mouse_move(self, context, event, delta_x):
        sens = -0.01 * (0.1 if event.shift else 1.0)
        self.mod.thickness = self.initial_thickness + (delta_x * sens)

    def on_apply_typed_value(self, context, event):
        if self.number_input.has_value():
            try:
                typed_val = self.number_input.get_value(initial_value=self.initial_thickness * self.unit_scale_display_inv)
                self.mod.thickness = typed_val * self.unit_scale
            except ValueError: pass

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

        if not mods:
            self.report({'WARNING'}, "Object has no modifiers")
            return {'CANCELLED'}
        mod = obj.modifiers.active if obj.modifiers.active else obj.modifiers[-1]

        if self.action == 'APPLY_LAST':
            mod = mods[-1]
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


class ALEC_OT_hidden_bools_visibility(bpy.types.Operator):
    """Control visibility for the Hidden_Bools collection"""
    bl_idname = "alec.hidden_bools_visibility"
    bl_label = "Hidden_Bools Visibility"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(
        items=[
            ('TOGGLE', "Toggle", ""),
            ('SHOW', "Show", ""),
            ('HIDE', "Hide", ""),
        ],
        default='TOGGLE',
    ) # type: ignore

    def execute(self, context):
        coll = bpy.data.collections.get("Hidden_Bools")
        if coll is None:
            self.report({'WARNING'}, "Hidden_Bools collection not found")
            return {'CANCELLED'}

        layer_coll = _find_layer_collection(context.view_layer.layer_collection, coll)
        if layer_coll is None:
            self.report({'WARNING'}, "Hidden_Bools not found in current View Layer")
            return {'CANCELLED'}

        if self.action == 'SHOW':
            layer_coll.exclude = False
        elif self.action == 'HIDE':
            layer_coll.exclude = True
        else:
            layer_coll.exclude = not bool(layer_coll.exclude)

        return {'FINISHED'}


class ALEC_OT_move_to_hidden_obj(bpy.types.Operator):
    """Move selected objects to Hidden_Obj collection and exclude it from View Layer"""
    bl_idname = "alec.move_to_hidden_obj"
    bl_label = "Move to Hidden_Obj"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects) or bool(_selected_outliner_collections(context))

    def execute(self, context):
        coll_name = "Hidden_Obj"
        coll = bpy.data.collections.get(coll_name)
        if coll is None:
            coll = bpy.data.collections.new(coll_name)
            context.scene.collection.children.link(coll)

        coll.color_tag = 'COLOR_01'
        coll.hide_viewport = False
        coll.hide_render = True

        moved_objects = 0
        for obj in context.selected_objects:
            move_to_collection(obj, coll)
            moved_objects += 1

        moved_collections = 0
        skipped_collections = 0
        for src_coll in _selected_outliner_collections(context):
            if src_coll == coll or src_coll == context.scene.collection:
                skipped_collections += 1
                continue
            # Avoid cyclic parenting (cannot move parent of Hidden_Obj under Hidden_Obj).
            if _collection_contains(src_coll, coll):
                skipped_collections += 1
                continue

            # Unlink from scene root as well (Scene Collection is not in bpy.data.collections).
            if context.scene.collection.children.get(src_coll.name) is not None:
                context.scene.collection.children.unlink(src_coll)

            for parent in bpy.data.collections:
                if parent.children.get(src_coll.name) is not None:
                    parent.children.unlink(src_coll)
            if coll.children.get(src_coll.name) is None:
                coll.children.link(src_coll)
            moved_collections += 1

        layer_coll = _find_layer_collection(context.view_layer.layer_collection, coll)
        if layer_coll is not None:
            layer_coll.exclude = True

        if skipped_collections:
            self.report(
                {'INFO'},
                f"Moved {moved_objects} object(s), {moved_collections} collection(s), skipped {skipped_collections} collection(s)"
            )

        return {'FINISHED'}


class ALEC_OT_hidden_obj_visibility(bpy.types.Operator):
    """Toggle Hidden_Obj collection visibility via View Layer exclude"""
    bl_idname = "alec.hidden_obj_visibility"
    bl_label = "Hidden_Obj Visibility"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        coll = bpy.data.collections.get("Hidden_Obj")
        if coll is None:
            self.report({'WARNING'}, "Hidden_Obj collection not found")
            return {'CANCELLED'}

        layer_coll = _find_layer_collection(context.view_layer.layer_collection, coll)
        if layer_coll is None:
            self.report({'WARNING'}, "Hidden_Obj not found in current View Layer")
            return {'CANCELLED'}

        layer_coll.exclude = not bool(layer_coll.exclude)
        return {'FINISHED'}


class ALEC_OT_delete_empty_collections(bpy.types.Operator):
    """Delete all empty collections in current .blend (excluding Scene Collection)"""
    bl_idname = "alec.delete_empty_collections"
    bl_label = "Delete Empty Collections"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        del_count = 0

        # Repeatedly remove empty leaf collections; parents may become empty afterwards.
        while True:
            to_delete = [
                coll for coll in bpy.data.collections
                if len(coll.objects) == 0 and len(coll.children) == 0
            ]
            if not to_delete:
                break
            for coll in to_delete:
                bpy.data.collections.remove(coll)
                del_count += 1

        if del_count == 0:
            self.report({'INFO'}, "No empty collections found")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Deleted {del_count} empty collection(s)")
        return {'FINISHED'}

classes = [
    ALEC_OT_boolean_op,
    ALEC_OT_slice_boolean,
    ALEC_OT_mirror_control,
    ALEC_OT_add_simple_modifier,
    ALEC_OT_solidify_modal,
    ALEC_OT_modifier_action,
    ALEC_OT_hidden_bools_visibility,
    ALEC_OT_move_to_hidden_obj,
    ALEC_OT_hidden_obj_visibility,
    ALEC_OT_delete_empty_collections,
]
