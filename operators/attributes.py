import bpy

_COLOR_TYPES = frozenset({"FLOAT_COLOR", "BYTE_COLOR"})
_UV_TYPE = "FLOAT2"
_UV_DOMAIN = "CORNER"

_DOMAIN_ITEMS = (
    ("POINT", "Point", "Attribute on vertices"),
    ("EDGE", "Edge", "Attribute on edges"),
    ("FACE", "Face", "Attribute on faces"),
    ("CORNER", "Face Corner", "Attribute on face corners"),
)

_TYPE_ITEMS = (
    ("FLOAT", "Float", ""),
    ("INT", "Integer", ""),
    ("BOOLEAN", "Boolean", ""),
    ("FLOAT_VECTOR", "Float Vector", ""),
    ("FLOAT2", "Float2", ""),
    ("FLOAT_COLOR", "Float Color", ""),
    ("BYTE_COLOR", "Byte Color", ""),
    ("QUATERNION", "Quaternion", ""),
)


def _get_section(data_type, domain):
    if data_type in _COLOR_TYPES:
        return "COLOR"
    if data_type == _UV_TYPE and domain == _UV_DOMAIN:
        return "UV"
    return "ATTR"


def _mesh_objects_from_names(context, names_text):
    if not names_text:
        return []
    names = set(names_text.split("|"))
    return [
        obj for obj in context.scene.objects
        if obj.name in names and obj.type == "MESH" and obj.data is not None
    ]


def _find_attribute(mesh, name, domain, data_type):
    for attr in mesh.attributes:
        if (
            attr.name == name
            and attr.domain == domain
            and attr.data_type == data_type
        ):
            return attr
    return None


def collect_unique_mesh_attributes(context):
    """Return (mesh_count, unique attribute dicts) across all selected meshes."""
    mesh_objects = [
        obj for obj in context.selected_objects
        if obj.type == "MESH" and obj.data is not None
    ]
    total = len(mesh_objects)
    counts = {}
    required = {}

    for obj in mesh_objects:
        seen_on_obj = set()
        for attr in obj.data.attributes:
            if attr.is_internal:
                continue
            key = (attr.name, attr.domain, attr.data_type)
            if key in seen_on_obj:
                continue
            seen_on_obj.add(key)
            counts[key] = counts.get(key, 0) + 1
            if attr.is_required:
                required[key] = True

    return total, [
        {
            "attribute_name": key[0],
            "domain": key[1],
            "data_type": key[2],
            "object_count": counts[key],
            "total_count": total,
            "section": _get_section(key[2], key[1]),
            "is_partial": counts[key] < total,
            "is_required": required.get(key, False),
        }
        for key in sorted(counts.keys(), key=lambda item: (item[0].lower(), item[1], item[2]))
    ]


def _fill_section(collection, items, section, search=""):
    collection.clear()
    needle = search.lower()
    for entry in items:
        if entry["section"] != section:
            continue
        if needle and needle not in entry["attribute_name"].lower():
            continue
        item = collection.add()
        item.attribute_name = entry["attribute_name"]
        item.domain = entry["domain"]
        item.data_type = entry["data_type"]
        item.object_count = entry["object_count"]
        item.total_count = entry["total_count"]
        item.is_partial = entry["is_partial"]
        item.is_required = entry["is_required"]


def refresh_attribute_lists(context, search=None):
    wm = context.window_manager
    if search is None:
        search = wm.alec_mesh_attr_search
    _, items = collect_unique_mesh_attributes(context)
    _fill_section(wm.alec_mesh_attr_items, items, "ATTR", search)
    _fill_section(wm.alec_mesh_color_items, items, "COLOR", search)
    _fill_section(wm.alec_mesh_uv_items, items, "UV", search)
    return len(items)


def _apply_fill_value(attr, data_type, fill_value, use_fill):
    if not use_fill:
        return
    data = attr.data
    count = len(data)
    if count == 0:
        return

    if data_type == "FLOAT":
        data.foreach_set("value", [float(fill_value[0])] * count)
    elif data_type == "INT":
        data.foreach_set("value", [int(fill_value[0])] * count)
    elif data_type == "BOOLEAN":
        data.foreach_set("value", [bool(fill_value[0])] * count)
    elif data_type == "FLOAT_VECTOR":
        v = (float(fill_value[0]), float(fill_value[1]), float(fill_value[2]))
        data.foreach_set("vector", list(v) * count)
    elif data_type in _COLOR_TYPES:
        c = (float(fill_value[0]), float(fill_value[1]), float(fill_value[2]), float(fill_value[3]))
        data.foreach_set("color", list(c) * count)
    elif data_type == "FLOAT2":
        v = (float(fill_value[0]), float(fill_value[1]))
        data.foreach_set("vector", list(v) * count)


def _on_search_update(_wm, context):
    if context is None:
        return
    refresh_attribute_lists(context)
    if context.area:
        context.area.tag_redraw()


class ALEC_PG_mesh_attribute_item(bpy.types.PropertyGroup):
    attribute_name: bpy.props.StringProperty(name="Name")  # type: ignore
    domain: bpy.props.StringProperty(name="Domain")  # type: ignore
    data_type: bpy.props.StringProperty(name="Type")  # type: ignore
    object_count: bpy.props.IntProperty(name="Objects")  # type: ignore
    total_count: bpy.props.IntProperty(name="Total")  # type: ignore
    is_partial: bpy.props.BoolProperty(name="Partial")  # type: ignore
    is_required: bpy.props.BoolProperty(name="Required")  # type: ignore


class ALEC_UL_mesh_attribute_list(bpy.types.UIList):
    bl_idname = "ALEC_UL_mesh_attribute_list"

    def draw_item(
        self,
        _context,
        layout,
        _data,
        item,
        _icon,
        _active_data,
        _active_propname,
        _index=0,
    ):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            icon = "RADIOBUT_OFF" if item.is_partial else "RADIOBUT_ON"
            split = layout.split(factor=0.42, align=True)
            row = split.row(align=True)
            row.label(text="", icon=icon)
            row.label(text=item.attribute_name)
            info = split.row(align=True)
            info.alignment = "RIGHT"
            info.label(
                text=f"{item.domain}  ·  {item.data_type}  ·  ({item.object_count}/{item.total_count})"
            )


class ALEC_OT_mesh_attribute_begin_rename(bpy.types.Operator):
    """Prepare inline rename for the active attribute."""

    bl_idname = "alec.mesh_attribute_begin_rename"
    bl_label = "Rename"
    bl_options = {"INTERNAL"}

    section_key: bpy.props.StringProperty()  # type: ignore
    attr_name: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        wm = context.window_manager
        wm.alec_mesh_attr_rename_section = self.section_key
        wm.alec_mesh_attr_new_name = self.attr_name
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ALEC_OT_mesh_attribute_cancel_rename(bpy.types.Operator):
    """Cancel inline rename."""

    bl_idname = "alec.mesh_attribute_cancel_rename"
    bl_label = "Cancel Rename"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        wm = context.window_manager
        wm.alec_mesh_attr_rename_section = ""
        wm.alec_mesh_attr_new_name = ""
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ALEC_OT_delete_mesh_attribute(bpy.types.Operator):
    """Remove attribute from all selected meshes that have it."""

    bl_idname = "alec.delete_mesh_attribute"
    bl_label = "Delete Attribute"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    attr_name: bpy.props.StringProperty()  # type: ignore
    domain: bpy.props.StringProperty()  # type: ignore
    data_type: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        removed = 0
        for obj in context.selected_objects:
            if obj.type != "MESH" or obj.data is None:
                continue
            attr = _find_attribute(obj.data, self.attr_name, self.domain, self.data_type)
            if attr is None or attr.is_required:
                continue
            obj.data.attributes.remove(attr)
            removed += 1

        refresh_attribute_lists(context)
        self.report({"INFO"}, f"Removed attribute from {removed} object(s)")
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ALEC_OT_rename_mesh_attribute(bpy.types.Operator):
    """Rename attribute on all selected meshes that have it."""

    bl_idname = "alec.rename_mesh_attribute"
    bl_label = "Confirm Rename"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    old_name: bpy.props.StringProperty()  # type: ignore
    domain: bpy.props.StringProperty()  # type: ignore
    data_type: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        wm = context.window_manager
        new_name = wm.alec_mesh_attr_new_name.strip()
        if not new_name:
            self.report({"WARNING"}, "Name cannot be empty")
            return {"CANCELLED"}

        renamed = 0
        for obj in context.selected_objects:
            if obj.type != "MESH" or obj.data is None:
                continue
            attr = _find_attribute(obj.data, self.old_name, self.domain, self.data_type)
            if attr is None or attr.is_required:
                continue
            if _find_attribute(obj.data, new_name, self.domain, self.data_type):
                self.report({"WARNING"}, f"'{new_name}' already exists on {obj.name}")
                return {"CANCELLED"}
            attr.name = new_name
            renamed += 1

        wm.alec_mesh_attr_rename_section = ""
        wm.alec_mesh_attr_new_name = ""
        refresh_attribute_lists(context)
        self.report({"INFO"}, f"Renamed on {renamed} object(s)")
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ALEC_OT_select_objects_by_attribute(bpy.types.Operator):
    """Select only mesh objects from the dialog selection that have this attribute."""

    bl_idname = "alec.select_objects_by_attribute"
    bl_label = "Select Objects"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    attr_name: bpy.props.StringProperty()  # type: ignore
    domain: bpy.props.StringProperty()  # type: ignore
    data_type: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        wm = context.window_manager
        source_objects = _mesh_objects_from_names(context, wm.alec_mesh_attr_source_names)
        if not source_objects:
            self.report({"WARNING"}, "No source objects stored")
            return {"CANCELLED"}

        bpy.ops.object.select_all(action="DESELECT")
        selected = 0
        active_obj = None
        for obj in source_objects:
            if _find_attribute(obj.data, self.attr_name, self.domain, self.data_type):
                obj.select_set(True)
                if active_obj is None:
                    active_obj = obj
                selected += 1

        if active_obj is not None:
            context.view_layer.objects.active = active_obj
        self.report({"INFO"}, f"Selected {selected} object(s)")
        return {"FINISHED"}


class ALEC_OT_propagate_mesh_attribute(bpy.types.Operator):
    """Create attribute on selected meshes that do not have it yet."""

    bl_idname = "alec.propagate_mesh_attribute"
    bl_label = "Propagate Attribute"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    attr_name: bpy.props.StringProperty()  # type: ignore
    domain: bpy.props.StringProperty()  # type: ignore
    data_type: bpy.props.StringProperty()  # type: ignore
    use_fill: bpy.props.BoolProperty(name="Fill Value", default=False)  # type: ignore
    fill_value: bpy.props.FloatVectorProperty(name="Fill", size=4, default=(0.0, 0.0, 0.0, 1.0))  # type: ignore

    def execute(self, context):
        added = 0
        for obj in context.selected_objects:
            if obj.type != "MESH" or obj.data is None:
                continue
            if _find_attribute(obj.data, self.attr_name, self.domain, self.data_type):
                continue
            try:
                attr = obj.data.attributes.new(
                    name=self.attr_name,
                    type=self.data_type,
                    domain=self.domain,
                )
            except RuntimeError as exc:
                self.report({"WARNING"}, str(exc))
                return {"CANCELLED"}
            _apply_fill_value(attr, self.data_type, self.fill_value, self.use_fill)
            added += 1

        refresh_attribute_lists(context)
        self.report({"INFO"}, f"Added attribute to {added} object(s)")
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ALEC_OT_add_mesh_attribute(bpy.types.Operator):
    """Create a new attribute on all selected meshes."""

    bl_idname = "alec.add_mesh_attribute"
    bl_label = "Add Attribute"
    bl_options = {"REGISTER", "UNDO"}

    attr_name: bpy.props.StringProperty(name="Name", default="")  # type: ignore
    domain: bpy.props.EnumProperty(name="Domain", items=_DOMAIN_ITEMS, default="POINT")  # type: ignore
    data_type: bpy.props.EnumProperty(name="Type", items=_TYPE_ITEMS, default="FLOAT")  # type: ignore

    @classmethod
    def poll(cls, context):
        return any(
            obj.type == "MESH" and obj.data is not None
            for obj in context.selected_objects
        )

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, layout):
        layout.prop(self, "attr_name")
        layout.prop(self, "domain")
        layout.prop(self, "data_type")

    def execute(self, context):
        name = self.attr_name.strip()
        if not name:
            self.report({"WARNING"}, "Name cannot be empty")
            return {"CANCELLED"}

        added = 0
        skipped = 0
        for obj in context.selected_objects:
            if obj.type != "MESH" or obj.data is None:
                continue
            if _find_attribute(obj.data, name, self.domain, self.data_type):
                skipped += 1
                continue
            try:
                obj.data.attributes.new(name=name, type=self.data_type, domain=self.domain)
            except RuntimeError as exc:
                self.report({"WARNING"}, str(exc))
                return {"CANCELLED"}
            added += 1

        refresh_attribute_lists(context)
        msg = f"Added '{name}' to {added} object(s)"
        if skipped:
            msg += f", skipped {skipped} (already had it)"
        self.report({"INFO"}, msg)
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


def _draw_section_actions(layout, wm, section_key, coll_prop, idx_prop):
    coll = getattr(wm, coll_prop)
    if not coll:
        return

    active_idx = getattr(wm, idx_prop)
    if not (0 <= active_idx < len(coll)):
        return

    active = coll[active_idx]
    can_edit = not active.is_required

    if wm.alec_mesh_attr_rename_section == section_key:
        row = layout.row(align=True)
        row.prop(wm, "alec_mesh_attr_new_name", text="New name")
        op_ok = row.operator("alec.rename_mesh_attribute", text="", icon="CHECKMARK")
        op_ok.old_name = active.attribute_name
        op_ok.domain = active.domain
        op_ok.data_type = active.data_type
        row.operator("alec.mesh_attribute_cancel_rename", text="", icon="X")
        return

    row = layout.row(align=True)
    edit_row = row.row(align=True)
    edit_row.enabled = can_edit
    op_del = edit_row.operator("alec.delete_mesh_attribute", text="Delete", icon="X")
    op_del.attr_name = active.attribute_name
    op_del.domain = active.domain
    op_del.data_type = active.data_type

    op_ren = edit_row.operator("alec.mesh_attribute_begin_rename", text="Rename", icon="GREASEPENCIL")
    op_ren.section_key = section_key
    op_ren.attr_name = active.attribute_name

    op_sel = row.operator("alec.select_objects_by_attribute", text="Select", icon="RESTRICT_SELECT_OFF")
    op_sel.attr_name = active.attribute_name
    op_sel.domain = active.domain
    op_sel.data_type = active.data_type

    op_prop = row.operator("alec.propagate_mesh_attribute", text="Propagate", icon="ADD")
    op_prop.attr_name = active.attribute_name
    op_prop.domain = active.domain
    op_prop.data_type = active.data_type
    op_prop.use_fill = wm.alec_mesh_attr_use_fill
    op_prop.fill_value = wm.alec_mesh_attr_fill_value


class ALEC_OT_list_mesh_attributes(bpy.types.Operator):
    """List unique mesh attributes across the current selection."""

    bl_idname = "alec.list_mesh_attributes"
    bl_label = "List Attributes"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return any(
            obj.type == "MESH" and obj.data is not None
            for obj in context.selected_objects
        )

    def invoke(self, context, _event):
        wm = context.window_manager
        mesh_names = [
            obj.name for obj in context.selected_objects
            if obj.type == "MESH" and obj.data is not None
        ]
        wm.alec_mesh_attr_source_names = "|".join(mesh_names)
        wm.alec_mesh_attr_search = ""
        wm.alec_mesh_attr_rename_section = ""
        wm.alec_mesh_attr_new_name = ""

        refresh_attribute_lists(context, search="")
        wm.alec_mesh_attr_index = 0
        wm.alec_mesh_color_index = 0
        wm.alec_mesh_uv_index = 0
        return wm.invoke_props_dialog(self, width=560)

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        layout.prop(wm, "alec_mesh_attr_search", text="", icon="VIEWZOOM")
        layout.separator(factor=0.4)

        sections = (
            ("ATTR", "alec_mesh_attr_items", "alec_mesh_attr_index", "Attributes", "MESH_DATA"),
            ("COLOR", "alec_mesh_color_items", "alec_mesh_color_index", "Color Attributes", "COLOR"),
            ("UV", "alec_mesh_uv_items", "alec_mesh_uv_index", "UV", "GROUP_UVS"),
        )
        visible = 0
        for section_key, coll_prop, idx_prop, label, icon in sections:
            coll = getattr(wm, coll_prop)
            if not coll:
                continue
            visible += len(coll)
            layout.label(text=label, icon=icon)
            layout.template_list(
                "ALEC_UL_mesh_attribute_list",
                coll_prop,
                wm,
                coll_prop,
                wm,
                idx_prop,
                rows=min(len(coll), 8),
            )
            _draw_section_actions(layout, wm, section_key, coll_prop, idx_prop)
            layout.separator(factor=0.3)

        if visible == 0:
            layout.label(text="No attributes match the filter.", icon="ERROR")

        layout.separator(factor=0.5)
        row = layout.row(align=True)
        row.prop(wm, "alec_mesh_attr_use_fill", text="Fill on propagate")
        row.prop(wm, "alec_mesh_attr_fill_value", text="")
        layout.operator("alec.add_mesh_attribute", text="Add Attribute", icon="ADD")

    def execute(self, _context):
        return {"FINISHED"}


classes = (
    ALEC_PG_mesh_attribute_item,
    ALEC_UL_mesh_attribute_list,
    ALEC_OT_mesh_attribute_begin_rename,
    ALEC_OT_mesh_attribute_cancel_rename,
    ALEC_OT_delete_mesh_attribute,
    ALEC_OT_rename_mesh_attribute,
    ALEC_OT_select_objects_by_attribute,
    ALEC_OT_propagate_mesh_attribute,
    ALEC_OT_add_mesh_attribute,
    ALEC_OT_list_mesh_attributes,
)


def post_register():
    bpy.types.WindowManager.alec_mesh_attr_items = bpy.props.CollectionProperty(
        type=ALEC_PG_mesh_attribute_item,
    )
    bpy.types.WindowManager.alec_mesh_color_items = bpy.props.CollectionProperty(
        type=ALEC_PG_mesh_attribute_item,
    )
    bpy.types.WindowManager.alec_mesh_uv_items = bpy.props.CollectionProperty(
        type=ALEC_PG_mesh_attribute_item,
    )
    bpy.types.WindowManager.alec_mesh_attr_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.alec_mesh_color_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.alec_mesh_uv_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.alec_mesh_attr_search = bpy.props.StringProperty(
        name="Filter",
        default="",
        update=_on_search_update,
    )
    bpy.types.WindowManager.alec_mesh_attr_source_names = bpy.props.StringProperty(default="")
    bpy.types.WindowManager.alec_mesh_attr_rename_section = bpy.props.StringProperty(default="")
    bpy.types.WindowManager.alec_mesh_attr_new_name = bpy.props.StringProperty(name="New Name", default="")
    bpy.types.WindowManager.alec_mesh_attr_use_fill = bpy.props.BoolProperty(
        name="Fill on Propagate",
        default=False,
    )
    bpy.types.WindowManager.alec_mesh_attr_fill_value = bpy.props.FloatVectorProperty(
        name="Fill",
        size=4,
        default=(0.0, 0.0, 0.0, 1.0),
        subtype="COLOR",
        min=0.0,
        max=1.0,
    )


def post_unregister():
    for wm in bpy.data.window_managers:
        for attr in ("alec_mesh_attr_items", "alec_mesh_color_items", "alec_mesh_uv_items"):
            try:
                getattr(wm, attr).clear()
            except Exception:
                pass
    for attr in (
        "alec_mesh_attr_items", "alec_mesh_color_items", "alec_mesh_uv_items",
        "alec_mesh_attr_index", "alec_mesh_color_index", "alec_mesh_uv_index",
        "alec_mesh_attr_search", "alec_mesh_attr_source_names",
        "alec_mesh_attr_rename_section", "alec_mesh_attr_new_name",
        "alec_mesh_attr_use_fill", "alec_mesh_attr_fill_value",
    ):
        try:
            delattr(bpy.types.WindowManager, attr)
        except AttributeError:
            pass
