/* Student workspaces. All stored work and timing remain owned by the app engine. */
(()=>{'use strict';
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const $=s=>document.querySelector(s);
let generation=0,context=null,voicePanel=null,voiceUnsubscribe=null,previewActive=false;
const shapes={
 home:'<path d="M4 11 12 4l8 7v9h-6v-6h-4v6H4z"/>',
 practice:'<rect x="5" y="3" width="14" height="18" rx="3"/><path d="M9 8h6m-6 4h6m-6 4h3"/>',
 learn:'<path d="M12 6c-4-3-8-2-9-1v15c4-2 7-1 9 1 2-2 5-3 9-1V5c-3-1-6-2-9 1zm0 0v15"/>',
 progress:'<path d="M4 20V4m0 16h17M8 16v-4m5 4V8m5 8V5"/>',
 scoring:'<path d="m5 6 2 2 4-4M14 6h6M5 14l2 2 4-4m3 2h6M5 21h15"/>',
 voice:'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M6 11v2a6 6 0 0 0 12 0v-2m-6 8v3m-4 0h8"/>',
 sealed:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h6m-6 4h6"/><circle cx="15.5" cy="16" r=".8"/>',
};
function icon(key){return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${shapes[key]||shapes.practice}</svg>`;}
function family(system){const s=String(system||'').toLowerCase();return /resp|pulmon/.test(s)?'pulmonary':/card/.test(s)?'cardio':/gastro|abdom|gi\b/.test(s)?'gi':/renal|urinar|genit/.test(s)?'renal':/neuro/.test(s)?'neuro':'general';}
function illustration(key='general'){
 const body={
  cardio:'<path d="M68 43c-12-23-42-12-40 8 2 17 21 31 40 43 19-12 38-26 40-43 2-20-28-31-40-8Z" fill="#e79988"/><path d="M37 62h17l7-17 12 35 8-19h18" stroke="#783f43" stroke-width="4" fill="none"/>',
  pulmonary:'<g data-organ="lungs"><path d="M61 40c-8-7-16 3-23 16-10 17-17 34-12 49 3 10 23 8 31 0 8-9 6-28 6-42Z" fill="#94bfc4" stroke="#497780" stroke-width="3"/><path d="M79 40c8-7 16 3 23 16 10 17 17 34 12 49-3 10-22 8-30 0-5-5-4-11-1-17 4-7-8-11-8-23Z" fill="#a7ccd0" stroke="#497780" stroke-width="3"/><path d="M70 23v35m0 0L49 77m21-19 22 19M51 75l-12 6m12-6 3 16m35-17 12 7m-12-7-3 15" fill="none" stroke="#f5e2c6" stroke-width="6" stroke-linecap="round"/><path d="M66 29h8m-8 8h8m-8 8h8" stroke="#7e9ca0" stroke-width="2"/><path d="m29 92 21 2m42-3 19 6" stroke="#65969c" stroke-width="2" fill="none"/></g>',
  gi:'<path d="M61 21v31c-10 5-16 14-14 25 3 18 39 26 52 7 12-18 1-31-11-37-12-5-17-13-17-26" fill="#e8b872" stroke="#8c612e" stroke-width="3"/><path d="M50 95c-15 2-16 19-1 20h37c15 0 17-15 4-16H64" fill="none" stroke="#c39254" stroke-width="8"/>',
  renal:'<path d="M48 31c-26-1-28 43-9 54 10 7 20 0 19-10-1-7-12-7-11-15s13-5 14-12c2-9-5-15-13-17Zm40 0c26-1 28 43 9 54-10 7-20 0-19-10 1-7 12-7 11-15S76 55 75 48c-2-9 5-15 13-17Z" fill="#bf879c" stroke="#79596e" stroke-width="3"/><path d="M52 64c15 13 2 31 12 41m20-41c-15 13-2 31-12 41" stroke="#bd9a61" stroke-width="3" fill="none"/><path d="M59 104h18v8c0 12-18 12-18 0Z" fill="#ddb874"/>',
  neuro:'<path d="M83 113V92c18-10 25-25 19-46-7-25-43-30-63-11-11 11-10 27-9 37l-9 13h14v18h23v10" fill="#bcbdde" stroke="#686485" stroke-width="3"/><path d="M56 35c-11 1-17 9-14 17-7 8-3 19 6 21m21-41c-12-3-14 12-6 16-12-1-17 13-7 17m20-29c14 0 18 13 9 19 8 10 1 17-9 16m-7-25v29" fill="none" stroke="#7c729d" stroke-width="4"/>',
  sealed:'<rect x="35" y="19" width="68" height="103" rx="7" fill="#9db9af" stroke="#526f67" stroke-width="3"/><rect x="46" y="32" width="46" height="28" rx="3" fill="#e5ece0"/><path d="M56 42h26m-26 9h19" stroke="#7d978b" stroke-width="3"/><circle cx="88" cy="83" r="4" fill="#cb9e58"/>',
  general:'<rect x="35" y="24" width="70" height="91" rx="9" fill="#a2c1b6"/><rect x="52" y="16" width="37" height="16" rx="5" fill="#587f70"/><path d="M59 47h22m-11-11v22M50 74h40M50 86h40M50 98h27" stroke="#fffaf0" stroke-width="5"/>',
 };
 return `<svg viewBox="0 0 140 140" aria-hidden="true"><circle cx="70" cy="70" r="64" fill="currentColor" opacity=".07"/><circle cx="112" cy="28" r="10" fill="currentColor" opacity=".10"/>${body[key]||body.general}</svg>`;
}
const phaseLabel={briefing:'At the doorway',encounter:'Patient encounter',organize:'Organization interval',note:'SOAP note',submitted:'Feedback ready'};
function nav(kind){document.querySelectorAll('[data-destination]').forEach(b=>b.setAttribute('aria-current',b.dataset.destination===kind?'page':'false'));}
function buttons(root){root.querySelectorAll('[data-portal-go]').forEach(b=>b.onclick=()=>window.pcmNavigate?.(b.dataset.portalGo));root.querySelectorAll('[data-resume]').forEach(b=>b.onclick=()=>{location.hash='#/'+b.dataset.resume;});}
function when(ms){const d=new Date(ms),now=new Date();
 return d.toDateString()===now.toDateString()
  ? d.toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'})
  : d.toLocaleDateString(undefined,{month:'short',day:'numeric'});}
function activity(rows,cases){return rows.slice(0,4).map(s=>{const c=cases.find(c=>c.id===s.case_id);return `<button class="portal-activity" data-resume="${E(s.id)}"><span class="portal-activity-icon">${icon(s.phase==='submitted'?'progress':'practice')}</span><span><b>${E(c?.title||c?.station_label||'Saved station')}</b><small>${E(phaseLabel[s.phase]||s.phase)} · ${E(when(s.created_at))}</small></span><span aria-hidden="true">↗</span></button>`;}).join('')||'<div class="portal-empty">Your encounters will appear here as you practice. Start with a guided encounter whenever you’re ready.</div>';}
function heading(kicker,title,detail){return `<header class="portal-heading"><div><span class="portal-kicker">${kicker}</span><h1>${title}</h1><p>${detail}</p></div></header>`;}
function completedCount(data){const counts=data.progress?.completed_by_mode;if(counts&&Object.keys(counts).length)return Object.values(counts).reduce((sum,n)=>sum+(Number(n)||0),0);return (data.sessions||[]).filter(s=>s.phase==='submitted').length;}
function home(data){
 const rows=data.sessions||[],cases=data.cases||[],progress=data.progress||{},completed=rows.filter(s=>s.phase==='submitted'),unfinished=rows.find(s=>s.phase!=='submitted'),coverage=(progress.completed_cases||[]).length;
 // "Pick up your encounter" named neither the patient nor the presentation,
 // so a student with several saved attempts could not tell which one the
 // button would open. The row list had the same problem: four "Station 2".
 const unfinishedCase=cases.find(c=>c.id===unfinished?.case_id);
 const resume=unfinished?`<section class="portal-resume"><span class="portal-kicker">Ready when you are</span><h2>Pick up your ${unfinished.phase==='note'?'SOAP note':'encounter'}.</h2><p><b>${E(unfinishedCase?.title||'Saved attempt')}</b>${unfinishedCase?.station_label?` · ${E(unfinishedCase.station_label)}`:''} · ${E(phaseLabel[unfinished.phase]||'Saved attempt')}<br>Your original work and timing are retained.</p><button class="btn portal-primary" data-resume="${E(unfinished.id)}">Resume saved attempt <span aria-hidden="true">→</span></button></section>`:`<section class="portal-resume"><span class="portal-kicker">Your next patient is waiting</span><h2>Build a routine you can trust.</h2><p>Choose a presentation and the amount of guidance you want. Review the doorway before the encounter begins.</p><button class="btn portal-primary" data-portal-go="practice">Choose a practice case <span aria-hidden="true">→</span></button></section>`;
 return `<div class="portal-workspace">${heading('Student portal','Your practice desk.','A place for patient encounters, clear teaching, and the next step in your learning.')}<section class="portal-metrics" aria-label="Your practice at a glance"><div><b>${cases.length}</b><span>patient presentations</span></div><div><b>${completedCount(data)}</b><span>completed attempts</span></div><div><b>${coverage}<small> / ${cases.length}</small></b><span>presentations explored</span></div><div><b>${progress.conditions?.independent||0}</b><span>independent completions</span></div></section><div class="portal-dashboard"><div class="portal-main">${resume}<section><div class="portal-section-heading"><h2>Your workspaces</h2><span>Choose how you want to learn</span></div><div class="portal-destinations">${[
  ['practice','Meet a patient','Work through history, examination, and documentation.','Open case library','cardio'],
  ['cases','Practice with a partner','Print a patient script, examination findings and a blank note. Compare with the example afterward.','Open case documents','general'],
  ['progress','Reflect and improve','Revisit your original attempts, feedback, and focused repair exercises.','Review your practice','neuro'],
  ['scoring','Know where the points are','See the SOAP requirements and the actions that support each point.','Open scoring guide','sealed'],
 ].map(([key,title,description,cta,art])=>`<button class="portal-destination" data-portal-go="${key}"><span class="portal-tile-art">${illustration(art)}</span><span class="portal-tile-copy"><b>${title}</b><span>${description}</span><strong>${cta} <span aria-hidden="true">→</span></strong></span></button>`).join('')}</div></section></div><aside class="portal-side"><section class="portal-side-card"><div class="portal-section-heading"><h2>Recent practice</h2>${icon('progress')}</div>${activity(rows,cases)}<button class="btn ghost" data-portal-go="progress">All attempts &amp; progress →</button></section><section class="portal-routine"><span class="portal-kicker">Keep your place</span><h2>One useful step at a time.</h2><ol><li><b>Understand</b><span>Hear the concern.</span></li><li><b>Explore</b><span>Ask, examine, interpret.</span></li><li><b>Explain</b><span>Share the next steps.</span></li><li><b>Document</b><span>Use the evidence you obtained.</span></li></ol></section></aside></div></div>`;
}
async function render(kind,ctx){
 restoreVoicePanel();context=ctx;const token=++generation;nav(kind);
 ctx.view.innerHTML='<div class="portal-workspace"><p class="portal-loading" role="status">Opening your workspace…</p></div>';
 let data=await ctx.api('/api/bootstrap');if(token!==generation)return;
 if(data.error){ctx.view.innerHTML=`<div class="portal-workspace"><section class="portal-side-card"><h1>Your workspace could not refresh</h1><p>${E(data.message||'Reconnect and try again. Saved attempts have not been removed.')}</p><button class="btn primary" id="portalRetry">Try again</button></section></div>`;$('#portalRetry').onclick=()=>render(kind,ctx);return;}
 ctx.onData(data);
 if(kind==='home')ctx.view.innerHTML=home(data);
 else if(kind==='progress'){ctx.view.innerHTML=`<div class="portal-workspace" id="progressWorkspace">${heading('Practice record','Your progress, in context.','Original notes, assistance, retries, and feedback remain separate.')}<section class="portal-progress-intro"><b>${completedCount(data)} completed attempts</b><span>Use a previous attempt to review evidence or practice a repair. Showing the ${Math.min((data.sessions||[]).length,40)} most recent attempts.</span></section><div class="disclosure open" id="extraPanel" data-open="past">${ctx.past()}</div></div>`;ctx.wirePast();}
 else if(kind==='scoring')ctx.view.innerHTML=`<div class="portal-workspace portal-reading">${ctx.scoring()}</div>`;
 buttons(ctx.view);ctx.view.focus({preventScroll:true});
}
function restoreVoicePanel(){
 if(previewActive){window.speechSynthesis?.cancel();previewActive=false;}
}
function decoratePractice(mode,reveal){
 const grid=$('#stationGrid');if(!grid)return;
 document.body.dataset.workspace='practice';
 grid.querySelectorAll('.station-card').forEach(card=>{
  let art=card.querySelector('.s-illustration');if(!art){art=document.createElement('span');art.className='s-illustration';card.prepend(art);}
  const c=(context?.boot?.cases||window.pcmPortalCases?.()||[]).find(c=>c.id===card.dataset.case),key=reveal?family(c?.system):'sealed';
  if(art.dataset.kind!==key){art.dataset.kind=key;art.innerHTML=illustration(key);}
 });
 const system=$('#sysPick');if(system){system.hidden=!reveal;system.disabled=!reveal;if(!reveal&&system.value){system.value='';system.dispatchEvent(new Event('change',{bubbles:true}));}}
 for(const id of ['skillFilter','variantChoice']){const el=$('#'+id);if(!el)continue;el.closest('label').hidden=!reveal;if(!reveal&&id==='skillFilter'&&el.value){el.value='';el.dispatchEvent(new Event('change',{bubbles:true}));}}
 let families=$('#portalFamilies');if(!families){families=document.createElement('div');families.id='portalFamilies';families.className='portal-families';families.setAttribute('aria-label','Choose a complaint family');grid.before(families);}
 families.hidden=!reveal;
 const systems=[...new Set((context?.boot?.cases||window.pcmPortalCases?.()||[]).map(c=>c.system))];
 if(reveal&&families.dataset.ready!=='true'){
  families.innerHTML=`<button type="button" class="portal-family selected" data-family="">${icon('practice')}<span>All presentations</span></button>`+systems.map(s=>`<button type="button" class="portal-family" data-family="${E(s)}">${illustration(family(s))}<span>${E(s)}</span></button>`).join('');families.dataset.ready='true';
  families.querySelectorAll('button').forEach(b=>b.onclick=()=>{system.value=b.dataset.family;system.dispatchEvent(new Event('change',{bubbles:true}));});
  system?.addEventListener('change',()=>families.querySelectorAll('button').forEach(b=>{const selected=b.dataset.family===system.value;b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',String(selected));}));
 }
}
function setupNavigation(){
 const skip=$('.skip-link');if(skip)skip.onclick=e=>{e.preventDefault();const view=$('#view');view?.focus({preventScroll:true});view?.scrollIntoView({block:'start',behavior:'instant'});};
 const bar=$('.workspace-nav');if(bar)bar.innerHTML=[['home','Home'],['practice','Practice'],['cases','Cases & print'],['progress','Progress'],['scoring','Scoring']].map(([key,label])=>`<button class="btn ghost sm" type="button" data-destination="${key}">${icon(key)}<span>${label}</span></button>`).join('');
 document.querySelectorAll('[data-destination]').forEach(b=>b.onclick=()=>window.pcmNavigate?.(b.dataset.destination));
 $('#btnBrand')?.addEventListener('click',()=>window.pcmNavigate?.('home'));
}
window.pcmPortal={render,decoratePractice,icon,illustration,setupNavigation,nav,invalidate:()=>{restoreVoicePanel();generation++;}};
window.addEventListener('pcm-lobby-ready',()=>decoratePractice(window.pcmPortalMode?.().mode,window.pcmPortalMode?.().reveal));
})();
