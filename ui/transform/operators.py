"""Transform operators (ALEC_OT_*)."""

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from . import selection_math as sm

class ALEC_OT_object_world_translation(bpy.types.Operator):
    bl_idname = "alec.object_world_translation"
    bl_label = "Object world location"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Set object translation in world space"

    translation: bpy.props.FloatVectorProperty(
        name="Translation",
        size=3,
        subtype="TRANSLATION",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        mw = obj.matrix_world.copy()
        mw.translation = Vector(self.translation)
        obj.matrix_world = mw
        sm._sync_object_world_from_active(context)
        return {"FINISHED"}


class ALEC_OT_object_rotation_world(bpy.types.Operator):
    bl_idname = "alec.object_rotation_world"
    bl_label = "Object world rotation"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Set object Euler XYZ rotation in world space"

    euler_xyz: bpy.props.FloatVectorProperty(
        name="Euler",
        size=3,
        subtype="EULER",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        mw = obj.matrix_world
        loc = mw.translation
        scale = mw.to_scale()
        euler = Euler(Vector(self.euler_xyz), "XYZ")
        obj.matrix_world = Matrix.LocRotScale(loc, euler, scale)
        sm._sync_object_world_from_active(context)
        return {"FINISHED"}


class ALEC_OT_object_rotation_local(bpy.types.Operator):
    bl_idname = "alec.object_rotation_local"
    bl_label = "Object rotation (orient)"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Set Euler XYZ in active Transform Orientation space"

    euler_xyz: bpy.props.FloatVectorProperty(
        name="Euler",
        size=3,
        subtype="EULER",
        options={"SKIP_SAVE"},
    )
    orient_type: bpy.props.StringProperty(options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        sm._apply_euler_orientation(
            context, obj, Vector(self.euler_xyz), self.orient_type or "GLOBAL"
        )
        sm._sync_object_world_from_active(context)
        return {"FINISHED"}

class ALEC_OT_selection_translate_delta(bpy.types.Operator):
    """Undo corect în Edit Mesh (REGISTER|UNDO); bmesh direct + undo_push nu e mereu în stivă."""

    bl_idname = "alec.selection_translate_delta"
    bl_label = "Selection translate"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Translate selected geometry in world space"

    delta_w: bpy.props.FloatVectorProperty(
        name="Delta",
        size=3,
        subtype="TRANSLATION",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "EDIT_MESH"
            and context.active_object is not None
            and context.active_object.type == "MESH"
        )

    def execute(self, context):
        obj = context.active_object
        props = context.scene.alec_edit_selection
        delta = Vector(self.delta_w)
        if delta.length < 1e-12:
            return {"CANCELLED"}
        sm._apply_translation_world(context, obj, delta)
        sm._sync_selection_props_from_mesh(context, props)
        return {"FINISHED"}


class ALEC_OT_selection_resize_orient(bpy.types.Operator):
    bl_idname = "alec.selection_resize_orient"
    bl_label = "Selection resize (orient)"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Resize selection bbox along active Transform Orientation axes"

    new_dims: bpy.props.FloatVectorProperty(
        name="New dims",
        size=3,
        subtype="XYZ",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "EDIT_MESH"
            and context.active_object is not None
            and context.active_object.type == "MESH"
        )

    def execute(self, context):
        obj = context.active_object
        props = context.scene.alec_edit_selection
        sm._apply_resize_orientation(context, obj, Vector(self.new_dims))
        sm._sync_selection_props_from_mesh(context, props)
        return {"FINISHED"}


class ALEC_OT_selection_scale_orient(bpy.types.Operator):
    bl_idname = "alec.selection_scale_orient"
    bl_label = "Selection scale (orient)"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Scale selection around oriented bbox center (multipliers per axis)"

    mult: bpy.props.FloatVectorProperty(
        name="Scale",
        size=3,
        subtype="XYZ",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "EDIT_MESH"
            and context.active_object is not None
            and context.active_object.type == "MESH"
        )

    def execute(self, context):
        obj = context.active_object
        props = context.scene.alec_edit_selection
        sm._apply_scale_orientation(context, obj, Vector(self.mult))
        sm._sync_selection_props_from_mesh(context, props)
        return {"FINISHED"}


class ALEC_OT_reset_transform_column(bpy.types.Operator):
    bl_idname = "alec.reset_transform_column"
    bl_label = "Reset column"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Pune valorile coloanei la 0 (scale la 1, dimensiuni la 0)"

    column: bpy.props.StringProperty(options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None:
            return False
        if context.mode == "EDIT_MESH" and obj.type == "MESH":
            return bool(sm._selected_vert_positions_world(context, obj, obj.data))
        return True

    def execute(self, context):
        st = sm._reset_transform_column(context, self.column)
        return {"FINISHED"} if st == "FINISHED" else {"CANCELLED"}


class ALEC_OT_selection_rotate(bpy.types.Operator):
    bl_idname = "alec.selection_rotate"
    bl_label = "Selection rotate"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Rotate selected vertices around selection centroid (world)"

    rotation: bpy.props.FloatVectorProperty(
        name="Rotation",
        size=4,
        subtype="QUATERNION",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "EDIT_MESH"
            and context.active_object is not None
            and context.active_object.type == "MESH"
        )

    def execute(self, context):
        obj = context.active_object
        q = Quaternion(self.rotation)
        sm._apply_selection_rotation_quat(context, obj, q)
        props = context.scene.alec_edit_selection
        props.sel_rot_quat = (q.w, q.x, q.y, q.z)
        sm._sync_sel_rot_eulers_from_quat(context, props)
        return {"FINISHED"}
