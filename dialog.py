
classes = [
    ALEC_OT_align_dialog,
    ALEC_OT_modify_material_slot,
    ALEC_OT_material_apply_operation,
    ALEC_OT_material_linker,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)