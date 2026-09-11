/** Shared clinical patient views for the authored adult public cohort. */
import {Color3} from '@babylonjs/core/Maths/math.color.js';
import {Texture} from '@babylonjs/core/Materials/Textures/texture.js';
import {MorphTarget} from '@babylonjs/core/Morph/morphTarget.js';
import {MorphTargetManager} from '@babylonjs/core/Morph/morphTargetManager.js';
import {Matrix,Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {createAnimatedPatient} from './animated-patient.js';
import {prepareMPFBHairSupport} from './mpfb-support.js';

const HAIR = Object.freeze({blonde:'#d4ba82',brunette:'#62412e',black:'#282322',ginger:'#b96c40'});
const SKIN = Object.freeze(['#fffaf6','#fff1e5','#f5e8dc']);
const CLOTHING = new Set(['PCM_FittedKnit','PCM_FittedCasual','PCM_Sneakers']);
const EYE_ANGLE = Math.PI / 60;
/** Sparse attention glances, not a repeated clinical eye-movement sign. */
export function mpfbGazeIntent(state={}, now=0) {
  if(state.reducedMotion || state.phase!=='encounter')return{x:0,y:0};
  const seconds=Math.max(0,now/1000), cycle=Math.floor(seconds/54.3), t=seconds%54.3;
  const events=[[4.1,.035,-.008],[12.0,-.028,.011],[23.4,.022,-.009],[30.2,.037,.003],[39.8,-.032,-.008],[51.1,.024,.010]];
  const event=events.find(([start])=>t>=start&&t<start+2.15);
  if(!event)return{x:0,y:0};
  const u=t-event[0], smooth=x=>x*x*(3-2*x);
  const strength=u<.26?smooth(u/.26):u>1.45?1-smooth((u-1.45)/.7):1;
  const attention=(state.listening===true || state.speaking===true) ? .38 : 1;
  const drift=.82+.18*Math.sin((cycle+1)*7.31+event[0]);
  return{x:event[1]*strength*attention*drift,y:event[2]*strength*attention*drift};
}
/** Generate restrained, reproducible geometry controls from the actual eye
 * halves. These are not exported FACS controls or a diagnostic gaze exam. */
export function prepareMPFBEyeGeometry(container,scene) {
  const mesh=container.meshes.find(mesh=>mesh.name==='PCM_Eyes');
  const positions=mesh?.getVerticesData('position'),normals=mesh?.getVerticesData('normal');
  if(!positions || mesh.morphTargetManager)return{gazeUnavailable:'Eye geometry already has controls or is unavailable.'};
  const bounds=[{min:Vector3.Zero().setAll(Infinity),max:Vector3.Zero().setAll(-Infinity),count:0},{min:Vector3.Zero().setAll(Infinity),max:Vector3.Zero().setAll(-Infinity),count:0}];
  for(let i=0;i<positions.length;i+=3){const v=Vector3.FromArray(positions,i),b=bounds[v.x<0?0:1];b.min=Vector3.Minimize(b.min,v);b.max=Vector3.Maximize(b.max,v);b.count++;}
  if(bounds.some(b=>b.count<250||b.count>650||b.max.x-b.min.x>.04||b.max.x-b.min.x<.02))return{gazeUnavailable:'Eye dimensions require a fresh asset review.'};
  const centers=bounds.map(b=>b.min.add(b.max).scale(.5)),manager=new MorphTargetManager(scene),names=[];
  for(const [name,yaw,pitch] of [['PCM_GazeLeft',-EYE_ANGLE,0],['PCM_GazeRight',EYE_ANGLE,0],['PCM_GazeUp',0,-EYE_ANGLE],['PCM_GazeDown',0,EYE_ANGLE]]){
    const rotation=Matrix.RotationYawPitchRoll(yaw,pitch,0),target=new MorphTarget(name,0,scene),points=new Float32Array(positions.length),directions=normals?new Float32Array(normals.length):null;
    for(let i=0;i<positions.length;i+=3){const p=Vector3.FromArray(positions,i),center=centers[p.x<0?0:1];Vector3.TransformCoordinates(p.subtract(center),rotation).add(center).toArray(points,i);if(directions)Vector3.TransformNormal(Vector3.FromArray(normals,i),rotation).toArray(directions,i);}
    target.setPositions(points);if(directions)target.setNormals(directions);manager.addTarget(target);names.push(name);
  }
  mesh.morphTargetManager=manager;if(!container.morphTargetManagers.includes(manager))container.morphTargetManagers.push(manager);
  return{generatedMorphTargets:names,centers:centers.map(c=>c.asArray()),maximumDegrees:3,gazeMechanism:'Runtime geometric eye targets rotate both verified eye halves by at most 3 degrees. Sparse attention glances; not FACS, nystagmus, or examination evidence.'};
}
/* The clothed body is a reduced mesh whose under-garment vertices were deleted,
   and it is capped at the hip crease -- it has no pelvis or thigh geometry at
   all. Standing, the trouser legs meet and nothing shows. SEATED, the thighs
   rotate up and the inner trouser surfaces separate just enough to see between
   them, and with no body behind the gap the room reads straight through as a
   white spike at the crotch.

   Re-enabling the whole anatomy mesh closes the gap but tears skin through the
   clothes everywhere the garments were fitted against deleted vertices. So we
   keep exactly the triangles that sit in the gap: a small filler deep between
   the legs, skinned by the same skeleton, hidden by the trousers from every
   angle that does not already see through them.

   The window is expressed as fractions of the mesh's own bind-pose bounds so
   each authored body size derives its own, rather than sharing one set of
   hard-coded metres. */
const CROTCH_FILLER = Object.freeze({
  yLow: 0.419, yHigh: 0.519, xHalf: 0.057, zLow: 0.08, zHigh: 0.78,
});

function crotchFillerIndices(mesh) {
  const positions = mesh.getVerticesData('position');
  const indices = mesh.getIndices();
  if (!positions || !indices) return null;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity, minZ = Infinity, maxZ = -Infinity;
  for (let i = 0; i < positions.length; i += 3) {
    const x = positions[i], y = positions[i + 1], z = positions[i + 2];
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (y < minY) minY = y; if (y > maxY) maxY = y;
    if (z < minZ) minZ = z; if (z > maxZ) maxZ = z;
  }
  const height = maxY - minY, width = maxX - minX, depth = maxZ - minZ;
  if (!(height > 0 && width > 0 && depth > 0)) return null;
  const centreX = (minX + maxX) / 2;
  const yLow = minY + CROTCH_FILLER.yLow * height, yHigh = minY + CROTCH_FILLER.yHigh * height;
  const xHalf = CROTCH_FILLER.xHalf * width;
  const zLow = minZ + CROTCH_FILLER.zLow * depth, zHigh = minZ + CROTCH_FILLER.zHigh * depth;
  const kept = [];
  for (let t = 0; t < indices.length; t += 3) {
    let inside = true;
    for (let k = 0; k < 3 && inside; k++) {
      const v = indices[t + k] * 3;
      const x = positions[v], y = positions[v + 1], z = positions[v + 2];
      inside = Math.abs(x - centreX) <= xHalf && y >= yLow && y <= yHigh && z >= zLow && z <= zHigh;
    }
    if (inside) kept.push(indices[t], indices[t + 1], indices[t + 2]);
  }
  return kept.length ? kept : null;
}

export function applyMPFBWardrobe(container, appearance = {}) {
  const anatomy=appearance.outfit==='clinical-anatomy';
  for(const mesh of container.meshes){
    if(mesh.name.startsWith('PCM_Public'))mesh.setEnabled(!anatomy);
    if(mesh.name!=='PCM_AnatomicalBody')continue;
    if(anatomy){
      // The anatomy view needs the whole body back, exactly as authored.
      if(mesh.metadata?.pcmFullIndices)mesh.setIndices(mesh.metadata.pcmFullIndices);
      if(mesh.metadata?.pcmSkinMaterial)mesh.material=mesh.metadata.pcmSkinMaterial;
      mesh.setEnabled(true);
      continue;
    }
    if(!mesh.metadata)mesh.metadata={};
    if(mesh.metadata.pcmFullIndices===undefined){
      mesh.metadata.pcmFullIndices=Array.from(mesh.getIndices()||[]);
      mesh.metadata.pcmCrotchFiller=crotchFillerIndices(mesh);
    }
    if(mesh.metadata.pcmCrotchFiller){
      mesh.setIndices(mesh.metadata.pcmCrotchFiller);
      // Skin tone is wrong for a filler: supine, its pubis edge sits a fraction
      // outside the trousers and reads as bare skin through the denim. Its whole
      // job is to stop the room showing through, so it wears a flat dark tone
      // that reads as the shadow inside the garment.
      if(!mesh.metadata.pcmFillerMaterial&&mesh.material){
        const filler=mesh.material.clone('PCM_Mat_CrotchFiller');
        filler.albedoTexture=null;filler.bumpTexture=null;
        filler.metallicTexture=null;filler.reflectivityTexture=null;
        filler.albedoColor=new Color3(0.055,0.06,0.085);
        filler.roughness=0.95;filler.metallic=0;filler.environmentIntensity=0.35;
        mesh.metadata.pcmSkinMaterial=mesh.material;
        mesh.metadata.pcmFillerMaterial=filler;
      }
      if(mesh.metadata.pcmFillerMaterial)mesh.material=mesh.metadata.pcmFillerMaterial;
      mesh.setEnabled(true);
    }else{
      mesh.setEnabled(false);
    }
  }
}
export function mpfbAppearanceChoices(appearance = {}) {
  return {
    skin: SKIN[Math.max(0,Math.min(2,Math.round(Number(appearance.skinTone)||0)))],
    hair: HAIR[appearance.hairColor] || HAIR.brunette,
    eyes: appearance.eyeColor === 'green' ? 'green' : 'blue',
  };
}
function color(hex) { return Color3.FromHexString(hex).toLinearSpace(); }
function loadTexture(url, scene) {
  return new Promise((resolve,reject) => {
    let timer;
    const texture = new Texture(url,scene,false,false,Texture.TRILINEAR_SAMPLINGMODE,
      () => {clearTimeout(timer);resolve(texture);},
      (message) => {clearTimeout(timer);texture.dispose();reject(new Error(`Eye texture unavailable: ${message || url}`));});
    texture.gammaSpace = true;
    timer = setTimeout(()=>{texture.dispose();reject(new Error('Eye texture did not finish loading.'));},7000);
  });
}
export function createMPFBPatient(scene, options = {}) {
  let eyes = {};
  const bodyBuild=['short-slender','standard','tall-full'].includes(options.bodyBuild)?options.bodyBuild:null;
  const presentation=options.presentation==='male'?'male':'female';
  const assetName=presentation==='male'?'public-male-standard.glb':'public-female-'+(bodyBuild||'standard')+'.glb';
  return createAnimatedPatient(scene, {
    preciseSkinnedPicking:true, label: 'Patient', rootName: 'MPFB public patient', presentation,
    assetUrl: new URL('../assets/'+assetName+'?v=room-clearance-1',import.meta.url).href,
    capabilityMetadata: {model:'mpfb-public-patient',trial:false,bodyBuild:bodyBuild||'original'},
    isEligible: state => state.appearance?.model === 'mpfb-public-patient' && state.appearance?.presentation === presentation,
    controlNames: {blink:['Blink'],speech:['Speech'],concern:['Concern'],discomfort:['Discomfort'],hairSupport:['PCM_HairSupineSupport'],hairProneSupport:['PCM_HairProneSupport']},
    requiredControls:['blink','speech','concern','discomfort'],
    requiredMeshes:['PCM_PublicBody','PCM_AnatomicalBody'],
    supportedPostures:['seated','supine','standing','prone'],requiredPostures:['seated','supine','standing','prone'],
    postureClips:{seated:'PCM_Seated',supine:'PCM_Supine',standing:'PCM_Standing',prone:'PCM_Prone'},postureTransitionMs:600,
    rigNodes:{head:'head',chest:'spine_03',eyeLeft:'no-eye-bone-left',eyeRight:'no-eye-bone-right'},
    landmarkNodes:{face:'Face',chest:'Chest',abdomen:'Abdomen',lap:'Lap',neck:'neck_01'},
    requiredLandmarks:['face','chest','abdomen','lap'],
    readyMessage:'Patient ready.',
    prepareGeometry:(container,scene)=>({...prepareMPFBEyeGeometry(container,scene),...(presentation==='female'?prepareMPFBHairSupport(container,scene,options.bodyBuild):{})}),
    poseControlValues:posture=>({hairSupport:posture==='supine'?1:0,hairProneSupport:posture==='prone'?1:0}),gazeIntent:mpfbGazeIntent,gazeMorphRadians:EYE_ANGLE,
    async prepare(container) {
      const textures = await Promise.allSettled(['blue','green'].map(shade=>loadTexture(new URL(`../assets/mpfb-eyes-${shade}.png`,import.meta.url).href,scene)));
      const failed = textures.find(result=>result.status==='rejected');
      if(failed){for(const item of textures)if(item.status==='fulfilled')item.value.dispose();throw failed.reason;}
      eyes = {blue:textures[0].value,green:textures[1].value};
      return Object.values(eyes);
    },
    applyAppearance(container, appearance) {
      applyMPFBWardrobe(container, appearance);
      const choices = mpfbAppearanceChoices(appearance);
      for(const material of container.materials){
        if(material.name==='PCM_Mat_Skin'){material.albedoColor=color(choices.skin);material.roughness=.57;material.metallic=0;material.environmentIntensity=.78;}
        if(material.name==='PCM_Mat_LongHair'){
          material.albedoColor=color(choices.hair);
          // Depth-sort the visible surface before blending its strand edges.
          // The exported overlapping cards otherwise reveal rear-layer holes at
          // the crown. Geometry, licensed alpha texels and contact stay intact.
          material.needDepthPrePass=true;material.roughness=.66;material.environmentIntensity=.85;material.specularIntensity=.38;material.backFaceCulling=false;
        }
        if(material.name==='PCM_Mat_Eyes'){
          // The authored image changes the iris while retaining white sclera.
          // Tinting the entire material would incorrectly color the whole eye.
          material.albedoColor=Color3.White();material.albedoTexture=eyes[choices.eyes];material.roughness=.19;material.metallic=0;material.environmentIntensity=.9;if(material.clearCoat){material.clearCoat.isEnabled=true;material.clearCoat.intensity=.28;material.clearCoat.roughness=.20;}
        }
      }
    },
    ...options,
  });
}
