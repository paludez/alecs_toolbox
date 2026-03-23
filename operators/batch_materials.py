import os
import json
import re
import shutil
import tempfile
import uuid

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.app.handlers import persistent

from . import material_builder

_BATCH_PREVIEW_PAYLOAD_KEY = "_alec_batch_preview_payload"
_BATCH_PREVIEW_PAYLOAD_FILE = os.path.join(tempfile.gettempdir(), "alec_batch_preview_payload.json")


def _invoke_batch_continue_prompt():
    if not os.path.isfile(_BATCH_PREVIEW_PAYLOAD_FILE):
        return None
    try:
        bpy.ops.alec.batch_materials_continue_after_open("INVOKE_DEFAULT")
        return None
    except Exception:
        # UI may not be ready immediately after file load.
        return 0.5


@persistent
def _on_file_load_post(_dummy):
    if os.path.isfile(_BATCH_PREVIEW_PAYLOAD_FILE):
        bpy.app.timers.register(_invoke_batch_continue_prompt, first_interval=0.5)


def _split_keywords(value):
    return [k.strip().lower() for k in value.split(",") if k.strip()]


def _split_tags_semicolon(value):
    return [t.strip() for t in value.split(";") if t.strip()]


def _norm_stem(path):
    return os.path.splitext(os.path.basename(path))[0].lower()


def _tokens(stem):
    return [t for t in re.split(r"[\s_\-\.]+", stem.lower()) if t]


def _scan_images(folder):
    out = []
    try:
        for name in os.listdir(folder):
            p = os.path.join(folder, name)
            if not os.path.isfile(p):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in material_builder.IMAGE_EXTENSIONS:
                out.append(p)
    except OSError:
        return []
    return out


def _pick_best_by_ext(paths):
    if not paths:
        return None
    return sorted(
        paths,
        key=lambda p: material_builder.EXT_PRIORITY.get(os.path.splitext(p)[1].lower(), 99),
    )[0]


def _pick_by_keywords(images, keywords):
    keys = set(_split_keywords(keywords))
    if not keys:
        return None
    matches = []
    for p in images:
        toks = set(_tokens(_norm_stem(p)))
        # Prefer explicit token matches; no broad substring match to avoid false positives.
        if keys & toks:
            matches.append(p)
    return _pick_best_by_ext(matches)


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
    kw_basecolor: StringProperty(name="Base Color", default="basecolor,base_color,diffuse,albedo,color")  # type: ignore
    kw_normal: StringProperty(name="Normal", default="normal,nrm,nor")  # type: ignore
    kw_roughness: StringProperty(name="Roughness", default="roughness,rough")  # type: ignore
    kw_metallic: StringProperty(name="Metallic", default="metallic,metalness,metal")  # type: ignore
    kw_ao: StringProperty(name="AO", default="ao,ambientocclusion,occlusion")  # type: ignore
    kw_displacement: StringProperty(name="Displacement", default="displacement,height,disp")  # type: ignore
    kw_specular: StringProperty(name="Specular", default="specular,spec")  # type: ignore
    kw_bump: StringProperty(name="Bump", default="bump")  # type: ignore
    kw_gloss: StringProperty(name="Gloss", default="gloss,glossiness")  # type: ignore
    kw_cavity: StringProperty(name="Cavity", default="cavity")  # type: ignore
    use_ao: BoolProperty(name="Use AO", default=False)  # type: ignore
    use_bump: BoolProperty(name="Use Bump", default=False)  # type: ignore
    use_cavity: BoolProperty(name="Use Cavity", default=False)  # type: ignore
    use_displacement: BoolProperty(name="Use Displacement", default=False)  # type: ignore

    def invoke(self, context, _event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "directory")
        layout.prop(self, "flip_normal_y")
        layout.prop(self, "apply_to_active")
        layout.separator()
        layout.label(text="Keyword Rules (comma separated):")
        layout.prop(self, "kw_basecolor")
        layout.prop(self, "kw_normal")
        layout.prop(self, "kw_roughness")
        layout.prop(self, "kw_metallic")
        layout.prop(self, "kw_ao")
        layout.prop(self, "kw_displacement")
        layout.prop(self, "kw_specular")
        layout.prop(self, "kw_bump")
        layout.prop(self, "kw_gloss")
        layout.prop(self, "kw_cavity")
        layout.separator()
        layout.label(text="Optional Maps")
        row = layout.row(align=True)
        row.prop(self, "use_ao")
        row.prop(self, "use_cavity")
        row = layout.row(align=True)
        row.prop(self, "use_bump")
        row.prop(self, "use_displacement")

    def _build_map_paths(self, images):
        out = {}
        remaining = list(images)
        rules = [
            ("basecolor", self.kw_basecolor),
            ("normal", self.kw_normal),
            ("roughness", self.kw_roughness),
            ("metallic", self.kw_metallic),
            ("specular", self.kw_specular),
            ("gloss", self.kw_gloss),
            ("ao", self.kw_ao),
            ("bump", self.kw_bump),
            ("cavity", self.kw_cavity),
            ("displacement", self.kw_displacement),
        ]
        for map_type, kw in rules:
            picked = _pick_by_keywords(remaining, kw)
            out[map_type] = picked
            if picked in remaining:
                remaining.remove(picked)
        if not self.use_ao:
            out.pop("ao", None)
        if not self.use_bump:
            out.pop("bump", None)
        if not self.use_cavity:
            out.pop("cavity", None)
        if not self.use_displacement:
            out.pop("displacement", None)
        return out

    def execute(self, context):
        folder = bpy.path.abspath(self.directory)
        folder = os.path.normpath(folder)
        if not os.path.isdir(folder):
            self.report({"ERROR"}, "Texture folder not found.")
            return {"CANCELLED"}

        images = _scan_images(folder)
        if not images:
            self.report({"ERROR"}, "No image textures found in folder.")
            return {"CANCELLED"}

        paths_by_type = {k: v for k, v in self._build_map_paths(images).items() if v}

        if not paths_by_type:
            self.report({"ERROR"}, "Could not match any texture maps by name.")
            return {"CANCELLED"}

        mat_name = material_builder.unique_material_name(os.path.basename(folder) or "Material")
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        material_builder.build_principled_tree(
            mat,
            paths_by_type,
            disp_scale=0.1,
            disp_bias=0.0,
            flip_normal_y=self.flip_normal_y,
        )

        # Optional: assign to active mesh object only when requested.
        if self.apply_to_active:
            obj = context.active_object
            if obj and obj.type == "MESH":
                if not obj.data.materials:
                    obj.data.materials.append(mat)
                else:
                    obj.material_slots[obj.active_material_index].material = mat

        self.report({"INFO"}, f"Material '{mat_name}' created from folder textures.")
        return {"FINISHED"}


class ALEC_OT_batch_materials(bpy.types.Operator):
    """Create one material per direct subfolder from texture keywords."""

    bl_idname = "alec.batch_materials"
    bl_label = "Batch Materials"
    bl_options = {"REGISTER", "UNDO"}

    directory: StringProperty(name="Root Folder", subtype="DIR_PATH")  # type: ignore
    asset_tags: StringProperty(
        name="Asset Tags",
        description="Semicolon-separated tags (ex: beton;exterior;pbr)",
        default="",
    )  # type: ignore
    mark_as_asset: BoolProperty(name="Mark As Asset", default=True)  # type: ignore

    flip_normal_y: BoolProperty(name="Flip Normal Y", default=False)  # type: ignore

    kw_basecolor: StringProperty(name="Base Color", default="basecolor,base_color,diffuse,albedo,color")  # type: ignore
    kw_normal: StringProperty(name="Normal", default="normal,nrm,nor")  # type: ignore
    kw_roughness: StringProperty(name="Roughness", default="roughness,rough")  # type: ignore
    kw_metallic: StringProperty(name="Metallic", default="metallic,metalness,metal")  # type: ignore
    kw_ao: StringProperty(name="AO", default="ao,ambientocclusion,occlusion")  # type: ignore
    kw_displacement: StringProperty(name="Displacement", default="displacement,height,disp")  # type: ignore
    kw_specular: StringProperty(name="Specular", default="specular,spec")  # type: ignore
    kw_bump: StringProperty(name="Bump", default="bump")  # type: ignore
    kw_gloss: StringProperty(name="Gloss", default="gloss,glossiness")  # type: ignore
    kw_cavity: StringProperty(name="Cavity", default="cavity")  # type: ignore
    use_ao: BoolProperty(name="Use AO", default=False)  # type: ignore
    use_bump: BoolProperty(name="Use Bump", default=False)  # type: ignore
    use_cavity: BoolProperty(name="Use Cavity", default=False)  # type: ignore
    use_displacement: BoolProperty(name="Use Displacement", default=False)  # type: ignore
    _catalog_id_cache: str | None = None
    _catalog_path_cache: str = ""

    def invoke(self, context, _event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "directory")
        layout.prop(self, "flip_normal_y")
        row = layout.row(align=True)
        row.prop(self, "mark_as_asset")
        row.prop(self, "asset_tags")
        layout.separator()
        layout.label(text="Keyword Rules (comma separated):")
        layout.prop(self, "kw_basecolor")
        layout.prop(self, "kw_normal")
        layout.prop(self, "kw_roughness")
        layout.prop(self, "kw_metallic")
        layout.prop(self, "kw_ao")
        layout.prop(self, "kw_displacement")
        layout.prop(self, "kw_specular")
        layout.prop(self, "kw_bump")
        layout.prop(self, "kw_gloss")
        layout.prop(self, "kw_cavity")
        layout.separator()
        layout.label(text="Optional Maps")
        row = layout.row(align=True)
        row.prop(self, "use_ao")
        row.prop(self, "use_cavity")
        row = layout.row(align=True)
        row.prop(self, "use_bump")
        row.prop(self, "use_displacement")

    def _build_map_paths(self, images):
        out = {}
        remaining = list(images)
        # Resolve in strict priority so one file is used for one map only.
        rules = [
            ("basecolor", self.kw_basecolor),
            ("normal", self.kw_normal),
            ("roughness", self.kw_roughness),
            ("metallic", self.kw_metallic),
            ("specular", self.kw_specular),
            ("gloss", self.kw_gloss),
            ("ao", self.kw_ao),
            ("bump", self.kw_bump),
            ("cavity", self.kw_cavity),
            ("displacement", self.kw_displacement),
        ]
        for map_type, kw in rules:
            picked = _pick_by_keywords(remaining, kw)
            out[map_type] = picked
            if picked in remaining:
                remaining.remove(picked)
        if not self.use_ao:
            out.pop("ao", None)
        if not self.use_bump:
            out.pop("bump", None)
        if not self.use_cavity:
            out.pop("cavity", None)
        if not self.use_displacement:
            out.pop("displacement", None)
        return out

    def _catalog_file_current_blend(self):
        if not bpy.data.filepath:
            return None
        return os.path.join(os.path.dirname(bpy.data.filepath), "blender_assets.cats.txt")

    def _read_catalogs(self, cats_path):
        out = {}
        if not os.path.isfile(cats_path):
            return out
        try:
            with open(cats_path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#") or line.startswith("VERSION"):
                        continue
                    parts = line.split(":")
                    if len(parts) >= 3:
                        out[parts[1]] = parts[0]
        except OSError:
            return {}
        return out

    def _ensure_catalogs_current_file(self, root_name):
        cats_path = self._catalog_file_current_blend()
        if not cats_path:
            self.report({"WARNING"}, "Save the .blend first to assign Current File catalogs.")
            return None

        wanted = [("Materials", "Materials"), (f"Materials/{root_name}", root_name)]
        existing = self._read_catalogs(cats_path)
        missing = [(path, simple) for path, simple in wanted if path not in existing]
        if not missing:
            return existing.get(f"Materials/{root_name}")

        lines = []
        if os.path.isfile(cats_path):
            try:
                with open(cats_path, "r", encoding="utf-8") as f:
                    lines = [ln.rstrip("\n") for ln in f]
            except OSError:
                lines = []

        if not lines:
            lines = [
                "# This is an Asset Catalog Definition file for Blender.",
                "VERSION 1",
                "",
            ]
        elif not any(ln.startswith("VERSION") for ln in lines):
            lines.insert(0, "VERSION 1")

        for path, simple in missing:
            lines.append(f"{uuid.uuid4()}:{path}:{simple}")

        try:
            with open(cats_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines).rstrip() + "\n")
        except OSError as e:
            self.report({"WARNING"}, f"Could not write current-file catalogs: {e}")
            return None

        updated = self._read_catalogs(cats_path)
        return updated.get(f"Materials/{root_name}")

    def _apply_asset_metadata(self, mat, root_name):
        if not self.mark_as_asset:
            return
        mat.asset_mark()
        ad = mat.asset_data
        if ad is None:
            return
        tags = [root_name] + _split_tags_semicolon(self.asset_tags)
        seen = set()
        for tag in tags:
            key = tag.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            try:
                ad.tags.new(tag, skip_if_exists=True)
            except TypeError:
                # Compatibility with builds that don't support skip_if_exists.
                try:
                    ad.tags.new(tag)
                except Exception:
                    pass
        catalog_id = self._catalog_id_cache
        if catalog_id is None:
            catalog_id = self._ensure_catalogs_current_file(root_name)
            self._catalog_id_cache = catalog_id
        if catalog_id:
            ad.catalog_id = catalog_id

    def _progress_update(self, wm, value):
        wm.progress_update(value)
        # Force UI refresh so progress is visible during long loops.
        for win in wm.windows:
            if win.screen:
                for area in win.screen.areas:
                    area.tag_redraw()
        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN", iterations=1)
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass

    def _pick_operator_context(self, context):
        win = context.window
        screen = context.screen
        if win is None or screen is None:
            return None

        def first_window_region(area):
            for region in area.regions:
                if region.type == "WINDOW":
                    return region
            return None

        for area in screen.areas:
            if area.type == "FILE_BROWSER" and getattr(area.spaces.active, "browse_mode", "") == "ASSETS":
                region = first_window_region(area)
                if region:
                    return {"window": win, "screen": screen, "area": area, "region": region}

        for area_type in ("PROPERTIES", "VIEW_3D", "FILE_BROWSER"):
            for area in screen.areas:
                if area.type == area_type:
                    region = first_window_region(area)
                    if region:
                        return {"window": win, "screen": screen, "area": area, "region": region}
        return None

    def _refresh_asset_browser_ui(self, context):
        area_ctx = self._pick_operator_context(context)
        if area_ctx is None:
            return
        try:
            space = area_ctx["area"].spaces.active
            params = getattr(space, "params", None)
            if params and hasattr(params, "asset_library_reference"):
                params.asset_library_reference = "LOCAL"
                if self._catalog_id_cache and hasattr(params, "catalog_id"):
                    params.catalog_id = self._catalog_id_cache
            with context.temp_override(**area_ctx):
                bpy.ops.asset.library_refresh()
                try:
                    bpy.ops.asset.catalogs_save()
                except Exception:
                    pass
        except Exception:
            pass

    def _build_material_for_folder(self, folder):
        images = _scan_images(folder)
        if not images:
            return None

        paths_by_type = {k: v for k, v in self._build_map_paths(images).items() if v}
        if not paths_by_type:
            return None

        mat_name = material_builder.unique_material_name(os.path.basename(folder))
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        material_builder.build_principled_tree(mat, paths_by_type, 0.1, 0.0, self.flip_normal_y)
        return mat

    def execute(self, context):
        root = bpy.path.abspath(self.directory)
        root = os.path.normpath(root)
        if not os.path.isdir(root):
            self.report({"ERROR"}, "Root folder not found.")
            return {"CANCELLED"}
        if self.mark_as_asset and not bpy.data.filepath:
            self.report({"ERROR"}, "Save the .blend first (Current File catalogs require a saved file).")
            return {"CANCELLED"}

        try:
            subfolders = [
                os.path.join(root, name)
                for name in os.listdir(root)
                if os.path.isdir(os.path.join(root, name))
            ]
        except OSError as e:
            self.report({"ERROR"}, f"Could not list root folder: {e}")
            return {"CANCELLED"}

        if not subfolders:
            self.report({"WARNING"}, "No direct subfolders found.")
            return {"CANCELLED"}

        created = 0
        skipped = 0
        root_name = os.path.basename(root.rstrip("\\/")) or "Materials"
        self._catalog_path_cache = f"Materials/{root_name}"
        self._catalog_id_cache = None
        wm = context.window_manager
        wm.progress_begin(0, len(subfolders))
        try:
            self._catalog_id_cache = self._ensure_catalogs_current_file(root_name)
            if self.mark_as_asset and self._catalog_id_cache is None:
                cats_path = self._catalog_file_current_blend()
                self.report({"WARNING"}, f"Catalog not available. Expected in: {cats_path}")
            self._refresh_asset_browser_ui(context)
            for folder in sorted(subfolders):
                mat = self._build_material_for_folder(folder)
                if mat is None:
                    skipped += 1
                else:
                    self._apply_asset_metadata(mat, root_name)
                    created += 1
                self._progress_update(wm, created + skipped)
        finally:
            wm.progress_end()

        self.report({"INFO"}, f"Batch Materials: created {created}, skipped {skipped}.")
        return {"FINISHED"}


class ALEC_OT_batch_materials_capture_previews(ALEC_OT_batch_materials):
    """Batch Materials + mark as assets + capture previews from scene objects."""

    bl_idname = "alec.batch_materials_capture_previews"
    bl_label = "Batch Materials + Capture Previews"
    bl_options = {"REGISTER", "UNDO"}

    preview_sphere_name: StringProperty(name="Sphere Object", default="Sphere")  # type: ignore
    preview_plane_name: StringProperty(name="Plane Object", default="Plane")  # type: ignore
    open_preview_scene_first: BoolProperty(
        name="Open Preview Scene First",
        description="Open assets/Materials_Assets_Scene.blend in current Blender session before running",
        default=False,
    )  # type: ignore
    use_active_object_preview: BoolProperty(
        name="Use Active Object Preview",
        description="If off, render from camera and load as custom preview",
        default=False,
    )  # type: ignore
    preview_camera_name: StringProperty(name="Camera Object", default="Camera")  # type: ignore
    preview_resolution: IntProperty(name="Preview Resolution", default=512, min=64, max=2048)  # type: ignore
    transparent_bg: BoolProperty(name="Transparent Background", default=True)  # type: ignore

    def draw(self, context):
        super().draw(context)
        layout = self.layout
        layout.separator()
        layout.label(text="Preview Scene Objects")
        layout.prop(self, "open_preview_scene_first")
        layout.prop(self, "use_active_object_preview")
        layout.prop(self, "preview_sphere_name")
        layout.prop(self, "preview_plane_name")
        if not self.use_active_object_preview:
            layout.prop(self, "preview_camera_name")
            row = layout.row(align=True)
            row.prop(self, "preview_resolution")
            row.prop(self, "transparent_bg")

    def _apply_material(self, obj, mat):
        if obj is None or obj.type != "MESH":
            return False
        if not obj.data.materials:
            obj.data.materials.append(mat)
        else:
            obj.material_slots[obj.active_material_index].material = mat
        return True

    def _pick_operator_context(self, context):
        win = context.window
        screen = context.screen
        if win is None or screen is None:
            return None

        def first_window_region(area):
            for region in area.regions:
                if region.type == "WINDOW":
                    return region
            return None

        # Best case: Asset Browser area.
        for area in screen.areas:
            if area.type == "FILE_BROWSER" and getattr(area.spaces.active, "browse_mode", "") == "ASSETS":
                region = first_window_region(area)
                if region:
                    return {"window": win, "screen": screen, "area": area, "region": region}

        # Fallbacks.
        for area_type in ("PROPERTIES", "VIEW_3D", "FILE_BROWSER"):
            for area in screen.areas:
                if area.type == area_type:
                    region = first_window_region(area)
                    if region:
                        return {"window": win, "screen": screen, "area": area, "region": region}
        return None

    def _capture_material_preview(self, context, mat, sphere_obj):
        # Operators are context-sensitive. Keep explicit overrides and report failures.
        area_ctx = self._pick_operator_context(context)
        if area_ctx is None:
            self.report({"WARNING"}, "No usable UI area found for preview generation.")
            return False

        override_common = {
            **area_ctx,
            "id": mat,
            "object": sphere_obj,
            "active_object": sphere_obj,
            "selected_objects": [sphere_obj],
            "selected_editable_objects": [sphere_obj],
        }

        if self.use_active_object_preview:
            try:
                with context.temp_override(**override_common):
                    result = bpy.ops.ed.lib_id_generate_preview_from_object()
                    if "FINISHED" in result:
                        return True
            except Exception as e:
                self.report({"WARNING"}, f"Active object preview failed for '{mat.name}': {e}")
        else:
            # Screen Capture preview mode (as in Asset Browser UI flow).
            try:
                with context.temp_override(**{**area_ctx, "id": mat}):
                    result = bpy.ops.ed.lib_id_generate_preview()
                    if "FINISHED" in result:
                        return True
            except Exception as e:
                self.report({"WARNING"}, f"Screen capture preview failed for '{mat.name}': {e}")

        return False

    def _load_custom_preview(self, context, mat, filepath):
        area_ctx = self._pick_operator_context(context)
        if area_ctx is None:
            self.report({"WARNING"}, f"Load custom preview skipped for '{mat.name}': no UI area context.")
            return False

        override = {**area_ctx, "id": mat}

        try:
            with context.temp_override(**override):
                result = bpy.ops.ed.lib_id_load_custom_preview(filepath=filepath)
                if "FINISHED" in result:
                    return True
        except Exception as e:
            # One retry after redraw helps when UI context is in flux.
            try:
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
            except Exception:
                pass
            try:
                with context.temp_override(**override):
                    result = bpy.ops.ed.lib_id_load_custom_preview(filepath=filepath)
                    if "FINISHED" in result:
                        return True
            except Exception as e2:
                self.report(
                    {"WARNING"},
                    f"Load custom preview failed for '{mat.name}': {e} / retry: {e2}",
                )
        return False

    def _render_preview_to_file(self, context, camera_obj, filepath):
        scene = context.scene
        render = scene.render
        image_settings = render.image_settings

        old_camera = scene.camera
        old_path = render.filepath
        old_res_x = render.resolution_x
        old_res_y = render.resolution_y
        old_res_pct = render.resolution_percentage
        old_format = image_settings.file_format
        old_color_mode = image_settings.color_mode
        old_transparent = render.film_transparent

        try:
            scene.camera = camera_obj
            render.filepath = filepath
            render.resolution_x = self.preview_resolution
            render.resolution_y = self.preview_resolution
            render.resolution_percentage = 100
            image_settings.file_format = "PNG"
            image_settings.color_mode = "RGBA"
            render.film_transparent = self.transparent_bg
            bpy.ops.render.render(write_still=True)
            return os.path.isfile(filepath)
        except Exception as e:
            self.report({"WARNING"}, f"Render preview failed: {e}")
            return False
        finally:
            scene.camera = old_camera
            render.filepath = old_path
            render.resolution_x = old_res_x
            render.resolution_y = old_res_y
            render.resolution_percentage = old_res_pct
            image_settings.file_format = old_format
            image_settings.color_mode = old_color_mode
            render.film_transparent = old_transparent

    def _preview_scene_path(self):
        addon_root = os.path.dirname(os.path.dirname(__file__))
        candidates = [
            os.path.join(addon_root, "assets", "Materials_Assets_Scene.blend"),
            r"d:\BLENDER_DEV\alecs_toolbox\assets\Materials_Assets_Scene.blend",
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
        # Return first candidate so error message shows expected primary path.
        return candidates[0]

    def _payload_dict(self):
        return {
            "directory": self.directory,
            "asset_tags": self.asset_tags,
            "mark_as_asset": self.mark_as_asset,
            "flip_normal_y": self.flip_normal_y,
            "kw_basecolor": self.kw_basecolor,
            "kw_normal": self.kw_normal,
            "kw_roughness": self.kw_roughness,
            "kw_metallic": self.kw_metallic,
            "kw_ao": self.kw_ao,
            "kw_displacement": self.kw_displacement,
            "kw_specular": self.kw_specular,
            "kw_bump": self.kw_bump,
            "kw_gloss": self.kw_gloss,
            "kw_cavity": self.kw_cavity,
            "use_ao": self.use_ao,
            "use_bump": self.use_bump,
            "use_cavity": self.use_cavity,
            "use_displacement": self.use_displacement,
            "preview_sphere_name": self.preview_sphere_name,
            "preview_plane_name": self.preview_plane_name,
            "use_active_object_preview": self.use_active_object_preview,
            "preview_camera_name": self.preview_camera_name,
            "preview_resolution": self.preview_resolution,
            "transparent_bg": self.transparent_bg,
            "open_preview_scene_first": False,
        }

    def execute(self, context):
        if self.open_preview_scene_first:
            preview_scene = self._preview_scene_path()
            if not os.path.isfile(preview_scene):
                self.report({"ERROR"}, f"Preview scene not found: {preview_scene}")
                return {"CANCELLED"}
            try:
                with open(_BATCH_PREVIEW_PAYLOAD_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._payload_dict(), f)
            except OSError as e:
                self.report({"ERROR"}, f"Could not store pending batch payload: {e}")
                return {"CANCELLED"}
            # Open directly (don't show file browser). Blender handles save prompt if needed.
            bpy.ops.wm.open_mainfile("EXEC_DEFAULT", filepath=preview_scene)
            self.report(
                {"INFO"},
                "Preview scene opened. Confirm the popup to start batch automatically.",
            )
            return {"CANCELLED"}

        root = bpy.path.abspath(self.directory)
        root = os.path.normpath(root)
        if not os.path.isdir(root):
            self.report({"ERROR"}, "Root folder not found.")
            return {"CANCELLED"}
        if self.mark_as_asset and not bpy.data.filepath:
            self.report({"ERROR"}, "Save the .blend first (Current File catalogs require a saved file).")
            return {"CANCELLED"}

        sphere_obj = bpy.data.objects.get(self.preview_sphere_name)
        plane_obj = bpy.data.objects.get(self.preview_plane_name)
        if sphere_obj is None or plane_obj is None:
            self.report(
                {"ERROR"},
                f"Preview objects not found: '{self.preview_sphere_name}' and/or '{self.preview_plane_name}'.",
            )
            return {"CANCELLED"}
        camera_obj = None
        if not self.use_active_object_preview:
            camera_obj = bpy.data.objects.get(self.preview_camera_name)
            if camera_obj is None or camera_obj.type != "CAMERA":
                self.report({"ERROR"}, f"Camera object not found or invalid: '{self.preview_camera_name}'.")
                return {"CANCELLED"}

        try:
            subfolders = [
                os.path.join(root, name)
                for name in os.listdir(root)
                if os.path.isdir(os.path.join(root, name))
            ]
        except OSError as e:
            self.report({"ERROR"}, f"Could not list root folder: {e}")
            return {"CANCELLED"}

        if not subfolders:
            self.report({"WARNING"}, "No direct subfolders found.")
            return {"CANCELLED"}

        created = 0
        skipped = 0
        preview_ok = 0
        preview_fail = 0
        temp_dir = tempfile.mkdtemp(prefix="alecs_batch_preview_")
        root_name = os.path.basename(root.rstrip("\\/")) or "Materials"
        self._catalog_path_cache = f"Materials/{root_name}"
        self._catalog_id_cache = None
        wm = context.window_manager
        wm.progress_begin(0, len(subfolders))
        try:
            self._catalog_id_cache = self._ensure_catalogs_current_file(root_name)
            if self.mark_as_asset and self._catalog_id_cache is None:
                cats_path = self._catalog_file_current_blend()
                self.report({"WARNING"}, f"Catalog not available. Expected in: {cats_path}")
            self._refresh_asset_browser_ui(context)
            for folder in sorted(subfolders):
                mat = self._build_material_for_folder(folder)
                if mat is None:
                    skipped += 1
                    self._progress_update(wm, created + skipped)
                    continue
                created += 1

                self._apply_asset_metadata(mat, root_name)
                self._apply_material(sphere_obj, mat)
                self._apply_material(plane_obj, mat)
                if sphere_obj.mode != "OBJECT":
                    try:
                        bpy.ops.object.mode_set(mode="OBJECT")
                    except Exception:
                        pass
                sphere_obj.select_set(True)
                plane_obj.select_set(False)
                context.view_layer.objects.active = sphere_obj
                context.view_layer.update()

                if self.use_active_object_preview:
                    ok = self._capture_material_preview(context, mat, sphere_obj)
                else:
                    preview_file = os.path.join(temp_dir, f"{mat.name}.png")
                    ok = self._render_preview_to_file(context, camera_obj, preview_file) and self._load_custom_preview(
                        context, mat, preview_file
                    )

                if ok:
                    preview_ok += 1
                else:
                    preview_fail += 1
                self._refresh_asset_browser_ui(context)
                self._progress_update(wm, created + skipped)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            wm.progress_end()
        self.report(
            {"INFO"},
            f"Batch+Previews: created {created}, skipped {skipped}, previews ok {preview_ok}, failed {preview_fail}.",
        )
        return {"FINISHED"}


class ALEC_OT_batch_materials_continue_after_open(bpy.types.Operator):
    """Ask confirmation then run batch after opening preview scene."""

    bl_idname = "alec.batch_materials_continue_after_open"
    bl_label = "Preview Scene Loaded"

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, _context):
        layout = self.layout
        layout.label(text="Preview scene loaded successfully.", icon="INFO")
        layout.label(text="Run 'Batch Materials + Previews' now with saved options?")
        layout.separator()
        layout.label(text="Press OK to start, Cancel to stop.")

    def execute(self, context):
        if not os.path.isfile(_BATCH_PREVIEW_PAYLOAD_FILE):
            self.report({"WARNING"}, "No pending batch payload found.")
            return {"CANCELLED"}
        try:
            with open(_BATCH_PREVIEW_PAYLOAD_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            self.report({"ERROR"}, "Invalid pending batch payload.")
            return {"CANCELLED"}
        try:
            os.remove(_BATCH_PREVIEW_PAYLOAD_FILE)
        except Exception:
            pass
        bpy.ops.alec.batch_materials_capture_previews("EXEC_DEFAULT", **payload)
        return {"FINISHED"}


classes = (
    ALEC_OT_make_mat_from_tex,
    ALEC_OT_batch_materials_capture_previews,
    ALEC_OT_batch_materials_continue_after_open,
)


def post_register():
    handlers = bpy.app.handlers.load_post
    if _on_file_load_post not in handlers:
        handlers.append(_on_file_load_post)


def post_unregister():
    handlers = bpy.app.handlers.load_post
    if _on_file_load_post in handlers:
        handlers.remove(_on_file_load_post)
