/* One source for printable case sections. No answers are inferred by the renderer. */
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const p=(x,cls='')=>x?`<p class="${cls}">${esc(x).replaceAll('\n','<br>')}</p>`:'';
const block=(html,cls='',id='')=>`<section class="pw-block ${cls}"${id?` data-anchor="${esc(id)}"`:''}>${html}</section>`;
const heading=(title,id='')=>block(`<h2>${esc(title)}</h2>`,'pw-heading',id);
const section=(title,blocks,{paper='landscape',kind='reading',startPage=true}={})=>({title,blocks,paper,kind,startPage});
const cover=(l,label,showAge=true)=>block(`<div class="pw-kicker">${esc(label)}</div><h1>${esc(l.patient.name)}</h1><p class="rp-case">${showAge && l.patient.age != null ? `${esc(l.patient.age)} years · ` : ''}${esc(l.patient.sex)} · ${esc(l.variant_label)}</p>`,'rp-cover');
const ref=(id,label)=>`<a class="rp-ref" href="#rp-${esc(id)}" data-page-ref="${esc(id)}">${esc(label)} <span class="rp-page-ref">p. —</span></a>`;
export const PRINT_EDITIONS={
 doorway:{label:'Doorway information',paper:'portrait',protected:false,description:'Before the encounter. Supplied information only.'},
 patient:{label:'Patient script',paper:'landscape',protected:true,description:'For your partner. History answers; no examination findings or SOAP key.'},
 examiner:{label:'Examinations and findings',paper:'landscape',protected:true,description:'For the examiner. Findings released after the matching examination.'},
 blank:{label:'Blank SOAP workspace',paper:'portrait',protected:false,description:'Two writing pages. No answers.'},
 soap:{label:'Example SOAP note',paper:'portrait',protected:true,description:'Answer key for the complete demonstrated encounter.'},
 student:{label:'Student copy',paper:'portrait',protected:false,description:'Doorway information and blank SOAP pages. No answers.'},
 study:{label:'Complete practice packet',paper:'mixed',protected:true,description:'All five sections, each starting on a new page. Includes the answer key.'}
};
const vitalLabels={T:'Temperature',P:'Pulse',BP:'Blood pressure',R:'Respirations','Pulse Ox':'Oxygen saturation',Ht:'Height',Wt:'Weight'};
export function doorwaySections(l){return [section('Doorway information',[
 cover(l,'Doorway information',false),block((l.doorway.doorway||[]).map(x=>p(x)).join(''),'rp-doorway'),
 heading('Supplied vital signs'),block(`<dl class="pw-vitals">${Object.entries(l.doorway.vitals||{}).map(([k,v])=>`<div><dt>${esc(vitalLabels[k]||k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`),
 ...(l.doorway.supplied_results?.length?[heading('Supplied results'),...l.doorway.supplied_results.map(x=>block(`<b>${esc(x.label)}</b>${p(x.value)}`))]:[])
],{paper:'portrait',kind:'doorway'})];}
export function patientSections(l){
 const r=l.partner_script;if(!r?.sections)throw Error('The patient script is unavailable. Reload this case and try again.');
 const byId=new Map(r.sections.map(s=>[s.id,s]));
 const sections=['history','surgical','medications','allergies','social','family','medical','ros'].map(id=>byId.get(id)).filter(Boolean);
 const b=r.briefing;
 const blocks=[cover(l,'Patient script'),block('<p class="rp-instruction">Give the opening complaint first; share the remaining details when asked. Answer the parts asked about. If a detail is absent, tell your partner outside the patient role that it is not provided.</p>'),block(`<h2>Opening complaint</h2>${p(b.opening,'rp-answer')}`,'rp-opening','opening')];
 const styles={concise:'Give brief, direct answers.',reserved:'Respond quietly and allow time for questions.',talkative:'Answer warmly; stay with the topic being asked.'};
 const demeanor=styles[b.communication_style];
 if(demeanor)blocks.push(block(p(demeanor,'rp-instruction')));
 blocks.push(block(`<nav class="rp-index">${sections.map(s=>ref(s.id,s.title)).join(' · ')}</nav>`,'rp-navigation'));
 for(const s of sections){
  blocks.push(heading(s.title,s.id));let system=null;
  for(const t of s.topics){
   if(s.id==='ros'&&t.system_label&&t.system_label!==system){system=t.system_label;blocks.push(block(`<h3>${esc(system)}</h3>`,'pw-heading rp-system'));}
   const answers=[...new Set([t.answer,...(t.followups||[]).map(f=>f.answer)].filter(Boolean))];
   const missing=!answers.length?'<span class="rp-instruction">Not provided in this case.</span>':'';
   blocks.push(block(`<b class="rp-topic-label">${esc(t.title)}</b> ${answers.map(x=>p(x,'rp-answer')).join('')}${missing}${t.crossrefs?.length?`<p class="rp-crossref">See ${t.crossrefs.map(x=>ref(x.topic_id||x.section_id,x.label)).join(' · ')}.</p>`:''}`,'rp-topic',t.id));
  }
 }
 const limits=(r.actor_notes||[]).filter(n=>n.source_fact_ids?.length||/conflict|refus|position/i.test(n.title+' '+n.text));
 if(limits.length){blocks.push(heading('Actor notes'));for(const n of limits)blocks.push(block(`<b>${esc(n.title)}</b>${p(n.text,'rp-instruction')}`,'rp-actor-detail'));}
 return [section('Patient script',blocks,{kind:'patient'})];
}
const systemFor=id=>/^(heart|jvd|carotid|peripheral)/.test(id)?'Cardiovascular':/^(lung|chest)/.test(id)?'Respiratory':/^abd/.test(id)?'Abdomen':/^(heent|lymph|thyroid|neck)/.test(id)?'HEENT & neck':/^(msk|gait)/.test(id)?'Musculoskeletal':/^(neuro|mental)/.test(id)?'Neurological':/^skin/.test(id)?'Skin':/^osteo/.test(id)?'Osteopathic':/^extrem/.test(id)?'Extremities':'General';
const systemOrder=['General','Cardiovascular','Respiratory','Abdomen','HEENT & neck','Musculoskeletal','Neurological','Skin','Extremities','Osteopathic'];
export function examinerSections(l){
 const rows=l.partner_examinations||l.timeline.filter(t=>t.maneuver_id).map(t=>({...t,system:systemFor(t.maneuver_id)}));
 const blocks=[cover(l,'Examinations and findings'),block('<p class="rp-instruction">Release each finding after the student performs or explicitly simulates that examination with permission. These are supplied simulation results, not observations about your real partner. Declined or deferred examinations have no normal finding.</p>')];
 for(const extra of [false,true]){
  const list=rows.filter(t=>Boolean(t.condition)===extra);if(!list.length)continue;
  if(extra)blocks.push(heading('Conditional additions'));
  for(const system of [...new Set([...systemOrder,...list.map(t=>t.system)])]){
   const matches=list.filter(t=>(t.system||systemFor(t.maneuver_id))===system);if(!matches.length)continue;
   blocks.push(heading(system));
   blocks.push(block('<div class="rp-exam-columns rp-exam-head"><b>Examination</b><b>Finding</b></div>','pw-heading rp-table-head'));
   for(const t of matches)blocks.push(block(`<div class="rp-exam-columns"><div><b>${esc(t.action)}</b>${t.condition?p(t.condition,'rp-instruction'):''}</div><div>${p(t.finding||'No finding obtained.','rp-finding')}</div></div>`,'rp-exam-topic',`exam-${t.maneuver_id}`));
  }
 }
 const refusals=l.timeline.filter(t=>t.kind==='action'&&!t.maneuver_id&&t.finding&&/refus|declin|defer|not perform/i.test(t.finding));
 if(refusals.length){blocks.push(heading('Declined or deferred'));for(const t of refusals)blocks.push(block(`<b>${esc(t.action)}</b>${p(t.finding,'rp-instruction')}`));}
 return [section('Examinations and findings',blocks,{kind:'examiner'})];
}
export function blankSections(l){
 const field=(title,size)=>block(`<h2>${esc(title)}</h2><div class="rp-writing" style="height:${size}in" aria-label="Writing space for ${esc(title)}">${'<span class="rp-rule" aria-hidden="true"></span>'.repeat(Math.floor(size/.28))}</div>`,'rp-writing-block');
 return [section('Blank SOAP workspace',[cover(l,'Your SOAP note'),block('<p>Name: __________________________ &nbsp; Date: ______________</p>'),field('Subjective',4.1),field('Objective',2.6)],{paper:'portrait',kind:'blank'}),
 section('Blank SOAP workspace',[block('<p class="rp-instruction">Continue your note.</p>'),field('Assessment',2.6),field('Plan',5.2)],{paper:'portrait',kind:'blank'})];
}
export function soapSections(l){
 const n=l.partner_note;if(!n?.subjective)throw Error('The example note is unavailable. Reload this case and try again.');
 const blocks=[cover(l,'Example SOAP note'),block('<p class="rp-instruction">Example for the complete demonstrated encounter. Your note must reflect only what you actually asked, were supplied, and examined.</p>')];
 // Source gaps stay outside the clinical note. Do not reprint the old teaching preface.
 for(const x of n.outside_note||[])if(['authoring_gap','source_conflict'].includes(x.kind))blocks.push(block(p(x.text,'rp-instruction'),'rp-key-limit'));
 for(const [title,rows] of [['Subjective',n.subjective],['Objective',n.objective]]){blocks.push(heading(title));for(const row of rows)blocks.push(block(`<h3>${esc(row.heading)}</h3>${(row.paragraphs||row.text.split('\n\n')).map(x=>p(x)).join('')}`,'rp-note-section'));}
 blocks.push(heading('Assessment'));for(const a of n.assessment)blocks.push(block(`<h3>${a.rank}. ${esc(a.text)}</h3>${p(a.reasoning||a.support||'')}`,'rp-note-assessment'));
 blocks.push(heading('Plan'));for(const plan of n.plan)blocks.push(block(`<h3>${plan.rank}. ${esc(plan.diagnosis)}</h3>${plan.rank>1?p(plan.condition,'rp-condition'):''}${p(plan.text)}`,'rp-note-plan'));
 return [section('Example SOAP note',blocks,{paper:'portrait',kind:'clinical-note'})];
}
export function buildPartnerSections(l,edition='patient'){
 if(!PRINT_EDITIONS[edition])throw Error('Choose a printable document.');
 if(edition==='doorway')return doorwaySections(l);
 if(edition==='patient')return patientSections(l);
 if(edition==='examiner')return examinerSections(l);
 if(edition==='blank')return blankSections(l);
 if(edition==='soap')return soapSections(l);
 if(edition==='student')return [...doorwaySections(l),...blankSections(l)];
 return [...doorwaySections(l),...patientSections(l),...examinerSections(l),...blankSections(l),...soapSections(l)];
}
