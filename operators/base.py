# Base classes for operators
import bpy
from ..modules import bbox_tools
from ..modules import align_tools

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

class QuickAlignBase:
    bl_options = {'REGISTER', 'UNDO'}
    source_point: str = ""
    target_point: str = ""

    def execute(self, context):
        target = context.active_object
        sources = [o for o in context.selected_objects if o != target]

        if not self.source_point or not self.target_point:
            self.report({'ERROR'}, "Alignment points not set in QuickAlign operator subclass") # type: ignore
            return {'CANCELLED'}

        for source in sources:
            align_tools.align_position(source, target, x=True, y=True, z=True,
                source_point=self.source_point, target_point=self.target_point)
            align_tools.align_orientation(source, target, x=True, y=True, z=True)
        return {'FINISHED'}
