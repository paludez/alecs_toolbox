import os
import re
import shutil
import tempfile

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, StringProperty

from . import material_builder

_LAST_BROWSE_DIR = ""

# ---------------------------------------------------------------------------
# Texture file helpers
# ---------------------------------------------------------------------------

_KW_MAP_RULES = (
    "basecolor", "normal", "roughness", "metallic",
    "anisotropy",
    "specular", "gloss", "ao", "bump", "cavity", "displacement",
)
_OPTIONAL_MAP_KEYS = frozenset(("ao", "bump", "cavity", "displacement", "anisotropy"))


def _split_keywords(value: str) -> list[str]:
    return [k.strip().lower() for k in value.split(",") if k.strip()]


def _split_tags(value: str) -> list[str]:
    return [t.strip() for t in value.split(";") if t.strip()]


def _tokens(path: str) -> set[str]:
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    return set(re.split(r"[\s_\-\.]+", stem))


def _scan_images(folder: str) -> list[str]:
    try:
        return [
            os.path.join(folder, name)
            for name in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, name))
            and os.path.splitext(name)[1].lower() in material_builder.IMAGE_EXTENSIONS
        ]
    except OSError:
        return []


def _pick_by_keywords(images: list[str], keywords: str) -> str | None:
    keys = set(_split_keywords(keywords))
    if not keys:
        return None
    matches = [p for p in images if keys & _tokens(p)]
    if not matches:
        return None
    return min(matches, key=lambda p: material_builder.EXT_PRIORITY.get(os.path.splitext(p)[1].lower(), 99))


def _resolve_map_paths(op, images: list[str]) -> dict[str, str]:
    """Match texture files to map types using the operator's keyword properties."""
    remaining = list(images)
    out = {}
    for key in _KW_MAP_RULES:
        picked = _pick_by_keywords(remaining, getattr(op, f"kw_{key}"))
        if picked:
            out[key] = picked
            remaining.remove(picked)
    for key in _OPTIONAL_MAP_KEYS:
        if not getattr(op, f"use_{key}"):
            out.pop(key, None)
    return out


def _draw_keyword_rules(layout, op) -> None:
    layout.separator()
    layout.label(text="Keyword Rules (comma separated):")
    for key in _KW_MAP_RULES:
        layout.prop(op, f"kw_{key}")
    layout.separator()
    layout.label(text="Optional Maps")
    row = layout.row(align=True)
    row.prop(op, "use_ao")
    row.prop(op, "use_cavity")
    row = layout.row(align=True)
    row.prop(op, "use_bump")
    row.prop(op, "use_displacement")
    row = layout.row(align=True)
    row.prop(op, "use_anisotropy")


def _material_preview_scene_path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "Materials_Assets_Scene.blend")


def _active_material(context) -> bpy.types.Material | None:
    mat = getattr(context, "material", None)
    if isinstance(mat, bpy.types.Material):
        return mat
    obj = context.object
    if obj and getattr(obj, "active_material", None):
        return obj.active_material
    return None


def _rename_image_texture_nodes_to_map_names(mat: bpy.types.Material) -> int:
    """Set each Image Texture node's name to img.name. Clears node.label so the header matches (Blender shows label over name if label is set)."""
    if not mat or not mat.use_nodes or not mat.node_tree:
        return 0
    tree = mat.node_tree
    used = {n.name for n in tree.nodes}
    renamed = 0
    for node in tree.nodes:
        if node.type != "TEX_IMAGE" or node.image is None:
            continue
        base = node.image.name[:63]
        # Skip only when name already matches AND there is no custom label hiding it.
        if node.name == base and not node.label:
            continue

        used.discard(node.name)
        new_name = base
        n = 0
        while new_name in used:
            n += 1
            suffix = f"_{n}"
            new_name = (base[: 63 - len(suffix)] + suffix) if len(base) + len(suffix) > 63 else f"{base}{suffix}"
        node.name = new_name
        node.label = ""
        used.add(new_name)
        renamed += 1
    return renamed


def _preview_pick_operator_context(context) -> dict | None:
    win, screen = context.window, context.screen
    if win is None or screen is None:
        return None

    def window_region(area):
        return next((r for r in area.regions if r.type == "WINDOW"), None)

    for area in screen.areas:
        if area.type == "FILE_BROWSER" and getattr(area.spaces.active, "browse_mode", "") == "ASSETS":
            if (r := window_region(area)):
                return {"window": win, "screen": screen, "area": area, "region": r}

    for area_type in ("PROPERTIES", "VIEW_3D", "FILE_BROWSER"):
        for area in screen.areas:
            if area.type == area_type:
                if (r := window_region(area)):
                    return {"window": win, "screen": screen, "area": area, "region": r}
    return None


def _preview_apply_material(obj, mat) -> bool:
    if obj is None or obj.type != "MESH":
        return False
    if not obj.data.materials:
        obj.data.materials.append(mat)
    else:
        obj.material_slots[obj.active_material_index].material = mat
    return True


def _preview_capture_material(
    context, mat, sphere_obj, use_active_object_preview: bool, report
) -> bool:
    area_ctx = _preview_pick_operator_context(context)
    if area_ctx is None:
        report({"WARNING"}, "No usable UI area for preview generation.")
        return False

    if use_active_object_preview:
        try:
            with context.temp_override(
                **area_ctx,
                id=mat,
                object=sphere_obj,
                active_object=sphere_obj,
                selected_objects=[sphere_obj],
                selected_editable_objects=[sphere_obj],
            ):
                return "FINISHED" in bpy.ops.ed.lib_id_generate_preview_from_object()
        except Exception as e:
            report({"WARNING"}, f"Active object preview failed for '{mat.name}': {e}")
    else:
        try:
            with context.temp_override(**area_ctx, id=mat):
                return "FINISHED" in bpy.ops.ed.lib_id_generate_preview()
        except Exception as e:
            report({"WARNING"}, f"Screen capture preview failed for '{mat.name}': {e}")
    return False


def _preview_load_custom(context, mat, filepath: str, report) -> bool:
    area_ctx = _preview_pick_operator_context(context)
    if area_ctx is None:
        report({"WARNING"}, f"Load custom preview skipped for '{mat.name}': no UI area context.")
        return False

    abs_target = os.path.normcase(os.path.abspath(filepath))
    names_before = {img.name for img in bpy.data.images}
    ok = False
    try:
        with context.temp_override(**area_ctx, id=mat):
            ok = "FINISHED" in bpy.ops.ed.lib_id_load_custom_preview(filepath=filepath)
    except Exception as e:
        report({"WARNING"}, f"Load custom preview failed for '{mat.name}': {e}")
    finally:
        for img in list(bpy.data.images):
            if img.name in names_before or img.users > 0:
                continue
            try:
                path = os.path.normcase(os.path.abspath(bpy.path.abspath(img.filepath)))
            except Exception:
                path = ""
            if path == abs_target:
                try:
                    bpy.data.images.remove(img)
                except Exception:
                    pass
    return ok


def _preview_render_to_file(
    context,
    camera_obj,
    filepath: str,
    preview_resolution: int,
    report,
) -> bool:
    scene = context.scene
    render = scene.render
    img_settings = render.image_settings

    saved = {
        "camera": scene.camera,
        "filepath": render.filepath,
        "resolution_x": render.resolution_x,
        "resolution_y": render.resolution_y,
        "resolution_percentage": render.resolution_percentage,
        "file_format": img_settings.file_format,
        "color_mode": img_settings.color_mode,
        "film_transparent": render.film_transparent,
        "quality": getattr(img_settings, "quality", 90),
    }
    try:
        scene.camera = camera_obj
        render.filepath = filepath
        render.resolution_x = render.resolution_y = preview_resolution
        render.resolution_percentage = 100
        img_settings.file_format = "JPEG"
        img_settings.color_mode = "RGB"
        render.film_transparent = False
        if hasattr(img_settings, "quality"):
            img_settings.quality = 90
        bpy.ops.render.render(write_still=True)
        return os.path.isfile(filepath)
    except Exception as e:
        report({"WARNING"}, f"Render preview failed: {e}")
        return False
    finally:
        scene.camera = saved["camera"]
        render.filepath = saved["filepath"]
        render.resolution_x = saved["resolution_x"]
        render.resolution_y = saved["resolution_y"]
        render.resolution_percentage = saved["resolution_percentage"]
        img_settings.file_format = saved["file_format"]
        img_settings.color_mode = saved["color_mode"]
        render.film_transparent = saved["film_transparent"]
        if hasattr(img_settings, "quality"):
            img_settings.quality = saved["quality"]
        for img in list(bpy.data.images):
            if img.type == "RENDER_RESULT":
                try:
                    bpy.data.images.remove(img)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Keyword properties — declared once per operator class (Blender RNA requirement)
# ---------------------------------------------------------------------------

_KW_PROPS_DEFAULTS = {
    "kw_basecolor": "basecolor,base_color,diffuse,albedo,color,diff",
    "kw_normal": "normal,nrm,nor,norm",
    "kw_roughness": "roughness,rough",
    "kw_metallic": "metallic,metalness,metal",
    "kw_anisotropy": "anisotropy,aniso,anisotropic",
    "kw_ao": "ao,ambientocclusion,occlusion",
    "kw_displacement": "displacement,heightmap,height,disp",
    "kw_specular": "specular,spec",
    "kw_bump": "bump",
    "kw_gloss": "gloss,glossiness",
    "kw_cavity": "cavity",
}

# ---------------------------------------------------------------------------
# PropertyGroup for subfolder selection (lives on WindowManager)
# ---------------------------------------------------------------------------

class ALEC_PG_subfolder_item(bpy.types.PropertyGroup):
    name: StringProperty(name="Subfolder Name")  # type: ignore
    selected: BoolProperty(name="Selected", default=True)  # type: ignore


class ALEC_UL_subfolder_list(bpy.types.UIList):
    """Scrollable list of subfolders with checkbox per item."""

    bl_idname = "ALEC_UL_subfolder_list"

    def draw_item(
        self, _context, layout, _data, item, _icon, _active_data, _active_propname, index=0
    ):
        split = layout.split(factor=0.1, align=True)
        split.label(text=f"{index + 1}.")
        split.prop(item, "selected", text=item.name)

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        f = context.window_manager.alec_subfolder_filter.lower()
        flt_flags = [
            self.bitflag_filter_item if (not f or f in it.name.lower()) else 0
            for it in items
        ]
        return flt_flags, []


class ALEC_OT_batch_subfolder_action(bpy.types.Operator):
    """Select / deselect / invert visible subfolder items."""

    bl_idname = "alec.batch_subfolder_action"
    bl_label = ""
    bl_options = {"INTERNAL"}

    action: EnumProperty(  # type: ignore
        items=[("ALL", "All", ""), ("NONE", "None", ""), ("INVERT", "Invert", "")],
    )

    def execute(self, context):
        wm = context.window_manager
        f = wm.alec_subfolder_filter.lower()
        for it in wm.alec_subfolder_items:
            if f and f not in it.name.lower():
                continue
            if self.action == "ALL":
                it.selected = True
            elif self.action == "NONE":
                it.selected = False
            else:
                it.selected = not it.selected
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Make Mat From Tex
# ---------------------------------------------------------------------------

class ALEC_OT_make_mat_from_tex(bpy.types.Operator):
    """Create one material from textures in a selected folder."""

    bl_idname = "alec.make_mat_from_tex"
    bl_label = "Make Mat From Tex"
    bl_options = {"REGISTER", "UNDO"}

    directory: StringProperty(name="Texture Folder", subtype="DIR_PATH")  # type: ignore
    flip_normal_y: BoolProperty(name="Flip Green Channel", default=False)  # type: ignore
    apply_to_active: BoolProperty(
        name="Apply To Active Object",
        description="Assign the created material to the active mesh object",
        default=False,
    )  # type: ignore

    kw_basecolor: StringProperty(name="Base Color", default=_KW_PROPS_DEFAULTS["kw_basecolor"])  # type: ignore
    kw_normal: StringProperty(name="Normal", default=_KW_PROPS_DEFAULTS["kw_normal"])  # type: ignore
    kw_roughness: StringProperty(name="Roughness", default=_KW_PROPS_DEFAULTS["kw_roughness"])  # type: ignore
    kw_metallic: StringProperty(name="Metallic", default=_KW_PROPS_DEFAULTS["kw_metallic"])  # type: ignore
    kw_anisotropy: StringProperty(name="Anisotropy", default=_KW_PROPS_DEFAULTS["kw_anisotropy"])  # type: ignore
    kw_ao: StringProperty(name="AO", default=_KW_PROPS_DEFAULTS["kw_ao"])  # type: ignore
    kw_displacement: StringProperty(name="Displacement", default=_KW_PROPS_DEFAULTS["kw_displacement"])  # type: ignore
    kw_specular: StringProperty(name="Specular", default=_KW_PROPS_DEFAULTS["kw_specular"])  # type: ignore
    kw_bump: StringProperty(name="Bump", default=_KW_PROPS_DEFAULTS["kw_bump"])  # type: ignore
    kw_gloss: StringProperty(name="Gloss", default=_KW_PROPS_DEFAULTS["kw_gloss"])  # type: ignore
    kw_cavity: StringProperty(name="Cavity", default=_KW_PROPS_DEFAULTS["kw_cavity"])  # type: ignore
    use_ao: BoolProperty(name="Use AO", default=False)  # type: ignore
    use_bump: BoolProperty(name="Use Bump", default=False)  # type: ignore
    use_cavity: BoolProperty(name="Use Cavity", default=False)  # type: ignore
    use_displacement: BoolProperty(name="Use Displacement", default=False)  # type: ignore
    use_anisotropy: BoolProperty(name="Use Anisotropy", default=False)  # type: ignore

    def invoke(self, context, _event):
        if _LAST_BROWSE_DIR and os.path.isdir(_LAST_BROWSE_DIR):
            self.directory = _LAST_BROWSE_DIR
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "flip_normal_y")
        layout.prop(self, "apply_to_active")
        _draw_keyword_rules(layout, self)

    def execute(self, context):
        global _LAST_BROWSE_DIR
        folder = os.path.normpath(bpy.path.abspath(self.directory))
        if not os.path.isdir(folder):
            self.report({"ERROR"}, "Texture folder not found.")
            return {"CANCELLED"}
        _LAST_BROWSE_DIR = folder

        images = _scan_images(folder)
        if not images:
            self.report({"ERROR"}, "No image textures found in folder.")
            return {"CANCELLED"}

        paths_by_type = _resolve_map_paths(self, images)
        if not paths_by_type:
            self.report({"ERROR"}, "Could not match any texture maps by name.")
            return {"CANCELLED"}

        mat_name = material_builder.unique_material_name(os.path.basename(folder) or "Material")
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        material_builder.build_principled_tree(mat, paths_by_type, disp_scale=0.1, disp_bias=0.0, flip_normal_y=self.flip_normal_y)

        if self.apply_to_active:
            obj = context.active_object
            if obj and obj.type == "MESH":
                if not obj.data.materials:
                    obj.data.materials.append(mat)
                else:
                    obj.material_slots[obj.active_material_index].material = mat

        self.report({"INFO"}, f"Material '{mat_name}' created.")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Batch Materials base (not registered — subclass only)
# ---------------------------------------------------------------------------

def _batch_materials_root_dir_update(op, context):
    """Refresh subfolder list when Root Folder changes (stage-2 dialog only)."""
    if not op.selection_stage:
        return
    d = op.directory
    wm = context.window_manager
    if not d:
        wm.alec_subfolder_items.clear()
        wm.alec_subfolder_filter = ""
        wm.alec_subfolder_active_index = 0
        return
    root = os.path.normpath(bpy.path.abspath(d))
    if os.path.isdir(root):
        op._populate_subfolder_state(context, root)
    else:
        wm.alec_subfolder_items.clear()
        wm.alec_subfolder_filter = ""
        wm.alec_subfolder_active_index = 0
        wm.alec_batch_start = 1
        wm.alec_batch_end = 0
    win = context.window
    if win and win.screen:
        win.screen.tag_redraw()


class ALEC_OT_batch_materials(bpy.types.Operator):
    """Base for batch material operators. Not registered directly."""

    bl_idname = "alec.batch_materials"
    bl_label = "Batch Materials"
    bl_options = {"UNDO"}

    directory: StringProperty(
        name="Root Folder",
        subtype="DIR_PATH",
        update=_batch_materials_root_dir_update,
    )  # type: ignore
    selection_stage: BoolProperty(default=False, options={"HIDDEN"})  # type: ignore
    process_all_subfolders: BoolProperty(
        name="Process All Subfolders",
        description="Skip selection and process every direct subfolder",
        default=False,
    )  # type: ignore
    asset_tags: StringProperty(
        name="Asset Tags",
        description="Semicolon-separated tags (ex: beton;exterior;pbr)",
        default="",
    )  # type: ignore
    mark_as_asset: BoolProperty(name="Mark As Asset", default=True)  # type: ignore
    skip_existing: BoolProperty(
        name="Skip Existing",
        description="Skip folders whose material name already exists in this file",
        default=True,
    )  # type: ignore
    auto_save: BoolProperty(
        name="Auto Save",
        description="Save the file every N materials processed",
        default=True,
    )  # type: ignore
    auto_save_interval: IntProperty(
        name="Every N",
        default=10,
        min=1,
    )  # type: ignore
    flip_normal_y: BoolProperty(name="Flip Normal Y", default=False)  # type: ignore

    kw_basecolor: StringProperty(name="Base Color", default=_KW_PROPS_DEFAULTS["kw_basecolor"])  # type: ignore
    kw_normal: StringProperty(name="Normal", default=_KW_PROPS_DEFAULTS["kw_normal"])  # type: ignore
    kw_roughness: StringProperty(name="Roughness", default=_KW_PROPS_DEFAULTS["kw_roughness"])  # type: ignore
    kw_metallic: StringProperty(name="Metallic", default=_KW_PROPS_DEFAULTS["kw_metallic"])  # type: ignore
    kw_anisotropy: StringProperty(name="Anisotropy", default=_KW_PROPS_DEFAULTS["kw_anisotropy"])  # type: ignore
    kw_ao: StringProperty(name="AO", default=_KW_PROPS_DEFAULTS["kw_ao"])  # type: ignore
    kw_displacement: StringProperty(name="Displacement", default=_KW_PROPS_DEFAULTS["kw_displacement"])  # type: ignore
    kw_specular: StringProperty(name="Specular", default=_KW_PROPS_DEFAULTS["kw_specular"])  # type: ignore
    kw_bump: StringProperty(name="Bump", default=_KW_PROPS_DEFAULTS["kw_bump"])  # type: ignore
    kw_gloss: StringProperty(name="Gloss", default=_KW_PROPS_DEFAULTS["kw_gloss"])  # type: ignore
    kw_cavity: StringProperty(name="Cavity", default=_KW_PROPS_DEFAULTS["kw_cavity"])  # type: ignore
    use_ao: BoolProperty(name="Use AO", default=False)  # type: ignore
    use_bump: BoolProperty(name="Use Bump", default=False)  # type: ignore
    use_cavity: BoolProperty(name="Use Cavity", default=False)  # type: ignore
    use_displacement: BoolProperty(name="Use Displacement", default=False)  # type: ignore
    use_anisotropy: BoolProperty(name="Use Anisotropy", default=False)  # type: ignore

    def _reinvoke_kwargs(self) -> dict:
        # Only pass directory — stage 1 shows no properties to the user, so all
        # keyword/option settings keep their defaults in stage 2.  Passing many
        # StringProperty values through bpy.ops allocates C blocks that Blender
        # does not reliably free when the dialog is cancelled.
        return {
            "directory": self.directory,
            "selection_stage": True,
            "process_all_subfolders": self.process_all_subfolders,
        }

    def _reinvoke_for_selection(self):
        bpy.ops.alec.batch_materials("INVOKE_DEFAULT", **self._reinvoke_kwargs())

    def invoke(self, context, _event):
        if self.selection_stage:
            root = os.path.normpath(bpy.path.abspath(self.directory))
            if not os.path.isdir(root):
                self.report({"ERROR"}, "Root folder not found.")
                return {"CANCELLED"}
            self._populate_subfolder_state(context, root)
            return context.window_manager.invoke_props_dialog(self, width=560)
        if _LAST_BROWSE_DIR and os.path.isdir(_LAST_BROWSE_DIR):
            self.directory = _LAST_BROWSE_DIR
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        wm = context.window_manager
        wm.alec_subfolder_items.clear()
        wm.alec_subfolder_filter = ""
        wm.alec_subfolder_active_index = 0
        wm.alec_batch_start = 1
        wm.alec_batch_end = 0

    def draw(self, _context):
        layout = self.layout
        if not self.selection_stage:
            return
        layout.prop(self, "directory")
        layout.separator()
        layout.prop(self, "process_all_subfolders")
        layout.separator()
        wm = bpy.context.window_manager
        if self.process_all_subfolders:
            layout.label(text="All direct subfolders will be processed.", icon="INFO")
        else:
            row = layout.row(align=True)
            row.prop(wm, "alec_subfolder_filter", text="", icon="VIEWZOOM")
            row.separator()
            for label, action in (("All", "ALL"), ("None", "NONE"), ("Invert", "INVERT")):
                row.operator("alec.batch_subfolder_action", text=label).action = action
            if wm.alec_subfolder_items:
                layout.template_list(
                    "ALEC_UL_subfolder_list", "",
                    wm, "alec_subfolder_items",
                    wm, "alec_subfolder_active_index",
                    rows=8,
                )
            else:
                layout.label(text="No direct subfolders found. Root folder will be processed.")
        row = layout.row(align=True)
        row.label(text="Range:")
        row.prop(wm, "alec_batch_start")
        row.prop(wm, "alec_batch_end")
        row.label(text="(0 = until last)")
        layout.prop(self, "skip_existing")
        row = layout.row(align=True)
        row.prop(self, "auto_save")
        sub = row.row(align=True)
        sub.enabled = self.auto_save
        sub.prop(self, "auto_save_interval")
        layout.prop(self, "flip_normal_y")
        row = layout.row(align=True)
        row.prop(self, "mark_as_asset")
        row.prop(self, "asset_tags")
        _draw_keyword_rules(layout, self)

    def _populate_subfolder_state(self, context, root: str) -> None:
        wm = context.window_manager
        wm.alec_subfolder_items.clear()
        wm.alec_subfolder_filter = ""
        wm.alec_subfolder_active_index = 0
        wm.alec_batch_start = 1
        wm.alec_batch_end = 0
        try:
            names = sorted(n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n)))
        except OSError:
            names = []
        for name in names:
            item = wm.alec_subfolder_items.add()
            item.name = name
            item.selected = True

    def _selected_subfolder_names(self, context) -> list[str]:
        return [it.name for it in context.window_manager.alec_subfolder_items if it.selected]

    def _target_subfolders(self, context, root: str) -> list[str] | None:
        try:
            all_dirs = sorted(
                os.path.join(root, n)
                for n in os.listdir(root)
                if os.path.isdir(os.path.join(root, n))
            )
        except OSError as e:
            self.report({"ERROR"}, f"Could not list root folder: {e}")
            return None
        if not all_dirs:
            return [root]
        if self.process_all_subfolders:
            return all_dirs
        selected = set(self._selected_subfolder_names(context))
        wm_items = context.window_manager.alec_subfolder_items
        if not selected:
            return [] if wm_items else all_dirs
        return [p for p in all_dirs if os.path.basename(p) in selected]

    def _build_material_for_folder(self, folder: str):
        images = _scan_images(folder)
        if not images:
            return None
        paths_by_type = _resolve_map_paths(self, images)
        if not paths_by_type:
            return None
        mat_name = material_builder.unique_material_name(os.path.basename(folder))
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        material_builder.build_principled_tree(mat, paths_by_type, 0.1, 0.0, self.flip_normal_y)
        return mat

    def _apply_asset_metadata(self, mat, root_name: str) -> None:
        if not self.mark_as_asset:
            return
        mat.asset_mark()
        ad = mat.asset_data
        if ad is None:
            return
        seen: set[str] = set()
        for tag in [root_name] + _split_tags(self.asset_tags):
            key = tag.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            try:
                ad.tags.new(tag, skip_if_exists=True)
            except Exception:
                pass

    def _set_asset_browser_current_file(self, context) -> None:
        win, screen = context.window, context.screen
        if win is None or screen is None:
            return
        for area in screen.areas:
            if area.type != "FILE_BROWSER":
                continue
            space = area.spaces.active
            if getattr(space, "browse_mode", "") != "ASSETS":
                continue
            params = getattr(space, "params", None)
            if params is None:
                break
            for attr, val in (
                ("asset_library_reference", "LOCAL"),
                ("catalog_id", "00000000-0000-0000-0000-000000000000"),
            ):
                try:
                    setattr(params, attr, val)
                except Exception:
                    pass
            break

    # --- Per-folder logic (overridden by subclass) ---

    def _process_one_folder(self, context, folder: str) -> bool:
        """Process one folder. Returns True if created, False if skipped."""
        if self.skip_existing:
            if bpy.path.clean_name(os.path.basename(folder)) in bpy.data.materials:
                return False
        mat = self._build_material_for_folder(folder)
        if mat is None:
            return False
        self._apply_asset_metadata(mat, self._root_name)
        return True

    def _setup_modal_state(self, context) -> bool:
        """Called once before modal loop starts. Return False to abort."""
        self._set_asset_browser_current_file(context)
        return True

    def _cleanup_wm(self, wm) -> None:
        wm.alec_subfolder_items.clear()
        wm.alec_subfolder_filter = ""
        wm.alec_subfolder_active_index = 0
        wm.alec_batch_start = 1
        wm.alec_batch_end = 0

    def _finish(self, context) -> None:
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        wm.progress_end()
        self._cleanup_wm(wm)
        self._set_asset_browser_current_file(context)
        self.report({"INFO"}, f"Batch Materials: {self._created} created, {self._skipped} skipped.")

    # --- Operator lifecycle ---

    def execute(self, context):
        global _LAST_BROWSE_DIR
        root = os.path.normpath(bpy.path.abspath(self.directory))
        if not os.path.isdir(root):
            self.report({"ERROR"}, "Root folder not found.")
            return {"CANCELLED"}
        _LAST_BROWSE_DIR = root

        if not self.selection_stage:
            self._populate_subfolder_state(context, root)
            self._reinvoke_for_selection()
            # Return FINISHED so Blender destroys this (stage 1) operator instance
            # and frees its StringProperty allocations. Stage 2 runs independently.
            return {"FINISHED"}

        subfolders = self._target_subfolders(context, root)
        if subfolders is None:
            return {"CANCELLED"}
        if not subfolders:
            self.report({"WARNING"}, "No target subfolders found.")
            return {"CANCELLED"}

        self._root_name = os.path.basename(root.rstrip("\\/")) or "Materials"
        self._folders = subfolders
        self._idx = 0
        self._created = 0
        self._skipped = 0

        if not self._setup_modal_state(context):
            return {"CANCELLED"}

        wm = context.window_manager
        wm.progress_begin(0, len(subfolders))
        self._timer = wm.event_timer_add(0.001, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}


    def modal(self, context, event):
        if event.type == "ESC":
            self.cancel(context)
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        if self._idx >= len(self._folders):
            self._finish(context)
            return {"FINISHED"}
        folder = self._folders[self._idx]
        if self._process_one_folder(context, folder):
            self._created += 1
        else:
            self._skipped += 1
        self._idx += 1
        context.window_manager.progress_update(self._idx)
        if self.auto_save and bpy.data.filepath and self._idx % self.auto_save_interval == 0:
            try:
                bpy.ops.wm.save_mainfile("EXEC_DEFAULT", check_existing=False)
            except Exception:
                pass
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        wm = context.window_manager
        if hasattr(self, "_timer") and self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        wm.progress_end()
        self._cleanup_wm(wm)


# ---------------------------------------------------------------------------
# Batch Materials + Capture Previews
# ---------------------------------------------------------------------------

class ALEC_OT_batch_materials_capture_previews(ALEC_OT_batch_materials):
    """Batch Materials + mark as assets + optionally capture previews."""

    bl_idname = "alec.batch_materials_capture_previews"
    bl_label = "Batch Materials + Capture Previews"
    bl_options = {"UNDO"}

    generate_previews: BoolProperty(
        name="Generate Previews",
        description="Generate thumbnails for created materials",
        default=True,
    )  # type: ignore
    preview_sphere_name: StringProperty(name="Sphere Object", default="Sphere")  # type: ignore
    preview_plane_name: StringProperty(name="Plane Object", default="Plane")  # type: ignore
    use_active_object_preview: BoolProperty(
        name="Use Active Object Preview",
        description="If off, render from camera and load as custom preview",
        default=False,
    )  # type: ignore
    preview_camera_name: StringProperty(name="Camera Object", default="Camera")  # type: ignore
    preview_resolution: IntProperty(name="Preview Resolution", default=256, min=64, max=2048)  # type: ignore

    def _reinvoke_for_selection(self):
        bpy.ops.alec.batch_materials_capture_previews("INVOKE_DEFAULT", **self._reinvoke_kwargs())

    def draw(self, context):
        super().draw(context)
        if not self.selection_stage:
            return
        layout = self.layout
        layout.separator()
        layout.prop(self, "generate_previews")
        if not self.generate_previews:
            return
        layout.separator()
        layout.label(text="Preview Scene Objects")
        layout.prop(self, "use_active_object_preview")
        layout.prop(self, "preview_sphere_name")
        layout.prop(self, "preview_plane_name")
        if not self.use_active_object_preview:
            layout.prop(self, "preview_camera_name")
            layout.prop(self, "preview_resolution")

    # --- Preview helpers ---

    def _apply_material(self, obj, mat) -> bool:
        return _preview_apply_material(obj, mat)

    def _pick_operator_context(self, context) -> dict | None:
        return _preview_pick_operator_context(context)

    def _capture_material_preview(self, context, mat, sphere_obj) -> bool:
        return _preview_capture_material(
            context, mat, sphere_obj, self.use_active_object_preview, self.report
        )

    def _load_custom_preview(self, context, mat, filepath: str) -> bool:
        return _preview_load_custom(context, mat, filepath, self.report)

    def _render_preview_to_file(self, context, camera_obj, filepath: str) -> bool:
        return bool(
            _preview_render_to_file(
                context,
                camera_obj,
                filepath,
                self.preview_resolution,
                self.report,
            )
        )

    # --- Modal overrides ---

    def _setup_modal_state(self, context) -> bool:
        self._sphere_obj = self._plane_obj = self._camera_obj = None
        self._temp_dir = None
        self._preview_ok = 0
        self._preview_fail = 0
        if not self.generate_previews:
            return True
        sphere_obj = bpy.data.objects.get(self.preview_sphere_name)
        plane_obj = bpy.data.objects.get(self.preview_plane_name)
        if sphere_obj is None or plane_obj is None:
            self.report({"ERROR"}, f"Preview objects not found: '{self.preview_sphere_name}' / '{self.preview_plane_name}'.")
            return False
        if not self.use_active_object_preview:
            camera_obj = bpy.data.objects.get(self.preview_camera_name)
            if camera_obj is None or camera_obj.type != "CAMERA":
                self.report({"ERROR"}, f"Camera object not found or invalid: '{self.preview_camera_name}'.")
                return False
            self._camera_obj = camera_obj
        self._sphere_obj = sphere_obj
        self._plane_obj = plane_obj
        self._temp_dir = tempfile.mkdtemp(prefix="alecs_batch_preview_")
        return True

    def _process_one_folder(self, context, folder: str) -> bool:
        if self.skip_existing:
            if bpy.path.clean_name(os.path.basename(folder)) in bpy.data.materials:
                return False
        mat = self._build_material_for_folder(folder)
        if mat is None:
            return False
        self._apply_asset_metadata(mat, self._root_name)
        if self.generate_previews:
            self._apply_material(self._sphere_obj, mat)
            self._apply_material(self._plane_obj, mat)
            if self._sphere_obj.mode != "OBJECT":
                try:
                    bpy.ops.object.mode_set(mode="OBJECT")
                except Exception:
                    pass
            self._sphere_obj.select_set(True)
            self._plane_obj.select_set(False)
            context.view_layer.objects.active = self._sphere_obj
            context.view_layer.update()
            if self.use_active_object_preview:
                ok = self._capture_material_preview(context, mat, self._sphere_obj)
            else:
                preview_file = os.path.join(self._temp_dir, f"{mat.name}.jpg")
                ok = (
                    self._render_preview_to_file(context, self._camera_obj, preview_file)
                    and self._load_custom_preview(context, mat, preview_file)
                )
            if ok:
                self._preview_ok += 1
            else:
                self._preview_fail += 1
        return True

    def _finish(self, context) -> None:
        td = getattr(self, "_temp_dir", None)
        if td:
            shutil.rmtree(td, ignore_errors=True)
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        wm.progress_end()
        self._cleanup_wm(wm)
        self._set_asset_browser_current_file(context)
        msg = f"Batch+Previews: {self._created} created, {self._skipped} skipped."
        if self.generate_previews:
            msg += f" Previews: {self._preview_ok} ok, {self._preview_fail} failed."
        self.report({"INFO"}, msg)

    def cancel(self, context):
        td = getattr(self, "_temp_dir", None)
        if td:
            shutil.rmtree(td, ignore_errors=True)
        super().cancel(context)


class ALEC_OT_material_preview_rename_tex_nodes(bpy.types.Operator):
    """Rename Image Texture nodes to map file names, then capture material preview."""

    bl_idname = "alec.material_preview_rename_tex_nodes"
    bl_label = "Preview + Rename Tex Nodes"
    bl_options = {"REGISTER", "UNDO"}

    use_active_object_preview: BoolProperty(
        name="Use Active Object Preview",
        description="If off, render from camera and load as custom preview",
        default=False,
    )  # type: ignore
    preview_sphere_name: StringProperty(name="Sphere Object", default="Sphere")  # type: ignore
    preview_plane_name: StringProperty(name="Plane Object", default="Plane")  # type: ignore
    preview_camera_name: StringProperty(name="Camera Object", default="Camera")  # type: ignore
    preview_resolution: IntProperty(name="Preview Resolution", default=256, min=64, max=2048)  # type: ignore

    @classmethod
    def poll(cls, context):
        return _active_material(context) is not None

    def execute(self, context):
        mat = _active_material(context)
        if not mat or not mat.use_nodes:
            self.report({"WARNING"}, "Need an active material with nodes.")
            return {"CANCELLED"}

        renamed = _rename_image_texture_nodes_to_map_names(mat)

        sphere_obj = bpy.data.objects.get(self.preview_sphere_name)
        plane_obj = bpy.data.objects.get(self.preview_plane_name)
        if sphere_obj is None or plane_obj is None:
            self.report(
                {"ERROR"},
                f"Preview objects not found: '{self.preview_sphere_name}' / '{self.preview_plane_name}'. "
                "Open the Material Preview Scene.",
            )
            return {"CANCELLED"}

        camera_obj = None
        temp_dir = None
        if not self.use_active_object_preview:
            camera_obj = bpy.data.objects.get(self.preview_camera_name)
            if camera_obj is None or camera_obj.type != "CAMERA":
                self.report({"ERROR"}, f"Camera not found: '{self.preview_camera_name}'.")
                return {"CANCELLED"}
            temp_dir = tempfile.mkdtemp(prefix="alecs_preview_")

        _preview_apply_material(sphere_obj, mat)
        _preview_apply_material(plane_obj, mat)
        if sphere_obj.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass
        sphere_obj.select_set(True)
        plane_obj.select_set(False)
        context.view_layer.objects.active = sphere_obj
        context.view_layer.update()

        ok = False
        try:
            if self.use_active_object_preview:
                ok = _preview_capture_material(
                    context, mat, sphere_obj, self.use_active_object_preview, self.report
                )
            else:
                assert temp_dir is not None and camera_obj is not None
                preview_file = os.path.join(temp_dir, f"{mat.name}.jpg")
                ok = bool(
                    _preview_render_to_file(
                        context,
                        camera_obj,
                        preview_file,
                        self.preview_resolution,
                        self.report,
                    )
                ) and _preview_load_custom(context, mat, preview_file, self.report)
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

        if ok:
            self.report({"INFO"}, f"Preview OK. Renamed {renamed} Image Texture node(s).")
        else:
            self.report({"WARNING"}, f"Preview failed. Renamed {renamed} Image Texture node(s).")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Open Material Preview Scene
# ---------------------------------------------------------------------------

class ALEC_OT_open_material_preview_scene(bpy.types.Operator):
    """Open bundled material preview scene."""

    bl_idname = "alec.open_material_preview_scene"
    bl_label = "Open Material Preview Scene"

    unsaved_action: EnumProperty(  # type: ignore
        name="Action",
        items=(
            ("SAVE", "Save Current Scene", "Save current scene before loading"),
            ("DONT_SAVE", "Don't Save", "Discard changes and load preview scene"),
            ("CANCEL", "Cancel", "Cancel"),
        ),
        default="DONT_SAVE",
    )

    def invoke(self, context, _event):
        if bpy.data.is_dirty:
            return context.window_manager.invoke_props_dialog(self, width=560)
        return self.execute(context)

    def draw(self, _context):
        layout = self.layout
        layout.label(text="Current scene has unsaved changes.", icon="ERROR")
        layout.label(text="How do you want to continue?")
        layout.prop(self, "unsaved_action", text="")

    def execute(self, context):
        if bpy.data.is_dirty:
            action = self.unsaved_action
            if action == "CANCEL":
                return {"CANCELLED"}
            if action == "SAVE":
                try:
                    op = bpy.ops.wm.save_mainfile
                    result = op("EXEC_DEFAULT") if bpy.data.filepath else op("INVOKE_DEFAULT")
                    if "FINISHED" not in result:
                        return {"CANCELLED"}
                except Exception as e:
                    self.report({"ERROR"}, f"Could not save current file: {e}")
                    return {"CANCELLED"}

        preview_scene = _material_preview_scene_path()
        if not os.path.isfile(preview_scene):
            self.report({"ERROR"}, f"Preview scene not found: {preview_scene}")
            return {"CANCELLED"}
        bpy.ops.wm.open_mainfile("EXEC_DEFAULT", filepath=preview_scene)
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    ALEC_PG_subfolder_item,
    ALEC_UL_subfolder_list,
    ALEC_OT_batch_subfolder_action,
    ALEC_OT_make_mat_from_tex,
    ALEC_OT_open_material_preview_scene,
    ALEC_OT_batch_materials_capture_previews,
    ALEC_OT_material_preview_rename_tex_nodes,
)


def _on_subfolder_filter_update(wm, _context):
    f = wm.alec_subfolder_filter.lower()
    for it in wm.alec_subfolder_items:
        it.selected = not f or f in it.name.lower()


def _on_subfolder_range_update(wm, _context):
    start = wm.alec_batch_start - 1  # convert to 0-based
    end = wm.alec_batch_end or None
    for idx, it in enumerate(wm.alec_subfolder_items):
        it.selected = start <= idx and (end is None or idx < end)


def post_register():
    bpy.types.WindowManager.alec_subfolder_items = CollectionProperty(type=ALEC_PG_subfolder_item)
    bpy.types.WindowManager.alec_subfolder_filter = StringProperty(
        default="", update=_on_subfolder_filter_update
    )
    bpy.types.WindowManager.alec_subfolder_active_index = IntProperty(default=0)
    bpy.types.WindowManager.alec_batch_start = IntProperty(
        name="From", default=1, min=1, update=_on_subfolder_range_update
    )
    bpy.types.WindowManager.alec_batch_end = IntProperty(
        name="To", default=0, min=0,
        description="0 = until last",
        update=_on_subfolder_range_update,
    )


def post_unregister():
    for wm in bpy.data.window_managers:
        try:
            wm.alec_subfolder_items.clear()
        except Exception:
            pass
    for attr in (
        "alec_subfolder_items", "alec_subfolder_filter",
        "alec_subfolder_active_index", "alec_batch_start", "alec_batch_end",
    ):
        try:
            delattr(bpy.types.WindowManager, attr)
        except AttributeError:
            pass
