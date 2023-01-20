import bpy

def add_corrective_smooth(repeat_factor=150):
    selected_objects = bpy.context.selected_objects
    for obj in selected_objects:
        obj.modifiers.new(name="Corrective Smooth", type='CORRECTIVE_SMOOTH')
        obj.modifiers["Corrective Smooth"].iterations = repeat_factor
        obj.modifiers["Corrective Smooth"].show_viewport = True


def remove_corrective_smooth():
    selected_objects = bpy.context.selected_objects
    for obj in selected_objects:
        for modifier in obj.modifiers:
            if modifier.type == 'CORRECTIVE_SMOOTH':
                obj.modifiers.remove(modifier)
                
def select_selected_collection_objects():
    collection = bpy.context.view_layer.active_layer_collection.collection
    for obj in collection.objects:
        obj.select_set(True)
