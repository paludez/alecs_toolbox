import bpy


class ALEC_OT_mesh_edit_component(bpy.types.Operator):
    """Enter Edit Mode if needed and set mesh vertex/edge/face selection mode (1–3 style)."""
    bl_idname = "alec.mesh_edit_component"
    bl_label = "Mesh component mode"
    bl_options = {'REGISTER', 'UNDO'}

    component: bpy.props.EnumProperty(
        name="Component",
        items=[
            ('VERT', "Vertex", ""),
            ('EDGE', "Edge", ""),
            ('FACE', "Face", ""),
        ],
        options={'HIDDEN', 'SKIP_SAVE'},
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, "Select an active mesh object")
            return {'CANCELLED'}
        if context.mode != 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')
        ts = context.tool_settings
        if self.component == 'VERT':
            ts.mesh_select_mode = (True, False, False)
        elif self.component == 'EDGE':
            ts.mesh_select_mode = (False, True, False)
        else:
            ts.mesh_select_mode = (False, False, True)
        return {'FINISHED'}


classes = (ALEC_OT_mesh_edit_component,)
