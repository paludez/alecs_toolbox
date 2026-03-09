# Operators for mesh editing in Edit Mode
import bpy
import bmesh
import blf
from bpy_extras.view3d_utils import location_3d_to_region_2d
import math
from mathutils import Matrix, Vector, geometry
from ..modules.modal_handler import ModalNumberInput, update_modal_header
from ..modules.utils import find_farthest_vertices, unit_suffixes, draw_modal_status_bar, get_unit_scale

_draw_handler = None
_draw_data = {}

def depsgraph_update_handler(scene):
    """Clear draw data if Edit Mode is exited or target object is invalid."""
    global _draw_handler, _draw_data
    if not _draw_data:
        return

    should_clear = False
    
    # 1. Check Mode: If not in Edit Mode, wipe everything.
    if bpy.context.mode != 'EDIT_MESH':
        should_clear = True
    else:
        # 2. Check Object Validity
        obj_name = _draw_data.get('object_name')
        mesh_name = _draw_data.get('mesh_name')
        obj = bpy.data.objects.get(obj_name) if obj_name else None
        
        if not obj or not mesh_name or obj.data.name != mesh_name:
            should_clear = True

    if should_clear:
        if _draw_handler:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, 'WINDOW')
            except ValueError:
                pass # Already removed
            _draw_handler = None
        _draw_data.clear()
        
        # Force redraw to remove text from all views
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

def unregister_draw_handler():
    """Force remove the draw handler when unregistering the addon."""
    global _draw_handler
    if _draw_handler:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, 'WINDOW')
        except ValueError:
            pass # Already removed
        _draw_handler = None

def draw_callback_px(context):
    """Draw handler to display edge lengths in the 3D View."""
    if context.mode != 'EDIT_MESH' or not context.edit_object:
        return

    obj = context.edit_object
    # Ensure we are drawing for the correct object and mesh datablock
    if not _draw_data or obj.name != _draw_data.get('object_name') or obj.data.name != _draw_data.get('mesh_name'):
        return

    bm = bmesh.from_edit_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    
    edge_indices = _draw_data.get('edge_indices', [])
    if not edge_indices:
        return

    world_mx = obj.matrix_world
    region = context.region
    region_3d = context.space_data.region_3d
    
    font_id = 0  # Default font
    font_size = 12
    blf.size(font_id, font_size)
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0) # White text
    blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 0.8) # Black shadow

    for idx in edge_indices:
        if idx >= len(bm.edges):
            continue
        edge = bm.edges[idx]
        
        v1_world = world_mx @ edge.verts[0].co
        v2_world = world_mx @ edge.verts[1].co
        
        length = (v1_world - v2_world).length
        mid_point_world = (v1_world + v2_world) / 2.0
        
        pos_2d = location_3d_to_region_2d(region, region_3d, mid_point_world)
        if pos_2d:
            display_length = length * _draw_data.get('unit_inv', 1.0)
            text = f"{display_length:.4f}{_draw_data.get('suffix', '')}"
            blf.position(font_id, pos_2d.x - blf.dimensions(font_id, text)[0] / 2, pos_2d.y, 0)
            blf.draw(font_id, text)

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

        items = [
            ("Anchor", "[A] Active", self.anchor_mode == 'ACTIVE'),
            ("", "[B] Other", self.anchor_mode == 'OTHER'),
            ("", "[C] Center", self.anchor_mode == 'CENTER'),
            None, # Separator
            ("Confirm", "[LMB]"),
            ("Cancel", "[RMB]"),
        ]
        draw_modal_status_bar(panel_self.layout, items)

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
        suffix = unit_suffixes.get(unit_setting, '')

        len_val = self.current_length * self.unit_scale_display_inv
        init_len_val = self.initial_length * self.unit_scale_display_inv
        
        secondary = ""
        if not self.number_input.has_value():
            formatted_init = f"{init_len_val:.4f}".rstrip('0').rstrip('.')
            if formatted_init == '-0': formatted_init = '0'
            secondary = f"Initial: {formatted_init}{suffix}"

        update_modal_header(context, "Length", len_val, self.number_input.value_str, suffix, secondary_text=secondary, initial_value=init_len_val)

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
        
        if self.anchor_mode == 'CENTER':
            world_center_point = (self.world_mx @ self.v1.co + self.world_mx @ self.v2.co) / 2
            half_length = self.current_length / 2
            self.v1.co = self.inv_world_mx @ (world_center_point - world_direction * half_length)
            self.v2.co = self.inv_world_mx @ (world_center_point + world_direction * half_length)
        else:
            # Determine stationary and moved vertices based on mode
            if self.anchor_mode == 'ACTIVE':
                stationary_vert, moved_vert = self.active_vert, self.other_vert
            else: # OTHER
                stationary_vert, moved_vert = self.other_vert, self.active_vert

            stationary_co = self.world_mx @ stationary_vert.co
            
            # Direction is v1 -> v2. If stationary is v1, we add. If stationary is v2, we subtract.
            sign = 1.0 if stationary_vert == self.v1 else -1.0
            
            new_moved_co = stationary_co + (world_direction * sign) * self.current_length
            moved_vert.co = self.inv_world_mx @ new_moved_co

        bmesh.update_edit_mesh(self.me)

    def invoke(self, context, event):
        self.obj = context.active_object
        self.me = self.obj.data
        self.bm = bmesh.from_edit_mesh(self.me)

        # Try to get an edge first, otherwise check for 2 vertices
        self.edge = self._get_active_edge(self.bm)
        
        if self.edge:
            self.v1, self.v2 = self.edge.verts
        else:
            selected_verts = [v for v in self.bm.verts if v.select]
            if len(selected_verts) == 2:
                self.v1, self.v2 = selected_verts
            else:
                self.report({'WARNING'}, "Select an edge or exactly 2 vertices")
                return {'CANCELLED'}

        self.initial_v1_co = self.v1.co.copy()
        self.initial_v2_co = self.v2.co.copy()

        # Matrices
        self.world_mx = self.obj.matrix_world
        self.inv_world_mx = self.world_mx.inverted()
        
        # Determine direction
        world_v1_co = self.world_mx @ self.v1.co
        world_v2_co = self.world_mx @ self.v2.co
        direction_vector = world_v2_co - world_v1_co
        if direction_vector.length_squared < 1e-9:
            self.report({'WARNING'}, "Distance is zero, cannot determine direction.")
            return {'CANCELLED'}
        self.world_direction = direction_vector.normalized()
        
        # Determine active/other verts
        active_vert_hist = self.bm.select_history.active
        if isinstance(active_vert_hist, bmesh.types.BMVert) and active_vert_hist in (self.v1, self.v2):
            self.active_vert = active_vert_hist
        else:
            self.active_vert = self.v1
        
        self.other_vert = self.v2 if self.active_vert == self.v1 else self.v1
        
        # State
        self.initial_length = direction_vector.length
        self.current_length = self.initial_length
        self.anchor_mode = 'ACTIVE'
        self.number_input = ModalNumberInput()
        self.unit_scale = get_unit_scale(context)
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
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'}:
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
                typed_val = self.number_input.get_value(initial_value=self.initial_length * self.unit_scale_display_inv)
                self.current_length = abs(typed_val * self.unit_scale)
                self.apply_length()
            except ValueError:
                pass # Ignore errors from partial input like "-"
        
        self.update_header_text(context)
        return {'RUNNING_MODAL'}

class ALEC_OT_dimension_action(bpy.types.Operator):
    """Manage Edge Dimensions: Add, Remove, Clear"""
    bl_idname = "alec.dimension_action"
    bl_label = "Dimension Action"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(
        items=[
            ('ADD', "Add Selected", "Add dimensions to selected edges"),
            ('REMOVE', "Remove Selected", "Remove dimensions from selected edges"),
            ('CLEAR', "Clear All", "Clear all dimensions"),
        ]
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def _update_handler(self, context, has_items):
        global _draw_handler
        if has_items and not _draw_handler:
            _draw_handler = bpy.types.SpaceView3D.draw_handler_add(draw_callback_px, (context,), 'WINDOW', 'POST_PIXEL')
        elif not has_items and _draw_handler:
            bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, 'WINDOW')
            _draw_handler = None

    def execute(self, context):
        global _draw_data
        
        # Aggressive Clear: Wipe everything and stop handler immediately
        if self.action == 'CLEAR':
            _draw_data.clear()
            self._update_handler(context, False)
            self.report({'INFO'}, "All dimensions cleared")
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            return {'FINISHED'}

        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        
        # Reset data if we switched objects
        if _draw_data.get('object_name') != obj.name or _draw_data.get('mesh_name') != obj.data.name:
            _draw_data.clear()
            _draw_data['object_name'] = obj.name
            _draw_data['mesh_name'] = obj.data.name
            _draw_data['edge_indices'] = []

        # Update unit settings (in case they changed)
        unit_scale = get_unit_scale(context)
        unit_setting = context.scene.unit_settings.length_unit
        _draw_data['unit_inv'] = 1.0 / unit_scale if unit_scale != 0 else 1.0
        _draw_data['suffix'] = unit_suffixes.get(unit_setting, '')

        current_indices = set(_draw_data.get('edge_indices', []))
        selected_indices = set(e.index for e in bm.edges if e.select)

        if self.action == 'ADD':
            if not selected_indices:
                self.report({'WARNING'}, "Select edges first")
                return {'CANCELLED'}
            current_indices.update(selected_indices)
            self.report({'INFO'}, f"Dimensions added")

        elif self.action == 'REMOVE':
            if not selected_indices:
                self.report({'WARNING'}, "Select edges first")
                return {'CANCELLED'}
            current_indices.difference_update(selected_indices)
            self.report({'INFO'}, f"Dimensions removed")

        # Save back to global data
        _draw_data['edge_indices'] = list(current_indices)
        
        # Manage the draw handler
        self._update_handler(context, bool(current_indices))

        # Redraw all 3D views to show/hide the text immediately
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}

class ALEC_OT_select_dimension_edges(bpy.types.Operator):
    """Select edges that currently have dimensions displayed"""
    bl_idname = "alec.select_dimension_edges"
    bl_label = "Select Dimension Edges"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        obj = context.edit_object
        if not _draw_data or obj.name != _draw_data.get('object_name') or obj.data.name != _draw_data.get('mesh_name'):
            self.report({'WARNING'}, "No dimensions displayed for this object")
            return {'CANCELLED'}
        
        indices = _draw_data.get('edge_indices', [])
        if not indices:
            return {'CANCELLED'}

        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        
        # Deselect all first
        for e in bm.edges: e.select = False
        for v in bm.verts: v.select = False
        for f in bm.faces: f.select = False
            
        for idx in indices:
            if idx < len(bm.edges):
                bm.edges[idx].select = True
                # Ensure vertices are selected so the edge selection persists
                bm.edges[idx].verts[0].select = True
                bm.edges[idx].verts[1].select = True
        
        bm.select_flush(True)
        bmesh.update_edit_mesh(obj.data)
        return {'FINISHED'}

class ALEC_OT_set_edge_angle(bpy.types.Operator):
    """Set the angle between two edges by rotating the selection"""
    bl_idname = "alec.set_edge_angle"
    bl_label = "Set Edge Angle"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING', 'GRAB_CURSOR'}

    angle: bpy.props.FloatProperty(
        name="Angle", subtype='ANGLE', default=math.pi / 2.0,
        description="The target angle between the edges"
    ) # type: ignore

    run_modal: bpy.props.BoolProperty(
        name="Interactive", default=False,
        description="Run in interactive modal mode"
    ) # type: ignore

    _active_instance = None
    _initial_state = {}
    _bm = None
    _obj = None
    _pivot_vert_co = None
    _rot_axis = None
    _stationary_vec = None
    _verts_to_transform_indices = []
    _initial_angle = 0.0
    _current_angle = 0.0

    @staticmethod
    def draw_status_bar(panel_self, context):
        self = ALEC_OT_set_edge_angle._active_instance
        if not self: return
        items = [("Confirm", "[LMB]"), ("Cancel", "[RMB]")]
        draw_modal_status_bar(panel_self.layout, items)

    def cleanup(self, context):
        ALEC_OT_set_edge_angle._active_instance = None
        try:
            bpy.types.STATUSBAR_HT_header.remove(ALEC_OT_set_edge_angle.draw_status_bar)
        except: pass
        context.area.header_text_set(None)
        context.area.tag_redraw()

    def update_header_text(self, context):
        angle_deg = math.degrees(self._current_angle)
        init_angle_deg = math.degrees(self._initial_angle)
        secondary = ""
        if not self.number_input.has_value():
            formatted_init = f"{init_angle_deg:.2f}".rstrip('0').rstrip('.')
            if formatted_init == '-0': formatted_init = '0'
            secondary = f"Initial: {formatted_init}°"
        update_modal_header(context, "Angle", angle_deg, self.number_input.value_str, "°", secondary_text=secondary, initial_value=init_angle_deg, precision=2)

    @classmethod
    def poll(cls, context):
        if not (context.active_object and context.mode == 'EDIT_MESH'):
            return False
        try:
            bm = bmesh.from_edit_mesh(context.active_object.data)
            history = [elem for elem in bm.select_history if isinstance(elem, bmesh.types.BMEdge)]
            return len(history) >= 2
        except:
            return False

    def _get_op_data(self, context):
        self._obj = context.active_object
        self._bm = bmesh.from_edit_mesh(self._obj.data)
        self._bm.select_flush(False)

        history = [elem for elem in self._bm.select_history if isinstance(elem, bmesh.types.BMEdge)]
        if len(history) < 2:
            self.report({'WARNING'}, "Select two edges in order (last one is stationary)")
            return False

        stationary_edge, moving_edge = history[-1], history[-2]
        common_verts = set(stationary_edge.verts) & set(moving_edge.verts)
        if not common_verts:
            self.report({'WARNING'}, "Edges must share a common vertex")
            return False
        pivot_vert = common_verts.pop()
        self._pivot_vert_co = pivot_vert.co.copy()

        v_stat = [v for v in stationary_edge.verts if v != pivot_vert][0]
        v_mov = [v for v in moving_edge.verts if v != pivot_vert][0]
        self._stationary_vec = (v_stat.co - self._pivot_vert_co).normalized()
        moving_vec = (v_mov.co - self._pivot_vert_co).normalized()

        self._rot_axis = self._stationary_vec.cross(moving_vec)
        if self._rot_axis.length < 1e-6:
            self.report({'WARNING'}, "Edges are collinear, cannot determine rotation axis")
            return False
        self._rot_axis.normalize()

        self._initial_angle = self._stationary_vec.angle(moving_vec)
        self._current_angle = self._initial_angle

        stationary_verts_indices = {v.index for v in stationary_edge.verts}
        self._verts_to_transform_indices = [v.index for v in self._bm.verts if v.select and v.index not in stationary_verts_indices]
        self._bm.verts.ensure_lookup_table()
        self._initial_state = {idx: self._bm.verts[idx].co.copy() for idx in self._verts_to_transform_indices}
        return True

    def _apply_rotation(self, target_angle):
        angle_delta = target_angle - self._initial_angle
        rot_mat = Matrix.Rotation(angle_delta, 4, self._rot_axis)
        T = Matrix.Translation(self._pivot_vert_co)
        transform_mat = T @ rot_mat @ T.inverted()

        self._bm.verts.ensure_lookup_table()
        for v_idx in self._verts_to_transform_indices:
            v = self._bm.verts[v_idx]
            v.co = transform_mat @ self._initial_state[v_idx]
        bmesh.update_edit_mesh(self._obj.data)

    def execute(self, context):
        if not self._get_op_data(context): return {'CANCELLED'}
        self._apply_rotation(self.angle)
        return {'FINISHED'}

    def invoke(self, context, event):
        if not self.run_modal: return self.execute(context)
        if not self._get_op_data(context): return {'CANCELLED'}

        self.number_input = ModalNumberInput()
        self.initial_mouse_x = event.mouse_x
        ALEC_OT_set_edge_angle._active_instance = self
        bpy.types.STATUSBAR_HT_header.prepend(ALEC_OT_set_edge_angle.draw_status_bar)
        context.window_manager.modal_handler_add(self)
        self.update_header_text(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        context.area.tag_redraw()
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'}:
            self.cleanup(context)
            return {'FINISHED'}
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self._apply_rotation(self._initial_angle)
            self.cleanup(context)
            return {'CANCELLED'}
        if self.number_input.handle_event(event): pass
        elif event.type == 'MOUSEMOVE':
            self.number_input.reset()
            delta_x = event.mouse_x - self.initial_mouse_x
            sens = 0.005 * (0.1 if event.shift else 1.0)
            self._current_angle = self._initial_angle + delta_x * sens
            self._apply_rotation(self._current_angle)
        if self.number_input.has_value():
            try: self._current_angle = math.radians(self.number_input.get_value(initial_value=math.degrees(self._initial_angle)))
            except ValueError: pass
            self._apply_rotation(self._current_angle)
        self.update_header_text(context)
        return {'RUNNING_MODAL'}

class ALEC_OT_distribute_vertices(bpy.types.Operator):
    """Distributes selected vertices evenly along the existing path"""
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
            self.report({'WARNING'}, "Select at least 3 vertices forming a chain")
            return {'CANCELLED'}

        # Build adjacency list for selected vertices based on selected edges
        adj = {v: [] for v in selected_verts}
        for edge in bm.edges:
            if edge.select and edge.verts[0] in selected_verts and edge.verts[1] in selected_verts:
                adj[edge.verts[0]].append(edge.verts[1])
                adj[edge.verts[1]].append(edge.verts[0])

        # Find endpoints (vertices with only one connection in the selection)
        endpoints = [v for v, neighbors in adj.items() if len(neighbors) == 1]
        
        if len(endpoints) != 2:
            self.report({'WARNING'}, "Selection must form a single, unbranched chain of edges.")
            return {'CANCELLED'}

        # Order the vertices from one endpoint to the other
        ordered_chain = []
        current_vert = endpoints[0]
        prev_vert = None
        
        while current_vert:
            ordered_chain.append(current_vert)
            if len(ordered_chain) > len(selected_verts): # Failsafe for loops
                 self.report({'WARNING'}, "Selection seems to contain a loop. Operation aborted.")
                 return {'CANCELLED'}
            
            neighbors = adj.get(current_vert, [])
            next_vert = None
            for v in neighbors:
                if v != prev_vert:
                    next_vert = v
                    break
            
            prev_vert = current_vert
            current_vert = next_vert

        if len(ordered_chain) != len(selected_verts):
            self.report({'WARNING'}, "Selection contains disconnected parts. Select a continuous chain.")
            return {'CANCELLED'}

        # Store original coordinates to avoid reading modified values during update
        original_coords = [v.co.copy() for v in ordered_chain]

        # Calculate cumulative distances along the chain
        distances = [0.0]
        total_length = 0.0
        for i in range(len(ordered_chain) - 1):
            p1 = original_coords[i]
            p2 = original_coords[i+1]
            segment_length = (p2 - p1).length
            total_length += segment_length
            distances.append(total_length)

        if total_length < 1e-6:
            self.report({'INFO'}, "Chain has zero length, nothing to do.")
            return {'CANCELLED'}

        # Reposition intermediate vertices
        num_segments = len(ordered_chain) - 1
        equal_segment_length = total_length / num_segments
        
        for i in range(1, num_segments): # Iterate over intermediate vertices
            target_dist = i * equal_segment_length
            
            # Find which original segment this target distance falls into
            current_segment_idx = next((j for j, d in enumerate(distances) if d >= target_dist), len(distances) - 2)
            if distances[current_segment_idx] > target_dist:
                current_segment_idx -= 1

            # Interpolate position within that segment
            p_start = original_coords[current_segment_idx]
            p_end = original_coords[current_segment_idx + 1]
            
            original_segment_len = (p_end - p_start).length
            
            if original_segment_len > 1e-9:
                dist_into_segment = target_dist - distances[current_segment_idx]
                interpolation_factor = dist_into_segment / original_segment_len
                new_pos = p_start.lerp(p_end, interpolation_factor)
                ordered_chain[i].co = new_pos

        bmesh.update_edit_mesh(me)
        return {'FINISHED'}

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

    distribute: bpy.props.BoolProperty(
        name="Distribute",
        description="Evenly distribute vertices along the line",
        default=False
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

        # Calculate projections for all selected vertices
        # List of tuples: (distance_along_line, vertex)
        projections = []
        for v in selected_verts:
            vec = world_mx @ v.co - line_origin
            dist = vec.dot(line_direction)
            projections.append((dist, v))

        if self.distribute and len(projections) > 1:
            projections.sort(key=lambda x: x[0])
            start_dist = projections[0][0]
            end_dist = projections[-1][0]
            total_len = end_dist - start_dist
            
            for i, (dist, v) in enumerate(projections):
                fraction = i / (len(projections) - 1)
                target_dist = start_dist + total_len * fraction
                target_world_co = line_origin + line_direction * target_dist
                target_local_co = inv_world_mx @ target_world_co
                v.co = v.co * (1.0 - self.factor) + target_local_co * self.factor
        else:
            for dist, v in projections:
                target_world_co = line_origin + line_direction * dist
                target_local_co = inv_world_mx @ target_world_co
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

class ALEC_OT_make_circle(bpy.types.Operator):
    """Flatten selected vertices into a perfect circle"""
    bl_idname = "alec.make_circle"
    bl_label = "Make Circle"
    bl_options = {'REGISTER', 'UNDO'}

    radius: bpy.props.FloatProperty(
        name="Radius",
        default=1.0,
        min=0.0,
        unit='LENGTH'
    ) # type: ignore

    influence: bpy.props.FloatProperty(
        name="Influence", 
        default=1.0, 
        min=0.0, 
        max=1.0,
        subtype='FACTOR'
    ) # type: ignore
    
    regular: bpy.props.BoolProperty(
        name="Regular", 
        default=True, 
        description="Distribute vertices evenly along the circle"
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == 'MESH' and
                context.mode == 'EDIT_MESH')

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "radius")
        
        layout.prop(self, "influence")
        layout.prop(self, "regular")

    def _get_target_verts(self, bm, context):
        # If Face Mode is active, try to get boundary vertices
        if context.tool_settings.mesh_select_mode[2]:
            selected_faces = [f for f in bm.faces if f.select]
            if selected_faces:
                boundary_verts = set()
                for f in selected_faces:
                    for e in f.edges:
                        # Boundary edge has exactly one selected face linked
                        if sum(1 for lf in e.link_faces if lf.select) == 1:
                            boundary_verts.add(e.verts[0])
                            boundary_verts.add(e.verts[1])
                if boundary_verts:
                    return list(boundary_verts)
        
        # Fallback: return all selected vertices
        return [v for v in bm.verts if v.select]

    def invoke(self, context, event):
        # Pre-calculate radius so the slider starts at a logical value
        obj = context.active_object
        if obj and obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            sel_verts = self._get_target_verts(bm, context)
            if len(sel_verts) >= 3:
                center = Vector((0,0,0))
                for v in sel_verts: center += v.co
                center /= len(sel_verts)
                
                # Calculate max radius (Best Fit) to initialize the slider
                max_dist_sq = max(((v.co - center).length_squared for v in sel_verts), default=1.0)
                self.radius = math.sqrt(max_dist_sq)
        
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        selected_verts = self._get_target_verts(bm, context)

        if len(selected_verts) < 3:
            self.report({'WARNING'}, "Select at least 3 vertices (or a face selection boundary)")
            return {'CANCELLED'}

        # 1. Calculate Center
        center = Vector((0,0,0))
        for v in selected_verts: 
            center += v.co
        center /= len(selected_verts)

        # 2. Calculate Plane (Best Fit)
        try:
            normal = geometry.normal([v.co for v in selected_verts])
        except:
            normal = Vector((0,0,1))
        
        if normal.length_squared < 1e-6:
             normal = Vector((0,0,1))

        # Create basis vectors for the plane
        tangent = normal.orthogonal()
        bitangent = normal.cross(tangent)

        # --- Align Orientation to Geometry & Calculate Radius ---
        # Find vertex farthest from center to align the circle start point
        # This prevents the circle from shrinking (uses max radius) and prevents rotation
        max_dist_sq = 0.0
        farthest_v = None
        
        for v in selected_verts:
            d_sq = (v.co - center).length_squared
            if d_sq > max_dist_sq:
                max_dist_sq = d_sq
                farthest_v = v
        
        # Align basis so the farthest vertex is at angle 0 (on the Tangent axis)
        if farthest_v:
            vec = farthest_v.co - center
            vec = vec - vec.dot(normal) * normal # Project to plane
            if vec.length_squared > 1e-6:
                # Current angle of the farthest vertex
                angle = math.atan2(vec.dot(bitangent), vec.dot(tangent))
                # Rotate basis so this vertex aligns with 0 degrees
                rot_angle = angle
                
                rot_mat = Matrix.Rotation(rot_angle, 3, normal)
                tangent = rot_mat @ tangent
                bitangent = rot_mat @ bitangent

        target_radius = self.radius

        # 4. Project and Position
        if self.regular:
            # Project to 2D plane defined by (tangent, bitangent) to get angles
            vert_angles = []
            for v in selected_verts:
                vec = v.co - center
                x = vec.dot(tangent)
                y = vec.dot(bitangent)
                angle = math.atan2(y, x)
                vert_angles.append((v, angle))
            
            # Sort by angle to ensure sequential ordering around the circle
            vert_angles.sort(key=lambda x: x[1])
            
            start_angle = vert_angles[0][1]
            step = (2 * math.pi) / len(selected_verts)

            for i, (v, _) in enumerate(vert_angles):
                theta = start_angle + i * step
                circle_pos = center + (tangent * math.cos(theta) + bitangent * math.sin(theta)) * target_radius
                v.co = v.co.lerp(circle_pos, self.influence)
        else:
            for v in selected_verts:
                vec = v.co - center
                dist_from_plane = vec.dot(normal)
                vec_on_plane = vec - (normal * dist_from_plane)
                
                if vec_on_plane.length_squared > 1e-6:
                    vec_on_plane.normalize()
                    circle_pos = center + vec_on_plane * target_radius
                    v.co = v.co.lerp(circle_pos, self.influence)

        bmesh.update_edit_mesh(me)
        return {'FINISHED'}

class ALEC_OT_make_square(bpy.types.Operator):
    """Flatten selected vertices into a perfect square"""
    bl_idname = "alec.make_square"
    bl_label = "Make Square"
    bl_options = {'REGISTER', 'UNDO'}

    radius: bpy.props.FloatProperty(
        name="Radius",
        default=1.0,
        min=0.0,
        unit='LENGTH'
    ) # type: ignore

    influence: bpy.props.FloatProperty(
        name="Influence", 
        default=1.0, 
        min=0.0, 
        max=1.0,
        subtype='FACTOR'
    ) # type: ignore
    
    regular: bpy.props.BoolProperty(
        name="Regular", 
        default=True, 
        description="Distribute vertices evenly along the square"
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == 'MESH' and
                context.mode == 'EDIT_MESH')

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "radius")
        layout.prop(self, "influence")
        layout.prop(self, "regular")

    def _get_target_verts(self, bm, context):
        # If Face Mode is active, try to get boundary vertices
        if context.tool_settings.mesh_select_mode[2]:
            selected_faces = [f for f in bm.faces if f.select]
            if selected_faces:
                boundary_verts = set()
                for f in selected_faces:
                    for e in f.edges:
                        # Boundary edge has exactly one selected face linked
                        if sum(1 for lf in e.link_faces if lf.select) == 1:
                            boundary_verts.add(e.verts[0])
                            boundary_verts.add(e.verts[1])
                if boundary_verts:
                    return list(boundary_verts)
        
        # Fallback: return all selected vertices
        return [v for v in bm.verts if v.select]

    def invoke(self, context, event):
        # Pre-calculate radius so the slider starts at a logical value
        obj = context.active_object
        if obj and obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            sel_verts = self._get_target_verts(bm, context)
            if len(sel_verts) >= 3:
                center = Vector((0,0,0))
                for v in sel_verts: center += v.co
                center /= len(sel_verts)
                
                # Calculate max radius (Best Fit) to initialize the slider
                max_dist_sq = max(((v.co - center).length_squared for v in sel_verts), default=1.0)
                self.radius = math.sqrt(max_dist_sq)
        
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        selected_verts = self._get_target_verts(bm, context)

        if len(selected_verts) < 3:
            self.report({'WARNING'}, "Select at least 3 vertices (or a face selection boundary)")
            return {'CANCELLED'}

        # 1. Calculate Center
        center = Vector((0,0,0))
        for v in selected_verts: 
            center += v.co
        center /= len(selected_verts)

        # 2. Calculate Plane (Best Fit)
        try:
            normal = geometry.normal([v.co for v in selected_verts])
        except:
            normal = Vector((0,0,1))
        
        if normal.length_squared < 1e-6:
             normal = Vector((0,0,1))

        # Create basis vectors for the plane
        # Try to align tangent to Object X axis projected on plane for predictable rotation
        ref_axis = Vector((1, 0, 0))
        if abs(normal.dot(ref_axis)) > 0.9: # If normal is roughly X, use Y
            ref_axis = Vector((0, 1, 0))
            
        tangent = (ref_axis - ref_axis.dot(normal) * normal).normalized()
        bitangent = normal.cross(tangent)

        # --- Align Orientation to Geometry ---
        # Find vertex farthest from center to align corners
        # This prevents "beveled" corners when the mesh is rotated relative to the calculated basis
        max_dist_sq = 0.0
        candidates = []
        
        for v in selected_verts:
            d_sq = (v.co - center).length_squared
            if d_sq > max_dist_sq + 1e-5:
                max_dist_sq = d_sq
                candidates = [v]
            elif d_sq > max_dist_sq - 1e-5:
                candidates.append(v)
        
        # Pick the candidate that minimizes basis rotation (closest to 45 degrees in current basis)
        best_rot_angle = 0.0
        min_abs_rot = 1000.0
        
        for v in candidates:
            vec = v.co - center
            vec = vec - vec.dot(normal) * normal # Project to plane
            if vec.length_squared > 1e-6:
                angle = math.atan2(vec.dot(bitangent), vec.dot(tangent))
                # Rotate basis so this vertex is at 45 degrees (PI/4)
                rot = angle - (math.pi / 4)
                # Normalize to -pi..pi
                while rot > math.pi: rot -= 2*math.pi
                while rot <= -math.pi: rot += 2*math.pi
                
                if abs(rot) < min_abs_rot:
                    min_abs_rot = abs(rot)
                    best_rot_angle = rot

        if candidates:
            rot_mat = Matrix.Rotation(best_rot_angle, 3, normal)
            tangent = rot_mat @ tangent
            bitangent = rot_mat @ bitangent

        # 3. Calculate Size
        # Use the radius property (distance to corner) to determine size
        half_size = self.radius * (math.sqrt(2) / 2.0)
        
        if half_size < 1e-6:
            self.report({'INFO'}, "Selection has zero size, cannot create square.")
            return {'CANCELLED'}

        # 4. Project and Position
        
        # Calculate angles and sort vertices
        vert_angles = []
        for v in selected_verts:
            vec = v.co - center
            x = vec.dot(tangent)
            y = vec.dot(bitangent)
            angle = math.atan2(y, x) # -pi to pi
            vert_angles.append((v, angle))
        
        vert_angles.sort(key=lambda x: x[1])

        # Corner-aware distribution for Regular Squares
        if self.regular and len(selected_verts) >= 4:
            # Identify indices of the 4 corners based on angle proximity
            # Targets: BL(-135), BR(-45), TR(45), TL(135)
            targets = [-3*math.pi/4, -math.pi/4, math.pi/4, 3*math.pi/4]
            corner_indices = []
            used_indices = set()
            for target in targets:
                best_idx = -1
                min_dist = 100.0
                for i, (v, a) in enumerate(vert_angles):
                    if i in used_indices: continue
                    dist = abs(a - target)
                    if dist > math.pi: dist = 2*math.pi - dist # Handle wrap-around
                    if dist < min_dist:
                        min_dist = dist
                        best_idx = i
                corner_indices.append(best_idx)
                used_indices.add(best_idx)
            
            # Corner positions in normalized space corresponding to targets
            corners_pos = [Vector((-1,-1)), Vector((1,-1)), Vector((1,1)), Vector((-1,1))]
            
            # Distribute vertices between corners
            for i in range(4):
                idx_start = corner_indices[i]
                idx_end = corner_indices[(i+1)%4]
                p_start = corners_pos[i]
                p_end = corners_pos[(i+1)%4]
                
                # Collect indices for this side
                segment_indices = []
                curr = idx_start
                while curr != idx_end:
                    segment_indices.append(curr)
                    curr = (curr + 1) % len(vert_angles)
                segment_indices.append(idx_end)
                
                # Distribute linearly along the edge
                # We exclude the last point to avoid processing corners twice (it will be start of next segment)
                count = len(segment_indices)
                for k, v_idx in enumerate(segment_indices[:-1]):
                    factor = k / (count - 1) if count > 1 else 0
                    pos_2d = p_start.lerp(p_end, factor)
                    
                    v = vert_angles[v_idx][0]
                    final_pos = center + (tangent * pos_2d.x + bitangent * pos_2d.y) * half_size
                    v.co = v.co.lerp(final_pos, self.influence)

        else:
            # Fallback / Regular=False: Project each vertex to the nearest point on the square perimeter
            
            # Identify corners to snap them (prevents beveled corners)
            corner_verts = set()
            if len(selected_verts) >= 4:
                targets = [-3*math.pi/4, -math.pi/4, math.pi/4, 3*math.pi/4]
                used_indices = set()
                for target in targets:
                    best_v = None
                    min_dist = 100.0
                    best_idx = -1
                    for i, (v, a) in enumerate(vert_angles):
                        if i in used_indices: continue
                        dist = abs(a - target)
                        if dist > math.pi: dist = 2*math.pi - dist # Handle wrap-around
                        if dist < min_dist:
                            min_dist = dist
                            best_v = v
                            best_idx = i
                    if best_v:
                        corner_verts.add(best_v)
                        used_indices.add(best_idx)

            for v, angle in vert_angles:
                vec = v.co - center
                x = vec.dot(tangent)
                y = vec.dot(bitangent)

                # If this vertex was identified as a corner candidate, snap it exactly
                if v in corner_verts:
                    sx = 1.0 if x >= 0 else -1.0
                    sy = 1.0 if y >= 0 else -1.0
                else:
                    # Standard radial projection for sides
                    max_comp = max(abs(x), abs(y))
                    if max_comp < 1e-9: continue
                    scale = 1.0 / max_comp
                    sx = x * scale
                    sy = y * scale
                
                square_pos = center + (tangent * sx + bitangent * sy) * half_size
                v.co = v.co.lerp(square_pos, self.influence)

        bmesh.update_edit_mesh(me)
        return {'FINISHED'}

class ALEC_OT_clean_mesh(bpy.types.Operator):
    """Dissolve redundant edges on flat surfaces and merge double vertices"""
    bl_idname = "alec.clean_mesh"
    bl_label = "Clean Mesh"
    bl_options = {'REGISTER', 'UNDO'}

    angle_limit: bpy.props.FloatProperty(
        name="Angle Limit",
        default=0.0872665, # 5 degrees in radians
        subtype='ANGLE',
        description="Max angle between faces to dissolve"
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        return context.active_object and context.mode == 'EDIT_MESH'

    def execute(self, context):
        bpy.ops.mesh.remove_doubles()
        bpy.ops.mesh.dissolve_limited(angle_limit=self.angle_limit)
        return {'FINISHED'}

class ALEC_OT_extract_and_solidify(bpy.types.Operator):
    """Duplicate selected faces, separate them, and add Solidify"""
    bl_idname = "alec.extract_and_solidify"
    bl_label = "Extract & Solidify"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.active_object

    def execute(self, context):
        bpy.ops.mesh.duplicate()
        bpy.ops.mesh.separate(type='SELECTED')
        bpy.ops.object.mode_set(mode='OBJECT')
        
        active = context.active_object
        selected = context.selected_objects
        new_obj = None
        
        for obj in selected:
            if obj != active:
                new_obj = obj
                break
        
        if new_obj:
            bpy.ops.object.select_all(action='DESELECT')
            new_obj.select_set(True)
            context.view_layer.objects.active = new_obj
            
            # Trigger the modal solidify operator
            bpy.ops.alec.solidify_modal('INVOKE_DEFAULT')
            
        return {'FINISHED'}

classes = [
    ALEC_OT_set_edge_length,
    ALEC_OT_dimension_action,
    ALEC_OT_select_dimension_edges,
    ALEC_OT_set_edge_angle,
    ALEC_OT_distribute_vertices,
    ALEC_OT_make_collinear,
    ALEC_OT_make_coplanar,
    ALEC_OT_make_circle,
    ALEC_OT_make_square,
    ALEC_OT_clean_mesh,
    ALEC_OT_extract_and_solidify,
]
