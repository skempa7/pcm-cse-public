import {SceneLoader} from '@babylonjs/core/Loading/sceneLoader.js';
import {Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {Color3} from '@babylonjs/core/Maths/math.color.js';
import {VertexData} from '@babylonjs/core/Meshes/mesh.vertexData.js';
import {TABLE_SUPPORT_PROFILES} from './table-support-profiles.js';

const OLD_TABLE = new Set(['Exam table base','Exam table inset','Exam mattress','Paper covering','Soft pillow','Exam table step','Step nonslip']);
const smooth=(a,b,x)=>{const t=Math.max(0,Math.min(1,(x-a)/(b-a)));return t*t*(3-2*t);};
/** Measured from the exported prone skin surface, with 7 mm clearance. The
 * original seated/supine profiles below remain unchanged. Positioning changes
 * the support geometry; it never changes body dimensions or clinical facts. */
const PRONE_SUPPORT_PROFILES=Object.freeze({"base":{"cushion":[[-0.5,1.038],[-0.46,1.038],[-0.42,1.04683],[-0.38,1.04683],[-0.34,1.0492],[-0.3,1.05332],[-0.26,1.05121],[-0.22,1.05503],[-0.18,1.06451],[-0.14,1.06938],[-0.1,1.06591],[-0.06,1.0605],[-0.02,1.05584],[0.02,1.05482],[0.06,1.05482],[0.1,1.05629],[0.14,1.06291],[0.18,1.06558],[0.22,1.06905],[0.26,1.07774],[0.3,1.09937],[0.34,1.10493],[0.38,1.10676],[0.42,1.10747],[0.46,1.11096],[0.5,1.11226],[0.54,1.11496],[0.58,1.11224],[0.62,1.11224],[0.66,1.11161],[0.7,1.09915],[0.74,1.07869],[0.78,1.07869]],"pillowZ":-0.82921,"pillowCenterY":1.05849},"short-slender":{"cushion":[[-0.5,1.038],[-0.46,1.038],[-0.42,1.0469],[-0.38,1.0469],[-0.34,1.05327],[-0.3,1.05505],[-0.26,1.05505],[-0.22,1.05847],[-0.18,1.06684],[-0.14,1.07124],[-0.1,1.0683],[-0.06,1.06413],[-0.02,1.06022],[0.02,1.05933],[0.06,1.05933],[0.1,1.06038],[0.14,1.063],[0.18,1.06716],[0.22,1.06816],[0.26,1.07139],[0.3,1.08499],[0.34,1.10232],[0.38,1.10431],[0.42,1.10686],[0.46,1.11009],[0.5,1.11095],[0.54,1.11095],[0.58,1.1127],[0.62,1.10968],[0.66,1.10968],[0.7,1.10944],[0.74,1.09633],[0.78,1.07534],[0.82,1.07534]],"pillowZ":-0.85026,"pillowCenterY":1.05776},"standard":{"cushion":[[-0.5,1.038],[-0.46,1.0397],[-0.42,1.04709],[-0.38,1.04709],[-0.34,1.05174],[-0.3,1.05176],[-0.26,1.05176],[-0.22,1.05559],[-0.18,1.06525],[-0.14,1.07018],[-0.1,1.06714],[-0.06,1.06132],[-0.02,1.05907],[0.02,1.05489],[0.06,1.05489],[0.1,1.05616],[0.14,1.0594],[0.18,1.06258],[0.22,1.06683],[0.26,1.0684],[0.3,1.07697],[0.34,1.09903],[0.38,1.10455],[0.42,1.10626],[0.46,1.10677],[0.5,1.11051],[0.54,1.11214],[0.58,1.11515],[0.62,1.11495],[0.66,1.11169],[0.7,1.11169],[0.74,1.11088],[0.78,1.09499],[0.82,1.07582],[0.86,1.07582]],"pillowZ":-0.86808,"pillowCenterY":1.06066},"tall-full":{"cushion":[[-0.5,1.038],[-0.46,1.04449],[-0.42,1.04728],[-0.38,1.04728],[-0.34,1.04769],[-0.3,1.04583],[-0.26,1.04583],[-0.22,1.04949],[-0.18,1.06025],[-0.14,1.06606],[-0.1,1.06486],[-0.06,1.05908],[-0.02,1.05593],[0.02,1.05242],[0.06,1.05177],[0.1,1.05371],[0.14,1.05762],[0.18,1.06179],[0.22,1.06558],[0.26,1.07032],[0.3,1.08049],[0.34,1.09025],[0.38,1.10787],[0.42,1.10889],[0.46,1.10955],[0.5,1.10955],[0.54,1.11354],[0.58,1.11552],[0.62,1.11947],[0.66,1.11968],[0.7,1.11657],[0.74,1.11778],[0.78,1.11146],[0.82,1.09486],[0.86,1.07937],[0.9,1.07937]],"pillowZ":-0.88582,"pillowCenterY":1.06659},"male":{"cushion":[[-0.5,1.038],[-0.46,1.038],[-0.42,1.04532],[-0.38,1.04781],[-0.34,1.04978],[-0.3,1.05119],[-0.26,1.05018],[-0.22,1.05177],[-0.18,1.05357],[-0.14,1.0556],[-0.1,1.06267],[-0.06,1.04429],[-0.02,1.0418],[0.02,1.04238],[0.06,1.05703],[0.1,1.05819],[0.14,1.05903],[0.18,1.07073],[0.22,1.07448],[0.26,1.07475],[0.3,1.08683],[0.34,1.09632],[0.38,1.10611],[0.42,1.11094],[0.46,1.11524],[0.5,1.11666],[0.54,1.12019],[0.58,1.12209],[0.62,1.12209],[0.66,1.12169],[0.7,1.1188],[0.74,1.11621],[0.78,1.11401],[0.82,1.10716],[0.86,1.09162],[0.9,1.08124],[0.94,1.08124]],"pillowZ":-0.88197,"pillowCenterY":1.04064}});
function proneProfile(bodyBuild,presentation){return PRONE_SUPPORT_PROFILES[presentation==='male'?'male':bodyBuild]||PRONE_SUPPORT_PROFILES.base;}
export function proneCushionHeight(z,bodyBuild,presentation='female',outfit='unclothed'){
 const clothed=!['unclothed','clinical-anatomy'].includes(outfit),allowance=clothed?(.011+(presentation==='male'?.007:0))+(.022-(presentation==='male'?.007:0))*smooth(.50,.64,z):0;
 // Small mattress compression under the updated female thorax; measured against
 // the authored rest shape. Clinical findings and all patient pose clips stay unchanged.
 const chestCenters={base:-.481,'short-slender':-.492,standard:-.502,'tall-full':-.510};
 const chestWidths={base:.094,'short-slender':.096,standard:.098,'tall-full':.101};
 // 2026-09-12: current public bodies need 10 mm more local compression.
 // Checked against actual skinned vertices and rendered cushion ray hits in all builds.
 const chestDepths={base:.018,'short-slender':.0285,standard:.029,'tall-full':.0295};
 const key=Object.hasOwn(chestCenters,bodyBuild)?bodyBuild:'base',t=(z-chestCenters[key])/chestWidths[key];
 const chestRelief=presentation==='female'&&Math.abs(t)<1?chestDepths[key]*(1+Math.cos(Math.PI*t))/2:0;
 return rawProneCushionHeight(z,bodyBuild,presentation)-allowance-chestRelief;
}
function rawProneCushionHeight(z,bodyBuild,presentation){
 const rows=proneProfile(bodyBuild,presentation).cushion;
 if(z<-.65)return 1.041;
 if(z<rows[0][0])return 1.041+(rows[0][1]-1.041)*smooth(-.65,rows[0][0],z);
 for(let i=1;i<rows.length;i++)if(z<=rows[i][0]){const [a,y]=rows[i-1],[b,v]=rows[i];return y+(v-y)*smooth(a,b,z);}
 return rows.at(-1)[1];
}
/** Physical support profiles mirror the editable Blender generator, in meters.
 * These are visual surfaces, not examination findings or patient measurements. */
export function mainCushionHeight(z,bodyBuild){const p=TABLE_SUPPORT_PROFILES[bodyBuild];const base=p?1.013:1.014;return base+((p?.backCushionM||1.037)-base)*smooth(-.14,-.26,z)*(1-smooth(-.62,-.79,z));}
export function legCushionHeight(z,bodyBuild){const p=TABLE_SUPPORT_PROFILES[bodyBuild];if(p)return p.calfCushionM+.012*(1-smooth(.12,.40,z))+(p.heelCushionM-p.calfCushionM)*smooth(p.calfZ+.025,p.heelZ,z);return 1.046+.012*(1-smooth(.12,.40,z))+.026*Math.exp(-(((z-.68)/.12)**2));}
export function patientSupportHeight(x,z,{posture='supine',includePillow=true,bodyBuild,presentation='female',outfit='unclothed'}={}){
 if(presentation==='male')bodyBuild='male';
 if(Math.abs(x)>.35||z< -1.14||z>.91)return null;
 const prone=posture==='prone',p=prone?proneProfile(bodyBuild,presentation):TABLE_SUPPORT_PROFILES[bodyBuild];
 let y=prone?proneCushionHeight(z,bodyBuild,presentation,outfit)+.003:mainCushionHeight(z,bodyBuild)+.003;
 if(posture==='supine'&&z>=.085)y=legCushionHeight(z,bodyBuild)+.003;
 if(includePillow){const cx=prone?-.045:0,radius=1-((x-cx)/.245)**2-((z-(p?.pillowZ??-.745))/.17)**2;if(radius>0)y=Math.max(y,(p?.pillowCenterY??1.038)+.023*Math.sqrt(radius));}
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
 if(upholstery){upholstery.albedoColor=Color3.FromHexString('#bca58a').toLinearSpace();upholstery.roughness=.72;upholstery.metallic=0;}
 for(const [name,color]of [['Upholstery piping','#8f775d'],['Table enamel','#eeeae3'],['Powder coated frame','#9d9c94']]){const m=scene.getMaterialByName(name);if(m)m.albedoColor=Color3.FromHexString(color).toLinearSpace();}
 if(upholstery&&fabric?.bumpTexture){upholstery.bumpTexture=fabric.bumpTexture.clone();upholstery.bumpTexture.uScale=12;upholstery.bumpTexture.vScale=12;upholstery.bumpTexture.level=.035;upholstery.invertNormalMapX=false;upholstery.invertNormalMapY=true;}
 for(const mesh of imported.meshes){mesh.isPickable=false;mesh.receiveShadows=true;if(mesh.getTotalVertices()>0)shadowGenerator?.addShadowCaster(mesh);}
 const fittedNames=new Set(['Main upholstered cushion','Main cushion tailored seam','Fresh main examination paper','Upholstered leg extension','Leg cushion tailored seam','Fresh leg examination paper']);
 const fitted=imported.meshes.filter(m=>fittedNames.has(m.name)).map(mesh=>({mesh,original:new Float32Array(mesh.getVerticesData('position')),world:mesh.computeWorldMatrix(true).clone()}));
 const pillow=scene.getTransformNodeByName('PositioningPillow'),pillowRest=pillow?.position.clone();let supportIdentity=null;
 function fitSupport(next,nextPosture,presentation,outfit){
  if(presentation==='male')next='male';
  const isProne=nextPosture==='prone',identity=[next,isProne,presentation,isProne?outfit:''].join(':');
  if(identity===supportIdentity)return;supportIdentity=identity;const profile=isProne?proneProfile(next,presentation):TABLE_SUPPORT_PROFILES[next];
  for(const {mesh,original,world}of fitted){
   const positions=new Float32Array(original),inverse=world.clone().invert(),leg=/leg/i.test(mesh.name),bottom=leg ? .968 : .923,oldHeight=leg?legCushionHeight:mainCushionHeight;
   for(let i=0;i<positions.length;i+=3){const p=Vector3.TransformCoordinates(Vector3.FromArray(original,i),world),before=oldHeight(p.z),after=isProne?proneCushionHeight(p.z,next,presentation,outfit):oldHeight(p.z,next),blend=/paper|seam/.test(mesh.name)?1:Math.max(0,Math.min(1,(p.y-bottom)/(before-bottom)));p.y+=(after-before)*blend;Vector3.TransformCoordinates(p,inverse).toArray(positions,i);}
   const normals=new Float32Array(positions.length);VertexData.ComputeNormals(positions,mesh.getIndices(),normals,{useRightHandedSystem:scene.useRightHandedSystem});mesh.setVerticesData('position',positions,true);mesh.setVerticesData('normal',normals,true);mesh.refreshBoundingInfo();
  }
  if(pillow){pillow.position.copyFrom(pillowRest);if(isProne)pillow.position.x-=.045;pillow.position.y+=(profile?.pillowCenterY??1.038)-1.038;pillow.position.z+=(profile?.pillowZ??-.745)+.745;}
 }
 // Local Poly Haven wall/cabinet maps retain their scanned grain proportions.
 for(const mesh of scene.meshes){if(/^(Back wall|Left wall|Corridor wall|Wall above doorway|Cabinet( door(\.\d+)?)?|Hinged examination-room door)$/.test(mesh.name))physicalScaleUV(mesh);}
 let posture=null,extensionTransition=null;
 const extensionRest=extension.position.clone(),clock=()=>globalThis.performance?.now?.()||Date.now();
 const report={asset:'clinical-exam-table.glb',meshCount:imported.meshes.filter(m=>m.getTotalVertices()).length,legacyMeshesHidden:old.map(m=>m.name),support:'Authored pillow, upper-back cushion, pelvis surface and retractable lower-leg support. Separate measured seated/supine and prone fits for historical base, three female builds and the independently generated adult male.',bodyBuilds:['base',...Object.keys(TABLE_SUPPORT_PROFILES)],source:'Editable Blender geometry plus existing local Poly Haven CC0 maps.'};
 const controller={report,update(state={}){
  const next=['seated','supine','standing','prone'].includes(state.posture)?state.posture:'seated';
  fitSupport(state.appearance?.bodyBuild||'base',next,state.appearance?.presentation||'female',state.appearance?.outfit||'fitted-casual');
  if(posture===next)return;
  const animated=posture!==null&&state.phase==='encounter'&&!state.reducedMotion;
  posture=next;extensionTransition=null;extension.position.copyFrom(extensionRest);
  // Keep the lower-leg space clear while the knees unfold. The support rises
  // after the authored 600 ms patient pose has settled, rather than appearing
  // through the patient's legs at the beginning of the movement.
  if(animated&&['supine','prone'].includes(next)){extension.setEnabled(false);extensionTransition={start:clock()+620,duration:180};}
  else extension.setEnabled(['supine','prone'].includes(next));
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
