import bpy

class POSE_OT_CopyConstraints(bpy.types.Operator):
    bl_idname = "pose.copy_constraints_with_drivers"
    bl_label = "Copy Constraints with Drivers"
    bl_description = "Copy all constraints and their drivers from active bone to selected bones"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Basic checks
        if context.mode != 'POSE':
            self.report({'ERROR'}, "Must be in Pose Mode")
            return {'CANCELLED'}
        
        active_bone = context.active_pose_bone
        if not active_bone:
            self.report({'ERROR'}, "No active bone")
            return {'CANCELLED'}
        
        selected_bones = [bone for bone in context.selected_pose_bones if bone != active_bone]
        if not selected_bones:
            self.report({'ERROR'}, "Select target bones (other than active)")
            return {'CANCELLED'}
        
        if not active_bone.constraints:
            self.report({'WARNING'}, "Active bone has no constraints")
            return {'CANCELLED'}
        
        armature = context.object
        
        # Copy constraints and drivers for each target bone
        for target_bone in selected_bones:
            self.copy_all_constraints_and_drivers(armature, active_bone, target_bone)
        
        drivers_count = self.count_constraint_drivers(armature, selected_bones)
        
        self.report({'INFO'}, f"Copied {len(active_bone.constraints)} constraints to {len(selected_bones)} bones with {drivers_count} drivers")
        return {'FINISHED'}
    
    def copy_all_constraints_and_drivers(self, armature, src_bone, dest_bone):
        """Copy all constraints and their drivers from source to destination bone"""
        
        # Clear existing constraints
        while dest_bone.constraints:
            dest_bone.constraints.remove(dest_bone.constraints[0])
        
        # Copy each constraint
        for src_constraint in src_bone.constraints:
            # Create new constraint
            new_constraint = dest_bone.constraints.new(type=src_constraint.type)
            
            # Copy all constraint properties
            self.copy_constraint_properties(src_constraint, new_constraint)
        
        # Copy ALL drivers that belong to source bone's constraints
        self.copy_all_constraint_drivers(armature, src_bone, dest_bone)
    
    def copy_constraint_properties(self, src_constraint, dest_constraint):
        """Copy all properties from source to destination constraint"""
        
        # Properties to skip
        skip_props = {'rna_type', 'type', 'is_valid', 'error_location', 'error_rotation'}
        
        # Copy basic properties
        for prop in src_constraint.bl_rna.properties:
            if prop.identifier in skip_props or prop.is_readonly or prop.type == 'COLLECTION':
                continue
            
            try:
                value = getattr(src_constraint, prop.identifier)
                setattr(dest_constraint, prop.identifier, value)
            except:
                continue
        
        # Handle targets collection (for armature constraints, etc.)
        if hasattr(src_constraint, 'targets'):
            # Clear existing targets
            while dest_constraint.targets:
                dest_constraint.targets.remove(dest_constraint.targets[0])
            
            # Copy each target
            for src_target in src_constraint.targets:
                new_target = dest_constraint.targets.new()
                
                # Copy target properties
                for prop in src_target.bl_rna.properties:
                    if prop.identifier == 'rna_type' or prop.is_readonly:
                        continue
                    
                    try:
                        value = getattr(src_target, prop.identifier)
                        setattr(new_target, prop.identifier, value)
                    except:
                        continue
    
    def copy_all_constraint_drivers(self, armature, src_bone, dest_bone):
        """Copy ALL drivers from source bone's constraints to destination bone's constraints"""
        
        if not armature.animation_data or not armature.animation_data.drivers:
            return
        
        # Build the base path for source bone's constraints
        src_base_path = f'pose.bones["{src_bone.name}"].constraints'
        dest_base_path = f'pose.bones["{dest_bone.name}"].constraints'
        
        # Find ALL drivers that start with the source constraint path
        drivers_to_copy = []
        for driver in armature.animation_data.drivers:
            if driver.data_path and driver.data_path.startswith(src_base_path):
                drivers_to_copy.append(driver)
        
        print(f"Found {len(drivers_to_copy)} drivers to copy from {src_bone.name} to {dest_bone.name}")
        
        # Copy each driver
        for src_driver in drivers_to_copy:
            # Create destination path by replacing the bone name
            dest_path = src_driver.data_path.replace(src_base_path, dest_base_path)
            
            print(f"Copying: {src_driver.data_path} -> {dest_path} (array_index: {src_driver.array_index})")
            
            try:
                # Handle array index properly
                array_index = src_driver.array_index
                
                # Remove existing driver if it exists
                self.remove_existing_driver(armature, dest_path, array_index)
                
                # Create new driver - try with array index first, fallback to no array index
                new_driver = None
                try:
                    if array_index == -1:
                        new_driver = armature.driver_add(dest_path)
                    else:
                        new_driver = armature.driver_add(dest_path, array_index)
                except (TypeError, RuntimeError) as e:
                    # If array index fails, try without it
                    if "not an array" in str(e) and array_index != -1:
                        print(f"  Retrying without array index...")
                        new_driver = armature.driver_add(dest_path)
                    else:
                        raise e
                
                if new_driver:
                    self.copy_driver_data(src_driver, new_driver, src_bone.name, dest_bone.name)
                    print(f"✓ Successfully copied driver")
                else:
                    print(f"✗ Failed to create driver")
                    
            except Exception as e:
                print(f"✗ Error copying driver: {e}")
    
    def remove_existing_driver(self, armature, data_path, array_index):
        """Remove existing driver if it exists"""
        if not armature.animation_data or not armature.animation_data.drivers:
            return
        
        drivers_to_remove = []
        for driver in armature.animation_data.drivers:
            if driver.data_path == data_path and driver.array_index == array_index:
                drivers_to_remove.append(driver)
        
        for driver in drivers_to_remove:
            armature.animation_data.drivers.remove(driver)
    
    def copy_driver_data(self, src_driver, dest_driver, src_bone_name, dest_bone_name):
        """Copy all driver data from source to destination"""
        
        # Copy basic driver properties
        dest_driver.driver.type = src_driver.driver.type
        dest_driver.driver.expression = src_driver.driver.expression
        dest_driver.driver.use_self = src_driver.driver.use_self
        
        # Copy variables
        for src_var in src_driver.driver.variables:
            new_var = dest_driver.driver.variables.new()
            new_var.name = src_var.name
            new_var.type = src_var.type
            
            # Copy variable targets
            for i, src_target in enumerate(src_var.targets):
                if i < len(new_var.targets):
                    dest_target = new_var.targets[i]
                    dest_target.id = src_target.id
                    dest_target.id_type = src_target.id_type
                    
                    # Update data path if it references the source bone
                    if hasattr(src_target, 'data_path') and src_target.data_path:
                        new_data_path = src_target.data_path
                        if f'["{src_bone_name}"]' in new_data_path:
                            new_data_path = new_data_path.replace(f'["{src_bone_name}"]', f'["{dest_bone_name}"]')
                        dest_target.data_path = new_data_path
                    
                    # Copy other target properties
                    for prop_name in ['bone_target', 'transform_type', 'transform_space']:
                        if hasattr(src_target, prop_name):
                            try:
                                setattr(dest_target, prop_name, getattr(src_target, prop_name))
                            except:
                                pass
        
        # Copy keyframe points for keyframe-based drivers
        if hasattr(src_driver, 'keyframe_points') and src_driver.keyframe_points:
            for src_point in src_driver.keyframe_points:
                dest_driver.keyframe_points.insert(src_point.co[0], src_point.co[1])
    
    def count_constraint_drivers(self, armature, bones):
        """Count drivers on constraint properties for given bones"""
        if not armature.animation_data or not armature.animation_data.drivers:
            return 0
        
        count = 0
        for bone in bones:
            bone_constraints_path = f'pose.bones["{bone.name}"].constraints'
            for driver in armature.animation_data.drivers:
                if driver.data_path and driver.data_path.startswith(bone_constraints_path):
                    count += 1
        return count

class POSE_PT_ConstraintToolsPanel(bpy.types.Panel):
    bl_label = "Constraint Tools"
    bl_idname = "POSE_PT_constraint_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tools"
    bl_context = "posemode"
    
    def draw(self, context):
        layout = self.layout
        
        if context.mode != 'POSE':
            layout.label(text="Switch to Pose Mode")
            return
        
        active_bone = context.active_pose_bone
        if not active_bone:
            layout.label(text="No active bone")
            return
        
        selected_bones = [bone for bone in context.selected_pose_bones if bone != active_bone]
        
        col = layout.column(align=True)
        col.label(text=f"Source: {active_bone.name}")
        col.label(text=f"Constraints: {len(active_bone.constraints)}")
        col.label(text=f"Targets: {len(selected_bones)}")
        
        layout.separator()
        
        op = layout.operator("pose.copy_constraints_with_drivers", 
                           text="Copy Constraints + Drivers")
        
        if len(active_bone.constraints) == 0:
            layout.label(text="No constraints to copy", icon='INFO')
        elif len(selected_bones) == 0:
            layout.label(text="Select target bones", icon='INFO')

def register():
    bpy.utils.register_class(POSE_OT_CopyConstraints)
    bpy.utils.register_class(POSE_PT_ConstraintToolsPanel)

def unregister():
    bpy.utils.unregister_class(POSE_PT_ConstraintToolsPanel)
    bpy.utils.unregister_class(POSE_OT_CopyConstraints)

if __name__ == "__main__":
    register()
