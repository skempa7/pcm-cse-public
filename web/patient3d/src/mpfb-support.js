import {Matrix,Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {MorphTarget} from '@babylonjs/core/Morph/morphTarget.js';
import {MorphTargetManager} from '@babylonjs/core/Morph/morphTargetManager.js';
import {VertexData} from '@babylonjs/core/Meshes/mesh.vertexData.js';
import {patientSupportHeight} from './clinical-table.js';

/** Each lying pose receives its own rest-space hair correction, derived from
 * that exported pose's actual skin matrices and its measured support surface.
 * These restrained contact controls are not dynamic hair physics or findings. */
export function prepareMPFBHairSupport(container,scene,bodyBuild){
 const mesh=container.meshes.find(m=>m.name==='PCM_LongHair');
 const seated=container.animationGroups.find(g=>g.name==='PCM_Seated');
 const poses=[['supine','PCM_Supine','PCM_HairSupineSupport'],['prone','PCM_Prone','PCM_HairProneSupport']];
 if(!mesh?.skeleton||!seated||mesh.morphTargetManager||poses.some(([,clip])=>!container.animationGroups.some(g=>g.name===clip)))return{hairSupportUnavailable:'The unmodified hair rig and all three table postures are required.'};
 const positions=mesh.getVerticesData('position'),weights=mesh.getVerticesData('matricesWeights'),indices=mesh.getVerticesData('matricesIndices');
 const manager=new MorphTargetManager(scene),reports={};
 for(const [posture,clip,name] of poses){
  for(const group of container.animationGroups)group.stop();
  const group=container.animationGroups.find(g=>g.name===clip);group.start(false);group.goToFrame(group.from);group.pause();
  for(const node of [...container.transformNodes,...container.meshes])node.computeWorldMatrix?.(true);
  mesh.skeleton.prepare(true);const matrices=mesh.skeleton.getTransformMatrices(mesh),world=mesh.computeWorldMatrix(true),inverseWorld=world.clone().invert();
  const output=new Float32Array(positions),blended=Matrix.Zero();let changed=0,maximumLift=0;
  for(let i=0;i<positions.length/3;i++){
   const values=new Array(16).fill(0);
   for(let j=0;j<4;j++){const w=weights[i*4+j];if(!w)continue;const offset=Math.round(indices[i*4+j])*16;for(let k=0;k<16;k++)values[k]+=matrices[offset+k]*w;}
   Matrix.FromArrayToRef(values,0,blended);
   const rest=Vector3.FromArray(positions,i*3),posed=Vector3.TransformCoordinates(rest,blended),p=Vector3.TransformCoordinates(posed,world);
   const support=patientSupportHeight(p.x,p.z,{posture,bodyBuild});
   if(support===null||p.y>=support+.0014)continue;
   const lift=support+.0014-p.y;
   if(lift>.13)throw new Error(`${posture} hair support exceeds the reviewed 13 cm correction bound.`);
   p.y+=lift;Vector3.TransformCoordinates(Vector3.TransformCoordinates(p,inverseWorld),blended.clone().invert()).toArray(output,i*3);
   changed++;maximumLift=Math.max(maximumLift,lift);
  }
  const normals=new Float32Array(output.length);VertexData.ComputeNormals(output,mesh.getIndices(),normals,{useRightHandedSystem:scene.useRightHandedSystem});
  const target=new MorphTarget(name,0,scene);target.setPositions(output);target.setNormals(normals);manager.addTarget(target);
  reports[posture]={target:name,changedVertices:changed,maximumLiftM:maximumLift,method:'Separate pose-specific rest-space morph derived from actual skin matrices and measured table/pillow support. No clinical evidence or hair-physics claim.'};
 }
 manager.numMaxInfluencers=2;mesh.morphTargetManager=manager;container.morphTargetManagers.push(manager);
 for(const group of container.animationGroups)group.stop();seated.start(false);seated.goToFrame(seated.from);seated.pause();
 for(const node of [...container.transformNodes,...container.meshes])node.computeWorldMatrix?.(true);mesh.skeleton.prepare(true);
 return{hairSupport:reports.supine,hairProneSupport:reports.prone};
}
