import {buildPartnerSections,PRINT_EDITIONS} from './partner-print.js?v=31bd29f16e';
export {PRINT_EDITIONS};
/* A source-preserving print edition. No encounter or grading writes occur here. */
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const para=(text,cls='')=>text?`<p${cls?` class="${cls}"`:''}>${esc(text).replaceAll('\n','<br>')}</p>`:'';
const label=(name,text,cls='')=>text?`<p class="pw-line ${cls}"><b>${esc(name)}</b> ${esc(text).replaceAll('\n','<br>')}</p>`:'';
const assetURL=path=>new URL(path,import.meta.url).href;
const safeImage=path=>typeof path==='string'&&/^(?:\.\/)?print-assets\/[\w./-]+\.(?:png|jpe?g|webp)$/i.test(path)?assetURL(path):null;
const arrayText=value=>Array.isArray(value)?value.join('\n'):String(value??'');
function figure(path,caption,cls='',version=''){
 let src=safeImage(path);if(src&&version){const url=new URL(src);url.searchParams.set('v',version);src=url.href;}return src?`<figure class="pw-figure ${cls}"><img src="${esc(src)}" alt="${esc(caption)}"><figcaption>${esc(caption)}</figcaption></figure>`:'';
}
export function chooseSimulation(l,manifest={}){
 const candidate=manifest.cases?.[l.case_id];
 const exact=candidate&&['name','sex','age'].every(key=>candidate.patient?.[key]===l.patient?.[key])?candidate:null;
 const profile=exact||manifest.generic?.[l.patient?.sex]||manifest.generic?.female||manifest.generic;
 if(!profile?.images)return null;
 // Variants may differ clinically. A screenshot never establishes the written case's findings.
 return {images:profile.images,label:exact?`${profile.label||'Actual case in Chat CSE'} · illustrative simulation view`:`${profile.label||'Representative Chat CSE patient'} · not this case's patient`,exact:Boolean(exact)};
}
function titleBlock(title,text=''){return `<section class="pw-block pw-heading"><h2>${esc(title)}</h2>${para(text)}</section>`;}
function sourceText(source){
 if(typeof source==='string')return esc(source);
 const title=source.title||source.label||source.document||(source.path||'').split('/').pop()||'Source reference';
 const url=source.url||source.source_url;
 return `${esc(title)}${source.locator?' — '+esc(source.locator):''}${source.reviewed?' · reviewed '+esc(source.reviewed):''}${url&&/^https:\/\//.test(url)?`<br><span class="pw-url">${esc(url)}</span>`:''}`;
}
const memoryBlocks=[
 ['FIFE · Patient perspective','The syllabus groups Feelings/Fears; Insight/Ideas; Function/Effects; Expectations. At the patient-perspective turn, ask what worries the patient and how symptoms affect daily life. Use what they actually report; an unanswered topic remains unknown.'],
 ['VINDICATE · Consider alternatives','A common expansion is Vascular, Infectious, Neoplastic, Degenerative/Deficiency, Iatrogenic/Intoxication, Congenital, Autoimmune, Traumatic, Endocrine/Metabolic. The course requires three different categories; the supplied files do not settle every expansion or diagnosis placement. Organize reasonable alternatives, not implausible diagnoses chosen just to fill letters.'],
 ['MOTHERR · Build a paired plan','Medications, Osteopathic treatment, Testing, Humanistic / supportive needs, Education, Referral, Return/follow-up. Consider function, support, and the ability to carry out the plan. The course requires at least three different elements per paired plan. This is a working expansion; see Scoring for its source status. For this case, connect the actual first plan’s proposed tests, explanation and disposition; do not add unnecessary treatment to collect letters.'],
 ['When blank · Recover your place','Pause → name your phase → recall its purpose → choose one relevant question or action. This recovery cue is supplementary teaching, not a scored course mnemonic.']
];
export function buildPrintSections(l,manifest={},credits=[]){
 const sim=chooseSimulation(l,manifest),imgs=sim?.images||{},caption=sim?.label||'';
 const illustration=(path,text,cls='')=>figure(path,text,cls,manifest.assets?.[path?.split('/').pop()]);
 const photo=(kind,cls='',brief=false)=>illustration(imgs[kind]||imgs.conversation||imgs.examination,brief?(sim?.exact?'Illustrative simulation view.':'Representative patient; not this case.'):caption,cls);
 const header=`<section class="pw-block pw-cover"><div class="pw-kicker">Chat CSE · Written encounter fieldbook</div><h1>${esc(l.title)}</h1><p class="pw-patient">${esc(l.patient.name)} · ${esc(l.patient.age)} · ${esc(l.variant_label)}</p><p>One defensible approach. Adapt the sequence to the patient; deeper explanations are outside the timed example.</p><div class="pw-facts"><span><b>${Math.floor(l.estimated_encounter_s/60)}:${String(l.estimated_encounter_s%60).padStart(2,'0')}</b> estimated encounter</span><span><b>${l.note_words}</b> note words</span><span><b>14 / 9 min</b> app rehearsal preset</span></div></section>`;
 const doorway=[header,`<section class="pw-block pw-doorway"><h2>01 · Read the doorway</h2>${(l.doorway.doorway||[]).map(x=>para(x)).join('')}<dl class="pw-vitals">${Object.entries(l.doorway.vitals||{}).map(([k,v])=>`<div><dt>${esc(({T:'Temperature',P:'Pulse',BP:'Blood pressure',R:'Respirations','Pulse Ox':'Oxygen saturation',Ht:'Height',Wt:'Weight'})[k]||k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>${(l.doorway.supplied_results||[]).map(x=>label('Supplied '+x.label,x.value)).join('')}<p class="pw-caption">Doorway vitals and supplied results are authorized information. The equipment illustration does not mean the student measured them.</p></section>`,
 `<section class="pw-block">${photo('doorway','pw-wide')}</section>`,
 `<section class="pw-block pw-callout"><h2>Find your starting point</h2>${label('Memory anchor',l.plan.anchor)}${para(l.plan.notice)}${para(l.plan.pivot)}</section>`,
 `<section class="pw-block">${illustration('print-assets/blood-pressure-equipment.jpg','Blood-pressure equipment · CDC, public domain. Equipment illustration; no patient result is shown.','pw-equipment')}<h3>Read the storyboard</h3><p><span class="pw-key pw-student">STUDENT</span> spoken words · <span class="pw-key pw-patient-key">PATIENT</span> an authored response · <span class="pw-key pw-action-key">ACTION</span> physical / virtual action · <span class="pw-key pw-finding-key">FINDING</span> obtained in this example · <span class="pw-key pw-why-key">WHY</span> teaching commentary.</p><p>Read each page down the left column, then down the right. Follow the numbered steps. Pictures orient the scene; only the written findings and linked encounter record supply clinical evidence.</p></section>`,
 `<section class="pw-block"><h3>Timing & simulation limits</h3>${para(l.estimate_method)}<p>Course files disagree on timing (14/9 versus 15/10 minutes). Follow the current station instructions. Application timers are unchanged. The example note is a study reference, not a typing target; leave time for thinking and editing. Virtual actions do not verify touch, force, auscultatory discrimination or full physical technique.</p><p>Guided and Coached practice are untimed. Independent practice uses 30 / 5 / 20 minutes. These allowances are practice modifications, not course requirements.</p></section>`];
 const timingNotes=doorway.pop();
 // A portrait and compact key fill the opening reading pane; station facts stay together opposite it.
 const [cover,doorwayBrief,simulationImage,memoryAnchor,storyboardKey]=doorway;
 doorway.splice(0,doorway.length,cover,simulationImage,storyboardKey,doorwayBrief,memoryAnchor);
 if(l.variant_id!=='base'){
  doorway.push(`<section class="pw-block pw-callout"><h3>This variation</h3>${para(l.variant_guidance)}</section>`);
  for(const d of l.differences||[])doorway.push(`<section class="pw-block"><h3>${esc(d.topic.replaceAll('_',' '))}</h3>${label('This path',d.current)}${label('Core case',d.base)}</section>`);
 }
 const appGuide=`<section class="pw-block pw-app-guide"><h3>Practice this walkthrough in the app</h3><p><b>Talk</b> for the interview. Use Bedside or Interview coach to draft an editable, unsent question; keep or combine an existing draft.</p><p><b>Physical Exam</b> performs the selected action. Wait for its finding, then use <b>Saved in Notes</b> to review it. Exam guide teaches the maneuver without creating a patient finding.</p><p><b>Notes</b> organizes obtained history by OLDCARTS. End the encounter to write your SOAP note; consult references only where the mode allows. Saving keeps a draft; <b>Submit note</b> finishes it.</p></section>`;
 const encounter=[titleBlock('02 · The encounter, step by step','A chronological reference: dialogue, actions, findings and the reason for each step.')];
 if(l.plan.urgent)encounter.push(`<section class="pw-block pw-urgent"><h3>Urgent care takes priority</h3><p>The example states escalation early; continue nonurgent questions or examinations only if care permits. A real patient should not wait for checklist completion.</p></section>`);
 let equipmentShown=false;
 l.timeline.forEach((t,i)=>{
  const first=i===0||l.timeline[i-1].section!==t.section;
  const equipment=t.kind==='action'&&/auscultat|listen.*(?:lung|heart)|stethoscop/i.test(t.action||'');
  let art='';
  if(equipment&&!equipmentShown){art=illustration('print-assets/stethoscope.jpg','Stethoscope · equipment illustration.','pw-turn-photo pw-equipment');equipmentShown=true;}
  else if(first)art=photo(t.kind==='action'?'examination':'conversation','pw-turn-photo',true);
  encounter.push(`<article class="pw-block pw-turn ${t.kind==='action'?'pw-action':'pw-dialogue'}" data-turn-index="${i}"><header class="pw-turn-header"><span class="pw-step">${String(i+1).padStart(2,'0')}</span><h3>${esc(t.section)}</h3></header>${art}${t.kind==='dialogue'?label('Student',t.student,'pw-student')+label('Patient',t.patient,'pw-patient-key'):label('Action',t.action,'pw-action-key')+label('Finding',t.finding,'pw-finding-key')}${label('Why',t.why,'pw-why-key')}<div class="pw-trace">${(t.event_ids||[]).length?'Encounter record: '+t.event_ids.map(esc).join(', '):'Teaching context'}</div></article>`);
 });
 const reasoning=[titleBlock('03 · Reason & remember',l.plan.exam),appGuide,timingNotes];
 for(const r of l.reasoning||[])reasoning.push(`<section class="pw-block pw-reasoning"><h3>${esc(r.question)}</h3>${para(r.why)}${label('If present',r.if_present)}${label('If absent',r.if_absent)}${label('Next action',r.next_action)}</section>`);
 reasoning.push(`<section class="pw-block pw-callout"><p>Assessment contains clinical inferences. Neither a differential nor its mnemonic category proves the diagnosis. Consider urgent alternatives even when they are less likely.</p></section>`,titleBlock('Memory tools in context'));
 for(const [title,text] of memoryBlocks)reasoning.push(`<section class="pw-block"><h3>${esc(title)}</h3>${para(text)}</section>`);
 reasoning.push(titleBlock('Common traps',l.plan.avoid));
 for(const x of l.omissions||[])reasoning.push(`<section class="pw-block pw-omission"><p>↳ ${esc(x)}</p></section>`);
 const soap=[titleBlock('04 · The complete SOAP note','Subjective reports what the patient said. Objective records supplied information and completed examination findings. Assessment is inference; Plan proposes future care. Do not copy this note into an attempt where you did not obtain its evidence.')];
 for(const key of ['S','O','A','P']){
  const name={S:'Subjective',O:'Objective',A:'Assessment',P:'Plan'}[key];
  const chunks=arrayText(l.note[key]).split(/\n/).filter(x=>x.trim());
  soap.push(`<section class="pw-block pw-soap" data-soap="${key}"><h3>${key} · ${name}</h3>${chunks.map(text=>para(text)).join('')}</section>`);
 }
 soap.push(`<section class="pw-block pw-callout"><p>Plans are proposals. No future ultrasound, CT, culture or treatment response is added to Objective merely because it is mentioned in Plan.</p></section>`);
 const evidence=[titleBlock('05 · Follow the evidence','Find the numbered storyboard step, then the exact encounter record. Statements stay tied to what was supplied, said or examined; inferences and proposed care remain distinct.')];
 const events=new Map((l.ledger||[]).map(e=>[e.seq,e]));
 const stepsByEvent=new Map();
 (l.timeline||[]).forEach((turn,i)=>(turn.event_ids||[]).forEach(id=>{const steps=stepsByEvent.get(id)||[];steps.push(i+1);stepsByEvent.set(id,steps);}));
 const unmatched=new Map();
 (l.note_links||[]).forEach((link,i)=>{
  const steps=[...new Set((link.event_ids||[]).flatMap(id=>stepsByEvent.get(id)||[]))];
  const extra=(link.event_ids||[]).filter(id=>!stepsByEvent.has(id));
  extra.forEach(id=>{if(events.has(id))unmatched.set(id,events.get(id));});
  const source=[steps.length?'Storyboard '+steps.map(n=>'step '+String(n).padStart(2,'0')).join(', '):'',extra.length?'Additional record below: '+extra.join(', '):''].filter(Boolean).join(' · ');
  evidence.push(`<section class="pw-block pw-evidence-line" data-note-link="${i}"><p><b class="pw-soap-tag">${esc(link.section)}</b> ${esc(link.statement)}</p><p class="pw-evidence-ref"><b>${esc(link.classification)}</b> · ${esc(link.trace_method)}<br>${esc(source)}${(link.event_ids||[]).length?'<br>Record IDs: '+link.event_ids.map(esc).join(', '):''}</p></section>`);
 });
 if(unmatched.size){
  evidence.push(titleBlock('Additional source records','These records are referenced by the note but do not appear in a numbered storyboard step. Each is printed once.'));
  for(const e of unmatched.values())evidence.push(`<blockquote class="pw-block pw-evidence" data-extra-event="${esc(e.seq)}"><b>Record ${esc(e.seq)} · ${esc(e.kind.replaceAll('_',' '))}</b>${para(e.text)}</blockquote>`);
 }
 const recall=[titleBlock('06 · Recall before you look','Try the prompts on paper. Your reflection here is separate from examination scores. Answers follow on a separate reading section.')];
 for(const [i,r] of (l.recall||[]).entries())recall.push(`<section class="pw-block pw-recall"><h3>${i+1}. ${esc(r.prompt)}</h3><div class="pw-answer-space"></div></section>`);
 const answers=[titleBlock('Check your recall','Use these explanations after attempting the prompts.')];
 for(const [i,r] of (l.recall||[]).entries())answers.push(`<section class="pw-block pw-reasoning"><h3>${i+1}. ${esc(r.prompt)}</h3>${para(r.answer)}</section>`);
 const sources=[titleBlock('Sources, review & image credits',l.review_status),`<section class="pw-block"><h3>Course authority</h3><p>These are paraphrased study examples, not a faculty-approved answer key. Automated consistency checks and a source citation do not establish full clinical review. Use the current course instructions where they differ.</p></section>`];
 for(const source of [...l.course_sources||[],...l.sources||[]])sources.push(`<section class="pw-block pw-source"><p>${sourceText(source)}</p></section>`);
 sources.push(titleBlock('Images are orientation, not evidence',`${caption}. Screenshots are from the running Chat CSE simulation. Pose and appearance are illustrative; they do not demonstrate technique or supply a finding. Meaningful case variations follow the written data, not the photograph.`));
 const usedImages=new Set(Object.values(imgs).map(path=>path?.split('/').pop()));usedImages.add('blood-pressure-equipment.jpg');if(equipmentShown)usedImages.add('stethoscope.jpg');
 for(const credit of credits.filter(c=>!c.file||usedImages.has(c.file.split('/').pop())))sources.push(`<section class="pw-block pw-source"><h3>${esc(credit.title)}</h3>${para(credit.author+' · '+credit.license)}${para(credit.usage)}<p class="pw-url">${esc(credit.source_url)}</p></section>`);
 return [{title:'Doorway preparation',kind:'preparation',blocks:doorway},{title:'Encounter storyboard',kind:'storyboard',blocks:encounter},{title:'Clinical reasoning & memory',kind:'reading',blocks:reasoning},{title:'Example SOAP note',kind:'reading',blocks:soap},{title:'Documentation evidence',kind:'reading',blocks:evidence},{title:'Recall exercise',kind:'reading',blocks:recall},{title:'Recall explanations',kind:'reading',startPage:true,blocks:answers},{title:'Sources & review',kind:'reading',blocks:sources}];
}
let activeRoot=null,previewContext=null;
export function clearWalkthroughPrint(){if(previewContext){document.title=previewContext.title;previewContext=null;}document.body.removeAttribute('data-walkthrough-print');document.body.removeAttribute('data-walkthrough-preview');document.getElementById('walkthroughPrintToolbar')?.remove();activeRoot?.remove();activeRoot=null;window.pcmPrintReport=null;}
export function showWalkthroughPreview({onPrint,onClose}){
 if(!activeRoot||!window.pcmPrintReport)throw Error('Prepare the print edition first.');
 if(!previewContext)previewContext={title:document.title};document.title=activeRoot.dataset.documentTitle;
 let bar=document.getElementById('walkthroughPrintToolbar');
 if(!bar){bar=document.createElement('nav');bar.id='walkthroughPrintToolbar';bar.setAttribute('aria-label','Print preview controls');document.body.insertBefore(bar,activeRoot);}
 bar.innerHTML=`<div><b>${esc(PRINT_EDITIONS[window.pcmPrintReport.edition].label)}</b><span>${window.pcmPrintReport.pages} Letter sheets · ${window.pcmPrintReport.edition==='soap'?'portrait clinical note':window.pcmPrintReport.edition==='study'?'landscape script; portrait SOAP key':'read left column, then right'}</span></div><button type="button" id="pwNativePrint">Print / Save PDF</button><button type="button" id="pwClosePrint">Return to lesson</button>`;
 bar.querySelector('#pwNativePrint').onclick=onPrint;bar.querySelector('#pwClosePrint').onclick=onClose;
 activeRoot.setAttribute('aria-hidden','false');activeRoot.setAttribute('aria-label',PRINT_EDITIONS[window.pcmPrintReport.edition].label+' preview');
 document.body.setAttribute('data-walkthrough-preview','true');document.body.setAttribute('data-walkthrough-print','approved');
 window.scrollTo(0,0);bar.querySelector('#pwNativePrint').focus();
}

async function loadStyle(){
 if(document.getElementById('walkthroughPrintCSS'))return;
 await new Promise((resolve,reject)=>{const link=document.createElement('link');link.id='walkthroughPrintCSS';link.rel='stylesheet';link.href=assetURL('walkthrough-print.css?v=d154cbfbfc');link.onload=resolve;link.onerror=()=>{link.remove();reject(Error('The print layout could not load. Please reconnect and try again.'));};document.head.append(link);});
}
function makePage(root,l,title,kind,paper='landscape'){
 const page=document.createElement('section');page.className='pw-page '+(kind==='storyboard'?'pw-storyboard-page':'pw-reading-page');page.dataset.section=title;page.dataset.paper=paper;page.dataset.kind=kind;
 page.innerHTML=`<header class="pw-page-header"><span class="pw-brand">Chat CSE <i>/</i> ${esc(title)}</span><span>${esc(l.patient.name)} · ${esc(l.variant_label)}</span></header><div class="pw-columns"><div class="pw-column"></div>${paper==='portrait'?'':'<div class="pw-column"></div>'}</div><footer class="pw-page-footer"><span>${esc(l.case_id)} · ${esc(l.variant_id)} · Print edition 2026-09-13</span><span class="pw-page-count"></span></footer>`;root.append(page);return page;
}
async function decodeImages(root){
 const images=[...root.querySelectorAll('img')];
 const failures=[];
 await Promise.all(images.map(async img=>{try{await img.decode();if(!img.naturalWidth)throw Error();}catch{failures.push(img.getAttribute('src'));}}));
 if(failures.length)throw Error('A walkthrough image could not load. Reconnect and try Print case documents again.');
}
function paginate(root,l,sections,edition){
 const report={edition,case_id:l.case_id,variant_id:l.variant_id,pages:0,turns:l.timeline.length,oversized:[],images:0,sections:[],evidence_strategy:'Actor facts are separate from obtained evidence. Revised note references identify demonstrated topics and exact examinations; they are not automatic semantic verification.'};
 let page=null,column=null,colIndex=0,previousKind=null,previousPaper=null;
 for(const section of sections){
  const paper=section.paper||'landscape';
  const continueReading=section.kind===previousKind&&previousPaper===paper&&!section.startPage;
  if(!continueReading){page=makePage(root,l,section.title,section.kind,paper);column=page.querySelector('.pw-column');colIndex=0;}

  previousKind=section.kind;previousPaper=paper;
  const next=()=>{if(paper!=='portrait'&&colIndex===0){colIndex=1;column=page.querySelectorAll('.pw-column')[1];}else{page=makePage(root,l,section.title,section.kind,paper);colIndex=0;column=page.querySelector('.pw-column');}};
  const queue=section.blocks.map(html=>{const holder=document.createElement('template');holder.innerHTML=html;return holder.content.firstElementChild;});
  for(let n=0;n<queue.length;n++){
   const block=queue[n];column.append(block);
   // Headings stay with enough of the following block to preserve reading order.
   let overflow=column.scrollHeight>column.clientHeight+1;
   if(!overflow&&block.classList.contains('pw-heading')&&queue[n+1]){
    // Keep the section label, navigation line, and first actual answer together.
    const preview=[];
    for(let look=n+1;look<queue.length;look++){const child=queue[look].cloneNode(true);column.append(child);preview.push(child);if(!child.classList.contains('pw-heading')&&!child.classList.contains('rp-crossref'))break;}
    overflow=column.scrollHeight>column.clientHeight+1;preview.forEach(child=>child.remove());
   }
   if(overflow&&column.children.length>1){block.remove();next();column.append(block);}
   if(column.scrollHeight>column.clientHeight+1){
    // Split by direct children, preserving complete paragraphs and every original word.
    const children=[...block.children];
    if(children.length>1){
     block.remove();let part=block.cloneNode(false);part.dataset.continuation='false';
     column.append(part);
     for(const child of children){
      part.append(child);
      if(column.scrollHeight>column.clientHeight+1&&part.children.length>1){child.remove();next();part=block.cloneNode(false);part.dataset.continuation='true';part.removeAttribute('data-anchor');part.removeAttribute('id');part.removeAttribute('data-turn-index');part.removeAttribute('data-note-link');column.append(part);part.append(child);}
      if(column.scrollHeight>column.clientHeight+1)report.oversized.push({section:section.title,text:child.textContent.slice(0,100)});
     }
    }else report.oversized.push({section:section.title,text:block.textContent.slice(0,100)});
   }
  }
  report.sections.push({name:section.title,blocks:section.blocks.length});
 }
 const pages=[...root.querySelectorAll('.pw-page')];report.pages=pages.length;report.images=root.querySelectorAll('img').length;
 pages.forEach((page,i)=>{page.querySelector('.pw-page-count').textContent=`${i+1} / ${pages.length}`;});
 const anchors=new Map();
 pages.forEach((page,i)=>page.querySelectorAll('[data-anchor]').forEach(el=>{if(!anchors.has(el.dataset.anchor)){el.id='rp-'+el.dataset.anchor;anchors.set(el.dataset.anchor,{page:i+1,element:el});}}));
 report.missingReferences=[];
 root.querySelectorAll('[data-page-ref]').forEach(link=>{const target=anchors.get(link.dataset.pageRef);if(target){link.querySelector('.rp-page-ref').textContent='p. '+target.page;link.onclick=event=>{event.preventDefault();target.element.scrollIntoView({block:'center'});};}else {report.missingReferences.push(link.dataset.pageRef);}});
 return report;
}
export async function prepareWalkthrough(l,{edition='patient'}={}){
 clearWalkthroughPrint();await loadStyle();await document.fonts.ready;
 const [manifest,onlineCredits,appCredits]=edition==='study'?await Promise.all([
  fetch(assetURL('print-assets/manifest.json?v=576a8c5fb4'),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('The simulation image set is unavailable. Please try again after reconnecting.');return r.json();}),
  fetch(assetURL('print-assets/ONLINE-SOURCES.json'),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Image credits could not load.');return r.json();}),
  fetch(assetURL('print-assets/APP-SOURCES.json'),{cache:'no-store'}).then(r=>r.ok?r.json():[])
 ]):[{},[],[]];
 if(edition==='study'&&!chooseSimulation(l,manifest))throw Error('No approved simulation image is available for this print edition.');
 const root=document.createElement('div');root.id='walkthroughPrint';root.dataset.documentTitle=`${l.patient.name} - ${PRINT_EDITIONS[edition]?.label||'Print'} - ${l.variant_label}`;root.dataset.edition=edition;root.setAttribute('aria-hidden','true');document.body.append(root);activeRoot=root;
 const credits=[...onlineCredits,...(Array.isArray(appCredits)?appCredits:[]).map(c=>({...c,title:c.title||c.file,author:c.author||c.source||'Chat CSE screenshot',license:c.license||'Underlying model and room asset credits are provided in the application',source_url:c.source_url||'',usage:c.usage||'Illustrative app scene.'}))];
 const sections=buildPartnerSections(l,edition,edition==='study'?buildPrintSections(l,manifest,credits):[]);
 // Preload each unique local image before measuring physical page geometry.
 const preloader=document.createElement('div');preloader.innerHTML=sections.flatMap(s=>s.blocks).join('');root.append(preloader);
 try{
  await decodeImages(preloader);preloader.remove();
  const report=paginate(root,l,sections,edition);
  await decodeImages(root);
  if(report.missingReferences.length)throw Error('A script cross-reference could not be resolved. No pages were removed.');
  if(report.oversized.length)throw Error('A section is too long for the print layout. The lesson has not been truncated. Please use the written lesson while this layout is corrected.');
  window.pcmPrintReport=report;return {root,report};
 }catch(error){clearWalkthroughPrint();throw error;}
}
