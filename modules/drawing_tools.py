import gpu
from gpu_extras.batch import batch_for_shader
import math
from mathutils import Vector, Matrix

def draw_wire_sphere(center, radius, color=(1.0, 0.6, 0.1, 0.4), segments=32):
    """Draws a simple 3D wireframe sphere (3 intersecting circles) in the viewport."""
    verts = []
    
    # XY circle
    for i in range(segments):
        a = i * 2 * math.pi / segments
        verts.append(center + Vector((math.cos(a)*radius, math.sin(a)*radius, 0)))
        a_next = (i + 1) * 2 * math.pi / segments
        verts.append(center + Vector((math.cos(a_next)*radius, math.sin(a_next)*radius, 0)))
        
    # XZ circle
    for i in range(segments):
        a = i * 2 * math.pi / segments
        verts.append(center + Vector((math.cos(a)*radius, 0, math.sin(a)*radius)))
        a_next = (i + 1) * 2 * math.pi / segments
        verts.append(center + Vector((math.cos(a_next)*radius, 0, math.sin(a_next)*radius)))
        
    # YZ circle
    for i in range(segments):
        a = i * 2 * math.pi / segments
        verts.append(center + Vector((0, math.cos(a)*radius, math.sin(a)*radius)))
        a_next = (i + 1) * 2 * math.pi / segments
        verts.append(center + Vector((0, math.cos(a_next)*radius, math.sin(a_next)*radius)))

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'LINES', {"pos": verts})

    gpu.state.blend_set('ALPHA')
    
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    
    gpu.state.blend_set('NONE')

def draw_angle_pie(center, dir_base, normal, angle, radius, color=(0.1, 0.6, 1.0, 0.4), segments=32):
    """Draws a semi-transparent pie slice to visualize an angle."""
    verts = [center]
    
    # Generate arc points
    for i in range(segments + 1):
        t = i / segments
        current_angle = angle * t
        rot_mat = Matrix.Rotation(current_angle, 3, normal)
        rotated_dir = rot_mat @ dir_base
        verts.append(center + rotated_dir * radius)
        
    # Generate triangle indices for the filled pie
    indices = []
    for i in range(1, segments + 1):
        indices.append((0, i, i + 1))
        
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch_tris = batch_for_shader(shader, 'TRIS', {"pos": verts}, indices=indices)
    
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float("color", color)
    batch_tris.draw(shader)
    
    # Draw border lines on top
    border_verts = [center, verts[1], center, verts[-1]]
    for i in range(1, segments):
        border_verts.append(verts[i])
        border_verts.append(verts[i+1])
    batch_lines = batch_for_shader(shader, 'LINES', {"pos": border_verts})
    shader.uniform_float("color", (color[0], color[1], color[2], min(1.0, color[3] * 2.5))) # Less transparent for borders
    batch_lines.draw(shader)
    
    gpu.state.blend_set('NONE')

def draw_mesh_wireframe(world_matrix, coords, normals, edges, offset, color=(0.0, 0.5, 1.0, 0.6)):
    """Draws a wireframe of a mesh with a normal-based offset."""
    new_coords = [world_matrix @ (co + normal * offset) for co, normal in zip(coords, normals)]
    
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'LINES', {"pos": new_coords}, indices=edges)
    
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.blend_set('NONE')