import bpy


def _area_under_mouse(context, event):
    win = context.window
    if not win or not win.screen:
        return None
    mx, my = event.mouse_x, event.mouse_y
    for area in win.screen.areas:
        if area.x <= mx < area.x + area.width and area.y <= my < area.y + area.height:
            return area
    return None


def _schedule_area_update(fn) -> None:
    """Run area type/ui_type changes next frame (avoids HUD region assert on switch)."""

    def _deferred():
        fn()
        return None

    bpy.app.timers.register(_deferred, first_interval=0.0)


def _set_area_view3d(area) -> None:
    if area.type != "VIEW_3D":
        area.type = "VIEW_3D"


def _set_area_shader(area, mode: str, context) -> None:
    if area.type != "NODE_EDITOR":
        area.type = "NODE_EDITOR"
    if getattr(area, "ui_type", None) != "ShaderNodeTree":
        area.ui_type = "ShaderNodeTree"
    space = area.spaces.active
    if space and space.type == "NODE_EDITOR":
        space.shader_type = mode
    if mode == "WORLD":
        world = context.scene.world
        if not world:
            world = bpy.data.worlds.new("World")
            context.scene.world = world
        if not world.use_nodes:
            world.use_nodes = True


def _set_area_uv(area) -> None:
    if area.type != "IMAGE_EDITOR":
        area.type = "IMAGE_EDITOR"
    if getattr(area, "ui_type", None) != "UV":
        area.ui_type = "UV"


class ALEC_OT_menu_dispatcher(bpy.types.Operator):
    """Shows a different menu based on the context (Object/Edit mode)"""
    bl_idname = "alec.menu_dispatcher"
    bl_label = "Menu Dispatcher"

    def execute(self, context):
        if context.mode == 'EDIT_MESH':
            bpy.ops.wm.call_menu_pie(name='ALEC_MT_edit_menu')
        elif context.mode == 'EDIT_CURVE':
            bpy.ops.wm.call_menu_pie(name='ALEC_MT_edit_curve_menu')
        else:
            bpy.ops.wm.call_menu_pie(name='ALEC_MT_object_menu')
        return {'FINISHED'}


class ALEC_OT_set_area_view3d_under_mouse(bpy.types.Operator):
    """Set the editor under mouse to 3D View"""
    bl_idname = "alec.set_area_view3d_under_mouse"
    bl_label = "Set Area To 3D View"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        if not context.window or not context.window.screen:
            self.report({'WARNING'}, "No active window/screen")
            return {'CANCELLED'}
        target_area = _area_under_mouse(context, event)
        if target_area is None:
            self.report({'WARNING'}, "No area under mouse")
            return {'CANCELLED'}
        area_ref = target_area
        _schedule_area_update(lambda: _set_area_view3d(area_ref))
        return {'FINISHED'}

class ALEC_OT_set_area_shader_under_mouse(bpy.types.Operator):
    """Set the editor under mouse to Shader Editor"""
    bl_idname = "alec.set_area_shader_under_mouse"
    bl_label = "Set Area To Shader Editor"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        items=[('OBJECT', "Object", ""), ('WORLD', "World", "")]
    ) # type: ignore

    def invoke(self, context, event):
        if not context.window or not context.window.screen:
            self.report({'WARNING'}, "No active window/screen")
            return {'CANCELLED'}
        target_area = _area_under_mouse(context, event)
        if target_area is None:
            self.report({'WARNING'}, "No area under mouse")
            return {'CANCELLED'}
        area_ref = target_area
        mode = self.mode
        _schedule_area_update(lambda: _set_area_shader(area_ref, mode, context))
        return {'FINISHED'}


class ALEC_OT_set_area_uv_under_mouse(bpy.types.Operator):
    """Set the editor under mouse to UV Editor"""
    bl_idname = "alec.set_area_uv_under_mouse"
    bl_label = "Set Area To UV Editor"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        if not context.window or not context.window.screen:
            self.report({'WARNING'}, "No active window/screen")
            return {'CANCELLED'}
        target_area = _area_under_mouse(context, event)
        if target_area is None:
            self.report({'WARNING'}, "No area under mouse")
            return {'CANCELLED'}
        area_ref = target_area
        _schedule_area_update(lambda: _set_area_uv(area_ref))
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


class ALEC_OT_toggle_global_local_orientation(bpy.types.Operator):
    """Toggle transform orientation between Global and Local"""
    bl_idname = "alec.toggle_global_local_orientation"
    bl_label = "Toggle Global/Local Orientation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ..modules import notice_overlay

        slot = context.scene.transform_orientation_slots[0]
        slot.type = 'LOCAL' if slot.type == 'GLOBAL' else 'GLOBAL'
        notice_overlay.show_notice(slot.type.title())
        return {'FINISHED'}


class ALEC_OT_view_selected_safe(bpy.types.Operator):
    """Toggle frame selected / frame all in a safe VIEW_3D context"""
    bl_idname = "alec.view_selected_safe"
    bl_label = "Frame Selected/All (Safe Toggle)"
    _next_is_selected = True

    def execute(self, context):
        win = context.window
        screen = context.screen
        area = context.area

        if not win or not screen:
            self.report({'WARNING'}, "No active window/screen")
            return {'CANCELLED'}

        if not area or area.type != 'VIEW_3D':
            area = next((a for a in screen.areas if a.type == 'VIEW_3D'), None)
            if area is None:
                self.report({'WARNING'}, "No 3D View available")
                return {'CANCELLED'}

        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        space = area.spaces.active
        if region is None or space is None:
            self.report({'WARNING'}, "No 3D View window region")
            return {'CANCELLED'}

        try:
            with bpy.context.temp_override(
                window=win,
                screen=screen,
                area=area,
                region=region,
                space_data=space,
            ):
                if self.__class__._next_is_selected:
                    bpy.ops.view3d.view_selected('EXEC_DEFAULT')
                else:
                    bpy.ops.view3d.view_all('EXEC_DEFAULT', center=False)
        except RuntimeError as exc:
            self.report({'WARNING'}, f"Frame toggle failed: {exc}")
            return {'CANCELLED'}

        self.__class__._next_is_selected = not self.__class__._next_is_selected
        return {'FINISHED'}


class ALEC_OT_open_alec_panel(bpy.types.Operator):
    """Open sidebar and jump to Alec tab; close sidebar if Alec tab is already visible."""

    bl_idname = "alec.open_alec_panel"
    bl_label = "Open Alec Panel"
    bl_options = set()

    _CATEGORY = "Alec"

    @classmethod
    def poll(cls, context):
        return getattr(context, "screen", None) is not None

    def execute(self, context):
        screen = context.screen
        if not screen:
            return {"CANCELLED"}

        area = context.area
        if area is None or area.type != "VIEW_3D":
            area = next((a for a in screen.areas if a.type == "VIEW_3D"), None)
        if area is None:
            return {"CANCELLED"}

        space = area.spaces.active
        if space is None or space.type != "VIEW_3D":
            return {"CANCELLED"}

        ui_region = next((r for r in area.regions if r.type == "UI"), None)
        sidebar_open = bool(ui_region and ui_region.width > 1)
        cur = (
            getattr(ui_region, "active_panel_category", None) if ui_region else None
        )

        if sidebar_open and cur == self._CATEGORY:
            if hasattr(space, "show_region_ui"):
                space.show_region_ui = False
            area.tag_redraw()
            return {"FINISHED"}

        if hasattr(space, "show_region_ui"):
            space.show_region_ui = True
        area.tag_redraw()

        category = self._CATEGORY

        def apply_category():
            ctx = bpy.context
            ar = ctx.area
            if ar is None or ar.type != "VIEW_3D":
                ar = next(
                    (a for a in ctx.screen.areas if a.type == "VIEW_3D"), None
                )
            if ar is None:
                return None
            ui = next((r for r in ar.regions if r.type == "UI"), None)
            if ui is not None and hasattr(ui, "active_panel_category"):
                try:
                    ui.active_panel_category = category
                except Exception:
                    pass
            ar.tag_redraw()
            return None

        bpy.app.timers.register(apply_category, first_interval=0)
        return {"FINISHED"}


classes = (
    ALEC_OT_menu_dispatcher,
    ALEC_OT_set_area_view3d_under_mouse,
    ALEC_OT_set_area_shader_under_mouse,
    ALEC_OT_set_area_uv_under_mouse,
    ALEC_OT_floating_shader_editor,
    ALEC_OT_toggle_global_local_orientation,
    ALEC_OT_view_selected_safe,
    ALEC_OT_open_alec_panel,
)
