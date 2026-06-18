"""Helpers for managing auxiliary hidden Blender collections."""

import bpy

from .utils import find_layer_collection


def ensure_hidden_collection(context, coll_name, color_tag):
    """Get or create a hidden auxiliary collection excluded from the View Layer."""
    if coll_name in bpy.data.collections:
        coll = bpy.data.collections[coll_name]
    else:
        coll = bpy.data.collections.new(coll_name)
        context.scene.collection.children.link(coll)
        coll.color_tag = color_tag

    coll.hide_viewport = False
    coll.hide_render = True

    layer_coll = find_layer_collection(context.view_layer.layer_collection, coll)
    if layer_coll:
        layer_coll.exclude = True

    return coll


def get_boolean_collection(context):
    return ensure_hidden_collection(context, "Hidden_Bools", 'COLOR_01')


def get_hidden_sources_collection(context):
    return ensure_hidden_collection(context, "Hidden_Sources", 'COLOR_05')
