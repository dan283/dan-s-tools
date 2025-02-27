import bpy
import numpy as np
import mathutils
from bpy.props import PointerProperty
from bpy.types import Operator, Panel, PropertyGroup

# Function to get a camera ray in world space
def get_camera_ray(camera, screen_x, screen_y):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    cam_eval = camera.evaluated_get(depsgraph)
    
    # Get the inverse camera matrix
    cam_inv = cam_eval.matrix_world
    
    # Convert screen coordinates to normalized device coordinates (-1 to 1 range)
    cam_x = (screen_x - 0.5) * 2
    cam_y = (screen_y - 0.5) * 2
    cam_z = -1  # Camera points in negative Z direction

    # Convert to world space
    ray_origin = cam_inv.translation
    ray_direction = cam_inv.to_3x3() @ mathutils.Vector((cam_x, cam_y, cam_z))
    ray_direction.normalize()
    
    return np.array(ray_origin), np.array(ray_direction)

# Function to compute the intersection of three camera rays
def triangulate(cams):
    if len(cams) != 3:
        return None
    
    origins = []
    directions = []
    
    for cam in cams:
        if cam is None:
            return None
        origin, direction = get_camera_ray(cam, 0.5, 0.5)
        origins.append(origin)
        directions.append(direction)
    
    origins = np.array(origins)
    directions = np.array(directions)

    A = np.zeros((3, 3))
    b = np.zeros(3)
    
    for i in range(3):
        A += np.eye(3) - np.outer(directions[i], directions[i])
        b += (np.eye(3) - np.outer(directions[i], directions[i])) @ origins[i]

    intersection = np.linalg.solve(A, b)
    return intersection

# Operator to triangulate the empty
class OBJECT_OT_TriangulateEmpty(Operator):
    bl_idname = "object.triangulate_empty"
    bl_label = "Triangulate Empty"
    bl_description = "Creates an empty at the triangulated intersection of three camera rays"
    
    def execute(self, context):
        scene = context.scene
        cam1 = scene.triangulation_settings.camera1
        cam2 = scene.triangulation_settings.camera2
        cam3 = scene.triangulation_settings.camera3
        
        if not cam1 or not cam2 or not cam3:
            self.report({'ERROR'}, "Please select three cameras")
            return {'CANCELLED'}
        
        intersection = triangulate([cam1, cam2, cam3])
        
        if intersection is None:
            self.report({'ERROR'}, "Could not triangulate a valid point")
            return {'CANCELLED'}
        
        empty = bpy.data.objects.new("Triangulated_Point", None)
        empty.location = intersection
        bpy.context.collection.objects.link(empty)
        
        self.report({'INFO'}, "Empty created at triangulated point")
        return {'FINISHED'}

# Property group for storing camera selection
class TriangulationProperties(PropertyGroup):
    camera1: PointerProperty(type=bpy.types.Object, poll=lambda self, obj: obj.type == 'CAMERA')
    camera2: PointerProperty(type=bpy.types.Object, poll=lambda self, obj: obj.type == 'CAMERA')
    camera3: PointerProperty(type=bpy.types.Object, poll=lambda self, obj: obj.type == 'CAMERA')

# UI Panel in the N-panel
class VIEW3D_PT_TriangulationPanel(Panel):
    bl_label = "Triangulation"
    bl_idname = "VIEW3D_PT_triangulation_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Triangulation"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.triangulation_settings

        layout.prop(settings, "camera1", text="Camera 1")
        layout.prop(settings, "camera2", text="Camera 2")
        layout.prop(settings, "camera3", text="Camera 3")

        layout.operator("object.triangulate_empty", text="Triangulate")

# Register classes
classes = [TriangulationProperties, OBJECT_OT_TriangulateEmpty, VIEW3D_PT_TriangulationPanel]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.triangulation_settings = PointerProperty(type=TriangulationProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.triangulation_settings

if __name__ == "__main__":
    register()
