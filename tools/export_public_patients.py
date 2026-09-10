"""Export the existing clinical patient views without replacing human skin.
Female runtime GLBs retain the exact original binary payload (geometry, skin,
textures, morphs, skeleton and animation). Only public wardrobe node names change.
The original MPFB source scenes and runtime assets are opened read-only.
Set PCM_PRIVATE_ASSETS to the original MPFB source directory and PCM_PRIVATE_GLBS
to its already-exported patient3d/assets directory. No trial assets are used.
"""
from pathlib import Path
import bpy,json,math,os,struct
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(os.environ['PCM_PRIVATE_ASSETS'])
RUNTIME=Path(os.environ['PCM_PRIVATE_GLBS'])
OUT=ROOT/'web/patient3d/assets';OUT.mkdir(parents=True,exist_ok=True)
EDIT=ROOT/'editable-public-assets';EDIT.mkdir(exist_ok=True)

def subset(source,name,polys,material=None):
 ids=sorted({i for p in polys for i in p.vertices});remap={old:i for i,old in enumerate(ids)}
 mesh=bpy.data.meshes.new(name);mesh.from_pydata([source.data.vertices[i].co for i in ids],[],[[remap[i] for i in p.vertices] for p in polys]);mesh.update()
 obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);obj.parent=source.parent
 for m in ([material] if material else source.data.materials):mesh.materials.append(m)
 for uv in source.data.uv_layers:
  layer=mesh.uv_layers.new(name=uv.name)
  for a,b in zip(polys,mesh.polygons):
   for x,y in zip(a.loop_indices,b.loop_indices):layer.data[y].uv=uv.data[x].uv
 for group in source.vertex_groups:obj.vertex_groups.new(name=group.name)
 for old,i in remap.items():
  for g in source.data.vertices[old].groups:obj.vertex_groups[g.group].add([i],g.weight,'REPLACE')
 if source.data.shape_keys:
  for sk in source.data.shape_keys.key_blocks:
   key=obj.shape_key_add(name=sk.name)
   for old,i in remap.items():key.data[i].co=sk.data[old].co
 for mod in source.modifiers:
  if mod.type=='ARMATURE':m=obj.modifiers.new('Patient rig','ARMATURE');m.object=mod.object
 for p in mesh.polygons:p.use_smooth=True
 return obj

NODE_NAMES={'PCM_FemaleBody':'PCM_AnatomicalBody',
 'PCM_FemaleBody_Covered':'PCM_PublicBody','PCM_FittedKnit':'PCM_PublicKnit',
 'PCM_FittedCasual':'PCM_PublicTrousers','PCM_Sneakers':'PCM_PublicShoes'}

def copy_female_runtime(build):
 source=RUNTIME/('mpfb-female-'+build+'.glb')
 data=source.read_bytes();length,kind=struct.unpack_from('<II',data,12)
 assert data[:4]==b'glTF' and kind==0x4e4f534a
 doc=json.loads(data[20:20+length])
 for node in doc['nodes']:
  if node.get('name') in NODE_NAMES:node['name']=NODE_NAMES[node['name']]
 payload=json.dumps(doc,separators=(',',':')).encode();payload+=b' '*((-len(payload))%4)
 binary=data[20+length:]
 out=struct.pack('<4sII',b'glTF',2,20+len(payload)+len(binary))+struct.pack('<II',len(payload),kind)+payload+binary
 (OUT/('public-female-'+build+'.glb')).write_bytes(out)
 print('EXACT_FEMALE_RUNTIME',build,flush=True)

def male_deform(co,height):
 x,y,z=co;u=z/height
 if u>=.85:return co.copy() # Exactly preserve the existing face/head.
 # Neutral basic male torso, broad shoulders and narrower pelvis; same rig.
 chest=max(0,1-abs(u-.738)/.108)
 if abs(x)<height*.17 and y<0 and chest>0:
  # Rounded thoracic cross-section rather than a flat clipping plane. Blend
  # gradually through the chest into the abdomen/shoulders.
  radial=max(.12,1-(x/(height*.175))**2)**.5
  target=-height*(.075*radial+.006)
  blend=min(1.,chest*1.8)
  y=y*(1-blend)+max(y,target)*blend
 width=1+.10*max(0,1-abs(u-.805)/.10)-.055*max(0,1-abs(u-.53)/.11)
 return Vector((x*width,y,z))

for build,sex in ([('standard','male')] if os.environ.get('PCM_PUBLIC_MALE_ONLY') else [('short-slender','female'),('standard','female'),('tall-full','female'),('standard','male')]):
 bpy.ops.wm.open_mainfile(filepath=str(SOURCE/'variants'/build/'MPFB-female-patient.blend'))
 if sex=='female':
  for old,new in NODE_NAMES.items():bpy.data.objects[old].name=new
  bpy.ops.wm.save_as_mainfile(filepath=str(EDIT/('public-female-'+build+'.blend')))
  copy_female_runtime(build)
  continue
 body=bpy.data.objects['PCM_FemaleBody'];rig=body.parent
 rig.animation_data.action=None
 from mathutils import Matrix
 rig.location=(0,0,0);rig.rotation_quaternion=(1,0,0,0)
 for b in rig.pose.bones:b.matrix_basis=Matrix.Identity(4)
 h=max(v.co.z for v in body.data.vertices);male=sex=='male'
 if male:
  for key in body.data.shape_keys.key_blocks:
   for v in key.data:v.co=male_deform(v.co,h)
  for v in body.data.vertices:v.co=male_deform(v.co,h)
 # Existing male torso adaptation uses the original human skin material.
 # It is an approximate surface model, not a genital-examination model.
 manikin=subset(body,'PCM_AnatomicalBody',list(body.data.polygons))
 # Smooth the central anterior pelvic surface. Vaginal, rectal, and genital
 # examination detail is intentionally excluded from this public teaching view.
 adjacency=[set() for _ in manikin.data.vertices]
 for edge in manikin.data.edges:
  a,b=edge.vertices;adjacency[a].add(b);adjacency[b].add(a)
 for key in manikin.data.shape_keys.key_blocks:
  coords=[v.co.copy() for v in key.data]
  for iteration in range(24):
   new=[v.copy() for v in coords]
   for i,v in enumerate(coords):
    if abs(v.x)<h*.057 and .42<v.z/h<.56 and v.y<-.015 and adjacency[i]:
     new[i]=v.lerp(sum((coords[j] for j in adjacency[i]),Vector())/len(adjacency[i]),.65)
   coords=new
  for v,co in zip(key.data,coords):v.co=co
 manikin.hide_render=True
 # The public edition uses the existing fully clothed presentation. The
 # clothing-masked body physically lacks the concealed torso/pelvic surfaces.
 covered=bpy.data.objects['PCM_FemaleBody_Covered']
 if male:
  for key in covered.data.shape_keys.key_blocks:
   for v in key.data:v.co=male_deform(v.co,h)
  for v in covered.data.vertices:v.co=male_deform(v.co,h)
 skin=subset(covered,'PCM_PublicBody',list(covered.data.polygons))
 clothes=[]
 for old,new in [('PCM_FittedKnit','PCM_PublicKnit'),('PCM_FittedCasual','PCM_PublicTrousers'),('PCM_Sneakers','PCM_PublicShoes')]:
  obj=bpy.data.objects[old];obj.name=new
  if male:
   for v in obj.data.vertices:v.co=male_deform(v.co,h)
  clothes.append(obj)
 # Keep eyes, eyebrows, teeth, tongue and appropriate licensed hair.
 keep=[rig,skin,manikin]+clothes+[bpy.data.objects[n] for n in ['PCM_Eyes','PCM_Eyebrows','PCM_Teeth','PCM_Tongue']]
 if not male:keep.append(bpy.data.objects['PCM_LongHair'])
 keep += [bpy.data.objects[n] for n in ['Face','Chest','Abdomen','Lap']]
 # Keep only the clothed and anatomical presentations with the shared rig.
 for obj in list(bpy.data.objects):
  if obj not in keep:bpy.data.objects.remove(obj,do_unlink=True)
 # Discard unused source datablocks before saving the public editable file.
 for _ in range(3):bpy.ops.outliner.orphans_purge(do_local_ids=True,do_linked_ids=True,do_recursive=True)
 for obj in keep:obj.hide_render=False;obj.hide_set(False)
 rig.animation_data_create();rig.animation_data.action=bpy.data.actions.get('PCM_Seated');bpy.context.scene.frame_set(1)
 bpy.ops.object.select_all(action='DESELECT')
 for obj in keep:obj.select_set(True)
 bpy.context.view_layer.objects.active=rig
 # Existing hair shader multiply has to be flattened for the glTF material.
 if not male:
  mat=bpy.data.objects['PCM_LongHair'].data.materials[0];bs=mat.node_tree.nodes.get('Principled BSDF')
  link=next(iter(bs.inputs['Base Color'].links),None)
  if link and link.from_node.type=='MIX_RGB':
   tex=next((l.from_node for l in link.from_node.inputs[1].links),None)
   if tex:mat.node_tree.links.new(tex.outputs['Color'],bs.inputs['Base Color'])
 name='public-male-standard' if male else 'public-female-'+build
 bpy.ops.wm.save_as_mainfile(filepath=str(EDIT/(name+'.blend')))
 bpy.ops.export_scene.gltf(filepath=str(OUT/(name+'.glb')),export_format='GLB',use_selection=True,export_animations=True,export_animation_mode='ACTIONS',export_force_sampling=True,export_morph=True,export_skins=True,export_yup=True,export_apply=False,export_extras=False)
 print('PUBLIC_EXPORTED',name,flush=True)
