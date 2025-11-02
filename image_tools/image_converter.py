bl_info = {
    "name": "HEIC to JPG Converter",
    "author": "ChatGPT",
    "version": (1, 2),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Image Convert",
    "description": "Convert HEIC image files to JPG format",
    "category": "Import-Export",
}

import bpy
from bpy.props import StringProperty, CollectionProperty
from bpy.types import Operator, Panel
import os
import sys

# --- 🔧 Fix for user installs (adds user site-packages path) ---
from site import USER_SITE
if USER_SITE not in sys.path:
    sys.path.append(USER_SITE)

# --- Try importing Pillow + pillow-heif ---
try:
    from PIL import Image
    import pillow_heif
    pillow_heif.register_heif_opener()
    PIL_AVAILABLE = True
except ImportError as e:
    print("⚠️ Could not import Pillow or pillow-heif:", e)
    PIL_AVAILABLE = False


# --- Operator: Select multiple HEIC files ---
class IMAGECONVERT_OT_select_files(Operator):
    bl_idname = "imageconvert.select_files"
    bl_label = "Select HEIC Files"

    directory: StringProperty(subtype='DIR_PATH')
    files: CollectionProperty(type=bpy.types.PropertyGroup)

    def execute(self, context):
        filepaths = [
            os.path.join(self.directory, f.name)
            for f in self.files
            if f.name.lower().endswith(".heic")
        ]
        context.scene.imageconvert_file_list = ";".join(filepaths)
        self.report({'INFO'}, f"Selected {len(filepaths)} HEIC files.")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


# --- Operator: Convert HEIC -> JPG ---
class IMAGECONVERT_OT_convert(Operator):
    bl_idname = "imageconvert.convert"
    bl_label = "Convert to JPG"

    def execute(self, context):
        if not PIL_AVAILABLE:
            self.report({'ERROR'}, "Pillow or pillow-heif not installed or not found.")
            return {'CANCELLED'}

        files = [f for f in context.scene.imageconvert_file_list.split(";") if f]
        if not files:
            self.report({'WARNING'}, "No files selected.")
            return {'CANCELLED'}

        converted = 0
        for path in files:
            try:
                img = Image.open(path)
                out_path = os.path.splitext(path)[0] + ".jpg"
                img.convert("RGB").save(out_path, "JPEG")
                converted += 1
            except Exception as e:
                self.report({'WARNING'}, f"Failed: {os.path.basename(path)} ({e})")

        self.report({'INFO'}, f"Converted {converted} file(s) to JPG.")
        return {'FINISHED'}


# --- UI Panel in N-panel ---
class IMAGECONVERT_PT_panel(Panel):
    bl_label = "HEIC to JPG"
    bl_idname = "IMAGECONVERT_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Image Convert"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        if not PIL_AVAILABLE:
            layout.label(text="Pillow or pillow-heif not found.", icon='ERROR')
            layout.label(text="Install them for your Blender Python.")
            return

        layout.operator("imageconvert.select_files", icon="FILE_IMAGE")
        layout.operator("imageconvert.convert", icon="IMAGE_DATA")

        layout.label(text="Selected Files:")
        box = layout.box()
        if scene.imageconvert_file_list:
            for f in scene.imageconvert_file_list.split(";"):
                box.label(text=os.path.basename(f))
        else:
            box.label(text="None selected.")


# --- Registration ---
classes = (
    IMAGECONVERT_OT_select_files,
    IMAGECONVERT_OT_convert,
    IMAGECONVERT_PT_panel,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.imageconvert_file_list = StringProperty(default="")

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.imageconvert_file_list

if __name__ == "__main__":
    register()
