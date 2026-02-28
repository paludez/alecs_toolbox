import bpy

addon_keymaps = []

class ALEC_MT_quad_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_quad_menu"
    bl_label = "Quad Menu"

    def draw(self, context):
        pie = self.layout.menu_pie()

        # LEFT: Viewport & Cursor
        col = pie.column()
        box_view = col.box()
        box_view.label(text="Viewport", icon='RESTRICT_VIEW_OFF')
        col_inner = box_view.column(align=True)
        col_inner.prop(context.space_data.overlay, "show_wireframes", text="Wireframe")
        if context.space_data and context.space_data.type == 'VIEW_3D':
            r = col_inner.row(align=True)
            r.prop(context.space_data, "show_gizmo_object_translate", text="Move")
            r.prop(context.space_data, "show_gizmo_object_rotate", text="Rotate")
        
        box_cursor = col.box()
        box_cursor.label(text="Cursor", icon='PIVOT_CURSOR')
        col_inner = box_cursor.column(align=True)
        col_inner.operator("alec.cursor_to_selected", text="To Selected")
        col_inner.operator("alec.cursor_to_geometry_center", text="To Center")

        # RIGHT: Orientation & Snap
        col_right = pie.column()

        # Pivot
        b_pivot = col_right.box()
        b_pivot.label(text="Pivot Point", icon='PIVOT_MEDIAN')
        grid = b_pivot.grid_flow(columns=3, align=True, even_columns=True)
        grid.prop_enum(context.tool_settings, "transform_pivot_point", value='BOUNDING_BOX_CENTER', text="BBox")
        grid.prop_enum(context.tool_settings, "transform_pivot_point", value='CURSOR', text="Cursor")
        grid.prop_enum(context.tool_settings, "transform_pivot_point", value='INDIVIDUAL_ORIGINS', text="Indiv")
        grid.prop_enum(context.tool_settings, "transform_pivot_point", value='MEDIAN_POINT', text="Median")
        grid.prop_enum(context.tool_settings, "transform_pivot_point", value='ACTIVE_ELEMENT', text="Active")
        grid.prop(context.tool_settings, "use_transform_pivot_point_align", text="Only Loc")

        # Orientation
        b_orient = col_right.box()
        b_orient.label(text="Orientation", icon='ORIENTATION_GLOBAL')
        slot = context.scene.transform_orientation_slots[0]
        grid = b_orient.grid_flow(columns=3, align=True, even_columns=True)

        grid.prop_enum(slot, "type", value='GLOBAL', text="Global")
        grid.prop_enum(slot, "type", value='LOCAL', text="Local")
        grid.prop_enum(slot, "type", value='NORMAL', text="Normal")
        grid.prop_enum(slot, "type", value='GIMBAL', text="Gimbal")
        grid.prop_enum(slot, "type", value='CURSOR', text="Cursor")
        grid.prop_enum(slot, "type", value='PARENT', text="Parent")

        # Snap Settings
        b5 = col_right.box()
        r5 = b5.grid_flow(columns=3, align=True)
        r5.prop_enum(context.tool_settings, "snap_elements", value='INCREMENT', text="Incr")
        r5.prop_enum(context.tool_settings, "snap_elements", value='VERTEX')
        r5.prop_enum(context.tool_settings, "snap_elements", value='EDGE')
        r5.prop_enum(context.tool_settings, "snap_elements", value='FACE')
        r5.prop_enum(context.tool_settings, "snap_elements", value='VOLUME')

        b5.separator()
        r6 = b5.grid_flow(columns=3, align=True)
        r6.prop_enum(context.tool_settings, "snap_target", value='CENTER')
        r6.prop_enum(context.tool_settings, "snap_target", value='MEDIAN')
        r6.prop_enum(context.tool_settings, "snap_target", value='ACTIVE')

        # DOWN: Empty
        pie.column()

        # UP: Empty
        pie.column()

class ALEC_MT_edit_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_edit_menu"
    bl_label = "Edit Menu"
    def draw(self, context):
        pie = self.layout.menu_pie()

        # LEFT: Collinear
        col = pie.column()
        box = col.box()
        box.label(text="Collinear", icon='PROP_CON')
        col_inner = box.column(align=True)
        op = col_inner.operator("alec.make_collinear", text="Farthest Points")
        op.mode = 'FARTHEST'
        op = col_inner.operator("alec.make_collinear", text="Last Two Selected")
        op.mode = 'HISTORY'

        # RIGHT: Coplanar
        col = pie.column()
        box = col.box()
        box.label(text="Coplanar", icon='GRID')
        col_inner = box.column(align=True)
        op = col_inner.operator("alec.make_coplanar", text="Best Fit")
        op.mode = 'BEST_FIT'
        op = col_inner.operator("alec.make_coplanar", text="Last Three Selected")
        op.mode = 'HISTORY'

        # DOWN: Distribute
        col = pie.column()
        box = col.box()
        col_inner = box.column(align=True)
        col_inner.operator("alec.distribute_vertices", text="Distribute Vertices", icon='NODE_TEXTURE')

        # UP: Set Edge Length
        col = pie.column()
        box = col.box()
        col_inner = box.column(align=True)
        col_inner.operator("alec.set_edge_length", text="Set Edge Length", icon='SEQ_STRIP_DUPLICATE')
        
        box = col.box()
        box.label(text="Origin", icon='OBJECT_ORIGIN')
        box.operator("alec.origin_to_selected_edit", text="To Selection")
        box.operator("alec.origin_to_selected_edit_aligned", text="To Selection (Aligned)")

class ALEC_MT_object_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_object_menu"
    bl_label = "Object Menu"

    def draw(self, context):
        pie = self.layout.menu_pie()

        # LEFT: BBox & Align
        col_left = pie.column()
        row = col_left.row()

            # 1. BBox
        col_b = row.column()
        box_bbox = col_b.box()
        box_bbox.label(text="BBox", icon='MESH_CUBE')
        col_inner = box_bbox.column(align=True)
        col_inner.operator("alec.bbox_local", text="BBox Local")
        col_inner.operator("alec.bbox_world", text="BBox World")
        col_inner.operator("alec.bboxoff_dialog", text="BBox Offset")

            # 2. Align
        col_a = row.column()
        box_align = col_a.box()
        box_align.label(text="Align", icon='LIGHTPROBE_VOLUME')
        col_inner = box_align.column(align=True)
        col_inner.operator("alec.quick_center", text="OBJ_Centers")
        col_inner.operator("alec.quick_pivot", text="OBJ_Origins")
        col_inner.operator("alec.align_dialog", text="Align Dialog")

        # RIGHT: BBox
        col_right = pie.column()
        box_bbox = col_right.box()
        box_bbox.label(text="BBox", icon='MESH_CUBE')
        col_inner = box_bbox.column(align=True)
        col_inner.operator("alec.bbox_local", text="BBox Local")
        col_inner.operator("alec.bbox_world", text="BBox World")
        col_inner.operator("alec.bboxoff_dialog", text="BBox Offset")
        
        # DOWN: Grouping & Materials
        col_down = pie.column()
        b5 = col_down.box()
        b5.label(text="Grouping", icon='GROUP')
        col_grp = b5.grid_flow(columns=3, align=True)
        col_grp.operator("alec.group", text="Group", icon='OUTLINER_OB_EMPTY')
        col_grp.operator("alec.group_active", text="Group Active", icon='EMPTY_AXIS')
        col_grp.operator("alec.ungroup", text="Ungroup", icon='MOD_EXPLODE')

        box_mat = col_down.box()
        box_mat.label(text="Materials", icon='MATERIAL')
        col_inner = box_mat.column(align=True)
        col_inner.operator("alec.material_linker", text="Material Linker")
        col_inner.operator("object.make_links_data", text="Link Materials", icon='LINKED').type = 'MATERIAL'
        col_inner.operator("alec.assign_gray_material", text="Gray Material (70%)", icon='SHADING_SOLID')
        col_inner.operator("alec.remove_orphan_materials", text="Clean Unused", icon='TRASH')
        col_inner.operator("alec.select_material_users", text="Select Users", icon='RESTRICT_SELECT_OFF')

        # UP: Origin & Parenting
        col_up = pie.column()

        box_parent = col_up.box()
        box_parent.label(text="Parenting", icon='ORIENTATION_PARENT')
        col_inner = box_parent.grid_flow(columns=3, align=True)
        op = col_inner.operator("object.parent_set", text="Parent", icon='LINKED')
        op.type = 'OBJECT'
        op.keep_transform = True
        col_inner.operator("object.parent_clear", text="Clear Parent", icon='X').type = 'CLEAR'
        col_inner.operator("object.parent_clear", text="Keep Transform", icon='UNLINKED').type = 'CLEAR_KEEP_TRANSFORM'

        box_origin = col_up.box()
        box_origin.label(text="Origin", icon='OBJECT_ORIGIN')
        grid = box_origin.grid_flow(columns=3, align=True)
        op = grid.operator("object.origin_set", text="BBox", icon='PIVOT_BOUNDBOX')
        op.type = 'ORIGIN_GEOMETRY'
        op.center = 'BOUNDS'
        grid.operator("object.origin_set", text="To Cursor", icon='PIVOT_CURSOR').type = 'ORIGIN_CURSOR'
        grid.operator("alec.origin_to_cursor", text="To Cur (Rot)", icon='ORIENTATION_GIMBAL')
        grid.operator("alec.origin_to_active", text="To Active", icon='PIVOT_ACTIVE')
        grid.operator("alec.origin_to_bottom", text="To Bottom", icon='TRIA_DOWN')



classes = [
    ALEC_MT_object_menu,
    ALEC_MT_edit_menu,
    ALEC_MT_quad_menu,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon:
        km = wm.keyconfigs.addon.keymaps.new(name='3D View', space_type='VIEW_3D')
        
        kmi_main = km.keymap_items.new('alec.menu_dispatcher', 'Q', 'PRESS', alt=True)
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