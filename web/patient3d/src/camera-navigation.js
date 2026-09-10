// Deliberate orbit only. Wheel, touch/pinch and keyboard remain browser-owned.
const clamp=(v,a,b)=>Math.min(b,Math.max(a,v));
export function orbitDirection(alpha,beta){return{x:Math.cos(alpha)*Math.sin(beta),y:Math.cos(beta),z:Math.sin(alpha)*Math.sin(beta)};}
/** Forward ray interval through an expanded world-space box. */
export function rayBoxInterval(origin,direction,box,padding=0){
 let enter=-Infinity,exit=Infinity;
 for(const axis of ['x','y','z']){const lo=box.min[axis]-padding,hi=box.max[axis]+padding,d=direction[axis],o=origin[axis];if(Math.abs(d)<1e-9){if(o<lo||o>hi)return null;continue;}let a=(lo-o)/d,b=(hi-o)/d;if(a>b)[a,b]=[b,a];enter=Math.max(enter,a);exit=Math.min(exit,b);if(enter>exit)return null;}
 return exit<0?null:[Math.max(0,enter),exit];
}
/** Find a clear camera location on an orbit ray, without passing room walls.
 * The boxes are conservative visual clearances; they never release findings. */
export function safeOrbitRadius({target,alpha,beta,radius,obstacles=[],boundaries=[],floorY=.20,ceilingY=3.05,minimum=.38,maximum=4.5,padding=.12}){
 const direction=orbitDirection(alpha,beta);let min=minimum,max=maximum;
 if(Math.abs(direction.y)<=.00001&&(target.y<floorY||target.y>ceilingY))return null;
 if(direction.y>.00001)min=Math.max(min,(floorY-target.y)/direction.y);
 if(direction.y<-.00001)min=Math.max(min,(target.y-ceilingY)/-direction.y);
 if(direction.y<-.00001)max=Math.min(max,(target.y-floorY)/-direction.y);
 if(direction.y>.00001)max=Math.min(max,(ceilingY-target.y)/direction.y);
 for(const box of boundaries){const hit=rayBoxInterval(target,direction,box,padding);if(hit)max=Math.min(max,hit[0]-.015);}
 if(max<min)return null;
 const blocked=obstacles.map(box=>rayBoxInterval(target,direction,box,padding)).filter(Boolean).map(([a,b])=>[Math.max(min,a-.015),Math.min(max,b+.015)]).filter(([a,b])=>a<=b).sort((a,b)=>a[0]-b[0]);
 const clear=[];let cursor=min;for(const [a,b]of blocked){if(a>cursor)clear.push([cursor,a]);cursor=Math.max(cursor,b);}if(cursor<max-1e-7)clear.push([cursor,max]);
 let best=null,distance=Infinity;for(const [lo,hi]of clear){const candidate=clamp(radius,lo,hi),delta=Math.abs(candidate-radius);if(delta<distance){best=candidate;distance=delta;}}return best;
}
export function createCameraNavigation({canvas,camera,allowed=()=>true,constraints=()=>({}),onChange=()=>{},onInteraction=()=>{}}){
 let adjusting=false,drag=null,referenceRadius=camera.radius;
 const release=()=>{const id=drag?.id;drag=null;if(id!==undefined&&canvas.hasPointerCapture?.(id))try{canvas.releasePointerCapture(id);}catch{}};
 function remember(){referenceRadius=camera.radius;}
 function setAdjusting(value){release();adjusting=!!value&&allowed();canvas.classList.toggle('adjusting-view',adjusting);if(adjusting){remember();onInteraction();}onChange(adjusting);return adjusting;}
 function move(horizontal=0,vertical=0,distance=0){
  if(!adjusting||!allowed()||![horizontal,vertical,distance].every(Number.isFinite)){if(!allowed())setAdjusting(false);return false;}
  onInteraction();const limits=constraints()||{},steps=Math.max(1,Math.min(180,Math.ceil(Math.max(Math.abs(horizontal),Math.abs(vertical))/.045)));
  for(let i=0;i<steps;i++){
   // Alpha stays unwrapped, so crossing ±pi/2pi never flips or hits a stop.
   const alpha=camera.alpha+horizontal/steps,wantedBeta=clamp(camera.beta+vertical/steps,.12,2.72),wantedRadius=camera.radius+distance/steps;
   let beta=wantedBeta,radius=safeOrbitRadius({...limits,target:camera.target,alpha,beta,radius:wantedRadius});
   // Near the floor/table a requested low angle may have no safe distance.
   // Raise this angle only as far as necessary while retaining the azimuth.
   for(let n=1;radius===null&&n<=60;n++){beta=Math.max(.12,wantedBeta-n*.045);radius=safeOrbitRadius({...limits,target:camera.target,alpha,beta,radius:wantedRadius});}
   if(radius===null)return false;
   camera.alpha=alpha;camera.beta=beta;camera.radius=radius;
  }
  return true;
 }
 const down=event=>{if(!adjusting||!allowed()||event.pointerType!=='mouse'||event.button!==0||event.ctrlKey||event.metaKey||event.altKey)return;release();drag={id:event.pointerId,x:event.clientX,y:event.clientY};try{canvas.setPointerCapture?.(event.pointerId);}catch{drag=null;}};
 const movePointer=event=>{if(!drag||event.pointerId!==drag.id)return;if(!allowed()||event.ctrlKey||event.metaKey||event.altKey){release();return;}const dx=event.clientX-drag.x,dy=event.clientY-drag.y;drag.x=event.clientX;drag.y=event.clientY;move(-dx*.006,-dy*.006);};
 const up=event=>{if(event.pointerId===drag?.id)release();};
 canvas.addEventListener('pointerdown',down);canvas.addEventListener('pointermove',movePointer);canvas.addEventListener('pointerup',up);canvas.addEventListener('pointercancel',up);canvas.addEventListener('lostpointercapture',up);
 return{remember,setAdjusting,move,get adjusting(){return adjusting;},get referenceRadius(){return referenceRadius;},dispose(){setAdjusting(false);canvas.removeEventListener('pointerdown',down);canvas.removeEventListener('pointermove',movePointer);canvas.removeEventListener('pointerup',up);canvas.removeEventListener('pointercancel',up);canvas.removeEventListener('lostpointercapture',up);}};
}
