import bpy
from .modules import align_tools


class ALEC_OT_align_dialog(bpy.types.Operator):
    bl_idname = "alec.align_dialog"
    bl_label = "Align"
    bl_description = "Align Dialog 3ds Max style"
    bl_options = {'REGISTER', 'UNDO'}

    align_x: bpy.props.BoolProperty(name="X", default=True) #type: ignore
    align_y: bpy.props.BoolProperty(name="Y", default=True) #type: ignore
    align_z: bpy.props.BoolProperty(name="Z", default=True) #type: ignore

    source_point: bpy.props.EnumProperty(
        name="Current Object",
        items=[
            ('MIN', "Minimum", ""),
            ('CENTER', "Center", ""),
            ('PIVOT', "Pivot Point", ""),
            ('MAX', "Maximum", ""),
        ],
        default='PIVOT') #type: ignore

    target_point: bpy.props.EnumProperty(
        name="Target Object",
        items=[
            ('MIN', "Minimum", ""),
            ('CENTER', "Center", ""),
            ('PIVOT', "Pivot Point", ""),
            ('MAX', "Maximum", ""),
        ],
        default='PIVOT') #type: ignore

    orient_x: bpy.props.BoolProperty(name="X", default=False) #type: ignore
    orient_y: bpy.props.BoolProperty(name="Y", default=False) #type: ignore
    orient_z: bpy.props.BoolProperty(name="Z", default=False) #type: ignore

    scale_x: bpy.props.BoolProperty(name="X", default=False) #type: ignore
    scale_y: bpy.props.BoolProperty(name="Y", default=False) #type: ignore
    scale_z: bpy.props.BoolProperty(name="Z", default=False) #type: ignore

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.label(text="POS")
        row.prop(self, "align_x", toggle=True)
        row.prop(self, "align_y", toggle=True)
        row.prop(self, "align_z", toggle=True)

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

    def execute(self, context):
        target = context.active_object
        sources = [o for o in context.selected_objects if o != target]
        for source in sources:
            align_tools.align_position(source, target,
                x=self.align_x, y=self.align_y, z=self.align_z,
                source_point=self.source_point,
                target_point=self.target_point)
            align_tools.align_orientation(source, target,
                x=self.orient_x, y=self.orient_y, z=self.orient_z)
            align_tools.match_scale(source, target,
                x=self.scale_x, y=self.scale_y, z=self.scale_z)
        return {'FINISHED'}

class ALEC_OT_bbox_dialog(bpy.types.Operator):
    bl_idname = "alec.bbox_dialog"
    bl_label = "BBox"
    bl_description = "Create bounding box"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty( # type: ignore
        name="Mode",
        items=[
            ('LOCAL', "LOCAL", ""),
            ('WORLD', "WORLD", ""),
        ],
        default='LOCAL')

    make_offset: bpy.props.BoolProperty(name="BBoxOF", default=False) # type: ignore

    offset: bpy.props.FloatProperty( # type: ignore
        name="Offset",
        default=0.5,
        min=0.0,
        soft_max=10.0)

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.prop(self, "mode", expand=True)
        row = layout.row(align=True)
        row.prop(self, "make_offset", toggle=True)
        row.prop(self, "offset", text="Offset")

    def execute(self, context):
        from .modules import bbox_tools
        if self.make_offset:
            bbox_tools.create_offset_bbox(context.active_object, offset=self.offset)
        else:
            bbox_tools.create_bbox(context, mode=self.mode)
        return {'FINISHED'}

classes = [
    ALEC_OT_align_dialog,
    ALEC_OT_bbox_dialog,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)