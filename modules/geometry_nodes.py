import bpy

def get_or_create_slice_gn_tree():
    """Initialize Alec_Slice_Plane_GN node group"""
    tree_name = "Alec_Slice_Plane_GN"
    if tree_name in bpy.data.node_groups:
        return bpy.data.node_groups[tree_name]
        
    tree = bpy.data.node_groups.new(name=tree_name, type='GeometryNodeTree')
    tree.color_tag = 'NONE'
    tree.description = ""
    tree.default_group_node_width = 140
    
    try:
        tree.show_modifier_manage_panel = True
    except AttributeError:
        pass

    geometry_socket = tree.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    try:
        geometry_socket.attribute_domain = 'POINT'
        geometry_socket.default_input = 'VALUE'
        geometry_socket.structure_type = 'AUTO'
    except AttributeError: pass

    geometry_socket_1 = tree.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    try:
        geometry_socket_1.attribute_domain = 'POINT'
        geometry_socket_1.default_input = 'VALUE'
        geometry_socket_1.structure_type = 'AUTO'
    except AttributeError: pass

    flip_socket = tree.interface.new_socket(name="Flip", in_out='INPUT', socket_type='NodeSocketBool')
    flip_socket.default_value = False
    try:
        flip_socket.attribute_domain = 'POINT'
        flip_socket.default_input = 'VALUE'
        flip_socket.structure_type = 'AUTO'
    except AttributeError: pass

    z_socket = tree.interface.new_socket(name="Location", in_out='INPUT', socket_type='NodeSocketFloat')
    z_socket.default_value = 0.0
    z_socket.min_value = -10000.0
    z_socket.max_value = 10000.0
    try:
        z_socket.subtype = 'DISTANCE'
        z_socket.attribute_domain = 'POINT'
        z_socket.default_input = 'VALUE'
        z_socket.structure_type = 'AUTO'
    except AttributeError: pass

    x_socket = tree.interface.new_socket(name="Rotate X", in_out='INPUT', socket_type='NodeSocketFloat')
    x_socket.default_value = 0.0
    x_socket.min_value = -10000.0
    x_socket.max_value = 10000.0
    try:
        x_socket.subtype = 'ANGLE'
        x_socket.attribute_domain = 'POINT'
        x_socket.default_input = 'VALUE'
        x_socket.structure_type = 'AUTO'
    except AttributeError: pass

    y_socket = tree.interface.new_socket(name="Rotate Y", in_out='INPUT', socket_type='NodeSocketFloat')
    y_socket.default_value = -0.0
    y_socket.min_value = -10000.0
    y_socket.max_value = 10000.0
    try:
        y_socket.subtype = 'ANGLE'
        y_socket.attribute_domain = 'POINT'
        y_socket.default_input = 'VALUE'
        y_socket.structure_type = 'AUTO'
    except AttributeError: pass
    
    nodes = tree.nodes
    links = tree.links
    
    group_input = nodes.new("NodeGroupInput")
    group_input.name = "Group Input"

    group_output = nodes.new("NodeGroupOutput")
    group_output.name = "Group Output"
    group_output.is_active_output = True

    transform_gizmo = nodes.new("GeometryNodeGizmoTransform")
    transform_gizmo.name = "Transform Gizmo"
    transform_gizmo.use_rotation_x = True
    transform_gizmo.use_rotation_y = True
    transform_gizmo.use_rotation_z = False
    transform_gizmo.use_scale_x = False
    transform_gizmo.use_scale_y = False
    transform_gizmo.use_scale_z = False
    transform_gizmo.use_translation_x = False
    transform_gizmo.use_translation_y = False
    transform_gizmo.use_translation_z = True

    grid = nodes.new("GeometryNodeMeshGrid")
    grid.name = "Grid"
    grid.inputs[0].default_value = 5.0 # Size X
    grid.inputs[1].default_value = 5.0 # Size Y
    grid.inputs[2].default_value = 2   # Vertices X
    grid.inputs[3].default_value = 2   # Vertices Y

    transform_geometry = nodes.new("GeometryNodeTransform")
    transform_geometry.name = "Transform Geometry"
    try: transform_geometry.inputs[1].default_value = 'Components'
    except: pass
    transform_geometry.inputs[4].default_value = (1.0, 1.0, 1.0)

    flip_faces = nodes.new("GeometryNodeFlipFaces")
    flip_faces.name = "Flip Faces"
    flip_faces.inputs[1].default_value = True

    keep_bottom = nodes.new("GeometryNodeMeshBoolean")
    keep_bottom.name = "Keep Bottom"
    keep_bottom.operation = 'DIFFERENCE'
    keep_bottom.solver = 'EXACT'
    keep_bottom.inputs[2].default_value = False
    keep_bottom.inputs[3].default_value = False

    switch_flip = nodes.new("GeometryNodeSwitch")
    switch_flip.name = "Switch Flip"
    switch_flip.input_type = 'GEOMETRY'

    combine_transform = nodes.new("FunctionNodeCombineTransform")
    combine_transform.name = "Combine Transform"
    combine_transform.inputs[2].default_value = (1.0, 1.0, 1.0)
    
    group_input_001 = nodes.new("NodeGroupInput")
    group_input_001.name = "Group Input.001"

    combine_xyz = nodes.new("ShaderNodeCombineXYZ")
    combine_xyz.name = "Combine XYZ"
    combine_xyz.inputs[0].default_value = 0.0
    combine_xyz.inputs[1].default_value = 0.0

    combine_xyz_001 = nodes.new("ShaderNodeCombineXYZ")
    combine_xyz_001.name = "Combine XYZ.001"
    combine_xyz_001.inputs[2].default_value = 0.0

    reroute = nodes.new("NodeReroute")
    reroute.name = "Reroute"
    try: reroute.socket_idname = "NodeSocketGeometry"
    except: pass
    reroute_001 = nodes.new("NodeReroute")
    reroute_001.name = "Reroute.001"
    try: reroute_001.socket_idname = "NodeSocketVector"
    except: pass
    reroute_002 = nodes.new("NodeReroute")
    reroute_002.name = "Reroute.002"
    try: reroute_002.socket_idname = "NodeSocketVector"
    except: pass
    reroute_003 = nodes.new("NodeReroute")
    reroute_003.name = "Reroute.003"
    try: reroute_003.socket_idname = "NodeSocketVector"
    except: pass
    reroute_004 = nodes.new("NodeReroute")
    reroute_004.name = "Reroute.004"
    try: reroute_004.socket_idname = "NodeSocketVector"
    except: pass
    reroute_005 = nodes.new("NodeReroute")
    reroute_005.name = "Reroute.005"
    try: reroute_005.socket_idname = "NodeSocketGeometry"
    except: pass
    reroute_006 = nodes.new("NodeReroute")
    reroute_006.name = "Reroute.006"
    try: reroute_006.socket_idname = "NodeSocketGeometry"
    except: pass

    # Set locations
    nodes["Group Input"].location = (-267.7757568359375, 61.90191650390625)
    nodes["Group Output"].location = (314.7242431640625, 70.69218444824219)
    nodes["Transform Gizmo"].location = (-267.7757568359375, -460.7025146484375)
    nodes["Grid"].location = (-710.2757568359375, -148.01522827148438)
    nodes["Transform Geometry"].location = (-470.2757568359375, -159.94244384765625)
    nodes["Flip Faces"].location = (-267.7757568359375, -206.09808349609375)
    nodes["Keep Bottom"].location = (124.7242431640625, 70.69218444824219)
    nodes["Switch Flip"].location = (-65.2757568359375, -77.36163330078125)
    nodes["Combine Transform"].location = (-470.2757568359375, -504.03680419921875)
    nodes["Group Input.001"].location = (-900.2757568359375, -480.7767333984375)
    nodes["Combine XYZ"].location = (-710.2757568359375, -361.1095886230469)
    nodes["Combine XYZ.001"].location = (-710.2757568359375, -547.046875)
    nodes["Reroute"].location = (74.7242431640625, 27.322189331054688)
    nodes["Reroute.001"].location = (-470.2757568359375, -407.94244384765625)
    nodes["Reroute.002"].location = (-330.2757568359375, -407.94244384765625)
    nodes["Reroute.003"].location = (-470.2757568359375, -735.0368041992188)
    nodes["Reroute.004"].location = (-330.2757568359375, -735.0368041992188)
    nodes["Reroute.005"].location = (-267.7757568359375, -148.09808349609375)
    nodes["Reroute.006"].location = (-127.7757568359375, -148.09808349609375)

    # Links
    links.new(grid.outputs[0], transform_geometry.inputs[0])
    links.new(combine_transform.outputs[0], transform_gizmo.inputs[0])
    links.new(transform_geometry.outputs[0], flip_faces.inputs[0])
    links.new(combine_xyz.outputs[0], combine_transform.inputs[0])
    links.new(group_input_001.outputs[2], combine_xyz.inputs[2])
    links.new(combine_xyz.outputs[0], transform_geometry.inputs[2])
    links.new(combine_xyz_001.outputs[0], combine_transform.inputs[1])
    links.new(group_input_001.outputs[3], combine_xyz_001.inputs[0])
    links.new(group_input_001.outputs[4], combine_xyz_001.inputs[1])
    links.new(combine_xyz_001.outputs[0], transform_geometry.inputs[3])
    links.new(keep_bottom.outputs[0], group_output.inputs[0])
    links.new(flip_faces.outputs[0], switch_flip.inputs[2])
    links.new(switch_flip.outputs[0], keep_bottom.inputs[1])
    links.new(group_input.outputs[1], switch_flip.inputs[0])
    links.new(group_input.outputs[0], reroute.inputs[0])
    links.new(transform_geometry.outputs[0], reroute_005.inputs[0])
    links.new(combine_xyz.outputs[0], reroute_001.inputs[0])
    links.new(combine_xyz_001.outputs[0], reroute_003.inputs[0])
    links.new(reroute_005.outputs[0], reroute_006.inputs[0])
    links.new(reroute_001.outputs[0], reroute_002.inputs[0])
    links.new(reroute_003.outputs[0], reroute_004.inputs[0])
    links.new(reroute_002.outputs[0], transform_gizmo.inputs[1])
    links.new(reroute_004.outputs[0], transform_gizmo.inputs[2])
    links.new(reroute_006.outputs[0], switch_flip.inputs[1])
    links.new(reroute.outputs[0], keep_bottom.inputs[0])
    
    return tree