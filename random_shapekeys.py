import random
import bpy

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
set_random_shape_key(objects)
