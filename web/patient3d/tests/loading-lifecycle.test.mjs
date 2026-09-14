import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {NullEngine} from '@babylonjs/core/Engines/nullEngine.js';
import {Scene} from '@babylonjs/core/scene.js';
import {SceneLoader,LoadAssetContainerAsync} from '@babylonjs/core/Loading/sceneLoader.js';
import {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial.js';
import {createMPFBPatient} from '../src/mpfb-patient.js';

test('disposing during texture preparation cleans late resources without adding a stale patient',async()=>{
 const engine=new NullEngine(),scene=new Scene(engine);scene.useRightHandedSystem=true;
 const original=SceneLoader.LoadAssetContainerAsync;let prepared,release,count=0;
 const began=new Promise(resolve=>prepared=resolve),pending=new Promise(resolve=>release=resolve);
 SceneLoader.LoadAssetContainerAsync=async()=>{
  const container=await LoadAssetContainerAsync(new Uint8Array(await readFile(new URL('../assets/public-female-standard.glb',import.meta.url))),scene,{pluginExtension:'.glb',pluginOptions:{gltf:{skipMaterials:true}}});
  const material=new StandardMaterial('Test',scene);for(const mesh of container.meshes)mesh.material=material;return container;
 };
 const patient=createMPFBPatient(scene,{prepareGeometry:()=>({}),prepare:async()=>{prepared();await pending;return[{dispose(){count++;}}];}});
 try{
  await began;patient.dispose();release();assert.equal(await patient.ready,false);
  assert.equal(count,1,'resource that completed after disposal must itself be disposed');
  assert.equal(patient.loaded,false);assert.equal(scene.meshes.some(m=>/^PCM_/.test(m.name)),false);
  assert.equal(scene.transformNodes.some(n=>n.name==='MPFB public patient'),false);
 }finally{SceneLoader.LoadAssetContainerAsync=original;patient.dispose();scene.dispose();engine.dispose();}
});
