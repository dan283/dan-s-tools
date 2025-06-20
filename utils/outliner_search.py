bl_info = {
    "name": "Outliner Search Panel",
    "author": "ChatGPT",
    "version": (1, 3),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > Outliner Search",
    "description": "Search and select objects in the Outliner based on multiple name inputs.",
    "category": "3D View",
}

import bpy

class SearchEntry(bpy.types.PropertyGroup):
    term: bpy.props.StringProperty(name="Search Term")

class OutlinerSearchProperties(bpy.types.PropertyGroup):
    search_items: bpy.props.CollectionProperty(type=SearchEntry)
    active_index: bpy.props.IntProperty()

class OUTLINERSEARCH_PT_panel(bpy.types.Panel):
    bl_label = "Outliner Search"
    bl_idname = "OUTLINERSEARCH_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Outliner Search'

    def draw(self, context):
        layout = self.layout
        props = context.scene.outliner_search_props

        for i, entry in enumerate(props.search_items):
            row = layout.row(align=True)
            row.prop(entry, "term", text=f"Search {i+1}")
            op = row.operator("outliner_search.select_single", text="", icon='RESTRICT_SELECT_OFF')
            op.index = i

        layout.operator("outliner_search.add_search_item", icon='ADD', text="Add Search Term")
        layout.operator("outliner_search.select_all_matches", text="Select All Matches")

class OUTLINERSEARCH_OT_add_search_item(bpy.types.Operator):
    bl_idname = "outliner_search.add_search_item"
    bl_label = "Add Search Term"

    def execute(self, context):
        context.scene.outliner_search_props.search_items.add()
        return {'FINISHED'}

class OUTLINERSEARCH_OT_select_all_matches(bpy.types.Operator):
    bl_idname = "outliner_search.select_all_matches"
    bl_label = "Select All Matching Objects"

    def execute(self, context):
        props = context.scene.outliner_search_props
        search_terms = [entry.term.lower().strip() for entry in props.search_items if entry.term.strip() != ""]

        if not search_terms:
            self.report({'WARNING'}, "No search terms provided.")
            return {'CANCELLED'}

        for obj in bpy.data.objects:
            obj.select_set(False)

        matches = []
        for obj in bpy.data.objects:
            if any(term in obj.name.lower() for term in search_terms):
                obj.select_set(True)
                matches.append(obj)

        if matches:
            context.view_layer.objects.active = matches[0]
            self.report({'INFO'}, f"Selected {len(matches)} object(s).")
        else:
            self.report({'INFO'}, "No matches found.")

        return {'FINISHED'}

class OUTLINERSEARCH_OT_select_single(bpy.types.Operator):
    bl_idname = "outliner_search.select_single"
    bl_label = "Select Matching Objects for Entry"

    index: bpy.props.IntProperty()

    def execute(self, context):
        props = context.scene.outliner_search_props

        if self.index >= len(props.search_items):
            self.report({'WARNING'}, "Invalid search entry index.")
            return {'CANCELLED'}

        term = props.search_items[self.index].term.lower().strip()
        if not term:
            self.report({'WARNING'}, "Search term is empty.")
            return {'CANCELLED'}

        for obj in bpy.data.objects:
            obj.select_set(False)

        matches = [obj for obj in bpy.data.objects if term in obj.name.lower()]

        for obj in matches:
            obj.select_set(True)

        if matches:
            context.view_layer.objects.active = matches[0]
            self.report({'INFO'}, f"Selected {len(matches)} object(s) for '{term}'.")
        else:
            self.report({'INFO'}, f"No matches for '{term}'.")

        return {'FINISHED'}

def register():
    bpy.utils.register_class(SearchEntry)
    bpy.utils.register_class(OutlinerSearchProperties)
    bpy.utils.register_class(OUTLINERSEARCH_PT_panel)
    bpy.utils.register_class(OUTLINERSEARCH_OT_add_search_item)
    bpy.utils.register_class(OUTLINERSEARCH_OT_select_all_matches)
    bpy.utils.register_class(OUTLINERSEARCH_OT_select_single)
    bpy.types.Scene.outliner_search_props = bpy.props.PointerProperty(type=OutlinerSearchProperties)

def unregister():
    bpy.utils.unregister_class(OUTLINERSEARCH_OT_select_single)
    bpy.utils.unregister_class(OUTLINERSEARCH_OT_select_all_matches)
    bpy.utils.unregister_class(OUTLINERSEARCH_OT_add_search_item)
    bpy.utils.unregister_class(OUTLINERSEARCH_PT_panel)
    bpy.utils.unregister_class(OutlinerSearchProperties)
    bpy.utils.unregister_class(SearchEntry)
    del bpy.types.Scene.outliner_search_props

if __name__ == "__main__":
    register()
