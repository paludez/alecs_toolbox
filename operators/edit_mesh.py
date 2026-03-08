# Operators for mesh editing in Edit Mode
import bpy
import bmesh
from ..modules import utils
from ..modules.modal_handler import ModalNumberInput, update_modal_header
from ..modules.utils import find_farthest_vertices

class ALEC_OT_set_edge_length(bpy.types.Operator):
    """Set the length of the selected edge interactively"""
    bl_idname = "alec.set_edge_length"
    bl_label = "Set Edge Length"
    bl_options = {'REGISTER', 'UNDO', 'GRAB_CURSOR', 'BLOCKING'}

    _active_instance = None

    @staticmethod
    def draw_status_bar(panel_self, context):
        self = ALEC_OT_set_edge_length._active_instance
        if not self:
            return

        layout = panel_self.layout
        row = layout.row(align=True)

        row.label(text="Anchor:")
        
        anchor_row = row.row(align=True)
        sub = anchor_row.row(align=True)
        sub.alert = self.anchor_mode == 'ACTIVE'
        sub.label(text="[A] Active")

        sub = anchor_row.row(align=True)
        sub.alert = self.anchor_mode == 'OTHER'
        sub.label(text="[B] Other")

        sub = anchor_row.row(align=True)
        sub.alert = self.anchor_mode == 'CENTER'
        sub.label(text="[C] Center")
        
        row.separator()
        row.label(text="Confirm: [LMB] | Cancel: [RMB]")

    def cleanup(self, context):
        ALEC_OT_set_edge_length._active_instance = None
        try:
            bpy.types.STATUSBAR_HT_header.remove(ALEC_OT_set_edge_length.draw_status_bar)
        except:
            pass # Fails if not found
        context.area.header_text_set(None)
        context.area.tag_redraw()

    def update_header_text(self, context):
        unit_setting = context.scene.unit_settings.length_unit
        unit_suffixes = {
            'METERS': 'm', 'CENTIMETERS': 'cm', 'MILLIMETERS': 'mm', 'KILOMETERS': 'km',
            'MICROMETERS': 'μm', 'FEET': "'", 'INCHES': '"', 'MILES': 'mi', 'THOU': 'thou'
        }
        suffix = unit_suffixes.get(unit_setting, '')

        len_val = self.current_length * self.unit_scale_display_inv
        
        secondary = ""
        if not self.number_input.has_value():
            init_len_val = self.initial_length * self.unit_scale_display_inv
            secondary = f"Initial: {init_len_val:.4f}{suffix}"

        update_modal_header(context, "Length", len_val, self.number_input.value_str, suffix, secondary_text=secondary)

    def _get_active_edge(self, bm):
        active_edge = bm.select_history.active
        if isinstance(active_edge, bmesh.types.BMEdge):
            return active_edge
        
        selected_edges = [e for e in bm.edges if e.select]
        if selected_edges:
            return selected_edges[-1]
            
        return None

    def apply_length(self):
        world_direction = self.world_direction
        
        if self.anchor_mode == 'ACTIVE':
            stationary_co = self.world_mx @ self.active_vert.co
            moved_co = self.world_mx @ self.other_vert.co
            new_moved_co = stationary_co + world_direction * self.current_length
            self.other_vert.co = self.inv_world_mx @ new_moved_co
        elif self.anchor_mode == 'OTHER':
            stationary_co = self.world_mx @ self.other_vert.co
            moved_co = self.world_mx @ self.active_vert.co
            new_moved_co = stationary_co - world_direction * self.current_length
            self.active_vert.co = self.inv_world_mx @ new_moved_co
        elif self.anchor_mode == 'CENTER':
            world_center_point = (self.world_mx @ self.v1.co + self.world_mx @ self.v2.co) / 2
            half_length = self.current_length / 2
            self.v1.co = self.inv_world_mx @ (world_center_point - world_direction * half_length)
            self.v2.co = self.inv_world_mx @ (world_center_point + world_direction * half_length)

        bmesh.update_edit_mesh(self.me)

    def invoke(self, context, event):
        self.obj = context.active_object
        self.me = self.obj.data
        self.bm = bmesh.from_edit_mesh(self.me)

        self.edge = self._get_active_edge(self.bm)
        if not self.edge:
            self.report({'WARNING'}, "No edge selected")
            return {'CANCELLED'}
        
        self.v1, self.v2 = self.edge.verts
        self.initial_v1_co = self.v1.co.copy()
        self.initial_v2_co = self.v2.co.copy()

        # Matrices
        self.world_mx = self.obj.matrix_world
        self.inv_world_mx = self.world_mx.inverted()
        
        # Determine edge direction
        world_v1_co = self.world_mx @ self.v1.co
        world_v2_co = self.world_mx @ self.v2.co
        direction_vector = world_v2_co - world_v1_co
        if direction_vector.length_squared < 1e-9:
            self.report({'WARNING'}, "Edge has zero length, cannot determine direction.")
            return {'CANCELLED'}
        self.world_direction = direction_vector.normalized()
        
        # Determine active/other verts
        active_vert_hist = self.bm.select_history.active
        if not isinstance(active_vert_hist, bmesh.types.BMVert) or active_vert_hist not in self.edge.verts:
            self.active_vert = self.v1
        else:
            self.active_vert = active_vert_hist
        
        self.other_vert = self.v2 if self.active_vert == self.v1 else self.v1
        
        # State
        self.initial_length = direction_vector.length
        self.current_length = self.initial_length
        self.anchor_mode = 'ACTIVE'
        self.number_input = ModalNumberInput()
        self.unit_scale = utils.get_unit_scale(context)
        self.unit_scale_display_inv = 1.0 / self.unit_scale if self.unit_scale != 0 else 1.0
        
        # Mouse state
        self.initial_mouse_x = event.mouse_x
        
        ALEC_OT_set_edge_length._active_instance = self
        bpy.types.STATUSBAR_HT_header.prepend(ALEC_OT_set_edge_length.draw_status_bar)
        context.window_manager.modal_handler_add(self)
        self.update_header_text(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        context.area.tag_redraw()

        # --- Finish or Cancel ---
        if event.type in {'LEFTMOUSE', 'ENTER'}:
            self.cleanup(context)
            return {'FINISHED'}

        if event.type in {'RIGHTMOUSE', 'ESC'}:
            # Restore initial state
            self.v1.co = self.initial_v1_co
            self.v2.co = self.initial_v2_co
            bmesh.update_edit_mesh(self.me)
            self.cleanup(context)
            return {'CANCELLED'}
        
        # --- Handle modal events ---
        if self.number_input.handle_event(event):
            pass # Handled by number input
        
        elif event.type == 'MOUSEMOVE':
            self.number_input.reset()
            delta_x = event.mouse_x - self.initial_mouse_x
            sens = 0.01 * (1.0 if not event.shift else 0.1)
            self.current_length = max(0.0, self.initial_length + delta_x * sens)
            self.apply_length()
        
        # Anchor mode change
        elif event.type in {'A', 'B', 'C'} and event.value == 'PRESS':
            # Reset vertices to initial positions
            self.v1.co = self.initial_v1_co
            self.v2.co = self.initial_v2_co
            
            # Reset current length to initial length
            self.current_length = self.initial_length
            
            # Reset mouse reference to prevent jumping on next mouse move
            self.initial_mouse_x = event.mouse_x
            
            # Reset numeric input
            self.number_input.reset()

            if event.type == 'A':
                self.anchor_mode = 'ACTIVE'
            elif event.type == 'B':
                self.anchor_mode = 'OTHER'
            elif event.type == 'C':
                self.anchor_mode = 'CENTER'
            
            # Update the mesh to show the reset state
            bmesh.update_edit_mesh(self.me)

        # Apply typed value if it exists
        if self.number_input.has_value():
            try:
                typed_val = self.number_input.get_value()
                self.current_length = abs(typed_val * self.unit_scale)
                self.apply_length()
            except ValueError:
                pass # Ignore errors from partial input like "-"
        
        self.update_header_text(context)
        return {'RUNNING_MODAL'}


class ALEC_OT_make_collinear(bpy.types.Operator):
    """Makes selected vertices collinear"""
    bl_idname = "alec.make_collinear"
    bl_label = "Make Collinear"
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

        selected_verts = [v for v in bm.verts if v.select]
        v_start, v_end = None, None

        if self.mode == 'FARTHEST':
            if len(selected_verts) < 2:
                self.report({'WARNING'}, "Select at least 2 vertices")
                return {'CANCELLED'}
            v_start, v_end = find_farthest_vertices(selected_verts)

        elif self.mode == 'HISTORY':
            history = [elem for elem in bm.select_history if isinstance(elem, bmesh.types.BMVert)]
            if len(history) < 2:
                self.report({'WARNING'}, "For 'Last Two Selected' mode, select at least 2 vertices in order")
                return {'CANCELLED'}
            v_start = history[-2]
            v_end = history[-1]

        if not v_start or not v_end:
            self.report({'WARNING'}, "Could not determine line endpoints")
            return {'CANCELLED'}

        world_mx = obj.matrix_world
        inv_world_mx = world_mx.inverted()

        world_start_co = world_mx @ v_start.co
        world_end_co = world_mx @ v_end.co

        line_origin = world_start_co
        line_vector = world_end_co - line_origin
        
        if line_vector.length_squared < 1e-9:
            self.report({'WARNING'}, "First and last selected vertices are at the same position")
            return {'CANCELLED'}
            
        line_direction = line_vector.normalized()

        for v in selected_verts:
            projected_world_co = line_origin + (world_mx @ v.co - line_origin).dot(line_direction) * line_direction
            target_local_co = inv_world_mx @ projected_world_co
            v.co = v.co * (1.0 - self.factor) + target_local_co * self.factor

        bmesh.update_edit_mesh(me)
        return {'FINISHED'}


class ALEC_OT_make_coplanar(bpy.types.Operator):
    """Makes selected vertices coplanar"""
    bl_idname = "alec.make_coplanar"
    bl_label = "Make Coplanar"
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
            v.co = v.co * (1.0 - self.factor) + target_local_co * self.factor

        bmesh.update_edit_mesh(me)
        return {'FINISHED'}


class ALEC_OT_distribute_vertices(bpy.types.Operator):
    """Spaces selected vertices evenly along the line connecting the two most distant ones"""
    bl_idname = "alec.distribute_vertices"
    bl_label = "Distribute Vertices"
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

        v_start, v_end = find_farthest_vertices(selected_verts)
        
        if not v_start or not v_end:
            self.report({'ERROR'}, "Could not determine endpoints.")
            return {'CANCELLED'}

        line_vec = v_end.co - v_start.co
        if line_vec.length_squared < 1e-9:
            self.report({'WARNING'}, "Endpoints are at the same location.")
            return {'CANCELLED'}
        line_dir = line_vec.normalized()

        projections = sorted([( (v.co - v_start.co).dot(line_dir), v ) for v in selected_verts])
        ordered_verts = [p[1] for p in projections]

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
    ALEC_OT_set_edge_length,
    ALEC_OT_make_collinear,
    ALEC_OT_make_coplanar,
    ALEC_OT_distribute_vertices,
]
