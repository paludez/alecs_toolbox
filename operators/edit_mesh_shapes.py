import bpy
import bmesh
import math
from mathutils import Vector

from ..modules import edit_mesh_helpers as emh
from .edit_mesh import (
    ProportionalFalloffMixin,
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


def _order_boundary_verts(bm, boundary_verts, center, tangent, bitangent):
    boundary_set = set(boundary_verts)
    adj = {v: [] for v in boundary_verts}

    for f in bm.faces:
        if not f.select:
            continue
        for e in f.edges:
            if sum(1 for lf in e.link_faces if lf.select) != 1:
                continue
            v0, v1 = e.verts
            if v0 in boundary_set and v1 in boundary_set:
                adj[v0].append(v1)
                adj[v1].append(v0)

    if any(adj[v] for v in boundary_verts):
        start = max(boundary_verts, key=lambda v: len(adj[v]))
        ordered = [start]
        prev = None
        current = start
        while len(ordered) < len(boundary_verts):
            neighbors = [n for n in adj[current] if n != prev]
            if not neighbors:
                break
            nxt = neighbors[0]
            if nxt in ordered:
                break
            ordered.append(nxt)
            prev, current = current, nxt

        if len(ordered) == len(boundary_verts):
            return ordered

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


def _step_corner(corners, slot, delta, n):
    c = list(_clamp_corners_to_valid(corners, n))
    lo = c[slot - 1] if slot > 0 else 0
    hi = c[slot + 1] if slot < 3 else n - 1
    new_val = c[slot] + delta
    if new_val < lo:
        new_val = hi
    elif new_val > hi:
        new_val = lo
    c[slot] = new_val
    return _clamp_corners_to_valid(c, n)


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
    corner_0: bpy.props.IntProperty(name="Corner 1", default=0, min=0) # type: ignore
    corner_1: bpy.props.IntProperty(name="Corner 2", default=0, min=0) # type: ignore
    corner_2: bpy.props.IntProperty(name="Corner 3", default=0, min=0) # type: ignore
    corner_3: bpy.props.IntProperty(name="Corner 4", default=0, min=0) # type: ignore

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
                for slot, (attr, label) in enumerate(corner_labels):
                    idx = getattr(self, attr)
                    vert_idx = ordered[idx].index if 0 <= idx < len(ordered) else idx
                    row = layout.row(align=True)
                    row.label(text=f"{label} (V{vert_idx})")
                    sub = row.row(align=True)
                    op = sub.operator("alec.make_square_corner_step", text="", icon='TRIA_LEFT')
                    op.slot = slot
                    op.delta = -1
                    sub.prop(self, attr, text="")
                    op = sub.operator("alec.make_square_corner_step", text="", icon='TRIA_RIGHT')
                    op.slot = slot
                    op.delta = 1

        self.draw_falloff(layout)

    def invoke(self, context, event):
        self.reset_proportional_falloff()
        self.flatten_interior = 0.0
        self.relax_interior = 0.0
        obj = context.active_object
        if obj and obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            boundary_verts, _, _ = get_boundary_and_interior_verts(bm, context)
            n = len(boundary_verts)
            if n >= 4:
                center = sum((v.co for v in boundary_verts), Vector()) / n
                normal = _get_plane_normal(bm, context, boundary_verts)
                tangent = normal.orthogonal().normalized()
                bitangent = normal.cross(tangent).normalized()
                ordered = _order_boundary_verts(bm, boundary_verts, center, tangent, bitangent)
                self.corner_0, self.corner_1, self.corner_2, self.corner_3 = _init_square_corners(n)
                max_extent = 0.0
                for v in ordered:
                    u, w, _ = _project_vert_2d(v, center, normal, tangent, bitangent)
                    max_extent = max(max_extent, abs(u), abs(w))
                self.size = max_extent * 2.0
                c0_vert = ordered[self.corner_0]
                u0, w0, _ = _project_vert_2d(c0_vert, center, normal, tangent, bitangent)
                corner_angle = math.atan2(w0, u0)
                self.rotation = corner_angle + math.pi * 0.75
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)

        old_coords = {v: v.co.copy() for v in bm.verts}

        boundary_verts, interior_verts, _ = get_boundary_and_interior_verts(bm, context)
        if len(boundary_verts) < 4:
            self.report({'WARNING'}, "Select at least 4 vertices")
            return {'CANCELLED'}

        center = sum((v.co for v in boundary_verts), Vector()) / len(boundary_verts)
        normal = _get_plane_normal(bm, context, boundary_verts)
        tangent = normal.orthogonal().normalized()
        bitangent = normal.cross(tangent).normalized()

        ordered = _order_boundary_verts(bm, boundary_verts, center, tangent, bitangent)
        n = len(ordered)
        corners = _clamp_corners_to_valid(
            (self.corner_0, self.corner_1, self.corner_2, self.corner_3), n
        )
        self.corner_0, self.corner_1, self.corner_2, self.corner_3 = corners

        half_size = self.size * 0.5
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

                target = _square_target_3d(
                    center, tangent, bitangent, normal,
                    half_size, self.rotation, arc_s, dist_normal, self.flatten,
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


class ALEC_OT_make_square_corner_step(bpy.types.Operator):
    """Step a square corner to the previous or next boundary vertex"""
    bl_idname = "alec.make_square_corner_step"
    bl_label = "Adjust Square Corner"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    slot: bpy.props.IntProperty(name="Corner Slot", default=0, min=0, max=3) # type: ignore
    delta: bpy.props.IntProperty(name="Delta", default=1) # type: ignore

    @classmethod
    def poll(cls, context):
        op = context.active_operator
        return op is not None and op.bl_idname == "alec.make_square"

    def execute(self, context):
        op = context.active_operator
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        boundary_verts, _, _ = get_boundary_and_interior_verts(bm, context)
        n = len(boundary_verts)
        if n < 4:
            return {'CANCELLED'}

        corners = (op.corner_0, op.corner_1, op.corner_2, op.corner_3)
        new_corners = _step_corner(corners, self.slot, self.delta, n)
        op.corner_0, op.corner_1, op.corner_2, op.corner_3 = new_corners
        return op.execute(context)


classes = (
    ALEC_OT_make_circle,
    ALEC_OT_make_square,
    ALEC_OT_make_square_corner_step,
)
