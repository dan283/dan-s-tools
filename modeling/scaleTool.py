bl_info = {
    "name": "Precise Scale Tool",
    "author": "Your Name",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > N-Panel > Scale Tool",
    "description": "Scale objects to precise dimensions",
    "category": "Mesh",
}

import bpy
import bmesh
from mathutils import Vector
from bpy.props import FloatProperty, EnumProperty, BoolProperty
from bpy.types import Panel, Operator, PropertyGroup

class MESH_OT_precise_scale(Operator):
    """Scale object to precise dimensions"""
    bl_idname = "mesh.precise_scale"
    bl_label = "Apply Scale"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({'WARNING'}, "No active object")
            return {'CANCELLED'}
        
        props = context.scene.precise_scale_props
        
        # Get current dimensions
        bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        min_coords = Vector((min(v.x for v in bbox), min(v.y for v in bbox), min(v.z for v in bbox)))
        max_coords = Vector((max(v.x for v in bbox), max(v.y for v in bbox), max(v.z for v in bbox)))
        current_dims = max_coords - min_coords
        
        # Calculate scale factor based on selected axis
        if props.scale_axis == 'X':
            if current_dims.x == 0:
                self.report({'WARNING'}, "Object has no X dimension")
                return {'CANCELLED'}
            scale_factor = props.target_size / current_dims.x
        elif props.scale_axis == 'Y':
            if current_dims.y == 0:
                self.report({'WARNING'}, "Object has no Y dimension")
                return {'CANCELLED'}
            scale_factor = props.target_size / current_dims.y
        else:  # Z
            if current_dims.z == 0:
                self.report({'WARNING'}, "Object has no Z dimension")
                return {'CANCELLED'}
            scale_factor = props.target_size / current_dims.z
        
        # Apply uniform scale
        if props.uniform_scale:
            obj.scale = (obj.scale.x * scale_factor, obj.scale.y * scale_factor, obj.scale.z * scale_factor)
        else:
            # Apply scale only to selected axis
            if props.scale_axis == 'X':
                obj.scale = (obj.scale.x * scale_factor, obj.scale.y, obj.scale.z)
            elif props.scale_axis == 'Y':
                obj.scale = (obj.scale.x, obj.scale.y * scale_factor, obj.scale.z)
            else:  # Z
                obj.scale = (obj.scale.x, obj.scale.y, obj.scale.z * scale_factor)
        
        # Update the display dimensions
        self.update_dimensions(context)
        
        return {'FINISHED'}
    
    def update_dimensions(self, context):
        """Update the dimension display properties"""
        obj = context.active_object
        if not obj:
            return
        
        props = context.scene.precise_scale_props
        
        # Calculate current dimensions
        bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        min_coords = Vector((min(v.x for v in bbox), min(v.y for v in bbox), min(v.z for v in bbox)))
        max_coords = Vector((max(v.x for v in bbox), max(v.y for v in bbox), max(v.z for v in bbox)))
        current_dims = max_coords - min_coords
        
        # Update properties
        props.current_x = current_dims.x
        props.current_y = current_dims.y
        props.current_z = current_dims.z

class MESH_OT_update_dimensions(Operator):
    """Update current dimensions display"""
    bl_idname = "mesh.update_dimensions"
    bl_label = "Update Dimensions"
    
    def execute(self, context):
        obj = context.active_object
        if not obj:
            return {'CANCELLED'}
        
        props = context.scene.precise_scale_props
        
        # Calculate current dimensions
        bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        min_coords = Vector((min(v.x for v in bbox), min(v.y for v in bbox), min(v.z for v in bbox)))
        max_coords = Vector((max(v.x for v in bbox), max(v.y for v in bbox), max(v.z for v in bbox)))
        current_dims = max_coords - min_coords
        
        # Update properties
        props.current_x = current_dims.x
        props.current_y = current_dims.y
        props.current_z = current_dims.z
        
        return {'FINISHED'}

class PreciseScaleProperties(PropertyGroup):
    """Properties for the precise scale tool"""
    
    scale_axis: EnumProperty(
        name="Scale Axis",
        description="Axis to scale based on",
        items=[
            ('X', "X", "Scale based on X dimension"),
            ('Y', "Y", "Scale based on Y dimension"),
            ('Z', "Z", "Scale based on Z dimension"),
        ],
        default='X'
    )
    
    target_size: FloatProperty(
        name="Target Size",
        description="Target size for the selected axis",
        default=1.0000,
        min=0.0001,
        soft_max=100.0,
        unit='LENGTH',
        precision=4
    )
    
    uniform_scale: BoolProperty(
        name="Uniform Scale",
        description="Scale uniformly on all axes",
        default=True
    )
    
    # Current dimensions (read-only display)
    current_x: FloatProperty(
        name="Current X",
        description="Current X dimension",
        default=0.0,
        unit='LENGTH'
    )
    
    current_y: FloatProperty(
        name="Current Y",
        description="Current Y dimension",
        default=0.0,
        unit='LENGTH'
    )
    
    current_z: FloatProperty(
        name="Current Z",
        description="Current Z dimension",
        default=0.0,
        unit='LENGTH'
    )

class VIEW3D_PT_precise_scale(Panel):
    """Panel for precise scaling tools"""
    bl_label = "Scale Tool"
    bl_idname = "VIEW3D_PT_precise_scale"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scale Tool"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.precise_scale_props
        obj = context.active_object
        
        if not obj:
            layout.label(text="No active object", icon='ERROR')
            return
        
        # Current dimensions section
        box = layout.box()
        box.label(text="Current Dimensions:", icon='DRIVER_DISTANCE')
        
        col = box.column(align=True)
        row = col.row(align=True)
        row.label(text=f"X: {props.current_x:.4f}")
        row = col.row(align=True)
        row.label(text=f"Y: {props.current_y:.4f}")
        row = col.row(align=True)
        row.label(text=f"Z: {props.current_z:.4f}")
        
        box.operator("mesh.update_dimensions", text="Update", icon='FILE_REFRESH')
        
        # Scale controls section
        box = layout.box()
        box.label(text="Scale Controls:", icon='FULLSCREEN_ENTER')
        
        col = box.column(align=True)
        col.prop(props, "scale_axis")
        col.prop(props, "target_size")
        col.prop(props, "uniform_scale")
        
        col.separator()
        col.operator("mesh.precise_scale", text="Apply Scale", icon='CHECKMARK')

def register():
    bpy.utils.register_class(PreciseScaleProperties)
    bpy.utils.register_class(MESH_OT_precise_scale)
    bpy.utils.register_class(MESH_OT_update_dimensions)
    bpy.utils.register_class(VIEW3D_PT_precise_scale)
    
    bpy.types.Scene.precise_scale_props = bpy.props.PointerProperty(type=PreciseScaleProperties)

def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_precise_scale)
    bpy.utils.unregister_class(MESH_OT_update_dimensions)
    bpy.utils.unregister_class(MESH_OT_precise_scale)
    bpy.utils.unregister_class(PreciseScaleProperties)
    
    del bpy.types.Scene.precise_scale_props

if __name__ == "__main__":
    register()
