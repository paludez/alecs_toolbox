import bpy


INSERT_MODE_ITEMS = [
    ("SMART", "Smart order", "Preserve relative order from the source stack"),
    ("APPEND", "Append", "Add at the end of the modifier stack"),
    ("PREPEND", "Prepend", "Add at the start of the modifier stack"),
]


def _get_modifier_label(mod_type):
    try:
        items = bpy.types.Modifier.bl_rna.properties["type"].enum_items
        return items[mod_type].name
    except (KeyError, AttributeError):
        return mod_type.replace("_", " ").title()


def collect_modifier_types(context):
    total = len(context.selected_objects)
    type_count = {}
    viewport_all = {}
    render_all = {}

    for obj in context.selected_objects:
        seen = set()
        for mod in obj.modifiers:
            if mod.type in seen:
                continue
            seen.add(mod.type)
            type_count[mod.type] = type_count.get(mod.type, 0) + 1
            if mod.type not in viewport_all:
                viewport_all[mod.type] = True
                render_all[mod.type] = True
            if not mod.show_viewport:
                viewport_all[mod.type] = False
            if not mod.show_render:
                render_all[mod.type] = False

    items = [
        {
            "mod_type": mod_type,
            "mod_label": _get_modifier_label(mod_type),
            "object_count": type_count[mod_type],
            "total_count": total,
            "is_partial": type_count[mod_type] < total,
            "all_viewport_on": viewport_all[mod_type],
            "all_render_on": render_all[mod_type],
        }
        for mod_type in sorted(type_count.keys(), key=lambda x: _get_modifier_label(x).lower())
    ]
    return total, items


def collect_target_modifier_union(context):
    """Aggregate modifiers across targets by NAME (not type) so duplicates are visible."""
    active = context.active_object
    targets = [obj for obj in context.selected_objects if obj != active]
    total = len(targets)
    name_data = {}

    for obj in targets:
        seen_names = set()
        for index, mod in enumerate(obj.modifiers):
            if mod.name in seen_names:
                continue
            seen_names.add(mod.name)
            if mod.name not in name_data:
                name_data[mod.name] = {
                    "mod_name": mod.name,
                    "mod_type": mod.type,
                    "mod_label": _get_modifier_label(mod.type),
                    "object_count": 0,
                    "index_sum": 0,
                    "all_viewport_on": True,
                    "all_render_on": True,
                }
            name_data[mod.name]["object_count"] += 1
            name_data[mod.name]["index_sum"] += index
            if not mod.show_viewport:
                name_data[mod.name]["all_viewport_on"] = False
            if not mod.show_render:
                name_data[mod.name]["all_render_on"] = False

    items = []
    for data in name_data.values():
        count = data["object_count"]
        items.append({
            "mod_name": data["mod_name"],
            "mod_type": data["mod_type"],
            "mod_label": data["mod_label"],
            "object_count": count,
            "total_count": total,
            "is_partial": count < total,
            "all_viewport_on": data["all_viewport_on"],
            "all_render_on": data["all_render_on"],
            "avg_index": data["index_sum"] / count if count else 0.0,
        })

    items.sort(key=lambda x: (x["avg_index"], x["mod_name"].lower()))
    return total, items


def _fill_modifier_list(collection, items, search=""):
    collection.clear()
    needle = search.lower()
    for entry in items:
        if needle and needle not in entry["mod_label"].lower():
            continue
        item = collection.add()
        item.mod_type = entry["mod_type"]
        item.mod_label = entry["mod_label"]
        item.object_count = entry["object_count"]
        item.total_count = entry["total_count"]
        item.is_partial = entry["is_partial"]
        item.all_viewport_on = entry["all_viewport_on"]
        item.all_render_on = entry["all_render_on"]


def _fill_source_items(collection, obj):
    collection.clear()
    for mod in obj.modifiers:
        item = collection.add()
        item.mod_name = mod.name
        item.mod_type = mod.type
        item.mod_label = _get_modifier_label(mod.type)


def _fill_target_items(collection, items):
    collection.clear()
    for entry in items:
        item = collection.add()
        item.mod_name = entry["mod_name"]
        item.mod_type = entry["mod_type"]
        item.mod_label = entry["mod_label"]
        item.object_count = entry["object_count"]
        item.total_count = entry["total_count"]
        item.is_partial = entry["is_partial"]
        item.all_viewport_on = entry["all_viewport_on"]
        item.all_render_on = entry["all_render_on"]


def refresh_modifier_list(context, search=None):
    wm = context.window_manager
    if search is None:
        search = wm.alec_mod_search
    _, items = collect_modifier_types(context)
    _fill_modifier_list(wm.alec_mod_type_items, items, search)
    return len(wm.alec_mod_type_items)


def refresh_linker_lists(context):
    wm = context.window_manager
    active = context.active_object
    if active is None:
        return
    _fill_source_items(wm.alec_mod_source_items, active)
    _, target_items = collect_target_modifier_union(context)
    _fill_target_items(wm.alec_mod_target_items, target_items)


def _copy_modifier_props(src_mod, dst_mod):
    skip = {"rna_type", "name", "type", "is_active"}
    for prop in src_mod.bl_rna.properties:
        if prop.identifier in skip or prop.is_readonly:
            continue
        try:
            setattr(dst_mod, prop.identifier, getattr(src_mod, prop.identifier))
        except (AttributeError, TypeError):
            pass


def _target_has_type(obj, mod_type):
    return any(mod.type == mod_type for mod in obj.modifiers)


def _target_index_after_type(obj, mod_type):
    """Return the index after the last modifier of the given type, or None if missing."""
    last_index = None
    for index, mod in enumerate(obj.modifiers):
        if mod.type == mod_type:
            last_index = index
    if last_index is None:
        return None
    return last_index + 1


def _smart_insert_index(target, source_mod_types, src_index):
    """Insert after the nearest preceding source modifier type already on the target."""
    for prev_index in range(src_index - 1, -1, -1):
        prev_type = source_mod_types[prev_index]
        after_index = _target_index_after_type(target, prev_type)
        if after_index is not None:
            return after_index
    return 0


def _resolve_insert_index(target, insert_mode, source_mod_types, src_index):
    if insert_mode == "APPEND":
        return None
    if insert_mode == "PREPEND":
        return 0
    return _smart_insert_index(target, source_mod_types, src_index)


def _source_mod_types(active):
    return [mod.type for mod in active.modifiers]


def _move_modifier_to_index(obj, mod_name, index):
    mod = obj.modifiers.get(mod_name)
    if mod is None:
        return
    current_index = list(obj.modifiers).index(mod)
    index = min(max(index, 0), len(obj.modifiers) - 1)
    if current_index != index:
        obj.modifiers.move(current_index, index)


def _on_mod_search_update(_wm, context):
    if context is None:
        return
    refresh_modifier_list(context)
    if context.area:
        context.area.tag_redraw()


class ALEC_PG_modifier_type_item(bpy.types.PropertyGroup):
    mod_name: bpy.props.StringProperty()  # type: ignore
    mod_type: bpy.props.StringProperty()  # type: ignore
    mod_label: bpy.props.StringProperty()  # type: ignore
    object_count: bpy.props.IntProperty()  # type: ignore
    total_count: bpy.props.IntProperty()  # type: ignore
    is_partial: bpy.props.BoolProperty()  # type: ignore
    all_viewport_on: bpy.props.BoolProperty()  # type: ignore
    all_render_on: bpy.props.BoolProperty()  # type: ignore


class ALEC_PG_modifier_source_item(bpy.types.PropertyGroup):
    mod_name: bpy.props.StringProperty()  # type: ignore
    mod_type: bpy.props.StringProperty()  # type: ignore
    mod_label: bpy.props.StringProperty()  # type: ignore


class ALEC_UL_modifier_type_list(bpy.types.UIList):
    bl_idname = "ALEC_UL_modifier_type_list"

    def draw_item(
        self,
        context,
        layout,
        _data,
        item,
        _icon,
        _ad,
        _ap,
        _index=0,
    ):
        if self.layout_type not in {"DEFAULT", "COMPACT"}:
            return
        icon = "RADIOBUT_OFF" if item.is_partial else "RADIOBUT_ON"
        split = layout.split(factor=0.45, align=True)
        row = split.row(align=True)
        row.label(text="", icon=icon)
        row.label(text=item.mod_label)
        info = split.row(align=True)
        info.alignment = "RIGHT"
        vp_icon = "RESTRICT_VIEW_OFF" if item.all_viewport_on else "RESTRICT_VIEW_ON"
        rdr_icon = "RESTRICT_RENDER_OFF" if item.all_render_on else "RESTRICT_RENDER_ON"
        op_vp = info.operator(
            "alec.modifier_toggle_visibility",
            text="",
            icon=vp_icon,
            emboss=False,
        )
        op_vp.mod_type = item.mod_type
        op_vp.target = "VIEWPORT"
        op_rdr = info.operator(
            "alec.modifier_toggle_visibility",
            text="",
            icon=rdr_icon,
            emboss=False,
        )
        op_rdr.mod_type = item.mod_type
        op_rdr.target = "RENDER"
        info.label(text=f"({item.object_count}/{item.total_count})")


class ALEC_UL_modifier_source_list(bpy.types.UIList):
    bl_idname = "ALEC_UL_modifier_source_list"

    def draw_item(
        self,
        _ctx,
        layout,
        _data,
        item,
        _icon,
        _ad,
        _ap,
        index=0,
    ):
        if self.layout_type not in {"DEFAULT", "COMPACT"}:
            return
        split = layout.split(factor=0.12, align=True)
        split.label(text=f"{index + 1}.")
        name_row = split.row(align=True)
        name_row.label(text=item.mod_name, icon="MODIFIER")
        if item.mod_label and item.mod_label.lower() not in item.mod_name.lower():
            name_row.label(text=item.mod_label)


class ALEC_UL_modifier_target_list(bpy.types.UIList):
    bl_idname = "ALEC_UL_modifier_target_list"

    def draw_item(
        self,
        _ctx,
        layout,
        _data,
        item,
        _icon,
        _ad,
        _ap,
        _index=0,
    ):
        if self.layout_type not in {"DEFAULT", "COMPACT"}:
            return
        icon = "RADIOBUT_OFF" if item.is_partial else "RADIOBUT_ON"
        split = layout.split(factor=0.65, align=True)
        row = split.row(align=True)
        row.label(text="", icon=icon)
        row.label(text=item.mod_name)
        info = split.row(align=True)
        info.alignment = "RIGHT"
        info.label(text=f"({item.object_count}/{item.total_count})")


class ALEC_OT_modifier_toggle_visibility(bpy.types.Operator):
    """Toggle viewport or render visibility for a modifier type on all selected objects."""

    bl_idname = "alec.modifier_toggle_visibility"
    bl_label = "Toggle Modifier Visibility"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    mod_type: bpy.props.StringProperty()  # type: ignore
    target: bpy.props.EnumProperty(  # type: ignore
        items=[
            ("VIEWPORT", "Viewport", ""),
            ("RENDER", "Render", ""),
        ],
    )

    def execute(self, context):
        mods = [
            mod for obj in context.selected_objects
            for mod in obj.modifiers
            if mod.type == self.mod_type
        ]
        if not mods:
            self.report({"WARNING"}, "No matching modifiers found")
            return {"CANCELLED"}

        if self.target == "VIEWPORT":
            all_on = all(mod.show_viewport for mod in mods)
            new_value = not all_on
            for mod in mods:
                mod.show_viewport = new_value
        else:
            all_on = all(mod.show_render for mod in mods)
            new_value = not all_on
            for mod in mods:
                mod.show_render = new_value

        refresh_modifier_list(context)
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ALEC_OT_modifier_delete_by_type(bpy.types.Operator):
    """Delete all modifiers of a given type from selected objects."""

    bl_idname = "alec.modifier_delete_by_type"
    bl_label = "Delete All of Type"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    mod_type: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        removed = 0
        for obj in context.selected_objects:
            to_remove = [mod for mod in obj.modifiers if mod.type == self.mod_type]
            for mod in to_remove:
                obj.modifiers.remove(mod)
                removed += 1

        refresh_modifier_list(context)
        self.report({"INFO"}, f"Removed {removed} modifier(s)")
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ALEC_OT_list_modifier_types(bpy.types.Operator):
    """List unique modifier types across the current selection."""

    bl_idname = "alec.list_modifier_types"
    bl_label = "List Modifiers"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return any(obj.modifiers for obj in context.selected_objects)

    def invoke(self, context, _event):
        wm = context.window_manager
        wm.alec_mod_search = ""
        refresh_modifier_list(context, search="")
        wm.alec_mod_type_index = 0
        return wm.invoke_props_dialog(self, width=480)

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        layout.prop(wm, "alec_mod_search", text="", icon="VIEWZOOM")
        layout.separator(factor=0.4)

        coll = wm.alec_mod_type_items
        if not coll:
            layout.label(text="No modifiers match the filter.", icon="ERROR")
            return

        layout.template_list(
            "ALEC_UL_modifier_type_list",
            "alec_mod_types",
            wm,
            "alec_mod_type_items",
            wm,
            "alec_mod_type_index",
            rows=min(len(coll), 10),
        )

        active_idx = wm.alec_mod_type_index
        if not (0 <= active_idx < len(coll)):
            return

        active = coll[active_idx]
        row = layout.row(align=True)
        op_del = row.operator(
            "alec.modifier_delete_by_type",
            text="Delete All of Type",
            icon="X",
        )
        op_del.mod_type = active.mod_type

    def execute(self, _context):
        return {"FINISHED"}


class ALEC_OT_copy_modifier_to_targets(bpy.types.Operator):
    """Copy one modifier from the active object to all other selected objects."""

    bl_idname = "alec.copy_modifier_to_targets"
    bl_label = "Copy Modifier"
    bl_options = {"INTERNAL"}

    src_mod_name: bpy.props.StringProperty()  # type: ignore
    src_mod_index: bpy.props.IntProperty(default=0)  # type: ignore
    insert_mode: bpy.props.EnumProperty(items=INSERT_MODE_ITEMS, default="SMART")  # type: ignore
    allow_duplicate: bpy.props.BoolProperty(default=False)  # type: ignore

    def execute(self, context):
        active = context.active_object
        if active is None:
            self.report({"WARNING"}, "No active object")
            return {"CANCELLED"}

        src_mod = active.modifiers.get(self.src_mod_name)
        if src_mod is None:
            self.report({"WARNING"}, f"Modifier '{self.src_mod_name}' not found")
            return {"CANCELLED"}

        targets = [obj for obj in context.selected_objects if obj != active]
        if not targets:
            self.report({"WARNING"}, "No target objects selected")
            return {"CANCELLED"}

        source_types = _source_mod_types(active)
        added = 0
        skipped = 0
        for target in targets:
            if _target_has_type(target, src_mod.type) and not self.allow_duplicate:
                skipped += 1
                continue

            new_mod = target.modifiers.new(name=src_mod.name, type=src_mod.type)
            _copy_modifier_props(src_mod, new_mod)
            insert_index = _resolve_insert_index(
                target,
                self.insert_mode,
                source_types,
                self.src_mod_index,
            )
            if insert_index is not None:
                _move_modifier_to_index(target, new_mod.name, insert_index)
            added += 1

        refresh_linker_lists(context)
        msg = f"Copied to {added} object(s)"
        if skipped:
            msg += f", skipped {skipped} (already had type; enable Dup.)"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class ALEC_OT_copy_all_modifiers_to_targets(bpy.types.Operator):
    """Copy the full modifier stack from the active object to all other selected objects."""

    bl_idname = "alec.copy_all_modifiers_to_targets"
    bl_label = "Copy All Modifiers"
    bl_options = {"INTERNAL"}

    insert_mode: bpy.props.EnumProperty(items=INSERT_MODE_ITEMS, default="SMART")  # type: ignore
    allow_duplicate: bpy.props.BoolProperty(default=False)  # type: ignore

    def execute(self, context):
        active = context.active_object
        if active is None:
            self.report({"WARNING"}, "No active object")
            return {"CANCELLED"}

        targets = [obj for obj in context.selected_objects if obj != active]
        if not targets:
            self.report({"WARNING"}, "No target objects selected")
            return {"CANCELLED"}

        source_mods = list(active.modifiers)
        source_types = [mod.type for mod in source_mods]
        if self.insert_mode == "PREPEND":
            indexed_mods = list(reversed(list(enumerate(source_mods))))
        else:
            indexed_mods = list(enumerate(source_mods))

        added = 0
        skipped = 0
        for src_index, src_mod in indexed_mods:
            for target in targets:
                if _target_has_type(target, src_mod.type) and not self.allow_duplicate:
                    skipped += 1
                    continue
                new_mod = target.modifiers.new(name=src_mod.name, type=src_mod.type)
                _copy_modifier_props(src_mod, new_mod)
                insert_index = _resolve_insert_index(
                    target,
                    self.insert_mode,
                    source_types,
                    src_index,
                )
                if insert_index is not None:
                    _move_modifier_to_index(target, new_mod.name, insert_index)
                added += 1

        refresh_linker_lists(context)
        msg = f"Copied {added} modifier(s)"
        if skipped:
            msg += f", skipped {skipped} (already had type; enable Dup.)"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class ALEC_OT_modifier_linker(bpy.types.Operator):
    """Copy modifiers from the active object to other selected objects."""

    bl_idname = "alec.modifier_linker"
    bl_label = "Modifier Linker"
    bl_options = {"REGISTER"}

    insert_mode: bpy.props.EnumProperty(  # type: ignore
        name="Insert Mode",
        items=INSERT_MODE_ITEMS,
        default="SMART",
    )
    allow_duplicate: bpy.props.BoolProperty(name="Allow Duplicate", default=False)  # type: ignore

    @classmethod
    def poll(cls, context):
        active = context.active_object
        if active is None:
            return False
        return any(obj != active for obj in context.selected_objects)

    def invoke(self, context, _event):
        wm = context.window_manager
        active = context.active_object
        wm.alec_mod_linker_active_name = active.name if active else ""
        targets = [obj for obj in context.selected_objects if obj != active]
        self._snapshot = {
            obj.name: [m.name for m in obj.modifiers]
            for obj in targets
        }
        refresh_linker_lists(context)
        wm.alec_mod_source_index = 0
        wm.alec_mod_target_index = 0
        return wm.invoke_props_dialog(self, width=720)

    def cancel(self, context):
        snapshot = getattr(self, "_snapshot", {})
        if not snapshot:
            return
        active = context.active_object
        for obj in context.selected_objects:
            if obj == active or obj.name not in snapshot:
                continue
            original_names = set(snapshot[obj.name])
            to_remove = [m for m in obj.modifiers if m.name not in original_names]
            for mod in to_remove:
                obj.modifiers.remove(mod)
        refresh_linker_lists(context)

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        active = context.active_object
        if active is None:
            layout.label(text="No active object", icon="ERROR")
            return

        targets = [obj for obj in context.selected_objects if obj != active]
        if not targets:
            layout.label(text="Select at least one other object.", icon="ERROR")
            return

        target_count = len(targets)
        target_names = ", ".join(obj.name for obj in targets[:3])
        if target_count > 3:
            target_names += f", +{target_count - 3} more"

        list_rows = 6
        src_coll = wm.alec_mod_source_items
        tgt_coll = wm.alec_mod_target_items
        src_idx = wm.alec_mod_source_index
        has_src = 0 <= src_idx < len(src_coll)
        mod_count = len(active.modifiers)

        split = layout.split(factor=0.5)

        box_src = split.box()
        col_src = box_src.column()
        col_src.label(
            text=f"Source: {active.name} ({mod_count} mod{'s' if mod_count != 1 else ''})",
            icon="CHECKBOX_HLT",
        )
        col_src.template_list(
            "ALEC_UL_modifier_source_list",
            "alec_mod_src",
            wm,
            "alec_mod_source_items",
            wm,
            "alec_mod_source_index",
            rows=list_rows,
        )
        if not src_coll:
            col_src.label(text="No modifiers on source", icon="INFO")

        box_tgt = split.box()
        col_tgt = box_tgt.column()
        col_tgt.label(text=f"Targets ({target_count})", icon="OUTLINER_OB_MESH")
        col_tgt.template_list(
            "ALEC_UL_modifier_target_list",
            "alec_mod_tgt",
            wm,
            "alec_mod_target_items",
            wm,
            "alec_mod_target_index",
            rows=list_rows,
        )
        if not tgt_coll:
            col_tgt.label(text="No modifiers on targets", icon="INFO")

        layout.separator(factor=0.5)

        row_copy = layout.row(align=True)
        row_copy.scale_y = 1.2
        col_copy = row_copy.column(align=True)
        col_copy.enabled = has_src
        op_copy = col_copy.operator(
            "alec.copy_modifier_to_targets",
            text="Copy ->",
            icon="FORWARD",
        )
        if has_src:
            op_copy.src_mod_name = src_coll[src_idx].mod_name
            op_copy.src_mod_index = src_idx
        op_copy.insert_mode = self.insert_mode
        op_copy.allow_duplicate = self.allow_duplicate

        col_copy_all = row_copy.column(align=True)
        op_all = col_copy_all.operator(
            "alec.copy_all_modifiers_to_targets",
            text="Copy All ->",
            icon="FILE_TICK",
        )
        op_all.insert_mode = self.insert_mode
        op_all.allow_duplicate = self.allow_duplicate

        layout.separator(factor=0.4)
        layout.label(text="Insert mode:")
        layout.prop(self, "insert_mode", expand=True)

        row_opts = layout.row(align=True)
        row_opts.prop(self, "allow_duplicate", text="Allow Duplicate", toggle=True)

        layout.separator(factor=0.3)
        layout.label(text=f"Applies to: {target_names}", icon="INFO")

    def execute(self, _context):
        return {"FINISHED"}


classes = (
    ALEC_PG_modifier_type_item,
    ALEC_PG_modifier_source_item,
    ALEC_UL_modifier_type_list,
    ALEC_UL_modifier_source_list,
    ALEC_UL_modifier_target_list,
    ALEC_OT_modifier_toggle_visibility,
    ALEC_OT_modifier_delete_by_type,
    ALEC_OT_list_modifier_types,
    ALEC_OT_copy_modifier_to_targets,
    ALEC_OT_copy_all_modifiers_to_targets,
    ALEC_OT_modifier_linker,
)


def post_register():
    bpy.types.WindowManager.alec_mod_type_items = bpy.props.CollectionProperty(
        type=ALEC_PG_modifier_type_item,
    )
    bpy.types.WindowManager.alec_mod_source_items = bpy.props.CollectionProperty(
        type=ALEC_PG_modifier_source_item,
    )
    bpy.types.WindowManager.alec_mod_target_items = bpy.props.CollectionProperty(
        type=ALEC_PG_modifier_type_item,
    )
    bpy.types.WindowManager.alec_mod_type_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.alec_mod_source_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.alec_mod_target_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.alec_mod_search = bpy.props.StringProperty(
        name="Filter",
        default="",
        update=_on_mod_search_update,
    )
    bpy.types.WindowManager.alec_mod_linker_active_name = bpy.props.StringProperty(default="")


def post_unregister():
    for wm in bpy.data.window_managers:
        for attr in ("alec_mod_type_items", "alec_mod_source_items", "alec_mod_target_items"):
            try:
                getattr(wm, attr).clear()
            except Exception:
                pass
    for attr in (
        "alec_mod_type_items",
        "alec_mod_source_items",
        "alec_mod_target_items",
        "alec_mod_type_index",
        "alec_mod_source_index",
        "alec_mod_target_index",
        "alec_mod_search",
        "alec_mod_linker_active_name",
    ):
        try:
            delattr(bpy.types.WindowManager, attr)
        except AttributeError:
            pass
