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
        
        
collection_list = ['Hair', 'Hats', 'Glasses', 'Shoes', 'Pants', 'Socks', 'Tops']

folder_path = 'e:/test/'


frame_start = bpy.context.scene.frame_start
frame_end = bpy.context.scene.frame_end
iterations = 10

# Render animation and save images
for i in range(iterations):
    random_frame = random.randint(frame_start, frame_end)
    hide_and_show_random(collection_list)
    bpy.context.scene.frame_set(random_frame)
    bpy.context.scene.render.filepath = f"{folder_path}_{'collection_name'}_{i}"
    bpy.ops.render.render(write_still=True)
