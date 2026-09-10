import {SceneLoader} from '@babylonjs/core/Loading/sceneLoader.js';
import {Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {Color3} from '@babylonjs/core/Maths/math.color.js';
import {VertexData} from '@babylonjs/core/Meshes/mesh.vertexData.js';
import {TABLE_SUPPORT_PROFILES} from './table-support-profiles.js';

const OLD_TABLE = new Set(['Exam table base','Exam table inset','Exam mattress','Paper covering','Soft pillow','Exam table step','Step nonslip']);
const smooth=(a,b,x)=>{const t=Math.max(0,Math.min(1,(x-a)/(b-a)));return t*t*(3-2*t);};
/** Physical support profiles mirror the editable Blender generator, in meters.
 * These are visual surfaces, not examination findings or patient measurements. */
export function mainCushionHeight(z,bodyBuild){const p=TABLE_SUPPORT_PROFILES[bodyBuild];const base=p?1.013:1.014;return base+((p?.backCushionM||1.037)-base)*smooth(-.14,-.26,z)*(1-smooth(-.62,-.79,z));}
export function legCushionHeight(z,bodyBuild){const p=TABLE_SUPPORT_PROFILES[bodyBuild];if(p)return p.calfCushionM+.012*(1-smooth(.12,.40,z))+(p.heelCushionM-p.calfCushionM)*smooth(p.calfZ+.025,p.heelZ,z);return 1.046+.012*(1-smooth(.12,.40,z))+.026*Math.exp(-(((z-.68)/.12)**2));}
export function patientSupportHeight(x,z,{posture='supine',includePillow=true,bodyBuild}={}){
 if(Math.abs(x)>.35||z< -1.14||z>.91)return null;
 const p=TABLE_SUPPORT_PROFILES[bodyBuild];let y=mainCushionHeight(z,bodyBuild)+.003;
 if(posture==='supine'&&z>=.085)y=legCushionHeight(z,bodyBuild)+.003;
 if(includePillow){const radius=1-(x/.245)**2-((z-(p?.pillowZ??-.745))/.17)**2;if(radius>0)y=Math.max(y,(p?.pillowCenterY??1.038)+.023*Math.sqrt(radius));}
 return y;
}
/** Project a surface in world meters before applying repeatable scanned maps.
 * Dominant-axis projection avoids stretching a square map across long walls. */
export function physicalScaleUV(mesh){
 const positions=mesh.getVerticesData('position'),normals=mesh.getVerticesData('normal');
 if(!positions||!normals)return;
 const world=mesh.computeWorldMatrix(true),uv=new Float32Array(positions.length/3*2);
 for(let i=0;i<positions.length;i+=3){
  const p=Vector3.TransformCoordinates(Vector3.FromArray(positions,i),world),n=Vector3.TransformNormal(Vector3.FromArray(normals,i),world);
  const a=[Math.abs(n.x),Math.abs(n.y),Math.abs(n.z)],axis=a.indexOf(Math.max(...a)),v=axis===0?[p.z,p.y]:axis===1?[p.x,p.z]:[p.x,p.y];uv[i/3*2]=v[0];uv[i/3*2+1]=v[1];
 }
 mesh.setVerticesData('uv',uv);
}
export async function createClinicalTable(scene,{shadowGenerator,assetUrl}={}){
 const old=scene.meshes.filter(mesh=>OLD_TABLE.has(mesh.name));
 const url=assetUrl||new URL('../assets/clinical-exam-table.glb',import.meta.url).href,split=url.lastIndexOf('/');
 const imported=await SceneLoader.ImportMeshAsync('',url.slice(0,split+1),url.slice(split+1),scene);
 const extension=scene.getTransformNodeByName('LegSupportExtension');
 if(!extension)throw new Error('The examination table is missing its leg support.');
 for(const mesh of old)mesh.setEnabled(false);
 const fabric=scene.getMaterialByName('Poly Haven fabric');
 const linen=scene.getMaterialByName('Pillow linen');
 if(fabric&&linen){linen.albedoTexture=fabric.albedoTexture;linen.bumpTexture=fabric.bumpTexture;linen.metallicTexture=fabric.metallicTexture;linen.useRoughnessFromMetallicTextureAlpha=false;linen.useRoughnessFromMetallicTextureGreen=true;linen.useMetallnessFromMetallicTextureBlue=true;linen.albedoColor=Color3.FromHexString('#eef1e9').toLinearSpace();}
 const upholstery=scene.getMaterialByName('Clinical upholstery');
 if(upholstery&&fabric?.bumpTexture){upholstery.bumpTexture=fabric.bumpTexture.clone();upholstery.bumpTexture.uScale=12;upholstery.bumpTexture.vScale=12;upholstery.bumpTexture.level=.035;upholstery.invertNormalMapX=false;upholstery.invertNormalMapY=true;}
 for(const mesh of imported.meshes){mesh.isPickable=false;mesh.receiveShadows=true;if(mesh.getTotalVertices()>0)shadowGenerator?.addShadowCaster(mesh);}
 const fittedNames=new Set(['Main upholstered cushion','Main cushion tailored seam','Fresh main examination paper','Upholstered leg extension','Leg cushion tailored seam','Fresh leg examination paper']);
 const fitted=imported.meshes.filter(m=>fittedNames.has(m.name)).map(mesh=>({mesh,original:new Float32Array(mesh.getVerticesData('position')),world:mesh.computeWorldMatrix(true).clone()}));
 const pillow=scene.getTransformNodeByName('PositioningPillow'),pillowRest=pillow?.position.clone();let bodyBuild=null;
 function fitSupport(next){
  if(next===bodyBuild)return;bodyBuild=next;const profile=TABLE_SUPPORT_PROFILES[next];
  for(const {mesh,original,world}of fitted){
   const positions=new Float32Array(original),inverse=world.clone().invert(),leg=/leg/i.test(mesh.name),bottom=leg ? .968 : .923,oldHeight=leg?legCushionHeight:mainCushionHeight;
   for(let i=0;i<positions.length;i+=3){const p=Vector3.TransformCoordinates(Vector3.FromArray(original,i),world),before=oldHeight(p.z),after=oldHeight(p.z,next),blend=/paper|seam/.test(mesh.name)?1:Math.max(0,Math.min(1,(p.y-bottom)/(before-bottom)));p.y+=(after-before)*blend;Vector3.TransformCoordinates(p,inverse).toArray(positions,i);}
   const normals=new Float32Array(positions.length);VertexData.ComputeNormals(positions,mesh.getIndices(),normals,{useRightHandedSystem:scene.useRightHandedSystem});mesh.setVerticesData('position',positions,true);mesh.setVerticesData('normal',normals,true);mesh.refreshBoundingInfo();
  }
  if(pillow){pillow.position.copyFrom(pillowRest);pillow.position.y+=(profile?.pillowCenterY??1.038)-1.038;pillow.position.z+=(profile?.pillowZ??-.745)+.745;}
 }
 // Local Poly Haven wall/cabinet maps retain their scanned grain proportions.
 for(const mesh of scene.meshes){if(/^(Back wall|Left wall|Corridor wall|Wall above doorway|Cabinet( door(\.\d+)?)?|Hinged examination-room door)$/.test(mesh.name))physicalScaleUV(mesh);}
 let posture=null,extensionTransition=null;
 const extensionRest=extension.position.clone(),clock=()=>globalThis.performance?.now?.()||Date.now();
 const report={asset:'clinical-exam-table.glb',meshCount:imported.meshes.filter(m=>m.getTotalVertices()).length,legacyMeshesHidden:old.map(m=>m.name),support:'Authored pillow, upper-back cushion, pelvis surface and retractable lower-leg support. Separate measured fit for historical base and three MPFB body builds.',bodyBuilds:['base',...Object.keys(TABLE_SUPPORT_PROFILES)],source:'Editable Blender geometry plus existing local Poly Haven CC0 maps.'};
 const controller={report,update(state={}){
  fitSupport(state.appearance?.bodyBuild||'base');
  const next=state.posture==='supine'?'supine':'seated';if(posture===next)return;
  const animated=posture!==null&&state.phase==='encounter'&&!state.reducedMotion;
  posture=next;extensionTransition=null;extension.position.copyFrom(extensionRest);
  // Keep the lower-leg space clear while the knees unfold. The support rises
  // after the authored 600 ms patient pose has settled, rather than appearing
  // through the patient's legs at the beginning of the movement.
  if(animated&&next==='supine'){extension.setEnabled(false);extensionTransition={start:clock()+620,duration:180};}
  else extension.setEnabled(next==='supine');
 },animate(now=clock()){
  if(!extensionTransition)return;
  if(now<extensionTransition.start)return;
  const t=Math.min(1,(now-extensionTransition.start)/extensionTransition.duration),e=t*t*(3-2*t);
  extension.setEnabled(true);extension.position.y=extensionRest.y-.10*(1-e);
  if(t===1)extensionTransition=null;
 },dispose(){scene.onBeforeRenderObservable.remove(observer);for(const mesh of imported.meshes)mesh.dispose();}};
 const observer=scene.onBeforeRenderObservable.add(()=>controller.animate());
 controller.update();scene.metadata={...scene.metadata,clinicalTable:report};return controller;
}
