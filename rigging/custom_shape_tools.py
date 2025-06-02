import bpy
from mathutils import Matrix, Vector

class CustomShapeProperties(bpy.types.PropertyGroup):
    custom_shape: bpy.props.PointerProperty(
        name="Custom Shape",
        type=bpy.types.Object,
        description="Mesh object to use as custom shape"
    )

class OBJECT_PT_CustomShapePanel(bpy.types.Panel):
    bl_label = "Custom Shape Aligner"
    bl_idname = "OBJECT_PT_custom_shape_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "CSA01"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.custom_shape_props
        layout.prop(props, "custom_shape")
        layout.operator("object.assign_custom_shape", text="Assign Custom Shape")

class OBJECT_OT_AssignCustomShape(bpy.types.Operator):
    bl_idname = "object.assign_custom_shape"
    bl_label = "Assign Custom Shape to Bone"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.custom_shape_props
        original_shape = props.custom_shape
        arm = context.object
        
        if not original_shape or arm.type != 'ARMATURE' or context.mode != 'POSE':
            self.report({'ERROR'}, "Select an armature in Pose Mode and a mesh shape")
            return {'CANCELLED'}
        
        # Get selected bones - if none selected, use active bone
        selected_bones = [bone for bone in context.selected_pose_bones if bone]
        if not selected_bones:
            if context.active_pose_bone:
                selected_bones = [context.active_pose_bone]
            else:
                self.report({'ERROR'}, "No bones selected")
                return {'CANCELLED'}
        
        # Store original state
        original_mode = context.mode
        bones_processed = 0
        
        # Process each selected bone
        for bone in selected_bones:
            # STEP 1: Create a duplicate of the original shape for use as custom shape
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            original_shape.select_set(True)
            context.view_layer.objects.active = original_shape
            
            # Duplicate the object
            bpy.ops.object.duplicate()
            custom_shape = context.active_object
            custom_shape.name = original_shape.name + "_" + bone.name + "_CustomShape"
            
            # STEP 2: Get bone info (switch to pose mode temporarily)
            bpy.ops.object.select_all(action='DESELECT')
            context.view_layer.objects.active = arm
            arm.select_set(True)
            bpy.ops.object.mode_set(mode='POSE')
            
            # Get bone info in armature local space
            head = bone.head
            tail = bone.tail
            center = (head + tail) / 2
            direction = (tail - head).normalized()
            length = (tail - head).length
            
            # Create rotation matrix to align Y-axis with bone direction
            bone_vector = direction
            rotation_matrix = bone_vector.to_track_quat('Y', 'Z').to_matrix().to_4x4()
            
            # STEP 3: Transform the custom shape duplicate
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            context.view_layer.objects.active = custom_shape
            custom_shape.select_set(True)
            
            # Get shape's bounding box in local space
            bbox = [Vector(v) for v in custom_shape.bound_box]
            y_min = min(v.y for v in bbox)
            y_max = max(v.y for v in bbox)
            mesh_y_size = y_max - y_min if (y_max - y_min) != 0 else 1.0
            scale_factor = length / mesh_y_size
            
            # Position the custom shape to match bone in armature local space
            custom_shape.location = center
            custom_shape.rotation_euler = rotation_matrix.to_euler()
            custom_shape.scale = (scale_factor, scale_factor, scale_factor)
            
            # Apply the transform to make it permanent
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            
            # Reset custom shape transforms after applying
            custom_shape.location = (0, 0, 0)
            custom_shape.rotation_euler = (0, 0, 0)
            custom_shape.scale = (1, 1, 1)
            
            # STEP 4: Assign the custom shape to the bone
            bpy.ops.object.select_all(action='DESELECT')
            context.view_layer.objects.active = arm
            arm.select_set(True)
            bpy.ops.object.mode_set(mode='POSE')
            
            # Assign custom shape
            bone.custom_shape = custom_shape
            bone.use_custom_shape_bone_size = True
            
            # Calculate the transformation matrix for proper alignment
            bone_matrix = arm.matrix_world @ bone.matrix
            inverse_bone_matrix = bone_matrix.inverted()
            
            # STEP 5: Switch to object mode and adjust custom shape positioning
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            context.view_layer.objects.active = custom_shape
            custom_shape.select_set(True)
            
            # Transform the custom shape to account for bone matrix and scaling
            custom_shape.matrix_world = Matrix.Scale(1/bone.length, 4) @ inverse_bone_matrix @ custom_shape.matrix_world
            
            # Apply the transform
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            
            # Set final position with bone length scaling
            custom_shape.matrix_world = arm.matrix_world @ bone.matrix @ Matrix.Scale(bone.length, 4)
            
            # STEP 6: Clean up - delete the custom shape duplicate since it's now assigned to the bone
            bpy.ops.object.select_all(action='DESELECT')
            custom_shape.select_set(True)
            context.view_layer.objects.active = custom_shape
            bpy.ops.object.delete()
            
            # Ensure armature is active after deletion
            bpy.ops.object.select_all(action='DESELECT')
            context.view_layer.objects.active = arm
            arm.select_set(True)
            
            bones_processed += 1
        
        # Return to original state
        bpy.ops.object.select_all(action='DESELECT')
        context.view_layer.objects.active = arm
        arm.select_set(True)
        
        # Return to pose mode
        if context.mode != 'POSE' and arm.type == 'ARMATURE':
            bpy.ops.object.mode_set(mode='POSE')
        
        # Re-select the originally selected bones
        for bone in selected_bones:
            bone.bone.select = True
        
        if bones_processed == 1:
            self.report({'INFO'}, f"Custom shape assigned to bone '{selected_bones[0].name}'. Original object '{original_shape.name}' unchanged.")
        else:
            self.report({'INFO'}, f"Custom shape assigned to {bones_processed} bones. Original object '{original_shape.name}' unchanged.")
        
        return {'FINISHED'}

classes = (
    CustomShapeProperties,
    OBJECT_PT_CustomShapePanel,
    OBJECT_OT_AssignCustomShape,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.custom_shape_props = bpy.props.PointerProperty(type=CustomShapeProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.custom_shape_props

if __name__ == "__main__":
    register()
