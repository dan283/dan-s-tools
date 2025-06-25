bl_info = {
    "name": "Render Variations Manager",
    "author": "Assistant",
    "version": (1, 1, 0),
    "blender": (3, 0, 0),
    "location": "3D Viewport > N Panel > Render Tools",
    "description": "Manage render variations with collections, shaders, and custom outputs",
    "category": "Render",
}

import bpy
import os
from bpy.props import StringProperty, BoolProperty, CollectionProperty, IntProperty, EnumProperty, PointerProperty
from bpy.types import PropertyGroup, Panel, Operator, UIList

# Helper functions
def get_cameras(self, context):
    cameras = []
    for obj in bpy.data.objects:
        if obj.type == 'CAMERA':
            cameras.append((obj.name, obj.name, f"Camera: {obj.name}"))
    if not cameras:
        cameras.append(('NONE', 'No Cameras', 'No cameras found in scene'))
    return cameras

def get_materials(self, context):
    materials = [('NONE', 'No Override', 'Use original materials')]
    for mat in bpy.data.materials:
        materials.append((mat.name, mat.name, f"Material: {mat.name}"))
    return materials

# Property Groups
class RenderSetCollection(PropertyGroup):
    name: StringProperty(name="Collection", default="")
    enabled: BoolProperty(name="Enabled", default=True)
    use_material_override: BoolProperty(name="Override Material", default=True)

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
    
    # Shader override settings
    override_material: EnumProperty(
        name="Override Material",
        description="Material to apply to all objects in enabled collections",
        items=get_materials,
    )
    use_material_override: BoolProperty(name="Use Material Override", default=False)
    
    # Store original materials for restoration
    original_materials: CollectionProperty(type=PropertyGroup)

class RenderVariationsProperties(PropertyGroup):
    render_sets: CollectionProperty(type=RenderSet)
    active_set_index: IntProperty(name="Active Set", default=0)
    collection_index: IntProperty(name="Active Collection", default=0)

# UI Lists
class RENDERVARIATIONS_UL_sets(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "name", text="", emboss=False, icon='COLLECTION_NEW')
            if item.use_custom_output:
                layout.label(text="", icon='OUTPUT')
            if item.use_material_override:
                layout.label(text="", icon='MATERIAL')
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='COLLECTION_NEW')

class RENDERVARIATIONS_UL_collections(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "enabled", text="")
            layout.label(text=item.name, icon='OUTLINER_COLLECTION')
            # Show material override toggle if parent set has material override enabled
            parent_set = None
            props = context.scene.render_variations
            if props.render_sets and props.active_set_index < len(props.render_sets):
                parent_set = props.render_sets[props.active_set_index]
            
            if parent_set and parent_set.use_material_override:
                layout.prop(item, "use_material_override", text="", icon='MATERIAL')
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.prop(item, "enabled", text="")

# Utility functions for material management
def store_original_materials(render_set):
    """Store original materials before override"""
    render_set.original_materials.clear()
    
    for coll_item in render_set.collections:
        if (coll_item.enabled and 
            coll_item.use_material_override and 
            coll_item.name in bpy.data.collections):
            
            collection = bpy.data.collections[coll_item.name]
            for obj in collection.all_objects:
                if obj.type == 'MESH' and obj.data.materials:
                    for slot_idx, slot in enumerate(obj.material_slots):
                        if slot.material:
                            # Store: object_name|slot_index|material_name
                            mat_info = render_set.original_materials.add()
                            mat_info.name = f"{obj.name}|{slot_idx}|{slot.material.name}"

def apply_material_override(render_set):
    """Apply material override to objects in enabled collections"""
    if not render_set.use_material_override or render_set.override_material == 'NONE':
        return
    
    if render_set.override_material not in bpy.data.materials:
        return
    
    override_mat = bpy.data.materials[render_set.override_material]
    
    # Store originals first
    store_original_materials(render_set)
    
    # Apply override only to collections that have material override enabled
    for coll_item in render_set.collections:
        if (coll_item.enabled and 
            coll_item.use_material_override and 
            coll_item.name in bpy.data.collections):
            
            collection = bpy.data.collections[coll_item.name]
            for obj in collection.all_objects:
                if obj.type == 'MESH' and obj.data.materials:
                    for slot in obj.material_slots:
                        if slot.material:
                            slot.material = override_mat

def restore_original_materials(render_set):
    """Restore original materials from stored data"""
    for mat_info in render_set.original_materials:
        parts = mat_info.name.split('|')
        if len(parts) == 3:
            obj_name, slot_idx, mat_name = parts
            
            if obj_name in bpy.data.objects and mat_name in bpy.data.materials:
                obj = bpy.data.objects[obj_name]
                slot_index = int(slot_idx)
                
                if slot_index < len(obj.material_slots):
                    obj.material_slots[slot_index].material = bpy.data.materials[mat_name]

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
                coll_item.enabled = not collection.hide_render
        
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
    bl_description = "Apply the selected render set to scene"
    
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
        
        # Apply material override
        apply_material_override(active_set)
        
        self.report({'INFO'}, f"Applied render set: {active_set.name}")
        return {'FINISHED'}

class RENDERVARIATIONS_OT_restore_materials(Operator):
    bl_idname = "render_variations.restore_materials"
    bl_label = "Restore Materials"
    bl_description = "Restore original materials for the active set"
    
    def execute(self, context):
        props = context.scene.render_variations
        if not props.render_sets or props.active_set_index >= len(props.render_sets):
            return {'CANCELLED'}
        
        active_set = props.render_sets[props.active_set_index]
        restore_original_materials(active_set)
        
        self.report({'INFO'}, f"Restored materials for: {active_set.name}")
        return {'FINISHED'}

class RENDERVARIATIONS_OT_render_frame(Operator):
    bl_idname = "render_variations.render_frame"
    bl_label = "Render Frame"
    bl_description = "Render current frame with active set"
    
    def execute(self, context):
        bpy.ops.render_variations.apply_set()
        bpy.ops.render.render('INVOKE_DEFAULT')
        return {'FINISHED'}

class RENDERVARIATIONS_OT_render_animation(Operator):
    bl_idname = "render_variations.render_animation"
    bl_label = "Render Animation"
    bl_description = "Render animation with active set"
    
    def execute(self, context):
        bpy.ops.render_variations.apply_set()
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
            
            # Restore materials after render
            restore_original_materials(render_set)
            
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
        active_set.collections.clear()
        
        # Add all current collections with their current visibility state
        for collection in bpy.data.collections:
            if collection.name not in ['Master Collection']:
                coll_item = active_set.collections.add()
                coll_item.name = collection.name
                coll_item.enabled = not collection.hide_render
        
        return {'FINISHED'}

class RENDERVARIATIONS_OT_store_current_state(Operator):
    bl_idname = "render_variations.store_current_state"
    bl_label = "Store Current State"
    bl_description = "Store current collection visibility and settings to active set"
    
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
        
        # Copy all properties
        new_set.name = f"{active_set.name}_Copy"
        new_set.output_path = active_set.output_path
        new_set.file_prefix = active_set.file_prefix
        new_set.use_custom_output = active_set.use_custom_output
        new_set.resolution_scale = active_set.resolution_scale
        new_set.samples = active_set.samples
        new_set.use_samples_override = active_set.use_samples_override
        new_set.camera = active_set.camera
        new_set.use_custom_camera = active_set.use_custom_camera
        new_set.resolution_x = active_set.resolution_x
        new_set.resolution_y = active_set.resolution_y
        new_set.use_custom_resolution = active_set.use_custom_resolution
        new_set.override_material = active_set.override_material
        new_set.use_material_override = active_set.use_material_override
        
        # Copy collections
        for coll in active_set.collections:
            new_coll = new_set.collections.add()
            new_coll.name = coll.name
            new_coll.enabled = coll.enabled
            new_coll.use_material_override = coll.use_material_override
        
        props.active_set_index = len(props.render_sets) - 1
        return {'FINISHED'}

# Panels
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
        
        # Active Set Settings
        if props.render_sets and props.active_set_index < len(props.render_sets):
            active_set = props.render_sets[props.active_set_index]
            
            # Basic Settings
            box = layout.box()
            box.prop(active_set, "name")
            
            # Output Settings
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
            box = layout.box()
            box.label(text="Camera Settings", icon='CAMERA_DATA')
            box.prop(active_set, "use_custom_camera")
            if active_set.use_custom_camera:
                box.prop(active_set, "camera", text="Camera")
            
            # Resolution Settings
            box.prop(active_set, "use_custom_resolution")
            if active_set.use_custom_resolution:
                row = box.row()
                row.prop(active_set, "resolution_x", text="X")
                row.prop(active_set, "resolution_y", text="Y")
            
            # Material Override Settings
            box = layout.box()
            box.label(text="Material Override", icon='MATERIAL')
            box.prop(active_set, "use_material_override")
            if active_set.use_material_override:
                box.prop(active_set, "override_material", text="Material")
                if active_set.original_materials:
                    box.operator("render_variations.restore_materials", icon='FILE_REFRESH')
            
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
            
            # Collections List
            row = layout.row()
            row.template_list("RENDERVARIATIONS_UL_collections", "", active_set, "collections",
                             props, "collection_index", rows=5)
            
            # Show legend when material override is enabled
            if active_set.use_material_override:
                box = layout.box()
                box.scale_y = 0.8
                row = box.row()
                row.label(text="Legend:", icon='INFO')
                row = box.row()
                row.label(text="👁  Visible")
                row.label(text="🎨 Material Override", icon='MATERIAL')
            
            # Refresh Collections
            layout.operator("render_variations.refresh_collections", icon='FILE_REFRESH')
        else:
            layout.label(text="No active render set", icon='INFO')

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
    RENDERVARIATIONS_OT_restore_materials,
    RENDERVARIATIONS_OT_render_frame,
    RENDERVARIATIONS_OT_render_animation,
    RENDERVARIATIONS_OT_batch_render,
    RENDERVARIATIONS_OT_refresh_collections,
    RENDERVARIATIONS_OT_store_current_state,
    RENDERVARIATIONS_OT_duplicate_set,
    RENDERVARIATIONS_PT_main,
    RENDERVARIATIONS_PT_sets,
    RENDERVARIATIONS_PT_collections,
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
