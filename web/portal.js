/* Student workspaces. All stored work and timing remain owned by the app engine. */
(()=>{'use strict';
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const $=s=>document.querySelector(s);
let generation=0,context=null,voicePanel=null,voiceUnsubscribe=null,previewActive=false,headerObserver=null;
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
// The display taxonomy uses authored system labels; it never infers a diagnosis.
const systemOrder=['Cardiovascular','Cardiopulmonary','Respiratory','Gastrointestinal','Renal / Genitourinary','Neurologic','Musculoskeletal','HEENT','Skin'];
function orderedSystems(cases){return [...new Set(cases.map(c=>c.system).filter(Boolean))].sort((a,b)=>{const x=systemOrder.indexOf(a),y=systemOrder.indexOf(b);return (x<0?99:x)-(y<0?99:y)||a.localeCompare(b);});}
function systemLabel(system){return system==='HEENT'?'Head, eyes, ears, nose & throat':system;}
function family(system){const s=String(system||'').toLowerCase();return /cardiopulmon/.test(s)?'cardiopulmonary':/resp|pulmon/.test(s)?'pulmonary':/card/.test(s)?'cardio':/gastro|abdom|gi\b/.test(s)?'gi':/renal|urinar|genit/.test(s)?'renal':/neuro/.test(s)?'neuro':/musculo|msk/.test(s)?'msk':/heent|head.*neck/.test(s)?'heent':/skin|dermat/.test(s)?'skin':'general';}
function illustration(key='general'){
 const body={
  cardio:'<path d="M69 45C56 21 29 34 30 54c1 20 21 35 39 49 18-14 39-29 40-49 1-20-27-33-40-9Z" fill="#e79988" stroke="#8d5755"/><path d="M38 65h17l7-15 11 30 8-15h19" fill="none" stroke="#754249"/>',
  pulmonary:'<path d="M60 39c-11-3-20 10-28 24-8 15-10 31-4 39 6 8 21 6 29-1 8-7 7-24 7-39V43Z" fill="#9cc6cb" stroke="#4e7f88"/><path d="M80 39c11-3 20 10 28 24 8 15 10 31 4 39-6 8-21 6-29-1-8-7-7-24-7-39V43Z" fill="#9cc6cb" stroke="#4e7f88"/><path d="M70 26v31m0 0L48 76m22-19 22 19m-22-44h-5m5 9h-5m5 9h-5" fill="none" stroke="#47737b"/><path d="m48 76-10 7m10-7 2 16m42-16 10 7m-10-7-2 16" fill="none" stroke="#47737b"/>',
  cardiopulmonary:'<path d="M56 37C42 36 25 66 25 87c0 13 15 15 27 7l8-45m24-12c14-1 31 29 31 50 0 13-15 15-27 7l-8-45" fill="#9cc6cb" stroke="#4e7f88"/><path d="M70 24v29m0 0L48 72m22-19 22 19" fill="none" stroke="#47737b"/><path d="M70 82c-11-16-30-6-24 9 4 10 16 18 24 24 8-6 20-14 24-24 6-15-13-25-24-9Z" fill="#e79988" stroke="#8d5755"/>',
  gi:'<path d="M61 24v28c-12 5-20 17-16 31 5 20 38 27 51 9 13-19 1-33-12-39-10-5-14-15-14-29" fill="#e8bc83" stroke="#966e43"/><path d="M46 103c-16 1-15 16 0 16h44m-1-15H65" fill="none" stroke="#bd955e"/>',
  renal:'<path d="M46 32C23 30 20 68 34 83c9 9 22 5 23-5 1-9-11-9-11-17s11-6 13-13c2-8-5-15-13-16Zm48 0c23-2 26 36 12 51-9 9-22 5-23-5-1-9 11-9 11-17s-11-6-13-13c-2-8 5-15 13-16Z" fill="#c295a5" stroke="#805d73"/><path d="M50 65c16 12 7 26 16 38m24-38c-16 12-7 26-16 38" stroke="#a88a54" fill="none"/><path d="M58 103h24v7c0 15-24 15-24 0Z" fill="#e0c084" stroke="#a88a54"/>',
  neuro:'<path d="M84 114V96c19-12 27-31 19-51-9-23-41-28-60-11-11 10-14 25-12 38L22 86h13v18h23v10" fill="#c2c1df" stroke="#746d95"/><path d="M56 38c-10 0-17 10-12 18-8 7-3 18 6 20m18-39c-12-5-17 10-9 17-10 3-13 13-4 18m24-34c13 1 17 13 8 20 7 11 0 19-10 17m-7-22v26" fill="none" stroke="#7f789f"/>',
  msk:'<path d="M46 31c-9-7-18 4-13 12l27 28 14-14-28-26Zm29 47 27 29c8 8 19-2 13-11L88 65Z" fill="#ede0bf" stroke="#a18d65"/><path d="M59 56c-6-4-13 0-13 7s8 12 15 8l9-9c4-7-1-15-8-15s-10 7-3 9Zm26 25c7 5 14-1 13-8-1-7-9-11-15-7l-9 9c-4 6 0 14 7 15 7 1 13-6 4-9Z" fill="#a9c9c3" stroke="#527f78"/><path d="m51 84-7 7m17-7-1 11m18-40 7-7m-7 16 11-1" stroke="#789b92" fill="none"/>',
  heent:'<path d="M89 114V97c17-14 22-33 13-52-9-20-37-25-55-13-15 10-17 25-17 41L20 86h15v15h23v13" fill="#e8c8a8" stroke="#997b62"/><path d="M70 66c0-14 19-17 22-3 2 8-5 10-6 15-2 10-14 8-14-1m6-7c-2-6 6-10 8-5M41 59h10m-6-4v8M39 90h10" fill="none" stroke="#846b58"/>',
  skin:'<path d="M24 57c13-10 24 8 38 0s25 8 38 0 16-1 16-1v50H24Z" fill="#e7b6a1" stroke="#a17665"/><path d="M24 72c13-10 24 8 38 0s25 8 38 0 16-1 16-1v35H24Z" fill="#efd2b4" stroke="#a17665"/><path d="M73 36c-4 12-4 29 1 43 3 10-9 18-13 8-4-11 10-15 2-36m26 44 7-12m-7 3 12 2m-61 4 8-12" fill="none" stroke="#916c58"/><circle cx="43" cy="60" r="3" fill="#be7f70" stroke="none"/><circle cx="95" cy="62" r="3" fill="#be7f70" stroke="none"/>',
  sealed:'<rect x="37" y="23" width="66" height="94" rx="6" fill="#a8c1b5" stroke="#617f73"/><path d="M51 39h37M51 50h27" stroke="#edf2df"/><rect x="56" y="73" width="29" height="25" rx="4" fill="#f0d294" stroke="#8f825a"/><path d="M62 73v-8a9 9 0 0 1 18 0v8m-9 12v5" fill="none" stroke="#8f825a"/>',
  general:'<rect x="37" y="28" width="66" height="85" rx="8" fill="#a8c9bd" stroke="#628878"/><rect x="53" y="20" width="34" height="15" rx="5" fill="#e2d6a4" stroke="#958862"/><path d="M60 52h20m-10-10v20M51 79h38M51 93h29" stroke="#3f7062"/>',
 };
 const safe=Object.hasOwn(body,key)?key:'general';
 return `<svg class="system-illustration" data-organ="${safe}" viewBox="0 0 140 140" fill="none" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" focusable="false" aria-hidden="true"><circle cx="70" cy="70" r="63" fill="currentColor" opacity=".055" stroke="none"/>${body[safe]}</svg>`;
}
function updatePracticeGroups(){
 const grid=$('#stationGrid');if(!grid)return;
 grid.querySelectorAll('.station-system').forEach(group=>{const count=group.querySelectorAll('.station-card:not([hidden])').length;group.hidden=!count;group.querySelector('.system-count').textContent=count+' presentation'+(count===1?'':'s');});
 grid.dispatchEvent(new Event('pcm-selection-change'));
}
function groupPractice(grid,cases,reveal){
 const mode=reveal?'systems':'sealed';if(grid.dataset.grouping===mode)return;
 const selected=document.activeElement,cards=[...grid.querySelectorAll('.station-card')];
 if(!grid._stationOrder)grid._stationOrder=new Map(cards.map((card,i)=>[card.dataset.case,i]));
 const order=grid._stationOrder;
 cards.sort((a,b)=>(order.get(a.dataset.case)??99)-(order.get(b.dataset.case)??99));
 grid.replaceChildren();grid.dataset.grouping=mode;
 if(reveal){orderedSystems(cases).forEach((system,i)=>{const rows=cards.filter(card=>cases.find(c=>c.id===card.dataset.case)?.system===system);const group=document.createElement('section');group.className='station-system';group.dataset.system=system;group.setAttribute('role','group');group.setAttribute('aria-labelledby','stationSystem-'+i);group.innerHTML=`<div class="case-system-heading"><h3 id="stationSystem-${i}">${E(systemLabel(system))}</h3><span class="system-count"></span></div><div class="station-system-cards"></div>`;group.querySelector('.station-system-cards').append(...rows);grid.append(group);});}
 else grid.append(...cards);
 if(selected&&grid.contains(selected))selected.focus({preventScroll:true});
 updatePracticeGroups();
}
function groupedCaseLinks(cases,renderCard){return orderedSystems(cases).map((system,i)=>{const rows=cases.filter(c=>c.system===system);return `<section class="case-library-system" data-system="${E(system)}" aria-labelledby="caseLibrarySystem-${i}"><div class="case-system-heading"><h2 id="caseLibrarySystem-${i}">${E(systemLabel(system))}</h2><span class="system-count">${rows.length} presentation${rows.length===1?'':'s'}</span></div><div class="system-case-grid">${rows.map(renderCard).join('')}</div></section>`;}).join('');}
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
 const cases=context?.boot?.cases||window.pcmPortalCases?.()||[];
 grid.querySelectorAll('.station-card').forEach(card=>{
  let art=card.querySelector('.s-illustration');if(!art){art=document.createElement('span');art.className='s-illustration';card.prepend(art);}
  const c=cases.find(c=>c.id===card.dataset.case),key=reveal?family(c?.system):'sealed';
  if(art.dataset.kind!==key){art.dataset.kind=key;art.innerHTML=illustration(key);}
 });
 groupPractice(grid,cases,reveal);
 const system=$('#sysPick');if(system){system.hidden=true;system.disabled=!reveal;if(!reveal&&system.value){system.value='';system.dispatchEvent(new Event('change',{bubbles:true}));}}
 for(const id of ['skillFilter','variantChoice']){const el=$('#'+id);if(!el)continue;el.closest('label').hidden=!reveal;if(!reveal&&id==='skillFilter'&&el.value){el.value='';el.dispatchEvent(new Event('change',{bubbles:true}));}}
 let families=$('#portalFamilies');if(!families){families=document.createElement('div');families.id='portalFamilies';families.className='portal-families';families.setAttribute('aria-label','Filter by system');grid.before(families);}
 families.hidden=!reveal;
 if(reveal&&families.dataset.ready!=='true'){
  families.innerHTML=`<button type="button" class="portal-family selected" data-family="" aria-pressed="true">${icon('practice')}<span>All systems</span></button>`+orderedSystems(cases).map(s=>`<button type="button" class="portal-family" data-family="${E(s)}" aria-pressed="false">${illustration(family(s))}<span>${E(s)}</span></button>`).join('');families.dataset.ready='true';
  families.querySelectorAll('button').forEach(b=>b.onclick=()=>{system.value=b.dataset.family;system.dispatchEvent(new Event('change',{bubbles:true}));});
  system?.addEventListener('change',()=>families.querySelectorAll('button').forEach(b=>{const selected=b.dataset.family===system.value;b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',String(selected));}));
 }
 updatePracticeGroups();
}
function setupNavigation(){
 const header=$('.topbar');
 if(header){const measure=()=>document.documentElement.style.setProperty('--portal-header-height',header.getBoundingClientRect().height+'px');headerObserver?.disconnect();if(window.ResizeObserver){headerObserver=new ResizeObserver(measure);headerObserver.observe(header);}measure();}

 const skip=$('.skip-link');if(skip)skip.onclick=e=>{e.preventDefault();const view=$('#view');view?.focus({preventScroll:true});view?.scrollIntoView({block:'start',behavior:'instant'});};
 const bar=$('.workspace-nav');if(bar)bar.innerHTML=[['home','Home'],['practice','Practice'],['cases','Cases & print'],['progress','Progress'],['scoring','Scoring']].map(([key,label])=>`<button class="btn ghost sm" type="button" data-destination="${key}">${icon(key)}<span>${label}</span></button>`).join('');
 document.querySelectorAll('[data-destination]').forEach(b=>b.onclick=()=>window.pcmNavigate?.(b.dataset.destination));
 $('#btnBrand')?.addEventListener('click',()=>window.pcmNavigate?.('home'));
}
window.pcmPortal={render,decoratePractice,updatePracticeGroups,orderedSystems,systemLabel,family,groupedCaseLinks,icon,illustration,setupNavigation,nav,invalidate:()=>{restoreVoicePanel();generation++;}};
window.addEventListener('pcm-lobby-ready',()=>decoratePractice(window.pcmPortalMode?.().mode,window.pcmPortalMode?.().reveal));
})();
