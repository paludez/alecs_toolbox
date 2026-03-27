"""Shader Editor: shared Box triplanar for all selected Image Texture nodes."""

import bpy
from bpy.types import Operator


def _shader_node_tree(context):
    space = context.space_data
    if space is None or space.type != "NODE_EDITOR":
        return None
    tree = getattr(space, "edit_tree", None) or getattr(space, "node_tree", None)
    if tree is None or tree.bl_idname != "ShaderNodeTree":
        return None
    if getattr(space, "shader_type", "OBJECT") not in {"OBJECT", "WORLD"}:
        return None
    return tree


def triplanar_target_shader_tree(context):
    """Shader tree: focused Node Editor (Object / World), else active material or scene world."""
    t = _shader_node_tree(context)
    if t is not None:
        return t
    obj = getattr(context, "active_object", None)
    if obj is not None:
        m = getattr(obj, "active_material", None)
        if m and m.use_nodes and m.node_tree and m.node_tree.bl_idname == "ShaderNodeTree":
            return m.node_tree
    mat = getattr(context, "material", None)
    if mat and mat.use_nodes and mat.node_tree and mat.node_tree.bl_idname == "ShaderNodeTree":
        return mat.node_tree
    world = getattr(getattr(context, "scene", None), "world", None)
    if world and world.use_nodes and world.node_tree and world.node_tree.bl_idname == "ShaderNodeTree":
        return world.node_tree
    return None


def _deselect_all(nodes):
    for n in nodes:
        n.select = False


def selected_tex_image_nodes(tree):
    """All selected Image Texture nodes; if none selected, active if it is TEX_IMAGE."""
    imgs = [n for n in tree.nodes if n.type == "TEX_IMAGE" and n.select]
    if not imgs:
        act = tree.nodes.active
        if act is not None and act.type == "TEX_IMAGE":
            imgs = [act]
    return imgs


def triplanar_has_selected_tex_images(context):
    tree = triplanar_target_shader_tree(context)
    if tree is None:
        return False
    return len(selected_tex_image_nodes(tree)) > 0


def _disconnect_vector_input(tree, img_node):
    sock = img_node.inputs.get("Vector")
    if sock is None:
        return
    for l in list(tree.links):
        if l.to_socket == sock:
            tree.links.remove(l)


def _clear_projection_blend_driver(tex_node):
    try:
        tex_node.driver_remove("projection_blend")
    except Exception:
        pass


def apply_shared_box_triplanar(tree, img_nodes) -> str | None:
    """TexCoord → Mapping → images (Box). Scară = Value → Mapping Scale (float→vector). Blend = 0.15 pe fiecare tex."""
    if not img_nodes:
        return None

    nodes, links = tree.nodes, tree.links
    scale_val = 1.0
    blend_val = 0.15

    for img in img_nodes:
        _clear_projection_blend_driver(img)
        _disconnect_vector_input(tree, img)

    xs = [n.location.x for n in img_nodes]
    ys = [n.location.y for n in img_nodes]
    min_x, avg_y = min(xs), sum(ys) / len(ys)

    frame = nodes.new("NodeFrame")
    frame.label = "Alec Triplanar (shared UV)"
    frame_x = min_x - 520
    frame_y = avg_y + 120
    frame.location = (frame_x, frame_y)

    def rel(x, y):
        return (x - frame.location.x, y - frame.location.y)

    val_scale = nodes.new("ShaderNodeValue")
    val_scale.parent = frame
    val_scale.location = rel(frame_x + 120, frame_y - 160)
    val_scale.label = "Triplanar scale"
    vout = val_scale.outputs[0]
    vout.default_value = scale_val

    tex = nodes.new("ShaderNodeTexCoord")
    tex.parent = frame
    tex.location = rel(frame_x, frame_y)

    mapping = nodes.new("ShaderNodeMapping")
    mapping.parent = frame
    mapping.location = rel(frame_x + 200, frame_y)

    links.new(tex.outputs["Object"], mapping.inputs["Vector"])
    vec_out = mapping.outputs["Vector"]

    sc = mapping.inputs.get("Scale")
    if sc is not None:
        try:
            links.new(vout, sc)
        except (RuntimeError, TypeError, ValueError):
            sc.default_value = (scale_val, scale_val, scale_val)

    for img in img_nodes:
        links.new(vec_out, img.inputs["Vector"])
        img.projection = "BOX"
        img.projection_blend = blend_val
        if not img.label:
            img.label = "Triplanar (Box)"

    return (
        f"{len(img_nodes)}× Image Texture — UV comun. "
        "Scară: nodul Value → Mapping Scale. Blend: 0.15 pe fiecare (editezi manual pe nod)."
    )


class ALEC_OT_triplanar_color_maps(Operator):
    """Object → Mapping → Image Texture selectate (Box); scară prin nod Value → Scale, fără drivere."""

    bl_idname = "alec.triplanar_color_maps"
    bl_label = "Triplanar: selectate (UV comun, fără drivere)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return triplanar_has_selected_tex_images(context)

    def execute(self, context):
        tree = triplanar_target_shader_tree(context)
        if tree is None:
            self.report({"ERROR"}, "Nu s-a găsit un arbore de noduri shader.")
            return {"CANCELLED"}
        imgs = selected_tex_image_nodes(tree)
        if not imgs:
            self.report({"ERROR"}, "Selectează unul sau mai multe noduri Image Texture.")
            return {"CANCELLED"}
        _deselect_all(tree.nodes)
        msg = apply_shared_box_triplanar(tree, imgs)
        for img in imgs:
            img.select = True
        tree.nodes.active = imgs[-1]
        self.report({"INFO"}, msg or "Triplanar aplicat.")
        return {"FINISHED"}


class ALEC_OT_triplanar_node_arrange(Operator):
    """Apel la Node Arrange: NA Arrange Selected."""

    bl_idname = "alec.triplanar_node_arrange"
    bl_label = "NA Arrange Selected"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if _shader_node_tree(context) is None:
            return False
        na = getattr(bpy.ops.node, "na_arrange_selected", None)
        if na is None:
            return False
        try:
            return na.poll()
        except Exception:
            return False

    def execute(self, context):
        try:
            return bpy.ops.node.na_arrange_selected()
        except Exception as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}


def _unregister_legacy_material_triplanar_props():
    for attr in ("alec_triplanar_box_scale", "alec_triplanar_box_blend"):
        if hasattr(bpy.types.Material, attr):
            try:
                delattr(bpy.types.Material, attr)
            except Exception:
                pass


def post_register():
    _unregister_legacy_material_triplanar_props()


classes = (
    ALEC_OT_triplanar_color_maps,
    ALEC_OT_triplanar_node_arrange,
)
