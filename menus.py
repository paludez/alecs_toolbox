import bpy
import math

from . import menus_browser


class ALEC_MT_quad_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_quad_menu"
    bl_label = "Quad Menu"

    def draw(self, context):
        pie = self.layout.menu_pie()

        col = pie.column()
        box_view = col.box()
        box_view.label(text="Viewport", icon='RESTRICT_VIEW_OFF')
        col_inner = box_view.column(align=True)
        if context.space_data and context.space_data.type == 'VIEW_3D':
            col_inner.prop(context.space_data.overlay, "show_wireframes", text="Wireframe")
            r = col_inner.row(align=True)
            r.prop(context.space_data, "show_gizmo_object_translate", text="Move")
            r.prop(context.space_data, "show_gizmo_object_rotate", text="Rotate")

        box_cursor = col.box()
        box_cursor.label(text="Cursor", icon='PIVOT_CURSOR')
        col_inner = box_cursor.column(align=True)
        col_inner.operator("alec.cursor_to_selected", text="To Selected")
        col_inner.operator("alec.cursor_to_geometry_center", text="To Center")

        col_right = pie.column()

        b_pivot = col_right.box()
        b_pivot.label(text="Pivot Point", icon='PIVOT_MEDIAN')
        grid = b_pivot.grid_flow(columns=3, align=True, even_columns=True)
        for val, txt in [('BOUNDING_BOX_CENTER', "BBox"), ('CURSOR', "Cursor"), ('INDIVIDUAL_ORIGINS', "Indiv"),
                         ('MEDIAN_POINT', "Median"), ('ACTIVE_ELEMENT', "Active")]:
            grid.prop_enum(context.tool_settings, "transform_pivot_point", value=val, text=txt)
        grid.prop(context.tool_settings, "use_transform_pivot_point_align", text="Only Loc")

        b_orient = col_right.box()
        b_orient.label(text="Orientation", icon='ORIENTATION_GLOBAL')
        slot = context.scene.transform_orientation_slots[0]
        grid = b_orient.grid_flow(columns=3, align=True, even_columns=True)
        for val in ['GLOBAL', 'LOCAL', 'NORMAL', 'GIMBAL', 'CURSOR', 'PARENT']:
            grid.prop_enum(slot, "type", value=val, text=val.capitalize())

        b5 = col_right.box()
        r5 = b5.grid_flow(columns=3, align=True)
        for val, txt in [('INCREMENT', "Incr"), ('VERTEX', "Vertex"), ('EDGE', "Edge"), ('FACE', "Face"), ('VOLUME', "Volume")]:
            r5.prop_enum(context.tool_settings, "snap_elements", value=val, text=txt)

        b5.separator()
        r6 = b5.grid_flow(columns=3, align=True)
        for val in ['CENTER', 'MEDIAN', 'ACTIVE']:
            r6.prop_enum(context.tool_settings, "snap_target", value=val, text=val.capitalize())

        pie.column()

        col_up = pie.column()
        box = col_up.box()
        box.label(text="Floating Shaders", icon='WINDOW')
        col_inner = box.column(align=True)
        col_inner.operator("alec.floating_shader_editor", text="Object Shader", icon='NODE_MATERIAL').mode = 'OBJECT'
        col_inner.operator("alec.floating_shader_editor", text="World Shader", icon='WORLD').mode = 'WORLD'
        col_inner.separator()
        col_inner.operator("alec.square_pixels", text="Square Pixels", icon='UV')

class ALEC_MT_uv_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_uv_menu"
    bl_label = "UV Menu"

    def draw(self, context):
        pie = self.layout.menu_pie()

        col = pie.column()
        box = col.box()
        box.label(text="Unwrap", icon='UV')
        col_inner = box.column(align=True)
        col_inner.operator("uv.unwrap", text="Unwrap")
        col_inner.operator("uv.smart_project", text="Smart UV")
        col_inner.operator("uv.cube_project", text="Cube Projection")

        box = col.box()
        box.label(text="Image", icon='IMAGE_DATA')
        col_inner = box.column(align=True)
        col_inner.operator("alec.load_material_image", text="Load from Mat")

        col = pie.column()
        box = col.box()
        box.label(text="Align", icon='ALIGN_CENTER')
        col_inner = box.column(align=True)
        col_inner.operator("uv.align", text="Straighten").axis = 'ALIGN_AUTO'
        col_inner.operator("uv.align", text="Align X").axis = 'ALIGN_X'
        col_inner.operator("uv.align", text="Align Y").axis = 'ALIGN_Y'

        col = pie.column()
        box = col.box()
        box.label(text="Pack & Scale", icon='UV_ISLANDSEL')
        col_inner = box.column(align=True)
        col_inner.operator("uv.average_islands_scale", text="Average Scale")
        col_inner.operator("uv.pack_islands", text="Pack Islands")

        col = pie.column()
        box = col.box()
        box.label(text="Seams", icon='MOD_EDGESPLIT')
        col_inner = box.column(align=True)
        col_inner.operator("uv.seams_from_islands", text="Seams from Islands")

class ALEC_MT_edit_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_edit_menu"
    bl_label = "Edit Menu"
    def draw(self, context):
        pie = self.layout.menu_pie()

        col = pie.column()

        box = col.box()
        box.label(text="Collinear", icon='PROP_CON')
        col_inner = box.column(align=True)
        op = col_inner.operator("alec.make_collinear", text="Farthest Points")
        op.mode = 'FARTHEST'
        op.distribute = False
        op = col_inner.operator("alec.make_collinear", text="Last Two Selected")
        op.mode = 'HISTORY'
        op.distribute = False
        op = col_inner.operator("alec.make_collinear", text="Align & Distribute")
        op.mode = 'FARTHEST'
        op.distribute = True
        col_inner.operator("alec.distribute_vertices", text="Distribute Evenly")

        box = col.box()
        box.label(text="Coplanar", icon='GRID')
        col_inner = box.column(align=True)
        op = col_inner.operator("alec.make_coplanar", text="Best Fit")
        op.mode = 'BEST_FIT'
        op = col_inner.operator("alec.make_coplanar", text="Last Three Selected")
        op.mode = 'HISTORY'
        op = col_inner.operator("alec.make_coplanar", text="Active Face Normal")
        op.mode = 'ACTIVE_FACE'

        box = col.box()
        box.label(text="Extract", icon='DUPLICATE')
        box.operator("alec.extract_and_solidify", text="Panel (Solidify)")

        col = pie.column()

        box_shapes = col.box()
        box_shapes.label(text="Shapes", icon='MESH_CIRCLE')
        col_inner = box_shapes.column(align=True)
        col_inner.operator("alec.make_circle", text="Perfect Circle")

        box = col.box()
        box.label(text="Orientation", icon='ORIENTATION_GLOBAL')
        col_inner = box.column(align=True)
        op = col_inner.operator("transform.create_orientation", text="Create New", icon='ADD')
        op.use = True
        op.overwrite = True

        box_clean = col.box()
        box_clean.label(text="Cleanup", icon='BRUSH_DATA')
        box_clean.operator("alec.clean_mesh", text="Clean Planar")

        col = pie.column()
        box = col.box()
        box.label(text="Origin", icon='OBJECT_ORIGIN')
        col_inner = box.column(align=True)
        col_inner.operator("alec.origin_to_selected_edit", text="To Selection")
        col_inner.operator("alec.origin_to_selected_edit_aligned", text="To Selection (Aligned)")

        col = pie.column()

        box_dim = col.box()
        box_dim.label(text="Dimensions", icon='DRIVER_DISTANCE')
        col_inner_dim = box_dim.column(align=True)
        col_inner_dim.operator("alec.equalize_edge_lengths", text="Equalize Lengths", icon='ALIGN_JUSTIFY')
        col_inner_dim.operator("alec.set_edge_length", text="Set Edge Length", icon='SEQ_STRIP_DUPLICATE')

        row = col_inner_dim.row(align=True)
        row.operator("alec.dimension_action", text="Add", icon='ADD').action = 'ADD'
        row.operator("alec.dimension_action", text="Rem", icon='REMOVE').action = 'REMOVE'

        col_inner_dim.operator("alec.dimension_action", text="Clear All", icon='TRASH').action = 'CLEAR'
        col_inner_dim.operator("alec.select_dimension_edges", text="Select Dim Edges", icon='RESTRICT_SELECT_OFF')

        col_inner_dim.separator()
        col_inner_dim.operator("alec.set_edge_angle", text="Set to 90°", icon='IPO_CONSTANT').angle = math.pi / 2.0
        col_inner_dim.operator("alec.set_edge_angle", text="Set Angle...", icon='IPO_EASE_IN_OUT').run_modal = True


class ALEC_MT_edit_curve_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_edit_curve_menu"
    bl_label = "Curve Edit"

    def draw(self, context):
        pie = self.layout.menu_pie()
        col = pie.column()

        box = col.box()
        box.label(text="Collinear", icon='CURVE_BEZCURVE')
        col_inner = box.column(align=True)
        op = col_inner.operator("alec.make_collinear", text="Farthest Points")
        op.mode = 'FARTHEST'
        op.distribute = False
        op = col_inner.operator("alec.make_collinear", text="Align & Distribute")
        op.mode = 'FARTHEST'
        op.distribute = True

        box = col.box()
        box.label(text="Coplanar", icon='GRID')
        col_inner = box.column(align=True)
        op = col_inner.operator("alec.make_coplanar", text="Best Fit")
        op.mode = 'BEST_FIT'
        col_inner.operator("alec.coplanar_curve_three_point_plane", text="3-Point Plane")


class ALEC_MT_object_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_object_menu"
    bl_label = "Object Menu"

    def draw(self, context):
        pie = self.layout.menu_pie()

        col_left = pie.column()
        row = col_left.row()

        col_b = row.column()
        box_bbox = col_b.box()
        box_bbox.label(text="BBox", icon='MESH_CUBE')
        col_inner = box_bbox.column(align=True)
        col_inner.operator("alec.bbox_local", text="BBox Local")
        col_inner.operator("alec.bbox_world", text="BBox World")
        col_inner.operator("alec.bbox_offset_modal", text="BBox Offset")

        col_a = row.column()
        box_align = col_a.box()
        box_align.label(text="Align", icon='LIGHTPROBE_VOLUME')
        col_inner = box_align.column(align=True)
        col_inner.operator("alec.quick_center", text="Align_Centers")
        col_inner.operator("alec.quick_pivot", text="Align_Origins")
        col_inner.operator("alec.align_dialog", text="Align Dialog")

        col_right = pie.column()
        box_mods = col_right.box()
        box_mods.label(text="Modifiers", icon='MODIFIER')

        grid_bool = box_mods.grid_flow(columns=2, align=True)
        grid_bool.operator("alec.boolean_op", text="Union", icon='MOD_BOOLEAN').operation = 'UNION'
        grid_bool.operator("alec.boolean_op", text="Diff", icon='MOD_BOOLEAN').operation = 'DIFFERENCE'
        grid_bool.operator("alec.boolean_op", text="Intersect", icon='MOD_BOOLEAN').operation = 'INTERSECT'
        grid_bool.operator("alec.slice_boolean", text="Slice", icon='MOD_BOOLEAN')

        box_mods.separator()

        col_gen = box_mods.column(align=True)
        col_gen.operator("alec.add_simple_modifier", text="Mirror", icon='MOD_MIRROR').mod_type = 'MIRROR'
        col_gen.operator("alec.mirror_control", text="Mirror (Null)", icon='EMPTY_AXIS')
        col_gen.operator("alec.solidify_modal", text="Solidify", icon='MOD_SOLIDIFY')
        col_gen.operator("alec.add_simple_modifier", text="Subdivision", icon='MOD_SUBSURF').mod_type = 'SUBSURF'

        box_mods.separator()

        grid_man = box_mods.grid_flow(columns=2, align=True, row_major=True)
        grid_man.operator("alec.modifier_action", text="Move Up", icon='TRIA_UP').action = 'MOVE_UP'
        grid_man.operator("alec.modifier_action", text="Move Down", icon='TRIA_DOWN').action = 'MOVE_DOWN'
        grid_man.operator("alec.modifier_action", text="Apply Last", icon='CHECKMARK').action = 'APPLY_LAST'
        grid_man.operator("alec.modifier_action", text="Apply All", icon='FILE_TICK').action = 'APPLY_ALL'
        grid_man.operator("alec.modifier_action", text="Del Last", icon='X').action = 'DELETE_LAST'
        grid_man.operator("alec.modifier_action", text="Del All", icon='TRASH').action = 'DELETE_ALL'


        col_down = pie.column()
        b5 = col_down.box()
        b5.label(text="Grouping", icon='GROUP')
        col_grp = b5.grid_flow(columns=2, align=True)
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

        col_up = pie.column()

        box_parent = col_up.box()
        box_parent.label(text="Parenting", icon='ORIENTATION_PARENT')
        col_inner = box_parent.grid_flow(columns=2, align=True)
        op = col_inner.operator("object.parent_set", text="Parent", icon='LINKED')
        op.type = 'OBJECT'
        op.keep_transform = True
        col_inner.operator("object.parent_clear", text="Clear Parent", icon='X').type = 'CLEAR'
        col_inner.operator("object.parent_clear", text="Keep Tran.", icon='UNLINKED').type = 'CLEAR_KEEP_TRANSFORM'

        box_origin = col_up.box()
        box_origin.label(text="Origin", icon='OBJECT_ORIGIN')
        grid = box_origin.grid_flow(columns=2, align=True)
        op = grid.operator("object.origin_set", text="BBox", icon='PIVOT_BOUNDBOX')
        op.type = 'ORIGIN_GEOMETRY'
        op.center = 'BOUNDS'
        grid.operator("object.origin_set", text="To Cursor", icon='PIVOT_CURSOR').type = 'ORIGIN_CURSOR'
        grid.operator("alec.origin_to_cursor", text="To Cur (Rot)", icon='ORIENTATION_GIMBAL')
        grid.operator("alec.origin_to_active", text="To Active", icon='PIVOT_ACTIVE')
        grid.operator("alec.origin_to_bottom", text="To Bott.", icon='TRIA_DOWN')



classes = [
    ALEC_MT_object_menu,
    ALEC_MT_edit_menu,
    ALEC_MT_edit_curve_menu,
    ALEC_MT_uv_menu,
    ALEC_MT_quad_menu,
    *menus_browser.classes,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
