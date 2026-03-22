"""N-panel Alec tab: Transform + Camera Tools (același panel)."""

import bpy

from .operators.camera_tools import _camera_data_from_context
from .ui.transform import selection_math as sm


def _draw_reset_btn(row, column_id: str, enabled: bool = True) -> None:
    op = row.operator(
        "alec.reset_transform_column",
        icon="FILE_ALIAS",
        text="",
        emboss=False,
    )
    op.column = column_id
    try:
        op.enabled = enabled
    except Exception:
        pass

def _draw_object_transform(layout, context, obj):
    scene = context.scene
    layout.use_property_split = True
    layout.use_property_decorate = True

    no_obj = obj is None
    if no_obj:
        edit_mesh = False
        props = None
        mesh = None
        has_sel = False
    else:
        edit_mesh = context.mode == "EDIT_MESH" and obj.type == "MESH"
        props = scene.alec_edit_selection if edit_mesh else None
        mesh = obj.data if edit_mesh else None
        has_sel = (
            bool(sm._selected_vert_positions_world(context, obj, mesh))
            if edit_mesh and mesh
            else False
        )

    block = layout.column()
    if no_obj:
        block.enabled = False

    if edit_mesh:
        block.label(text="Selection Transform", icon="EDITMODE_HLT")
    else:
        block.label(text="Object Transform", icon="OBJECT_DATA")

    row = block.row(align=True)
    split = row.split(factor=0.5)

    col_w = split.column(align=True)
    sub_w = col_w.column(align=True)
    sub_w.use_property_split = True
    sub_w.use_property_decorate = True
    row_w = sub_w.row(align=True)
    row_w.use_property_split = True

    row_wh = row_w.row(align=True)
    row_wh.label(text="World")
    _draw_reset_btn(
        row_wh, "WORLD_MEAN", enabled=(not no_obj) and ((not edit_mesh) or has_sel)
    )
    xyz_w = sub_w.column(align=True)
    xyz_w.use_property_split = False
    xyz_w.use_property_decorate = False
    if edit_mesh and props is not None:
        xyz_w.enabled = has_sel
        for i, axis in enumerate(("X", "Y", "Z")):
            xyz_w.prop(props, "mean_w", index=i, text=axis)
    else:
        for i, axis in enumerate(("X", "Y", "Z")):
            xyz_w.prop(scene, "alec_object_world", index=i, text=axis)

    row_wr = sub_w.row(align=True)
    row_wr.use_property_split = True

    row_wrh = row_wr.row(align=True)
    row_wrh.label(text="Rot.World")
    if not edit_mesh:
        _draw_reset_btn(row_wrh, "ROT_WORLD", enabled=not no_obj)
    rot_w = sub_w.column(align=True)
    rot_w.use_property_split = False
    rot_w.use_property_decorate = False
    if edit_mesh and props is not None:
        rot_w.enabled = has_sel
        for i, axis in enumerate(("X", "Y", "Z")):
            rot_w.prop(props, "sel_rot_world_euler", index=i, text=axis)
    else:
        for i, axis in enumerate(("X", "Y", "Z")):
            rot_w.prop(scene, "alec_rotation_world", index=i, text=axis)

    col_o = split.column(align=True)
    sub_o = col_o.column(align=True)
    sub_o.use_property_split = True
    sub_o.use_property_decorate = True
    row_o = sub_o.row(align=True)
    row_o.use_property_split = True
    row_oh = row_o.row(align=True)
    row_oh.label(text="Local")
    _draw_reset_btn(
        row_oh, "LOCAL_MEAN", enabled=(not no_obj) and ((not edit_mesh) or has_sel)
    )

    xyz_o = sub_o.column(align=True)
    xyz_o.use_property_split = False
    xyz_o.use_property_decorate = False
    if edit_mesh and props is not None:
        xyz_o.enabled = has_sel
        for i, axis in enumerate(("X", "Y", "Z")):
            xyz_o.prop(props, "mean_local", index=i, text=axis)
    elif no_obj:
        for i, axis in enumerate(("X", "Y", "Z")):
            xyz_o.prop(scene, "alec_transform_ui_dummy_loc", index=i, text=axis)
    else:
        for i, axis in enumerate(("X", "Y", "Z")):
            xyz_o.prop(obj, "location", index=i, text=axis)

    row_or = sub_o.row(align=True)
    row_or.use_property_split = True

    row_orh = row_or.row(align=True)
    row_orh.label(text=sm._rot_orient_column_label(context))
    if not edit_mesh:
        _draw_reset_btn(row_orh, "ROT_ORIENT", enabled=not no_obj)
    rot_o = sub_o.column(align=True)
    rot_o.use_property_split = False
    rot_o.use_property_decorate = False
    if edit_mesh and props is not None:
        rot_o.enabled = has_sel
        for i, axis in enumerate(("X", "Y", "Z")):
            rot_o.prop(props, "sel_rot_orient_euler", index=i, text=axis)
    else:
        for i, axis in enumerate(("X", "Y", "Z")):
            rot_o.prop(scene, "alec_rotation_local", index=i, text=axis)


    row_sd = block.row(align=True)
    row_sd.use_property_split = False
    split_sd = row_sd.split(factor=0.5)
    col_s = split_sd.column(align=True)
    col_d = split_sd.column(align=True)
    oshort = sm._transform_orient_short(context)
    if edit_mesh and props is not None:
        col_s.label(text=f"Scale ({oshort})")
        sub_s = col_s.column(align=True)
        sub_s.use_property_split = False
        sub_s.use_property_decorate = False
        sub_s.enabled = has_sel
        for i, axis in enumerate(("X", "Y", "Z")):
            sub_s.prop(props, "sel_scale_orient", index=i, text=axis)
        col_d.label(text=f"Dims ({oshort})")
        sub_d = col_d.column(align=True)
        sub_d.use_property_split = False
        sub_d.use_property_decorate = False
        sub_d.enabled = has_sel
        for i, axis in enumerate(("X", "Y", "Z")):
            sub_d.prop(props, "sel_dims_orient", index=i, text=axis)
    else:
        row_sh = col_s.row(align=True)
        row_sh.label(text="Scale")
        _draw_reset_btn(row_sh, "SCALE", enabled=not no_obj)
        sub_s = col_s.column(align=True)
        sub_s.use_property_split = False
        sub_s.use_property_decorate = False
        if no_obj:
            sub_s.prop(scene, "alec_transform_ui_dummy_scale", text="")
        else:
            sub_s.prop(obj, "scale", text="")
        col_d.label(text="Dimensions")
        sub_d = col_d.column(align=True)
        sub_d.use_property_split = False
        sub_d.use_property_decorate = False
        if no_obj:
            sub_d.prop(scene, "alec_transform_ui_dummy_dims", text="")
        else:
            sub_d.prop(obj, "dimensions", text="")


def _draw_camera_tools(layout, context):
    layout.use_property_split = False
    layout.use_property_decorate = False
    layout.separator()
    layout.label(text="Camera Tools", icon="CAMERA_DATA")
    col = layout.column(align=True)
    col.use_property_split = False
    row = col.row(align=True)
    row.operator("alec.new_camera_to_view", text="New Cam.")
    cd = _camera_data_from_context(context)
    icon = (
        "STRIP_COLOR_09"
        if (cd is not None and cd.passepartout_alpha >= 0.75)
        else "MATPLANE"
    )
    depress = cd is not None and cd.passepartout_alpha >= 0.75
    row.operator(
        "alec.camera_passepartout",
        text="",
        icon=icon,
        depress=depress,
    )


class ALEC_PT_alec_transform(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Alec"
    bl_label = "Transform"

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "VIEW_3D"

    def draw_header(self, context):
        layout = self.layout

        layout.label(text="Alec's Tools", icon="EXPERIMENTAL")

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is not None and context.mode == "EDIT_MESH" and obj.type == "MESH":
            mesh = obj.data
            edit_positions = sm._selected_vert_positions_world(context, obj, mesh)
            sig = sm._selection_vert_signature(context, obj, mesh)
            sid = id(context.scene)
            if sig != sm._last_selection_sig_by_scene.get(sid):
                sm._last_selection_sig_by_scene[sid] = sig
                if edit_positions and not sm._sync_selection_timer_pending:
                    sm._sync_selection_timer_pending = True
                    bpy.app.timers.register(
                        sm._deferred_sync_selection_props, first_interval=0.0
                    )
        _draw_object_transform(layout, context, obj)
        _draw_camera_tools(layout, context)


def register():
    bpy.types.Scene.alec_transform_ui_dummy_loc = bpy.props.FloatVectorProperty(
        name="Location",
        size=3,
        subtype="TRANSLATION",
        default=(0.0, 0.0, 0.0),
    )
    bpy.types.Scene.alec_transform_ui_dummy_scale = bpy.props.FloatVectorProperty(
        name="Scale",
        size=3,
        subtype="XYZ",
        default=(1.0, 1.0, 1.0),
    )
    bpy.types.Scene.alec_transform_ui_dummy_dims = bpy.props.FloatVectorProperty(
        name="Dimensions",
        size=3,
        subtype="XYZ",
        default=(0.0, 0.0, 0.0),
    )
    bpy.utils.register_class(ALEC_PT_alec_transform)


def unregister():
    bpy.utils.unregister_class(ALEC_PT_alec_transform)
    del bpy.types.Scene.alec_transform_ui_dummy_loc
    del bpy.types.Scene.alec_transform_ui_dummy_scale
    del bpy.types.Scene.alec_transform_ui_dummy_dims