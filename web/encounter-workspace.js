/* One encounter viewport. This module changes navigation, never clinical evidence. */
(()=>{'use strict';
const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let active=null,latest=null,queued=false,voiceAnchor=null,voiceNode=null,openedSheet=null,priorExam=window.openExamPanel;
const icons={talk:'◌',exam:'✚',guide:'◇',record:'≡'};
function button(text,id,cls=''){const b=document.createElement('button');b.type='button';b.className='btn sm '+cls;b.id=id;b.textContent=text;return b;}
function sheet(title,nodes){
 closeSheet();const d=document.createElement('dialog');d.className='ew-sheet';d.setAttribute('aria-label',title);d.innerHTML='<div class="ew-sheet-head"><h2>'+E(title)+'</h2><button type="button" class="btn sm">Close</button></div><div class="ew-sheet-body"></div>';
 const moved=nodes.filter(Boolean).map(node=>{const marker=document.createComment('encounter-sheet-return');node.before(marker);q('.ew-sheet-body',d).append(node);return {node,marker,open:node.open};});
 moved.forEach(x=>{if(x.node.tagName==='DETAILS')x.node.open=true;});document.body.append(d);
 // Where to put the keyboard back. The control that opened the sheet may have
 // been re-rendered while it was open -- the coach rebuilds its action row on
 // every state update -- and "prev is gone" used to mean focus fell to <main>,
 // stranding a keyboard user at the top of the page.
 const prev=document.activeElement,prevId=prev?.id||'',prevLabel=(prev?.textContent||'').trim();
 const restore=()=>{
  if(q('#overlayRoot .overlay'))return;
  let target=prev?.isConnected?prev:null;
  if(!target&&prevId)target=document.getElementById(prevId);
  if(!target&&prevLabel)target=qa('button',active?.root||document).find(b=>b.textContent.trim()===prevLabel&&b.offsetParent);
  (target||q('[data-ew-tab="'+(active?.tab||'talk')+'"]',active?.root||document))?.focus({preventScroll:true});
 };
 const finish=()=>{moved.forEach(({node,marker,open})=>{if(marker.isConnected){marker.replaceWith(node);if(node.tagName==='DETAILS')node.open=open;}});d.remove();openedSheet=null;restore();positionRoomFrame?.();};
 d.addEventListener('close',finish,{once:true});d.addEventListener('click',e=>{if(e.target.closest('#toolRefuse,#toolPrompts,#unityFallback,#guideRecommend,#guideDefer,[data-step]'))d.close();},{capture:true});d.addEventListener('change',e=>{if(e.target.id==='guideJump')d.close();},{capture:true});q('button',d).onclick=()=>d.close();d.addEventListener('click',e=>{if(e.target===d)d.close();});openedSheet=d;d.showModal();return d;
}
function closeSheet(){if(openedSheet?.open)openedSheet.close();}
/* Where the student had the conversation scrolled, and whether that was the
   newest turn. Read before any move of the log, never after. */
function rememberStream(){
 const stream=q('#stream');if(!stream||!active)return;
 if(!stream.clientHeight||stream.dataset.moving)return;   // mid-move: not a reading position
 active.streamTop=stream.scrollTop;
}
function restoreVoice(){/* retired: the voice settings panel no longer exists */}
function cleanup(){if(!active)return;clearTimeout(active.outcomeTimer);closeSheet();restoreVoice();
 document.body.classList.remove('encounter-workspace-active');document.documentElement.style.removeProperty('--ew-available');active=null;}
function fit(){if(!active)return;const room=active.root;if(!room.isConnected)return;const top=Math.max(0,room.getBoundingClientRect().top);document.documentElement.style.setProperty('--ew-available',Math.max(280,innerHeight-top-8)+'px');positionRoomFrame?.();}
function selectTab(name,focus=false){
 if(name==='guide'){name='talk';const guide=q('#ewPanelGuide');if(guide)guide.open=true;}
 if(!active||!q('[data-ew-tab="'+name+'"]',active.root))return;
 rememberStream();
 active.tab=name;
 qa('[data-ew-tab]',active.root).forEach(b=>{const selected=b.dataset.ewTab===name;b.setAttribute('aria-selected',String(selected));b.tabIndex=selected?0:-1;});
 qa('[data-ew-panel]',active.root).forEach(p=>p.hidden=p.dataset.ewPanel!==name);
 // Moving the log between panels used to end with a jump to the newest turn,
 // so glancing at Record and coming back lost the place of anyone re-reading
 // an earlier answer. Remember where they were; only follow the newest turn if
 // that is where they already were.
 const stream=q('#stream');if(stream){
  const pinned=window.pcmStreamPinned?window.pcmStreamPinned(stream):true;
  const top=active.streamTop||0;
  // Re-parenting a scroller resets scrollTop and fires a scroll event, which
  // would be read as "the student scrolled to the top". Mark the move.
  stream.dataset.moving='1';
  q('#ewTalkLog',active.root).append(stream);active.convo.classList.remove('full-record');q('.ew-right',active.root).classList.remove('full-record');
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
   stream.scrollTop=pinned?stream.scrollHeight:top;
   delete stream.dataset.moving;
  }));
 }
 if(name==='exam'){refreshExam();const tab=q('[data-ew-tab=exam]');tab?.classList.remove('ew-record-new');tab?.querySelector('.ew-new-badge')?.remove();
 }if(name==='record'){renderRecord();active.unreadFinding=false;const tab=q('[data-ew-tab=record]');tab?.classList.remove('ew-record-new');tab?.querySelector('.ew-new-badge')?.remove();}
 if(focus)q('[data-ew-tab="'+name+'"]',active.root)?.focus({preventScroll:true});
 active.root.dataset.workspaceTab=name;fit();
}
/* The patient-view options. Everything here drives a control inside the 3D
   frame, so three things have to be true and were not:

   - availability must be read from what is actually RENDERED. The old check
     tested `hidden`/`disabled` on the button, but it is the CONTAINER that the
     frame hides, so "Put clothes on the patient" closed the sheet and did
     nothing on every case that is not the unclothed model.
   - a refusal must be visible. toast() is position:fixed at z-index 90 and this
     sheet is a <dialog> in the top layer, so the explanation was painted
     underneath its own backdrop.
   - a toggle must say which way it will go, read when it is CLICKED. */
function views(){
 const host=document.createElement('section');host.className='ew-view-options';
 host.innerHTML='<p>Choose a useful view. Scrolling, trackpad pinch and browser zoom remain normal browser controls.</p><div class="ew-view-grid"></div><p class="ew-view-status" role="status"></p>';
 const status=q('.ew-view-status',host);
 const frame=()=>{try{return q('#unityFrame')?.contentDocument||null;}catch{return null;}};
 const find=sel=>{const d=frame();return d?d.querySelector(sel):null;};
 const usable=el=>!!el&&!el.disabled&&!el.hidden&&!!el.offsetParent;
 const pressed=sel=>find(sel)?.getAttribute('aria-pressed')==='true';
 const actions=[
  ['Face',()=>'Face','[data-view="face"]'],
  ['Upper body',()=>'Upper body','[data-view="patient"]'],
  ['Full patient',()=>'Full patient','[data-view="full"]'],
  ['Reset view',()=>'Reset view','#resetView'],
  ['Reduce motion',()=>pressed('#motion')?'Resume patient animation':'Reduce patient animation','#motion'],
  ['Clothes',()=>pressed('#coverageView')?'Show anatomical view':'Put clothes on the patient','#coverageView'],
 ];
 const buttons=[];
 actions.forEach(([,label,selector])=>{
  const b=button(label(),'');q('.ew-view-grid',host).append(b);buttons.push([b,label,selector]);
  b.onclick=()=>{
   const target=find(selector);
   if(!usable(target)){
    status.textContent=frame()
     ?'That option is not available for this patient display.'
     :'The patient view is still loading. Try again in a moment.';
    return;}
   target.click();
   // Toggles stay in the sheet and re-label themselves; one-way views close it.
   if(target.hasAttribute('aria-pressed')){
    buttons.forEach(([btn,text])=>{btn.textContent=text();});
    status.textContent='Applied to the patient view.';
   } else closeSheet();
  };
 });
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
// A delayed browser voice list can become available after the first reply.
window.pcmDeviceSpeech?.subscribe(()=>{const b=q('#ewVoice');if(!b||!latest)return;const info=window.pcmDeviceSpeech.state(latest.appearance?.presentation);b.dataset.unavailable=info.available||info.loading?'0':'1';paintVoiceToggle();});

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
 return left.length? ('ask '+left.map(x=>PART_LABEL[x]||x).join(', ')) : '';
}
function bedsideStatus(message){
  const el=q('#ewBedsideStatus');if(el)el.textContent=message||'';
}
function openBedside(){
  const done=(typeof courtesyDone==='function')?courtesyDone():{};
  const host=document.createElement('div');host.className='ew-bedside';
  host.innerHTML=bedsideGroups().map(g=>
    // The effect belongs on the group, as a short verb, not as a sentence
    // repeated above every list. Two kinds, two labels, no paragraph.
    '<section class="ew-bs-group ew-bs-'+E(g.kind)+'"><h3>'+E(g.title)
      +'<span class="ew-bs-kind">'+(g.kind==='action'?'Says it to the patient':'Fills the composer')+'</span></h3>'
      +'<div class="ew-bs-items">'+
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
      if(!box){bedsideStatus('The composer is not available on this screen.');return;}
      const fill=()=>{box.value=text;if(typeof autogrow==='function')autogrow(box);
        box.dispatchEvent(new Event('input',{bubbles:true}));
        bedsideStatus('Placed in the composer — edit it, then send when you are ready.');
        closeSheet();box.focus();};
      const existing=box.value.trim();
      // Silently replacing an unsent message threw away the student's own
      // words. The coach's Draft asks first; this is the same action and now
      // asks the same question.
      if(existing&&existing!==text){
        const host=q('#ewBedsideStatus');if(!host)return fill();
        host.innerHTML='';
        host.append(document.createTextNode('You have an unsent message. '));
        const replace=button('Replace it','','ghost'),keep=button('Keep mine','','ghost');
        replace.onclick=fill;keep.onclick=()=>{bedsideStatus('Kept what you had typed.');};
        host.append(replace,keep);
        return;
      }
      fill();
    }
  };});
}
function makeExam(panel){
 panel.innerHTML='<div class="ew-panel-title"><h2>Perform an examination</h2><span id="ewExamScope"></span><button type="button" class="btn sm ghost" id="ewRefuse">Propose a sensitive examination</button></div><div class="ew-board-search"><input id="manSearch" type="search" aria-label="Find an examination" placeholder="Find an action…"><button class="btn sm ghost" id="ewExamAll" aria-pressed="false">All actions</button></div><select id="ewManeuver" hidden aria-hidden="true"><option value="">Choose an action</option></select><div id="regionList" hidden><button data-region="" type="button">All regions</button></div><div id="manCount" class="tiny muted" aria-live="polite"></div><nav id="ewExamRegions" class="ew-exam-regions" aria-label="Jump to a body system" hidden></nav><section id="ewExamOutcome" class="ew-exam-outcome" role="status" aria-live="polite" hidden></section><div class="ew-exam-scroll"><div id="ewExamBoard"></div></div><p id="examRunning" role="status" class="small ew-exam-running"></p>';
 q('#manSearch',panel).oninput=()=>refreshExam(true);q('#regionList button',panel).onclick=()=>{active.showAllExams=true;refreshExam(true);};q('#ewExamAll',panel).onclick=()=>{active.showAllExams=!active.showAllExams;refreshExam(true);};q('#ewManeuver',panel).onchange=drawManeuver;
 // The syllabus form -- "At this point, I would do a (xxx) exam" -- is named,
 // never performed, and it is the only way to earn those rows. Its one entry
 // point lived on the card this workspace stores away, so it existed and could
 // not be reached. It belongs with the examinations.
 q('#ewRefuse',panel).onclick=()=>window.pcmOpenRefusePanel?.();
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
  // Cervical suitability is a SAFETY precondition, not a technique component.
  // Bundling it meant one click asserted the student had cleared the neck --
  // the very check engine.perform_maneuver refuses to proceed without.
  neuro_dix_hallpike:[['screen','Check cervical and positional-test suitability first',['cervical_suitability']],
                      ['right','Dix–Hallpike, right — after clearing the neck',['cervical_suitability','right']],
                      ['left','Dix–Hallpike, left — after clearing the neck',['cervical_suitability','left']]],
 };
 if(groups[m.id])return groups[m.id].map(g=>bundle(...g));
 const separate=new Set(['abd_special','msk_palpate','msk_strength','neuro_cn','neuro_sensory','neuro_coordination','skin_inspect','osteo_screen']);
 if(separate.has(m.id))return m.components.map((c,i)=>bundle(String(i),m.id==='abd_special'?({'cva tenderness':'Check costovertebral-angle tenderness',murphy:'Perform Murphy sign',mcburney:'Assess McBurney-point tenderness',rovsing:'Perform Rovsing sign',psoas:'Perform psoas test',obturator:'Perform obturator test'}[c]):m.label+' — '+c,[c]));
 return [bundle('complete',m.label,m.components)];
}

/* What a single click will put on the record.

   Components are STATED technique ("this records stated technique; hands-on
   proficiency cannot be verified virtually"), and they gate which authored
   findings are released. A tile that bundles several of them is therefore
   making a specific claim on the student's behalf, and the honest way to keep
   one-click speed is to show the claim on the tile rather than to split every
   action into a longer list of clicks. */
function statedTechnique(m){
 const parts=(m.components||[]).filter(Boolean);
 if(parts.length<2)return '';
 const readable=parts.map(c=>String(c).replace(/_/g,' '));
 return 'Declares: '+readable.join(', ');
}

/* What has already been performed, from the ledger the engine keeps -- never
   from a local tally that could drift. A tile counts as done when the same
   maneuver was completed with at least the components the tile declares. */
function performedActions(){
 const events=[...(latest?.examination_activity||[]),...(latest?.transcript||[])];
 return events.filter(e=>e.kind==='exam_action'&&e.meta&&e.meta.status==='completed')
   .map(e=>({id:e.meta.maneuver_id,components:new Set(e.meta.components||[])}));
}
function isPerformed(m,done){
 return done.some(d=>d.id===m.id&&(m.components||[]).every(c=>d.components.has(c)));
}
function refreshExam(reset=false){if(!active)return;const panel=q('#ewPanelExam'),sel=q('#ewManeuver',panel);if(!panel||!sel)return;
 const searchBox=q('#manSearch',panel);const search=(searchBox?searchBox.value:'').trim().toLowerCase(),regions=relevantRegions(latest),all=active.showAllExams||!regions||!!search;
 const candidates=catalog().flatMap(g=>g.maneuvers.flatMap(m=>quickActions({...m,region:g.region}))).filter(m=>all||regions.has(m.region));
 const unfiltered=candidates.length;
 const list=candidates.filter(m=>!search||(m.label+' '+m.searchLabel+' '+m.id+' '+m.region+' '+(m.notes||'')+' '+m.components.join(' ')).toLowerCase().includes(search));
 if(!all&&regions){const order=[...regions];list.sort((a,b)=>order.indexOf(a.region)-order.indexOf(b.region));}
 const old=sel.value,signature=list.map(m=>m.actionKey).join('|');active.examList=list;
 if(reset||signature!==sel.dataset.signature){sel.innerHTML='<option value="">Choose an action</option>'+list.map(m=>'<option value="'+E(m.actionKey)+'">'+E(m.label)+'</option>').join('');sel.dataset.signature=signature;if(!reset&&list.some(m=>m.actionKey===old))sel.value=old;if(search&&list.length===1)sel.value=list[0].actionKey;
 // The complaint-relevant systems come first; everything after the third is
 // real but secondary, and a 27-tile wall made the core route hard to find.
 const regionsInOrder=[...new Set(list.map(m=>m.region))];
 const core=regionsInOrder.slice(0,3),rest=regionsInOrder.slice(3);
 const groupHtml=region=>'<section class="ew-action-group"><h3>'+E(region)+'</h3><div class="ew-action-grid">'+list.filter(m=>m.region===region).map(m=>'<button type="button" class="ew-action-tile" data-exam-action="'+E(m.actionKey)+'"><span aria-hidden="true">'+({inspect:'\u25c9',auscultate:'\u25d6',palpate:'\u270b',percuss:'\u22ef',special:'\u25c7'}[m.method]||'\u271a')+'</span><b>'+E(m.label)+'</b><small>'+E(m.method)+' \u00b7 '+m.duration_s+'s</small><small class="ew-done-flag" hidden>✓ performed</small>'+(statedTechnique(m)?'<small class="ew-states">'+E(statedTechnique(m))+'</small>':'')+'</button>').join('')+'</div></section>';
 q('#ewExamBoard',panel).innerHTML=list.length
  ?core.map(groupHtml).join('')
    +(rest.length?'<details class="ew-more-systems"><summary>Other systems ('+rest.length+')</summary>'+rest.map(groupHtml).join('')+'</details>':'')
  :'<p class="small">No actions match here. Use All actions to see the full catalog.</p>';
 qa('[data-exam-action]',panel).forEach(b=>b.onclick=()=>{perform(b.dataset.examAction);});
 // Exam rehearsal offers the whole catalog -- 84 actions over a dozen systems
 // in a short scroller, against a 14-minute clock. Naming the systems is not
 // a hint: the catalog is the same for every case.
 const strip=q('#ewExamRegions',panel),board=q('#ewExamBoard',panel);
 strip.hidden=regionsInOrder.length<4;
 if(!strip.hidden){
  strip.innerHTML=regionsInOrder.map(r=>'<button type="button" data-region-jump="'+E(r)+'">'+E(r)+'</button>').join('');
  qa('[data-region-jump]',strip).forEach(b=>b.onclick=()=>{
   const heading=qa('.ew-action-group h3',board).find(h=>h.textContent===b.dataset.regionJump);
   const group=heading&&heading.parentElement;if(!group)return;
   const more=group.closest('.ew-more-systems');if(more)more.open=true;
   const scroller=q('.ew-exam-scroll',panel);
   if(scroller)scroller.scrollTop=group.offsetTop-board.offsetTop;
   qa('[data-region-jump]',strip).forEach(x=>x.setAttribute('aria-current',String(x===b)));
  });
 }
 drawManeuver();}
 q('#ewExamScope',panel).textContent=latest?.learning_mode==='rehearsal'?'Full catalog · choose your own approach':all?'All actions · select only what is indicated':'Complaint & related systems · choose what fits';
 const toggle=q('#ewExamAll',panel);toggle.hidden=latest?.learning_mode==='rehearsal'||!regions;toggle.textContent=active.showAllExams?'Focused actions':'All actions';toggle.setAttribute('aria-pressed',String(!!active.showAllExams));// Whether the box is offered depends on how long the list is BEFORE the query,
 // never after. Deciding it from the filtered list hid the field on the third
 // keystroke, dropped focus, and -- because a hidden box's value was ignored --
 // silently reset the filter while its result stayed on screen.
 if(searchBox&&document.activeElement!==searchBox)searchBox.hidden=unfiltered<=30&&!search;
 q('#manCount',panel).dataset.total=list.length;paintExamDone();
}
/* Painted from the ledger on every state update, so a finding that lands while
   the board is open marks its tile without rebuilding (and losing) the list. */
function paintExamDone(){
 if(!active)return;const panel=q('#ewPanelExam');if(!panel)return;
 const done=performedActions();let n=0;
 qa('[data-exam-action]',panel).forEach(b=>{
  const m=(active.examList||[]).find(x=>x.actionKey===b.dataset.examAction);
  const was=m?isPerformed(m,done):false;if(was)n++;
  b.classList.toggle('is-done',was);
  const flag=q('.ew-done-flag',b);if(flag)flag.hidden=!was;
 });
 const count=q('#manCount',panel);
 if(count)count.textContent=(count.dataset.total||0)+' actions · '+(n?n+' already performed · ':'')
   +'one click performs the action and records the technique listed on it';
}
function drawManeuver(){if(!active)return;updateExamStatus();}
function updateExamStatus(){if(!active)return;const busy=!!latest?.pending_exam||active.examSending;
 const why=busy?'An examination is already running. Its findings appear here when it finishes.'
   :latest?.phase!=='encounter'?'The encounter is closed; no further examinations can be performed.':'';
 qa('[data-exam-action]',q('#ewPanelExam')).forEach(b=>{b.disabled=!!why;b.title=why;});
 // A board that greys out with no explanation reads as broken. The engine
 // already knows the reason; put it beside the board rather than nowhere.
 const running=q('#examRunning');if(running)running.textContent=why;
 // Moving the patient mid-examination was accepted by the toolbar and refused
 // by the engine, so the only feedback was an error. Say it on the control.
 const pos=q('#ewPosition');
 if(pos)qa('.ew-pos',pos).forEach(b=>{b.disabled=busy||!!active.positionBusy;
  b.title=busy?'Wait for the running examination to finish before repositioning':'';});}
async function perform(key){if(!active||!latest||latest.phase!=='encounter'||latest.pending_exam||active.examSending)return;const ctx=active,m=ctx.examList.find(x=>x.actionKey===key);if(!m)return;const sid=latest.id,components=m.components;ctx.examSending=true;updateExamStatus();
 try{const r=await api('/api/session/'+sid+'/exam',{maneuver_id:m.id,components,source_text:'Perform: '+m.label+(components.length?' ('+components.join(', ')+')':'')+' — patient '+recordedPosition()});if(active!==ctx||S?.id!==sid)return;if(r.error){outcome('Examination could not complete',r.message||'Please try again.');return;}if(r.state)S=Object.assign({},S,r.state);(r.events||[]).forEach(deliverEvent);if(r.state?.transcript)paintStream(S.transcript||[]);paintExamProgress();notifyPublicState();}
 catch{if(active===ctx)outcome('Connection interrupted','Reconnect and check Notes before retrying.');}
 finally{ctx.examSending=false;if(active===ctx)updateExamStatus();}
}
// Display feedback separately from the evidence ledger: explanations are not findings.
function outcome(title,text){const host=q('#ewExamOutcome');if(!host)return;const signature=title+'|'+text;if(host.dataset.signature===signature)return;host.dataset.signature=signature;host.hidden=false;host.innerHTML='<strong>'+E(title)+'</strong><p>'+E(text)+'</p>';
 clearTimeout(active?.outcomeTimer);
 if(!active)return;
 // The result of the examination you just performed used to disappear after
 // nine seconds, so re-reading a three-sentence finding meant leaving the
 // panel for Record. It is the panel's own status line: it stays until the
 // next examination replaces it, which costs no extra space and removes a
 // panel switch from every examination.
 if(active.tab!=='exam')markExamUnread();}
function markExamUnread(){
 const tab=q('[data-ew-tab=exam]');if(!tab||tab.querySelector('.ew-new-badge'))return;
 tab.insertAdjacentHTML('beforeend','<small class="ew-new-badge">Result</small>');tab.classList.add('ew-record-new');}
function syncExamOutcome(s){
 if(!active)return;
 // The engine reports, once, WHY a completed examination released nothing --
 // naming the parts that carry the finding. It only does so in the teaching
 // modes; elsewhere the list is empty and the generic wording stands, because
 // naming "rebound" or "guarding" would be telling the student the answer.
 if(s.exam_outcome)active.lastExamOutcome=s.exam_outcome;const events=[...(s.transcript||[]),...(s.examination_activity||[])].sort((a,b)=>a.seq-b.seq);
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
 else if(meta.status!=='in_progress'){
  const missed=active.lastExamOutcome&&active.lastExamOutcome.label===title
   ?(active.lastExamOutcome.missing_components||[]):[];
  outcome(title+' — no finding released',
   (missed.length
     ?'Nothing was released because these parts were not performed: '+missed.join(', ')+'. '
     :'The selected sites or technique did not release a finding. Check the required position and technique. ')
   +'Do not document a normal result from this action.');
 }
}
function renderRecord(){
 const host=q('#ewRecordLog');if(!host||!active)return;
 const summary=latest?.record;
 const signature=JSON.stringify(summary||null);if(signature===active.recordSignature)return;active.recordSignature=signature;
 host.innerHTML=recordHtml(summary);
}
// The same summary is wanted on the note screen, where the reference rail used
// to say nothing was available even in the modes that supply it.
function recordHtml(summary){
 if(!summary||!summary.groups?.length){
  return '<p class="ew-rec-empty">Nothing recorded yet. What the patient tells you, the chart supplies and your completed examinations find will be summarised here, ready to write up.</p>';
 }
 const row=(item,repeat)=>{
  // A denial is history the patient reported, never a measurement. Saying so
  // on the row is what stops "denies shortness of breath" being written up as
  // a clear chest.
  const notes=[];
  if(item.reported_negative)notes.push('reported negative');
  if(item.volunteered)notes.push('volunteered');
  if(item.uncertain)notes.push('patient unsure');
  // The row reads short; the exact words the patient used stay one hover or
  // one screen-reader description away, never as a default transcript.
  const exact=item.text_full?' title="Said: '+E(item.text_full)+'"':'';
  return '<div class="ew-rec-row"><dt'+(repeat?' class="ew-rec-cont" aria-hidden="true"':'')+'>'
   +(repeat?'':E(item.label||'Reported'))+'</dt><dd'+exact+'>'+E(item.text)
   +(notes.length?' <span class="ew-rec-note">'+E(notes.join(' \u00b7 '))+'</span>':'')+'</dd></div>';
 };
 const finding=(item,repeat)=>'<div class="ew-rec-row"><dt'+(repeat?' class="ew-rec-cont" aria-hidden="true"':'')+'>'
   +(repeat?'':E(item.label))+'</dt><dd>'+E(item.text)
   +(item.documented_as?'<span class="ew-rec-doc">Document as: '+E(item.documented_as)+'</span>':'')+'</dd></div>';
 // One list per group, not one per rubric row. The row name was printed as a
 // heading AND again as the label beneath it ("Onset / location" then "Onset",
 // "Location"), and a label repeated down consecutive rows ("Associated" three
 // times) read as three unrelated facts. Order still follows the note's rows.
 const dedupe=(html,items)=>{let last='';return items.map((item,i)=>{
   const label=item.label||(item.fact_id?'Reported':'Finding');
   const out=html(item,label===last&&i>0);last=label;return out;}).join('');};
 const hpiHtml=group=>{
   const slots=[['onset','O · Onset'],['location','L · Location / radiation'],['duration','D · Duration'],['character','C · Character'],['aggravating','A · Aggravating factors'],['relieving','R · Relieving factors'],['timing','T · Timing / course'],['severity','S · Severity']];
   const buckets=Object.fromEntries(slots.map(([id])=>[id,[]])),other=[];
   for(const section of group.sections)for(const item of section.items){
     const category=item.category;
     let slot=({onset:'onset',setting:'onset',location:'location',radiation:'location',duration:'duration',quality:'character',aggravating:'aggravating',alleviating:'relieving',timing:'timing',chronology:'timing',severity:'severity'})[category];
     // Duration is an authored fact identity, not a guess from a time mentioned
     // inside a longer answer. Every disclosed row appears exactly once.
     if(category==='timing'&&/duration/.test(item.fact_id||''))slot='duration';
     (slot?buckets[slot]:other).push(item);
   }
   return '<section class="ew-rec-group"><h3>History of present illness · OLDCARTS</h3>'+slots.map(([id,label])=>'<h4 class="ew-oldcarts-title">'+E(label)+'</h4>'+(buckets[id].length?'<dl class="ew-rec">'+dedupe(row,buckets[id])+'</dl>':'<p class="ew-oldcarts-empty">Not yet recorded</p>')).join('')+(other.length?'<h4 class="ew-oldcarts-title">Associated symptoms, prior episodes &amp; treatments</h4><dl class="ew-rec">'+dedupe(row,other)+'</dl>':'')+'</section>';
 };
 return summary.groups.map(group=>group.id==='hpi'?hpiHtml(group):
   '<section class="ew-rec-group"><h3>'+E(group.label)+'</h3><dl class="ew-rec">'
   +group.sections.map(section=>
     dedupe((item,repeat)=>item.fact_id?row(item,repeat):finding(item,repeat),section.items)
   ).join('')
   +'</dl></section>').join('')
  +(summary.unanswered?.length
    ? '<section class="ew-rec-group ew-rec-gaps"><h3>Asked, no information</h3><dl class="ew-rec">'
      +summary.unanswered.map(u=>'<div class="ew-rec-row"><dt>No answer</dt><dd>'+E(u.text)+'</dd></div>').join('')
      +'</dl></section>'
    : '');
}
window.pcmRecordHtml=recordHtml;
window.pcmSheet=(title,nodes)=>sheet(title,nodes);
function arrangeAside(){
 // Settings belong next to the control they affect, not above the conversation.
 if(!active)return;const ai=q('#aiConversation');const composer=q('.ew-right > .composer');
 if(ai&&composer&&ai.nextElementSibling!==composer)composer.before(ai);
}
function arrangeGuide(){if(!active)return;const panel=q('#encounterGuide');if(!panel||!active.root.contains(panel))return;const dest=q('#ewGuideCard');if(!dest)return;if(panel.parentElement!==dest)dest.append(panel);
 if(panel.classList.contains('case-guide')&&!q('.ew-guide-scroll',panel)){
  const scroll=document.createElement('div');scroll.className='ew-guide-scroll';const footer=document.createElement('div');footer.className='ew-guide-footer';const actions=q('.guide-current .guide-actions',panel),nav=q('.guide-navigation',panel);const contents=[...panel.children];contents.forEach(n=>scroll.append(n));if(actions)footer.append(actions);if(nav)footer.append(nav);panel.append(scroll,footer);
  const route=q('.guide-route',panel);const moreActions=document.createElement('div');moreActions.className='guide-navigation';[q('#guideRecommend',panel),q('#guideDefer',panel)].filter(Boolean).forEach(n=>moreActions.append(n));if(route){route.append(moreActions);const urgency=q('.guide-urgency',panel);if(urgency)route.append(urgency);}const draft=q('#guideDraft',panel);if(draft)draft.textContent='Draft question';// One name for one action. The coached card calls this "I'm stuck"; calling
  // it "Get unstuck" here made the same button read as a different feature.
  const help=q('#unstuckButton',panel);if(help)help.textContent="I'm stuck";
  const extra=button('Steps','ewGuideMore','ghost');(nav||footer).append(extra);extra.onclick=()=>sheet('Your encounter path and obtained evidence',[q('.guide-route',panel),q('.guide-coverage',panel)]);
  qa('.guide-route,.guide-coverage',panel).forEach(n=>n.hidden=true);
  extra.addEventListener('click',()=>qa('.ew-sheet .guide-route,.ew-sheet .guide-coverage').forEach(n=>n.hidden=false));
 }
 if(!panel.classList.contains('case-guide')){
  panel.classList.add('coaching-open','ew-coached');
  const steps=q('.encounter-steps',panel);
  if(steps&&!q('#ewCoachMoves',panel)){
   // "Other moves" opens the same list in a sheet, where each stage can name
   // itself. The dropdown replaced the move you were reading the moment it
   // changed, and gave no way back to it.
   steps.hidden=true;
   // The card renders its own "Other moves" button; this only hides the strip.
  }
 }
 if(!panel.dataset.sidebarWired){panel.dataset.sidebarWired='true';panel.addEventListener('click',e=>{if(e.target.closest('#guideDraft')){selectTab('talk');q('#say')?.focus({preventScroll:true});}if(e.target.closest('#unstuckButton')){const body=q('#recoveryBody',panel);if(body)sheet('Get unstuck · pause, orient, choose',[body]);}});}
}
function mount(s){
 const root=q('#view .experience-room'),convo=q('.convo',root);if(!root||!convo)return;if(active?.root===root){latest=s;return;}cleanup();latest=s;
 active={root,convo,tab:'talk',sessionId:s.id};const small=document.createElement('p');small.className='ew-small-screen';small.textContent='Compact screen: scroll between the patient and tools. Use a wider window to keep the encounter side by side.';root.prepend(small);document.body.classList.add('encounter-workspace-active');root.classList.add('ew-room');
 const work=document.createElement('div');work.className='ew-right';const hasGuide=['guided','coached'].includes(s.learning_mode);work.innerHTML='<nav class="ew-tabs" role="tablist" aria-label="Encounter workspace">'+[['talk','Talk'],['exam','Physical Exam'],['record','Notes']].map(([id,label])=>'<button type="button" role="tab" id="ewTab'+id+'" data-ew-tab="'+id+'" aria-controls="ewPanel'+id[0].toUpperCase()+id.slice(1)+'"><span aria-hidden="true">'+icons[id]+'</span> '+label+'</button>').join('')+'</nav><div class="ew-panels"><section role="tabpanel" id="ewPanelTalk" data-ew-panel="talk" aria-labelledby="ewTabtalk">'+'<div id="ewTalkLog"></div>'+(hasGuide?'<details id="ewPanelGuide" class="ew-talk-guide" open><summary><span class="ew-guide-eyebrow">Next step</span><span class="ew-guide-toggle" aria-hidden="true"></span></summary><div id="ewGuideCard"><p class="small ew-guide-loading">Preparing your next step…</p></div></details>':'')+'</section><section role="tabpanel" id="ewPanelExam" data-ew-panel="exam" aria-labelledby="ewTabexam" hidden></section>'+'<section role="tabpanel" id="ewPanelRecord" data-ew-panel="record" aria-labelledby="ewTabrecord" hidden><p class="small ew-record-note">What you have learned so far. Present illness is organized by OLDCARTS. The conversation itself stays in Talk.</p><div id="ewRecordLog"></div></section></div>';
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
  set disabled(v){if(active)active.positionBusy=!!v;qa('.ew-pos',position).forEach(b=>b.disabled=!!v);},
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
 const recordNote=q('.ew-record-note',work);recordNote.textContent='Only what you obtained in this encounter, in the order your note is scored. Hover a row to see the patient\u2019s exact words.';
 makeExam(q('#ewPanelExam'));selectTab(active.tab);arrangeGuide();arrangeAside();fit();
}
function extras(){if(!active)return;arrangeGuide();arrangeAside();if(active.tab==='record')renderRecord();const pane=q('#ewPanelGuide');if(pane&&q('#encounterGuide',pane))q('.ew-guide-loading',pane)?.remove();}
window.pcmEncounterWorkspaceState=s=>{latest=s;if(!s||s.phase!=='encounter'){cleanup();return;}if(!active||active.root!==q('#view .experience-room')){requestAnimationFrame(()=>{if(latest?.phase==='encounter'){mount(latest);window.pcmEncounterWorkspaceState(latest);}});return;}if(active){const pos=q('#ewPosition');if(pos&&!qa('.ew-pos',pos).every(b=>b.disabled))paintPosition(s.patient_posture||'seated');updateExamStatus();paintExamDone();syncExamOutcome(s);const last=(s.transcript||[]).filter(x=>['patient_reply','patient'].includes(x.kind)).slice(-1)[0];const text=q('.ew-latest-reply p');if(text&&text.textContent!==(last?.text||'Your conversation appears here.'))text.textContent=last?.text||'Your conversation appears here.';extras();}};
window.pcmFocusExam=function(id){if(!active)return false;selectTab('exam');const search=q('#manSearch');search.value=id;search.dispatchEvent(new Event('input',{bubbles:true}));search.focus({preventScroll:true});return true;};
window.openExamPanel=function(){if(active){selectTab('exam');return;}return priorExam?.();};
const observer=new MutationObserver(()=>{if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;if(document.body.dataset.phase!=='encounter'){cleanup();return;}if(typeof S!=='undefined'&&S?.phase==='encounter'){mount(S);extras();fit();}});});observer.observe(document.getElementById('view'),{childList:true,subtree:true});new MutationObserver(()=>{if(document.body.dataset.phase!=='encounter')cleanup();}).observe(document.body,{attributes:true,attributeFilter:['data-phase']});document.addEventListener('toggle',e=>{const detail=e.target;if(active&&detail instanceof HTMLDetailsElement&&detail.open&&detail.closest('.public-notice')){detail.open=false;sheet('About this public edition',[detail]);}},{capture:true});window.addEventListener('resize',fit);if(typeof S!=='undefined'&&S?.phase==='encounter')window.pcmEncounterWorkspaceState(S);
})();
