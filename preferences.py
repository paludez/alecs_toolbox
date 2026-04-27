import bpy
from bpy.props import BoolProperty
from bpy.types import AddonPreferences


def _refresh_addon_keymaps(_self, _context):
    try:
        from . import shortcuts

        shortcuts.refresh_keymaps_from_prefs()
    except Exception:
        pass


def _addon_id() -> str:
    # e.g. "alecs_toolbox" or "bl_ext.vscode_development.alecs_toolbox"
    if __package__:
        return __package__
    return __name__.rsplit(".", 1)[0]


def prefs():
    return bpy.context.preferences.addons[_addon_id()].preferences


def _on_mesh_keys_toggle(self, _context):
    from . import shortcuts
    shortcuts.set_mesh_max_keys(self.use_max_style_mesh_keys)


class ALECS_TB_AddonPreferences(AddonPreferences):
    bl_idname = _addon_id()

    use_max_style_mesh_keys: BoolProperty(
        name="Max-style mesh keys (1–3, 5)",
        description=(
            "In Object or Edit mesh: 1 Vertex, 2 Edge, 3 Face (Tab not required from Object); "
            "5: grow along connected open/boundary edges. "
            "Key 4 (auto-linked) is a separate shortcut option below."
        ),
        default=True,
        update=_on_mesh_keys_toggle,
    )

    shortcut_q_alt_menu: BoolProperty(
        name="Alt+Q — Alec menu (3D View + UV Editor)",
        description="Open the Alec radial / menu dispatcher.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_alt_rmb_quad: BoolProperty(
        name="Alt+Right Mouse — Quad pie menu",
        description=(
            "Pie menu on Alt+right-click in the 3D View; "
            "UV Alec pie in the UV / Image Editor; "
            "Triplanar + NA Arrange in the Shader Editor (Object / World)."
        ),
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_f1_search: BoolProperty(
        name="F1 — Operator search (Menu Search)",
        description="Same as default Blender F3: wm.search_menu.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_f3_wireframe_xray: BoolProperty(
        name="F3 — Toggle wireframe + X-Ray (viewport)",
        description="Toggle wireframe shading + X-Ray; second press restores previous shading.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_f4_overlay_wireframes: BoolProperty(
        name="F4 — Toggle overlay wireframes",
        description="Toggle Viewport Overlays » Wireframe.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_f5_solid_rendered: BoolProperty(
        name="F5 — Toggle Solid / Rendered shading",
        description="Switch viewport shading between Solid and Rendered preview.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_c_camera: BoolProperty(
        name="C — Camera view",
        description="Switch 3D View to active camera view.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_grave_isolate: BoolProperty(
        name="` — Isolate (Local View)",
        description="Toggle Local View isolate in 3D View.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_alt_grave_orientation: BoolProperty(
        name="Alt+` — Toggle Global/Local orientation",
        description="Toggle transform orientation between Global and Local.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_ctrl_grave_frame_selected: BoolProperty(
        name="Ctrl+` — Toggle Frame Selected / Frame All",
        description="Alternate between period (.) frame selected and Home frame all.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_grave_outliner_show_active: BoolProperty(
        name="` — Outliner Show Active (same as . in Outliner)",
        description="In Outliner, run Show Active (equivalent to period key there).",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_alt_1_view3d_under_mouse: BoolProperty(
        name="Alt+1 — Set area under mouse to 3D View",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_alt_2_shader_object_under_mouse: BoolProperty(
        name="Alt+2 — Set area under mouse to Shader (Object)",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_alt_3_shader_world_under_mouse: BoolProperty(
        name="Alt+3 — Set area under mouse to Shader (World)",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_alt_4_uv_under_mouse: BoolProperty(
        name="Alt+4 — Set area under mouse to UV Editor",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_alt_w_light_energy_modal: BoolProperty(
        name="Alt+W — Light/Empty value drag (modal)",
        description="If active is Light: energy; Empty: display size; Camera: focal length. Drag left/right or type value.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_w_move_tool: BoolProperty(
        name="W — Move tool (toolbar)",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_e_rotate_tool: BoolProperty(
        name="E — Rotate tool (toolbar)",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_alt_e_extrude: BoolProperty(
        name="Alt+E / Shift+Alt+E — Extrude (Edit Mesh / Curves)",
        description=(
            "Edit Mesh: Alt+E extrude along normal; Shift+Alt+E extrude menu. "
            "Edit Curve (legacy): Alt+E → curve.extrude_move. "
            "Edit Curves (hair): Alt+E → curves.extrude_move. Only when E is Rotate."
        ),
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_key_4_auto_linked: BoolProperty(
        name="4 — Auto-linked island toggle (Edit Mesh)",
        description="Toggle auto-linked island selection mode.",
        default=True,
        update=_refresh_addon_keymaps,
    )

    use_object_hide_sync_render_shortcuts: BoolProperty(
        name="Object Mode: H / Shift+H / Alt+H also affect render",
        description=(
            "When enabled, addon keymap (Object Mode) overrides default hide keys: "
            "Hide Selected / Unselected also sets hide_render; Reveal clears hide_render "
            "for objects that become visible in the viewport. Does not apply in Edit Mesh."
        ),
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_hide_h_sync_render: BoolProperty(
        name="H — Hide Selected (viewport + render)",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_hide_shift_h_sync_render: BoolProperty(
        name="Shift+H — Hide Unselected (viewport + render)",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_hide_alt_h_sync_render: BoolProperty(
        name="Alt+H — Reveal hidden (viewport + render)",
        default=True,
        update=_refresh_addon_keymaps,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "use_max_style_mesh_keys")

        box = layout.box()
        box.label(text="Shortcuts (addon keymap)")
        col = box.column(align=True)
        col.prop(self, "shortcut_q_alt_menu")
        col.prop(self, "shortcut_alt_rmb_quad")
        col.prop(self, "shortcut_f1_search")
        col.prop(self, "shortcut_f3_wireframe_xray")
        col.prop(self, "shortcut_f4_overlay_wireframes")
        col.prop(self, "shortcut_f5_solid_rendered")
        col.prop(self, "shortcut_c_camera")
        col.prop(self, "shortcut_grave_isolate")
        col.prop(self, "shortcut_alt_grave_orientation")
        col.prop(self, "shortcut_ctrl_grave_frame_selected")
        col.prop(self, "shortcut_grave_outliner_show_active")
        col.prop(self, "shortcut_alt_1_view3d_under_mouse")
        col.prop(self, "shortcut_alt_2_shader_object_under_mouse")
        col.prop(self, "shortcut_alt_3_shader_world_under_mouse")
        col.prop(self, "shortcut_alt_4_uv_under_mouse")
        col.prop(self, "shortcut_alt_w_light_energy_modal")

        box2 = layout.box()
        box2.label(text="Toolbar & extrude (W / E / Alt+E / Shift+Alt+E)")
        col2 = box2.column(align=True)
        col2.prop(self, "shortcut_w_move_tool")
        col2.prop(self, "shortcut_e_rotate_tool")
        col2.prop(self, "shortcut_alt_e_extrude")

        box3 = layout.box()
        box3.label(text="Mesh")
        box3.prop(self, "shortcut_key_4_auto_linked")

        box4 = layout.box()
        box4.label(text="Object hide (viewport + render)")
        box4.prop(self, "use_object_hide_sync_render_shortcuts")
        col4 = box4.column(align=True)
        col4.enabled = self.use_object_hide_sync_render_shortcuts
        col4.prop(self, "shortcut_hide_h_sync_render")
        col4.prop(self, "shortcut_hide_shift_h_sync_render")
        col4.prop(self, "shortcut_hide_alt_h_sync_render")


classes = (ALECS_TB_AddonPreferences,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
