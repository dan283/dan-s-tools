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
        
        bone = context.active_pose_bone
        if not bone:
            self.report({'ERROR'}, "No active bone selected")
            return {'CANCELLED'}
        
        # Store original state
        original_mode = context.mode
        
        # STEP 1: Create a duplicate of the original shape for use as custom shape
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        original_shape.select_set(True)
        context.view_layer.objects.active = original_shape
        
        # Duplicate the object
        bpy.ops.object.duplicate()
        custom_shape = context.active_object
        custom_shape.name = original_shape.name + "_CustomShape"
        
        # STEP 2: Transform the duplicate to align with the bone
        # Switch to pose mode to get bone info
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
        # Use Blender's built-in matrix creation for reliable orientation
        bone_vector = direction
        
        # Create a rotation matrix that aligns Y-axis to the bone direction
        # This uses the 'track to' approach
        if abs(bone_vector.z) < 0.999:
            up_vector = Vector((0, 0, 1))
        else:
            up_vector = Vector((1, 0, 0))
            
        # Create transformation matrix
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
        
        # Switch to object mode to adjust custom shape positioning
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
        
        # STEP 5: Clean up - delete the custom shape duplicate since it's now assigned to the bone
        bpy.ops.object.select_all(action='DESELECT')
        custom_shape.select_set(True)
        context.view_layer.objects.active = custom_shape
        bpy.ops.object.delete()
        
        # Return to original state
        bpy.ops.object.select_all(action='DESELECT')
        context.view_layer.objects.active = arm
        arm.select_set(True)
        
        # Return to pose mode
        if context.mode != 'POSE' and arm.type == 'ARMATURE':
            bpy.ops.object.mode_set(mode='POSE')
        
        self.report({'INFO'}, f"Custom shape assigned to bone '{bone.name}'. Original object '{original_shape.name}' unchanged.")
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
