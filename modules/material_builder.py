import os

import bpy

EXT_PRIORITY = {
    ".exr": 0, ".hdr": 0,
    ".png": 1,
    ".tif": 2, ".tiff": 2,
    ".jpg": 3, ".jpeg": 3,
}

IMAGE_EXTENSIONS = frozenset(
    (".exr", ".hdr", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".tga", ".webp")
)

# Map types that should use sRGB colorspace; everything else uses Non-Color.
_SRGB_MAP_TYPES = frozenset(("basecolor", "color", "diffuse", "albedo"))


def _colorspace_for_map(map_type: str) -> str:
    return "sRGB" if map_type in _SRGB_MAP_TYPES else "Non-Color"


def unique_material_name(base_name: str) -> str:
    base = bpy.path.clean_name(base_name) or "Material"
    name, n = base, 1
    while name in bpy.data.materials:
        name = f"{base}.{n:03d}"
        n += 1
    return name


def _new_image_texture(nodes, abs_path: str, colorspace: str, location):
    img = bpy.data.images.load(abs_path, check_existing=True)
    try:
        img.colorspace_settings.name = colorspace
    except (TypeError, ValueError):
        pass
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.label = os.path.basename(abs_path)
    tex.location = location
    return tex


def _inp(node, name: str):
    """Return an input socket by name, or None."""
    return node.inputs.get(name) if node is not None else None


def _tidy_node_layout(node_tree) -> None:
    grid, step = 20, 160

    def snap(v):
        return round(v / grid) * grid

    used: dict = {}
    for node in node_tree.nodes:
        x, y = snap(node.location.x), snap(node.location.y)
        if (x, y) in used:
            y -= step * used[(x, y)]
            used[(x, y)] += 1
        else:
            used[(x, y)] = 1
        node.location = (x, y)


def _build_normal_flip_chain(nodes, links, ntex):
    """Insert Separate → Invert → Combine nodes to flip the green channel.

    Returns the output Color socket to connect to the NormalMap node.
    Falls back to the raw texture output if CombineColor sockets are unavailable.
    """
    ox, oy = ntex.location

    sep = nodes.new("ShaderNodeSeparateColor")
    sep.location = (ox + 200, oy)
    links.new(ntex.outputs["Color"], sep.inputs["Color"])

    inv = nodes.new("ShaderNodeInvert")
    inv.location = (ox + 380, oy - 80)
    inv.inputs["Fac"].default_value = 1.0
    links.new(sep.outputs["Green"], inv.inputs["Color"])

    comb = nodes.new("ShaderNodeCombineColor")
    comb.location = (ox + 540, oy)
    r_in = comb.inputs.get("Red")
    g_in = comb.inputs.get("Green")
    b_in = comb.inputs.get("Blue")
    if r_in and g_in and b_in:
        links.new(sep.outputs["Red"], r_in)
        links.new(inv.outputs["Color"], g_in)   # inverted green scalar → green channel
        links.new(sep.outputs["Blue"], b_in)
        return comb.outputs.get("Color")

    return ntex.outputs["Color"]


def build_principled_tree(
    mat,
    paths_by_type: dict,
    disp_scale: float,
    disp_bias: float,
    flip_normal_y: bool = False,
) -> None:
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (520, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (220, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    x_tex, y = -560, 260

    def next_slot():
        nonlocal y
        loc, y = (x_tex, y), y - 280
        return loc

    def add_tex(map_type: str):
        path = paths_by_type.get(map_type)
        if not path:
            return None
        return _new_image_texture(nodes, path, _colorspace_for_map(map_type), next_slot())

    # --- Base Color --------------------------------------------------------
    base_out = None
    for base_key in ("basecolor", "color", "diffuse", "albedo"):
        if base_key in paths_by_type:
            if t := add_tex(base_key):
                base_out = t.outputs["Color"]
            break

    # AO and Cavity are multiplied on top of base color.
    for extra in ("ao", "cavity"):
        if extra not in paths_by_type or base_out is None:
            continue
        if not (t_extra := add_tex(extra)):
            continue
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.location = (t_extra.location[0] + 240, t_extra.location[1])
        fac = mix.inputs.get("Factor") or mix.inputs.get("Factor_Float")
        a   = mix.inputs.get("A") or mix.inputs.get("A_Color")
        b   = mix.inputs.get("B") or mix.inputs.get("B_Color")
        res = mix.outputs.get("Result") or mix.outputs.get("Result_Color")
        if fac:
            fac.default_value = 1.0
        if a and b:
            links.new(base_out, a)
            links.new(t_extra.outputs["Color"], b)
        if res:
            base_out = res

    if base_out and (bc_in := _inp(bsdf, "Base Color")):
        links.new(base_out, bc_in)

    # --- Roughness / Gloss -------------------------------------------------
    if "roughness" in paths_by_type:
        if (t := add_tex("roughness")) and (s := _inp(bsdf, "Roughness")):
            links.new(t.outputs["Color"], s)
    elif "gloss" in paths_by_type:
        if t := add_tex("gloss"):
            inv = nodes.new("ShaderNodeMath")
            inv.operation = "SUBTRACT"
            inv.location = (t.location[0] + 220, t.location[1])
            inv.inputs[0].default_value = 1.0
            links.new(t.outputs["Color"], inv.inputs[1])
            if s := _inp(bsdf, "Roughness"):
                links.new(inv.outputs["Value"], s)

    # --- Metallic ----------------------------------------------------------
    if "metallic" in paths_by_type:
        if (t := add_tex("metallic")) and (s := _inp(bsdf, "Metallic")):
            links.new(t.outputs["Color"], s)

    # --- Anisotropy (texture → Principled Anisotropic) ---------------------
    if "anisotropy" in paths_by_type:
        if (t := add_tex("anisotropy")) and (s := _inp(bsdf, "Anisotropic")):
            links.new(t.outputs["Color"], s)

    # --- Specular ----------------------------------------------------------
    if "specular" in paths_by_type:
        if t := add_tex("specular"):
            for sock_name in ("Specular IOR Level", "Specular"):
                if s := _inp(bsdf, sock_name):
                    links.new(t.outputs["Color"], s)
                    break

    # --- Normal (+ optional Bump chained on top) ---------------------------
    normal_out = None
    if "normal" in paths_by_type:
        if ntex := add_tex("normal"):
            if flip_normal_y:
                col_out = _build_normal_flip_chain(nodes, links, ntex)
                nm_x = ntex.location[0] + 740
            else:
                col_out = ntex.outputs["Color"]
                nm_x = ntex.location[0] + 240
            nm = nodes.new("ShaderNodeNormalMap")
            nm.location = (nm_x, ntex.location[1])
            links.new(col_out, nm.inputs["Color"])
            normal_out = nm.outputs["Normal"]

    if "bump" in paths_by_type:
        if btex := add_tex("bump"):
            bump = nodes.new("ShaderNodeBump")
            bump.location = (btex.location[0] + 240, btex.location[1])
            links.new(btex.outputs["Color"], bump.inputs["Height"])
            if normal_out and (n_in := _inp(bump, "Normal")):
                links.new(normal_out, n_in)
            normal_out = bump.outputs["Normal"]

    if normal_out and (n_in := _inp(bsdf, "Normal")):
        links.new(normal_out, n_in)

    # --- Displacement ------------------------------------------------------
    if "displacement" in paths_by_type:
        if dtex := add_tex("displacement"):
            disp = nodes.new("ShaderNodeDisplacement")
            disp.location = (dtex.location[0] + 240, dtex.location[1] - 40)
            if mid := _inp(disp, "Midlevel"):
                mid.default_value = float(disp_bias)
            if sc := _inp(disp, "Scale"):
                sc.default_value = float(disp_scale)
            links.new(dtex.outputs["Color"], disp.inputs["Height"])
            if d_in := out.inputs.get("Displacement"):
                links.new(disp.outputs["Displacement"], d_in)

    _tidy_node_layout(nt)
