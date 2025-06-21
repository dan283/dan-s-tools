bl_info = {
    "name": "Sawtooth F-Curve Modifier",
    "author": "ChatGPT",
    "version": (1, 9),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Sawtooth Motion",
    "description": "Apply various waveforms as motion on an axis using F-curve modifiers and keyframes",
    "category": "Animation",
}

import bpy
from bpy.types import Panel, Operator, PropertyGroup
from bpy.props import FloatProperty, IntProperty, PointerProperty, EnumProperty


class SawtoothSettings(PropertyGroup):
    amplitude: FloatProperty(
        name="Amplitude",
        default=1.0,
        min=0.0,
        description="Height of the wave"
    )

    frequency: IntProperty(
        name="Frequency",
        default=10,
        min=1,
        description="Number of cycles per 100 frames (approx)"
    )

    axis: EnumProperty(
        name="Axis",
        description="Axis to apply the motion to",
        items=[
            ('X', "X", "Apply to X-axis"),
            ('Y', "Y", "Apply to Y-axis"),
            ('Z', "Z", "Apply to Z-axis")
        ],
        default='Y'
    )

    waveform: EnumProperty(
        name="Waveform",
        description="Select the waveform type",
        items=[
            ('SIN', "Sine", "Smooth sine wave"),
            ('COS', "Cosine", "Smooth cosine wave"),
            ('TAN', "Tangent", "Tangent wave (use carefully)"),
            ('LN', "Logarithm (ln)", "Natural log wave"),
            ('SQRT', "Square Root", "Square root wave"),
            ('SINC', "Sinc", "Normalized sinc wave"),
            ('SAWTOOTH', "Sawtooth", "Sawtooth wave (keyframes)"),
            ('TRIANGLE', "Triangle", "Triangle wave (keyframes, linear ramps)"),
            ('SQUARE', "Square", "Square wave (keyframes, step function)"),
            ('NOISE', "Noise", "Random noise modifier"),
        ],
        default='SAWTOOTH'
    )


class OBJECT_OT_apply_waveform_motion(Operator):
    bl_idname = "object.apply_waveform_motion"
    bl_label = "Apply Waveform Motion"
    bl_description = "Apply selected waveform motion to the chosen axis"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        settings = context.scene.sawtooth_settings

        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}

        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[settings.axis]

        if not obj.animation_data:
            obj.animation_data_create()
        if not obj.animation_data.action:
            obj.animation_data.action = bpy.data.actions.new(name="WaveformMotionAction")

        try:
            obj.keyframe_insert(data_path="location", frame=1, index=axis_idx)
        except RuntimeError:
            self.report({'WARNING'}, "Keyframe insert failed - animation might be locked or NLA active")

        action = obj.animation_data.action
        fcurve = next((fc for fc in action.fcurves if fc.data_path == "location" and fc.array_index == axis_idx), None)

        if not fcurve:
            self.report({'ERROR'}, f"{settings.axis}-location F-curve not found")
            return {'CANCELLED'}

        # Clear existing modifiers and keyframes
        for mod in list(fcurve.modifiers):
            fcurve.modifiers.remove(mod)
        fcurve.keyframe_points.clear()

        cycle_frames = 100 / settings.frequency

        if settings.waveform in {'SIN', 'COS', 'TAN', 'LN', 'SQRT', 'SINC'}:
            gen = fcurve.modifiers.new(type='FNGENERATOR')
            gen.use_additive = True
            gen.function_type = settings.waveform
            gen.phase_multiplier = settings.frequency / 100
            gen.amplitude = settings.amplitude
            gen.phase_offset = 0.0

        elif settings.waveform == 'SAWTOOTH':
            steps = 10
            for i in range(steps + 1):
                frame = i * cycle_frames / steps
                val = settings.amplitude * (i / steps)
                fcurve.keyframe_points.insert(frame, val)
            fcurve.keyframe_points.insert(cycle_frames, 0.0)

            cycles = fcurve.modifiers.new(type='CYCLES')
            cycles.mode_before = 'REPEAT'
            cycles.mode_after = 'REPEAT'

            for kp in fcurve.keyframe_points:
                kp.interpolation = 'LINEAR'

        elif settings.waveform == 'TRIANGLE':
            steps = 10
            half_steps = steps // 2
            for i in range(steps + 1):
                frame = i * cycle_frames / steps
                if i <= half_steps:
                    val = settings.amplitude * (i / half_steps)
                else:
                    val = settings.amplitude * (1 - ((i - half_steps) / half_steps))
                fcurve.keyframe_points.insert(frame, val)

            cycles = fcurve.modifiers.new(type='CYCLES')
            cycles.mode_before = 'REPEAT'
            cycles.mode_after = 'REPEAT'

            for kp in fcurve.keyframe_points:
                kp.interpolation = 'LINEAR'

        elif settings.waveform == 'SQUARE':
            fcurve.keyframe_points.clear()
            half_cycle = cycle_frames / 2

            # On
            fcurve.keyframe_points.insert(0, settings.amplitude)
            fcurve.keyframe_points.insert(half_cycle - 0.001, settings.amplitude)

            # Off
            fcurve.keyframe_points.insert(half_cycle, 0.0)
            fcurve.keyframe_points.insert(cycle_frames - 0.001, 0.0)

            # Wrap
            fcurve.keyframe_points.insert(cycle_frames, settings.amplitude)

            for kp in fcurve.keyframe_points:
                kp.interpolation = 'CONSTANT'

            cycles = fcurve.modifiers.new(type='CYCLES')
            cycles.mode_before = 'REPEAT'
            cycles.mode_after = 'REPEAT'

        elif settings.waveform == 'NOISE':
            # Insert base keyframe at frame 1 for noise to work properly
            fcurve.keyframe_points.insert(1, 0.0)
            for kp in fcurve.keyframe_points:
                kp.interpolation = 'LINEAR'  # baseline smooth

            noise = fcurve.modifiers.new(type='NOISE')
            noise.strength = settings.amplitude
            noise.scale = max(0.01, 1.0 / settings.frequency)
            noise.phase = 0.0
            noise.offset = 0.0

        else:
            self.report({'ERROR'}, "Unknown waveform selected")
            return {'CANCELLED'}

        fcurve.update()
        return {'FINISHED'}


class VIEW3D_PT_sawtooth_motion(Panel):
    bl_label = "Waveform Motion"
    bl_idname = "VIEW3D_PT_sawtooth_motion"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Sawtooth'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.sawtooth_settings

        layout.prop(settings, "amplitude")
        layout.prop(settings, "frequency")
        layout.prop(settings, "axis")
        layout.prop(settings, "waveform")
        layout.operator("object.apply_waveform_motion")


def register():
    bpy.utils.register_class(SawtoothSettings)
    bpy.utils.register_class(OBJECT_OT_apply_waveform_motion)
    bpy.utils.register_class(VIEW3D_PT_sawtooth_motion)
    bpy.types.Scene.sawtooth_settings = PointerProperty(type=SawtoothSettings)


def unregister():
    del bpy.types.Scene.sawtooth_settings
    bpy.utils.unregister_class(SawtoothSettings)
    bpy.utils.unregister_class(OBJECT_OT_apply_waveform_motion)
    bpy.utils.unregister_class(VIEW3D_PT_sawtooth_motion)


if __name__ == "__main__":
    register()
