import bpy

class BoneRenamerProperties(bpy.types.PropertyGroup):
    prefix: bpy.props.StringProperty(name="Prefix", default="")
    suffix: bpy.props.StringProperty(name="Suffix", default="")
    base_name: bpy.props.StringProperty(name="Base Name", default="Bone")
    digits: bpy.props.IntProperty(name="Digits", default=2, min=1, max=6)

class OBJECT_OT_rename_bones(bpy.types.Operator):
    bl_idname = "object.rename_bones"
    bl_label = "Rename Bones"
    bl_description = "Renames selected bones hierarchically from parent to child"
    bl_options = {'REGISTER', 'UNDO'}
    
    def get_bone_chains(self, selected_bones):
        """Get bone chains from selected bones, ordered from parent to child"""
        bone_chains = []
        processed_bones = set()
        
        # Find root bones (bones with no selected parent)
        root_bones = []
        for bone in selected_bones:
            if bone.parent not in selected_bones:
                root_bones.append(bone)
        
        # For each root bone, traverse the chain
        for root in root_bones:
            chain = []
            current = root
            
            # Follow the chain down
            while current and current in selected_bones and current not in processed_bones:
                chain.append(current)
                processed_bones.add(current)
                
                # Find the next child in the selection
                next_bone = None
                for child in current.children:
                    if child in selected_bones and child not in processed_bones:
                        next_bone = child
                        break
                
                current = next_bone
            
            if chain:
                bone_chains.append(chain)
        
        return bone_chains
    
    def execute(self, context):
        props = context.scene.bone_renamer_props
        armature = context.object
        
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, "Select an armature object")
            return {'CANCELLED'}
        
        # Get selected bones based on current mode
        if context.mode == 'POSE':
            selected_bones = [bone.bone for bone in context.selected_pose_bones]
        elif context.mode == 'EDIT_ARMATURE':
            selected_bones = context.selected_editable_bones
        else:
            self.report({'ERROR'}, "Must be in Pose or Edit mode")
            return {'CANCELLED'}
        
        if not selected_bones:
            self.report({'ERROR'}, "No bones selected")
            return {'CANCELLED'}
        
        # Get bone chains ordered hierarchically
        bone_chains = self.get_bone_chains(selected_bones)
        
        # Rename bones in hierarchical order
        counter = 1
        for chain in bone_chains:
            for bone in chain:
                number = str(counter).zfill(props.digits)
                bone.name = f"{props.prefix}{props.base_name}{number}{props.suffix}"
                counter += 1
        
        self.report({'INFO'}, f"Renamed {counter-1} bones in hierarchical order")
        return {'FINISHED'}

class OBJECT_PT_bone_renamer_panel(bpy.types.Panel):
    bl_label = "Bone Renamer"
    bl_idname = "OBJECT_PT_bone_renamer_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Bone Name"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.bone_renamer_props
        
        layout.prop(props, "prefix")
        layout.prop(props, "base_name")
        layout.prop(props, "suffix")
        layout.prop(props, "digits")
        
        layout.operator("object.rename_bones")
        
        # Add helpful info
        layout.separator()
        box = layout.box()
        box.label(text="Info:", icon='INFO')
        box.label(text="Renames bones from parent to child")
        box.label(text="Works in Pose or Edit mode")

classes = [
    BoneRenamerProperties,
    OBJECT_OT_rename_bones,
    OBJECT_PT_bone_renamer_panel
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bone_renamer_props = bpy.props.PointerProperty(type=BoneRenamerProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.bone_renamer_props

if __name__ == "__main__":
    register()
