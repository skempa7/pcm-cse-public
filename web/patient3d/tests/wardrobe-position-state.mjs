/** Execute the shipped iframe handlers with a minimal DOM. This tests ordering,
 * not rendering: wardrobe is local visual state, never an encounter action. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
const script=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
const isPublic=html.includes('id="anatomySwitch"');
const elements=new Map(),outbound=[],applied=[],listeners=new Map();
function element(id){if(!elements.has(id))elements.set(id,{id,style:{},dataset:{},attributes:{},hidden:false,disabled:false,value:'',textContent:'',classList:{toggle(){}},setAttribute(k,v){this.attributes[k]=String(v);},getAttribute(k){return this.attributes[k];},focus(){},append(){},replaceChildren(){}});return elements.get(id);}
const document={getElementById:element,querySelectorAll:()=>[],body:element('body'),createElement:element,createTextNode:s=>s};
const parent={postMessage:d=>outbound.push(d)},window={parent,addEventListener:(type,fn)=>listeners.set(type,fn)};
const context=vm.createContext({window,document,location:{origin:'http://test.invalid'},localStorage:{getItem:()=>null,setItem(){}},matchMedia:()=>({matches:false,addEventListener(){}}),crypto:{randomUUID:()=>String(outbound.length+1)},setTimeout(){},fetch:async()=>({json:async()=>[]}),console});
vm.runInContext(script,context,{filename:'patient3d/index.html inline script'});
window.pcmBabylonReady({SendMessage(_object,method,payload){if(method==='ApplyState')applied.push(JSON.parse(payload));}});
const message=data=>listeners.get('message')({source:parent,origin:'http://test.invalid',data});
const appearance={model:isPublic?'mpfb-public-patient':'mpfb-young-woman',presentation:'female',outfit:isPublic?'fitted-casual':'unclothed'};
let seq=1;
function state(posture='seated',extra={}){return {sessionId:'same-attempt',phase:'encounter',mode:'coached',posture,eventSeq:seq,appearance,...extra};}
const sendState=s=>message({type:'pcm-unity-state',state:s});
const button=element(isPublic?'anatomySwitch':'coverageView');
const outfit=()=>applied.at(-1).appearance.outfit;
const covered=()=>outfit()==='fitted-casual';
sendState(state());
// Enter anatomical view, then switch to clothing immediately before a response.
if(isPublic)button.onclick();
assert.equal(covered(),false);
button.onclick();
assert.equal(covered(),true);
for(const posture of ['supine','seated','standing','prone']){
 ++seq;sendState(state(posture));
 assert.equal(covered(),true,posture+': parent pose response preserves local clothing');
 assert.equal(applied.at(-1).posture,posture);
 // A delayed equal-sequence notification also preserves the selected wardrobe.
 sendState(state(posture));assert.equal(covered(),true);
 // An older posture response is rejected, without changing visual preference.
 sendState(state('seated',{eventSeq:seq-1}));assert.equal(applied.at(-1).posture,posture);
}
// Exercise the iframe request path while visual state changes before its ack.
element('position').value='seated';element('position').onchange();
const request=outbound.at(-1);assert.equal(request.action,'position');
button.onclick();assert.equal(covered(),false);
++seq;sendState(state('seated'));message({type:'pcm-unity-ack',requestId:request.requestId,ok:true});
assert.equal(covered(),false,'late action acknowledgement cannot undo visual preference');
button.onclick();assert.equal(covered(),true);
message({type:'pcm-unity-ack',requestId:request.requestId,ok:true});
assert.equal(covered(),true,'duplicate acknowledgement cannot toggle clothes');
assert.deepEqual(outbound.filter(x=>x.type==='pcm-unity-action').map(x=>x.action),['position'],'wardrobe creates no clinical evidence request');
assert.equal(button.textContent,isPublic?'Show anatomy view':'Anatomy view');
console.log((isPublic?'public':'private')+': wardrobe remains stable across immediate/delayed/duplicate position messages; no wardrobe encounter events.');
