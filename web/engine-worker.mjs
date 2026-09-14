import {loadPyodide} from './vendor/pyodide/pyodide.mjs';
let py,request;
const sync=populate=>new Promise((resolve,reject)=>py.FS.syncfs(populate,error=>error?reject(error):resolve()));
const ready=(async()=>{
 postMessage({type:'progress',message:'Loading the local browser engine…'});
 py=await loadPyodide({indexURL:new URL('./vendor/pyodide/',import.meta.url).href});
 py.FS.mkdir('/pcm-cse-public-v1');py.FS.mount(py.FS.filesystems.IDBFS,{},'/pcm-cse-public-v1');await sync(true);
 const response=await fetch(new URL('./engine.zip?v=fc323f5d6b',import.meta.url),{cache:'no-store'});if(!response.ok)throw Error('The browser engine download failed. Reload to try again.');
 py.unpackArchive(new Uint8Array(await response.arrayBuffer()),'zip',{extractDir:'/app'});
 await py.runPythonAsync(`import os,sys\nos.environ['PCM_CSE_DB']='/pcm-cse-public-v1/attempts.sqlite'\nos.environ['PCM_CSE_SETTINGS']='/pcm-cse-public-v1/settings.json'\nsys.path.insert(0,'/app')\nfrom pcmcse import db\ndb.init()\nfrom offline_routes import request`);
 request=py.globals.get('request');await sync(false);postMessage({type:'ready'});
})();
let queue=Promise.resolve();let persistenceFault=false;
onmessage=event=>{
 const m=event.data;
 queue=queue.then(async()=>{
  try{
   await ready;
   if(persistenceFault){
    // The last operation already ran in memory. Retry only the disk flush,
    // never that operation, before accepting further work.
    try{await sync(false);persistenceFault=false;postMessage({type:'storage-recovered'});}
    catch(e){throw Error('Browser storage is still unavailable. Keep this tab open and copy your note. Free browser storage; saving will retry without repeating your last action.');}
   }
   const result=JSON.parse(request(m.path,m.method,m.body||'{}'));
   try{await sync(false);}catch(e){persistenceFault=true;throw Error('Your latest change is in memory but could not be saved to browser storage. Keep this tab open and copy your note. '+e.message);}
   postMessage({id:m.id,...result});
  }catch(e){postMessage({id:m.id,status:503,body:{error:e.message}});}
 });
};
ready.catch(e=>postMessage({type:'fatal',message:e.message}));
