# Operators for material management
import bpy

class ALEC_OT_assign_gray_material(bpy.types.Operator):
    """Create and assign a 70% Gray material to selected objects"""
    bl_idname = "alec.assign_gray_material"
    bl_label = "Assign Gray Material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mat_name = "Gray"
        # Check if material exists, otherwise create it
        if mat_name in bpy.data.materials:
            mat = bpy.data.materials[mat_name]
        else:
            mat = bpy.data.materials.new(name=mat_name)
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                val = 0.7
                bsdf.inputs['Base Color'].default_value = (val, val, val, 1.0)
        
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                if not obj.data.materials:
                    obj.data.materials.append(mat)
                else:
                    obj.material_slots[obj.active_material_index].material = mat
        return {'FINISHED'}

class ALEC_OT_remove_orphan_materials(bpy.types.Operator):
    """Remove materials that have 0 users"""
    bl_idname = "alec.remove_orphan_materials"
    bl_label = "Remove Unused Materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        to_remove = [m for m in bpy.data.materials if m.users == 0 and not m.use_fake_user]
        count = len(to_remove)
        for m in to_remove:
            bpy.data.materials.remove(m)
        self.report({'INFO'}, f"Removed {count} materials")
        return {'FINISHED'}

class ALEC_OT_select_material_users(bpy.types.Operator):
    """Select all objects in the scene that use the active material"""
    bl_idname = "alec.select_material_users"
    bl_label = "Select Users"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.active_material is not None

    def execute(self, context):
        mat = context.active_object.active_material
        
        # Deselect all first
        bpy.ops.object.select_all(action='DESELECT')

        if mat:
            for obj in context.scene.objects:
                if obj.type == 'MESH' and any(s.material == mat for s in obj.material_slots):
                    obj.select_set(True)
        return {'FINISHED'}

classes = [
    ALEC_OT_assign_gray_material,
    ALEC_OT_remove_orphan_materials,
    ALEC_OT_select_material_users,
]
