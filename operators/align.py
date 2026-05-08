import bpy
from mathutils import Vector

from ..modules import align_tools
from ..modules import distribute_gaps_overlay
from ..modules.utils import (
    world_aabb_evaluated_corner_vectors,
    world_obb_evaluated_corners_wrt_active,
)


def _axis_direction_from_enum(context, axis_mode):
    """Unit vector for WORLD_* / LOCAL_* (local needs active object)."""
    if axis_mode == "WORLD_X":
        return Vector((1.0, 0.0, 0.0))
    if axis_mode == "WORLD_Y":
        return Vector((0.0, 1.0, 0.0))
    if axis_mode == "WORLD_Z":
        return Vector((0.0, 0.0, 1.0))
    active = context.active_object
    if active is None:
        return None
    rot = active.matrix_world.to_3x3()
    if axis_mode == "LOCAL_X":
        return rot.col[0].normalized()
    if axis_mode == "LOCAL_Y":
        return rot.col[1].normalized()
    if axis_mode == "LOCAL_Z":
        return rot.col[2].normalized()
    return Vector((1.0, 0.0, 0.0))


def _distribute_spacing_gap_user_edit(self, context):
    """Mark spacing/gap as user-owned until mode, axis, or reference changes."""
    if getattr(self, "_autofill_programmatic", False):
        return
    self.manual_field_lock = True


def _distribute_reconfig_clear_manual_lock(self, context):
    """Changing core distribute inputs allows auto-sync to refill the field again."""
    self.manual_field_lock = False


def _distribute_auto_sync_updated(self, context):
    if self.auto_sync_field:
        self.manual_field_lock = False


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
            "Reset Align: position X/Y/Z on, Current/Target = Origins, "
            "clear rotation/scale and all offsets"
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

    def draw(self, context):
        layout = self.layout

        top = layout.box()
        top.row(align=True).prop(
            self, "reset_requested", toggle=True, icon="FILE_REFRESH", text="Reset"
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
            self.align_x = self.align_y = self.align_z = True
            self.source_point = self.target_point = "PIVOT"
            self.orient_x = self.orient_y = self.orient_z = False
            self.scale_x = self.scale_y = self.scale_z = False
            self.use_active_orient = False
            self.offset_x = self.offset_y = self.offset_z = 0.0
            self.orient_offset_x = self.orient_offset_y = self.orient_offset_z = 0.0
            self.scale_offset_x = self.scale_offset_y = self.scale_offset_z = 0.0
            self.reset_requested = False
        self.execute(context)
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
        self._is_modal = True
        self._capture_selection_snapshot(context)
        self.source_point = self.target_point = "CENTER"
        want_rot = bool(getattr(event, "alt", False))
        self.orient_x = self.orient_y = self.orient_z = want_rot
        self.execute(context)
        return {"FINISHED"}


class ALEC_OT_align_preset_origins(AlignBase, bpy.types.Operator):
    """Preset: origins; Alt also matches rotation."""

    bl_idname = "alec.align_preset_origins"
    bl_label = "Align (Origins)"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        self._is_modal = True
        self._capture_selection_snapshot(context)
        self.source_point = self.target_point = "PIVOT"
        want_rot = bool(getattr(event, "alt", False))
        self.orient_x = self.orient_y = self.orient_z = want_rot
        self.execute(context)
        return {"FINISHED"}


class ALEC_OT_quick_center(AlignBase, bpy.types.Operator):
    bl_idname = "alec.quick_center"
    bl_label = "Quick Center"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        self.source_point = self.target_point = "CENTER"
        return self.execute(context)


class ALEC_OT_quick_center_rot(AlignBase, bpy.types.Operator):
    bl_idname = "alec.quick_center_rot"
    bl_label = "Quick Center (Rot)"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        self.source_point = self.target_point = "CENTER"
        self.orient_x = self.orient_y = self.orient_z = True
        return self.execute(context)


class ALEC_OT_quick_pivot_rot(AlignBase, bpy.types.Operator):
    bl_idname = "alec.quick_pivot_rot"
    bl_label = "Quick Pivot (Rot)"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        self.source_point = self.target_point = "PIVOT"
        self.orient_x = self.orient_y = self.orient_z = True
        return self.execute(context)


class ALEC_OT_distribute_objects_dialog(bpy.types.Operator):
    """Distribute selected objects along an axis (redo panel, like Align dialog)."""

    bl_idname = "alec.distribute_objects_dialog"
    bl_label = "Distribute Objects"
    bl_description = (
        "Positions: even spacing between reference projections along one axis between extremes; "
        "Gaps: equal gaps between bbox slabs. Optional: plane-align (perpendicular) to active."
    )
    bl_options = {"REGISTER", "UNDO"}

    # draw()/check/execute set this for overlays.
    _redo_panel_self = None  # type: ignore[assignment]

    mode: bpy.props.EnumProperty(
        name="Mode",
        items=[
            ("POSITIONS", "Positions", "Even spacing between reference points along the axis"),
            ("GAPS", "Gaps", "Equal space between bounding boxes along the axis"),
        ],
        default="POSITIONS",
        update=_distribute_reconfig_clear_manual_lock,
    )  # type: ignore

    axis: bpy.props.EnumProperty(
        name="Axis",
        items=[
            ("WORLD_X", "World X", ""),
            ("WORLD_Y", "World Y", ""),
            ("WORLD_Z", "World Z", ""),
            ("LOCAL_X", "Local X", ""),
            ("LOCAL_Y", "Local Y", ""),
            ("LOCAL_Z", "Local Z", ""),
        ],
        default="WORLD_X",
        update=_distribute_reconfig_clear_manual_lock,
    )  # type: ignore

    reference_point: bpy.props.EnumProperty(
        name="Reference",
        description="Reference point on each object (Positions mode only)",
        items=[
            ("MIN", "Minimum", "Bounding box minimum along the spacing axis"),
            ("CENTER", "Center (Geo)", "Bounding box center (evaluated geometry, world)"),
            ("PIVOT", "Origins", "Object origin position"),
            ("MAX", "Maximum", "Bounding box maximum along the spacing axis"),
        ],
        default="PIVOT",
        update=_distribute_reconfig_clear_manual_lock,
    )  # type: ignore

    positions_spacing: bpy.props.FloatProperty(
        name="Spacing",
        description=(
            "Step between reference points after sort along the axis. "
            "Filled from current layout when the operator starts; use Auto to recompute."
        ),
        default=0.0,
        min=0.0,
        subtype="DISTANCE",
        update=_distribute_spacing_gap_user_edit,
    )  # type: ignore

    gaps_spacing: bpy.props.FloatProperty(
        name="Gap",
        description=(
            "Clear distance between bbox extents on the axis (negative = overlap). "
            "If the active object is in the selection, it stays fixed on this axis and "
            "others pack to either side at this gap. If not, stacking starts from the "
            "minimum projection side. "
            "Values cannot go below negative min slab width on this axis (overlap cap)."
        ),
        default=0.0,
        subtype="DISTANCE",
        update=_distribute_spacing_gap_user_edit,
    )  # type: ignore

    manual_field_lock: bpy.props.BoolProperty(
        default=False,
        options={"HIDDEN"},
        description="Internal: spacing/gap was edited manually; cleared when mode/axis/reference or Auto sync toggles on",
    )  # type: ignore

    auto_sync_field: bpy.props.BoolProperty(
        name="Auto",
        description=(
            "When on: on each apply, recompute spacing or gap from the current layout and "
            "put it in the field—except after you edit the field manually, until you change "
            "mode, axis, or reference (spacing), or turn this option off and on again."
        ),
        default=False,
        update=_distribute_auto_sync_updated,
    )  # type: ignore

    align_plane_toggle_a: bpy.props.BoolProperty(
        name="Plane align A",
        description=(
            "Match this axis of each non-active object to the active object "
            "(label updates with Axis; WORLD = world XYZ, LOCAL = active local XYZ)"
        ),
        default=False,
    )  # type: ignore

    align_plane_toggle_b: bpy.props.BoolProperty(
        name="Plane align B",
        description=(
            "Match second perpendicular axis toward the active object (see companion toggle)."
        ),
        default=False,
    )  # type: ignore

    plane_align_reference: bpy.props.EnumProperty(
        name="Plane reference",
        description=(
            "For Align to active: which point on each object to match to the active "
            "(same semantics as Align position; only enabled axes receive the delta)"
        ),
        items=[
            ("MIN", "Minimum", "Bounding box minimum (world)"),
            ("CENTER", "Center (Geo)", "Bounding box center (evaluated geometry, world)"),
            ("PIVOT", "Origins", "Object origin"),
            ("MAX", "Maximum", "Bounding box maximum (world)"),
        ],
        default="PIVOT",
    )  # type: ignore

    interpolate_rotation: bpy.props.BoolProperty(
        name="Rotation blend min → active → max",
        description=(
            "Before spacing: full world orientations (quaternion Slerp, all 3 rotation DOF). "
            "Only the spacing axis sets *order* along the row (min → active → max); "
            "it does not limit rotation to one axis. Then spacing/gaps use bbox after that"
        ),
        default=False,
    )  # type: ignore

    reset_requested: bpy.props.BoolProperty(
        name="Reset defaults",
        description=(
            "Reset Distribute: Positions mode, World X, spacing ref + plane ref = Origins, "
            "plane toggles off, rotation blend off; spacing/gap refilled from geometry when possible"
        ),
        default=False,
    )  # type: ignore

    _initial_state = {}
    _is_modal = False

    _SEP_MAIN = 2.0
    _SEP_BLOCK = 0.55

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and len(context.selected_objects) >= 2

    def _capture_selection_snapshot(self, context):
        self._initial_state = {}
        for obj in context.selected_objects:
            self._initial_state[obj.name] = {
                "location": obj.location.copy(),
                "rotation_euler": obj.rotation_euler.copy(),
                "scale": obj.scale.copy(),
            }

    def _restore_state(self):
        if getattr(self, "_is_modal", False) and self._initial_state:
            for name, state in self._initial_state.items():
                obj = bpy.data.objects.get(name)
                if obj:
                    obj.location = state["location"]
                    obj.rotation_euler = state["rotation_euler"]
                    obj.scale = state["scale"]

    def cancel(self, context):
        distribute_gaps_overlay.clear_preview()
        self._restore_state()

    def _store_initial_spacing_hints(self, context):
        """Snapshot auto spacing/gap numbers from geometry when the operator begins (Redo reference)."""
        self._initial_positions_spacing = None
        self._initial_gaps_spacing = None
        objs = list(context.selected_objects)
        ad = _axis_direction_from_enum(context, self.axis)
        if ad is None or len(objs) < 2:
            return
        context.view_layer.update()
        self._initial_positions_spacing = align_tools.positions_spacing_auto_value(
            objs, ad, self.reference_point
        )
        self._initial_gaps_spacing = align_tools.gaps_spacing_auto_value(objs, ad)

        self._autofill_programmatic = True
        try:
            if self._initial_positions_spacing is not None:
                self.positions_spacing = self._initial_positions_spacing
            if self._initial_gaps_spacing is not None:
                self.gaps_spacing = self._initial_gaps_spacing
        finally:
            self._autofill_programmatic = False

    def _gap_preview_corner_boxes(self, context, objs: list) -> list[list[Vector]]:
        if self.axis.startswith("LOCAL_"):
            act = context.active_object
            if act is not None:
                return [world_obb_evaluated_corners_wrt_active(act, o) for o in objs]
        return [world_aabb_evaluated_corner_vectors(o) for o in objs]

    def draw(self, context):
        # Do not drive viewport overlay from draw(): check()→execute() already updates geometry
        # and set_preview_corner_boxes. Rebuilding overlay + view_layer.update on every UI paint
        # tags full window redraw and makes the N-panel / Adjust Last Operation flicker.
        ALEC_OT_distribute_objects_dialog._redo_panel_self = self

        layout = self.layout

        top = layout.box()
        top.row(align=True).prop(
            self, "reset_requested", toggle=True, icon="FILE_REFRESH", text="Reset"
        )

        layout.separator(factor=self._SEP_MAIN)

        mode_row = layout.row(align=True)
        mode_row.prop(self, "mode", expand=True)
        layout.separator(factor=self._SEP_BLOCK)

        axis_col = layout.column(align=False)
        axis_col.label(text="Spacing axis")
        row_w = axis_col.row(align=True)
        for axis_val in ("WORLD_X", "WORLD_Y", "WORLD_Z"):
            row_w.prop_enum(self, "axis", axis_val)
        row_l = axis_col.row(align=True)
        for axis_val in ("LOCAL_X", "LOCAL_Y", "LOCAL_Z"):
            row_l.prop_enum(self, "axis", axis_val)

        layout.separator(factor=self._SEP_BLOCK)
        if self.mode == "POSITIONS":
            sp_row = layout.row(align=True)
            sp_row.prop(
                self,
                "auto_sync_field",
                text="Auto",
                toggle=True,
                icon="LINKED",
            )
            sp_row.prop(self, "positions_spacing")

        if self.mode == "GAPS":
            g_row = layout.row(align=True)
            g_row.prop(
                self,
                "auto_sync_field",
                text="Auto",
                toggle=True,
                icon="LINKED",
            )
            g_row.prop(self, "gaps_spacing")

        layout.separator(factor=self._SEP_BLOCK)
        ref_sp = layout.box()
        ref_sp.label(text="Reference (spacing along axis)")
        ref_in = ref_sp.column(align=True)
        ref_in.enabled = self.mode == "POSITIONS"
        ref_in.prop(self, "reference_point", expand=True)

        layout.separator(factor=self._SEP_MAIN)
        lbl_a, lbl_b = align_tools.distribute_perpendicular_toggle_labels(self.axis)
        plane_col = layout.column(align=False)
        plane_col.label(text=f"Align to active ({lbl_a} / {lbl_b})")
        prow = plane_col.row(align=True)
        prow.prop(self, "align_plane_toggle_a", toggle=True, text=lbl_a)
        prow.prop(self, "align_plane_toggle_b", toggle=True, text=lbl_b)

        layout.separator(factor=self._SEP_BLOCK)
        pref = layout.box()
        pref.label(text="Reference (align to active)")
        pref.prop(self, "plane_align_reference", expand=True)

        layout.separator(factor=self._SEP_BLOCK)
        layout.prop(self, "interpolate_rotation", toggle=True)

    def invoke(self, context, event):
        ALEC_OT_distribute_objects_dialog._redo_panel_self = self
        self._is_modal = True
        self._capture_selection_snapshot(context)
        self._store_initial_spacing_hints(context)
        return self.execute(context)

    def check(self, context):
        ALEC_OT_distribute_objects_dialog._redo_panel_self = self
        if self.reset_requested:
            self.mode = "POSITIONS"
            self.axis = "WORLD_X"
            self.reference_point = "PIVOT"
            self.positions_spacing = 0.0
            self.gaps_spacing = 0.0
            self.align_plane_toggle_a = False
            self.align_plane_toggle_b = False
            self.plane_align_reference = "PIVOT"
            self.auto_sync_field = False
            self.manual_field_lock = False
            self.interpolate_rotation = False
            self.reset_requested = False
            self._store_initial_spacing_hints(context)
        self.execute(context)
        return True

    def execute(self, context):
        ALEC_OT_distribute_objects_dialog._redo_panel_self = self
        self._restore_state()

        objects = list(context.selected_objects)
        active = context.active_object

        axis_dir = _axis_direction_from_enum(context, self.axis)
        if axis_dir is None:
            distribute_gaps_overlay.clear_preview()
            self.report({"WARNING"}, "Need an active object for local axes")
            return {"FINISHED"}

        context.view_layer.update()

        # Rotation before spacing so bbox-based gap / positions match final oriented geometry.
        if self.interpolate_rotation and len(objects) >= 2:
            align_tools.interpolate_rotations_active_to_farthest_slerp(
                objects, axis_dir, self.mode, self.reference_point, active
            )
            context.view_layer.update()

        if self.auto_sync_field and len(objects) >= 2 and not self.manual_field_lock:
            self._autofill_programmatic = True
            try:
                if self.mode == "POSITIONS":
                    ps = align_tools.positions_spacing_auto_value(
                        objects, axis_dir, self.reference_point
                    )
                    if ps is not None:
                        self.positions_spacing = ps
                else:
                    gs = align_tools.gaps_spacing_auto_value(objects, axis_dir)
                    if gs is not None:
                        self.gaps_spacing = gs
            finally:
                self._autofill_programmatic = False

        if self.mode == "GAPS" and len(objects) >= 2:
            bound = align_tools.gaps_spacing_lower_bound_for_overlap(objects, axis_dir)
            if bound is not None and self.gaps_spacing < bound:
                self.gaps_spacing = bound

        plane_precheck = align_tools.distribute_plane_align_xyz_orient(
            self.axis, self.align_plane_toggle_a, self.align_plane_toggle_b
        )
        if plane_precheck is not None:
            if active is None or active not in objects:
                distribute_gaps_overlay.clear_preview()
                self.report(
                    {"WARNING"},
                    "Align plane toggles require an active object in the selection",
                )
                return {"FINISHED"}

        distribute_gaps_overlay.notify_distribute_execute_tick()

        ok = True
        msg = ""

        if self.mode == "POSITIONS":
            distribute_gaps_overlay.mark_alive()
            if active is not None and active in objects:
                ok, msg = align_tools.distribute_objects_positions_fixed_step_anchor_active(
                    objects,
                    axis_dir,
                    self.reference_point,
                    self.positions_spacing,
                    active,
                )
            else:
                ok, msg = align_tools.distribute_objects_positions_fixed_step(
                    objects,
                    axis_dir,
                    self.reference_point,
                    self.positions_spacing,
                )
            if ok:
                context.view_layer.update()
        else:
            distribute_gaps_overlay.mark_alive()
            # Match Positions: anchor on active when in selection — otherwise left-edge stack
            # drifts from the gizmo object and extreme negative gaps look “reversed”.
            if active is not None and active in objects:
                ok, msg = align_tools.distribute_objects_gaps_fixed_gap_anchor_active(
                    objects, axis_dir, self.gaps_spacing, active
                )
            else:
                ok, msg = align_tools.distribute_objects_gaps_fixed_gap(
                    objects, axis_dir, self.gaps_spacing
                )
            if ok:
                context.view_layer.update()

        if ok:
            context.view_layer.update()

            plane_ref_src = self.plane_align_reference
            plane_ref_tgt = self.plane_align_reference
            align_tools.distribute_plane_align_to_active(
                objects,
                self.axis,
                active,
                self.align_plane_toggle_a,
                self.align_plane_toggle_b,
                plane_ref_src,
                plane_ref_tgt,
            )

            context.view_layer.update()
            if self.mode == "POSITIONS":
                distribute_gaps_overlay.set_preview_corner_boxes(
                    self._gap_preview_corner_boxes(context, objects),
                    context=context,
                    positions_objects=objects,
                    positions_axis_dir=axis_dir,
                    positions_ref_point=self.reference_point,
                )
            else:
                distribute_gaps_overlay.set_preview_corner_boxes(
                    self._gap_preview_corner_boxes(context, objects),
                    context=context,
                    gap_objects=objects,
                    gap_axis_dir=axis_dir,
                )

        if not ok:
            distribute_gaps_overlay.clear_preview()
            self.report({"WARNING"}, msg)
        # Always FINISHED: CANCELLED drops Adjust Last Operation / Redo UX for this op
        return {"FINISHED"}


classes = [
    ALEC_OT_align_dialog,
    ALEC_OT_align_preset_centers,
    ALEC_OT_align_preset_origins,
    ALEC_OT_quick_center,
    ALEC_OT_quick_center_rot,
    ALEC_OT_quick_pivot_rot,
    ALEC_OT_distribute_objects_dialog,
]
