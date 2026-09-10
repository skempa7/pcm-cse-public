"""Add standing/prone actions to the freshly generated adult male MPFB asset.
Blender --factory-startup --background --python add_male_postures.py -- MALE_BUILD_ROOT OUTPUT
The source apps are read-only. Output contains new GLBs, editable scenes, contact
measurements and exact-original-binary preservation hashes. No new anatomy or
examination findings are introduced by positioning.
"""
from pathlib import Path
import bpy, math, json, struct, copy, hashlib, sys, os
from mathutils import Matrix,Quaternion,Vector
args=sys.argv[sys.argv.index('--')+1:]
PRIVATE,OUT=map(Path,args[:2]); OUT.mkdir(parents=True,exist_ok=True)
ONLY=os.environ.get('PCM_POSTURE_ONLY')

def glb(path):
 data=path.read_bytes();n,k=struct.unpack_from('<II',data,12);doc=json.loads(data[20:20+n]);off=20+n
 size,kind=struct.unpack_from('<II',data,off);assert kind==0x004e4942
 return doc,data[off+8:off+8+size]
def write_glb(path,doc,binary):
 b=bytes(binary);b+=b'\0'*((-len(b))%4);doc['buffers']=[{'byteLength':len(b)}]
 j=json.dumps(doc,separators=(',',':')).encode();j+=b' '*((-len(j))%4)
 path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(struct.pack('<4sII',b'glTF',2,28+len(j)+len(b))+struct.pack('<II',len(j),0x4e4f534a)+j+struct.pack('<II',len(b),0x004e4942)+b)
def merge_clips(original,exported,target):
 doc,old=glb(original);extra,buf=glb(exported);binary=bytearray(old)
 nodeids={node.get('name'):i for i,node in enumerate(doc['nodes'])};amap={};vmap={}
 def accessor(idx):
  if idx in amap:return amap[idx]
  a=copy.deepcopy(extra['accessors'][idx]);assert 'sparse' not in a
  if 'bufferView' in a:
   vid=a['bufferView']
   if vid not in vmap:
    v=copy.deepcopy(extra['bufferViews'][vid]);start=v.get('byteOffset',0);size=v['byteLength']
    binary.extend(b'\0'*((-len(binary))%4));v['byteOffset']=len(binary);binary.extend(buf[start:start+size]);v['buffer']=0
    vmap[vid]=len(doc['bufferViews']);doc['bufferViews'].append(v)
   a['bufferView']=vmap[vid]
  amap[idx]=len(doc['accessors']);doc['accessors'].append(a);return amap[idx]
 doc['animations']=[a for a in doc.get('animations',[]) if a['name'] not in ('PCM_Standing','PCM_Prone')]
 for a in extra.get('animations',[]):
  if a['name'] not in ('PCM_Standing','PCM_Prone'):continue
  a=copy.deepcopy(a)
  for s in a['samplers']:s['input']=accessor(s['input']);s['output']=accessor(s['output'])
  for c in a['channels']:
   oldidx=c['target']['node'];name=extra['nodes'][oldidx]['name'];assert name in nodeids,name;c['target']['node']=nodeids[name]
  doc['animations'].append(a)
 assert {a['name'] for a in doc['animations']}>= {'PCM_Standing','PCM_Prone','PCM_Seated','PCM_Supine'}
 write_glb(target,doc,binary)
 return {'original_binary_sha256':hashlib.sha256(old).hexdigest(),'preserved_binary_prefix':bytes(binary[:len(old)])==old,'appended_bytes':len(binary)-len(old),'clips':[a['name'] for a in doc['animations']]}
def reset(rig):
 rig.animation_data_create();rig.animation_data.action=None;rig.location=(0,0,0);rig.rotation_mode='QUATERNION';rig.rotation_quaternion=(1,0,0,0)
 for b in rig.pose.bones:b.matrix_basis=Matrix.Identity(4);b.rotation_mode='QUATERNION'
 bpy.context.view_layer.update()
def aim(rig,name,direction,twist=0):
 b=rig.pose.bones[name];rest=b.bone.matrix_local.to_quaternion();orig=b.bone.tail_local-b.bone.head_local
 q=orig.normalized().rotation_difference(Vector(direction).normalized())@rest
 if twist:q=Quaternion(Vector(direction).normalized(),twist)@q
 m=q.to_matrix().to_4x4();m.translation=b.head.copy();b.matrix=m;bpy.context.view_layer.update()
def points(obj):
 dg=bpy.context.evaluated_depsgraph_get();ev=obj.evaluated_get(dg);mesh=ev.to_mesh();out=[ev.matrix_world@v.co for v in mesh.vertices];ev.to_mesh_clear();return out

def bounds(vals):
 return {'min':[min(p[i] for p in vals)for i in range(3)],'max':[max(p[i] for p in vals)for i in range(3)]}
def pose(rig,body,posture):
 reset(rig);h=max(v.co.z for v in body.data.vertices)
 for side,s in [('l',1),('r',-1)]:
  aim(rig,'thigh_'+side,(.025*s,-.12 if posture=='prone' else 0,-1));aim(rig,'calf_'+side,(.01*s,.055 if posture=='prone' else 0,-1))
  aim(rig,'upperarm_'+side,(.12*s,-.015,-1));aim(rig,'lowerarm_'+side,(.015*s,-.055,-1));aim(rig,'hand_'+side,(0,-.04,-1))
 if posture=='standing':
  # Natural erect position with the native flat-foot articulation retained.
  rig.location=(.83,-.22,0);bpy.context.view_layer.update();bodypts=points(body)
  rig.location.z=.007-min(v.z for v in bodypts)
 else:
  # Supine head-end retained, with the anterior body surface facing the table.
  rig.rotation_quaternion=Quaternion((1,0,0),-math.pi/2)@Quaternion((0,0,1),math.pi)
  # Rotation about the patient's upright axis before the lying root transform.
  for n,degrees in [('neck_01',18),('head',57)]:
   b=rig.pose.bones[n];m=b.matrix.copy();rot=Quaternion((0,0,1),math.radians(degrees));q=rot@m.to_quaternion();m=q.to_matrix().to_4x4();m.translation=b.head.copy();b.matrix=m;bpy.context.view_layer.update()
  # Toes point in line with the supported shin rather than digging down.
  for side,s in [('l',1),('r',-1)]:aim(rig,'foot_'+side,(.015*s,-.22,-1))
  pelvis=rig.rotation_quaternion@rig.pose.bones['pelvis'].head;rig.location=Vector((0,.15,1.24))-pelvis
  bpy.context.view_layer.update();vals=points(body)
  # Keep the anterior thorax/pelvis/knees clear of the flat support plane.
  central=[p for i,p in enumerate(vals) if abs(body.data.vertices[i].co.x)<h*.20 and .22<body.data.vertices[i].co.z/h<.84]
  rig.location.z+=1.045-min(v.z for v in central)
 bpy.context.view_layer.update()
 vals=points(body);shoe=bpy.data.objects.get('PCM_Sneakers') or bpy.data.objects.get('PCM_PublicShoes');shoevals=points(shoe) if shoe else []
 zones={}
 for key,lo,hi in [('feet',0,.13),('shins',.13,.29),('knees',.26,.32),('thighs',.33,.48),('pelvis',.48,.57),('abdomen',.57,.68),('chest',.68,.80),('head',.86,1.01)]:
  selected=[p for i,p in enumerate(vals) if lo<=body.data.vertices[i].co.z/h<hi and abs(body.data.vertices[i].co.x)<h*.17]
  if selected:zones[key]=bounds(selected)
 hair=bpy.data.objects.get('PCM_LongHair')
 from mathutils.bvhtree import BVHTree
 tree=BVHTree.FromPolygons(vals,[list(p.vertices) for p in body.data.polygons])
 lower=[]
 if posture=='prone':
  for by in [round(-.9+i*.05,3) for i in range(36)]:
   for x in [round(-.22+i*.02,3) for i in range(23)]:
    hit=tree.ray_cast(Vector((x,by,0)),Vector((0,0,1)))[0]
    if hit is not None:lower.append([x,by,hit.z])
 support_profile=[]
 if posture=='prone':
  for zz in [round(-.5+i*.04,3) for i in range(37)]:
   pts=[p.z for p in vals if abs(p.y+zz)<.035 and abs(p.x)<.34]
   if pts:support_profile.append([zz,round(min(pts)-.007,5)])
 return {'prone_cushion_profile_babylon':support_profile,'lower_surface_samples_blender':lower,'hair_bounds_blender':bounds(points(hair)) if hair else None,'root_blender':list(rig.location),'rotation_quaternion_wxyz':list(rig.rotation_quaternion),'body_bounds_blender':bounds(vals),'zones_blender':zones,'shoe_bounds_blender':bounds(shoevals) if shoevals else None,'anchors_blender':{n:list(bpy.data.objects[n].matrix_world.translation)for n in ('Face','Chest','Abdomen','Lap')},'standing_clothed_lift_m':max(0,.007-min(v.z for v in shoevals)) if posture=='standing' and shoevals else 0}

reports={}
items=[('male',PRIVATE/'assets3d/mpfb-male/MPFB-male-patient.blend',PRIVATE/'web/patient3d/assets/public-male-standard.glb')]
for name,source,runtime in items:
 if ONLY and name!=ONLY:continue
 bpy.ops.wm.open_mainfile(filepath=str(source));body=bpy.data.objects.get('PCM_FemaleBody') or bpy.data.objects['PCM_AnatomicalBody'];rig=body.parent
 for o in bpy.data.objects:
  if o.type=='MESH' and o.data.shape_keys:
   for k in o.data.shape_keys.key_blocks:k.value=0
 report={'source':str(source),'runtime':str(runtime),'poses':{}}
 for posture in ('standing','prone'):
  report['poses'][posture]=pose(rig,body,posture)
  old=bpy.data.actions.get('PCM_'+posture.capitalize())
  if old:bpy.data.actions.remove(old)
  action=bpy.data.actions.new('PCM_'+posture.capitalize());rig.animation_data.action=action
  for frame in (1,25):
   rig.keyframe_insert(data_path='location',frame=frame);rig.keyframe_insert(data_path='rotation_quaternion',frame=frame)
   for bone in rig.pose.bones:
    for path in ('location','rotation_quaternion','scale'):bone.keyframe_insert(data_path=path,frame=frame)
  action.use_fake_user=True;rig.animation_data.action=None
 rig.animation_data.action=bpy.data.actions.get('PCM_Seated');bpy.context.scene.frame_set(1)
 # Preserve original editable content, actions, materials and geometry.
 editable=OUT/'editable'/('public' if name=='male' else 'private');editable.mkdir(parents=True,exist_ok=True)
 bpy.ops.wm.save_as_mainfile(filepath=str(editable/(runtime.stem+'.blend')))
 bpy.ops.object.select_all(action='DESELECT')
 keep=[o for o in bpy.data.objects if o==rig or o.parent==rig]
 keep=[o for o in keep if not o.name.endswith('_Source')]
 for o in keep:o.hide_set(False);o.select_set(True)
 bpy.context.view_layer.objects.active=rig
 temp=OUT/(runtime.stem+'-pose-export.glb')
 bpy.ops.export_scene.gltf(filepath=str(temp),export_format='GLB',use_selection=True,export_animations=True,export_animation_mode='ACTIONS',export_force_sampling=True,export_morph=True,export_skins=True,export_yup=True,export_apply=False,export_extras=False)
 dest=OUT/('public' if name=='male' else 'private')/runtime.name
 report['merge']=merge_clips(runtime,temp,dest);temp.unlink()
 reports[name]=report
 (OUT/(name+'-posture-report.json')).write_text(json.dumps(report,indent=2)+'\n')
 print('POSTURE_ASSET_FINISHED',name,flush=True)
(OUT/'posture-report.json').write_text(json.dumps(reports,indent=2)+'\n')
