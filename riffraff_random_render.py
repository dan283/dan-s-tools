import bpy
import random

def hide_and_show_random(collection_names):
    # Hide all objects in viewport and disable in render
    for collection_name in collection_names:
        collection = bpy.data.collections[collection_name]
        for obj in collection.objects:
            obj.hide_viewport = True
            obj.hide_render = True
    
    
    # Show one random object per collection in viewport and enable in render
    for collection_name in collection_names:
        
        collection = bpy.data.collections[collection_name]
        random_obj = random.choice(collection.objects)
        random_obj.hide_viewport = False
        random_obj.hide_render = False
        
        
collection_list = ['Denim', 'Bomber', 'Baseball', 'Fluro']

folder_path = 'e:/test/'

# Render animation and save images
for i in range(10):
    hide_and_show_random(collection_list)
    bpy.context.scene.frame_set(i)
    bpy.context.scene.render.filepath = f"{folder_path}_{'collection_name'}_{i}"
    bpy.ops.render.render(write_still=True)


hide_and_show_random(collection_list)
