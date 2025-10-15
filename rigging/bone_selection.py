bl_info = {
    "name": "Advanced Selection Tools",
    "author": "Assistant",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > N-Panel > Selection",
    "description": "Advanced selection tools for rigging and animation",
    "category": "Rigging",
}

import bpy
import re
from bpy.props import (
    StringProperty,
    BoolProperty,
    EnumProperty,
    CollectionProperty,
    IntProperty,
)
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
    UIList,
)


# Selection Set Item
class SELSET_Item(PropertyGroup):
    name: StringProperty(
        name="Name",
        description="Selection set name",
        default="New Set"
    )
    
    object_names: StringProperty(
        name="Objects",
        description="Stored object names (internal)",
        default=""
    )


# Selection Set List UI
class SELSET_UL_List(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "name", text="", emboss=False, icon='GROUP')
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='GROUP')


# Operators
class SELSET_OT_SelectByName(Operator):
    bl_idname = "selset.select_by_name"
    bl_label = "Select by Name"
    bl_description = "Select objects/bones by name pattern"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.selection_tools
        pattern = props.search_pattern
        
        if not pattern:
            self.report({'WARNING'}, "Enter a search pattern")
            return {'CANCELLED'}
        
        mode = props.selection_mode
        partial = props.partial_match
        case_sensitive = props.case_sensitive
        use_regex = props.use_regex
        
        selected_count = 0
        
        # Object mode
        if mode == 'OBJECT':
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            
            bpy.ops.object.select_all(action='DESELECT')
            
            for obj in context.scene.objects:
                if self.name_matches(obj.name, pattern, partial, case_sensitive, use_regex):
                    obj.select_set(True)
                    selected_count += 1
            
            self.report({'INFO'}, f"Selected {selected_count} objects")
        
        # Bone mode
        elif mode == 'BONE':
            if context.mode not in {'POSE', 'EDIT_ARMATURE'}:
                self.report({'WARNING'}, "Enter Pose or Edit mode on an armature")
                return {'CANCELLED'}
            
            armature = context.active_object
            if not armature or armature.type != 'ARMATURE':
                self.report({'WARNING'}, "No active armature")
                return {'CANCELLED'}
            
            if context.mode == 'POSE':
                bpy.ops.pose.select_all(action='DESELECT')
                for bone in armature.pose.bones:
                    if self.name_matches(bone.name, pattern, partial, case_sensitive, use_regex):
                        bone.bone.select = True
                        selected_count += 1
            
            elif context.mode == 'EDIT_ARMATURE':
                bpy.ops.armature.select_all(action='DESELECT')
                for bone in armature.data.edit_bones:
                    if self.name_matches(bone.name, pattern, partial, case_sensitive, use_regex):
                        bone.select = True
                        bone.select_head = True
                        bone.select_tail = True
                        selected_count += 1
            
            self.report({'INFO'}, f"Selected {selected_count} bones")
        
        return {'FINISHED'}
    
    def name_matches(self, name, pattern, partial, case_sensitive, use_regex):
        if not case_sensitive:
            name = name.lower()
            pattern = pattern.lower()
        
        if use_regex:
            try:
                return re.search(pattern, name) is not None
            except:
                return False
        elif partial:
            return pattern in name
        else:
            return name == pattern


class SELSET_OT_SelectSymmetry(Operator):
    bl_idname = "selset.select_symmetry"
    bl_label = "Select Symmetry"
    bl_description = "Select symmetrical bones (L/R, Left/Right)"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        if context.mode not in {'POSE', 'EDIT_ARMATURE'}:
            self.report({'WARNING'}, "Enter Pose or Edit mode on an armature")
            return {'CANCELLED'}
        
        armature = context.active_object
        if not armature or armature.type != 'ARMATURE':
            self.report({'WARNING'}, "No active armature")
            return {'CANCELLED'}
        
        selected_count = 0
        
        if context.mode == 'POSE':
            selected_names = [b.name for b in armature.pose.bones if b.bone.select]
            
            for name in selected_names:
                sym_name = self.get_symmetry_name(name)
                if sym_name:
                    for bone in armature.pose.bones:
                        if bone.name == sym_name:
                            bone.bone.select = True
                            selected_count += 1
        
        elif context.mode == 'EDIT_ARMATURE':
            selected_names = [b.name for b in armature.data.edit_bones if b.select]
            
            for name in selected_names:
                sym_name = self.get_symmetry_name(name)
                if sym_name:
                    for bone in armature.data.edit_bones:
                        if bone.name == sym_name:
                            bone.select = True
                            bone.select_head = True
                            bone.select_tail = True
                            selected_count += 1
        
        self.report({'INFO'}, f"Added {selected_count} symmetrical bones")
        return {'FINISHED'}
    
    def get_symmetry_name(self, name):
        # Handle .L/.R suffix
        if name.endswith('.L'):
            return name[:-2] + '.R'
        elif name.endswith('.R'):
            return name[:-2] + '.L'
        
        # Handle _L/_R suffix
        if name.endswith('_L'):
            return name[:-2] + '_R'
        elif name.endswith('_R'):
            return name[:-2] + '_L'
        
        # Handle Left/Right in name
        if 'Left' in name:
            return name.replace('Left', 'Right')
        elif 'Right' in name:
            return name.replace('Right', 'Left')
        
        if 'left' in name:
            return name.replace('left', 'right')
        elif 'right' in name:
            return name.replace('right', 'left')
        
        return None


class SELSET_OT_SaveSet(Operator):
    bl_idname = "selset.save_set"
    bl_label = "Save Selection Set"
    bl_description = "Save current selection as a set"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.selection_tools
        
        selected_names = []
        
        if context.mode == 'OBJECT':
            selected_names = [obj.name for obj in context.selected_objects]
        elif context.mode == 'POSE':
            armature = context.active_object
            if armature and armature.type == 'ARMATURE':
                selected_names = [b.name for b in armature.pose.bones if b.bone.select]
        elif context.mode == 'EDIT_ARMATURE':
            armature = context.active_object
            if armature and armature.type == 'ARMATURE':
                selected_names = [b.name for b in armature.data.edit_bones if b.select]
        
        if not selected_names:
            self.report({'WARNING'}, "Nothing selected")
            return {'CANCELLED'}
        
        item = props.selection_sets.add()
        item.name = f"Set_{len(props.selection_sets)}"
        item.object_names = ",".join(selected_names)
        props.selection_sets_index = len(props.selection_sets) - 1
        
        self.report({'INFO'}, f"Saved {len(selected_names)} items to set")
        return {'FINISHED'}


class SELSET_OT_LoadSet(Operator):
    bl_idname = "selset.load_set"
    bl_label = "Load Selection Set"
    bl_description = "Load and select items from set"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.selection_tools
        
        if not props.selection_sets:
            self.report({'WARNING'}, "No selection sets")
            return {'CANCELLED'}
        
        item = props.selection_sets[props.selection_sets_index]
        names = item.object_names.split(",")
        
        selected_count = 0
        
        if context.mode == 'OBJECT':
            bpy.ops.object.select_all(action='DESELECT')
            for obj in context.scene.objects:
                if obj.name in names:
                    obj.select_set(True)
                    selected_count += 1
        
        elif context.mode == 'POSE':
            armature = context.active_object
            if armature and armature.type == 'ARMATURE':
                bpy.ops.pose.select_all(action='DESELECT')
                for bone in armature.pose.bones:
                    if bone.name in names:
                        bone.bone.select = True
                        selected_count += 1
        
        elif context.mode == 'EDIT_ARMATURE':
            armature = context.active_object
            if armature and armature.type == 'ARMATURE':
                bpy.ops.armature.select_all(action='DESELECT')
                for bone in armature.data.edit_bones:
                    if bone.name in names:
                        bone.select = True
                        bone.select_head = True
                        bone.select_tail = True
                        selected_count += 1
        
        self.report({'INFO'}, f"Selected {selected_count} items from set")
        return {'FINISHED'}


class SELSET_OT_DeleteSet(Operator):
    bl_idname = "selset.delete_set"
    bl_label = "Delete Selection Set"
    bl_description = "Delete the active selection set"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.selection_tools
        
        if not props.selection_sets:
            return {'CANCELLED'}
        
        props.selection_sets.remove(props.selection_sets_index)
        props.selection_sets_index = min(props.selection_sets_index, len(props.selection_sets) - 1)
        
        return {'FINISHED'}


class SELSET_OT_SelectHierarchy(Operator):
    bl_idname = "selset.select_hierarchy"
    bl_label = "Select Hierarchy"
    bl_description = "Select all children in bone hierarchy"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        if context.mode not in {'POSE', 'EDIT_ARMATURE'}:
            self.report({'WARNING'}, "Enter Pose or Edit mode on an armature")
            return {'CANCELLED'}
        
        armature = context.active_object
        if not armature or armature.type != 'ARMATURE':
            self.report({'WARNING'}, "No active armature")
            return {'CANCELLED'}
        
        if context.mode == 'POSE':
            selected = [b for b in armature.pose.bones if b.bone.select]
            for bone in selected:
                self.select_children_pose(bone)
        
        elif context.mode == 'EDIT_ARMATURE':
            selected = [b for b in armature.data.edit_bones if b.select]
            for bone in selected:
                self.select_children_edit(bone)
        
        return {'FINISHED'}
    
    def select_children_pose(self, bone):
        for child in bone.children:
            child.bone.select = True
            self.select_children_pose(child)
    
    def select_children_edit(self, bone):
        for child in bone.children:
            child.select = True
            child.select_head = True
            child.select_tail = True
            self.select_children_edit(child)


# Properties
class SelectionToolsProperties(PropertyGroup):
    search_pattern: StringProperty(
        name="Pattern",
        description="Search pattern for selection",
        default=""
    )
    
    selection_mode: EnumProperty(
        name="Mode",
        description="What to select",
        items=[
            ('OBJECT', "Objects", "Select objects in scene"),
            ('BONE', "Bones", "Select bones in armature"),
        ],
        default='OBJECT'
    )
    
    partial_match: BoolProperty(
        name="Partial Match",
        description="Match names containing the pattern",
        default=True
    )
    
    case_sensitive: BoolProperty(
        name="Case Sensitive",
        description="Match case when searching",
        default=False
    )
    
    use_regex: BoolProperty(
        name="Use Regex",
        description="Use regular expressions for pattern matching",
        default=False
    )
    
    selection_sets: CollectionProperty(type=SELSET_Item)
    selection_sets_index: IntProperty(default=0)


# Panel
class SELSET_PT_MainPanel(Panel):
    bl_label = "Selection Tools"
    bl_idname = "SELSET_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Selection"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.selection_tools
        
        # Name-based selection
        box = layout.box()
        box.label(text="Select by Name:", icon='VIEWZOOM')
        
        box.prop(props, "selection_mode", text="")
        box.prop(props, "search_pattern", text="")
        
        row = box.row(align=True)
        row.prop(props, "partial_match", toggle=True)
        row.prop(props, "case_sensitive", toggle=True)
        row.prop(props, "use_regex", toggle=True)
        
        box.operator("selset.select_by_name", icon='RESTRICT_SELECT_OFF')
        
        # Rigging tools
        box = layout.box()
        box.label(text="Rigging Tools:", icon='ARMATURE_DATA')
        box.operator("selset.select_symmetry", icon='MOD_MIRROR')
        box.operator("selset.select_hierarchy", icon='OUTLINER')
        
        # Selection sets
        box = layout.box()
        box.label(text="Selection Sets:", icon='GROUP')
        
        row = box.row()
        row.template_list("SELSET_UL_List", "", props, "selection_sets", 
                         props, "selection_sets_index", rows=3)
        
        col = row.column(align=True)
        col.operator("selset.save_set", icon='ADD', text="")
        col.operator("selset.delete_set", icon='REMOVE', text="")
        
        if props.selection_sets:
            box.operator("selset.load_set", icon='RESTRICT_SELECT_OFF')


# Registration
classes = (
    SELSET_Item,
    SELSET_UL_List,
    SELSET_OT_SelectByName,
    SELSET_OT_SelectSymmetry,
    SELSET_OT_SaveSet,
    SELSET_OT_LoadSet,
    SELSET_OT_DeleteSet,
    SELSET_OT_SelectHierarchy,
    SelectionToolsProperties,
    SELSET_PT_MainPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.selection_tools = bpy.props.PointerProperty(type=SelectionToolsProperties)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.selection_tools


if __name__ == "__main__":
    register()
