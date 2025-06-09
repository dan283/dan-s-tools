import bpy
from bpy.props import IntProperty, BoolProperty, StringProperty
from bpy.types import PropertyGroup

bl_info = {
    "name": "Bone Collection UI Manager",
    "author": "Assistant",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > N-Panel > Bone Collections",
    "description": "Manage bone collection visibility through custom UI",
    "category": "Rigging",
}

# Property group to store UI assignment data
class BoneCollectionUIData(PropertyGroup):
    collection_name: StringProperty(name="Collection Name")
    ui_row: IntProperty(name="UI Row", default=1, min=1, max=20)
    assigned_to_ui: BoolProperty(name="Assigned to UI", default=False)

class ARMATURE_OT_assign_collection_to_ui(bpy.types.Operator):
    """Assign/Unassign bone collection to UI"""
    bl_idname = "armature.assign_collection_to_ui"
    bl_label = "Assign to UI"
    bl_options = {'REGISTER', 'UNDO'}
    
    collection_name: StringProperty()
    
    def execute(self, context):
        if not context.active_object or context.active_object.type != 'ARMATURE':
            self.report({'WARNING'}, "No active armature selected")
            return {'CANCELLED'}
        
        armature = context.active_object.data
        ui_data = context.scene.bone_collection_ui_data
        
        # Find existing UI data for this collection
        existing_data = None
        for item in ui_data:
            if item.collection_name == self.collection_name:
                existing_data = item
                break
        
        if existing_data:
            # Toggle assignment
            existing_data.assigned_to_ui = not existing_data.assigned_to_ui
            status = "assigned to" if existing_data.assigned_to_ui else "removed from"
            self.report({'INFO'}, f"Collection '{self.collection_name}' {status} UI")
        else:
            # Create new UI data entry
            new_item = ui_data.add()
            new_item.collection_name = self.collection_name
            new_item.assigned_to_ui = True
            new_item.ui_row = 1
            self.report({'INFO'}, f"Collection '{self.collection_name}' assigned to UI")
        
        return {'FINISHED'}

class ARMATURE_OT_toggle_collection_visibility(bpy.types.Operator):
    """Toggle bone collection visibility"""
    bl_idname = "armature.toggle_collection_visibility"
    bl_label = "Toggle Collection Visibility"
    bl_options = {'REGISTER', 'UNDO'}
    
    collection_name: StringProperty()
    
    def execute(self, context):
        if not context.active_object or context.active_object.type != 'ARMATURE':
            self.report({'WARNING'}, "No active armature selected")
            return {'CANCELLED'}
        
        armature = context.active_object.data
        
        # Find the collection and toggle visibility
        for collection in armature.collections:
            if collection.name == self.collection_name:
                collection.is_visible = not collection.is_visible
                status = "visible" if collection.is_visible else "hidden"
                self.report({'INFO'}, f"Collection '{self.collection_name}' is now {status}")
                break
        
        return {'FINISHED'}

class ARMATURE_OT_update_ui_row(bpy.types.Operator):
    """Update UI row for collection"""
    bl_idname = "armature.update_ui_row"
    bl_label = "Update Row"
    bl_options = {'REGISTER', 'UNDO'}
    
    collection_name: StringProperty()
    new_row: IntProperty()
    
    def execute(self, context):
        ui_data = context.scene.bone_collection_ui_data
        
        for item in ui_data:
            if item.collection_name == self.collection_name:
                item.ui_row = self.new_row
                break
        
        return {'FINISHED'}

class VIEW3D_PT_bone_collections_panel(bpy.types.Panel):
    """Panel for Bone Collection Management"""
    bl_label = "Bone Collections"
    bl_idname = "VIEW3D_PT_bone_collections"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Bone Collections"
    
    def draw(self, context):
        layout = self.layout
        
        if not context.active_object or context.active_object.type != 'ARMATURE':
            layout.label(text="Select an Armature")
            return
        
        armature = context.active_object.data
        ui_data = context.scene.bone_collection_ui_data
        
        # Create a dictionary for quick lookup of UI data
        ui_data_dict = {item.collection_name: item for item in ui_data}
        
        layout.label(text="Bone Collections:", icon='OUTLINER_DATA_ARMATURE')
        
        for collection in armature.collections:
            box = layout.box()
            row = box.row()
            
            # Collection name and visibility indicator
            icon = 'HIDE_OFF' if collection.is_visible else 'HIDE_ON'
            row.label(text=collection.name, icon=icon)
            
            # UI assignment status and controls
            ui_item = ui_data_dict.get(collection.name)
            
            if ui_item and ui_item.assigned_to_ui:
                # Show assigned status and row input
                sub_row = box.row()
                sub_row.label(text="UI Row:")
                sub_row.prop(ui_item, "ui_row", text="")
                
                # Unassign button
                op = sub_row.operator("armature.assign_collection_to_ui", 
                                    text="Remove from UI", icon='X')
                op.collection_name = collection.name
            else:
                # Assign to UI button
                op = row.operator("armature.assign_collection_to_ui", 
                                text="Assign to UI", icon='PLUS')
                op.collection_name = collection.name

class VIEW3D_PT_rig_ui_panel(bpy.types.Panel):
    """Panel for Rig UI Controls"""
    bl_label = "Rig UI"
    bl_idname = "VIEW3D_PT_rig_ui"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Bone Collections"
    
    def draw(self, context):
        layout = self.layout
        
        if not context.active_object or context.active_object.type != 'ARMATURE':
            return
        
        armature = context.active_object.data
        ui_data = context.scene.bone_collection_ui_data
        
        # Get assigned collections sorted by row
        assigned_collections = [item for item in ui_data if item.assigned_to_ui]
        assigned_collections.sort(key=lambda x: x.ui_row)
        
        if not assigned_collections:
            layout.label(text="No collections assigned to UI")
            return
        
        # Group collections by row
        rows = {}
        for item in assigned_collections:
            if item.ui_row not in rows:
                rows[item.ui_row] = []
            rows[item.ui_row].append(item)
        
        # Draw collections organized by rows
        for row_num in sorted(rows.keys()):
            collections_in_row = rows[row_num]
            
            if len(collections_in_row) == 1:
                # Single collection in row - full width button
                collection_name = collections_in_row[0].collection_name
                
                # Find the actual collection to check visibility
                collection_obj = None
                for col in armature.collections:
                    if col.name == collection_name:
                        collection_obj = col
                        break
                
                if collection_obj:
                    icon = 'HIDE_OFF' if collection_obj.is_visible else 'HIDE_ON'
                    op = layout.operator("armature.toggle_collection_visibility", 
                                       text=collection_name, icon=icon)
                    op.collection_name = collection_name
            else:
                # Multiple collections in row - split layout
                row_layout = layout.row()
                for item in collections_in_row:
                    collection_name = item.collection_name
                    
                    # Find the actual collection to check visibility
                    collection_obj = None
                    for col in armature.collections:
                        if col.name == collection_name:
                            collection_obj = col
                            break
                    
                    if collection_obj:
                        icon = 'HIDE_OFF' if collection_obj.is_visible else 'HIDE_ON'
                        op = row_layout.operator("armature.toggle_collection_visibility", 
                                               text=collection_name, icon=icon)
                        op.collection_name = collection_name

# Registration
classes = [
    BoneCollectionUIData,
    ARMATURE_OT_assign_collection_to_ui,
    ARMATURE_OT_toggle_collection_visibility,
    ARMATURE_OT_update_ui_row,
    VIEW3D_PT_bone_collections_panel,
    VIEW3D_PT_rig_ui_panel,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register collection property
    bpy.types.Scene.bone_collection_ui_data = bpy.props.CollectionProperty(
        type=BoneCollectionUIData
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Unregister collection property
    del bpy.types.Scene.bone_collection_ui_data

if __name__ == "__main__":
    register()
