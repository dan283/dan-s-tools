-------------random camera movements---------------

import bpy
import random
import datetime


for obj in bpy.context.scene.objects:
  # Select the object
  obj.select_set(True)
  # Set the current frame to the first frame
  bpy.context.scene.frame_set(0)
  # Clear all keyframes on the object
  bpy.ops.anim.keyframe_clear_v3d()
  # Deselect the object
  obj.select_set(False)
 
# Set the rotation of the camera to a random value
bpy.data.objects["Camera"].rotation_euler[2] = random.uniform(0, 360)

# Animate the camera's movement over 500 frames
bpy.data.objects["Camera"].keyframe_insert(data_path="location", frame=1)

for frame in range(2, 5001, 20):
    # Add some noise or randomness to the camera's movement
    bpy.data.objects["Camera"].location.x += random.uniform(-1, 1)
    bpy.data.objects["Camera"].location.y += random.uniform(-1, 1)
    bpy.data.objects["Camera"].location.z += random.uniform(-1, 1)
   
    # Insert a keyframe and set the interpolation type to 'BEZIER'
    bpy.data.objects["Camera"].keyframe_insert(data_path="location", frame=frame)
    
--------------random clicks----------------

import ctypes

# Load the user32 DLL
user32 = ctypes.cdll.LoadLibrary('user32.dll')

# Define the coordinates for the mouse click
x = 100
y = 200

# Emulate the mouse click
user32.SetCursorPos(x, y)
user32.mouse_event(2, 0, 0, 0, 0)  # left down
user32.mouse_event(4, 0, 0, 0, 0)  # left up
