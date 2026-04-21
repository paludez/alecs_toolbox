"""Outliner-related operators: hidden collections, collection cleanup, data renaming."""

import bpy
from ..modules.utils import move_to_collection, find_layer_collection, collection_in_subtree


def _selected_outliner_collections(context):
    result = []
    for item in getattr(context, "selected_ids", []):
        if isinstance(item, bpy.types.Collection):
            result.append(item)
    return result


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


def objects_from_outliner_or_view(context):
    """Objects selected in Outliner (selected_ids) or 3D View (selected_objects)."""
    objs = []
    for item in getattr(context, "selected_ids", []):
        if isinstance(item, bpy.types.Object):
            objs.append(item)
    if not objs:
        objs = list(context.selected_objects)
    seen = set()
    unique = []
    for o in objs:
        key = id(o)
        if key not in seen:
            seen.add(key)
            unique.append(o)
    return unique


class ALEC_OT_rename_data_to_object_name(bpy.types.Operator):
    """Rename each object's data-block name to match the object name (selected in Outliner or 3D View)."""
    bl_idname = "alec.rename_data_to_object_name"
    bl_label = "Rename Data to Object Name"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(objects_from_outliner_or_view(context))

    def execute(self, context):
        objs = objects_from_outliner_or_view(context)
        if not objs:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        renamed = 0
        skipped_linked = 0
        skipped_no_data = 0
        for obj in objs:
            data = getattr(obj, "data", None)
            if data is None:
                skipped_no_data += 1
                continue
            if getattr(data, "library", None) is not None:
                skipped_linked += 1
                continue
            if data.name == obj.name:
                continue
            try:
                data.name = obj.name
                renamed += 1
            except RuntimeError as exc:
                self.report({'WARNING'}, f"{obj.name}: {exc}")
                return {'CANCELLED'}

        if renamed == 0:
            msg = "Nothing to rename"
            if skipped_linked:
                msg += f" ({skipped_linked} linked)"
            if skipped_no_data:
                msg += f" ({skipped_no_data} without data)"
            self.report({'INFO'}, msg)
            return {'FINISHED'}

        self.report({'INFO'}, f"Renamed data for {renamed} object(s)")
        return {'FINISHED'}


class ALEC_OT_hidden_collection_visibility(bpy.types.Operator):
    """Toggle exclude state of a hidden auxiliary collection in the current View Layer"""
    bl_idname = "alec.hidden_collection_visibility"
    bl_label = "Hidden Collection Visibility"
    bl_options = {'REGISTER', 'UNDO'}

    coll_name: bpy.props.StringProperty() # type: ignore
    action: bpy.props.EnumProperty(
        items=[
            ('TOGGLE', "Toggle", ""),
            ('SHOW', "Show", ""),
            ('HIDE', "Hide", ""),
        ],
        default='TOGGLE',
    ) # type: ignore

    def execute(self, context):
        coll = bpy.data.collections.get(self.coll_name)
        if coll is None:
            self.report({'WARNING'}, f"{self.coll_name} collection not found")
            return {'CANCELLED'}

        layer_coll = find_layer_collection(context.view_layer.layer_collection, coll)
        if layer_coll is None:
            self.report({'WARNING'}, f"{self.coll_name} not found in current View Layer")
            return {'CANCELLED'}

        if self.action == 'SHOW':
            layer_coll.exclude = False
        elif self.action == 'HIDE':
            layer_coll.exclude = True
        else:
            layer_coll.exclude = not bool(layer_coll.exclude)

        return {'FINISHED'}


class ALEC_OT_move_to_hidden_obj(bpy.types.Operator):
    """Move selected objects to Hidden_Obj collection and exclude it from View Layer"""
    bl_idname = "alec.move_to_hidden_obj"
    bl_label = "Move to Hidden_Obj"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects) or bool(_selected_outliner_collections(context))

    def execute(self, context):
        coll = ensure_hidden_collection(context, "Hidden_Obj", 'COLOR_01')

        moved_objects = 0
        for obj in context.selected_objects:
            move_to_collection(obj, coll)
            moved_objects += 1

        moved_collections = 0
        skipped_collections = 0
        for src_coll in _selected_outliner_collections(context):
            if src_coll == coll or src_coll == context.scene.collection:
                skipped_collections += 1
                continue
            if collection_in_subtree(src_coll, coll):
                skipped_collections += 1
                continue

            if context.scene.collection.children.get(src_coll.name) is not None:
                context.scene.collection.children.unlink(src_coll)

            for parent in bpy.data.collections:
                if parent.children.get(src_coll.name) is not None:
                    parent.children.unlink(src_coll)
            if coll.children.get(src_coll.name) is None:
                coll.children.link(src_coll)
            moved_collections += 1

        if skipped_collections:
            self.report(
                {'INFO'},
                f"Moved {moved_objects} object(s), {moved_collections} collection(s), skipped {skipped_collections} collection(s)"
            )

        return {'FINISHED'}


class ALEC_OT_delete_empty_collections(bpy.types.Operator):
    """Delete all empty collections in current .blend (excluding Scene Collection)"""
    bl_idname = "alec.delete_empty_collections"
    bl_label = "Delete Empty Collections"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        del_count = 0

        # Repeatedly remove empty leaf collections; parents may become empty afterwards.
        while True:
            to_delete = [
                coll for coll in bpy.data.collections
                if len(coll.objects) == 0 and len(coll.children) == 0
            ]
            if not to_delete:
                break
            for coll in to_delete:
                bpy.data.collections.remove(coll)
                del_count += 1

        if del_count == 0:
            self.report({'INFO'}, "No empty collections found")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Deleted {del_count} empty collection(s)")
        return {'FINISHED'}


classes = [
    ALEC_OT_rename_data_to_object_name,
    ALEC_OT_hidden_collection_visibility,
    ALEC_OT_move_to_hidden_obj,
    ALEC_OT_delete_empty_collections,
]
