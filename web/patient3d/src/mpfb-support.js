import {Matrix,Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {MorphTarget} from '@babylonjs/core/Morph/morphTarget.js';
import {MorphTargetManager} from '@babylonjs/core/Morph/morphTargetManager.js';
import {VertexData} from '@babylonjs/core/Meshes/mesh.vertexData.js';
import {patientSupportHeight} from './clinical-table.js';

/** Rest-space correction derived from the actual exported skin matrices. The
 * supine hair rests on the cushion instead of penetrating it. This is an
 * authored support correction, not hair physics or a patient finding. */
export function prepareMPFBHairSupport(container,scene,bodyBuild){
 const mesh=container.meshes.find(m=>m.name==='PCM_LongHair');
 const supine=container.animationGroups.find(g=>g.name==='PCM_Supine'),seated=container.animationGroups.find(g=>g.name==='PCM_Seated');
 if(!mesh?.skeleton||!supine||!seated||mesh.morphTargetManager)return{hairSupportUnavailable:'Expected unmodified hair rig and both authored poses are required.'};
 for(const group of container.animationGroups)group.stop();supine.start(false);supine.goToFrame(supine.from);supine.pause();
 for(const node of [...container.transformNodes,...container.meshes])node.computeWorldMatrix?.(true);
 mesh.skeleton.prepare(true);const matrices=mesh.skeleton.getTransformMatrices(mesh),world=mesh.computeWorldMatrix(true),inverseWorld=world.clone().invert();
 const positions=mesh.getVerticesData('position'),weights=mesh.getVerticesData('matricesWeights'),indices=mesh.getVerticesData('matricesIndices');
 const output=new Float32Array(positions),blended=Matrix.Zero();let changed=0,maximumLift=0;
 for(let i=0;i<positions.length/3;i++){
  const values=new Array(16).fill(0);
  for(let j=0;j<4;j++){const w=weights[i*4+j];if(!w)continue;const offset=Math.round(indices[i*4+j])*16;for(let k=0;k<16;k++)values[k]+=matrices[offset+k]*w;}
  Matrix.FromArrayToRef(values,0,blended);
  const rest=Vector3.FromArray(positions,i*3),posed=Vector3.TransformCoordinates(rest,blended),p=Vector3.TransformCoordinates(posed,world);
  const support=patientSupportHeight(p.x,p.z,{posture:'supine',bodyBuild});
  if(support===null||p.y>=support+.0014)continue;
  const lift=support+.0014-p.y;
  // A changed export needs review rather than an arbitrary large deformation.
  if(lift>.13)throw new Error('Hair support exceeds the reviewed 13 cm correction bound.');
  p.y+=lift;Vector3.TransformCoordinates(Vector3.TransformCoordinates(p,inverseWorld),blended.clone().invert()).toArray(output,i*3);
  changed++;maximumLift=Math.max(maximumLift,lift);
 }
 const normals=new Float32Array(output.length);VertexData.ComputeNormals(output,mesh.getIndices(),normals,{useRightHandedSystem:scene.useRightHandedSystem});
 const target=new MorphTarget('PCM_HairSupineSupport',0,scene);target.setPositions(output);target.setNormals(normals);
 const manager=new MorphTargetManager(scene);manager.addTarget(target);manager.numMaxInfluencers=1;mesh.morphTargetManager=manager;container.morphTargetManagers.push(manager);
 supine.stop();seated.start(false);seated.goToFrame(seated.from);seated.pause();
 for(const node of [...container.transformNodes,...container.meshes])node.computeWorldMatrix?.(true);
 mesh.skeleton.prepare(true);
 return{hairSupport:{target:'PCM_HairSupineSupport',changedVertices:changed,maximumLiftM:maximumLift,method:'Pose-specific rest-space morph derived from actual skin matrices and measured table/pillow support. No clinical evidence or dynamic hair-physics claim.'}};
}
