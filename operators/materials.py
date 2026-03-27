import bpy

class ALEC_OT_assign_gray_material(bpy.types.Operator):
    """Create and assign a 70% Gray material to selected objects"""
    bl_idname = "alec.assign_gray_material"
    bl_label = "Assign Gray Material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mat_name = "Gray"
        if mat_name in bpy.data.materials:
            mat = bpy.data.materials[mat_name]
        else:
            mat = bpy.data.materials.new(name=mat_name)
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                val = 0.7
                bsdf.inputs['Base Color'].default_value = (val, val, val, 1.0)
        
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                if not obj.data.materials:
                    obj.data.materials.append(mat)
                else:
                    obj.material_slots[obj.active_material_index].material = mat
        return {'FINISHED'}

class ALEC_OT_remove_orphan_materials(bpy.types.Operator):
    """Remove materials that have 0 users"""
    bl_idname = "alec.remove_orphan_materials"
    bl_label = "Remove Unused Materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        to_remove = [m for m in bpy.data.materials if m.users == 0 and not m.use_fake_user]
        count = len(to_remove)
        for m in to_remove:
            bpy.data.materials.remove(m)
        self.report({'INFO'}, f"Removed {count} materials")
        return {'FINISHED'}

class ALEC_OT_select_material_users(bpy.types.Operator):
    """Select all objects in the scene that use the active material"""
    bl_idname = "alec.select_material_users"
    bl_label = "Select Users"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.active_material is not None

    def execute(self, context):
        mat = context.active_object.active_material

        bpy.ops.object.select_all(action='DESELECT')

        if mat:
            for obj in context.scene.objects:
                if any(s.material == mat for s in obj.material_slots):
                    obj.select_set(True)
        return {'FINISHED'}

class ALEC_OT_modify_material_slot(bpy.types.Operator):
    """Adds, removes, or clears a material slot on an object"""
    bl_idname = "alec.modify_material_slot"
    bl_label = "Modify Material Slot"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(
        items=[
            ('ADD', "Add", "Add a new empty material slot to the object"),
            ('REMOVE', "Remove", "Remove the currently selected material slot"),
            ('CLEAR', "Clear", "Clear the material from the slot, leaving the slot empty")
        ]
    ) #type: ignore

    target_obj_name: bpy.props.StringProperty() #type: ignore
    slot_index: bpy.props.IntProperty() #type: ignore

    def execute(self, context):
        obj = bpy.data.objects.get(self.target_obj_name)
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "Target object not found or not a mesh.")
            return {'CANCELLED'}

        if self.action == 'ADD':
            obj.data.materials.append(None)

        elif self.action == 'REMOVE':
            if not (0 <= self.slot_index < len(obj.material_slots)):
                self.report({'WARNING'}, "Invalid slot index for removal.")
                return {'CANCELLED'}
            obj.active_material_index = self.slot_index
            with context.temp_override(object=obj, active_object=obj):
                bpy.ops.object.material_slot_remove()

        elif self.action == 'CLEAR':
            if not (0 <= self.slot_index < len(obj.material_slots)):
                self.report({'WARNING'}, "Invalid slot index for clearing.")
                return {'CANCELLED'}
            obj.material_slots[self.slot_index].material = None

        context.area.tag_redraw()
        return {'FINISHED'}

class ALEC_OT_material_apply_operation(bpy.types.Operator):
    """Applies a material operation immediately"""
    bl_idname = "alec.material_apply_operation"
    bl_label = "Apply Material Operation"
    bl_options = {'REGISTER', 'UNDO'}

    source_index: bpy.props.IntProperty() #type: ignore
    target_index: bpy.props.IntProperty() #type: ignore
    operation: bpy.props.EnumProperty(
        items=[
            ('COPY', "Copy ->", "Copy the source material to the target slot (creates slot if needed)"),
            ('ADD', "Add New ->", "Append the source material as a new slot on the target object"),
            ('SWAP', "Swap <->", "Swap the source and target materials between the two objects")
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
    """Transfer materials from Active (Source) to Selected (Target)"""
    bl_idname = "alec.material_linker"
    bl_label = "Material Linker"
    bl_options = {'REGISTER', 'UNDO'}

    source_index: bpy.props.IntProperty(name="Source Index", default=0) #type: ignore
    target_index: bpy.props.IntProperty(name="Target Index", default=0) #type: ignore

    @classmethod
    def poll(cls, context):
        if not context.active_object or context.active_object.type != 'MESH':
            return False
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        return len(meshes) >= 2

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=600)

    def _draw_slot_buttons(self, layout, obj, index_val):
        row = layout.row()
        rem_col = row.column()
        rem_col.active = len(obj.material_slots) > 0
        op_rem = rem_col.operator("alec.modify_material_slot", text="-")
        op_rem.target_obj_name = obj.name
        op_rem.slot_index = index_val
        op_rem.action = 'REMOVE'

        clear_col = row.column()
        is_clearable = len(obj.material_slots) > 0 and obj.material_slots[index_val].material is not None
        clear_col.active = is_clearable
        op_clear = clear_col.operator("alec.modify_material_slot", text="0")
        op_clear.target_obj_name = obj.name
        op_clear.slot_index = index_val
        op_clear.action = 'CLEAR'

        add_col = row.column()
        op_add = add_col.operator("alec.modify_material_slot", text="+")
        op_add.target_obj_name = obj.name
        op_add.action = 'ADD'

    def draw(self, context):
        layout = self.layout
        
        source_obj = context.active_object
        targets = [o for o in context.selected_objects if o != source_obj and o.type == 'MESH']
        
        if not targets:
            layout.label(text="Select another mesh!", icon='ERROR')
            return
            
        target_obj = targets[0]

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

        split = layout.split(factor=0.4)

        col_s = split.column()
        col_s.label(text=f"SOURCE: {source_obj.name}", icon='CHECKBOX_HLT')
        col_s.template_list("UI_UL_list","source_list",source_obj,"material_slots",self,"source_index",rows=6)
        
        self._draw_slot_buttons(col_s, source_obj, self.source_index)

        split2 = split.split(factor=0.33)
        col_m = split2.column(align=True)
        col_m.separator(factor=3.5)

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

        col_t = split2.column()
        count_suffix = f" (+{len(targets)-1} others)" if len(targets) > 1 else ""
        
        col_t.label(text=f"TARGET: {target_obj.name}{count_suffix}", icon='OUTLINER_OB_MESH')
        col_t.template_list("UI_UL_list", "target_list", 
                            target_obj, "material_slots", 
                            self, "target_index", rows=6)

        self._draw_slot_buttons(col_t, target_obj, self.target_index)

        if len(targets) > 1:
            row = layout.row()
            row.label(text="Note: Swap uses the first target's material.", icon='INFO')

    def execute(self, context):
        return {'FINISHED'}

classes = [
    ALEC_OT_assign_gray_material,
    ALEC_OT_remove_orphan_materials,
    ALEC_OT_select_material_users,
    ALEC_OT_modify_material_slot,
    ALEC_OT_material_apply_operation,
    ALEC_OT_material_linker,
]
