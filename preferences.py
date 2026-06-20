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


def _on_workflow_pref_change(self, _context):
    if not self.apply_blender_workflow_defaults:
        return
    from .modules.blender_workflow_prefs import refresh_workflow_preferences

    refresh_workflow_preferences()


def _on_workflow_master_toggle(self, _context):
    from .modules.blender_workflow_prefs import (
        apply_workflow_preferences,
        revert_workflow_preferences,
    )

    if self.apply_blender_workflow_defaults:
        apply_workflow_preferences()
    else:
        revert_workflow_preferences()


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
    shortcut_ctrl_shift_f3_wireframe_color: BoolProperty(
        name="Ctrl+Shift+F3 — Cycle wireframe color",
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
    shortcut_alt_2_toggle_shader_object_world_under_mouse: BoolProperty(
        name="Alt+2 — Toggle area under mouse: Shader Editor (Object / World)",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_alt_3_toggle_uv_image_under_mouse: BoolProperty(
        name="Alt+3 — Toggle area under mouse: UV Editor / Image Viewer",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_alt_4_toggle_graph_dopesheet_under_mouse: BoolProperty(
        name="Alt+4 — Toggle area under mouse: Graph Editor (F-Curves) / Dope Sheet",
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_alt_f1_join_area_under_mouse: BoolProperty(
        name="Alt+F1 — Join area under mouse (interactive)",
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
    shortcut_alt_n_auto_key: BoolProperty(
        name="Alt+N — Toggle Auto Keying",
        description=(
            "Toggle record on transform (tool_settings.use_keyframe_insert_auto). "
            "Blender has no default shortcut; Edit Mesh keeps Alt+N for the normals menu."
        ),
        default=True,
        update=_refresh_addon_keymaps,
    )
    shortcut_shift_1234_timeline_nav: BoolProperty(
        name="Shift+1–4 — Begin / Prev key / Next key / End",
        description=(
            "Shift+1: scene/preview start; Shift+2: previous keyframe; "
            "Shift+3: next keyframe; Shift+4: scene/preview end. "
            "Edit Mesh keeps Shift+1–3 for select-mode extend."
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

    apply_blender_workflow_defaults: BoolProperty(
        name="Apply Blender workflow defaults",
        description=(
            "When checked, apply the options below to Blender preferences. "
            "Uncheck to restore previous values. Off by default."
        ),
        default=False,
        update=_on_workflow_master_toggle,
    )
    wf_hide_splash: BoolProperty(
        name="Hide splash screen",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_show_tooltips_python: BoolProperty(
        name="Python tooltips",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_show_number_arrows: BoolProperty(
        name="Numeric input arrows",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_show_statusbar_stats: BoolProperty(
        name="Scene statistics (status bar)",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_use_mouse_over_open: BoolProperty(
        name="Open on mouse over",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_open_toplevel_delay_one: BoolProperty(
        name="Top level open delay = 1",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_open_sublevel_delay_one: BoolProperty(
        name="Sub level open delay = 1",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_pie_animation_timeout_zero: BoolProperty(
        name="Pie menu animation timeout = 0",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_object_align_cursor: BoolProperty(
        name="Align to 3D Cursor (new objects)",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_show_only_selected_curve_keyframes: BoolProperty(
        name="Only show selected F-Curve keyframes",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_disable_fcurve_high_quality: BoolProperty(
        name="Disable F-Curve high quality drawing",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_fcurve_unselected_alpha: BoolProperty(
        name="F-Curve unselected opacity = 0",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_use_numeric_input_advanced: BoolProperty(
        name="Default to advanced numeric input",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_orbit_around_selection: BoolProperty(
        name="Orbit around selection",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_disable_auto_perspective: BoolProperty(
        name="Disable auto perspective",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_use_mouse_depth_navigate: BoolProperty(
        name="Auto depth (navigate)",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_use_zoom_to_mouse: BoolProperty(
        name="Zoom to mouse position",
        default=True,
        update=_on_workflow_pref_change,
    )
    wf_theme_box_inner_alpha_one: BoolProperty(
        name="Theme: Box inner alpha = 1.0",
        description=(
            "Preferences → Themes → User Interface → Box → Inner: set alpha to 1.0 "
            "(RGB unchanged)."
        ),
        default=True,
        update=_on_workflow_pref_change,
    )

    def draw(self, context):
        layout = self.layout

        box_shading = layout.box()
        box_shading.label(text="Shading / viewport")
        col_shading = box_shading.column(align=True)
        col_shading.prop(self, "shortcut_f1_search")
        col_shading.prop(self, "shortcut_f3_wireframe_xray")
        col_shading.prop(self, "shortcut_f4_overlay_wireframes")
        col_shading.prop(self, "shortcut_ctrl_shift_f3_wireframe_color")
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
        col_window.prop(self, "shortcut_alt_2_toggle_shader_object_world_under_mouse")
        col_window.prop(self, "shortcut_alt_3_toggle_uv_image_under_mouse")
        col_window.prop(self, "shortcut_alt_4_toggle_graph_dopesheet_under_mouse")
        col_window.prop(self, "shortcut_alt_f1_join_area_under_mouse")

        box_other = layout.box()
        box_other.label(text="Other")
        col_other = box_other.column(align=True)
        col_other.prop(self, "shortcut_alt_w_light_energy_modal")
        col_other.prop(self, "shortcut_alt_n_auto_key")
        col_other.prop(self, "shortcut_shift_1234_timeline_nav")
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

        box_workflow = layout.box()
        box_workflow.label(text="Blender workflow defaults")
        box_workflow.prop(self, "apply_blender_workflow_defaults")
        col_wf = box_workflow.column(align=True)
        col_wf.enabled = self.apply_blender_workflow_defaults

        box_wf_iface = col_wf.box()
        box_wf_iface.label(text="Interface")
        col_iface = box_wf_iface.column(align=True)
        col_iface.prop(self, "wf_hide_splash")
        col_iface.prop(self, "wf_show_tooltips_python")
        col_iface.prop(self, "wf_show_number_arrows")
        col_iface.prop(self, "wf_show_statusbar_stats")
        col_iface.prop(self, "wf_use_mouse_over_open")
        col_iface.prop(self, "wf_open_toplevel_delay_one")
        col_iface.prop(self, "wf_open_sublevel_delay_one")
        col_iface.prop(self, "wf_pie_animation_timeout_zero")

        box_wf_edit = col_wf.box()
        box_wf_edit.label(text="Editing")
        col_edit = box_wf_edit.column(align=True)
        col_edit.prop(self, "wf_object_align_cursor")
        col_edit.prop(self, "wf_show_only_selected_curve_keyframes")
        col_edit.prop(self, "wf_disable_fcurve_high_quality")
        col_edit.prop(self, "wf_fcurve_unselected_alpha")

        box_wf_input = col_wf.box()
        box_wf_input.label(text="Input")
        box_wf_input.prop(self, "wf_use_numeric_input_advanced")

        box_wf_nav = col_wf.box()
        box_wf_nav.label(text="Navigation")
        col_nav = box_wf_nav.column(align=True)
        col_nav.prop(self, "wf_orbit_around_selection")
        col_nav.prop(self, "wf_disable_auto_perspective")
        col_nav.prop(self, "wf_use_mouse_depth_navigate")
        col_nav.prop(self, "wf_use_zoom_to_mouse")

        box_wf_theme = col_wf.box()
        box_wf_theme.label(text="Themes")
        box_wf_theme.prop(self, "wf_theme_box_inner_alpha_one")


classes = (ALEC_AddonPreferences,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
