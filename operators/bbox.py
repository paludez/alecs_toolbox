import bpy
import bmesh
from ..modules import bbox_tools
from ..modules.modal_handler import BaseModalOperator
from ..modules.utils import unit_suffixes, draw_modal_status_bar, get_unit_scale
from ..modules.drawing_tools import draw_mesh_wireframe

class BBoxOperatorBase:
    bl_options = {'REGISTER', 'UNDO'}
    mode: str = ""

    def execute(self, context):
        if not self.mode:
            self.report({'ERROR'}, "Mode not set in BBox operator subclass") # type: ignore
            return {'CANCELLED'}
        
        # Delegate to bbox_tools
        bbox_tools.create_bbox(context, mode=self.mode)
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
        if not self.source_obj or self.source_obj.type != 'MESH':
            self.report({'WARNING'}, "No valid mesh object selected.")
            return {'CANCELLED'}

        # Extract necessary geometry data purely in memory
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
        
        # Attach the GPU drawing routine
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

        bbox_tools.setup_bbox_visibility(offset_obj, color=(0.0, 0.5, 1.0, 1.0))
        bbox_tools.set_shading_to_object(context)
        
        from ..modules.utils import move_to_collection, get_or_create_collection
        move_to_collection(offset_obj, get_or_create_collection(context))

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

classes = [
    ALEC_OT_bbox_offset_modal,
    ALEC_OT_bbox_local,
    ALEC_OT_bbox_world,
]
