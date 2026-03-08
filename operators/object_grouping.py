# Operators for grouping, bbox, and quick alignment
import bpy
from ..modules import misc_tools, align_tools, bbox_tools
from .base import BBoxOperatorBase, QuickAlignBase

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

class ALEC_OT_quick_center(QuickAlignBase, bpy.types.Operator):
    """Align selected objects to active object's bounding box center"""
    bl_idname = "alec.quick_center"
    bl_label = "Quick Center"
    source_point = 'CENTER'
    target_point = 'CENTER'

class ALEC_OT_quick_pivot(QuickAlignBase, bpy.types.Operator):
    """Align selected objects to active object's pivot point"""
    bl_idname = "alec.quick_pivot"
    bl_label = "Quick Pivot"
    source_point = 'PIVOT'
    target_point = 'PIVOT'

classes = [
    ALEC_OT_group,
    ALEC_OT_group_active,
    ALEC_OT_ungroup,
    ALEC_OT_bbox_local,
    ALEC_OT_bbox_world,
    ALEC_OT_quick_center,
    ALEC_OT_quick_pivot,
]
