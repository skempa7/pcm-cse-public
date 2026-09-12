import test from 'node:test';
import assert from 'node:assert/strict';
import {NullEngine} from '@babylonjs/core/Engines/nullEngine.js';
import {Scene} from '@babylonjs/core/scene.js';
import {ArcRotateCamera} from '@babylonjs/core/Cameras/arcRotateCamera.js';
import {Vector3,Matrix} from '@babylonjs/core/Maths/math.vector.js';
import {conversationFrame,fitPatientFrame} from '../src/patient-framing.js';
const V=(x,y,z)=>new Vector3(x,y,z);
for(const [width,height]of [[636,812],[390,332],[1200,420],[320,900]])for(const posture of ['seated','standing','supine','prone']){
 test(`Full patient fits ${posture} at ${width}x${height}`,()=>{
  const lying=['supine','prone'].includes(posture),face=lying?V(0,1.25,-.82):V(0,1.88,0),lap=lying?V(0,1.12,-.05):V(0,1.08,.17);
  const bounds=lying?{min:V(-.48,1.01,-1.12),max:V(.48,1.60,1.10)}:{min:V(-.48,.02,-.2),max:V(.48,2,.7)};
  const engine=new NullEngine({renderWidth:width,renderHeight:height}),scene=new Scene(engine);scene.useRightHandedSystem=true;
  const camera=new ArcRotateCamera('Framing test',0,0,3,V(0,0,0),scene),frame=fitPatientFrame(conversationFrame(face,lap,'full',posture),bounds,width/height);
  camera.fov=frame.fov;camera.setTarget(frame.target);camera.setPosition(frame.position);
  const transform=camera.getViewMatrix(true).multiply(camera.getProjectionMatrix(true)),viewport=camera.viewport.toGlobal(width,height);
  for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z]){
   const p=Vector3.Project(V(x,y,z),Matrix.Identity(),transform,viewport);
   assert.ok(p.x>=width*.074&&p.x<=width*.926,`Horizontal crop: ${p.x}`);
   assert.ok(p.y>=height*.109&&p.y<=height*.891,`Vertical crop: ${p.y}`);
  }
  scene.dispose();engine.dispose();
 });
}
