/* Print-only organization. Clinical replies and note values come from the guarded teaching payload. */
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const p=(x,cls='')=>x?`<p class="${cls}">${esc(cls==='rp-actor'?String(x).replace(/^Actor (?:instruction|note):\s*/i,''):x).replaceAll('\n','<br>')}</p>`:'';
const block=(html,cls='',id='')=>`<section class="pw-block ${cls}"${id?` data-anchor="${esc(id)}"`:''}>${html}</section>`;
const heading=(title,text='',id='')=>block(`<h2>${esc(title)}</h2>${p(text)}`,'pw-heading',id);
const ref=(id,label)=>`<a class="rp-ref" href="#rp-${esc(id)}" data-page-ref="${esc(id)}">${esc(label)} <span class="rp-page-ref">p. —</span></a>`;
const actorText=x=>String(x||'').replace(/^Actor instruction:\s*/i,'');
const sentenceList=rows=>(rows||[]).map(x=>p(actorText(typeof x==='string'?x:x.text),'rp-actor')).join('');
export const PRINT_EDITIONS={patient:{label:'Patient role-play script',paper:'landscape',description:'Give this to the partner playing the patient. History answers only; no SOAP solution.'},examiner:{label:'Simulated examination findings',paper:'landscape',description:'Keep findings separate. Release a result only after the matching action is performed or verbalized.'},soap:{label:'Example SOAP answer key',paper:'portrait',description:'Review after practice. Includes the demonstrated-encounter scope and any authoring limitations.'},study:{label:'Complete study packet',paper:'mixed',description:'Patient script, findings, demonstration, teaching, evidence, and the example SOAP note at the end.'}};
function section(title,blocks,{startPage=false,paper='landscape',kind='partner'}={}){return {title,kind,startPage,paper,blocks};}
function cover(l,label,sub){return block(`<div class="pw-kicker">Chat CSE · ${esc(label)}</div><h1>${esc(l.patient.name)}</h1><p class="rp-case">${esc(l.title)} · ${esc(l.patient.age)} years · ${esc(l.patient.sex)} · ${esc(l.variant_label)}</p>${p(sub)}`,'rp-cover');}
function qa(question,answer,{actor=false}={}){return `<div class="rp-qa">${p(question,'rp-question')}${answer?p(answer,actor?'rp-actor':'rp-answer'):''}</div>`;}
export function patientSections(l){
 const r=l.partner_script;if(!r?.sections)throw Error('The patient script is unavailable. Reload this lesson and try again.');
 const b=r.briefing,nav=r.sections.map(s=>`<li><b>${esc(s.letter)}</b> ${ref(s.id,s.title)}</li>`).join('');
 const brief=[cover(l,'Patient copy','For the partner playing the patient. Follow the question’s meaning; the interview may happen in any order.'),block(`<h2>Your role</h2>${p(b.background)}${sentenceList(b.acting_directions?.map(text=>text.startsWith(b.background)?text.slice(b.background.length).replace(/^[.; ]+/,''):text).filter(Boolean))}`,'rp-briefing'),block(`<h2>Opening statement</h2>${p(b.opening,'rp-answer')}${p(b.volunteer_rule,'rp-actor')}`,'rp-opening','opening'),block(`<h2>Find an answer</h2><p>Start with the opening. For symptom details, go directly to ${ref('history','History of present illness')}.</p><ol class="rp-index">${nav}</ol><p class="rp-small">SMASH FMR follows the requested history organization. <b>H</b> is the current illness; the second <b>M</b> is past medical conditions.</p>`,'rp-navigation'),block(`<h3>How to respond</h3><p><b>Ask</b> gives common wording. <b>Say</b> is the patient’s response. <b>Actor note</b> is guidance for you, not dialogue.</p><p>For a broad question, use the short opening answer for that section. Give the focused details only when the question asks for them. If two topics are asked together, answer both relevant topics.</p>${p(actorText(b.unknown_rule),'rp-actor')}<p>Keep this patient copy separate from the simulated findings and SOAP key. Do not diagnose the patient or invent test results.</p>`,'rp-how')];
 const result=[section('Patient briefing',brief)];
 for(const s of r.sections){
  const blocks=[heading(`${s.letter} · ${s.title}`,s.id==='history'?'The current illness: onset, location, duration, character, triggers, relief, timing and severity.':'',s.id)];
  if(s.id==='history')blocks.push(block(`<p>Associated symptoms and relevant negatives: ${ref('ros','Review of systems')}.</p>`,'rp-crossref'));
  if(s.id==='ros')blocks.push(block(`<p>For the main symptom’s chronology and triggers: ${ref('history','History of present illness')}.</p>`,'rp-crossref'));
  let previousSystem=null;
  if(s.entry&&(s.topics.length!==1||s.topics[0].followups?.length||s.entry.answer!==s.topics[0].answer))blocks.push(block(`<h3>When asked broadly</h3>${qa(s.entry.question,s.entry.answer)}${p(s.entry.actor_note,'rp-actor')}`,'rp-broad'));
  for(const t of s.topics){
   if(s.id==='ros'&&t.system_label&&t.system_label!==previousSystem){blocks.push(heading(t.system_label));previousSystem=t.system_label;}
   const ask=t.questions?.[0]||t.title,alts=(t.questions||[]).slice(1);
   const body=`<h3>${esc(t.title)}</h3><div class="rp-qa">${p(ask,'rp-question')}${alts.length?p('Also means: '+alts.join(' / '),'rp-alias'):''}${p(t.answer,'rp-answer')}${p(t.actor_note,'rp-actor')}</div>`+(t.followups||[]).map(f=>`<div class="rp-followup"><h4>Focused follow-up</h4>${qa(f.question,f.answer)}${p(f.actor_note,'rp-actor')}</div>`).join('')+(t.crossrefs?.length?`<p class="rp-crossref">See also ${t.crossrefs.map(x=>ref(x.topic_id||x.section_id,x.label)).join(' · ')}</p>`:'');
   blocks.push(block(body,'rp-topic',t.id));
  }
  result.push(section('Patient history lookup',blocks));
 }
 if(r.actor_notes?.length)result.push(section('Actor instructions', [heading('Actor instructions and case limits'),...r.actor_notes.map(n=>block(`<h3>${esc(n.title)}</h3>${p(n.text,'rp-actor')}`,'rp-actor-detail'))]));
 return result;
}
export function examinerSections(l){
 const prep=[cover(l,'Examiner / partner copy','Simulated findings are separate from patient dialogue. This page does not establish what happened in your own practice attempt.'),block(`<h2>Release findings only after the action</h2><p>After the student explains and performs or clearly verbalizes the named examination with permission, read its result exactly. Do not release a whole system of findings for an unspecified examination.</p><p>These are supplied simulation findings, not observations about your real partner. Practice safely and respect consent; do not try to reproduce pain or abnormal signs.</p><p><b>Course SP refusals:</b> breast, genital, gynecological, rectal and corneal-reflex examinations are verbalized, then refused. Say, “I do not want that examination.” Document the refusal only; do not release an unperformed normal result.</p><p>Use your current station instructions for timing. Course files differ; this print edition does not change application timers.</p>`,'rp-release'),heading('Supplied before examination'),block((l.doorway.doorway||[]).map(x=>p(x)).join('')+`<dl class="pw-vitals">${Object.entries(l.doorway.vitals||{}).map(([k,v])=>`<div><dt>${esc(({T:'Temperature',P:'Pulse',BP:'Blood pressure',R:'Respirations','Pulse Ox':'Oxygen saturation',Ht:'Height',Wt:'Weight'})[k]||k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`+(l.doorway.supplied_results||[]).map(x=>p(`${x.label}: ${x.value}`)).join(''))];
 const findings=[];
 for(const [i,t] of l.timeline.entries())if(t.kind==='action'){
  findings.push(block(`<h3>${esc(t.section)}</h3>${p(t.action,'rp-exam-action')}${t.finding?p(t.finding,t.maneuver_id?'rp-finding':'rp-actor'):p('No clinical result is supplied for this preparation step.','rp-actor')}<p class="rp-small">Demonstration step ${i+1}${t.maneuver_id?' · release only for this action':''}</p>`,'rp-exam-topic',`exam-${i}`));
 }
 return [section('Examiner instructions',prep,{startPage:true}),section('Simulated examination findings',[heading('Action → supplied finding','Do not read these findings as patient dialogue.'),...findings])];
}
export function soapSections(l){
 const n=l.partner_note;if(!n?.subjective)throw Error('The example SOAP note is unavailable. Reload this lesson and try again.');
 const outside=[cover(l,'SOAP answer key',n.label||'Example for the complete demonstrated encounter'),block(`<h2>Which encounter does this note describe?</h2>${p(`${n.encounter_definition.history_turns} demonstrated history exchanges, ${n.encounter_definition.examination_results} documented examination results, and the supplied station information. ${n.encounter_definition.evidence_rule}`)}<p>Your own submitted note must contain only information you actually obtained: supplied information, answers you elicited, and examinations you completed. This answer key creates no evidence in your attempt.</p><p>The complete study packet contains the numbered dialogue, examination actions and evidence references. Keep this key out of view during a partner rehearsal and write your own note before comparing.</p>`,'rp-key-context')];
 const reached=new Set(l.timeline.flatMap(t=>t.fact_ids||[]));
 for(const s of l.partner_script?.sections||[]){const labels=s.topics.filter(t=>(t.source_fact_ids||[]).some(id=>reached.has(id))).map(t=>t.title);if(labels.length)outside.push(block(`<h3>${esc(s.title)}</h3>${p(labels.join(' · '))}`,'rp-obtained'));}
 const actions=l.timeline.filter(t=>t.maneuver_id).map(t=>t.action);outside.push(block(`<h3>Examinations demonstrated</h3>${p(actions.join('\n'))}`,'rp-obtained'));
 for(const note of (n.outside_note||[]).filter(note=>note.kind!=='scope'))outside.push(block(`<h3>${esc(note.kind==='authoring_gap'?'Case authoring required':note.kind==='correction'?'Evidence correction':note.kind==='source_conflict'?'Source wording conflict':note.kind==='plan'?'How to read the plan':'Documentation guidance')}</h3>${p(note.text)}`,'rp-key-limit'));
 outside.push(block(`<h3>Course format</h3><p>HPI is a paragraph; other histories have named headings. Assessment is ranked and plans are numbered to match. Proposed or conditional care remains in Plan, never Objective.</p><p>The course expects three supported differentials from distinct categories and a corresponding plan for each. A gap in case support is flagged here instead of being filled with an invented diagnosis or finding.</p><p class="rp-small">Sources: PCM student manual, SOAP rubric and note template, pp. 5–6; updated CSE #1 announcement, pp. 2–3. The supplied acronym sheet does not expand SMASH FMR. Follow current course instructions for timing and permitted references.</p>`,'rp-key-context'));
 const notes=[block(`<div class="rp-note-heading"><h1>SOAP note</h1><p>${esc(l.patient.name)} · ${esc(l.patient.age)}-year-old ${esc(l.patient.sex)} · ${esc(l.variant_label)}</p></div>`,'rp-clinical-title')];
 for(const [title,rows] of [['Subjective',n.subjective],['Objective',n.objective]]){notes.push(heading(title));for(const row of rows)notes.push(block(`<h3>${esc(row.heading)}</h3>${(row.paragraphs||row.text.split('\n\n')).map(text=>p(text)).join('')}`,'rp-note-section'));}
 notes.push(heading('Assessment'));
 for(const a of n.assessment)notes.push(block(`<h3>${a.rank}. ${esc(a.text)}</h3>${p(a.reasoning||a.support||'')}`,'rp-note-assessment'));
 notes.push(heading('Plan'));
 for(const plan of n.plan)notes.push(block(`<h3>${plan.rank}. ${esc(plan.diagnosis)}</h3>${plan.condition?p(plan.condition,'rp-condition'):''}${p(plan.text)}`,'rp-note-plan'));
 return [section('Example encounter and evidence limits',outside,{startPage:true,paper:'portrait',kind:'key-context'}),section('Example SOAP note',notes,{startPage:true,paper:'portrait',kind:'clinical-note'})];
}
export function buildPartnerSections(l,edition='patient',studySections=[]){
 if(!PRINT_EDITIONS[edition])throw Error('Choose a printable document.');
 if(edition==='patient')return patientSections(l);
 if(edition==='examiner')return examinerSections(l);
 if(edition==='soap')return soapSections(l);
 const retained=studySections.filter(s=>!['Doorway preparation','Example SOAP note','Documentation evidence'].includes(s.title));
 const evidence=noteEvidenceSections(l);
 if(l.case_id==='renal-flank-pain'){const storyboard=retained.find(s=>s.title==='Encounter storyboard');if(storyboard)storyboard.blocks=[...storyboard.blocks.slice(0,1),block('<h3>Source wording conflict in this demonstration</h3><p>The recorded dialogue uses both husband and boyfriend. The historical transcript is reproduced as recorded. For role-play, use the neutral wording in the patient script; no explanation for that conflict is supplied.</p>','rp-key-limit'),...storyboard.blocks.slice(1)];}
 const recallIndex=retained.findIndex(s=>s.title==='Recall exercise');
 retained.splice(recallIndex<0?retained.length:recallIndex,0,...evidence);
 return [...patientSections(l),...examinerSections(l),...retained.map(s=>({...s,startPage:s.startPage||s.title==='Encounter storyboard'})),...soapSections(l)];
}

function noteEvidenceSections(l){
 const n=l.partner_note,blocks=[heading('Sources for the revised example note','These references identify demonstrated history topics and exact examination results for review. A linked topic is not automatic proof of every paraphrase. Assessment is inference; Plan is proposed care.')];
 const events=new Map(l.ledger.map(e=>[e.seq,e]));
 for(const [label,rows] of [['Subjective',n.subjective],['Objective',n.objective]])for(const row of rows){
  const steps=[...new Set(l.timeline.flatMap((t,i)=>t.event_ids?.some(id=>row.event_ids.includes(id))?[i+1]:[]))];
  blocks.push(block(`<h3>${esc(label)} · ${esc(row.heading)}</h3>${p(row.text)}${p((steps.length?'Demonstration steps '+steps.join(', ')+'. ':'')+'Record IDs: '+row.event_ids.join(', '),'rp-small')}`,'pw-evidence-line'));
 }
 const ids=[...new Set([...n.subjective,...n.objective].flatMap(row=>row.event_ids))];
 const extra=ids.filter(id=>!l.timeline.some(t=>t.event_ids?.includes(id)));
 for(const id of extra){const e=events.get(id);if(e)blocks.push(block(`<h3>Additional supplied record ${esc(id)}</h3>${p(e.text)}`));}
 for(const c of n.corrections)blocks.push(block(`<h3>Correction to the earlier teaching note</h3>${p(c.reason)}${p('Use: '+c.replacement)}`,'rp-key-limit'));
 return [section('Revised note evidence',blocks,{kind:'reading'})];
}
