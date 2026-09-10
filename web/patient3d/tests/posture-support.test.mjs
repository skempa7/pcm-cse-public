import {readFile,writeFile,readdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {NullEngine} from '@babylonjs/core/Engines/nullEngine.js';
import {Scene} from '@babylonjs/core/scene.js';
import {SceneLoader,LoadAssetContainerAsync} from '@babylonjs/core/Loading/sceneLoader.js';
import {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial.js';
import {Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {Ray,RegisterRay} from '@babylonjs/core/Culling/ray.pure.js';
import '@babylonjs/loaders/glTF/index.js';
import {createClinicalTable,patientSupportHeight} from '../src/clinical-table.js';
import {prepareMPFBHairSupport} from '../src/mpfb-support.js';
RegisterRay();
const source=new URL('../assets/',import.meta.url),reports=[];
const files=(await readdir(source)).filter(n=>/^(?:public-(?:female-(?:standard|short-slender|tall-full)|male-standard)|mpfb-female-(?:patient|standard|short-slender|tall-full))\.glb$/.test(n));
const td=new Uint8Array(await readFile(new URL('clinical-exam-table.glb',source))); 
for(const file of files){
 const build=file.includes('male-standard')&&!file.includes('female')?'male':file.includes('short-slender')?'short-slender':file.includes('tall-full')?'tall-full':file.includes('standard')?'standard':'base';
 const engine=new NullEngine(),scene=new Scene(engine);scene.useRightHandedSystem=true;
 const male=build==='male',isPublic=file.startsWith('public-');
 const asset=await LoadAssetContainerAsync(new Uint8Array(await readFile(new URL(file,source))),scene,{pluginExtension:'.glb',pluginOptions:{gltf:{skipMaterials:true}}});asset.addAllToScene();
 const material=new StandardMaterial('verification',scene);for(const m of asset.meshes)m.material=material;
 const supports=!male?prepareMPFBHairSupport(asset,scene,build):null;
 const original=SceneLoader.ImportMeshAsync;let tableAsset;
 SceneLoader.ImportMeshAsync=async()=>{tableAsset=await LoadAssetContainerAsync(td,scene,{pluginExtension:'.glb',pluginOptions:{gltf:{skipMaterials:true}}});tableAsset.addAllToScene();return{meshes:tableAsset.meshes};};
 const table=await createClinicalTable(scene);SceneLoader.ImportMeshAsync=original;
 const report={build,supports,positions:{}};
 function update(posture){
  for(const g of asset.animationGroups)g.stop();let g=asset.animationGroups.find(g=>g.name==='PCM_'+posture[0].toUpperCase()+posture.slice(1));g.start(false);g.goToFrame(g.from);g.pause();
  const hair=asset.meshes.find(m=>m.name==='PCM_LongHair');if(hair)for(let i=0;i<hair.morphTargetManager.numTargets;i++)hair.morphTargetManager.getTarget(i).influence=hair.morphTargetManager.getTarget(i).name===(posture==='supine'?'PCM_HairSupineSupport':posture==='prone'?'PCM_HairProneSupport':'none')?1:0;
  table.update({posture,reducedMotion:true,phase:'encounter',appearance:{bodyBuild:male?'standard':build,presentation:male?'male':'female',outfit:'unclothed'}});
  for(const n of [...asset.transformNodes,...asset.meshes,...tableAsset.transformNodes,...tableAsset.meshes])n.computeWorldMatrix?.(true);for(const sk of asset.skeletons)sk.prepare(true);
 }
 function points(mesh){const ps=mesh.getPositionData(true,true),w=mesh.computeWorldMatrix(true),out=[];for(let i=0;i<ps.length;i+=3)out.push(Vector3.TransformCoordinates(Vector3.FromArray(ps,i),w));return out;}
 for(const posture of ['standing','prone','supine','seated','prone']){
  update(posture);const body=asset.meshes.find(m=>m.name===(isPublic?'PCM_AnatomicalBody':'PCM_FemaleBody')),ps=points(body);
  const entry={floorMin:Math.min(...ps.map(p=>p.y)),bounds:{min:[0,1,2].map(i=>Math.min(...ps.map(p=>p.asArray()[i]))),max:[0,1,2].map(i=>Math.max(...ps.map(p=>p.asArray()[i])))} };
  if(posture==='prone'){
   entry.regions={};
   for(const [name,a,b] of [['head',-1.05,-.79],['thorax',-.64,-.38],['abdomen',-.38,-.16],['pelvis',-.16,.04],['thighs',.04,.28],['knees',.28,.40],['calves',.40,.62],['feet',.62,.91]]){
    const zone=ps.filter(p=>p.z>=a&&p.z<=b&&Math.abs(p.x)<.24);if(!zone.length)continue;const p=zone.reduce((a,b)=>a.y<b.y?a:b);
    const hit=scene.pickWithRay(new Ray(p.add(new Vector3(0,.2,0)),new Vector3(0,-1,0),.5),m=>tableAsset.meshes.includes(m)&&m.isEnabled());
    entry.regions[name]={body:p.asArray(),support:hit?.hit?hit.pickedPoint.asArray():null,gap:hit?.hit?p.y-hit.pickedPoint.y:null};
   }
   let minGap=Infinity;for(const p of ps){const s=patientSupportHeight(p.x,p.z,{posture,bodyBuild:build,presentation:male?'male':'female'});if(s!==null)minGap=Math.min(minGap,p.y-s);}
   entry.minimumBodyClearance=minGap;assert.ok(minGap>=-.001,'Actual prone body stays above its support');for(const region of Object.values(entry.regions)){assert.ok(region.gap!==null&&region.gap>=-.004&&region.gap<=.022,'Each anatomical region has a nearby support surface');}
   entry.clothing={};table.update({posture,reducedMotion:true,phase:'encounter',appearance:{bodyBuild:male?'standard':build,presentation:male?'male':'female',outfit:'fitted-casual'}});for(const mesh of asset.meshes.filter(m=>/FittedKnit|FittedCasual|Sneakers|PublicKnit|PublicTrousers|PublicShoes/.test(m.name))){let gap=Infinity;for(const p of points(mesh)){const support=patientSupportHeight(p.x,p.z,{posture,bodyBuild:build,presentation:male?'male':'female',outfit:'fitted-casual'});if(support!==null)gap=Math.min(gap,p.y-support);}entry.clothing[mesh.name]=gap;assert.ok(gap>=-.002,'Clothing clears prone support');}
   const hair=asset.meshes.find(m=>m.name==='PCM_LongHair');if(hair){let h=Infinity;for(const p of points(hair)){const s=patientSupportHeight(p.x,p.z,{posture,bodyBuild:build});if(s!==null)h=Math.min(h,p.y-s);}entry.minimumHairClearance=h;assert.ok(h>.001,'Hair support has actual post-skin clearance');}
  }
  report.positions[posture]=entry;
 }
 reports.push(report);console.log(build,JSON.stringify(report.positions.prone));table.dispose();asset.dispose();scene.dispose();engine.dispose();
}
if(process.env.PCM_POSTURE_REPORT)await writeFile(process.env.PCM_POSTURE_REPORT,JSON.stringify(reports,null,2)+'\n');
