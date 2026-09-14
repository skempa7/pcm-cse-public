/* Written teaching lives behind the same backend assistance gate in every tab. */
(()=>{'use strict';
const $=s=>document.querySelector(s), esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let request=0;
let accessCheck=0, forcedAccessChecks=0, approvedPrint=false, printDialogOpen=false, tabPaused=false;
let printModule=null, printTask=0, printReturn=null, printProtected=false;
function closePrintChoice(){document.getElementById('printDocumentChoice')?.close();document.getElementById('printDocumentChoice')?.remove();}
window.addEventListener('hashchange',closePrintChoice);
const accessKey='pcmcse.solution-access-change.v1';
let accessChannel=null;try{accessChannel=new BroadcastChannel(accessKey);}catch{}
const inLibrary=()=>/^#learn(?:\/|$)/.test(location.hash);
function coverSolutions(message='Checking active attempts before showing this lesson…'){
 if(!inLibrary()&&!printProtected)return;
 approvedPrint=false;document.body.removeAttribute('data-walkthrough-print');document.body.removeAttribute('data-walkthrough-preview');
 const view=$('#view');view.classList.add('solution-locked');
 let box=$('#solutionStatus');if(!box){box=document.createElement('div');box.id='solutionStatus';box.className='solution-status card';box.setAttribute('role','status');view.append(box);}
 box.innerHTML=`<h2>Written teaching is paused</h2><p>${esc(message)}</p><button class="btn primary" id="reviewSolutionAccess">Review solution access</button> <a class="btn" href="#">Return to practice</a>`;
 $('#reviewSolutionAccess').onclick=()=>{if(/^#cases(?:\/|$)/.test(location.hash)){closePrintedLesson();renderMaterials(location.hash.slice(1));}else render(location.hash.slice(1));};
}
function notifyAccess(pending){const value={pending,at:Date.now(),nonce:Math.random()};try{localStorage.setItem(accessKey,JSON.stringify(value));}catch{}try{accessChannel?.postMessage(value);}catch{}coverSolutions('An independent attempt is being opened. Answers stay hidden until access is checked.');}
async function verifyCached(force=false){
 // Periodic probes must not cancel the access check started by a user action.
 if(!inLibrary()&&!printProtected)return true;
 if(!force&&forcedAccessChecks)return false;
 if(force)forcedAccessChecks++;
 const token=++accessCheck;if(force)coverSolutions();
 try{
  const r=await api('/api/teaching/status');if(token!==accessCheck||(!inLibrary()&&!printProtected))return false;
  if(r.error)throw Error(r.error);
  let pending=false;try{const v=JSON.parse(localStorage.getItem(accessKey)||'null');pending=v?.pending&&Date.now()-v.at<30000;}catch{}
  if(r.requires_assistance||pending){coverSolutions(r.requires_assistance?'An independent or exam rehearsal attempt is active. Review the effect on assistance before revealing any solution. Your work and deadlines are preserved.':'An independent attempt is being opened. Please wait, then review solution access.');return false;}
  if(document.hidden||tabPaused)return false;
  $('#view').classList.remove('solution-locked');$('#solutionStatus')?.remove();return true;
 }catch{coverSolutions('The server cannot verify solution access. Answers remain hidden; reconnect and try again. Your work is retained.');return false;}
 finally{if(force)forcedAccessChecks--;}
}
const accessChanged=()=>{accessCheck++;coverSolutions('Active attempts changed in another tab. Review solution access to continue.');};
if(accessChannel)accessChannel.onmessage=accessChanged;
window.addEventListener('storage',e=>{if(e.key===accessKey)accessChanged();});
window.addEventListener('blur',()=>{if(!printDialogOpen){tabPaused=true;accessCheck++;coverSolutions();}});
window.addEventListener('focus',()=>{tabPaused=false;verifyCached(true);});
document.addEventListener('visibilitychange',()=>{if(document.hidden){accessCheck++;coverSolutions();}else {tabPaused=false;verifyCached(true);}});
window.addEventListener('pagehide',()=>{tabPaused=true;coverSolutions();});window.addEventListener('pageshow',()=>{tabPaused=false;verifyCached(true);});
window.addEventListener('hashchange',()=>{if(!inLibrary()){$('#view').classList.remove('solution-locked');$('#solutionStatus')?.remove();}});
function closePrintedLesson(){
 approvedPrint=false;printDialogOpen=false;printTask++;printModule?.clearWalkthroughPrint();
 const previous=printReturn;printReturn=null;printProtected=false;
 if(!inLibrary()){$('#view').classList.remove('solution-locked');$('#solutionStatus')?.remove();}
 if(previous?.route===location.hash){document.getElementById(previous.focusId||'printLesson')?.focus({preventScroll:true});window.scrollTo(previous.x,previous.y);}
}
window.addEventListener('beforeprint',()=>{
 if(!approvedPrint||!document.body.hasAttribute('data-walkthrough-preview'))coverSolutions('Use Print case documents to verify solution access before printing.');
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
 const catalog=(await import(new URL('./partner-print.js?v=9639edf495',location.href))).PRINT_EDITIONS;
 dialog.innerHTML=`<form method="dialog"><h2 id="printChoiceTitle">Print for practice</h2><fieldset><legend>Choose a document</legend>${Object.entries(catalog).map(([id,item])=>`<label><input type="radio" name="edition" value="${id}" ${id==='patient'?'checked':''}><span><b>${esc(item.label)}</b><small>${esc(item.description)}</small></span></label>`).join('')}</fieldset><div class="print-choice-actions"><button class="btn" value="cancel">Cancel</button><button class="btn primary" id="preparePrintDocument" value="prepare">Prepare preview</button></div></form>`;
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
 status.textContent='Preparing the selected document and checking page breaks. Your encounter and writing are unchanged.';
 try{
  printModule=printModule||await import(new URL('./walkthrough-print.js?v=0f21a52b27',location.href));
  const prepared=await printModule.prepareWalkthrough(l,{edition});
  if(token!==printTask||location.hash!==route){printModule.clearWalkthroughPrint(prepared.root);return;}
  if(!await verifyCached(true)){printModule.clearWalkthroughPrint(prepared.root);return;}
  if(token!==printTask||location.hash!==route){printModule.clearWalkthroughPrint(prepared.root);return;}
  const openPreview=()=>{approvedPrint=true;printModule.showWalkthroughPreview({onClose:closePrintedLesson,onPrint:async()=>{
   if(!await verifyCached(true))return;
   if(token!==printTask||location.hash!==route)return;
   openPreview();printDialogOpen=true;window.print();
  }});};
  status.textContent=`${prepared.report.pages} sheets prepared: ${printModule.PRINT_EDITIONS[edition].label}.`;
  openPreview();
 }catch(e){if(token!==printTask||location.hash!==route)return;printModule?.clearWalkthroughPrint();approvedPrint=false;status.textContent='Print edition could not be prepared: '+e.message+' Your selected case and saved work are unchanged.';}
 finally{if(button.isConnected){button.disabled=false;button.innerHTML=oldButton;}}
}
setInterval(()=>{if((inLibrary()||printProtected)&&!document.hidden)verifyCached();},2000);
async function api(path,body){const r=await fetch(path,{cache:'no-store',method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});return r.json();}
function heading(kicker,title,sub){return `<div class="workbench-heading"><div><div class="eyebrow">${kicker}</div><h1>${title}</h1><p>${sub}</p></div>${window.pcmLastAttempt?'<a class="btn" href="#/'+esc(window.pcmLastAttempt)+'">Return to encounter</a>':''}</div>`;}
function sourceLine(source){
 if(typeof source==='string')return '<li>'+esc(source)+'</li>';
 const label=source.title||source.label||source.document||(source.path||'').split('/').pop()||'Source reference';
 const url=source.url||source.source_url;
 const title=url&&/^https:\/\//.test(url)?`<a href="${esc(url)}" target="_blank" rel="noopener">${esc(label)}</a>`:esc(label);
 return '<li>'+title+(source.locator?' — '+esc(source.locator):'')+(source.reviewed?' · reviewed '+esc(source.reviewed):'')+'</li>';
}
async function guard(){let r=await api('/api/teaching');if(r.requires_assistance){const yes=await window.pcmConfirmChoice(`Opening written solutions changes ${r.attempts.length} active independent or exam rehearsal attempt(s) to assisted practice. Your note, evidence and original deadlines remain intact; assistance is shown separately in results. Open these answer materials?`);if(!yes)return null;const access=await api('/api/teaching/access',{confirm:true,attempt_ids:r.attempts.map(a=>a.id)});if(access.error)throw Error(access.error);r=await api('/api/teaching');}if(r.error)throw Error(r.error);return r;}
async function render(route){const token=++request;const previous=window.pcmActiveAttempt?.();try{
 const kind=route.split('/')[0];const data=kind==='learn'?await guard():await api('/api/bootstrap');
 if(!data){location.hash=previous?'#/'+previous:'';return;}
 if(!await window.pcmEnterWorkbench(kind))return;
 if(token!==request)return;
 const view=$('#view');document.querySelectorAll('[data-destination]').forEach(b=>b.setAttribute('aria-current',b.dataset.destination===kind?'page':'false'));
 if(kind==='progress'){view.innerHTML='<div class="workbench">'+heading('Your practice','Keep the next step small.','Original submissions, assisted practice and retries remain separate.')+`<div class="progress-cards"><div><b>${(data.sessions||[]).filter(s=>s.phase==='submitted').length}</b><span>completed attempts</span></div><div><b>${data.cases?.length||24}</b><span>presentations to explore</span></div></div><section class="card"><h2>Attempts on this computer</h2>${(data.sessions||[]).map(s=>`<a class="attempt-row" href="#/${esc(s.id)}"><span><b>${esc(s.patient_name||s.case_title||s.case_id)}</b><small>${esc(s.phase)} · ${s.assisted?'assisted practice':s.learning_mode==='guided'?'guided learning':s.learning_mode==='coached'?'coached practice':s.learning_mode==='rehearsal'?'exam rehearsal':s.learning_mode==='independent'?'independent practice':'historical attempt'} · ${new Date(s.created_at).toLocaleDateString()}</small></span><span>${s.phase==='submitted'?'Review feedback →':'Resume →'}</span></a>`).join('')||'<p>Your first practice will appear here.</p>'}</section></div>`;return;}
 const cid=route.split('/')[1];if(cid){const params=new URLSearchParams(route.split('?')[1]||'');const clean=cid.split('?')[0];const result=await api('/api/teaching/'+encodeURIComponent(clean)+'?variant='+encodeURIComponent(params.get('variant')||'base'));
 if(result.error){if(result.requires_assistance){coverSolutions(result.error);return;}throw Error(result.error);}if(token!==request)return;coverSolutions();lesson(result.lesson,data);await verifyCached();return;}
 view.innerHTML='<div class="workbench">'+heading('Written teaching library','See the whole encounter.','Read one strong approach, connect every finding to its source, then practice with less help.')+`<div class="library-tools"><label>Find a presentation<input id="lessonSearch" type="search" placeholder="Headache, urinary symptoms, chest pain…"></label><label>System<select id="lessonSystem"><option value="">All systems</option>${[...new Set(data.cases.map(c=>c.system))].map(x=>'<option>'+esc(x)+'</option>').join('')}</select></label><span class="small">${data.cases.length} presentations · ${data.cases.reduce((n,c)=>n+c.walkthroughs.length,0)} case paths</span></div><div id="lessonGrid" class="lesson-grid"></div><details class="card"><summary>How these lessons were reviewed</summary><p>Every example runs through the authored patient and specific examination engine. Clinical content is source-linked and has automated consistency checks; it is not a faculty-approved answer key. Content review and direct browser coverage are documented separately. Estimates exclude deeper explanations and are not proof of real-world performance.</p><p>Course authority: 14-minute encounter, 9-minute note, SOAP rubric and SP refusal rules. Guided and Coached are untimed; Independent practice uses 30/5/20 minutes. These practice allowances are not course requirements.</p></details></div>`;
 const paint=()=>{const q=$('#lessonSearch').value.toLowerCase(),system=$('#lessonSystem').value;const rows=data.cases.filter(c=>(!system||c.system===system)&&`${c.title} ${c.blurb} ${c.system}`.toLowerCase().includes(q));$('#lessonGrid').innerHTML=rows.map(c=>`<a class="lesson-card" href="#learn/${esc(c.id)}"><span class="eyebrow">${esc(c.system)}</span><h2>${esc(c.title)}</h2><p>${esc(c.blurb)}</p><span class="lesson-foot">${c.walkthroughs.length} case paths · ${data.progress.some(p=>p.case_id===c.id)?'reflection saved':'read & recall'} <b>→</b></span></a>`).join('')||'<p>No matching presentations. Try a broader term.</p>';};$('#lessonSearch').oninput=paint;$('#lessonSystem').onchange=paint;paint();await verifyCached();
 }catch(e){$('#view').insertAdjacentHTML('afterbegin',`<div class="card" role="alert">The library could not load: ${esc(e.message)}. Your attempts remain saved. <button class="btn" id="studyRetry">Try again</button></div>`);$('#studyRetry').onclick=()=>render(route);}}
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
$('#view').innerHTML=`<div class="lesson-reader"><div class="reader-top"><a href="#cases">← Cases & print</a><button class="btn sm" id="printLesson">Print case documents</button><button class="btn primary sm" id="practiceLesson">Practice this case</button></div>${heading('One defensible approach',esc(l.title),esc(l.patient.name)+' · '+l.patient.age+' · '+esc(l.variant_label))}<div class="reader-meta"><label>Case path<select id="lessonVariant">${variants.map(v=>`<option value="${esc(v.id)}" ${v.id===l.variant_id?'selected':''}>${esc(v.label)}</option>`).join('')}</select></label><p><b>${Math.floor(l.estimated_encounter_s/60)}m ${l.estimated_encounter_s%60}s</b> estimated encounter · <b>${l.note_words} words</b> in the example note<br><small>14-minute encounter / 9-minute SOAP. Deeper explanations are outside the timed example.</small></p></div><nav class="reader-toc" aria-label="Walkthrough sections">${phaseLinks.map(k=>`<button class="btn ghost sm" data-section="${k}">${({doorway:'1 Prepare',encounter:'2 Encounter',reasoning:'3 Reason',soap:'4 Document',recall:'5 Recall'})[k]}</button>`).join('')}</nav>
<section id="lesson-doorway"><h2>1. At the doorway</h2><div class="doorway-written">${l.doorway.doorway.map(t=>'<p>'+esc(t)+'</p>').join('')}<dl class="written-vitals">${Object.entries(l.doorway.vitals).map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>${(l.doorway.supplied_results||[]).map(x=>'<p>Supplied '+esc(x.label)+': '+esc(x.value)+'</p>').join('')}</div><p class="learning-anchor">${esc(l.plan.anchor)}</p><p>${esc(l.plan.notice)}</p><p>${esc(l.plan.pivot)}</p>${l.variant_id!=='base'?`<aside class="variant-note"><h3>What changes in this variation</h3><p>${esc(l.variant_guidance)}</p>${l.differences.map(d=>`<p><b>${esc(d.topic.replaceAll('_',' '))}:</b> ${esc(d.current)}<br><small>Core case: ${esc(d.base)}</small></p>`).join('')}</aside>`:''}</section>
<section id="lesson-encounter"><h2>2. An example encounter</h2><p>Read the dialogue and actions in order. This is one defensible approach, with room to adapt to the patient. Expand teaching notes after the first read.</p>${l.plan.urgent?'<div class="clinical-priority">Urgent care takes priority. The example states escalation early; continue nonurgent questions or examinations only if care permits. A real patient should not wait for checklist completion.</div>':''}<details><summary>Timing and simulation assumptions</summary><p>${esc(l.estimate_method)}</p><p>The note requires approximately ${Math.ceil(l.note_words/9)} words per minute over nine minutes; allow additional time for thinking and editing. This is a reference, not a typing target. Virtual actions do not verify touch, force, auscultatory discrimination or full physical technique.</p></details><div class="example-transcript">${l.timeline.map((t,i)=>`<article class="example-turn ${t.kind}" id="turn-${i}"><div class="turn-phase">${esc(t.section)}</div>${t.kind==='dialogue'?`<p><b>Student</b> ${esc(t.student)}</p>${t.patient?`<p><b>Patient</b> ${esc(t.patient)}</p>`:''}`:`<p><b>Action</b> ${esc(t.action)}</p>${t.finding?`<p class="obtained-finding"><b>Finding obtained</b> ${esc(t.finding)}</p>`:''}`}${t.why?`<details><summary>Why this step matters</summary><p>${esc(t.why)}</p></details>`:''}</article>`).join('')}</div></section>
<section id="lesson-reasoning"><h2>3. Connect the findings to a decision</h2><p>${esc(l.plan.exam)}</p>${l.reasoning.map(r=>`<div class="reasoning-card"><h3>${esc(r.question)}</h3><p>${esc(r.why)}</p><p><b>If present:</b> ${esc(r.if_present)}</p><p><b>If absent:</b> ${esc(r.if_absent)}</p><p><b>Next action:</b> ${esc(r.next_action)}</p></div>`).join('')}<p>Assessment contains clinical inferences. Neither a differential nor its mnemonic category proves the diagnosis. Consider urgent alternatives even when they are less likely.</p><details><summary>Memory tools, expanded and used in context</summary><p><b>FIFE:</b> the syllabus groups Feelings/Fears; Insight/Ideas; Function/Effects; Expectations. At the patient-perspective turn, ask what worries the patient and how symptoms affect daily life. Use what they actually report; an unanswered topic remains unknown.</p><p><b>VINDICATE:</b> a common expansion is Vascular, Infectious, Neoplastic, Degenerative/Deficiency, Iatrogenic/Intoxication, Congenital, Autoimmune, Traumatic, Endocrine/Metabolic. The course requires three different categories; the supplied files do not settle every expansion or diagnosis placement. Organize reasonable alternatives, not implausible diagnoses chosen just to fill letters.</p><p><b>MOTHERR:</b> Medications, Osteopathic treatment, Testing, Humanistic / supportive needs, Education, Referral, Return/follow-up. Consider function, support, and the ability to carry out the plan. The course requires at least three different elements per paired plan. This is a working expansion; see Scoring for its source status. For this case, connect the actual first plan's proposed tests, explanation and disposition; do not add unnecessary treatment to collect letters.</p><p><b>When blank:</b> pause → name your phase → recall its purpose → choose one relevant question or action. This recovery cue is supplementary teaching, not a scored course mnemonic.</p></details><h3>Common traps</h3><p>${esc(l.plan.avoid)}</p><ul>${l.omissions.map(x=>'<li>'+esc(x)+'</li>').join('')}</ul></section>
<section id="lesson-soap"><h2>4. A concise example SOAP note</h2><p>Subjective reports what the patient said; Objective records supplied information and completed examination findings. Assessment is inference; Plan describes proposed future care. Do not copy this note into an attempt where you did not obtain its evidence.</p>${clinicalExample(l)}<h3>Where the note came from</h3>${l.note_links.map(link=>`<details class="source-link"><summary><span>${esc(link.section)}</span> ${esc(link.statement)}</summary><p><b>${esc(link.classification)}</b> · ${esc(link.trace_method)}</p>${link.event_ids.map(id=>events.get(id)).filter(Boolean).map(e=>`<blockquote><small>Event ${e.seq} · ${esc(e.kind.replaceAll('_',' '))}</small><br>${esc(e.text)}</blockquote>`).join('')}</details>`).join('')}<p>Plans are proposals. No future ultrasound, CT, culture or treatment response is added to Objective merely because it is mentioned in Plan.</p></section>
<section id="lesson-recall"><h2>5. Close the page in your mind</h2><p>Try each prompt before revealing the explanation. Your reflection is saved separately from examination scores.</p>${l.recall.map((r,i)=>`<div class="recall-card"><label for="recall-${i}">${i+1}. ${esc(r.prompt)}</label><textarea id="recall-${i}" maxlength="2000" rows="3" placeholder="Recall first, then check…">${esc((localDraft||JSON.parse(index.progress.find(p=>p.case_id===l.case_id&&p.variant_id===l.variant_id)?.recall_json||'[]'))[i]||'')}</textarea><details><summary>Reveal explanation</summary><p>${esc(r.answer)}</p></details></div>`).join('')}<button class="btn primary" id="saveRecall">Save reflection</button><span id="recallStatus" role="status"></span></section>
<footer class="lesson-sources"><h2>Sources and review status</h2><p>${esc(l.review_status)}</p><ul>${l.course_sources.map(s=>`<li>${esc(s.label)} — ${esc(s.locator)}</li>`).join('')}${l.sources.map(sourceLine).join('')}</ul></footer></div>`;
$('#lessonVariant').onchange=e=>location.hash='#learn/'+l.case_id+'?variant='+encodeURIComponent(e.target.value);
document.querySelectorAll('[data-section]').forEach(b=>b.onclick=async()=>{if(!await verifyCached(true))return;$('#lesson-'+b.dataset.section).scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});} );
$('#printLesson').onclick=()=>choosePrintDocument(l);$('#practiceLesson').onclick=async()=>{const r=await api('/api/session',{case_id:l.case_id,variant_id:l.variant_id,learning_mode:'coached',from_walkthrough:true});if(r.error){alert(r.error);return;}location.hash='#/'+r.id;};
l.recall.forEach((_,i)=>$('#recall-'+i).oninput=()=>{try{localStorage.setItem(draftKey,JSON.stringify(l.recall.map((_,j)=>$('#recall-'+j).value)));$('#recallStatus').textContent='Draft kept in this browser. Save reflection to add it to your learning history.';}catch{$('#recallStatus').textContent='Browser draft storage unavailable. Use Save reflection before leaving.';}});
$('#saveRecall').onclick=async()=>{try{const r=await api('/api/teaching/progress',{case_id:l.case_id,variant_id:l.variant_id,answers:l.recall.map((_,i)=>$('#recall-'+i).value)});$('#recallStatus').textContent=r.error||r.message;if(r.saved){try{localStorage.removeItem(draftKey);}catch{}}}catch(e){$('#recallStatus').textContent='Could not save. Keep this page open and try again.';}};
}
async function renderMaterials(route){
 const token=++request,routeHash=location.hash,current=()=>token===request&&location.hash===routeHash,view=$('#view');printProtected=false;view.classList.remove('solution-locked');$('#solutionStatus')?.remove();
 view.innerHTML='<div class="workbench"><p role="status">Opening practice documents…</p></div>';
 try{
  const data=await api('/api/printables');if(data.error)throw Error(data.error);if(!current())return;
  document.querySelectorAll('[data-destination]').forEach(b=>b.setAttribute('aria-current',b.dataset.destination==='cases'?'page':'false'));
  const params=new URLSearchParams(route.split('?')[1]||''),cid=(route.split('/')[1]||'').split('?')[0],variant=params.get('variant')||'base';
  if(!cid){
   view.innerHTML=`<div class="workbench materials-library">${heading('Cases & print','Practice together. Study independently.','Choose a presentation, then print only the materials you need.')}<p class="material-intro"><b>Partner practice:</b> student copy for you; patient script and findings for your partner. <b>Individual study:</b> write first, then open the example note.</p><div class="library-tools"><label>Find a case<input id="materialSearch" type="search" placeholder="Cough, knee, rash…"></label><label>System<select id="materialSystem"><option value="">All systems</option>${[...new Set(data.cases.map(c=>c.system))].map(x=>'<option>'+esc(x)+'</option>').join('')}</select></label><span class="small">${data.cases.length} presentations</span></div><div id="materialGrid" class="lesson-grid"></div></div>`;
   const paint=()=>{const q=$('#materialSearch').value.toLowerCase(),system=$('#materialSystem').value;$('#materialGrid').innerHTML=data.cases.filter(c=>(!system||c.system===system)&&`${c.title} ${c.system}`.toLowerCase().includes(q)).map(c=>`<a class="lesson-card" href="#cases/${esc(c.id)}"><span class="eyebrow">${esc(c.system)}</span><h2>${esc(c.title)}</h2><span class="lesson-foot">${c.variants.length} case path${c.variants.length===1?'':'s'} <b>Choose materials →</b></span></a>`).join('')||'<p>No matching cases. Try another term.</p>';};$('#materialSearch').oninput=paint;$('#materialSystem').onchange=paint;paint();return;
  }
  const c=data.cases.find(c=>c.id===cid);if(!c)throw Error('This case could not be found.');
  const result=await api('/api/printables/'+encodeURIComponent(cid)+'?variant='+encodeURIComponent(variant));if(result.error)throw Error(result.error);if(!current())return;
  const l=result.material,m=await import(new URL('./partner-print.js?v=9639edf495',location.href));if(!current())return;
  const option=id=>`<button type="button" class="material-option" id="material-${id}" data-material="${id}"><b>${esc(m.PRINT_EDITIONS[id].label)}</b><span>${esc(m.PRINT_EDITIONS[id].description)}</span><small>Preview & print →</small></button>`;
  view.innerHTML=`<div class="workbench materials-case"><div class="reader-top"><a href="#cases">← All cases</a><button class="btn" id="materialPractice">Start coached practice</button></div>${heading('Practice documents',esc(c.title),esc(l.patient.name)+' · '+esc(l.patient.age)+' · '+esc(l.patient.sex))}${c.variants.length>1?`<label class="material-variant">Case path<select id="materialVariant">${c.variants.map(v=>`<option value="${esc(v.id)}" ${v.id===variant?'selected':''}>${esc(v.label)}</option>`).join('')}</select></label>`:''}<p>Choose a document to preview or print.</p><section aria-labelledby="studentMaterialsTitle"><h2 id="studentMaterialsTitle">Student materials <span class="material-note">No answers</span></h2><div class="material-options">${['student','doorway','blank'].map(option).join('')}</div></section><section aria-labelledby="answerMaterialsTitle"><h2 id="answerMaterialsTitle">Patient & reference materials <span class="material-note">Contains answers</span></h2><div class="material-options">${['patient','examiner','soap','study'].map(option).join('')}</div><p class="small muted">During a scored attempt, opening these materials requires an explicit change to assisted practice. Your deadline and saved work stay intact.</p></section><p id="printLessonStatus" role="status"></p><details class="material-details"><summary>Demonstration and sources</summary><p><a href="#learn/${esc(cid)}?variant=${esc(variant)}">Read the demonstrated encounter and source references →</a></p></details></div>`;
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
  $('#materialPractice').onclick=async()=>{const r=await api('/api/session',{case_id:cid,variant_id:variant,learning_mode:'coached'});if(r.error){$('#printLessonStatus').textContent=r.error;return;}location.hash='#/'+r.id;};
 }catch(e){if(!current())return;view.innerHTML=`<div class="workbench"><h1>Case documents could not load</h1><p role="alert">${esc(e.message)}</p><button class="btn" id="materialRetry">Try again</button> <a class="btn" href="#cases">All cases</a></div>`;$('#materialRetry')?.addEventListener('click',()=>renderMaterials(route));}
}

window.pcmStudy={render,renderMaterials,beginProtectedAttempt:()=>notifyAccess(true),endProtectedAttempt:()=>notifyAccess(false)};})();
