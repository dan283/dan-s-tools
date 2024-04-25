import bpy
import mathutils

# Get the selected mesh and empty objects
mesh_obj = bpy.context.active_object
empty_objs = [obj for obj in bpy.context.selected_objects if obj.type == 'EMPTY']

if not mesh_obj or not empty_objs:
    print("Error: No mesh object or empty objects selected")
else:
    # Function to find the closest vertex to an empty
    def find_closest_vertex(empty_loc, vertices):
        min_distance = float('inf')
        closest_vertex = None
        for vertex in vertices:
            distance = (empty_loc - vertex.co).length
            if distance < min_distance:
                min_distance = distance
                closest_vertex = vertex
        return closest_vertex.index

    # Get the vertices of the mesh object
    mesh_verts = mesh_obj.data.vertices

    # Loop through each empty object
    for empty_obj in empty_objs:
        # Get the location of the empty
        empty_loc = empty_obj.location

        # Find the closest vertex to the empty
        closest_vertex_index = find_closest_vertex(empty_loc, mesh_verts)

        if closest_vertex_index is not None:
            print("Closest vertex to empty '{}' is at index {}".format(empty_obj.name, closest_vertex_index))
        else:
            print("Error: No closest vertex found for empty '{}'".format(empty_obj.name))
