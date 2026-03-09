# Operators for grouping, bbox, and quick alignment
import bpy
from ..modules import misc_tools

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

classes = [
    ALEC_OT_group,
    ALEC_OT_group_active,
    ALEC_OT_ungroup,
]
