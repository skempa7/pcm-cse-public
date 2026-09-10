import {Vector3,Quaternion} from '@babylonjs/core/Maths/math.vector.js';
const clamp=x=>Math.max(0,Math.min(1,Number(x)||0));
const smooth=x=>{x=clamp(x);return x*x*(3-2*x)};
/** All inputs are already disclosed acting cues. No gesture creates evidence. */
export function gestureIntent(state={},now=0){
 const cue=state.gesture||{},region=cue.region||state.affect?.guardRegion||'none';
 if(state.phase!=='encounter'||state.reducedMotion||region==='none'||Number(state.busyMs)>0)return{kind:'rest',weight:0,region};
 const t=Math.max(0,now-(state.gestureStartedAt||0))/1000,offset={abdomen:0,chest:2.7,head:4.1,flank:1.8,back:1.8,shoulder:3.3,knee:1.1}[region]||0;
 // Infrequent 7-second gestures followed by a long quiet interval. Talking about
 // the location provides a separate short gesture; absence of pain stays neutral.
 const cycle=t%22,periodic=smooth(cycle/1.8)*(1-smooth((cycle-5.2)/2.0));
 const symptomatic=Number(state.affect?.discomfort)>0;
 const explaining=(state.speaking===true||now<(state.gestureReplyUntil||0))&&cue.disclosed===true;
 const weight=(symptomatic?periodic:explaining?periodic:0)*.94;
 const prone=state.posture==='prone';
 return{region,weight,kind:prone?'prone-comfort':region==='head'?'temple-touch':region==='abdomen'?'abdominal-soothing':region==='chest'?'chest-indication':region==='back'||region==='flank'?'flank-support':region==='shoulder'?'shoulder-indication':region==='knee'?'knee-indication':'rest',rub:symptomatic&&region==='abdomen'?Math.sin(t*1.5)*.012:0,expression:weight*(symptomatic?.18:0)};
}
function world(n){n.computeWorldMatrix(true);return n.getAbsolutePosition().clone()}
function worldQ(n){const q=Quaternion.Identity();n.computeWorldMatrix(true).decompose(undefined,q);return q}
function rotateWorld(n,delta){const parent=n.parent?worldQ(n.parent):Quaternion.Identity();n.rotationQuaternion=Quaternion.Inverse(parent).multiply(delta).multiply(parent).multiply(n.rotationQuaternion||Quaternion.FromEulerVector(n.rotation));n.computeWorldMatrix(true)}
function align(n,from,to){if(from.lengthSquared()<1e-10||to.lengthSquared()<1e-10)return;const q=Quaternion.Identity();Quaternion.FromUnitVectorsToRef(from.normalize(),to.normalize(),q);rotateWorld(n,q)}
export function createPatientGestures(container){
 const nodes=[...container.transformNodes,...container.meshes],get=name=>nodes.find(n=>n.name===name);
 const R={upper:get('upperarm_r'),lower:get('lowerarm_r'),hand:get('hand_r'),middle:get('middle_01_r'),index:get('index_01_r'),pinky:get('pinky_01_r')};
 const L={upper:get('upperarm_l'),lower:get('lowerarm_l'),hand:get('hand_l'),middle:get('middle_01_l'),index:get('index_01_l'),pinky:get('pinky_01_l')};
 const neck=get('neck_01'),lap=get('Lap'),abdomen=get('Abdomen'),chest=get('Chest'),head=get('head');
 if(!R.upper||!R.lower||!R.hand||!L.upper||!neck||!lap||!abdomen||!chest)return{capture(){},restore(){},animate(){return{available:false}}};
 const moving=[R.upper,R.lower,R.hand,L.upper,L.lower,L.hand,...nodes.filter(n=>/^(index|middle|ring|pinky|thumb)_0[123]_[rl]$/.test(n.name))];let rest=[],blend=0,lastTime=0,surfaceCache=null;
 function capture(){blend=0;surfaceCache=null;rest=moving.map(n=>({n,q:(n.rotationQuaternion||Quaternion.FromEulerVector(n.rotation)).clone()}))}
 function restore(){for(const e of rest)e.n.rotationQuaternion=e.q.clone()}
 function animate(state,now){
  restore();const intent=gestureIntent(state,now),dt=Math.min(.1,Math.max(0,(now-(lastTime||now))/1000));lastTime=now;blend=state.reducedMotion?0:blend+(intent.weight-blend)*(1-Math.exp(-dt*7));const a=blend;intent.weight=a;if(a<.001)return{...intent,available:true};
  const r=intent.region==='shoulder'?(state.gesture?.side==='left'?R:L):(state.gesture?.side==='left'?L:R);const up=world(neck).subtract(world(lap)).normalize(),globalRight=world(R.upper).subtract(world(L.upper)).normalize(),right=globalRight.scale(r===L?-1:1),front=Vector3.Cross(up,globalRight).normalize();
  // A prone patient's anterior torso is supported by the table: no hand is
  // driven through it. Keep the supported arm pose and make a small hand release.
  if(state.posture==='prone'&&!['back','flank'].includes(intent.region)){
   const e=rest.find(e=>e.n===r.hand);r.hand.rotationQuaternion=e.q.multiply(Quaternion.FromEulerAngles(.04*a,0,.025*a));
   return{...intent,available:true,adaptation:'supported arm; restrained hand movement, no anterior reach'};
  }
  let target,normal=front,dir=right.scale(-1).add(up.scale(-.12)).normalize();
  if(intent.region==='head'){target=world(head).add(up.scale(.015)).add(right.scale(.082)).add(front.scale(.13));dir=up;normal=right;}
  else if(intent.region==='chest'){target=world(chest).add(up.scale(-.045)).add(front.scale(.19)).add(right.scale(.075));}
  else if(intent.region==='back'||intent.region==='flank'){
   target=world(abdomen).add(right.scale(.19)).add(up.scale(-.04)).add(front.scale(state.posture==='supine'?.07:-.075));dir=up.scale(-1);normal=right;
  }else if(intent.region==='shoulder'){target=world((r===R?L:R).upper).add(front.scale(.09));dir=right.scale(-1);}
  else if(intent.region==='knee'){
   // A standing knee cannot be reached without an authored full-body bend.
   if(state.posture==='standing')return{...intent,weight:0,available:true,adaptation:'standing knee reach omitted'};
   const knee=get(r===L?'calf_l':'calf_r');target=world(knee).add(front.scale(.09)).add(up.scale(.06));dir=up.scale(-1);
  }else{target=world(abdomen).add(up.scale(.025+intent.rub)).add(front.scale(.145)).add(right.scale(.062));}
  if(['abdomen','chest'].includes(intent.region)){
   const identity=[state.posture,state.appearance?.outfit].join(':');
   if(surfaceCache?.identity!==identity){
    const naked=['unclothed','clinical-anatomy'].includes(state.appearance?.outfit);
    const mesh=container.meshes.find(m=>naked?['PCM_FemaleBody','PCM_AnatomicalBody'].includes(m.name):['PCM_FittedKnit','PCM_PublicKnit'].includes(m.name));
    const values=mesh?.getPositionData(true,true),points=[];
    if(values){const matrix=mesh.computeWorldMatrix(true);for(let i=0;i<values.length;i+=3)points.push(Vector3.TransformCoordinates(Vector3.FromArray(values,i),matrix));}
    surfaceCache={identity,points};
   }
   let best=null,score=Infinity;
   for(const p of surfaceCache.points){const d=p.subtract(target),across=Vector3.Dot(d,right),along=Vector3.Dot(d,up),depth=Vector3.Dot(d,front);const cost=across*across+along*along+.08*depth*depth;
    if(Math.abs(across)<.035&&Math.abs(along)<.035&&depth>-.13&&depth<.28&&cost<score){score=cost;best=p;}}
   if(best)target=target.add(front.scale(Vector3.Dot(best.subtract(target),front)+.018));
  }
  const S=world(r.upper),E=world(r.lower),W=world(r.hand),l1=Vector3.Distance(S,E),l2=Vector3.Distance(E,W);
  let T=Vector3.Lerp(W,target,a).add(front.scale(Math.sin(a*Math.PI)*(state.posture==='prone'?-.075:.075)));let d=T.subtract(S),distance=d.length();const max=l1+l2-.009,min=Math.abs(l1-l2)+.012;distance=Math.max(min,Math.min(max,distance));d.normalize();T=S.add(d.scale(distance));
  const pole=right.scale(.85).add(front.scale(state.posture==='prone'?-.35:.28)).subtract(up.scale(.2));let perpendicular=pole.subtract(d.scale(Vector3.Dot(pole,d))).normalize();
  const along=(l1*l1-l2*l2+distance*distance)/(2*distance),height=Math.sqrt(Math.max(.00001,l1*l1-along*along));const elbow=S.add(d.scale(along)).add(perpendicular.scale(height));
  align(r.upper,E.subtract(S),elbow.subtract(S));const e2=world(r.lower),w2=world(r.hand);align(r.lower,w2.subtract(e2),T.subtract(e2));
  if(r.middle&&r.index&&r.pinky){
   const wrist=world(r.hand),long=world(r.middle).subtract(wrist);const desired=Vector3.Lerp(long.normalize(),dir,a).normalize();align(r.hand,long,desired);
   const palm=Vector3.Cross(world(r.index).subtract(world(r.hand)),world(r.pinky).subtract(world(r.hand))).normalize();
   // Rotate only around the finger axis to put the palm toward the torso.
   const axis=world(r.middle).subtract(world(r.hand)).normalize(),want=normal.scale(-1);let pa=palm.subtract(axis.scale(Vector3.Dot(palm,axis))).normalize(),pb=want.subtract(axis.scale(Vector3.Dot(want,axis))).normalize();const angle=Math.atan2(Vector3.Dot(axis,Vector3.Cross(pa,pb)),Vector3.Dot(pa,pb));rotateWorld(r.hand,Quaternion.RotationAxis(axis,angle*a));
  }
  const side=r===L?'l':'r';const fingerAxis=world(r.middle).subtract(world(r.hand)).normalize();
  for(const finger of ['index','middle','ring','pinky']){
   const proximal=get(finger+'_01_'+side),middle=get(finger+'_02_'+side),tip=get(finger+'_03_'+side);if(!proximal||!middle||!tip)continue;
   const curl=(intent.region==='chest'?.30:intent.region==='head'?.06:.14)*a;
   let v=world(middle).subtract(world(proximal));align(proximal,v,v.normalize().scale(.55).add(fingerAxis.scale(.45)).subtract(normal.scale(curl)));
   v=world(tip).subtract(world(middle));align(middle,v,v.normalize().subtract(normal.scale(curl)));
  }
  return{...intent,available:true,wrist:world(r.hand).asArray(),target:T.asArray(),wristError:Vector3.Distance(world(r.hand),T)};
 }
 capture();return{capture,restore,animate};
}
