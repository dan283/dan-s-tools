import bpy
import hashlib
from bpy.props import StringProperty, BoolProperty, CollectionProperty, IntProperty, FloatProperty
from bpy.types import PropertyGroup, UIList

# Property group for storing custom property UI settings
class CustomPropUIItem(PropertyGroup):
    bone_name: StringProperty(
        name="Bone Name",
        description="Name of the bone containing the custom property",
        default="PROPERTIES"
    )
    prop_name: StringProperty(
        name="Property Name", 
        description="Name of the custom property",
        default="",
        update=lambda self, context: update_subpanels_delayed(context)
    )
    display_name: StringProperty(
        name="Display Name",
        description="Label to show in UI (leave empty to use property name)",
        default=""
    )
    show_in_ui: BoolProperty(
        name="Show in UI",
        description="Whether to show this property in the UI",
        default=True,
        update=lambda self, context: update_subpanels_delayed(context)
    )
    panel_name: StringProperty(
        name="Panel",
        description="Which panel to place this property in",
        default="Main",
        update=lambda self, context: update_subpanels_delayed(context)
    )
    ui_row: IntProperty(
        name="Row",
        description="Row order within the panel",
        default=0,
        min=0
    )
    in_box: BoolProperty(
        name="In Box",
        description="Draw this property inside a box",
        default=False
    )

# UI List for managing custom properties
class CUSTOMPROP_UL_properties(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            # Match the header proportions
            split = row.split(factor=0.08, align=True)
            split.prop(item, "show_in_ui", text="", emboss=False, 
                      icon='HIDE_OFF' if item.show_in_ui else 'HIDE_ON')
            split = split.split(factor=0.25, align=True)
            split.prop(item, "bone_name", text="", emboss=False)
            split = split.split(factor=0.33, align=True)
            split.prop(item, "prop_name", text="", emboss=False)
            split = split.split(factor=0.5, align=True)
            split.prop(item, "display_name", text="", emboss=False)
            split.prop(item, "panel_name", text="", emboss=False)

# Settings panel for configuring custom properties
class CUSTOMPROP_PT_settings(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Item'
    bl_label = "Custom Props Manager"
    bl_idname = "CUSTOMPROP_PT_settings"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return (context.active_object and context.active_object.type == 'ARMATURE')

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        armature = obj.data
        
        # Main controls
        col = layout.column()
        
        # Scan and refresh buttons
        row = col.row(align=True)
        row.operator("customprop.scan_properties", text="Scan Properties", icon='VIEWZOOM')
        row.operator("customprop.refresh_panels", text="Refresh UI", icon='FILE_REFRESH')
        
        col.separator()
        
        # Property list headers
        header_row = col.row()
        header_row.alignment = 'LEFT'
        split = header_row.split(factor=0.08)
        split.label(text="Show")
        split = split.split(factor=0.25)
        split.label(text="Bone")
        split = split.split(factor=0.33)
        split.label(text="Property")
        split = split.split(factor=0.5)
        split.label(text="Display Name")
        split.label(text="Panel")
        
        # Property list
        col.template_list("CUSTOMPROP_UL_properties", "", 
                         armature, "customprop_ui_items",
                         armature, "customprop_active_item_index")
        
        # Property management buttons
        row = col.row(align=True)
        row.operator("customprop.add_property", text="Add", icon='ADD')
        row.operator("customprop.remove_property", text="Remove", icon='REMOVE')
        
        # Property details for selected item
        if (armature.customprop_active_item_index >= 0 and 
            armature.customprop_active_item_index < len(armature.customprop_ui_items)):
            
            item = armature.customprop_ui_items[armature.customprop_active_item_index]
            
            col.separator()
            box = col.box()
            box.label(text="Property Settings:")
            box.prop(item, "ui_row")
            box.prop(item, "in_box")

# Main custom properties panel
class CUSTOMPROP_PT_main(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Item'
    bl_label = "Rig Properties"
    bl_idname = "CUSTOMPROP_PT_main"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj and obj.type == 'ARMATURE' and 
                hasattr(obj.data, 'customprop_ui_items') and
                any(item.show_in_ui for item in obj.data.customprop_ui_items))

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        armature = obj.data
        
        # Only draw properties assigned to Main panel
        main_items = [item for item in armature.customprop_ui_items 
                     if item.show_in_ui and item.panel_name == "Main"]
        
        # Sort items by ui_row
        main_items.sort(key=lambda x: x.ui_row)
        
        # Draw properties
        current_box = None
        for item in main_items:
            # Update current_box based on in_box setting BEFORE drawing
            if item.in_box and current_box is None:
                current_box = layout.box()
            elif not item.in_box:
                current_box = None
                
            self.draw_property(context, layout, item, current_box)

    def draw_property(self, context, layout, item, current_box):
        """Draw a single property, returns True if successful"""
        obj = context.active_object
        
        try:
            # Get the bone and check if property exists
            if item.bone_name not in obj.pose.bones:
                return False
                
            bone = obj.pose.bones[item.bone_name]
            
            # Check if property exists (only custom properties in bone.keys())
            if item.prop_name not in bone.keys():
                return False
            
            # Determine display name
            display_name = item.display_name if item.display_name else item.prop_name
            
            # Choose layout based on box setting
            if item.in_box and current_box is not None:
                prop_layout = current_box
            else:
                prop_layout = layout
            
            # Draw the property (always with slider=True)
            prop_layout.prop(bone, f'["{item.prop_name}"]', 
                           text=display_name, slider=True)
            
            return True
            
        except (KeyError, AttributeError, TypeError) as e:
            return False

# Global registry for dynamic subpanel classes
_subpanel_registry = {}

def get_panel_class_name(panel_name):
    """Generate a unique, stable class name for a panel"""
    # Create a hash of the panel name for uniqueness while keeping it readable
    panel_hash = hashlib.md5(panel_name.encode()).hexdigest()[:8]
    safe_name = "".join(c if c.isalnum() else "_" for c in panel_name)
    return f"CUSTOMPROP_PT_sub_{safe_name}_{panel_hash}"

def create_subpanel_class(panel_name, class_name):
    """Create a subpanel class for a given panel name"""
    
    # Check if we already have this class
    if class_name in _subpanel_registry:
        return _subpanel_registry[class_name]
    
    class SubPanel(bpy.types.Panel):
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = 'Item'
        bl_label = panel_name
        bl_parent_id = "CUSTOMPROP_PT_main"
        bl_options = {'DEFAULT_CLOSED'}

        @classmethod
        def poll(cls, context):
            obj = context.active_object
            return (obj and obj.type == 'ARMATURE' and 
                    hasattr(obj.data, 'customprop_ui_items') and
                    any(item.show_in_ui and item.panel_name == panel_name 
                        for item in obj.data.customprop_ui_items))

        def draw(self, context):
            layout = self.layout
            obj = context.active_object
            armature = obj.data
            
            # Get properties for this panel
            panel_items = [item for item in armature.customprop_ui_items 
                          if item.show_in_ui and item.panel_name == panel_name]
            
            # Sort items by ui_row
            panel_items.sort(key=lambda x: x.ui_row)
            
            # Draw properties
            current_box = None
            for item in panel_items:
                # Update current_box based on in_box setting BEFORE drawing
                if item.in_box and current_box is None:
                    current_box = layout.box()
                elif not item.in_box:
                    current_box = None
                    
                self.draw_property(context, layout, item, current_box)

        def draw_property(self, context, layout, item, current_box):
            """Draw a single property"""
            obj = context.active_object
            
            try:
                # Get the bone and check if property exists
                if item.bone_name not in obj.pose.bones:
                    return False
                    
                bone = obj.pose.bones[item.bone_name]
                
                # Check if property exists (only custom properties)
                if item.prop_name not in bone.keys():
                    return False
                
                # Determine display name
                display_name = item.display_name if item.display_name else item.prop_name
                
                # Choose layout based on box setting
                if item.in_box and current_box is not None:
                    prop_layout = current_box
                else:
                    prop_layout = layout
                
                # Draw the property
                prop_layout.prop(bone, f'["{item.prop_name}"]', 
                               text=display_name, slider=True)
                
                return True
                
            except (KeyError, AttributeError, TypeError) as e:
                return False
    
    # Set the class name and identifiers
    SubPanel.__name__ = class_name
    SubPanel.bl_idname = class_name
    
    # Store in registry
    _subpanel_registry[class_name] = SubPanel
    
    return SubPanel

def update_subpanels(context=None):
    """Update subpanels based on current panel names"""
    global _subpanel_registry
    
    # Get current context if not provided
    if context is None:
        context = bpy.context
    
    # Check if we have an armature
    if not (context.active_object and context.active_object.type == 'ARMATURE'):
        return
    
    armature = context.active_object.data
    if not hasattr(armature, 'customprop_ui_items'):
        return
    
    # Get unique panel names (excluding "Main")
    current_panel_names = set()
    for item in armature.customprop_ui_items:
        if item.show_in_ui and item.panel_name != "Main" and item.panel_name.strip():
            current_panel_names.add(item.panel_name)
    
    # Get currently required class names
    required_classes = {get_panel_class_name(name): name for name in current_panel_names}
    
    # Unregister panels that are no longer needed
    to_unregister = []
    for class_name, panel_class in _subpanel_registry.items():
        if class_name not in required_classes:
            try:
                bpy.utils.unregister_class(panel_class)
                to_unregister.append(class_name)
                print(f"Unregistered subpanel: {class_name}")
            except:
                pass
    
    # Remove from registry
    for class_name in to_unregister:
        del _subpanel_registry[class_name]
    
    # Register new panels
    for class_name, panel_name in required_classes.items():
        if class_name not in _subpanel_registry:
            panel_class = create_subpanel_class(panel_name, class_name)
            try:
                bpy.utils.register_class(panel_class)
                print(f"Registered subpanel: {class_name} for '{panel_name}'")
            except Exception as e:
                print(f"Failed to register subpanel {class_name}: {e}")
        elif class_name not in [cls.bl_idname for cls in bpy.types.Panel.__subclasses__() if hasattr(cls, 'bl_idname')]:
            # Panel exists in registry but not in Blender - re-register
            panel_class = _subpanel_registry[class_name]
            try:
                bpy.utils.register_class(panel_class)
                print(f"Re-registered subpanel: {class_name} for '{panel_name}'")
            except Exception as e:
                print(f"Failed to re-register subpanel {class_name}: {e}")
    
    # Force UI refresh
    if context and context.screen:
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

def update_subpanels_delayed(context):
    """Update subpanels with a delay to avoid update conflicts"""
    bpy.app.timers.register(lambda: update_subpanels(context), first_interval=0.1)

# Operators
class CUSTOMPROP_OT_scan_properties(bpy.types.Operator):
    bl_idname = "customprop.scan_properties"
    bl_label = "Scan Properties"
    bl_description = "Scan all bones for custom properties"
    
    def execute(self, context):
        obj = context.active_object
        armature = obj.data
        
        found_props = []
        existing_props = {(item.bone_name, item.prop_name) for item in armature.customprop_ui_items}
        
        # Scan all pose bones for custom properties ONLY
        for bone in obj.pose.bones:
            # Only scan custom properties (in bone.keys())
            for prop_name in bone.keys():
                # Skip internal properties
                if prop_name.startswith('_'):
                    continue
                if (bone.name, prop_name) not in existing_props:
                    found_props.append((bone.name, prop_name))
        
        # Add new properties to the list
        for bone_name, prop_name in found_props:
            item = armature.customprop_ui_items.add()
            item.bone_name = bone_name
            item.prop_name = prop_name
            item.panel_name = "Main"
            item.ui_row = len(armature.customprop_ui_items) - 1
        
        # Update subpanels
        update_subpanels(context)
        
        self.report({'INFO'}, f"Found {len(found_props)} new custom properties")
        return {'FINISHED'}

class CUSTOMPROP_OT_refresh_panels(bpy.types.Operator):
    bl_idname = "customprop.refresh_panels"
    bl_label = "Refresh UI"
    bl_description = "Refresh the custom properties UI and rebuild subpanels"
    
    def execute(self, context):
        # Update subpanels
        update_subpanels(context)
        
        self.report({'INFO'}, "UI refreshed")
        return {'FINISHED'}

class CUSTOMPROP_OT_add_property(bpy.types.Operator):
    bl_idname = "customprop.add_property"
    bl_label = "Add Property"
    bl_description = "Add a new custom property UI item"
    
    def execute(self, context):
        obj = context.active_object
        armature = obj.data
        item = armature.customprop_ui_items.add()
        item.bone_name = "PROPERTIES"
        item.panel_name = "Main"
        item.ui_row = len(armature.customprop_ui_items) - 1
        armature.customprop_active_item_index = len(armature.customprop_ui_items) - 1
        
        # Update subpanels will be triggered by the update callback
        
        return {'FINISHED'}

class CUSTOMPROP_OT_remove_property(bpy.types.Operator):
    bl_idname = "customprop.remove_property"
    bl_label = "Remove Property"
    bl_description = "Remove the selected custom property UI item"
    
    def execute(self, context):
        obj = context.active_object
        armature = obj.data
        if armature.customprop_active_item_index >= 0:
            armature.customprop_ui_items.remove(armature.customprop_active_item_index)
            armature.customprop_active_item_index = min(
                armature.customprop_active_item_index, 
                len(armature.customprop_ui_items) - 1
            )
        
        # Update subpanels after a short delay
        bpy.app.timers.register(lambda: update_subpanels(context), first_interval=0.1)
        
        return {'FINISHED'}

# Registration
classes = [
    CustomPropUIItem,
    CUSTOMPROP_UL_properties,
    CUSTOMPROP_PT_settings,
    CUSTOMPROP_PT_main,
    CUSTOMPROP_OT_scan_properties,
    CUSTOMPROP_OT_refresh_panels,
    CUSTOMPROP_OT_add_property,
    CUSTOMPROP_OT_remove_property,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Add properties to armature data
    bpy.types.Armature.customprop_ui_items = CollectionProperty(type=CustomPropUIItem)
    bpy.types.Armature.customprop_active_item_index = IntProperty()
    
    # Update subpanels on registration with delay to allow UI to initialize
    bpy.app.timers.register(lambda: update_subpanels(), first_interval=0.5)

def unregister():
    global _subpanel_registry
    
    # Unregister all dynamic subpanels
    for class_name, panel_class in list(_subpanel_registry.items()):
        try:
            bpy.utils.unregister_class(panel_class)
        except:
            pass
    
    # Clear registry
    _subpanel_registry.clear()
    
    # Unregister main classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Remove properties
    if hasattr(bpy.types.Armature, 'customprop_ui_items'):
        del bpy.types.Armature.customprop_ui_items
    if hasattr(bpy.types.Armature, 'customprop_active_item_index'):
        del bpy.types.Armature.customprop_active_item_index

if __name__ == "__main__":
    register()
