import bpy
from ..modules.utils import draw_hidden_coll_toggle, safe_operator_props

_VIEW3D_TYPE_FILTER_UI = (
    ("mesh", 'MESH_DATA'),
    ("curves", 'OUTLINER_OB_CURVE'),
    ("empty", 'EMPTY_DATA'),
    ("light", 'LIGHT_DATA'),
    ("camera", 'CAMERA_DATA'),
)


def _draw_view3d_type_filter_row(box, space, label, prop_prefix, enable_op_id, *, label_icon='NONE'):
    row = box.row(align=True)
    row.label(text=label, icon=label_icon)
    btns = row.row(align=True)
    for name, icon in _VIEW3D_TYPE_FILTER_UI:
        btns.prop(space, f"show_object_{prop_prefix}_{name}", text="", icon=icon, toggle=True)
    btns.operator(enable_op_id, text="", icon='CON_ROTLIKE')


class ALEC_MT_quad_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_quad_menu"
    bl_label = "Quad Menu"

    def draw(self, context):
        pie = self.layout.menu_pie()
        # 1) Left  : Viewport | Align View
        # 2) Right : Pivot + Orientation + Snap
        # 3) Bottom: Cursor + Origin
        # 4) Top   : Visibility

        # --- Slice 1 (Left): Viewport | Align View ---
        col_left = pie.column()
        row_lv = col_left.row()

        col_view = row_lv.column()
        box_view = col_view.box()
        space = context.space_data
        _draw_view3d_type_filter_row(
            box_view, space, "Vis.", "viewport", "alec.viewport_show_common_types",
            label_icon='HIDE_OFF',
        )
        _draw_view3d_type_filter_row(
            box_view, space, "Sel.", "select", "alec.viewport_select_common_types",
            label_icon='RESTRICT_SELECT_OFF',
        )

        col_rot = row_lv.column()
        box_rot = col_rot.box()

        row_align = box_rot.row(align=True)
        row_align.label(text="Align View")
        axes = row_align.row(align=True)
        axes.operator_context = 'INVOKE_DEFAULT'
        for op_id, icon in (
            ("alec.view_axis_top", 'AXIS_TOP'),
            ("alec.view_axis_front", 'AXIS_FRONT'),
            ("alec.view_axis_right", 'AXIS_SIDE'),
        ):
            axes.operator(op_id, text="", icon=icon)

        row_affect = box_rot.row(align=True)
        row_affect.label(text="Affect Only")
        btns = row_affect.row(align=True)
        ts = context.tool_settings
        btns.prop(ts, "use_transform_data_origin", text="", icon='TRANSFORM_ORIGINS', toggle=True)
        btns.prop(ts, "use_transform_pivot_point_align", text="", icon='PIVOT_CURSOR', toggle=True)
        btns.prop(ts, "use_transform_skip_children", text="", icon='FILE_PARENT', toggle=True)

        # --- Slice 2 (Right): Pivot Point ---
        col_right = pie.column()
        box_pivot = col_right.box()
        row_pivot = box_pivot.row(align=True)
        row_pivot.label(text="Pivot Point")
        pivots = row_pivot.row(align=True)
        ts_pivot = context.tool_settings
        for val, icon in (
            ('BOUNDING_BOX_CENTER', 'PIVOT_BOUNDBOX'),
            ('CURSOR', 'PIVOT_CURSOR'),
            ('INDIVIDUAL_ORIGINS', 'PIVOT_INDIVIDUAL'),
            ('MEDIAN_POINT', 'PIVOT_MEDIAN'),
            ('ACTIVE_ELEMENT', 'PIVOT_ACTIVE'),
        ):
            pivots.prop_enum(ts_pivot, "transform_pivot_point", value=val, text="", icon=icon)

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

        # --- Slice 4 (Top): Visibility ---
        col_top = pie.column()
        box_vis = col_top.box()
        box_vis.label(text="Visibility", icon='WINDOW')
        grid_vis_tools = box_vis.grid_flow(columns=2, align=True, even_columns=True)
        draw_hidden_coll_toggle(grid_vis_tools, context, "Hidden_Bools", "Bools Toggle", icon='OUTLINER_COLLECTION')
        draw_hidden_coll_toggle(grid_vis_tools, context, "Hidden_Obj", "Hidden_Obj Toggle")
        draw_hidden_coll_toggle(grid_vis_tools, context, "Hidden_Sources", "Sources Toggle")

        grid_vis_tools.operator("alec.move_to_hidden_obj", text="To Hidden_Obj", icon='HIDE_ON')
        grid_vis_tools.operator("alec.toggle_mesh_wire_textured", text="Wire Togg", icon='SHADING_WIRE')
        grid_vis_tools.operator("alec.toggle_mesh_bounds_textured", text="Box Togg", icon='SHADING_BBOX')
