import bpy
import bmesh
from .modules import bbox_tools
from .modules import align_tools
from .modules import cursor_tools
from .modules import misc_tools

class ALEC_OT_group_manager(bpy.types.Operator):
    bl_idname = "alec.group_manager"
    bl_label = "Group Manager"
    bl_description = "Manage object grouping operations"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(
        items=[
            ('GROUP', "Group", "Group selected objects under a common Empty"),
            ('GROUP_ACTIVE', "Group Active", "Group selected objects under an Empty at the active object's bounding box center"),
            ('UNGROUP', "Ungroup", "Ungroup selected Empty and release all children")
        ],
        default='GROUP'
    ) # type: ignore

    def execute(self, context):
        misc_tools.manage_grouping(context, self.action)
        return {'FINISHED'}


class BBoxOperatorBase:
    """Base class for Bounding Box operators to reduce code duplication."""
    bl_options = {'REGISTER', 'UNDO'}
    mode: str = ""

    def execute(self, context):
        if not self.mode:
            self.report({'ERROR'}, "Mode not set in BBox operator subclass") # type: ignore
            return {'CANCELLED'}
        
        # Delegate to bbox_tools
        bbox_tools.create_bbox(context, mode=self.mode)
        return {'FINISHED'}


class ALEC_OT_bbox_local(BBoxOperatorBase, bpy.types.Operator):
    """Create a bounding box aligned to object's local axes"""
    bl_idname = "alec.bbox_local"
    bl_label = "LOCAL"
    mode = 'LOCAL'


class ALEC_OT_bbox_world(BBoxOperatorBase, bpy.types.Operator):
    """Create a bounding box aligned to object's world axes"""
    bl_idname = "alec.bbox_world"
    bl_label = "WORLD"
    mode = 'WORLD'


class ALEC_OT_bbox_offset(bpy.types.Operator):
    bl_idname = "alec.bbox_offset"
    bl_label = "BBoxOF"
    bl_description = "Create a bounding box with an offset from the original object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bbox_tools.create_offset_bbox(context.active_object, offset=context.scene.alec_bbox_offset)
        return {'FINISHED'}


class ALEC_OT_align(bpy.types.Operator):
    bl_idname = "alec.align"
    bl_label = "Apply"
    bl_description = "Align selected objects to active object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sc = context.scene
        target = context.active_object
        sources = [o for o in context.selected_objects if o != target]
        for source in sources:
            align_tools.align_position(source, target,
                x=sc.alec_align_x, y=sc.alec_align_y, z=sc.alec_align_z,
                source_point=sc.alec_align_source_point,
                target_point=sc.alec_align_target_point)
            align_tools.align_orientation(source, target,
                x=sc.alec_orient_x, y=sc.alec_orient_y, z=sc.alec_orient_z)
            align_tools.match_scale(source, target,
                x=sc.alec_scale_x, y=sc.alec_scale_y, z=sc.alec_scale_z)
        return {'FINISHED'}


class ALEC_OT_quick_center(bpy.types.Operator):
    bl_idname = "alec.quick_center"
    bl_label = "Quick Center"
    bl_description = "Align selected objects to active object's bounding box center"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        target = context.active_object
        sources = [o for o in context.selected_objects if o != target]
        for source in sources:
            align_tools.align_position(source, target, x=True, y=True, z=True,
                source_point='CENTER', target_point='CENTER')
            align_tools.align_orientation(source, target, x=True, y=True, z=True)
        return {'FINISHED'}


class ALEC_OT_quick_pivot(bpy.types.Operator):
    bl_idname = "alec.quick_pivot"
    bl_label = "Quick Pivot"
    bl_description = "Align selected objects to active object's pivot point"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        target = context.active_object
        sources = [o for o in context.selected_objects if o != target]
        for source in sources:
            align_tools.align_position(source, target, x=True, y=True, z=True,
                source_point='PIVOT', target_point='PIVOT')
            align_tools.align_orientation(source, target, x=True, y=True, z=True)
        return {'FINISHED'}


class ALEC_OT_cursor_to_selected(bpy.types.Operator):
    bl_idname = "alec.cursor_to_selected"
    bl_label = "Cursor to Selected"
    bl_description = "Move&Rotate 3D cursor to selected object's origin"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cursor_tools.cursor_to_selected(context)
        return {'FINISHED'}


class ALEC_OT_cursor_to_geometry_center(bpy.types.Operator):
    bl_idname = "alec.cursor_to_geometry_center"
    bl_label = "Cursor to Geometry Center"
    bl_description = "Move&Rotate 3D cursor to selected object's BBox center"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cursor_tools.cursor_to_geometry_center(context)
        return {'FINISHED'}


class ALEC_OT_origin_to_cursor(bpy.types.Operator):
    bl_idname = "alec.origin_to_cursor"
    bl_label = "Origin to Cursor"
    bl_description = "Move object origin to 3D cursor position and orientation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cursor_tools.origin_to_cursor(context)
        return {'FINISHED'}


class ALEC_OT_menu_dispatcher(bpy.types.Operator):
    bl_idname = "alec.menu_dispatcher"
    bl_label = "Menu Dispatcher"
    bl_description = "Shows a different menu based on the context (Object/Edit mode)"

    def execute(self, context):
        if context.mode == 'EDIT_MESH':
            bpy.ops.wm.call_menu(name='ALEC_MT_edit_menu')
        else:
            bpy.ops.wm.call_menu(name='ALEC_MT_object_menu')
        return {'FINISHED'}


class ALEC_OT_set_edge_length(bpy.types.Operator):
    """Set the length of the selected edge"""
    bl_idname = "alec.set_edge_length"
    bl_label = "Set Edge Length"
    bl_options = {'REGISTER', 'UNDO'}
    _initialized = False
    length: bpy.props.FloatProperty(
        name="Length",
        description="The desired length for the edge",
        default=1.0,
        min=0.001,
        unit='LENGTH'
    ) # type: ignore

    anchor: bpy.props.EnumProperty(
        name="Anchor",
        description="How to anchor the edge when resizing",
        items=[
            ('ACTIVE_VERTEX', "Active Vertex", "The active vertex will remain stationary"),
            ('CENTER', "Center", "Both vertices will move towards/away from the center")
        ],
        default='ACTIVE_VERTEX'
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == 'MESH' and
                context.mode == 'EDIT_MESH')

    def _get_active_edge(self, bm):
        """Helper to get the target edge from selection history or selection."""
        active_edge = bm.select_history.active
        if isinstance(active_edge, bmesh.types.BMEdge):
            return active_edge
        
        selected_edges = [e for e in bm.edges if e.select]
        if selected_edges:
            return selected_edges[-1]
            
        return None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = context.active_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        active_edge = self._get_active_edge(bm)
        if not active_edge:
            self.report({'WARNING'}, "No edge selected")
            return {'CANCELLED'}

        # Get object's transformation matrices to work in world space
        world_mx = obj.matrix_world
        inv_world_mx = world_mx.inverted()

        v1, v2 = active_edge.verts

        # Calculate the length on the first run, overriding the dialog's default.
        # This is the logic that correctly handles the operator's initialization.
        if not self._initialized:
            # Calculate initial length in world space to ignore object scale
            world_v1_co = world_mx @ v1.co
            world_v2_co = world_mx @ v2.co
            self.length = (world_v2_co - world_v1_co).length
            self._initialized = True

        # --- All calculations from here are in world space ---

        # Get current world-space coordinates and direction
        world_v1_co = world_mx @ v1.co
        world_v2_co = world_mx @ v2.co
        world_direction = (world_v2_co - world_v1_co).normalized()

        active_vert = bm.select_history.active
        if not isinstance(active_vert, bmesh.types.BMVert) or active_vert not in active_edge.verts:
            active_vert = v1

        if self.anchor == 'ACTIVE_VERTEX':
            if active_vert == v1:
                new_world_v2_co = world_v1_co + world_direction * self.length
                v2.co = inv_world_mx @ new_world_v2_co
            else:
                new_world_v1_co = world_v2_co - world_direction * self.length
                v1.co = inv_world_mx @ new_world_v1_co
        elif self.anchor == 'CENTER':
            world_center_point = (world_v1_co + world_v2_co) / 2
            half_length = self.length / 2
            v1.co = inv_world_mx @ (world_center_point - world_direction * half_length)
            v2.co = inv_world_mx @ (world_center_point + world_direction * half_length)

        bmesh.update_edit_mesh(me)
        return {'FINISHED'}


class ALEC_OT_make_collinear(bpy.types.Operator):
    """Make selected vertices collinear"""
    bl_idname = "alec.make_collinear"
    bl_label = "Make Collinear"
    bl_description = "Aligns selected vertices to a line"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Mode",
        description="How to determine the alignment line",
        items=[
            ('FARTHEST', "Farthest Points", "Use the two most distant vertices in the selection"),
            ('HISTORY', "Last Two Selected", "Use the last two vertices selected to define the line")
        ],
        default='FARTHEST'
    )  # type: ignore

    factor: bpy.props.FloatProperty(
        name="Factor",
        description="Influence of the operation",
        default=1.0,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == 'MESH' and
                context.mode == 'EDIT_MESH')

    def execute(self, context):
        obj = context.active_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        # Get all vertices that are part of the selection, regardless of mode (vert/edge/face)
        selected_verts = [v for v in bm.verts if v.select]

        v_start = None
        v_end = None

        if self.mode == 'FARTHEST':
            if len(selected_verts) < 2:
                self.report({'WARNING'}, "Select at least 2 vertices")
                return {'CANCELLED'}
            # --- Farthest Points Logic ---
            max_dist_sq = -1.0
            for i in range(len(selected_verts)):
                for j in range(i + 1, len(selected_verts)):
                    v_i = selected_verts[i]
                    v_j = selected_verts[j]
                    dist_sq = (v_i.co - v_j.co).length_squared
                    if dist_sq > max_dist_sq:
                        max_dist_sq = dist_sq
                        v_start = v_i
                        v_end = v_j
        elif self.mode == 'HISTORY':
            # --- Last Two Selected Logic ---
            history = [elem for elem in bm.select_history if isinstance(elem, bmesh.types.BMVert)]
            if len(history) < 2:
                self.report({'WARNING'}, "For 'Last Two Selected' mode, select at least 2 vertices in order")
                return {'CANCELLED'}
            v_start = history[-2]
            v_end = history[-1]

        if not v_start or not v_end:
            self.report({'WARNING'}, "Could not determine line endpoints")
            return {'CANCELLED'}

        # Get object's transformation to work in world space
        world_mx = obj.matrix_world
        inv_world_mx = world_mx.inverted()

        world_start_co = world_mx @ v_start.co
        world_end_co = world_mx @ v_end.co

        line_origin = world_start_co
        line_vector = world_end_co - line_origin
        
        # Check for a zero-length line to avoid division by zero
        if line_vector.length_squared < 1e-9:
            self.report({'WARNING'}, "First and last selected vertices are at the same position")
            return {'CANCELLED'}
            
        line_direction = line_vector.normalized()

        # Process all selected vertices
        for v in selected_verts:
            # Project the vertex's world position onto the line and convert back to local
            projected_world_co = line_origin + (world_mx @ v.co - line_origin).dot(line_direction) * line_direction
            target_local_co = inv_world_mx @ projected_world_co
            # Interpolate between original (current v.co) and target, then assign. This correctly handles Redo panel updates.
            v.co = v.co * (1.0 - self.factor) + target_local_co * self.factor

        bmesh.update_edit_mesh(me)
        return {'FINISHED'}


class ALEC_OT_make_coplanar(bpy.types.Operator):
    """Make selected vertices coplanar"""
    bl_idname = "alec.make_coplanar"
    bl_label = "Make Coplanar"
    bl_description = "Aligns selected vertices to a plane"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Mode",
        description="How to determine the alignment plane",
        items=[
            ('BEST_FIT', "Best Fit", "Use the three most defining vertices in the selection"),
            ('HISTORY', "Last Three Selected", "Use the last three vertices selected to define the plane")
        ],
        default='BEST_FIT'
    ) # type: ignore

    factor: bpy.props.FloatProperty(
        name="Factor",
        description="Influence of the operation",
        default=1.0,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == 'MESH' and
                context.mode == 'EDIT_MESH')

    def execute(self, context):
        obj = context.active_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        selected_verts = [v for v in bm.verts if v.select]

        if len(selected_verts) < 3:
            self.report({'WARNING'}, "Select at least 3 vertices")
            return {'CANCELLED'}

        plane_def_verts = []

        if self.mode == 'BEST_FIT':
            # --- Best Fit Logic (Farthest points heuristic) ---
            v_a, v_b = None, None
            max_dist_sq = -1.0
            for i in range(len(selected_verts)):
                for j in range(i + 1, len(selected_verts)):
                    dist_sq = (selected_verts[i].co - selected_verts[j].co).length_squared
                    if dist_sq > max_dist_sq:
                        max_dist_sq = dist_sq
                        v_a, v_b = selected_verts[i], selected_verts[j]

            v_c = None
            max_line_dist_sq = -1.0
            line_vec = v_b.co - v_a.co
            if line_vec.length_squared > 1e-9:
                for v in selected_verts:
                    if v == v_a or v == v_b: continue
                    dist_sq = (v.co - v_a.co).cross(line_vec).length_squared
                    if dist_sq > max_line_dist_sq:
                        max_line_dist_sq = dist_sq
                        v_c = v

            if not all([v_a, v_b, v_c]):
                self.report({'WARNING'}, "Could not define a plane from selection (are vertices collinear?)")
                return {'CANCELLED'}
            plane_def_verts = [v_a, v_b, v_c]

        elif self.mode == 'HISTORY':
            history = [elem for elem in bm.select_history if isinstance(elem, bmesh.types.BMVert)]
            if len(history) < 3:
                self.report({'WARNING'}, "For 'History' mode, select at least 3 vertices in order")
                return {'CANCELLED'}
            plane_def_verts = history[-3:]

        # --- Projection Logic (in World Space) ---
        world_mx = obj.matrix_world
        inv_world_mx = world_mx.inverted()

        p1_w, p2_w, p3_w = (world_mx @ v.co for v in plane_def_verts)
        plane_normal = (p2_w - p1_w).cross(p3_w - p1_w)

        if plane_normal.length_squared < 1e-9:
            self.report({'WARNING'}, "Defining vertices are collinear. Cannot create a plane.")
            return {'CANCELLED'}
        plane_normal.normalize()
        plane_point = p1_w

        for v in selected_verts:
            v_world_co = world_mx @ v.co
            dist = (v_world_co - plane_point).dot(plane_normal)
            projected_world_co = v_world_co - dist * plane_normal
            target_local_co = inv_world_mx @ projected_world_co
            # Interpolate between original (current v.co) and target, then assign. This correctly handles Redo panel updates.
            v.co = v.co * (1.0 - self.factor) + target_local_co * self.factor

        bmesh.update_edit_mesh(me)
        return {'FINISHED'}


class ALEC_OT_distribute_vertices(bpy.types.Operator):
    """Distribute selected vertices evenly between the two farthest points"""
    bl_idname = "alec.distribute_vertices"
    bl_label = "Distribute Vertices"
    bl_description = "Spaces selected vertices evenly along the line connecting the two most distant ones"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == 'MESH' and
                context.mode == 'EDIT_MESH')

    def execute(self, context):
        obj = context.active_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        selected_verts = [v for v in bm.verts if v.select]

        if len(selected_verts) < 3:
            self.report({'WARNING'}, "Select at least 3 vertices to distribute")
            return {'CANCELLED'}

        # 1. Find the two farthest vertices to serve as endpoints
        v_start, v_end = None, None
        max_dist_sq = -1.0
        for i in range(len(selected_verts)):
            for j in range(i + 1, len(selected_verts)):
                dist_sq = (selected_verts[i].co - selected_verts[j].co).length_squared
                if dist_sq > max_dist_sq:
                    max_dist_sq = dist_sq
                    v_start, v_end = selected_verts[i], selected_verts[j]
        
        if not v_start or not v_end:
            self.report({'ERROR'}, "Could not determine endpoints.")
            return {'CANCELLED'}

        # 2. Order all vertices by projecting them onto the line defined by the endpoints
        line_vec = v_end.co - v_start.co
        if line_vec.length_squared < 1e-9:
            self.report({'WARNING'}, "Endpoints are at the same location.")
            return {'CANCELLED'}
        line_dir = line_vec.normalized()

        projections = sorted([( (v.co - v_start.co).dot(line_dir), v ) for v in selected_verts])
        ordered_verts = [p[1] for p in projections]

        # 3. Distribute the vertices (in world space), keeping endpoints fixed
        world_mx = obj.matrix_world
        inv_world_mx = world_mx.inverted()
        start_pos_world = world_mx @ ordered_verts[0].co
        end_pos_world = world_mx @ ordered_verts[-1].co
        num_segments = len(ordered_verts) - 1

        for i in range(1, num_segments):
            fraction = i / num_segments
            ordered_verts[i].co = inv_world_mx @ start_pos_world.lerp(end_pos_world, fraction)

        bmesh.update_edit_mesh(me)
        return {'FINISHED'}

classes = [
    ALEC_OT_bbox_local,
    ALEC_OT_bbox_world,
    ALEC_OT_bbox_offset,
    ALEC_OT_align,
    ALEC_OT_quick_center,
    ALEC_OT_quick_pivot,
    ALEC_OT_cursor_to_selected,
    ALEC_OT_cursor_to_geometry_center,
    ALEC_OT_origin_to_cursor,
    ALEC_OT_group_manager,
    ALEC_OT_set_edge_length,
    ALEC_OT_menu_dispatcher,
    ALEC_OT_make_collinear,
    ALEC_OT_make_coplanar,
    ALEC_OT_distribute_vertices,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)