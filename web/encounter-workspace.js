/* One encounter viewport. This module changes navigation, never clinical evidence. */
(()=>{'use strict';
const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let active=null,latest=null,queued=false,voiceAnchor=null,voiceNode=null,openedSheet=null,priorExam=window.openExamPanel;
const icons={talk:'◌',exam:'✚',guide:'◇',record:'≡'};
function button(text,id,cls=''){const b=document.createElement('button');b.type='button';b.className='btn sm '+cls;b.id=id;b.textContent=text;return b;}
function sheet(title,nodes){
 closeSheet();const d=document.createElement('dialog');d.className='ew-sheet';d.innerHTML='<div class="ew-sheet-head"><h2>'+E(title)+'</h2><button type="button" class="btn sm">Close</button></div><div class="ew-sheet-body"></div>';
 const moved=nodes.filter(Boolean).map(node=>{const marker=document.createComment('encounter-sheet-return');node.before(marker);q('.ew-sheet-body',d).append(node);return {node,marker,open:node.open};});
 moved.forEach(x=>{if(x.node.tagName==='DETAILS')x.node.open=true;});document.body.append(d);const prev=document.activeElement;
 const finish=()=>{moved.forEach(({node,marker,open})=>{if(marker.isConnected){marker.replaceWith(node);if(node.tagName==='DETAILS')node.open=open;}});d.remove();openedSheet=null;if(!q('#overlayRoot .overlay')&&prev?.isConnected)prev.focus({preventScroll:true});positionRoomFrame?.();};
 d.addEventListener('close',finish,{once:true});d.addEventListener('click',e=>{if(e.target.closest('#toolRefuse,#toolPrompts,#unityFallback,#guideRecommend,#guideDefer'))d.close();},{capture:true});d.addEventListener('change',e=>{if(e.target.id==='guideJump')d.close();},{capture:true});q('button',d).onclick=()=>d.close();d.addEventListener('click',e=>{if(e.target===d)d.close();});openedSheet=d;d.showModal();return d;
}
function closeSheet(){if(openedSheet?.open)openedSheet.close();}
function restoreVoice(){/* retired: the voice settings panel no longer exists */}
function cleanup(){if(!active)return;clearTimeout(active.outcomeTimer);closeSheet();restoreVoice();document.body.classList.remove('encounter-workspace-active');document.documentElement.style.removeProperty('--ew-available');active=null;}
function fit(){if(!active)return;const room=active.root;if(!room.isConnected)return;const top=Math.max(0,room.getBoundingClientRect().top);document.documentElement.style.setProperty('--ew-available',Math.max(280,innerHeight-top-8)+'px');positionRoomFrame?.();}
function selectTab(name,focus=false){
 if(name==='guide'){name='talk';const guide=q('#ewPanelGuide');if(guide)guide.open=true;}
 if(!active||!q('[data-ew-tab="'+name+'"]',active.root))return;
 active.tab=name;
 qa('[data-ew-tab]',active.root).forEach(b=>{const selected=b.dataset.ewTab===name;b.setAttribute('aria-selected',String(selected));b.tabIndex=selected?0:-1;});
 qa('[data-ew-panel]',active.root).forEach(p=>p.hidden=p.dataset.ewPanel!==name);
 const stream=q('#stream');if(stream){q('#ewTalkLog',active.root).append(stream);active.convo.classList.remove('full-record');q('.ew-right',active.root).classList.remove('full-record');stream.scrollTop=stream.scrollHeight;}
 if(name==='exam')refreshExam();if(name==='record'){renderRecord();active.unreadFinding=false;const tab=q('[data-ew-tab=record]');tab?.classList.remove('ew-record-new');tab?.querySelector('.ew-new-badge')?.remove();}
 if(focus)q('[data-ew-tab="'+name+'"]',active.root)?.focus({preventScroll:true});
 active.root.dataset.workspaceTab=name;fit();
}
function views(){const host=document.createElement('section');host.className='ew-view-options';host.innerHTML='<p>Choose a useful view. Scrolling, trackpad pinch and browser zoom remain normal browser controls.</p><div class="ew-view-grid"></div>';
 const actions=[['Face','[data-view="face"]'],['Upper body','[data-view="patient"]'],['Full patient','[data-view="full"]'],['Reset view','#resetView'],['Reduce motion','#motion'],['Clothes / anatomy','#coverageView, #anatomySwitch']];
 actions.forEach(([label,selector])=>{const b=button(label,'');q('.ew-view-grid',host).append(b);b.onclick=()=>{try{const target=q('#unityFrame')?.contentDocument?.querySelector(selector);if(!target||target.disabled||target.hidden){toast('This view option is unavailable in the current patient display.');return;}target.click();closeSheet();}catch{toast('Use the controls inside the patient view.');}};});
 const helper=q('.scene-help',active.root);sheet('Patient view',[host,helper]);}

/* Patient speech is a direct on/off control, not a settings screen. It governs
   the PATIENT'S output only: it never touches the clinician's microphone or the
   hands-free preference. Turning it off cancels anything currently or pending
   speaking; turning it on affects the NEXT reply and never replays old ones. */
function speechOn(){return !!window.pcmSpeechOptions?.enabled?.();}
function paintVoiceToggle(){
 const b=q('#ewVoice');if(!b)return;
 const unavailable=b.dataset.unavailable==='1';
 const on=speechOn()&&!unavailable;
 // A label and aria-pressed carry the state, so it never depends on colour.
 b.textContent=unavailable?'♫ Voice unavailable':(on?'♫ Voice on':'♪ Voice off');
 b.setAttribute('aria-pressed',String(on));
 b.setAttribute('aria-label',unavailable
   ?'Patient voice unavailable in this browser'
   :(on?'Patient speech is on. Activate to turn it off.'
       :'Patient speech is off. Activate to turn it on.'));
 b.classList.toggle('is-on',on);
 b.classList.toggle('is-unavailable',unavailable);
 b.disabled=unavailable;
}
function toggleVoice(){
 const options=window.pcmSpeechOptions;if(!options)return;
 const next=!options.enabled();
 options.setEnabled(next);          // cancels current+queued speech when false
 paintVoiceToggle();
 toast(next?'Patient speech on':'Patient speech off');
}
window.addEventListener('pcm-speech-preference',paintVoiceToggle);
window.addEventListener('pcm-voice-unavailable',()=>{const b=q('#ewVoice');if(b){b.dataset.unavailable='1';paintVoiceToggle();}});

// Compact labels for a segmented control; the full authored label stays as the
// accessible title so nothing is lost.
const POSITION_GLYPH={seated:'\u25E7',supine:'\u25AC',standing:'\u25AF',prone:'\u25AD'};
function shortPosition(label){return String(label).split('\u00b7')[0].replace(/ on the table| beside the table/,'').trim();}
/* Paint the selected position. Called only with the engine's recorded posture,
   so the highlight can never drift from the patient's actual state. */
function paintPosition(value){
 const host=q('#ewPosition');if(!host)return;
 qa('.ew-pos',host).forEach(b=>{
  const on=b.dataset.pos===value;
  b.setAttribute('aria-pressed',String(on));
  b.classList.toggle('is-on',on);
 });
}

/* ---------- Bedside ---------------------------------------------------- */
/* Grouped by purpose, and the distinction that matters is explicit:

   ACTION      - a bedside behaviour you are stating to the patient. It is SENT
                 through the ordinary patient-chat pipeline and recorded, the
                 same as typing it.
   SUGGESTION  - a phrase to consider. It is placed in the composer for you to
                 read, edit and send yourself. Browsing them sends nothing and
                 earns nothing.

   Opening this menu performs no action and records nothing. */
function bedsideGroups(){
  const coached=['guided','coached'].includes(latest?.learning_mode);
  const groups=[{
    title:'Preparation & comfort', kind:'action',
    note:'Stating one of these sends it to your patient and records the behaviour.',
    items:(typeof BEDSIDE!=='undefined'?BEDSIDE:[]).map(b=>({id:b.id,label:b.short,say:b.say})),
  }];
  // Interview moves are teaching aids. They are withheld in unassisted modes
  // for the same reason the rest of the coaching is.
  if(coached && typeof INTERVIEW_PROMPTS!=='undefined'){
    const closing=/anything you wanted to tell me|questions or concerns/i;
    groups.push({
      title:'Interview moves', kind:'suggestion',
      note:'Placed in the composer for you to review and send. Nothing is sent from here.',
      items:INTERVIEW_PROMPTS.filter(([t])=>!closing.test(t)).map(([say,why])=>({label:say,say,why})),
    },{
      title:'Wrapping up', kind:'suggestion',
      note:'For checking you have not missed anything before you finish.',
      items:INTERVIEW_PROMPTS.filter(([t])=>closing.test(t)).map(([say,why])=>({label:say,say,why})),
    });
  }
  return groups;
}

// Two-part bedside items report what is still outstanding rather than showing
// the whole item as undone once half of it is genuinely complete.
const COURTESY_PARTS={confirm_name:['name','preferred_address']};
const PART_LABEL={name:'name asked',preferred_address:'preferred name'};
function remainingLabel(id,parts){
 const all=COURTESY_PARTS[id]||[];
 const left=all.filter(x=>!parts.includes(x));
 return left.length? (left.map(x=>PART_LABEL[x]||x).join(', ')+' still to ask') : '';
}
function bedsideStatus(message){
  const el=q('#ewBedsideStatus');if(el)el.textContent=message||'';
}
function openBedside(){
  const done=(typeof courtesyDone==='function')?courtesyDone():{};
  const host=document.createElement('div');host.className='ew-bedside';
  host.innerHTML=bedsideGroups().map(g=>
    '<section class="ew-bs-group"><h3>'+E(g.title)+'</h3><p class="ew-bs-note">'+E(g.note)+'</p><div class="ew-bs-items">'+
    g.items.map((it,i)=>{
      const parts=(typeof courtesyParts==='function')?(courtesyParts()[it.id]||[]):[];
      const total=(typeof COURTESY_PARTS!=='undefined'&&COURTESY_PARTS[it.id])||null;
      const partial=!!(total&&parts.length&&parts.length<total.length);
      const used=g.kind==='action'&&it.id&&done[it.id]&&!partial;
      return '<button type="button" class="ew-bs'+(used?' used':'')+'" data-kind="'+g.kind+'" data-say="'+E(it.say)+'"'+
        (it.why?' title="'+E(it.why)+'"':'')+'>'+
        (g.kind==='action'?'<span class="ew-bs-tick" aria-hidden="true">'+(used?'✓':'○')+'</span>':'<span class="ew-bs-tick" aria-hidden="true">›</span>')+
        '<span>'+E(it.label)+'</span>'+
        (used?'<span class="ew-bs-done">done</span>'
             :partial?'<span class="ew-bs-done ew-bs-partial">'+E(remainingLabel(it.id,parts))+'</span>':'')+'</button>';
    }).join('')+'</div></section>').join('')+
    '<p class="ew-bs-status" id="ewBedsideStatus" role="status"></p>';
  sheet('Bedside',[host]);
  qa('.ew-bs',host).forEach(b=>{b.onclick=()=>{
    const text=b.dataset.say;
    if(b.dataset.kind==='action'){
      // Same pipeline as typing or speaking it. A repeat is allowed: repeating
      // an action is sometimes the right thing to do, and the record shows it.
      if(typeof sendSay==='function')sendSay(text);
      b.classList.add('used');
      const tick=q('.ew-bs-tick',b);if(tick)tick.textContent='✓';
      bedsideStatus('Said to your patient and recorded.');
      closeSheet();
    }else{
      const box=q('#say');
      if(box){box.value=text;box.focus();if(typeof autogrow==='function')autogrow(box);}
      bedsideStatus('Placed in the composer — edit it, then send when you are ready.');
      closeSheet();
    }
  };});
}
function makeExam(panel){
 panel.innerHTML='<div class="ew-panel-title"><h2>Perform an examination</h2><span id="ewExamScope"></span></div><div class="ew-board-search"><input id="manSearch" type="search" aria-label="Find an examination" placeholder="Find an action…"><button class="btn sm ghost" id="ewExamAll" aria-pressed="false">All actions</button></div><select id="ewManeuver" hidden aria-hidden="true"><option value="">Choose an action</option></select><div id="regionList" hidden><button data-region="" type="button">All regions</button></div><div id="manCount" class="tiny muted" aria-live="polite"></div><section id="ewExamOutcome" class="ew-exam-outcome" role="status" aria-live="polite" hidden></section><div class="ew-exam-scroll"><div id="ewExamBoard"></div><div class="ew-exam-detail" hidden tabindex="-1" aria-label="Examination technique"><button class="btn sm ghost" id="ewExamBack">← Actions</button><div id="manList"></div></div></div><div class="ew-exam-footer" hidden><div id="examRunning" role="status" class="small"></div><button class="btn primary" id="ewPerform" disabled>Perform selected action</button></div>';
 q('#manSearch',panel).oninput=()=>refreshExam(true);q('#regionList button',panel).onclick=()=>{active.showAllExams=true;refreshExam(true);};q('#ewExamAll',panel).onclick=()=>{active.showAllExams=!active.showAllExams;refreshExam(true);};q('#ewManeuver',panel).onchange=drawManeuver;q('#ewPerform',panel).onclick=perform;q('#ewExamBack',panel).onclick=()=>{q('#ewManeuver',panel).value='';drawManeuver();};
}
// Complaint-based navigation uses only the doorway and information already delivered.
// It never reads hidden expected maneuvers, diagnoses or the case answer key.
function relevantRegions(s){
 if(s?.learning_mode==='rehearsal')return null;
 const text=[s?.station_chart?.doorway,s?.station?.doorway,...(s?.transcript||[]).filter(e=>e.kind==='patient_reply'&&!e.meta?.no_information).map(e=>e.text)].filter(Boolean).join(' ').toLowerCase();
 const regions=new Set(['General']);let matched=false;
 const add=(pattern,names)=>{if(pattern.test(text)){matched=true;names.forEach(n=>regions.add(n));}};
 add(/cough|chest|breath|wheez|palpitation|edema|swelling|faint|syncope/,['Heart','Lungs','Extremities','HEENT']);
 add(/abdom|stomach|flank|urina|urine|urinary|dysuria|hematuria|kidney|bowel|vomit|nausea|diarrh|stool|constipat|swallow/,['Abdomen','Heart','Lungs','HEENT']);
 add(/headache|dizz|vertigo|weak|numb|tingl|balance|confus|seizure|speech|vision/,['Neurologic','HEENT','Neck','Heart','Musculoskeletal']);
 add(/back pain|back hurts|back ache|injur|joint|shoulder|knee|hip pain|neck pain|leg pain|arm pain/,['Musculoskeletal','Neurologic','Extremities','Neck','Osteopathic']);
 add(/sore throat|ear pain|sinus|fever|fatigue/,['HEENT','Neck','Heart','Lungs','Abdomen']);
 regions.add('Skin');return matched?regions:null;
}

// Each tile is an explicit, complete action. Never silently select mutually
// exclusive positions or unrelated special tests just to release more findings.
function quickActions(m){
 if(m.id==='vitals_review')return [];
 const bundle=(key,label,components)=>({...m,searchLabel:m.label,actionKey:m.id+':'+key,label,components});
 const groups={
  heent_eyes:[['inspect','Inspect pupils, conjunctivae, sclerae and corneas',['pupils','conjunctivae','sclerae','cornea']],['eye-movement','Check extraocular movements',['extraocular movements']],['fundus','Perform fundoscopic examination',['fundoscopic']]],
  neck_rom:[['rom','Check neck flexion and rotation',['flexion','rotation']],['brudzinski','Perform Brudzinski test',['brudzinski']],['kernig','Perform Kernig test',['kernig']]],
  abd_auscultate:[['sounds','Listen for bowel sounds in all four quadrants',['all four quadrants']],['bruits','Listen for abdominal bruits',['bruits']]],
  abd_percuss:[['quadrants','Percuss all four abdominal quadrants',['four quadrants']],['liver','Percuss liver span',['liver span']],['ascites','Check shifting dullness',['shifting dullness']]],
  abd_palpate:[['light','Lightly palpate all quadrants; assess guarding',['light','four quadrants','guarding']],['deep','Deeply palpate all four quadrants',['deep','four quadrants']],['rebound','Assess rebound tenderness',['rebound']]],
  msk_slr:[['supine','Supine straight-leg raise — both legs',['supine','right','left']],['seated','Seated straight-leg raise — both legs',['seated','right','left']]],
  neuro_reflexes:[['dtr','Check biceps, triceps, patellar and Achilles reflexes',['biceps','triceps','patellar','achilles']],['plantar','Check plantar response (Babinski)',['babinski']]],
  heart_auscultate:[['all','Listen at all four heart valve areas, on skin',m.components]],
  lungs_auscultate:[['all','Listen to lungs — compare both sides, front, back and sides',m.components]],
 };
 if(groups[m.id])return groups[m.id].map(g=>bundle(...g));
 const separate=new Set(['abd_special','msk_palpate','msk_strength','neuro_cn','neuro_sensory','neuro_coordination','skin_inspect','osteo_screen']);
 if(separate.has(m.id))return m.components.map((c,i)=>bundle(String(i),m.id==='abd_special'?({'cva tenderness':'Check costovertebral-angle tenderness',murphy:'Perform Murphy sign',mcburney:'Assess McBurney-point tenderness',rovsing:'Perform Rovsing sign',psoas:'Perform psoas test',obturator:'Perform obturator test'}[c]):m.label+' — '+c,[c]));
 return [bundle('complete',m.label,m.components)];
}

function refreshExam(reset=false){if(!active)return;const panel=q('#ewPanelExam'),sel=q('#ewManeuver',panel);if(!panel||!sel)return;
 const search=q('#manSearch',panel).value.trim().toLowerCase(),regions=relevantRegions(latest),all=active.showAllExams||!regions||!!search;
 const list=catalog().flatMap(g=>g.maneuvers.flatMap(m=>quickActions({...m,region:g.region}))).filter(m=>(all||regions.has(m.region))&&(!search||(m.label+' '+m.searchLabel+' '+m.id+' '+m.region+' '+(m.notes||'')+' '+m.components.join(' ')).toLowerCase().includes(search)));
 if(!all&&regions){const order=[...regions];list.sort((a,b)=>order.indexOf(a.region)-order.indexOf(b.region));}
 const old=sel.value,signature=list.map(m=>m.actionKey).join('|');active.examList=list;
 if(reset||signature!==sel.dataset.signature){sel.innerHTML='<option value="">Choose an action</option>'+list.map(m=>'<option value="'+E(m.actionKey)+'">'+E(m.label)+'</option>').join('');sel.dataset.signature=signature;if(!reset&&list.some(m=>m.actionKey===old))sel.value=old;if(search&&list.length===1)sel.value=list[0].actionKey;
 q('#ewExamBoard',panel).innerHTML=list.length?[...new Set(list.map(m=>m.region))].map(region=>'<section class="ew-action-group"><h3>'+E(region)+'</h3><div class="ew-action-grid">'+list.filter(m=>m.region===region).map(m=>'<button type="button" class="ew-action-tile" data-exam-action="'+E(m.actionKey)+'"><span aria-hidden="true">'+({inspection:'◉',auscultation:'◖',palpation:'✋',percussion:'⋯'}[m.method]||'✚')+'</span><b>'+E(m.label)+'</b><small>'+E(m.method)+' · '+m.duration_s+'s</small></button>').join('')+'</div></section>').join(''):'<p class="ew-empty">No matching actions. Try a shorter search.</p>';
 qa('[data-exam-action]',panel).forEach(b=>b.onclick=()=>{perform(b.dataset.examAction);});drawManeuver();}
 q('#ewExamScope',panel).textContent=latest?.learning_mode==='rehearsal'?'Full catalog · choose your own approach':all?'All actions · select only what is indicated':'Complaint & related systems · choose what fits';
 const toggle=q('#ewExamAll',panel);toggle.hidden=latest?.learning_mode==='rehearsal'||!regions;toggle.textContent=active.showAllExams?'Focused actions':'All actions';toggle.setAttribute('aria-pressed',String(!!active.showAllExams));q('#manCount',panel).textContent=list.length+' actions · click once to perform';updateExamStatus();
}
function drawManeuver(){if(!active)return;const p=q('#ewPanelExam');q('#ewExamBoard',p).hidden=false;q('.ew-exam-detail',p).hidden=true;q('.ew-exam-footer',p).hidden=true;updateExamStatus();}
function updateExamStatus(){if(!active)return;const busy=!!latest?.pending_exam||active.examSending;qa('[data-exam-action]',q('#ewPanelExam')).forEach(b=>b.disabled=busy||latest?.phase!=='encounter');}
async function perform(key){if(!active||!latest||latest.phase!=='encounter'||latest.pending_exam||active.examSending)return;const ctx=active,m=ctx.examList.find(x=>x.actionKey===key);if(!m)return;const sid=latest.id,components=m.components;ctx.examSending=true;updateExamStatus();
 try{const r=await api('/api/session/'+sid+'/exam',{maneuver_id:m.id,components,source_text:'Perform: '+m.label+(components.length?' ('+components.join(', ')+')':'')+' — patient '+recordedPosition()});if(active!==ctx||S?.id!==sid)return;if(r.error){outcome('Examination could not complete',r.message||'Please try again.');return;}if(r.state)S=Object.assign({},S,r.state);(r.events||[]).forEach(deliverEvent);if(r.state?.transcript)paintStream(S.transcript||[]);paintExamProgress();notifyPublicState();}
 catch{if(active===ctx)outcome('Connection interrupted','Reconnect and check Record before retrying.');}
 finally{ctx.examSending=false;if(active===ctx)updateExamStatus();}
}
// Display feedback separately from the evidence ledger: explanations are not findings.
function outcome(title,text){const host=q('#ewExamOutcome');if(!host)return;const signature=title+'|'+text;if(host.dataset.signature===signature)return;host.dataset.signature=signature;host.hidden=false;host.innerHTML='<strong>'+E(title)+'</strong><p>'+E(text)+'</p>';clearTimeout(active?.outcomeTimer);if(active&&!/progress|interrupted|could not/i.test(title))active.outcomeTimer=setTimeout(()=>{if(host.dataset.signature===signature)host.hidden=true;},9000);}
function syncExamOutcome(s){
 if(!active)return;const events=[...(s.transcript||[]),...(s.examination_activity||[])].sort((a,b)=>a.seq-b.seq);
 const findings=events.filter(e=>e.kind==='exam_finding');const last= findings.at(-1);
 if(active.lastFindingSeq!==undefined&&last&&last.seq>active.lastFindingSeq&&active.tab!=='record'){
  const tab=q('[data-ew-tab=record]');if(tab&&!tab.querySelector('.ew-new-badge')){tab.insertAdjacentHTML('beforeend','<small class="ew-new-badge">New</small>');tab.classList.add('ew-record-new');}
 }
 active.lastFindingSeq=last?.seq||0;
 if(s.pending_exam){active.outcomeSeq=null;outcome('Examination in progress','The action is running. Its findings will appear here when it finishes.');return;}
 const index=events.findLastIndex(e=>e.kind==='exam_action'||e.kind==='exam_refused');if(index<0)return;
 const action=events[index],meta=action.meta||{},rows=events.slice(index+1).filter(e=>e.kind==='exam_finding');
 const signature=String(action.seq)+':'+rows.map(e=>e.seq).join(',');if(active.outcomeSeq===signature)return;active.outcomeSeq=signature;
 const title=meta.label||meta.maneuver_id||'Examination';
 if(rows.length)outcome(title+' — findings',rows.map(e=>e.text).join('\n\n'));
 else if(action.kind==='exam_refused')outcome('Examination declined',action.text);
 else if(meta.status==='not_simulated')outcome(title+' — result unavailable','This case has no authored result for this action. The action is recorded, but it provides no finding to document. This does not mean the examination is clinically irrelevant or normal.');
 else if(meta.status==='interrupted')outcome('Examination interrupted','No findings were released. Check the encounter phase before trying again.');
 else if(meta.status!=='in_progress')outcome(title+' — no finding released','The selected sites or technique did not release a finding. Check the required position and technique. Do not document a normal result from this action.');
}
function renderRecord(){
 const host=q('#ewRecordLog');if(!host||!active)return;
 const events=latest?.transcript||[],activity=(latest?.examination_activity||[]).filter(e=>['not_simulated','interrupted'].includes(e.meta?.status)),signature=JSON.stringify([events,activity]);if(signature===active.recordSignature)return;active.recordSignature=signature;
 const open=new Set(qa('details[open][data-record]',host).map(n=>n.dataset.record));
 const groups={'Supplied information':[],'History obtained':[],'Examinations & findings':[],'Needs clarification':[],'Actions without findings':[],'Communication':[]};let question='Patient volunteered information';
 for(const ev of events){const meta=ev.meta||{};if(ev.kind==='student_utterance'){question=ev.text;continue;}
 let group,label,status='✓',detail=ev.text;
 if(ev.kind==='station_info'){group='Supplied information';label=meta.label||(meta.supplied_kind==='vitals'?'Doorway vitals':meta.supplied_kind==='result'?'Supplied result':'Doorway information');}
 else if(ev.kind==='patient_reply'){group=meta.no_information||meta.uncertain?'Needs clarification':meta.has_clinical_information===false?'Communication':'History obtained';label=group==='Communication'?'Introductions and conversation':meta.volunteered?'Volunteered history':question;status=group==='Needs clarification'?'?':group==='Communication'?'•':'✓';}
 else if(ev.kind==='exam_finding'){group='Examinations & findings';label=meta.label||meta.maneuver_id||'Examination finding';detail+=(meta.components?.length?'\nSites / technique: '+meta.components.join(', '):'');}
 else if(ev.kind==='exam_refused'){group='Needs clarification';label='Examination declined';status='!';}
 else continue;
 const rows=groups[group],prior=rows.find(x=>x.label===label);if(prior){prior.details.push({seq:ev.seq,text:detail});}else rows.push({label,status,seq:ev.seq,details:[{seq:ev.seq,text:detail}]});
 }
 for(const ev of activity)groups['Actions without findings'].push({label:ev.meta.label||ev.meta.maneuver_id,status:'!',seq:ev.seq,details:[{seq:ev.seq,text:ev.meta.status==='interrupted'?'Interrupted before findings were obtained.':'No authored result is available for this action. Do not document a normal finding.'}]});
 host.innerHTML=Object.entries(groups).filter(([label,rows])=>rows.length||['History obtained','Examinations & findings'].includes(label)).map(([label,rows])=>'<section class="ew-record-group"><h3>'+E(label)+' <span>'+rows.length+'</span></h3>'+(rows.length?rows.map(row=>'<details data-record="'+row.seq+'" '+(open.has(String(row.seq))?'open':'')+'><summary><span class="ew-check '+(row.status==='✓'?'':'uncertain')+'" aria-label="'+(row.status==='✓'?'Recorded':'Not established')+'">'+row.status+'</span><span>'+E(row.label)+'</span></summary><div>'+row.details.map(e=>'<p>'+E(e.text)+'</p><small>Encounter evidence #'+e.seq+'</small>').join('')+'</div></details>').join(''):'<p class="ew-empty">Nothing recorded here yet.</p>')+'</section>').join('');
}
function arrangeGuide(){if(!active)return;const panel=q('#encounterGuide');if(!panel||!active.root.contains(panel))return;const dest=q('#ewGuideCard');if(!dest)return;if(panel.parentElement!==dest)dest.append(panel);
 if(panel.classList.contains('case-guide')&&!q('.ew-guide-scroll',panel)){
  const scroll=document.createElement('div');scroll.className='ew-guide-scroll';const footer=document.createElement('div');footer.className='ew-guide-footer';const actions=q('.guide-current .guide-actions',panel),nav=q('.guide-navigation',panel);const contents=[...panel.children];contents.forEach(n=>scroll.append(n));if(actions)footer.append(actions);if(nav)footer.append(nav);panel.append(scroll,footer);
  const route=q('.guide-route',panel);const moreActions=document.createElement('div');moreActions.className='guide-navigation';[q('#guideRecommend',panel),q('#guideDefer',panel)].filter(Boolean).forEach(n=>moreActions.append(n));if(route){route.append(moreActions);const urgency=q('.guide-urgency',panel);if(urgency)route.append(urgency);}const draft=q('#guideDraft',panel);if(draft)draft.textContent='Draft question';const help=q('#unstuckButton',panel);if(help)help.textContent='Get unstuck';
  const extra=button('Steps','ewGuideMore','ghost');(nav||footer).append(extra);extra.onclick=()=>sheet('Your encounter path and obtained evidence',[q('.guide-route',panel),q('.guide-coverage',panel)]);
  qa('.guide-route,.guide-coverage',panel).forEach(n=>n.hidden=true);
  extra.addEventListener('click',()=>qa('.ew-sheet .guide-route,.ew-sheet .guide-coverage').forEach(n=>n.hidden=false));
 }
 if(!panel.classList.contains('case-guide')){
  panel.classList.add('coaching-open','ew-coached');
  const steps=q('.encounter-steps',panel);
  if(steps&&!q('#ewCoachStage',panel)){
   const wrap=document.createElement('label');wrap.className='ew-coach-stage';wrap.textContent='Focus';
   const select=document.createElement('select');select.id='ewCoachStage';select.setAttribute('aria-label','Coaching focus');
   const buttons=qa('[data-step]',steps);select.innerHTML=buttons.map(b=>'<option value="'+E(b.dataset.step)+'">'+E(b.textContent.trim().replace(/^(\d+)/,'$1 · '))+'</option>').join('');select.value=buttons.find(b=>b.getAttribute('aria-pressed')==='true')?.dataset.step||'';
   select.onchange=()=>buttons.find(b=>b.dataset.step===select.value)?.click();wrap.append(select);steps.before(wrap);steps.hidden=true;
  }
 }
 if(!panel.dataset.sidebarWired){panel.dataset.sidebarWired='true';panel.addEventListener('click',e=>{if(e.target.closest('#guideDraft')){selectTab('talk');q('#say')?.focus({preventScroll:true});}if(e.target.closest('#unstuckButton')){const body=q('#recoveryBody',panel);if(body)sheet('Get unstuck · pause, orient, choose',[body]);}});}
}
function mount(s){
 const root=q('#view .experience-room'),convo=q('.convo',root);if(!root||!convo)return;if(active?.root===root){latest=s;return;}cleanup();latest=s;
 active={root,convo,tab:'talk',sessionId:s.id};const small=document.createElement('p');small.className='ew-small-screen';small.textContent='Compact screen: the patient and tools stack here. The action bar stays available while you scroll. Use a wider window for the single-screen encounter.';root.prepend(small);document.body.classList.add('encounter-workspace-active');root.classList.add('ew-room');
 const work=document.createElement('div');work.className='ew-right';const hasGuide=['guided','coached'].includes(s.learning_mode);work.innerHTML='<nav class="ew-tabs" role="tablist" aria-label="Encounter workspace">'+[['talk','Talk'],['exam','Examine'],['record','Record']].map(([id,label])=>'<button type="button" role="tab" id="ewTab'+id+'" data-ew-tab="'+id+'" aria-controls="ewPanel'+id[0].toUpperCase()+id.slice(1)+'"><span aria-hidden="true">'+icons[id]+'</span> '+label+'</button>').join('')+'</nav><div class="ew-panels"><section role="tabpanel" id="ewPanelTalk" data-ew-panel="talk" aria-labelledby="ewTabtalk">'+(hasGuide?'<details id="ewPanelGuide" class="ew-talk-guide" '+(s.learning_mode==='guided'?'open':'')+'><summary>◇ Encounter coach <span>Your next move</span></summary><div id="ewGuideCard"><p class="small ew-guide-loading">Preparing your next step…</p></div></details>':'')+'<div id="ewTalkLog"></div></section><section role="tabpanel" id="ewPanelExam" data-ew-panel="exam" aria-labelledby="ewTabexam" hidden></section>'+'<section role="tabpanel" id="ewPanelRecord" data-ew-panel="record" aria-labelledby="ewTabrecord" hidden><p class="small ew-record-note">Your actual conversation, supplied information and completed actions.</p><div id="ewRecordLog"></div></section></div>';
 convo.before(work);work.append(convo);convo.classList.add('ew-conversation');q('#ewTalkLog',work).append(q('#stream',convo));const composer=q('.composer',convo);const reply=document.createElement('div');reply.className='ew-latest-reply';reply.innerHTML='<button class="btn sm ghost" type="button" aria-label="Read full conversation">Patient ↗</button><p></p>';reply.querySelector('button').onclick=()=>selectTab('talk');work.append(reply,composer);q('#voiceBar',convo)&&q('#ewPanelTalk',work).prepend(q('#voiceBar',convo));q('.branch-reminder',convo)&&q('#ewPanelTalk',work).prepend(q('.branch-reminder',convo));
 const bar=document.createElement('div');bar.className='ew-bottom';bar.setAttribute('aria-label','Essential encounter actions');root.append(bar);const tools=document.createElement('div');tools.className='ew-bottom-tools';bar.append(tools);
 const bedside=button('♡ Bedside','ewBedside');tools.append(bedside);bedside.onclick=openBedside;
 const position=document.createElement('div');position.className='ew-position';position.id='ewPosition';
 position.setAttribute('role','group');position.setAttribute('aria-label','Patient position');
 position.innerHTML=POSITIONS.map(([id,label])=>'<button type="button" class="ew-pos" data-pos="'+id+'" aria-pressed="false"><span class="ew-pos-i" aria-hidden="true">'+(POSITION_GLYPH[id]||'')+'</span>'+E(shortPosition(label))+'</button>').join('');
 tools.append(position);
 // requestPosition() is the ONE canonical path: it posts the change, and on a
 // refusal resets to the engine's real posture. It expects a `control` with
 // .disabled and .value, so the group is handed an adapter rather than being
 // given its own state that could disagree with the patient.
 const positionControl={
  set disabled(v){qa('.ew-pos',position).forEach(b=>b.disabled=!!v);},
  get disabled(){return qa('.ew-pos',position).every(b=>b.disabled);},
  set value(v){paintPosition(v);},
  get value(){return q('.ew-pos[aria-pressed="true"]',position)?.dataset.pos||'seated';}
 };
 qa('.ew-pos',position).forEach(b=>{b.onclick=()=>{
  if(b.getAttribute('aria-pressed')==='true')return;   // already there
  requestPosition(b.dataset.pos,positionControl);
 };});
 const view=button('⊙ View','ewView');view.onclick=views;tools.append(view);const chart=q('#toolChart',root);chart.textContent='Vitals';tools.append(chart);const audio=button('','ewVoice');audio.className='btn sm ew-toggle';tools.append(audio);paintVoiceToggle();audio.onclick=toggleVoice;
 const end=q('#btnEnd',root);end.textContent='Finish encounter →';end.classList.add('primary');bar.append(end);
 const store=document.createElement('div');store.className='ew-stored';store.hidden=true;root.append(store);[q('.room-left',root),q('.room-right',root),q('.patient-toolbar',root),q('.scene-help',root)].filter(Boolean).forEach(n=>store.append(n));
 q('#toolExam',root).onclick=()=>selectTab('exam');q('#unityFallback',root).onclick=()=>selectTab('exam');if(q('#quickUnstuck',root))q('#quickUnstuck',root).onclick=()=>{selectTab('guide');q('#unstuckButton')?.click();};
 q('#toggleRecord',root).onclick=()=>selectTab(active.tab==='record'?'talk':'record');
 qa('[data-ew-tab]',work).forEach(b=>{b.onclick=()=>selectTab(b.dataset.ewTab);b.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const tabs=qa('[data-ew-tab]',work);let i=tabs.indexOf(b);i=e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;selectTab(tabs[i].dataset.ewTab,true);};});
 const say=q('#say');say.onfocus=null;const focus=q('#patientFocus');focus.onclick=()=>{const expanded=root.classList.toggle('patient-focus');focus.textContent=expanded?'Return to split view':'Expand patient view';focus.setAttribute('aria-pressed',String(expanded));setUiMeta(s.id,{...uiMeta(s.id),expandedPatient:expanded});fit();};
 const recordNote=q('.ew-record-note',work);recordNote.textContent='✓ Recorded in this encounter. Expand a row for the answer or finding. These checks are not rubric scores.';
 makeExam(q('#ewPanelExam'));selectTab(active.tab);arrangeGuide();fit();
}
function extras(){if(!active)return;arrangeGuide();if(active.tab==='record')renderRecord();const ai=q('#aiConversation');if(ai&&active.root.contains(ai)&&ai.parentElement!==q('#ewPanelTalk'))q('#ewPanelTalk').prepend(ai);const pane=q('#ewPanelGuide');if(pane&&q('#encounterGuide',pane))q('.ew-guide-loading',pane)?.remove();}
window.pcmEncounterWorkspaceState=s=>{latest=s;if(!s||s.phase!=='encounter'){cleanup();return;}if(!active||active.root!==q('#view .experience-room')){requestAnimationFrame(()=>{if(latest?.phase==='encounter'){mount(latest);window.pcmEncounterWorkspaceState(latest);}});return;}if(active){const pos=q('#ewPosition');if(pos&&!qa('.ew-pos',pos).every(b=>b.disabled))paintPosition(s.patient_posture||'seated');updateExamStatus();syncExamOutcome(s);const last=(s.transcript||[]).filter(x=>['patient_reply','patient'].includes(x.kind)).slice(-1)[0];const text=q('.ew-latest-reply p');if(text&&text.textContent!==(last?.text||'Your conversation appears here.'))text.textContent=last?.text||'Your conversation appears here.';extras();}};
window.pcmFocusExam=function(id){if(!active)return false;selectTab('exam');const search=q('#manSearch');search.value=id;search.dispatchEvent(new Event('input',{bubbles:true}));search.focus({preventScroll:true});return true;};
window.openExamPanel=function(){if(active){selectTab('exam');return;}return priorExam?.();};
const observer=new MutationObserver(()=>{if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;if(document.body.dataset.phase!=='encounter'){cleanup();return;}if(typeof S!=='undefined'&&S?.phase==='encounter'){mount(S);extras();fit();}});});observer.observe(document.getElementById('view'),{childList:true,subtree:true});new MutationObserver(()=>{if(document.body.dataset.phase!=='encounter')cleanup();}).observe(document.body,{attributes:true,attributeFilter:['data-phase']});document.addEventListener('toggle',e=>{const detail=e.target;if(active&&detail instanceof HTMLDetailsElement&&detail.open&&detail.closest('.public-notice')){detail.open=false;sheet('About this public edition',[detail]);}},{capture:true});window.addEventListener('resize',fit);if(typeof S!=='undefined'&&S?.phase==='encounter')window.pcmEncounterWorkspaceState(S);
})();
