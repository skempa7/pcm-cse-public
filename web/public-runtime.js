/* Static edition: API-shaped calls stay inside a dedicated local Web Worker.
   No backend, provider credential, payment service, or remote API exists. */
(()=>{
 'use strict';
 const originalFetch=window.fetch.bind(window),base=new URL('./',location.href),pending=new Map();
 let worker,counter=0,resolveReady,rejectReady;
 const ready=new Promise((resolve,reject)=>{resolveReady=resolve;rejectReady=reject;});ready.catch(()=>{});
 function message(text){const el=document.getElementById('localEngineStatus');if(el)el.textContent=text;}
 async function start(){
  if(!navigator.locks)throw Error('This browser cannot safely coordinate saved attempts. Use a current Chrome, Edge, Firefox or Safari.');
  await navigator.locks.request('pcm-public-engine-v1',{mode:'exclusive',ifAvailable:true},async lock=>{
   if(!lock)throw Error('This app is already open in another tab. Close that tab, then reload this one to resume the same saved work.');
   worker=new Worker(new URL('engine-worker.mjs',base),{type:'module'});
   worker.onmessage=event=>{
    const data=event.data;
    if(data.type==='progress')message(data.message);
    else if(data.type==='ready'){message('Saved on this browser · Computer voice · No paid services');resolveReady();}
    else if(data.type==='fatal'){message('Could not start: '+data.message);rejectReady(Error(data.message));}
    else if(pending.has(data.id)){pending.get(data.id)(data);pending.delete(data.id);}
   };
   worker.onerror=()=>{const error='The local engine stopped. Reload to restore saved work; copy any visible unsaved note first.';message(error);rejectReady(Error(error));for(const resolve of pending.values())resolve({status:503,body:{error}});pending.clear();};
   await new Promise(()=>{}); // Keep the exclusive lock for this tab's lifetime.
  });
 }
 window.fetch=async(input,options={})=>{
  const raw=typeof input==='string'?input:input.url||String(input),url=new URL(raw,location.href);
  const localPath=url.pathname.startsWith(base.pathname)?'/'+url.pathname.slice(base.pathname.length):url.pathname;
  if(url.origin===location.origin && localPath.startsWith('/api/')){
   await ready;
   const result=await new Promise(resolve=>{const id=++counter;pending.set(id,resolve);worker.postMessage({id,path:localPath+url.search,method:options.method||'GET',body:options.body||'{}'});});
   return new Response(JSON.stringify(result.body),{status:result.status,headers:{'Content-Type':'application/json'}});
  }
  if(url.origin!==location.origin)throw Error('External service requests are disabled in this free public edition.');
  return originalFetch(input,options);
 };
 document.addEventListener('DOMContentLoaded',()=>{
  const bar=document.createElement('aside');bar.className='public-notice';bar.setAttribute('aria-label','Public edition status');
  bar.innerHTML='<strong>Free development preview · SOAP feedback may be inaccurate</strong><span id="localEngineStatus" role="status">Starting the local engine…</span><details><summary>About this edition</summary><p>All encounters, notes and grading run on your device. No account, paid AI, hosted backend or payment service. Computer speech uses your browser’s default voice.</p><p><strong>Development build, not study-ready:</strong> the inherited SOAP checker can flag valid statements incorrectly, especially timing/context, refusals and proposed tests. Check feedback against your course rubric; scores are provisional.</p><p>Work is saved in this browser only. Clearing site data deletes it. Use one tab at a time. Browser/device clocks and client source are accessible: this is a practice tool, not secure exam software. The 24 fictional presentations have 72 written paths; demographic choices are an authored practice cohort, not representative clinical coverage.</p><p>14-minute encounter + 9-minute SOAP. Default practice adds a 2-minute organization interval; course rehearsal does not. No private course documents or personal attempts are included.</p></details>';
  document.body.insertBefore(bar,document.getElementById('app'));
  start().catch(e=>{message(e.message);rejectReady(e);});
 });
})();
