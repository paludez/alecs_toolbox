import os
import re
import shutil
import tempfile

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, StringProperty

from . import material_builder

_LAST_BROWSE_DIR = ""


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


def _material_preview_scene_path():
    addon_root = os.path.dirname(os.path.dirname(__file__))
    candidates = [
        os.path.join(addon_root, "assets", "Materials_Assets_Scene.blend"),
        r"d:\BLENDER_DEV\alecs_toolbox\assets\Materials_Assets_Scene.blend",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return candidates[0]


class ALEC_PG_subfolder_item(bpy.types.PropertyGroup):
    name: StringProperty(name="Subfolder Name")  # type: ignore
    selected: BoolProperty(name="Selected", default=True)  # type: ignore


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
        if _LAST_BROWSE_DIR and os.path.isdir(_LAST_BROWSE_DIR):
            self.directory = _LAST_BROWSE_DIR
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
        global _LAST_BROWSE_DIR
        folder = bpy.path.abspath(self.directory)
        folder = os.path.normpath(folder)
        if not os.path.isdir(folder):
            self.report({"ERROR"}, "Texture folder not found.")
            return {"CANCELLED"}
        _LAST_BROWSE_DIR = folder

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
    bl_options = {"UNDO"}

    directory: StringProperty(name="Root Folder", subtype="DIR_PATH")  # type: ignore
    selected_subfolders_payload: StringProperty(default="", options={"HIDDEN"})  # type: ignore
    selection_stage: BoolProperty(default=False, options={"HIDDEN"})  # type: ignore
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
    def _base_reinvoke_kwargs(self):
        # Only pass directory — stage 1 shows no properties to the user,
        # so all keyword/option settings keep their defaults in stage 2.
        # Passing many StringProperty values through bpy.ops allocates C blocks
        # that Blender does not reliably free when the dialog is cancelled.
        return {"directory": self.directory, "selection_stage": True}

    def _reinvoke_kwargs(self):
        return self._base_reinvoke_kwargs()

    def _reinvoke_for_selection(self):
        return bpy.ops.alec.batch_materials("INVOKE_DEFAULT", **self._reinvoke_kwargs())

    def invoke(self, context, _event):
        if self.selection_stage:
            root = bpy.path.abspath(self.directory)
            root = os.path.normpath(root)
            if not os.path.isdir(root):
                self.report({"ERROR"}, "Root folder not found.")
                return {"CANCELLED"}
            self._populate_subfolder_state(root)
            return context.window_manager.invoke_props_dialog(self, width=560)
        self.selection_stage = False
        if _LAST_BROWSE_DIR and os.path.isdir(_LAST_BROWSE_DIR):
            self.directory = _LAST_BROWSE_DIR
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def draw(self, _context):
        layout = self.layout
        if not self.selection_stage:
            return
        layout.prop(self, "directory")
        layout.separator()
        layout.label(text="Subfolder Selection")
        box = layout.box()
        wm = bpy.context.window_manager
        if wm.alec_subfolder_items:
            for it in wm.alec_subfolder_items:
                box.prop(it, "selected", text=it.name)
        else:
            box.label(text="No direct subfolders found. Root folder will be processed.")
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

    def _progress_update(self, wm, value):
        wm.progress_update(value)

    def _set_asset_browser_current_file(self, context):
        win = context.window
        screen = context.screen
        if win is None or screen is None:
            return
        for area in screen.areas:
            if area.type != "FILE_BROWSER":
                continue
            space = area.spaces.active
            if getattr(space, "browse_mode", "") != "ASSETS":
                continue
            params = getattr(space, "params", None)
            if params and hasattr(params, "asset_library_reference"):
                try:
                    params.asset_library_reference = "LOCAL"
                except Exception:
                    pass
                # Show newly created assets immediately in Current File.
                if hasattr(params, "catalog_id"):
                    try:
                        params.catalog_id = "00000000-0000-0000-0000-000000000000"
                    except Exception:
                        try:
                            params.catalog_id = ""
                        except Exception:
                            pass
            break

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

    def _populate_subfolder_state(self, root):
        wm = bpy.context.window_manager
        wm.alec_subfolder_items.clear()
        selected_from_payload = set(_split_tags_semicolon(self.selected_subfolders_payload))
        try:
            all_names = sorted(
                name for name in os.listdir(root) if os.path.isdir(os.path.join(root, name))
            )
        except OSError:
            all_names = []
        for name in all_names:
            item = wm.alec_subfolder_items.add()
            item.name = name
            item.selected = (not selected_from_payload) or (name in selected_from_payload)
        self.selected_subfolders_payload = ""

    def _selected_subfolder_names(self):
        return [it.name for it in bpy.context.window_manager.alec_subfolder_items if it.selected]

    def _target_subfolders(self, root):
        try:
            all_subfolders = sorted(
                os.path.join(root, name)
                for name in os.listdir(root)
                if os.path.isdir(os.path.join(root, name))
            )
        except OSError as e:
            self.report({"ERROR"}, f"Could not list root folder: {e}")
            return None
        if not all_subfolders:
            return [root]
        wm = bpy.context.window_manager
        selected = set(self._selected_subfolder_names())
        if not selected:
            if wm.alec_subfolder_items:
                return []
            return all_subfolders
        return [p for p in all_subfolders if os.path.basename(p) in selected]

    def cancel(self, context):
        context.window_manager.alec_subfolder_items.clear()

    def execute(self, context):
        global _LAST_BROWSE_DIR
        root = bpy.path.abspath(self.directory)
        root = os.path.normpath(root)
        if not os.path.isdir(root):
            self.report({"ERROR"}, "Root folder not found.")
            return {"CANCELLED"}
        _LAST_BROWSE_DIR = root
        if not self.selection_stage:
            self._populate_subfolder_state(root)
            self._reinvoke_for_selection()
            # Return FINISHED so Blender destroys this (stage 1) operator instance
            # and frees its StringProperty allocations. Stage 2 runs independently.
            return {"FINISHED"}

        subfolders = self._target_subfolders(root)
        if subfolders is None:
            return {"CANCELLED"}

        if not subfolders:
            self.report({"WARNING"}, "No target subfolders found.")
            return {"CANCELLED"}

        created = 0
        skipped = 0
        root_name = os.path.basename(root.rstrip("\\/")) or "Materials"
        wm = context.window_manager
        wm.progress_begin(0, len(subfolders))
        try:
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
            wm.alec_subfolder_items.clear()
        self._set_asset_browser_current_file(context)

        self.report({"INFO"}, f"Batch Materials: created {created}, skipped {skipped}.")
        return {"FINISHED"}


class ALEC_OT_batch_materials_capture_previews(ALEC_OT_batch_materials):
    """Batch Materials + mark as assets + capture previews from scene objects."""

    bl_idname = "alec.batch_materials_capture_previews"
    bl_label = "Batch Materials + Capture Previews"
    bl_options = {"UNDO"}

    generate_previews: BoolProperty(
        name="Generate Previews",
        description="Generate thumbnails for created materials",
        default=False,
    )  # type: ignore
    preview_sphere_name: StringProperty(name="Sphere Object", default="Sphere")  # type: ignore
    preview_plane_name: StringProperty(name="Plane Object", default="Plane")  # type: ignore
    use_active_object_preview: BoolProperty(
        name="Use Active Object Preview",
        description="If off, render from camera and load as custom preview",
        default=False,
    )  # type: ignore
    preview_camera_name: StringProperty(name="Camera Object", default="Camera")  # type: ignore
    preview_resolution: IntProperty(name="Preview Resolution", default=512, min=64, max=2048)  # type: ignore
    transparent_bg: BoolProperty(name="Transparent Background", default=True)  # type: ignore

    def _reinvoke_kwargs(self):
        out = self._base_reinvoke_kwargs()
        # No extra strings needed — preview options are set by the user in stage 2 dialog.
        return out

    def _reinvoke_for_selection(self):
        return bpy.ops.alec.batch_materials_capture_previews("INVOKE_DEFAULT", **self._reinvoke_kwargs())

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
        abs_target = os.path.normcase(os.path.abspath(filepath))
        image_names_before = {img.name for img in bpy.data.images}

        ok = False
        try:
            with context.temp_override(**override):
                result = bpy.ops.ed.lib_id_load_custom_preview(filepath=filepath)
                if "FINISHED" in result:
                    ok = True
        except Exception as e:
            self.report({"WARNING"}, f"Load custom preview failed for '{mat.name}': {e}")
        finally:
            # Clean any transient image datablocks loaded from this temp preview file.
            for img in list(bpy.data.images):
                if img.name in image_names_before:
                    continue
                try:
                    img_path = os.path.normcase(os.path.abspath(bpy.path.abspath(img.filepath)))
                except Exception:
                    img_path = ""
                if img_path != abs_target:
                    continue
                if img.users == 0:
                    try:
                        bpy.data.images.remove(img)
                    except Exception:
                        pass
        return ok

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
            for img in list(bpy.data.images):
                if img.type == "RENDER_RESULT":
                    try:
                        bpy.data.images.remove(img)
                    except Exception:
                        pass

    def execute(self, context):
        root = bpy.path.abspath(self.directory)
        root = os.path.normpath(root)
        if not os.path.isdir(root):
            self.report({"ERROR"}, "Root folder not found.")
            return {"CANCELLED"}
        if not self.selection_stage:
            self._populate_subfolder_state(root)
            self._reinvoke_for_selection()
            return {"FINISHED"}

        sphere_obj = None
        plane_obj = None
        camera_obj = None
        if self.generate_previews:
            sphere_obj = bpy.data.objects.get(self.preview_sphere_name)
            plane_obj = bpy.data.objects.get(self.preview_plane_name)
            if sphere_obj is None or plane_obj is None:
                self.report(
                    {"ERROR"},
                    f"Preview objects not found: '{self.preview_sphere_name}' and/or '{self.preview_plane_name}'.",
                )
                return {"CANCELLED"}
            if not self.use_active_object_preview:
                camera_obj = bpy.data.objects.get(self.preview_camera_name)
                if camera_obj is None or camera_obj.type != "CAMERA":
                    self.report({"ERROR"}, f"Camera object not found or invalid: '{self.preview_camera_name}'.")
                    return {"CANCELLED"}

        subfolders = self._target_subfolders(root)
        if subfolders is None:
            return {"CANCELLED"}

        if not subfolders:
            self.report({"WARNING"}, "No target subfolders found.")
            return {"CANCELLED"}

        created = 0
        skipped = 0
        preview_ok = 0
        preview_fail = 0
        temp_dir = tempfile.mkdtemp(prefix="alecs_batch_preview_")
        root_name = os.path.basename(root.rstrip("\\/")) or "Materials"
        wm = context.window_manager
        wm.progress_begin(0, len(subfolders))
        try:
            for folder in sorted(subfolders):
                mat = self._build_material_for_folder(folder)
                if mat is None:
                    skipped += 1
                    self._progress_update(wm, created + skipped)
                    continue
                created += 1

                self._apply_asset_metadata(mat, root_name)
                if self.generate_previews:
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
                else:
                    ok = True

                if ok:
                    preview_ok += 1
                else:
                    preview_fail += 1
                self._progress_update(wm, created + skipped)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            wm.progress_end()
            wm.alec_subfolder_items.clear()
        self._set_asset_browser_current_file(context)
        self.report(
            {"INFO"},
            f"Batch+Previews: created {created}, skipped {skipped}, previews ok {preview_ok}, failed {preview_fail}, preview generation {'on' if self.generate_previews else 'off'}.",
        )
        return {"FINISHED"}


class ALEC_OT_open_material_preview_scene(bpy.types.Operator):
    """Open bundled material preview scene."""

    bl_idname = "alec.open_material_preview_scene"
    bl_label = "Open Material Preview Scene"

    unsaved_action: EnumProperty(  # type: ignore
        name="Unsaved Changes Action",
        items=(
            ("SAVE", "Save Current Scene", "Save current scene, then load preview scene"),
            ("DONT_SAVE", "Don't Save", "Discard changes and load preview scene"),
            ("CANCEL", "Cancel", "Cancel loading preview scene"),
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
        layout.label(text="How do you want to continue before loading preview scene?")
        layout.prop(self, "unsaved_action", text="")

    def execute(self, context):
        if bpy.data.is_dirty:
            action = self.unsaved_action or "DONT_SAVE"
            if action == "CANCEL":
                return {"CANCELLED"}
            if action == "SAVE":
                try:
                    if bpy.data.filepath:
                        save_result = bpy.ops.wm.save_mainfile("EXEC_DEFAULT")
                    else:
                        save_result = bpy.ops.wm.save_mainfile("INVOKE_DEFAULT")
                    if "FINISHED" not in save_result:
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


classes = (
    ALEC_PG_subfolder_item,
    ALEC_OT_make_mat_from_tex,
    ALEC_OT_open_material_preview_scene,
    ALEC_OT_batch_materials_capture_previews,
)


def post_register():
    bpy.types.WindowManager.alec_subfolder_items = CollectionProperty(type=ALEC_PG_subfolder_item)


def post_unregister():
    for wm in bpy.data.window_managers:
        try:
            wm.alec_subfolder_items.clear()
        except Exception:
            pass
    try:
        del bpy.types.WindowManager.alec_subfolder_items
    except AttributeError:
        pass
