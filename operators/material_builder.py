import os

import bpy

EXT_PRIORITY = {
    ".exr": 0,
    ".hdr": 0,
    ".png": 1,
    ".tif": 2,
    ".tiff": 2,
    ".jpg": 3,
    ".jpeg": 3,
}

IMAGE_EXTENSIONS = frozenset(
    (".exr", ".hdr", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".tga", ".webp")
)

_BASECOLOR_MAP_TYPES = frozenset(("basecolor", "color", "diffuse", "albedo"))


def _colorspace_for_map(map_type):
    if map_type in _BASECOLOR_MAP_TYPES:
        return "sRGB"
    return "Non-Color"


def _apply_image_colorspace(image, space_name):
    if image is None:
        return
    try:
        image.colorspace_settings.name = space_name
    except (TypeError, ValueError):
        pass


def unique_material_name(base_name):
    base = bpy.path.clean_name(base_name) if base_name else ""
    if not base:
        base = "Material"
    name = base
    n = 1
    while name in bpy.data.materials:
        name = f"{base}.{n:03d}"
        n += 1
    return name


def _new_image_texture(nodes, abs_path, colorspace, location):
    img = bpy.data.images.load(abs_path, check_existing=True)
    _apply_image_colorspace(img, colorspace)
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.label = os.path.basename(abs_path)
    tex.location = location
    return tex


def _socket(node, name):
    if node is None:
        return None
    return node.inputs.get(name) if hasattr(node, "inputs") else None


def _mix_rgba_multiply_sockets(mix):
    a = mix.inputs.get("A") or mix.inputs.get("A_Color")
    b = mix.inputs.get("B") or mix.inputs.get("B_Color")
    fac = mix.inputs.get("Factor") or mix.inputs.get("Factor_Float")
    result = mix.outputs.get("Result") or mix.outputs.get("Result_Color")
    return fac, a, b, result


def _tidy_node_layout(node_tree):
    nodes = node_tree.nodes
    used = {}
    grid = 20
    stack_step = 160

    def snap(v):
        return round(v / grid) * grid

    for node in nodes:
        x = snap(node.location.x)
        y = snap(node.location.y)
        key = (x, y)
        if key in used:
            y -= stack_step * used[key]
            used[key] += 1
        else:
            used[key] = 1
        node.location = (x, y)


def build_principled_tree(mat, paths_by_type, disp_scale, disp_bias, flip_normal_y=False):
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (520, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (220, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    x_tex = -560
    y = 260
    dy = -280

    def next_slot():
        nonlocal y
        loc = (x_tex, y)
        y += dy
        return loc

    def add_tex(map_type, key):
        path = paths_by_type.get(key)
        if not path:
            return None
        cs = _colorspace_for_map(map_type)
        return _new_image_texture(nodes, path, cs, next_slot())

    base_keys = ("basecolor", "color", "diffuse", "albedo")
    base_key = next((k for k in base_keys if k in paths_by_type), None)
    base_out_socket = None
    if base_key:
        t_base = add_tex(base_key, base_key)
        if t_base:
            base_out_socket = t_base.outputs["Color"]
    for extra in ("ao", "cavity"):
        if extra not in paths_by_type or base_out_socket is None:
            continue
        t_extra = add_tex(extra, extra)
        if not t_extra:
            continue
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.location = (t_extra.location[0] + 240, t_extra.location[1])
        f, a, b, result = _mix_rgba_multiply_sockets(mix)
        if f is not None:
            f.default_value = 1.0
        if a and b:
            links.new(base_out_socket, a)
            links.new(t_extra.outputs["Color"], b)
        if result:
            base_out_socket = result

    bc_in = _socket(bsdf, "Base Color")
    if base_out_socket is not None and bc_in:
        links.new(base_out_socket, bc_in)

    if "roughness" in paths_by_type:
        rough_tex = add_tex("roughness", "roughness")
        rin = _socket(bsdf, "Roughness")
        if rough_tex and rin:
            links.new(rough_tex.outputs["Color"], rin)
    elif "gloss" in paths_by_type:
        gloss_tex = add_tex("gloss", "gloss")
        rin = _socket(bsdf, "Roughness")
        if gloss_tex and rin:
            math = nodes.new("ShaderNodeMath")
            math.operation = "SUBTRACT"
            math.location = (gloss_tex.location[0] + 220, gloss_tex.location[1])
            math.inputs[0].default_value = 1.0
            links.new(gloss_tex.outputs["Color"], math.inputs[1])
            links.new(math.outputs["Value"], rin)

    for mk in ("metallic", "metalness"):
        if mk in paths_by_type:
            mtex = add_tex(mk, mk)
            minp = _socket(bsdf, "Metallic")
            if mtex and minp:
                links.new(mtex.outputs["Color"], minp)
            break

    if "specular" in paths_by_type:
        stex = add_tex("specular", "specular")
        for sock_name in ("Specular IOR Level", "Specular"):
            sinp = _socket(bsdf, sock_name)
            if stex and sinp:
                links.new(stex.outputs["Color"], sinp)
                break

    normal_map_node = None
    if "normal" in paths_by_type:
        ntex = add_tex("normal", "normal")
        if ntex:
            nm = nodes.new("ShaderNodeNormalMap")
            if flip_normal_y:
                sep = nodes.new("ShaderNodeSeparateColor")
                sep.location = (ntex.location[0] + 200, ntex.location[1])
                links.new(ntex.outputs["Color"], sep.inputs["Color"])

                inv = nodes.new("ShaderNodeInvert")
                inv.location = (ntex.location[0] + 400, ntex.location[1] - 120)
                inv.inputs["Fac"].default_value = 1.0
                links.new(sep.outputs["Green"], inv.inputs["Color"])

                sep_inv = nodes.new("ShaderNodeSeparateColor")
                sep_inv.location = (ntex.location[0] + 560, ntex.location[1] - 120)
                links.new(inv.outputs["Color"], sep_inv.inputs["Color"])

                comb = nodes.new("ShaderNodeCombineColor")
                comb.location = (ntex.location[0] + 620, ntex.location[1])
                cr = comb.inputs.get("Red")
                cg = comb.inputs.get("Green")
                cb = comb.inputs.get("Blue")
                if cr and cg and cb:
                    links.new(sep.outputs["Red"], cr)
                    links.new(sep_inv.outputs["Green"], cg)
                    links.new(sep.outputs["Blue"], cb)

                nm.location = (ntex.location[0] + 860, ntex.location[1])
                comb_out = comb.outputs.get("Color")
                if comb_out:
                    links.new(comb_out, nm.inputs["Color"])
                else:
                    links.new(ntex.outputs["Color"], nm.inputs["Color"])
            else:
                nm.location = (ntex.location[0] + 240, ntex.location[1])
                links.new(ntex.outputs["Color"], nm.inputs["Color"])
            normal_map_node = nm

    if "bump" in paths_by_type:
        btex = add_tex("bump", "bump")
        if btex:
            bump = nodes.new("ShaderNodeBump")
            bump.location = (btex.location[0] + 240, btex.location[1])
            links.new(btex.outputs["Color"], bump.inputs["Height"])
            n_in = _socket(bump, "Normal")
            if normal_map_node and n_in:
                links.new(normal_map_node.outputs["Normal"], n_in)
            nin_bsdf = _socket(bsdf, "Normal")
            if nin_bsdf:
                links.new(bump.outputs["Normal"], nin_bsdf)
            normal_map_node = None

    if normal_map_node is not None:
        nin_bsdf = _socket(bsdf, "Normal")
        if nin_bsdf:
            links.new(normal_map_node.outputs["Normal"], nin_bsdf)

    if "displacement" in paths_by_type:
        dtex = add_tex("displacement", "displacement")
        if dtex:
            disp = nodes.new("ShaderNodeDisplacement")
            disp.location = (dtex.location[0] + 240, dtex.location[1] - 40)
            mid = _socket(disp, "Midlevel")
            if mid is not None:
                mid.default_value = float(disp_bias)
            sc = _socket(disp, "Scale")
            if sc is not None:
                sc.default_value = float(disp_scale)
            links.new(dtex.outputs["Color"], disp.inputs["Height"])
            din = out.inputs.get("Displacement")
            if din:
                links.new(disp.outputs["Displacement"], din)

    _tidy_node_layout(nt)
