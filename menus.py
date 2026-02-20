import bpy

addon_keymaps = []

class ALEC_MT_quad_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_quad_menu"
    bl_label = "Quad Menu"

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()
        ts = context.tool_settings

        # --- 1. STÂNGA (Pivot & Origins - COMPACT) ---
        col_left = pie.column()
        

        
        # Cursor
        b2 = col_left.box()
        b2.label(text="Parenting", icon='ORIENTATION_PARENT')
        
        r3 = b2.row(align=False) 

        op = r3.operator("object.parent_set", text="Parent KT", icon='PIVOT_CURSOR')
        op.type = 'OBJECT'
        op.keep_transform = True
        
        r3.operator("alec.cursor_to_geometry_center", text="To Center", icon='PIVOT_CURSOR')

        # Origin
        b3 = col_left.box()
        b3.label(text="Origin", icon='OBJECT_ORIGIN')
        r4 = b3.grid_flow(columns=3, align=True)
        r4.operator("object.origin_set", text="Origin->BBox Center", icon='EMPTY_DATA').type = 'ORIGIN_GEOMETRY'
        r4.operator("object.origin_set", text="Origin to Cursor POS", icon='ORIENTATION_CURSOR').type = 'ORIGIN_CURSOR'
        r4.operator("alec.origin_to_cursor", text="Origin to Cursor POS&ROT", icon='ORIENTATION_GIMBAL')

        # --- 2. DREAPTA (Orientation & Snap) ---
        col_right = pie.column()

        # Pivot
        b_pivot = col_right.box()
        b_pivot.label(text="Pivot Point", icon='PIVOT_MEDIAN')
        ts = context.scene.tool_settings
        grid = b_pivot.grid_flow(columns=3, align=True, even_columns=True)
        grid.prop_enum(ts, "transform_pivot_point", value='BOUNDING_BOX_CENTER', text="BBox")
        grid.prop_enum(ts, "transform_pivot_point", value='CURSOR', text="Cursor")
        grid.prop_enum(ts, "transform_pivot_point", value='INDIVIDUAL_ORIGINS', text="Indiv")
        grid.prop_enum(ts, "transform_pivot_point", value='MEDIAN_POINT', text="Median")
        grid.prop_enum(ts, "transform_pivot_point", value='ACTIVE_ELEMENT', text="Active")
        grid.prop(ts, "use_transform_pivot_point_align", text="Only Loc")

        # Orientation
        b_orient = col_right.box()
        b_orient.label(text="Orientation", icon='ORIENTATION_GLOBAL')
        slot = context.scene.transform_orientation_slots[0]
        grid = b_orient.grid_flow(columns=3, align=True, even_columns=True)

        grid.prop_enum(slot, "type", value='GLOBAL', text="Global")
        grid.prop_enum(slot, "type", value='LOCAL', text="Local")
        grid.prop_enum(slot, "type", value='NORMAL', text="Normal")
        grid.prop_enum(slot, "type", value='GIMBAL', text="Gimbal")
        grid.prop_enum(slot, "type", value='VIEW', text="View")
        grid.prop_enum(slot, "type", value='CURSOR', text="Cursor")

        # Snap Settings
        b5 = col_right.box()
        r5 = b5.grid_flow(columns=3, align=True)
        r5.prop_enum(ts, "snap_elements", value='INCREMENT', text="Incr")
        r5.prop_enum(ts, "snap_elements", value='VERTEX')
        r5.prop_enum(ts, "snap_elements", value='EDGE')
        r5.prop_enum(ts, "snap_elements", value='FACE')
        r5.prop_enum(ts, "snap_elements", value='VOLUME')

        b5.separator()
        r6 = b5.grid_flow(columns=3, align=True)
        r6.prop_enum(ts, "snap_target", value='CENTER')
        r6.prop_enum(ts, "snap_target", value='MEDIAN')
        r6.prop_enum(ts, "snap_target", value='ACTIVE')

        #--- 3. JOS (Grouping) ---
        col_down = pie.column()
        b5 = col_down.box()
        
        b5.prop(context.space_data.overlay, "show_wireframes", text="Wireframe", toggle=True)
        b5.operator("alec.group", text="Group Selection", icon='OUTLINER_COLLECTION')

        # --- 4. SUS (BBox Tools) ---
        col_up = pie.column()
        b6 = col_up.box()
        b6.prop(context.space_data.overlay, "show_wireframes", text="Wireframe", toggle=True)

        space = context.space_data
        
        if space and space.type == 'VIEW_3D':
            b_giz = col_up.box()
            r = b_giz.row(align=True)
            
            # Folosim iconițele corecte: 'TRANSFORM_MOVE' și 'TRANSFORM_ROTATE'
            r.prop(space, "show_gizmo_object_translate", text="Move")
            r.prop(space, "show_gizmo_object_rotate", text="Rotate")

class ALEC_MT_menu_align(bpy.types.Menu):
    bl_label = "Align"
    def draw(self, context):
        layout = self.layout
        layout.operator("alec.quick_center", text="Quick Align OBJ_Centers", icon='PIVOT_BOUNDBOX')
        layout.operator("alec.quick_pivot", text="Quick Align OBJ_Origins", icon='OBJECT_ORIGIN')
        layout.operator("alec.align_dialog", text="Align Dialog", icon='PREFERENCES')
        layout.separator()
        layout.operator("alec.cursor_to_selected", text="To Selected", icon='PIVOT_CURSOR')
        layout.operator("alec.cursor_to_geometry_center", text="To Center", icon='PIVOT_CURSOR')
        layout.separator()
        layout.operator("object.origin_set", text="Origin->BBox Center", icon='EMPTY_DATA').type = 'ORIGIN_GEOMETRY'
        layout.operator("object.origin_set", text="Origin to Cursor POS", icon='ORIENTATION_CURSOR').type = 'ORIGIN_CURSOR'
        layout.operator("alec.origin_to_cursor", text="Origin to Cursor POS&ROT", icon='ORIENTATION_GIMBAL')



class ALEC_MT_menu_pivot(bpy.types.Menu):
    bl_label = "Pivot Point"
    def draw(self, context):
        layout = self.layout
        for value, label, icon in [('BOUNDING_BOX_CENTER', "BBox Center", 'PIVOT_BOUNDBOX'), ('MEDIAN_POINT', "Median", 'PIVOT_MEDIAN'), ('ACTIVE_ELEMENT', "Active", 'PIVOT_ACTIVE'), ('CURSOR', "3D Cursor", 'PIVOT_CURSOR'), ('INDIVIDUAL_ORIGINS', "Individual", 'PIVOT_INDIVIDUAL')]:
            op = layout.operator("wm.context_set_enum", text=label, icon=icon)
            op.data_path = "tool_settings.transform_pivot_point"
            op.value = value
        layout.separator()
        layout.prop(context.tool_settings, "use_transform_pivot_point_align", text="Only Locations")

class ALEC_MT_menu_misc(bpy.types.Menu):
    bl_label = "Misc"
    def draw(self, context):
        layout = self.layout
        layout.operator("alec.bbox_local", text="BBox Local", icon='MESH_CUBE')
        layout.operator("alec.bbox_world", text="BBox World", icon='WORLD')
        layout.operator("alec.bboxoff_dialog", text="BBox Offset", icon='MOD_OFFSET')
        layout.separator()
        layout.operator("alec.group", icon='MESH_PLANE')
        layout.operator("alec.ungroup", icon='MOD_EXPLODE')

class ALEC_MT_menu_main(bpy.types.Menu):
    bl_label = "Alec's Toolbox"
    def draw(self, context):
        layout = self.layout
        layout.menu("ALEC_MT_menu_align", icon='LIGHTPROBE_VOLUME')
        layout.menu("ALEC_MT_menu_misc", icon='FILE_SOUND')

classes = [
    ALEC_MT_menu_align,
    ALEC_MT_menu_misc,
    ALEC_MT_menu_main,
    ALEC_MT_quad_menu,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon:
        km = wm.keyconfigs.addon.keymaps.new(name='3D View', space_type='VIEW_3D')
        
        kmi_main = km.keymap_items.new('wm.call_menu', 'Q', 'PRESS', alt=True)
        kmi_main.properties.name = "ALEC_MT_menu_main"
        addon_keymaps.append((km, kmi_main))

        kmi_quad = km.keymap_items.new('wm.call_menu_pie', 'RIGHTMOUSE', 'PRESS', alt=True)
        kmi_quad.properties.name = "ALEC_MT_quad_menu"
        addon_keymaps.append((km, kmi_quad))

def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)