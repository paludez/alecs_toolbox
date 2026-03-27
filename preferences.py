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
    shortcut_q_ctrl_alt_browser: BoolProperty(
        name="Ctrl+Alt+Q — Alec browser",
        description="Open the Alec browser menu (3D View + UV Editor).",
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
        name="Alt+E / Shift+Alt+E — Extrude (Edit Mesh)",
        description=(
            "Alt+E: view3d.edit_mesh_extrude_move_normal (extrude along normal). "
            "Shift+Alt+E: Extrude menu (VIEW3D_MT_edit_mesh_extrude). Only when E is Rotate."
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

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "use_max_style_mesh_keys")

        box = layout.box()
        box.label(text="Shortcuts (addon keymap)")
        col = box.column(align=True)
        col.prop(self, "shortcut_q_alt_menu")
        col.prop(self, "shortcut_q_ctrl_alt_browser")
        col.prop(self, "shortcut_alt_rmb_quad")
        col.prop(self, "shortcut_f1_search")
        col.prop(self, "shortcut_f3_wireframe_xray")
        col.prop(self, "shortcut_f4_overlay_wireframes")
        col.prop(self, "shortcut_f5_solid_rendered")

        box2 = layout.box()
        box2.label(text="Toolbar & extrude (W / E / Alt+E / Shift+Alt+E)")
        col2 = box2.column(align=True)
        col2.prop(self, "shortcut_w_move_tool")
        col2.prop(self, "shortcut_e_rotate_tool")
        col2.prop(self, "shortcut_alt_e_extrude")

        box3 = layout.box()
        box3.label(text="Mesh")
        box3.prop(self, "shortcut_key_4_auto_linked")


classes = (ALECS_TB_AddonPreferences,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
