import bpy

# Create a cube mesh
bpy.ops.mesh.primitive_cube_add(size=2)

# Get the cube object
cube_obj = bpy.context.active_object

# Create an empty object
bpy.ops.object.empty_add(location=(0, 0, 0))

# Get the empty object
empty_obj = bpy.context.active_object

# Ensure the cube is selected
bpy.context.view_layer.objects.active = cube_obj
cube_obj.select_set(True)

# Switch to edit mode to access vertices
bpy.ops.object.mode_set(mode='EDIT')

# Deselect all vertices
bpy.ops.mesh.select_all(action='DESELECT')

# Select the vertex with index 1
cube_obj.data.vertices[1].select = True

# Switch back to object mode
bpy.ops.object.mode_set(mode='OBJECT')

# Get the location of the selected vertex
vertex_loc = cube_obj.matrix_world @ cube_obj.data.vertices[1].co

# Set the location of the empty to the location of the selected vertex
empty_obj.location = vertex_loc

# Parent the empty to the vertex
bpy.ops.object.select_all(action='DESELECT')
empty_obj.select_set(True)
cube_obj.select_set(True)
bpy.context.view_layer.objects.active = cube_obj
bpy.ops.object.parent_set(type='VERTEX')
empty_obj.parent_vertices[0] = 1  # Index of the vertex

print("Empty '{}' is parented to the vertex with index 1".format(empty_obj.name))
