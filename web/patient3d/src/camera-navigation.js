// Deliberate view changes only. Wheel, touch/pinch and keyboard events belong
// to the browser; this controller never registers handlers for them.
export function createCameraNavigation({canvas,camera,allowed=()=>true,onChange=()=>{},onInteraction=()=>{}}){
 let adjusting=false,drag=null,anchor=null;
 const bounded=(v,low,high)=>Math.min(high,Math.max(low,v));
 function remember(){anchor={alpha:camera.alpha,beta:camera.beta,radius:camera.radius};}
 function setAdjusting(value){adjusting=!!value&&allowed();drag=null;canvas.classList.toggle('adjusting-view',adjusting);onChange(adjusting);return adjusting;}
 function move(horizontal=0,vertical=0,distance=0){
  if(!allowed())return false;
  if(!anchor)remember();
  onInteraction();
  // A small orbit around a known useful view cannot travel behind the patient
  // or below the mattress. The frame itself changes with the recorded pose.
  camera.alpha=bounded(camera.alpha+horizontal,anchor.alpha-.34,anchor.alpha+.34);
  camera.beta=bounded(camera.beta+vertical,Math.max(.20,anchor.beta-.18),Math.min(1.55,anchor.beta+.18));
  camera.radius=bounded(camera.radius+distance,Math.max(.60,anchor.radius*.90),anchor.radius*1.24);
  return true;
 }
 const down=event=>{if(!adjusting||!allowed()||event.pointerType!=='mouse'||event.button!==0||event.ctrlKey||event.metaKey||event.altKey)return;drag={id:event.pointerId,x:event.clientX,y:event.clientY};canvas.setPointerCapture?.(event.pointerId);};
 const movePointer=event=>{if(!drag||event.pointerId!==drag.id)return;const dx=event.clientX-drag.x,dy=event.clientY-drag.y;drag.x=event.clientX;drag.y=event.clientY;move(-dx*.0035,-dy*.0035);};
 const up=event=>{if(event.pointerId===drag?.id){if(canvas.hasPointerCapture?.(event.pointerId))canvas.releasePointerCapture(event.pointerId);drag=null;}};
 canvas.addEventListener('pointerdown',down);canvas.addEventListener('pointermove',movePointer);canvas.addEventListener('pointerup',up);canvas.addEventListener('pointercancel',up);canvas.addEventListener('lostpointercapture',up);
 return{remember,setAdjusting,move,get adjusting(){return adjusting;},dispose(){setAdjusting(false);canvas.removeEventListener('pointerdown',down);canvas.removeEventListener('pointermove',movePointer);canvas.removeEventListener('pointerup',up);canvas.removeEventListener('pointercancel',up);canvas.removeEventListener('lostpointercapture',up);}};
}
