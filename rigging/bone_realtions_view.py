bl_info = {
    "name": "Bone Hierarchy Analyzer",
    "author": "Assistant",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > N-Panel > Bone Analyzer",
    "description": "Visualize bone hierarchies, relationships, and constraints",
    "category": "Rigging",
}

import bpy
import gpu
import blf
from gpu_extras.batch import batch_for_shader
from bpy.props import BoolProperty, FloatProperty
from bpy.types import Panel, Operator, PropertyGroup
from mathutils import Vector, Matrix


# Global storage for visualization data
_viz_data = {
    'exposed_bones': [],
    'original_matrices': {},
    'hierarchy_lines': [],
    'constraint_lines': [],
    'is_active': False,
}

_draw_handler = None


def get_constraint_info(pose_bone):
    """Extract constraint information from a pose bone"""
    infos = []
    for con in pose_bone.constraints:
        info = {'type': con.type, 'target': None}
        
        if hasattr(con, 'target') and con.target:
            if hasattr(con, 'subtarget') and con.subtarget:
                info['target'] = con.subtarget
            else:
                info['target'] = con.target.name
        
        infos.append(info)
    
    return infos


def build_hierarchy_tree(selected_bones):
    """Build a tree structure from selected bones"""
    roots = []
    
    for bone in selected_bones:
        # Find root bones (no parent in selection)
        if not bone.parent or bone.parent not in selected_bones:
            roots.append(bone)
    
    return roots


def assign_bone_levels(roots, selected_bones):
    """Recursively assign depth levels to bones"""
    levels = {}
    
    def recurse(bone, level):
        levels[bone] = level
        for child in bone.children:
            if child in selected_bones:
                recurse(child, level + 1)
    
    for root in roots:
        recurse(root, 0)
    
    return levels


def calculate_bone_layout(selected_bones, h_spacing, v_spacing):
    """Calculate non-overlapping positions for bones"""
    if not selected_bones:
        return {}
    
    roots = build_hierarchy_tree(selected_bones)
    levels_dict = assign_bone_levels(roots, selected_bones)
    
    # Group bones by level
    level_groups = {}
    for bone, level in levels_dict.items():
        if level not in level_groups:
            level_groups[level] = []
        level_groups[level].append(bone)
    
    # Calculate positions
    positions = {}
    
    for level_idx in sorted(level_groups.keys()):
        bones_at_level = level_groups[level_idx]
        num_bones = len(bones_at_level)
        
        # Center the bones horizontally
        start_x = -(num_bones - 1) * h_spacing / 2.0
        
        for i, bone in enumerate(bones_at_level):
            x = start_x + i * h_spacing
            y = -level_idx * v_spacing
            z = 0.0
            
            positions[bone] = Vector((x, y, z))
    
    return positions


def store_original_transforms(selected_bones):
    """Store original bone transforms for restoration"""
    _viz_data['original_matrices'].clear()
    
    for bone in selected_bones:
        _viz_data['original_matrices'][bone.name] = bone.matrix.copy()


def apply_bone_layout(armature, positions):
    """Apply calculated positions to bones"""
    for bone, pos in positions.items():
        # Set bone to new position
        bone.matrix = Matrix.Translation(pos)


def calculate_relationship_lines(selected_bones, positions, armature):
    """Calculate lines for hierarchy and constraints"""
    _viz_data['hierarchy_lines'].clear()
    _viz_data['constraint_lines'].clear()
    
    # Parent-child hierarchy lines
    for bone in selected_bones:
        if bone.parent and bone.parent in selected_bones:
            if bone in positions and bone.parent in positions:
                start = armature.matrix_world @ positions[bone.parent]
                end = armature.matrix_world @ positions[bone]
                _viz_data['hierarchy_lines'].append((start, end))
    
    # Constraint lines
    for bone in selected_bones:
        bone_pos = positions.get(bone)
        if not bone_pos:
            continue
        
        for constraint in bone.constraints:
            if hasattr(constraint, 'target') and constraint.target == armature:
                if hasattr(constraint, 'subtarget') and constraint.subtarget:
                    target_bone = armature.pose.bones.get(constraint.subtarget)
                    if target_bone and target_bone in selected_bones:
                        target_pos = positions.get(target_bone)
                        if target_pos:
                            start = armature.matrix_world @ bone_pos
                            end = armature.matrix_world @ target_pos
                            _viz_data['constraint_lines'].append((start, end))


def store_visualization_data(armature, selected_bones, positions):
    """Store all data needed for drawing"""
    _viz_data['exposed_bones'].clear()
    
    for bone in selected_bones:
        if bone not in positions:
            continue
        
        constraints = get_constraint_info(bone)
        
        data = {
            'name': bone.name,
            'position': positions[bone],
            'world_position': armature.matrix_world @ positions[bone],
            'constraints': constraints,
            'parent_name': bone.parent.name if bone.parent and bone.parent in selected_bones else None,
        }
        
        _viz_data['exposed_bones'].append(data)


def draw_callback_px():
    """Draw handler for viewport overlay"""
    context = bpy.context
    
    if not context.scene.bone_analyzer.show_visualization:
        return
    
    if not _viz_data['is_active']:
        return
    
    armature = context.active_object
    if not armature or armature.type != 'ARMATURE':
        return
    
    if context.mode != 'POSE':
        return
    
    region = context.region
    rv3d = context.region_data
    
    if not region or not rv3d:
        return
    
    # Import here to avoid issues during registration
    import bpy_extras.view3d_utils
    
    # Enable alpha blending
    gpu.state.blend_set('ALPHA')
    
    props = context.scene.bone_analyzer
    
    # Draw hierarchy lines (blue)
    if props.show_relationships and _viz_data['hierarchy_lines']:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()
        shader.uniform_float("color", (0.3, 0.6, 1.0, 0.7))
        
        gpu.state.line_width_set(3.0)
        
        for start_3d, end_3d in _viz_data['hierarchy_lines']:
            start_2d = bpy_extras.view3d_utils.location_3d_to_region_2d(region, rv3d, start_3d)
            end_2d = bpy_extras.view3d_utils.location_3d_to_region_2d(region, rv3d, end_3d)
            
            if start_2d and end_2d:
                vertices = [(start_2d[0], start_2d[1]), (end_2d[0], end_2d[1])]
                batch = batch_for_shader(shader, 'LINES', {"pos": vertices})
                batch.draw(shader)
    
    # Draw constraint lines (orange)
    if props.show_relationships and _viz_data['constraint_lines']:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()
        shader.uniform_float("color", (1.0, 0.5, 0.0, 0.6))
        
        gpu.state.line_width_set(2.0)
        
        for start_3d, end_3d in _viz_data['constraint_lines']:
            start_2d = bpy_extras.view3d_utils.location_3d_to_region_2d(region, rv3d, start_3d)
            end_2d = bpy_extras.view3d_utils.location_3d_to_region_2d(region, rv3d, end_3d)
            
            if start_2d and end_2d:
                vertices = [(start_2d[0], start_2d[1]), (end_2d[0], end_2d[1])]
                batch = batch_for_shader(shader, 'LINES', {"pos": vertices})
                batch.draw(shader)
    
    # Draw bone points and labels
    font_id = 0
    blf.size(font_id, 13)
    
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    
    for bone_data in _viz_data['exposed_bones']:
        pos_3d = bone_data['world_position']
        pos_2d = bpy_extras.view3d_utils.location_3d_to_region_2d(region, rv3d, pos_3d)
        
        if not pos_2d:
            continue
        
        # Draw bone marker point
        shader.uniform_float("color", (1.0, 0.8, 0.2, 1.0))
        gpu.state.point_size_set(12.0)
        
        vertices = [(pos_2d[0], pos_2d[1])]
        batch = batch_for_shader(shader, 'POINTS', {"pos": vertices})
        batch.draw(shader)
        
        # Draw bone name
        blf.position(font_id, pos_2d[0] + 12, pos_2d[1] + 8, 0)
        blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
        blf.draw(font_id, bone_data['name'])
        
        # Draw constraints
        y_offset = -8
        for con_info in bone_data['constraints']:
            con_text = f"  {con_info['type']}"
            if con_info['target']:
                con_text += f" → {con_info['target']}"
            
            blf.position(font_id, pos_2d[0] + 12, pos_2d[1] + y_offset, 0)
            blf.color(font_id, 1.0, 0.6, 0.2, 0.9)
            blf.draw(font_id, con_text)
            
            y_offset -= 14
    
    # Reset GPU state
    gpu.state.blend_set('NONE')
    gpu.state.line_width_set(1.0)
    gpu.state.point_size_set(1.0)


# Operators
class BONEANAL_OT_ExposeBones(Operator):
    bl_idname = "boneanal.expose_bones"
    bl_label = "Expose Selected Bones"
    bl_description = "Isolate and arrange selected bones for analysis"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        armature = context.active_object
        
        if not armature or armature.type != 'ARMATURE':
            self.report({'WARNING'}, "Select an armature")
            return {'CANCELLED'}
        
        if context.mode != 'POSE':
            self.report({'WARNING'}, "Switch to Pose mode")
            return {'CANCELLED'}
        
        selected_bones = [b for b in armature.pose.bones if b.bone.select]
        
        if not selected_bones:
            self.report({'WARNING'}, "No bones selected")
            return {'CANCELLED'}
        
        # Store original transforms
        store_original_transforms(selected_bones)
        
        # Calculate layout
        props = context.scene.bone_analyzer
        positions = calculate_bone_layout(
            selected_bones,
            props.horizontal_spacing,
            props.vertical_spacing
        )
        
        # Apply layout
        apply_bone_layout(armature, positions)
        
        # Calculate relationship lines
        calculate_relationship_lines(selected_bones, positions, armature)
        
        # Store visualization data
        store_visualization_data(armature, selected_bones, positions)
        
        # Activate visualization
        _viz_data['is_active'] = True
        context.scene.bone_analyzer.show_visualization = True
        
        # Force viewport update
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        self.report({'INFO'}, f"Exposed {len(selected_bones)} bones")
        return {'FINISHED'}


class BONEANAL_OT_RestoreBones(Operator):
    bl_idname = "boneanal.restore_bones"
    bl_label = "Restore Bones"
    bl_description = "Restore bones to their original positions"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        armature = context.active_object
        
        if not armature or armature.type != 'ARMATURE':
            return {'CANCELLED'}
        
        if context.mode != 'POSE':
            return {'CANCELLED'}
        
        # Restore original matrices
        for bone_name, matrix in _viz_data['original_matrices'].items():
            if bone_name in armature.pose.bones:
                armature.pose.bones[bone_name].matrix = matrix.copy()
        
        # Clear visualization data
        _viz_data['exposed_bones'].clear()
        _viz_data['original_matrices'].clear()
        _viz_data['hierarchy_lines'].clear()
        _viz_data['constraint_lines'].clear()
        _viz_data['is_active'] = False
        
        context.scene.bone_analyzer.show_visualization = False
        
        # Force viewport update
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        self.report({'INFO'}, "Bones restored")
        return {'FINISHED'}


class BONEANAL_OT_Recalculate(Operator):
    bl_idname = "boneanal.recalculate"
    bl_label = "Recalculate Layout"
    bl_description = "Recalculate bone layout with current spacing settings"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        if not _viz_data['is_active']:
            return {'CANCELLED'}
        
        armature = context.active_object
        
        if not armature or armature.type != 'ARMATURE':
            return {'CANCELLED'}
        
        if context.mode != 'POSE':
            return {'CANCELLED'}
        
        # Restore original positions first
        for bone_name, matrix in _viz_data['original_matrices'].items():
            if bone_name in armature.pose.bones:
                armature.pose.bones[bone_name].matrix = matrix.copy()
        
        # Get selected bones
        selected_bones = [b for b in armature.pose.bones if b.bone.select]
        
        if not selected_bones:
            return {'CANCELLED'}
        
        # Recalculate layout
        props = context.scene.bone_analyzer
        positions = calculate_bone_layout(
            selected_bones,
            props.horizontal_spacing,
            props.vertical_spacing
        )
        
        # Apply new layout
        apply_bone_layout(armature, positions)
        
        # Recalculate lines
        calculate_relationship_lines(selected_bones, positions, armature)
        
        # Update visualization data
        store_visualization_data(armature, selected_bones, positions)
        
        # Force viewport update
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}


# Properties
class BoneAnalyzerProperties(PropertyGroup):
    show_visualization: BoolProperty(
        name="Show Visualization",
        description="Display bone hierarchy overlay in viewport",
        default=False,
        update=lambda self, context: tag_redraw_all(context)
    )
    
    show_relationships: BoolProperty(
        name="Show Relationships",
        description="Draw lines showing hierarchy and constraint connections",
        default=True,
        update=lambda self, context: tag_redraw_all(context)
    )
    
    horizontal_spacing: FloatProperty(
        name="Horizontal Spacing",
        description="Distance between bones at the same hierarchy level",
        default=2.0,
        min=0.5,
        max=10.0,
        step=10,
        update=lambda self, context: recalc_if_active()
    )
    
    vertical_spacing: FloatProperty(
        name="Vertical Spacing",
        description="Distance between hierarchy levels",
        default=3.0,
        min=0.5,
        max=10.0,
        step=10,
        update=lambda self, context: recalc_if_active()
    )


def tag_redraw_all(context):
    """Force all 3D viewports to redraw"""
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def recalc_if_active():
    """Recalculate layout if visualization is active"""
    if _viz_data['is_active']:
        bpy.ops.boneanal.recalculate()


# Panel
class BONEANAL_PT_MainPanel(Panel):
    bl_label = "Bone Analyzer"
    bl_idname = "BONEANAL_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Bone Analyzer"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.bone_analyzer
        
        # Main controls
        box = layout.box()
        box.label(text="Expose Bones:", icon='OUTLINER_OB_ARMATURE')
        
        col = box.column(align=True)
        row = col.row(align=True)
        row.scale_y = 1.3
        row.operator("boneanal.expose_bones", text="Expose", icon='ZOOM_SELECTED')
        row.operator("boneanal.restore_bones", text="Restore", icon='LOOP_BACK')
        
        # Visualization toggles
        box = layout.box()
        box.label(text="Display:", icon='OVERLAY')
        box.prop(props, "show_visualization", text="Show Overlay", toggle=True)
        box.prop(props, "show_relationships", text="Show Relations", toggle=True)
        
        # Layout settings
        box = layout.box()
        box.label(text="Layout:", icon='GRID')
        box.prop(props, "horizontal_spacing", slider=True)
        box.prop(props, "vertical_spacing", slider=True)
        
        # Status info
        if _viz_data['is_active']:
            box = layout.box()
            num_bones = len(_viz_data['exposed_bones'])
            box.label(text=f"Active: {num_bones} bones", icon='INFO')
            
            if _viz_data['hierarchy_lines']:
                box.label(text=f"{len(_viz_data['hierarchy_lines'])} hierarchy links")
            if _viz_data['constraint_lines']:
                box.label(text=f"{len(_viz_data['constraint_lines'])} constraints")


# Registration
classes = (
    BoneAnalyzerProperties,
    BONEANAL_OT_ExposeBones,
    BONEANAL_OT_RestoreBones,
    BONEANAL_OT_Recalculate,
    BONEANAL_PT_MainPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.bone_analyzer = bpy.props.PointerProperty(type=BoneAnalyzerProperties)
    
    # Register draw handler
    global _draw_handler
    _draw_handler = bpy.types.SpaceView3D.draw_handler_add(
        draw_callback_px, (), 'WINDOW', 'POST_PIXEL'
    )


def unregister():
    # Remove draw handler
    global _draw_handler
    if _draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, 'WINDOW')
        _draw_handler = None
    
    # Clear data
    _viz_data['exposed_bones'].clear()
    _viz_data['original_matrices'].clear()
    _viz_data['hierarchy_lines'].clear()
    _viz_data['constraint_lines'].clear()
    _viz_data['is_active'] = False
    
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.bone_analyzer


if __name__ == "__main__":
    register()
