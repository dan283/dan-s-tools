bl_info = {
    "name": "Custom Bone Shape Manager",
    "author": "Assistant",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > N-Panel > Bone Shape",
    "description": "Assign custom shapes to bones with proper transforms",
    "category": "Rigging",
}

import bpy
from bpy.props import PointerProperty, StringProperty, BoolProperty, FloatProperty
from bpy.types import Panel, Operator, PropertyGroup
from mathutils import Matrix, Vector


def get_or_create_wgt_collection(context):
    """Get or create the WGT collection for custom bone shapes"""
    collection_name = context.scene.bone_shape_props.collection_name
    
    if collection_name in bpy.data.collections:
        return bpy.data.collections[collection_name]
    
    # Create new collection
    collection = bpy.data.collections.new(collection_name)
    context.scene.collection.children.link(collection)
    
    # Hide it from viewport by default
    collection.hide_viewport = True
    
    return collection


def get_shape_name(bone_name):
    """Generate widget name from bone name"""
    return f"WGT-{bone_name}"


def match_bone_transform(armature, bone, shape_obj, use_custom_transform=False, use_bone_scale=False):
    """
    Transform the shape object to match the bone's world transform.
    Based on the orient_bone_shapes addon logic.
    This transforms the widget so the shape appears in the same place.
    """
    if use_custom_transform and bone.custom_shape_transform:
        # Use the custom transform bone if specified
        transform_bone = bone.custom_shape_transform
    else:
        transform_bone = bone
    
    # Get the bone's world matrix
    mat = armature.matrix_world @ transform_bone.matrix
    
    # Invert the matrix to get transform from world to bone space
    mat.invert()
    
    # Transform the shape object from world space to bone space
    if use_bone_scale:
        # Scale by bone length if requested
        from mathutils import Matrix
        shape_obj.matrix_world = Matrix.Scale(1/transform_bone.length, 4) @ mat @ shape_obj.matrix_world
    else:
        shape_obj.matrix_world = mat @ shape_obj.matrix_world
    
    # Now apply all transforms to bake them into the mesh
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    shape_obj.select_set(True)
    bpy.context.view_layer.objects.active = shape_obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    
    # Transform back to world space at the bone's position
    if use_bone_scale:
        shape_obj.matrix_world = armature.matrix_world @ transform_bone.matrix @ Matrix.Scale(transform_bone.length, 4)
    else:
        shape_obj.matrix_world = armature.matrix_world @ transform_bone.matrix
    
    # Clean up selection
    shape_obj.select_set(False)
    armature.select_set(True)


def duplicate_shape_to_collection(source_obj, target_name, collection):
    """Duplicate an object and move it to the WGT collection"""
    # Duplicate the object
    new_obj = source_obj.copy()
    new_obj.data = source_obj.data.copy()
    new_obj.name = target_name
    
    # Link to collection
    collection.objects.link(new_obj)
    
    # Remove from all other collections
    for coll in new_obj.users_collection:
        if coll != collection:
            coll.objects.unlink(new_obj)
    
    return new_obj


class BONESHAPE_OT_AssignShape(Operator):
    bl_idname = "boneshape.assign_shape"
    bl_label = "Assign Custom Bone Shape"
    bl_description = "Assign the selected object as a custom shape to the selected bone(s)"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return (context.mode == 'POSE' and 
                context.active_object and 
                context.active_object.type == 'ARMATURE' and
                context.selected_pose_bones)
    
    def execute(self, context):
        props = context.scene.bone_shape_props
        
        if not props.shape_object:
            self.report({'WARNING'}, "No shape object selected")
            return {'CANCELLED'}
        
        shape_obj = props.shape_object
        armature = context.active_object
        selected_bones = context.selected_pose_bones
        
        if not selected_bones:
            self.report({'WARNING'}, "No bones selected")
            return {'CANCELLED'}
        
        # Get or create WGT collection
        wgt_collection = get_or_create_wgt_collection(context)
        
        # Store the current mode to restore later
        original_mode = context.mode
        
        assigned_count = 0
        
        for bone in selected_bones:
            # Generate name for this bone's widget
            widget_name = get_shape_name(bone.name)
            
            # Check if widget already exists
            if widget_name in bpy.data.objects:
                widget_obj = bpy.data.objects[widget_name]
                self.report({'INFO'}, f"Reusing existing widget: {widget_name}")
            else:
                # Duplicate shape object to WGT collection
                widget_obj = duplicate_shape_to_collection(shape_obj, widget_name, wgt_collection)
            
            # Assign the custom shape first
            bone.custom_shape = widget_obj
            bone.use_custom_shape_bone_size = props.use_bone_scale
            
            # Match bone transform if requested
            if props.match_transforms:
                match_bone_transform(
                    armature, 
                    bone, 
                    widget_obj,
                    props.use_custom_transform,
                    props.use_bone_scale
                )
            
            # Apply additional settings
            if props.custom_scale != 1.0:
                bone.custom_shape_scale_xyz = (props.custom_scale, props.custom_scale, props.custom_scale)
            
            if props.wireframe:
                bone.show_wire = True
            
            assigned_count += 1
        
        # Return to pose mode if we switched out
        if context.mode != 'POSE':
            bpy.ops.object.mode_set(mode='POSE')
        
        self.report({'INFO'}, f"Assigned custom shape to {assigned_count} bone(s)")
        
        # Update viewport
        context.view_layer.update()
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}


class BONESHAPE_OT_ClearShape(Operator):
    bl_idname = "boneshape.clear_shape"
    bl_label = "Clear Custom Shape"
    bl_description = "Remove custom shape from selected bone(s)"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return (context.mode == 'POSE' and 
                context.active_object and 
                context.active_object.type == 'ARMATURE' and
                context.selected_pose_bones)
    
    def execute(self, context):
        selected_bones = context.selected_pose_bones
        
        cleared_count = 0
        for bone in selected_bones:
            if bone.custom_shape:
                bone.custom_shape = None
                cleared_count += 1
        
        self.report({'INFO'}, f"Cleared {cleared_count} custom shape(s)")
        return {'FINISHED'}


class BONESHAPE_OT_MatchTransform(Operator):
    bl_idname = "boneshape.match_transform"
    bl_label = "Match Bone Transform"
    bl_description = "Update the widget object to match current bone transform"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return (context.mode == 'POSE' and 
                context.active_object and 
                context.active_object.type == 'ARMATURE' and
                context.active_pose_bone and
                context.active_pose_bone.custom_shape)
    
    def execute(self, context):
        props = context.scene.bone_shape_props
        armature = context.active_object
        selected_bones = context.selected_pose_bones
        
        updated_count = 0
        
        for bone in selected_bones:
            if bone.custom_shape:
                match_bone_transform(
                    armature,
                    bone,
                    bone.custom_shape,
                    props.use_custom_transform,
                    props.use_bone_scale
                )
                updated_count += 1
        
        self.report({'INFO'}, f"Updated {updated_count} widget transform(s)")
        return {'FINISHED'}


class BONESHAPE_OT_EditShape(Operator):
    bl_idname = "boneshape.edit_shape"
    bl_label = "Edit Shape"
    bl_description = "Enter edit mode for the custom shape of the active bone"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return (context.mode == 'POSE' and 
                context.active_pose_bone and 
                context.active_pose_bone.custom_shape)
    
    def execute(self, context):
        bone = context.active_pose_bone
        shape_obj = bone.custom_shape
        
        if not shape_obj:
            self.report({'WARNING'}, "No custom shape assigned")
            return {'CANCELLED'}
        
        # Switch to object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Deselect all
        bpy.ops.object.select_all(action='DESELECT')
        
        # Select and activate the shape object
        shape_obj.select_set(True)
        context.view_layer.objects.active = shape_obj
        
        # Enter edit mode
        bpy.ops.object.mode_set(mode='EDIT')
        
        return {'FINISHED'}


class BONESHAPE_OT_ToggleCollection(Operator):
    bl_idname = "boneshape.toggle_collection"
    bl_label = "Toggle Widget Collection"
    bl_description = "Show/hide the widget collection in viewport"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.bone_shape_props
        collection_name = props.collection_name
        
        if collection_name not in bpy.data.collections:
            self.report({'WARNING'}, "Widget collection not found")
            return {'CANCELLED'}
        
        collection = bpy.data.collections[collection_name]
        collection.hide_viewport = not collection.hide_viewport
        
        status = "hidden" if collection.hide_viewport else "visible"
        self.report({'INFO'}, f"Widget collection {status}")
        
        return {'FINISHED'}


class BoneShapeProperties(PropertyGroup):
    shape_object: PointerProperty(
        name="Shape Object",
        description="Object to use as custom bone shape",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'MESH'
    )
    
    collection_name: StringProperty(
        name="Collection",
        description="Name of the collection to store widget objects",
        default="WGT_Widgets"
    )
    
    match_transforms: BoolProperty(
        name="Match Bone Transform",
        description="Transform the widget to match the bone's position/rotation",
        default=True
    )
    
    use_custom_transform: BoolProperty(
        name="Use Custom Transform Bone",
        description="Use the bone's custom shape transform if set",
        default=False
    )
    
    use_bone_scale: BoolProperty(
        name="Scale to Bone Length",
        description="Scale the widget by bone length",
        default=False
    )
    
    custom_scale: FloatProperty(
        name="Scale",
        description="Additional scale factor for the widget",
        default=1.0,
        min=0.01,
        max=10.0,
        step=10
    )
    
    wireframe: BoolProperty(
        name="Wireframe",
        description="Display bone as wireframe",
        default=False
    )


class BONESHAPE_PT_MainPanel(Panel):
    bl_label = "Bone Shape Manager"
    bl_idname = "BONESHAPE_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Bone Shape"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.bone_shape_props
        
        # Shape selection
        box = layout.box()
        box.label(text="Custom Shape:", icon='MESH_CUBE')
        box.prop(props, "shape_object", text="")
        
        # Main assign button
        col = box.column(align=True)
        col.scale_y = 1.3
        col.operator("boneshape.assign_shape", icon='CHECKMARK')
        
        # Settings
        box = layout.box()
        box.label(text="Settings:", icon='SETTINGS')
        box.prop(props, "match_transforms")
        
        if props.match_transforms:
            box.prop(props, "use_custom_transform")
        
        box.prop(props, "use_bone_scale")
        box.prop(props, "custom_scale", slider=True)
        box.prop(props, "wireframe")
        
        # Utilities
        box = layout.box()
        box.label(text="Utilities:", icon='TOOL_SETTINGS')
        
        col = box.column(align=True)
        col.operator("boneshape.match_transform", icon='CON_TRANSFORM')
        col.operator("boneshape.edit_shape", icon='EDITMODE_HLT')
        col.operator("boneshape.clear_shape", icon='X')
        
        # Collection management
        box = layout.box()
        box.label(text="Collection:", icon='OUTLINER_COLLECTION')
        box.prop(props, "collection_name", text="")
        box.operator("boneshape.toggle_collection", icon='HIDE_OFF')
        
        # Info
        if context.mode == 'POSE' and context.active_pose_bone:
            bone = context.active_pose_bone
            box = layout.box()
            box.label(text=f"Active: {bone.name}", icon='BONE_DATA')
            
            if bone.custom_shape:
                box.label(text=f"Shape: {bone.custom_shape.name}")
            else:
                box.label(text="No custom shape", icon='INFO')


classes = (
    BoneShapeProperties,
    BONESHAPE_OT_AssignShape,
    BONESHAPE_OT_ClearShape,
    BONESHAPE_OT_MatchTransform,
    BONESHAPE_OT_EditShape,
    BONESHAPE_OT_ToggleCollection,
    BONESHAPE_PT_MainPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.bone_shape_props = bpy.props.PointerProperty(type=BoneShapeProperties)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.bone_shape_props


if __name__ == "__main__":
    register()
