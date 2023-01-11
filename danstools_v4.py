bl_info = {
    "name": "Dan's Tools",
    "author": "Dan",
    "version": (1, 1),
    "blender": (2, 90, 0),
    "location": "View3D > Toolbar > Dan's Tools",
    "description": "various doodads",
    "warning": "",
    "wiki_url": "",
    "category": "",
}

import bpy


def apply_modifiers(obj):
    ctx = bpy.context.copy()
    ctx['object'] = obj
    for _, m in enumerate(obj.modifiers):
        try:
            ctx['modifier'] = m
            bpy.ops.object.modifier_apply(ctx, modifier=m.name)
        except RuntimeError:
            print(f"Error applying {m.name} to {obj.name}, removing it instead.")
            obj.modifiers.remove(m)

    for m in obj.modifiers:
        obj.modifiers.remove(m)


class DecimationTools():
    def __init__(self):
        pass

    def select_objects_by_poly_count(self, context):
        start_count = context.scene.start_count
        bpy.ops.object.select_all(action='DESELECT')  # deselect all objects
        for obj in bpy.data.objects:
            if len(obj.data.polygons) > start_count:
                obj.select_set(True)

    def decimate_selected(self, context):
        target_count = context.scene.target_count
        selected_objects = bpy.context.selected_objects
        for obj in selected_objects:
            decimate_mod = obj.modifiers.new(name="Decimate", type='DECIMATE')
            decimate_mod.ratio = target_count
            bpy.ops.object.modifier_apply(modifier="Decimate")

    def decimate_selected_relative(self, context):
        decimate_value = context.scene.decimate_value
        selected_objects = bpy.context.selected_objects
        for obj in selected_objects:
            decimate_mod = obj.modifiers.new(name="Decimate", type='DECIMATE')
            decimate_mod.ratio = obj.target_count/obj.start_count
            bpy.ops.object.modifier_apply(modifier="Decimate")


class MESH_OT_delallshapekeys(bpy.types.Operator):
    bl_idname = 'delall.shapekeys'
    bl_label = 'Del SKs'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Get a list of all objects in the scene
        objects = bpy.data.objects

        # Loop through each object
        for obj in objects:
            # Check if the object has any shape keys
            if obj.data.shape_keys is not None:
                # Get the list of shape keys for the object
                shape_keys = obj.data.shape_keys.key_blocks

                # Create a new shape key from a mix of all of the existing shape keys
                new_shape_key = obj.shape_key_add(name="Mix", from_mix=True)

                # Loop through each shape key
                for shape_key in shape_keys:
                    # Delete the shape key
                    obj.shape_key_remove(shape_key)

        return {'FINISHED'}


class MESH_OT_SelectByPolycount(bpy.types.Operator):
    bl_idname = 'select.polycount'
    bl_label = 'Select by polycount'


    def execute(self, context):
        start_count = context.scene.start_count
        bpy.ops.object.select_all(action='DESELECT')  # deselect all objects
        for obj in bpy.data.objects:
            if len(obj.data.polygons) > start_count:
                obj.select_set(True)

        return {'FINISHED'}


class MESH_OT_DecimateSelected(bpy.types.Operator):
    bl_idname = 'decimate.selected'
    bl_label = 'decimate selected'
    bl_options = {'REGISTER', 'UNDO'}

    def __init__(self):
        self.decimation_tools = DecimationTools()

    def execute(self, context):

        target_count = context.scene.target_count
        selected_objects = bpy.context.selected_objects
        ratio = 0
        for object in selected_objects:
            ratio = len(object.data.polygons)
            decimate_mod = object.modifiers.new(name="Decimate", type='DECIMATE')
            decimate_mod.ratio = target_count / ratio
            bpy.ops.object.modifier_apply(modifier="Decimate")

        return {'FINISHED'}


class MESH_OT_DecimateSelectedRelative(bpy.types.Operator):
    bl_idname = 'decimate.relative'
    bl_label = 'decimate relative'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        decimate_value = context.scene.decimate_value
        selected_objects = bpy.context.selected_objects
        for obj in selected_objects:
            decimate_mod = obj.modifiers.new(name="Decimate", type='DECIMATE')
            decimate_mod.ratio = decimate_value
            bpy.ops.object.modifier_apply(modifier="Decimate")

        return {'FINISHED'}


class MESH_OT_applyallmodifiers(bpy.types.Operator):
    bl_idname = 'applyall.modifiers'
    bl_label = 'Apply Modifiers'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for obj in bpy.data.objects:
            apply_modifiers(obj)
        return {'FINISHED'}


class MESH_OT_togglerimonly(bpy.types.Operator):
    bl_idname = 'togglerim.solid'
    bl_label = 'Toggle Rim'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Get a list of all objects in the scene
        objects = bpy.data.objects

        # Get all objects in the scene
        objects = bpy.context.scene.objects

        # Loop through each object
        for obj in objects:
          # Loop through each modifier on the object
          for mod in obj.modifiers:
            # Check if the modifier is a Solidify modifier
            if mod.type == 'SOLIDIFY':
              # Toggle the "Rim Only" option
              mod.use_rim_only = not mod.use_rim_only

        return {'FINISHED'}


class MESH_OT_uvscene(bpy.types.Operator):
    bl_idname = 'uv.scene'
    bl_label = 'Setup UV'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Get the current screen
        screen = bpy.context.screen

        # Iterate over the areas in the screen
        for area in screen.areas:
            # Check if the area is an Outliner
            if area.type == 'OUTLINER':
                # Set the display mode in the Outliner to "View Layer"
                area.spaces[0].display_mode = 'VIEW_LAYER'

        # Enable "Live Unwrap"
        bpy.context.scene.tool_settings.use_edge_path_live_unwrap = True

        # Enable "UV Sync Selection"
        bpy.context.scene.tool_settings.use_uv_select_sync = True

        # Set the render engine to Cycles
        bpy.context.scene.render.engine = 'CYCLES'

        return {'FINISHED'}


class MESH_OT_animshapekeys(bpy.types.Operator):
    bl_idname = 'anim.shapekeys'
    bl_label = 'Anim SK'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        frames = bpy.context.scene.frame_end + 1

        # For the active object...
        ob = bpy.context.active_object
        me = ob.data

        # Remove ['Basis'] from a shallow copy of *ob's* shape-keys list.
        kblocks = dict(me.shape_keys.key_blocks)
        del kblocks['Basis']

        # Keyframe shapekeys' values to 1 for the frame corresponding
        # to their position in remaining list, 0 for other frames
        for f in range(frames):
            for i, kb in enumerate(kblocks):
                kblocks[kb].value = (f == i)
                kblocks[kb].keyframe_insert("value", frame=f)

        return {'FINISHED'}


class MESH_OT_deleteanim(bpy.types.Operator):
    bl_idname = 'anim.delete'
    bl_label = 'Del Anim'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.context.active_object.animation_data_clear()

        return {'FINISHED'}


class MESH_OT_setupuvscene(bpy.types.Operator):
    bl_idname = 'uvscene.setup'
    bl_label = 'UV Scene'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Get the current screen
        screen = bpy.context.screen

        # Iterate over the areas in the screen
        for area in screen.areas:
            # Check if the area is an Outliner
            if area.type == 'OUTLINER':
                # Set the display mode in the Outliner to "View Layer"
                area.spaces[0].display_mode = 'VIEW_LAYER'

        # Enable "Live Unwrap"
        bpy.context.scene.tool_settings.use_edge_path_live_unwrap = True

        # Enable "UV Sync Selection"
        bpy.context.scene.tool_settings.use_uv_select_sync = True

        # Set the render engine to Cycles
        bpy.context.scene.render.engine = 'CYCLES'


class MESH_OT_borders(bpy.types.Operator):
    bl_idname = 'mesh.borders'
    bl_label = 'Show Borders'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.region_to_loop()
        bpy.ops.mesh.mark_seam(clear=False)
        bpy.ops.mesh.select_all(action='DESELECT')

        return {'FINISHED'}


class ADDONNAME_OT_add_basic(bpy.types.Operator):
    bl_label = "Del Mats"
    bl_idname = "mesh.mat"

    col = bpy.props.FloatVectorProperty(name='Color', subtype='COLOR_GAMMA', size=4, default=(0, 1, 0, 1))

    def execute(self, context):
        material_basic = bpy.data.materials.new(name='Basic')
        material_basic.use_nodes = True

        bpy.context.object.active_material = material_basic

        principled_node = material_basic.node_tree.nodes.get('Principled BSDF')

        #        principled_node.inputs[0].default_value = (1,0,1,1)
        principled_node.inputs[7].default_value = 0.08

        rgb_node = material_basic.node_tree.nodes.new('ShaderNodeRGB')
        rgb_node.location = (-250, 225)
        rgb_node.outputs[0].default_value = self.col

        link = material_basic.node_tree.links.new

        link(rgb_node.outputs[0], principled_node.inputs[0])

        ramp_one = material_basic.node_tree.nodes.new('ShaderNodeValToRGB')
        ramp_one.location = [-900, 300]

        ramp_two = material_basic.node_tree.nodes.new('ShaderNodeValToRGB')
        ramp_two.location = [-900, 0]

        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class MESH_OT_L(bpy.types.Operator):
    bl_idname = "mesh.l"
    bl_label = "clearSplits"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selection = bpy.context.selected_objects

        for o in selection:
            bpy.context.view_layer.objects.active = o
            bpy.ops.mesh.customdata_custom_splitnormals_clear()

        return {'FINISHED'}


class MESH_OT_pivot(bpy.types.Operator):
    bl_idname = 'mesh.pivot'
    bl_label = 'pivotToBase'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')
        o = bpy.context.active_object
        init = 0
        for x in o.data.vertices:
            if init == 0:
                a = x.co.z
                init = 1
            elif x.co.z < a:
                a = x.co.z

        for x in o.data.vertices:
            x.co.z -= a

        o.location.z += a

        return {'FINISHED'}


class VIEW3D_PT_dansTools(bpy.types.Panel):
    bl_label = "General"
    bl_category = "Dan's Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        split = layout.split()

        col = split.column(align=True)

        col.scale_y = 1.2
        col.operator('mesh.l', icon='TRACKING_CLEAR_FORWARDS')
        col.operator('mesh.pivot', icon='TRIA_DOWN')

        col = split.column(align=True)

        col.scale_y = 1.2
        col.operator('mesh.borders', icon='MESH_CUBE')
        col.operator('mesh.mat', icon='SHADING_TEXTURE')


class VIEW3D_PT_dansToolsB(bpy.types.Panel):
    bl_label = "Anim Tools"
    bl_category = "Dan's Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        row = layout.row(align=True)
        row.scale_y = 1.2
        row.operator('anim.shapekeys', icon='OUTLINER_OB_META')
        row.operator('anim.delete', icon='CANCEL')


class VIEW3D_PT_dansToolsD(bpy.types.Panel):
    bl_label = "Chibis"
    bl_category = "Dan's Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        split = layout.split()

        col = split.column(align=True)

        col.scale_y = 1.2
        col.operator('delall.shapekeys', icon='TRACKING_CLEAR_FORWARDS')
        col.operator('togglerim.solid', icon='TRIA_DOWN')

        col = split.column(align=True)

        col.scale_y = 1.2
        col.operator('uv.scene', icon='MESH_CUBE')
        col.operator('applyall.modifiers', icon='SHADING_TEXTURE')


class VIEW3D_PT_dansToolsC(bpy.types.Panel):
    bl_label = "Doodads"
    bl_category = "Dan's Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout

        scene = context.scene
        split = layout.split()
        col = split.column(align=True)
        col.label(text="Column Two:")
        col.scale_y = 1.3
        col.operator("render.render")
        col.prop(scene, "frame_end")


class VIEW3D_PT_dansToolsE(bpy.types.Panel):
    bl_label = "Decimation Tools"
    bl_category = "Dan's Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        row = layout.row(align=False)
        row.scale_y = 1.1

        row.operator("select.polycount", text="Select Polycount")
        row.prop(scene, "start_count", text="")


        row = layout.row(align=False)
        row.scale_y = 1.1

        row.operator("decimate.selected", text="New Polycount")
        row.prop(scene, "target_count", text="")


        row = layout.row(align=False)
        row.scale_y = 1.1

        row.operator("decimate.relative", text="Decimate %")
        row.prop(scene, "decimate_value", text="")


classes = (
    MESH_OT_L,
    MESH_OT_SelectByPolycount,
    MESH_OT_DecimateSelected,
    MESH_OT_DecimateSelectedRelative,
    MESH_OT_delallshapekeys,
    MESH_OT_togglerimonly,
    MESH_OT_borders,
    MESH_OT_uvscene,
    MESH_OT_applyallmodifiers,
    ADDONNAME_OT_add_basic,
    MESH_OT_pivot,
    VIEW3D_PT_dansTools,
    VIEW3D_PT_dansToolsB,
    VIEW3D_PT_dansToolsD,
    VIEW3D_PT_dansToolsC,
    VIEW3D_PT_dansToolsE,
    MESH_OT_animshapekeys,
    MESH_OT_deleteanim,
)


def register():
    bpy.types.Scene.decimate_value = FloatProperty(
        name="decimation value", default=.1)
    bpy.types.Scene.target_count = IntProperty(
        name="target polycount", default=200000)
    bpy.types.Scene.start_count = IntProperty(
        name="start polycount", default=1000000)

    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    del bpy.types.Scene.decimate_value
    del bpy.types.Scene.target_count
    del bpy.types.Scene.start_count

    for cls in classes:
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()


