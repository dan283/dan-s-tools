import bpy
import numpy as np
import mathutils
from bpy.props import PointerProperty, BoolProperty
from bpy.types import Operator, Panel, PropertyGroup

# Function to get a camera ray in world space
def get_camera_ray(camera, screen_x, screen_y):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    cam_eval = camera.evaluated_get(depsgraph)
    
    cam_inv = cam_eval.matrix_world  # Inverse camera matrix
    cam_x = (screen_x - 0.5) * 2
    cam_y = (screen_y - 0.5) * 2
    cam_z = -1  # Camera points in negative Z direction

    ray_origin = cam_inv.translation
    ray_direction = cam_inv.to_3x3() @ mathutils.Vector((cam_x, cam_y, cam_z))
    ray_direction.normalize()
    
    return np.array(ray_origin), np.array(ray_direction)

# Function to compute the intersection of three camera rays
def triangulate(cams):
    if len(cams) != 3:
        return None, None
    
    origins, directions = [], []
    
    for cam in cams:
        if cam is None:
            return None, None
        origin, direction = get_camera_ray(cam, 0.5, 0.5)
        origins.append(origin)
        directions.append(direction)
    
    origins, directions = np.array(origins), np.array(directions)
    
    A, b = np.zeros((3, 3)), np.zeros(3)
    
    for i in range(3):
        A += np.eye(3) - np.outer(directions[i], directions[i])
        b += (np.eye(3) - np.outer(directions[i], directions[i])) @ origins[i]

    try:
        intersection = np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        return None, None
    
    avg_direction = np.mean(directions, axis=0)
    avg_direction /= np.linalg.norm(avg_direction)
    
    z_axis = mathutils.Vector(avg_direction)
    y_axis = mathutils.Vector((0, 1, 0)) if abs(z_axis.dot((0, 1, 0))) < 0.9 else mathutils.Vector((1, 0, 0))
    x_axis = y_axis.cross(z_axis).normalized()
    y_axis = z_axis.cross(x_axis).normalized()
    
    rotation_matrix = mathutils.Matrix((x_axis, y_axis, z_axis)).transposed()
    
    return intersection, rotation_matrix.to_quaternion()

# Operator to triangulate the empty
class OBJECT_OT_TriangulateEmpty(Operator):
    bl_idname = "object.triangulate_empty"
    bl_label = "Triangulate Empty"
    bl_description = "Creates an empty at the triangulated intersection of three camera rays"
    
    def execute(self, context):
        scene = context.scene
        settings = scene.triangulation_settings
        cam1, cam2, cam3 = settings.camera1, settings.camera2, settings.camera3
        
        if not cam1 or not cam2 or not cam3:
            self.report({'ERROR'}, "Please select three cameras")
            return {'CANCELLED'}
        
        intersection, rotation = triangulate([cam1, cam2, cam3])
        
        if intersection is None:
            self.report({'ERROR'}, "Could not triangulate a valid point")
            return {'CANCELLED'}
        
        empty = bpy.data.objects.get("Triangulated_Point")
        if empty is None:
            empty = bpy.data.objects.new("Triangulated_Point", None)
            bpy.context.collection.objects.link(empty)

        empty.location = intersection
        empty.rotation_quaternion = rotation
        
        settings.keep_live = False  # Reset live mode to prevent instant handler activation
        self.report({'INFO'}, "Empty created at triangulated point")
        return {'FINISHED'}

# Handler function for live updates
def update_triangulation(scene):
    settings = scene.triangulation_settings
    if not settings.keep_live:
        return

    cam1, cam2, cam3 = settings.camera1, settings.camera2, settings.camera3
    if not cam1 or not cam2 or not cam3:
        return
    
    intersection, rotation = triangulate([cam1, cam2, cam3])
    if intersection is None:
        return
    
    empty = bpy.data.objects.get("Triangulated_Point")
    if empty:
        empty.location = intersection
        empty.rotation_quaternion = rotation

# Property group for storing camera selection and "Keep Live" checkbox
class TriangulationProperties(PropertyGroup):
    camera1: PointerProperty(type=bpy.types.Object, poll=lambda self, obj: obj.type == 'CAMERA')
    camera2: PointerProperty(type=bpy.types.Object, poll=lambda self, obj: obj.type == 'CAMERA')
    camera3: PointerProperty(type=bpy.types.Object, poll=lambda self, obj: obj.type == 'CAMERA')
    keep_live: BoolProperty(name="Keep Live", description="Continuously update triangulated empty", default=False)

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
        layout.prop(settings, "keep_live")

# Register classes and handlers
classes = [TriangulationProperties, OBJECT_OT_TriangulateEmpty, VIEW3D_PT_TriangulationPanel]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.triangulation_settings = PointerProperty(type=TriangulationProperties)
    
    # Add a handler to check for live updates
    bpy.app.handlers.depsgraph_update_post.append(update_triangulation)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.triangulation_settings
    
    # Remove the handler
    bpy.app.handlers.depsgraph_update_post.remove(update_triangulation)

if __name__ == "__main__":
    register()
