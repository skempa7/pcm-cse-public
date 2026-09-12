import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,readdir} from 'node:fs/promises';
import {NullEngine} from '@babylonjs/core/Engines/nullEngine.js';
import {Scene} from '@babylonjs/core/scene.js';
import {SceneLoader,LoadAssetContainerAsync} from '@babylonjs/core/Loading/sceneLoader.js';
import {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial.js';
import {Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {createMPFBPatient,applyMPFBWardrobe} from '../src/mpfb-patient.js';
import {conversationFrame} from '../src/patient-framing.js';
const files=(await readdir(new URL('../assets/',import.meta.url))).filter(n=>/^(?:public-(?:female-(?:standard|short-slender|tall-full)|male-standard)|mpfb-female-(?:patient|standard|short-slender|tall-full))\.glb$/.test(n));
for(const file of files)test(`${file}: actual four poses and transitions preserve skinned patient`,async()=>{
 const isPublic=file.startsWith('public-'),male=file.includes('male-standard')&&!file.includes('female'),build=['short-slender','tall-full','standard'].find(x=>file.includes(x))||null;
 const engine=new NullEngine(),scene=new Scene(engine);scene.useRightHandedSystem=true;
 let asset;const original=SceneLoader.LoadAssetContainerAsync;
 SceneLoader.LoadAssetContainerAsync=async()=>{asset=await LoadAssetContainerAsync(new Uint8Array(await readFile(new URL('../assets/'+file,import.meta.url))),scene,{pluginExtension:'.glb',pluginOptions:{gltf:{skipMaterials:true}}});const m=new StandardMaterial('Test',scene);for(const mesh of asset.meshes)mesh.material=m;return asset;};
 const c=createMPFBPatient(scene,{bodyBuild:build,presentation:male?'male':'female',prepare:async()=>[],prepareGeometry:()=>({}),applyAppearance:applyMPFBWardrobe});
 try{
  assert.equal(await c.ready,true);assert.deepEqual(c.capabilities.supportedPostures,['seated','supine','standing','prone']);c.setEnabled(true);
  const state={phase:'encounter',sessionId:'geometry',appearance:{model:isPublic?'mpfb-public-patient':'mpfb-young-woman',presentation:male?'male':'female',bodyBuild:build,outfit:isPublic?'clinical-anatomy':'unclothed'}};
  for(const posture of ['seated','supine','standing','prone']){
   c.update({...state,posture,reducedMotion:true});c.animate(performance.now());
   for(const node of [...asset.transformNodes,...asset.meshes])node.computeWorldMatrix?.(true);for(const rig of asset.skeletons)rig.prepare(true);
   assert.equal(c.visible,true);assert.equal(c.postureSupported,true);const marks=c.anchors;
   for(const name of ['face','chest','abdomen','lap'])assert.ok(marks[name].asArray().every(Number.isFinite));
   const body=asset.meshes.find(m=>m.name===(isPublic?'PCM_AnatomicalBody':'PCM_FemaleBody')),pos=body.getPositionData(true,true),points=[];
   for(let i=0;i<pos.length;i+=3)points.push(Vector3.TransformCoordinates(Vector3.FromArray(pos,i),body.getWorldMatrix()));
   const minY=Math.min(...points.map(p=>p.y)),maxY=Math.max(...points.map(p=>p.y));
   if(posture==='standing'){assert.ok(minY>=-.005&&minY<.02,`feet floor ${minY}`);assert.ok(maxY>1.55&&maxY<1.85);assert.ok(Math.abs(marks.chest.x)>.6,'beside the table');}
   if(posture==='prone'){assert.ok(minY>.97&&maxY<1.65,`prone body bounds ${minY}..${maxY}`);assert.ok(Math.abs(marks.face.z-marks.lap.z)>.45);}
   for(const preset of ['face','patient','full']){const frame=conversationFrame(marks.face,marks.lap,preset,posture);assert.ok(frame.position.asArray().every(Number.isFinite));assert.ok(Vector3.Distance(frame.position,frame.target)>=.6);}
   if(isPublic){
    const anatomical=asset.meshes.find(m=>m.name==='PCM_AnatomicalBody');
    const covered=asset.meshes.filter(m=>m.name.startsWith('PCM_Public'));
    const fullIndices=Array.from(anatomical.getIndices()),skinMaterial=anatomical.material;
    assert.ok(covered.length>=4,'Covered body and complete outfit are present');
    c.update({...state,posture,reducedMotion:true,appearance:{...state.appearance,outfit:'fitted-casual'}});c.animate(performance.now());
    // 2026-09-12: the female covered outfit intentionally uses a small,
    // dark pelvic subset to close a gap in the trousers. Check the actual
    // coverage contract and lossless anatomy restoration instead of treating
    // the intentional filler as a fully exposed anatomical body.
    if(male)assert.equal(anatomical.isEnabled(),false,`${posture}: male anatomy hidden beneath trousers`);
    else{
     const filler=Array.from(anatomical.getIndices());
     assert.equal(anatomical.isEnabled(),true,`${posture}: female trouser gap stays filled`);
     assert.ok(filler.length>0&&filler.length<fullIndices.length*.05,'Only a small body subset fills the garment gap');
     const available=new Set(fullIndices);assert.ok(filler.every(index=>available.has(index)),'Filler uses authored vertices');
     assert.notEqual(anatomical.material,skinMaterial,'Clothed filler must not use visible skin');
     assert.equal(anatomical.material.albedoTexture,null,'Skin texture is not exposed beneath clothing');
     assert.ok(anatomical.material.albedoColor.asArray().every(value=>value<.1),'Filler reads as a garment shadow');
    }
    assert.ok(covered.every(m=>m.isEnabled()),`${posture}: covered body and clothes remain visible`);
    c.update({...state,posture,reducedMotion:true});c.animate(performance.now());
    assert.equal(anatomical.isEnabled(),true,`${posture}: anatomical view restored`);
    assert.deepEqual(Array.from(anatomical.getIndices()),fullIndices,'Anatomy toggle restores every authored triangle');
    assert.equal(anatomical.material,skinMaterial,'Anatomy toggle restores the original skin material');
    assert.ok(covered.every(m=>!m.isEnabled()),`${posture}: clothes hidden in anatomical view`);
   }
  }
  for(const from of ['seated','supine','standing','prone'])for(const to of ['seated','supine','standing','prone'])if(from!==to){
   c.update({...state,posture:from,reducedMotion:true});c.animate(performance.now()+1000);
   c.update({...state,posture:to,reducedMotion:false});c.animate(performance.now()+1000);assert.equal(c.visible,true);assert.equal(c.transition,null);
  }
 }finally{SceneLoader.LoadAssetContainerAsync=original;c.dispose();scene.dispose();engine.dispose();}
});
