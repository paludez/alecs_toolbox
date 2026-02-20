import bpy
from .modules import bbox_tools
from .modules import align_tools
from .modules import cursor_tools
from .modules import misc_tools

class ALEC_OT_group_active(bpy.types.Operator):
    bl_idname = "alec.group_active"
    bl_label = "Group Active"
    bl_description = "Group selected objects under an Empty at the active object's bounding box center"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        misc_tools.group_active(context)
        return {'FINISHED'}

class ALEC_OT_group(bpy.types.Operator):
    bl_idname = "alec.group"
    bl_label = "Group"
    bl_description = "Groups selected objects under a common Empty"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        misc_tools.group_objects(context)
        return {'FINISHED'}

class ALEC_OT_ungroup(bpy.types.Operator):
    bl_idname = "alec.ungroup"
    bl_label = "Ungroup"
    bl_description = "Ungroup selected Empty and release all children"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        misc_tools.ungroup_objects(context)
        return {'FINISHED'}


class ALEC_OT_bbox_local(bpy.types.Operator):
    bl_idname = "alec.bbox_local"
    bl_label = "LOCAL"
    bl_description = "Create a bounding box aligned to object's local axes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bbox_tools.create_bbox(context, mode='LOCAL') 
        return {'FINISHED'}


class ALEC_OT_bbox_world(bpy.types.Operator):
    bl_idname = "alec.bbox_world"
    bl_label = "WORLD"
    bl_description = "Create a bounding box aligned to object's world axes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # TRIMITE context, NU context.active_object
        bbox_tools.create_bbox(context, mode='WORLD') 
        return {'FINISHED'}


class ALEC_OT_bbox_offset(bpy.types.Operator):
    bl_idname = "alec.bbox_offset"
    bl_label = "BBoxOF"
    bl_description = "Create a bounding box with an offset from the original object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bbox_tools.create_offset_bbox(context.active_object, offset=context.scene.alec_bbox_offset)
        return {'FINISHED'}


class ALEC_OT_align(bpy.types.Operator):
    bl_idname = "alec.align"
    bl_label = "Apply"
    bl_description = "Align selected objects to active object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sc = context.scene
        target = context.active_object
        sources = [o for o in context.selected_objects if o != target]
        for source in sources:
            align_tools.align_position(source, target,
                x=sc.alec_align_x, y=sc.alec_align_y, z=sc.alec_align_z,
                source_point=sc.alec_align_source_point,
                target_point=sc.alec_align_target_point)
            align_tools.align_orientation(source, target,
                x=sc.alec_orient_x, y=sc.alec_orient_y, z=sc.alec_orient_z)
            align_tools.match_scale(source, target,
                x=sc.alec_scale_x, y=sc.alec_scale_y, z=sc.alec_scale_z)
        return {'FINISHED'}


class ALEC_OT_quick_center(bpy.types.Operator):
    bl_idname = "alec.quick_center"
    bl_label = "Quick Center"
    bl_description = "Align selected objects to active object's bounding box center"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        target = context.active_object
        sources = [o for o in context.selected_objects if o != target]
        for source in sources:
            align_tools.align_position(source, target, x=True, y=True, z=True,
                source_point='CENTER', target_point='CENTER')
            align_tools.align_orientation(source, target, x=True, y=True, z=True)
        return {'FINISHED'}


class ALEC_OT_quick_pivot(bpy.types.Operator):
    bl_idname = "alec.quick_pivot"
    bl_label = "Quick Pivot"
    bl_description = "Align selected objects to active object's pivot point"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        target = context.active_object
        sources = [o for o in context.selected_objects if o != target]
        for source in sources:
            align_tools.align_position(source, target, x=True, y=True, z=True,
                source_point='PIVOT', target_point='PIVOT')
            align_tools.align_orientation(source, target, x=True, y=True, z=True)
        return {'FINISHED'}


class ALEC_OT_cursor_to_selected(bpy.types.Operator):
    bl_idname = "alec.cursor_to_selected"
    bl_label = "Cursor to Selected"
    bl_description = "Move&Rotate 3D cursor to selected object's origin"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cursor_tools.cursor_to_selected(context)
        return {'FINISHED'}


class ALEC_OT_cursor_to_geometry_center(bpy.types.Operator):
    bl_idname = "alec.cursor_to_geometry_center"
    bl_label = "Cursor to Geometry Center"
    bl_description = "Move&Rotate 3D cursor to selected object's BBox center"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cursor_tools.cursor_to_geometry_center(context)
        return {'FINISHED'}

class ALEC_OT_origin_to_cursor(bpy.types.Operator):
    bl_idname = "alec.origin_to_cursor"
    bl_label = "Origin to Cursor"
    bl_description = "Move object origin to 3D cursor position and orientation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cursor_tools.origin_to_cursor(context)
        return {'FINISHED'}

classes = [
    ALEC_OT_bbox_local,
    ALEC_OT_bbox_world,
    ALEC_OT_bbox_offset,
    ALEC_OT_align,
    ALEC_OT_quick_center,
    ALEC_OT_quick_pivot,
    ALEC_OT_cursor_to_selected,
    ALEC_OT_cursor_to_geometry_center,
    ALEC_OT_origin_to_cursor,
    ALEC_OT_group,
    ALEC_OT_group_active,
    ALEC_OT_ungroup,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)