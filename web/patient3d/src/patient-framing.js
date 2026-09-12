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

/** Fit the full posed patient inside either a wide or tall bedside pane.
 * Uses actual skinned bounds supplied by the renderer. The padding leaves room
 * for the compact overlay controls; it does not alter user-controlled orbit. */
export function fitPatientFrame(frame,bounds,aspect=1){
 if(!bounds?.min||!bounds?.max||!Number.isFinite(aspect)||aspect<=0)return frame;
 const target=Vector3.Lerp(bounds.min,bounds.max,.5);
 const backward=frame.position.subtract(frame.target).normalize();
 const right=Vector3.Cross(Vector3.Up(),backward).normalize();
 const up=Vector3.Cross(backward,right).normalize();
 const tan=Math.tan(frame.fov/2);
 let distance=Vector3.Distance(frame.position,frame.target);
 for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z]){
  const point=V(x,y,z).subtract(target),depth=Vector3.Dot(point,backward);
  distance=Math.max(distance,depth+Math.abs(Vector3.Dot(point,right))/(tan*aspect*.85),depth+Math.abs(Vector3.Dot(point,up))/(tan*.78));
 }
 return{...frame,target,position:target.add(backward.scale(distance))};
}
