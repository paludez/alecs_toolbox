# System-level operators like the menu dispatcher
import bpy

class ALEC_OT_menu_dispatcher(bpy.types.Operator):
    """Shows a different menu based on the context (Object/Edit mode)"""
    bl_idname = "alec.menu_dispatcher"
    bl_label = "Menu Dispatcher"

    def execute(self, context):
        if context.area.type == 'IMAGE_EDITOR':
            bpy.ops.wm.call_menu_pie(name='ALEC_MT_uv_menu')
        elif context.mode == 'EDIT_MESH':
            bpy.ops.wm.call_menu_pie(name='ALEC_MT_edit_menu')
        else:
            bpy.ops.wm.call_menu_pie(name='ALEC_MT_object_menu')
        return {'FINISHED'}

classes = [
    ALEC_OT_menu_dispatcher,
]
