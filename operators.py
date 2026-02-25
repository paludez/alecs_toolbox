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
    )

    def execute(self, context):
        misc_tools.manage_grouping(context, self.action)
        return {'FINISHED'}


# --- BBox Operators ---

class BBoxOperatorBase:
    """Base class for Bounding Box operators to reduce code duplication."""
    bl_options = {'REGISTER', 'UNDO'}
    mode: str = ""

    def execute(self, context):
        if not self.mode:
            self.report({'ERROR'}, "Mode not set in BBox operator subclass")
            return {'CANCELLED'}
        
        # The core logic is delegated to the bbox_tools module.
        # It's important that the tool function receives the full context.
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

    length: bpy.props.FloatProperty(
        name="Length",
        description="The desired length for the edge",
        default=1.0,
        min=0.001,
        unit='LENGTH'
    ) #type: ignore

    anchor: bpy.props.EnumProperty(
        name="Anchor",
        description="How to anchor the edge when resizing",
        items=[
            ('ACTIVE_VERTEX', "Active Vertex", "The active vertex will remain stationary"),
            ('CENTER', "Center", "Both vertices will move towards/away from the center")
        ],
        default='ACTIVE_VERTEX'
    ) #type: ignore

    @classmethod
    def poll(cls, context):
        # Operator is only available in Edit Mode for a mesh object
        return (context.active_object is not None and
                context.active_object.type == 'MESH' and
                context.mode == 'EDIT_MESH')

    def execute(self, context):
        obj = context.edit_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        # Find the active edge (last selected edge)
        active_edge = bm.select_history.active
        if not isinstance(active_edge, bmesh.types.BMEdge):
            # Fallback to any selected edge if no active history
            selected_edges = [e for e in bm.edges if e.select]
            if not selected_edges:
                self.report({'WARNING'}, "No edge selected")
                return {'CANCELLED'}
            active_edge = selected_edges[-1]

        v1, v2 = active_edge.verts
        
        # Determine the active vertex if in 'ACTIVE_VERTEX' mode
        active_vert = bm.select_history.active
        if not isinstance(active_vert, bmesh.types.BMVert):
             # If no active vert, just pick the first one
            active_vert = v1

        # Check if the active vertex is part of our edge
        if active_vert not in [v1, v2]:
             active_vert = v1 # Default to v1 if active vert is not on the edge

        current_length = (v1.co - v2.co).length
        if current_length == 0:
            self.report({'WARNING'}, "Cannot set length of a zero-length edge")
            return {'CANCELLED'}

        direction = (v2.co - v1.co).normalized()
        
        if self.anchor == 'ACTIVE_VERTEX':
            if active_vert == v1:
                # v1 is fixed, move v2
                v2.co = v1.co + direction * self.length
            else:
                # v2 is fixed, move v1
                v1.co = v2.co - direction * self.length
        
        elif self.anchor == 'CENTER':
            center_point = (v1.co + v2.co) / 2
            half_length = self.length / 2
            v1.co = center_point - direction * half_length
            v2.co = center_point + direction * half_length

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
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)