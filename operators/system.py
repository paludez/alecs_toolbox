import bpy


class ALEC_OT_menu_dispatcher(bpy.types.Operator):
    """Shows a different menu based on the context (Object/Edit mode)"""

    bl_idname = "alec.menu_dispatcher"
    bl_label = "Menu Dispatcher"

    def execute(self, context):
        if context.mode == "EDIT_MESH":
            bpy.ops.wm.call_menu_pie(name="ALEC_MT_edit_menu")
        elif context.mode == "EDIT_CURVE":
            bpy.ops.wm.call_menu_pie(name="ALEC_MT_edit_curve_menu")
        else:
            bpy.ops.wm.call_menu_pie(name="ALEC_MT_object_menu")
        return {"FINISHED"}


class ALEC_OT_toggle_global_local_orientation(bpy.types.Operator):
    """Toggle transform orientation between Global and Local"""

    bl_idname = "alec.toggle_global_local_orientation"
    bl_label = "Toggle Global/Local Orientation"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ..modules import notice_overlay

        slot = context.scene.transform_orientation_slots[0]
        slot.type = "LOCAL" if slot.type == "GLOBAL" else "GLOBAL"
        notice_overlay.show_notice(slot.type.title())
        return {"FINISHED"}


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
            self.report({"WARNING"}, "No active window/screen")
            return {"CANCELLED"}

        if not area or area.type != "VIEW_3D":
            area = next((a for a in screen.areas if a.type == "VIEW_3D"), None)
            if area is None:
                self.report({"WARNING"}, "No 3D View available")
                return {"CANCELLED"}

        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        space = area.spaces.active
        if region is None or space is None:
            self.report({"WARNING"}, "No 3D View window region")
            return {"CANCELLED"}

        try:
            with bpy.context.temp_override(
                window=win,
                screen=screen,
                area=area,
                region=region,
                space_data=space,
            ):
                if self.__class__._next_is_selected:
                    bpy.ops.view3d.view_selected("EXEC_DEFAULT")
                else:
                    bpy.ops.view3d.view_all("EXEC_DEFAULT", center=False)
        except RuntimeError as exc:
            self.report({"WARNING"}, f"Frame toggle failed: {exc}")
            return {"CANCELLED"}

        self.__class__._next_is_selected = not self.__class__._next_is_selected
        return {"FINISHED"}


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
        sidebar_open = bool(getattr(space, "show_region_ui", False))
        cur = (
            getattr(ui_region, "active_panel_category", None) if ui_region else None
        )

        if sidebar_open and cur == self._CATEGORY:
            space.show_region_ui = False
            area.tag_redraw()
            return {"FINISHED"}

        space.show_region_ui = True
        category = self._CATEGORY
        if ui_region is not None and hasattr(ui_region, "active_panel_category"):
            try:
                ui_region.active_panel_category = category
            except Exception:
                pass

        area.tag_redraw()

        def apply_category():
            ar = area
            if ar is None or ar.type != "VIEW_3D":
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
    ALEC_OT_toggle_global_local_orientation,
    ALEC_OT_view_selected_safe,
    ALEC_OT_open_alec_panel,
)
