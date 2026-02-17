import bpy

addon_keymaps = []


class ALEC_MT_menu_align(bpy.types.Menu):
    bl_label = "Align"

    def draw(self, context):
        layout = self.layout
        layout.operator("alec.quick_center", text="Quick Align OBJ_Centers", icon='PIVOT_BOUNDBOX')
        layout.operator("alec.quick_pivot", text="Quick Align OBJ_Origins", icon='OBJECT_ORIGIN')
        layout.operator("alec.align_dialog", text="Align Dialog", icon='PREFERENCES')



class ALEC_MT_menu_orientation(bpy.types.Menu):
    bl_label = "Orientation"

    def draw(self, context):
        layout = self.layout
        for value, label, icon in [
            ('GLOBAL', "Global", 'ORIENTATION_GLOBAL'),
            ('LOCAL', "Local", 'ORIENTATION_LOCAL'),
            ('NORMAL', "Normal", 'ORIENTATION_NORMAL'),
            ('GIMBAL', "Gimbal", 'ORIENTATION_GIMBAL'),
            ('VIEW', "View", 'ORIENTATION_VIEW'),
            ('CURSOR', "Cursor", 'ORIENTATION_CURSOR'),
            ('PARENT', "Parent", 'ORIENTATION_PARENT'),
        ]:
            op = layout.operator("wm.context_set_enum", text=label, icon=icon)
            op.data_path = "scene.transform_orientation_slots[0].type"
            op.value = value


class ALEC_MT_menu_pivot(bpy.types.Menu):
    bl_label = "Pivot Point"

    def draw(self, context):
        layout = self.layout
        for value, label, icon in [
            ('BOUNDING_BOX_CENTER', "Bounding Box Center", 'PIVOT_BOUNDBOX'),
            ('MEDIAN_POINT', "Median Point", 'PIVOT_MEDIAN'),
            ('ACTIVE_ELEMENT', "Active Element", 'PIVOT_ACTIVE'),
            ('CURSOR', "3D Cursor", 'PIVOT_CURSOR'),
            ('INDIVIDUAL_ORIGINS', "Individual Origins", 'PIVOT_INDIVIDUAL'),
        ]:
            op = layout.operator("wm.context_set_enum", text=label, icon=icon)
            op.data_path = "tool_settings.transform_pivot_point"
            op.value = value

        layout.separator()
        layout.prop(context.tool_settings, "use_transform_pivot_point_align", text="Only Locations")
        
        layout.separator()
        layout.operator("alec.cursor_to_selected", icon='CURSOR')
        layout.operator("alec.cursor_to_geometry_center", icon='CURSOR')

        layout.separator()
        op = layout.operator("object.origin_set", text="Origin to BOUNDS Center", icon='EMPTY_DATA')
        op.type = 'ORIGIN_GEOMETRY'
        op.center = 'BOUNDS'
        op = layout.operator("object.origin_set", text="Origin to Cursor POS", icon='ORIENTATION_CURSOR')
        op.type = 'ORIGIN_CURSOR'
        op.center = 'BOUNDS'
        op = layout.operator("alec.origin_to_cursor", text="Origin to Cursor POS&ROT", icon='ORIENTATION_GIMBAL')


class ALEC_MT_menu_misc(bpy.types.Menu):
    bl_label = "Misc"

    def draw(self, context):
        layout = self.layout
        layout.operator("alec.bbox_dialog", icon='MESH_CUBE')
        layout.operator("alec.group", icon='MESH_PLANE')
        layout.operator("alec.group_active", icon='MOD_SUBSURF')
        layout.operator("alec.ungroup", icon='MOD_EXPLODE')
        layout.operator("object.make_links_data", text="Apply Material", icon='MATERIAL').type = 'MATERIAL'
        layout.operator("alec.material_linker", text="Linker Materiale", icon='LINKED')


class ALEC_MT_menu_main(bpy.types.Menu):
    bl_label = "Alec's Toolbox"

    def draw(self, context):
        layout = self.layout
        layout.menu("ALEC_MT_menu_align", icon='LIGHTPROBE_VOLUME')
        layout.menu("ALEC_MT_menu_orientation", icon='ORIENTATION_GIMBAL')
        layout.menu("ALEC_MT_menu_pivot", icon='CON_PIVOT')
        layout.menu("ALEC_MT_menu_misc", icon='FILE_SOUND')


classes = [
    ALEC_MT_menu_align,
    ALEC_MT_menu_orientation,
    ALEC_MT_menu_pivot,
    ALEC_MT_menu_misc,
    ALEC_MT_menu_main,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    kc = bpy.context.window_manager.keyconfigs.addon
    km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
    kmi = km.keymap_items.new('wm.call_menu', 'Q', 'PRESS', alt=True)
    kmi.properties.name = "ALEC_MT_menu_main"
    addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)