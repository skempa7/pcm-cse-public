/* Worked examples and answer documents live behind the same backend assistance gate in every tab. */
(()=>{'use strict';
const $=s=>document.querySelector(s), esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let request=0;
let accessCheck=0, forcedAccessChecks=0, approvedPrint=false, printDialogOpen=false, tabPaused=false;
let printModule=null, printTask=0, printReturn=null, printProtected=false;
function closePrintChoice(){document.getElementById('printDocumentChoice')?.close();document.getElementById('printDocumentChoice')?.remove();}
window.addEventListener('hashchange',closePrintChoice);
const accessKey='pcmcse.solution-access-change.v1';
let accessChannel=null;try{accessChannel=new BroadcastChannel(accessKey);}catch{}
// Only a worked example itself shows answers; the list of them doesn't.
const inLibrary=()=>/^#learn\/./.test(location.hash);
function coverSolutions(message='Checking for open encounters before showing the answers…'){
 if(!inLibrary()&&!printProtected)return;
 approvedPrint=false;document.body.removeAttribute('data-walkthrough-print');document.body.removeAttribute('data-walkthrough-preview');
 const view=$('#view');view.classList.add('solution-locked');
 let box=$('#solutionStatus');if(!box){box=document.createElement('div');box.id='solutionStatus';box.className='solution-status card';box.setAttribute('role','status');view.append(box);}
 const open=window.pcmActiveAttempt?.()||null;
 box.innerHTML=`<h2>Answers are hidden during an unassisted encounter</h2><p>${esc(message)}</p>${open?`<a class="btn primary" href="#/${esc(open)}">Resume my encounter</a> `:''}<button class="btn${open?'':' primary'}" id="reviewSolutionAccess">Open answers anyway…</button> <a class="btn ghost" href="#learn">All worked examples</a>`;
 $('#reviewSolutionAccess').onclick=()=>{if(/^#cases(?:\/|$)/.test(location.hash)){closePrintedLesson();renderMaterials(location.hash.slice(1));}else render(location.hash.slice(1));};
}
function notifyAccess(pending){const value={pending,at:Date.now(),nonce:Math.random()};try{localStorage.setItem(accessKey,JSON.stringify(value));}catch{}try{accessChannel?.postMessage(value);}catch{}coverSolutions('An unassisted encounter is starting, so answers stay hidden.');}
async function verifyCached(force=false){
 // Periodic probes must not cancel the access check started by a user action.
 if(!inLibrary()&&!printProtected)return true;
 if(!force&&forcedAccessChecks)return false;
 if(force)forcedAccessChecks++;
 const token=++accessCheck;
 try{
  const r=await api('/api/teaching/status');if(token!==accessCheck||(!inLibrary()&&!printProtected))return false;
  if(r.error)throw Error(r.error);
  let pending=false;try{const v=JSON.parse(localStorage.getItem(accessKey)||'null');pending=v?.pending&&Date.now()-v.at<30000;}catch{}
  if(r.requires_assistance||pending){coverSolutions(r.requires_assistance?'You have an open Independent or Exam rehearsal encounter. Worked examples show the answers, so opening one marks that encounter as assisted practice. Your work and timer are kept.':'An unassisted encounter is starting. Wait a moment, then check again.');return false;}
  if(document.hidden||tabPaused)return false;
  $('#view').classList.remove('solution-locked');$('#solutionStatus')?.remove();return true;
 }catch{coverSolutions('We couldn’t check for open encounters, so answers stay hidden. Reload the page to try again; your work is saved in this browser.');return false;}
 finally{if(force)forcedAccessChecks--;}
}
const accessChanged=()=>{accessCheck++;coverSolutions('Your open encounters changed. Check again to continue.');};
if(accessChannel)accessChannel.onmessage=accessChanged;
window.addEventListener('storage',e=>{if(e.key===accessKey)accessChanged();});
window.addEventListener('focus',()=>{verifyCached();});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)verifyCached();});
window.addEventListener('pagehide',()=>{tabPaused=true;coverSolutions();});window.addEventListener('pageshow',()=>{tabPaused=false;verifyCached(true);});
window.addEventListener('hashchange',()=>{if(!inLibrary()){$('#view').classList.remove('solution-locked');$('#solutionStatus')?.remove();}});
function closePrintedLesson(){
 approvedPrint=false;printDialogOpen=false;printTask++;printModule?.clearWalkthroughPrint();
 const previous=printReturn;printReturn=null;printProtected=false;$('#printLessonStatus')?.replaceChildren();
 if(!inLibrary()){$('#view').classList.remove('solution-locked');$('#solutionStatus')?.remove();}
 if(previous?.route===location.hash){document.getElementById(previous.focusId||'printLesson')?.focus({preventScroll:true});window.scrollTo(previous.x,previous.y);}
}
window.addEventListener('beforeprint',()=>{
 if(!approvedPrint||!document.body.hasAttribute('data-walkthrough-preview'))coverSolutions('To print, use Print documents or Printable cases.');
 else printDialogOpen=true;
});
window.addEventListener('afterprint',()=>{closePrintedLesson();verifyCached(true);});
window.addEventListener('hashchange',closePrintedLesson);
window.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.hasAttribute('data-walkthrough-preview')){e.preventDefault();closePrintedLesson();}});
async function choosePrintDocument(l){
 const previous={route:location.hash,x:window.scrollX,y:window.scrollY};
 if(!await verifyCached(true))return;
 closePrintChoice();
 const dialog=document.createElement('dialog');dialog.id='printDocumentChoice';dialog.className='print-document-choice';
 dialog.setAttribute('aria-labelledby','printChoiceTitle');
 const catalog=(await import(new URL('./partner-print.js?v=f2f855ba0a',location.href))).PRINT_EDITIONS;
 dialog.innerHTML=`<form method="dialog"><h2 id="printChoiceTitle">Print documents for this case</h2><fieldset><legend>Choose a document</legend>${Object.entries(catalog).map(([id,item])=>`<label><input type="radio" name="edition" value="${id}" ${id==='patient'?'checked':''}><span><b>${esc(item.label)}</b><small>${esc(item.description)}</small></span></label>`).join('')}</fieldset><div class="print-choice-actions"><button class="btn" value="cancel">Cancel</button><button class="btn primary" id="preparePrintDocument" value="prepare">Prepare preview</button></div></form>`;
 document.body.append(dialog);dialog.showModal();
 dialog.addEventListener('close',()=>{const edition=dialog.querySelector('input:checked')?.value,prepare=dialog.returnValue==='prepare';dialog.remove();if(prepare)printLesson(l,edition,previous);else {$('#printLesson')?.focus({preventScroll:true});window.scrollTo(previous.x,previous.y);}},{once:true});
}
async function printLesson(l,edition='patient',returnPosition=null){
 const token=++printTask,route=location.hash,button=document.getElementById(returnPosition?.focusId||'printLesson'),previous=returnPosition||{route,x:window.scrollX,y:window.scrollY};
 if(!await verifyCached(true))return;
 if(token!==printTask||location.hash!==route||!button?.isConnected)return;
 printReturn=previous;
 const oldButton=button.innerHTML;button.disabled=true;button.textContent='Preparing pages…';
 let status=$('#printLessonStatus');if(!status){status=document.createElement('p');status.id='printLessonStatus';status.setAttribute('role','status');(button.closest('.reader-top')||button.parentElement).after(status);}
 status.className='small muted';status.textContent='Preparing pages…';
 try{
  printModule=printModule||await import(new URL('./walkthrough-print.js?v=ccec6b3a8f',location.href));
  const prepared=await printModule.prepareWalkthrough(l,{edition});
  if(token!==printTask||location.hash!==route){printModule.clearWalkthroughPrint(prepared.root);return;}
  if(!await verifyCached(true)){printModule.clearWalkthroughPrint(prepared.root);return;}
  if(token!==printTask||location.hash!==route){printModule.clearWalkthroughPrint(prepared.root);return;}
  const openPreview=()=>{approvedPrint=true;printModule.showWalkthroughPreview({onClose:closePrintedLesson,onPrint:async()=>{
   if(!await verifyCached(true))return;
   if(token!==printTask||location.hash!==route)return;
   openPreview();printDialogOpen=true;window.print();
  }});};
  status.textContent=`${printModule.PRINT_EDITIONS[edition].label}: ${prepared.report.pages} page${prepared.report.pages===1?'':'s'} ready.`;
  openPreview();
 }catch(e){if(token!==printTask||location.hash!==route)return;printModule?.clearWalkthroughPrint();approvedPrint=false;status.textContent='This document could not be prepared ('+e.message.replace(/\.$/,'')+'). Nothing was changed. Try again, or read it in the worked example.';}
 finally{if(button.isConnected){button.disabled=false;button.innerHTML=oldButton;}}
}
setInterval(()=>{if((inLibrary()||printProtected)&&!document.hidden)verifyCached();},2000);
async function api(path,body){const r=await fetch(path,{cache:'no-store',method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});return r.json();}
function heading(kicker,title,sub){return `<div class="workbench-heading"><div>${kicker?`<div class="eyebrow">${kicker}</div>`:''}<h1>${title}</h1>${sub?`<p>${sub}</p>`:''}</div>${window.pcmLastAttempt?'<a class="btn" href="#/'+esc(window.pcmLastAttempt)+'">Resume your encounter</a>':''}</div>`;}
// Search matches every word typed, anywhere in the case's title, description or system.
function matches(q,text){const words=q.toLowerCase().split(/\s+/).filter(Boolean),hay=text.toLowerCase();return words.every(w=>hay.includes(w));}
function noMatch(q){return `<p role="status">No cases match “${esc(q)}”. Try one word, like “cough”.</p>`;}
function count(n,one,many){return n+' '+(n===1?one:(many||one+'s'));}
// Plain labels for what a variation changes.
const DIFF_LABEL={hpi_onset:'When it started',care_barrier:'Barrier to the care plan',chronology:'Timeline',onset:'When it started'};
function diffLabel(key){return DIFF_LABEL[key]||String(key||'').replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());}
function reviewLine(text){return /deterministic engine|source-linked authored/i.test(text||'')?'Written from the course materials and the sources below; every variation was replayed in the simulator. Not reviewed or approved by faculty.':text;}
function sourceLine(source){
 if(typeof source==='string')return '<li>'+esc(source)+'</li>';
 const label=source.title||source.label||source.document||(source.path||'').split('/').pop()||'Source reference';
 const url=source.url||source.source_url;
 const title=url&&/^https:\/\//.test(url)?`<a href="${esc(url)}" target="_blank" rel="noopener">${esc(label)}</a>`:esc(label);
 return '<li>'+title+(source.locator?' — '+esc(source.locator):'')+(source.reviewed?' · reviewed '+esc(source.reviewed):'')+'</li>';
}
async function guard(){let r=await api('/api/teaching');if(r.requires_assistance){const n=r.attempts.length,first=r.attempts[0],where=first?` (${first.station}${first.phase==='briefing'?', at the doorway':''})`:'';const yes=await window.pcmConfirmChoice(`Worked examples and answer documents show the answers. Opening one now marks your open Independent or Exam rehearsal encounter${n>1?'s':''}${n===1?where:''} as assisted practice in Scores. Your note, findings and timer don't change.`,{title:'Switch to assisted practice?',confirm:'Open and mark as assisted',cancel:'Go back'});if(!yes)return null;const access=await api('/api/teaching/access',{confirm:true,attempt_ids:r.attempts.map(a=>a.id)});if(access.error)throw Error(access.error);r=await api('/api/teaching');}if(r.error)throw Error(r.error);return r;}
async function render(route){const token=++request;const previous=window.pcmActiveAttempt?.();try{
 const kind=route.split('/')[0],cidInRoute=!!route.split('/')[1];
 const data=kind==='learn'?(cidInRoute?await guard():await api('/api/teaching')):await api('/api/bootstrap');
 if(!data){if(history.length>1)history.back();else location.hash='#learn';return;}
 if(data.error)throw Error(data.error);
 if(!await window.pcmEnterWorkbench(kind))return;
 if(token!==request)return;
 const view=$('#view');window.pcmPortal?.nav(kind);
 if(kind==='progress'){view.innerHTML='<div class="workbench">'+heading('Your practice','Keep the next step small.','Original submissions, assisted practice and retries remain separate.')+`<div class="progress-cards"><div><b>${(data.sessions||[]).filter(s=>s.phase==='submitted').length}</b><span>completed attempts</span></div><div><b>${data.cases?.length||24}</b><span>presentations to explore</span></div></div><section class="card"><h2>Attempts on this computer</h2>${(data.sessions||[]).map(s=>`<a class="attempt-row" href="#/${esc(s.id)}"><span><b>${esc(s.patient_name||s.case_title||s.case_id)}</b><small>${esc(s.phase)} · ${s.assisted?'assisted practice':s.learning_mode==='guided'?'guided learning':s.learning_mode==='coached'?'coached practice':s.learning_mode==='rehearsal'?'exam rehearsal':s.learning_mode==='independent'?'independent practice':'historical attempt'} · ${new Date(s.created_at).toLocaleDateString()}</small></span><span>${s.phase==='submitted'?'Review feedback →':'Resume →'}</span></a>`).join('')||'<p>Your first practice will appear here.</p>'}</section></div>`;return;}
 const cid=route.split('/')[1];if(cid){const params=new URLSearchParams(route.split('?')[1]||'');const clean=cid.split('?')[0];const result=await api('/api/teaching/'+encodeURIComponent(clean)+'?variant='+encodeURIComponent(params.get('variant')||'base'));
 if(result.error){if(result.requires_assistance){coverSolutions(result.error);return;}if(result.not_found&&(params.get('variant')||'base')!=='base'){location.replace('#learn/'+clean);return;}if(result.not_found)return missing(result.error,clean);throw Error(result.error);}if(token!==request)return;coverSolutions();lesson(result.lesson,data);await verifyCached();return;}
 const variations=data.cases.reduce((n,c)=>n+c.walkthroughs.length,0);
 view.innerHTML='<div class="workbench">'+heading('','See the whole encounter.','Read one strong approach, connect every finding to its source, then practice with less help.')+`<div class="library-tools"><label>Find a case<input id="lessonSearch" type="search" placeholder="Headache, urination, chest…"></label><label>System<select id="lessonSystem"><option value="">All systems</option>${window.pcmPortal.orderedSystems(data.cases).map(x=>'<option>'+esc(x)+'</option>').join('')}</select></label><span class="small" id="lessonCount">${count(data.cases.length,'case')} · ${count(variations,'variation')}</span></div><div id="lessonGrid" class="case-library-groups"></div><details class="card"><summary>How these worked examples were made</summary><p>Each worked example was written from the course materials and the clinical sources listed on its page, then replayed in the Chat CSE simulator, so every line of the example note traces back to something the patient said or a finding the student obtained. Faculty have not reviewed them: treat each as one good approach, not an answer key.</p><p>Course rules used: 14-minute encounter, 9-minute SOAP note, the course SOAP rubric and the standardized patient's refusal rules. Practice timing: Guided and Coached encounters are untimed; Independent practice allows 30 minutes for the encounter, 5 to organize and 20 for the note.</p></details></div>`;
 const paint=()=>{const q=$('#lessonSearch').value.trim(),system=$('#lessonSystem').value;const rows=data.cases.filter(c=>(!system||c.system===system)&&matches(q,`${c.title} ${c.blurb} ${c.system}`));$('#lessonCount').textContent=(rows.length===data.cases.length?count(data.cases.length,'case'):`${rows.length} of ${data.cases.length} cases`)+' · '+count(variations,'variation');$('#lessonGrid').innerHTML=window.pcmPortal.groupedCaseLinks(rows,c=>`<a class="lesson-card" href="#learn/${esc(c.id)}"><span class="case-card-art">${window.pcmPortal.illustration(window.pcmPortal.family(c.system))}</span><h2>${esc(c.title)}</h2><p>${esc(c.blurb)}</p><span class="lesson-foot">${count(c.walkthroughs.length,'variation')} · ${data.progress.some(p=>p.case_id===c.id)?'Reflection saved ✓':'Not started'} <b>→</b></span></a>`)||noMatch(q);};$('#lessonSearch').oninput=paint;$('#lessonSystem').onchange=paint;paint();await verifyCached();
 }catch(e){window.pcmPortal?.nav('learn');$('#view').innerHTML=`<div class="workbench"><h1>This page didn't load</h1><p role="alert">${esc(e.message)}</p><button class="btn primary" id="studyRetry">Try again</button> <a class="btn" href="#learn">All worked examples</a></div>`;$('#studyRetry').onclick=()=>render(route);}}
// A worked example that doesn't exist: say so, with the way back.
function missing(message,cid){window.pcmPortal?.nav('learn');$('#view').classList.remove('solution-locked');$('#solutionStatus')?.remove();$('#view').innerHTML=`<div class="workbench"><h1>That worked example isn't available</h1><p>${esc(message)} It may have been renamed.</p><a class="btn primary" href="#learn">All worked examples</a></div>`;}
function clinicalExample(l){
 const n=l.partner_note;
 if(!n)return '<p role="alert">The reviewed example note is unavailable. Reload this case before comparing your note.</p>';
 const paragraph=text=>'<p>'+esc(text).replaceAll('\n','<br>')+'</p>';
 const limits=(n.outside_note||[]).filter(x=>['authoring_gap','source_conflict'].includes(x.kind)).map(x=>'<p class="clinical-key-limit">'+esc(x.text)+'</p>').join('');
 return limits+'<div class="example-note">'+['subjective','objective'].map(group=>'<h3>'+({subjective:'Subjective',objective:'Objective'})[group]+'</h3>'+n[group].map(row=>'<p><b>'+esc(row.heading)+':</b> '+esc(row.text).replaceAll('\n','<br>')+'</p>').join('')).join('')+'<h3>Assessment</h3>'+n.assessment.map(a=>'<h4>'+a.rank+'. '+esc(a.text)+'</h4>'+paragraph(a.reasoning||a.support||'')).join('')+'<h3>Plan</h3>'+n.plan.map(p=>'<h4>'+p.rank+'. '+esc(p.diagnosis)+'</h4>'+(p.rank>1?paragraph(p.condition):'')+paragraph(p.text)).join('')+'</div>';
}
function lesson(l,index){
const draftKey='pcmcse.written-reflection.'+l.case_id+'.'+l.variant_id;let localDraft=null;
try{localDraft=JSON.parse(localStorage.getItem(draftKey)||'null');}catch{}
const variants=index.cases.find(c=>c.id===l.case_id).walkthroughs;const events=new Map(l.ledger.map(e=>[e.seq,e]));const phaseLinks=['doorway','encounter','reasoning','soap','recall'];
const system=index.cases.find(c=>c.id===l.case_id)?.system||'',est=l.current_demonstration_estimate_s??l.estimated_encounter_s;
$('#view').innerHTML=`<div class="lesson-reader"><div class="reader-top"><a href="#learn">← Worked examples</a><button class="btn sm" id="printLesson">Print documents</button><button class="btn primary sm" id="practiceLesson" title="Starts a new Coached encounter, recorded as assisted because you've read the worked example">Practice this case</button></div>${heading('Worked example'+(system?' · '+esc(system):''),esc(l.title),esc(l.patient.name)+' · '+l.patient.age+' · '+esc(l.variant_label))}<div class="reader-meta"><label>Variation<select id="lessonVariant">${variants.map(v=>`<option value="${esc(v.id)}" ${v.id===l.variant_id?'selected':''}>${esc(v.label)}</option>`).join('')}</select></label><p>About <b>${Math.floor(est/60)} min ${est%60} s</b> to perform · <b>${l.note_words}-word</b> example note<br><small>${est>840?'Longer than the 14-minute encounter because it shows every examination. In a timed encounter, choose the examinations that answer the key question in section 3.':'Fits the 14-minute encounter and 9-minute note.'}</small></p></div><nav class="reader-toc" aria-label="Worked example sections">${phaseLinks.map(k=>`<button class="btn ghost sm" data-section="${k}">${({doorway:'1 Doorway',encounter:'2 Encounter',reasoning:'3 Reasoning',soap:'4 SOAP note',recall:'5 Recall'})[k]}</button>`).join('')}</nav><p class="small" id="practiceStatus" role="status"></p>
<section id="lesson-doorway"><h2>1. At the doorway</h2><div class="doorway-written">${l.doorway.doorway.map(t=>'<p>'+esc(t)+'</p>').join('')}<dl class="written-vitals">${Object.entries(l.doorway.vitals).map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>${(l.doorway.supplied_results||[]).map(x=>'<p>Supplied '+esc(x.label)+': '+esc(x.value)+'</p>').join('')}</div><p class="learning-anchor">${esc(l.plan.anchor)}</p><p>${esc(l.plan.notice)}</p><p>${esc(l.plan.pivot)}</p>${l.variant_id!=='base'?`<aside class="variant-note"><h3>What's different in this variation</h3><p>${esc(l.variant_guidance)}</p>${l.differences.map(d=>`<p><b>${esc(diffLabel(d.topic))}:</b> ${esc(d.current)}<br><small>Core case: ${esc(/^not authored$/i.test(String(d.base||'').trim())?'none':d.base)}</small></p>`).join('')}</aside>`:''}</section>
<section id="lesson-encounter"><h2>2. The encounter</h2><p>Read the dialogue and actions in order. This is one defensible approach, with room to adapt to the patient. Open “Why this step matters” after your first read.</p>${l.plan.urgent?'<div class="clinical-priority">Urgent care takes priority. The example states escalation early; continue nonurgent questions or examinations only if care permits. A real patient should not wait for checklist completion.</div>':''}<details><summary>How the time was estimated</summary><p>Speaking at 150 words a minute, plus the time each examination takes in the simulator, plus about a minute for introductions. Writing this ${l.note_words}-word note in 9 minutes means about ${Math.ceil(l.note_words/9)} words a minute, so expect to write a shorter note under exam timing. Virtual actions can't check touch, force, what you hear through a stethoscope or full technique.</p></details><div class="example-transcript">${l.timeline.map((t,i)=>`<article class="example-turn ${t.kind}" id="turn-${i}"><div class="turn-phase">${esc(t.section)}</div>${t.kind==='dialogue'?`<p><b>Student</b> ${esc(t.student)}</p>${t.patient?`<p><b>Patient</b> ${esc(t.patient)}</p>`:''}`:`<p><b>Action</b> ${esc(t.action)}</p>${t.finding?`<p class="obtained-finding"><b>Finding obtained</b> ${esc(t.finding)}</p>`:''}`}${t.why?`<details><summary>Why this step matters</summary><p>${esc(t.why)}</p></details>`:''}</article>`).join('')}</div></section>
<section id="lesson-reasoning"><h2>3. From findings to a decision</h2><p>${esc(l.plan.exam)}</p>${l.reasoning.map(r=>`<div class="reasoning-card"><h3>${esc(r.question)}</h3><p>${esc(r.why)}</p><p><b>If present:</b> ${esc(r.if_present)}</p><p><b>If absent:</b> ${esc(r.if_absent)}</p><p><b>Next action:</b> ${esc(r.next_action)}</p></div>`).join('')}<p>Assessment contains clinical inferences. Neither a differential nor its mnemonic category proves the diagnosis. Consider urgent alternatives even when they are less likely.</p><details><summary>Memory tools, expanded and used in context</summary><p><b>FIFE:</b> the syllabus groups Feelings/Fears; Insight/Ideas; Function/Effects; Expectations. At the patient-perspective turn, ask what worries the patient and how symptoms affect daily life. Use what they actually report; an unanswered topic remains unknown.</p><p><b>VINDICATE:</b> a common expansion is Vascular, Infectious, Neoplastic, Degenerative/Deficiency, Iatrogenic/Intoxication, Congenital, Autoimmune, Traumatic, Endocrine/Metabolic. The course requires three different categories; the course materials don't define every letter or where every diagnosis belongs. Organize reasonable alternatives, not implausible diagnoses chosen just to fill letters.</p><p><b>MOTHERR:</b> Medications, Osteopathic treatment, Testing, Humanistic / supportive needs, Education, Referral, Return/follow-up. Consider function, support, and the ability to carry out the plan. The course requires at least three different elements per paired plan. This is a working expansion; see <a href="#scoring">How scoring works</a> for its source. For this case, connect the actual first plan's proposed tests, explanation and disposition; do not add unnecessary treatment to collect letters.</p><p><b>When blank:</b> pause → name your phase → recall its purpose → choose one relevant question or action. This recovery cue is supplementary teaching, not a scored course mnemonic.</p></details><h3>Common traps</h3><p>${esc(l.plan.avoid)}</p><ul>${l.omissions.map(x=>'<li>'+esc(x)+'</li>').join('')}</ul></section>
<section id="lesson-soap"><h2>4. The example SOAP note</h2><p>Subjective reports what the patient said; Objective records supplied information and completed examination findings. Assessment is inference; Plan describes proposed future care. Do not copy this note into an attempt where you did not obtain its evidence.</p>${clinicalExample(l)}<h3>Where the note came from</h3>${l.note_links.map(link=>`<details class="source-link"><summary><span>${esc(link.section)}</span> ${esc(link.statement)}</summary><p><b>${esc(link.classification)}</b> · ${esc(link.trace_method)}</p>${link.event_ids.map(id=>events.get(id)).filter(Boolean).map(e=>`<blockquote><small>Event ${e.seq} · ${esc(e.kind.replaceAll('_',' '))}</small><br>${esc(e.text)}</blockquote>`).join('')}</details>`).join('')}<p>Tests listed in the Plan haven't been done yet, so their results never go in Objective.</p></section>
<section id="lesson-recall"><h2>5. Check your recall</h2><p>Answer from memory, then compare. Reflections are saved with this case and don't affect your scores.</p>${l.recall.map((r,i)=>`<div class="recall-card"><label for="recall-${i}">${i+1}. ${esc(r.prompt)}</label><textarea id="recall-${i}" maxlength="2000" rows="3" placeholder="Recall first, then check…">${esc((localDraft||JSON.parse(index.progress.find(p=>p.case_id===l.case_id&&p.variant_id===l.variant_id)?.recall_json||'[]'))[i]||'')}</textarea><details><summary>Compare with the example answer</summary><p>${esc(r.answer)}</p></details></div>`).join('')}<button class="btn primary" id="saveRecall">Save reflection</button><span id="recallStatus" role="status"></span></section>
<footer class="lesson-sources"><h2>Sources and review status</h2><p>${esc(reviewLine(l.review_status))}</p><ul>${l.course_sources.map(s=>`<li>${esc(s.label)} — ${esc(s.locator)}</li>`).join('')}${l.sources.map(sourceLine).join('')}</ul></footer></div>`;
$('#lessonVariant').onchange=e=>location.hash='#learn/'+l.case_id+'?variant='+encodeURIComponent(e.target.value);
document.querySelectorAll('[data-section]').forEach(b=>b.onclick=async()=>{if(!await verifyCached(true))return;$('#lesson-'+b.dataset.section).scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});} );
$('#printLesson').onclick=()=>choosePrintDocument(l);$('#practiceLesson').onclick=async e=>{const b=e.currentTarget;if(b.disabled)return;b.disabled=true;b.textContent='Starting…';const r=await api('/api/session',{case_id:l.case_id,variant_id:l.variant_id,learning_mode:'coached',from_walkthrough:true});if(r.error){b.disabled=false;b.textContent='Practice this case';$('#practiceStatus').textContent=r.error;return;}location.hash='#/'+r.id;};
l.recall.forEach((_,i)=>$('#recall-'+i).oninput=()=>{try{localStorage.setItem(draftKey,JSON.stringify(l.recall.map((_,j)=>$('#recall-'+j).value)));$('#recallStatus').textContent='Draft kept in this browser. Select Save reflection to keep it with this case.';}catch{$('#recallStatus').textContent='Browser draft storage unavailable. Use Save reflection before leaving.';}});
$('#saveRecall').onclick=async()=>{if(!l.recall.some((_,i)=>$('#recall-'+i).value.trim())){$('#recallStatus').textContent='Write at least one answer before saving.';return;}try{const r=await api('/api/teaching/progress',{case_id:l.case_id,variant_id:l.variant_id,answers:l.recall.map((_,i)=>$('#recall-'+i).value)});$('#recallStatus').textContent=r.error||r.message;if(r.saved){try{localStorage.removeItem(draftKey);}catch{}}}catch(e){$('#recallStatus').textContent='Could not save. Keep this page open and try again.';}};
}
async function renderMaterials(route){
 const token=++request,routeHash=location.hash,current=()=>token===request&&location.hash===routeHash,view=$('#view');printProtected=false;view.classList.remove('solution-locked');$('#solutionStatus')?.remove();
 view.innerHTML='<div class="workbench"><p role="status">Loading…</p></div>';
 try{
  const data=await api('/api/printables');if(data.error)throw Error(data.error);if(!current())return;
  window.pcmPortal?.nav('cases');
  const params=new URLSearchParams(route.split('?')[1]||''),cid=(route.split('/')[1]||'').split('?')[0],variant=params.get('variant')||'base';
  if(!cid){
   view.innerHTML=`<div class="workbench materials-library">${heading('','Practice together. Study independently.','Choose a case, then print only the documents you need.')}<p class="material-intro"><b>Partner practice:</b> student copy for you; patient script and findings for your partner. <b>Individual study:</b> write first, then open the example note.</p><div class="library-tools"><label>Find a case<input id="materialSearch" type="search" placeholder="Cough, knee, rash…"></label><label>System<select id="materialSystem"><option value="">All systems</option>${window.pcmPortal.orderedSystems(data.cases).map(x=>'<option>'+esc(x)+'</option>').join('')}</select></label><span class="small" id="materialCount">${count(data.cases.length,'case')}</span></div><div id="materialGrid" class="case-library-groups"></div></div>`;
   const paint=()=>{const q=$('#materialSearch').value.trim(),system=$('#materialSystem').value,rows=data.cases.filter(c=>(!system||c.system===system)&&matches(q,`${c.title} ${c.blurb||''} ${c.system}`));$('#materialCount').textContent=rows.length===data.cases.length?count(data.cases.length,'case'):`${rows.length} of ${data.cases.length} cases`;$('#materialGrid').innerHTML=window.pcmPortal.groupedCaseLinks(rows,c=>`<a class="lesson-card" href="#cases/${esc(c.id)}"><span class="case-card-art">${window.pcmPortal.illustration(window.pcmPortal.family(c.system))}</span><h2>${esc(c.title)}</h2><span class="lesson-foot">${count(c.variants.length,'variation')} <b>Choose documents →</b></span></a>`)||noMatch(q);};$('#materialSearch').oninput=paint;$('#materialSystem').onchange=paint;paint();return;
  }
  const c=data.cases.find(c=>c.id===cid);if(!c)throw Error('This case could not be found.');
  const result=await api('/api/printables/'+encodeURIComponent(cid)+'?variant='+encodeURIComponent(variant));if(result.error)throw Error(result.error);if(!current())return;
  const l=result.material,m=await import(new URL('./partner-print.js?v=f2f855ba0a',location.href));if(!current())return;
  const option=id=>`<button type="button" class="material-option" id="material-${id}" data-material="${id}"><b>${esc(m.PRINT_EDITIONS[id].label)}</b><span>${esc(m.PRINT_EDITIONS[id].description)}</span><small>Preview & print →</small></button>`;
  const who=[l.patient.name,l.patient.age&&(l.patient.age+' years'),l.patient.sex].filter(Boolean).map(esc).join(' · ');
  view.innerHTML=`<div class="workbench materials-case"><div class="reader-top"><a href="#cases">← Printable cases</a><a class="btn ghost" href="#learn/${esc(cid)}?variant=${esc(variant)}">Read the worked example →</a><button class="btn" id="materialPractice" title="Starts a new Coached encounter">Practice this case</button></div>${heading('Printable case',esc(c.title),who)}${c.variants.length>1?`<label class="material-variant">Variation<select id="materialVariant">${c.variants.map(v=>`<option value="${esc(v.id)}" ${v.id===variant?'selected':''}>${esc(v.label)}</option>`).join('')}</select></label>`:''}<p class="material-intro">Practicing with a partner? Print the <b>Student copy</b> for yourself and the <b>Patient script</b> and <b>Examinations and findings</b> for your partner. Studying alone? Print the <b>Student copy</b>, write your note, then open the <b>Example SOAP note</b>.</p><section aria-labelledby="studentMaterialsTitle"><h2 id="studentMaterialsTitle">For you <span class="material-note">No answers</span></h2><div class="material-options">${['student','doorway','blank'].map(option).join('')}</div></section><section aria-labelledby="answerMaterialsTitle"><h2 id="answerMaterialsTitle">For your partner, and for checking <span class="material-note is-answers">Contains answers</span></h2><div class="material-options">${['patient','examiner','soap','study'].map(option).join('')}</div><p class="small muted">If an Independent or Exam rehearsal encounter is open, opening these documents marks it as assisted practice. Your note and timer don't change.</p></section><p id="printLessonStatus" role="status"></p></div>`;
  if($('#materialVariant'))$('#materialVariant').onchange=e=>location.hash='#cases/'+cid+'?variant='+encodeURIComponent(e.target.value);
  let openingMaterial=false;
  view.querySelectorAll('[data-material]').forEach(button=>button.onclick=async()=>{
   if(openingMaterial)return;openingMaterial=true;
   view.querySelectorAll('[data-material]').forEach(b=>b.disabled=true);
   const edition=button.dataset.material,previous={route:location.hash,x:scrollX,y:scrollY,focusId:button.id};
   try{let payload=l;
    if(m.PRINT_EDITIONS[edition].protected){const allowed=await guard();if(!allowed)return;const r=await api('/api/teaching/'+encodeURIComponent(cid)+'?variant='+encodeURIComponent(variant));if(r.error)throw Error(r.error);payload=r.lesson;}
    if(previous.route!==location.hash)return;printProtected=m.PRINT_EDITIONS[edition].protected;await printLesson(payload,edition,previous);
   }catch(e){if(previous.route===location.hash)$('#printLessonStatus').textContent=e.message+' Your saved work is unchanged.';}
   finally{openingMaterial=false;view.querySelectorAll('[data-material]').forEach(b=>b.disabled=false);}
  });
  $('#materialPractice').onclick=async e=>{const b=e.currentTarget;if(b.disabled)return;b.disabled=true;b.textContent='Starting…';const r=await api('/api/session',{case_id:cid,variant_id:variant,learning_mode:'coached'});if(r.error){b.disabled=false;b.textContent='Practice this case';$('#printLessonStatus').textContent=r.error;return;}location.hash='#/'+r.id;};
 }catch(e){if(!current())return;const gone=/could not be found|Unknown printable/i.test(e.message);view.innerHTML=`<div class="workbench"><h1>${gone?"That printable case isn't available":"This page didn't load"}</h1><p role="alert">${esc(gone?'It may have been renamed.':e.message)}</p>${gone?'':'<button class="btn" id="materialRetry">Try again</button> '}<a class="btn primary" href="#cases">Back to printable cases</a></div>`;$('#materialRetry')?.addEventListener('click',()=>renderMaterials(route));}
}

window.pcmStudy={render,renderMaterials,beginProtectedAttempt:()=>notifyAccess(true),endProtectedAttempt:()=>notifyAccess(false)};})();
