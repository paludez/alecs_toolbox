import math
import bpy
from mathutils import Matrix
from ..modules.utils import get_bounds_data


def _cursor_to_origin_rot(context):
    obj = context.active_object
    context.scene.cursor.location = obj.location.copy()
    context.scene.cursor.rotation_euler = obj.rotation_euler.copy()


def _cursor_to_bbox_rot(context):
    obj = context.active_object
    context.scene.cursor.location = get_bounds_data(obj, 'CENTER', 'LOCAL')
    context.scene.cursor.rotation_euler = obj.rotation_euler.copy()


def _origin_to_cursor_rot(context):
    context.scene.tool_settings.use_transform_data_origin = True
    bpy.ops.view3d.snap_selected_to_cursor(use_offset=False, use_rotation=True)
    context.scene.tool_settings.use_transform_data_origin = False


def _origin_to_cursor(context):
    context.scene.tool_settings.use_transform_data_origin = True
    bpy.ops.view3d.snap_selected_to_cursor(use_offset=False, use_rotation=False)
    context.scene.tool_settings.use_transform_data_origin = False


def _selection_orientation_matrix(context):
    """Return selection orientation matrix without leaving temp orientations behind."""
    slot = context.scene.transform_orientation_slots[0]
    prev_type = slot.type
    temp_name = "Temp_Alec_Align"

    try:
        bpy.ops.transform.create_orientation(
            name=temp_name, use=True, overwrite=True
        )
        custom_orient = slot.custom_orientation
        if not custom_orient:
            return None
        rot_mat = custom_orient.matrix.to_4x4()
        try:
            bpy.ops.transform.delete_orientation()
        except Exception:
            pass
        return rot_mat
    finally:
        try:
            slot.type = prev_type
        except Exception:
            pass


class ALEC_OT_cursor_to_selected(bpy.types.Operator):
    """Move&Rotate 3D cursor to selected object's origin"""
    bl_idname = "alec.cursor_to_origin_rot"
    bl_label = "Cursor to Selected"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _cursor_to_origin_rot(context)
        return {'FINISHED'}

class ALEC_OT_cursor_to_geometry_center(bpy.types.Operator):
    """Move&Rotate 3D cursor to selected object's BBox center"""
    bl_idname = "alec.cursor_to_bbox_rot"
    bl_label = "Cursor to Geometry Center"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _cursor_to_bbox_rot(context)
        return {'FINISHED'}

class ALEC_OT_origin_to_cursor_rot(bpy.types.Operator):
    """Move object origin to 3D cursor position and orientation"""
    bl_idname = "alec.origin_to_cursor_rot"
    bl_label = "Origin to Cursor (Rot)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        saved_mode = context.mode
        saved_cursor = context.scene.cursor.matrix.copy()
        selected = list(context.selected_objects)
        active = context.active_object

        # This operator uses bpy.ops.view3d.snap_selected_to_cursor, which can
        # fail in Edit Mode due to context.poll. Switch modes internally.
        if saved_mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                self.report({'ERROR'}, "Could not switch to Object Mode.")
                return {'CANCELLED'}

        try:
            # Re-apply selection so snap operates on the expected objects.
            try:
                bpy.ops.object.select_all(action='DESELECT')
            except Exception:
                pass
            for obj in selected:
                # Keep selection for non-mesh object types too (e.g. CURVES).
                # The underlying snap operator works on objects; filtering to
                # MESH breaks "To Cur (Rot)" for CURVES.
                obj.select_set(True)
            if active:
                context.view_layer.objects.active = active

            _origin_to_cursor_rot(context)
        finally:
            context.scene.cursor.matrix = saved_cursor
            try:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in selected:
                    obj.select_set(True)
                if active:
                    context.view_layer.objects.active = active
            except Exception:
                pass

            if saved_mode == 'EDIT_MESH':
                try:
                    bpy.ops.object.mode_set(mode='EDIT')
                except Exception:
                    pass

        return {'FINISHED'}


class ALEC_OT_origin_to_cursor(bpy.types.Operator):
    """Set object origin to the 3D cursor (non-rotational)"""
    bl_idname = "alec.origin_to_cursor"
    bl_label = "Origin to Cursor"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        saved_mode = context.mode
        saved_cursor = context.scene.cursor.matrix.copy()
        selected = list(context.selected_objects)
        active = context.active_object

        # object.origin_set / select_all can fail poll() in Edit Mode.
        if saved_mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                self.report({'ERROR'}, "Could not switch to Object Mode.")
                return {'CANCELLED'}

        try:
            for obj in selected:
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj
                # Same approach as "To Cur (Rot)" but without rotation, so it
                # works consistently for EMPTY / CURVES / etc.
                _origin_to_cursor(context)
        finally:
            context.scene.cursor.matrix = saved_cursor
            try:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in selected:
                    obj.select_set(True)
                if active:
                    context.view_layer.objects.active = active
            except Exception:
                pass

            if saved_mode == 'EDIT_MESH':
                try:
                    bpy.ops.object.mode_set(mode='EDIT')
                except Exception:
                    pass

        return {'FINISHED'}


class ALEC_OT_origin_set_to_bbox(bpy.types.Operator):
    """Set object origin to the active object's bounding box center"""
    bl_idname = "alec.origin_set_to_bbox"
    bl_label = "Origin to BBox"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        saved_mode = context.mode
        saved_cursor = context.scene.cursor.matrix.copy()
        selected = list(context.selected_objects)
        active = context.active_object

        # object.origin_set / select_all can fail poll() in Edit Mode.
        if saved_mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                self.report({'ERROR'}, "Could not switch to Object Mode.")
                return {'CANCELLED'}

        try:
            for obj in selected:
                if obj.type != 'MESH':
                    continue
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj
                bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
        finally:
            # Restore cursor + selection
            context.scene.cursor.matrix = saved_cursor
            try:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in selected:
                    obj.select_set(True)
                if active:
                    context.view_layer.objects.active = active
            except Exception:
                pass

            if saved_mode == 'EDIT_MESH':
                try:
                    bpy.ops.object.mode_set(mode='EDIT')
                except Exception:
                    pass

        return {'FINISHED'}


class ALEC_OT_origin_to_active(bpy.types.Operator):
    """Set the origin of selected objects to the active object's origin"""
    bl_idname = "alec.origin_to_active"
    bl_label = "Origin to Active"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
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

class ALEC_OT_origin_to_active_rot(bpy.types.Operator):
    """Set selected origins to active object's origin and orientation"""
    bl_idname = "alec.origin_to_active_rot"
    bl_label = "Origin to Active (Rot)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and len(context.selected_objects) > 1

    def execute(self, context):
        active_obj = context.active_object
        saved_cursor_matrix = context.scene.cursor.matrix.copy()

        try:
            context.scene.cursor.matrix = active_obj.matrix_world.copy()
            active_obj.select_set(False)
            _origin_to_cursor_rot(context)
        finally:
            active_obj.select_set(True)
            context.scene.cursor.matrix = saved_cursor_matrix

        return {'FINISHED'}

class ALEC_OT_origin_to_bottom(bpy.types.Operator):
    """Move object origin to the bottom center of its bounding box"""
    bl_idname = "alec.origin_to_bottom"
    bl_label = "Origin to Bottom"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        saved_mode = context.mode
        saved_cursor = context.scene.cursor.matrix.copy()
        selected = list(context.selected_objects)
        active = context.active_object

        # In Edit Mode, bpy.ops.object.* operators can fail poll() with
        # "context is incorrect". Switch to Object Mode internally, then
        # switch back to what the user had.
        if saved_mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                self.report({'ERROR'}, "Could not switch to Object Mode.")
                return {'CANCELLED'}

        try:
            for obj in selected:
                if obj.type != 'MESH':
                    continue
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj

                bounds_min = get_bounds_data(obj, point_type='MIN', space='WORLD')
                loc = obj.matrix_world.translation

                context.scene.cursor.location = (loc.x, loc.y, bounds_min.z)
                bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        finally:
            # Restore cursor and selection in whatever mode we end up in.
            context.scene.cursor.matrix = saved_cursor
            try:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in selected:
                    obj.select_set(True)
                if active:
                    context.view_layer.objects.active = active
            except Exception:
                pass

            if saved_mode == 'EDIT_MESH':
                try:
                    bpy.ops.object.mode_set(mode='EDIT')
                except Exception:
                    pass

        return {'FINISHED'}

class ALEC_OT_origin_to_selection(bpy.types.Operator):
    """Set origin to the average position of selected elements"""
    bl_idname = "alec.origin_to_selection"
    bl_label = "Origin to Selection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode in {'EDIT_MESH', 'EDIT_CURVE', 'EDIT_CURVES'}

    def execute(self, context):
        saved_cursor = context.scene.cursor.matrix.copy()
        bpy.ops.view3d.snap_cursor_to_selected()
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        bpy.ops.object.mode_set(mode='EDIT')
        context.scene.cursor.matrix = saved_cursor
        return {'FINISHED'}

class ALEC_OT_origin_to_selection_rot(bpy.types.Operator):
    """Set origin to selection center and align orientation to normal"""
    bl_idname = "alec.origin_to_selection_rot"
    bl_label = "Origin to Selection (Aligned)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode in {'EDIT_MESH', 'EDIT_CURVE', 'EDIT_CURVES'}

    def execute(self, context):
        obj = context.active_object
        saved_cursor_matrix = context.scene.cursor.matrix.copy()
        
        try:
            bpy.ops.view3d.snap_cursor_to_selected()
        except Exception:
            self.report({'WARNING'}, "No selection found")
            return {'CANCELLED'}
            
        rot_mat = _selection_orientation_matrix(context)
        if not rot_mat:
            self.report({'WARNING'}, "Could not create orientation")
            return {'CANCELLED'}

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

class ALEC_OT_cursor_to_selection_rot(bpy.types.Operator):
    """Move cursor to selected elements and align it to selection orientation"""
    bl_idname = "alec.cursor_to_selection_rot"
    bl_label = "Cursor to Selection (Rot)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode in {'EDIT_MESH', 'EDIT_CURVE', 'EDIT_CURVES'}

    def execute(self, context):
        try:
            bpy.ops.view3d.snap_cursor_to_selected()
        except Exception:
            self.report({'WARNING'}, "No selection found")
            return {'CANCELLED'}

        rot_mat = _selection_orientation_matrix(context)
        if not rot_mat:
            self.report({'WARNING'}, "Could not create orientation")
            return {'CANCELLED'}

        target_matrix = rot_mat
        target_matrix.translation = context.scene.cursor.location
        context.scene.cursor.matrix = target_matrix
        return {'FINISHED'}

class ALEC_OT_cursor_to_selection(bpy.types.Operator):
    """Move cursor to selected elements (position only)"""
    bl_idname = "alec.cursor_to_selection"
    bl_label = "Cursor to Selection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode in {'EDIT_MESH', 'EDIT_CURVE', 'EDIT_CURVES'}

    def execute(self, context):
        try:
            bpy.ops.view3d.snap_cursor_to_selected()
        except Exception:
            self.report({'WARNING'}, "No selection found")
            return {'CANCELLED'}
        return {'FINISHED'}


class ALEC_OT_origin_rotate_axis(bpy.types.Operator):
    """Rotate object origin around local axis while preserving geometry"""
    bl_idname = "alec.origin_rotate_axis"
    bl_label = "Origin Rotate Axis"
    bl_options = {'REGISTER', 'UNDO'}

    axis: bpy.props.EnumProperty(
        name="Axis",
        items=[
            ('X', "X", "Rotate origin around local X axis"),
            ('Y', "Y", "Rotate origin around local Y axis"),
            ('Z', "Z", "Rotate origin around local Z axis"),
        ],
        default='X',
    ) # type: ignore

    angle_degrees: bpy.props.FloatProperty(
        name="Angle",
        description="Rotation angle in degrees",
        default=90.0,
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def invoke(self, context, event):
        if event.ctrl and not event.alt:
            self.angle_degrees = 90.0
        elif event.alt and not event.ctrl:
            self.angle_degrees = -90.0
        else:
            self.angle_degrees = 0.0
        return self.execute(context)

    def execute(self, context):
        saved_mode = context.mode
        selected = list(context.selected_objects)
        active = context.active_object

        if saved_mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                self.report({'ERROR'}, "Could not switch to Object Mode.")
                return {'CANCELLED'}

        angle = math.radians(self.angle_degrees)
        rot_mat = Matrix.Rotation(angle, 4, self.axis)

        skipped = 0
        for obj in selected:
            data = getattr(obj, "data", None)
            if not data or not hasattr(data, "transform"):
                skipped += 1
                continue

            # Use local transform (matrix_basis) instead of matrix_world to keep
            # behaviour stable for parented objects while preserving geometry.
            m_old = obj.matrix_basis.copy()
            m_new = m_old @ rot_mat
            data_correction = m_new.inverted() @ m_old

            obj.matrix_basis = m_new
            data.transform(data_correction)
            data.update()

        try:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in selected:
                obj.select_set(True)
            if active:
                context.view_layer.objects.active = active
        except Exception:
            pass

        if saved_mode in {'EDIT_MESH', 'EDIT_CURVE', 'EDIT_CURVES'}:
            try:
                bpy.ops.object.mode_set(mode='EDIT')
            except Exception:
                pass

        if skipped:
            self.report({'INFO'}, f"Skipped {skipped} object(s) without transformable data")

        return {'FINISHED'}

classes = [
    ALEC_OT_cursor_to_selected,
    ALEC_OT_cursor_to_geometry_center,
    ALEC_OT_origin_to_cursor,
    ALEC_OT_origin_to_cursor_rot,
    ALEC_OT_origin_set_to_bbox,
    ALEC_OT_origin_to_active,
    ALEC_OT_origin_to_active_rot,
    ALEC_OT_origin_to_bottom,
    ALEC_OT_origin_to_selection,
    ALEC_OT_origin_to_selection_rot,
    ALEC_OT_cursor_to_selection,
    ALEC_OT_cursor_to_selection_rot,
    ALEC_OT_origin_rotate_axis,
]
