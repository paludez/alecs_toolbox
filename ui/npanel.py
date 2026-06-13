"""N-panel Alec tab: Camera Tools + Lights + 2D Drafting + Misc submenu."""

import bpy

from ..operators import camera_tools as _camera_tools_mod
from ..operators.camera_tools import (
    view3d_camera_rv3d,
    _camera_data_from_context,
    camera_sphere_track_target,
    focal_edit_camera,
    scene_persp_camera,
)
from ..operators.light_tools import alec_sphere_track_target

_LIGHTS_UI_DUMMY_PROPS = {
    "alec_lights_ui_dummy_energy": bpy.props.FloatProperty(
        name="Energy",
        description="Placeholder when no light is active",
        default=1000.0,
        min=0.0,
        soft_max=100000.0,
    ),
    "alec_lights_ui_dummy_color": bpy.props.FloatVectorProperty(
        name="Color",
        description="Placeholder when no light is active",
        size=3,
        subtype="COLOR",
        default=(1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
    ),
    "alec_lights_ui_dummy_lt_distance": bpy.props.FloatProperty(
        name="Distance",
        description="Placeholder when no light is active",
        default=3.0,
        min=0.01,
        soft_max=500.0,
        unit="LENGTH",
    ),
    "alec_lights_ui_dummy_lt_angle": bpy.props.FloatProperty(
        name="Azimuth",
        description="Placeholder when no light is active",
        default=0.0,
        subtype="ANGLE",
    ),
    "alec_lights_ui_dummy_lt_elevation": bpy.props.FloatProperty(
        name="Elevation",
        description="Placeholder when no light is active",
        default=0.0,
        subtype="ANGLE",
    ),
    "alec_lights_ui_dummy_lt_tgt_distance": bpy.props.FloatProperty(
        name="Target Distance",
        description="Placeholder when no light track target",
        default=3.0,
        min=0.01,
        soft_max=500.0,
        unit="LENGTH",
    ),
    "alec_lights_ui_dummy_lt_tgt_angle": bpy.props.FloatProperty(
        name="Target Azimuth",
        description="Placeholder when no light track target",
        default=0.0,
        subtype="ANGLE",
    ),
    "alec_lights_ui_dummy_lt_tgt_elevation": bpy.props.FloatProperty(
        name="Target Elevation",
        description="Placeholder when no light track target",
        default=0.0,
        subtype="ANGLE",
    ),
    "alec_lights_ui_dummy_area_size": bpy.props.FloatProperty(
        name="Size X",
        description="Placeholder when Area light is not active",
        default=1.0,
        min=0.0001,
        soft_max=100.0,
        unit="LENGTH",
    ),
    "alec_lights_ui_dummy_area_size_y": bpy.props.FloatProperty(
        name="Size Y",
        description="Placeholder when Area light is not active",
        default=1.0,
        min=0.0001,
        soft_max=100.0,
        unit="LENGTH",
    ),
}

_TRANSFORM_UI_DUMMY_PROPS = {
    "alec_transform_ui_dummy_location": bpy.props.FloatVectorProperty(
        name="Location",
        description="Placeholder when no active object",
        size=3,
        default=(0.0, 0.0, 0.0),
        subtype="TRANSLATION",
    ),
    "alec_transform_ui_dummy_rotation_euler": bpy.props.FloatVectorProperty(
        name="Rotation",
        description="Placeholder when no active object",
        size=3,
        default=(0.0, 0.0, 0.0),
        subtype="EULER",
    ),
    "alec_transform_ui_dummy_scale": bpy.props.FloatVectorProperty(
        name="Scale",
        description="Placeholder when no active object",
        size=3,
        default=(1.0, 1.0, 1.0),
    ),
    "alec_transform_ui_dummy_dimensions": bpy.props.FloatVectorProperty(
        name="Dimensions",
        description="Placeholder when no active object",
        size=3,
        default=(1.0, 1.0, 1.0),
        subtype="XYZ",
    ),
}

_CAMERA_UI_DUMMY_PROPS = {
    "alec_camera_ui_dummy_cam_distance": bpy.props.FloatProperty(
        name="Distance",
        description="Placeholder when scene camera has no Alec track target",
        default=5.0,
        min=1e-4,
        soft_max=5000.0,
        unit="LENGTH",
    ),
    "alec_camera_ui_dummy_cam_angle": bpy.props.FloatProperty(
        name="Azimuth",
        description="Placeholder when scene camera has no Alec track target",
        default=0.0,
        subtype="ANGLE",
    ),
    "alec_camera_ui_dummy_cam_elevation": bpy.props.FloatProperty(
        name="Elevation",
        description="Placeholder when scene camera has no Alec track target",
        default=0.0,
        subtype="ANGLE",
    ),
    "alec_camera_ui_dummy_tgt_distance": bpy.props.FloatProperty(
        name="Target Distance",
        description="Placeholder when scene camera has no Alec track target",
        default=3.0,
        min=0.01,
        soft_max=500.0,
        unit="LENGTH",
    ),
    "alec_camera_ui_dummy_tgt_angle": bpy.props.FloatProperty(
        name="Target Azimuth",
        description="Placeholder when scene camera has no Alec track target",
        default=0.0,
        subtype="ANGLE",
    ),
    "alec_camera_ui_dummy_tgt_elevation": bpy.props.FloatProperty(
        name="Target Elevation",
        description="Placeholder when scene camera has no Alec track target",
        default=0.0,
        subtype="ANGLE",
    ),
}


def _register_lights_ui_dummy_props() -> None:
    for name, prop in _LIGHTS_UI_DUMMY_PROPS.items():
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
        setattr(bpy.types.Scene, name, prop)


def _unregister_lights_ui_dummy_props() -> None:
    for name in _LIGHTS_UI_DUMMY_PROPS:
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)


def _register_camera_ui_dummy_props() -> None:
    for name, prop in _CAMERA_UI_DUMMY_PROPS.items():
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
        setattr(bpy.types.Scene, name, prop)


def _unregister_camera_ui_dummy_props() -> None:
    for name in _CAMERA_UI_DUMMY_PROPS:
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)


def _register_transform_ui_dummy_props() -> None:
    for name, prop in _TRANSFORM_UI_DUMMY_PROPS.items():
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
        setattr(bpy.types.Scene, name, prop)


def _unregister_transform_ui_dummy_props() -> None:
    for name in _TRANSFORM_UI_DUMMY_PROPS:
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)


def _draw_transform_panel_fields(layout, context):
    """Object transform block like Sidebar ▸ Item ▸ Transform (split + decorate)."""
    col = layout.column()
    col.use_property_split = True
    col.use_property_decorate = True

    scene = context.scene
    obj = context.active_object
    has_obj = obj is not None

    row = col.row(align=True)
    row.enabled = has_obj
    left = row.column(align=True)
    right = row.column(align=True)

    r = left.row(align=True)
    r.label(text="", icon="OBJECT_ORIGIN")
    if has_obj:
        r.prop(obj, "location", text="")
    else:
        r.prop(scene, "alec_transform_ui_dummy_location", text="")

    r = right.row(align=True)
    r.label(text="", icon="DRIVER_ROTATIONAL_DIFFERENCE")
    if has_obj:
        if obj.rotation_mode == "QUATERNION":
            r.prop(obj, "rotation_quaternion", text="")
        elif obj.rotation_mode == "AXIS_ANGLE":
            r.prop(obj, "rotation_axis_angle", text="")
        else:
            r.prop(obj, "rotation_euler", text="")
    else:
        r.prop(scene, "alec_transform_ui_dummy_rotation_euler", text="")

    row = col.row(align=True)
    row.enabled = has_obj
    left = row.column(align=True)
    right = row.column(align=True)

    r = left.row(align=True)
    r.label(text="", icon="FULLSCREEN_ENTER")
    if has_obj:
        r.prop(obj, "scale", text="")
    else:
        r.prop(scene, "alec_transform_ui_dummy_scale", text="")

    r = right.row(align=True)
    r.label(text="", icon="ARROW_LEFTRIGHT")
    if has_obj:
        r.prop(obj, "dimensions", text="")
    else:
        r.prop(scene, "alec_transform_ui_dummy_dimensions", text="")

    # cursor row
    layout.separator()
    layout.label(text="Cursor Transform", icon="PIVOT_CURSOR")
    col2 = layout.column(align=True)
    cursor = context.scene.cursor
    row = col2.row(align=True)
    row.label(text="", icon="OBJECT_ORIGIN")
    row.prop(cursor, "location", text="")
    row = col2.row(align=True)
    row.label(text="", icon="DRIVER_ROTATIONAL_DIFFERENCE")
    row.prop(cursor, "rotation_euler", text="")



def _draw_camera_tools(layout, context):
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
    space = context.space_data
    lock_on = (
        space is not None
        and getattr(space, "type", None) == "VIEW_3D"
        and bool(getattr(space, "lock_camera", False))
    )
    row.operator(
        "alec.toggle_lock_camera",
        text="",
        icon="LOCKED" if lock_on else "UNLOCKED",
        depress=lock_on,
    )
    row.operator(
        "alec.view_center_camera",
        text="",
        icon="SHADING_BBOX",
    )
    row.operator(
        "alec.select_scene_camera",
        text="",
        icon="OUTLINER_OB_CAMERA",
    )
    col.separator()
    row_tgt = col.row(align=True)
    row_tgt.operator("alec.camera_target_dist", text="Targ.Focus")
    row_tgt.operator("alec.camera_target_obj", text="Targ.Obj")
    row_tgt.operator("alec.camera_target_cursor", text="Targ.Curs")
    row_tgt.operator(
        "alec.camera_clear_track_target",
        text="",
        icon="UNLINKED",
    )
    row_tgt.operator(
        "alec.camera_select_track_target",
        text="",
        icon="RESTRICT_SELECT_OFF",
    )

    scene = context.scene
    cam_scene = getattr(scene, "camera", None)
    if cam_scene is not None and cam_scene.type != "CAMERA":
        cam_scene = None
    orbit_ok = (
        cam_scene is not None
        and camera_sphere_track_target(cam_scene, context) is not None
    )

    row_sp = col.row(align=True)
    row_sp.enabled = orbit_ok
    row_sp.operator(
        "alec.camera_rig_read_sphere",
        text="",
        icon="OUTLINER_OB_CAMERA",
    )
    if orbit_ok:
        row_sp.prop(cam_scene, "alec_cam_distance", text="C.Distance")
        row_sp.prop(cam_scene, "alec_cam_angle", text="C.Azimuth")
        row_sp.prop(cam_scene, "alec_cam_elevation", text="C.Elevation")
    else:
        row_sp.prop(scene, "alec_camera_ui_dummy_cam_distance", text="C.Distance")
        row_sp.prop(scene, "alec_camera_ui_dummy_cam_angle", text="C.Azimuth")
        row_sp.prop(scene, "alec_camera_ui_dummy_cam_elevation", text="C.Elevation")

    row_tgt_foot = col.row(align=True)
    row_tgt_foot.enabled = orbit_ok
    row_tgt_foot.operator(
        "alec.camera_target_read_foot_sphere",
        text="",
        icon="EMPTY_AXIS",
    )
    if orbit_ok:
        row_tgt_foot.prop(cam_scene, "alec_cam_tgt_distance", text="C.Targ.Distance")
        row_tgt_foot.prop(cam_scene, "alec_cam_tgt_angle", text="C.Targ.Azimuth")
        row_tgt_foot.prop(cam_scene, "alec_cam_tgt_elevation", text="C.Targ.Elevation")
    else:
        row_tgt_foot.prop(scene, "alec_camera_ui_dummy_tgt_distance", text="C.Targ.Distance")
        row_tgt_foot.prop(scene, "alec_camera_ui_dummy_tgt_angle", text="C.Targ.Azimuth")
        row_tgt_foot.prop(scene, "alec_camera_ui_dummy_tgt_elevation", text="C.Targ.Elevation")

    cam = focal_edit_camera(context)

    col.separator()
    focal_block = col.column(align=True)
    row_focal = focal_block.row(align=True)
    sub_ld = row_focal.row(align=True)
    sub_ld.enabled = cam is not None
    if cam is not None:
        sub_ld.prop(cam.data, "lens", text="Focal mm")
    dolly_on = bool(scene.alec_focal_dolly_compensate)
    tgt = context.active_object
    pivot_ok = cam is not None and tgt is not None and tgt is not cam
    dolly_wrap = sub_ld.row(align=True)
    dolly_wrap.alert = bool(cam is not None and dolly_on and not pivot_ok)
    dolly_wrap.prop(
        scene,
        "alec_focal_dolly_compensate",
        text="",
        icon="AUTO",
        toggle=True,
    )
    if cam is not None:
        crop_op = sub_ld.row(align=True)
        crop_op.enabled = view3d_camera_rv3d(context) is not None
        crop_op.operator(
            "alec.camera_crop_modal",
            text="Crop",
            icon="NONE",
        )

    col.separator()
    row_tl = col.row(align=True)
    row_tl.operator(
        "alec.cameras_bind_all_to_timeline",
        text="All Cams -> TL",
        icon="MARKER_HLT",
    )
    row_tl.operator(
        "alec.cameras_bind_selected_to_end",
        text="Sel. -> End",
        icon="MARKER",
    )
    sub_step = row_tl.row(align=True)
    sub_step.ui_units_x = 4
    sub_step.prop(scene, "alec_camera_marker_step", text="Step")


def _draw_lights_tools(layout, context):
    layout.label(text="Lights Tools", icon="LIGHT_DATA")
    col = layout.column(align=True)
    col.use_property_split = False
    obj = context.active_object
    light_data = (
        obj.data
        if obj is not None and obj.type == "LIGHT" and obj.data is not None
        else None
    )
    cur_type = light_data.type if light_data is not None else None
    scene = context.scene

    row_types = col.row(align=True)
    row_types.operator("alec.new_light_rig", text="New Light")
    for lt, icon in (
        ("POINT", "LIGHT_POINT"),
        ("SUN", "LIGHT_SUN"),
        ("SPOT", "LIGHT_SPOT"),
        ("AREA", "LIGHT_AREA"),
    ):
        op = row_types.operator(
            "alec.light_add",
            text="",
            icon=icon,
            depress=(cur_type == lt),
        )
        op.light_type = lt

    area_light_ok = light_data is not None and light_data.type == "AREA"
    cur_area_shape = light_data.shape if area_light_ok else None

    area_block = col.column(align=True)
    area_block.enabled = area_light_ok
    row_area = area_block.row(align=True)
    sz = row_area.row(align=True)
    sz.ui_units_x = 12
    if area_light_ok:
        _area_uses_second_dim = cur_area_shape in {"RECTANGLE", "ELLIPSE"}
        sz.prop(light_data, "size", text="")
        ry = sz.row(align=True)
        ry.enabled = _area_uses_second_dim
        ry.prop(light_data, "size_y", text="")
    else:
        sz.prop(scene, "alec_lights_ui_dummy_area_size", text="")
        sz.prop(scene, "alec_lights_ui_dummy_area_size_y", text="")
    for shape_id, icon in (
        ("SQUARE", "MESH_PLANE"),
        ("RECTANGLE", "MOD_EDGESPLIT"),
        ("DISK", "MESH_CIRCLE"),
        ("ELLIPSE", "MESH_CAPSULE"),
    ):
        op = row_area.operator(
            "alec.light_area_shape",
            text="",
            icon=icon,
            depress=(area_light_ok and cur_area_shape == shape_id),
        )
        op.shape = shape_id

    row_lt_tgt = col.row(align=True)
    row_lt_tgt.operator("alec.light_target_dist", text="Targ.Dist")
    row_lt_tgt.operator("alec.light_target_obj", text="Target.Obj")
    row_lt_tgt.operator("alec.light_target_cursor", text="Target.Curs")
    row_lt_tgt.operator(
        "alec.light_clear_track_target",
        text="",
        icon="UNLINKED",
    )
    row_lt_tgt.operator(
        "alec.light_select_track_target",
        text="",
        icon="RESTRICT_SELECT_OFF",
    )

    track_tgt_ok = (
        light_data is not None
        and alec_sphere_track_target(obj, context) is not None
    )

    row_rig = col.row(align=True)
    row_rig.enabled = light_data is not None
    row_rig.operator(
        "alec.light_rig_read_sphere",
        text="",
        icon="LIGHT_DATA",
    )
    if light_data is not None:
        row_rig.prop(obj, "alec_lt_distance", text="L.Distance")
        row_rig.prop(obj, "alec_lt_angle", text="L.Azimuth")
        row_rig.prop(obj, "alec_lt_elevation", text="L.Elevation")
    else:
        row_rig.prop(scene, "alec_lights_ui_dummy_lt_distance", text="L.Distance")
        row_rig.prop(scene, "alec_lights_ui_dummy_lt_angle", text="L.Azimuth")
        row_rig.prop(scene, "alec_lights_ui_dummy_lt_elevation", text="L.Elevation")

    row_tgt_rig = col.row(align=True)
    row_tgt_rig.enabled = track_tgt_ok
    row_tgt_rig.operator(
        "alec.light_target_read_foot_sphere",
        text="",
        icon="EMPTY_AXIS",
    )
    if track_tgt_ok:
        row_tgt_rig.prop(obj, "alec_lt_tgt_distance", text="L.Targ.Distance")
        row_tgt_rig.prop(obj, "alec_lt_tgt_angle", text="L.Targ.Azimuth")
        row_tgt_rig.prop(obj, "alec_lt_tgt_elevation", text="L.Targ.Elevation")
    else:
        row_tgt_rig.prop(scene, "alec_lights_ui_dummy_lt_tgt_distance", text="L.Targ.Distance")
        row_tgt_rig.prop(scene, "alec_lights_ui_dummy_lt_tgt_angle", text="L.Targ.Azimuth")
        row_tgt_rig.prop(scene, "alec_lights_ui_dummy_lt_tgt_elevation", text="L.Targ.Elevation")

    col.separator()
    eng_block = col.column(align=True)
    eng_block.enabled = light_data is not None
    row_e = eng_block.row(align=True)
    if light_data is not None:
        row_e.prop(light_data, "energy", text="Energy")
    else:
        row_e.prop(scene, "alec_lights_ui_dummy_energy", text="Energy")
    sub = row_e.row(align=True)
    sub.ui_units_x = 4
    if light_data is not None:
        sub.prop(light_data, "color", text="")
    else:
        sub.prop(scene, "alec_lights_ui_dummy_color", text="")


def _draw_2d_drafting(layout, _context):
    layout.label(text="2D Drafting", icon="GREASEPENCIL")
    col = layout.column(align=True)
    col.operator("alec.draw_mesh_edges", text="Draw Mesh Edges", icon="GREASEPENCIL")
    col.operator("alec.trim_extend_edges", text="Trim / Extend", icon="UV_EDGESEL")
    col.operator("alec.angle_rays", text="Angle Rays", icon="EMPTY_AXIS")
    col.operator("alec.fillet_edges", text="Fillet / Chamfer", icon="MOD_BEVEL")


class ALEC_PT_npanelMain(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Alec"
    bl_label = ""

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "VIEW_3D"

    def draw_header(self, context):
        layout = self.layout

        layout.label(text="Alec's Tools", icon="HEART")

    def draw(self, context):
        layout = self.layout
        _draw_transform_panel_fields(layout, context)
        _draw_camera_tools(layout, context)
        _draw_lights_tools(layout, context)
        _draw_2d_drafting(layout, context)


class ALEC_PT_alec_misc(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Alec"
    bl_label = "Misc"

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "VIEW_3D"

    def draw(self, _context):
        # Parent panel for utility sections.
        pass


class ALEC_PT_alec_misc_materials(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Alec"
    bl_label = "Materials"
    bl_parent_id = "ALEC_PT_alec_misc"

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "VIEW_3D"

    def draw(self, _context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator("alec.material_linker", text="Material Linker", icon="MATERIAL")
        col.operator("alec.make_mat_from_tex", text="Make Mat From Tex", icon="MATERIAL_DATA")
        col.operator("alec.open_material_preview_scene", text="Open Material Preview Scene", icon="FILE_BLEND")
        row = col.row(align=True)
        row.operator("alec.batch_materials_capture_previews", text="Batch + Previews", icon="RENDER_STILL")
        row.operator(
            "alec.material_preview_rename_tex_nodes",
            text="",
            icon="TEXTURE",
        )


def register():
    _register_transform_ui_dummy_props()
    _register_lights_ui_dummy_props()
    _register_camera_ui_dummy_props()
    bpy.utils.register_class(ALEC_PT_npanelMain)
    bpy.utils.register_class(ALEC_PT_alec_misc)
    bpy.utils.register_class(ALEC_PT_alec_misc_materials)


def unregister():
    bpy.utils.unregister_class(ALEC_PT_alec_misc_materials)
    bpy.utils.unregister_class(ALEC_PT_alec_misc)
    bpy.utils.unregister_class(ALEC_PT_npanelMain)
    _unregister_lights_ui_dummy_props()
    _unregister_camera_ui_dummy_props()
    _unregister_transform_ui_dummy_props()
