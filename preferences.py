import bpy
from bpy.props import BoolProperty
from bpy.types import AddonPreferences


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
        name="Max-style mesh keys (1–3)",
        description="In Object or Edit mesh mode: 1 Vertex, 2 Edge, 3 Face (no Tab first from Object)",
        default=True,
        update=_on_mesh_keys_toggle,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "use_max_style_mesh_keys")


classes = (ALECS_TB_AddonPreferences,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
