import json
import bpy
from ..modules import bbox_tools


class ALEC_OT_bbox_dialog(bpy.types.Operator):
    """Create bbox helper cubes from the redo panel (like Align / Distribute)."""

    bl_idname = "alec.bbox_dialog"
    bl_label = "Bounding Box"
    bl_options = {"REGISTER", "UNDO"}

    _SEP_MAIN = 2.0
    _SEP_BLOCK = 0.55

    bbox_space: bpy.props.EnumProperty(
        name="Axes",
        description=(
            "World: XYZ axis-aligned bounds. Combined selection + Local: all geometry in active's local space; "
            "Each object + Local: one cage per mesh, aligned to that object's axes"
        ),
        items=[
            ("LOCAL", "Local", "Local axes—depends on Combined vs Each object toggle"),
            ("WORLD", "World", "World XYZ bounds"),
        ],
        default="LOCAL",
    )  # type: ignore

    bbox_each_object: bpy.props.BoolProperty(
        name="Each object",
        description="Place one cage on every mesh in the selection instead of merging into a single cage",
        default=False,
    )  # type: ignore

    helper_setup: bpy.props.BoolProperty(
        name="Wire & helpers collection",
        description=(
            "On: green wireframe, move to the BBox helpers collection, viewport wire uses Object color. "
            "Off: plain mesh cube and keep it in the same collections as the active (same as Shift on the direct BBox operators)"
        ),
        default=True,
    )  # type: ignore

    bbox_padding: bpy.props.FloatProperty(
        name="Offset",
        description="Grow the bbox cage on each side along its axes (+/- also shrinks tightly toward center)",
        default=0.0,
        subtype="DISTANCE",
        unit="LENGTH",
    )  # type: ignore

    bbox_padding_second_object: bpy.props.BoolProperty(
        name="Separate padded cage",
        description=(
            "Off: one bbox helper with padding baked in. On: tight bbox plus a second helper with padding applied"
        ),
        default=False,
    )  # type: ignore

    reset_requested: bpy.props.BoolProperty(
        name="Reset defaults",
        description="Combined mode defaults; bbox offset 0; padding/copy off; Each object off",
        default=False,
    )  # type: ignore

    redo_bbox_helpers_json: bpy.props.StringProperty(
        default="[]",
        options={"HIDDEN"},
        description="Internal: JSON list of bpy object names created this redo tweak",
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            return False
        active = context.active_object
        if active is None or active.type != "MESH":
            return False
        return any(o.type == "MESH" for o in context.selected_objects)

    def draw(self, context):
        layout = self.layout

        top = layout.box()
        top.row(align=True).prop(
            self, "reset_requested", toggle=True, icon="FILE_REFRESH", text="Reset"
        )

        layout.separator(factor=self._SEP_MAIN)

        row_ax = layout.row(align=True)
        row_ax.prop_enum(self, "bbox_space", "LOCAL")
        row_ax.prop_enum(self, "bbox_space", "WORLD")
        row_ax.separator(factor=0.65)
        row_ax.prop(self, "bbox_each_object", toggle=True, text="Each")

        row_pad = layout.row(align=True)
        row_pad.prop(self, "bbox_padding")
        row_pad.prop(self, "bbox_padding_second_object", toggle=True, text="+ copy")

        layout.separator(factor=self._SEP_BLOCK)
        layout.prop(self, "helper_setup")

    def invoke(self, context, event):
        self.redo_bbox_helpers_json = "[]"
        return self.execute(context)

    def check(self, context):
        if self.reset_requested:
            self.bbox_space = "LOCAL"
            self.helper_setup = True
            self.bbox_padding = 0.0
            self.bbox_padding_second_object = False
            self.bbox_each_object = False
            self.reset_requested = False
        self.execute(context)
        return True

    def execute(self, context):
        selected_meshes = [o for o in context.selected_objects if o.type == "MESH"]
        active = context.active_object
        if not selected_meshes or not active:
            self.report({"WARNING"}, "Select at least one mesh object.")  # type: ignore
            return {"CANCELLED"}

        try:
            prev_names = json.loads(self.redo_bbox_helpers_json or "[]")
        except json.JSONDecodeError:
            prev_names = []
        for nm in prev_names:
            ob_rm = bpy.data.objects.get(nm)
            if ob_rm is not None:
                bpy.data.objects.remove(ob_rm, do_unlink=True)

        pad = self.bbox_padding
        dual = bool(self.bbox_padding_second_object) and abs(pad) > 1e-20
        cages = []

        if self.bbox_each_object:
            cages = list(
                bbox_tools.iter_bbox_helpers_for_selected(
                    context,
                    mode=self.bbox_space,
                    apply_extras=self.helper_setup,
                    pad=pad,
                    dual=dual,
                )
            )
            if not cages:
                self.redo_bbox_helpers_json = "[]"
                self.report({"WARNING"}, "Could not evaluate mesh bounds.")  # type: ignore
                return {"CANCELLED"}
        elif dual:
            tight = bbox_tools.create_bbox(
                context,
                mode=self.bbox_space,
                apply_extras=self.helper_setup,
                margin=0.0,
                name_suffix="",
            )
            if tight is None:
                self.redo_bbox_helpers_json = "[]"
                self.report({"WARNING"}, "Could not evaluate mesh bounds.")  # type: ignore
                return {"CANCELLED"}
            cages.append(tight)
            outer = bbox_tools.create_bbox(
                context,
                mode=self.bbox_space,
                apply_extras=self.helper_setup,
                margin=pad,
                name_suffix="_p",
                wire_color=bbox_tools.BBOX_HELPER_COLOR_PADDED,
            )
            if outer is not None:
                cages.append(outer)
        else:
            bbox = bbox_tools.create_bbox(
                context,
                mode=self.bbox_space,
                apply_extras=self.helper_setup,
                margin=pad,
                name_suffix="",
            )
            if bbox is None:
                self.redo_bbox_helpers_json = "[]"
                self.report({"WARNING"}, "Could not evaluate mesh bounds.")  # type: ignore
                return {"CANCELLED"}
            cages.append(bbox)

        self.redo_bbox_helpers_json = json.dumps([c.name for c in cages])

        return {"FINISHED"}


classes = (
    ALEC_OT_bbox_dialog,
)
