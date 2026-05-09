"""Transform UI dialog (sidebar entry → popup); fields will grow here."""

import bpy


class ALEC_OT_transform_dialog(bpy.types.Operator):
    bl_idname = "alec.transform_dialog"
    bl_label = "Transform"
    bl_description = "Edit transforms (placeholder dialog)"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        obj = context.active_object
        if obj is None:
            layout.label(text="No active object", icon="INFO")
            return
        layout.label(text=obj.name, icon="OBJECT_DATA")
        col = layout.column(align=True)
        col.prop(obj, "location")
        col.prop(obj, "rotation_euler")
        col.prop(obj, "scale")

    def execute(self, context):
        return {"FINISHED"}


classes = (ALEC_OT_transform_dialog,)
