import bpy
import math

from . import menus_browser


def _shader_add_node(layout, text, icon, node_type: str):
    """node.add_node: type/use_transform are not valid UILayout.operator() kwargs in Blender 5."""
    op = layout.operator("node.add_node", text=text, icon=icon)
    op.type = node_type
    op.use_transform = True


# Insert between tuples in _SHADER_EDIT_PIE_NODES_* for a horizontal rule in the pie slice.
_SHADER_PIE_SEP = object()


def _shader_add_node_pairs(parent, entries):
    col = parent.column(align=True)
    n = len(entries)
    i = 0
    while i < n:
        entry = entries[i]
        if entry is _SHADER_PIE_SEP:
            col.separator()
            i += 1
            continue
        if i + 1 < n and entries[i + 1] is not _SHADER_PIE_SEP:
            split = col.split(factor=0.5, align=True)
            c0 = split.column(align=True)
            c1 = split.column(align=True)
            label, icon, node_id = entries[i]
            label2, icon2, node_id2 = entries[i + 1]
            _shader_add_node(c0, label, icon, node_id)
            _shader_add_node(c1, label2, icon2, node_id2)
            i += 2
        else:
            label, icon, node_id = entries[i]
            _shader_add_node(col, label, icon, node_id)
            i += 1


# Shader Editor pie: four slices (Left/Right/Bottom/Top) — direct buttons, no submenus.
_SHADER_EDIT_PIE_NODES_NORMAL = (
    ("Image", "IMAGE_DATA", "ShaderNodeTexImage"),
    ("Environment", "WORLD", "ShaderNodeTexEnvironment"),
    _SHADER_PIE_SEP,
    ("Principled", "SHADING_RENDERED", "ShaderNodeBsdfPrincipled"),
    ("Emission", "LIGHT", "ShaderNodeEmission"),
    ("Glass", "SHADING_RENDERED", "ShaderNodeBsdfGlass"),
    ("Gloassy", "SHADING_RENDERED", "ShaderNodeBsdfGlossy"),
    _SHADER_PIE_SEP,
    ("RGB", "COLOR", "ShaderNodeRGB"),
    ("Value", "LINENUMBERS_OFF", "ShaderNodeValue"),
    ("Ramp", "COLOR", "ShaderNodeValToRGB"),
    _SHADER_PIE_SEP,
    ("AO", "COLOR", "ShaderNodeAmbientOcclusion"),
    ("Bevel", "LINENUMBERS_OFF", "ShaderNodeBevel"),
    ("Attrib.", "LINENUMBERS_OFF", "ShaderNodeAttribute"),
    ("Geo", "MOD_NOISE", "ShaderNodeNewGeometry"),
    ("Light Path", "SHADING_RENDERED", "ShaderNodeLightPath"),

)
_SHADER_EDIT_PIE_NODES_SHADERS = (
    ("Tex Coord", "EMPTY_AXIS", "ShaderNodeTexCoord"),
    ("Mapping", "EMPTY_DATA", "ShaderNodeMapping"),
    ("UV Map", "GROUP_UVS", "ShaderNodeUVMap"),
    _SHADER_PIE_SEP,
    ("Normal Map", "ORIENTATION_NORMAL", "ShaderNodeNormalMap"),
    ("Bump", "MOD_NOISE", "ShaderNodeBump"),
    ("Fresnel", "SHADING_RENDERED", "ShaderNodeFresnel"),
    ("Layer Weight", "MOD_VERTEX_WEIGHT", "ShaderNodeLayerWeight"),
    ("Light Falloff", "LIGHT", "ShaderNodeLightFalloff"),
)
_SHADER_EDIT_PIE_NODES_UTILS = (
    ("fMath", "LINENUMBERS_OFF", "ShaderNodeMath"),
    ("vMath", "LINENUMBERS_OFF", "ShaderNodeVectorMath"),
    ("Mix", "IMAGE_ALPHA", "ShaderNodeMix"),
    ("Curves", "TEXTURE", "ShaderNodeRGBCurve"),
    ("Invert", "ARROW_LEFTRIGHT", "ShaderNodeInvert"),
    ("Hue/Sat", "COLOR", "ShaderNodeHueSaturation"),
    ("Gamma", "IMAGE", "ShaderNodeGamma"),
    ("Clamp", "MOD_LENGTH", "ShaderNodeClamp"),
    ("Map Range", "ARROW_LEFTRIGHT", "ShaderNodeMapRange"),
    _SHADER_PIE_SEP,
    ("Sep Color", "COLOR", "ShaderNodeSeparateColor"),
    ("Comb Color", "COLOR", "ShaderNodeCombineColor"),

)


class ALEC_OT_viewport_show_common_types(bpy.types.Operator):
    """Enable common viewport object-type visibility filters"""
    bl_idname = "alec.viewport_show_common_types"
    bl_label = "Show Common Types"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.space_data and context.space_data.type == 'VIEW_3D')

    def execute(self, context):
        space = context.space_data
        space.show_object_viewport_mesh = True
        space.show_object_viewport_curves = True
        space.show_object_viewport_empty = True
        space.show_object_viewport_light = True
        space.show_object_viewport_camera = True
        return {'FINISHED'}


class ALEC_MT_quad_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_quad_menu"
    bl_label = "Quad Menu"

    def draw(self, context):
        pie = self.layout.menu_pie()
        # Pie slice ordering for Alt+RightClick:
        # 1) Left  : Viewport
        # 2) Right : Pivot + Orientation + Snap
        # 3) Bottom: Cursor + Origin
        # 4) Top   : Floating Shaders

        # --- Slice 1 (Left): Viewport ---
        col_left = pie.column()
        box_view = col_left.box()
        box_view.label(text="Viewport", icon='RESTRICT_VIEW_OFF')
        col_inner = box_view.column(align=True)
        grid_vis = col_inner.grid_flow(columns=3, align=True, even_columns=True)
        grid_vis.prop(context.space_data, "show_object_viewport_mesh", text="Mesh", icon='MESH_DATA', toggle=True)
        grid_vis.prop(context.space_data, "show_object_viewport_curves", text="Curves", icon='OUTLINER_OB_CURVE', toggle=True)
        grid_vis.prop(context.space_data, "show_object_viewport_empty", text="Empty", icon='EMPTY_DATA', toggle=True)
        grid_vis.prop(context.space_data, "show_object_viewport_light", text="Light", icon='LIGHT_DATA', toggle=True)
        grid_vis.prop(context.space_data, "show_object_viewport_camera", text="Camera", icon='CAMERA_DATA', toggle=True)
        col_inner.operator("alec.viewport_show_common_types", text="Show All", icon='CHECKMARK')


        # --- Slice 2 (Right): Pivot Point ---
        col_right = pie.column()
        box_pivot = col_right.box()
        box_pivot.label(text="Pivot Point", icon='PIVOT_MEDIAN')
        grid = box_pivot.grid_flow(columns=3, align=True, even_columns=True)
        for val, txt in [('BOUNDING_BOX_CENTER', "BBox"), ('CURSOR', "Cursor"), ('INDIVIDUAL_ORIGINS', "Indiv"),
                         ('MEDIAN_POINT', "Median"), ('ACTIVE_ELEMENT', "Active")]:
            grid.prop_enum(context.tool_settings, "transform_pivot_point", value=val, text=txt)
        grid.prop(context.tool_settings, "use_transform_pivot_point_align", text="Only Loc")

        box_orient = col_right.box()
        box_orient.label(text="Orientation", icon='ORIENTATION_GLOBAL')
        slot = context.scene.transform_orientation_slots[0]
        grid = box_orient.grid_flow(columns=3, align=True, even_columns=True)
        for val in ['GLOBAL', 'LOCAL', 'NORMAL', 'GIMBAL', 'CURSOR', 'PARENT']:
            grid.prop_enum(slot, "type", value=val, text=val.capitalize())

        box_snap = col_right.box()
        grid_snap_elements = box_snap.grid_flow(columns=3, align=True)
        for val, txt in [('INCREMENT', "Incr"), ('VERTEX', "Vertex"), ('EDGE', "Edge"), ('FACE', "Face"), ('VOLUME', "Volume")]:
            grid_snap_elements.prop_enum(context.tool_settings, "snap_elements", value=val, text=txt)

        box_snap.separator()
        grid_snap_target = box_snap.grid_flow(columns=3, align=True)
        for val in ['CENTER', 'MEDIAN', 'ACTIVE']:
            grid_snap_target.prop_enum(context.tool_settings, "snap_target", value=val, text=val.capitalize())

        # --- Slice 3 (Bottom): Cursor + Origin ---
        col_bottom = pie.column()
        box_cursor = col_bottom.box()
        box_cursor.label(text="Cursor", icon='PIVOT_CURSOR')
        grid_cursor = box_cursor.grid_flow(columns=2, align=True)
        grid_cursor.operator("alec.cursor_to_origin_rot", text="Origin(R)", icon='TRACKING_FORWARDS')
        grid_cursor.operator("alec.cursor_to_bbox_rot", text="BBox(R)", icon='TRACKING_FORWARDS')
        grid_cursor.operator("alec.cursor_to_selection", text="Selection", icon='TRACKING_FORWARDS_SINGLE')
        grid_cursor.operator("alec.cursor_to_selection_rot", text="Selection(R)", icon='TRACKING_FORWARDS_SINGLE')

        box_origin = col_bottom.box()
        box_origin.label(text="Origin", icon='OBJECT_ORIGIN')
        grid_origin = box_origin.grid_flow(columns=2, align=True)
        grid_origin.operator("alec.origin_set_to_bbox", text="BBox", icon='PIVOT_BOUNDBOX')
        grid_origin.operator("alec.origin_to_cursor", text="Cursor", icon='PIVOT_CURSOR')
        grid_origin.operator("alec.origin_to_cursor_rot", text="Cursor(R)", icon='ORIENTATION_GIMBAL')
        grid_origin.operator("alec.origin_to_bottom", text="Bottom", icon='TRIA_DOWN')
        grid_origin.operator("alec.origin_to_active", text="Active", icon='PIVOT_ACTIVE')
        grid_origin.operator("alec.origin_to_active_rot", text="Active(R)", icon='ORIENTATION_GIMBAL')
        grid_origin.operator("alec.origin_to_selection", text="Selection", icon='PIVOT_CURSOR')
        grid_origin.operator("alec.origin_to_selection_rot", text="Selection(R)", icon='ORIENTATION_NORMAL')
        prev_ctx = grid_origin.operator_context
        grid_origin.operator_context = 'INVOKE_DEFAULT'
        op = grid_origin.operator("alec.origin_rotate_axis", text="Rotate X", icon='DRIVER_ROTATIONAL_DIFFERENCE')
        op.axis = 'X'
        op.angle_degrees = 0.0
        op = grid_origin.operator("alec.origin_rotate_axis", text="Rotate Y", icon='DRIVER_ROTATIONAL_DIFFERENCE')
        op.axis = 'Y'
        op.angle_degrees = 0.0
        op = grid_origin.operator("alec.origin_rotate_axis", text="Rotate Z", icon='DRIVER_ROTATIONAL_DIFFERENCE')
        op.axis = 'Z'
        op.angle_degrees = 0.0
        grid_origin.operator_context = prev_ctx
        
        # --- Slice 4 (Top): Floating Shaders ---
        col_top = pie.column()
        box = col_top.box()
        box.label(text="Floating Shaders", icon='WINDOW')


class ALEC_MT_shader_edit_pie(bpy.types.Menu):
    bl_idname = "ALEC_MT_shader_edit_pie"
    bl_label = "Alec — Shader Editor"

    def draw(self, context):
        pie = self.layout.menu_pie()
        # Same order as quad pie: 1 Left, 2 Right, 3 Bottom, 4 Top
        col_left = pie.column()
        b = col_left.box()
        b.label(text="Normal", icon="NODE_COMPOSITING")
        _shader_add_node_pairs(b, _SHADER_EDIT_PIE_NODES_NORMAL)

        col_right = pie.column()
        b = col_right.box()
        b.label(text="Shaders", icon="SHADING_RENDERED")
        _shader_add_node_pairs(b, _SHADER_EDIT_PIE_NODES_SHADERS)

        col_bottom = pie.column()
        b = col_bottom.box()
        b.label(text="Utilities", icon="MODIFIER")
        _shader_add_node_pairs(b, _SHADER_EDIT_PIE_NODES_UTILS)

        col_top = pie.column()
        b = col_top.box()
        b.label(text="Triplanar", icon="TEXTURE")
        inner = b.column(align=True)
        inner.operator("alec.triplanar_color_maps", icon="TEXTURE")
        inner.operator("alec.triplanar_node_arrange", icon="NODE_SEL")


class ALEC_MT_uv_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_uv_menu"
    bl_label = "Alec UV"

    def draw(self, context):
        # Unwrap / align / pack etc. are already in the editor's default RMB menu.
        pie = self.layout.menu_pie()

        col = pie.column()
        box = col.box()
        box.label(text="Alec UV", icon='UV')
        inner = box.column(align=True)
        inner.operator("alec.load_material_image", text="Load from Mat", icon='IMAGE_DATA')
        inner.operator("alec.square_pixels", text="Square Pixels", icon='UV')

        pie.column()
        pie.column()
        pie.column()

class ALEC_MT_edit_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_edit_menu"
    bl_label = "Edit Menu"
    def draw(self, context):
        pie = self.layout.menu_pie()

        # Desired positions:
        # - Left  : Collinear / Coplanar / Extract
        # - Top   : Dimensions
        # - Right : Shapes / Orientation / Cleanup
        # - Bottom: Cursor + Origin (Edit)

        # --- Slice 1 (Left): Collinear / Coplanar / Extract ---
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

        # --- Slice 2 (Right): Shapes / Orientation / Cleanup ---
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

        # --- Slice 3 (Bottom): intentionally empty ---
        pie.column()

        # --- Slice 4 (Top): Dimensions ---
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

        box = col.box()
        box.label(text="Segments", icon='CURVE_DATA')
        col_inner = box.column(align=True)
        col_inner.operator("alec.curve_split_at_point", text="Split At Point", icon='SCULPTMODE_HLT')


class ALEC_MT_object_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_object_menu"
    bl_label = "Object Menu"

    def draw(self, context):
        pie = self.layout.menu_pie()
        # Pie slice ordering:
        # 1) Left  : BBox + Align
        # 2) Right : Modifiers
        # 3) Bottom: Grouping + Materials
        # 4) Top   : Parenting

        # --- Slice 1 (Left): BBox + Align ---
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
        col_inner.operator("alec.quick_center_rot", text="Align_Centers(Rot)")
        col_inner.operator("view3d.snap_selected_to_active", text="Align_Origins")
        col_inner.operator("alec.quick_pivot_rot", text="Align_Origins(Rot)")
        col_inner.operator("alec.align_dialog", text="Align Dialog")

        # --- Slice 2 (Right): Modifiers ---
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

        # --- Slice 3 (Bottom): Grouping + Materials ---
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

        # --- Slice 4 (Top): Parenting ---
        col_up = pie.column()

        box_parent = col_up.box()
        box_parent.label(text="Parenting", icon='ORIENTATION_PARENT')
        col_inner = box_parent.grid_flow(columns=2, align=True)
        op = col_inner.operator("object.parent_set", text="Parent", icon='LINKED')
        op.type = 'OBJECT'
        op.keep_transform = True
        col_inner.operator("object.parent_clear", text="Clear Parent", icon='X').type = 'CLEAR'
        col_inner.operator("object.parent_clear", text="Keep Tran.", icon='UNLINKED').type = 'CLEAR_KEEP_TRANSFORM'

classes = [
    ALEC_OT_viewport_show_common_types,
    ALEC_MT_object_menu,
    ALEC_MT_edit_menu,
    ALEC_MT_edit_curve_menu,
    ALEC_MT_uv_menu,
    ALEC_MT_quad_menu,
    ALEC_MT_shader_edit_pie,
    *menus_browser.classes,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
