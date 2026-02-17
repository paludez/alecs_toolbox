import bpy

class ALEC_OT_material_linker(bpy.types.Operator):
    bl_idname = "alec.material_linker"
    bl_label = "Material Linker"
    bl_description = "Transfer materials from Active (Source) to Selected (Target)"
    bl_options = {'REGISTER', 'UNDO'}

    # Indexul slotului selectat în lista din Stânga (Sursa)
    source_index: bpy.props.IntProperty(name="Source Index", default=0)
    
    # Indexul slotului selectat în lista din Dreapta (Ținta)
    target_index: bpy.props.IntProperty(name="Target Index", default=0)
    
    # Ce operațiune facem?
    operation: bpy.props.EnumProperty(
        name="Action",
        items=[
            ('COPY', "Copy -->", "Copy material from Source slot to Target slot"),
            ('ADD', "Add New -->", "Append source material as a new slot on Target"),
            ('SWAP', "<-- Swap -->", "Swap materials between the two slots")
        ],
        default='COPY'
    )

    @classmethod
    def poll(cls, context):
        # Activul trebuie să fie Mesh, și să mai existe cel puțin un alt Mesh selectat
        if not context.active_object or context.active_object.type != 'MESH':
            return False
        # Numărăm mesh-urile selectate
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        return len(meshes) >= 2

    def invoke(self, context, event):
        # Deschidem fereastra. Lățime 600px ca să încapă listele bine.
        return context.window_manager.invoke_props_dialog(self, width=600)

    def draw(self, context):
        layout = self.layout
        
        # --- DEFINIRE ACTORI ---
        source_obj = context.active_object # Sursa (Active)
        
        # Ținta (Primul obiect selectat care NU e activ)
        targets = [o for o in context.selected_objects if o != source_obj and o.type == 'MESH']
        
        # Safety check pentru draw
        if not targets:
            layout.label(text="Select another mesh!", icon='ERROR')
            return
            
        target_obj = targets[0]

        row = layout.row()
        
        # === COLOANA STÂNGA: SURSA (ACTIVE) ===
        col_s = row.column()
        # FIX: Iconita valida (CHECKBOX_HLT sugereaza 'Activ')
        col_s.label(text=f"SOURCE: {source_obj.name}", icon='CHECKBOX_HLT')
        col_s.template_list("UI_UL_list", "source_list", 
                            source_obj, "material_slots", 
                            self, "source_index", rows=6)
        
        # === COLOANA MIJLOC: ACȚIUNI ===
        col_m = row.column(align=True)
        col_m.alignment = 'CENTER'
        # Spacer ca să ajungem la mijlocul listei
        col_m.label(text="") 
        col_m.label(text="") 
        
        if self.operation == 'COPY':
            col_m.label(text="  COPY  -->  ", icon='FORWARD')
        elif self.operation == 'ADD':
            col_m.label(text="  ADD NEW  -->  ", icon='ADD')
        elif self.operation == 'SWAP':
            col_m.label(text="  <-- SWAP -->  ", icon='FILE_REFRESH')

        # === COLOANA DREAPTA: ȚINTA (SELECTED) ===
        col_t = row.column()
        # Dacă sunt mai multe ținte, scriem "+ X others"
        count_suffix = f" (+{len(targets)-1} others)" if len(targets) > 1 else ""
        
        col_t.label(text=f"TARGET: {target_obj.name}{count_suffix}", icon='OUTLINER_OB_MESH')
        col_t.template_list("UI_UL_list", "target_list", 
                            target_obj, "material_slots", 
                            self, "target_index", rows=6)

        layout.separator()
        
        # Selectorul de Mod
        row = layout.row()
        row.prop(self, "operation", expand=True)
        
        # Info Box
        if len(targets) > 1 and self.operation == 'SWAP':
            row = layout.row()
            row.label(text="Swap works best with single target.", icon='INFO')


    def execute(self, context):
        source_obj = context.active_object
        targets = [o for o in context.selected_objects if o != source_obj and o.type == 'MESH']
        
        if not source_obj.material_slots:
            self.report({'WARNING'}, "Source object has no materials!")
            return {'CANCELLED'}

        # Materialul Sursă
        try:
            src_mat = source_obj.material_slots[self.source_index].material
        except IndexError:
            self.report({'ERROR'}, "Invalid Source Slot.")
            return {'CANCELLED'}

        # --- EXECUTĂM PENTRU FIECARE ȚINTĂ SELECTATĂ ---
        for tgt in targets:
            
            # 1. COPY (Înlocuiește slotul X de pe Țintă cu materialul Sursă)
            if self.operation == 'COPY':
                # Dacă slotul țintă există, îl înlocuim
                if self.target_index < len(tgt.material_slots):
                    tgt.material_slots[self.target_index].material = src_mat
                # Dacă nu există (e.g. ținta are 0 materiale), îl adăugăm
                else:
                    tgt.data.materials.append(src_mat)
            
            # 2. ADD (Adaugă la coadă)
            elif self.operation == 'ADD':
                tgt.data.materials.append(src_mat)
            
            # 3. SWAP (Schimbă între ele - Doar dacă există sloturile)
            elif self.operation == 'SWAP':
                if self.target_index < len(tgt.material_slots):
                    tgt_mat = tgt.material_slots[self.target_index].material
                    tgt.material_slots[self.target_index].material = src_mat
                    
                    # Atenție: Swap pe Sursă se face o singură dată, cu primul target
                    if tgt == targets[0]:
                        source_obj.material_slots[self.source_index].material = tgt_mat

        return {'FINISHED'}

def register():
    bpy.utils.register_class(ALEC_OT_material_linker)

def unregister():
    bpy.utils.unregister_class(ALEC_OT_material_linker)