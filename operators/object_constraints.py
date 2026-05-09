import bpy


class ALEC_OT_track_to_active(bpy.types.Operator):
    bl_idname = "alec.track_to_active"
    bl_label = "Track To Active"
    bl_description = "Add a Track To constraint on each selected object, targeting the active object"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            return False
        target = context.active_object
        if target is None:
            return False
        return any(o is not target for o in context.selected_objects)

    def execute(self, context):
        target = context.active_object
        if target is None:
            return {"CANCELLED"}

        added = 0
        for obj in context.selected_objects:
            if obj is target:
                continue
            if obj.library is not None:
                self.report(
                    {"WARNING"},
                    'Skipped "{}" (linked datablock cannot be edited here)'.format(obj.name),
                )
                continue
            con = obj.constraints.new(type="TRACK_TO")
            con.target = target
            con.track_axis = "TRACK_NEGATIVE_Y"
            con.up_axis = "UP_Z"
            added += 1

        if added == 0:
            self.report({"ERROR"}, "No constraints added")
            return {"CANCELLED"}

        context.view_layer.update()
        return {"FINISHED"}


classes = (ALEC_OT_track_to_active,)
