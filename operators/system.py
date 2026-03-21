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
        elif context.mode == 'EDIT_CURVE':
            bpy.ops.wm.call_menu_pie(name='ALEC_MT_edit_curve_menu')
        else:
            bpy.ops.wm.call_menu_pie(name='ALEC_MT_object_menu')
        return {'FINISHED'}

class ALEC_OT_floating_shader_editor(bpy.types.Operator):
    """Open a floating Shader Editor window"""
    bl_idname = "alec.floating_shader_editor"
    bl_label = "Floating Shader Editor"

    mode: bpy.props.EnumProperty(
        items=[('OBJECT', "Object", ""), ('WORLD', "World", "")]
    ) # type: ignore

    def execute(self, context):
        wm = context.window_manager
        existing_windows = {w for w in wm.windows}

        bpy.ops.wm.window_new()

        new_windows = [w for w in wm.windows if w not in existing_windows]
        win = new_windows[0] if new_windows else bpy.context.window
        if not win:
            return {'CANCELLED'}

        screen = win.screen
        if not screen.areas:
            return {'CANCELLED'}

        area = next(
            (a for a in screen.areas if a.type in {'NODE_EDITOR', 'VIEW_3D', 'IMAGE_EDITOR'}),
            screen.areas[0],
        )
        area.type = 'NODE_EDITOR'
        area.ui_type = 'ShaderNodeTree'

        space = area.spaces.active
        if space and space.type == 'NODE_EDITOR':
            space.shader_type = self.mode

        has_nodes = False
        if self.mode == 'OBJECT':
            obj = context.active_object
            mat = obj.active_material if obj else None
            nt = mat.node_tree if mat and mat.use_nodes else None
            has_nodes = bool(nt and nt.nodes)
        elif self.mode == 'WORLD':
            world = context.scene.world
            if not world:
                world = bpy.data.worlds.new("World")
                context.scene.world = world
            if not world.use_nodes:
                world.use_nodes = True
            nt = world.node_tree
            has_nodes = bool(nt and nt.nodes)

        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        if has_nodes and region and space and space.type == 'NODE_EDITOR':
            try:
                with bpy.context.temp_override(
                    window=win,
                    screen=screen,
                    area=area,
                    region=region,
                    space_data=space,
                ):
                    bpy.ops.node.view_all()
            except RuntimeError:
                pass
        
        return {'FINISHED'}

classes = [
    ALEC_OT_menu_dispatcher,
    ALEC_OT_floating_shader_editor,
]
