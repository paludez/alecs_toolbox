import json
import bpy
import bmesh
from ..modules import bbox_tools
from ..modules.modal_handler import BaseModalOperator
from ..modules.utils import unit_suffixes, draw_modal_status_bar
from ..modules.drawing_tools import draw_mesh_wireframe

class BBoxOperatorBase:
    bl_options = {'REGISTER', 'UNDO'}
    mode: str = ""

    def invoke(self, context, event):
        self.minimal_mode = bool(event.shift)
        return self.execute(context)

    def execute(self, context):
        if not self.mode:
            self.report({'ERROR'}, "Mode not set in BBox operator subclass") # type: ignore
            return {'CANCELLED'}

        if bbox_tools.create_bbox(
            context,
            mode=self.mode,
            apply_extras=not getattr(self, "minimal_mode", False),
        ) is None:
            self.report({'WARNING'}, "Select at least one mesh object.")  # type: ignore
            return {'CANCELLED'}
        return {'FINISHED'}
        
class ALEC_OT_bbox_offset_modal(BaseModalOperator, bpy.types.Operator):
    """Create an offset of a mesh object with interactive mouse and keyboard control."""
    bl_idname = "alec.bbox_offset_modal"
    bl_label = "Interactive BBox Offset"
    bl_options = {'REGISTER', 'UNDO', 'GRAB_CURSOR', 'BLOCKING'}

    def draw_callback_3d(self, context):
        draw_mesh_wireframe(self.world_matrix, self.orig_coords, self.orig_normals, self.edges, self.offset)

    def invoke(self, context, event):
        """Setup for the modal operator."""
        self.source_obj = context.active_object
        self.minimal_mode = bool(event.shift)
        if not self.source_obj or self.source_obj.type != 'MESH':
            self.report({'WARNING'}, "No valid mesh object selected.")
            return {'CANCELLED'}

        bm = bmesh.new()
        bm.from_mesh(self.source_obj.data)
        bm.verts.ensure_lookup_table()
        
        self.orig_coords = [v.co.copy() for v in bm.verts]
        self.orig_normals = [v.normal.copy() for v in bm.verts]
        self.edges = [(e.verts[0].index, e.verts[1].index) for e in bm.edges]
        bm.free()

        if not self.orig_coords:
            self.report({'WARNING'}, "Mesh has no vertices.")
            return {'CANCELLED'}

        self.offset = 0.0
        self.world_matrix = self.source_obj.matrix_world.copy()
        
        self._draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_callback_3d, (context,), 'WINDOW', 'POST_VIEW')
            
        return self.base_invoke(context, event)

    def on_cleanup(self, context):
        if hasattr(self, '_draw_handler') and self._draw_handler:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._draw_handler, 'WINDOW')
            except ValueError: pass
            self._draw_handler = None

    def on_confirm(self, context, event):
        """Generate the actual mesh object only upon confirmation."""
        bpy.ops.object.duplicate()
        offset_obj = context.active_object
        offset_obj.name = f"{self.source_obj.name}_offset"

        if offset_obj.data.users > 1:
            offset_obj.data = offset_obj.data.copy()

        mesh = offset_obj.data
        new_coords = [co + normal * self.offset for co, normal in zip(self.orig_coords, self.orig_normals)]
        flat_coords = [c for co in new_coords for c in co]
        mesh.vertices.foreach_set("co", flat_coords)
        mesh.update()

        if not self.minimal_mode:
            bbox_tools.setup_bbox_visibility(offset_obj, color=(0.0, 0.5, 1.0, 1.0))
            bbox_tools.set_shading_to_object(context)
            from ..modules.utils import move_to_collection, get_or_create_collection
            move_to_collection(offset_obj, get_or_create_collection(context))
        else:
            bbox_tools.move_to_same_collections(offset_obj, self.source_obj)

    def get_header_args(self, context):
        return {"main_label": "Offset", "main_value": self.offset * self.unit_scale_display_inv, 
                "suffix": unit_suffixes.get(context.scene.unit_settings.length_unit, '')}

    def on_mouse_move(self, context, event, delta_x):
        self.offset = delta_x * 0.005

    def on_apply_typed_value(self, context, event):
        if self.number_input.has_value():
            try:
                self.offset = self.number_input.get_value() * self.unit_scale
            except ValueError: pass

class ALEC_OT_bbox_local(BBoxOperatorBase, bpy.types.Operator):
    """Create a bounding box aligned to the object's local axes"""
    bl_idname = "alec.bbox_local"
    bl_label = "LOCAL"
    mode = 'LOCAL'

class ALEC_OT_bbox_world(BBoxOperatorBase, bpy.types.Operator):
    """Create a bounding box aligned to the world axes"""
    bl_idname = "alec.bbox_world"
    bl_label = "WORLD"
    mode = 'WORLD'


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


classes = [
    ALEC_OT_bbox_offset_modal,
    ALEC_OT_bbox_local,
    ALEC_OT_bbox_world,
    ALEC_OT_bbox_dialog,
]
