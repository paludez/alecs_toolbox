"""
Normal (non-pie) menus listing Alec operators for Quick Favorites (right-click).
Pies and Alt+Q dispatcher stay in menus.py / system.py.
"""

import bpy
import math


def _has_alec_op(name: str) -> bool:
    """False if mesh-key operators are unregistered."""
    try:
        cat, op = name.split(".", 1)
    except ValueError:
        return False
    mod = getattr(bpy.ops, cat, None)
    if mod is None:
        return False
    return hasattr(mod, op)


class ALEC_MT_alec_browser(bpy.types.Menu):
    bl_idname = "ALEC_MT_alec_browser"
    bl_label = "Alec's Toolbox"

    def draw(self, context):
        layout = self.layout
        layout.menu("ALEC_MT_alec_browser_object", icon="OBJECT_DATA")
        layout.menu("ALEC_MT_alec_browser_mesh", icon="MESH_DATA")
        layout.menu("ALEC_MT_alec_browser_curve", icon="CURVE_DATA")
        layout.menu("ALEC_MT_alec_browser_uv", icon="UV")
        layout.menu("ALEC_MT_alec_browser_viewport", icon="VIEW3D")
        layout.menu("ALEC_MT_alec_browser_materials", icon="MATERIAL")
        layout.menu("ALEC_MT_alec_browser_mesh_keys", icon="KEYINGSET")
        layout.separator()
        layout.operator("alec.menu_dispatcher", text="Context pie (Alt+Q)", icon="MENU_PANEL")


class ALEC_MT_alec_browser_object(bpy.types.Menu):
    bl_idname = "ALEC_MT_alec_browser_object"
    bl_label = "Object / Modifiers / Group"

    def draw(self, context):
        l = self.layout
        l.label(text="BBox")
        col = l.column(align=True)
        col.operator("alec.bbox_local", text="BBox Local")
        col.operator("alec.bbox_world", text="BBox World")
        col.operator("alec.bbox_offset_modal", text="BBox Offset")
        l.separator()
        l.label(text="Align")
        col = l.column(align=True)
        col.operator("alec.quick_center", text="Align Centers")
        col.operator("alec.quick_pivot", text="Align Origins")
        col.operator("alec.align_dialog", text="Align Dialog")
        l.separator()
        l.label(text="Modifiers")
        col = l.column(align=True)
        col.operator("alec.boolean_op", text="Boolean Union").operation = "UNION"
        col.operator("alec.boolean_op", text="Boolean Difference").operation = "DIFFERENCE"
        col.operator("alec.boolean_op", text="Boolean Intersect").operation = "INTERSECT"
        col.operator("alec.slice_boolean", text="Slice Boolean")
        col.operator("alec.slice_gn", text="Slice Plane (GN)")
        col.operator("alec.add_simple_modifier", text="Mirror").mod_type = "MIRROR"
        col.operator("alec.mirror_control", text="Mirror (Null)")
        col.operator("alec.solidify_modal", text="Solidify")
        col.operator("alec.add_simple_modifier", text="Subdivision").mod_type = "SUBSURF"
        col.operator("alec.modifier_action", text="Modifier Move Up").action = "MOVE_UP"
        col.operator("alec.modifier_action", text="Modifier Move Down").action = "MOVE_DOWN"
        col.operator("alec.modifier_action", text="Apply Last Modifier").action = "APPLY_LAST"
        col.operator("alec.modifier_action", text="Apply All Modifiers").action = "APPLY_ALL"
        col.operator("alec.modifier_action", text="Delete Last Modifier").action = "DELETE_LAST"
        col.operator("alec.modifier_action", text="Delete All Modifiers").action = "DELETE_ALL"
        l.separator()
        l.label(text="Grouping")
        col = l.column(align=True)
        col.operator("alec.group", text="Group")
        col.operator("alec.group_active", text="Group Active")
        col.operator("alec.ungroup", text="Ungroup")
        l.separator()
        l.label(text="Origin (Alec)")
        col = l.column(align=True)
        col.operator("alec.origin_to_cursor", text="Origin to Cursor (Rot)")
        col.operator("alec.origin_to_active", text="Origin to Active")
        col.operator("alec.origin_to_bottom", text="Origin to Bottom")


class ALEC_MT_alec_browser_mesh(bpy.types.Menu):
    bl_idname = "ALEC_MT_alec_browser_mesh"
    bl_label = "Edit Mesh"

    def draw(self, context):
        l = self.layout
        l.label(text="Collinear")
        col = l.column(align=True)
        op = col.operator("alec.make_collinear", text="Farthest Points")
        op.mode = "FARTHEST"
        op.distribute = False
        op = col.operator("alec.make_collinear", text="Last Two Selected")
        op.mode = "HISTORY"
        op.distribute = False
        op = col.operator("alec.make_collinear", text="Align & Distribute")
        op.mode = "FARTHEST"
        op.distribute = True
        col.operator("alec.distribute_vertices", text="Distribute Evenly")
        l.separator()
        l.label(text="Coplanar")
        col = l.column(align=True)
        op = col.operator("alec.make_coplanar", text="Best Fit")
        op.mode = "BEST_FIT"
        op = col.operator("alec.make_coplanar", text="Last Three Selected")
        op.mode = "HISTORY"
        op = col.operator("alec.make_coplanar", text="Active Face Normal")
        op.mode = "ACTIVE_FACE"
        l.separator()
        l.operator("alec.extract_and_solidify", text="Extract Panel (Solidify)")
        l.separator()
        l.label(text="Shapes / Cleanup")
        col = l.column(align=True)
        col.operator("alec.make_circle", text="Perfect Circle")
        col.operator("alec.clean_mesh", text="Clean Planar")
        l.separator()
        l.label(text="Origin (Edit)")
        col = l.column(align=True)
        col.operator("alec.origin_to_selected_edit", text="To Selection")
        col.operator("alec.origin_to_selected_edit_aligned", text="To Selection (Aligned)")
        l.separator()
        l.label(text="Dimensions / Edges")
        col = l.column(align=True)
        col.operator("alec.equalize_edge_lengths", text="Equalize Edge Lengths")
        col.operator("alec.set_edge_length", text="Set Edge Length")
        col.operator("alec.dimension_action", text="Dimension Add").action = "ADD"
        col.operator("alec.dimension_action", text="Dimension Remove").action = "REMOVE"
        col.operator("alec.dimension_action", text="Dimension Clear All").action = "CLEAR"
        col.operator("alec.select_dimension_edges", text="Select Dimension Edges")
        col.operator("alec.set_edge_angle", text="Set Edge Angle 90°").angle = math.pi / 2.0
        col.operator("alec.set_edge_angle", text="Set Edge Angle…").run_modal = True


class ALEC_MT_alec_browser_curve(bpy.types.Menu):
    bl_idname = "ALEC_MT_alec_browser_curve"
    bl_label = "Edit Curve"

    def draw(self, context):
        l = self.layout
        col = l.column(align=True)
        op = col.operator("alec.make_collinear", text="Farthest Points")
        op.mode = "FARTHEST"
        op.distribute = False
        op = col.operator("alec.make_collinear", text="Align & Distribute")
        op.mode = "FARTHEST"
        op.distribute = True
        op = col.operator("alec.make_coplanar", text="Best Fit")
        op.mode = "BEST_FIT"
        col.operator("alec.coplanar_curve_three_point_plane", text="3-Point Plane")


class ALEC_MT_alec_browser_uv(bpy.types.Menu):
    bl_idname = "ALEC_MT_alec_browser_uv"
    bl_label = "UV / Image"

    def draw(self, context):
        l = self.layout
        col = l.column(align=True)
        col.operator("alec.load_material_image", text="Load Image from Material")
        col.operator("alec.square_pixels", text="Square Pixels")


class ALEC_MT_alec_browser_viewport(bpy.types.Menu):
    bl_idname = "ALEC_MT_alec_browser_viewport"
    bl_label = "Cursor / Shaders"

    def draw(self, context):
        l = self.layout
        col = l.column(align=True)
        col.operator("alec.cursor_to_selected", text="Cursor to Selected")
        col.operator("alec.cursor_to_geometry_center", text="Cursor to Geometry Center")
        col.separator()
        col.operator("alec.floating_shader_editor", text="Floating Object Shader").mode = "OBJECT"
        col.operator("alec.floating_shader_editor", text="Floating World Shader").mode = "WORLD"


class ALEC_MT_alec_browser_materials(bpy.types.Menu):
    bl_idname = "ALEC_MT_alec_browser_materials"
    bl_label = "Materials"

    def draw(self, context):
        l = self.layout
        col = l.column(align=True)
        col.operator("alec.material_linker", text="Material Linker")
        col.operator("alec.assign_gray_material", text="Gray Material (70%)")
        col.operator("alec.remove_orphan_materials", text="Remove Orphan Materials")
        col.operator("alec.select_material_users", text="Select Material Users")
        col.operator("alec.modify_material_slot", text="Modify Material Slot")
        col.operator("alec.material_apply_operation", text="Material Apply Operation")


class ALEC_MT_alec_browser_mesh_keys(bpy.types.Menu):
    bl_idname = "ALEC_MT_alec_browser_mesh_keys"
    bl_label = "Mesh keys (1–5)"

    def draw(self, context):
        l = self.layout
        if _has_alec_op("alec.mesh_edit_component"):
            col = l.column(align=True)
            col.operator("alec.mesh_edit_component", text="Component: Vertex").component = "VERT"
            col.operator("alec.mesh_edit_component", text="Component: Edge").component = "EDGE"
            col.operator("alec.mesh_edit_component", text="Component: Face").component = "FACE"
        else:
            l.label(text="Enable in addon preferences:")
            l.label(text="Max-style mesh keys (1–5)")
        if _has_alec_op("alec.mesh_select_linked_expand"):
            l.separator()
            l.operator("alec.mesh_select_linked_expand", text="Select Linked Expand (4)")
        if _has_alec_op("alec.mesh_select_open_edges_connected"):
            l.operator("alec.mesh_select_open_edges_connected", text="Open Edges Connected (5)")


classes = (
    ALEC_MT_alec_browser,
    ALEC_MT_alec_browser_object,
    ALEC_MT_alec_browser_mesh,
    ALEC_MT_alec_browser_curve,
    ALEC_MT_alec_browser_uv,
    ALEC_MT_alec_browser_viewport,
    ALEC_MT_alec_browser_materials,
    ALEC_MT_alec_browser_mesh_keys,
)
