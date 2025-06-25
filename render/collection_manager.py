bl_info = {
    "name": "Render Variations Manager",
    "author": "Assistant",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "3D Viewport > N Panel > Render Tools",
    "description": "Manage render variations with collection sets and custom outputs",
    "category": "Render",
}

import bpy
import os
from bpy.props import StringProperty, BoolProperty, CollectionProperty, IntProperty, EnumProperty
from bpy.types import PropertyGroup, Panel, Operator, UIList

# Helper function for camera enumeration
def get_cameras(self, context):
    cameras = []
    for obj in bpy.data.objects:
        if obj.type == 'CAMERA':
            cameras.append((obj.name, obj.name, f"Camera: {obj.name}"))
    if not cameras:
        cameras.append(('NONE', 'No Cameras', 'No cameras found in scene'))
    return cameras

# Property Groups
class RenderSetCollection(PropertyGroup):
    name: StringProperty(name="Collection", default="")
    enabled: BoolProperty(name="Enabled", default=True)

class RenderSet(PropertyGroup):
    name: StringProperty(name="Set Name", default="Render Set")
    collections: CollectionProperty(type=RenderSetCollection)
    output_path: StringProperty(name="Output Path", default="", subtype='DIR_PATH')
    file_prefix: StringProperty(name="File Prefix", default="")
    use_custom_output: BoolProperty(name="Use Custom Output", default=False)
    resolution_scale: IntProperty(name="Resolution Scale %", default=100, min=1, max=500)
    samples: IntProperty(name="Samples Override", default=0, min=0, max=10000)
    use_samples_override: BoolProperty(name="Override Samples", default=False)
    
    # Camera settings
    camera: EnumProperty(
        name="Camera",
        description="Camera to use for this render set",
        items=get_cameras,
    )
    use_custom_camera: BoolProperty(name="Use Custom Camera", default=False)
    
    # Resolution settings
    resolution_x: IntProperty(name="Resolution X", default=1920, min=1, max=10000)
    resolution_y: IntProperty(name="Resolution Y", default=1080, min=1, max=10000)
    use_custom_resolution: BoolProperty(name="Use Custom Resolution", default=False)

class RenderVariationsProperties(PropertyGroup):
    render_sets: CollectionProperty(type=RenderSet)
    active_set_index: IntProperty(name="Active Set", default=0)
    collection_index: IntProperty(name="Active Collection", default=0)
    batch_render_active: BoolProperty(name="Batch Render Active", default=False)
    auto_increment_frame: BoolProperty(name="Auto Increment Frame", default=False)
    frame_step: IntProperty(name="Frame Step", default=1, min=1)

# UI Lists
class RENDERVARIATIONS_UL_sets(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "name", text="", emboss=False, icon='COLLECTION_NEW')
            if item.use_custom_output:
                layout.label(text="", icon='OUTPUT')
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='COLLECTION_NEW')

class RENDERVARIATIONS_UL_collections(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "enabled", text="")
            layout.label(text=item.name, icon='OUTLINER_COLLECTION')
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.prop(item, "enabled", text="")

# Operators
class RENDERVARIATIONS_OT_add_set(Operator):
    bl_idname = "render_variations.add_set"
    bl_label = "Add Render Set"
    bl_description = "Add a new render set"
    
    def execute(self, context):
        props = context.scene.render_variations
        new_set = props.render_sets.add()
        new_set.name = f"Set {len(props.render_sets)}"
        
        # Store current render settings
        new_set.resolution_x = context.scene.render.resolution_x
        new_set.resolution_y = context.scene.render.resolution_y
        
        # Store current camera if available
        if context.scene.camera:
            new_set.camera = context.scene.camera.name
        
        # Add all collections to the new set with current visibility state
        for collection in bpy.data.collections:
            if collection.name not in ['Master Collection']:
                coll_item = new_set.collections.add()
                coll_item.name = collection.name
                coll_item.enabled = not collection.hide_render  # Store render visibility
        
        props.active_set_index = len(props.render_sets) - 1
        return {'FINISHED'}

class RENDERVARIATIONS_OT_remove_set(Operator):
    bl_idname = "render_variations.remove_set"
    bl_label = "Remove Render Set"
    bl_description = "Remove the active render set"
    
    def execute(self, context):
        props = context.scene.render_variations
        if props.render_sets:
            props.render_sets.remove(props.active_set_index)
            props.active_set_index = max(0, props.active_set_index - 1)
        return {'FINISHED'}

class RENDERVARIATIONS_OT_apply_set(Operator):
    bl_idname = "render_variations.apply_set"
    bl_label = "Apply Set"
    bl_description = "Apply the selected render set to scene collections"
    
    def execute(self, context):
        props = context.scene.render_variations
        if not props.render_sets or props.active_set_index >= len(props.render_sets):
            return {'CANCELLED'}
        
        active_set = props.render_sets[props.active_set_index]
        
        # Apply collection visibility
        for coll_item in active_set.collections:
            if coll_item.name in bpy.data.collections:
                collection = bpy.data.collections[coll_item.name]
                collection.hide_viewport = not coll_item.enabled
                collection.hide_render = not coll_item.enabled
        
        # Apply camera settings
        if active_set.use_custom_camera and active_set.camera != 'NONE':
            if active_set.camera in bpy.data.objects:
                context.scene.camera = bpy.data.objects[active_set.camera]
        
        # Apply resolution settings
        if active_set.use_custom_resolution:
            context.scene.render.resolution_x = active_set.resolution_x
            context.scene.render.resolution_y = active_set.resolution_y
        
        # Apply render settings if using custom output
        if active_set.use_custom_output:
            if active_set.output_path:
                context.scene.render.filepath = os.path.join(
                    bpy.path.abspath(active_set.output_path),
                    active_set.file_prefix
                )
            
            # Apply resolution scale
            context.scene.render.resolution_percentage = active_set.resolution_scale
            
            # Apply samples override
            if active_set.use_samples_override and hasattr(context.scene, 'cycles'):
                context.scene.cycles.samples = active_set.samples
        
        self.report({'INFO'}, f"Applied render set: {active_set.name}")
        return {'FINISHED'}

class RENDERVARIATIONS_OT_render_frame(Operator):
    bl_idname = "render_variations.render_frame"
    bl_label = "Render Frame"
    bl_description = "Render current frame with active set"
    
    def execute(self, context):
        # Apply current set first
        bpy.ops.render_variations.apply_set()
        # Render frame
        bpy.ops.render.render('INVOKE_DEFAULT')
        return {'FINISHED'}

class RENDERVARIATIONS_OT_render_animation(Operator):
    bl_idname = "render_variations.render_animation"
    bl_label = "Render Animation"
    bl_description = "Render animation with active set"
    
    def execute(self, context):
        # Apply current set first
        bpy.ops.render_variations.apply_set()
        # Render animation
        bpy.ops.render.render('INVOKE_DEFAULT', animation=True)
        return {'FINISHED'}

class RENDERVARIATIONS_OT_batch_render(Operator):
    bl_idname = "render_variations.batch_render"
    bl_label = "Batch Render All Sets"
    bl_description = "Render current frame with all render sets"
    
    def execute(self, context):
        props = context.scene.render_variations
        original_index = props.active_set_index
        
        for i, render_set in enumerate(props.render_sets):
            props.active_set_index = i
            bpy.ops.render_variations.apply_set()
            
            # Store original filepath
            original_filepath = context.scene.render.filepath
            
            # Set custom filename with set name
            if render_set.use_custom_output and render_set.output_path:
                filename = f"{render_set.file_prefix}_{render_set.name}_f{context.scene.frame_current:04d}"
                context.scene.render.filepath = os.path.join(
                    bpy.path.abspath(render_set.output_path), filename
                )
            else:
                # Use default path with set name
                base_path = os.path.dirname(context.scene.render.filepath)
                filename = f"{render_set.name}_f{context.scene.frame_current:04d}"
                context.scene.render.filepath = os.path.join(base_path, filename)
            
            # Render
            bpy.ops.render.render(write_still=True)
            
            # Restore filepath
            context.scene.render.filepath = original_filepath
        
        # Restore original active set
        props.active_set_index = original_index
        self.report({'INFO'}, f"Batch rendered {len(props.render_sets)} sets")
        return {'FINISHED'}

class RENDERVARIATIONS_OT_refresh_collections(Operator):
    bl_idname = "render_variations.refresh_collections"
    bl_label = "Refresh Collections"
    bl_description = "Refresh collections list for active set"
    
    def execute(self, context):
        props = context.scene.render_variations
        if not props.render_sets or props.active_set_index >= len(props.render_sets):
            return {'CANCELLED'}
        
        active_set = props.render_sets[props.active_set_index]
        
        # Clear existing collections
        active_set.collections.clear()
        
        # Add all current collections with their current visibility state
        for collection in bpy.data.collections:
            if collection.name not in ['Master Collection']:
                coll_item = active_set.collections.add()
                coll_item.name = collection.name
                coll_item.enabled = not collection.hide_render  # Use render visibility
        
        return {'FINISHED'}

class RENDERVARIATIONS_OT_store_current_state(Operator):
    bl_idname = "render_variations.store_current_state"
    bl_label = "Store Current State"
    bl_description = "Store current collection visibility and camera settings to active set"
    
    def execute(self, context):
        props = context.scene.render_variations
        if not props.render_sets or props.active_set_index >= len(props.render_sets):
            return {'CANCELLED'}
        
        active_set = props.render_sets[props.active_set_index]
        
        # Update collection states
        for coll_item in active_set.collections:
            if coll_item.name in bpy.data.collections:
                collection = bpy.data.collections[coll_item.name]
                coll_item.enabled = not collection.hide_render
        
        # Store current camera
        if context.scene.camera:
            active_set.camera = context.scene.camera.name
        
        # Store current resolution
        active_set.resolution_x = context.scene.render.resolution_x
        active_set.resolution_y = context.scene.render.resolution_y
        
        self.report({'INFO'}, f"Stored current state to: {active_set.name}")
        return {'FINISHED'}

class RENDERVARIATIONS_OT_duplicate_set(Operator):
    bl_idname = "render_variations.duplicate_set"
    bl_label = "Duplicate Set"
    bl_description = "Duplicate the active render set"
    
    def execute(self, context):
        props = context.scene.render_variations
        if not props.render_sets or props.active_set_index >= len(props.render_sets):
            return {'CANCELLED'}
        
        active_set = props.render_sets[props.active_set_index]
        new_set = props.render_sets.add()
        
        # Copy properties
        new_set.name = f"{active_set.name}_Copy"
        new_set.output_path = active_set.output_path
        new_set.file_prefix = active_set.file_prefix
        new_set.use_custom_output = active_set.use_custom_output
        new_set.resolution_scale = active_set.resolution_scale
        new_set.samples = active_set.samples
        new_set.use_samples_override = active_set.use_samples_override
        
        # Copy camera settings
        new_set.camera = active_set.camera
        new_set.use_custom_camera = active_set.use_custom_camera
        
        # Copy resolution settings
        new_set.resolution_x = active_set.resolution_x
        new_set.resolution_y = active_set.resolution_y
        new_set.use_custom_resolution = active_set.use_custom_resolution
        
        # Copy collections
        for coll in active_set.collections:
            new_coll = new_set.collections.add()
            new_coll.name = coll.name
            new_coll.enabled = coll.enabled
        
        props.active_set_index = len(props.render_sets) - 1
        return {'FINISHED'}

# Main Panel
class RENDERVARIATIONS_PT_main(Panel):
    bl_label = "Render Tools"
    bl_idname = "RENDERVARIATIONS_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Render Tools"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.render_variations
        
        # Output Path
        box = layout.box()
        box.label(text="Output Settings", icon='OUTPUT')
        box.prop(context.scene.render, "filepath", text="Default Output")
        
        # Quick Render
        box = layout.box()
        box.label(text="Quick Render", icon='RENDER_STILL')
        row = box.row(align=True)
        row.operator("render_variations.render_frame", icon='RENDER_STILL')
        row.operator("render_variations.render_animation", icon='RENDER_ANIMATION')

class RENDERVARIATIONS_PT_sets(Panel):
    bl_label = "Render Sets"
    bl_idname = "RENDERVARIATIONS_PT_sets"
    bl_parent_id = "RENDERVARIATIONS_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Render Tools"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.render_variations
        
        # Render Sets List
        row = layout.row()
        row.template_list("RENDERVARIATIONS_UL_sets", "", props, "render_sets", 
                         props, "active_set_index", rows=3)
        
        col = row.column(align=True)
        col.operator("render_variations.add_set", icon='ADD', text="")
        col.operator("render_variations.remove_set", icon='REMOVE', text="")
        col.separator()
        col.operator("render_variations.duplicate_set", icon='DUPLICATE', text="")
        
        # Active Set Operations
        if props.render_sets and props.active_set_index < len(props.render_sets):
            active_set = props.render_sets[props.active_set_index]
            
            # Set Settings
            box = layout.box()
            box.prop(active_set, "name")
            box.prop(active_set, "use_custom_output")
            
            if active_set.use_custom_output:
                box.prop(active_set, "output_path")
                box.prop(active_set, "file_prefix")
                box.prop(active_set, "resolution_scale")
                
                row = box.row()
                row.prop(active_set, "use_samples_override")
                if active_set.use_samples_override:
                    row.prop(active_set, "samples", text="")
            
            # Camera Settings
            box.prop(active_set, "use_custom_camera")
            if active_set.use_custom_camera:
                box.prop(active_set, "camera", text="Camera")
            
            # Resolution Settings
            box.prop(active_set, "use_custom_resolution")
            if active_set.use_custom_resolution:
                row = box.row()
                row.prop(active_set, "resolution_x", text="X")
                row.prop(active_set, "resolution_y", text="Y")
            
            # Apply Set
            row = layout.row(align=True)
            row.operator("render_variations.apply_set", icon='CHECKMARK')
            row.operator("render_variations.store_current_state", icon='FILE_CACHE', text="Store")
            
            # Batch Render
            layout.operator("render_variations.batch_render", icon='RENDER_RESULT')

class RENDERVARIATIONS_PT_collections(Panel):
    bl_label = "Collections"
    bl_idname = "RENDERVARIATIONS_PT_collections"
    bl_parent_id = "RENDERVARIATIONS_PT_sets"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Render Tools"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.render_variations
        
        if props.render_sets and props.active_set_index < len(props.render_sets):
            active_set = props.render_sets[props.active_set_index]
            
            # Collections List - Fixed to use proper integer property
            row = layout.row()
            row.template_list("RENDERVARIATIONS_UL_collections", "", active_set, "collections",
                             props, "collection_index", rows=5)
            
            # Refresh Collections
            layout.operator("render_variations.refresh_collections", icon='FILE_REFRESH')
        else:
            layout.label(text="No active render set", icon='INFO')

class RENDERVARIATIONS_PT_all_collections(Panel):
    bl_label = "All Collections"
    bl_idname = "RENDERVARIATIONS_PT_all_collections"
    bl_parent_id = "RENDERVARIATIONS_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Render Tools"
    
    def draw(self, context):
        layout = self.layout
        
        # Show all collections with toggle
        for collection in bpy.data.collections:
            if collection.name != 'Master Collection':
                row = layout.row()
                row.prop(collection, "hide_viewport", text="", icon='HIDE_OFF' if not collection.hide_viewport else 'HIDE_ON')
                row.prop(collection, "hide_render", text="", icon='RESTRICT_RENDER_OFF' if not collection.hide_render else 'RESTRICT_RENDER_ON')
                row.label(text=collection.name, icon='OUTLINER_COLLECTION')

# Registration
classes = (
    RenderSetCollection,
    RenderSet,
    RenderVariationsProperties,
    RENDERVARIATIONS_UL_sets,
    RENDERVARIATIONS_UL_collections,
    RENDERVARIATIONS_OT_add_set,
    RENDERVARIATIONS_OT_remove_set,
    RENDERVARIATIONS_OT_apply_set,
    RENDERVARIATIONS_OT_render_frame,
    RENDERVARIATIONS_OT_render_animation,
    RENDERVARIATIONS_OT_batch_render,
    RENDERVARIATIONS_OT_refresh_collections,
    RENDERVARIATIONS_OT_store_current_state,
    RENDERVARIATIONS_OT_duplicate_set,
    RENDERVARIATIONS_PT_main,
    RENDERVARIATIONS_PT_sets,
    RENDERVARIATIONS_PT_collections,
    RENDERVARIATIONS_PT_all_collections,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.render_variations = bpy.props.PointerProperty(type=RenderVariationsProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.render_variations

if __name__ == "__main__":
    register()
