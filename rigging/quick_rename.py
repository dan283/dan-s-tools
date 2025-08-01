import bpy
import re

class BoneRenamerProperties(bpy.types.PropertyGroup):
    # Original properties
    prefix: bpy.props.StringProperty(name="Prefix", default="")
    suffix: bpy.props.StringProperty(name="Suffix", default="")
    base_name: bpy.props.StringProperty(name="Base Name", default="Bone")
    digits: bpy.props.IntProperty(name="Digits", default=2, min=1, max=6)
    use_numbering: bpy.props.BoolProperty(name="Use Numbering", default=True, description="Add numbers to bone names")
    use_prefix: bpy.props.BoolProperty(name="Use Prefix", default=True, description="Add prefix to bone names")
    
    # New properties for find/replace functionality
    find_prefix: bpy.props.StringProperty(name="Find Prefix", default="DEF_", description="Prefix to find and replace")
    replace_prefix: bpy.props.StringProperty(name="Replace Prefix", default="MCH_", description="New prefix to replace with")
    remove_suffix: bpy.props.StringProperty(name="Remove Suffix", default=".001", description="Suffix to remove (e.g., .001, .002)")
    use_find_replace: bpy.props.BoolProperty(name="Use Find/Replace", default=False, description="Enable find and replace mode")

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
                
                # Find the next child in the selection (prioritize single child chains)
                selected_children = [child for child in current.children if child in selected_bones and child not in processed_bones]
                
                if len(selected_children) == 1:
                    # Single child - continue the chain
                    current = selected_children[0]
                elif len(selected_children) > 1:
                    # Multiple children - end this chain and start new ones for each child
                    current = None
                    # Add each child as a new root for separate chains
                    for child in selected_children:
                        if child not in processed_bones:
                            root_bones.append(child)
                else:
                    # No children - end the chain
                    current = None
            
            if chain:
                bone_chains.append(chain)
        
        # Handle any remaining unprocessed bones (isolated bones)
        for bone in selected_bones:
            if bone not in processed_bones:
                bone_chains.append([bone])
                processed_bones.add(bone)
        
        return bone_chains
    
    def get_next_available_number(self, armature, base_pattern, digits):
        """Find the next available number for bones following the pattern"""
        # Create regex pattern to match existing bones
        # Pattern matches: prefix + base_name + number + suffix
        escaped_pattern = re.escape(base_pattern).replace(r'\{number\}', r'(\d+)')
        pattern = re.compile(escaped_pattern)
        
        existing_numbers = set()
        
        # Check all bones in the armature
        for bone in armature.data.bones:
            match = pattern.match(bone.name)
            if match:
                existing_numbers.add(int(match.group(1)))
        
        # Find the next available number
        counter = 1
        while counter in existing_numbers:
            counter += 1
        
        return counter
    
    def find_replace_rename(self, bone, props):
        """Handle find and replace renaming"""
        original_name = bone.name
        new_name = original_name
        
        # Replace prefix if it exists
        if props.find_prefix and new_name.startswith(props.find_prefix):
            new_name = props.replace_prefix + new_name[len(props.find_prefix):]
        
        # Remove suffix if it exists
        if props.remove_suffix and new_name.endswith(props.remove_suffix):
            new_name = new_name[:-len(props.remove_suffix)]
        
        return new_name
    
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
        
        if props.use_find_replace:
            # Find and replace mode
            renamed_count = 0
            for bone in selected_bones:
                old_name = bone.name
                new_name = self.find_replace_rename(bone, props)
                if new_name != old_name:
                    bone.name = new_name
                    renamed_count += 1
            
            self.report({'INFO'}, f"Renamed {renamed_count} bones using find/replace")
            return {'FINISHED'}
        
        else:
            # Original hierarchical renaming mode
            # Get bone chains ordered hierarchically
            bone_chains = self.get_bone_chains(selected_bones)
            
            # Create the base pattern for checking existing names
            pattern_parts = []
            if props.use_prefix and props.prefix:
                pattern_parts.append(props.prefix)
            pattern_parts.append(props.base_name)
            if props.use_numbering:
                pattern_parts.append("{number}")
            base_pattern = "".join(pattern_parts)
            if props.suffix:
                base_pattern += props.suffix
            
            # Get starting number (continues from existing sequence)
            if props.use_numbering:
                counter = self.get_next_available_number(armature, base_pattern, props.digits)
            else:
                counter = 1
            
            # Rename bones in hierarchical order
            for chain in bone_chains:
                for bone in chain:
                    # Build the name based on options
                    name_parts = []
                    
                    # Add prefix if enabled and not empty
                    if props.use_prefix and props.prefix:
                        name_parts.append(props.prefix)
                    
                    # Add base name
                    name_parts.append(props.base_name)
                    
                    # Add number if enabled
                    if props.use_numbering:
                        number = str(counter).zfill(props.digits)
                        name_parts.append(number)
                    
                    # Combine parts and add suffix
                    bone_name = "".join(name_parts)
                    if props.suffix:
                        bone_name += props.suffix
                    
                    bone.name = bone_name
                    if props.use_numbering:
                        counter += 1
            
            bone_count = sum(len(chain) for chain in bone_chains)
            self.report({'INFO'}, f"Renamed {bone_count} bones in hierarchical order")
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
        
        # Mode selection
        box = layout.box()
        box.prop(props, "use_find_replace", text="Find & Replace Mode", icon='ZOOM_ALL')
        
        if props.use_find_replace:
            # Find and Replace Mode UI
            layout.separator()
            
            col = layout.column(align=True)
            col.label(text="Find & Replace:", icon='VIEWZOOM')
            
            # Find prefix
            row = col.row(align=True)
            row.label(text="Find Prefix:")
            row.prop(props, "find_prefix", text="")
            
            # Replace prefix
            row = col.row(align=True)
            row.label(text="Replace With:")
            row.prop(props, "replace_prefix", text="")
            
            # Remove suffix
            row = col.row(align=True)
            row.label(text="Remove Suffix:")
            row.prop(props, "remove_suffix", text="")
            
            # Preview section for find/replace
            layout.separator()
            box = layout.box()
            box.label(text="Preview:", icon='HIDE_OFF')
            
            example_name = f"{props.find_prefix}Shoulder_01.L{props.remove_suffix}"
            preview_name = example_name
            
            if props.find_prefix and preview_name.startswith(props.find_prefix):
                preview_name = props.replace_prefix + preview_name[len(props.find_prefix):]
            if props.remove_suffix and preview_name.endswith(props.remove_suffix):
                preview_name = preview_name[:-len(props.remove_suffix)]
            
            col = box.column(align=True)
            col.label(text=f'"{example_name}"', icon='RIGHTARROW_THIN')
            col.label(text=f'"{preview_name}"', icon='BONE_DATA')
            
        else:
            # Original hierarchical renaming UI
            layout.separator()
            
            # Main naming options
            col = layout.column(align=True)
            
            # Prefix section
            row = col.row(align=True)
            row.prop(props, "use_prefix", text="", icon='FORWARD')
            sub = row.row(align=True)
            sub.enabled = props.use_prefix
            sub.prop(props, "prefix", text="Prefix")
            
            # Base name section
            col.prop(props, "base_name")
            
            # Numbering section
            row = col.row(align=True)
            row.prop(props, "use_numbering", text="", icon='LINENUMBERS_ON')
            sub = row.row(align=True)
            sub.enabled = props.use_numbering
            sub.prop(props, "digits", text="Digits")
            
            # Suffix section
            col.prop(props, "suffix")
            
            # Preview section
            layout.separator()
            box = layout.box()
            box.label(text="Preview:", icon='HIDE_OFF')
            
            # Generate preview name
            preview_parts = []
            if props.use_prefix and props.prefix:
                preview_parts.append(props.prefix)
            preview_parts.append(props.base_name or "Bone")
            if props.use_numbering:
                number = "1".zfill(props.digits)
                preview_parts.append(number)
            preview_name = "".join(preview_parts)
            if props.suffix:
                preview_name += props.suffix
            
            box.label(text=f'"{preview_name}"', icon='BONE_DATA')
        
        # Action button
        layout.separator()
        if props.use_find_replace:
            layout.operator("object.rename_bones", text="Find & Replace", icon='ZOOM_ALL')
        else:
            layout.operator("object.rename_bones", text="Rename Hierarchically", icon='FILE_REFRESH')
        
        # Help section
        layout.separator()
        box = layout.box()
        box.label(text="Usage:", icon='INFO')
        col = box.column(align=True)
        col.scale_y = 0.8
        
        if props.use_find_replace:
            col.label(text="• Select bones to rename")
            col.label(text="• Enter prefix to find (e.g., 'DEF_')")
            col.label(text="• Enter replacement prefix (e.g., 'MCH_')")
            col.label(text="• Enter suffix to remove (e.g., '.001')")
        else:
            col.label(text="• Select bones in Pose or Edit mode")
            col.label(text="• Renames from parent to child")
            col.label(text="• Toggle icons to enable/disable options")

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
