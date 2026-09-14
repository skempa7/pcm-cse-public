/* Static edition: API-shaped calls stay inside a dedicated local Web Worker.
   No backend, provider credential, payment service, or remote API exists. */
(()=>{
 'use strict';
 const originalFetch=window.fetch.bind(window),base=new URL('./',location.href),pending=new Map();
 let worker,counter=0,resolveReady,rejectReady,terminalError=null;
 const ready=new Promise((resolve,reject)=>{resolveReady=resolve;rejectReady=reject;});ready.catch(()=>{});
 function message(text,urgent=false){const el=document.getElementById('localEngineStatus');if(el){el.textContent=text;el.hidden=!urgent;}}
 function fail(error){terminalError=error;message(error,true);rejectReady(Error(error));for(const resolve of pending.values())resolve({status:503,body:{error}});pending.clear();}
 async function start(){
  if(!navigator.locks)throw Error('This browser cannot safely coordinate saved attempts. Use a current Chrome, Edge, Firefox or Safari.');
  await navigator.locks.request('pcm-public-engine-v1',{mode:'exclusive',ifAvailable:true},async lock=>{
   if(!lock)throw Error('This app is already open in another tab. Close that tab, then reload this one to resume the same saved work.');
   worker=new Worker(new URL('engine-worker.mjs?v=b309637eda',base),{type:'module'});
   worker.onmessage=event=>{
    const data=event.data;
    if(data.type==='progress')message(data.message);
    else if(data.type==='ready'){message('Saved on this browser · Computer voice · No paid services');resolveReady();}
    else if(data.type==='storage-recovered'){message('Saved on this browser · Computer voice · No paid services');}
    else if(data.type==='fatal'){fail('Could not start: '+data.message);}
    else if(pending.has(data.id)){if(data.status>=500)message(data.body?.error||'The last action could not be saved.',true);pending.get(data.id)(data);pending.delete(data.id);}
   };
   worker.onerror=()=>{const error='The local engine stopped. Reload to restore saved work; copy any visible unsaved note first.';fail(error);};
   await new Promise(()=>{}); // Keep the exclusive lock for this tab's lifetime.
  });
 }
 window.fetch=async(input,options={})=>{
  const raw=typeof input==='string'?input:input.url||String(input),url=new URL(raw,location.href);
  const localPath=url.pathname.startsWith(base.pathname)?'/'+url.pathname.slice(base.pathname.length):url.pathname;
  if(url.origin===location.origin && localPath.startsWith('/api/')){
   await ready;if(terminalError)throw Error(terminalError);
   const result=await new Promise(resolve=>{const id=++counter;pending.set(id,resolve);worker.postMessage({id,path:localPath+url.search,method:options.method||'GET',body:options.body||'{}'});});
   return new Response(JSON.stringify(result.body),{status:result.status,headers:{'Content-Type':'application/json'}});
  }
  if(url.origin!==location.origin)throw Error('External service requests are disabled in this free public edition.');
  return originalFetch(input,options);
 };
 document.addEventListener('DOMContentLoaded',()=>{
  const status=document.createElement('div');status.id='localEngineStatus';status.hidden=true;status.setAttribute('role','alert');document.body.insertBefore(status,document.getElementById('app'));
  start().catch(e=>{message(e.message,true);rejectReady(e);});
 });
})();
