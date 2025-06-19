import bpy
from bpy.props import StringProperty, BoolProperty, CollectionProperty, IntProperty
from bpy.types import PropertyGroup, UIList

# Property group to store bone collection UI settings
class BoneCollectionUIItem(PropertyGroup):
    collection_name: StringProperty(
        name="Collection Name",
        description="Name of the bone collection",
        default=""
    )
    display_name: StringProperty(
        name="Display Name", 
        description="Name to display in UI (leave empty to use collection name)",
        default=""
    )
    show_in_ui: BoolProperty(
        name="Show in UI",
        description="Whether to show this collection in the UI",
        default=True
    )
    ui_row: IntProperty(
        name="UI Row",
        description="Which row to place this collection in (collections with same row number will be grouped)",
        default=0,
        min=0
    )

# UI List for managing bone collection settings
class RIGUI_UL_bone_collections(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "show_in_ui", text="", emboss=False, icon='HIDE_OFF' if item.show_in_ui else 'HIDE_ON')
            row.prop(item, "collection_name", text="Collection", emboss=False)
            row.prop(item, "display_name", text="Display Name", emboss=False)
            row.prop(item, "ui_row", text="Row", emboss=False)
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)

# Settings panel for configuring the UI
class RIGUI_PT_settings(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Item'
    bl_label = "Rig UI Settings"
    bl_idname = "RIGUI_PT_settings"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        try:
            obj = context.active_object
            # Just check if we have an armature selected
            return (obj and obj.type == 'ARMATURE')
        except (AttributeError, KeyError, TypeError):
            return False

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        armature = obj.data
        
        # UI configuration section
        col = layout.column()
        col.label(text="UI Configuration:")
        
        # Instructions
        box = col.box()
        box.label(text="Instructions:", icon='INFO')
        box.label(text="• Collections with same Row number appear together")
        box.label(text="• Use Display Name to override button text")
        box.label(text="• Toggle Show in UI to hide collections")
        
        # Armature name override
        col.prop(armature, '["ui_armature_name"]', text="Target Armature")
        
        # Auto-populate button
        row = col.row(align=True)
        row.operator("rigui.populate_collections", text="Auto-Populate")
        row.operator("rigui.group_pairs", text="Group Pairs")
        row.operator("rigui.clear_collections", text="Clear")
        
        # Collection list with headers
        col.label(text="Bone Collections:")
        row = col.row()
        row.label(text="Show")
        row.label(text="Collection Name")
        row.label(text="Display Name")
        row.label(text="Row")
        
        col.template_list("RIGUI_UL_bone_collections", "", 
                         armature, "rigui_bone_collections",
                         armature, "rigui_active_collection_index")
        
        # Add/Remove buttons
        row = col.row(align=True)
        row.operator("rigui.add_collection", text="Add")
        row.operator("rigui.remove_collection", text="Remove")

# Main rig UI panel
class RIGUI_PT_main(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Item'
    bl_label = "Rig UI"
    bl_idname = "RIGUI_PT_main"

    @classmethod
    def poll(cls, context):
        try:
            obj = context.active_object
            # More permissive poll - just check if armature has UI collections configured
            return (obj and obj.type == 'ARMATURE' and 
                   hasattr(obj.data, 'rigui_bone_collections') and
                   len(obj.data.rigui_bone_collections) > 0)
        except (AttributeError, KeyError, TypeError):
            return False

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        armature = obj.data
        
        # Get armature name (use override if set, otherwise use actual name)
        armature_name = armature.get("ui_armature_name", armature.name)
        
        # Check if the specified armature exists
        if armature_name not in bpy.data.armatures:
            layout.label(text=f"Armature '{armature_name}' not found!", icon='ERROR')
            return
        
        target_armature = bpy.data.armatures[armature_name]
        col = layout.column()
        
        # Group collections by row number
        collections_by_row = {}
        for item in armature.rigui_bone_collections:
            if item.show_in_ui and item.collection_name in target_armature.collections:
                if item.ui_row not in collections_by_row:
                    collections_by_row[item.ui_row] = []
                collections_by_row[item.ui_row].append(item)
        
        # Draw collections grouped by rows
        for row_num in sorted(collections_by_row.keys()):
            row = col.row(align=True)
            for item in collections_by_row[row_num]:
                collection = target_armature.collections[item.collection_name]
                display_name = item.display_name if item.display_name else item.collection_name
                row.prop(collection, 'is_visible', toggle=True, text=display_name)

# Operators
class RIGUI_OT_populate_collections(bpy.types.Operator):
    bl_idname = "rigui.populate_collections"
    bl_label = "Populate Collections"
    bl_description = "Auto-populate the list with all bone collections from the armature"
    
    def execute(self, context):
        obj = context.active_object
        armature = obj.data
        
        # Get target armature name
        armature_name = armature.get("ui_armature_name", armature.name)
        if armature_name not in bpy.data.armatures:
            self.report({'WARNING'}, f"Armature '{armature_name}' not found!")
            return {'CANCELLED'}
        
        target_armature = bpy.data.armatures[armature_name]
        
        # Clear existing items
        armature.rigui_bone_collections.clear()
        
        # Add all collections
        for i, collection in enumerate(target_armature.collections):
            item = armature.rigui_bone_collections.add()
            item.collection_name = collection.name
            item.ui_row = i  # Each collection gets its own row by default
            
        return {'FINISHED'}

class RIGUI_OT_group_pairs(bpy.types.Operator):
    bl_idname = "rigui.group_pairs"
    bl_label = "Group Pairs"
    bl_description = "Automatically group Left/Right pairs and common collections"
    
    def execute(self, context):
        obj = context.active_object
        armature = obj.data
        
        if not armature.rigui_bone_collections:
            self.report({'WARNING'}, "No collections found. Run Auto-Populate first.")
            return {'CANCELLED'}
        
        # Group collections intelligently
        collections = list(armature.rigui_bone_collections)
        
        # Find L/R pairs and group them
        row_counter = 0
        used_collections = set()
        
        for item in collections:
            if item.collection_name in used_collections:
                continue
                
            # Check for L/R pairs
            name = item.collection_name
            if name.endswith('.L') or name.endswith('_L'):
                base_name = name[:-2]
                r_name = base_name + ('.R' if name.endswith('.L') else '_R')
                
                # Find the matching R collection
                r_item = None
                for other in collections:
                    if other.collection_name == r_name:
                        r_item = other
                        break
                
                if r_item:
                    # Group them together
                    item.ui_row = row_counter
                    r_item.ui_row = row_counter
                    used_collections.add(item.collection_name)
                    used_collections.add(r_item.collection_name)
                    row_counter += 1
                else:
                    # Single L collection
                    item.ui_row = row_counter
                    used_collections.add(item.collection_name)
                    row_counter += 1
                    
            elif name.endswith('.R') or name.endswith('_R'):
                # Skip R collections as they're handled with L collections
                if item.collection_name not in used_collections:
                    item.ui_row = row_counter
                    used_collections.add(item.collection_name)
                    row_counter += 1
            else:
                # Single collection
                item.ui_row = row_counter
                used_collections.add(item.collection_name)
                row_counter += 1
                
        self.report({'INFO'}, f"Grouped collections into {row_counter} rows")
        return {'FINISHED'}

class RIGUI_OT_clear_collections(bpy.types.Operator):
    bl_idname = "rigui.clear_collections"
    bl_label = "Clear Collections"
    bl_description = "Clear all bone collection UI settings"
    
    def execute(self, context):
        obj = context.active_object
        armature = obj.data
        armature.rigui_bone_collections.clear()
        return {'FINISHED'}

class RIGUI_OT_add_collection(bpy.types.Operator):
    bl_idname = "rigui.add_collection"
    bl_label = "Add Collection"
    bl_description = "Add a new bone collection UI item"
    
    def execute(self, context):
        obj = context.active_object
        armature = obj.data
        item = armature.rigui_bone_collections.add()
        armature.rigui_active_collection_index = len(armature.rigui_bone_collections) - 1
        return {'FINISHED'}

class RIGUI_OT_remove_collection(bpy.types.Operator):
    bl_idname = "rigui.remove_collection"
    bl_label = "Remove Collection"
    bl_description = "Remove the selected bone collection UI item"
    
    def execute(self, context):
        obj = context.active_object
        armature = obj.data
        if armature.rigui_active_collection_index >= 0:
            armature.rigui_bone_collections.remove(armature.rigui_active_collection_index)
            armature.rigui_active_collection_index = min(
                armature.rigui_active_collection_index, 
                len(armature.rigui_bone_collections) - 1
            )
        return {'FINISHED'}

# Registration
classes = [
    BoneCollectionUIItem,
    RIGUI_UL_bone_collections,
    RIGUI_PT_settings,
    RIGUI_PT_main,
    RIGUI_OT_populate_collections,
    RIGUI_OT_group_pairs,
    RIGUI_OT_clear_collections,
    RIGUI_OT_add_collection,
    RIGUI_OT_remove_collection,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Add properties to armature data
    bpy.types.Armature.rigui_bone_collections = CollectionProperty(type=BoneCollectionUIItem)
    bpy.types.Armature.rigui_active_collection_index = IntProperty()

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Remove properties
    del bpy.types.Armature.rigui_bone_collections
    del bpy.types.Armature.rigui_active_collection_index

if __name__ == "__main__":
    register()
