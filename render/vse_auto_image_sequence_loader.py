
bl_info = {
    "name": "VSE Auto Image Sequence Loader",
    "author": "OpenAI",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "location": "Video Sequencer > Sidebar > Sequence Loader",
    "description": "Detect and load numbered image sequences from a folder without selecting first/last frames",
    "category": "Sequencer",
}

import bpy
import os
import re
from pathlib import Path
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup, UIList


IMAGE_EXTENSIONS = {
    ".bmp", ".cin", ".dpx", ".exr", ".hdr", ".jpeg", ".jpg",
    ".jp2", ".png", ".psd", ".tga", ".tif", ".tiff", ".webp"
}

# Captures the final run of digits before the extension:
# shot_beauty.0012.exr -> prefix "shot_beauty.", frame 12, suffix ".exr"
FRAME_RE = re.compile(r"^(.*?)(\d+)(\.[^.]+)$")


def natural_key(text):
    return [
        int(chunk) if chunk.isdigit() else chunk.casefold()
        for chunk in re.split(r"(\d+)", text)
    ]


def sequence_editor(scene):
    if scene.sequence_editor is None:
        scene.sequence_editor_create()
    return scene.sequence_editor


def strips_collection(scene):
    editor = sequence_editor(scene)
    # Blender 5.x uses editor.strips. Keep fallback for older API layouts.
    return getattr(editor, "strips", getattr(editor, "sequences", None))


def scan_sequences(settings):
    root = Path(bpy.path.abspath(settings.directory)).expanduser()
    if not root.is_dir():
        return [], f"Folder does not exist: {root}"

    iterator = root.rglob("*") if settings.recursive else root.iterdir()
    groups = {}

    for path in iterator:
        if not path.is_file() or path.suffix.casefold() not in IMAGE_EXTENSIONS:
            continue

        match = FRAME_RE.match(path.name)
        if not match:
            continue

        prefix, digits, suffix = match.groups()
        key = (str(path.parent), prefix, suffix.casefold(), len(digits))
        groups.setdefault(key, []).append((int(digits), path.name, str(path)))

    results = []
    for (folder, prefix, suffix, padding), frames in groups.items():
        frames.sort(key=lambda item: (item[0], natural_key(item[1])))

        # Avoid treating a single numbered still as a sequence unless requested.
        if len(frames) < settings.minimum_frames:
            continue

        numbers = [item[0] for item in frames]
        missing = max(0, numbers[-1] - numbers[0] + 1 - len(set(numbers)))
        display_name = f"{prefix}[{numbers[0]:0{padding}d}-{numbers[-1]:0{padding}d}]{suffix}"

        results.append({
            "name": display_name,
            "folder": folder,
            "prefix": prefix,
            "suffix": suffix,
            "padding": padding,
            "first": numbers[0],
            "last": numbers[-1],
            "count": len(frames),
            "missing": missing,
            "files": [item[2] for item in frames],
        })

    results.sort(key=lambda item: natural_key(os.path.join(item["folder"], item["name"])))
    return results, ""


def first_free_channel(scene, start_channel, frame_start, duration):
    strips = strips_collection(scene)
    channel = max(1, start_channel)
    frame_end = frame_start + max(1, duration)

    while True:
        collision = False
        for strip in strips:
            if strip.channel != channel:
                continue
            if strip.frame_final_start < frame_end and strip.frame_final_end > frame_start:
                collision = True
                break
        if not collision:
            return channel
        channel += 1


class VSEAIL_SequenceItem(PropertyGroup):
    selected: BoolProperty(name="Load", default=True)
    display_name: StringProperty()
    folder: StringProperty()
    first_frame: IntProperty()
    last_frame: IntProperty()
    file_count: IntProperty()
    missing_count: IntProperty()


class VSEAIL_Settings(PropertyGroup):
    directory: StringProperty(
        name="Folder",
        subtype="DIR_PATH",
        description="Folder containing numbered image sequences",
    )
    recursive: BoolProperty(
        name="Include Subfolders",
        default=False,
    )
    minimum_frames: IntProperty(
        name="Minimum Frames",
        default=2,
        min=1,
        description="Minimum files required before a numbered set is considered a sequence",
    )
    frame_start: IntProperty(
        name="Timeline Start",
        default=1,
        min=-1048574,
        max=1048574,
    )
    channel: IntProperty(
        name="Starting Channel",
        default=1,
        min=1,
        max=128,
    )
    placement: EnumProperty(
        name="Placement",
        items=[
            ("STACK", "Stack Channels", "All sequences begin on the same frame, using separate channels"),
            ("SEQUENTIAL", "Place Sequentially", "Place sequences one after another"),
        ],
        default="STACK",
    )
    skip_existing: BoolProperty(
        name="Skip Existing",
        default=True,
        description="Skip a sequence if its first image is already used by an image strip",
    )
    set_scene_range: BoolProperty(
        name="Set Scene Range",
        default=True,
        description="Expand the scene frame range to include imported strips",
    )
    fit_method: EnumProperty(
        name="Image Fit",
        items=[
            ("ORIGINAL", "Original", "Keep original image size"),
            ("FIT", "Fit", "Fit entire image inside the render frame"),
            ("FILL", "Fill", "Fill render frame, cropping where necessary"),
            ("STRETCH", "Stretch", "Stretch to render frame"),
        ],
        default="FIT",
    )


class VSEAIL_UL_sequences(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        col = row.column()
        col.label(text=item.display_name, icon="IMAGE_DATA")
        status = f"{item.file_count} frames"
        if item.missing_count:
            status += f"  |  {item.missing_count} missing"
        col.label(text=status)


class VSEAIL_OT_scan(Operator):
    bl_idname = "vse_auto_loader.scan"
    bl_label = "Scan Folder"
    bl_description = "Find all numbered image sequences in the selected folder"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        settings = scene.vse_auto_loader_settings
        items = scene.vse_auto_loader_items
        items.clear()

        found, error = scan_sequences(settings)
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}

        for seq in found:
            item = items.add()
            item.selected = True
            item.display_name = seq["name"]
            item.folder = seq["folder"]
            item.first_frame = seq["first"]
            item.last_frame = seq["last"]
            item.file_count = seq["count"]
            item.missing_count = seq["missing"]

        scene.vse_auto_loader_index = 0
        self.report({"INFO"}, f"Found {len(found)} image sequence(s)")
        return {"FINISHED"}


class VSEAIL_OT_select_all(Operator):
    bl_idname = "vse_auto_loader.select_all"
    bl_label = "Select All"

    value: BoolProperty(default=True)

    def execute(self, context):
        for item in context.scene.vse_auto_loader_items:
            item.selected = self.value
        return {"FINISHED"}


class VSEAIL_OT_load(Operator):
    bl_idname = "vse_auto_loader.load"
    bl_label = "Load Selected Sequences"
    bl_description = "Create VSE image strips for all selected detected sequences"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        settings = scene.vse_auto_loader_settings
        listed = scene.vse_auto_loader_items

        detected, error = scan_sequences(settings)
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}

        selected_keys = {
            (item.folder, item.display_name)
            for item in listed if item.selected
        }
        sequences = [
            seq for seq in detected
            if (seq["folder"], seq["name"]) in selected_keys
        ]

        if not sequences:
            self.report({"WARNING"}, "No sequences selected")
            return {"CANCELLED"}

        strips = strips_collection(scene)
        if strips is None:
            self.report({"ERROR"}, "Could not access the VSE strip collection")
            return {"CANCELLED"}

        existing_first_files = set()
        if settings.skip_existing:
            for strip in strips:
                if getattr(strip, "type", "") != "IMAGE":
                    continue
                directory = getattr(strip, "directory", "")
                elements = getattr(strip, "elements", None)
                if elements and len(elements):
                    existing_first_files.add(
                        os.path.normcase(os.path.abspath(os.path.join(directory, elements[0].filename)))
                    )

        loaded = 0
        skipped = 0
        cursor = settings.frame_start
        max_end = scene.frame_end

        for seq in sequences:
            first_file = os.path.normcase(os.path.abspath(seq["files"][0]))
            if settings.skip_existing and first_file in existing_first_files:
                skipped += 1
                continue

            start = cursor if settings.placement == "SEQUENTIAL" else settings.frame_start
            channel = first_free_channel(scene, settings.channel, start, seq["count"])

            try:
                strip = strips.new_image(
                    name=seq["name"],
                    filepath=seq["files"][0],
                    channel=channel,
                    frame_start=start,
                    fit_method=settings.fit_method,
                )
            except TypeError:
                # Compatibility fallback if fit_method is unavailable.
                strip = strips.new_image(
                    name=seq["name"],
                    filepath=seq["files"][0],
                    channel=channel,
                    frame_start=start,
                )

            for filepath in seq["files"][1:]:
                strip.elements.append(os.path.basename(filepath))

            # Match strip duration to the number of loaded files.
            strip.frame_final_duration = len(seq["files"])

            loaded += 1
            end = start + len(seq["files"]) - 1
            max_end = max(max_end, end)

            if settings.placement == "SEQUENTIAL":
                cursor = end + 1

        if settings.set_scene_range and loaded:
            scene.frame_start = min(scene.frame_start, settings.frame_start)
            scene.frame_end = max_end

        self.report({"INFO"}, f"Loaded {loaded} sequence(s); skipped {skipped}")
        return {"FINISHED"}


class VSEAIL_PT_panel(Panel):
    bl_label = "Auto Sequence Loader"
    bl_idname = "VSEAIL_PT_panel"
    bl_space_type = "SEQUENCE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Sequence Loader"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.vse_auto_loader_settings

        col = layout.column(align=True)
        col.prop(settings, "directory")
        row = col.row(align=True)
        row.prop(settings, "recursive")
        row.prop(settings, "minimum_frames")

        col.operator("vse_auto_loader.scan", icon="VIEWZOOM")

        items = scene.vse_auto_loader_items
        if items:
            layout.template_list(
                "VSEAIL_UL_sequences",
                "",
                scene,
                "vse_auto_loader_items",
                scene,
                "vse_auto_loader_index",
                rows=min(8, max(3, len(items))),
            )
            row = layout.row(align=True)
            op = row.operator("vse_auto_loader.select_all", text="All")
            op.value = True
            op = row.operator("vse_auto_loader.select_all", text="None")
            op.value = False

            box = layout.box()
            box.prop(settings, "frame_start")
            box.prop(settings, "channel")
            box.prop(settings, "placement")
            box.prop(settings, "fit_method")
            box.prop(settings, "skip_existing")
            box.prop(settings, "set_scene_range")

            layout.operator("vse_auto_loader.load", icon="ADD")
        else:
            layout.label(text="Choose a folder, then Scan Folder.", icon="INFO")


classes = (
    VSEAIL_SequenceItem,
    VSEAIL_Settings,
    VSEAIL_UL_sequences,
    VSEAIL_OT_scan,
    VSEAIL_OT_select_all,
    VSEAIL_OT_load,
    VSEAIL_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.vse_auto_loader_settings = PointerProperty(type=VSEAIL_Settings)
    bpy.types.Scene.vse_auto_loader_items = CollectionProperty(type=VSEAIL_SequenceItem)
    bpy.types.Scene.vse_auto_loader_index = IntProperty(default=0)


def unregister():
    del bpy.types.Scene.vse_auto_loader_index
    del bpy.types.Scene.vse_auto_loader_items
    del bpy.types.Scene.vse_auto_loader_settings

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
