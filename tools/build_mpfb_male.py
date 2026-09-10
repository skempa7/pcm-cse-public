"""Build a new authored young-adult male from the neutral MPFB base, using licensed local packs.

Run with Blender --factory-startup --background --python tools/build_mpfb_male.py.
No add-on preference installation, network request, or proprietary trial assets.
The full MPFB source is preserved; browser export has clean body topology and PBR.
"""
from pathlib import Path
import bpy, sys, addon_utils, json, math, os, bmesh
from mathutils import Vector, Matrix, Quaternion

ROOT = Path(os.environ.get('PCM_MALE_BUILD_ROOT', str(Path(__file__).resolve().parents[1])))
BASE_OUT = ROOT / 'assets3d/mpfb-male'
# Optional authored variants share this pipeline; absent a configuration, all
# original output paths and macro defaults remain exactly as before.
VARIANT = {'id':'standard','macro':{'height':.5,'weight':.44,'muscle':.56,'proportions':.52},'target_height_m':1.78}
OUT = BASE_OUT
ASSET_NAME = 'public-male-standard'
PACKS = Path(os.environ.get('PCM_MPFB_PACKS', '/private/tmp/pcm-mpfb-assetpacks'))
if not os.environ.get('PCM_MPFB_ADDON'):
    raise RuntimeError('Set PCM_MPFB_ADDON to the installed MPFB add-on directory.')
ADDON = Path(os.environ['PCM_MPFB_ADDON']).expanduser().resolve()
if not (ADDON/'services/humanservice.py').is_file():
    raise RuntimeError('PCM_MPFB_ADDON does not contain an MPFB add-on.')
RUNTIME = ROOT/'mpfb-runtime'
OUT.mkdir(parents=True, exist_ok=True)
RUNTIME.mkdir(parents=True, exist_ok=True)
if not (RUNTIME/'mpfb').exists(): (RUNTIME/'mpfb').symlink_to(ADDON, target_is_directory=True)
sys.path.insert(0, str(RUNTIME))
original_extension_path = bpy.utils.extension_path_user
bpy.utils.extension_path_user = lambda package,*a,**kw: str(RUNTIME/'user-data') if package == 'mpfb' else original_extension_path(package,*a,**kw)
addon_utils.enable('mpfb', default_set=True, persistent=False)
from mpfb.services.humanservice import HumanService
from mpfb.services.targetservice import TargetService

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
macro = TargetService.get_default_macro_info_dict()
macro.update(gender=1., age=.50, muscle=.56, weight=.44, height=.5, proportions=.52, cupsize=.5, firmness=.5, race={'caucasian':1.,'asian':0.,'african':0.})
if VARIANT: macro.update(VARIANT['macro'])
# Neutral cup/firmness avoids subtractive breast targets, which MPFB does not
# attenuate by the zero female component. The male macro supplies the pectorals.
human = HumanService.create_human(macro_detail_dict=macro)
if VARIANT and VARIANT.get('target_height_m'):
    from mpfb.entities.objectproperties import HumanObjectProperties
    target_height=float(VARIANT['target_height_m'])
    assert 1.45 <= target_height <= 1.90
    low,high=0.,1.
    for iteration in range(17):
        value=(low+high)/2
        HumanObjectProperties.set_value('height',value,entity_reference=human)
        TargetService.reapply_macro_details(human);bpy.context.view_layer.update()
        ev=human.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
        minimum=min(v.co.z for v in mesh.vertices);maximum=max(v.co.z for v in mesh.vertices)
        measured=maximum-minimum;ev.to_mesh_clear()
        if measured<target_height:low=value
        else:high=value
    macro['height']=value
    # Normalize the authored soles before MPFB fits the skeleton and assets.
    human.location.z=-minimum
    bpy.context.view_layer.objects.active=human
    bpy.ops.object.transform_apply(location=True,rotation=False,scale=False)
    assert abs(measured-target_height)<.0001,(measured,target_height)
    print('PCM_TARGET_HEIGHT',target_height,measured,'macro',value,flush=True)
human.name = 'PCM_MaleBody_Source'
rig = HumanService.add_builtin_rig(human, 'game_engine')
rig.name = 'PCM_MaleRig'
# Values are measured from the original authored rest rig, not inferred from
# case demographics. New macro geometry is fitted by MPFB before this mapping.
REFERENCE_BONES = {'pelvis':(0,-.0231307838,.8257932663), 'spine_01':(0,.0222366191,.8974275589), 'spine_03':(0,-.0120929889,1.0506993532), 'neck_01':(0,.0011120350,1.3460584879), 'head':(0,-.0404847711,1.4512082338), 'foot_l':(.1646250784,-.0294691492,.0682370141)}
HEIGHT_RATIO = rig.data.bones['head'].head_local.z / REFERENCE_BONES['head'][2]
def fitted_location(bone, point):
    if not VARIANT: return point
    return rig.data.bones[bone].head_local + (Vector(point)-Vector(REFERENCE_BONES[bone]))*HEIGHT_RATIO

CORE = PACKS/'makehuman_system_assets'

def material(obj, mhmat, name, roughness=.6, alpha=False):
    """Explicit glTF-friendly PBR, retaining authored image UVs and normals."""
    mhmat = Path(mhmat)
    fields = {}
    for line in mhmat.read_text().splitlines():
        vals=line.strip().split()
        if len(vals)>1 and not vals[0].startswith(('#','//')): fields[vals[0]]=vals[1:]
    mat=bpy.data.materials.new(name);mat.use_nodes=True
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;bs=nodes.get('Principled BSDF')
    bs.inputs['Roughness'].default_value=roughness
    bs.inputs['Specular IOR Level'].default_value=.28
    for field, socket, normal in [('diffuseTexture','Base Color',False),('normalmapTexture','Normal',True)]:
        if field not in fields: continue
        path=(mhmat.parent/' '.join(fields[field])).resolve()
        if not path.exists(): continue
        tex=nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(path),check_existing=True)
        maxsize=2048 if field=='diffuseTexture' and 'Skin' in name else 1024
        if max(tex.image.size)>maxsize:
            w,h=tex.image.size;tex.image.scale(round(w*maxsize/max(w,h)),round(h*maxsize/max(w,h)))
        tex.image.pack()
        if normal:
            tex.image.colorspace_settings.name='Non-Color';nm=nodes.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.45
            links.new(tex.outputs['Color'],nm.inputs['Color']);links.new(nm.outputs['Normal'],bs.inputs['Normal'])
        else:
            links.new(tex.outputs['Color'],bs.inputs[socket])
            if alpha: links.new(tex.outputs['Alpha'],bs.inputs['Alpha'])
    mat.use_backface_culling=False
    if alpha: mat.surface_render_method='DITHERED'
    obj.data.materials.clear();obj.data.materials.append(mat)
    return mat

assets=[]
def asset(rel, kind, name, mhmat=None, roughness=.6, alpha=False, subdivision=0):
    path=PACKS/rel
    obj=HumanService.add_mhclo_asset(str(path),human,asset_type=kind,subdiv_levels=subdivision,material_type='GAMEENGINE')
    obj.name=name
    if mhmat is None:
        token=next(x.split(maxsplit=1)[1] for x in path.read_text().splitlines() if x.startswith('material '))
        mhmat=path.parent/token
    mat=material(obj,mhmat,name.replace('PCM_','PCM_Mat_'),roughness,alpha)
    assets.append(obj)
    print('PCM_ASSET',name,len(obj.data.vertices),[(m.name,m.type) for m in obj.modifiers],flush=True)
    return obj

material(human,CORE/'skins/young_caucasian_male2/young_caucasian_male2.mhmat','PCM_Mat_Skin',.48)
eyes=asset('makehuman_system_assets/eyes/high-poly/high-poly.mhclo','Eyes','PCM_Eyes',CORE/'eyes/materials/bluegreen.mhmat',.17,alpha=True)
teeth=asset('makehuman_system_assets/teeth/teeth_base/teeth_base.mhclo','Teeth','PCM_Teeth',roughness=.35)
tongue=asset('makehuman_system_assets/tongue/tongue01/tongue01.mhclo','Tongue','PCM_Tongue',roughness=.5)
brows=asset('makehuman_system_assets/eyebrows/eyebrow001/eyebrow001.mhclo','Eyebrows','PCM_Eyebrows',roughness=.7,alpha=True)
outfit=asset('makehuman_system_assets/clothes/male_casualsuit01/male_casualsuit01.mhclo','Clothes','PCM_PublicTrousers',roughness=.84,subdivision=1)
knit=asset('shirts01/clothes/toigo_fisherman_sweater/toigo_fisherman_sweater.mhclo','Clothes','PCM_PublicKnit',roughness=.84,subdivision=1)
shoes=asset('makehuman_system_assets/clothes/shoes05/shoes05.mhclo','Clothes','PCM_PublicShoes',roughness=.76)
# This authored external mesh is optional only in visibility, not missing from
# the anatomical body. Its own CC0 source/license receipt is retained locally.
EXTERNAL = Path(os.environ.get('PCM_MALE_EXTERNAL_SOURCE',str(ROOT/'external-source')))
external=HumanService.add_mhclo_asset(str(EXTERNAL/'male_external_neutral.mhclo'),human,asset_type='Clothes',subdiv_levels=1,material_type='NONE')
external.name='PCM_MaleExternal_Source';external.data.materials.clear();external.data.materials.append(human.data.materials[0]);assets.append(external)
# Keep neutral external tissue with the pelvis; there are no sexual-state bones,
# interactions or independent arousal animation.
external.vertex_groups.clear();external.vertex_groups.new(name='pelvis').add(list(range(len(external.data.vertices))),1.,'REPLACE')

def delete_geometry(obj, predicate):
    bm=bmesh.new();bm.from_mesh(obj.data)
    doomed=[v for v in bm.verts if predicate(v.co)]
    bmesh.ops.delete(bm,geom=doomed,context='VERTS');bm.to_mesh(obj.data);bm.free()
# Retain the licensed fitted jeans geometry, replacing its attached T-shirt with
# the fitted knit asset. The original complete outfit stays in the source pack.
outfit_cut = fitted_location('spine_01',(0,0,.895))[2]
delete_geometry(outfit,lambda co:co.z>outfit_cut)
shoe_cut = fitted_location('foot_l',(0,0,.11))[2]
delete_geometry(shoes,lambda co:co.z>shoe_cut)

def neutral_texture(obj, color, strength=1., runtime_tint=False):
    """Bake a neutral luminance texture for predictable authored color variations."""
    mat=obj.data.materials[0];nodes=mat.node_tree.nodes;bs=nodes.get('Principled BSDF')
    link=next(iter(bs.inputs['Base Color'].links),None)
    if not link:return
    tex=link.from_node;image=tex.image.copy();image.name=obj.name+'_Colorable'
    import numpy as np
    pix=np.empty(len(image.pixels),dtype=np.float32);image.pixels.foreach_get(pix);a=pix.reshape(-1,4)
    lum=a[:,:3]@np.array([.2126,.7152,.0722]);lum=np.clip(lum*strength,.02,1.)
    a[:,:3]=lum[:,None] if runtime_tint else lum[:,None]*np.array(color)[None,:]
    image.pixels.foreach_set(pix);image.update();image.pack();tex.image=image
    if runtime_tint:
        multiply=nodes.new('ShaderNodeMixRGB');multiply.blend_type='MULTIPLY';multiply.inputs[0].default_value=1.
        multiply.inputs[2].default_value=(*color,1.)
        mat.node_tree.links.new(tex.outputs['Color'],multiply.inputs[1]);mat.node_tree.links.new(multiply.outputs[0],bs.inputs['Base Color'])
neutral_texture(knit,(.52,.58,.56),2.)
neutral_texture(outfit,(.17,.25,.34),1.7)
for color in (() if VARIANT else ('blue','green')):
    eye_image=bpy.data.images.load(str(CORE/'eyes/materials'/(color+'_eye.png')),check_existing=True)
    if max(eye_image.size)>1024:eye_image.scale(1024,1024)
    eye_image.filepath_raw=str(ROOT/'web/patient3d/assets'/('mpfb-eyes-'+color+'.png'));eye_image.file_format='PNG';eye_image.save()

# Macro keys are retained in this complete, editable source checkpoint.
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MPFB-male-macro-source.blend'))
print('PCM_BONES',json.dumps({b.name:{'head':list(b.head_local),'tail':list(b.tail_local),'parent':b.parent.name if b.parent else None} for b in rig.data.bones}),flush=True)
print('PCM_BODY_MASKS',[(m.name,m.type,getattr(m,'vertex_group',''),getattr(m,'invert_vertex_group',False))for m in human.modifiers],flush=True)

# ---- Browser preparation: retain actual anatomy, UVs, skin weights and morphs. ----
mixed = human.shape_key_add(name='AuthoredNeutral', from_mix=True)
coords=[v.co.copy() for v in mixed.data]
human.shape_key_clear()
for v,co in zip(human.data.vertices,coords): v.co=co
human.shape_key_add(name='Basis')
expressions={
    'Blink': {'eye-left-closure':1., 'eye-right-closure':1.},
    'Speech': {'mouth-open':.68},
    'Warmth': {'mouth-corner-puller':.22,'mouth-upward-retraction':.10},
    'Concern': {'eyebrows-left-inner-up':.38,'eyebrows-right-inner-up':.38},
    'Discomfort': {'eyebrows-left-down':.32,'eyebrows-right-down':.32,'eye-left-slit':.18,'eye-right-slit':.18,'mouth-compression':.2},
}
for name,units in expressions.items():
    deltas=[Vector((0,0,0)) for _ in coords]
    for unit,strength in units.items():
        for ethnic in ('caucasian',):
            path=ADDON/'data/targets/expression/units'/ethnic/(unit+'.target.gz')
            if not path.exists(): raise RuntimeError('Required facial target missing: '+str(path))
            key=TargetService.load_target(human,str(path),name='WorkingTarget',weight=0.)
            for i,v in enumerate(key.data): deltas[i]+=(v.co-coords[i])*strength
            human.shape_key_remove(key)
    key=human.shape_key_add(name=name)
    for i,co in enumerate(coords):key.data[i].co=co+deltas[i]
    key.value=0.

# Eyebrow hair follows the authored expression through its original MHCLO
# barycentric correspondence, rather than floating while the brow skin moves.
brow_mapping=[];reading=False
for line in (CORE/'eyebrows/eyebrow001/eyebrow001.mhclo').read_text().splitlines():
    tokens=line.strip().split()
    if not tokens or tokens[0].startswith('#'):continue
    if tokens[0]=='verts':reading=True;continue
    if reading:
        if not tokens[0].lstrip('-').isdigit():break
        if len(tokens)==1:brow_mapping.append([(int(tokens[0]),1.)])
        else:brow_mapping.append([(int(tokens[i]),float(tokens[i+3]))for i in range(3)])
assert len(brow_mapping)==len(brows.data.vertices)
brows.shape_key_add(name='Basis').value=0.
for name in expressions:
    key=brows.shape_key_add(name=name);source=human.data.shape_keys.key_blocks[name]
    for i,mapping in enumerate(brow_mapping):
        delta=sum(((source.data[old].co-coords[old])*w for old,w in mapping),Vector())
        key.data[i].co=brows.data.vertices[i].co+delta
    key.value=0.

# Export complete native adult-male body anatomy. Clothing masks are deliberately
# excluded so the user-requested unclothed clinical preset cannot expose mesh holes.
# Nonbody construction helpers remain excluded. No additional anatomical detail
# is invented or inferred from the examination case.
weights={v.index:{human.vertex_groups[g.group].name:g.weight for g in v.groups}for v in human.data.vertices}
def build_body(object_name, covered=False):
    masks=[m for m in human.modifiers if m.type=='MASK' and (covered or m.vertex_group in ('body','Delete.male_external_neutral'))]
    def visible(i):
        # A clothing-only mask eliminates concealed torso intersections without
        # deleting any geometry from the separately toggled anatomical body.
        # The crew neck and long sleeves cover this entire conservative region.
        if covered and .90 < coords[i].z < 1.435 and abs(coords[i].x) < .24:
            return False
        for m in masks:
            member=weights[i].get(m.vertex_group,0.)>m.threshold
            if member==m.invert_vertex_group:return False
        return True
    faces=[p for p in human.data.polygons if all(visible(i)for i in p.vertices)]
    ids=sorted(set(i for p in faces for i in p.vertices));remap={old:i for i,old in enumerate(ids)}
    mesh=bpy.data.meshes.new(object_name+'_Anatomy');mesh.from_pydata([coords[i]for i in ids],[],[[remap[i]for i in p.vertices]for p in faces]);mesh.update()
    body=bpy.data.objects.new(object_name,mesh);bpy.context.collection.objects.link(body)
    body.parent=rig
    for mat in human.data.materials:mesh.materials.append(mat)
    for old_layer in human.data.uv_layers:
        layer=mesh.uv_layers.new(name=old_layer.name)
        for old_p,new_p in zip(faces,mesh.polygons):
            for oi,ni in zip(old_p.loop_indices,new_p.loop_indices):layer.data[ni].uv=old_layer.data[oi].uv
    for bone in rig.data.bones:
        group=body.vertex_groups.new(name=bone.name)
        for old in ids:
            w=weights[old].get(bone.name,0.)
            if w>0:group.add([remap[old]],w,'REPLACE')
    for name in ['Basis']+list(expressions):
        key=body.shape_key_add(name=name)
        source=human.data.shape_keys.key_blocks[name]
        for i,old in enumerate(ids):key.data[i].co=source.data[old].co
        key.value=0.
    arm=body.modifiers.new('Full anatomical rig','ARMATURE');arm.object=rig
    for p in mesh.polygons:p.use_smooth=True
    return body
body=build_body('PCM_AnatomicalBody')
covered_body=build_body('PCM_PublicBody',covered=True)
body.hide_render=True
human.hide_render=True;human.hide_set(True)
export_objects=[rig,body,covered_body]+assets

# Clothing subdivision is baked in its rest shape while weights are interpolated
# by Blender. Armature remains live; no sculpted per-pose body fragments.
for obj in assets:
    if any(m.type=='SUBSURF'for m in obj.modifiers):
        for m in obj.modifiers:
            if m.type=='ARMATURE':m.show_viewport=False
        bpy.context.view_layer.objects.active=obj
        for m in list(obj.modifiers):
            if m.type=='SUBSURF':
                m.show_viewport=True;m.levels=1;m.render_levels=1
                bpy.ops.object.modifier_move_to_index(modifier=m.name,index=0)
                bpy.ops.object.modifier_apply(modifier=m.name)
        for m in obj.modifiers:
            if m.type=='ARMATURE':m.show_viewport=True
    for p in obj.data.polygons:p.use_smooth=True

# Match the renderer's four skin influences in the editable source too. This
# prevents silent export truncation while keeping UVs and all morphs untouched.
for obj in [body,covered_body]+assets:
    names=[g.name for g in obj.vertex_groups]
    rows=[]
    for v in obj.data.vertices:
        weights=sorted([(names[g.group],g.weight)for g in v.groups if names[g.group] in rig.data.bones and g.weight>0],key=lambda x:-x[1])[:4]
        total=sum(w for _,w in weights)
        rows.append([(n,w/total)for n,w in weights] if total else [('head',1.)])
    obj.vertex_groups.clear();groups={n:obj.vertex_groups.new(name=n)for n in sorted(set(n for row in rows for n,w in row))}
    for i,row in enumerate(rows):
        for n,w in row:groups[n].add([i],w,'REPLACE')

# Merge the external surface into the anatomical mesh. Existing wardrobe code
# therefore hides every external vertex when the clothed view is selected.
bpy.ops.object.select_all(action='DESELECT');body.hide_set(False);body.select_set(True);external.select_set(True);bpy.context.view_layer.objects.active=body
assets.remove(external);export_objects.remove(external);bpy.ops.object.join()
def reset_pose():
    rig.animation_data_clear();rig.location=(0,0,0);rig.rotation_mode='QUATERNION';rig.rotation_quaternion=(1,0,0,0)
    for b in rig.pose.bones:b.matrix_basis=Matrix.Identity(4);b.rotation_mode='QUATERNION'
    bpy.context.view_layer.update()

def aim(name,direction,twist=0.):
    b=rig.pose.bones[name];rest=b.bone.matrix_local.to_quaternion()
    orig=b.bone.tail_local-b.bone.head_local
    q=orig.normalized().rotation_difference(Vector(direction).normalized()) @ rest
    if name.startswith('hand_'):
        side=name[-1];wrist=b.bone.head_local
        a=rig.data.bones['index_01_'+side].head_local-wrist
        c=rig.data.bones['pinky_01_'+side].head_local-wrist
        normal=a.cross(c).normalized()*(1 if side=='l' else -1)
        normal=q@rest.inverted()@normal
        axis=Vector(direction).normalized();desired=Vector((0,0,1))
        n=(normal-axis*normal.dot(axis)).normalized();d=(desired-axis*desired.dot(axis)).normalized()
        q=Quaternion(axis,math.atan2(axis.dot(n.cross(d)),n.dot(d)))@q
    if twist:q=Quaternion(Vector(direction).normalized(),twist)@q
    mat=q.to_matrix().to_4x4();mat.translation=b.head.copy();b.matrix=mat
    bpy.context.view_layer.update()

def variant_contact_alignment(posture):
    # Match the actual posterior pelvic surface to the same table reference.
    # This changes only an authored root translation, never anatomy scale.
    if not VARIANT: return
    from mathutils.bvhtree import BVHTree
    dg=bpy.context.evaluated_depsgraph_get();ev=body.evaluated_get(dg);mesh=ev.to_mesh()
    vertices=[ev.matrix_world@v.co for v in mesh.vertices]
    tree=BVHTree.FromPolygons(vertices,[list(p.vertices) for p in mesh.polygons])
    pelvis=rig.matrix_world@rig.pose.bones['pelvis'].head
    points=[]
    for x in (-.075,0,.075):
        point=tree.ray_cast(Vector((x,pelvis.y,-2)),Vector((0,0,1)))[0]
        if point is not None: points.append(point)
    ev.to_mesh_clear()
    if not points: raise RuntimeError('Cannot establish pelvic support from actual variant surface')
    support=min(p.z for p in points)
    rig.location.z += (1.021 if posture=='seated' else 1.020)-support
    bpy.context.view_layer.update()

def pose(posture):
    reset_pose()
    if posture=='seated':
        for side,sgn in [('l',1),('r',-1)]:
            aim('thigh_'+side,(.04*sgn,-1,-.09))
            aim('calf_'+side,(.015*sgn,.035,-1))
            aim('foot_'+side,(.025*sgn,-1,-.40))
            aim('upperarm_'+side,(.12*sgn,-.13,-1))
            aim('lowerarm_'+side,(-.32*sgn,-1,-.72))
            aim('hand_'+side,(-.2*sgn,-1,-.10))
            middle=rig.pose.bones['middle_01_'+side]
            relaxed=(middle.tail-middle.head).normalized()
            for finger in ('index','middle','ring','pinky'):
                name=finger+'_01_'+side;b=rig.pose.bones[name]
                direction=(b.tail-b.head).normalized().lerp(relaxed,.35)
                aim(name,direction)
        rig.location=(0,.06,1.12-rig.pose.bones['pelvis'].head.z)
    else:
        for side,sgn in [('l',1),('r',-1)]:
            aim('thigh_'+side,(.075*sgn,-.01,-1))
            aim('calf_'+side,(.035*sgn,0,-1))
            aim('upperarm_'+side,(.22*sgn,-.02,-1))
            aim('lowerarm_'+side,(-.05*sgn,-.02,-1))
            aim('hand_'+side,(-.02*sgn,-.01,-1))
        rig.rotation_quaternion=Quaternion((1,0,0),-math.pi/2)
        pelvis=rig.rotation_quaternion@rig.pose.bones['pelvis'].head
        rig.location=Vector((0,.05,1.13))-pelvis
    bpy.context.view_layer.update()
    variant_contact_alignment(posture)

def anchor(name,bone,location):
    location=fitted_location(bone,location)
    obj=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(obj)
    obj.parent=rig;obj.parent_type='BONE';obj.parent_bone=bone
    # Bone parent uses the tail as its origin. Invert its rest transform to place
    # an anatomical anchor, then Blender propagates the exact posed coordinates.
    parent_rest=rig.matrix_world@rig.data.bones[bone].matrix_local@Matrix.Translation((0,rig.data.bones[bone].length,0))
    obj.matrix_parent_inverse=Matrix.Identity(4)
    obj.matrix_basis=parent_rest.inverted()@Matrix.Translation(Vector(location))
    export_objects.append(obj)
    return obj
reset_pose()
anchors=[anchor('Face','head',(0,-.10,1.505)),anchor('Chest','spine_03',(0,-.12,1.21)),anchor('Abdomen','spine_01',(0,-.115,1.025)),anchor('Lap','pelvis',(0,-.23,.83))]
poses={}
for key in ('seated','supine'):
    pose(key)
    action=bpy.data.actions.new('PCM_'+key.capitalize());rig.animation_data_create();rig.animation_data.action=action
    for frame in (1,25):
        rig.keyframe_insert(data_path='location',frame=frame)
        rig.keyframe_insert(data_path='rotation_quaternion',frame=frame)
        for bone in rig.pose.bones:
            bone.keyframe_insert(data_path='location',frame=frame)
            bone.keyframe_insert(data_path='rotation_quaternion',frame=frame)
            bone.keyframe_insert(data_path='scale',frame=frame)
    action.use_fake_user=True
    poses[key]={'anchors_blender':{a.name:list(a.matrix_world.translation)for a in anchors},'bones_blender':{n:list((rig.matrix_world@rig.pose.bones[n].matrix).translation)for n in ('head','pelvis','hand_l','hand_r','calf_l','calf_r')}}
    rig.animation_data.action=None
pose('seated')
rig.animation_data_create();rig.animation_data.action=bpy.data.actions.get('PCM_Seated')
bpy.context.scene.frame_set(1)

manifest={'asset':ASSET_NAME,'schema':1,'addon':'MPFB 2.0.17','body':'PCM_AnatomicalBody','rig':rig.name,'posture_clips':['PCM_Seated','PCM_Supine'],'morphs':list(expressions),'bones':[b.name for b in rig.data.bones],'anchors':[a.name for a in anchors],'poses':poses,'materials':[m.name for o in [body]+assets for m in o.data.materials],'coordinate_conversion':'Blender (x,y,z) -> glTF (x,z,-y); Babylon import handedness must be accounted for by loader','clinical_note':'Appearance and ambient motions are not clinical findings. Only case-authorized observed behavior may enter the encounter record.','licenses':{'MPFB anatomy and core outfit/eyes/skin/shoes':'CC0','Hair':'Bald; no scalp hair mesh'},'review':'Authoring in progress; GLB and browser motion review pending'}
manifest['variant']=VARIANT
manifest['generation']='Fresh HumanService.create_human from neutral MPFB base, gender macro 1.0. No female patient mesh or female facial coordinates used.'
manifest['age_basis']='MPFB young-adult macro age .5; authored profile 25 years. Reference screenshot age UI is not followed.'
manifest['authored_macro']=macro
manifest['body_coverage']='Native adult male body with licensed MHX2 external flaccid penile/scrotal surface integrated into anatomical mesh. Clothing view contains no external surface. No internal examination anatomy.'
manifest['licenses']['External male anatomical mesh']='CC0 added content by Thomas Larsson / MHX2; https://thomasmakehuman.wordpress.com/license-information/; source makehumancommunity/mhx2-makehuman-exchange import_runtime_mhx2/data/hm8/genitalia/penis.mxa'
manifest['covered_body']='PCM_PublicBody'
manifest['optional_clothing_meshes']=['PCM_PublicKnit','PCM_PublicTrousers','PCM_PublicShoes']
(OUT/'export-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

# Source-stage render exposes proportion, cloth fit, hair and expression quality.
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=16
scene.render.resolution_x=840;scene.render.resolution_y=1050;scene.render.resolution_percentage=100
scene.world.color=(.18,.18,.18)
def light(name,loc,power,size):
    data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size
    obj=bpy.data.objects.new(name,data);scene.collection.objects.link(obj);obj.location=loc;obj.rotation_euler=(Vector((0,0,1.4))-obj.location).to_track_quat('-Z','Y').to_euler()
light('Portrait Key',(-2,-3,3.8),420,3)
light('Portrait Fill',(2,-1,2.5),230,2.5)
light('Hair Separation',(0,2,3),330,2)
camdata=bpy.data.cameras.new('Asset review camera');cam=bpy.data.objects.new('Asset review camera',camdata);scene.collection.objects.link(cam);scene.camera=cam
cam.location=(.65,-3.1,1.9);cam.rotation_euler=(Vector((0,-.06,1.24))-cam.location).to_track_quat('-Z','Y').to_euler();camdata.lens=60
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,.38,.94));table=bpy.context.object;table.name='Preview seat only';table.scale=(.63,1.30,.13);bevel=table.modifiers.new('Soft edges','BEVEL');bevel.width=.04;bevel.segments=3
seatmat=bpy.data.materials.new('Preview sage upholstery');seatmat.diffuse_color=(.13,.24,.22,1);table.data.materials.append(seatmat)
scene.render.filepath=str(OUT/'seated-source.png')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MPFB-male-patient.blend'))
bpy.ops.render.render(write_still=True)

bpy.ops.object.select_all(action='DESELECT')
for obj in export_objects:obj.hide_set(False);obj.select_set(True)
bpy.context.view_layer.objects.active=rig
scene.frame_start=1;scene.frame_end=25
bpy.ops.export_scene.gltf(filepath=str(ROOT/'web/patient3d/assets'/(ASSET_NAME+'.glb')),export_format='GLB',use_selection=True,export_animations=True,export_animation_mode='ACTIONS',export_force_sampling=True,export_morph=True,export_skins=True,export_yup=True,export_apply=False,export_extras=True)
import struct
glbpath=ROOT/'web/patient3d/assets'/(ASSET_NAME+'.glb')
raw=glbpath.read_bytes();json_length=struct.unpack_from('<I',raw,12)[0]
gltf=json.loads(raw[20:20+json_length]);binary=raw[20+json_length:]
for mat in gltf['materials']:
    if mat['name']=='PCM_Mat_LongHair':mat.setdefault('pbrMetallicRoughness',{})['baseColorFactor']=[.34,.19,.11,1]
data=json.dumps(gltf,separators=(',',':')).encode();data+=b' '*((-len(data))%4)
glbpath.write_bytes(struct.pack('<III',0x46546c67,2,20+len(data)+len(binary))+struct.pack('<II',len(data),0x4e4f534a)+data+binary)
import hashlib
manifest['glb_sha256']=hashlib.sha256(glbpath.read_bytes()).hexdigest();manifest['bytes']=glbpath.stat().st_size
manifest['triangles']=sum(gltf['accessors'][p['indices']]['count']//3 for m in gltf['meshes']for p in m['primitives'])
manifest['eye_textures']={'blue':'mpfb-eyes-blue.png','green':'mpfb-eyes-green.png'}
manifest['licenses']['Fitted fisherman knit']='CC0, MRT, source pack shirts01'
(OUT/'export-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('PCM_EXPORT_COMPLETE',flush=True)
