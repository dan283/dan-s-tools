bl_info = {
    "name": "Universal Image Converter",
    "author": "Enhanced by Claude",
    "version": (2, 1),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Image Convert",
    "description": "Convert between multiple image formats with advanced options",
    "category": "Import-Export",
}

import bpy
from bpy.props import StringProperty, CollectionProperty, EnumProperty, IntProperty, BoolProperty
from bpy.types import Operator, Panel
import os
import sys
import subprocess

# --- Fix for user installs ---
from site import USER_SITE
if USER_SITE not in sys.path:
    sys.path.append(USER_SITE)

# --- Check Python executable ---
def get_python_exe():
    """Get the Python executable used by Blender"""
    if sys.platform == "win32":
        # Check multiple possible locations for Python on Windows
        candidates = [
            sys.executable,  # Current Python executable
            os.path.join(sys.prefix, 'bin', 'python.exe'),
            os.path.join(sys.prefix, 'python.exe'),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        return sys.executable  # Fallback
    else:
        return os.path.join(sys.prefix, 'bin', 'python')

def get_all_python_executables():
    """Get all Python executables that might be used"""
    executables = [sys.executable]
    
    if sys.platform == "win32":
        # Add Blender's bundled Python if different
        blender_python = os.path.join(sys.prefix, 'bin', 'python.exe')
        if os.path.exists(blender_python) and blender_python != sys.executable:
            executables.append(blender_python)
        
        # Check for system Python in common locations
        import shutil
        system_python = shutil.which('python')
        if system_python and system_python not in executables:
            executables.append(system_python)
        
        system_python3 = shutil.which('python3')
        if system_python3 and system_python3 not in executables:
            executables.append(system_python3)
    
    return executables

# --- Try importing Pillow + pillow-heif ---
PIL_AVAILABLE = False
PILLOW_MISSING = False
HEIF_MISSING = False

try:
    from PIL import Image
except ImportError:
    PILLOW_MISSING = True

try:
    import pillow_heif
    if not PILLOW_MISSING:
        pillow_heif.register_heif_opener()
except ImportError:
    HEIF_MISSING = True

PIL_AVAILABLE = not PILLOW_MISSING and not HEIF_MISSING

# Supported formats
INPUT_FORMATS = ('.heic', '.heif', '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp', '.gif')
OUTPUT_FORMATS = [
    ('JPG', 'JPEG', 'Convert to JPEG format'),
    ('PNG', 'PNG', 'Convert to PNG format'),
    ('WEBP', 'WebP', 'Convert to WebP format'),
    ('BMP', 'BMP', 'Convert to BMP format'),
    ('TIFF', 'TIFF', 'Convert to TIFF format'),
]

# --- Operator: Install Pillow ---
class IMAGECONVERT_OT_install_pillow(Operator):
    bl_idname = "imageconvert.install_pillow"
    bl_label = "Install Pillow"
    bl_description = "Install Pillow library for all detected Python installations"
    
    def execute(self, context):
        python_executables = get_all_python_executables()
        
        if not python_executables:
            self.report({'ERROR'}, "No Python executable found!")
            return {'CANCELLED'}
        
        self.report({'INFO'}, f"Installing Pillow to {len(python_executables)} Python installation(s)...")
        
        success_count = 0
        log_output = []
        
        for i, python_exe in enumerate(python_executables, 1):
            if not os.path.exists(python_exe):
                log_output.append(f"\n[{i}] Skipped (not found): {python_exe}")
                continue
            
            log_output.append(f"\n[{i}] Installing to: {python_exe}")
            print(f"Installing Pillow to: {python_exe}")
            
            try:
                result = subprocess.run(
                    [python_exe, "-m", "pip", "install", "--user", "Pillow"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    success_count += 1
                    log_output.append(f"    ✓ Success!")
                    log_output.append(f"    {result.stdout[:200]}")
                else:
                    error_msg = result.stderr if result.stderr else result.stdout
                    log_output.append(f"    ✗ Failed: {error_msg[:200]}")
                    
            except subprocess.TimeoutExpired:
                log_output.append(f"    ✗ Timed out")
            except Exception as e:
                log_output.append(f"    ✗ Error: {str(e)}")
        
        context.scene.imageconvert_install_log = "\n".join(log_output)
        
        if success_count > 0:
            self.report({'INFO'}, f"✓ Pillow installed to {success_count}/{len(python_executables)} Python(s). Restart Blender!")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Installation failed for all Python installations. Check log.")
            return {'CANCELLED'}

# --- Operator: Install pillow-heif ---
class IMAGECONVERT_OT_install_heif(Operator):
    bl_idname = "imageconvert.install_heif"
    bl_label = "Install pillow-heif"
    bl_description = "Install pillow-heif library for HEIC/HEIF support (all Python installations)"
    
    def execute(self, context):
        python_executables = get_all_python_executables()
        
        if not python_executables:
            self.report({'ERROR'}, "No Python executable found!")
            return {'CANCELLED'}
        
        self.report({'INFO'}, f"Installing pillow-heif to {len(python_executables)} Python installation(s)...")
        
        success_count = 0
        log_output = []
        
        for i, python_exe in enumerate(python_executables, 1):
            if not os.path.exists(python_exe):
                log_output.append(f"\n[{i}] Skipped (not found): {python_exe}")
                continue
            
            log_output.append(f"\n[{i}] Installing to: {python_exe}")
            print(f"Installing pillow-heif to: {python_exe}")
            
            try:
                result = subprocess.run(
                    [python_exe, "-m", "pip", "install", "--user", "pillow-heif"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    success_count += 1
                    log_output.append(f"    ✓ Success!")
                    log_output.append(f"    {result.stdout[:200]}")
                else:
                    error_msg = result.stderr if result.stderr else result.stdout
                    log_output.append(f"    ✗ Failed: {error_msg[:200]}")
                    
            except subprocess.TimeoutExpired:
                log_output.append(f"    ✗ Timed out")
            except Exception as e:
                log_output.append(f"    ✗ Error: {str(e)}")
        
        context.scene.imageconvert_install_log = "\n".join(log_output)
        
        if success_count > 0:
            self.report({'INFO'}, f"✓ pillow-heif installed to {success_count}/{len(python_executables)} Python(s). Restart Blender!")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Installation failed for all Python installations. Check log.")
            return {'CANCELLED'}

# --- Operator: Install pip ---
class IMAGECONVERT_OT_install_pip(Operator):
    bl_idname = "imageconvert.install_pip"
    bl_label = "Install pip"
    bl_description = "Install pip package manager for Blender's Python"
    
    def execute(self, context):
        python_exe = get_python_exe()
        
        if not os.path.exists(python_exe):
            self.report({'ERROR'}, f"Python executable not found at: {python_exe}")
            return {'CANCELLED'}
        
        self.report({'INFO'}, "Installing pip... Please wait.")
        
        try:
            result = subprocess.run(
                [python_exe, "-m", "ensurepip", "--user"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                self.report({'INFO'}, "✓ pip installed successfully!")
                context.scene.imageconvert_install_log = result.stdout
                return {'FINISHED'}
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                self.report({'ERROR'}, f"pip installation failed. Check console.")
                context.scene.imageconvert_install_log = error_msg
                print("pip installation error:", error_msg)
                return {'CANCELLED'}
                
        except subprocess.TimeoutExpired:
            self.report({'ERROR'}, "Installation timed out.")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Installation error: {str(e)}")
            print("Exception during pip installation:", e)
            return {'CANCELLED'}

# --- Operator: Select multiple image files ---
class IMAGECONVERT_OT_select_files(Operator):
    bl_idname = "imageconvert.select_files"
    bl_label = "Select Image Files"
    bl_description = "Select one or more image files to convert"
    
    directory: StringProperty(subtype='DIR_PATH')
    files: CollectionProperty(type=bpy.types.PropertyGroup)
    
    def execute(self, context):
        filepaths = [
            os.path.join(self.directory, f.name)
            for f in self.files
            if f.name.lower().endswith(INPUT_FORMATS)
        ]
        
        if not filepaths:
            self.report({'WARNING'}, "No supported image files selected.")
            return {'CANCELLED'}
        
        context.scene.imageconvert_file_list = ";".join(filepaths)
        self.report({'INFO'}, f"Selected {len(filepaths)} image file(s).")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# --- Operator: Select output directory ---
class IMAGECONVERT_OT_select_output(Operator):
    bl_idname = "imageconvert.select_output"
    bl_label = "Select Output Folder"
    bl_description = "Choose where to save converted images"
    
    directory: StringProperty(subtype='DIR_PATH')
    
    def execute(self, context):
        context.scene.imageconvert_output_dir = self.directory
        self.report({'INFO'}, f"Output directory set.")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# --- Operator: Convert images ---
class IMAGECONVERT_OT_convert(Operator):
    bl_idname = "imageconvert.convert"
    bl_label = "Convert Images"
    bl_description = "Convert selected images to chosen format"
    
    def execute(self, context):
        if not PIL_AVAILABLE:
            self.report({'ERROR'}, "Pillow or pillow-heif not installed.")
            return {'CANCELLED'}
        
        from PIL import Image
        
        scene = context.scene
        files = [f for f in scene.imageconvert_file_list.split(";") if f]
        
        if not files:
            self.report({'WARNING'}, "No files selected.")
            return {'CANCELLED'}
        
        output_format = scene.imageconvert_output_format
        quality = scene.imageconvert_quality
        resize = scene.imageconvert_resize_enabled
        resize_width = scene.imageconvert_resize_width
        resize_height = scene.imageconvert_resize_height
        maintain_aspect = scene.imageconvert_maintain_aspect
        output_dir = scene.imageconvert_output_dir
        
        # Format-specific settings
        format_map = {
            'JPG': 'JPEG',
            'PNG': 'PNG',
            'WEBP': 'WEBP',
            'BMP': 'BMP',
            'TIFF': 'TIFF',
        }
        
        file_ext = {
            'JPG': '.jpg',
            'PNG': '.png',
            'WEBP': '.webp',
            'BMP': '.bmp',
            'TIFF': '.tiff',
        }
        
        converted = 0
        failed = []
        
        for path in files:
            try:
                img = Image.open(path)
                
                # Convert RGBA to RGB for formats that don't support transparency
                if output_format in ['JPG', 'BMP'] and img.mode in ('RGBA', 'LA', 'P'):
                    # Create white background
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')
                
                # Resize if enabled
                if resize and (resize_width > 0 or resize_height > 0):
                    original_size = img.size
                    if maintain_aspect:
                        img.thumbnail((resize_width, resize_height), Image.Resampling.LANCZOS)
                    else:
                        new_width = resize_width if resize_width > 0 else original_size[0]
                        new_height = resize_height if resize_height > 0 else original_size[1]
                        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Determine output path
                base_name = os.path.splitext(os.path.basename(path))[0]
                if output_dir and os.path.isdir(output_dir):
                    out_path = os.path.join(output_dir, base_name + file_ext[output_format])
                else:
                    out_path = os.path.join(os.path.dirname(path), base_name + file_ext[output_format])
                
                # Save with format-specific options
                save_kwargs = {}
                if output_format == 'JPG':
                    save_kwargs = {'quality': quality, 'optimize': True}
                elif output_format == 'PNG':
                    save_kwargs = {'optimize': True}
                elif output_format == 'WEBP':
                    save_kwargs = {'quality': quality}
                
                img.save(out_path, format_map[output_format], **save_kwargs)
                converted += 1
                
            except Exception as e:
                failed.append((os.path.basename(path), str(e)))
        
        # Report results
        if converted > 0:
            self.report({'INFO'}, f"✓ Converted {converted} file(s) to {output_format}.")
        
        if failed:
            for fname, error in failed[:3]:  # Show first 3 failures
                self.report({'WARNING'}, f"Failed: {fname} ({error})")
            if len(failed) > 3:
                self.report({'WARNING'}, f"...and {len(failed) - 3} more failures.")
        
        return {'FINISHED'}

# --- Operator: Clear file list ---
class IMAGECONVERT_OT_clear_files(Operator):
    bl_idname = "imageconvert.clear_files"
    bl_label = "Clear List"
    bl_description = "Clear the selected files list"
    
    def execute(self, context):
        context.scene.imageconvert_file_list = ""
        self.report({'INFO'}, "File list cleared.")
        return {'FINISHED'}

# --- Operator: Show installation log ---
class IMAGECONVERT_OT_show_log(Operator):
    bl_idname = "imageconvert.show_log"
    bl_label = "Show Installation Log"
    bl_description = "Show the installation log in console"
    
    def execute(self, context):
        log = context.scene.imageconvert_install_log
        if log:
            print("\n" + "="*60)
            print("INSTALLATION LOG:")
            print("="*60)
            print(log)
            print("="*60 + "\n")
            self.report({'INFO'}, "Log printed to console (Window > Toggle System Console)")
        else:
            self.report({'INFO'}, "No installation log available.")
        return {'FINISHED'}

# --- UI Panel ---
class IMAGECONVERT_PT_panel(Panel):
    bl_label = "Universal Image Converter"
    bl_idname = "IMAGECONVERT_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Image Convert"
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Installation section if dependencies missing
        if not PIL_AVAILABLE:
            box = layout.box()
            box.label(text="⚠️ Setup Required", icon='ERROR')
            
            # Python info
            python_executables = get_all_python_executables()
            col = box.column(align=True)
            col.label(text=f"Found {len(python_executables)} Python installation(s):", icon='CONSOLE')
            for i, python_exe in enumerate(python_executables, 1):
                col.label(text=f"  [{i}] {python_exe[:45]}")
                if len(python_exe) > 45:
                    col.label(text=f"      {python_exe[45:]}")
            
            if sys.executable in python_executables:
                col.label(text=f"Active: {os.path.basename(sys.executable)}", icon='LAYER_ACTIVE')
            
            box.separator()
            
            # Status indicators
            col = box.column(align=True)
            if PILLOW_MISSING:
                row = col.row()
                row.label(text="❌ Pillow", icon='CANCEL')
                row.operator("imageconvert.install_pillow", text="Install", icon='IMPORT')
            else:
                col.label(text="✓ Pillow installed", icon='CHECKMARK')
            
            if HEIF_MISSING:
                row = col.row()
                row.label(text="❌ pillow-heif", icon='CANCEL')
                row.operator("imageconvert.install_heif", text="Install", icon='IMPORT')
            else:
                col.label(text="✓ pillow-heif installed", icon='CHECKMARK')
            
            box.separator()
            
            # Additional options
            col = box.column(align=True)
            col.label(text="Troubleshooting:", icon='QUESTION')
            col.operator("imageconvert.install_pip", text="Install pip (if needed)", icon='CONSOLE')
            
            if scene.imageconvert_install_log:
                col.operator("imageconvert.show_log", text="Show Installation Log", icon='TEXT')
            
            box.separator()
            info_box = box.box()
            info_box.label(text="After installation:", icon='INFO')
            info_box.label(text="1. Restart Blender completely")
            info_box.label(text="2. Reload this addon if needed")
            
            return
        
        # Normal UI when dependencies are available
        # File Selection
        box = layout.box()
        box.label(text="1. Select Files", icon='FILEBROWSER')
        box.operator("imageconvert.select_files", icon="FILE_IMAGE")
        
        file_count = len([f for f in scene.imageconvert_file_list.split(";") if f])
        if file_count > 0:
            row = box.row()
            row.label(text=f"{file_count} file(s) selected")
            row.operator("imageconvert.clear_files", text="", icon='X')
        
        # Output Settings
        box = layout.box()
        box.label(text="2. Output Settings", icon='SETTINGS')
        box.prop(scene, "imageconvert_output_format", text="Format")
        
        # Quality slider (for JPG and WebP)
        if scene.imageconvert_output_format in ['JPG', 'WEBP']:
            box.prop(scene, "imageconvert_quality", text="Quality")
        
        # Output directory
        box.prop(scene, "imageconvert_output_dir", text="")
        box.operator("imageconvert.select_output", text="Choose Output Folder", icon='FOLDER_REDIRECT')
        if not scene.imageconvert_output_dir:
            box.label(text="(Save to source folder)", icon='INFO')
        
        # Resize Options
        box = layout.box()
        box.label(text="3. Resize (Optional)", icon='FULLSCREEN_EXIT')
        box.prop(scene, "imageconvert_resize_enabled", text="Enable Resize")
        
        if scene.imageconvert_resize_enabled:
            col = box.column(align=True)
            col.prop(scene, "imageconvert_resize_width", text="Width")
            col.prop(scene, "imageconvert_resize_height", text="Height")
            box.prop(scene, "imageconvert_maintain_aspect", text="Maintain Aspect Ratio")
            box.label(text="(0 = keep original)", icon='INFO')
        
        # Convert Button
        layout.separator()
        row = layout.row()
        row.scale_y = 1.5
        row.operator("imageconvert.convert", icon="IMAGE_DATA")
        
        # File List Preview
        if file_count > 0:
            layout.separator()
            box = layout.box()
            box.label(text="Selected Files:", icon='TEXT')
            col = box.column(align=True)
            files = [f for f in scene.imageconvert_file_list.split(";") if f]
            for i, f in enumerate(files[:10]):  # Show first 10
                col.label(text=f"• {os.path.basename(f)}")
            if len(files) > 10:
                col.label(text=f"...and {len(files) - 10} more")

# --- Registration ---
classes = (
    IMAGECONVERT_OT_install_pip,
    IMAGECONVERT_OT_install_pillow,
    IMAGECONVERT_OT_install_heif,
    IMAGECONVERT_OT_select_files,
    IMAGECONVERT_OT_select_output,
    IMAGECONVERT_OT_convert,
    IMAGECONVERT_OT_clear_files,
    IMAGECONVERT_OT_show_log,
    IMAGECONVERT_PT_panel,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    
    bpy.types.Scene.imageconvert_file_list = StringProperty(default="")
    bpy.types.Scene.imageconvert_output_format = EnumProperty(
        name="Output Format",
        items=OUTPUT_FORMATS,
        default='JPG'
    )
    bpy.types.Scene.imageconvert_quality = IntProperty(
        name="Quality",
        description="JPEG/WebP quality (1-100)",
        default=95,
        min=1,
        max=100
    )
    bpy.types.Scene.imageconvert_output_dir = StringProperty(
        name="Output Directory",
        description="Leave empty to save in source folder",
        default="",
        subtype='DIR_PATH'
    )
    bpy.types.Scene.imageconvert_resize_enabled = BoolProperty(
        name="Enable Resize",
        description="Resize images during conversion",
        default=False
    )
    bpy.types.Scene.imageconvert_resize_width = IntProperty(
        name="Width",
        description="Target width (0 = keep original)",
        default=0,
        min=0,
        max=16384
    )
    bpy.types.Scene.imageconvert_resize_height = IntProperty(
        name="Height",
        description="Target height (0 = keep original)",
        default=0,
        min=0,
        max=16384
    )
    bpy.types.Scene.imageconvert_maintain_aspect = BoolProperty(
        name="Maintain Aspect Ratio",
        description="Keep original aspect ratio when resizing",
        default=True
    )
    bpy.types.Scene.imageconvert_install_log = StringProperty(
        name="Installation Log",
        description="Log output from package installation",
        default=""
    )

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    
    del bpy.types.Scene.imageconvert_file_list
    del bpy.types.Scene.imageconvert_output_format
    del bpy.types.Scene.imageconvert_quality
    del bpy.types.Scene.imageconvert_output_dir
    del bpy.types.Scene.imageconvert_resize_enabled
    del bpy.types.Scene.imageconvert_resize_width
    del bpy.types.Scene.imageconvert_resize_height
    del bpy.types.Scene.imageconvert_maintain_aspect
    del bpy.types.Scene.imageconvert_install_log

if __name__ == "__main__":
    register()
