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
 scribbi:'<path d="M4 5.5h16v10.5H9.5L4 20z"/><path d="m14.5 7.5 2 2-4.5 4.5H10v-2z"/>',
 chat:'<path d="M6.5 3H5v5.5a4.5 4.5 0 0 0 9 0V3h-1.5"/><path d="M9.5 13v1.5a4.5 4.5 0 0 0 9 0V12"/><circle cx="18.5" cy="10" r="2"/>',
 cases:'<path d="M7 3h8l4 4v14H7z"/><path d="M15 3v4h4M10 12h6m-6 4h6"/>',
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
 grid.querySelectorAll('.station-system').forEach(group=>{const count=group.querySelectorAll('.station-card:not([hidden])').length;group.hidden=!count;group.querySelector('.system-count').textContent=count+' case'+(count===1?'':'s');});
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
function groupedCaseLinks(cases,renderCard){return orderedSystems(cases).map((system,i)=>{const rows=cases.filter(c=>c.system===system);return `<section class="case-library-system" data-system="${E(system)}" aria-labelledby="caseLibrarySystem-${i}"><div class="case-system-heading"><h2 id="caseLibrarySystem-${i}">${E(systemLabel(system))}</h2><span class="system-count">${rows.length} case${rows.length===1?'':'s'}</span></div><div class="system-case-grid">${rows.map(renderCard).join('')}</div></section>`;}).join('');}
const phaseLabel={briefing:'At the doorway',encounter:'In the room',organize:'Organizing',note:'Writing the SOAP note',submitted:'Feedback ready'};
const modeLabel={guided:'Guided encounter',coached:'Coached encounter',independent:'Independent practice',rehearsal:'Exam rehearsal',practice:'Guided encounter',drill:'Coached encounter'};
const count=(n,one,many)=>`${n} ${n===1?one:(many||one+'s')}`;
// DocKnock holds two features, Chat CSE and Scribbi, plus Home and Scores.
// Every route belongs to one top-level tab; Chat CSE, Scribbi and Scores
// also get a feature bar under the top bar with their own sections.
const TABS=[['home','Home','home'],['practice','Chat CSE','chat'],['scribbi','Scribbi','scribbi'],['scores','Scores','progress']];
const TAB_OF={home:'home',practice:'practice',cases:'practice',learn:'practice',scribbi:'scribbi',progress:'scores',scores:'scores',scoring:'scores'};
const SECTIONS={
 practice:{cls:'is-chat',title:'Chat CSE',tagline:'Patient encounters and SOAP notes',items:[['practice','Encounters'],['learn','Worked examples'],['cases','Printable cases']]},
 scribbi:{cls:'is-scribbi',title:'Scribbi',tagline:'AI scribe review',jumps:[['.sb-setup','Start a review'],['#sbStatsHead','Your record'],['#sbGuideHead','Field guide']]},
 scores:{cls:'is-scores',title:'Scores',tagline:'Chat CSE encounters and Scribbi reviews',items:[['scores','Your scores'],['scoring','How scoring works']]},
};
const TITLES={practice:'Encounters · Chat CSE',learn:'Worked examples · Chat CSE',cases:'Printable cases · Chat CSE',scribbi:'Scribbi',progress:'Your scores · Scores',scores:'Your scores · Scores',scoring:'How scoring works · Scores'};
function sectionMark(tab){
 if(tab==='practice')return '<img class="fb-mark" src="brand/chat-cse-64.png" alt="" aria-hidden="true">';
 if(tab==='scribbi')return `<span class="fb-mark fb-mascot" aria-hidden="true">${window.pcmScribbi?.mascot?.('happy','')||''}</span>`;
 return `<span class="fb-mark fb-icon" aria-hidden="true">${icon('progress')}</span>`;
}
function featureBar(kind,tab){
 const bar=$('#featureBar');if(!bar)return;
 const sec=SECTIONS[tab],session=document.body.dataset.workspace==='encounter',round=tab==='scribbi'&&!/^#scribbi\/?$/.test(location.hash);
 if(!sec||session||round){bar.hidden=true;bar.dataset.tab='';bar.replaceChildren();return;}
 const current=kind==='progress'?'scores':kind;
 if(bar.dataset.tab!==tab){
  bar.dataset.tab=tab;bar.className='feature-bar '+sec.cls;
  const items=(sec.items||[]).map(([key,label])=>`<button type="button" class="fb-tab" data-destination="${key}">${label}</button>`).join('')+(sec.jumps?.length?'<span class="fb-onpage">On this page</span>':'')+(sec.jumps||[]).map(([target,label])=>`<button type="button" class="fb-tab fb-jump" data-jump="${target}">${label}</button>`).join('');
  bar.setAttribute('aria-label',sec.title+' sections');
  bar.innerHTML=`<div class="fb-inner"><div class="fb-id">${sectionMark(tab)}<span><b>${sec.title}</b><small>${sec.tagline}</small></span></div><div class="fb-tabs">${items}</div></div>`;
  const tabs=bar.querySelector('.fb-tabs'),fade=()=>{const more=tabs.scrollWidth-tabs.clientWidth;tabs.dataset.fade=more<=2?'none':tabs.scrollLeft<=2?'right':tabs.scrollLeft>=more-2?'left':'both';};tabs.addEventListener('scroll',fade,{passive:true});requestAnimationFrame(fade);
  bar.querySelectorAll('[data-destination]').forEach(b=>b.onclick=()=>window.pcmNavigate?.(b.dataset.destination));
  bar.querySelectorAll('[data-jump]').forEach(b=>b.onclick=()=>document.querySelector(b.dataset.jump)?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'}));
 }
 bar.querySelectorAll('[data-destination]').forEach(b=>b.setAttribute('aria-current',b.dataset.destination===current?'page':'false'));
 bar.hidden=false;
}
function nav(kind){
 const tab=TAB_OF[kind]||kind;document.body.dataset.tab=tab;
 document.querySelectorAll('.workspace-nav [data-destination]').forEach(b=>{const on=b.dataset.destination===tab;b.setAttribute('aria-current',on?'page':'false');if(on&&b.parentElement&&b.parentElement.scrollWidth>b.parentElement.clientWidth)b.scrollIntoView({block:'nearest',inline:'center'});});
 const bar=$('.workspace-nav');if(bar)bar.dispatchEvent(new Event('scroll'));
 featureBar(kind,tab);
 if(document.body.dataset.workspace!=='encounter')setTitle(TITLES[kind]);
}
// Page titles read most specific first and always end with the app name.
function setTitle(...parts){document.title=[...parts.flat(),'DocKnock'].filter(Boolean).join(' · ');
}
function buttons(root){root.querySelectorAll('[data-portal-go]').forEach(b=>b.onclick=()=>{const jump=b.dataset.portalJump;window.pcmNavigate?.(b.dataset.portalGo);if(jump){const t=Date.now(),seek=()=>{const el=document.querySelector(jump);if(el)el.scrollIntoView({block:'start'});else if(Date.now()-t<4000)setTimeout(seek,120);};setTimeout(seek,120);}});root.querySelectorAll('[data-resume]').forEach(b=>b.onclick=()=>{location.hash='#/'+b.dataset.resume;});}
function when(ms){const d=new Date(ms),now=new Date();
 return d.toDateString()===now.toDateString()
  ? d.toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'})
  : d.toLocaleDateString(undefined,{month:'short',day:'numeric'});}
function heading(kicker,title,detail){return `<header class="portal-heading"><div>${kicker?`<span class="portal-kicker">${kicker}</span>`:''}<h1>${title}</h1>${detail?`<p>${detail}</p>`:''}</div></header>`;}
function completedCount(data){const counts=data.progress?.completed_by_mode;if(counts&&Object.keys(counts).length)return Object.values(counts).reduce((sum,n)=>sum+(Number(n)||0),0);return (data.sessions||[]).filter(s=>s.phase==='submitted').length;}
function continueItem({feature,kicker,art,title,detail,action,resume,href,ts}){
 const target=resume?`data-resume="${E(resume)}"`:`data-href="${E(href)}"`;
 return `<article class="dk-continue-item is-${feature}" data-ts="${Number(ts)||0}"><span class="dk-ci-art" aria-hidden="true">${art}</span><span class="dk-ci-text"><small>${E(kicker)}</small><b>${E(title)}</b><span>${E(detail)}</span></span><button class="btn ${feature==='chat'?'portal-primary':'portal-scribbi'} dk-ci-go" ${target} aria-label="${E(action+': '+title)}">${E(action)} <span aria-hidden="true">→</span></button></article>`;
}
// Show the newest open work from both features first, at most four, with a way to see the rest.
function sortContinue(){
 const list=$('#dkContinueList'),section=$('#dkContinue');if(!list||!section)return;
 const items=[...list.querySelectorAll('.dk-continue-item')].sort((a,b)=>Number(b.dataset.ts)-Number(a.dataset.ts));
 list.replaceChildren(...items);items.forEach((item,i)=>{item.hidden=i>=4;});
 section.hidden=!items.length;
 const more=$('#dkContinueMore');if(more){more.hidden=items.length<=4;more.querySelector('b').textContent=String(items.length);}
}
function home(data){
 const rows=data.sessions||[],cases=data.cases||[],progress=data.progress||{},coverage=(progress.completed_cases||[]).length;
 // Everything still open, named by case and level so a student with several
 // saved encounters can tell which one each button opens. Exam rehearsal
 // stays sealed here exactly as it does on Scores.
 const open=rows.filter(s=>s.phase!=='submitted');
 const chat=open.map(s=>{const c=cases.find(c=>c.id===s.case_id),sealed=s.case_title==='Exam rehearsal';
  return continueItem({feature:'chat',kicker:'Chat CSE · '+(modeLabel[s.learning_mode]||'Encounter'),art:illustration(sealed?'sealed':family(c?.system)),title:sealed?`Exam rehearsal · ${c?.station_label||'sealed case'}`:(c?.title||'Saved encounter'),detail:`${phaseLabel[s.phase]||'In progress'} · started ${when(s.created_at)}`,action:s.phase==='note'?'Resume your note':'Resume',resume:s.id,ts:s.created_at});}).join('');
 const cont=`<section class="dk-continue" id="dkContinue" aria-labelledby="dkContinueHead"${chat?'':' hidden'}><div class="portal-section-heading"><h2 id="dkContinueHead">Continue where you left off</h2><button class="btn ghost" id="dkContinueMore" data-portal-go="scores" hidden>See all <b></b> in progress <span aria-hidden="true">→</span></button></div><div class="dk-continue-list" id="dkContinueList">${chat}</div></section>`;
 const modes=`<section class="portal-modes" aria-label="Choose how to practice">
  <article class="portal-mode is-chat"><span class="portal-mode-art" aria-hidden="true">${illustration('cardio')}</span><span class="portal-kicker">Chat CSE · Patient encounter</span><h2>See the patient.</h2><p>Interview and examine a virtual patient, then write your SOAP note and get feedback on the evidence you actually obtained.</p><div class="portal-mode-actions"><button class="btn portal-primary" data-portal-go="practice">Choose an encounter <span aria-hidden="true">→</span></button></div><div class="dk-mode-links"><button type="button" data-portal-go="learn">Worked examples</button><button type="button" data-portal-go="cases">Printable cases</button></div><span class="portal-mode-foot">${count(cases.length,'case')} · 4 levels of support</span></article>
  <article class="portal-mode is-scribbi"><span class="portal-mode-art portal-mode-mascot" aria-hidden="true">${window.pcmScribbi?.mascot?.('happy','is-bobbing is-listening')||''}</span><span class="portal-kicker">Scribbi · AI scribe review</span><h2>Review the AI scribe.</h2><p>Watch a patient visit, or lead it yourself, while Scribbi listens. Then catch what its note got wrong, add what it couldn't feel, and sign.</p><div class="portal-mode-actions" id="portalScribbiActions"><button class="btn portal-scribbi" data-portal-go="scribbi">Start a review <span aria-hidden="true">→</span></button></div><div class="dk-mode-links"><button type="button" data-portal-go="scribbi" data-portal-jump="#sbGuideHead">Field guide</button></div><span class="portal-mode-foot" id="portalScribbiFoot">${count(cases.length,'case')} · 3 review levels</span></article>
 </section>`;
 const cell=(value,label,id,help)=>`<div${help?` title="${E(help)}"`:''}><b${id?` id="${id}"`:''}>${value}</b><small${id?` id="${id}Label"`:''}>${label}</small></div>`;
 const done=completedCount(data),unassisted=progress.conditions?.independent||0;
 const snapshot=`<section class="dk-snapshot" aria-labelledby="dkScoresHead"><div class="portal-section-heading"><h2 id="dkScoresHead">Your scores</h2><button class="btn ghost" data-portal-go="scores">See all scores <span aria-hidden="true">→</span></button></div><div class="dk-snapshot-groups">
  <div class="dk-snap-group is-chat"><h3>Chat CSE</h3><div class="dk-snapshot-grid">${cell(done,done===1?'completed encounter':'completed encounters')}${cell(`${coverage}<small> / ${cases.length}</small>`,'cases completed')}${cell(unassisted,unassisted===1?'unassisted encounter':'unassisted encounters','','Submitted without cues, hints or answer materials')}</div></div>
  <div class="dk-snap-group is-scribbi"><h3>Scribbi</h3><div class="dk-snapshot-grid">${cell('0','signed notes','dkScribbiSigned')}${cell('–','average score, out of 100','dkScribbiAvg')}${cell('–','of mistakes caught','dkScribbiCatch')}</div></div>
 </div></section>`;
 return `<div class="portal-workspace dk-home">${heading('Clinical skills practice','What are you practicing today?','Two ways to practice: see the patient yourself in Chat CSE, or review the note an AI scribe wrote in Scribbi. Free, with no account; your work is saved only in this browser.')}<div class="portal-dashboard dk-home-stack">${cont}${modes}${snapshot}</div></div>`;
}
async function fillScribbi(token){
 const info=await window.pcmScribbi?.summary?.();if(!info||token!==generation)return;
 const st=info.stats||{};
 const set=(id,value)=>{const el=document.getElementById(id);if(el&&value!=null&&value!=='')el.textContent=value;};
 set('dkScribbiSigned',String(st.rounds||0));set('dkScribbiSignedLabel',st.rounds===1?'signed note':'signed notes');set('dkScribbiAvg',st.average!=null?String(st.average):'–');set('dkScribbiCatch',st.catch_rate!=null?st.catch_rate+'%':'–');
 // While an unassisted encounter is open Scribbi is paused; say which one and link to it.
 if(info.locked?.blocked){
  const first=(info.locked.attempts||[])[0],actions=document.getElementById('portalScribbiActions');
  if(actions&&first)actions.innerHTML=`<p class="dk-pause">Paused while your ${E(first.station||'')} encounter is open, because Scribbi shows complete notes.</p><button class="btn portal-scribbi" data-resume="${E(first.id)}">Go to that encounter <span aria-hidden="true">→</span></button>`;
  buttons(actions||document.createElement('div'));
  sortContinue();return;
 }
 const mascot=window.pcmScribbi?.mascot?.('happy','')||'';
 const items=(info.open_visits||[]).map(v=>continueItem({feature:'scribbi',kicker:'Scribbi · Visit',art:mascot,title:v.title||'Your visit',detail:`Your visit with ${String(v.patient_name||'your patient').split(/\s+/)[0]} · started ${when(v.created_at)}`,action:'Back to the visit',href:'#/'+v.id,ts:v.created_at}))
  .concat((info.recent||[]).filter(r=>r.status==='reviewing').map(r=>continueItem({feature:'scribbi',kicker:`Scribbi · ${r.mode_label||'Coached'} review`,art:mascot,title:r.title||'Scribbi review',detail:`Not yet signed · started ${when(r.created_at)}`,action:'Resume review',href:'#scribbi/r/'+r.id,ts:r.created_at})));
 const list=document.getElementById('dkContinueList');
 if(list&&items.length){list.insertAdjacentHTML('beforeend',items.join(''));list.querySelectorAll('[data-href]').forEach(b=>b.onclick=()=>{location.hash=b.dataset.href;});}
 sortContinue();
}
// How Scribbi scores a review (pcmcse/scribbi/review.py is the authority).
function scribbiScoring(){return `<div class="portal-card dk-scribbi-scoring"><h2>Scribbi: how your review is scored</h2><p>Scribbi plants its mistakes, so it holds the answer key for every draft. A review is scored out of 100.</p><ul>
 <li><b>Each planted mistake is one item, and so is the hands-on finding</b> (the structural exam Scribbi couldn't feel).</li>
 <li><b>Fixed:</b> the mistake is gone and the right information is there, for full credit. <b>Caught:</b> the mistake is gone but the right information is missing, for half. <b>Missed:</b> none.</li>
 <li><b>Breaking what was right costs half an item:</b> removing or changing a correct line, or adding an exam, history or drug the visit doesn't support.</li>
 <li><b>Fewer items, bigger stakes:</b> the score is the share of items you earned, so when a draft has only one or two, each counts for more. If there is nothing to find at all, each broken line or unsupported addition costs 20 points.</li>
 <li><b>Hints</b> at Scribbi's Coached level cost 5 points each.</li>
 <li><b>Safe to sign</b> only when no mistake that could change care was missed and nothing unsupported was added. Three stars need 90 or more and a safe note; two need 70; one needs 40.</li>
</ul></div>`;}
async function render(kind,ctx){
 restoreVoicePanel();context=ctx;const token=++generation;nav(kind);
 ctx.view.innerHTML='<div class="portal-workspace"><p class="portal-loading" role="status">Loading…</p></div>';
 let data=await ctx.api('/api/bootstrap');if(token!==generation)return;
 if(data.error){ctx.view.innerHTML=`<div class="portal-workspace"><section class="portal-side-card"><h1>This page didn't load</h1><p>${E(data.message||'Your saved encounters and reviews are safe in this browser. Try again, or reload the page.')}</p><button class="btn primary" id="portalRetry">Try again</button></section></div>`;$('#portalRetry').onclick=()=>render(kind,ctx);return;}
 ctx.onData(data);
 if(kind==='home'){ctx.view.innerHTML=home(data);sortContinue();fillScribbi(token);}
 else if(kind==='progress'||kind==='scores'){ctx.view.innerHTML=`<div class="portal-workspace" id="progressWorkspace">${heading('','Your scores','Your Chat CSE encounters and Scribbi reviews, saved in this browser. Retrying never changes an original score.')}<div class="disclosure open" id="extraPanel" data-open="past">${ctx.past({scores:true})}</div><div id="scribbiScoresSlot"></div><section class="dk-reset">${ctx.reset()}</section></div>`;ctx.wirePast();window.pcmScribbi?.progressPanel?.(document.getElementById('scribbiScoresSlot'));}
 else if(kind==='scoring'){ctx.view.innerHTML=`<div class="portal-workspace portal-reading dk-scoring">${heading('','How scoring works','Chat CSE scores the SOAP note you write. Scribbi scores your review of the note it drafted.')}<div class="dk-score-switch" role="group" aria-label="Jump to a scoring guide"><button type="button" class="is-chat" data-scroll="#dkScoreChat">Chat CSE · your SOAP note</button><button type="button" class="is-scribbi" data-scroll="#dkScoreScribbi">Scribbi · your review</button></div><section class="dk-score-part is-chat" id="dkScoreChat">${ctx.scoring()}</section><section class="dk-score-part is-scribbi" id="dkScoreScribbi">${scribbiScoring()}</section></div>`;
  ctx.view.querySelectorAll('[data-scroll]').forEach(b=>b.onclick=()=>document.querySelector(b.dataset.scroll)?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'}));}
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
 const bar=$('.workspace-nav');if(bar)bar.innerHTML=TABS.map(([key,label,art])=>`<button class="btn ghost sm" type="button" data-destination="${key}">${icon(art)}<span>${label}</span></button>`).join('');
 document.querySelectorAll('[data-destination]').forEach(b=>b.onclick=()=>window.pcmNavigate?.(b.dataset.destination));
 // On a phone the destinations scroll in one row; fade only the edge that has more.
 if(bar){const fade=()=>{const more=bar.scrollWidth-bar.clientWidth;bar.dataset.fade=more<=2?'none':bar.scrollLeft<=2?'right':bar.scrollLeft>=more-2?'left':'both';};bar.addEventListener('scroll',fade,{passive:true});window.addEventListener('resize',fade);fade();}
 $('#btnBrand')?.addEventListener('click',()=>window.pcmNavigate?.('home'));
}
window.pcmPortal={render,decoratePractice,updatePracticeGroups,orderedSystems,systemLabel,family,groupedCaseLinks,icon,illustration,setupNavigation,nav,invalidate:()=>{restoreVoicePanel();generation++;}};
// After a reset, Chat CSE's list redraws itself; redraw Scribbi's beside it.
window.addEventListener('pcm-progress-reset',()=>{const slot=document.getElementById('scribbiScoresSlot');if(slot){slot.innerHTML='';window.pcmScribbi?.progressPanel?.(slot);}});
window.addEventListener('pcm-lobby-ready',()=>decoratePractice(window.pcmPortalMode?.().mode,window.pcmPortalMode?.().reveal));
})();
