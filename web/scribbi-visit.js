/* Scribbi visit player: watch the demonstrated visit before Scribbi drafts it.

   Route: #scribbi/r/<id>/visit

   The visit plays like a video. The 3D patient talks while her lines are
   spoken aloud, captions follow every line, each examination shows its
   technique demonstration, and Scribbi visibly listens -- except when the
   clinician palpates in silence, which is exactly why hands-on findings never
   reach Scribbi's note. When the visit ends (or the student skips ahead), the
   review clock starts and Scribbi's draft opens.

   Everything shown comes from the engine: the visit record the review uses
   (/api/scribbi/rounds/<id>) and its staging (/playback). Nothing here grades
   or reveals the draft. */
(()=>{'use strict';
const kit=()=>window.pcmScribbi?.kit||{};
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const $=(s,r)=>(r||document).querySelector(s);
const $$=(s,r)=>Array.from((r||document).querySelectorAll(s));
const view=()=>document.getElementById('view');
const call=(path,body)=>kit().call?kit().call(path,body):Promise.resolve({error:'offline'});
const ic=(k,cls)=>kit().ic?kit().ic(k,cls):'';
const mascot=(mood,extra)=>kit().mascot?kit().mascot(mood,extra):'';
const reduced=()=>kit().reduced?kit().reduced():false;
const store={get:k=>kit().store?.get(k),set:(k,v)=>kit().store?.set(k,v),del:k=>kit().store?.del(k)};
const firstName=n=>String(n||'Patient').split(/\s+/)[0];
const mmss=s=>{s=Math.max(0,Math.round(s||0));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');};
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
// The iframe URL is stamped by tools/stamp_cache_tags.py; viewer mode is appended.
const ROOM_URL='patient3d/index.html?v=d0af1e6fb3';
const SPEEDS=[0.75,1,1.25,1.5,2];
const PACE={measured:.94,conversational:.98,slightly_hesitant:.94,direct:1,unhurried:.92,deliberate:.94};
const REQUIRED={female:'Google US English',male:'Google UK English Male'};
const FEMALE=/\b(?:female|woman|samantha|victoria|karen|moira|tessa|fiona|serena|zira|susan|allison|ava|nicky|kate|joanna|salli|kendra|kimberly|ivy|emma|amy|olivia|jenny|aria|flo|sandy|shelley)\b/i;
const MALE=/\b(?:male|man|alex|daniel|tom|aaron|arthur|oliver|rishi|david|mark|evan|nathan|matthew|joey|justin|brian|guy|ryan|eric|thomas|eddy|reed|rocko)\b/i;

let P=null,gen=0;

/* ---------------------------------------------------------------- voices */
function synth(){return 'speechSynthesis' in window&&typeof SpeechSynthesisUtterance==='function'?window.speechSynthesis:null;}
function loadVoices(){
 const s=synth();if(!s)return Promise.resolve([]);
 const now=s.getVoices();if(now.length)return Promise.resolve(now);
 return new Promise(resolve=>{let done=false;const finish=()=>{if(done)return;done=true;s.removeEventListener?.('voiceschanged',finish);resolve(s.getVoices());};s.addEventListener?.('voiceschanged',finish);setTimeout(finish,1500);});
}
// macOS ships novelty voices (sound effects and singing); never cast them.
const NOVELTY=/\b(?:albert|bad news|bahh|bells|boing|bubbles|cellos|good news|jester|organ|superstar|trinoids|whisper|wobble|zarvox)\b/i;
function pickVoices(all,sex){
 const en=all.filter(v=>/^en(?:[-_]|$)/i.test(v.lang||'')&&!NOVELTY.test(v.name||''));if(!en.length)return null;
 const named=n=>en.find(v=>v.name===n);
 const fits=(v,s)=>s==='male'?MALE.test(v.name)&&!FEMALE.test(v.name):FEMALE.test(v.name);
 const other=sex==='male'?'female':'male';
 const patient=named(REQUIRED[sex])||en.find(v=>fits(v,sex))||en[0];
 let clinician=named(REQUIRED[other]);
 if(!clinician||clinician===patient)clinician=en.find(v=>v!==patient&&fits(v,other))||en.find(v=>v!==patient&&/en[-_]US/i.test(v.lang))||en.find(v=>v!==patient)||patient;
 return {patient,clinician,same:patient===clinician};
}
// Long utterances can stall in some browsers; speak a line a sentence or two at a time.
function chunks(text){
 const parts=String(text||'').replace(/\s+/g,' ').trim().split(/(?<=[.!?])\s+(?=[A-Z0-9"'(])/);
 const out=[];for(const p of parts){if(out.length&&(out[out.length-1]+' '+p).length<=190)out[out.length-1]+=' '+p;else out.push(p);}
 return out.filter(Boolean);
}
const words=t=>String(t||'').trim().split(/\s+/).filter(Boolean).length;
function estimate(text){return Math.max(1.4,words(text)/2.55+.35);}

/* ------------------------------------------------------------------ beats */
// One beat is one thing seen or heard: a line spoken, an examination, or an
// action such as helping the patient lie back.
function spokenFinding(t){
 const text=String(t.finding||'').trim();
 return text.replace(/\s*\(No finding was released for this action\.\)\s*/i,'');
}
function buildBeats(visit,pb){
 const staging=new Map((pb?.turns||[]).map(t=>[t.id,t]));
 const beats=[];
 for(const t of visit.turns||[]){
  const st=staging.get(t.id)||{};
  const base={turn:t.id,section:t.section||'',posture:st.posture||'seated',why:st.why||'',affect:st.affect,gesture:st.gesture};
  if(t.kind==='talk'){
   if(t.student)beats.push({...base,kind:'say',who:'you',text:t.student});
   if(t.patient)beats.push({...base,kind:'reply',who:'patient',text:t.patient});
  }else if(t.kind==='exam'){
   beats.push({...base,kind:'exam',who:'you',label:t.label||'Examination',region:t.region||'',felt:!!t.felt,finding:spokenFinding(t),plan:st.plan||null,maneuver:t.maneuver_id||'',components:st.components||[]});
  }else if(t.label){
   beats.push({...base,kind:'step',who:'you',text:t.label,detail:t.detail||''});
  }
 }
 beats.forEach((b,i)=>{b.i=i;b.est=b.kind==='step'?1.8:b.kind==='exam'?examSeconds(b)+(b.felt?3:estimate(b.finding)):estimate(b.text)+.3;});
 let at=0;for(const b of beats){b.at=at;at+=b.est;}
 return {beats,total:at};
}
function examSeconds(b){const d=Number(b.plan?.duration_s)||12;return clamp(d/7,3.2,7);}

/* ------------------------------------------------------------------ open */
async function open(id){
 close();
 const token=++gen;
 view().innerHTML=`<div class="sv-shell is-loading"><p class="sv-loading-note" role="status">Setting up the visit…</p></div>`;
 const [round,pb]=await Promise.all([call('/api/scribbi/rounds/'+encodeURIComponent(id)),call('/api/scribbi/rounds/'+encodeURIComponent(id)+'/playback')]);
 if(token!==gen)return;
 if(round?.error||!round?.id){return fail('That visit isn’t available',round?.message||round?.error||'It may have been removed by a progress reset.');}
 if(round.status==='signed'||pb?.error){location.replace('#scribbi/r/'+round.id);return;}
 const {beats,total}=buildBeats(round.visit,pb);
 if(!beats.length){location.replace('#scribbi/r/'+round.id);return;}
 const prefs=store.get('player')||{};
 const saved=Number(store.get('visitpos.'+round.id))||0;
 P={id:round.id,round,pb,beats,total,i:clamp(saved,0,Math.max(0,beats.length-1)),resumeAt:saved>0&&saved<beats.length?saved:0,
    playing:false,token:0,speed:SPEEDS.includes(prefs.speed)?prefs.speed:1.25,captions:prefs.captions!==false,voiceOn:prefs.voice!==false,
    why:!!prefs.why,voices:null,frame:null,frameReady:false,patientReady:false,seq:0,posture:'seated',speaking:false,busy:false,
    raf:0,userScrolledAt:0,started:false,listeners:[],ended:false,lastReply:'',replay:round.started!==false};
 paint();
 loadVoices().then(all=>{if(!P||P.id!==round.id)return;P.voices=pickVoices(all,round.visit?.patient?.sex==='male'||pb?.appearance?.presentation==='male'?'male':'female');paintControls();});
 mountRoom();
 listen(document,'keydown',keys);
 listen(window,'message',roomMessage);
}
function fail(title,msg){view().innerHTML=`<div class="sv-shell"><div class="sv-fail">${mascot('oops')}<h1>${E(title)}</h1><p>${E(msg)}</p><a class="sb-btn sb-primary" href="#scribbi">Back to Scribbi</a></div></div>`;}
function listen(target,type,fn,opts){target.addEventListener(type,fn,opts);P.listeners.push(()=>target.removeEventListener(type,fn,opts));}
function close(){
 if(!P)return;
 P.token++;P.playing=false;
 try{synth()?.cancel();}catch(e){}
 cancelAnimationFrame(P.raf);clearTimeout(P.bubbleTimer);clearTimeout(P.noteTimer);clearTimeout(P.frameTimer);
 P.listeners.forEach(off=>off());
 if(P.frame){try{P.frame.src='about:blank';}catch(e){}P.frame.remove();}
 P=null;
}

/* ----------------------------------------------------------------- paint */
function paint(){
 const r=P.round,v=r.visit,name=v.patient?.name||'Patient',learn=r.mode?.key==='learn';
 view().innerHTML=`<div class="sv-shell" data-state="ready">
  <header class="sv-top">
   <button class="sv-back" type="button" data-sv="back" aria-label="Back to Scribbi">${ic('arrow','sv-flip')}<span>Scribbi</span></button>
   <div class="sv-title"><b>${E(name)} · ${E(v.title||'')}</b><span>${E(v.station_label||'')} · Demonstrated visit · ${E(r.mode?.label||'')} review</span></div>
   <button class="sb-btn sb-primary sv-skip" type="button" data-sv="skip">${skipLabel()} ${ic('arrow')}</button>
  </header>
  <div class="sv-main">
   <section class="sv-stage" aria-label="The visit with ${E(name)}">
    <div class="sv-room" id="svRoom"></div>
    <div class="sv-standin" id="svStandin" aria-hidden="true">${standin(v)}</div>
    <div class="sv-rec" aria-hidden="true"><span class="sv-dot"></span><span class="sv-rec-label">Scribbi is listening</span><span class="sv-wave"><i></i><i></i><i></i><i></i><i></i></span></div>
    <div class="sv-chapter" id="svChapter" aria-hidden="true"></div>
    <div class="sv-pip" id="svPip" hidden><div class="sv-pip-head"><span>Technique</span><b id="svPipLabel"></b></div><div class="sv-pip-canvas exam-demo-canvas" id="svPipCanvas"></div><p class="sv-pip-step" id="svPipStep"></p></div>
    <div class="sv-scribbi" id="svScribbi">${mascot('happy','is-listening')}<span class="sv-bubble" id="svBubble" hidden></span></div>
    <div class="sv-caption" id="svCaption" ${P.captions?'':'hidden'}><span class="sv-who" id="svWho"></span><p id="svLine"></p></div>
    <div class="sv-cover" id="svCover">${coverHtml()}</div>
   </section>
   <aside class="sv-side" aria-label="Visit transcript">
    <div class="sv-side-head"><h2>${ic('chat')} The visit</h2><span class="sv-heard" id="svHeard" title="Lines Scribbi has heard so far"></span></div>
    ${learn?`<label class="sv-why-toggle"><input type="checkbox" id="svWhy" ${P.why?'checked':''}> Show why each step matters</label>`:''}
    <div class="sv-why" id="svWhyBox" hidden></div>
    <ol class="sv-list" id="svList">${listHtml()}</ol>
   </aside>
  </div>
  <footer class="sv-controls" aria-label="Playback controls">
   <div class="sv-buttons">
    <button type="button" class="sv-ctl" data-sv="prev" aria-label="Previous line (J)">${ICONS.prev}</button>
    <button type="button" class="sv-ctl sv-play" data-sv="play" aria-label="Play (Space)">${ICONS.play}</button>
    <button type="button" class="sv-ctl" data-sv="next" aria-label="Next line (L)">${ICONS.next}</button>
   </div>
   <div class="sv-track"><input type="range" class="sv-scrub" id="svScrub" min="0" max="${Math.max(0,P.beats.length-1)}" step="1" value="${P.i}" aria-label="Position in the visit"><span class="sv-time" id="svTime"></span></div>
   <div class="sv-options">
    <label class="sv-speed"><span class="sr-only">Speed</span><select id="svSpeed" aria-label="Playback speed">${SPEEDS.map(s=>`<option value="${s}" ${s===P.speed?'selected':''}>${s}×</option>`).join('')}</select></label>
    <button type="button" class="sv-ctl sv-toggle" data-sv="cc" aria-pressed="${P.captions}" aria-label="Captions (C)">${ICONS.cc}</button>
    <button type="button" class="sv-ctl sv-toggle" data-sv="voice" aria-pressed="${P.voiceOn}" aria-label="Voice (M)">${ICONS.voice}</button>
   </div>
  </footer>
 </div>`;
 wire();paintAt(P.i,false);paintControls();
}
const svg=d=>`<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">${d}</svg>`;
const ICONS={
 play:svg('<path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.2-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z"/>'),
 pause:svg('<rect x="6.5" y="5" width="4" height="14" rx="1.2"/><rect x="13.5" y="5" width="4" height="14" rx="1.2"/>'),
 prev:svg('<path d="M6 5h2v14H6zM19 5.8v12.4a.8.8 0 0 1-1.24.67L9.5 13a1.2 1.2 0 0 1 0-2l8.26-5.87A.8.8 0 0 1 19 5.8z"/>'),
 next:svg('<path d="M16 5h2v14h-2zM5 5.8v12.4a.8.8 0 0 0 1.24.67L14.5 13a1.2 1.2 0 0 0 0-2L6.24 5.13A.8.8 0 0 0 5 5.8z"/>'),
 cc:svg('<path d="M4 5h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zm4.5 4A2.5 2.5 0 0 0 6 11.5v1A2.5 2.5 0 0 0 8.5 15h1.5v-1.6H8.6a1 1 0 0 1-1-1v-.8a1 1 0 0 1 1-1H10V9zm6 0A2.5 2.5 0 0 0 12 11.5v1a2.5 2.5 0 0 0 2.5 2.5H16v-1.6h-1.4a1 1 0 0 1-1-1v-.8a1 1 0 0 1 1-1H16V9z"/>'),
 voice:svg('<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4a1 1 0 0 1-1-1v-2a1 1 0 0 1 1-1z"/><path d="M15.5 8.6a4.8 4.8 0 0 1 0 6.8M18 6.2a8.2 8.2 0 0 1 0 11.6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'),
 big:svg('<path d="M9 6.4v11.2a1 1 0 0 0 1.52.86l9.07-5.6a1 1 0 0 0 0-1.72l-9.07-5.6A1 1 0 0 0 9 6.4z"/>'),
};
function standin(v){
 const initials=String(v.patient?.name||'P').split(/\s+/).map(x=>x[0]).join('').slice(0,2);
 return `<div class="sv-standin-card"><span class="sv-avatar">${E(initials)}</span><b>${E(v.patient?.name||'Patient')}</b><span class="sv-standin-note" id="svStandinNote">Bringing ${E(firstName(v.patient?.name))} into the room…</span></div>`;
}
function skipLabel(){return P.replay?'Back to the note':P.started?'Scribbi, write the note':'Skip to the note';}
function coverHtml(){
 const at=P.resumeAt?P.beats[P.resumeAt]:null,length=mmss(P.total/P.speed);
 return `<div class="sv-cover-card">
  <button type="button" class="sv-bigplay" data-sv="play" aria-label="${at?'Resume the visit':'Watch the visit'}">${ICONS.big}</button>
  <h2>${at?'Pick up where you left off':'Watch the visit'}</h2>
  <p>${at?`Resume at ${mmss(at.at/P.speed)} of about ${length}.`:`About ${length} at ${P.speed}×. Scribbi listens and writes the note, then you review it.`}</p>
  <div class="sv-cover-actions">${at?`<button type="button" class="sb-btn sb-ghost sb-sm" data-sv="restart">Start over</button>`:''}<button type="button" class="sb-btn sb-ghost sb-sm" data-sv="skip">${P.replay?'Back to the note':'Skip to the note'}</button></div>
  <p class="sv-cover-tip">${P.voiceOn?'Voices on':'Voices off'} · <kbd>Space</kbd> play or pause · <kbd>J</kbd>/<kbd>L</kbd> previous or next line</p>
 </div>`;
}
function listHtml(){
 let section=null;const name=firstName(P.round.visit.patient?.name);
 return P.beats.map(b=>{
  let head='';if(b.section&&b.section!==section){section=b.section;head=`<li class="sv-chap" aria-hidden="false">${E(section)}</li>`;}
  const who=b.who==='patient'?name:b.kind==='exam'?(b.felt?'You feel':'You examine'):b.kind==='step'?'You':'You';
  const cls=`sv-item is-${b.kind}${b.felt?' is-felt':''}`;
  const text=b.kind==='exam'?`<b>${E(b.label)}</b>${b.finding?`<span>${E(b.finding)}</span>`:''}${b.felt?`<em class="sv-tag">${ic('hand')} Felt, not said. Scribbi can’t hear this.</em>`:''}`:E(b.text);
  return `${head}<li class="${cls}" data-beat="${b.i}"><button type="button" class="sv-item-btn" data-seek="${b.i}"><span class="sv-item-who">${E(who)}</span><span class="sv-item-text">${text}</span><span class="sv-item-t">${mmss(b.at/P.speed)}</span></button></li>`;
 }).join('');
}

/* ------------------------------------------------------------------ wire */
function wire(){
 const shell=$('.sv-shell');
 shell.addEventListener('click',e=>{
  const b=e.target.closest('[data-sv]');if(b){act(b.dataset.sv);return;}
  const s=e.target.closest('[data-seek]');if(s){seek(Number(s.dataset.seek),true);}
 });
 const scrub=$('#svScrub');
 scrub.addEventListener('input',()=>{const b=P.beats[Number(scrub.value)];if(b)$('#svTime').textContent=mmss(b.at/P.speed)+' / '+mmss(P.total/P.speed);});
 scrub.addEventListener('change',()=>seek(Number(scrub.value),P.playing));
 $('#svSpeed').addEventListener('change',e=>{P.speed=Number(e.target.value)||1;savePrefs();paintAt(P.i,false);paintControls();});
 $('#svWhy')?.addEventListener('change',e=>{P.why=e.target.checked;savePrefs();paintWhy(P.beats[P.i]);});
 // Only the student's own scrolling pauses auto-follow (our smooth scroll also fires 'scroll').
 const list=$('#svList'),mine=()=>{if(P)P.userScrolledAt=performance.now();};
 for(const type of ['wheel','touchmove','pointerdown','keydown'])list.addEventListener(type,mine,{passive:true});
}
function savePrefs(){store.set('player',{speed:P.speed,captions:P.captions,voice:P.voiceOn,why:P.why});}
function act(kind){
 if(!P)return;
 if(kind==='back'){location.hash='#scribbi';return;}
 if(kind==='skip'){finish(true);return;}
 if(kind==='play'){P.playing?pause():play();return;}
 if(kind==='restart'){P.resumeAt=0;seek(0,true);return;}
 if(kind==='prev'){seek(Math.max(0,P.i-(P.playing&&P.lineStarted&&performance.now()-P.lineStarted>2500?0:1)),P.playing);return;}
 if(kind==='next'){if(P.i>=P.beats.length-1){finish(false);return;}seek(P.i+1,P.playing);return;}
 if(kind==='cc'){P.captions=!P.captions;savePrefs();$('#svCaption').hidden=!P.captions;paintControls();return;}
 if(kind==='voice'){P.voiceOn=!P.voiceOn;savePrefs();if(!P.voiceOn)try{synth()?.cancel();}catch(e){}paintControls();if(P.playing)seek(P.i,true);return;}
}
function keys(e){
 if(!P||e.defaultPrevented||e.metaKey||e.ctrlKey||e.altKey)return;
 const t=e.target;if(t&&(t.isContentEditable||/^(?:INPUT|TEXTAREA|SELECT)$/.test(t.tagName))&&!(t.type==='range'&&e.key===' '))return;
 const k=e.key.toLowerCase();
 if((k===' '||k==='enter')&&t?.closest?.('button,a,summary'))return;
 if(k===' '||k==='k'){e.preventDefault();act('play');}
 else if(k==='j'||k==='arrowleft'&&t?.type!=='range'){e.preventDefault();act('prev');}
 else if(k==='l'||k==='arrowright'&&t?.type!=='range'){e.preventDefault();act('next');}
 else if(k==='c'){act('cc');}
 else if(k==='m'){act('voice');}
}

/* -------------------------------------------------------------- playback */
function play(){
 if(!P||P.ended)return;
 P.playing=true;P.started=true;P.resumeAt=0;
 $('#svCover')?.classList.add('is-gone');
 $('.sv-shell')?.setAttribute('data-state','playing');
 paintControls();
 run();
}
function pause(){
 if(!P)return;
 P.playing=false;P.token++;
 try{synth()?.cancel();}catch(e){}
 cancelAnimationFrame(P.raf);
 setSpeaking(null);
 $('.sv-shell')?.setAttribute('data-state','paused');
 paintControls();
}
function seek(i,keepPlaying){
 if(!P)return;
 i=clamp(i,0,P.beats.length-1);
 P.token++;try{synth()?.cancel();}catch(e){}cancelAnimationFrame(P.raf);setSpeaking(null);
 P.i=i;store.set('visitpos.'+P.id,i);
 paintAt(i,true);
 if(keepPlaying){P.playing=true;$('#svCover')?.classList.add('is-gone');run();}
 else{P.playing=false;paintControls();}
}
async function run(){
 const token=++P.token;
 paintControls();
 while(P&&P.playing&&token===P.token&&P.i<P.beats.length){
  await playBeat(P.beats[P.i],token);
  if(!P||token!==P.token||!P.playing)return;
  if(P.i>=P.beats.length-1){finish(false);return;}
  P.i++;store.set('visitpos.'+P.id,P.i);
 }
}
function wait(ms,token){return new Promise(resolve=>{const t=setTimeout(resolve,ms);const check=setInterval(()=>{if(!P||token!==P.token){clearTimeout(t);clearInterval(check);resolve();}},120);setTimeout(()=>clearInterval(check),ms+50);});}
async function playBeat(b,token){
 paintAt(b.i,true);
 P.lineStarted=performance.now();
 setPosture(b.posture,b);
 if(b.kind==='step'){setCaption('action',b.text,false);await wait(1800/P.speed,token);return;}
 if(b.kind==='exam'){await playExam(b,token);return;}
 if(b.kind==='reply')P.lastReply=b.text;
 await speak(b.text,b.who==='patient'?'patient':'clinician',token);
 if(P&&token===P.token&&b.kind==='reply')scribbiNoted();
 await wait(240/P.speed,token);
}
async function playExam(b,token){
 setBusy(true);
 room('FocusRegion',focusRegion(b));
 room('ShowExam',{region:focusRegion(b),maneuver_id:b.maneuver,components:b.components,duration:3});
 showPip(b);
 await animatePip(b,token);
 if(!P||token!==P.token){hidePip();setBusy(false);return;}
 if(b.felt){
  scribbiSays('I can’t hear palpation. That finding won’t be in my note.',Math.max(3200,estimate(b.finding)*900)/P.speed);
  setCaption('you','You feel: '+b.finding,true);
  await wait(Math.max(3200,estimate(b.finding)*1000)/P.speed,token);
 }else if(b.finding){
  setCaption('you',b.finding,false);
  await speak(b.finding,'clinician',token,true);
  if(P&&token===P.token)scribbiNoted();
 }
 hidePip();setBusy(false);camera('patient');
}
function focusRegion(b){
 const r=b.region||'';
 if(/HEENT|Neck|Head/i.test(r))return 'HEENT';
 if(/Abdomen|GI/i.test(r))return 'Abdomen';
 // The structural screen is thoracic and lumbar: frame the trunk, not the lap.
 if(/Osteo|Skin/i.test(r))return 'General';
 if(/Musculo|MSK|Extrem/i.test(r))return 'MSK';
 if(/Heart|Cardio/i.test(r))return 'Heart';
 if(/Lung|Chest|Resp/i.test(r))return 'Lungs';
 if(/Neuro/i.test(r))return 'Neurologic';
 return 'General';
}

/* ----------------------------------------------------------------- speech */
function speak(text,who,token,captionSet){
 return new Promise(resolve=>{
  if(!P||token!==P.token)return resolve();
  if(!captionSet)setCaption(who==='patient'?'patient':'you',text,false);
  const s=synth(),voices=P.voices;
  const timed=()=>{setSpeaking(who);wait(estimate(text)*1000/P.speed,token).then(()=>{if(P&&token===P.token)setSpeaking(null);resolve();});};
  if(!P.voiceOn||!s||!voices){timed();return;}
  const list=chunks(text);let k=0,watchdog=0;
  const next=()=>{
   clearTimeout(watchdog);
   if(!P||token!==P.token){resolve();return;}
   if(k>=list.length){setSpeaking(null);resolve();return;}
   const part=list[k++],u=new SpeechSynthesisUtterance(part);
   const v=who==='patient'?voices.patient:voices.clinician;
   if(v){u.voice=v;u.lang=v.lang;}
   const base=who==='patient'?(PACE[P.pb?.demeanor?.pace]||.97):1;
   u.rate=clamp(base*P.speed,.5,2.4);
   u.pitch=voices.same?(who==='patient'?1.12:.9):1;
   // Whichever comes first wins: the end, an error, or the watchdog.
   let settled=false;const settle=fn=>{if(settled)return;settled=true;clearTimeout(watchdog);fn();};
   const timedRest=()=>{const rest=list.slice(k-1).join(' ');setSpeaking(who);wait(estimate(rest)*1000/P.speed,token).then(()=>{if(P&&token===P.token)setSpeaking(null);resolve();});};
   u.onstart=()=>setSpeaking(who);
   u.onend=()=>settle(next);
   u.onerror=e=>settle(()=>{
    if(e.error==='interrupted'||e.error==='canceled'){resolve();return;}
    if(e.error==='not-allowed'){P.voiceOn=false;paintControls();}
    timedRest();
   });
   // A browser that never reports the end must not stall the visit.
   watchdog=setTimeout(()=>settle(()=>{try{s.cancel();}catch(e){}setTimeout(next,90);}),(estimate(part)*1000/Math.max(.5,P.speed))*2.2+2500);
   try{s.speak(u);}catch(e){settle(timedRest);}
  };
  if(s.speaking||s.pending){try{s.cancel();}catch(e){}setTimeout(next,90);}else next();
 });
}
function setSpeaking(who){
 if(!P)return;
 P.speaking=who;
 const shell=$('.sv-shell');if(shell)shell.dataset.speaking=who||'';
 $('#svScribbi .sb-mascot')?.classList.toggle('is-listening',true);
 roomState();
}

/* ------------------------------------------------------------- stage bits */
function setCaption(who,text,felt){
 const name=firstName(P.round.visit.patient?.name);
 const w=$('#svWho'),l=$('#svLine'),c=$('#svCaption');if(!w||!l)return;
 w.textContent=who==='patient'?name:who==='action'?'Action':'You';
 w.className='sv-who is-'+(who==='patient'?'patient':who==='action'?'action':'you')+(felt?' is-felt':'');
 l.textContent=text;
 c.classList.remove('is-new');void c.offsetWidth;c.classList.add('is-new');
 c.classList.toggle('is-felt',!!felt);
}
function scribbiNoted(){
 const m=$('#svScribbi .sb-mascot');if(!m||reduced())return;
 m.classList.remove('is-writing');void m.getBoundingClientRect();m.classList.add('is-writing');
 clearTimeout(P.noteTimer);P.noteTimer=setTimeout(()=>m.classList.remove('is-writing'),900);
 paintHeard();
}
function scribbiSays(text,ms){
 const b=$('#svBubble'),m=$('#svScribbi .sb-mascot');if(!b)return;
 b.textContent=text;b.hidden=false;m?.classList.add('mood-oops');m?.classList.remove('mood-happy');
 clearTimeout(P.bubbleTimer);P.bubbleTimer=setTimeout(()=>{if(!P)return;b.hidden=true;m?.classList.remove('mood-oops');m?.classList.add('mood-happy');},ms||3200);
}
function showPip(b){
 const pip=$('#svPip');if(!pip)return;
 $('#svPipLabel').textContent=b.label;
 $('#svPipStep').textContent=b.plan?.position||'';
 pip.hidden=false;pip.classList.toggle('is-felt',b.felt);
 setCaption('you',(b.felt?'You palpate: ':'You examine: ')+b.label,b.felt);
}
function hidePip(){const pip=$('#svPip');if(pip)pip.hidden=true;cancelAnimationFrame(P?.raf);}
function animatePip(b,token){
 return new Promise(resolve=>{
  const canvas=$('#svPipCanvas'),plan=b.plan,A=window.PCMExamAnimation;
  const seconds=examSeconds(b)/P.speed;
  if(!plan||!A||!canvas||!plan.steps?.length){if(canvas)canvas.innerHTML=`<div class="sv-pip-icon">${ic(b.felt?'hand':'stethoscope')}</div>`;wait(seconds*1000,token).then(resolve);return;}
  const focus=/hand/.test(P.round.case_id)?'hand':/shoulder/.test(P.round.case_id)?'torso':/knee/.test(P.round.case_id)?'joint':/skin/.test(P.round.case_id)?'arm':'back';
  const start=performance.now(),stepEl=$('#svPipStep');let lastStep=-1;
  const frame=stamp=>{
   if(!P||token!==P.token){resolve();return;}
   const u=clamp((stamp-start)/(seconds*1000),0,1);
   try{
    const f=reduced()?A.frame(plan,plan.steps.slice(0,Math.min(plan.steps.length-1,Math.floor(u*plan.steps.length))).reduce((a,x)=>a+x.seconds,0)+.5,focus):A.frame(plan,u*plan.duration_s,focus);
    if(!reduced()||f.index!==lastStep)canvas.innerHTML=f.svg;
    if(f.index!==lastStep){lastStep=f.index;if(stepEl)stepEl.textContent=f.caption||'';}
   }catch(e){canvas.innerHTML=`<div class="sv-pip-icon">${ic('stethoscope')}</div>`;}
   if(u>=1){resolve();return;}
   P.raf=requestAnimationFrame(frame);
  };
  P.raf=requestAnimationFrame(frame);
 });
}
function paintAt(i,scroll){
 if(!P)return;
 const b=P.beats[i];if(!b)return;
 $$('#svList .sv-item.is-now').forEach(x=>x.classList.remove('is-now'));
 const item=$(`#svList .sv-item[data-beat="${i}"]`);
 if(item){item.classList.add('is-now');$$('#svList .sv-item').forEach(x=>x.classList.toggle('is-past',Number(x.dataset.beat)<i));
  if(scroll&&performance.now()-P.userScrolledAt>4000){const list=$('#svList');const top=item.offsetTop-list.clientHeight*.34;list.scrollTo({top:Math.max(0,top),behavior:reduced()?'auto':'smooth'});}}
 const chapter=$('#svChapter');if(chapter){chapter.textContent=b.section||'';chapter.hidden=!b.section;}
 if(b.kind!=='exam')hidePip();
 if(!P.playing&&b.kind!=='exam')setCaption(b.who==='patient'?'patient':b.kind==='step'?'action':'you',b.text,false);
 if(!P.playing&&b.kind==='exam')setCaption('you',(b.felt?'You palpate: ':'You examine: ')+b.label,b.felt);
 const scrub=$('#svScrub');if(scrub)scrub.value=String(i);
 const time=$('#svTime');if(time)time.textContent=mmss(b.at/P.speed)+' / '+mmss(P.total/P.speed);
 paintHeard();paintWhy(b);
}
function paintHeard(){
 const el=$('#svHeard');if(!el||!P)return;
 const n=P.beats.slice(0,P.i+(P.playing?0:0)).filter(b=>b.kind==='reply'||(b.kind==='exam'&&!b.felt&&b.finding)).length;
 el.innerHTML=`${ic('pen')} Scribbi heard <b>${n}</b> ${n===1?'thing':'things'}`;
}
function paintWhy(b){
 const box=$('#svWhyBox');if(!box)return;
 const show=P.why&&P.round.mode?.key==='learn'&&b?.why;
 box.hidden=!show;if(show)box.innerHTML=`<b>Why this step matters</b><p>${E(b.why)}</p>`;
}
function paintControls(){
 if(!P)return;
 const play=$('.sv-play');if(play){play.innerHTML=P.playing?ICONS.pause:ICONS.play;play.setAttribute('aria-label',P.playing?'Pause (Space)':'Play (Space)');}
 const cc=$('[data-sv="cc"]');cc?.setAttribute('aria-pressed',String(P.captions));
 const voice=$('[data-sv="voice"]');if(voice){voice.setAttribute('aria-pressed',String(P.voiceOn));voice.classList.toggle('is-off',!P.voiceOn);voice.title=!synth()?'This browser cannot speak; captions only':P.voices?'':'No English voice found; captions only';}
 const skip=$('.sv-skip');if(skip)skip.innerHTML=skipLabel()+' '+ic('arrow');
}

/* ------------------------------------------------------------------ room */
function mountRoom(){
 const host=$('#svRoom');if(!host)return;
 window.pcmReleaseRoomFrame?.();
 const frame=document.createElement('iframe');
 frame.className='sv-frame';frame.title='The patient';frame.setAttribute('aria-hidden','true');frame.tabIndex=-1;
 frame.src=ROOM_URL+'&viewer=1&env=studio';
 host.append(frame);P.frame=frame;
 P.frameTimer=setTimeout(()=>{if(P&&!P.patientReady){const n=$('#svStandinNote');if(n)n.textContent='The 3D room is taking a while. The visit plays fine with voices and captions.';}},20000);
}
function roomMessage(e){
 if(!P||!P.frame||e.source!==P.frame.contentWindow||e.origin!==location.origin)return;
 const d=e.data||{};
 if(d.type==='pcm-unity-ready'||d.type==='pcm-room-ready'){P.frameReady=true;roomState();}
 if(d.type==='pcm-patient-status'&&d.sessionId===sessionId()){
  if(d.status==='ready'){P.patientReady=true;P.cameraPreset=null;$('#svStandin')?.classList.add('is-gone');$('.sv-stage')?.classList.add('has-room');camera('patient');}
  if(['failed','error','limited'].includes(d.status)){const n=$('#svStandinNote');if(n)n.textContent='The 3D patient is unavailable here. The visit plays with voices and captions.';}
 }
 if(d.type==='pcm-unity-error'&&!P.patientReady){const n=$('#svStandinNote');if(n)n.textContent='The 3D room is unavailable in this browser. The visit plays with voices and captions.';}
}
function sessionId(){return 'scribbi-'+P.id;}
function setPosture(posture,b){
 if(!P)return;
 const changed=posture&&posture!==P.posture;
 if(posture)P.posture=posture;
 if(b?.affect)P.affect=b.affect;
 if(b?.gesture)P.gesture=b.gesture;
 if(changed||b?.affect||b?.gesture)roomState();
}
function setBusy(on){if(!P)return;P.busy=on;roomState();}
function roomState(){
 if(!P?.frame?.contentWindow||!P.frameReady)return;
 const pb=P.pb||{},v=P.round.visit;
 const state={sessionId:sessionId(),caseId:P.round.case_id,phase:'encounter',mode:'independent',eventSeq:++P.seq,
  patientName:v.patient?.name||'',posture:P.posture||'seated',speaking:P.speaking==='patient',listening:P.speaking==='clinician',
  patientReply:P.lastReply||'',appearance:pb.appearance||{},affect:P.affect||pb.affect||{},gesture:P.gesture||pb.gesture||{},
  demeanor:pb.demeanor||{},respiratoryRate:pb.respiratory_rate||16,busyMs:P.busy?4000:0,reducedMotion:reduced(),assisted:true};
 try{P.frame.contentWindow.postMessage({type:'pcm-unity-state',state},location.origin);}catch(e){}
}
function room(command,payload){
 if(!P?.frame?.contentWindow||!P.patientReady)return;
 try{P.frame.contentWindow.postMessage({type:'pcm-room-command',command,payload},location.origin);}catch(e){}
}
function camera(preset){if(!P||P.cameraPreset===preset)return;P.cameraPreset=preset;room('SetView',preset);}

/* ---------------------------------------------------------------- finish */
async function finish(skipped){
 if(!P||P.finishing)return;
 P.finishing=true;P.ended=true;P.token++;P.playing=false;
 try{synth()?.cancel();}catch(e){}
 setSpeaking(null);hidePip();
 const id=P.id,cover=$('#svCover');
 if(P.replay){store.set('visitpos.'+id,P.i);location.hash='#scribbi/r/'+id;return;}
 if(cover){cover.classList.remove('is-gone');cover.innerHTML=`<div class="sv-cover-card is-end">${mascot('happy','is-writing is-listening')}<h2>${skipped?'Scribbi is writing the note…':'That’s the visit. Scribbi is writing the note…'}</h2><p>From everything it heard. Not what you felt.</p></div>`;}
 $('.sv-shell')?.setAttribute('data-state','ended');
 const r=await call('/api/scribbi/rounds/'+encodeURIComponent(id)+'/begin',{});
 if(!P||P.id!==id)return;
 if(r?.error&&!/signed/i.test(r.error)){P.finishing=false;P.ended=false;if(typeof toast==='function')toast(r.message||r.error);return;}
 store.del('visitpos.'+id);
 store.set('fresh',id);
 setTimeout(()=>{if(P&&P.id===id)location.hash='#scribbi/r/'+id;},reduced()?0:skipped?500:1100);
}

window.pcmScribbiVisit={open,close,buildBeats,pickVoices,chunks,estimate};
})();
