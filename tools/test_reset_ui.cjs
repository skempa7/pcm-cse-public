const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('node:assert/strict');
function fixture(edition){
 const source=fs.readFileSync(edition,'utf8');
 const functions=source.slice(source.indexOf('function panelPast(){'),source.indexOf('\nasync function begin(',source.indexOf('function panelPast(){')));
 const store=new Map(),els=new Map(),calls=[],events=[],state={focused:null,refreshes:0,notices:[]};
 function element(id,tag='div',attrs=''){
  const el={id,tag,isConnected:true,disabled:/\bdisabled\b/.test(attrs),checked:false,value:'',textContent:'',children:[],setAttribute(){},removeAttribute(){},focus(){state.focused=id;},remove(){els.delete(id);this.isConnected=false;}};
  let content='';Object.defineProperty(el,'innerHTML',{get:()=>content,set(v){for(const id of el.children)els.delete(id);el.children=[];content=v;for(const match of v.matchAll(/<(\w+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)){const child=element(match[3],match[1],match[2]);els.set(child.id,child);el.children.push(child.id);}}});
  els.set(id,el);return el;
 }
 for(const id of ['extraPanel','stationGrid','progressResetConfirm','progressResetStatus','progressResetTools','btnPast'])element(id);
 const trigger=element('trigger','button');
 const context={console,Set,Map,Array,JSON,Date,Number,Error,String,Promise,
  S:null,BOOT:{sessions:[{id:'a',case_id:'case-a',phase:'submitted'},{id:'b',case_id:'case-b',phase:'submitted'}],cases:[{id:'case-a',title:'Secret A'},{id:'case-b',title:'Secret B'}],progress:{old:true}},
  MODES:{coached:{reveal:true},rehearsal:{reveal:false}},mode:'coached',
  currentUiMode:()=>context.mode,caseById:id=>context.BOOT.cases.find(c=>c.id===id),stationTitle:id=>id==='case-a'?'Station 1':'Station 2',esc:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
  $:id=>els.get(id.replace(/^#/,'')), $$:selector=>selector==='button,input,select'?[...els.values()].filter(e=>['button','input','select'].includes(e.tag)):[],
  localStorage:{get length(){return store.size},key:i=>[...store.keys()][i],removeItem:k=>store.delete(k),getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},
  window:{pcmLastAttempt:'a',pcmLearningRender:()=>events.push('learning'),dispatchEvent:e=>events.push(e)},CustomEvent:function(type,options){this.type=type;this.detail=options.detail},location:{hash:''},
  refreshLobbyHistory:()=>state.refreshes++,toast:m=>state.notices.push(m),alertNow:m=>state.notices.push(m),
  api:async()=>({sessions:context.BOOT.sessions,progress:{refreshed:true}}),
 };
 context.fetch=async(path,opts)=>{const payload=JSON.parse(opts.body);calls.push({path,payload});const r=await context.response(path,payload);return{ok:r.status<400,status:r.status,json:async()=>r.body};};
 context.response=async(path)=>path.endsWith('reset-preview')?{status:200,body:{scope:'case',case_id:'case-a',attempt_count:55,unfinished_count:3,study_progress_count:2}}:{status:200,body:{ok:true,deleted:{attempts:55},deleted_attempt_ids:['a','old'],sessions:[{id:'b',case_id:'case-b',phase:'submitted'}],progress:{reset:true}}};
 vm.createContext(context);vm.runInContext(functions,context);return{context,els,store,calls,state,trigger};
}
(async()=>{
 const passed=[];
 for(const edition of (process.argv.length>2?process.argv.slice(2):[path.join(__dirname,'../web/app.js')])){
  let f=fixture(edition);const pref=['pcmcse.device-voice.v1','pcmcse.prefs','pcmcse.reducedMotion','pcmcse.theme','pcm-natural-voice','pcm-paid-voice-consent','pcm-room-covered'];
  for(const k of [...pref,'pcmcse.draft.note.a','pcmcse.draft.scratch.a','pcmcse.draft.conversation.a','pcmcse.ui.a','pcm-camera.a','pcmcse.courtesy.a','pcmcse.entrance.a','pcmcse.performed.a','pcmcse.written-reflection.case-a.base','pcmcse.written-reflection.case-a.variant-2','pcmcse.draft.note.b','pcm-camera.b','pcmcse.written-reflection.case-b.base'])f.store.set(k,'saved');
  assert.equal(f.context.clearResetLocalWork('case','case-a',['a']),true);for(const k of pref)assert.ok(f.store.has(k));assert.ok(f.store.has('pcmcse.draft.note.b'));assert.ok(f.store.has('pcm-camera.b'));assert.ok(f.store.has('pcmcse.written-reflection.case-b.base'));assert.ok(!f.store.has('pcmcse.written-reflection.case-a.variant-2'));assert.equal(f.context.window.pcmLastAttempt,null);passed.push(`${edition}: exact targeted local cleanup, unrelated attempts and preferences preserved`);
  f=fixture(edition);f.context.S={id:'a'};assert.ok(!f.context.panelPast().includes('id="resetAllProgress"'));await f.context.showProgressResetConfirmation('all',null,f.trigger);assert.equal(f.calls.length,0);f.context.S=null;f.context.mode='rehearsal';assert.ok(!f.context.panelPast().includes('Secret A'));passed.push(`${edition}: active-attempt lock and sealed case labels`);
  f=fixture(edition);f.store.set('pcmcse.draft.note.old','old');f.store.set('pcmcse.draft.note.b','keep');f.store.set('pcmcse.written-reflection.case-a.base','draft');
  await f.context.showProgressResetConfirmation('case','case-a',f.trigger);assert.ok(f.els.get('progressResetConfirm').innerHTML.includes('55 saved attempts'));assert.equal(f.state.focused,'cancelProgressReset');assert.equal(f.els.get('confirmProgressReset').disabled,true);await f.els.get('confirmProgressReset').onclick();assert.equal(f.calls.filter(c=>c.path==='/api/progress/reset').length,0);
  const check=f.els.get('resetIncludeUnfinished');check.checked=true;check.onchange();assert.equal(f.els.get('confirmProgressReset').disabled,false);await f.els.get('confirmProgressReset').onclick();assert.deepEqual(JSON.parse(JSON.stringify(f.calls.at(-1).payload)),{scope:'case',confirm:true,include_in_progress:true,case_id:'case-a'});assert.ok(!f.store.has('pcmcse.draft.note.old'));assert.ok(f.store.has('pcmcse.draft.note.b'));assert.ok(f.context.BOOT.progress.reset);assert.ok(f.state.notices.some(x=>x.includes('55 attempts removed')));passed.push(`${edition}: accurate full-history counts, unfinished opt-in, exact backend IDs and progress refresh`);
  f=fixture(edition);await f.context.showProgressResetConfirmation('all',null,f.trigger);f.els.get('cancelProgressReset').onclick();assert.equal(f.calls.length,1);assert.equal(f.els.get('progressResetConfirm').innerHTML,'');passed.push(`${edition}: cancellation has no mutation request`);
  f=fixture(edition);const normal=f.context.response;f.context.response=async(path,payload)=>path==='/api/progress/reset'?{status:409,body:{error:'New unfinished attempt',reset:false}}:normal(path,payload);f.store.set('pcmcse.draft.note.a','keep');await f.context.showProgressResetConfirmation('all',null,f.trigger);const cb=f.els.get('resetIncludeUnfinished');cb.checked=true;cb.onchange();await f.els.get('confirmProgressReset').onclick();assert.equal(f.calls.filter(c=>c.path==='/api/progress/reset').length,1);assert.ok(f.store.has('pcmcse.draft.note.a'));assert.equal(f.state.refreshes,1);assert.ok(f.state.notices.some(x=>x.includes('Nothing was reset')));passed.push(`${edition}:409 refreshes without retry or deleting local drafts`);
  f=fixture(edition);f.context.response=async(path)=>path.endsWith('reset-preview')?{status:200,body:{attempt_count:0,unfinished_count:0,study_progress_count:1}}:{status:200,body:{ok:true,deleted:{attempts:0},deleted_attempt_ids:[],sessions:f.context.BOOT.sessions,progress:{}}};f.store.set('pcmcse.written-reflection.case-a.base','draft');await f.context.showProgressResetConfirmation('case','case-a',f.trigger);assert.equal(f.els.get('resetIncludeUnfinished'),undefined);await f.els.get('confirmProgressReset').onclick();assert.ok(!f.store.has('pcmcse.written-reflection.case-a.base'));passed.push(`${edition}: written-reflection-only case reset works without attempts`);
  f=fixture(edition);f.context.response=async()=>({status:503,body:{error:'Could not inspect progress'}});await f.context.showProgressResetConfirmation('all',null,f.trigger);assert.equal(f.calls.length,1);assert.ok(f.els.get('progressResetStatus').textContent.includes('No progress was removed'));passed.push(`${edition}: failed preview never exposes a destructive confirmation`);
 }
 console.log(JSON.stringify({passed:passed.length,checks:passed},null,2));
})().catch(e=>{console.error(e);process.exitCode=1});
