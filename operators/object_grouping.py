# Operators for grouping, bbox, and quick alignment
import bpy
from ..modules import misc_tools, bbox_tools
from .base import BBoxOperatorBase
from ..dialog import ALEC_OT_align_dialog

class ALEC_OT_group(bpy.types.Operator):
    """Group selected objects under a new Empty at the world origin"""
    bl_idname = "alec.group"
    bl_label = "Group"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        misc_tools.manage_grouping(context, 'GROUP')
        return {'FINISHED'}

class ALEC_OT_group_active(bpy.types.Operator):
    """Group selected objects under a new Empty at the active object's center"""
    bl_idname = "alec.group_active"
    bl_label = "Group Active"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        misc_tools.manage_grouping(context, 'GROUP_ACTIVE')
        return {'FINISHED'}

class ALEC_OT_ungroup(bpy.types.Operator):
    """Ungroup the selected Empty, releasing all children"""
    bl_idname = "alec.ungroup"
    bl_label = "Ungroup"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        misc_tools.manage_grouping(context, 'UNGROUP')
        return {'FINISHED'}

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

class ALEC_OT_quick_center(ALEC_OT_align_dialog):
    """Align selected objects to active object's bounding box center"""
    bl_idname = "alec.quick_center"
    bl_label = "Quick Center"
    
    def invoke(self, context, event):
        self.align_x = True
        self.align_y = True
        self.align_z = True
        self.orient_x = False
        self.orient_y = False
        self.orient_z = False
        self.scale_x = False
        self.scale_y = False
        self.scale_z = False
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.offset_z = 0.0
        self.use_active_orient = False
        self.reset_requested = False
        
        self.source_point = 'CENTER'
        self.target_point = 'CENTER'
        return self.execute(context)

class ALEC_OT_quick_pivot(ALEC_OT_align_dialog):
    """Align selected objects to active object's pivot point"""
    bl_idname = "alec.quick_pivot"
    bl_label = "Quick Pivot"
    
    def invoke(self, context, event):
        self.align_x = True
        self.align_y = True
        self.align_z = True
        self.orient_x = False
        self.orient_y = False
        self.orient_z = False
        self.scale_x = False
        self.scale_y = False
        self.scale_z = False
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.offset_z = 0.0
        self.use_active_orient = False
        self.reset_requested = False
        
        self.source_point = 'PIVOT'
        self.target_point = 'PIVOT'
        return self.execute(context)

classes = [
    ALEC_OT_group,
    ALEC_OT_group_active,
    ALEC_OT_ungroup,
    ALEC_OT_bbox_local,
    ALEC_OT_bbox_world,
    ALEC_OT_quick_center,
    ALEC_OT_quick_pivot,
]
