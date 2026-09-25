/* Scribbi: review the AI scribe's draft before you sign.

   Routes (hash):   #scribbi                home: modes, patients, stats, field guide
                    #scribbi/r/<id>/visit   watch the demonstrated visit (scribbi-visit.js)
                    #scribbi/r/<id>         a review (or its debrief once signed)
   A student can also LEAD the visit in the Chat CSE room (a Scribbi visit
   session); finishing it hands the encounter to Scribbi (finishVisit).

   The engine owns everything that matters: which mistakes were planted, the
   answer key, grading, timing. This file renders what the engine returns,
   keeps the student's edits, and autosaves them. A signed note is frozen on
   the engine side, so a late save can never change a result. */
(()=>{'use strict';
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const $=(s,r)=>(r||document).querySelector(s);
const $$=(s,r)=>Array.from((r||document).querySelectorAll(s));
const view=()=>document.getElementById('view');
const call=(path,body)=>typeof api==='function'?api(path,body):fetch(path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>r.json()).catch(e=>({error:'offline',message:e.message}));
const clockNow=()=>typeof now==='function'?now():Date.now();
const say=msg=>{if(typeof announce==='function')announce(msg);};
const pop=msg=>{if(typeof toast==='function')toast(msg);};
const confirmBox=(msg,opts)=>window.pcmConfirmChoice?window.pcmConfirmChoice(msg,opts):Promise.resolve(window.confirm(msg));
const store={
 get(k){try{return JSON.parse(localStorage.getItem('pcmcse.scribbi.'+k));}catch(e){return null;}},
 set(k,v){try{localStorage.setItem('pcmcse.scribbi.'+k,JSON.stringify(v));return true;}catch(e){return false;}},
 del(k){try{localStorage.removeItem('pcmcse.scribbi.'+k);}catch(e){}}
};
const reduced=()=>{try{if(JSON.parse(localStorage.getItem('pcmcse.reducedMotion')))return true;}catch(e){}return !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;};
const mmss=ms=>{const t=Math.max(0,Math.round((ms||0)/1000));return Math.floor(t/60)+':'+String(t%60).padStart(2,'0');};
const plural=(n,one,many)=>n+' '+(n===1?one:(many||one+'s'));
const firstName=name=>String(name||'Patient').split(/\s+/)[0];
// "22:09" of visit time reads like a clock; say "22 min".
const visitLength=t=>{const m=/^(\d+):(\d\d)$/.exec(t||'');if(!m)return '';const min=Math.round((+m[1]*60+ +m[2])/60);return min<1?'under a minute':min+' min';};

/* ---------- icons ---------- */
const I={
 stethoscope:'<path d="M6 3v5a4 4 0 0 0 8 0V3M10 12v3a5 5 0 0 0 10 0v-2"/><circle cx="20" cy="11" r="2"/>',
 question:'<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7M12 17h.01"/>',
 flip:'<path d="M7 7h11l-3-3M17 17H6l3 3"/>',
 hash:'<path d="M5 9h14M5 15h14M10 4 8 20M16 4l-2 16"/>',
 people:'<circle cx="8" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3 20c.6-3.6 2.6-6 5-6s4.4 2.4 5 6M14 20c.3-2.8 1.5-4.6 3-4.6s2.7 1.8 3 4.6"/>',
 gap:'<path d="M4 7h16M4 12h5m6 0h5M4 17h16"/><path d="M11 10.5h2" stroke-dasharray="1 2"/>',
 hand:'<path d="M8 13V6a1.5 1.5 0 0 1 3 0v6m0-7a1.5 1.5 0 0 1 3 0v7m0-5.5a1.5 1.5 0 0 1 3 0V14c0 4-2.5 7-6.5 7-2.6 0-4.3-1.3-5.8-3.7L3.4 14.6a1.5 1.5 0 0 1 2.5-1.6L8 15"/>',
 anchor:'<circle cx="12" cy="5" r="2"/><path d="M12 7v14M5 13a7 7 0 0 0 14 0M8 11h8"/>',
 ghost:'<path d="M6 20V10a6 6 0 0 1 12 0v10l-2-1.5-2 1.5-2-1.5-2 1.5-2-1.5z"/><circle cx="10" cy="10" r=".8"/><circle cx="14" cy="10" r=".8"/>',
 alert:'<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
 eye:'<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
 check:'<path d="m5 12 4 4 10-10"/>',
 shield:'<path d="M12 3 4 6v6c0 5 3.4 8.4 8 9 4.6-.6 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
 seal:'<circle cx="12" cy="10" r="6"/><path d="m9 15-2 6 5-2 5 2-2-6"/>',
 clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 x:'<path d="M6 6l12 12M18 6 6 18"/>',
 pencil:'<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
 undo:'<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
 search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
 plus:'<path d="M12 5v14M5 12h14"/>',
 book:'<path d="M12 6c-3-2-7-2-9-1v14c2-1 6-1 9 1 3-2 7-2 9-1V5c-2-1-6-1-9 1zm0 0v14"/>',
 compass:'<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5z"/>',
 target:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
 dice:'<rect x="4" y="4" width="16" height="16" rx="3"/><circle cx="9" cy="9" r="1"/><circle cx="15" cy="15" r="1"/><circle cx="15" cy="9" r="1"/><circle cx="9" cy="15" r="1"/>',
 bulb:'<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.8.8 1 1.5 1 2.5h6c0-1 .2-1.7 1-2.5A6 6 0 0 0 12 3z"/>',
 pen:'<path d="m15 5 4 4L8 20H4v-4z"/>',
 chat:'<path d="M4 5h16v11H9l-5 4z"/>',
 arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',
 home:'<path d="M4 11 12 4l8 7v9h-6v-6h-4v6H4z"/>',
 star:'<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
};
const ic=(k,cls)=>`<svg class="sb-ic ${cls||''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${I[k]||I.pen}</svg>`;
const MODE_ICON={learn:'bulb',coached:'compass',solo:'target'};
/* How the student sees the visit before Scribbi drafts it. */
const STYLES=[
 {key:'watch',label:'Watch it',tag:'Like a video',detail:'The demonstrated visit plays out with voices, captions and every exam. Pause, rewind, or speed it up.',quick:'Watch a random visit',start:'Start the visit'},
 {key:'lead',label:'Lead it',tag:'You’re the clinician',detail:'Ask your own questions and choose your own exams in the patient room. Scribbi writes the note from what you did.',quick:'Lead a random visit',start:'Enter the room'},
 {key:'read',label:'Read it',tag:'Straight to the note',detail:'Skip the visit. Check Scribbi’s draft against the visit transcript.',quick:'Open a random draft',start:'Open the draft'},
];
const STYLE_ICON={watch:'eye',lead:'stethoscope',read:'book'};
const styleOf=k=>STYLES.find(x=>x.key===k)||STYLES[0];
const own=p=>p.source==='attempt'||p.source==='visit';
function heroMeta(){const sel=homeSel;return (sel.style==='read'?'Straight to the draft · ':sel.style==='lead'?'You lead the visit · ':'5–12 minutes to watch · ')+modeLabel(sel.mode)+' level';}
function visitResume(d){
 const v=(d.open_visits||[])[0];if(!v||d.locked?.blocked)return '';
 return `<div class="sb-resume sb-resume-visit"><div><b>Your visit with ${E(firstName(v.patient_name))} is still open</b><span>${E(v.title)} · Scribbi is waiting to write the note</span></div><button class="sb-btn sb-primary sb-sm" data-resume-visit="${E(v.id)}">Back to the visit ${ic('arrow')}</button></div>`;
}
const TYPE_ICON={fabricated_exam:'stethoscope',fabricated_history:'question',flipped:'flip',wrong_detail:'hash',misattributed:'people',dropped:'gap',hands_on:'hand',anchored_dx:'anchor',unsupported_dx:'ghost',allergy_conflict:'alert'};
const BADGE_ICON={eagle_eye:'eye',clean_hands:'check',hands_on:'hand',safety_net:'shield',trust_but_verify:'seal',clinic_pace:'clock'};

/* ---------- the mascot ---------- */
let mascotN=0;
function mascot(mood='happy',extra=''){
 const id='sbg'+(++mascotN);
 return `<svg class="sb-mascot mood-${mood} ${extra}" viewBox="0 0 120 120" aria-hidden="true" focusable="false"><defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8b80ff"/><stop offset="1" stop-color="#4a3fd4"/></linearGradient></defs>
 <path class="sb-wave" d="M19 40c-5 6-5 14 0 20" stroke="#b9b3ff" stroke-width="3.5" fill="none" stroke-linecap="round"/><path class="sb-wave w2" d="M10 34c-9 10-9 23 0 32" stroke="#b9b3ff" stroke-width="3.5" fill="none" stroke-linecap="round"/>
 <path d="M61 17c24 0 41 16 41 37s-17 37-41 37c-6 0-11-1-16-3l-15 9 4-15C26 76 20 66 20 54c0-21 17-37 41-37Z" fill="url(#${id})"/>
 <ellipse cx="50" cy="33" rx="15" ry="6.5" fill="#fff" opacity=".2"/>
 <g class="sb-eyes-open"><ellipse cx="49" cy="52" rx="7.4" ry="8.8" fill="#fff"/><ellipse cx="73" cy="52" rx="7.4" ry="8.8" fill="#fff"/><circle class="sb-pupil" cx="50" cy="54" r="3.8" fill="#1c1848"/><circle class="sb-pupil" cx="74" cy="54" r="3.8" fill="#1c1848"/><circle cx="51.3" cy="52.4" r="1.2" fill="#fff"/><circle cx="75.3" cy="52.4" r="1.2" fill="#fff"/></g>
 <g class="sb-eyes-closed"><path d="M42.5 54q6.5-7 13 0M66.5 54q6.5-7 13 0" stroke="#fff" stroke-width="3.4" fill="none" stroke-linecap="round"/></g>
 <circle cx="40" cy="64" r="4.2" fill="#ff9fbe" opacity=".55"/><circle cx="82" cy="64" r="4.2" fill="#ff9fbe" opacity=".55"/>
 <path class="sb-mouth-smile" d="M54 66q7 7.5 14 0" stroke="#1c1848" stroke-width="3.2" fill="none" stroke-linecap="round"/>
 <ellipse class="sb-mouth-oops" cx="61" cy="68.5" rx="4" ry="5" fill="#1c1848"/>
 <g class="sb-quill"><path d="M100 18c9 3 12 13 6 22-5 8-12 13-19 18l-3-3c4-7 8-14 10-21 2-6 3-11 6-16Z" fill="#fff8e8" stroke="#dcc9a0" stroke-width="1.6"/><path d="M103 24c-3 8-7 16-12 23" stroke="#dcc9a0" stroke-width="1.2" fill="none"/><path d="m84 56-3 7 6-4z" fill="#28265f"/></g>
 <g class="sb-sparkles" fill="#ffd66b"><path d="M27 18l2 5 5 2-5 2-2 5-2-5-5-2 5-2z"/><path d="M102 74l1.5 3.5 3.5 1.5-3.5 1.5-1.5 3.5-1.5-3.5-3.5-1.5 3.5-1.5z"/></g></svg>`;
}

/* ---------- state ---------- */
let HOME=null,R=null,gen=0,homeSel=null;
const SYS_ORDER=['Cardiovascular','Cardiopulmonary','Respiratory','Gastrointestinal','Renal / Genitourinary','Neurologic','Musculoskeletal','HEENT','Skin'];
const sortSystems=list=>[...new Set(list)].sort((a,b)=>{const x=SYS_ORDER.indexOf(a),y=SYS_ORDER.indexOf(b);return (x<0?99:x)-(y<0?99:y)||a.localeCompare(b);});
const art=system=>window.pcmPortal?.illustration?.(window.pcmPortal.family?.(system)||'general')||'';

function render(hash){
 const route=String(hash||'').replace(/^#?\/?/,'');
 teardownRound();
 window.pcmScribbiVisit?.close();
 document.body.dataset.workspace='scribbi';
 window.scrollTo({top:0,behavior:'instant'});
 const visit=route.match(/^scribbi\/r\/([A-Za-z0-9]+)\/visit$/);
 if(visit&&window.pcmScribbiVisit)return window.pcmScribbiVisit.open(visit[1]);
 const m=route.match(/^scribbi\/r\/([A-Za-z0-9]+)$/);
 if(m)return openRound(m[1]);
 return renderHome();
}

/* ======================================================================
   Home
   ====================================================================== */
async function renderHome(){
 const token=++gen;
 view().innerHTML=`<div class="sb-shell"><p class="sb-muted" role="status" style="padding:60px 0">Opening Scribbi…</p></div>`;
 const data=await call('/api/scribbi');
 if(token!==gen)return;
 if(data.error){return errorView('Scribbi could not open',data.message||data.error,()=>renderHome());}
 HOME=data;
 const prefs=store.get('prefs')||{};
 homeSel=homeSel||{mode:prefs.mode&&data.modes.some(m=>m.key===prefs.mode)?prefs.mode:'learn',timed:!!prefs.timed,style:STYLES.some(x=>x.key===prefs.style)?prefs.style:'watch',system:'',patient:null,variant:'random'};
 paintHome();
}
function paintHome(){
 const d=HOME,s=d.stats||{},sel=homeSel;
 const unfinished=(d.recent||[]).find(r=>r.status==='reviewing');
 // Name the encounter that pauses Scribbi and link straight to it.
 const held=d.locked?.attempts||[],first=held[0],where=first?`${first.station||'Station'}, ${({briefing:'at the doorway',encounter:'in the room',organize:'organizing',note:'writing the note'})[first.phase]||'in progress'}`:'';
 const lock=d.locked?.blocked?`<section class="sb-lock" role="alert">${mascot('oops')}<div><h2>Scribbi is paused while you have an unassisted encounter open.</h2><p>Scribbi shows complete visits and notes, which would give away answers. Submit your open Independent or Exam rehearsal encounter${held.length>1?'s':''}${where?` (${E(where)})`:''}, or switch ${held.length>1?'them':'it'} to assisted practice. Your timer and your work are kept either way.</p><div class="sb-hero-actions">${first?`<button class="sb-btn sb-primary" data-open-attempt="${E(first.id)}">Go to that encounter</button>`:''}<button class="sb-btn" id="sbConvert">Switch to assisted practice</button></div></div></section>`:'';
 const resume=unfinished&&!d.locked?.blocked?`<div class="sb-resume"><div><b>Pick up where you left off</b><span>${E(unfinished.title)} · ${E(unfinished.mode_label)} review, not yet signed</span></div><button class="sb-btn sb-primary sb-sm" data-open="${E(unfinished.id)}">Resume review ${ic('arrow')}</button></div>`:'';
 const systems=sortSystems(d.library.map(x=>x.system));
 const cards=patientsFor(sel.system);
 view().innerHTML=`<div class="sb-shell sb-home">
 <section class="sb-hero">
  <div class="sb-hero-copy"><span class="sb-kicker">Scribbi · AI scribe review</span><h1>Scribbi writes the note.<br>You sign it.</h1><p>Watch a patient visit, or lead it yourself, while Scribbi listens. Then Scribbi drafts the SOAP note. Some of it is wrong, and it never includes what you felt with your hands. Find the mistakes, fix them, then sign.</p>
   <div class="sb-hero-actions"><button class="sb-btn sb-bright" id="sbQuick" ${d.locked?.blocked?'disabled':''}>${ic(STYLE_ICON[sel.style]||'dice')} ${E(styleOf(sel.style).quick)}</button><span class="sb-hero-meta">${E(heroMeta())}</span></div></div>
  <div class="sb-hero-art" aria-hidden="true"><div class="sb-mini-note"><b>Draft · Scribbi</b><p>Lungs: <span class="m-strike">clear to auscultation bilaterally</span> <span class="m-fix">not examined</span></p><p>ROS: <span class="m-strike">Denies</span> <span class="m-fix">Reports</span> fever and chills.</p><span class="m-add">Osteopathic: T10–L1 right paraspinal TTC.</span><span class="sb-mini-stamp">Signed ✓</span></div>${mascot('happy','is-bobbing is-listening')}</div>
 </section>
 ${lock}${visitResume(d)}${resume}
 <div class="sb-strip">
  <div class="sb-step"><span class="sb-step-num">1</span><div><b>Scribbi listens and drafts</b><span>Watch the visit, lead it yourself, or go straight to the draft. Scribbi hears every word.</span></div></div>
  <div class="sb-step is-feel"><span class="sb-step-num">2</span><div><b>You check every statement</b><span>Fix what's wrong and add what's missing, including your structural findings: Scribbi can't feel.</span></div></div>
  <div class="sb-step"><span class="sb-step-num">3</span><div><b>You sign</b><span>See what you caught, what you missed, and why it matters.</span></div></div>
 </div>
 <section class="sb-setup" aria-label="Set up a review">
  <div><div class="sb-section-head"><h2>How do you want the visit?</h2><span>Scribbi drafts from the same visit either way</span></div>
   <div class="sb-modes sb-styles" role="radiogroup" aria-label="Visit">${STYLES.map(x=>`<button class="sb-mode" role="radio" aria-checked="${x.key===sel.style}" data-style="${x.key}"><span class="sb-mode-check">${ic('check')}</span><span class="sb-mode-top"><span class="sb-mode-icon">${ic(STYLE_ICON[x.key])}</span><b>${E(x.label)}</b></span><span class="sb-mode-tag">${E(x.tag)}</span><p>${E(x.detail)}</p></button>`).join('')}</div></div>
  <div><div class="sb-section-head"><h2>Choose your level</h2><span>Pick a level for each review</span></div>
   <div class="sb-modes" role="radiogroup" aria-label="Review level">${d.modes.map(m=>`<button class="sb-mode" role="radio" aria-checked="${m.key===sel.mode}" data-mode="${m.key}"><span class="sb-mode-check">${ic('check')}</span><span class="sb-mode-top"><span class="sb-mode-icon">${ic(MODE_ICON[m.key])}</span><b>${E(m.label)}</b></span><span class="sb-mode-tag">${E(m.tagline)}</span><p>${E(m.detail)}</p></button>`).join('')}</div>
   <label class="sb-timer-toggle" id="sbTimerRow" ${sel.mode==='solo'?'':'hidden'}><input class="sb-switch" type="checkbox" id="sbTimed" ${sel.timed?'checked':''}> Add a 5-minute clock</label></div>
  <div><div class="sb-section-head"><h2>Choose a patient</h2><span>${presentations().length} cases · ${d.library.length} visits</span></div>
   <div class="sb-systems" role="group" aria-label="Filter by system"><button class="sb-system is-all" aria-pressed="${!sel.system}" data-system="">All systems</button>${systems.map(x=>`<button class="sb-system" aria-pressed="${sel.system===x}" data-system="${E(x)}">${art(x)}<span>${E(x)}</span></button>`).join('')}</div>
   <div class="sb-patients" role="radiogroup" aria-label="Patient">${patientCard(null)}${cards.map(patientCard).join('')}</div></div>
  <div class="sb-start-bar"><p>${startSummary()}</p><button class="sb-btn sb-primary" id="sbStart" ${d.locked?.blocked?'disabled':''}>${E(styleOf(sel.style).start)} ${ic('arrow')}</button></div>
 </section>
 <div class="sb-lower">
  <section class="sb-card" aria-labelledby="sbStatsHead"><div class="sb-section-head"><h2 id="sbStatsHead">Your Scribbi record</h2>${s.rounds?'':'<span>No signed notes yet</span>'}</div>${statsHtml(s)}<div class="sb-section-head" style="margin-top:18px"><h2 style="font-size:16px">Recent reviews</h2></div>${recentHtml(d.recent)}</section>
  <div style="display:grid;gap:18px;align-content:start">
   <section class="sb-card" aria-labelledby="sbGuideHead"><div class="sb-section-head"><h2 id="sbGuideHead">Field guide: what scribes get wrong</h2></div><div class="sb-guide">${d.types.map(t=>`<details><summary><span class="sb-type-icon">${ic(TYPE_ICON[t.type])}</span><span>${E(t.label)}<small>${E(t.short)}</small></span></summary><dl><div><dt>Why it happens</dt><dd>${E(t.why)}</dd></div><div><dt>Why it matters</dt><dd>${E(t.risk)}</dd></div><div><dt>How to fix it</dt><dd>${E(t.fix)}</dd></div><div><dt>Habit</dt><dd>${E(t.habit)}</dd></div></dl></details>`).join('')}</div></section>
   <section class="sb-card" aria-labelledby="sbWhyHead"><div class="sb-section-head"><h2 id="sbWhyHead">Why this matters</h2></div><div class="sb-research">${d.research.map(r=>`<div class="sb-fact"><b>${E(r.stat)}</b><p>${E(r.text)}</p><a href="https://doi.org/${E(r.doi)}" target="_blank" rel="noopener noreferrer">${E(r.cite)}</a></div>`).join('')}</div></section>
  </div>
 </div></div>`;
 wireHome();
}
function modeLabel(key){return HOME?.modes?.find(m=>m.key===key)?.label||key;}
/* One card per presentation; its demonstrated variations are chosen in the
   start bar (a random one by default, like a new patient walking in). */
function presentations(){
 const by=new Map();
 (HOME?.library||[]).forEach(p=>{let c=by.get(p.case_id);if(!c){c={case_id:p.case_id,title:p.title,system:p.system,variants:[],best:null,plays:0};by.set(p.case_id,c);}c.variants.push({id:p.variant_id,label:p.variant_id==='base'?'Core presentation':p.variant_label});if(p.best!=null)c.best=Math.max(c.best??0,p.best);c.plays+=p.plays||0;});
 return [...by.values()];
}
function patientsFor(system){return presentations().filter(p=>!system||p.system===system).sort((a,b)=>{const x=SYS_ORDER.indexOf(a.system),y=SYS_ORDER.indexOf(b.system);return (x<0?99:x)-(y<0?99:y)||a.title.localeCompare(b.title);});}
function selectedCase(){return presentations().find(p=>p.case_id===homeSel.patient)||null;}
function patientCard(p){
 const sel=homeSel.patient;
 if(!p)return `<button class="sb-patient sb-random" role="radio" aria-checked="${!sel}" data-patient=""><span class="sb-patient-art">${ic('dice')}</span><b>Surprise me</b><small>${homeSel.system?E(homeSel.system):'Any system'} · any variation</small></button>`;
 return `<button class="sb-patient" role="radio" aria-checked="${sel===p.case_id}" data-patient="${E(p.case_id)}"><span class="sb-patient-art">${art(p.system)}</span><b>${E(p.title)}</b><small>${plural(p.variants.length,'variation')}${p.best!=null?`<span class="sb-best" title="Your best score">Best ${p.best}</span>`:''}</small></button>`;
}
function startSummary(){
 const sel=homeSel,c=selectedCase();
 const variant=c&&c.variants.length>1?`<label class="sb-variant">Variation <select id="sbVariant"><option value="random">Any (surprise me)</option>${c.variants.map(v=>`<option value="${E(v.id)}" ${sel.variant===v.id?'selected':''}>${E(v.label)}</option>`).join('')}</select></label>`:'';
 return `<span><b>${E(styleOf(sel.style).label)}</b> · <b>${E(modeLabel(sel.mode))}</b> level${sel.mode==='solo'&&sel.timed?' · 5-minute clock':''} · ${c?`<b>${E(c.title)}</b>`:`<b>Random patient</b>${sel.system?' · '+E(sel.system):''}`}</span>${variant}`;
}
function wireHome(){
 const root=view();
 const modes=$$('[data-mode]',root);
 modes.forEach(b=>{b.onclick=()=>{homeSel.mode=b.dataset.mode;savePrefs();repaintSetup();};
  b.onkeydown=e=>{if(!['ArrowRight','ArrowLeft','ArrowDown','ArrowUp'].includes(e.key))return;e.preventDefault();const i=modes.indexOf(b),n=modes[(i+(e.key==='ArrowRight'||e.key==='ArrowDown'?1:modes.length-1))%modes.length];n.focus();n.click();};});
 const timed=$('#sbTimed',root);if(timed)timed.onchange=()=>{homeSel.timed=timed.checked;savePrefs();repaintSetup();};
 root.querySelectorAll('[data-system]').forEach(b=>b.onclick=()=>{homeSel.system=b.dataset.system;const c=selectedCase();if(c&&homeSel.system&&c.system!==homeSel.system){homeSel.patient=null;homeSel.variant='random';}paintHome();$(`[data-system="${CSS.escape(homeSel.system)}"]`)?.focus();});
 root.querySelectorAll('[data-patient]').forEach(b=>b.onclick=()=>{homeSel.patient=b.dataset.patient||null;homeSel.variant='random';repaintSetup();});
 wireVariant();
 root.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>{location.hash='#scribbi/r/'+b.dataset.open;});
 root.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>window.pcmNavigate?.(b.dataset.go));
 const styles=$$('[data-style]',root);
 styles.forEach(b=>{b.onclick=()=>{homeSel.style=b.dataset.style;savePrefs();repaintSetup();};
  b.onkeydown=e=>{if(!['ArrowRight','ArrowLeft','ArrowDown','ArrowUp'].includes(e.key))return;e.preventDefault();const i=styles.indexOf(b),n=styles[(i+(e.key==='ArrowRight'||e.key==='ArrowDown'?1:styles.length-1))%styles.length];n.focus();n.click();};});
 const quick=$('#sbQuick',root);if(quick)quick.onclick=()=>startWith({random:true,system:''},quick);
 const start=$('#sbStart',root);if(start)start.onclick=()=>{const c=selectedCase();startWith(c?{case_id:c.case_id,variant_id:homeSel.variant||'random'}:{random:true,system:homeSel.system},start);};
 root.querySelectorAll('[data-resume-visit]').forEach(b=>b.onclick=()=>{location.hash='#/'+b.dataset.resumeVisit;});
 const convert=$('#sbConvert',root);if(convert)convert.onclick=convertAttempts;
 root.querySelectorAll('[data-open-attempt]').forEach(b=>b.onclick=()=>{location.hash='#/'+b.dataset.openAttempt;});
}
function repaintSetup(){
 const root=view();
 root.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-checked',String(b.dataset.mode===homeSel.mode)));
 root.querySelectorAll('[data-style]').forEach(b=>b.setAttribute('aria-checked',String(b.dataset.style===homeSel.style)));
 const quick=$('#sbQuick',root);if(quick)quick.innerHTML=`${ic(STYLE_ICON[homeSel.style]||'dice')} ${E(styleOf(homeSel.style).quick)}`;
 const start=$('#sbStart',root);if(start)start.innerHTML=`${E(styleOf(homeSel.style).start)} ${ic('arrow')}`;
 root.querySelectorAll('[data-patient]').forEach(b=>b.setAttribute('aria-checked',String((b.dataset.patient||null)===homeSel.patient)));
 const bar=$('.sb-start-bar p',root);if(bar){bar.innerHTML=startSummary();wireVariant();}
 const meta=$('.sb-hero-meta',root);if(meta)meta.textContent=heroMeta();
 const timed=$('#sbTimed',root);if(timed)timed.checked=!!homeSel.timed;
 const row=$('#sbTimerRow',root);if(row)row.hidden=homeSel.mode!=='solo';
}
function savePrefs(){store.set('prefs',{mode:homeSel.mode,timed:!!homeSel.timed,style:homeSel.style});}
function wireVariant(){const v=$('#sbVariant');if(v)v.onchange=()=>{homeSel.variant=v.value;};}
async function convertAttempts(){
 const attempts=HOME?.locked?.attempts||[];if(!attempts.length)return;
 const ok=await confirmBox('Switching marks your open Independent or Exam rehearsal encounter'+(attempts.length>1?'s':'')+' as assisted practice in Scores. Your work and timer are kept.',{title:'Switch to assisted practice?',confirm:'Switch and open Scribbi',cancel:'Keep it unassisted'});
 if(!ok)return;
 const r=await call('/api/teaching/access',{confirm:true,attempt_ids:attempts.map(a=>a.id)});
 if(r.error){pop(r.error==='offline'?'The local engine is unavailable.':r.error);return;}
 pop('Converted to assisted practice.');renderHome();
}
function statsHtml(s){
 if(!s.rounds)return `<p class="sb-empty">Sign your first note to start your record. Scribbi tracks how often you catch each kind of mistake, so you can see what slips past you.</p>`;
 const types=(s.by_type||[]).filter(t=>t.planted).sort((a,b)=>(a.fixed+a.caught)/a.planted-(b.fixed+b.caught)/b.planted);
 return `<div class="sb-stats-grid"><div class="sb-stat"><b>${s.rounds}</b><span>${s.rounds===1?'signed note':'signed notes'}</span></div><div class="sb-stat"><b>${s.average??'–'}</b><span>average score, out of 100</span></div><div class="sb-stat"><b>${s.catch_rate!=null?s.catch_rate+'%':'–'}</b><span>mistakes caught</span></div><div class="sb-stat" title="Signed without missing a mistake that could change care, and without adding anything unsupported"><b>${s.safe_streak||0}</b><span>safe sign-offs in a row</span></div></div>
 ${types.length?`<h3 class="sb-typehead">Mistakes caught, by type</h3><div aria-label="Catch rate by mistake type">${types.map(t=>{const pct=Math.round(100*(t.fixed+t.caught)/t.planted);return `<div class="sb-typebar"><span>${E(t.label)}</span><span class="bar" role="img" aria-label="${pct}% caught"><i style="width:${pct}%"></i></span><em>${t.fixed+t.caught}/${t.planted}</em></div>`;}).join('')}</div>`:''}
 ${(s.badges||[]).length?`<div class="sb-badge-row" style="margin-top:14px">${s.badges.map(b=>`<span class="sb-badge">${ic(BADGE_ICON[b.key]||'star')}${E(b.label)} <small>×${b.count}</small></span>`).join('')}</div>`:''}`;
}
function starsHtml(n){return `<span class="sb-stars" aria-label="${n} of 3 stars">${[0,1,2].map(i=>i<n?'★':'<span class="off">☆</span>').join('')}</span>`;}
function recentHtml(rows,max=6,extra=''){
 if((!rows||!rows.length)&&!extra)return `<p class="sb-empty">Your reviews will appear here.</p>`;
 return `<div class="sb-recent">${extra}${(rows||[]).slice(0,max).map(r=>`<button class="sb-recent-row" data-state="${r.status==='signed'?'done':'open'}" data-open="${E(r.id)}"><span class="sb-score-dot ${r.status!=='signed'?'is-open':''}">${r.status==='signed'?E(r.score):ic('pen')}</span><span><b>${E(r.title)}</b><small>${own(r)?'Your visit · ':''}${E(r.mode_label)} · ${r.status==='signed'?'signed '+when(r.signed_at):'not yet signed'}</small></span>${r.status==='signed'?starsHtml(r.stars||0):'<span class="sb-pill">Resume</span>'}</button>`).join('')}</div>`;
}
function when(ms){if(!ms)return '';const d=new Date(ms),n=new Date();return d.toDateString()===n.toDateString()?d.toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'}):d.toLocaleDateString(undefined,{month:'short',day:'numeric'});}

async function startRound(body,button){
 if(button){button.disabled=true;button.dataset.label=button.innerHTML;button.innerHTML='Scribbi is drafting…';}
 const r=await call('/api/scribbi/rounds',body);
 if(button&&button.isConnected){button.disabled=false;button.innerHTML=button.dataset.label;}
 if(r.error||!r.id){
  if(r.requires_assistance){pop('Scribbi is paused while an unassisted encounter is open.');if(location.hash.startsWith('#scribbi'))renderHome();else location.hash='#scribbi';return;}
  pop(r.error==='offline'?(r.message||'The local engine is unavailable.'):(r.error||'Scribbi could not start a review.'));return;
 }
 if(body.watch){location.hash='#scribbi/r/'+r.id+'/visit';return;}
 store.set('fresh',r.id);
 location.hash='#scribbi/r/'+r.id;
}
function startWith(target,button){
 const timed=homeSel.mode==='solo'&&!!homeSel.timed;
 if(homeSel.style==='lead')return startLead(target,button);
 return startRound({...target,mode:homeSel.mode,timed,watch:homeSel.style==='watch'},button);
}
/* Lead the visit: an untimed coached Chat CSE encounter that Scribbi listens
   to. Finishing it in the room hands the encounter to Scribbi (finishVisit). */
async function startLead(target,button){
 const label=button?.innerHTML;if(button){button.disabled=true;button.innerHTML='Opening the room…';}
 const body={learning_mode:'coached',purpose:'scribbi',interaction_mode:'type',variant_id:target.variant_id||'random'};
 if(target.random){body.random=true;if(target.system)body.system=target.system;}else body.case_id=target.case_id;
 const r=await call('/api/session',body);
 if(button&&button.isConnected){button.disabled=false;button.innerHTML=label;}
 if(r.error||!r.id){pop(r.error==='offline'?(r.message||'The local engine is unavailable.'):(r.error||'Could not open the room.'));return;}
 store.set('visitmode.'+r.id,{mode:homeSel.mode,timed:homeSel.mode==='solo'&&!!homeSel.timed});
 location.hash='#/'+r.id;
}
async function finishVisit(session){
 if(!session?.id)return false;
 const prefs=store.get('visitmode.'+session.id)||store.get('prefs')||{};
 const mode=['learn','coached','solo'].includes(prefs.mode)?prefs.mode:'learn';
 const ok=await confirmBox('Scribbi will write the note from everything you asked and every examination you did, except what you palpated: add that yourself. You can’t go back to the patient afterwards.',{title:'Finish the visit?',confirm:'Finish · Scribbi writes the note',cancel:'Keep going'});
 if(!ok)return false;
 const r=await call('/api/scribbi/rounds',{attempt_id:session.id,mode,timed:mode==='solo'&&!!prefs.timed});
 if(r.too_short){pop(r.error||'Scribbi needs more of the visit to write a useful note. Keep going: cover more of the history, and do at least two examinations that produce findings.');return false;}
 if(r.error||!r.id){pop(r.error==='offline'?(r.message||'The local engine is unavailable.'):(r.error||'Scribbi could not write the note.'));return false;}
 store.del('visitmode.'+session.id);
 store.set('fresh',r.id);
 return r;
}

/* ======================================================================
   A review
   ====================================================================== */
async function openRound(id){
 const token=++gen;
 view().innerHTML=`<div class="sb-shell"><p class="sb-muted" role="status" style="padding:60px 0">Opening the draft…</p></div>`;
 const data=await call('/api/scribbi/rounds/'+encodeURIComponent(id));
 if(token!==gen)return;
 if(data.error||!data.id){
  if(data.requires_assistance)return renderHome();
  return errorView('That review isn’t available',/no longer exists/i.test(data.error||'')?'It may have been removed by a progress reset.':(data.message||data.error),()=>{location.hash='#scribbi';});
 }
 if(data.status==='signed')return paintDebrief(data,false);
 // A watched visit comes first; its review clock has not started yet.
 if(data.started===false&&data.visit?.source==='library'&&window.pcmScribbiVisit){location.replace('#scribbi/r/'+data.id+'/visit');return;}
 const backup=store.get('round.'+data.id);
 const review=backup&&backup.state&&JSON.stringify(backup.state)!==JSON.stringify(data.review)?backup.state:(data.review||{chips:{},added:[]});
 R={round:data,review:normalizeReview(review),open:null,editing:null,tab:'talk',q:'',pane:'draft',saveChain:Promise.resolve(),saveTimer:null,pending:false,saveState:'saved',progress:data.progress||null,coach:null,coachHidden:false,timer:null,signing:false,autoSigned:false,token};
 paintReview();
 if(backup&&review===backup.state)queueSave(null,true);
 const fresh=store.get('fresh')===data.id;store.del('fresh');
 if(fresh&&!reduced())playDrafting();else introCoach();
}
function normalizeReview(r){return {chips:Object.assign({},r?.chips||{}),added:Array.isArray(r?.added)?r.added.map(a=>({id:String(a.id),section:a.section,text:String(a.text||'')})):[]};}
function teardownRound(){if(R){clearInterval(R.timer);clearTimeout(R.saveTimer);if(R.pending)flushSave();}R=null;closePop();}

function modeKey(){return R.round.mode.key;}
function allChips(){const out=[];R.round.draft.forEach(s=>s.lines.forEach(ln=>ln.chips.forEach(ch=>out.push({sec:s.key,ln,ch}))));return out;}
function chipById(id){return allChips().find(x=>x.ch.id===id);}
function chipState(id){return R.review.chips[id]||{status:'kept'};}

function paintReview(){
 const p=R.round,v=p.visit;
 document.title=['Review',v.title,'Scribbi','DocKnock'].filter(Boolean).join(' · ');
 const count=p.expect?.count;
 view().innerHTML=`<div class="sb-shell sb-round">
  <header class="sb-bar" aria-label="Review controls">${mascot('happy','is-listening')}<div class="sb-who"><b>${E(v.patient?.name||'Patient')} · ${E(v.title)}</b><span>${own(p)?'<span class="sb-yours">Your visit</span>':'Demonstrated visit'}${v.variant_label&&v.variant_id!=='base'?' · '+E(v.variant_label):''} · ${E(p.mode.label)} level</span></div>
   <div class="sb-meter" id="sbMeter">${meterHtml()}</div>${p.timed?`<span class="sb-clock" id="sbClock" role="timer" aria-label="Time remaining">--:--</span>`:''}
   <span class="sb-save" id="sbSave" role="status">Saved</span>
   ${p.hints?`<button class="sb-btn sb-sm" id="sbHint" ${p.hints.left?'':'disabled'} aria-label="Get a hint: ${p.hints.left} left, 5 points each" title="Each hint costs 5 points">${ic('bulb')} Hint · <span id="sbHintLeft">${p.hints.left}</span> left</button>`:''}
   <button class="sb-btn sb-primary" id="sbSign">${ic('seal')} Sign note</button></header>
  <div class="sb-pane-switch" role="tablist" aria-label="Show"><button class="sb-btn sb-sm" role="tab" data-pane="visit" aria-selected="false">${ic('chat')} The visit</button><button class="sb-btn sb-sm" role="tab" data-pane="draft" aria-selected="true">${ic('pen')} Scribbi's draft</button></div>
  <div class="sb-work" data-pane="${R.pane}">
   <aside class="sb-visit" aria-label="The visit">${visitHtml()}</aside>
   <main class="sb-draft"><article class="sb-paper" id="sbPaper" aria-label="Scribbi's draft note">
    <div class="sb-paper-head"><div><h2>Progress note</h2><p>${E(v.patient?.name||'')} · Drafted by Scribbi from ${own(p)?'your visit':'the visit'} · ${count!=null?`Scribbi made ${plural(count,'mistake')}`:'Draft for your review'}</p></div><span class="sb-draft-stamp">${ic('pen')} Draft · not signed</span></div>
    <div id="sbDraft">${draftHtml()}</div>
    <div class="sb-sign-foot"><p class="sb-kbd-hint">Select a line to check it. Keys: <kbd>V</kbd> looks right · <kbd>E</kbd> edit · <kbd>R</kbd> remove${p.mode.sources?' · <kbd>F</kbd> find in visit':''}</p><span class="sb-sign-line">Awaiting your signature</span></div>
   </article>
   <div id="sbCoachSlot"></div></main>
  </div></div>`;
 wireReview();
 startClock();
 updateSave();
}

/* ---------- the visit ---------- */
function visitHtml(){
 const v=R.round.visit;
 const talk=v.turns.filter(t=>t.kind==='talk').length,exam=v.turns.filter(t=>t.kind==='exam').length;
 return `<div class="sb-visit-head"><h2>${ic('chat')} ${v.source==='attempt'?'Your visit':'The visit'} <small>${[visitLength(v.length),'you and '+firstName(v.patient?.name)].filter(Boolean).map(E).join(' · ')}</small>${v.source==='library'?`<a class="sb-btn sb-sm sb-watch" href="#scribbi/r/${E(R.round.id)}/visit">${ic('eye')} Watch</a>`:''}</h2>
  <div class="sb-tabs" role="tablist" aria-label="Visit record">${[['talk','Conversation',talk],['exam','Exam',exam],['chart','Chart','']].map(([k,l,n])=>`<button class="sb-tab" role="tab" id="sbTab-${k}" aria-selected="${R.tab===k}" aria-controls="sbVisitBody" data-tab="${k}">${l}${n!==''?` <em>${n}</em>`:''}</button>`).join('')}</div>
  <label class="sb-search">${ic('search')}<span class="sb-sr">Search the visit</span><input id="sbSearch" type="search" placeholder="Search the visit" value="${E(R.q)}" autocomplete="off"></label></div>
  <div class="sb-visit-body" id="sbVisitBody" role="tabpanel" aria-labelledby="sbTab-${R.tab}" tabindex="0">${visitBody()}</div>`;
}
function hl(text){const raw=String(text??''),q=R.q.trim();if(!q)return E(raw);const lower=raw.toLowerCase(),ql=q.toLowerCase();let out='',i=0,j;while((j=lower.indexOf(ql,i))>=0){out+=E(raw.slice(i,j))+'<mark class="sb-q">'+E(raw.slice(j,j+q.length))+'</mark>';i=j+q.length;}return out+E(raw.slice(i));}
function visitBody(){
 const v=R.round.visit,q=R.q.trim().toLowerCase(),match=s=>!q||String(s||'').toLowerCase().includes(q);
 const who=firstName(v.patient?.name);
 if(R.tab==='chart'){
  const vit=Object.entries(v.vitals||{});
  const parts=[`<div class="sb-chart-card" data-turn="chart:doorway"><h3>Posted at the door</h3>${(v.doorway||[]).filter(match).map(l=>`<p>${hl(l)}</p>`).join('')||'<p class="sb-muted">No match.</p>'}</div>`,
   `<div class="sb-chart-card" data-turn="chart:vitals"><h3>Vital signs</h3><div class="sb-vitals">${vit.filter(([k,val])=>match(k+' '+val)).map(([k,val])=>`<div><span>${E(k)}</span><b>${hl(val)}</b></div>`).join('')||'<p class="sb-muted">No match.</p>'}</div></div>`];
  (v.supplied||[]).forEach(r=>{if(match(r.label+' '+r.value))parts.push(`<div class="sb-chart-card" data-turn="chart:result:${E(r.id)}"><h3>${E(r.label)}</h3><p>${hl(r.value)}</p></div>`);});
  return `<div class="sb-chart">${parts.join('')}</div>`;
 }
 const rows=v.turns.filter(t=>R.tab==='talk'?t.kind==='talk':t.kind!=='talk');
 const shown=rows.filter(t=>match([t.student,t.patient,t.label,t.finding,t.detail].join(' ')));
 if(!shown.length)return `<p class="sb-empty">${q?'Nothing in this tab matches “'+E(R.q)+'”.':'Nothing recorded here.'}</p>`;
 return shown.map(t=>{
  if(t.kind==='talk')return `<div class="sb-turn" data-turn="${t.id}"><span class="sb-t">${E(t.t)}${t.section?' · '+E(t.section):''}</span><div class="sb-bubble you"><span class="who">You</span>${hl(t.student)}</div><div class="sb-bubble pt"><span class="who">${E(who)}</span>${hl(t.patient)}</div></div>`;
  if(t.kind==='exam')return `<div class="sb-turn" data-turn="${t.id}"><div class="sb-exam-item ${t.felt?'is-felt':''}"><span class="ico">${ic(t.felt?'hand':'stethoscope')}</span><b>${hl(t.label)}${t.felt?'<span class="sb-felt-tag">Felt · not said aloud</span>':''}</b><p>${hl(t.finding)}</p></div></div>`;
  return `<div class="sb-turn" data-turn="${t.id}"><div class="sb-step-row"><span class="sb-t">${E(t.t)}</span><span><b>${hl(t.label)}</b>${t.detail?' '+hl(t.detail):''}</span></div></div>`;
 }).join('');
}
function paintVisit(keepScroll){
 const body=$('#sbVisitBody');if(!body)return;const top=body.scrollTop;
 $$('.sb-tab').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab===R.tab)));
 body.setAttribute('aria-labelledby','sbTab-'+R.tab);body.innerHTML=visitBody();if(keepScroll)body.scrollTop=top;
}
function showSources(refs,section){
 if(!refs||!refs.length){
  if(section==='A'||section==='P'){showCoach({kind:'info',title:'Assessment and plan lines are reasoning, not quotes.',message:'Check this one against the findings in Subjective and Objective. Does the visit make it a reasonable choice?'});return;}
  showCoach({kind:'alarm',title:'Scribbi couldn’t link this line to the visit.',message:'No single question, answer, exam or chart entry is tied to it. Search the visit to check it; if nothing supports it, that is exactly what to look for.'});return;
 }
 const first=refs[0],v=R.round.visit;
 let tab='chart';if(!first.startsWith('chart:')){const t=v.turns.find(x=>x.id===first);tab=t&&t.kind==='talk'?'talk':'exam';}
 R.tab=tab;R.q='';const s=$('#sbSearch');if(s)s.value='';setPane('visit',true);paintVisit();
 const body=$('#sbVisitBody');const hits=refs.map(r=>body.querySelector(`[data-turn="${CSS.escape(r)}"]`)).filter(Boolean);
 hits.forEach(h=>h.classList.add('is-hit'));
 if(hits[0]){if(body.scrollHeight>body.clientHeight+4){const top=hits[0].offsetTop-Math.max(0,(body.clientHeight-hits[0].offsetHeight)/2);body.scrollTo({top:Math.max(0,top),behavior:reduced()?'instant':'smooth'});}else hits[0].scrollIntoView({block:'center',behavior:reduced()?'instant':'smooth'});}
 setTimeout(()=>hits.forEach(h=>h.classList.remove('is-hit')),3200);
 say('Showing '+plural(hits.length,'matching moment')+' in the visit.');
}

/* ---------- the draft ---------- */
function draftHtml(){
 return R.round.draft.map(sec=>`<section class="sb-sec" data-sec="${sec.key}" aria-labelledby="sbSec-${sec.key}"><div class="sb-sec-head"><span class="sb-sec-letter" aria-hidden="true">${sec.key}</span><h3 id="sbSec-${sec.key}">${E(sec.title)}</h3></div>
  ${sec.lines.map(ln=>lineHtml(sec.key,ln)).join('')}
  ${addedHtml(sec.key)}
  ${R.editing==='add:'+sec.key?editorHtml('add:'+sec.key,'',addPlaceholder(sec.key)):`<button class="sb-add-btn" data-add="${sec.key}">${ic('plus')} Add to ${E(sec.title)}</button>`}</section>`).join('');
}
function addPlaceholder(sec){return {S:'Something the patient said that is missing…',O:'An exam finding that is missing, e.g. Osteopathic: level, side, what you felt…',A:'A diagnosis that belongs in the assessment…',P:'A plan item that is missing…'}[sec];}
function lineHtml(sec,ln){
 const ap=sec==='A'||sec==='P',vit=ln.label==='Vitals';
 const chips=ln.chips.map(ch=>chipHtml(ch,ln)).join(vit?'<span class="sb-vsep" aria-hidden="true">·</span>':' ');
 return `<div class="sb-line ${ap?'is-ap':''}" data-line="${ln.id}"><span class="sb-label">${E(ap?ln.label+'.':ln.label)}</span><p class="sb-text">${chips}</p></div>`;
}
function chipHtml(ch,ln){
 if(R.editing===ch.id)return editorHtml(ch.id,chipState(ch.id).status==='edited'?chipState(ch.id).text:ch.text,'');
 const st=chipState(ch.id),text=st.status==='edited'?st.text:ch.text;
 const cls=['sb-chip',st.status==='removed'?'is-removed':'',st.status==='edited'?'is-edited':'',st.verified?'is-verified':'',R.open===ch.id?'is-open':''].join(' ');
 const status=st.status==='removed'?'removed':st.status==='edited'?'edited':st.verified?'checked, looks right':'not yet checked';
 return `<span class="${cls}" role="button" tabindex="0" data-chip="${ch.id}" aria-haspopup="true" aria-expanded="${R.open===ch.id}" aria-label="${E((ln.label?ln.label+': ':'')+text+' ('+status+')')}">${E(text)}</span>`;
}
function addedHtml(sec){
 const rows=R.review.added.filter(a=>a.section===sec);if(!rows.length)return '';
 return `<div class="sb-added">${rows.map(a=>R.editing==='added:'+a.id?editorHtml('added:'+a.id,a.text,''):`<div class="sb-add-item" data-added="${E(a.id)}"><span class="sb-label">You added</span><span class="txt">${E(a.text)}</span><span class="acts"><button class="sb-btn sb-ghost sb-sm" data-edit-added="${E(a.id)}" aria-label="Edit your added line">${ic('pencil')}</button><button class="sb-btn sb-ghost sb-sm" data-del-added="${E(a.id)}" aria-label="Remove your added line">${ic('x')}</button></span></div>`).join('')}</div>`;
}
function editorHtml(key,value,placeholder){
 return `<span class="sb-edit-wrap" data-editor="${E(key)}"><textarea aria-label="${key.startsWith('add')?'New line':'Edit this line'}" placeholder="${E(placeholder)}" maxlength="2000">${E(value)}</textarea><span class="sb-edit-actions"><small>Enter saves · Shift+Enter new line · Esc cancels</small><button class="sb-btn sb-sm" data-editor-cancel>Cancel</button><button class="sb-btn sb-primary sb-sm" data-editor-save>Save</button></span></span>`;
}
function paintDraft(focusSel){
 const d=$('#sbDraft');if(!d)return;
 d.innerHTML=draftHtml();wireDraft();
 const ed=d.querySelector('[data-editor] textarea');
 if(ed){autosize(ed);ed.focus();const n=ed.value.length;ed.setSelectionRange(n,n);}
 else if(focusSel){const el=d.querySelector(focusSel);if(el)el.focus({preventScroll:true});}
}
function autosize(t){const fit=()=>{t.style.height='auto';t.style.height=Math.min(420,Math.max(62,t.scrollHeight+4))+'px';};fit();t.addEventListener('input',fit);}

/* ---------- wiring ---------- */
function wireReview(){
 $('#sbSign').onclick=()=>signNote(false);
 const hint=$('#sbHint');if(hint)hint.onclick=askHint;
 $$('.sb-tab').forEach(b=>b.onclick=()=>{R.tab=b.dataset.tab;paintVisit();});
 $$('.sb-tab').forEach(b=>b.onkeydown=e=>{if(e.key!=='ArrowRight'&&e.key!=='ArrowLeft')return;const tabs=$$('.sb-tab'),i=tabs.indexOf(b),n=tabs[(i+(e.key==='ArrowRight'?1:tabs.length-1))%tabs.length];n.focus();n.click();});
 const s=$('#sbSearch');let t;s.oninput=()=>{clearTimeout(t);t=setTimeout(()=>{if(!R)return;R.q=s.value;paintVisit();},120);};
 $$('.sb-pane-switch [data-pane]').forEach(b=>b.onclick=()=>setPane(b.dataset.pane));
 wireDraft();
 document.addEventListener('keydown',docKeys);
}
function setPane(p,fromSource){
 R.pane=p;const w=$('.sb-work');if(w)w.dataset.pane=p;
 $$('.sb-pane-switch [data-pane]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.pane===p)));
 if(fromSource&&window.matchMedia('(max-width:920px)').matches)window.scrollTo({top:0,behavior:'instant'});
}
function wireDraft(){
 const d=$('#sbDraft');
 d.querySelectorAll('.sb-chip').forEach(el=>{
  el.onclick=e=>{e.stopPropagation();togglePop(el.dataset.chip);};
  el.onkeydown=e=>chipKeys(e,el.dataset.chip);
 });
 d.querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>{closePop();R.editing='add:'+b.dataset.add;paintDraft();});
 d.querySelectorAll('[data-edit-added]').forEach(b=>b.onclick=()=>{closePop();R.editing='added:'+b.dataset.editAdded;paintDraft();});
 d.querySelectorAll('[data-del-added]').forEach(b=>b.onclick=()=>{const id=b.dataset.delAdded;R.review.added=R.review.added.filter(a=>a.id!==id);paintDraft();changed(null);say('Your added line was removed.');});
 const ed=d.querySelector('[data-editor]');
 if(ed){const ta=ed.querySelector('textarea');
  ed.querySelector('[data-editor-save]').onclick=()=>saveEditor(ed.dataset.editor,ta.value);
  ed.querySelector('[data-editor-cancel]').onclick=()=>cancelEditor(ed.dataset.editor);
  ta.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();saveEditor(ed.dataset.editor,ta.value);}else if(e.key==='Escape'){e.preventDefault();cancelEditor(ed.dataset.editor);}};}
}
function docKeys(e){
 if(!R||!$('#sbDraft'))return;
 if(e.key==='Escape'&&R.open){closePop(true);}
}
document.addEventListener('click',e=>{if(R&&R.open&&!e.target.closest('.sb-pop')&&!e.target.closest('.sb-chip'))closePop();});
function chipKeys(e,id){
 if(e.metaKey||e.ctrlKey||e.altKey)return;
 const k=e.key.toLowerCase();
 if(k==='enter'||k===' '){e.preventDefault();togglePop(id);return;}
 const st=chipState(id);
 const map={v:'verify',e:'edit',r:'remove',u:'restore',f:'find',delete:'remove',backspace:'remove'};
 const act=map[k];if(!act)return;
 if(act==='find'&&!R.round.mode.sources)return;
 if(act==='restore'&&st.status==='kept'&&!st.verified)return;
 e.preventDefault();doAction(act,id);
}
function popButtons(id){
 const st=chipState(id),b=[];
 if(st.status==='removed')b.push(['restore','undo','Restore','U']);
 else{
  if(st.status==='kept')b.push(st.verified?['unverify','undo','Unmark','V']:['verify','check','Looks right','V']);
  b.push(['edit','pencil',st.status==='edited'?'Edit again':'Edit','E']);
  if(st.status==='edited')b.push(['restore','undo','Undo edit','U']);
  b.push(['remove','x','Remove','R']);
 }
 if(R.round.mode.sources)b.push(['find','search','Find in visit','F']);
 return b;
}
function togglePop(id){if(R.open===id){closePop(true);return;}openPop(id);}
function openPop(id){
 closePop();R.open=id;
 const chip=$(`#sbDraft [data-chip="${CSS.escape(id)}"]`),paper=$('#sbPaper');if(!chip||!paper)return;
 chip.classList.add('is-open');chip.setAttribute('aria-expanded','true');
 const p=document.createElement('div');p.className='sb-pop';p.setAttribute('role','toolbar');p.setAttribute('aria-label','Actions for this line');
 p.innerHTML=popButtons(id).map(([act,icon,label,key])=>`<button type="button" data-act="${act}">${ic(icon)}${E(label)} <kbd>${key}</kbd></button>`).join('');
 paper.appendChild(p);
 const pr=paper.getBoundingClientRect(),rects=chip.getClientRects(),cr=rects[rects.length-1]||chip.getBoundingClientRect();
 const pw=p.offsetWidth,maxLeft=paper.clientWidth-pw-8;
 let left=Math.max(8,Math.min(cr.left-pr.left,maxLeft));
 p.style.left=left+'px';p.style.top=(cr.bottom-pr.top+10)+'px';
 p.style.setProperty('--arrow',Math.max(10,Math.min(pw-22,cr.left-pr.left-left+Math.min(24,cr.width/2)))+'px');
 p.querySelectorAll('button').forEach(b=>b.onclick=e=>{e.stopPropagation();doAction(b.dataset.act,id);});
 p.onkeydown=e=>{const bs=$$('button',p),i=bs.indexOf(document.activeElement);
  if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();bs[(i+(e.key==='ArrowRight'?1:bs.length-1))%bs.length].focus();return;}
  if(e.key==='Escape'){e.preventDefault();closePop(true);return;}
  if(e.key==='Tab'&&!e.shiftKey&&i===bs.length-1){closePop(false);return;}
  if(e.metaKey||e.ctrlKey||e.altKey)return;
  // The same single-key shortcuts work from the menu as from the line.
  const k=e.key.toLowerCase(),byKey={v:['verify','unverify'],e:['edit'],r:['remove'],u:['restore'],f:['find'],delete:['remove'],backspace:['remove']}[k];
  const match=byKey&&bs.find(b=>byKey.includes(b.dataset.act));
  if(match){e.preventDefault();doAction(match.dataset.act,id);}};
 p.querySelector('button')?.focus({preventScroll:true});
}
function closePop(refocus){
 const p=$('.sb-pop');if(p)p.remove();
 if(R&&R.open){const id=R.open;R.open=null;const chip=$(`#sbDraft [data-chip="${CSS.escape(id)}"]`);if(chip){chip.classList.remove('is-open');chip.setAttribute('aria-expanded','false');if(refocus)chip.focus({preventScroll:true});}}
}
function doAction(act,id){
 const info=chipById(id);if(!info)return;
 const st=chipState(id);
 if(act==='find'){closePop();showSources(info.ch.sources||[],info.sec||info.ln?.section);return;}
 if(act==='edit'){closePop();R.editing=id;paintDraft();return;}
 closePop();
 if(act==='verify'){R.review.chips[id]={status:'kept',verified:true};say('Marked as checked.');}
 else if(act==='unverify'){delete R.review.chips[id];say('Unmarked.');}
 else if(act==='remove'){R.review.chips[id]={status:'removed'};say('Line removed. Press U to restore it.');}
 else if(act==='restore'){delete R.review.chips[id];say(st.status==='removed'?'Line restored.':'Edit undone.');}
 paintDraft(`[data-chip="${CSS.escape(id)}"]`);
 changed(act==='verify'||act==='unverify'?null:{chip:id});
}
function saveEditor(key,value){
 const text=String(value||'').trim();
 if(key.startsWith('add:')){
  const sec=key.slice(4);R.editing=null;
  if(!text){paintDraft();return;}
  const id='a'+Date.now().toString(36)+Math.floor(Math.random()*1e4).toString(36);
  R.review.added.push({id,section:sec,text});paintDraft(`[data-added="${CSS.escape(id)}"] button`);changed({added:id});say('Line added to the note.');return;
 }
 if(key.startsWith('added:')){
  const id=key.slice(6),row=R.review.added.find(a=>a.id===id);R.editing=null;
  if(row){if(text)row.text=text;else R.review.added=R.review.added.filter(a=>a.id!==id);}
  paintDraft();changed(row&&text?{added:id}:null);return;
 }
 const info=chipById(key);R.editing=null;
 if(!info){paintDraft();return;}
 if(!text)R.review.chips[key]={status:'removed'};
 else if(text===info.ch.text)delete R.review.chips[key];
 else R.review.chips[key]={status:'edited',text};
 paintDraft(`[data-chip="${CSS.escape(key)}"]`);changed({chip:key});say('Line updated.');
}
function cancelEditor(key){R.editing=null;const sel=key.startsWith('add:')?`[data-add="${key.slice(4)}"]`:key.startsWith('added:')?`[data-added="${CSS.escape(key.slice(6))}"] button`:`[data-chip="${CSS.escape(key)}"]`;paintDraft(sel);}

/* ---------- saving ---------- */
function changed(target){
 R.pending=true;updateSave('saving');
 store.set('round.'+R.round.id,{state:R.review,at:Date.now()});
 queueSave(target);
}
function queueSave(target,immediate){
 clearTimeout(R.saveTimer);
 const instant=R.round.mode.instant_feedback&&target;
 if(instant){flushSave(target);return;}
 R.pending=true;R.saveTimer=setTimeout(()=>flushSave(null),immediate?0:450);
}
function flushSave(target){
 if(!R)return Promise.resolve();
 clearTimeout(R.saveTimer);
 const round=R.round,snapshot=JSON.parse(JSON.stringify(R.review)),instant=round.mode.instant_feedback&&target,rid=round.id,mine=R;
 R.pending=false;
 const run=async()=>{
  const res=await call(`/api/scribbi/rounds/${rid}/${instant?'check':'review'}`,instant?{state:snapshot,target}:{state:snapshot});
  if(R!==mine)return res;
  if(res.error){
   if(/already signed/i.test(res.error||'')){reloadAfterSign();return res;}
   R.pending=true;updateSave('error');return res;
  }
  if(res.saved===false&&res.status==='signed'){reloadAfterSign();return res;}
  if(JSON.stringify(R.review)===JSON.stringify(snapshot)){store.del('round.'+rid);if(!R.pending)updateSave('saved');}
  if(res.progress){R.progress=res.progress;paintMeter();}
  if(instant&&res.verdict)verdictFeedback(res,target);
  return res;
 };
 mine.saveChain=mine.saveChain.then(run,run);
 return mine.saveChain;
}
async function reloadAfterSign(){if(!R)return;const id=R.round.id;store.del('round.'+id);const data=await call('/api/scribbi/rounds/'+id);if(data&&data.status==='signed'){teardownRoundSoft();paintDebrief(data,true);}}
function teardownRoundSoft(){if(R){clearInterval(R.timer);clearTimeout(R.saveTimer);}document.removeEventListener('keydown',docKeys);closePop();R=null;}
function updateSave(state){
 if(state)R.saveState=state;
 const el=$('#sbSave');if(!el)return;
 el.classList.toggle('is-error',R.saveState==='error');
 el.textContent={saved:'Saved',saving:'Saving…',error:'Not saved: retrying'}[R.saveState]||'';
 if(R.saveState==='error'){clearTimeout(R.retry);R.retry=setTimeout(()=>{if(R&&R.pending)flushSave(null);},2500);}
}
window.addEventListener('beforeunload',e=>{if(R&&(R.pending||R.saveState==='saving')){e.preventDefault();e.returnValue='';}});

/* ---------- meter, coach, hints ---------- */
function meterHtml(){
 const p=R.round,m=p.mode,pr=R.progress,exp=p.expect||{};
 if(m.instant_feedback&&pr){
  const dots=Array.from({length:pr.total},(_,i)=>`<i class="${i<pr.found?'on':''}"></i>`).join('')+(exp.hands_on?`<i class="hand ${pr.hands_on&&pr.hands_on!=='missed'?'on':''}" title="Structural findings"></i>`:'');
  return `<span class="sb-found" aria-label="${pr.found} of ${pr.total} mistakes found${exp.hands_on?(pr.hands_on&&pr.hands_on!=='missed'?', structural findings added':', structural findings not added yet'):''}"><span class="dots">${dots}</span>${pr.found} of ${pr.total} found</span>`;
 }
 if(exp.count!=null)return `<span class="sb-pill">${ic('target')} ${plural(exp.count,'mistake')} to find${exp.hands_on?' + your hands-on findings':''}</span>`;
 return `<span class="sb-pill">${ic('eye')} Verify every line</span>`;
}
function paintMeter(){const m=$('#sbMeter');if(m)m.innerHTML=meterHtml();}
function introCoach(){
 const p=R.round,exp=p.expect||{},key=modeKey();
 if(key==='learn'){
  const types=(exp.types||[]).map(t=>`<span class="sb-type-chip" data-type="${t.type}"><i>${t.count}</i>${E(t.label)}</span>`).join('');
  showCoach({kind:'intro',title:`I made ${plural(exp.count||0,'mistake')} in this draft.`,message:`Select any line to check it against the visit. Use Find in visit to see where it came from.${exp.hands_on?' And I couldn’t feel your structural exam, so that is missing too.':''}`,html:types?`<div class="sb-types">${types}${exp.hands_on?`<span class="sb-type-chip" data-type="hands_on"><i>${ic('hand')}</i>Hands-on finding</span>`:''}</div>`:''});
  paintTypeChips();
 }else if(key==='coached'){
  showCoach({kind:'intro',title:`I made ${plural(exp.count||0,'mistake')}. Can you find ${exp.count===1?'it':'them'}?`,message:`Check every line against the visit. You have ${plural(p.hints?.left||0,'hint')} if you get stuck.${exp.hands_on?' I also couldn’t feel your structural exam.':''}`});
 }else{
  showCoach({kind:'intro',title:'Your review. Your signature.',message:'Nobody will tell you what’s wrong, or whether anything is. Verify every line against the visit, then sign.',autohide:9000});
 }
}
function paintTypeChips(){
 const pr=R.progress;if(!pr)return;
 (pr.types||[]).forEach(t=>{const el=$(`.sb-type-chip[data-type="${t.type}"]`);if(el){el.classList.toggle('is-done',t.found>=t.total);el.querySelector('i').textContent=t.found>=t.total?'✓':String(t.total-t.found);}});
 const h=$('.sb-type-chip[data-type="hands_on"]');if(h)h.classList.toggle('is-done',!!pr.hands_on&&pr.hands_on!=='missed');
}
function showCoach(c){
 R.coach=c;const slot=$('#sbCoachSlot');if(!slot)return;
 const mood={fixed:'proud',alarm:'oops',wrong:'think',intro:'happy',hint:'think'}[c.kind]||'happy';
 slot.innerHTML=`<div class="sb-coach ${c.kind==='fixed'?'is-fixed':c.kind==='alarm'?'is-alarm':c.kind==='wrong'?'is-wrong':''}" role="status">${mascot(mood)}<div class="sb-coach-body"><b>${E(c.title)}</b><p>${E(c.message)}</p>${c.html||''}${c.evidence?.length?`<div class="sb-coach-evidence">${c.evidence.map(quoteHtml).join('')}</div>`:''}</div><button class="sb-coach-close" aria-label="Dismiss">×</button></div>`;
 slot.querySelector('.sb-coach-close').onclick=()=>{slot.innerHTML='';};
 if(c.kind==='intro')paintTypeChips();
 // On a phone the card covers the note, so feedback tucks itself away.
 const small=window.matchMedia('(max-width:560px)').matches,hide=c.autohide||(small&&c.kind!=='intro'?6500:0);
 clearTimeout(R.coachTimer);if(hide)R.coachTimer=setTimeout(()=>{if(R&&R.coach===c)slot.innerHTML='';},hide);
}
function quoteHtml(q){
 if(q.kind==='talk')return `<div><b>You:</b> ${E(q.student)}<br><b>${E(firstName(R?R.round.visit.patient?.name:''))}:</b> ${E(q.patient)}</div>`;
 if(q.kind==='exam')return `<div><b>${E(q.label)}:</b> ${E(q.finding)}</div>`;
 return `<div><b>${E(q.label||'Chart')}:</b> ${E(q.text||q.detail||'')}</div>`;
}
function verdictFeedback(res,target){
 const sel=target.chip?`[data-chip="${CSS.escape(target.chip)}"]`:target.added?`[data-added="${CSS.escape(target.added)}"] .txt`:null;
 const el=sel&&$('#sbDraft '+sel);
 const kind={fixed:'fixed',caught:'wrong',false_alarm:'alarm',unsupported:'alarm',still_wrong:'wrong'}[res.verdict];
 if(el&&kind){el.classList.remove('flash-fixed','flash-alarm','flash-wrong');void el.offsetWidth;el.classList.add(kind==='fixed'?'flash-fixed':kind==='alarm'?'flash-alarm':'flash-wrong');}
 if(res.verdict==='neutral'){if(R.coach&&(R.coach.kind==='alarm'||R.coach.kind==='wrong')){const slot=$('#sbCoachSlot');if(slot)slot.innerHTML='';R.coach=null;}return;}
 showCoach({kind,title:res.title,message:res.message,evidence:res.evidence});
 const bar=$('.sb-bar .sb-mascot');if(bar){bar.classList.remove('mood-happy','mood-proud','mood-oops','mood-think');bar.classList.add(kind==='fixed'?'mood-proud':kind==='alarm'?'mood-oops':'mood-think');setTimeout(()=>{if(bar.isConnected){bar.classList.remove('mood-proud','mood-oops','mood-think');bar.classList.add('mood-happy');}},2200);}
 paintTypeChips();
 const pr=R.progress;
 if(pr&&(pr.fixed??pr.found)===pr.total&&(!R.round.expect?.hands_on||pr.hands_on==='fixed')&&!pr.unsupported&&!pr.false_alarms&&kind==='fixed'){
  showCoach({kind:'fixed',title:'That’s everything I got wrong.',message:'Give the draft one last read, then sign your note.'});
 }
}
async function askHint(){
 const b=$('#sbHint');if(b)b.disabled=true;
 await flushSave(null);
 const r=await call(`/api/scribbi/rounds/${R.round.id}/hint`,{state:R.review});
 if(!R)return;
 if(r.error){pop(r.error==='offline'?'The local engine is unavailable.':r.error);if(b)b.disabled=!(R.round.hints&&R.round.hints.left);return;}
 R.round.hints.used=r.used;R.round.hints.left=r.left;
 if(b){b.disabled=!r.left;const n=b.querySelector('#sbHintLeft');if(n)n.textContent=r.left;b.setAttribute('aria-label',`Get a hint: ${r.left} left, 5 points each`);}
 showCoach({kind:'hint',title:r.hint.level?`Hint ${r.used} of ${r.used+r.left}`:'All found',message:r.hint.text});
 if(r.hint.section){const sec=$(`.sb-sec[data-sec="${r.hint.section}"]`);if(sec){setPane('draft');sec.classList.remove('is-hinted');void sec.offsetWidth;sec.classList.add('is-hinted');scrollUnderBars(sec);setTimeout(()=>sec.classList.remove('is-hinted'),4500);}}
}

// Scroll an element into view below the sticky app header and review bar.
function scrollUnderBars(el){
 const header=document.querySelector('.topbar')?.getBoundingClientRect().height||64,bar=$('.sb-bar')?.getBoundingClientRect().height||0;
 const top=el.getBoundingClientRect().top+window.scrollY-header-bar-24;
 window.scrollTo({top:Math.max(0,top),behavior:reduced()?'instant':'smooth'});
}

/* ---------- timer ---------- */
function startClock(){
 const p=R.round;if(!p.timed||!p.deadline)return;
 const el=$('#sbClock'),tick=()=>{if(!R){return;}const left=p.deadline-clockNow();if(el){el.textContent=mmss(left)+' left';el.classList.toggle('is-low',left<60000);}
  if(left<=0&&!R.autoSigned){R.autoSigned=true;clearInterval(R.timer);signNote(true);}};
 tick();R.timer=setInterval(tick,250);
}

/* ---------- drafting animation ---------- */
function playDrafting(){
 const paper=$('#sbPaper');if(!paper)return introCoach();
 const mine=R;
 const chips=$$('#sbDraft .sb-chip');chips.forEach(c=>c.classList.add('is-typing'));
 const overlay=document.createElement('div');overlay.className='sb-drafting';
 overlay.innerHTML=`<div class="sb-drafting-card">${mascot('happy','is-writing is-listening')}<div><b>Scribbi is drafting your note…</b><span>From ${plural(R.round.visit.counts?.talk||0,'exchange')} and ${plural(R.round.visit.counts?.exam||0,'exam step')}. Click to skip.</span></div></div>`;
 paper.appendChild(overlay);
 let i=0,done=false;const step=Math.max(8,Math.min(28,1600/Math.max(1,chips.length)));
 // Leaving the review before the animation ends must not touch the next page.
 const finish=()=>{if(done)return;done=true;clearInterval(t);if(R!==mine)return;chips.forEach(c=>{c.classList.remove('is-typing');});overlay.remove();introCoach();};
 const t=setInterval(()=>{for(let k=0;k<2&&i<chips.length;k++,i++){chips[i].classList.remove('is-typing');chips[i].classList.add('typed');}if(i>=chips.length)setTimeout(finish,220);},step);
 overlay.onclick=finish;
 setTimeout(finish,2600);
}

/* ---------- signing ---------- */
async function signNote(auto){
 if(!R||R.signing)return;
 if(R.editing){const ed=$('#sbDraft [data-editor]');if(ed)saveEditor(ed.dataset.editor,ed.querySelector('textarea').value);}
 if(!auto){
  const c=Object.values(R.review.chips);const edits=c.filter(x=>x.status==='edited').length,removed=c.filter(x=>x.status==='removed').length,added=R.review.added.length,checked=c.filter(x=>x.verified).length,total=allChips().length;
  const found=R.progress&&R.round.mode.instant_feedback?` You've found ${R.progress.found} of ${R.progress.total}.`:'';
  const structural=R.round.expect?.hands_on&&!(R.review.added||[]).some(a=>a.section==='O'&&/osteopath|paraspinal|tissue texture|\bT\d|\bL\d|\bC\d/i.test(a.text))?' Your structural findings aren’t in the note yet.':'';
  const msg=`You edited ${plural(edits,'line')}, removed ${removed} and added ${added}.${found}${structural} Once signed, the note is final and you’ll see what you caught, missed and changed.`;
  if(!await confirmBox(msg,{title:'Sign this note?',confirm:'Sign note',cancel:'Keep reviewing'}))return;
 }
 R.signing=true;const btn=$('#sbSign');if(btn){btn.disabled=true;btn.textContent='Signing…';}
 await R.saveChain;
 const id=R.round.id,res=await call(`/api/scribbi/rounds/${id}/sign`,{state:R.review,auto:!!auto});
 if(!R||R.round.id!==id)return;
 if(res.error||res.status!=='signed'){R.signing=false;if(btn){btn.disabled=false;btn.innerHTML=ic('seal')+' Sign note';}pop(res.error==='offline'?'The local engine is unavailable. Your review is kept in this browser.':(res.error||'The note could not be signed.'));return;}
 store.del('round.'+id);
 teardownRoundSoft();
 paintDebrief(res,true);
 if(auto)pop('Time is up. Your note was signed as it stood.');
}

/* ======================================================================
   Debrief
   ====================================================================== */
function verdictPill(v){return {fixed:[ 'check','Fixed'],caught:['eye','Caught, not fixed'],missed:['alert','Missed']}[v]||['eye',v];}
function paintDebrief(p,animate){
 const r=p.result,v=p.visit,c=r.counts||{},name=v.patient?.name||'the patient';
 const unsafe=!r.safe;
 const missedN=(r.items||[]).filter(i=>i.verdict==='missed'&&i.type!=='hands_on').length;
 const handsMissing=(r.items||[]).some(i=>i.type==='hands_on'&&i.verdict==='missed');
 const headline=unsafe?(missedN?`${plural(missedN,'mistake')} would reach the chart${handsMissing?', and your structural findings would not':''}.`:'Something unsupported would reach the chart.'):(r.score>=90?'Clean note. Safe to sign.':missedN?`Safe to sign, but ${plural(missedN,'mistake')} slipped through.`:handsMissing?'Safe to sign, but your hands-on findings are missing.':'Safe to sign, with room to sharpen.');
 const mood=unsafe?'oops':r.score>=90?'proud':'happy';
 const summary=c.planted?`Scribbi made ${plural(c.planted,'mistake')}. You fixed ${c.fixed}${c.caught?`, caught ${c.caught} without fixing ${c.caught===1?'it':'them'}`:''}${c.missed?`, and missed ${c.missed}`:''}.`:'Scribbi made no mistakes in this draft.';
 const items=[...(r.items||[])].sort((a,b)=>({missed:0,caught:1,fixed:2}[a.verdict]-{missed:0,caught:1,fixed:2}[b.verdict]));
 const hands=(r.items||[]).find(i=>i.type==='hands_on');
 document.title=['Debrief',p.visit?.title,'Scribbi','DocKnock'].filter(Boolean).join(' · ');
 view().innerHTML=`<div class="sb-shell sb-debrief">
 <section class="sb-result ${unsafe?'is-unsafe':''}">${mascot(mood,'is-bobbing')}<div><span class="sb-kicker">Signed note · ${E(name)} · ${E(p.mode.label)}</span><h1>${E(headline)}</h1><p>${E(summary)}${hands?(hands.verdict==='fixed'?' You added the structural findings Scribbi couldn’t feel.':' The structural findings Scribbi couldn’t feel are still missing.'):''}</p>
  <div class="sb-result-pills"><span class="sb-pill">${ic('target')} ${c.planted?`${c.fixed+c.caught}/${c.planted} found`:'No planted mistakes'}</span>${hands?`<span class="sb-pill">${ic('hand')} Hands-on ${hands.verdict==='fixed'?'added':hands.verdict==='caught'?'partly added':'missing'}</span>`:''}<span class="sb-pill">${ic('alert')} ${plural(c.false_alarms||0,'false alarm')}</span>${c.unsupported?`<span class="sb-pill">${ic('ghost')} ${c.unsupported} unsupported</span>`:''}<span class="sb-pill">${ic('clock')} Review time ${mmss(r.elapsed_ms)}${r.timed_out?' · time ran out':''}</span>${r.hints_used?`<span class="sb-pill">${ic('bulb')} ${plural(r.hints_used,'hint')} · −${5*r.hints_used}</span>`:''}</div></div>
  <div class="sb-ring" role="img" aria-label="Score ${r.score} out of 100, ${r.stars} of 3 stars"><svg viewBox="0 0 120 120"><circle class="track" cx="60" cy="60" r="52"/><circle class="fill" cx="60" cy="60" r="52" stroke-dasharray="326.7" stroke-dashoffset="${animate&&!reduced()?326.7:326.7*(1-r.score/100)}"/></svg><div class="sb-ring-num"><div><b id="sbScoreNum">${animate&&!reduced()?0:r.score}</b><span>score</span>${starsHtml(r.stars)}</div></div></div>
 </section>
 ${(r.badges||[]).length?`<div class="sb-badge-row" style="margin:0 0 18px">${r.badges.map(b=>`<span class="sb-badge" title="${E(b.text)}">${ic(BADGE_ICON[b.key]||'star')}${E(b.label)}</span>`).join('')}</div>`:''}
 <div class="sb-debrief-grid"><div class="sb-items">
  ${items.map(it=>itemHtml(it,name)).join('')}
  ${(r.false_alarms||[]).length?`<div class="sb-alarm-card"><h3>${ic('alert')} ${plural(r.false_alarms.length,'false alarm')}: these lines were right</h3>${r.false_alarms.map(f=>`<p class="ln">${f.kind==='removed'?'You removed':'You changed'}: “${E(f.text)}”${f.edited?` → “${E(f.edited)}”`:''}</p>${(f.evidence||[]).slice(0,2).map(q=>`<div class="sb-evid"><div class="q">${quoteBody(q,name)}</div></div>`).join('')}`).join('')}<p class="sb-muted" style="margin-top:8px">Deleting what really happened is also a documentation error. The fix is to verify, not to delete.</p></div>`:''}
  ${(r.unsupported||[]).length?`<div class="sb-alarm-card" style="border-color:var(--sb-missed-line);background:var(--sb-missed-soft)"><h3>${ic('ghost')} You added something the visit doesn’t support</h3>${r.unsupported.map(u=>`<p class="ln">“${E(u.text)}”</p><p>${E(u.why)}</p>`).join('')}</div>`:''}
  ${!items.length&&!(r.false_alarms||[]).length?`<div class="sb-card"><b>Nothing to fix.</b><p class="sb-muted">This draft was clean. Trusting it after checking is the right call.</p></div>`:''}
 </div>
 <aside class="sb-side"><section class="sb-card"><div class="sb-section-head"><h2 style="font-size:16px">What next?</h2></div><div class="sb-next">
  <button class="sb-btn sb-primary" data-next="again">${ic('dice')} Review a new draft of ${E(firstName(name))}’s visit</button>
  <button class="sb-btn" data-next="new">${ic('arrow')} A new patient</button>
  <button class="sb-btn" data-next="chatcse">${ic('chat')} Practice ${E(firstName(name))}’s visit in Chat CSE (Guided)</button>
  <button class="sb-btn sb-ghost" data-next="home">${ic('home')} Scribbi home</button></div></section>
  <details class="sb-final" ${items.length?'':'open'}><summary>Your signed note</summary><div class="sb-legend"><span><i style="background:var(--sb-fixed-soft)"></i>Fixed mistake</span><span><i style="background:var(--sb-missed-soft)"></i>Missed mistake</span><span><i style="background:var(--sb-caught-soft)"></i>Caught / false alarm</span><span><i style="background:var(--sb-added)"></i>You added</span></div>${finalNoteHtml(r.final_note)}</details>
 </aside></div></div>`;
 document.body.dataset.workspace='scribbi';
 view().querySelectorAll('[data-next]').forEach(b=>b.onclick=()=>nextAction(b.dataset.next,p,b));
 if(animate&&!reduced()){
  requestAnimationFrame(()=>requestAnimationFrame(()=>{const f=$('.sb-ring .fill');if(f)f.style.strokeDashoffset=326.7*(1-r.score/100);}));
  const num=$('#sbScoreNum');const t0=performance.now();const run=t=>{const k=Math.min(1,(t-t0)/1100);if(num)num.textContent=Math.round(r.score*(1-Math.pow(1-k,3)));if(k<1)requestAnimationFrame(run);};requestAnimationFrame(run);
  if(r.score>=95&&r.safe)confetti();
 }
 try{view().focus({preventScroll:true});}catch(e){}
 window.scrollTo({top:0,behavior:'instant'});
 say(`Note signed. Score ${r.score}. ${headline}`);
}
function quoteBody(q,name){
 if(q.kind==='talk')return `<b>You</b>${E(q.student)}<br><b>${E(firstName(name))}</b>${E(q.patient)}`;
 if(q.kind==='exam')return `<b>${q.felt?'You felt':'Exam'}</b>${E(q.label)}: ${E(q.finding)}`;
 return `<b>${E(q.label||'Chart')}</b>${E(q.text||'')}`;
}
function itemHtml(it,name){
 const [vi,vl]=verdictPill(it.verdict);
 const gap=!it.planted;
 const where=[it.section_title,it.label].filter(Boolean).join(' · ');
 const yours=it.student_text?E(it.student_text):it.verdict==='missed'?(gap?'Not added':'Left as Scribbi wrote it'):(gap?'Not added':'Removed');
 return `<article class="sb-item v-${it.verdict}"><div class="sb-item-head"><span class="sb-type-icon">${ic(TYPE_ICON[it.type])}</span><div><b>${E(it.type_label)}</b><small>${E(where)}${it.severity==='high'?' · could change care':''}</small></div><span class="sb-verdict">${ic(vi)}${E(vl)}</span></div>
 <div class="sb-item-body"><div class="sb-compare"><div class="was ${gap?'is-gap':''} ${!gap&&it.verdict==='missed'?'is-still':''}"><h4>${gap?(it.type==='hands_on'?'Scribbi couldn’t feel':'Scribbi left out'):it.verdict==='missed'?'Still in your note':'Scribbi wrote'}</h4><p>${E(gap?it.original:it.planted)}</p></div><div class="now ${it.verdict==='missed'?'is-none':''}"><h4>Your note</h4><p>${yours}</p></div></div>
 ${it.correct&&!gap?`<div class="sb-evid"><h4>${E(it.correct_label||'What the visit supports')}</h4><div class="q">${E(it.correct)}</div></div>`:''}
 ${(it.evidence||[]).length?`<div class="sb-evid"><h4>In the visit</h4>${it.evidence.slice(0,3).map(q=>`<div class="q">${quoteBody(q,name)}</div>`).join('')}</div>`:''}
 <div class="sb-why"><div><h4>What went wrong</h4><p>${E(it.note)}</p>${it.why?`<h4 style="margin-top:10px">Why scribes do this</h4><p>${E(it.why)}</p>`:''}</div><div><h4>Why it matters</h4><p>${E(it.risk)}</p></div><div class="sb-habit">${ic('bulb')}<span>${E(it.habit)}</span></div></div></div></article>`;
}
function finalNoteHtml(sections){
 return (sections||[]).map(sec=>`<div class="sb-sec"><div class="sb-sec-head"><span class="sb-sec-letter">${sec.key}</span><h3>${E(sec.title)}</h3></div>${sec.lines.map(ln=>{const ap=sec.key==='A'||sec.key==='P';const chips=ln.chips.map(ch=>{const v=ch.error?.verdict||'';const txt=ch.status==='edited'?ch.edited:ch.text;return `<span class="sb-fnote-chip ${ch.status==='removed'?'is-removed':''} ${v?'v-'+v:''}">${E(txt)}</span>`;}).join(' ');return `<div class="sb-line ${ap?'is-ap':''}"><span class="sb-label">${E(ap?ln.label+'.':ln.label)}</span><p class="sb-text">${chips}</p></div>`;}).join('')}${(sec.added||[]).map(a=>`<span class="sb-fnote-add">${E(a.text)}</span>`).join('')}</div>`).join('');
}
async function nextAction(kind,p,btn){
 if(kind==='home'){location.hash='#scribbi';return;}
 if(kind==='again')return startRound(own(p)&&p.source_attempt_id?{attempt_id:p.source_attempt_id,mode:p.mode.key,timed:p.timed,again:true}:{case_id:p.case_id,variant_id:p.variant_id,mode:p.mode.key,timed:p.timed},btn);
 // A new patient keeps the way this student likes to meet the visit: watch, lead or read.
 const style=homeSel?.style||store.get('prefs')?.style||'read';
 if(kind==='new'){if(style==='lead')return startLead({random:true},btn);return startRound({random:true,mode:p.mode.key,timed:p.timed,watch:style==='watch'},btn);}
 if(kind==='chatcse'){
  btn.disabled=true;
  const s=await call('/api/session',{case_id:p.case_id,variant_id:p.variant_id,learning_mode:'guided',interaction_mode:'type'});
  btn.disabled=false;
  if(s.error||!s.id){pop(s.error==='offline'?'The local engine is unavailable.':(s.error||'Could not start the encounter.'));return;}
  location.hash='#/'+s.id;
 }
}
function confetti(){
 const box=document.createElement('div');box.className='sb-confetti';const colors=['#8a80ff','#ffd66b','#6fd3a3','#ff9fbe','#5549dc'];
 for(let i=0;i<70;i++){const c=document.createElement('i');c.style.left=Math.random()*100+'vw';c.style.background=colors[i%colors.length];c.style.setProperty('--dx',(Math.random()*160-80)+'px');c.style.setProperty('--rot',(Math.random()*720-360)+'deg');c.style.animationDuration=(1.8+Math.random()*1.6)+'s';c.style.animationDelay=(Math.random()*.4)+'s';box.appendChild(c);}
 document.body.appendChild(box);setTimeout(()=>box.remove(),4200);
}

/* ---------- shared ---------- */
function errorView(title,message,retry){
 view().innerHTML=`<div class="sb-shell"><section class="sb-lock">${mascot('oops')}<div><h2>${E(title)}</h2><p>${E(message||'Something went wrong.')}</p><div class="sb-hero-actions"><button class="sb-btn sb-primary" id="sbRetry">Try again</button><button class="sb-btn" id="sbHomeBtn">Scribbi home</button></div></div></section></div>`;
 $('#sbRetry').onclick=retry;$('#sbHomeBtn').onclick=()=>{if(location.hash==='#scribbi')renderHome();else location.hash='#scribbi';};
}
window.addEventListener('hashchange',()=>{if(R&&!location.hash.startsWith('#scribbi/r/'+R.round.id)){flushSave(null);document.removeEventListener('keydown',docKeys);clearInterval(R.timer);}});

/* ---------- integration with the rest of the app ---------- */
async function startFor(caseId,variantId,mode,button){return startRound({case_id:caseId,variant_id:variantId||'base',mode:mode||'coached'},button);}
function launchCard(caseId,variantId,patientName,attemptId){
 const who=E(firstName(patientName)||'the patient');
 return `<div class="sb-launch-card">${mascot('happy')}<div><b>Now let Scribbi draft this visit</b><span>Scribbi writes ${who}’s note from ${attemptId?'your own encounter':'the demonstrated visit'}, with mistakes. Can you catch them before you sign?${attemptId?` <a href="#" data-scribbi-start data-case="${E(caseId)}" data-variant="${E(variantId||'base')}" data-mode="coached">Use the full demonstrated visit instead</a>`:''}</span></div>${attemptId?`<button class="sb-btn sb-primary sb-sm" data-scribbi-attempt="${E(attemptId)}" data-mode="coached">Review Scribbi’s draft ${ic('arrow')}</button>`:`<button class="sb-btn sb-primary sb-sm" data-scribbi-start data-case="${E(caseId)}" data-variant="${E(variantId||'base')}" data-mode="coached">Review Scribbi’s draft ${ic('arrow')}</button>`}</div>`;
}
document.addEventListener('click',e=>{
 const own=e.target.closest('[data-scribbi-attempt]');
 if(own){e.preventDefault();startFromAttempt(own.dataset.scribbiAttempt,own.dataset.mode,own);return;}
 const b=e.target.closest('[data-scribbi-start]');if(!b)return;e.preventDefault();startFor(b.dataset.case,b.dataset.variant,b.dataset.mode,b);});
async function startFromAttempt(attemptId,mode,button){
 const label=button?.innerHTML;if(button){button.disabled=true;button.innerHTML='Scribbi is drafting…';}
 const r=await call('/api/scribbi/rounds',{attempt_id:attemptId,mode:mode||'coached'});
 if(button&&button.isConnected){button.disabled=false;button.innerHTML=label;}
 if(r.error||!r.id){
  if(r.too_short){if(await confirmBox(r.error,{title:'Not enough to draft yet',confirm:'Use the full visit',cancel:'Not now'}))startFor(r.case_id,r.variant_id,mode||'coached');return;}
  pop(r.error==='offline'?(r.message||'The local engine is unavailable.'):(r.error||'Scribbi could not draft your visit.'));return;
 }
 store.set('fresh',r.id);location.hash='#scribbi/r/'+r.id;
}
async function progressPanel(container){
 if(!container)return;
 const d=await call('/api/scribbi');if(d.error||!container.isConnected)return;
 const box=document.createElement('section');box.className='sb-card sb-progress-card';box.setAttribute('aria-labelledby','sbProgHead');
 // Scores lists every review, open visits included, with the same filters as Chat CSE.
 const rows=d.recent||[],visits=d.open_visits||[];
 const visitRows=visits.map(v=>`<button class="sb-recent-row" data-state="open" data-visit="${E(v.id)}"><span class="sb-score-dot is-open">${ic('pen')}</span><span><b>${E(v.title||'Your visit')}</b><small>Your visit · still open · started ${when(v.created_at)}</small></span><span class="sb-pill">Back to the visit</span></button>`).join('');
 const open=visits.length+rows.filter(r=>r.status!=='signed').length,signed=rows.filter(r=>r.status==='signed').length,all=open+signed;
 const filters=all?`<div class="attempt-filter" role="group" aria-label="Show reviews">${[['all','All',all],['open','In progress',open],['done','Signed',signed]].map(([k,l,n])=>`<button class="btn sm ghost" type="button" data-review-filter="${k}" aria-pressed="${k==='all'}">${l} <span class="attempt-count">${n}</span></button>`).join('')}</div>`:'';
 box.innerHTML=`<div class="sb-section-head"><h2 id="sbProgHead" style="display:flex;align-items:center;gap:10px"><span style="width:34px;display:inline-block">${mascot('happy')}</span>Scribbi reviews</h2><button class="sb-btn sb-sm" data-go-scribbi>Open Scribbi ${ic('arrow')}</button></div>${statsHtml(d.stats||{})}${filters}${all?`<div style="margin-top:12px">${recentHtml(rows,40,visitRows)}</div>`:''}`;
 container.appendChild(box);
 box.querySelector('[data-go-scribbi]').onclick=()=>{location.hash='#scribbi';};
 box.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>{location.hash='#scribbi/r/'+b.dataset.open;});
 box.querySelectorAll('[data-visit]').forEach(b=>b.onclick=()=>{location.hash='#/'+b.dataset.visit;});
 box.querySelectorAll('[data-review-filter]').forEach(b=>b.onclick=()=>{const k=b.dataset.reviewFilter;box.querySelectorAll('[data-review-filter]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));box.querySelectorAll('.sb-recent-row').forEach(r=>{r.hidden=k!=='all'&&r.dataset.state!==k;});});
}
async function summary(){const d=await call('/api/scribbi');return d.error?null:{stats:d.stats,recent:d.recent,locked:d.locked,open_visits:d.open_visits||[]};}
window.pcmScribbi={render,startFor,launchCard,progressPanel,summary,mascot,finishVisit,kit:{ic,mascot,call,store,reduced,pop}};
})();
