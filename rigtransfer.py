#starting a rig transfer tool

import bpy

# Get the selected armature object
armature_obj = bpy.context.active_object

# Make sure the selected object is an armature
if armature_obj.type != 'ARMATURE':
    raise ValueError("Please select an armature object")

# Get the armature data
armature_data = armature_obj.data

# Loop through all the bones in the armature
for bone in armature_data.bones:
    # Create a new ico sphere object with 1 subdivision
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, location=bone.head_local)
    ico_obj = bpy.context.active_object
    ico_obj.name = bone.name + "_ico"
    
    # Add a subsurf modifier to the ico sphere with 1 subdivision
    ico_mod = ico_obj.modifiers.new(name="Subdivision", type='SUBSURF')
    ico_mod.subdivision_type = 'CATMULL_CLARK'
    ico_mod.levels = 1
    
    # Add the ico sphere to the scene and parent it to the armature
    bpy.context.scene.collection.objects.link(ico_obj)
    ico_obj.parent = armature_obj
