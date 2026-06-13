import bpy

from ..modules import align_tools


def _align_preset_center_axis_enum_updated(operator, context):
    """Redo UI Axis → position toggles only (do not wipe offsets/refs like full preset reset)."""
    operator.align_x = operator.align_y = operator.align_z = False
    ax = getattr(operator, "axis", "X")
    if ax == "X":
        operator.align_x = True
    elif ax == "Y":
        operator.align_y = True
    else:
        operator.align_z = True


class AlignBase:
    """Shared RNA, redo UI and execute() for Alec align operators."""

    align_x: bpy.props.BoolProperty(name="X", default=True, description="Align on X axis")  # type: ignore
    align_y: bpy.props.BoolProperty(name="Y", default=True, description="Align on Y axis")  # type: ignore
    align_z: bpy.props.BoolProperty(name="Z", default=True, description="Align on Z axis")  # type: ignore

    source_point: bpy.props.EnumProperty(
        name="Current Object",
        description="Point on the current object to align from",
        items=[
            ("MIN", "Minimum", "Align from the bounding box minimum"),
            ("CENTER", "Center (Geo)", "Align from the bounding box center"),
            ("PIVOT", "Origins", "Align from the object's origin"),
            ("MAX", "Maximum", "Align from the bounding box maximum"),
        ],
        default="PIVOT",
    )  # type: ignore

    target_point: bpy.props.EnumProperty(
        name="Target Object",
        description="Point on the target object to align to",
        items=[
            ("MIN", "Minimum", "Align to the bounding box minimum"),
            ("CENTER", "Center (Geo)", "Align to the bounding box center"),
            ("PIVOT", "Origins", "Align to the object's origin"),
            ("MAX", "Maximum", "Align to the bounding box maximum"),
        ],
        default="PIVOT",
    )  # type: ignore

    orient_x: bpy.props.BoolProperty(name="X", default=False, description="Match orientation on X axis")  # type: ignore
    orient_y: bpy.props.BoolProperty(name="Y", default=False, description="Match orientation on Y axis")  # type: ignore
    orient_z: bpy.props.BoolProperty(name="Z", default=False, description="Match orientation on Z axis")  # type: ignore

    scale_x: bpy.props.BoolProperty(name="X", default=False, description="Match scale on X axis")  # type: ignore
    scale_y: bpy.props.BoolProperty(name="Y", default=False, description="Match scale on Y axis")  # type: ignore
    scale_z: bpy.props.BoolProperty(name="Z", default=False, description="Match scale on Z axis")  # type: ignore

    use_active_orient: bpy.props.BoolProperty(
        name="Local (Active)",
        default=False,
        description="Align along the active object's local axes instead of world axes",
    )  # type: ignore

    offset_x: bpy.props.FloatProperty(name="Offset X", default=0.0, unit="LENGTH")  # type: ignore
    offset_y: bpy.props.FloatProperty(name="Offset Y", default=0.0, unit="LENGTH")  # type: ignore
    offset_z: bpy.props.FloatProperty(name="Offset Z", default=0.0, unit="LENGTH")  # type: ignore

    orient_offset_x: bpy.props.FloatProperty(
        name="Rot offset X", default=0.0, subtype="ANGLE"
    )  # type: ignore
    orient_offset_y: bpy.props.FloatProperty(
        name="Rot offset Y", default=0.0, subtype="ANGLE"
    )  # type: ignore
    orient_offset_z: bpy.props.FloatProperty(
        name="Rot offset Z", default=0.0, subtype="ANGLE"
    )  # type: ignore

    scale_offset_x: bpy.props.FloatProperty(name="Scale offset X", default=0.0)  # type: ignore
    scale_offset_y: bpy.props.FloatProperty(name="Scale offset Y", default=0.0)  # type: ignore
    scale_offset_z: bpy.props.FloatProperty(name="Scale offset Z", default=0.0)  # type: ignore

    reset_requested: bpy.props.BoolProperty(
        name="Reset defaults",
        description=(
            "Reset Align: turn off position/rotation/scale X/Y/Z, Current/Target = Origins/Centers "
            "(per preset), clear offsets and Local (Active)"
        ),
        default=False,
    )  # type: ignore

    apply_requested: bpy.props.BoolProperty(
        name="Apply baseline",
        description=(
            "Use current object transforms as the new baseline for interactive align "
            "(same as reopening Align on this pose)"
        ),
        default=False,
    )  # type: ignore

    _initial_state = {}
    _is_modal = False

    _ICON_COL_W = 0.12  # Same split for icon row + empty gutter on offset row (alignment).
    _SEP_MAIN = 2.0
    _SEP_BLOCK = 0.55

    _AX_POS = ("align_x", "align_y", "align_z")
    _OFF_POS = (("align_x", "offset_x"), ("align_y", "offset_y"), ("align_z", "offset_z"))
    _AX_ROT = ("orient_x", "orient_y", "orient_z")
    _OFF_ROT = (("orient_x", "orient_offset_x"), ("orient_y", "orient_offset_y"), ("orient_z", "orient_offset_z"))
    _AX_SCL = ("scale_x", "scale_y", "scale_z")
    _OFF_SCL = (
        ("scale_x", "scale_offset_x"),
        ("scale_y", "scale_offset_y"),
        ("scale_z", "scale_offset_z"),
    )

    def _draw_axis_block(self, layout, section_icon: str, toggles: tuple[str, str, str], off_pairs):
        spl = layout.split(factor=self._ICON_COL_W, align=True)
        spl.label(text="", icon=section_icon)
        row = spl.row(align=True)
        for key in toggles:
            row.prop(self, key, toggle=True)

        spl = layout.split(factor=self._ICON_COL_W, align=True)
        spl.label(text="")
        row = spl.row(align=True)
        for tk, ok in off_pairs:
            col = row.column(align=True)
            col.prop(self, ok, text="")
            col.enabled = bool(getattr(self, tk))

    def _capture_selection_snapshot(self, context):
        self._initial_state = {}
        target = context.active_object
        for obj in context.selected_objects:
            if obj != target:
                self._initial_state[obj.name] = {
                    "location": obj.location.copy(),
                    "rotation_euler": obj.rotation_euler.copy(),
                    "scale": obj.scale.copy(),
                }

    def _default_ref_point_for_reset(self) -> str:
        if getattr(self, "bl_idname", "") == "alec.align_preset_centers":
            return "CENTER"
        return "PIVOT"

    def _reset_align_defaults(
        self,
        ref_point: str,
        *,
        match_position: bool = True,
        match_rotation: bool = False,
        match_scale: bool = False,
    ):
        self.align_x = self.align_y = self.align_z = match_position
        self.source_point = self.target_point = ref_point
        self.orient_x = self.orient_y = self.orient_z = match_rotation
        self.scale_x = self.scale_y = self.scale_z = match_scale
        self.use_active_orient = False
        self.offset_x = self.offset_y = self.offset_z = 0.0
        self.orient_offset_x = self.orient_offset_y = self.orient_offset_z = 0.0
        self.scale_offset_x = self.scale_offset_y = self.scale_offset_z = 0.0
        self.reset_requested = False

    def _invoke_align_preset(self, context, event, ref_point: str):
        want_rot = bool(getattr(event, "alt", False))
        self._reset_align_defaults(
            ref_point, match_position=True, match_rotation=want_rot
        )
        self._is_modal = True
        self._capture_selection_snapshot(context)
        self.execute(context)
        return {"FINISHED"}

    def _invoke_align_preset_flags(
        self,
        context,
        ref_point: str,
        *,
        match_position: bool,
        match_rotation: bool,
        match_scale: bool,
    ):
        self._reset_align_defaults(
            ref_point,
            match_position=match_position,
            match_rotation=match_rotation,
            match_scale=match_scale,
        )
        self._is_modal = True
        self._capture_selection_snapshot(context)
        self.execute(context)
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout

        top = layout.box()
        row_top = top.row(align=True)
        row_top.prop(
            self, "reset_requested", toggle=True, icon="FILE_REFRESH", text="Reset"
        )
        row_top.prop(
            self, "apply_requested", toggle=True, icon="CHECKMARK", text="Apply"
        )
        top.prop(self, "use_active_orient")

        layout.separator(factor=self._SEP_MAIN)

        self._draw_axis_block(layout, "ORIENTATION_GLOBAL", self._AX_POS, self._OFF_POS)
        layout.separator(factor=self._SEP_BLOCK)
        self._draw_axis_block(layout, "DRIVER_ROTATIONAL_DIFFERENCE", self._AX_ROT, self._OFF_ROT)
        layout.separator(factor=self._SEP_BLOCK)
        self._draw_axis_block(layout, "CON_SIZELIKE", self._AX_SCL, self._OFF_SCL)

        layout.separator(factor=self._SEP_MAIN)

        refs = layout.box()
        row = refs.row(align=True)
        a = row.column(align=True)
        a.label(text="Current Object:")
        a.prop(self, "source_point", expand=True)
        b = row.column(align=True)
        b.label(text="Target Object:")
        b.prop(self, "target_point", expand=True)

    def check(self, context):
        if self.reset_requested:
            self._reset_align_defaults(
                self._default_ref_point_for_reset(),
                match_position=False,
                match_rotation=False,
                match_scale=False,
            )
        snap_baseline = self.apply_requested
        self.execute(context)
        if snap_baseline:
            self._capture_selection_snapshot(context)
            self.apply_requested = False
        return True

    def _restore_state(self):
        if getattr(self, "_is_modal", False) and self._initial_state:
            for name, state in self._initial_state.items():
                obj = bpy.data.objects.get(name)
                if obj:
                    obj.location = state["location"]
                    obj.rotation_euler = state["rotation_euler"]
                    obj.scale = state["scale"]

    def cancel(self, context):
        self._restore_state()

    def execute(self, context):
        self._restore_state()
        target = context.active_object
        sources = [o for o in context.selected_objects if o != target]
        for source in sources:
            align_tools.align_orientation(
                source,
                target,
                x=self.orient_x,
                y=self.orient_y,
                z=self.orient_z,
                offset_x=self.orient_offset_x,
                offset_y=self.orient_offset_y,
                offset_z=self.orient_offset_z,
            )
            align_tools.match_scale(
                source,
                target,
                x=self.scale_x,
                y=self.scale_y,
                z=self.scale_z,
                offset_x=self.scale_offset_x,
                offset_y=self.scale_offset_y,
                offset_z=self.scale_offset_z,
            )
            align_tools.align_position(
                source,
                target,
                x=self.align_x,
                y=self.align_y,
                z=self.align_z,
                source_point=self.source_point,
                target_point=self.target_point,
                use_active_orient=self.use_active_orient,
                offset_x=self.offset_x,
                offset_y=self.offset_y,
                offset_z=self.offset_z,
            )
        return {"FINISHED"}


class ALEC_OT_align_dialog(AlignBase, bpy.types.Operator):
    """Align via redo panel (no centered modal)."""

    bl_idname = "alec.align_dialog"
    bl_label = "Align"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        # Fresh defaults each open: Blender keeps last op props for redo otherwise.
        self._reset_align_defaults(
            self._default_ref_point_for_reset(),
            match_position=True,
            match_rotation=False,
            match_scale=False,
        )
        self._is_modal = True
        self._capture_selection_snapshot(context)
        self.execute(context)
        return {"FINISHED"}


class ALEC_OT_align_preset_centers(AlignBase, bpy.types.Operator):
    """Preset: bbox centers; Alt also matches rotation."""

    bl_idname = "alec.align_preset_centers"
    bl_label = "Align (Centers)"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return self._invoke_align_preset(context, event, "CENTER")


class ALEC_OT_align_preset_origins(AlignBase, bpy.types.Operator):
    """Preset: origins; Alt also matches rotation."""

    bl_idname = "alec.align_preset_origins"
    bl_label = "Align (Origins)"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return self._invoke_align_preset(context, event, "PIVOT")


class ALEC_OT_align_preset_rotate(AlignBase, bpy.types.Operator):
    """Preset: match rotation to active (origins ref, no position move)."""

    bl_idname = "alec.align_preset_rotate"
    bl_label = "Align (Rotation)"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return self._invoke_align_preset_flags(
            context,
            "PIVOT",
            match_position=False,
            match_rotation=True,
            match_scale=False,
        )


class ALEC_OT_align_preset_scale(AlignBase, bpy.types.Operator):
    """Preset: match scale to active (origins ref, no position move)."""

    bl_idname = "alec.align_preset_scale"
    bl_label = "Align (Scale)"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return self._invoke_align_preset_flags(
            context,
            "PIVOT",
            match_position=False,
            match_rotation=False,
            match_scale=True,
        )


class ALEC_OT_align_preset_center_axis(AlignBase, bpy.types.Operator):
    """Preset: bbox centers to active bbox along one world axis, or perpendicular plane if Alt-held."""

    bl_idname = "alec.align_preset_center_axis"
    bl_label = "Align Centers (Axis)"
    bl_description = (
        "Match bbox centers along one world axis (X / Y / Z). "
        "Hold Alt when choosing a pie button to use the perpendicular plane (e.g. Alt+X → Y+Z only)."
    )
    bl_options = {"REGISTER", "UNDO"}

    axis: bpy.props.EnumProperty(
        name="Axis",
        items=[
            ("X", "X", "World X (single axis); Alt-held from pie: perpendicular plane → Y + Z"),
            ("Y", "Y", "World Y (single axis); Alt-held from pie: perpendicular plane → X + Z"),
            ("Z", "Z", "World Z (single axis); Alt-held from pie: perpendicular plane → X + Y"),
        ],
        default="X",
        update=_align_preset_center_axis_enum_updated,
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            return False
        active = context.active_object
        if active is None or active not in context.selected_objects:
            return False
        return len(context.selected_objects) >= 2

    def _apply_center_world_axis_preset(self):
        self._reset_align_defaults("CENTER", match_position=True, match_rotation=False)
        self.align_x = self.align_y = self.align_z = False
        ax = getattr(self, "axis", "X")
        if ax == "X":
            self.align_x = True
        elif ax == "Y":
            self.align_y = True
        else:
            self.align_z = True

    def _apply_center_world_axis_plane_preset(self, ax: str):
        """Lock to active on the plane perpendicular to world axis *ax* (two position axes only)."""
        self._reset_align_defaults("CENTER", match_position=True, match_rotation=False)
        self.align_x = self.align_y = self.align_z = False
        if ax == "X":
            self.align_y = self.align_z = True
        elif ax == "Y":
            self.align_x = self.align_z = True
        else:
            self.align_x = self.align_y = True

    def invoke(self, context, event):
        if getattr(event, "alt", False):
            self._apply_center_world_axis_plane_preset(getattr(self, "axis", "X"))
        else:
            self._apply_center_world_axis_preset()
        self._is_modal = True
        self._capture_selection_snapshot(context)
        self.execute(context)
        return {"FINISHED"}


classes = (
    ALEC_OT_align_dialog,
    ALEC_OT_align_preset_centers,
    ALEC_OT_align_preset_origins,
    ALEC_OT_align_preset_rotate,
    ALEC_OT_align_preset_scale,
    ALEC_OT_align_preset_center_axis,
)
