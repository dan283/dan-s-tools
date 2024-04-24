import bpy

# Check if an armature is selected
selected = bpy.context.selected_objects
if not selected:
    print("Please select an armature.")
    quit()

armature = None
for obj in selected:
    if obj.type == 'ARMATURE':
        armature = obj
        break

if not armature:
    print("No armature selected.")
    quit()

# Go to object mode to manipulate the armature
bpy.ops.object.mode_set(mode='OBJECT')

# Loop through the armature's bones and create an empty for each bone's head
for bone in armature.data.bones:
    empty = bpy.data.objects.new(name=bone.name + "_Empty", object_data=None)
    empty.location = armature.matrix_world @ bone.head_local
    bpy.context.collection.objects.link(empty)

# Select the armature again
armature.select_set(True)
