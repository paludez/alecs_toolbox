import bpy

from . import align
from . import attributes
from . import distribute
from . import angle_rays
from . import auto_linked_mode
from . import batch_materials
from . import bbox
from . import camera_tools
from . import draw_mesh_edges
from . import edit_curve
from . import edit_mesh
from . import edit_mesh_shapes
from . import edit_mesh_circle_arc
from . import fillet_chamfer
from . import light_tools
from . import materials
from . import modifiers
from . import object_origin
from . import object_tools
from . import outliner
from . import system
from . import triplanar_mapping
from . import trim_extend
from . import viewport_tools

classes = (
    *align.classes,
    *attributes.classes,
    *distribute.classes,
    *angle_rays.classes,
    *auto_linked_mode.classes,
    *batch_materials.classes,
    *bbox.classes,
    *camera_tools.classes,
    *draw_mesh_edges.classes,
    *edit_curve.classes,
    *edit_mesh.classes,
    *edit_mesh_shapes.classes,
    *edit_mesh_circle_arc.classes,
    *fillet_chamfer.classes,
    *light_tools.classes,
    *materials.classes,
    *modifiers.classes,
    *object_origin.classes,
    *object_tools.classes,
    *outliner.classes,
    *system.classes,
    *triplanar_mapping.classes,
    *trim_extend.classes,
    *viewport_tools.classes,
)

_app_handlers = []

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    attributes.post_register()
    batch_materials.post_register()
    triplanar_mapping.post_register()
    camera_tools.register_focal_lens_scene_props()
    camera_tools.register_camera_sphere_object_props()
    light_tools.register_light_rig_object_props()
    angle_rays.post_register()

    depsgraph_handler = edit_mesh.depsgraph_update_handler
    bpy.app.handlers.depsgraph_update_post.append(depsgraph_handler)
    _app_handlers.append((bpy.app.handlers.depsgraph_update_post, depsgraph_handler))

def unregister():
    from ..modules import distribute_gaps_overlay
    from ..modules import notice_overlay

    distribute_gaps_overlay.unregister_preview()
    notice_overlay.unregister()
    edit_mesh.unregister_draw_handler()
    auto_linked_mode._exit_auto_linked()
    attributes.post_unregister()
    batch_materials.post_unregister()
    camera_tools.unregister_focal_lens_scene_props()
    camera_tools.unregister_camera_sphere_object_props()
    light_tools.unregister_light_rig_object_props()
    angle_rays.post_unregister()
    edit_mesh_circle_arc.clear_three_point_circle_session()
    edit_mesh_circle_arc.clear_two_point_circle_session()
    edit_mesh_circle_arc.clear_three_point_arc_session()
    edit_mesh_circle_arc.clear_two_point_arc_session()
    edit_mesh_circle_arc.clear_center_circle_session()
    edit_mesh_circle_arc.clear_tan_tan_radius_circle_session()
    edit_mesh_circle_arc.clear_three_tan_circle_session()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    for handler_list, handler_func in _app_handlers:
        if handler_func in handler_list:
            handler_list.remove(handler_func)
    _app_handlers.clear()
