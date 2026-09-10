/** Conversation composition is anchored to each exported body, never patient
 * demographics. Face preserves a comfortable physical distance while narrowing
 * the lens; Upper body retains posture and hands. Full patient remains the
 * examination overview. All presets are identical for current/previous assets. */
import {Vector3} from '@babylonjs/core/Maths/math.vector.js';
const V=(x,y,z)=>new Vector3(x,y,z);
export function conversationFrame(face,lap,preset,posture){
 const lyingDown=posture===true||posture==='supine'||posture==='prone';
 if(posture==='prone'&&preset==='face'){
  const target=face.clone();return{target,position:target.add(V(-1.0,.23,.08)),fov:.56};
 }
 if(lyingDown){
  const target=preset==='face'?face.add(V(0,0,.05)):Vector3.Lerp(face,lap,preset==='full'?.65:.42);
  return {target,position:target.add(preset==='face'?V(.07,.64,.20):preset==='full'?V(1.55,1.80,.64):V(.75,1.18,.48)),fov:preset==='face'?.56:preset==='full'?.77:.65};
 }
 const target=preset==='face'?face.add(V(0,-.065,0)):preset==='full'?Vector3.Lerp(face,lap,.95).add(V(0,.04,.05)):Vector3.Lerp(face,lap,.43);
 return {target,position:target.add(preset==='face'?V(.06,0,.62):preset==='full'?V(.24,.13,2.90):V(.12,.06,1.60)),fov:preset==='face'?.56:preset==='full'?.77:.65};
}

/** Follow the animated landmarks directly while easing the camera's offset.
 * Smoothing a target that is itself moving causes the face to leave the frame. */
export function transitionConversationFrame(from,to,progress){
 const u=Math.min(1,Math.max(0,progress)),e=u*u*(3-2*u);
 const target=Vector3.Lerp(from.target,to.target,e);
 const offset=Vector3.Lerp(from.position.subtract(from.target),to.position.subtract(to.target),e);
 return {target,position:target.add(offset),fov:from.fov+(to.fov-from.fov)*e};
}
