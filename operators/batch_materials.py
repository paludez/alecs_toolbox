import os

import bpy
from bpy.props import BoolProperty, StringProperty

from . import material_builder


def _split_keywords(value):
    return [k.strip().lower() for k in value.split(",") if k.strip()]


def _norm_stem(path):
    return os.path.splitext(os.path.basename(path))[0].lower()


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
    keys = _split_keywords(keywords)
    if not keys:
        return None
    matches = []
    for p in images:
        stem = _norm_stem(p)
        if any(k in stem for k in keys):
            matches.append(p)
    return _pick_best_by_ext(matches)


class ALEC_OT_batch_materials(bpy.types.Operator):
    """Create one material per direct subfolder from texture keywords."""

    bl_idname = "alec.batch_materials"
    bl_label = "Batch Materials"
    bl_options = {"REGISTER", "UNDO"}

    directory: StringProperty(name="Root Folder", subtype="DIR_PATH")  # type: ignore

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

    def invoke(self, context, _event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "directory")
        layout.prop(self, "flip_normal_y")
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
        out = {
            "basecolor": _pick_by_keywords(images, self.kw_basecolor),
            "normal": _pick_by_keywords(images, self.kw_normal),
            "roughness": _pick_by_keywords(images, self.kw_roughness),
            "metallic": _pick_by_keywords(images, self.kw_metallic),
            "ao": _pick_by_keywords(images, self.kw_ao),
            "displacement": _pick_by_keywords(images, self.kw_displacement),
            "specular": _pick_by_keywords(images, self.kw_specular),
            "bump": _pick_by_keywords(images, self.kw_bump),
            "gloss": _pick_by_keywords(images, self.kw_gloss),
            "cavity": _pick_by_keywords(images, self.kw_cavity),
        }
        if not self.use_ao:
            out.pop("ao", None)
        if not self.use_bump:
            out.pop("bump", None)
        if not self.use_cavity:
            out.pop("cavity", None)
        if not self.use_displacement:
            out.pop("displacement", None)
        return out

    def execute(self, _context):
        root = bpy.path.abspath(self.directory)
        root = os.path.normpath(root)
        if not os.path.isdir(root):
            self.report({"ERROR"}, "Root folder not found.")
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
        for folder in sorted(subfolders):
            images = _scan_images(folder)
            if not images:
                skipped += 1
                continue

            paths_by_type = {k: v for k, v in self._build_map_paths(images).items() if v}
            if not paths_by_type:
                skipped += 1
                continue

            mat_name = material_builder.unique_material_name(os.path.basename(folder))
            mat = bpy.data.materials.new(name=mat_name)
            mat.use_nodes = True
            material_builder.build_principled_tree(mat, paths_by_type, 0.1, 0.0, self.flip_normal_y)
            created += 1

        self.report({"INFO"}, f"Batch Materials: created {created}, skipped {skipped}.")
        return {"FINISHED"}


classes = (ALEC_OT_batch_materials,)
