# Operators for UV editing
import bpy

class ALEC_OT_load_material_image(bpy.types.Operator):
    """Load image from active material's Base Color into the editor"""
    bl_idname = "alec.load_material_image"
    bl_label = "Load Material Image"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not (context.area.type == 'IMAGE_EDITOR' and context.active_object):
            return False
        
        mat = context.active_object.active_material
        if not mat or not mat.use_nodes:
            return False
        
        bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not (bsdf and bsdf.inputs['Base Color'].is_linked):
            return False
            
        node = bsdf.inputs['Base Color'].links[0].from_node
        return node.type == 'TEX_IMAGE' and node.image is not None

    def execute(self, context):
        mat = context.active_object.active_material
        bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        node = bsdf.inputs['Base Color'].links[0].from_node
        context.space_data.image = node.image
        return {'FINISHED'}

classes = [
    ALEC_OT_load_material_image,
]
