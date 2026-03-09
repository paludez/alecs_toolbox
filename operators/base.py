# Base classes for operators
import bpy
from ..modules import bbox_tools

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
