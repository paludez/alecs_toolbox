import bpy
import bmesh
import math
from mathutils import Vector

from ..modules import edit_mesh_helpers as emh
from ..modules.edit_mesh_helpers import ProportionalFalloffMixin
from .edit_mesh import (
    get_boundary_and_interior_verts,
    relax_planar_vertices,
)


def _get_plane_normal(bm, context, verts):
    if context.tool_settings.mesh_select_mode[2]:
        faces = [f for f in bm.faces if f.select]
        if faces:
            n = Vector((0, 0, 0))
            for f in faces:
                n += f.normal
            if n.length_squared > 1e-10:
                return n.normalized()

    count = len(verts)
    a = verts[0].co
    b = verts[count // 3].co
    c = verts[2 * count // 3].co
    n = (b - a).cross(c - a)
    if n.length_squared > 1e-10:
        return n.normalized()

    return Vector((0, 0, 1))


def _project_to_local_tangent(co, anchor, normal):
    return co - normal * (co - anchor).dot(normal)


def _build_square_frame(bm, context, boundary_verts):
    center = sum((v.co for v in boundary_verts), Vector()) / len(boundary_verts)
    normal = _get_plane_normal(bm, context, boundary_verts)
    tangent = normal.orthogonal().normalized()
    bitangent = normal.cross(tangent).normalized()
    ordered = _order_boundary_verts(bm, boundary_verts, center, tangent, bitangent)
    corners = _find_boundary_corners(ordered, center, normal, tangent, bitangent)

    c0 = _project_to_local_tangent(ordered[corners[0]].co, center, normal)
    c1 = _project_to_local_tangent(ordered[corners[1]].co, center, normal)
    edge = c1 - c0
    if edge.length_squared > 1e-12:
        tangent = edge.normalized()
        bitangent = normal.cross(tangent).normalized()

    return center, normal, tangent, bitangent, ordered, corners


def _find_corners_by_quadrants(ordered, center, normal, tangent, bitangent):
    n = len(ordered)
    if n < 4:
        return _init_square_corners(n)

    quadrants = [[] for _ in range(4)]
    for i, v in enumerate(ordered):
        u, w, _ = _project_vert_2d(v, center, normal, tangent, bitangent)
        angle = math.atan2(w, u)
        q = int((angle + math.pi) / (math.pi / 2)) % 4
        quadrants[q].append((u * u + w * w, i))

    corners = []
    for q in quadrants:
        if q:
            corners.append(max(q)[1])
    if len(corners) < 4:
        return _init_square_corners(n)
    corners.sort()
    return tuple(corners)


def _order_boundary_verts(bm, boundary_verts, center, tangent, bitangent):
    def _angle_key(v):
        d = v.co - center
        return math.atan2(d.dot(bitangent), d.dot(tangent))

    return sorted(boundary_verts, key=_angle_key)


def _square_point_at_arc_length(s, half_size, rotation):
    size = half_size * 2.0
    perimeter = 4.0 * size
    if perimeter <= 1e-9:
        return Vector((0.0, 0.0))
    s = s % perimeter

    if s <= size:
        u = -half_size + s
        v = -half_size
    elif s <= 2.0 * size:
        u = half_size
        v = -half_size + (s - size)
    elif s <= 3.0 * size:
        u = half_size - (s - 2.0 * size)
        v = half_size
    else:
        u = -half_size
        v = half_size - (s - 3.0 * size)

    cos_r = math.cos(rotation)
    sin_r = math.sin(rotation)
    return Vector((u * cos_r - v * sin_r, u * sin_r + v * cos_r))


def _square_target_3d(center, tangent, bitangent, normal, half_size, rotation, arc_s, dist_normal, flatten):
    local_2d = _square_point_at_arc_length(arc_s, half_size, rotation)
    target = center + tangent * local_2d.x + bitangent * local_2d.y
    target += normal * dist_normal * (1.0 - flatten)
    return target


def _vertex_turn_sharpness(ordered, i):
    n = len(ordered)
    e1 = ordered[i].co - ordered[(i - 1) % n].co
    e2 = ordered[(i + 1) % n].co - ordered[i].co
    if e1.length_squared < 1e-12 or e2.length_squared < 1e-12:
        return 0.0
    cross = e1.cross(e2)
    dot = e1.dot(e2)
    return math.atan2(cross.length, dot)


def _find_boundary_corners(ordered, center, normal, tangent, bitangent):
    n = len(ordered)
    if n < 4:
        return _init_square_corners(n)

    sharpness = [_vertex_turn_sharpness(ordered, i) for i in range(n)]
    min_turn = math.radians(45.0)
    candidates = []
    for i in range(n):
        s_curr = sharpness[i]
        if s_curr < min_turn:
            continue
        if s_curr >= sharpness[(i - 1) % n] and s_curr >= sharpness[(i + 1) % n]:
            candidates.append((i, s_curr))

    if len(candidates) >= 4:
        if len(candidates) > 4:
            candidates = sorted(candidates, key=lambda x: -x[1])[:4]
        candidates.sort(key=lambda x: x[0])
        return tuple(c[0] for c in candidates[:4])

    return _find_corners_by_quadrants(ordered, center, normal, tangent, bitangent)


def _boundary_loop_length(ordered):
    n = len(ordered)
    if n < 2:
        return 0.0
    length = 0.0
    for i in range(n):
        length += (ordered[(i + 1) % n].co - ordered[i].co).length
    return length


def _init_square_corners(n):
    if n < 4:
        return 0, 0, 0, 0
    return 0, n // 4, n // 2, (3 * n) // 4


def _clamp_corners_to_valid(corners, n):
    c0, c1, c2, c3 = corners
    c0 = max(0, min(c0, n - 1))
    c1 = max(c0, min(c1, n - 1))
    c2 = max(c1, min(c2, n - 1))
    c3 = max(c2, min(c3, n - 1))
    return c0, c1, c2, c3


def _segment_order_indices(c_start, c_end, n):
    indices = []
    i = c_start
    while True:
        indices.append(i)
        if i == c_end:
            break
        i = (i + 1) % n
        if len(indices) > n:
            break
    return indices


def _project_vert_2d(v, center, normal, tangent, bitangent):
    vec = v.co - center
    dist_normal = vec.dot(normal)
    d = vec - dist_normal * normal
    return d.dot(tangent), d.dot(bitangent), dist_normal


def update_circle_rotation(self, context):
    self.rotation = 0.0


class ALEC_OT_make_circle(ProportionalFalloffMixin, bpy.types.Operator):
    """Selected vertices into a perfect circle"""
    bl_idname = "alec.make_circle"
    bl_label = "Make Circle"
    bl_options = {'REGISTER', 'UNDO'}

    radius: bpy.props.FloatProperty(name="Radius", default=1.0, min=0.0, unit='LENGTH', update=update_circle_rotation) # type: ignore
    influence: bpy.props.FloatProperty(name="Influence", default=1.0, min=0.0, max=1.0, subtype='FACTOR', update=update_circle_rotation) # type: ignore
    flatten: bpy.props.FloatProperty(name="Flatten", default=1.0, min=0.0, max=1.0, subtype='FACTOR', description="Flatten vertices to the plane", update=update_circle_rotation) # type: ignore
    flatten_interior: bpy.props.FloatProperty(name="Flatten Interior", default=0.0, min=0.0, max=1.0, subtype='FACTOR', description="Flatten interior face vertices to the plane", update=update_circle_rotation) # type: ignore
    relax_interior: bpy.props.FloatProperty(name="Relax Interior", default=0.0, min=0.0, max=1.0, subtype='FACTOR', description="Relax interior vertices within the projection plane", update=update_circle_rotation) # type: ignore
    regular: bpy.props.BoolProperty(name="Regular", default=True, description="Distribute vertices evenly", update=update_circle_rotation) # type: ignore
    rotation: bpy.props.FloatProperty(name="Rotation", default=0.0, subtype='ANGLE', description="Rotate vertices along the circle") # type: ignore

    @classmethod
    def poll(cls, context):
        return emh.poll_active_mesh_edit_mode(context)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "radius")
        layout.prop(self, "influence")
        layout.prop(self, "flatten")
        if context.tool_settings.mesh_select_mode[2]:
            layout.prop(self, "flatten_interior")
            layout.prop(self, "relax_interior")
        layout.prop(self, "regular")
        layout.prop(self, "rotation")
        self.draw_falloff(layout)

    def invoke(self, context, event):
        self.reset_proportional_falloff()
        self.flatten_interior = 0.0
        self.relax_interior = 0.0
        obj = context.active_object
        if obj and obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            boundary_verts, _, _ = get_boundary_and_interior_verts(bm, context)
            if len(boundary_verts) >= 3:
                center = Vector((0, 0, 0))
                for v in boundary_verts:
                    center += v.co
                center /= len(boundary_verts)
                max_dist_sq = max(((v.co - center).length_squared for v in boundary_verts), default=1.0)
                self.radius = math.sqrt(max_dist_sq)
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)

        old_coords = {v: v.co.copy() for v in bm.verts}

        boundary_verts, interior_verts, _ = get_boundary_and_interior_verts(bm, context)
        verts = boundary_verts

        if len(verts) < 3:
            self.report({'WARNING'}, "Select at least 3 vertices")
            return {'CANCELLED'}

        center = Vector((0, 0, 0))
        for v in verts:
            center += v.co
        center /= len(verts)

        normal = _get_plane_normal(bm, context, verts)

        tangent: Vector = normal.orthogonal() # type: ignore[assignment]
        tangent.normalize()
        bitangent: Vector = normal.cross(tangent) # type: ignore[assignment]
        bitangent.normalize()

        pairs = []
        for v in verts:
            vec = v.co - center
            dist_normal = vec.dot(normal)
            d = vec - dist_normal * normal
            angle = math.atan2(d.dot(bitangent), d.dot(tangent))
            pairs.append((v, angle, dist_normal))

        pairs.sort(key=lambda x: x[1])
        count = len(pairs)
        r = self.radius

        if self.regular:
            step = 2 * math.pi / count
            phase = sum(pairs[i][1] - i * step for i in range(count)) / count
            for i, (v, _, dist_normal) in enumerate(pairs):
                theta = phase + i * step + self.rotation
                target = center + tangent * math.cos(theta) * r + bitangent * math.sin(theta) * r
                target += normal * dist_normal * (1.0 - self.flatten)
                v.co = v.co.lerp(target, self.influence)
        else:
            for v, angle, dist_normal in pairs:
                theta = angle + self.rotation
                target = center + tangent * math.cos(theta) * r + bitangent * math.sin(theta) * r
                target += normal * dist_normal * (1.0 - self.flatten)
                v.co = v.co.lerp(target, self.influence)

        if interior_verts and self.flatten_interior > 0.0:
            for v in interior_verts:
                vec = v.co - center
                dist_normal = vec.dot(normal)
                target = v.co - normal * dist_normal
                v.co = v.co.lerp(target, self.flatten_interior * self.influence)

        if interior_verts and self.relax_interior > 0.0:
            relax_planar_vertices(interior_verts, normal, self.relax_interior * self.influence)

        moved_verts = set(verts)
        if interior_verts:
            moved_verts.update(interior_verts)

        moved_coords = {v: v.co.copy() for v in moved_verts}

        self.process_falloff(bm, old_coords, moved_coords, obj.matrix_world)

        bmesh.update_edit_mesh(obj.data)
        return {'FINISHED'}


class ALEC_OT_make_square(ProportionalFalloffMixin, bpy.types.Operator):
    """Selected vertices into a perfect square"""
    bl_idname = "alec.make_square"
    bl_label = "Make Square"
    bl_options = {'REGISTER', 'UNDO'}

    size: bpy.props.FloatProperty(name="Size", default=1.0, min=0.0, unit='LENGTH') # type: ignore
    influence: bpy.props.FloatProperty(name="Influence", default=1.0, min=0.0, max=1.0, subtype='FACTOR') # type: ignore
    flatten: bpy.props.FloatProperty(name="Flatten", default=1.0, min=0.0, max=1.0, subtype='FACTOR', description="Flatten vertices to the plane") # type: ignore
    flatten_interior: bpy.props.FloatProperty(name="Flatten Interior", default=0.0, min=0.0, max=1.0, subtype='FACTOR', description="Flatten interior face vertices to the plane") # type: ignore
    relax_interior: bpy.props.FloatProperty(name="Relax Interior", default=0.0, min=0.0, max=1.0, subtype='FACTOR', description="Relax interior vertices within the projection plane") # type: ignore
    regular: bpy.props.BoolProperty(name="Regular", default=True, description="Distribute vertices evenly along each edge") # type: ignore
    rotation: bpy.props.FloatProperty(name="Rotation", default=0.0, subtype='ANGLE', description="Rotate the square in the selection plane") # type: ignore
    spin: bpy.props.FloatProperty(name="Spin", default=0.0, unit='LENGTH', description="Slide vertex mapping along the square perimeter") # type: ignore
    offset: bpy.props.IntProperty(name="Offset", default=0, description="Shift all corner assignments along the boundary loop") # type: ignore
    corner_0: bpy.props.IntProperty(name="Corner 1", default=0, min=0) # type: ignore
    corner_1: bpy.props.IntProperty(name="Corner 2", default=0, min=0) # type: ignore
    corner_2: bpy.props.IntProperty(name="Corner 3", default=0, min=0) # type: ignore
    corner_3: bpy.props.IntProperty(name="Corner 4", default=0, min=0) # type: ignore
    init_done: bpy.props.BoolProperty(name="", default=False, options={'HIDDEN'}) # type: ignore
    base_rotation: bpy.props.FloatProperty(name="", default=0.0, options={'HIDDEN'}) # type: ignore
    ref_center: bpy.props.FloatVectorProperty(name="", size=3, default=(0.0, 0.0, 0.0), options={'HIDDEN'}) # type: ignore
    ref_normal: bpy.props.FloatVectorProperty(name="", size=3, default=(0.0, 0.0, 1.0), options={'HIDDEN'}) # type: ignore
    ref_tangent: bpy.props.FloatVectorProperty(name="", size=3, default=(1.0, 0.0, 0.0), options={'HIDDEN'}) # type: ignore

    def _init_square_reference(self, bm, context, boundary_verts):
        center, normal, tangent, bitangent, ordered, corners = _build_square_frame(
            bm, context, boundary_verts
        )
        self.corner_0, self.corner_1, self.corner_2, self.corner_3 = corners
        self.size = _boundary_loop_length(ordered) * 0.25
        self.rotation = 0.0
        self.base_rotation = 0.0
        self.ref_center = center
        self.ref_normal = normal
        self.ref_tangent = tangent
        self.init_done = True
        return ordered, normal, tangent, bitangent, corners

    @classmethod
    def poll(cls, context):
        return emh.poll_active_mesh_edit_mode(context)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "size")
        layout.prop(self, "influence")
        layout.prop(self, "flatten")
        if context.tool_settings.mesh_select_mode[2]:
            layout.prop(self, "flatten_interior")
            layout.prop(self, "relax_interior")
        layout.prop(self, "regular")
        layout.prop(self, "rotation")
        layout.prop(self, "spin")
        layout.prop(self, "offset")

        obj = context.active_object
        if obj and obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            boundary_verts, _, _ = get_boundary_and_interior_verts(bm, context)
            if boundary_verts:
                center = sum((v.co for v in boundary_verts), Vector()) / len(boundary_verts)
                normal = _get_plane_normal(bm, context, boundary_verts)
                tangent = normal.orthogonal().normalized()
                bitangent = normal.cross(tangent).normalized()
                ordered = _order_boundary_verts(bm, boundary_verts, center, tangent, bitangent)
                corner_labels = (
                    ("corner_0", "Corner 1"),
                    ("corner_1", "Corner 2"),
                    ("corner_2", "Corner 3"),
                    ("corner_3", "Corner 4"),
                )
                for attr, label in corner_labels:
                    idx = (getattr(self, attr) + self.offset) % len(ordered)
                    vert_idx = ordered[idx].index if 0 <= idx < len(ordered) else idx
                    row = layout.row(align=True)
                    row.label(text=f"{label} (V{vert_idx})")
                    row.prop(self, attr, text="")

        self.draw_falloff(layout)

    def invoke(self, context, event):
        self.reset_proportional_falloff()
        self.flatten_interior = 0.0
        self.relax_interior = 0.0
        self.spin = 0.0
        self.offset = 0
        self.init_done = False
        obj = context.active_object
        if obj and obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            boundary_verts, _, _ = get_boundary_and_interior_verts(bm, context)
            if len(boundary_verts) >= 4:
                self._init_square_reference(bm, context, boundary_verts)
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)

        old_coords = {v: v.co.copy() for v in bm.verts}

        boundary_verts, interior_verts, _ = get_boundary_and_interior_verts(bm, context)
        if len(boundary_verts) < 4:
            self.report({'WARNING'}, "Select at least 4 vertices")
            return {'CANCELLED'}

        if self.init_done:
            center = Vector(self.ref_center)
            normal = Vector(self.ref_normal).normalized()
            tangent = Vector(self.ref_tangent).normalized()
            bitangent = normal.cross(tangent).normalized()
            ordered = _order_boundary_verts(bm, boundary_verts, center, tangent, bitangent)
        else:
            ordered, normal, tangent, bitangent, _ = self._init_square_reference(
                bm, context, boundary_verts
            )
            center = Vector(self.ref_center)

        n = len(ordered)
        base_corners = (
            self.corner_0, self.corner_1, self.corner_2, self.corner_3,
        )
        if base_corners == (0, 0, 0, 0):
            base_corners = _find_boundary_corners(ordered, center, normal, tangent, bitangent)
            base_corners = _clamp_corners_to_valid(base_corners, n)
            self.corner_0, self.corner_1, self.corner_2, self.corner_3 = base_corners
        else:
            base_corners = _clamp_corners_to_valid(base_corners, n)
            self.corner_0, self.corner_1, self.corner_2, self.corner_3 = base_corners

        corners = tuple((c + self.offset) % n for c in base_corners)

        half_size = self.size * 0.5
        effective_rotation = self.base_rotation + self.rotation
        perimeter = max(self.size * 4.0, 1e-9)
        corner_arcs = [0.0, self.size, 2.0 * self.size, 3.0 * self.size]

        for seg in range(4):
            c_start = corners[seg]
            c_end = corners[(seg + 1) % 4]
            seg_indices = _segment_order_indices(c_start, c_end, n)
            if len(seg_indices) < 2:
                continue

            arc_start = corner_arcs[seg]
            arc_end = corner_arcs[(seg + 1) % 4]
            edge_arc_len = self.size

            source_dists = [0.0]
            for i in range(1, len(seg_indices)):
                v_prev = ordered[seg_indices[i - 1]]
                v_curr = ordered[seg_indices[i]]
                source_dists.append(source_dists[-1] + (v_curr.co - v_prev.co).length)
            total_source_len = source_dists[-1]

            for local_i, order_idx in enumerate(seg_indices):
                # Corner already placed as the last vertex of the previous segment.
                if seg > 0 and local_i == 0:
                    continue
                # corner_0 wrap-around - already placed as the first vertex of seg 0.
                if seg == 3 and local_i == len(seg_indices) - 1:
                    continue

                v = ordered[order_idx]
                _, _, dist_normal = _project_vert_2d(v, center, normal, tangent, bitangent)

                if local_i == 0:
                    arc_s = arc_start
                elif local_i == len(seg_indices) - 1:
                    arc_s = arc_end
                elif self.regular:
                    t = local_i / (len(seg_indices) - 1)
                    arc_s = arc_start + t * edge_arc_len
                elif total_source_len > 1e-9:
                    t = source_dists[local_i] / total_source_len
                    arc_s = arc_start + t * edge_arc_len
                else:
                    t = local_i / (len(seg_indices) - 1)
                    arc_s = arc_start + t * edge_arc_len

                arc_s = (arc_s + self.spin) % perimeter

                target = _square_target_3d(
                    center, tangent, bitangent, normal,
                    half_size, effective_rotation, arc_s, dist_normal, self.flatten,
                )
                v.co = v.co.lerp(target, self.influence)

        if interior_verts and self.flatten_interior > 0.0:
            for v in interior_verts:
                vec = v.co - center
                dist_normal = vec.dot(normal)
                target = v.co - normal * dist_normal
                v.co = v.co.lerp(target, self.flatten_interior * self.influence)

        if interior_verts and self.relax_interior > 0.0:
            relax_planar_vertices(interior_verts, normal, self.relax_interior * self.influence)

        moved_verts = set(boundary_verts)
        if interior_verts:
            moved_verts.update(interior_verts)

        moved_coords = {v: v.co.copy() for v in moved_verts}
        self.process_falloff(bm, old_coords, moved_coords, obj.matrix_world)

        bmesh.update_edit_mesh(obj.data)
        return {'FINISHED'}


classes = (
    ALEC_OT_make_circle,
    ALEC_OT_make_square,
)
