"""Central registration of all RNA properties added to Blender built-in types."""

from .operators import (
    attributes,
    batch_materials,
    camera_tools,
    light_tools,
    modifiers_dialog,
    triplanar_mapping,
)
from .ui import npanel


def register():
    attributes.post_register()
    modifiers_dialog.post_register()
    batch_materials.post_register()
    triplanar_mapping.post_register()
    camera_tools.register_focal_lens_scene_props()
    camera_tools.register_camera_sphere_object_props()
    light_tools.register_light_rig_object_props()
    npanel._register_transform_ui_dummy_props()
    npanel._register_lights_ui_dummy_props()
    npanel._register_camera_ui_dummy_props()


def unregister():
    npanel._unregister_camera_ui_dummy_props()
    npanel._unregister_lights_ui_dummy_props()
    npanel._unregister_transform_ui_dummy_props()
    attributes.post_unregister()
    modifiers_dialog.post_unregister()
    batch_materials.post_unregister()
    camera_tools.unregister_focal_lens_scene_props()
    camera_tools.unregister_camera_sphere_object_props()
    light_tools.unregister_light_rig_object_props()
