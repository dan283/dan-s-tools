import bpy
import random
from mathutils import Vector


def set_z_location(name):
    obj = bpy.data.objects.get(name)
    if obj is not None:
        # Get the minimum z value of the bounding box of all visible objects
        min_z = float("inf")
        for o in bpy.data.objects:
            if not o.hide_viewport and o.name != name:
                corners = [o.matrix_world @ Vector(corner) for corner in o.bound_box]
                min_z = min(min_z, min([corner[2] for corner in corners]))

        # Set the z location of the object to the minimum z value of the bounding box
        obj.location.z = min_z
    else:
        print("Object with name '{}' not found.".format(name))
       

def set_random_shape_key(obj_names):
    for obj_name in obj_names:
        obj = bpy.data.objects[obj_name]
        for shape_key in obj.data.shape_keys.key_blocks:
            shape_key.value = 0
        # Choose a random shape key and set its value to 1
        random_shape_key = random.choice(obj.data.shape_keys.key_blocks)
        print(random_shape_key.name)
        random_shape_key.value = 1


objects = ['body_midres']


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
        
        set_random_shape_key(objects)
        set_z_location('ground')
        
        random_obj.hide_viewport = False
        random_obj.hide_render = False
        
        
collection_list = ['hatHair', 'Hats', 'Glasses', 'Shoes', 'Pants', 'Socks', 'Tops']
collection_listB = ['Hair', 'Shoes', 'Pants', 'Socks', 'Tops', 'Lashes', 'Brows', 'Eyes', 'Bodies']
collection_list_glasses = ['Hair', 'Shoes', 'Glasses','Pants', 'Socks', 'Tops', 'Lashes', 'Brows', 'Eyes', 'Bodies']

folder_path = 'e:/test/'


frame_start = bpy.context.scene.frame_start
frame_end = bpy.context.scene.frame_end
iterations = 10

# Render animation and save images
for i in range(iterations):
    random_frame = random.randint(frame_start, frame_end)
    hide_and_show_random(collection_listB)
    bpy.context.scene.frame_set(random_frame)
    bpy.context.scene.render.filepath = f"{folder_path}{'riffraffs'}_{i}"
    bpy.ops.render.render(write_still=True)






#hide_and_show_random(collection_list)
