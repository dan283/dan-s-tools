import bpy
import bmesh
import os
from bpy.types import Panel, Operator
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy_extras.io_utils import ExportHelper

bl_info = {
    "name": "Object Exporter",
    "author": "Your Name",
    "version": (1, 0),
    "blender": (3, 2, 0),
    "location": "3D Viewport > N Panel > Object Exporter",
    "description": "Export selected objects as separate OBJ files",
    "category": "Import-Export",
}

class OBJEXP_OT_export_selected_objects(Operator, ExportHelper):
    """Export selected objects as separate OBJ files"""
    bl_idname = "objexp.export_selected_objects"
    bl_label = "Export Selected Objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    # File browser properties
    filename_ext = ""
    use_filter_folder = True
    
    # Export options
    use_smooth_groups: BoolProperty(
        name="Smooth Groups",
        description="Write sharp edges as smooth groups",
        default=False,
    )
    
    use_normals: BoolProperty(
        name="Write Normals",
        description="Export vertex normals",
        default=True,
    )
    
    use_uvs: BoolProperty(
        name="Write UVs",
        description="Export UV coordinates",
        default=True,
    )
    
    use_materials: BoolProperty(
        name="Write Materials",
        description="Export material information",
        default=True,
    )
    
    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="Apply modifiers to exported objects",
        default=True,
    )
    
    axis_forward: EnumProperty(
        name="Forward",
        items=(
            ('X', "X Forward", ""),
            ('Y', "Y Forward", ""),
            ('Z', "Z Forward", ""),
            ('NEGATIVE_X', "-X Forward", ""),
            ('NEGATIVE_Y', "-Y Forward", ""),
            ('NEGATIVE_Z', "-Z Forward", ""),
        ),
        default='NEGATIVE_Z',
    )
    
    axis_up: EnumProperty(
        name="Up",
        items=(
            ('X', "X Up", ""),
            ('Y', "Y Up", ""),
            ('Z', "Z Up", ""),
            ('NEGATIVE_X', "-X Up", ""),
            ('NEGATIVE_Y', "-Y Up", ""),
            ('NEGATIVE_Z', "-Z Up", ""),
        ),
        default='Y',
    )
    
    global_scale: bpy.props.FloatProperty(
        name="Scale",
        description="Global scale for exported objects",
        default=1.0,
        min=0.001,
        max=1000.0,
    )

    def execute(self, context):
        # Get the directory path
        directory = os.path.dirname(self.filepath)
        
        # Get selected objects
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'WARNING'}, "No mesh objects selected!")
            return {'CANCELLED'}
        
        # Store original selection and active object
        original_selection = selected_objects.copy()
        original_active = context.view_layer.objects.active
        
        exported_count = 0
        
        try:
            # Deselect all objects first
            bpy.ops.object.select_all(action='DESELECT')
            
            for obj in selected_objects:
                # Clean the object name for filename
                clean_name = self.clean_filename(obj.name)
                if not clean_name:
                    clean_name = f"unnamed_object_{exported_count + 1}"
                
                filepath = os.path.join(directory, f"{clean_name}.obj")
                
                # Select only the current object
                obj.select_set(True)
                context.view_layer.objects.active = obj
                
                # Export the object
                try:
                    # Always use the new exporter format (Blender 3.2+)
                    # If user has older Blender, they need to update
                    bpy.ops.wm.obj_export(
                        filepath=filepath,
                        export_selected_objects=True,
                        export_smooth_groups=self.use_smooth_groups,
                        export_normals=self.use_normals,
                        export_uv=self.use_uvs,
                        export_materials=self.use_materials,
                        apply_modifiers=self.apply_modifiers,
                        forward_axis=self.axis_forward,
                        up_axis=self.axis_up,
                        global_scale=self.global_scale,
                    )
                    exported_count += 1
                    print(f"Exported: {clean_name}.obj")
                    
                except Exception as e:
                    self.report({'ERROR'}, f"Failed to export {obj.name}: {str(e)}")
                    continue
                
                # Deselect the object
                obj.select_set(False)
            
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            return {'CANCELLED'}
        
        finally:
            # Restore original selection
            for obj in original_selection:
                obj.select_set(True)
            if original_active:
                context.view_layer.objects.active = original_active
        
        self.report({'INFO'}, f"Successfully exported {exported_count} objects to {directory}")
        return {'FINISHED'}
    
    def clean_filename(self, filename):
        """Clean filename to be filesystem-safe"""
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        cleaned = filename
        
        for char in invalid_chars:
            cleaned = cleaned.replace(char, '_')
        
        # Remove leading/trailing spaces and dots
        cleaned = cleaned.strip(' .')
        
        # Limit length
        if len(cleaned) > 200:
            cleaned = cleaned[:200]
        
        return cleaned

class OBJEXP_PT_main_panel(Panel):
    """Main panel for Object Exporter"""
    bl_label = "Object Exporter"
    bl_idname = "OBJEXP_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Object Exporter"

    def draw(self, context):
        layout = self.layout
        
        # Header
        box = layout.box()
        box.label(text="Export Selected Objects", icon='EXPORT')
        
        # Selected objects info
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if selected_meshes:
            box.label(text=f"Selected: {len(selected_meshes)} mesh objects", icon='CHECKMARK')
            
            # Show list of selected objects
            col = box.column(align=True)
            col.label(text="Objects to export:")
            for i, obj in enumerate(selected_meshes[:5]):  # Show first 5
                col.label(text=f"• {obj.name}", icon='MESH_DATA')
            
            if len(selected_meshes) > 5:
                col.label(text=f"... and {len(selected_meshes) - 5} more")
        else:
            box.label(text="No mesh objects selected", icon='ERROR')
        
        # Export button
        row = layout.row()
        row.scale_y = 1.5
        if selected_meshes:
            row.operator("objexp.export_selected_objects", text="Export as OBJ Files", icon='EXPORT')
        else:
            row.enabled = False
            row.operator("objexp.export_selected_objects", text="Select Objects First", icon='EXPORT')

class OBJEXP_PT_settings_panel(Panel):
    """Settings panel for Object Exporter"""
    bl_label = "Export Settings"
    bl_idname = "OBJEXP_PT_settings_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Object Exporter"
    bl_parent_id = "OBJEXP_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        
        # Quick settings info
        box = layout.box()
        box.label(text="Export Options Preview", icon='SETTINGS')
        
        col = box.column(align=True)
        col.label(text="• Normals: Enabled")
        col.label(text="• UVs: Enabled") 
        col.label(text="• Materials: Enabled")
        col.label(text="• Modifiers: Applied")
        col.label(text="• Scale: 1.0")
        
        layout.label(text="Full settings available in export dialog")

# Registration
classes = [
    OBJEXP_OT_export_selected_objects,
    OBJEXP_PT_main_panel,
    OBJEXP_PT_settings_panel,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    print("Object Exporter addon registered")

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    print("Object Exporter addon unregistered")

if __name__ == "__main__":
    register()
    
    # Test the addon
    print("Object Exporter addon loaded successfully!")
    print("Check the N-panel in 3D Viewport > Object Exporter tab")
