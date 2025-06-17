bl_info = {
    "name": "Lock Bone Weights",
    "author": "Claude AI",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > N-Panel > Lock Bone Weights",
    "description": "Lock and unlock vertex groups for bone weights",
    "category": "Rigging",
}

import bpy
from bpy.props import StringProperty, CollectionProperty, IntProperty
from bpy.types import Panel, Operator, PropertyGroup


class MESH_OT_lock_selected_bones(Operator):
    """Lock vertex groups for selected bones"""
    bl_idname = "mesh.lock_selected_bones"
    bl_label = "Lock Selected"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "No active mesh object")
            return {'CANCELLED'}
        
        armature = obj.find_armature()
        if not armature:
            self.report({'WARNING'}, "No armature found for this mesh")
            return {'CANCELLED'}
        
        locked_count = 0
        for bone in armature.data.bones:
            if bone.select:
                vg = obj.vertex_groups.get(bone.name)
                if vg and not vg.lock_weight:
                    vg.lock_weight = True
                    locked_count += 1
        
        self.report({'INFO'}, f"Locked {locked_count} vertex groups")
        return {'FINISHED'}


class MESH_OT_unlock_selected_bones(Operator):
    """Unlock vertex groups for selected bones"""
    bl_idname = "mesh.unlock_selected_bones"
    bl_label = "Unlock Selected"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "No active mesh object")
            return {'CANCELLED'}
        
        armature = obj.find_armature()
        if not armature:
            self.report({'WARNING'}, "No armature found for this mesh")
            return {'CANCELLED'}
        
        unlocked_count = 0
        for bone in armature.data.bones:
            if bone.select:
                vg = obj.vertex_groups.get(bone.name)
                if vg and vg.lock_weight:
                    vg.lock_weight = False
                    unlocked_count += 1
        
        self.report({'INFO'}, f"Unlocked {unlocked_count} vertex groups")
        return {'FINISHED'}


class MESH_OT_lock_bones_by_name(Operator):
    """Lock vertex groups by name (supports partial matches)"""
    bl_idname = "mesh.lock_bones_by_name"
    bl_label = "Lock by Name"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "No active mesh object")
            return {'CANCELLED'}
        
        props = context.scene.lock_bone_weights_props
        locked_count = 0
        
        # Check all input fields
        names_to_check = []
        if props.bone_name_1.strip():
            names_to_check.append(props.bone_name_1.strip())
        if props.num_fields >= 2 and props.bone_name_2.strip():
            names_to_check.append(props.bone_name_2.strip())
        if props.num_fields >= 3 and props.bone_name_3.strip():
            names_to_check.append(props.bone_name_3.strip())
        
        # Check for partial matches in all vertex groups
        for search_name in names_to_check:
            for vg in obj.vertex_groups:
                if search_name.lower() in vg.name.lower() and not vg.lock_weight:
                    vg.lock_weight = True
                    locked_count += 1
        
        self.report({'INFO'}, f"Locked {locked_count} vertex groups by name")
        return {'FINISHED'}


class MESH_OT_unlock_bones_by_name(Operator):
    """Unlock vertex groups by name (supports partial matches)"""
    bl_idname = "mesh.unlock_bones_by_name"
    bl_label = "Unlock by Name"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "No active mesh object")
            return {'CANCELLED'}
        
        props = context.scene.lock_bone_weights_props
        unlocked_count = 0
        
        # Check all input fields
        names_to_check = []
        if props.bone_name_1.strip():
            names_to_check.append(props.bone_name_1.strip())
        if props.num_fields >= 2 and props.bone_name_2.strip():
            names_to_check.append(props.bone_name_2.strip())
        if props.num_fields >= 3 and props.bone_name_3.strip():
            names_to_check.append(props.bone_name_3.strip())
        
        # Check for partial matches in all vertex groups
        for search_name in names_to_check:
            for vg in obj.vertex_groups:
                if search_name.lower() in vg.name.lower() and vg.lock_weight:
                    vg.lock_weight = False
                    unlocked_count += 1
        
        self.report({'INFO'}, f"Unlocked {unlocked_count} vertex groups by name")
        return {'FINISHED'}


class MESH_OT_add_bone_name_field(Operator):
    """Add a new bone name input field"""
    bl_idname = "mesh.add_bone_name_field"
    bl_label = "Add Name Field"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.lock_bone_weights_props
        if props.num_fields < 3:
            props.num_fields += 1
        return {'FINISHED'}


class MESH_OT_remove_bone_name_field(Operator):
    """Remove a bone name input field"""
    bl_idname = "mesh.remove_bone_name_field"
    bl_label = "Remove Name Field"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.lock_bone_weights_props
        if props.num_fields > 1:
            props.num_fields -= 1
            # Clear the field that's being removed
            if props.num_fields == 1:
                props.bone_name_2 = ""
                props.bone_name_3 = ""
            elif props.num_fields == 2:
                props.bone_name_3 = ""
        return {'FINISHED'}


class LockBoneWeightsProperties(PropertyGroup):
    bone_name_inputs: CollectionProperty(
        type=bpy.types.PropertyGroup,
        name="Bone Name Inputs"
    )
    
    # Simple string properties for input fields
    bone_name_1: StringProperty(
        name="Bone Name 1",
        description="Enter bone name to lock",
        default=""
    )
    bone_name_2: StringProperty(
        name="Bone Name 2", 
        description="Enter bone name to lock",
        default=""
    )
    bone_name_3: StringProperty(
        name="Bone Name 3",
        description="Enter bone name to lock", 
        default=""
    )
    
    num_fields: IntProperty(
        name="Number of Fields",
        default=1,
        min=1,
        max=3
    )


class VIEW3D_PT_lock_bone_weights(Panel):
    """Lock Bone Weights panel in the N-panel"""
    bl_label = "Lock Bone Weights"
    bl_idname = "VIEW3D_PT_lock_bone_weights"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Lock Bone Weights"
    
    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        # Show locked vertex groups count
        if obj and obj.type == 'MESH':
            armature = obj.find_armature()
            if armature:
                locked_count = 0
                total_bone_vgs = 0
                
                for bone in armature.data.bones:
                    vg = obj.vertex_groups.get(bone.name)
                    if vg:
                        total_bone_vgs += 1
                        if vg.lock_weight:
                            locked_count += 1
                
                box = layout.box()
                box.label(text=f"Locked: {locked_count}/{total_bone_vgs}")
                

            else:
                layout.label(text="No armature found", icon='ERROR')
        else:
            layout.label(text="Select a mesh object", icon='INFO')
        
        layout.separator()
        
        # Lock/Unlock selected bones
        col = layout.column(align=True)
        col.label(text="Selected Bones:")
        row = col.row(align=True)
        row.operator("mesh.lock_selected_bones", icon='LOCKED')
        row.operator("mesh.unlock_selected_bones", icon='UNLOCKED')
        
        layout.separator()
        
        # Lock by name section
        box = layout.box()
        col = box.column()
        col.label(text="Lock by Name:")
        
        props = context.scene.lock_bone_weights_props
        
        # Draw input fields based on num_fields
        col.prop(props, "bone_name_1", text="")
        
        if props.num_fields >= 2:
            col.prop(props, "bone_name_2", text="")
            
        if props.num_fields >= 3:
            col.prop(props, "bone_name_3", text="")
        
        # Add/Remove buttons
        row = col.row(align=True)
        if props.num_fields < 3:
            row.operator("mesh.add_bone_name_field", text="", icon='ADD')
        if props.num_fields > 1:
            row.operator("mesh.remove_bone_name_field", text="", icon='REMOVE')
        
        # Lock/Unlock by name buttons
        row = col.row(align=True)
        row.operator("mesh.lock_bones_by_name", text="Lock by Name")
        row.operator("mesh.unlock_bones_by_name", text="Unlock by Name")


classes = (
    LockBoneWeightsProperties,
    MESH_OT_lock_selected_bones,
    MESH_OT_unlock_selected_bones,
    MESH_OT_lock_bones_by_name,
    MESH_OT_unlock_bones_by_name,
    MESH_OT_add_bone_name_field,
    MESH_OT_remove_bone_name_field,
    VIEW3D_PT_lock_bone_weights,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.lock_bone_weights_props = bpy.props.PointerProperty(
        type=LockBoneWeightsProperties
    )


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.lock_bone_weights_props


if __name__ == "__main__":
    register()
