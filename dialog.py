import bpy
from .modules import align_tools
from .modules import bbox_tools

class ALEC_OT_align_dialog(bpy.types.Operator):
    """Align Dialog 3ds Max style"""
    bl_idname = "alec.align_dialog"
    bl_label = "Align"
    bl_options = {'REGISTER', 'UNDO'}

    align_x: bpy.props.BoolProperty(name="X", default=True, description="Align on X axis") #type: ignore
    align_y: bpy.props.BoolProperty(name="Y", default=True, description="Align on Y axis") #type: ignore
    align_z: bpy.props.BoolProperty(name="Z", default=True, description="Align on Z axis") #type: ignore

    source_point: bpy.props.EnumProperty(
        name="Current Object",
        description="Point on the current object to align from",
        items=[
            ('MIN', "Minimum", "Align from the bounding box minimum"),
            ('CENTER', "Center", "Align from the bounding box center"),
            ('PIVOT', "Pivot Point", "Align from the object's origin"),
            ('MAX', "Maximum", "Align from the bounding box maximum"),
        ],
        default='PIVOT') #type: ignore

    target_point: bpy.props.EnumProperty(
        name="Target Object",
        description="Point on the target object to align to",
        items=[
            ('MIN', "Minimum", "Align to the bounding box minimum"),
            ('CENTER', "Center", "Align to the bounding box center"),
            ('PIVOT', "Pivot Point", "Align to the object's origin"),
            ('MAX', "Maximum", "Align to the bounding box maximum"),
        ],
        default='PIVOT') #type: ignore

    orient_x: bpy.props.BoolProperty(name="X", default=False, description="Match orientation on X axis") #type: ignore
    orient_y: bpy.props.BoolProperty(name="Y", default=False, description="Match orientation on Y axis") #type: ignore
    orient_z: bpy.props.BoolProperty(name="Z", default=False, description="Match orientation on Z axis") #type: ignore

    scale_x: bpy.props.BoolProperty(name="X", default=False, description="Match scale on X axis") #type: ignore
    scale_y: bpy.props.BoolProperty(name="Y", default=False, description="Match scale on Y axis") #type: ignore
    scale_z: bpy.props.BoolProperty(name="Z", default=False, description="Match scale on Z axis") #type: ignore

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.label(text="POS")
        row.prop(self, "align_x", toggle=True)
        row.prop(self, "align_y", toggle=True)
        row.prop(self, "align_z", toggle=True)

        row = layout.row(align=True)
        col = row.column(align=True)
        col.label(text="Current Object:")
        col.prop(self, "source_point", expand=True)
        col = row.column(align=True)
        col.label(text="Target Object:")
        col.prop(self, "target_point", expand=True)

        row = layout.row(align=True)
        row.label(text="ORI")
        row.prop(self, "orient_x", toggle=True)
        row.prop(self, "orient_y", toggle=True)
        row.prop(self, "orient_z", toggle=True)

        row = layout.row(align=True)
        row.label(text="SCL")
        row.prop(self, "scale_x", toggle=True)
        row.prop(self, "scale_y", toggle=True)
        row.prop(self, "scale_z", toggle=True)

    def execute(self, context):
        target = context.active_object
        sources = [o for o in context.selected_objects if o != target]
        for source in sources:
            align_tools.align_position(source, target,
                x=self.align_x, y=self.align_y, z=self.align_z,
                source_point=self.source_point,
                target_point=self.target_point)
            align_tools.align_orientation(source, target,
                x=self.orient_x, y=self.orient_y, z=self.orient_z)
            align_tools.match_scale(source, target,
                x=self.scale_x, y=self.scale_y, z=self.scale_z)
        return {'FINISHED'}

class ALEC_OT_bboxoff_dialog(bpy.types.Operator):
    """Create bounding box with custom offset"""
    bl_idname = "alec.bboxoff_dialog"
    bl_label = "BBox Offset Settings"
    bl_options = {'REGISTER', 'UNDO'}

    # Offset property
    offset: bpy.props.FloatProperty(
        name="Offset Amount",
        description="The amount to offset the bounding box from the original object",
        default=0.5,
        min=0.0,
        soft_max=10.0) #type: ignore

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "offset")

    def execute(self, context):
        bbox_tools.create_offset_bbox(context.active_object, offset=self.offset)
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
        
        # Source Column
        col_s = split.column()
        col_s.label(text=f"SOURCE: {source_obj.name}", icon='CHECKBOX_HLT')
        col_s.template_list("UI_UL_list","source_list",source_obj,"material_slots",self,"source_index",rows=6)
        
        self._draw_slot_buttons(col_s, source_obj, self.source_index)
        
        # Actions Column
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

        # Target Column
        col_t = split2.column()
        count_suffix = f" (+{len(targets)-1} others)" if len(targets) > 1 else ""
        
        col_t.label(text=f"TARGET: {target_obj.name}{count_suffix}", icon='OUTLINER_OB_MESH')
        col_t.template_list("UI_UL_list", "target_list", 
                            target_obj, "material_slots", 
                            self, "target_index", rows=6)

        self._draw_slot_buttons(col_t, target_obj, self.target_index)
        
        # Check if any operator is about to be used on multiple targets for SWAP
        if len(targets) > 1:
            row = layout.row()
            row.label(text="Note: Swap uses the first target's material.", icon='INFO')

    def execute(self, context):
        return {'FINISHED'}

classes = [
    ALEC_OT_align_dialog,
    ALEC_OT_bboxoff_dialog,
    ALEC_OT_modify_material_slot,
    ALEC_OT_material_apply_operation,
    ALEC_OT_material_linker,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)