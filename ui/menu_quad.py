"""3D View quad pie menu (Alt+Right Click) — ALEC_MT_quad_menu."""

import bpy


def find_layer_collection(layer_coll, target_coll):
    if layer_coll.collection == target_coll:
        return layer_coll
    for child in layer_coll.children:
        found = find_layer_collection(child, target_coll)
        if found:
            return found
    return None


class ALEC_MT_quad_menu(bpy.types.Menu):
    bl_idname = "ALEC_MT_quad_menu"
    bl_label = "Quad Menu"

    def draw(self, context):
        pie = self.layout.menu_pie()
        # Ordine pie (4 felii): Stânga | Dreapta | Jos | Sus
        # 1) Left  : Viewport | Align View (+ rotate ±90°)
        # 2) Right : Pivot + Orientation + Snap
        # 3) Bottom: Cursor + Origin
        # 4) Top   : Visibility

        # --- Slice 1 (Left): Viewport | Align View ---
        col_left = pie.column()
        row_lv = col_left.row()

        col_view = row_lv.column()
        box_view = col_view.box()
        box_view.label(text="Viewport", icon='RESTRICT_VIEW_OFF')
        col_inner = box_view.column(align=True)
        grid_vis = col_inner.grid_flow(columns=3, align=True, even_columns=True)
        grid_vis.prop(context.space_data, "show_object_viewport_mesh", text="Mesh", icon='MESH_DATA', toggle=True)
        grid_vis.prop(context.space_data, "show_object_viewport_curves", text="Curves", icon='OUTLINER_OB_CURVE', toggle=True)
        grid_vis.prop(context.space_data, "show_object_viewport_empty", text="Empty", icon='EMPTY_DATA', toggle=True)
        grid_vis.prop(context.space_data, "show_object_viewport_light", text="Light", icon='LIGHT_DATA', toggle=True)
        grid_vis.prop(context.space_data, "show_object_viewport_camera", text="Camera", icon='CAMERA_DATA', toggle=True)
        col_inner.operator("alec.viewport_show_common_types", text="Show All", icon='CHECKMARK')

        col_rot = row_lv.column()
        box_rot = col_rot.box()
        box_rot.label(text="Align View", icon='VIEW_PERSPECTIVE')
        grid_align = box_rot.grid_flow(columns=2, align=True, even_columns=True)
        for axis_type, label in (
            ("TOP", "Top"),
            ("BOTTOM", "Bottom"),
            ("FRONT", "Front"),
            ("BACK", "Back"),
            ("RIGHT", "Right"),
            ("LEFT", "Left"),
        ):
            op = grid_align.operator("view3d.view_axis", text=label)
            op.align_active = True
            op.type = axis_type

        box_rot.separator(factor=0.5)
        box_rot.label(text="Rotate ±90°", icon='DRIVER_ROTATIONAL_DIFFERENCE')
        col_rot_btns = box_rot.column(align=True)
        prev_rot_ctx = col_rot_btns.operator_context
        col_rot_btns.operator_context = 'EXEC_DEFAULT'
        for axis in ('X', 'Y', 'Z'):
            row_ax = col_rot_btns.row(align=True)
            op_m = row_ax.operator(
                "alec.selection_rotate_axis_90",
                text=f"-90 {axis}",
            )
            op_m.axis = axis
            op_m.angle_degrees = -90.0
            op_p = row_ax.operator(
                "alec.selection_rotate_axis_90",
                text=f"+90 {axis}",
            )
            op_p.axis = axis
            op_p.angle_degrees = 90.0
        col_rot_btns.operator_context = prev_rot_ctx

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

        # --- Slice 4 (Top): Visibility ---
        col_top = pie.column()
        box_vis = col_top.box()
        box_vis.label(text="Visibility", icon='WINDOW')
        grid_vis_tools = box_vis.grid_flow(columns=2, align=True, even_columns=True)
        coll = bpy.data.collections.get("Hidden_Bools")
        if coll is not None:
            layer_coll = find_layer_collection(context.view_layer.layer_collection, coll)
            if layer_coll is not None:
                grid_vis_tools.prop(layer_coll, "exclude", text="Bools Toggle", toggle=True, icon='OUTLINER_COLLECTION')
            else:
                grid_vis_tools.operator("alec.hidden_bools_visibility", text="Bools Toggle", icon='OUTLINER_COLLECTION').action = 'TOGGLE'
        else:
            grid_vis_tools.operator("alec.hidden_bools_visibility", text="Bools Toggle", icon='OUTLINER_COLLECTION').action = 'TOGGLE'

        coll_hidden_obj = bpy.data.collections.get("Hidden_Obj")
        if coll_hidden_obj is not None:
            layer_coll_hidden_obj = find_layer_collection(context.view_layer.layer_collection, coll_hidden_obj)
            if layer_coll_hidden_obj is not None:
                grid_vis_tools.prop(
                    layer_coll_hidden_obj, "exclude",
                    text="Hidden_Obj Toggle", toggle=True, icon='HIDE_ON'
                )
            else:
                grid_vis_tools.operator("alec.hidden_obj_visibility", text="Hidden_Obj Toggle", icon='HIDE_ON')
        else:
            grid_vis_tools.operator("alec.hidden_obj_visibility", text="Hidden_Obj Toggle", icon='HIDE_ON')
        grid_vis_tools.operator("alec.move_to_hidden_obj", text="To Hidden_Obj", icon='HIDE_ON')
        grid_vis_tools.operator("alec.toggle_mesh_wire_textured", text="Wire Togg", icon='SHADING_WIRE')
        grid_vis_tools.operator("alec.toggle_mesh_bounds_textured", text="Box Togg", icon='SHADING_BBOX')
