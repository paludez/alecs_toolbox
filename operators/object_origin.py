# Operators for manipulating object origins and the 3D cursor
import bpy
from mathutils import Matrix
from ..modules import cursor_tools
from ..modules.utils import get_bounds_data

class ALEC_OT_cursor_to_selected(bpy.types.Operator):
    """Move&Rotate 3D cursor to selected object's origin"""
    bl_idname = "alec.cursor_to_selected"
    bl_label = "Cursor to Selected"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cursor_tools.cursor_to_selected(context)
        return {'FINISHED'}

class ALEC_OT_cursor_to_geometry_center(bpy.types.Operator):
    """Move&Rotate 3D cursor to selected object's BBox center"""
    bl_idname = "alec.cursor_to_geometry_center"
    bl_label = "Cursor to Geometry Center"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cursor_tools.cursor_to_geometry_center(context)
        return {'FINISHED'}

class ALEC_OT_origin_to_cursor(bpy.types.Operator):
    """Move object origin to 3D cursor position and orientation"""
    bl_idname = "alec.origin_to_cursor"
    bl_label = "Origin to Cursor"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cursor_tools.origin_to_cursor(context)
        return {'FINISHED'}

class ALEC_OT_origin_to_active(bpy.types.Operator):
    """Set the origin of selected objects to the active object's origin"""
    bl_idname = "alec.origin_to_active"
    bl_label = "Origin to Active"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Requires an active object and at least one other selected object
        return context.active_object and len(context.selected_objects) > 1

    def execute(self, context):
        active_obj = context.active_object
        
        saved_cursor_matrix = context.scene.cursor.matrix.copy()
        context.scene.cursor.location = active_obj.matrix_world.translation
        active_obj.select_set(False)
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        active_obj.select_set(True)
        
        context.scene.cursor.matrix = saved_cursor_matrix
        return {'FINISHED'}

class ALEC_OT_origin_to_bottom(bpy.types.Operator):
    """Move object origin to the bottom center of its bounding box"""
    bl_idname = "alec.origin_to_bottom"
    bl_label = "Origin to Bottom"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        saved_cursor = context.scene.cursor.matrix.copy()
        selected = context.selected_objects
        active = context.active_object
        
        for obj in selected:
            if obj.type == 'MESH':
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj
                
                # Calculate world bounds mathematically (faster/cleaner than creating a bbox object)
                bounds_min = get_bounds_data(obj, point_type='MIN', space='WORLD')
                loc = obj.matrix_world.translation
                
                # Move cursor to (Obj X, Obj Y, Bounds Min Z)
                context.scene.cursor.location = (loc.x, loc.y, bounds_min.z)
                
                # Apply origin
                bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        
        context.scene.cursor.matrix = saved_cursor
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected:
            obj.select_set(True)
        context.view_layer.objects.active = active
        
        return {'FINISHED'}

class ALEC_OT_origin_to_selected_edit(bpy.types.Operator):
    """Set origin to the average position of selected elements"""
    bl_idname = "alec.origin_to_selected_edit"
    bl_label = "Origin to Selection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        saved_cursor = context.scene.cursor.matrix.copy()
        bpy.ops.view3d.snap_cursor_to_selected()
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        bpy.ops.object.mode_set(mode='EDIT')
        context.scene.cursor.matrix = saved_cursor
        return {'FINISHED'}

class ALEC_OT_origin_to_selected_edit_aligned(bpy.types.Operator):
    """Set origin to selection center and align orientation to normal"""
    bl_idname = "alec.origin_to_selected_edit_aligned"
    bl_label = "Origin to Selection (Aligned)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        obj = context.active_object
        saved_cursor_matrix = context.scene.cursor.matrix.copy()
        
        try:
            bpy.ops.view3d.snap_cursor_to_selected()
        except Exception:
            self.report({'WARNING'}, "No selection found")
            return {'CANCELLED'}
            
        bpy.ops.transform.create_orientation(name="Temp_Alec_Align", use=True, overwrite=True)
        
        slot = context.scene.transform_orientation_slots[0]
        custom_orient = slot.custom_orientation
        
        if not custom_orient:
            self.report({'WARNING'}, "Could not create orientation")
            return {'CANCELLED'}
            
        rot_mat = custom_orient.matrix.to_4x4()
        target_matrix = rot_mat
        target_matrix.translation = context.scene.cursor.location
        
        bpy.ops.object.mode_set(mode='OBJECT')
        
        m_old = obj.matrix_world.copy()
        m_new = target_matrix
        
        mat_transform = m_new.inverted() @ m_old
        
        obj.matrix_world = m_new
        obj.data.transform(mat_transform)
        
        bpy.ops.object.mode_set(mode='EDIT')
        context.scene.cursor.matrix = saved_cursor_matrix
        
        return {'FINISHED'}

classes = [
    ALEC_OT_cursor_to_selected,
    ALEC_OT_cursor_to_geometry_center,
    ALEC_OT_origin_to_cursor,
    ALEC_OT_origin_to_active,
    ALEC_OT_origin_to_bottom,
    ALEC_OT_origin_to_selected_edit,
    ALEC_OT_origin_to_selected_edit_aligned,
]
