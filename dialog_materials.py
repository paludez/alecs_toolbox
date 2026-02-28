import bpy

class ALEC_OT_add_material_slot(bpy.types.Operator):
    """Adds a new empty material slot to the specified object"""
    bl_idname = "alec.add_material_slot"
    bl_label = "Add Material Slot"
    bl_options = {'REGISTER', 'UNDO'}

    target_obj_name: bpy.props.StringProperty() #type: ignore

    def execute(self, context):
        obj = bpy.data.objects.get(self.target_obj_name)
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "Target object not found or not a mesh.")
            return {'CANCELLED'}
        
        obj.data.materials.append(None)
        context.area.tag_redraw()
        return {'FINISHED'}

class ALEC_OT_remove_material_slot(bpy.types.Operator):
    """Removes the selected material slot from the specified object"""
    bl_idname = "alec.remove_material_slot"
    bl_label = "Remove Material Slot"
    bl_options = {'REGISTER', 'UNDO'}

    target_obj_name: bpy.props.StringProperty() #type: ignore
    slot_index: bpy.props.IntProperty() #type: ignore

    def execute(self, context):
        obj = bpy.data.objects.get(self.target_obj_name)
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "Target object not found or not a mesh.")
            return {'CANCELLED'}

        # This check is still good practice.
        if not (0 <= self.slot_index < len(obj.material_slots)):
            self.report({'WARNING'}, "Invalid slot index.")
            return {'CANCELLED'}
        
        # --- Switch to using bpy.ops for robustness ---
        # This is safer than direct data manipulation as it handles all necessary updates.
        
        # Set the active slot index on the object itself
        obj.active_material_index = self.slot_index
        
        # Call the operator with a temporary context override
        with context.temp_override(object=obj, active_object=obj):
            bpy.ops.object.material_slot_remove()

        context.area.tag_redraw()
        return {'FINISHED'}

class ALEC_OT_clear_material_slot(bpy.types.Operator):
    """Clears the material from the selected slot, leaving the slot empty"""
    bl_idname = "alec.clear_material_slot"
    bl_label = "Clear Material Slot"
    bl_options = {'REGISTER', 'UNDO'}

    target_obj_name: bpy.props.StringProperty() #type: ignore
    slot_index: bpy.props.IntProperty() #type: ignore

    def execute(self, context):
        obj = bpy.data.objects.get(self.target_obj_name)
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "Target object not found or not a mesh.")
            return {'CANCELLED'}

        if not (0 <= self.slot_index < len(obj.material_slots)):
            self.report({'WARNING'}, "Invalid slot index.")
            return {'CANCELLED'}
            
        obj.material_slots[self.slot_index].material = None
        
        context.area.tag_redraw()
        return {'FINISHED'}

class ALEC_OT_material_apply_operation(bpy.types.Operator):
    """Applies a material operation immediately"""
    bl_idname = "alec.material_apply_operation"
    bl_label = "Apply Material Operation"
    bl_options = {'REGISTER', 'UNDO'}

    # Properties to be set from the calling UI
    source_index: bpy.props.IntProperty() #type: ignore
    target_index: bpy.props.IntProperty() #type: ignore
    operation: bpy.props.EnumProperty(
        items=[
            ('COPY', "Copy ->", "Copy material from Source slot to Target slot"),
            ('ADD', "Add New ->", "Append source material as a new slot on Target"),
            ('SWAP', "Swap <->", "Swap materials between the two slots")
        ]
    ) #type: ignore

    def execute(self, context):
        source_obj = context.active_object
        targets = [o for o in context.selected_objects if o != source_obj and o.type == 'MESH']
        
        if not source_obj.material_slots:
            self.report({'WARNING'}, "Source object has no materials!")
            return {'CANCELLED'}

        try:
            src_mat = source_obj.material_slots[self.source_index].material
        except IndexError:
            self.report({'ERROR'}, "Invalid Source Slot.")
            return {'CANCELLED'}

        if src_mat is None:
            self.report({'WARNING'}, "Source slot is empty (no material assigned).")
            return {'CANCELLED'}

        if self.operation == 'COPY':
            for tgt in targets:
                while len(tgt.material_slots) <= self.target_index:
                    tgt.data.materials.append(None)
                tgt.material_slots[self.target_index].material = src_mat
        
        elif self.operation == 'ADD':
            for tgt in targets:
                tgt.data.materials.append(src_mat)
        
        elif self.operation == 'SWAP':
            if not targets or self.target_index >= len(targets[0].material_slots):
                self.report({'WARNING'}, "Target for SWAP must have the specified material slot.")
                return {'CANCELLED'}
            
            swapped_back_mat = targets[0].material_slots[self.target_index].material
            
            for tgt in targets:
                 if self.target_index < len(tgt.material_slots):
                    tgt.material_slots[self.target_index].material = src_mat
            
            source_obj.material_slots[self.source_index].material = swapped_back_mat

        context.area.tag_redraw()
        return {'FINISHED'}

class ALEC_OT_material_linker(bpy.types.Operator):
    bl_idname = "alec.material_linker"
    bl_label = "Material Linker"
    bl_description = "Transfer materials from Active (Source) to Selected (Target)"
    bl_options = {'REGISTER', 'UNDO'}

    # Source slot index
    source_index: bpy.props.IntProperty(name="Source Index", default=0) #type: ignore
    
    # Target slot index
    target_index: bpy.props.IntProperty(name="Target Index", default=0) #type: ignore

    @classmethod
    def poll(cls, context):
        # Poll: Active mesh + at least one other mesh selected
        if not context.active_object or context.active_object.type != 'MESH':
            return False
        # Check selection count
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        return len(meshes) >= 2

    def invoke(self, context, event):
        # Width 600px for lists
        return context.window_manager.invoke_props_dialog(self, width=600)

    def draw(self, context):
        layout = self.layout
        
        source_obj = context.active_object
        
        # Target: first selected non-active mesh
        targets = [o for o in context.selected_objects if o != source_obj and o.type == 'MESH']
        
        if not targets:
            layout.label(text="Select another mesh!", icon='ERROR')
            return
            
        target_obj = targets[0]

        # --- FIX: Clamp indices to prevent errors after removing slots ---
        # This ensures that if a slot is removed, the index doesn't point to an invalid location.
        num_source_slots = len(source_obj.material_slots)
        if num_source_slots > 0:
            self.source_index = min(self.source_index, num_source_slots - 1)
        else:
            self.source_index = 0

        num_target_slots = len(target_obj.material_slots)
        if num_target_slots > 0:
            self.target_index = min(self.target_index, num_target_slots - 1)
        else:
            self.target_index = 0

        # Use split to control column widths: 40% Source, 20% Actions, 40% Target
        split = layout.split(factor=0.4)
        
        # Source Column
        col_s = split.column()
        col_s.label(text=f"SOURCE: {source_obj.name}", icon='CHECKBOX_HLT')
        col_s.template_list("UI_UL_list", "source_list", 
                            source_obj, "material_slots", 
                            self, "source_index", rows=6)
        
        row_s_buttons = col_s.row()

        # Remove button (-)
        rem_col = row_s_buttons.column()
        rem_col.active = len(source_obj.material_slots) > 0
        op_s_rem = rem_col.operator("alec.remove_material_slot", text="-")
        op_s_rem.target_obj_name = source_obj.name
        op_s_rem.slot_index = self.source_index

        # Clear button (0)
        clear_col = row_s_buttons.column()
        clear_col.active = len(source_obj.material_slots) > 0 and source_obj.material_slots[self.source_index].material is not None
        op_s_clear = clear_col.operator("alec.clear_material_slot", text="0")
        op_s_clear.target_obj_name = source_obj.name
        op_s_clear.slot_index = self.source_index

        # Add button (+)
        add_col = row_s_buttons.column()
        op_s_add = add_col.operator("alec.add_material_slot", text="+")
        op_s_add.target_obj_name = source_obj.name
        
        # Actions Column
        split2 = split.split(factor=0.33)
        col_m = split2.column(align=True)
        col_m.separator(factor=3.5) # Vertical spacer

        op_copy = col_m.operator("alec.material_apply_operation", text="Copy ->", icon='FORWARD')
        op_copy.source_index = self.source_index
        op_copy.target_index = self.target_index
        op_copy.operation = 'COPY'

        op_add = col_m.operator("alec.material_apply_operation", text="Add New ->", icon='ADD')
        op_add.source_index = self.source_index
        op_add.target_index = self.target_index
        op_add.operation = 'ADD'

        op_swap = col_m.operator("alec.material_apply_operation", text="Swap <->", icon='FILE_REFRESH')
        op_swap.source_index = self.source_index
        op_swap.target_index = self.target_index
        op_swap.operation = 'SWAP'

        # Target Column
        col_t = split2.column()
        # Suffix for multiple targets
        count_suffix = f" (+{len(targets)-1} others)" if len(targets) > 1 else ""
        
        col_t.label(text=f"TARGET: {target_obj.name}{count_suffix}", icon='OUTLINER_OB_MESH')
        col_t.template_list("UI_UL_list", "target_list", 
                            target_obj, "material_slots", 
                            self, "target_index", rows=6)

        row_t_buttons = col_t.row()

        # Remove button (-)
        rem_col = row_t_buttons.column()
        rem_col.active = len(target_obj.material_slots) > 0
        op_t_rem = rem_col.operator("alec.remove_material_slot", text="-")
        op_t_rem.target_obj_name = target_obj.name
        op_t_rem.slot_index = self.target_index

        # Clear button (0)
        clear_col = row_t_buttons.column()
        clear_col.active = len(target_obj.material_slots) > 0 and target_obj.material_slots[self.target_index].material is not None
        op_t_clear = clear_col.operator("alec.clear_material_slot", text="0")
        op_t_clear.target_obj_name = target_obj.name
        op_t_clear.slot_index = self.target_index

        # Add button (+)
        add_col = row_t_buttons.column()
        op_t_add = add_col.operator("alec.add_material_slot", text="+")
        op_t_add.target_obj_name = target_obj.name
        
        # Check if any operator is about to be used on multiple targets for SWAP
        if len(targets) > 1:
            row = layout.row()
            row.label(text="Note: Swap uses the first target's material.", icon='INFO')


    def execute(self, context):
        # This operator now only serves to display the dialog.
        # The actual work is done by ALEC_OT_material_apply_operation.
        # Pressing OK will just close the dialog.
        return {'FINISHED'}

def register():
    bpy.utils.register_class(ALEC_OT_add_material_slot)
    bpy.utils.register_class(ALEC_OT_remove_material_slot)
    bpy.utils.register_class(ALEC_OT_clear_material_slot)
    bpy.utils.register_class(ALEC_OT_material_apply_operation)
    bpy.utils.register_class(ALEC_OT_material_linker)

def unregister():
    bpy.utils.unregister_class(ALEC_OT_material_linker)
    bpy.utils.unregister_class(ALEC_OT_material_apply_operation)
    bpy.utils.unregister_class(ALEC_OT_remove_material_slot)
    bpy.utils.unregister_class(ALEC_OT_clear_material_slot)
    bpy.utils.unregister_class(ALEC_OT_add_material_slot)