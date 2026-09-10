/* One device-voice policy for previews, authored and AI-prepared responses.
   A null voice delegates to the browser. It does not prove macOS chose the
   same voice shown in Accessibility settings. No gender/name override. */
(()=>{
 'use strict';
 const key='pcmcse.device-voice.v1';
 let preference=null,voices=[],listeners=new Set();
 try{const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved?.uri&&saved?.name)preference=saved;}catch{}
 const synth=window.speechSynthesis;
 function list(){return voices.map(v=>({uri:v.voiceURI,name:v.name,lang:v.lang,default:!!v.default,local:!!v.localService}));}
 function selected(){return preference?voices.find(v=>v.voiceURI===preference.uri&&v.name===preference.name)||voices.find(v=>v.name===preference.name&&v.lang===preference.lang):null;}
 function state(){const chosen=selected();return {supported:!!synth,preference,voices:list(),resolved:chosen?{name:chosen.name,lang:chosen.lang,uri:chosen.voiceURI}:null,browserDefault:list().find(v=>v.default)||null,missing:!!preference&&!chosen};}
 function refresh(){voices=synth?.getVoices?.()||[];for(const fn of listeners)fn(state());return state();}
 function choose(uri){
  if(window.pcmNaturalBusy)return {error:'Finish or stop playback before changing the voice.'};
  if(!uri)preference=null;
  else {const v=voices.find(v=>v.voiceURI===uri);if(!v)return {error:'That voice is no longer available. Refresh the list and choose again.'};preference={uri:v.voiceURI,name:v.name,lang:v.lang};}
  let saved=true;try{localStorage.setItem(key,JSON.stringify(preference));}catch{saved=false;}
  refresh();return {saved,...state()};
 }
 function configure(u,{pace}={}){
  refresh();const v=selected();
  // Leave voice AND language unset for browser/system default. Setting an old
  // language or selecting the first 'female' voice would override that choice.
  if(v){u.voice=v;u.lang=v.lang;}
  const rates={measured:.94,conversational:.98,slightly_hesitant:.94,direct:1,unhurried:.92,deliberate:.94};
  u.rate=rates[pace]||1;u.pitch=1;
  return v?.name||'Browser/system default';
 }
 function subscribe(fn){listeners.add(fn);fn(state());return()=>listeners.delete(fn);}
 synth?.addEventListener?.('voiceschanged',refresh);
 window.addEventListener('focus',refresh);
 window.addEventListener('storage',e=>{if(e.key===key){try{preference=JSON.parse(e.newValue||'null');}catch{preference=null;}refresh();}});
 window.pcmDeviceSpeech={state,refresh,choose,configure,subscribe};refresh();
})();
