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

class ALEC_OT_square_pixels(bpy.types.Operator):
    """Make the selected plane have square pixels via UV mapping"""
    bl_idname = "alec.square_pixels"
    bl_label = "Square Pixels"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        import bmesh
        obj = context.active_object

        img_w, img_h = 1.0, 1.0
        mat = obj.active_material
        if mat and mat.use_nodes:
            tree = mat.node_tree
            active_node = tree.nodes.active
            
            target_node = None
            if active_node and active_node.type == 'TEX_IMAGE' and active_node.image:
                target_node = active_node
            else:
                target_node = next((n for n in tree.nodes if n.type == 'TEX_IMAGE' and n.image), None)
                
            if target_node:
                img_w, img_h = target_node.image.size

        was_in_object = (context.mode != 'EDIT_MESH')
        if was_in_object:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            
        try:
            bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.0)
        except RuntimeError:
            self.report({'WARNING'}, "Select faces to unwrap.")
            if was_in_object:
                bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}
        
        if img_w > 0 and img_h > 0:
            aspect = img_w / img_h
            
            bm = bmesh.from_edit_mesh(obj.data)
            uv_layer = bm.loops.layers.uv.verify()
            
            min_v, max_v = float('inf'), float('-inf')
            has_sel = False
            for face in bm.faces:
                if face.select:
                    for loop in face.loops:
                        v = loop[uv_layer].uv[1]
                        min_v = min(min_v, v)
                        max_v = max(max_v, v)
                        has_sel = True
                        
            if has_sel:
                center_v = (min_v + max_v) / 2.0
                for face in bm.faces:
                    if face.select:
                        for loop in face.loops:
                            loop[uv_layer].uv[1] = center_v + (loop[uv_layer].uv[1] - center_v) * aspect

                min_u, max_u = float('inf'), float('-inf')
                min_v, max_v = float('inf'), float('-inf')
                for face in bm.faces:
                    if face.select:
                        for loop in face.loops:
                            u, v = loop[uv_layer].uv
                            min_u = min(min_u, u)
                            max_u = max(max_u, u)
                            min_v = min(min_v, v)
                            max_v = max(max_v, v)
                            
                uv_w = max_u - min_u
                uv_h = max_v - min_v
                
                if uv_w > 0 and uv_h > 0:
                    max_dim = max(uv_w, uv_h)
                    scale_fit = 1.0 / max_dim
                    
                    center_u = (min_u + max_u) / 2.0
                    center_v = (min_v + max_v) / 2.0
                    
                    for face in bm.faces:
                        if face.select:
                            for loop in face.loops:
                                u = loop[uv_layer].uv[0]
                                v = loop[uv_layer].uv[1]
                                
                                new_u = 0.5 + (u - center_u) * scale_fit
                                new_v = 0.5 + (v - center_v) * scale_fit
                                
                                loop[uv_layer].uv[0] = new_u
                                loop[uv_layer].uv[1] = new_v
                                
            bmesh.update_edit_mesh(obj.data)
            
        if was_in_object:
            bpy.ops.object.mode_set(mode='OBJECT')
            
        return {'FINISHED'}

classes = [
    ALEC_OT_load_material_image,
    ALEC_OT_square_pixels,
]
