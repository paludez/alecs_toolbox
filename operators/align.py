import bpy
from mathutils import Vector
from ..modules import align_tools


# ── Active-object history (last 2 distinct active names) ─────────────────────
_active_history: list[str] = []
_last_seen_active: str | None = None


def _track_active_object_handler(scene, depsgraph):
    global _last_seen_active
    try:
        obj = bpy.context.active_object
    except Exception:
        return
    if obj is None:
        return
    name = obj.name
    if name == _last_seen_active:
        return
    _last_seen_active = name
    if _active_history and _active_history[-1] == name:
        return
    if len(_active_history) >= 2:
        _active_history.pop(0)
    _active_history.append(name)


def get_last_two_active_objects():
    """Return (penultimate_active, last_active) or (None, None) if not enough history."""
    if len(_active_history) < 2:
        return None, None
    return (
        bpy.data.objects.get(_active_history[-2]),
        bpy.data.objects.get(_active_history[-1]),
    )
# ─────────────────────────────────────────────────────────────────────────────


def _axis_direction_from_enum(context, axis_mode):
    """World-space unit vector for enum WORLD_* / LOCAL_* (LOCAL uses active object)."""
    if axis_mode == 'WORLD_X':
        return Vector((1.0, 0.0, 0.0))
    if axis_mode == 'WORLD_Y':
        return Vector((0.0, 1.0, 0.0))
    if axis_mode == 'WORLD_Z':
        return Vector((0.0, 0.0, 1.0))
    active = context.active_object
    if active is None:
        return None
    rot = active.matrix_world.to_3x3()
    if axis_mode == 'LOCAL_X':
        return rot.col[0].normalized()
    if axis_mode == 'LOCAL_Y':
        return rot.col[1].normalized()
    if axis_mode == 'LOCAL_Z':
        return rot.col[2].normalized()
    return Vector((1.0, 0.0, 0.0))

class AlignBase:
    """Base mixin class for alignment operators containing properties and logic"""
    
    align_x: bpy.props.BoolProperty(name="X", default=True, description="Align on X axis") #type: ignore
    align_y: bpy.props.BoolProperty(name="Y", default=True, description="Align on Y axis") #type: ignore
    align_z: bpy.props.BoolProperty(name="Z", default=True, description="Align on Z axis") #type: ignore

    source_point: bpy.props.EnumProperty(
        name="Current Object",
        description="Point on the current object to align from",
        items=[
            ('MIN', "Minimum", "Align from the bounding box minimum"),
            ('CENTER', "Center", "Align from the bounding box center"),
            ('PIVOT', "Pivot Point", "Align from the object's origin"),
            ('MAX', "Maximum", "Align from the bounding box maximum"),
        ],
        default='PIVOT') #type: ignore

    target_point: bpy.props.EnumProperty(
        name="Target Object",
        description="Point on the target object to align to",
        items=[
            ('MIN', "Minimum", "Align to the bounding box minimum"),
            ('CENTER', "Center", "Align to the bounding box center"),
            ('PIVOT', "Pivot Point", "Align to the object's origin"),
            ('MAX', "Maximum", "Align to the bounding box maximum"),
        ],
        default='PIVOT') #type: ignore

    orient_x: bpy.props.BoolProperty(name="X", default=False, description="Match orientation on X axis") #type: ignore
    orient_y: bpy.props.BoolProperty(name="Y", default=False, description="Match orientation on Y axis") #type: ignore
    orient_z: bpy.props.BoolProperty(name="Z", default=False, description="Match orientation on Z axis") #type: ignore

    scale_x: bpy.props.BoolProperty(name="X", default=False, description="Match scale on X axis") #type: ignore
    scale_y: bpy.props.BoolProperty(name="Y", default=False, description="Match scale on Y axis") #type: ignore
    scale_z: bpy.props.BoolProperty(name="Z", default=False, description="Match scale on Z axis") #type: ignore

    use_active_orient: bpy.props.BoolProperty(
        name="Local (Active)", 
        default=False, 
        description="Align along the active object's local axes instead of world axes"
    ) #type: ignore

    offset_x: bpy.props.FloatProperty(name="Offset X", default=0.0, unit='LENGTH') #type: ignore
    offset_y: bpy.props.FloatProperty(name="Offset Y", default=0.0, unit='LENGTH') #type: ignore
    offset_z: bpy.props.FloatProperty(name="Offset Z", default=0.0, unit='LENGTH') #type: ignore

    reset_requested: bpy.props.BoolProperty(name="Reset", description="Reset to defaults") #type: ignore

    _initial_state = {}
    _is_modal = False

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.prop(self, "reset_requested", toggle=True, icon='FILE_REFRESH', text="Reset")

        row = layout.row(align=True)
        row.label(text="POS")
        row.prop(self, "align_x", toggle=True)
        row.prop(self, "align_y", toggle=True)
        row.prop(self, "align_z", toggle=True)
        layout.prop(self, "use_active_orient")

        row = layout.row(align=True)
        row.label(text="Offset")
        
        sub = row.column(align=True)
        sub.prop(self, "offset_x", text="X")
        sub.enabled = self.align_x
        
        sub = row.column(align=True)
        sub.prop(self, "offset_y", text="Y")
        sub.enabled = self.align_y
        
        sub = row.column(align=True)
        sub.prop(self, "offset_z", text="Z")
        sub.enabled = self.align_z

        row = layout.row(align=True)
        col = row.column(align=True)
        col.label(text="Current Object:")
        col.prop(self, "source_point", expand=True)
        col = row.column(align=True)
        col.label(text="Target Object:")
        col.prop(self, "target_point", expand=True)

        row = layout.row(align=True)
        row.label(text="ORI")
        row.prop(self, "orient_x", toggle=True)
        row.prop(self, "orient_y", toggle=True)
        row.prop(self, "orient_z", toggle=True)

        row = layout.row(align=True)
        row.label(text="SCL")
        row.prop(self, "scale_x", toggle=True)
        row.prop(self, "scale_y", toggle=True)
        row.prop(self, "scale_z", toggle=True)

    def check(self, context):
        if self.reset_requested:
            self.align_x = False
            self.align_y = False
            self.align_z = False
            self.source_point = 'PIVOT'
            self.target_point = 'PIVOT'
            self.orient_x = False
            self.orient_y = False
            self.orient_z = False
            self.scale_x = False
            self.scale_y = False
            self.scale_z = False
            self.use_active_orient = False
            self.offset_x = 0.0
            self.offset_y = 0.0
            self.offset_z = 0.0
            self.reset_requested = False

        self.execute(context)
        return True

    def _restore_state(self):
        if getattr(self, '_is_modal', False) and self._initial_state:
            for name, state in self._initial_state.items():
                obj = bpy.data.objects.get(name)
                if obj:
                    obj.location = state['location']
                    obj.rotation_euler = state['rotation_euler']
                    obj.scale = state['scale']

    def cancel(self, context):
        self._restore_state()

    def execute(self, context):
        self._restore_state()

        target = context.active_object
        sources = [o for o in context.selected_objects if o != target]
        for source in sources:
            align_tools.align_orientation(source, target,
                x=self.orient_x, y=self.orient_y, z=self.orient_z)
            align_tools.match_scale(source, target,
                x=self.scale_x, y=self.scale_y, z=self.scale_z)
            
            align_tools.align_position(source, target,
                x=self.align_x, y=self.align_y, z=self.align_z,
                source_point=self.source_point,
                target_point=self.target_point,
                use_active_orient=self.use_active_orient,
                offset_x=self.offset_x, offset_y=self.offset_y, offset_z=self.offset_z)
        return {'FINISHED'}

class ALEC_OT_align_dialog(AlignBase, bpy.types.Operator):
    """Align Dialog 3ds Max style"""
    bl_idname = "alec.align_dialog"
    bl_label = "Align"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        self._is_modal = True
        self._initial_state = {}
        target = context.active_object
        sources = [o for o in context.selected_objects if o != target]

        for obj in sources:
            self._initial_state[obj.name] = {
                'location': obj.location.copy(),
                'rotation_euler': obj.rotation_euler.copy(),
                'scale': obj.scale.copy()
            }

        # Run once and rely on Blender's "Last Operator" redo panel (bottom-left).
        # This avoids centered modal dialogs/popups entirely.
        self.execute(context)
        return {'FINISHED'}

class ALEC_OT_quick_center(AlignBase, bpy.types.Operator):
    """Align selected objects to active object's bounding box center"""
    bl_idname = "alec.quick_center"
    bl_label = "Quick Center"
    bl_options = {'REGISTER', 'UNDO'}
    
    def invoke(self, context, event):
        self.source_point = 'CENTER'
        self.target_point = 'CENTER'
        return self.execute(context)

class ALEC_OT_quick_center_rot(AlignBase, bpy.types.Operator):
    """Align selected objects to active bbox center and match rotation"""
    bl_idname = "alec.quick_center_rot"
    bl_label = "Quick Center (Rot)"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        self.source_point = 'CENTER'
        self.target_point = 'CENTER'
        self.orient_x = True
        self.orient_y = True
        self.orient_z = True
        return self.execute(context)

class ALEC_OT_quick_pivot_rot(AlignBase, bpy.types.Operator):
    """Align selected objects to active pivot and match rotation"""
    bl_idname = "alec.quick_pivot_rot"
    bl_label = "Quick Pivot (Rot)"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        self.source_point = 'PIVOT'
        self.target_point = 'PIVOT'
        self.orient_x = True
        self.orient_y = True
        self.orient_z = True
        return self.execute(context)


class ALEC_OT_distribute_objects_dialog(bpy.types.Operator):
    """Distribute selected objects along an axis (even positions or equal bbox gaps)"""
    bl_idname = "alec.distribute_objects_dialog"
    bl_label = "Distribute Objects"
    bl_description = (
        "Positions: space reference points evenly. Gaps: equal space between evaluated bbox projections. "
        "Endpoints: shift-click two objects last (penultimate + active); otherwise uses left/right extremes on axis"
    )
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Mode",
        items=[
            ('POSITIONS', "Positions", "Even spacing between reference points (min/center/pivot/max)"),
            ('GAPS', "Gaps", "Equal space between bounding boxes along the axis"),
        ],
        default='POSITIONS',
    ) # type: ignore

    axis: bpy.props.EnumProperty(
        name="Axis",
        items=[
            ('WORLD_X', "World X", ""),
            ('WORLD_Y', "World Y", ""),
            ('WORLD_Z', "World Z", ""),
            ('LOCAL_X', "Local X (Active)", ""),
            ('LOCAL_Y', "Local Y (Active)", ""),
            ('LOCAL_Z', "Local Z (Active)", ""),
        ],
        default='WORLD_X',
    ) # type: ignore

    reference_point: bpy.props.EnumProperty(
        name="Reference",
        description="Reference point on each object (Positions mode only)",
        items=[
            ('MIN', "Minimum", ""),
            ('CENTER', "Center", ""),
            ('PIVOT', "Pivot", ""),
            ('MAX', "Maximum", ""),
        ],
        default='PIVOT',
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        return (
            context.mode == 'OBJECT'
            and len(context.selected_objects) >= 2
        )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mode", expand=True)
        layout.prop(self, "axis", text="Axis")
        sub = layout.column()
        sub.prop(self, "reference_point", expand=True)
        sub.enabled = self.mode == 'POSITIONS'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def execute(self, context):
        axis_dir = _axis_direction_from_enum(context, self.axis)
        if axis_dir is None:
            self.report({'WARNING'}, "Need an active object for local axes")
            return {'CANCELLED'}

        objects = list(context.selected_objects)

        ep_prev, ep_last = get_last_two_active_objects()
        sel_set = set(objects)
        if ep_prev in sel_set and ep_last in sel_set:
            endpoints = (ep_prev, ep_last)
        else:
            endpoints = None

        if self.mode == 'POSITIONS':
            ok, msg = align_tools.distribute_objects_positions(
                objects, axis_dir, self.reference_point, endpoint_objs=endpoints)
        else:
            ok, msg = align_tools.distribute_objects_gaps(
                objects, axis_dir, endpoint_objs=endpoints)

        if not ok:
            self.report({'WARNING'}, msg)
            return {'CANCELLED'}
        return {'FINISHED'}


classes = [
    ALEC_OT_align_dialog,
    ALEC_OT_quick_center,
    ALEC_OT_quick_center_rot,
    ALEC_OT_quick_pivot_rot,
    ALEC_OT_distribute_objects_dialog,
]