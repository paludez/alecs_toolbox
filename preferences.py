import bpy
from bpy.props import BoolProperty, IntProperty
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


class ALEC_AddonPreferences(AddonPreferences):
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
        name="Alt+Q — Alec menu (3D View)",
        description="Open the Alec radial / menu dispatcher in the 3D View.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_alt_rmb_quad: BoolProperty(
        name="Alt+Right Mouse — Quad pie menu",
        description=(
            "Pie menu on Alt+right-click in the 3D View; "
            "shader / outliner pies in their editors."
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
        description="Wireframe + X-Ray; press again for Solid.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_f4_overlay_wireframes: BoolProperty(
        name="F4 — Toggle overlay wireframes",
        description="Overlay wireframes on/off in any shading mode.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_alt_f3_wireframe_color: BoolProperty(
        name="Alt+F3 — Cycle wireframe color",
        description="Cycle wireframe color type: Theme, Object, Random.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_ctrl_alt_f3_color_type: BoolProperty(
        name="Ctrl+Alt+F3 — Cycle object color",
        description=(
            "Cycle color type: Material, Object, Random, Attribute, Texture, Custom."
        ),
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_f5_rendered: BoolProperty(
        name="F5 — Toggle Rendered shading",
        description="Rendered preview; press again for Solid.",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_f6_material: BoolProperty(
        name="F6 — Toggle Material Preview",
        description="Material Preview; press again for Solid.",
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
    shortcut_n_alec_panel: BoolProperty(
        name="N — Open Alec panel (replaces default sidebar toggle)",
        description=(
            "N opens sidebar and jumps to Alec tab; "
            "if Alec tab is already visible, N closes the sidebar."
        ),
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_alt_w_light_energy_modal: BoolProperty(
        name="Alt+W — Light / Camera / Empty (modal)",
        description=(
            "Active object only: Light energy, Empty display size, or Camera focal length."
        ),
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
        name="Alt+E / Shift+Alt+E — Extrude (Edit Mesh / Curves / Armature / Surface)",
        description=(
            "Edit Mesh: Alt+E extrude along normal; Shift+Alt+E extrude menu. "
            "Edit Curve (legacy): Alt+E → curve.extrude_move. "
            "Edit Curves (hair): Alt+E → curves.extrude_move. "
            "Edit Armature: Alt+E → armature.extrude_move. "
            "Edit Surface: Alt+E → surface.extrude_move. Only when E is Rotate."
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

    shortcut_alt_a_align_origins: BoolProperty(
        name="Alt+A — Align (Origins + rotation)",
        description=(
            "Object Mode: align origins to active and match rotation "
            "(same as Origins preset with Alt held)."
        ),
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_ctrl_alt_a_align_dialog: BoolProperty(
        name="Ctrl+Alt+A — Align (dialog)",
        description="Object Mode: same as the Align button (full redo panel).",
        default=True,
        update=_refresh_addon_keymaps,
    )

    draw_mesh_snap_max_verts_per_object: IntProperty(
        name="Max vertices per object (world snap)",
        description=(
            "Draw Mesh Edges: world snap ([W]) skips mesh objects whose evaluated "
            "vertex count exceeds this limit."
        ),
        default=12_000,
        min=1_000,
        max=500_000,
    )
    draw_mesh_snap_max_verts_total: IntProperty(
        name="Max vertices total (world snap)",
        description=(
            "Draw Mesh Edges: cap on how many vertices are indexed for world snap "
            "across the whole scene (dense scenes show a limited notice)."
        ),
        default=40_000,
        min=5_000,
        max=2_000_000,
    )
    draw_mesh_snap_kdtree_min_elements: IntProperty(
        name="KD-tree threshold (object snap)",
        description=(
            "Draw Mesh Edges: use screen-space KD-tree acceleration on the drawn mesh "
            "when vert+edge count is at least this value."
        ),
        default=256,
        min=32,
        max=100_000,
    )

    def draw(self, context):
        layout = self.layout

        box_shading = layout.box()
        box_shading.label(text="Shading / viewport")
        col_shading = box_shading.column(align=True)
        col_shading.prop(self, "shortcut_f1_search")
        col_shading.prop(self, "shortcut_f3_wireframe_xray")
        col_shading.prop(self, "shortcut_f4_overlay_wireframes")
        col_shading.prop(self, "shortcut_alt_f3_wireframe_color")
        col_shading.prop(self, "shortcut_ctrl_alt_f3_color_type")
        col_shading.prop(self, "shortcut_f5_rendered")
        col_shading.prop(self, "shortcut_f6_material")

        box_nav = layout.box()
        box_nav.label(text="3D Navigation")
        col_nav = box_nav.column(align=True)
        col_nav.prop(self, "shortcut_c_camera")
        col_nav.prop(self, "shortcut_grave_isolate")
        col_nav.prop(self, "shortcut_alt_grave_orientation")
        col_nav.prop(self, "shortcut_ctrl_grave_frame_selected")

        box_menu = layout.box()
        box_menu.label(text="Menu / Panel")
        col_menu = box_menu.column(align=True)
        col_menu.prop(self, "shortcut_q_alt_menu")
        col_menu.prop(self, "shortcut_alt_rmb_quad")
        col_menu.prop(self, "shortcut_n_alec_panel")

        box_window = layout.box()
        box_window.label(text="Window areas")
        col_window = box_window.column(align=True)
        col_window.prop(self, "shortcut_alt_1_view3d_under_mouse")
        col_window.prop(self, "shortcut_alt_2_shader_object_under_mouse")
        col_window.prop(self, "shortcut_alt_3_shader_world_under_mouse")
        col_window.prop(self, "shortcut_alt_4_uv_under_mouse")

        box_other = layout.box()
        box_other.label(text="Other")
        col_other = box_other.column(align=True)
        col_other.prop(self, "shortcut_alt_w_light_energy_modal")
        col_other.prop(self, "shortcut_grave_outliner_show_active")

        box_toolbar = layout.box()
        box_toolbar.label(text="Toolbar & extrude (W / E / Alt+E / Shift+Alt+E)")
        col_toolbar = box_toolbar.column(align=True)
        col_toolbar.prop(self, "shortcut_w_move_tool")
        col_toolbar.prop(self, "shortcut_e_rotate_tool")
        col_toolbar.prop(self, "shortcut_alt_e_extrude")

        box_mesh = layout.box()
        box_mesh.label(text="Mesh")
        box_mesh.prop(self, "use_max_style_mesh_keys")
        box_mesh.prop(self, "shortcut_key_4_auto_linked")

        box_hide = layout.box()
        box_hide.label(text="Object hide (viewport + render)")
        box_hide.prop(self, "use_object_hide_sync_render_shortcuts")
        col_hide = box_hide.column(align=True)
        col_hide.enabled = self.use_object_hide_sync_render_shortcuts
        col_hide.prop(self, "shortcut_hide_h_sync_render")
        col_hide.prop(self, "shortcut_hide_shift_h_sync_render")
        col_hide.prop(self, "shortcut_hide_alt_h_sync_render")

        box_align = layout.box()
        box_align.label(text="Align (Object Mode)")
        col_align = box_align.column(align=True)
        col_align.prop(self, "shortcut_alt_a_align_origins")
        col_align.prop(self, "shortcut_ctrl_alt_a_align_dialog")

        box_snap = layout.box()
        box_snap.label(text="Draw Mesh Edges (snap)")
        col_snap = box_snap.column(align=True)
        col_snap.prop(self, "draw_mesh_snap_max_verts_per_object")
        col_snap.prop(self, "draw_mesh_snap_max_verts_total")
        col_snap.prop(self, "draw_mesh_snap_kdtree_min_elements")


classes = (ALEC_AddonPreferences,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
