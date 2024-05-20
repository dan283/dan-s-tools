import bpy
# swaps 2 meshes by moving the other meshes by 2000 units 
class SwapListItem(bpy.types.PropertyGroup):
    object: bpy.props.PointerProperty(type=bpy.types.Object)

class SwapListPanel(bpy.types.Panel):
    bl_label = "Swap"
    bl_idname = "OBJECT_PT_swap"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Swap'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        swap_list = scene.swap_list

        row = layout.row()
        row.template_list("UI_UL_list", "swap_list", scene, "swap_list", scene, "swap_list_index")

        col = row.column(align=True)
        col.operator("swap_list.add_item", icon='ADD', text="")
        col.operator("swap_list.remove_item", icon='REMOVE', text="")

        layout.operator("swap_list.swap_objects", text="Swap")

class UL_SwapList(bpy.types.UIList):
    bl_idname = "UI_UL_list"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=item.object.name if item.object else "")
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="")

class SwapListAddItem(bpy.types.Operator):
    bl_idname = "swap_list.add_item"
    bl_label = "Add Item"
    
    def execute(self, context):
        scene = context.scene
        swap_list = scene.swap_list
        obj = context.object
        
        if obj:
            item = swap_list.add()
            item.object = obj
        return {'FINISHED'}

class SwapListRemoveItem(bpy.types.Operator):
    bl_idname = "swap_list.remove_item"
    bl_label = "Remove Item"
    
    @classmethod
    def poll(cls, context):
        return context.scene.swap_list

    def execute(self, context):
        scene = context.scene
        swap_list = scene.swap_list
        
        index = scene.swap_list_index
        swap_list.remove(index)
        scene.swap_list_index = min(max(0, index - 1), len(swap_list) - 1)
        
        return {'FINISHED'}

class SwapListSwapObjects(bpy.types.Operator):
    bl_idname = "swap_list.swap_objects"
    bl_label = "Swap Objects"
    
    swap_state: bpy.props.IntProperty(default=0)
    
    def execute(self, context):
        scene = context.scene
        swap_list = scene.swap_list
        
        if not swap_list:
            return {'CANCELLED'}
        
        move_amount = 2000
        keep_index = self.swap_state % len(swap_list)
        
        for i, item in enumerate(swap_list):
            if item.object:
                if i == keep_index:
                    item.object.location.z = 0
                else:
                    item.object.location.z = move_amount
        
        self.swap_state += 1
        
        return {'FINISHED'}

def register():
    bpy.utils.register_class(SwapListItem)
    bpy.types.Scene.swap_list = bpy.props.CollectionProperty(type=SwapListItem)
    bpy.types.Scene.swap_list_index = bpy.props.IntProperty()
    
    bpy.utils.register_class(SwapListPanel)
    bpy.utils.register_class(UL_SwapList)
    bpy.utils.register_class(SwapListAddItem)
    bpy.utils.register_class(SwapListRemoveItem)
    bpy.utils.register_class(SwapListSwapObjects)

def unregister():
    bpy.utils.unregister_class(SwapListItem)
    del bpy.types.Scene.swap_list
    del bpy.types.Scene.swap_list_index
    
    bpy.utils.unregister_class(SwapListPanel)
    bpy.utils.unregister_class(UL_SwapList)
    bpy.utils.unregister_class(SwapListAddItem)
    bpy.utils.unregister_class(SwapListRemoveItem)
    bpy.utils.unregister_class(SwapListSwapObjects)

if __name__ == "__main__":
    register()
