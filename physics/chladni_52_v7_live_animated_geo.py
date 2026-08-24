
bl_info = {
    "name": "Chladni 5.2 Sequencer Live",
    "author": "OpenAI",
    "version": (7, 0, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Chladni 5.2",
    "description": "Live shader Chladni preview plus Geometry Nodes simulation",
    "category": "Physics",
}

import bpy
import math
import traceback
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import (
    PointerProperty, IntProperty, FloatProperty, BoolProperty,
    EnumProperty, FloatVectorProperty, CollectionProperty, StringProperty
)

MAT_NAME = "CHLADNI52_PREVIEW"
GN_NAME = "CHLADNI52_SIM"
MOD_NAME = "Chladni52 Simulation"
VEL_ATTR = "chladni_vel"

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def plate(context):
    o = context.object
    return o if o and o.type == 'MESH' else None

def bounds_xy(obj):
    if not obj or not obj.data.vertices:
        return -1.0, 1.0, -1.0, 1.0
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    return min(xs), max(xs), min(ys), max(ys)

def size_xy(obj):
    x0,x1,y0,y1 = bounds_xy(obj)
    return max(x1-x0, 1e-6), max(y1-y0, 1e-6)

def N(nt, type_id, name, x, y):
    n = nt.nodes.new(type_id)
    n.name = name
    n.label = name
    n.location = (x,y)
    return n

def V(nt, name, value, x, y):
    n = N(nt, 'ShaderNodeValue', name, x, y)
    n.outputs[0].default_value = float(value)
    return n

def M(nt, op, name, x, y, b=None):
    n = N(nt, 'ShaderNodeMath', name, x, y)
    n.operation = op
    if b is not None:
        n.inputs[1].default_value = b
    return n

def VM(nt, op, name, x, y):
    n = N(nt, 'ShaderNodeVectorMath', name, x, y)
    n.operation = op
    return n

def S(sockets, name, index=None):
    s = sockets.get(name)
    if s is not None:
        return s
    if index is not None:
        try:
            return sockets[index]
        except:
            return None
    return None

def L(nt, a, b):
    if a is not None and b is not None:
        nt.links.new(a,b)

def set_value(tree, name, value):
    if tree:
        n = tree.nodes.get(name)
        if n and n.bl_idname == 'ShaderNodeValue':
            n.outputs[0].default_value = float(value)


def drive_socket(socket_obj, scene, data_path, expression="var"):
    """Drive a node socket default value directly from a Scene property."""
    try:
        socket_obj.driver_remove("default_value")
    except Exception:
        pass
    fcurve = socket_obj.driver_add("default_value")
    drv = fcurve.driver
    drv.type = 'SCRIPTED'
    var = drv.variables.new()
    var.name = "var"
    var.type = 'SINGLE_PROP'
    target = var.targets[0]
    target.id_type = 'SCENE'
    target.id = scene
    target.data_path = data_path
    drv.expression = expression
    return fcurve

def drive_value_node(node, scene, data_path, expression="var"):
    return drive_socket(node.outputs[0], scene, data_path, expression)


# -------------------------------------------------------------------
# Shared formula helpers
# phi = (1-k) A + sign*k B
# classic: A=cos(m*pi*u)cos(n*pi*v), B=cos(n*pi*u)cos(m*pi*v)
# supported: sin equivalents
# -------------------------------------------------------------------

def trig(nt, coord, mode, op, x, y, tag):
    a = M(nt,'MULTIPLY',tag+' coord*mode',x,y)
    L(nt,coord,a.inputs[0]); L(nt,mode,a.inputs[1])
    p = M(nt,'MULTIPLY',tag+' *pi',x+140,y,math.pi)
    L(nt,a.outputs[0],p.inputs[0])
    t = M(nt,op,tag+' trig',x+280,y)
    L(nt,p.outputs[0],t.inputs[0])
    return t.outputs[0]

def phi_network(nt, u, v, m, n, mix, sign, use_sine, x, y, prefix):
    op = 'SINE' if use_sine else 'COSINE'
    t1 = trig(nt,u,m,op,x,y+180,prefix+' um')
    t2 = trig(nt,v,n,op,x,y+80,prefix+' vn')
    t3 = trig(nt,u,n,op,x,y-80,prefix+' un')
    t4 = trig(nt,v,m,op,x,y-180,prefix+' vm')

    A = M(nt,'MULTIPLY',prefix+' A',x+440,y+130)
    B = M(nt,'MULTIPLY',prefix+' B',x+440,y-130)
    L(nt,t1,A.inputs[0]); L(nt,t2,A.inputs[1])
    L(nt,t3,B.inputs[0]); L(nt,t4,B.inputs[1])

    om = M(nt,'SUBTRACT',prefix+' 1-mix',x+440,y-300)
    om.inputs[0].default_value = 1.0
    L(nt,mix,om.inputs[1])

    Aw = M(nt,'MULTIPLY',prefix+' Aw',x+600,y+130)
    Bw = M(nt,'MULTIPLY',prefix+' Bw',x+600,y-130)
    L(nt,A.outputs[0],Aw.inputs[0]); L(nt,om.outputs[0],Aw.inputs[1])
    L(nt,B.outputs[0],Bw.inputs[0]); L(nt,mix,Bw.inputs[1])

    Bs = M(nt,'MULTIPLY',prefix+' Bs',x+750,y-130)
    L(nt,Bw.outputs[0],Bs.inputs[0]); L(nt,sign,Bs.inputs[1])

    ph = M(nt,'ADD',prefix+' phi',x+900,y)
    L(nt,Aw.outputs[0],ph.inputs[0]); L(nt,Bs.outputs[0],ph.inputs[1])
    return ph.outputs[0]

# -------------------------------------------------------------------
# Shader preview
# -------------------------------------------------------------------

def make_preview(settings, obj):
    mat = bpy.data.materials.get(MAT_NAME)
    if not mat:
        mat = bpy.data.materials.new(MAT_NAME)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = N(nt,'ShaderNodeOutputMaterial','Output',1150,0)
    bs = N(nt,'ShaderNodeBsdfPrincipled','Surface',900,0)
    L(nt,bs.outputs['BSDF'],out.inputs['Surface'])

    tc = N(nt,'ShaderNodeTexCoord','Coordinates',-1350,0)
    sep = N(nt,'ShaderNodeSeparateXYZ','XY',-1170,0)
    L(nt,tc.outputs['Generated'],sep.inputs['Vector'])

    m = V(nt,'P_M',settings.m,-1320,-200)
    n = V(nt,'P_N',settings.n,-1320,-270)
    mix = V(nt,'P_MIX',settings.mix,-1320,-340)
    sign = V(nt,'P_SIGN',-1 if settings.combine=='SUB' else 1,-1320,-410)

    scene = bpy.context.scene
    drive_value_node(m, scene, 'chladni52.m')
    drive_value_node(n, scene, 'chladni52.n')
    drive_value_node(mix, scene, 'chladni52.mix')
    drive_value_node(sign, scene, 'chladni52.combine_driver')

    use_sine = settings.model == 'SUPPORTED'
    phi = phi_network(nt,sep.outputs['X'],sep.outputs['Y'],m.outputs[0],n.outputs[0],
                      mix.outputs[0],sign.outputs[0],use_sine,-980,0,'P')

    ab = M(nt,'ABSOLUTE','Abs Phi',100,0)
    L(nt,phi,ab.inputs[0])

    width = V(nt,'P_WIDTH',settings.line_width,100,-180)
    drive_value_node(width, scene, 'chladni52.line_width')
    div = M(nt,'DIVIDE','Node Width',250,0)
    L(nt,ab.outputs[0],div.inputs[0]); L(nt,width.outputs[0],div.inputs[1])

    one = M(nt,'SUBTRACT','Node Mask',400,0)
    one.inputs[0].default_value = 1.0
    L(nt,div.outputs[0],one.inputs[1])

    mx = M(nt,'MAXIMUM','Clamp Min',540,0,0.0)
    mn = M(nt,'MINIMUM','Clamp Max',680,0,1.0)
    L(nt,one.outputs[0],mx.inputs[0]); L(nt,mx.outputs[0],mn.inputs[0])

    ramp = N(nt,'ShaderNodeValToRGB','Preview Ramp',650,180)
    ramp.color_ramp.elements[0].color = settings.plate_color
    ramp.color_ramp.elements[1].color = settings.node_color
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[1].position = 1.0
    L(nt,mn.outputs[0],ramp.inputs['Fac'])
    L(nt,ramp.outputs['Color'],bs.inputs['Base Color'])
    bs.inputs['Roughness'].default_value = 0.4

    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    return mat

# -------------------------------------------------------------------
# Geometry simulation
# Uses finite-difference gradient of the same field.
# This makes the node tree simpler and much less API-fragile.
# -------------------------------------------------------------------

def field_at(nt, u, v, m, n, mix, sign, settings, x, y, tag):
    return phi_network(
        nt, u, v, m, n, mix, sign,
        settings.model == 'SUPPORTED',
        x, y, tag
    )

def make_sim(settings, obj):
    old = bpy.data.node_groups.get(GN_NAME)
    if old:
        bpy.data.node_groups.remove(old, do_unlink=True)

    ng = bpy.data.node_groups.new(GN_NAME,'GeometryNodeTree')
    ng.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    ng.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')

    gi = N(ng,'NodeGroupInput','Plate',-1900,450)
    go = N(ng,'NodeGroupOutput','Output',3300,450)

    x0,x1,y0,y1 = bounds_xy(obj)
    sx,sy = size_xy(obj)
    area = max(sx*sy,1e-6)

    # Spawn
    dist = N(ng,'GeometryNodeDistributePointsOnFaces','Spawn Grains',-1650,450)
    L(ng,gi.outputs['Geometry'],S(dist.inputs,'Mesh'))

    density = V(ng,'G_DENSITY',settings.grain_count/area,-1650,200)
    L(ng,density.outputs[0],S(dist.inputs,'Density',4))
    if S(dist.inputs,'Seed'):
        S(dist.inputs,'Seed').default_value = settings.seed

    init = N(ng,'GeometryNodeStoreNamedAttribute','Init Velocity',-1400,450)
    init.data_type='FLOAT_VECTOR'
    init.domain='POINT'
    S(init.inputs,'Name').default_value = VEL_ATTR
    S(init.inputs,'Value').default_value = (0,0,0)
    L(ng,dist.outputs['Points'],S(init.inputs,'Geometry'))

    # Simulation pair
    sin = N(ng,'GeometryNodeSimulationInput','Simulation Input',-1100,450)
    sout = N(ng,'GeometryNodeSimulationOutput','Simulation Output',2150,450)
    sin.pair_with_output(sout)
    L(ng,init.outputs['Geometry'],S(sin.inputs,'Geometry'))

    prev = N(ng,'GeometryNodeInputNamedAttribute','Velocity',-900,700)
    prev.data_type='FLOAT_VECTOR'
    S(prev.inputs,'Name').default_value = VEL_ATTR

    pos = N(ng,'GeometryNodeInputPosition','Position',-900,220)
    sep = N(ng,'ShaderNodeSeparateXYZ','Position XY',-730,220)
    L(ng,pos.outputs['Position'],sep.inputs['Vector'])

    xx = M(ng,'SUBTRACT','x-xmin',-560,270,x0)
    yy = M(ng,'SUBTRACT','y-ymin',-560,120,y0)
    L(ng,sep.outputs['X'],xx.inputs[0]); L(ng,sep.outputs['Y'],yy.inputs[0])

    u = M(ng,'DIVIDE','u',-410,270,sx)
    v = M(ng,'DIVIDE','v',-410,120,sy)
    L(ng,xx.outputs[0],u.inputs[0]); L(ng,yy.outputs[0],v.inputs[0])

    m = V(ng,'G_M',settings.m,-880,-80)
    n = V(ng,'G_N',settings.n,-880,-150)
    mix = V(ng,'G_MIX',settings.mix,-880,-220)
    sign = V(ng,'G_SIGN',-1 if settings.combine=='SUB' else 1,-880,-290)
    eps = V(ng,'G_EPS',settings.gradient_step,-880,-360)
    force = V(ng,'G_FORCE',settings.force,-880,-430)
    damp = V(ng,'G_DAMP',settings.damping,-880,-500)
    jitter = V(ng,'G_JITTER',settings.jitter,-880,-570)
    speed = V(ng,'G_SPEED',settings.speed_limit,-880,-640)
    coll_radius = V(ng,'G_COLLISION_RADIUS',settings.collision_radius,-880,-710)
    coll_strength = V(ng,'G_COLLISION_STRENGTH',settings.collision_strength,-880,-780)

    # LIVE animation drivers: Geometry Nodes sees these values every frame.
    scene = bpy.context.scene
    drive_value_node(m, scene, 'chladni52.m')
    drive_value_node(n, scene, 'chladni52.n')
    drive_value_node(mix, scene, 'chladni52.mix')
    drive_value_node(sign, scene, 'chladni52.combine_driver')
    drive_value_node(eps, scene, 'chladni52.gradient_step')
    drive_value_node(force, scene, 'chladni52.force')
    drive_value_node(damp, scene, 'chladni52.damping')
    drive_value_node(jitter, scene, 'chladni52.jitter')
    drive_value_node(speed, scene, 'chladni52.speed_limit')
    drive_value_node(coll_radius, scene, 'chladni52.collision_radius')
    drive_value_node(coll_strength, scene, 'chladni52.collision_strength')

    # finite difference u+eps, u-eps, v+eps, v-eps
    up = M(ng,'ADD','u+eps',-220,350); um = M(ng,'SUBTRACT','u-eps',-220,270)
    vp = M(ng,'ADD','v+eps',-220,120); vm = M(ng,'SUBTRACT','v-eps',-220,40)
    L(ng,u.outputs[0],up.inputs[0]); L(ng,eps.outputs[0],up.inputs[1])
    L(ng,u.outputs[0],um.inputs[0]); L(ng,eps.outputs[0],um.inputs[1])
    L(ng,v.outputs[0],vp.inputs[0]); L(ng,eps.outputs[0],vp.inputs[1])
    L(ng,v.outputs[0],vm.inputs[0]); L(ng,eps.outputs[0],vm.inputs[1])

    p_up = field_at(ng,up.outputs[0],v.outputs[0],m.outputs[0],n.outputs[0],mix.outputs[0],sign.outputs[0],settings,20,650,'UP')
    p_um = field_at(ng,um.outputs[0],v.outputs[0],m.outputs[0],n.outputs[0],mix.outputs[0],sign.outputs[0],settings,20,250,'UM')
    p_vp = field_at(ng,u.outputs[0],vp.outputs[0],m.outputs[0],n.outputs[0],mix.outputs[0],sign.outputs[0],settings,20,-200,'VP')
    p_vm = field_at(ng,u.outputs[0],vm.outputs[0],m.outputs[0],n.outputs[0],mix.outputs[0],sign.outputs[0],settings,20,-600,'VM')

    # energy = phi^2
    eup=M(ng,'MULTIPLY','E up',1050,650); eum=M(ng,'MULTIPLY','E um',1050,250)
    evp=M(ng,'MULTIPLY','E vp',1050,-200); evm=M(ng,'MULTIPLY','E vm',1050,-600)
    for p,e in [(p_up,eup),(p_um,eum),(p_vp,evp),(p_vm,evm)]:
        L(ng,p,e.inputs[0]); L(ng,p,e.inputs[1])

    du = M(ng,'SUBTRACT','dE u numerator',1200,540)
    dv = M(ng,'SUBTRACT','dE v numerator',1200,-330)
    L(ng,eup.outputs[0],du.inputs[0]); L(ng,eum.outputs[0],du.inputs[1])
    L(ng,evp.outputs[0],dv.inputs[0]); L(ng,evm.outputs[0],dv.inputs[1])

    twoeps = M(ng,'MULTIPLY','2 eps',1200,100,2.0)
    L(ng,eps.outputs[0],twoeps.inputs[0])

    gx = M(ng,'DIVIDE','Gradient X',1360,540)
    gy = M(ng,'DIVIDE','Gradient Y',1360,-330)
    L(ng,du.outputs[0],gx.inputs[0]); L(ng,twoeps.outputs[0],gx.inputs[1])
    L(ng,dv.outputs[0],gy.inputs[0]); L(ng,twoeps.outputs[0],gy.inputs[1])

    # convert normalized gradient to local-space gradient
    gxscale = M(ng,'DIVIDE','Gradient X / width',1510,540,sx)
    gyscale = M(ng,'DIVIDE','Gradient Y / height',1510,-330,sy)
    L(ng,gx.outputs[0],gxscale.inputs[0]); L(ng,gy.outputs[0],gyscale.inputs[0])

    negx = M(ng,'MULTIPLY','-Grad X',1660,540,-1.0)
    negy = M(ng,'MULTIPLY','-Grad Y',1660,-330,-1.0)
    L(ng,gxscale.outputs[0],negx.inputs[0]); L(ng,gyscale.outputs[0],negy.inputs[0])

    comb = N(ng,'ShaderNodeCombineXYZ','Force Vector',1810,150)
    L(ng,negx.outputs[0],comb.inputs['X']); L(ng,negy.outputs[0],comb.inputs['Y'])

    fs = VM(ng,'SCALE','Force Strength',1970,150)
    L(ng,comb.outputs['Vector'],fs.inputs[0]); L(ng,force.outputs[0],S(fs.inputs,'Scale',3))

    rnd = N(ng,'FunctionNodeRandomValue','Jitter',1810,-100)
    rnd.data_type='FLOAT_VECTOR'
    S(rnd.inputs,'Min').default_value=(-1,-1,0)
    S(rnd.inputs,'Max').default_value=(1,1,0)
    rs = VM(ng,'SCALE','Jitter Strength',1970,-100)
    L(ng,rnd.outputs['Value'],rs.inputs[0]); L(ng,jitter.outputs[0],S(rs.inputs,'Scale',3))

    # ---------------------------------------------------------------
    # Grain-grain soft collision / packing solver.
    #
    # Geometry Nodes has no native all-pairs rigid-sphere collision
    # solver.  We use eight nearest-neighbour probes around every grain.
    # Each probe samples the nearest grain to an offset query position.
    # If the sampled neighbour is closer than 2*collision_radius, an
    # overlap-separation impulse is generated.
    # ---------------------------------------------------------------

    diameter = M(ng,'MULTIPLY','Collision Diameter',2140,-520,2.0)
    L(ng,coll_radius.outputs[0],diameter.inputs[0])

    collision_terms = []
    dirs = [
        ( 1.0, 0.0, 'E'), (-1.0, 0.0, 'W'),
        ( 0.0, 1.0, 'N'), ( 0.0,-1.0, 'S'),
        ( 0.70710678, 0.70710678, 'NE'),
        (-0.70710678, 0.70710678, 'NW'),
        ( 0.70710678,-0.70710678, 'SE'),
        (-0.70710678,-0.70710678, 'SW'),
    ]

    probe_x = 2140
    probe_y0 = -720

    for probe_i, (dx,dy,tag) in enumerate(dirs):
        row_y = probe_y0 - probe_i * 180

        sxn = M(ng,'MULTIPLY',f'Collision {tag} X',probe_x,row_y,dx)
        syn = M(ng,'MULTIPLY',f'Collision {tag} Y',probe_x,row_y-45,dy)
        L(ng,coll_radius.outputs[0],sxn.inputs[0])
        L(ng,coll_radius.outputs[0],syn.inputs[0])

        off = N(ng,'ShaderNodeCombineXYZ',f'Collision {tag} Probe',probe_x+150,row_y)
        L(ng,sxn.outputs[0],off.inputs['X'])
        L(ng,syn.outputs[0],off.inputs['Y'])

        query = VM(ng,'ADD',f'Collision {tag} Query',probe_x+320,row_y)
        L(ng,pos.outputs['Position'],query.inputs[0])
        L(ng,off.outputs['Vector'],query.inputs[1])

        nearest = N(ng,'GeometryNodeIndexOfNearest',f'Collision {tag} Nearest',probe_x+500,row_y)
        L(ng,query.outputs['Vector'],S(nearest.inputs,'Position'))

        sample = N(ng,'GeometryNodeSampleIndex',f'Collision {tag} Position',probe_x+680,row_y)
        sample.data_type='FLOAT_VECTOR'
        sample.domain='POINT'
        L(ng,S(sin.outputs,'Geometry'),S(sample.inputs,'Geometry'))
        L(ng,pos.outputs['Position'],S(sample.inputs,'Value'))
        L(ng,S(nearest.outputs,'Index'),S(sample.inputs,'Index'))

        delta = VM(ng,'SUBTRACT',f'Collision {tag} Delta',probe_x+860,row_y)
        L(ng,pos.outputs['Position'],delta.inputs[0])
        L(ng,S(sample.outputs,'Value'),delta.inputs[1])

        distc = VM(ng,'LENGTH',f'Collision {tag} Distance',probe_x+1030,row_y-30)
        L(ng,delta.outputs['Vector'],distc.inputs[0])

        pen = M(ng,'SUBTRACT',f'Collision {tag} Penetration',probe_x+1190,row_y)
        L(ng,diameter.outputs[0],pen.inputs[0])
        L(ng,S(distc.outputs,'Value'),pen.inputs[1])

        positive = M(ng,'MAXIMUM',f'Collision {tag} Positive',probe_x+1350,row_y,0.0)
        L(ng,pen.outputs[0],positive.inputs[0])

        # Ignore the point itself (distance ~= 0), otherwise Normalize(0)
        # would create no direction but penetration would remain positive.
        not_self = M(ng,'GREATER_THAN',f'Collision {tag} Not Self',probe_x+1350,row_y-70,1e-7)
        L(ng,S(distc.outputs,'Value'),not_self.inputs[0])

        amount = M(ng,'MULTIPLY',f'Collision {tag} Amount',probe_x+1510,row_y)
        L(ng,positive.outputs[0],amount.inputs[0])
        L(ng,not_self.outputs[0],amount.inputs[1])

        direction = VM(ng,'NORMALIZE',f'Collision {tag} Direction',probe_x+1510,row_y-80)
        L(ng,delta.outputs['Vector'],direction.inputs[0])

        repel = VM(ng,'SCALE',f'Collision {tag} Repel',probe_x+1680,row_y)
        L(ng,direction.outputs['Vector'],repel.inputs[0])
        L(ng,amount.outputs[0],S(repel.inputs,'Scale',3))
        collision_terms.append(repel.outputs['Vector'])

    # Sum the eight probe impulses.
    collision_sum = collision_terms[0]
    sum_x = probe_x + 1880
    sum_y = probe_y0
    for i, term in enumerate(collision_terms[1:], start=1):
        addc = VM(ng,'ADD',f'Collision Sum {i}',sum_x + (i-1)*120,sum_y)
        L(ng,collision_sum,addc.inputs[0])
        L(ng,term,addc.inputs[1])
        collision_sum = addc.outputs['Vector']

    coll_scaled = VM(ng,'SCALE','Collision Strength',sum_x+900,sum_y)
    L(ng,collision_sum,coll_scaled.inputs[0])
    L(ng,coll_strength.outputs[0],S(coll_scaled.inputs,'Scale',3))

    base_acc = VM(ng,'ADD','Chladni + Jitter',2140,120)
    L(ng,fs.outputs['Vector'],base_acc.inputs[0])
    L(ng,rs.outputs['Vector'],base_acc.inputs[1])

    acc = VM(ng,'ADD','Acceleration + Collisions',2310,120)
    L(ng,base_acc.outputs['Vector'],acc.inputs[0])
    L(ng,coll_scaled.outputs['Vector'],acc.inputs[1])

    dt = S(sin.outputs,'Delta Time')
    adt = VM(ng,'SCALE','Acceleration dt',2310,120)
    L(ng,acc.outputs['Vector'],adt.inputs[0]); L(ng,dt,S(adt.inputs,'Scale',3))

    va = VM(ng,'ADD','Integrate Velocity',2480,620)
    L(ng,prev.outputs['Attribute'],va.inputs[0]); L(ng,adt.outputs['Vector'],va.inputs[1])

    retain = M(ng,'SUBTRACT','1-Damping',2480,500)
    retain.inputs[0].default_value=1.0
    L(ng,damp.outputs[0],retain.inputs[1])

    vd = VM(ng,'SCALE','Damped Velocity',2640,620)
    L(ng,va.outputs['Vector'],vd.inputs[0]); L(ng,retain.outputs[0],S(vd.inputs,'Scale',3))

    vlen = VM(ng,'LENGTH','Speed',2640,500)
    L(ng,vd.outputs['Vector'],vlen.inputs[0])
    vmax = M(ng,'MINIMUM','Limit Speed',2800,500)
    L(ng,vlen.outputs['Value'],vmax.inputs[0]); L(ng,speed.outputs[0],vmax.inputs[1])
    vdir = VM(ng,'NORMALIZE','Velocity Direction',2800,620)
    L(ng,vd.outputs['Vector'],vdir.inputs[0])
    vf = VM(ng,'SCALE','Final Velocity',2960,620)
    L(ng,vdir.outputs['Vector'],vf.inputs[0]); L(ng,vmax.outputs[0],S(vf.inputs,'Scale',3))

    step = VM(ng,'SCALE','Velocity dt',2960,450)
    L(ng,vf.outputs['Vector'],step.inputs[0]); L(ng,dt,S(step.inputs,'Scale',3))

    move = N(ng,'GeometryNodeSetPosition','Move Points',3120,450)
    L(ng,S(sin.outputs,'Geometry'),S(move.inputs,'Geometry'))
    L(ng,step.outputs['Vector'],S(move.inputs,'Offset'))

    store = N(ng,'GeometryNodeStoreNamedAttribute','Store Velocity',3290,450)
    store.data_type='FLOAT_VECTOR'
    store.domain='POINT'
    S(store.inputs,'Name').default_value=VEL_ATTR
    L(ng,move.outputs['Geometry'],S(store.inputs,'Geometry'))
    L(ng,vf.outputs['Vector'],S(store.inputs,'Value'))
    L(ng,store.outputs['Geometry'],S(sout.inputs,'Geometry'))

    # Display grains after sim
    ico = N(ng,'GeometryNodeMeshIcoSphere','Grain Mesh',2350,800)
    S(ico.inputs,'Radius').default_value=settings.grain_radius
    if S(ico.inputs,'Subdivisions'):
        S(ico.inputs,'Subdivisions').default_value=1

    inst = N(ng,'GeometryNodeInstanceOnPoints','Display Grains',2600,800)
    L(ng,S(sout.outputs,'Geometry'),S(inst.inputs,'Points'))
    L(ng,ico.outputs['Mesh'],S(inst.inputs,'Instance'))

    join = N(ng,'GeometryNodeJoinGeometry','Plate + Grains',3000,800)
    L(ng,gi.outputs['Geometry'],join.inputs['Geometry'])
    L(ng,inst.outputs['Instances'],join.inputs['Geometry'])
    L(ng,join.outputs['Geometry'],go.inputs['Geometry'])

    mod = obj.modifiers.get(MOD_NAME)
    if not mod:
        mod = obj.modifiers.new(MOD_NAME,'NODES')
    mod.node_group = ng
    return ng

# -------------------------------------------------------------------
# Live sync
# -------------------------------------------------------------------

def sync(self, context):
    # Keep enum -> numeric sign in sync for drivers.
    desired = -1.0 if self.combine == 'SUB' else 1.0
    if abs(self.combine_driver - desired) > 1e-6:
        self.combine_driver = desired

    # Driven numeric inputs update automatically every frame.
    # Only non-driven preview colors are pushed explicitly.
    mat = bpy.data.materials.get(MAT_NAME)
    if mat and mat.use_nodes:
        ramp = mat.node_tree.nodes.get('Preview Ramp')
        if ramp:
            ramp.color_ramp.elements[0].color = self.plate_color
            ramp.color_ramp.elements[1].color = self.node_color

# -------------------------------------------------------------------
# Properties
# -------------------------------------------------------------------


class CHLADNI52_SequenceItem(PropertyGroup):
    name: StringProperty(name='Name', default='Pattern')
    m: IntProperty(name='m', default=3, min=1, max=20)
    n: IntProperty(name='n', default=5, min=1, max=20)
    mix: FloatProperty(name='Mix', default=0.5, min=0.0, max=1.0)
    combine: EnumProperty(name='Combine',items=[('SUB','Subtract','A-B'),('ADD','Add','A+B')],default='SUB')
    model: EnumProperty(name='Model',items=[('CLASSIC','Classic Chladni','Cosine superposition'),('SUPPORTED','Simply Supported','Sine thin-plate modes')],default='CLASSIC')
    hold_frames: IntProperty(name='Hold', default=24, min=0, max=10000)
    transition_frames: IntProperty(name='Transition', default=48, min=1, max=10000)


def sync_combine_driver(self, context):
    self.combine_driver = -1.0 if self.combine == 'SUB' else 1.0
    sync(self, context)

class CHLADNI52_Settings(PropertyGroup):
    model: EnumProperty(
        name='Pattern Model',
        items=[
            ('CLASSIC','Classic Chladni','Cosine superposition'),
            ('SUPPORTED','Simply Supported','Sine thin-plate modes')
        ],
        default='CLASSIC'
    )
    m: IntProperty(name='m',default=3,min=1,max=20,update=sync)
    n: IntProperty(name='n',default=5,min=1,max=20,update=sync)
    mix: FloatProperty(name='Mode Mix',default=0.5,min=0,max=1,update=sync)
    combine: EnumProperty(
        name='Combine',
        items=[('SUB','Subtract','A-B'),('ADD','Add','A+B')],
        default='SUB', update=sync_combine_driver
    )
    combine_driver: FloatProperty(name='Combine Driver', default=-1.0)

    grain_count: IntProperty(name='Grains',default=10000,min=100,max=300000)
    seed: IntProperty(name='Seed',default=1,min=0,max=100000)
    grain_radius: FloatProperty(name='Grain Radius',default=0.008,min=0.0001,max=0.1,precision=4)

    force: FloatProperty(name='Transport Strength',default=4.0,min=0,max=500)
    damping: FloatProperty(name='Damping',default=0.08,min=0,max=0.99)
    jitter: FloatProperty(name='Jitter',default=0.01,min=0,max=5)
    speed_limit: FloatProperty(name='Max Speed',default=0.5,min=0.001,max=20)
    gradient_step: FloatProperty(name='Gradient Step',default=0.003,min=0.0001,max=0.1,precision=4)

    collision_radius: FloatProperty(
        name='Collision Radius',
        description='Physical grain collision radius. Usually close to Grain Radius',
        default=0.009, min=0.0001, max=0.2, precision=4
    )
    collision_strength: FloatProperty(
        name='Collision Strength',
        description='Separation impulse used when grains overlap',
        default=45.0, min=0.0, max=1000.0
    )

    sequence: CollectionProperty(type=CHLADNI52_SequenceItem)
    sequence_index: IntProperty(name='Selected Pattern', default=0)
    default_hold: IntProperty(name='Default Hold', default=24, min=0, max=10000)
    default_transition: IntProperty(name='Default Transition', default=48, min=1, max=10000)
    transition_type: EnumProperty(name='Transition',items=[('PHYSICAL','Physical','Crossfade the two excitation fields'),('MORPH','Morph','Visual morph'),('CUT','Cut','Instant switch')],default='PHYSICAL')
    easing: EnumProperty(name='Easing',items=[('SMOOTH','Smooth','Smoothstep'),('LINEAR','Linear','Linear'),('EASE_IN_OUT','Ease In/Out','Bezier ease')],default='SMOOTH')
    auto_timeline: BoolProperty(name='Auto Timeline', default=True)
    live_transition_preview: FloatProperty(name='Preview A → B', default=0.0, min=0.0, max=1.0)

    line_width: FloatProperty(name='Node Line Width',default=0.08,min=0.001,max=1,update=sync)
    plate_color: FloatVectorProperty(name='Plate Color',subtype='COLOR',size=4,default=(0.015,0.02,0.03,1),min=0,max=1,update=sync)
    node_color: FloatVectorProperty(name='Node Color',subtype='COLOR',size=4,default=(1.0,0.3,0.02,1),min=0,max=1,update=sync)

# -------------------------------------------------------------------
# Operators
# -------------------------------------------------------------------

class CHLADNI52_OT_preview(Operator):
    bl_idname='chladni52.create_preview'
    bl_label='Create / Update Shader Preview'
    def execute(self,context):
        obj=plate(context)
        if not obj:
            self.report({'ERROR'},'Select a mesh plane first.')
            return {'CANCELLED'}
        try:
            make_preview(context.scene.chladni52,obj)
            self.report({'INFO'},'Shader preview created.')
            return {'FINISHED'}
        except Exception:
            traceback.print_exc()
            self.report({'ERROR'},'Preview failed; see System Console.')
            return {'CANCELLED'}

class CHLADNI52_OT_sim(Operator):
    bl_idname='chladni52.create_sim'
    bl_label='Create / Rebuild Geo Simulation'
    def execute(self,context):
        obj=plate(context)
        if not obj:
            self.report({'ERROR'},'Select a mesh plane first.')
            return {'CANCELLED'}
        try:
            make_sim(context.scene.chladni52,obj)
            context.scene.frame_set(context.scene.frame_start)
            self.report({'INFO'},'Geometry Nodes simulation created.')
            return {'FINISHED'}
        except Exception:
            traceback.print_exc()
            self.report({'ERROR'},'Geo simulation failed; see System Console.')
            return {'CANCELLED'}

class CHLADNI52_OT_both(Operator):
    bl_idname='chladni52.create_both'
    bl_label='CREATE BOTH'
    def execute(self,context):
        obj=plate(context)
        if not obj:
            self.report({'ERROR'},'Select a mesh plane first.')
            return {'CANCELLED'}
        preview_ok=True
        sim_ok=True
        try:
            make_preview(context.scene.chladni52,obj)
        except Exception:
            preview_ok=False
            traceback.print_exc()
        try:
            make_sim(context.scene.chladni52,obj)
        except Exception:
            sim_ok=False
            traceback.print_exc()
        context.scene.frame_set(context.scene.frame_start)
        if preview_ok and sim_ok:
            self.report({'INFO'},'Preview and simulation created.')
            return {'FINISHED'}
        self.report({'WARNING'},f'Preview: {"OK" if preview_ok else "FAILED"} | Sim: {"OK" if sim_ok else "FAILED"}')
        return {'FINISHED'}



class CHLADNI52_OT_keyframe_live(Operator):
    bl_idname='chladni52.keyframe_live'
    bl_label='Keyframe Live Pattern'
    def execute(self,context):
        s=context.scene.chladni52
        props = (
            'm','n','mix','combine_driver','line_width',
            'force','damping','jitter','speed_limit',
            'gradient_step','collision_radius','collision_strength'
        )
        for p in props:
            try:
                s.keyframe_insert(data_path=p)
            except Exception:
                pass
        self.report({'INFO'},f'Keyframed live Chladni controls at frame {context.scene.frame_current}.')
        return {'FINISHED'}

class CHLADNI52_OT_seq_add(Operator):
    bl_idname='chladni52.seq_add'; bl_label='Add Current Pattern'
    def execute(self,context):
        s=context.scene.chladni52
        item=s.sequence.add()
        item.name=f'Pattern {len(s.sequence)}'
        item.m=s.m; item.n=s.n; item.mix=s.mix; item.combine=s.combine; item.model=s.model
        item.hold_frames=s.default_hold; item.transition_frames=s.default_transition
        s.sequence_index=len(s.sequence)-1
        return {'FINISHED'}

class CHLADNI52_OT_seq_load(Operator):
    bl_idname='chladni52.seq_load'; bl_label='Load Selected'
    def execute(self,context):
        s=context.scene.chladni52
        if not s.sequence: return {'CANCELLED'}
        i=max(0,min(s.sequence_index,len(s.sequence)-1)); item=s.sequence[i]
        s.m=item.m; s.n=item.n; s.mix=item.mix; s.combine=item.combine; s.model=item.model
        return {'FINISHED'}

class CHLADNI52_OT_seq_update(Operator):
    bl_idname='chladni52.seq_update'; bl_label='Update Selected'
    def execute(self,context):
        s=context.scene.chladni52
        if not s.sequence: return {'CANCELLED'}
        item=s.sequence[max(0,min(s.sequence_index,len(s.sequence)-1))]
        item.m=s.m; item.n=s.n; item.mix=s.mix; item.combine=s.combine; item.model=s.model
        return {'FINISHED'}

class CHLADNI52_OT_seq_remove(Operator):
    bl_idname='chladni52.seq_remove'; bl_label='Delete'
    def execute(self,context):
        s=context.scene.chladni52
        if not s.sequence: return {'CANCELLED'}
        i=max(0,min(s.sequence_index,len(s.sequence)-1)); s.sequence.remove(i)
        s.sequence_index=max(0,min(i,len(s.sequence)-1))
        return {'FINISHED'}

class CHLADNI52_OT_seq_duplicate(Operator):
    bl_idname='chladni52.seq_duplicate'; bl_label='Duplicate'
    def execute(self,context):
        s=context.scene.chladni52
        if not s.sequence: return {'CANCELLED'}
        a=s.sequence[max(0,min(s.sequence_index,len(s.sequence)-1))]
        b=s.sequence.add()
        for p in ('name','m','n','mix','combine','model','hold_frames','transition_frames'):
            setattr(b,p,getattr(a,p))
        b.name=a.name+' Copy'
        s.sequence_index=len(s.sequence)-1
        return {'FINISHED'}

class CHLADNI52_OT_seq_up(Operator):
    bl_idname='chladni52.seq_up'; bl_label='Up'
    def execute(self,context):
        s=context.scene.chladni52; i=s.sequence_index
        if 0<i<len(s.sequence): s.sequence.move(i,i-1); s.sequence_index=i-1
        return {'FINISHED'}

class CHLADNI52_OT_seq_down(Operator):
    bl_idname='chladni52.seq_down'; bl_label='Down'
    def execute(self,context):
        s=context.scene.chladni52; i=s.sequence_index
        if 0<=i<len(s.sequence)-1: s.sequence.move(i,i+1); s.sequence_index=i+1
        return {'FINISHED'}

class CHLADNI52_OT_seq_timeline(Operator):
    bl_idname='chladni52.seq_timeline'; bl_label='Build Timeline'
    def execute(self,context):
        s=context.scene.chladni52
        if not s.sequence:
            self.report({'ERROR'},'Add at least one pattern.')
            return {'CANCELLED'}
        f=context.scene.frame_start
        for item in s.sequence:
            item['_start_frame']=f
            item['_hold_end']=f+item.hold_frames
            item['_transition_end']=f+item.hold_frames+item.transition_frames
            f=item['_transition_end']
        if s.auto_timeline:
            context.scene.frame_end=max(context.scene.frame_start+1,f)
        self.report({'INFO'},f'Sequence laid out to frame {context.scene.frame_end}.')
        return {'FINISHED'}

class CHLADNI52_OT_seq_clear(Operator):
    bl_idname='chladni52.seq_clear'; bl_label='Clear'
    def execute(self,context):
        s=context.scene.chladni52; s.sequence.clear(); s.sequence_index=0
        return {'FINISHED'}


class CHLADNI52_OT_reset(Operator):
    bl_idname='chladni52.reset'
    bl_label='Reset to Frame 1'
    def execute(self,context):
        context.scene.frame_set(context.scene.frame_start)
        return {'FINISHED'}

# -------------------------------------------------------------------
# Panel - deliberately NO icons anywhere.
# -------------------------------------------------------------------

class CHLADNI52_PT_Main(Panel):
    bl_label='Chladni 5.2 Clean'
    bl_idname='CHLADNI52_PT_MAIN'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='Chladni 5.2'

    def draw(self,context):
        l=self.layout
        s=context.scene.chladni52
        obj=plate(context)

        l.label(text='VERSION 7.0.0 — LIVE ANIMATED GEO INPUTS')

        create=l.box()
        create.label(text='CREATE')
        create.operator('chladni52.create_preview')
        create.operator('chladni52.create_sim')
        create.operator('chladni52.create_both')

        if not obj:
            l.label(text='Select a mesh plane to build on.')
            return

        pattern=l.box()
        pattern.label(text='PATTERN')
        pattern.prop(s,'model')
        pattern.label(text='m / n / mix / force etc. are live and keyframeable.')
        pattern.label(text='Pattern Model changes require Rebuild.')
        r=pattern.row(align=True)
        r.prop(s,'m')
        r.prop(s,'n')
        pattern.prop(s,'mix')
        pattern.prop(s,'combine')
        pattern.operator('chladni52.keyframe_live', text='Keyframe Live Pattern')

        prev=l.box()
        prev.label(text='SHADER PREVIEW')
        prev.prop(s,'line_width')
        prev.prop(s,'plate_color')
        prev.prop(s,'node_color')
        prev.label(text='m / n / mix update live after preview exists.')

        anim=l.box()
        anim.label(text='PATTERN SEQUENCER')
        r=anim.row(align=True)
        r.operator('chladni52.seq_add', text='Add Current')
        r.operator('chladni52.seq_update', text='Update')

        if not s.sequence:
            anim.label(text='Add current → change pattern → Add current again.')
        else:
            anim.prop(s,'sequence_index', text='Pattern')
            i=max(0,min(s.sequence_index,len(s.sequence)-1))
            item=s.sequence[i]

            r=anim.row(align=True)
            r.prop(item,'name', text='')
            r.operator('chladni52.seq_load', text='Load')

            r=anim.row(align=True)
            r.label(text=f'm {item.m} / n {item.n}')
            r.label(text=f'mix {item.mix:.2f}')

            r=anim.row(align=True)
            r.prop(item,'hold_frames', text='Hold')
            r.prop(item,'transition_frames', text='Transition')

            r=anim.row(align=True)
            r.operator('chladni52.seq_up', text='Up')
            r.operator('chladni52.seq_down', text='Down')
            r.operator('chladni52.seq_duplicate', text='Duplicate')
            r.operator('chladni52.seq_remove', text='Delete')

            if len(s.sequence)>1:
                nxt=s.sequence[(i+1)%len(s.sequence)]
                anim.label(text=f'Next → {nxt.name}  m {nxt.m} / n {nxt.n}')
                anim.prop(s,'live_transition_preview', slider=True)

        adv=anim.box()
        adv.label(text='Defaults')
        r=adv.row(align=True)
        r.prop(s,'default_hold', text='Hold')
        r.prop(s,'default_transition', text='Transition')
        adv.prop(s,'transition_type')
        adv.prop(s,'easing')
        adv.prop(s,'auto_timeline')

        r=anim.row(align=True)
        r.operator('chladni52.seq_timeline', text='Build Timeline')
        r.operator('chladni52.seq_clear', text='Clear')

        sim=l.box()
        sim.label(text='GEO SIMULATION')
        sim.prop(s,'grain_count')
        sim.prop(s,'seed')
        sim.prop(s,'grain_radius')
        sim.prop(s,'force')
        sim.prop(s,'damping')
        sim.prop(s,'jitter')
        sim.prop(s,'speed_limit')
        sim.prop(s,'gradient_step')

        collision=sim.box()
        collision.label(text='GRAIN SELF-COLLISION')
        collision.prop(s,'collision_radius')
        collision.prop(s,'collision_strength')
        collision.label(text='Uses 8 nearest-neighbour probes per grain.')
        collision.label(text='Higher strength = harder packing.')

        sim.operator('chladni52.reset')
        sim.label(text='Rebuild after changing sim creation settings.')

        info=l.box()
        info.label(text='Generated:')
        info.label(text=MAT_NAME)
        info.label(text=GN_NAME)

classes=(
    CHLADNI52_SequenceItem,
    CHLADNI52_Settings,
    CHLADNI52_OT_preview,
    CHLADNI52_OT_sim,
    CHLADNI52_OT_both,
    CHLADNI52_OT_keyframe_live,
    CHLADNI52_OT_seq_add,
    CHLADNI52_OT_seq_load,
    CHLADNI52_OT_seq_update,
    CHLADNI52_OT_seq_remove,
    CHLADNI52_OT_seq_duplicate,
    CHLADNI52_OT_seq_up,
    CHLADNI52_OT_seq_down,
    CHLADNI52_OT_seq_timeline,
    CHLADNI52_OT_seq_clear,
    CHLADNI52_OT_reset,
    CHLADNI52_PT_Main,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.chladni52=PointerProperty(type=CHLADNI52_Settings)

def unregister():
    if hasattr(bpy.types.Scene,'chladni52'):
        del bpy.types.Scene.chladni52
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__=='__main__':
    register()
