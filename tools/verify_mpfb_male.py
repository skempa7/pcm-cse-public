"""Builder-side exported-asset verification, not an independent app critique.

Run with Blender --factory-startup --background --python tools/verify_mpfb_male.py.
Checks source vs reimported GLB poses/anchors/bounds, and renders actual GLB views.
"""
from pathlib import Path
import bpy,json,math,hashlib,struct,os
from mathutils import Vector
from mathutils.kdtree import KDTree
ROOT=Path(os.environ.get('PCM_MALE_BUILD_ROOT', str(Path(__file__).resolve().parents[1])));OUT=ROOT/'postures'
def activate(posture):
    rig=bpy.data.objects['PCM_MaleRig']
    for track in rig.animation_data.nla_tracks:track.mute=True
    rig.animation_data.action=bpy.data.actions['PCM_'+posture.capitalize()]
    bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
    return rig
def state():
    names=['PCM_AnatomicalBody','PCM_PublicBody','PCM_Eyes','PCM_Eyebrows','PCM_PublicTrousers','PCM_PublicKnit','PCM_PublicShoes','PCM_Teeth','PCM_Tongue']
    dg=bpy.context.evaluated_depsgraph_get();bounds={};points={}
    for name in names:
        obj=bpy.data.objects[name];ev=obj.evaluated_get(dg);mesh=ev.to_mesh()
        # glTF omits loose, unrendered vertices. Compare actual polygon surfaces.
        rendered_ids={i for poly in mesh.polygons for i in poly.vertices}
        positions=[ev.matrix_world@mesh.vertices[i].co for i in rendered_ids]
        points[name]=positions
        bounds[name]={'min':[min(v[i]for v in positions)for i in range(3)],'max':[max(v[i]for v in positions)for i in range(3)]}
        ev.to_mesh_clear()
    return {'anchors':{n:list(bpy.data.objects[n].matrix_world.translation)for n in ('Face','Chest','Abdomen','Lap')},'bounds':bounds,'_points':points}
bpy.ops.wm.open_mainfile(filepath=str(OUT/'editable/public/public-male-standard.blend'))
source={}
for p in ('seated','supine','standing','prone'):activate(p);source[p]=state()
bpy.ops.wm.read_factory_settings(use_empty=True)
glb=OUT/'public/public-male-standard.glb'
bpy.ops.import_scene.gltf(filepath=str(glb))
actual={}
for p in ('seated','supine','standing','prone'):activate(p);actual[p]=state()
differences=[];surface_differences={}
for p in source:
    for n in source[p]['anchors']:
        differences.append(max(abs(a-b)for a,b in zip(source[p]['anchors'][n],actual[p]['anchors'][n])))
    for n in source[p]['bounds']:
        for k in ('min','max'):differences.append(max(abs(a-b)for a,b in zip(source[p]['bounds'][n][k],actual[p]['bounds'][n][k])))
        left=source[p]['_points'][n];right=actual[p]['_points'][n]
        distances=[]
        for a,b in [(left,right),(right,left)]:
            tree=KDTree(len(b))
            for i,co in enumerate(b):tree.insert(co,i)
            tree.balance();distances.append(max(tree.find(co)[2]for co in a))
        surface_differences[p+'/'+n]=max(distances);differences.append(max(distances))
    del source[p]['_points'];del actual[p]['_points']
print('PCM_SURFACE_DIFFERENCES',json.dumps(surface_differences),flush=True)
assert max(differences)<.002, 'Export/import changed posed anatomy or anchors beyond 2 mm: '+str(max(differences))
raw=glb.read_bytes();size=struct.unpack_from('<I',raw,12)[0];gltf=json.loads(raw[20:20+size])
assert {a['name']for a in gltf['animations']}=={'PCM_Seated','PCM_Supine','PCM_Standing','PCM_Prone'}
for name in ('PCM_AnatomicalBody','PCM_PublicBody','PCM_Eyebrows'):
    keys=bpy.data.objects[name].data.shape_keys.key_blocks
    for key in ('Blink','Speech','Concern','Discomfort','Warmth'):assert key in keys and keys[key].value==0
report={'glb_sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'source_vs_glb_max_coordinate_difference_m':max(differences),'posed_surface_hausdorff_m':surface_differences,'source':source,'reimported_glb':actual,'clips':[{ 'name':a['name'],'channels':len(a['channels'])}for a in gltf['animations']],'neutral_morphs_zero':True,'scope':'Builder-side asset structure and pose readback. Browser operation and independent critique are separate requirements.'}
(OUT/'export-verification.json').write_text(json.dumps(report,indent=2)+'\n')


# Surface samples from a independently imported final GLB drive the male table.
from mathutils.bvhtree import BVHTree
activate('supine');body=bpy.data.objects['PCM_AnatomicalBody'];rig=body.parent
ev=body.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
verts=[ev.matrix_world@v.co for v in mesh.vertices]
tree=BVHTree.FromPolygons(verts,[list(p.vertices)for p in mesh.polygons]);rows=[]
for zi in range(-40,37):
 z=zi*.025;row=[]
 for x in (-.2,-.15,-.1,-.05,0,.05,.1,.15,.2):
  hit=tree.ray_cast(Vector((x,-z,0)),Vector((0,0,1)))[0]
  if hit is not None:row.append({'x':x,'y':hit.z})
 rows.append({'z':z,'samples':row})
def minimum(a,b):return min((p['y'],p['x'],row['z'])for row in rows if a<=row['z']<=b for p in row['samples']if abs(p['x'])<.2)
head=minimum(-1.,-.65);back=minimum(-.65,-.38);calf=minimum(.4,.65)
foot=rig.matrix_world@rig.pose.bones['foot_l'].head;ankle=-foot.y;heel=minimum(ankle-.035,ankle+.06)
profile=dict(sourceHash=hashlib.sha256(raw).hexdigest(),heightM=1.78,backCushionM=back[0]-.006,calfCushionM=calf[0]-.006,heelCushionM=heel[0]-.006,calfZ=calf[2],heelZ=ankle-.015,pillowZ=head[2],pillowCenterY=head[0]-.025,supportSamples=dict(occiput=head,back=back,calf=calf,heel=heel))
(OUT/'male-supine-support.json').write_text(json.dumps(profile,indent=2)+'\n')
report['supine_surface_rows']=rows;report['male_supine_support']=profile
(OUT/'export-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('NEW_MALE_GLTF_VERIFIED',max(differences),len(raw),flush=True)
