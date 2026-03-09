# Operators for mesh editing in Edit Mode
import bpy
import bmesh
from ..modules import utils
import blf
import gpu
from bpy_extras.view3d_utils import location_3d_to_region_2d
from ..modules.modal_handler import ModalNumberInput, update_modal_header
from ..modules.utils import find_farthest_vertices, unit_suffixes, draw_modal_status_bar

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
        unit_scale = utils.get_unit_scale(context)
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
    ALEC_OT_make_collinear,
    ALEC_OT_make_coplanar,
    ALEC_OT_clean_mesh,
    ALEC_OT_extract_and_solidify,
]
