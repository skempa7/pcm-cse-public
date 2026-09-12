/* PCM CSE — local served edition, front end.

   Six stages over one engine: lobby → doorway → patient room (with the
   examination surface and voice) → organization interval → SOAP workstation →
   debrief. The engine is the Python package behind server.py; this file only
   calls its JSON routes and renders what they return. It shares the design
   system and the stage structure of the browser edition (webapp/ui.js) so the
   two editions look and behave alike.

   Three rules shape almost every decision below:
     * timing is server-authoritative. The page interpolates between polls using
       a measured clock offset, so a refresh, a slow tab or a second window
       never changes the exam.
     * exam mode never leaks. No hidden diagnosis, no checklist and no "you
       missed X" prompt reaches the screen before the note is submitted.
     * nothing is claimed that the engine did not measure. Where this file adds
       an affordance the engine does not model (instrument choice, the drill
       lenses), it says so on the surface that offers it, and a save the server
       refused is never reported as "Saved."
*/
'use strict';

const $  = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.prototype.slice.call((r || document).querySelectorAll(s));

const view = $('#view'), clockEl = $('#clock'), clockDigits = $('#clockDigits'),
      clockLabel = $('#clockLabel'), chipEl = $('#phaseChip'), homeBtn = $('#btnHome'),
      liveRegion = $('#liveRegion'), alertRegion = $('#alertRegion'),
      overlayRoot = $('#overlayRoot'), brandSub = $('#brandSub');

const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');
const mmss = ms => { if (ms == null) return '--:--';
  const t = Math.max(0, Math.round(ms / 1000));
  return Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'); };
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
const isUntimedAttempt = (attempt=S) => !!attempt && (attempt.preset?.untimed === true || attempt.learning_mode === 'guided');
const phaseAllowance = seconds => mmss(Number(seconds || 0) * 1000);

let feedbackEpoch=0,announceTimer=null,alertTimer=null;
function clearContextFeedback(){
  feedbackEpoch++;clearTimeout(announceTimer);clearTimeout(alertTimer);
  if(liveRegion)liveRegion.textContent='';if(alertRegion)alertRegion.textContent='';
  $('.toast')?.remove();
}
function announce(msg) { if(liveRegion){
  const epoch=feedbackEpoch;clearTimeout(announceTimer);liveRegion.textContent='';
  announceTimer=setTimeout(()=>{if(epoch===feedbackEpoch)liveRegion.textContent=msg;},30);
} }
function alertNow(msg) { if(alertRegion){
  const epoch=feedbackEpoch;clearTimeout(alertTimer);alertRegion.textContent='';
  alertTimer=setTimeout(()=>{if(epoch===feedbackEpoch)alertRegion.textContent=msg;},30);
} }
let toastTimer = null;
function toast(msg) {
  let t = $('.toast');
  if (!t) { t = document.createElement('div'); t.className = 'toast'; document.body.appendChild(t); }
  t.textContent = msg; clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { if (t.parentNode) t.parentNode.removeChild(t); }, 3200);
  announce(msg);
}

/* ---------- storage (returns whether it actually stored) ---------- */
const LS = {
  get(k){ try { return JSON.parse(localStorage.getItem('pcmcse.' + k)); } catch(e){ return null; } },
  remove(k){try{localStorage.removeItem('pcmcse.'+k);return true;}catch(e){return false;}},
  set(k, v){ try { localStorage.setItem('pcmcse.' + k, JSON.stringify(v)); return true; }
             catch(e){ return false; } }
};

function setTheme(theme){document.documentElement.dataset.theme=theme==='night'?'night':'day';LS.set('theme',document.documentElement.dataset.theme);const b=$('#themeToggle');if(b){b.textContent=theme==='night'?'Daylight':'Evening';b.setAttribute('aria-label',theme==='night'?'Use daylight appearance':'Use evening appearance');}}
setTheme(LS.get('theme')||'day');$('#themeToggle').onclick=()=>setTheme(document.documentElement.dataset.theme==='night'?'day':'night');

function keepDraft(kind,sid,value){return LS.set('draft.'+kind+'.'+sid,{value,at:Date.now()});}
function draftValue(kind,sid){return LS.get('draft.'+kind+'.'+sid)?.value;}
function clearMatchingDraft(kind,sid,value){if(JSON.stringify(draftValue(kind,sid))===JSON.stringify(value))LS.remove('draft.'+kind+'.'+sid);}
let scratchSaveTimer=null,scratchWrite=Promise.resolve(),scratchNeedsSave=false,scratchProtected=true;
function scratchMessage(text){const el=$('#scratchStatus');if(el)el.textContent=text;}
function saveScratch(sid,value){
  const work=async()=>{const r=await api(`/api/session/${sid}/scratch`,{scratch:value});if(r.saved){if(S?.id===sid&&$('#scratch')?.value===value)scratchNeedsSave=false;clearMatchingDraft('scratch',sid,value);if(S?.id===sid&&draftValue('scratch',sid)===undefined)scratchMessage('Saved to this attempt.');}else if(S?.id===sid)scratchMessage('Saved in this browser for recovery; waiting to save to browser storage.');return r;};
  scratchWrite=scratchWrite.then(work,work);return scratchWrite;
}
function recoverScratch(){if(!S)return;const pending=draftValue('scratch',S.id);if(typeof pending==='string'){S.scratch=pending;if(['organize','note'].includes(S.phase))saveScratch(S.id,pending);}}

/* ---------- app state ---------- */
let BOOT = null, S = null, skew = 0, tick = null, poll = null, lastPhase = null;
let RESULTS = null, activeTab = 'lessons', tlFocus = null;
let noteSaveTimer = null, noteSave = { state:'idle', at:null, reason:'' };
let overlay = null, lastFocus = null, netDown = false;
/* Findings held back while an examination occupies its time. They belong to one
   session and one phase; leaving either drops them, because the ledger already
   has them and the debrief will show them there. */
let pendingReveals = [];
function clearPendingReveals(){
  pendingReveals.forEach(h => clearTimeout(h));
  pendingReveals = [];
}

let room = { view:'front', region:null, instrument:'', position:'seated',
             running:null, runTimer:null, runEnd:null, performed:{} };
let voice = { rec:null, listening:false, hands_free:false, speak:true, supported:false,
              muteUntil:0, failed:false, pending:null,
              // ONE finalized utterance must produce ONE message. `lastFinal`
              // is the highest final result index already submitted in the
              // CURRENT recognition session; a continuous session keeps
              // delivering the whole results array, so without a watermark an
              // earlier final is resubmitted every time a later one arrives.
              lastFinal:-1,
              // True from just before the patient becomes audible until just
              // after. Audio captured in this window is the app's own voice.
              suppressed:false,
              // Secondary defence only: identical text within a moment is a
              // duplicate event, not a deliberate repeat.
              lastSentText:'', lastSentAt:0 };

/* ---------- api ---------- */
async function api(path, body) {
  const t0 = Date.now(), requestEpoch=feedbackEpoch;
  let res, data;
  try {
    res = await fetch(path, body === undefined ? { cache:'no-store' } : {
      method:'POST', headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify(body)
    });
    data = await res.json();
  } catch (e) {
    if(requestEpoch===feedbackEpoch)setNetDown(true);
    return { error:'offline',
             message:e.message || 'The local engine is unavailable. Close other app tabs, then reload. Copy any unsaved note first.' };
  }
  if(requestEpoch===feedbackEpoch)setNetDown(false);
  // One measured clock offset, applied to every timer face on the page.
  const mid = t0 + (Date.now() - t0) / 2;
  if (data && data.server_now) skew = data.server_now - mid;
  else if (data && data.state && data.state.server_now) skew = data.state.server_now - mid;
  return data || {};
}
const post = (path, body) => api(path, body || {});
const now = () => Date.now() + skew;

function setNetDown(down) {
  if (down === netDown) return;
  netDown = down;
  paintNetBar();
  if (down) alertNow('Lost contact with the local engine. Typing is still recorded ' +
                     'locally, but nothing is saved until it returns.');
  else alertNow('Connection restored. Your local drafts remain available.');
}
function paintNetBar() {
  let bar = $('#netbar');
  if (!netDown) { if (bar) bar.remove(); return; }
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'netbar'; bar.className = 'netbar'; bar.setAttribute('role', 'status');
    view.insertBefore(bar, view.firstChild);
  }
  bar.textContent = 'The local engine is unavailable. Close other app tabs, then reload. Copy any unsaved note first. Previously saved attempts remain in this browser.';
}

/* ---------- stations: the number is the station's own, never the array index --
   The bootstrap case index does not publish hidden_label, so the label is
   learned from the doorway (which does publish it) and cached, seeded with the
   labels of the cases that ship with the app. A station whose own label is not
   known is never given an invented number — it says so instead. */
const STATION_SEED = {
  'renal-flank-pain': 'Station 1',
  'cardio-chest-pressure': 'Station 2',
  'gi-epigastric-melena': 'Station 3',
  'neuro-thunderclap-headache': 'Station 4'
};
function stationLabels() {
  return Object.assign({}, STATION_SEED, LS.get('station_labels') || {});
}
function learnStationLabel(caseId, label) {
  if (!caseId || !label) return;
  const map = LS.get('station_labels') || {};
  if (map[caseId] === label) return;
  map[caseId] = label; LS.set('station_labels', map);
}
function stationLabel(caseId) { return (BOOT?.cases||[]).find(c=>c.id===caseId)?.station_label || stationLabels()[caseId] || null; }
function stationNo(caseId) {
  const m = /(\d+)/.exec(stationLabel(caseId) || '');
  return m ? parseInt(m[1], 10) : 9999;
}
function stationTitle(caseId) { return stationLabel(caseId) || 'Station (number shown at the doorway)'; }
function caseById(id) { return (BOOT.cases || []).filter(c => c.id === id)[0]; }
function caseTitleOf(id) { const c = caseById(id); return c ? c.title : id; }
function stations() {
  return (BOOT.cases || []).slice().sort((a, b) =>
    stationNo(a.id) - stationNo(b.id) || a.id.localeCompare(b.id));
}

/* ---------- modes and drills ----------
   The server stores the timing preset; the lens a station was run through is a
   front-end framing, so it is kept beside the session id in this browser and
   never presented as something the engine scored. */
const MODES = {
  guided:{key:'guided',name:'Guided encounter',icon:'☀',preset:'guided_untimed',time:'Untimed encounter and SOAP note',desc:'Build a repeatable approach with memory cues, demonstrations and immediate practice.',reveal:true,coach:true},
  coached:{key:'coached',name:'Coached encounter',icon:'◐',preset:'coached_untimed',time:'Untimed encounter and SOAP note',desc:'Lead at your own pace, with targeted help whenever you need it. Assistance is tracked separately.',reveal:true,coach:true},
  independent:{key:'independent',name:'Independent practice',icon:'◇',preset:'independent_extended',time:'30 min encounter → 5 min organize → 20 min note',desc:'Complete the encounter yourself with extended practice time, then reflect on the evidence-based feedback.',reveal:true,coach:false},
  rehearsal:{key:'rehearsal',name:'Exam rehearsal',icon:'◆',preset:'course',time:'14 min encounter → 9 min note',desc:'Course timing, sealed case titles and no teaching help during the encounter or SOAP period.',reveal:false,coach:false}
};
function normalizeMode(value){return value==='practice'||value==='drill'?'coached':(MODES[value]?value:'coached');}
const DRILLS = {
  summary: { key:'summary', name:'Summaries',
    goal:'Summarize what you heard back to the patient, with at least three items, and ask them to verify it.',
    measure:'ACIR item 5 and relationship item 14 (summary of at least three items).' },
  focused_exam: { key:'focused_exam', name:'Focused examination',
    goal:'Cover the region the complaint points at, with the technique components named, before the clock runs out.',
    measure:'the case checklist’s physical examination items and the examinations you left incomplete.' },
  safety_net: { key:'safety_net', name:'Safety-netting and closure',
    goal:'Close by saying what you will do, what the patient should do, and when you will see them again.',
    measure:'relationship item 15 (closure) and the closure signals the engine records.' },
  documentation: { key:'documentation', name:'Documentation accuracy',
    goal:'Write only what your own encounter produced — no normals you did not examine, nothing in the wrong section.',
    measure:'the claim-by-claim documentation audit.' }
};
function uiMeta(sid) { return (sid && LS.get('ui.' + sid)) || {}; }
function setUiMeta(sid, meta) { if (sid) LS.set('ui.' + sid, meta); }
function mode() {
  const m = S ? (S.learning_mode || uiMeta(S.id).ui_mode) : (LS.get('prefs') || {}).ui_mode;
  return MODES[normalizeMode(m)];
}
function drillOf() {
  const d = S ? uiMeta(S.id).drill : null;
  return d ? DRILLS[d] : null;
}

/* ---------- one timer, many faces ---------- */
function startTick(){ if (tick) clearInterval(tick); tick = setInterval(paintClock, 250); paintClock(); }
function paintClock(){
  if (!S) { clockEl.classList.add('hidden'); return; }
  if(!S.phase_ends_at){if(['briefing','submitted'].includes(S.phase)){clockEl.classList.add('hidden');return;}clockEl.classList.remove('hidden');clockDigits.textContent='Untimed';clockLabel.textContent=S.learning_mode==='guided'?'guided learning':'coached practice';clockEl.setAttribute('aria-label','Untimed '+clockLabel.textContent);clockEl.classList.remove('warn','crit');$$('[data-clock]').forEach(el=>el.textContent='Untimed');return;}
  const left = S.phase_ends_at - now();
  clockEl.classList.remove('hidden');
  const txt = mmss(left);
  clockDigits.textContent = txt;
  clockLabel.textContent = { encounter:'encounter', organize:'organize', note:'note' }[S.phase] || 'remaining';
  clockEl.classList.toggle('warn', left <= 120000 && left > 30000);
  clockEl.classList.toggle('crit', left <= 30000);
  clockEl.setAttribute('aria-label', txt + ' remaining in the ' + clockLabel.textContent + ' phase');
  // Every other clock face on the page reads this same value, so no title,
  // header or panel can freeze while another keeps counting.
  $$('[data-clock]').forEach(el => { el.textContent = txt; });
  $$('[data-clock-pct]').forEach(el => {
    const total = (S.phase_duration_s || 0) * 1000;
    const pct = total ? clamp(100 * (1 - left / total), 0, 100) : 0;
    const bar = el.firstElementChild; if (bar) bar.style.width = pct.toFixed(1) + '%';
  });
  if (left <= 0) { clearInterval(tick); tick = null; refresh(); }
}
function paintChip(){
  const map = { briefing:['Doorway',''], encounter:['In the room','enc'],
    organize:['Organization interval','org'], note:['SOAP note','note'],
    submitted:['Debrief','done'] };
  const pair = map[S.phase] || ['', ''];
  chipEl.className = 'phase-chip ' + pair[1]; chipEl.textContent = pair[0];
  chipEl.classList.remove('hidden'); homeBtn.classList.remove('hidden');
  if (brandSub) brandSub.textContent = stationTitle(S.case_id) + ' · ' + mode().name;
}
function renderPhase(force){
  if (!S) return;
  document.body.dataset.phase=S.phase;entryPending=null;
  paintChip();
  if (S.phase !== lastPhase || force) {
    clearContextFeedback();
    lastPhase = S.phase;
    closeOverlay(true);
    ({ briefing:renderDoorway, encounter:renderRoom, organize:renderOrganize,
       note:renderNote, submitted:renderDebrief }[S.phase] || renderLobby)();
    paintNetBar();window.scrollTo({top:0,behavior:'instant'});positionRoomFrame();
    // Move focus to the view ONLY if the phase renderer did not place it
    // somewhere better. renderNote focuses the Subjective box and renderOrganize
    // the scratch pad; this line ran immediately afterwards and took it back, so
    // the student arrived at the note -- with the clock already running in exam
    // rehearsal -- and had to click before they could type.
    const placed = document.activeElement
      && document.activeElement !== document.body
      && document.activeElement !== view;
    if (!placed) { try { view.focus({ preventScroll:true }); } catch(e) { try { view.focus(); } catch(e2){} } }
  }
  startTick(); notifyPublicState();
  window.pcmLearningRender?.(S);
}

/* ---------- session plumbing ---------- */
let routeEpoch=0;
async function leaveForWorkspace(kind){
  const active=S&&S.phase!=='submitted';
  if(active){
    const timed=!!S.phase_ends_at;
    const message='Leave this attempt for '+({home:'Home',practice:'the case library',progress:'your progress',scoring:'the scoring guide',voice:'voice settings',session:'another attempt'}[kind]||'this workspace')+'? Your work will be saved and you can resume from Home or Progress.'+(timed?' The current timer keeps running; leaving does not add time.':' This attempt remains untimed.');
    if(!await confirmChoice(message,{title:'Leave this attempt?',confirm:'Leave attempt',cancel:'Stay here'})){history.replaceState(null,'','#/'+S.id);return false;}
  }
  if(!await window.pcmEnterWorkbench(kind))return false;
  clearContextFeedback();return true;
}
function portalContext(){return {boot:BOOT,view,api,onData:data=>Object.assign(BOOT,data),past:panelPast,scoring:panelAssume,wirePast:wirePastPanel};}
async function route(){
  const epoch=++routeEpoch,id=location.hash.replace(/^#\/?/, '');
  window.pcmPortal?.invalidate();
  if (/^learn(?:\/|$)/.test(id)) {document.body.dataset.workspace='learn';window.pcmStudy.render(id);return;}
  const kind=!id||id==='home'?'home':['practice','progress','scoring'].includes(id)?id:null;
  if(kind){
    if(!await leaveForWorkspace(kind)||epoch!==routeEpoch)return;
    document.body.dataset.workspace=kind;window.pcmPortal?.nav(kind);
    if(brandSub)brandSub.textContent='Your clinical skills workspace';
    if(kind==='practice')renderLobby();else window.pcmPortal.render(kind,portalContext());
    return;
  }
  if(S?.id&&S.id!==id&&(!await leaveForWorkspace('session')||epoch!==routeEpoch))return;
  document.body.dataset.workspace='encounter';openSession(id,epoch);
}
async function openSession(id,epoch=routeEpoch){
  document.querySelectorAll('[data-destination]').forEach(b=>b.setAttribute('aria-current',b.dataset.destination==='practice'?'page':'false'));
  const st = await api('/api/session/' + id);
  if(epoch!==routeEpoch)return;
  if (st.error || !st.phase) { location.hash = ''; return renderLobby(); }
  clearPendingReveals();
  S = st;recoverScratch();lastPhase = null;
  room = { view:'front', region:null, instrument:'', position:'seated',
           running:null, runTimer:null, runEnd:null,
           performed: (LS.get('performed.' + id) || {}) };
  startPolling(); renderPhase(true);
}
function startPolling(){ if (poll) clearInterval(poll); poll = setInterval(refresh, 1200); }
async function refresh(){
  if (!S) return;
  const sid = S.id;
  const st = await api('/api/session/' + sid);
  if (!S || S.id !== sid || st.error || !st.phase) return;
  const changed = st.phase !== S.phase;
  if(changed&&S.phase==='organize'){const scratch=$('#scratch')?.value ?? draftValue('scratch',sid) ?? S.scratch ?? '';keepDraft('scratch',sid,scratch);const saved=await saveScratch(sid,scratch);st.scratch=scratch;}
  const wasExamPending=!!S.pending_exam;
  const previousTranscript = JSON.stringify(S.transcript || []);
  const draft = S.note;                      // never let a poll clobber typing
  S = st;
  if (changed) {
    if (S.phase !== 'encounter') { stopVoice(); cancelRunningExam(); clearPendingReveals(); }
    renderPhase(true);
  } else if (S.phase === 'note') { S.note = draft; }
  else if (S.phase === 'encounter') {
    if(previousTranscript!==JSON.stringify(S.transcript||[])){paintStream(S.transcript||[]);paintRapport();paintExamProgress();}
    if(!S.pending_exam){if(!voice.patientSpeaking&&!window.pcmAISpeaking)setPatientState(window.pcmNaturalBusy?'preparing':window.pcmAIThinking?'thinking':patientIsListening()?'listening':'idle');const body=overlay?$('#ovBody',overlay):null;if(body){lockManeuverButtons(body,false);if(wasExamPending)paintManList(body);const running=$('#examRunning',body);if(running)running.innerHTML='';}}
  }
  notifyPublicState();
}

/* ======================================================================== */
/* 1. LOBBY                                                                  */
/* ======================================================================== */
function renderLobby(){
  document.querySelectorAll('[data-destination]').forEach(b=>b.setAttribute('aria-current',b.dataset.destination==='practice'?'page':'false'));
  document.body.dataset.workspace='practice';
  clearContextFeedback();
  window.scrollTo({top:0,behavior:'instant'});
  if (poll) clearInterval(poll);
  if (tick) clearInterval(tick);
  clearPendingReveals();
  S = null; lastPhase = null; RESULTS = null;document.body.dataset.phase='lobby';entryPending=null;positionRoomFrame();
  // Keep this workspace addressable separately from the student dashboard.
  history.replaceState(null, '', location.pathname + location.search + '#practice');
  clockEl.classList.add('hidden'); chipEl.classList.add('hidden');
  homeBtn.classList.add('hidden');
  if (brandSub) brandSub.textContent = 'Your clinical skills workspace';

  const prefs = LS.get('prefs') || {};
  const uiMode = normalizeMode(prefs.ui_mode);
  const drill = DRILLS[prefs.drill] ? prefs.drill : 'summary';
  const talk = prefs.mode === 'voice' ? 'voice' : 'type';
  voice.speak = prefs.speak !== false;
  window.dispatchEvent(new Event('pcm-speech-preference'));
  const open = (BOOT.sessions || []).filter(s => s.phase !== 'submitted')[0];

  view.innerHTML = `
  <div class="wrap-mid">
    <div class="lobby-hero">
      <div class="eyebrow">Patient encounter library</div>
      <h1>Choose your next encounter.</h1>
      <p>Choose your support, explore a presentation, then read the doorway before entering.</p>
      <div class="hero-path" aria-label="Practice journey"><span>01 &nbsp; Meet</span><span>02 &nbsp; Explore</span><span>03 &nbsp; Reflect</span></div>
    </div>



    <section class="card" aria-labelledby="modeH">
      <div class="card-head"><h2 id="modeH">Choose your support</h2></div>
      <div class="mode-grid" role="radiogroup" aria-labelledby="modeH">
        ${Object.keys(MODES).map(k => { const m = MODES[k]; return `
        <label class="mode-card ${k === uiMode ? 'sel' : ''}" data-mode="${k}">
          <input type="radio" name="uimode" value="${k}" ${k === uiMode ? 'checked' : ''}>
          <span class="m-ico" aria-hidden="true">${m.icon}</span>
          <span class="m-name">${esc(m.name)}</span>
          <span class="m-time">${esc(m.time)}</span>
          <span class="m-desc">${esc(m.desc)}</span>
          <span class="m-flags">
            <span class="badge ${m.reveal ? 'b-mute' : 'b-info'}">${m.reveal ? 'titles visible' : 'titles sealed'}</span>
            <span class="badge ${m.coach ? 'b-mute' : 'b-info'}">${m.coach ? 'bedside prompts' : 'no prompts'}</span>
          </span>
        </label>`; }).join('')}
      </div>
      <div id="drillPick" class="${uiMode === 'drill' ? '' : 'hidden'}" style="margin-top:var(--sp-4)">
        <fieldset><legend>Which skill is the drill about?</legend>
        <div class="drill-grid" role="radiogroup" aria-label="Drill focus">
          ${Object.keys(DRILLS).map(k => { const d = DRILLS[k]; return `
          <label class="opt ${k === drill ? 'sel' : ''}" data-drill="${k}">
            <input type="radio" name="drill" value="${k}" ${k === drill ? 'checked' : ''}>
            <span><b>${esc(d.name)}</b><span class="small muted">${esc(d.goal)}</span></span>
          </label>`; }).join('')}
        </div></fieldset>
      </div>
    </section>

    <section class="card" aria-labelledby="stationH">
      <div class="card-head station-head"><h2 id="stationH">Explore the patient presentations</h2>
        <span class="lobby-chosen tiny muted" id="lobbyChosen"></span>
        <div class="spacer"></div>
        <label class="sr-only" for="sysPick">System</label>
        <select id="sysPick" class="chip-model" aria-hidden="true" tabindex="-1">
          <option value="">Any system</option>
          ${(BOOT.systems || []).map(s => `<option>${esc(s)}</option>`).join('')}
        </select>
        <button class="btn sm ghost" id="btnRandom" type="button">Draw a case at random</button>
        <button class="btn primary" id="btnStart" type="button">Read the doorway</button>
      </div>
      <p class="small muted" id="revealNote"></p>
      <div class="station-grid" role="radiogroup" aria-labelledby="stationH" id="stationGrid">
        ${stations().map(c => `
        <label class="station-card" data-case="${esc(c.id)}">
          <input type="radio" name="station" value="${esc(c.id)}">
          <span class="station-no">${esc(stationTitle(c.id))}</span>
          <span class="s-open"></span>
        </label>`).join('')}
      </div>
    </section>

    <section class="card" aria-labelledby="talkH">
      <div class="card-head"><h2 id="talkH">How you talk to the patient</h2></div>
      <div class="row">
        <div class="seg" role="radiogroup" aria-labelledby="talkH">
          <button type="button" class="segbtn" data-talk="type" aria-pressed="${talk === 'type'}">Type</button>
          <button type="button" class="segbtn" data-talk="voice" aria-pressed="${talk === 'voice'}">Speak</button>
        </div>
        <span id="voiceOk" class="badge b-mute">checking…</span>
      </div>
      <p class="small muted" id="talkNote" style="margin-top:var(--sp-2)"></p>
    </section>

    <div class="card row lobby-reference" style="gap:var(--sp-3)">
      <button class="btn" id="btnResume" type="button" ${open ? '' : 'hidden'}>Resume in-progress station</button>
      <div class="spacer" style="flex:1"></div>
      <button class="btn ghost" id="btnAssume" type="button" aria-expanded="false"
        aria-controls="extraPanel">Scoring assumptions</button>
      <button class="btn ghost" id="btnReview" type="button" aria-expanded="false"
        aria-controls="extraPanel">Case review status</button>
      <button class="btn ghost" id="btnPast" type="button" aria-expanded="false"
        aria-controls="extraPanel">Past attempts (${(BOOT.sessions || []).length})</button>
    </div>
    <div id="extraPanel" class="disclosure"></div>
    <p class="tiny muted" id="capNote">Attempts, notes and scores stay in this browser. No paid AI services are included. Computer voice uses browser speech; optional microphone recognition may use your browser provider. Nothing is sent to the app creator. Clearing site data deletes local progress.</p>
  </div>`;

  $$('.mode-card').forEach(card => {
    const input = $('input', card);
    input.onchange = () => {
      $$('.mode-card').forEach(c => c.classList.toggle('sel', $('input', c).checked));
      $('#drillPick').classList.toggle('hidden', input.value !== 'drill');
      applyReveal(input.value); savePrefs();
    };
  });
  $$('#drillPick .opt').forEach(l => { $('input', l).onchange = () => {
    $$('#drillPick .opt').forEach(x => x.classList.toggle('sel', $('input', x).checked));
    savePrefs(); }; });
  // Choosing a station happens near the top of a 2000px page and the action
  // that uses it sits under 24 tiles. Say what is chosen ON the action, and
  // keep the action in view once there is something to act on.
  const paintChosen = () => {
    const picked = $('input[name=station]:checked');
    const chosen = $('#lobbyChosen'), row = $('.station-head');
    const c = picked ? caseById(picked.value) : null;
    const reveal = (MODES[currentUiMode()] || MODES.coached).reveal;
    if (chosen) chosen.textContent = c
      ? (reveal ? stationTitle(c.id) + ' — ' + c.title : stationTitle(c.id) + ' — contents sealed')
      : 'Choose a presentation to begin.';
    if (row) row.classList.toggle('is-ready', !!c);
  };
  $$('#stationGrid .station-card').forEach(l => { $('input', l).onchange = () => {
    $$('#stationGrid .station-card').forEach(x => x.classList.toggle('sel', $('input', x).checked));
    paintChosen(); }; });
  $$('input[name=drill]').forEach(r => r.addEventListener('change', paintChosen));
  paintChosen();
  $$('.segbtn[data-talk]').forEach(b => { b.onclick = () => {
    $$('.segbtn[data-talk]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    savePrefs(); paintTalkNote(); if (b.dataset.talk === 'voice') probeVoice(); }; });

  $('#btnStart').onclick = () => begin(false);
  $('#btnRandom').onclick = () => begin(true);
  $('#btnAssume').onclick = e => togglePanel('assume', e.currentTarget);
  $('#btnReview').onclick = e => togglePanel('review', e.currentTarget);
  $('#btnPast').onclick = e => togglePanel('past', e.currentTarget);
  refreshLobbyHistory();

  applyReveal(uiMode); paintTalkNote(); probeVoice();
  window.pcmLearningRender?.(null);
}
function refreshLobbyHistory(){
  if(S || (!$('#stationGrid')&&!$('#progressWorkspace'))) return;
  const rows=BOOT.sessions||[], past=$('#btnPast'), resume=$('#btnResume');
  if(past) past.textContent=`Past attempts (${rows.length})`;
  const open=rows.find(s=>s.phase!=='submitted');
  if(resume){resume.hidden=!open;resume.onclick=()=>{
    const latest=(BOOT.sessions||[]).find(s=>s.phase!=='submitted');
    if(latest) location.hash='#/'+latest.id;
  };}
  const panel=$('#extraPanel');
  if(panel?.dataset.open==='past'){
    panel.innerHTML=panelPast();
    wirePastPanel();
  }
}
function currentUiMode(){ const r = $('input[name=uimode]:checked'); return r ? r.value : 'coached'; }
function currentTalk(){ const b = $('.segbtn[data-talk][aria-pressed="true"]');
  return b ? b.dataset.talk : 'type'; }
function savePrefs(){
  // Only the lobby owns these controls; a call from anywhere else would write
  // defaults over the choices the learner actually made.
  const prev = LS.get('prefs') || {};
  if (!$('input[name=uimode]:checked')) {
    LS.set('prefs', Object.assign({}, prev, { speak: voice.speak }));
    return;
  }
  const d = $('input[name=drill]:checked');
  LS.set('prefs', { ui_mode: currentUiMode(), drill: d ? d.value : (prev.drill || 'summary'),
    mode: currentTalk(), speak: voice.speak });
}
function applyReveal(uiMode){
  const m = MODES[uiMode] || MODES.coached;
  const note = $('#revealNote');
  if (note) note.textContent = m.reveal
    ? 'Titles and systems are shown. The doorway still gives you only what the station gives you.'
    : 'Clinical titles stay hidden. Read the authorized station information at the doorway.';
  $$('#stationGrid .station-card').forEach(card => {
    const c = caseById(card.dataset.case), openEl = $('.s-open', card);
    if (!c || !openEl) return;
    openEl.innerHTML = m.reveal
      ? `<span class="s-title">${esc(c.title)}</span>
         <span class="s-meta">${esc(c.system)} · ${esc(c.level)}</span>
         <span class="s-blurb">${esc(c.blurb)}</span>`
      : `<span class="s-meta">${esc(c.level)} · system sealed</span>
         <span class="s-sealed">Nothing about this station is shown before the doorway.</span>`;
    $('input', card).setAttribute('aria-label', stationTitle(c.id) +
      (m.reveal ? ' — ' + c.title : ' — contents sealed'));
  });
  window.pcmPortal?.decoratePractice(uiMode,m.reveal);
}
function paintTalkNote(){
  const el = $('#talkNote'); if (!el) return;
  el.textContent = currentTalk() === 'voice'
    ? 'Speaking is closest to the real station. Recognition adds its own delay, so the pauses the debrief measures include that delay and are reported, not graded as conversational rhythm. Typed entry stays available at all times.'
    : 'Typing is fully supported and obeys exactly the same clinical rules as speaking. Pauses reflect your typing speed, so pacing is reported but not scored as conversational rhythm.';
}
function togglePanel(which, btn){
  const p = $('#extraPanel');
  $$('[aria-controls=extraPanel]').forEach(b => b.setAttribute('aria-expanded', 'false'));
  if (p.dataset.open === which) { p.innerHTML = ''; p.dataset.open = ''; return; }
  p.dataset.open = which;
  if (btn) btn.setAttribute('aria-expanded', 'true');
  if (which === 'assume') p.innerHTML = panelAssume();
  else if (which === 'review') p.innerHTML = panelReview();
  else p.innerHTML = panelPast();
  if (which === 'past') wirePastPanel();
  const h = $('h2', p); if (h) { h.setAttribute('tabindex', '-1'); h.focus(); }
}
function panelAssume(){
  // Point values and row names: PCM 2026 Student Manual, SOAP grading Table 4.
  // This is a learner guide only; pcmcse/grader.py remains the scoring authority.
  const subjective = [
    ['age_sex','Age and sex','State the supplied patient age and sex accurately.'],
    ['cc_clear','Chief complaint','Name the main reason for the visit clearly.'],
    ['onset_location','Onset / location','Describe when the symptom began and where it occurs.'],
    ['duration_chronological','Duration / chronology','Explain its duration and course over time.'],
    ['character_quality','Character / quality','Describe what the symptom feels like in the patient’s words.'],
    ['severity_quantity','Severity / quantity','Record the severity or amount you established.'],
    ['alleviating_aggravating','Alleviating / aggravating','Record what improves or worsens the symptom.'],
    ['associated_past_treatments','Associated symptoms / prior episodes / treatment','Include relevant associated symptoms, prior similar episodes, and treatments tried.'],
    ['pmh_psh','Past medical and surgical history','Ask and document both medical conditions and operations.'],
    ['medications','Medications','Document the medication history you obtained, including relevant nonprescription products.'],
    ['social_history','Social history','Always address tobacco, alcohol, and drug use; add relevant context.'],
    ['family_history','Family history','Address biological parents and siblings.'],
    ['allergies','Allergies','Document the allergy history actually obtained; include reported reactions when known.'],
    ['ros','Review of systems','Obtain and document 3 symptoms in each of 3 pertinent systems: 9 symptoms total.'],
  ];
  const objective = [
    ['vitals','Vitals','Put the supplied doorway measurements first in Objective. They are authorized information; you do not need to pretend you measured them.'],
    ['general','General','Describe the general findings you actually observed or were supplied.'],
    ['heart_lungs','Heart and lungs','Document both, using separate Heart: and Lungs: headers and the specific findings you obtained.'],
    ['most_relevant','Most relevant system','Expand the examination of the area of concern. Include the pertinent methods and results you actually obtained; a generic normal statement is insufficient.'],
    ['other_systems','Other system(s)','Record the other relevant examination findings you obtained under their own headers.'],
    ['osteopathic','Osteopathic','Document the examined level and the dysfunction you established.'],
  ];
  const table = (rows, points) => `<div class="table-scroll"><table class="rows"><thead><tr><th scope="col">Scored item</th><th scope="col">What to do</th><th scope="col">Points</th></tr></thead><tbody>${rows.map(([id,label,action])=>`<tr data-scoring-row="${id}"><th scope="row">${esc(label)}</th><td>${esc(action)}</td><td class="pts">${points}</td></tr>`).join('')}</tbody></table></div>`;
  const weights = [['Subjective',28],['Objective',30],['Assessment',15],['Plan',25],['Spelling / style',2]];
  return `<div class="disclosure-body" id="scoring-guide"><h2>How to earn the SOAP points</h2>
    <p>The PCM SOAP rubric has <b>100 available points</b>. Use this guide to collect the information you need and put it in the correct part of your note. It describes the rubric; the app’s automated feedback can still make mistakes.</p>
    <div class="exam-summary" aria-label="SOAP rubric point distribution">${weights.map(([label,points])=>`<div class="es" data-scoring-category="${esc(label)}" data-points="${points}"><div class="n">${points}</div><div class="k">${esc(label)}</div></div>`).join('')}</div>
    <p class="small muted">Course source: Student Manual, PCM 2026 SOAP note grading table (Table 4). Source details are listed below.</p>
    <div class="callout info"><b>Obtain it → document it → support it.</b> Ask the question or complete the specific examination, then document the information delivered to you. Doorway vitals count as supplied evidence. A hidden case fact, a body-view change, or a teaching animation does not establish a finding. Put a differential in Assessment and a proposed future action in Plan.</div>

    <details class="item" open><summary><b>Subjective — 28 points</b> · 14 history items, 2 points each</summary>
      <p class="small">Use clear headers: CC, HPI, PMH/PSH, Medications, Social History, Family History, Allergies, and ROS. Write accurate, specific history; do not invent a negative answer to fill a row.</p>
      ${table(subjective,2)}
    </details>
    <details class="item"><summary><b>Objective — 30 points</b> · 6 examination items, 5 points each</summary>
      <p class="small">Start with <b>Vitals:</b>, then use separate examination headers. Describe findings rather than writing <b>“Normal.”</b> Use approved abbreviations. The needed detail depends on the clinical concern.</p>
      ${table(objective,5)}
      <p class="small">Record supplied test results and an actual examination refusal in Objective. Never document an unperformed maneuver as a normal examination.</p>
    </details>
    <details class="item"><summary><b>Assessment — 15 points</b> · 3 differentials, 5 points each</summary>
      <ol class="tight small"><li>Number the diagnoses <b>1, 2, 3</b>, with the <b>most likely first</b>.</li><li>Choose diagnoses that fit the encounter, rather than vague labels or unrelated possibilities.</li><li>Use <b>3 different VINDICATE elements</b>, as required by the rubric.</li></ol>
      <p class="small"><b>VINDICATE — organize your differential:</b> <b>V</b>ascular; <b>I</b>nfectious / inflammatory; <b>N</b>eoplastic; <b>D</b>egenerative / deficiency; <b>I</b>atrogenic / intoxication; <b>C</b>ongenital; <b>A</b>utoimmune / allergic; <b>T</b>raumatic; <b>E</b>ndocrine / metabolic.</p>
      <p class="small">Use the categories to consider relevant causes, then choose the diagnoses best supported by this encounter. A reasonable differential is a clinical inference. It does not authorize adding unasked symptoms or unperformed findings to S or O.</p>
    </details>
    <details class="item"><summary><b>Plan — 25 points</b> · 3 plans + education + follow-up</summary>
      <div class="table-scroll"><table class="rows"><thead><tr><th scope="col">Scored item</th><th scope="col">What to do</th><th scope="col">Points</th></tr></thead><tbody>
        <tr data-scoring-row="plan1"><th scope="row">Plan 1</th><td>Number it 1 and match Assessment 1. Include at least 3 different MOTHERR elements, selected appropriately for this diagnosis.</td><td class="pts">5</td></tr>
        <tr data-scoring-row="plan2"><th scope="row">Plan 2</th><td>Number it 2 and match Assessment 2. Include at least 3 different MOTHERR elements.</td><td class="pts">5</td></tr>
        <tr data-scoring-row="plan3"><th scope="row">Plan 3</th><td>Number it 3 and match Assessment 3. Include at least 3 different MOTHERR elements.</td><td class="pts">5</td></tr>
        <tr data-scoring-row="education"><th scope="row">Specific education</th><td>Include concrete, relevant patient instructions in at least one plan. State what the patient should do rather than writing only “counseled.”</td><td class="pts">5</td></tr>
        <tr data-scoring-row="followup"><th scope="row">Specific follow-up / disposition</th><td>Put the specific follow-up in <b>Plan 1</b>. Give an interval, or an appropriate disposition when applicable.</td><td class="pts">5</td></tr>
      </tbody></table></div>
      <p class="small"><b>MOTHERR — organize your plan:</b> <b>M</b>edications; <b>O</b>steopathic treatment (OMT); <b>T</b>esting; <b>H</b>umanistic / supportive needs; <b>E</b>ducation; <b>R</b>eferral; <b>R</b>eturn / follow-up.</p>
      <p class="small"><b>Humanistic / supportive needs:</b> Consider daily function, comfort, support, and the patient’s ability to carry out the plan. Include appropriate supportive measures, such as activity modification or hydration, when relevant.</p>
      <p class="small">Make each plan specific; name the body location for imaging. Three tests are not three different MOTHERR elements. Do not add unnecessary treatment merely to fill a category.</p>
    </details>
    <details class="item"><summary><b>Spelling and style — 2 points</b> · a clear, readable note</summary>
      <p class="small">Proofread spelling and wording, organize the note under the required headings, and keep statements specific and unambiguous. Other rubric conditions still apply within their own rows.</p>
    </details>

    <h3>During the encounter: a separate part of your performance</h3>
    <p class="small">The standardized-patient checklist and interpersonal-skills assessment are separate from the 100-point SOAP rubric. The app reports their feedback separately; it does not invent a combined course score.</p>
    <ul class="tight small"><li>Introduce yourself, use hand hygiene and gloves before the physical examination, and obtain permission while explaining what you are doing.</li><li>Take a focused history and select relevant examination actions. Use the taught sequence and stated technique; include the appropriate osteopathic examination.</li><li>Attend to comfort, draping, and assistance with position changes. Listen, clarify, and discuss the plan before closing.</li><li>For the course’s specified invasive examinations, state the intended examination when warranted and document the patient’s refusal. These are not performed at the station.</li></ul>
    <p class="small muted">A virtual interaction cannot verify hands-on pressure, true stethoscope contact, eye contact, or physical technique. Changing a camera or patient position earns no examination finding by itself.</p>

    <h3>A final check before submitting</h3>
    <p class="small"><b>History:</b> relevant chronology, background history, and 3 × 3 ROS. <b>Objective:</b> supplied vitals first, specific obtained findings, and correct headers. <b>Assessment:</b> 3 numbered, defensible diagnoses, most likely first. <b>Plan:</b> 3 corresponding plans, 3 distinct elements each, specific education, and follow-up/disposition in Plan 1.</p>
    <p class="small">The confirmed timing is <b>14 minutes for the encounter and 9 minutes for the SOAP note</b>. Guided and Coached are untimed. Independent practice allows 30 minutes for the encounter, 5 to organize, and 20 for the note. Exam rehearsal uses the course timing without an organization break. Earlier saved attempts retain their original preset.</p>

    <h3 id="scoring-guide-sources">Where these requirements come from</h3>
    <ul class="tight small"><li><b>Student Manual, revised June 2026:</b> SOAP grading Table 4 supplies the point values and conditions; the blank note form and patient/interpersonal checklists supply the structure and separate encounter expectations.</li><li><b>PCM I syllabus, Fall 2026:</b> §III, pages 4–5, supplies timing, focused encounter, documentation, and invasive-examination refusal rules; §VII describes competency-based pass/fail.</li><li><b>Intro to PCM I:</b> PDF pages 21–27 clarify abbreviations, supplied results/refusals, specificity, section placement, and false documentation.</li><li><b>Interpersonal Skills:</b> PDF pages 27–33 clarify examination sequence, draping, structural examination, and Heart/Lungs header wording.</li></ul>

    <p class="small muted"><b>Mnemonic sources:</b> <a href="https://rad.uw.edu/online-musculoskeletal-radiology-book/general-principles" target="_blank" rel="noopener noreferrer">University of Washington</a> and <a href="https://www.acponline.org/sites/default/files/documents/clinical_information/journals_publications/books/teaching_clinical_reasoning/web_extras.pdf" target="_blank" rel="noopener noreferrer">ACP, Table w-2</a> publish VINDICATE variants with different D/I groupings; the app retains the mapping shown above. MOTHERR is a working expansion: the supplied course materials do not define its letters, and a complete authoritative online expansion was not found.</p>

    <h3>Assumptions, app defaults, and what remains unknown</h3>
    <p class="small">The point values above are confirmed. These details are not all settled by the course, or describe the simulator rather than the real examination. There is no published numeric SOAP passing cutoff or stated weighting that combines SOAP, encounter, and interpersonal performance.</p>
    <details class="item"><summary><b>Review the active interpretations and limitations</b></summary>
      ${(BOOT.assumptions || []).map(a => `<div class="item ${a.status === 'provisional' ? 'warn' : a.status === 'practice-mod' ? 'info' : 'mute'}"><h4>${esc(a.topic)} <span class="badge ${a.status === 'provisional' ? 'b-warn' : 'b-mute'}">${esc(a.status)}</span></h4><div class="small"><b>${esc(a.value)}</b></div><div class="small muted">${esc(a.detail)}</div></div>`).join('')}
    </details></div>`;
}
function panelReview(){
  return `<div class="disclosure-body"><h2>Case review status</h2>
    <div class="callout bad"><b>No licensed clinician has reviewed or approved any case
    in this app.</b> Automated guideline retrieval is not clinical validation, and nothing
    here creates a course scoring rule.</div>
    <p class="small">Each case carries its own review record — who looked at it, by what
    method, what changed, what the limits are, and every source with a link. The station
    list does not publish it, because naming a case's guideline sources before you enter
    would tell you the diagnosis. It is printed in full on the debrief, under
    <b>About this case</b>, for the station you just ran.</p>
    <p class="small muted">The three statuses a case can carry are
    <span class="badge b-bad">Not reviewed</span>
    <span class="badge b-warn">Internal consistency check only</span> and
    <span class="badge b-warn">Guideline-checked, not clinician-approved</span>.
    None of them is clinician approval.</p></div>`;
}
function panelPast(){
  const rows = BOOT.sessions || [], reveal=!!MODES[currentUiMode()]?.reveal;
  const choices=(BOOT.cases||[]).map(c=>`<option value="${esc(c.id)}">${esc(stationTitle(c.id))}${reveal?' — '+esc(c.title):''}</option>`).join('');
  return `<div class="disclosure-body"><h2>Past attempts</h2>
    <p class="small muted">Retries and revisions keep each original attempt intact. Use Reset progress below only when you want to remove saved work.</p>
    ${!rows.length ? '<p class="muted small">No saved attempts yet.</p>' : rows.map(h => `<div class="hist-row">
      <span class="small muted">${esc(new Date(h.created_at).toLocaleString())}</span>
      <span>${esc(stationTitle(h.case_id))} <span class="tiny muted">${esc(h.preset || '')} · ${esc(h.interaction_mode || '')}</span></span>
      <span class="ph">${h.graded ? '<span class="badge b-ok">graded</span>'
        : '<span class="badge b-mute">' + esc(h.phase) + '</span>'}</span>
      <span><button class="btn sm" type="button" data-open="${esc(h.id)}">Open</button></span>
    </div>`).join('')}
    ${S?'':`<details class="progress-reset-tools" id="progressResetTools"><summary>Reset progress</summary>
      <p class="small">Start fresh for one presentation, including all its variations, or for the whole library. You can review what will be removed before confirming.</p>
      <div class="progress-reset-actions"><label for="resetProgressCase">Presentation<select id="resetProgressCase"><option value="">Choose a presentation…</option>${choices}</select></label>
        <button class="btn" type="button" id="resetCaseProgress" disabled>Reset case progress</button>
        <button class="btn" type="button" id="resetAllProgress">Reset all progress</button></div>
      <p id="progressResetStatus" class="small muted" role="status"></p><div id="progressResetConfirm"></div>
    </details>`}</div>`;
}
function clearResetLocalWork(scope,caseId,attemptIds){
  const ids=new Set(attemptIds),known=['pcmcse.ui.','pcmcse.performed.','pcmcse.courtesy.','pcmcse.entrance.','pcm-camera.'];
  let cleared=true;
  try{
    const keys=Array.from({length:localStorage.length},(_,i)=>localStorage.key(i)).filter(Boolean);
    for(const key of keys){
      const draft=/^pcmcse\.draft\.(?:scratch|note|conversation)\.(.+)$/.exec(key);
      const attemptKey=draft?ids.has(draft[1]):known.some(prefix=>key.startsWith(prefix)&&ids.has(key.slice(prefix.length)));
      const reflection=key.startsWith('pcmcse.written-reflection.')&&(scope==='all'||key.startsWith('pcmcse.written-reflection.'+caseId+'.'));
      if(attemptKey||reflection)localStorage.removeItem(key);
    }
  }catch{cleared=false;}
  if(ids.has(window.pcmLastAttempt))window.pcmLastAttempt=null;
  return cleared;
}
function wirePastPanel(){
  const panel=$('#extraPanel');if(!panel)return;
  $$('[data-open]',panel).forEach(b=>{b.onclick=()=>{location.hash='#/'+b.dataset.open;};});
  if(S)return;
  const select=$('#resetProgressCase',panel),caseButton=$('#resetCaseProgress',panel),allButton=$('#resetAllProgress',panel);
  if(!select||!caseButton||!allButton)return;
  select.onchange=()=>{progressResetPreview++;caseButton.disabled=!select.value;$('#progressResetConfirm',panel).innerHTML='';$('#progressResetStatus',panel).textContent='';};
  caseButton.onclick=()=>showProgressResetConfirmation('case',select.value,caseButton);
  allButton.onclick=()=>showProgressResetConfirmation('all',null,allButton);
}
let progressResetPreview=0;
async function showProgressResetConfirmation(scope,caseId,trigger){
  if(S||(!$('#stationGrid')&&!$('#progressWorkspace'))||(scope==='case'&&!caseById(caseId)))return;
  const host=$('#progressResetConfirm'),status=$('#progressResetStatus');if(!host||!status)return;
  const requestId=++progressResetPreview;
  const label=scope==='all'?'all presentations':stationTitle(caseId)+' and all its variations';
  status.textContent='Checking all saved progress, including older attempts…';
  host.innerHTML='<button class="btn" type="button" id="cancelResetPreview">Cancel</button>';
  const previewCancel=$('#cancelResetPreview');previewCancel.focus();previewCancel.onclick=()=>{progressResetPreview++;host.innerHTML='';status.textContent='';trigger?.focus();};
  const previewPayload={scope};if(scope==='case')previewPayload.case_id=caseId;
  let preview;
  try{
    const response=await fetch('/api/progress/reset-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(previewPayload)});preview=await response.json();
    if(!response.ok||preview.error)throw Error(preview.message||preview.error||'Reset details could not be loaded.');
    if(!Number.isInteger(preview.attempt_count)||!Number.isInteger(preview.unfinished_count)||preview.attempt_count<0||preview.unfinished_count<0)throw Error('Reset counts could not be verified.');
  }catch(error){if(requestId===progressResetPreview&&host.isConnected){status.textContent=error.message+' No progress was removed.';host.innerHTML='';trigger?.focus();}return;}
  if(S||(!$('#stationGrid')&&!$('#progressWorkspace'))||!host.isConnected||requestId!==progressResetPreview)return;
  const unfinished=preview.unfinished_count,attemptCount=preview.attempt_count,reflections=preview.study_progress_count||0;
  status.textContent='';
  host.innerHTML=`<section class="callout warn" role="group" aria-labelledby="progressResetHeading" aria-describedby="progressResetDescription">
    <h3 id="progressResetHeading">Reset ${esc(label)}?</h3>
    <p id="progressResetDescription">This permanently removes ${attemptCount} saved attempt${attemptCount===1?'':'s'}, including their notes, scores, encounter records and learning activity, plus ${reflections} saved written reflection${reflections===1?'':'s'} and any browser reflection drafts for ${esc(label)}. This cannot be undone.</p>
    ${unfinished?`<label class="opt"><input type="checkbox" id="resetIncludeUnfinished"><span>Also remove ${unfinished} unfinished attempt${unfinished===1?'':'s'} and ${unfinished===1?'its':'their'} notes</span></label>`:''}
    <div class="progress-reset-actions"><button class="btn" type="button" id="cancelProgressReset">Cancel</button>
      <button class="btn danger" type="button" id="confirmProgressReset" ${unfinished?'disabled':''}>Permanently reset ${scope==='all'?'all progress':'case progress'}</button></div>
  </section>`;
  const cancel=$('#cancelProgressReset'),confirm=$('#confirmProgressReset'),checkbox=$('#resetIncludeUnfinished');
  cancel.onclick=()=>{host.innerHTML='';if(trigger?.isConnected)trigger.focus();};
  if(checkbox)checkbox.onchange=()=>{confirm.disabled=!checkbox.checked;};
  cancel.focus();
  confirm.onclick=async()=>{
    if(S||(!$('#stationGrid')&&!$('#progressWorkspace'))||(unfinished&&!checkbox?.checked))return;
    const payload={scope,confirm:true,include_in_progress:!!checkbox?.checked};if(scope==='case')payload.case_id=caseId;
    const controls=$$('button,input,select',$('#progressResetTools')),disabledBefore=new Map(controls.map(c=>[c,c.disabled]));
    controls.forEach(c=>c.disabled=true);host.setAttribute('aria-busy','true');status.textContent='Resetting the selected progress…';
    try{
      const response=await fetch('/api/progress/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),result=await response.json();
      if(response.status===409){
        const latest=await api('/api/bootstrap');if(!latest.error){BOOT.sessions=latest.sessions||[];BOOT.progress=latest.progress||{};}
        refreshLobbyHistory();const tools=$('#progressResetTools');if(tools)tools.open=true;
        const message='Saved attempts changed. Nothing was reset. Review the refreshed history, then choose Reset progress again.';
        const updated=$('#progressResetStatus');if(updated)updated.textContent=message;alertNow(message);return;
      }
      if(!response.ok||!result.ok)throw Error(result.message||result.error||'The reset could not be confirmed.');
      if(!Array.isArray(result.sessions)||!Array.isArray(result.deleted_attempt_ids))throw Error('The reset response was incomplete.');
      const remaining=result.sessions,ids=result.deleted_attempt_ids;
      const cleared=clearResetLocalWork(scope,caseId,ids);BOOT.sessions=remaining;BOOT.progress=result.progress||{};
      refreshLobbyHistory();$('#learningLibrary')?.remove();window.pcmLearningRender?.(null);
      window.dispatchEvent(new CustomEvent('pcm-progress-reset',{detail:{scope,case_id:caseId,attempt_ids:ids}}));
      const message=`Progress reset for ${label}: ${result.deleted?.attempts??ids.length} attempt${(result.deleted?.attempts??ids.length)===1?'':'s'} removed.`+(cleared?'':' Saved progress was removed, but browser draft storage could not be cleared.');
      toast(message);$('#btnPast')?.focus();
    }catch(error){
      if(status.isConnected)status.textContent=(error.message||'The reset could not be confirmed.')+' Cancel and reopen Reset progress to refresh history before trying again.';
      controls.forEach(c=>c.disabled=disabledBefore.get(c));confirm.disabled=true;host.removeAttribute('aria-busy');
      alertNow(status.textContent);cancel.focus();
    }
  };
}

async function begin(random, opts){
  opts = opts || {};
  const uiMode = normalizeMode(opts.learning_mode || opts.ui_mode || currentUiMode());
  const m = MODES[uiMode] || MODES.coached;
  const talk = opts.mode || currentTalk();
  const drillSel = $('input[name=drill]:checked');
  const drill = uiMode === 'drill' ? (opts.drill || (drillSel ? drillSel.value : 'summary')) : null;
  let caseId = opts.case_id || null;
  if (!caseId && !random) {
    const picked = $('input[name=station]:checked');
    caseId = picked ? picked.value : null;
  }
  if (!caseId && !random) {
    toast('Choose a station first, or draw one at random.');
    const first = $('#stationGrid input'); if (first) first.focus();
    return;
  }
  savePrefs();
  const sys = $('#sysPick');
  const protect=['independent','rehearsal'].includes(opts.learning_mode||uiMode);if(protect)window.pcmStudy?.beginProtectedAttempt();
  const st = await api('/api/session', {
    case_id: caseId, random: !caseId, system: (!caseId && sys && sys.value) || null,
    preset: opts.preset || m.preset, interaction_mode: talk, assisted: false,
    learning_mode: opts.learning_mode || uiMode, variant_id: opts.variant_id || null, visual_demo: opts.visual_demo || null
  });
  if(protect)window.pcmStudy?.endProtectedAttempt();
  if (st.error || !st.id) { toast(st.message || st.error || 'Could not open that station.'); return; }
  setUiMeta(st.id, { ui_mode: uiMode, drill: drill });
  S = st; lastPhase = null;
  room = { view:'front', region:null, instrument:'', position:'seated',
           running:null, runTimer:null, runEnd:null, performed:{} };
  history.pushState(null,'','#/'+st.id);
  startPolling(); renderPhase(true);
}

/* ======================================================================== */
/* 2. DOORWAY                                                                */
/* ======================================================================== */
let roomFrameReady=false,entryPending=null,roomViewportObserver=null;
const patientDisplayStates=new Map();
function patientDisplayLabel(){const status=patientDisplayStates.get(S?.id);return status==='ready'?'Patient ready':status==='loading'?'Preparing patient…':status==='failed'?'Patient display unavailable · text controls available':roomFrameReady?'Room ready · preparing patient':'Preparing room…';}
function positionRoomFrame(){
  const host=$('#roomFrameHost'),slot=$('#roomViewport');if(!host)return;
  if(!slot||!S||!['briefing','encounter'].includes(S.phase)){host.hidden=true;return;}
  const b=slot.getBoundingClientRect();host.hidden=false;Object.assign(host.style,{left:(b.left+window.scrollX)+'px',top:(b.top+window.scrollY)+'px',width:b.width+'px',height:b.height+'px'});
}
function mountPatientFrame(){
  let host=$('#roomFrameHost');if(!host){host=document.createElement('div');host.id='roomFrameHost';host.innerHTML=`<iframe id="unityFrame" src="patient3d/index.html?v=878ddfba16" title="Interactive patient and examination room" allow="autoplay"></iframe>`;document.body.append(host);roomFrameReady=false;$('#unityFrame').onload=notifyPublicState;}
  roomViewportObserver?.disconnect();roomViewportObserver=new ResizeObserver(positionRoomFrame);for(const target of [$('#roomViewport'),$('#patientVoiceSettings'),document.body])if(target)roomViewportObserver.observe(target);positionRoomFrame();if(roomFrameReady&&$('#unityStatus'))$('#unityStatus').textContent=patientDisplayLabel();notifyPublicState();
}
window.addEventListener('resize',positionRoomFrame);document.addEventListener('scroll',positionRoomFrame,true);
function setEntryStatus(text){const el=$('#entryStatus');if(el)el.textContent=text;}
async function completeEntrance(id){
  if(!entryPending||entryPending.id!==id||entryPending.starting||S?.id!==entryPending.sid||S.phase!=='briefing')return;
  entryPending.starting=true;const request=entryPending;setEntryStatus('Your room is ready. Starting the encounter…');
  const next=await post(`/api/session/${request.sid}/start`);
  if(S?.id!==request.sid)return;
  if(next.error){entryPending=null;$('#go').disabled=false;$('#skipEntrance').disabled=false;setEntryStatus('Unable to confirm entry. Reconnect to check the encounter clock before continuing.');$('#unityFrame')?.contentWindow?.postMessage({type:'pcm-room-reset-entry'},location.origin);return;}
  LS.set('entrance.'+request.sid,{skipped:request.skip,transition_ms:Math.round(performance.now()-request.at),phase_started_at:next.phase_started_at,phase_ends_at:next.phase_ends_at});
  entryPending=null;S=next;renderPhase(true);announce(isUntimedAttempt()?'You are in the room. Your encounter is untimed.':'You are in the room. Your encounter has started with '+phaseAllowance(S.preset.encounter_s)+' available.');
}
function dispatchEntrance(){
  if(!entryPending||entryPending.starting||!roomFrameReady)return;
  if(new URL(location.href).searchParams.get('renderer')==='unity'){completeEntrance(entryPending.id);return;}
  setEntryStatus('Entering the room… The encounter clock has not started.');
  $('#unityFrame')?.contentWindow?.postMessage({type:'pcm-room-enter',requestId:entryPending.id,skip:entryPending.skip},location.origin);
}
function beginEntrance(skip=false){
  if(!S||S.phase!=='briefing')return;
  const reduced=$('#entryReduced')?.checked||window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(entryPending){if(skip&&!entryPending.starting){entryPending.skip=true;if(roomFrameReady)dispatchEntrance();}return;}
  entryPending={id:crypto.randomUUID(),sid:S.id,skip:skip||reduced,at:performance.now(),starting:false};
  $('#go').disabled=true;setEntryStatus(roomFrameReady?'Entering the room… The encounter clock has not started.':'Preparing your room… Your encounter clock has not started.');
  const id=entryPending.id;setTimeout(()=>{if(entryPending?.id===id&&!entryPending.starting){entryPending=null;$('#unityFrame')?.contentWindow?.postMessage({type:'pcm-room-reset-entry'},location.origin);$('#go').disabled=false;$('#skipEntrance').disabled=false;setEntryStatus('The room did not finish responding. Retry, or enter with accessible controls.');$('#entryFallback').hidden=false;}},(S.visual_demo==='humgen-trial'||S.appearance?.model==='mpfb-young-woman')?45000:7000);
  if(roomFrameReady)dispatchEntrance();
}
function renderDoorway(){
  const st=S.station||{doorway:[],hidden_label:''};learnStationLabel(S.case_id,st.hidden_label);const pre=S.preset;
  view.innerHTML=`<div class="arrival-layout">
    <section class="arrival-scene card" aria-label="Outside the examination room"><div class="arrival-caption"><span class="eyebrow">${esc(st.hidden_label||stationTitle(S.case_id))}</span><h2>Outside the room</h2><p>Take a moment. Your patient is just inside.</p></div><div id="roomViewport"></div><div class="arrival-foot"><span class="arrival-dot" aria-hidden="true"></span>Encounter not started</div></section>
    <section class="doorway" aria-label="Posted station information"><div class="doorway-head"><span class="eyebrow">Posted beside the door</span><h1>Your station brief</h1><p class="small muted">Review this information before you enter.</p></div><div class="doorway-body">
      <ul class="doorway-lines">${(st.doorway||[]).map(l=>`<li>${esc(/^You have \d+ minutes/.test(l)?(isUntimedAttempt()?'This practice encounter is untimed.':'This encounter allows '+phaseAllowance(pre.encounter_s)+'.'):/^Vital signs (?:are|can be)/i.test(l)?'Vital signs are supplied at this station.':l)}</li>`).join('')}</ul>
      <section class="doorway-vitals" aria-labelledby="doorwayVitals"><div class="card-head"><h2 id="doorwayVitals">Vital signs</h2><span class="badge b-mute">Supplied information</span></div>${chartHtml({vitals:st.vitals||{},supplied_results:[]})}</section>
      <div class="doorway-facts"><div class="fact"><dt>Encounter</dt><dd>${isUntimedAttempt()?'Untimed':phaseAllowance(pre.encounter_s)}</dd></div>${pre.organize_s?'<div class="fact"><dt>Organize</dt><dd>'+phaseAllowance(pre.organize_s)+'</dd></div>':''}<div class="fact"><dt>SOAP</dt><dd>${isUntimedAttempt()?'Untimed':phaseAllowance(pre.note_s)}</dd></div></div>
      <p class="tiny muted">${pre.modified?'Practice timing is modified; exam rehearsal uses the course’s 14-minute encounter and 9-minute SOAP period. ':''}The encounter starts after entry, when your controls are ready.</p>
      <label class="motion-preference"><input id="entryReduced" type="checkbox" ${LS.get('reducedMotion')||window.matchMedia('(prefers-reduced-motion: reduce)').matches?'checked':''}> Reduce motion and skip the entrance animation</label>
      <div class="doorway-enter">
      <button class="btn primary big" id="go" type="button">Enter room <span aria-hidden="true">→</span></button><button class="btn ghost" id="skipEntrance" type="button">Skip animation &amp; enter</button>
      <p id="entryStatus" class="entry-status" role="status">Preparing the room. Review your station while it loads.</p><button class="btn sm ghost" id="entryFallback" type="button">Enter with accessible controls</button>
      </div>
    </div></section></div>`;
  $('#go').onclick=()=>beginEntrance(false);$('#skipEntrance').onclick=()=>beginEntrance(true);$('#entryFallback').onclick=()=>{if(entryPending?.starting)return;entryPending={id:crypto.randomUUID(),sid:S.id,skip:true,at:performance.now(),starting:false};completeEntrance(entryPending.id);};
  $('#entryReduced').onchange=e=>{LS.set('reducedMotion',e.target.checked);notifyPublicState();};mountPatientFrame();if(roomFrameReady)setEntryStatus('Ready when you are. Entering starts your encounter after the short transition.');
}

/* ======================================================================== */
/* 3. PATIENT ROOM                                                           */
/* ======================================================================== */

/* The bedside actions. Each one sends a real utterance, so the engine hears it
   exactly as if it had been typed, and the encounter carries the consent /
   draping / comfort thread instead of a row of dead buttons. */
const BEDSIDE = [
  { id:'introduce',    short:'Introduce yourself',
    say:"Hello, my name is Sebastian, I'm a student doctor and I'll be seeing you today." },
  { id:'confirm_name', short:'Confirm name and how to address them',
    say:'Can you confirm your name for me, and how would you like to be addressed?' },
  { id:'hand_hygiene', short:'Wash your hands',
    say:"I'm going to wash my hands before we start." },
  { id:'consent_exam', short:'Ask permission to examine',
    say:'Is it okay if I examine you now?' },
  { id:'gloves',       short:'Put on gloves',
    say:"I'm going to put on gloves before I examine you." },
  { id:'drape',        short:'Drape the patient',
    say:"I'm going to drape you so you stay covered." },
  { id:'gown_help',    short:'Help with the gown',
    say:'Let me help you with your gown.' },
  { id:'position_help',short:'Help them into position',
    say:'Let me help you lie back on the table.' },
  { id:'comfort_check',short:'Check they are comfortable',
    say:'Are you comfortable? Let me know if anything I do hurts.' },
  { id:'warn_cold',    short:'Warn before cold or pressure',
    say:"This might be cold — let me warm my hands first." }
];
/* Generic interview moves taught by the course (FIFE, barriers). Case-neutral:
   none of them names anything about this station. Offered only where the mode
   says prompts are allowed. */
const INTERVIEW_PROMPTS = [
  ['What do you think might be causing this?', 'F — ideas'],
  ['What worries you most about it?', 'F — fears'],
  ['How is this affecting your day to day?', 'F — function'],
  ['What were you hoping we could do today?', 'F — expectations'],
  ['Is there anything that would make that plan hard to follow?', 'practical barriers'],
  ['Before I move on — have I missed anything you wanted to tell me?', 'verification'],
  ['Do you have any questions or concerns before we finish?', 'closure']
];
// Only positions the encounter engine and patient rig can actually perform.
const POSITIONS = [
  ['seated','Seated on the table'],
  ['supine','Supine · face up'],
  ['standing','Standing beside the table'],
  ['prone','Prone · face down']
];
function recordedPosition(){
  return POSITIONS.some(p=>p[0]===S?.patient_posture)?S.patient_posture:'seated';
}
async function requestPosition(position, control){
  if(!S||S.phase!=='encounter')return;
  const sid=S.id;
  if(control)control.disabled=true;
  const response=await api(`/api/session/${sid}/room`,{
    action:'position',position,sessionId:sid,requestId:crypto.randomUUID(),renderer:'babylon'
  });
  if(S?.id!==sid)return;
  if(response.state)S=Object.assign({},S,response.state);
  room.position=recordedPosition();
  if(control){control.disabled=false;control.value=room.position;}
  if(response.error){toast(response.message||response.error);return;}
  (response.events||[]).forEach(deliverEvent);
  if(response.state?.transcript)paintStream(S.transcript||[]);
  notifyPublicState();
  toast(room.position===position?'Patient position updated.':'The patient remained in their previous position.');
}
const INSTRUMENTS = [
  ['', 'Any instrument', []],
  ['stethoscope','Stethoscope', ['auscultate']],
  ['hands','Hands only', ['palpate','percuss']],
  ['penlight','Penlight / otoscope / ophthalmoscope', ['inspect']],
  ['hammer','Reflex hammer, tuning fork, monofilament', ['special']]
];
const REFUSABLE = [
  ['gyn','Gynecological / pelvic examination'], ['rectal','Rectal examination'],
  ['genital','Genital examination'], ['breast','Breast examination'],
  ['corneal','Corneal reflex']
];

function renderRoom(){
  const m=mode(), chart=S.station_chart||{vitals:{},supplied_results:[],doorway:[]};
  view.innerHTML=`<div class="room room-integrated experience-room ${uiMeta(S.id).expandedPatient?'patient-focus':''}">
    <section class="unity-room card" aria-label="Interactive patient room">
      <div class="unity-heading"><div><span class="eyebrow">In the room together</span><h2>${esc(S.patient_name||'Your patient')}</h2></div><div class="patient-heading-actions"><span id="ptState" class="state-pill"><span class="dot" aria-hidden="true"></span><span class="txt">Ready to listen</span></span><button class="btn sm ghost" id="patientFocus" type="button" aria-pressed="${!!uiMeta(S.id).expandedPatient}">${uiMeta(S.id).expandedPatient?'Return to split view':'Expand patient view'}</button></div></div>
      <div id="roomViewport"></div>
      ${S.visual_demo==='humgen-trial'?'<div class="trial-disclosure">Human Generator free trial · one male character · original trial watermarks retained</div>':''}
      <div class="patient-toolbar" aria-label="Encounter tools">
        <button class="btn primary" id="toolExam" type="button">Examine patient <span aria-hidden="true">↗</span></button>
        <button class="btn" id="toolChart" type="button">Doorway &amp; vitals</button>
        ${m.coach?'<button class="btn ghost" id="quickUnstuck" type="button">Get unstuck</button>':''}
        <span class="tiny muted" id="unityStatus">${patientDisplayLabel()}</span>
      </div>
      <details class="scene-help"><summary>View &amp; examination controls</summary><p>Use Face, Upper body, Full patient or Reset to frame your patient. Choose Adjust view for deliberate camera movement. Ordinary scrolling and browser zoom remain available. Select a body region or choose Examine patient; a region opens your choices, and only a completed examination releases its findings. Expressions and demeanor do not establish examination findings.</p><button class="btn sm" id="unityFallback" type="button">Accessible examination controls</button><p class="tiny muted">Keyboard: Alt+1 conversation · Alt+2 examination · Alt+3 doorway chart.</p></details>
    </section>
    <section class="convo card" aria-label="Talk with your patient">
      <div class="conversation-heading"><div><span class="eyebrow">Listen · ask · connect</span><h2>Conversation</h2></div><span class="tiny muted" id="turnCount"></span><button class="btn sm ghost" id="toggleRecord" aria-pressed="false">Full record</button></div>
      ${S.branch?.is_branch?'<p class="branch-reminder small">A separate practice retry. Your original attempt is preserved.</p>':''}
      <div id="voiceBar" class="voice-bar hidden" role="status"></div>
      <div id="stream" class="stream" role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversation with the patient" tabindex="0"></div>
      <div class="composer">
        <div id="interim" class="interim" aria-live="polite"></div>
        <div class="composer-row">
          <span class="mic-wrap ${S.interaction_mode==='voice'?'':'hidden'}"><button class="btn mic-btn" id="btnMic" type="button" aria-pressed="false" aria-label="Microphone: click to start or stop hands-free listening.">Mic</button></span>
          <label class="sr-only" for="say">What you say to the patient, or the examination you perform</label>
          <textarea id="say" rows="2" autocomplete="off" spellcheck="true" placeholder="Talk to ${esc((S.patient_name||'your patient').split(' ')[0])}…"></textarea>
          <button class="btn sm ghost" id="stopPatient" type="button" disabled hidden aria-label="Stop patient speech">Stop speech</button><button class="btn primary" id="btnSay" type="button" aria-label="Send to patient">Send <span aria-hidden="true">↑</span></button>
        </div><p class="hint">Enter to send · Shift+Enter for a new line. Speak naturally, one question at a time.</p>
      </div>
    </section>
    <div class="room-left">
      ${m.coach?`<details class="card bedside-card"><summary>Bedside actions <span class="small muted">Introduce yourself, ask permission, offer comfort</span></summary><p class="tiny muted">Choose an action to say it to your patient. It records your stated behavior.</p><div class="rapport" id="rapport"></div><button class="btn sm ghost" id="toolPrompts">Explore interview moves</button></details><div id="coachDock"></div>`:''}
    </div>
    <div class="room-right card encounter-next"><div><span class="eyebrow">When you are ready</span><h3>Bring the encounter together.</h3><p class="small muted">Finish your conversation, then move into documentation.</p></div><div class="row"><button class="btn ghost sm" id="toolRefuse">Propose a sensitive examination</button><button class="btn" id="btnEnd">Finish encounter →</button></div><span class="tiny muted" id="examProgressSub"></span></div>
  </div>`;
  mountPatientFrame();paintRapport();paintStream(S.transcript||[]);
  $('#stopPatient').onclick=interruptPatient;$('#btnSay').onclick=()=>sendSay();$('#say').onkeydown=composerKey;$('#say').value=draftValue('conversation',S.id)||'';$('#say').onfocus=()=>requestAnimationFrame(()=>{const pair=$('.experience-room'),patient=$('.unity-room'),conversation=$('.convo');if(innerWidth>820&&pair&&patient&&conversation&&Math.max(patient.offsetHeight,conversation.offsetHeight)<innerHeight-76){window.scrollTo({top:Math.max(0,pair.getBoundingClientRect().top+scrollY-76),behavior:'instant'});positionRoomFrame();}});$('#say').oninput=e=>{autogrow(e.target);keepDraft('conversation',S.id,e.target.value);setPatientState(e.target.value?'listening':'idle');notifyPublicState();};
  $('#btnEnd').onclick=confirmEnd;$('#toolExam').onclick=openExamPanel;$('#unityFallback').onclick=openExamPanel;
  $('#toolChart').onclick=()=>openOverlay('Doorway information & vital signs',`<div class="doorway-vitals">${chartHtml(chart)}</div><ul class="doorway-lines">${(chart.doorway||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`);
  if($('#quickUnstuck'))$('#quickUnstuck').onclick=()=>{const guide=$('#encounterGuide');if(guide){guide.scrollIntoView({block:'center',behavior:LS.get('reducedMotion')?'instant':'smooth'});$('#unstuckButton')?.click();}};
  $('#patientFocus').onclick=e=>{const active=$('.experience-room').classList.toggle('patient-focus');setUiMeta(S.id,{...uiMeta(S.id),expandedPatient:active});e.currentTarget.setAttribute('aria-pressed',String(active));e.currentTarget.textContent=active?'Return to split view':'Expand patient view';positionRoomFrame();$('.unity-room').scrollIntoView({block:'start',behavior:LS.get('reducedMotion')||window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});};
  $('#toggleRecord').onclick=e=>{const active=$('.convo').classList.toggle('full-record');e.currentTarget.setAttribute('aria-pressed',String(active));e.currentTarget.textContent=active?'Dialogue view':'Full record';};
  $('#unityFrame').onload=notifyPublicState;const tp=$('#toolPrompts');if(tp)tp.onclick=openPromptsPanel;$('#toolRefuse').onclick=openRefusePanel;
  if(S.interaction_mode==='voice')setupVoice();paintExamProgress();setPatientState('idle');notifyPublicState();
}

function composerKey(e) {
  if (e.key !== 'Enter' || e.shiftKey || e.altKey || e.isComposing) return;
  e.preventDefault();
  if (e.key === 'Enter') sendSay();
}
function autogrow(el){
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}
function chartHtml(chart){
  const vitals=chart.vitals||{};const labels={P:'Pulse',R:'Respirations',T:'Temperature',Ht:'Height',Wt:'Weight','Pulse Ox':'Oxygen saturation',BP:'Blood pressure'};
  return `<dl class="chart-grid">${Object.entries(vitals).map(([k,v])=>`<div class="vital-tile"><dt>${esc(labels[k]||k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>${(chart.supplied_results||[]).map(r=>`<div class="supplied"><b>${esc(r.label)}</b><span class="val">${esc(r.value)}</span></div>`).join('')}<p class="tiny muted supplied-note">Supplied at the station. You may document these values as provided.</p>`;
}

/* --- patient presence ---------------------------------------------------- */
/* A deliberately abstract portrait: silhouette, hair mass and skin tone vary by
   a hash of the case id so each patient is visually distinct and stable, and
   nothing in the drawing carries a clinical sign. No pallor, no diaphoresis, no
   guarding — a learner must earn every finding from the engine. */
function portraitSvg(caseId, name){
  let h = 0; const id = caseId || '';
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  const tone = ['#e8c4a8','#d8ab86','#c08e68','#9d6f4e','#7a5236'][h % 5];
  const hairTone = ['#3b2f2a','#5a4436','#1f1b18','#6d5a4a','#2b2b30'][(h >> 3) % 5];
  const longHair = ((h >> 6) & 1) === 1;
  const gown = ['#8fb3c4','#a9bfae','#b7aec9','#c3b49b'][(h >> 9) % 4];
  return `<svg viewBox="0 0 120 132" role="img"
      aria-label="Stylized portrait of ${esc(name || 'the standardized patient')}. It is drawn from the case identifier and carries no clinical findings.">
    <rect x="0" y="0" width="120" height="132" fill="none"/>
    <path d="M18,132 Q20,96 44,88 L76,88 Q100,96 102,132 Z" fill="${gown}" opacity=".9"/>
    <rect x="50" y="72" width="20" height="20" rx="6" fill="${tone}"/>
    ${longHair ? `<path d="M32,58 Q30,104 42,110 L46,86 Q34,80 34,56 Z" fill="${hairTone}"/>
       <path d="M88,58 Q90,104 78,110 L74,86 Q86,80 86,56 Z" fill="${hairTone}"/>` : ''}
    <ellipse cx="60" cy="50" rx="26" ry="30" fill="${tone}"/>
    <path d="M34,48 Q36,20 60,20 Q84,20 86,48 Q86,32 74,26 Q60,34 46,26 Q34,32 34,48 Z"
      fill="${hairTone}"/>
    <ellipse cx="50" cy="50" rx="2.6" ry="3" fill="#2b2b30"/>
    <ellipse cx="70" cy="50" rx="2.6" ry="3" fill="#2b2b30"/>
    <path d="M52,64 Q60,68 68,64" stroke="#2b2b30" stroke-width="1.6" fill="none"
      stroke-linecap="round" opacity=".7"/>
  </svg>`;
}
function setPatientState(state, detail){
  const el = $('#ptState'); if (!el) return;
  const map = { idle:['','Ready to listen'], listening:['listening','Listening'],
    thinking:['thinking','Thinking…'], preparing:['thinking','Preparing speech…'], speaking:['speaking','Speaking'],
    examining:['examining', detail || 'Being examined'] };
  // "Stop speech" only exists while there is speech to stop. Parked beside
  // Send as a permanently greyed button it read as a broken control.
  const stop=$('#stopPatient');if(stop){const live=['speaking','preparing'].includes(state);stop.disabled=!live;stop.hidden=!live;}
  const pair = map[state] || map.idle;
  el.className = 'state-pill ' + pair[0];
  $('.txt', el).textContent = pair[1];
}

/* --- bedside strip --------------------------------------------------------
   The engine records a courtesy when it hears one, and returns the courtesy's
   own label. What is ticked here is therefore what the engine recorded, cached
   per session so a reload does not forget it, and re-derived from the frozen
   transcript when the cache is empty. */
function courtesyStore(){ return (S && LS.get('courtesy.' + S.id)) || {}; }
function markCourtesy(label){
  if (!S) return;
  const hit = BEDSIDE.filter(b => matchesCourtesy(b, label))[0];
  const map = courtesyStore();
  if (hit) map[hit.id] = true; else map['_other'] = true;
  LS.set('courtesy.' + S.id, map);
}
/* The engine returns the courtesy's own label, not its id, so the label is
   matched back to the bedside action it belongs to. A label that matches
   nothing is still recorded — as "something else you said" — rather than
   silently dropped. */
const COURTESY_LABEL_KEY = {
  introduce:'introduce yourself', confirm_name:'confirm patient name',
  hand_hygiene:'wash or sanitize', gloves:'apply gloves',
  consent_exam:'ask permission', drape:'drape the patient',
  gown_help:'help with the gown', position_help:'help lying down',
  comfort_check:'comfort', warn_cold:'warn before touching'
};
function matchesCourtesy(b, label){
  const key = COURTESY_LABEL_KEY[b.id];
  return !!key && String(label || '').toLowerCase().indexOf(key) >= 0;
}
function courtesyDone(){
  // The ENGINE's recognised evidence is the source of truth. It previously
  // marked an item done only when the typed text exactly equalled the helper
  // button's canned sentence, so asking "what is your name" in your own words
  // — and getting an answer — left the item looking untouched. The engine
  // already records a courtesy event for the behaviour however it was phrased;
  // this reads that, so independent and assisted work count the same.
  const map = courtesyStore();
  (S?.courtesy_done || []).forEach(id => { map[id] = true; });
  // The frozen transcript still backs a reload whose local cache is empty.
  (S?.transcript || []).forEach(t => {
    if (t.kind !== 'student_utterance') return;
    BEDSIDE.forEach(b => { if (t.text === b.say) map[b.id] = true; });
  });
  return map;
}
/* Sub-components recognised per courtesy, so a two-part item can show what is
   genuinely still outstanding rather than all-or-nothing. */
function courtesyParts(){ return (S && S.courtesy_components) || {}; }
function paintRapport(){
  const wrap = $('#rapport'); if (!wrap) return;
  const done = courtesyDone();
  wrap.innerHTML = BEDSIDE.map(b => {
    const isDone = !!done[b.id];
    return `<button type="button" class="btn rap ${isDone ? 'done' : ''}" data-say="${esc(b.say)}"
      ${isDone ? 'disabled aria-disabled="true"' : ''}
      aria-label="${esc(b.short)}${isDone ? ' — already done' : ''}">
      <span class="tick" aria-hidden="true">✓</span>
      <span class="lbl">${esc(b.short)}</span></button>`;
  }).join('');
  $$('.rap', wrap).forEach(btn => { btn.onclick = () => {
    if (btn.disabled) return;
    sendSay(btn.dataset.say);
  }; });
}

/* --- conversation --------------------------------------------------------- */
async function sendSay(textOverride, confidence){
  if(!S||S.phase!=='encounter')return;const sid=S.id;
  const input = $('#say');
  const text = (textOverride !== undefined ? textOverride : (input ? input.value : '')).trim();
  if (!text) return;
  // Secondary defence, not the fix: if a recognition event is somehow
  // delivered twice, the identical text arrives within milliseconds. Saying
  // the same thing again deliberately takes far longer than this window, so a
  // real repeated phrase is still sent as its own turn.
  if (textOverride !== undefined) {
    const now = Date.now();
    if (text === voice.lastSentText && now - voice.lastSentAt < 1200) return;
    voice.lastSentText = text; voice.lastSentAt = now;
  }
  if(S.ai_patient_enabled&&window.pcmAISend)return window.pcmAISend(text);
  if (textOverride === undefined && input) {keepDraft('conversation',sid,text);input.value = '';autogrow(input);}
  pushTurn('me', 'You', text);
  setPatientState('thinking');
  const conf = confidence !== undefined ? confidence : voice.pending;
  voice.pending = null;
  const r = await api(`/api/session/${S.id}/say`, {
    text, mode: S.interaction_mode === 'voice' ? 'voice' : 'type', confidence: conf
  });
  if(!S||S.id!==sid)return;
  if (r.error === 'offline') { if(input&&textOverride===undefined){input.value=text;autogrow(input);}pushTurn('bad', 'Simulator', r.message); setPatientState('idle'); return; }
  if (r.error === 'closed') { pushTurn('sys', 'Simulator', r.message); return refresh(); }
  if (r.uncertain) pushTurn('sys', 'Simulator', 'Speech recognition confidence was low for ' +
    'that turn. The text is kept as heard and will not be scored as a definite error.');
  if(!r.error&&textOverride===undefined)clearMatchingDraft('conversation',sid,text);
  if (r.state) S = Object.assign({}, S, r.state);
  const events = r.events || [];
  // An examination that is still occupying its time owns the patient's state,
  // so the turn that started it must not reset the pill back to idle.
  const examining = events.some(e =>
    ['exam_started','finding','no_result','not_simulated'].indexOf(e.kind) >= 0 &&
    (e.duration_s || 0) * 1000 >= 400);
  events.forEach(deliverEvent);
  paintRapport(); paintExamProgress(); paintTurnCount(); notifyPublicState();
  if (!examining && !events.some(e => e.kind === 'patient')) setPatientState('idle');
}
/* An examination narrated in the conversation occupies its time exactly as one
   started from the examination surface does: the outcome is held back until the
   maneuver completes, and the room says what is happening meanwhile. */
function deliverEvent(ev){
  if(!ev)return;
  if(ev.kind==='exam_started'){
    pushTurn('sys','Examination in progress',ev.text || ('Examining '+(ev.label||'the patient')+'. Findings appear when the action finishes.'));
    setPatientState('examining',ev.label||'Examination in progress');
    notifyPublicState(); return;
  }
  pushEvent(ev);
}
function pushEvent(ev){
  if (!ev || !S) return;
  const name = S.patient_name || 'Patient';
  switch (ev.kind) {
    case 'patient':
      pushTurn('pt', name, ev.text,
        ev.volunteered ? '<span class="badge b-info">volunteered</span>' : '');
      if (voice.speak) speak(ev.text); else setPatientState('idle');
      return;
    case 'finding':
      recordPerformed(ev);
      pushTurn('sim', 'Examination finding — ' + ev.label, ev.text,
        ev.duration_s ? '<span class="badge b-mute">' + ev.duration_s + 's</span>' : '',
        (ev.components || []).length ? 'Components covered: ' + ev.components.join(', ') : '');
      if (ev.assisted_timing) pushTurn('sys', 'Simulator',
        'Assisted timing is on in this build, so this examination did not occupy its ' +
        'full clinical duration. The real station gives you no such discount.');
      return;
    case 'no_result':
      recordPerformed(ev);
      pushTurn('sim', 'No result — ' + (ev.label || 'examination'), ev.text ||
        'That examination produced no result.', '<span class="badge b-warn">no result</span>',
        mode().coach && (ev.missing_components || []).length
          ? 'Not covered: ' + ev.missing_components.join(', ') : '');
      return;
    case 'not_simulated':
      pushTurn('sys', 'Simulator', ev.text ||
        'This station does not simulate that examination.');
      return;
    case 'exam_interrupted':
      pushTurn('sys', 'Simulator', ev.text ||
        'The examination was interrupted before it finished, so nothing was released.');
      return;
    case 'exam_busy':
      pushTurn('sys', 'Simulator', ev.text ||
        'An examination is already running. Wait for it to finish.');
      return;
    case 'refusal':
      pushTurn('sim', 'Patient refuses', ev.text, '<span class="badge b-warn">refused</span>');
      return;
    case 'sim_note':
      pushTurn('sys', 'Simulator', ev.text); return;
    case 'courtesy':
      markCourtesy(ev.label);
      pushTurn('sys', 'Recorded', ev.label); return;
    case 'counseling':
      pushTurn('sys', 'Recorded — discussed with patient', (ev.topics || []).join(', '));
      return;
    default:
      if (ev.text) pushTurn('sys', 'Simulator', ev.text);
  }
}
/* Auto-scrolling is for a log you are already at the end of. Pinning the
   transcript to the bottom on every repaint threw away the place of anyone who
   had scrolled back to re-read an earlier answer -- and there is no other copy
   of the conversation to read. */
const STREAM_PIN = 64;
function streamAtBottom(s){ return s.scrollHeight - s.scrollTop - s.clientHeight <= STREAM_PIN; }
/* Whether the student is following the newest turn. Held as the last DELIBERATE
   scroll rather than measured at paint time: the log is re-parented between
   panels, and a measurement taken mid-move reads as "scrolled to the top". */
function streamPinned(s){ return !s || s.dataset.pinned !== '0'; }
function streamToBottom(s){
  requestAnimationFrame(() => requestAnimationFrame(() => {
    s.scrollTop = s.scrollHeight; s.dataset.pinned = '1'; markStreamCaughtUp();
  }));
}
function streamCatchUp(s, wasAtBottom){
  if (wasAtBottom) { streamToBottom(s); return; }
  markStreamBehind();
}
function markStreamBehind(){
  const s = $('#stream'); if (!s) return;
  let jump = document.getElementById('streamJump');
  if (!jump) {
    jump = document.createElement('button');
    jump.id = 'streamJump'; jump.type = 'button'; jump.className = 'stream-jump';
    jump.innerHTML = 'New below <span aria-hidden="true">\u2193</span>';
    jump.onclick = () => { s.scrollTop = s.scrollHeight; markStreamCaughtUp(); };
  }
  // The log moves between panels, so re-home the marker beside it every time.
  const host = s.parentElement || s;
  if (jump.parentElement !== host) host.append(jump);
  jump.hidden = false;
}
function markStreamCaughtUp(){ const jump = document.getElementById('streamJump'); if (jump) jump.hidden = true; }
function watchStream(s){
  if (!s || s.dataset.pinWatch) return;
  s.dataset.pinWatch = '1'; if (!s.dataset.pinned) s.dataset.pinned = '1';
  // The panel around the log settles AFTER the first paint -- the coach card
  // resolves, the composer grows -- and a scroll applied before that left the
  // student staring at the top of a finished conversation. Re-pin on resize
  // while they are still following the newest turn.
  if (window.ResizeObserver) new ResizeObserver(() => {
    if (s.dataset.moving || !s.clientHeight || !streamPinned(s)) return;
    s.scrollTop = s.scrollHeight;
  }).observe(s);
  s.addEventListener('scroll', () => {
    // re-parenting resets scrollTop, and a hidden panel measures 0/0/0 -- which
    // reads as "at the bottom" and silently re-pins a reader who had scrolled
    // back. Neither is a reading position.
    if (s.dataset.moving || !s.clientHeight) return;
    const at = streamAtBottom(s); s.dataset.pinned = at ? '1' : '0';
    if (at) markStreamCaughtUp();
  }, {passive:true});
}
window.pcmStreamPinned = streamPinned;
window.pcmStreamToBottom = streamToBottom;
function pushTurn(cls, who, text, tag, sub){
  const s = $('#stream'); if (!s) return;
  watchStream(s);
  const wasAtBottom = streamPinned(s);
  // Read the encounter clock the same way every other face on the page does, so
  // a live label and the frozen transcript agree.
  const elapsed = S.phase_started_at ? Math.max(0,now()-S.phase_started_at) : (S.elapsed_ms||0);
  const d = document.createElement('div');
  d.className = 'turn ' + cls;
  d.innerHTML = `<div class="who"><span>${esc(who)}</span>${tag || ''}
      <span class="t">${mmss(elapsed)}</span></div>
    <div class="bubble">${esc(text)}${sub ? `<div class="comps-line">${esc(sub)}</div>` : ''}</div>`;
  $('.conversation-empty',s)?.remove();s.appendChild(d);
  watchStream(s); streamCatchUp(s, wasAtBottom);
}
function paintStream(rows){
  const s = $('#stream'); if (!s) return;
  watchStream(s);
  const wasAtBottom = streamPinned(s);
  // Rebuilding the whole log wiped any text the student had selected to copy
  // into their note, and flashed the scroll position. When the new transcript
  // simply CONTINUES the rendered one -- which is every ordinary turn -- keep
  // what is on screen and append the difference.
  const rendered = [...s.querySelectorAll('.turn')];
  const signature = r => (r.kind||'') + '\u0000' + (r.text||'');
  const drawn = s.dataset.signatures ? JSON.parse(s.dataset.signatures) : null;
  const next = (rows||[]).map(signature);
  let from = 0;
  const continues = Array.isArray(drawn) && drawn.length <= next.length
    && rendered.length === drawn.length
    && drawn.every((v,i) => v === next[i]);
  if (continues) { from = drawn.length; if (from === next.length) { s.dataset.signatures = JSON.stringify(next); return; } }
  else { s.innerHTML = ''; }
  s.dataset.signatures = JSON.stringify(next);
  const name = S.patient_name || 'Patient';
  const map = { student_utterance:['me','You'], patient_reply:['pt', name],
    exam_finding:['sim','Examination finding'], exam_refused:['sim','Patient refuses'],
    station_info:['station','Station information'], simulator:['sys','Simulator'] };
  (rows || []).forEach((r, index) => {
    if(r.kind==='exam_finding'&&r.meta?.label)recordPerformed({kind:'finding',label:r.meta.label,components:r.meta.components||[]});
    if (index < from) return;
    const m = map[r.kind] || ['sys', 'Simulator'];
    const d = document.createElement('div');
    d.className = 'turn ' + m[0];
    d.innerHTML = `<div class="who"><span>${esc(m[1])}</span>
        <span class="t">${esc(r.time)}</span></div>
      <div class="bubble">${esc(r.text)}</div>`;
    s.appendChild(d);
  });
  if(!(rows||[]).some(r=>['student_utterance','patient_reply','exam_finding'].includes(r.kind)))s.insertAdjacentHTML('beforeend',`<div class="conversation-empty"><span aria-hidden="true">◌</span><p>${mode().coach?'Your patient is ready to meet you. Start with an introduction and an open invitation.':'Your patient is ready. Type or speak when you are ready to begin.'}</p></div>`);
  watchStream(s); streamCatchUp(s, wasAtBottom || !continues);
  paintTurnCount();
}
function paintTurnCount(){
  const el = $('#turnCount'); if (!el) return;
  const n = (S.transcript || []).filter(t => t.kind === 'student_utterance').length;
  el.textContent = n + ' turn' + (n === 1 ? '' : 's');
}
async function confirmEnd(){
  const sid=S?.id;
  // A running examination is stopped by cancelRunningExam() below and releases
  // nothing. Ending on top of one silently threw the wait away, so say it.
  const running=S?.pending_exam?(' The examination you started ('+
      (S.pending_exam.source_text||'').replace(/^Perform:\s*/,'').replace(/\s*\(.*$/,'').trim()+
      ') is still running and will be stopped without a finding.'):'';
  if (!await confirmChoice('End the encounter now? The record freezes and no further information ' +
               'can be obtained from the patient.'+running,
               {title:'End the encounter?',confirm:'End encounter',cancel:'Keep interviewing'})) return;
  if(!S||S.id!==sid||S.phase!=='encounter')return;
  stopVoice(); cancelRunningExam();
  const next = await post(`/api/session/${S.id}/end_encounter`);
  if (next.error) { toast(next.message || 'Could not end the encounter.'); return; }
  S = next; renderPhase(true);
}

/* ======================================================================== */
/* overlay panels (tools that open when needed)                              */
/* ======================================================================== */
function openOverlay(title, bodyHtml, onMount){
  lastFocus = document.activeElement;
  overlayRoot.innerHTML = `<div class="overlay" role="presentation">
    <div class="overlay-panel" role="dialog" aria-modal="true" aria-labelledby="ovTitle">
      <div class="overlay-head"><h2 id="ovTitle">${esc(title)}</h2><div class="spacer"></div>
        <button class="btn sm" id="ovClose" type="button">Close</button></div>
      <div class="overlay-body" id="ovBody">${bodyHtml}</div>
    </div></div>`;
  overlay = $('.overlay', overlayRoot);
  $('#ovClose').onclick = () => closeOverlay();
  overlay.addEventListener('mousedown', e => { if (e.target === overlay) closeOverlay(); });
  document.addEventListener('keydown', overlayKeys, true);
  if (onMount) onMount($('#ovBody'));
  const focusable = $('#ovBody button, #ovBody input, #ovBody select, #ovBody a') || $('#ovClose');
  if (focusable) focusable.focus();
}
function overlayKeys(e){
  if (!overlay) return;
  if (e.key === 'Escape') { e.preventDefault(); closeOverlay(); return; }
  if (e.key !== 'Tab') return;
  const items = $$('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])', overlay)
    .filter(el => !el.disabled && el.offsetParent !== null);
  if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}
function closeOverlay(silent){
  if (!overlay) { overlayRoot.innerHTML = ''; return; }
  document.removeEventListener('keydown', overlayKeys, true);
  overlayRoot.innerHTML = ''; overlay = null;
  if (!silent && lastFocus && lastFocus.focus) { try { lastFocus.focus(); } catch(e){} }
}

function openPromptsPanel(){
  openOverlay('Interview moves', `
    <p class="small muted">Generic moves the course teaches — F.I.F.E., practical
    barriers, verification and closure. None of them names anything about this station,
    and none of them tells you what you have missed. They are hidden entirely in exam
    rehearsal.</p>
    <div class="stack">${INTERVIEW_PROMPTS.map(pair => `
      <button class="btn tool-btn" type="button" data-say="${esc(pair[0])}">
        <span class="ico" aria-hidden="true">&#8250;</span>
        <span><span class="t-name">${esc(pair[0])}</span><span class="t-sub">${esc(pair[1])}</span></span>
      </button>`).join('')}</div>`, body => {
    $$('[data-say]', body).forEach(b => { b.onclick = () => {
      const el = $('#say'); if (el) { el.value = b.dataset.say; autogrow(el); }
      closeOverlay(); if (el) el.focus(); }; });
  });
}
window.pcmOpenRefusePanel=()=>openRefusePanel();
function openRefusePanel(){
  openOverlay('Propose a refusable examination', `
    <p class="small">The syllabus form is: &ldquo;At this point, I would do a (xxx)
    exam.&rdquo; The patient declines, and you then document the refusal in Objective in
    the wording the simulator gives you. Proposing it properly is what earns the credit —
    performing it is not on offer.</p>
    <div class="stack">${REFUSABLE.map(pair => `
      <button class="btn tool-btn" type="button" data-k="${esc(pair[0])}">
        <span class="ico" aria-hidden="true">&#9995;</span>
        <span><span class="t-name">${esc(pair[1])}</span>
        <span class="t-sub">Named, not performed; the patient declines and you document that</span></span>
      </button>`).join('')}</div>`, body => {
    $$('[data-k]', body).forEach(b => { b.onclick = () => proposeRefusal(b.dataset.k); });
  });
}
async function proposeRefusal(key){
  if(!S||S.phase!=='encounter')return;
  const sid=S.id;closeOverlay();
  const r=await api(`/api/session/${sid}/propose_refusal`,{key});
  if(S?.id!==sid)return;
  if(r.error){toast(r.message||'That could not be proposed now.');return;}
  if(r.state)S=Object.assign({},S,r.state);
  (r.events||[]).forEach(deliverEvent);
  notifyPublicState();
}

/* ======================================================================== */
/* 3b. EXAMINATION SURFACE                                                   */
/* ======================================================================== */
const WHOLE_BODY = ['General','Skin','Neurologic','Osteopathic'];

function catalog(){ return BOOT.exam_catalog || S.exam_catalog || []; }
let REGION_OF = null;
function regionOf(mid){
  if (!REGION_OF) { REGION_OF = {};
    catalog().forEach(g => g.maneuvers.forEach(m => { REGION_OF[m.id] = g.region; })); }
  return REGION_OF[mid];
}
/* An examination narrated in the conversation comes back with the maneuver's
   label, not its id, so the label is matched back to the catalog. That keeps the
   map of what has been performed the same whether the maneuver was started from
   the surface or typed into the room. */
function recordPerformed(ev){
  if (!ev || !ev.label || !S) return;
  const lab = String(ev.label).toLowerCase();
  let hit = null;
  catalog().forEach(g => g.maneuvers.forEach(m => {
    if (!hit && m.label.toLowerCase() === lab) hit = m.id; }));
  if (!hit) return;
  const prev = room.performed[hit] || { components: [] };
  const comps = (ev.components || []).slice();
  prev.components.forEach(c => { if (comps.indexOf(c) < 0) comps.push(c); });
  room.performed[hit] = { components: comps };
  savePerformed();
}
function performedMap(){ return room.performed || {}; }
function savePerformed(){ if (S) LS.set('performed.' + S.id, room.performed); }
function performedByRegion(){
  const out = {};
  Object.keys(performedMap()).forEach(mid => {
    const region = regionOf(mid);
    if (region) out[region] = (out[region] || 0) + 1;
  });
  return out;
}
function openExamPanel(){
  openOverlay('Examination', examPanelHtml(), body => { wireExamPanel(body); });
}
/* The tiles are recomputed rather than left as they were rendered, so a
   maneuver that has just completed is counted the moment it completes. */
function examSummaryHtml(){
  const byRegion = performedByRegion();
  const donen = Object.keys(performedMap()).length;
  return `<div class="es"><div class="n">${donen}</div><div class="k">maneuvers performed</div></div>
    <div class="es"><div class="n">${Object.keys(byRegion).length}</div><div class="k">regions touched</div></div>
    <div class="es"><div class="n" data-clock>--:--</div><div class="k">encounter left</div></div>`;
}
function paintExamSummary(body){
  const host = body ? $('.exam-summary', body) : $('.exam-summary');
  if (host) { host.innerHTML = examSummaryHtml(); paintClock(); }
}
function examPanelHtml(){
  room.position=recordedPosition();
  const groups = catalog();
  const byRegion = performedByRegion();
  const total = groups.reduce((n, g) => n + g.maneuvers.length, 0);
  return `
  <div id="examRunning"></div>
  <div class="exam-summary">${examSummaryHtml()}</div>
  <div class="progressbar" data-clock-pct aria-hidden="true"><span style="width:0%"></span></div>

  <div class="exam-layout" style="margin-top:var(--sp-4)">
    <div>
      <div class="bodymap">
        <div class="row" style="margin-bottom:var(--sp-2)">
          <div class="seg" role="group" aria-label="Body map view">
            <button type="button" class="segbtn" data-bmview="front"
              aria-pressed="${room.view === 'front'}">Front</button>
            <button type="button" class="segbtn" data-bmview="back"
              aria-pressed="${room.view === 'back'}">Back</button>
          </div>
        </div>
        <div id="bodyMapHost">${bodyMapSvg(room.view, byRegion)}</div>
        <p class="tiny muted" style="margin-top:var(--sp-2)">The map is a shortcut. Every
        region it offers, and the four that are not localizable, are in the list below and
        work from the keyboard alone.</p>
      </div>

      <div class="card tight" style="margin-top:var(--sp-3)">
        <h3 style="font-size:var(--fs-md)">Regions</h3>
        <div class="region-list" id="regionList" role="group" aria-label="Examination regions">
          <button type="button" class="btn rbtn" data-region=""
            aria-pressed="${!room.region}">All regions <span class="cnt">${total}</span></button>
          ${groups.map(g => `<button type="button" class="btn rbtn ${byRegion[g.region] ? 'covered' : ''}"
            data-region="${esc(g.region)}" aria-pressed="${room.region === g.region}">
            ${esc(g.region)}${WHOLE_BODY.indexOf(g.region) >= 0 ? ' <span class="tiny muted">(whole body)</span>' : ''}
            <span class="cnt">${byRegion[g.region] ? byRegion[g.region] + '/' : ''}${g.maneuvers.length}</span></button>`).join('')}
        </div>
      </div>

      <div class="card tight" style="margin-top:var(--sp-3)">
        <h3 style="font-size:var(--fs-md)">Positioning</h3>
        <label class="sr-only" for="posSel">Patient position</label>
        <select id="posSel">${POSITIONS.map(p =>
          `<option value="${p[0]}" ${room.position === p[0] ? 'selected' : ''}>${esc(p[1])}</option>`).join('')}</select>
        <p class="tiny muted" style="margin-top:var(--sp-2)">A position change is recorded only after the patient responds. The same position is used in the 3D room and encounter record. Seated, supine, standing and prone positions are available. Positioning alone does not establish an examination finding.</p>

        <h3 style="font-size:var(--fs-md);margin-top:var(--sp-3)">Instrument</h3>
        <label class="sr-only" for="instSel">Instrument</label>
        <select id="instSel">${INSTRUMENTS.map(i =>
          `<option value="${i[0]}" ${room.instrument === i[0] ? 'selected' : ''}>${esc(i[1])}</option>`).join('')}</select>
        <p class="tiny muted" style="margin-top:var(--sp-2)">This filters the list to the
        maneuvers that use it. The simulator does not model instruments and does not grade
        the choice.</p>
      </div>
    </div>

    <div>
      <div class="row" style="margin-bottom:var(--sp-3)">
        <label class="sr-only" for="manSearch">Search maneuvers</label>
        <input type="search" id="manSearch" placeholder="Search maneuvers…" style="max-width:260px">
        <span class="tiny muted" id="manCount"></span>
      </div>
      <div id="manList"></div>
    </div>
  </div>`;
}

/* Schematic anterior / posterior figures. Each hit area is a real button in the
   tab order with its own accessible name. Nothing on the figure encodes a
   finding — it is a locator, not a picture of this patient. */
function bodyMapSvg(which, byRegion){
  const hit = (region, shape, label) => `
    <g class="bm-region ${byRegion[region] ? 'covered' : ''}" role="button" tabindex="0"
       data-region="${esc(region)}" aria-pressed="${room.region === region}"
       aria-label="${esc(label || region)}">
      <title>${esc(label || region)}</title>${shape}</g>`;
  const body = which === 'front' ? `
    <ellipse cx="60" cy="26" rx="15" ry="18" class="bm-body bm-skin"/>
    <rect x="53" y="41" width="14" height="9" class="bm-body bm-skin"/>
    <path d="M38,50 Q60,44 82,50 L86,102 L82,152 L38,152 L34,102 Z" class="bm-body bm-gown"/>
    <path d="M38,52 L23,60 L17,118 L26,121 L33,66 Z" class="bm-body bm-skin"/>
    <path d="M82,52 L97,60 L103,118 L94,121 L87,66 Z" class="bm-body bm-skin"/>
    <path d="M41,152 L39,212 L43,250 L53,250 L56,212 L58,154 Z" class="bm-body bm-skin"/>
    <path d="M79,152 L81,212 L77,250 L67,250 L64,212 L62,154 Z" class="bm-body bm-skin"/>
    <line x1="60" y1="50" x2="60" y2="152" class="bm-line" opacity=".3"/>`
  : `
    <ellipse cx="60" cy="26" rx="15" ry="18" class="bm-body bm-skin"/>
    <rect x="53" y="41" width="14" height="9" class="bm-body bm-skin"/>
    <path d="M38,50 Q60,44 82,50 L86,102 L82,152 L38,152 L34,102 Z" class="bm-body bm-gown"/>
    <path d="M38,52 L23,60 L17,118 L26,121 L33,66 Z" class="bm-body bm-skin"/>
    <path d="M82,52 L97,60 L103,118 L94,121 L87,66 Z" class="bm-body bm-skin"/>
    <path d="M41,152 L39,212 L43,250 L53,250 L56,212 L58,154 Z" class="bm-body bm-skin"/>
    <path d="M79,152 L81,212 L77,250 L67,250 L64,212 L62,154 Z" class="bm-body bm-skin"/>
    <rect x="56" y="52" width="8" height="98" rx="3" class="bm-body" opacity=".45"/>`;

  const zones = which === 'front' ? [
    hit('HEENT', '<ellipse class="hit" cx="60" cy="26" rx="17" ry="20"/>', 'HEENT — head, eyes, ears, nose, throat (front)'),
    hit('Neck', '<rect class="hit" x="46" y="38" width="28" height="14" rx="4"/>', 'Neck — thyroid, range of motion, meningeal signs'),
    hit('Lungs', '<rect class="hit" x="36" y="54" width="48" height="22" rx="4"/>', 'Lungs — anterior chest fields'),
    hit('Heart', '<rect class="hit" x="58" y="76" width="26" height="22" rx="4"/>', 'Heart — precordium, valve areas, carotids'),
    hit('Lungs', '<rect class="hit" x="36" y="76" width="22" height="22" rx="4"/>', 'Lungs — left anterior field'),
    hit('Abdomen', '<rect class="hit" x="37" y="98" width="46" height="36" rx="5"/>', 'Abdomen — four quadrants and special tests'),
    hit('Musculoskeletal', '<rect class="hit" x="38" y="134" width="45" height="26" rx="5"/>', 'Musculoskeletal — pelvis, hips, affected area'),
    hit('Extremities', '<rect class="hit" x="14" y="52" width="24" height="72" rx="8"/>', 'Extremities — right arm and hand'),
    hit('Extremities', '<rect class="hit" x="82" y="52" width="24" height="72" rx="8"/>', 'Extremities — left arm and hand'),
    hit('Extremities', '<rect class="hit" x="36" y="160" width="48" height="94" rx="10"/>', 'Extremities — legs, pulses, edema')
  ] : [
    hit('HEENT', '<ellipse class="hit" cx="60" cy="26" rx="17" ry="20"/>', 'Head — posterior'),
    hit('Neck', '<rect class="hit" x="46" y="38" width="28" height="14" rx="4"/>', 'Posterior neck — cervical spine and range of motion'),
    hit('Lungs', '<rect class="hit" x="34" y="54" width="24" height="48" rx="4"/>', 'Lungs — right posterior fields'),
    hit('Lungs', '<rect class="hit" x="64" y="54" width="24" height="48" rx="4"/>', 'Lungs — left posterior fields'),
    hit('Osteopathic', '<rect class="hit" x="56" y="52" width="9" height="98" rx="3"/>', 'Osteopathic — cervical, thoracic, lumbar, sacrum, ribs'),
    hit('Abdomen', '<rect class="hit" x="34" y="102" width="24" height="26" rx="4"/>', 'Right flank — costovertebral angle'),
    hit('Abdomen', '<rect class="hit" x="64" y="102" width="24" height="26" rx="4"/>', 'Left flank — costovertebral angle'),
    hit('Musculoskeletal', '<rect class="hit" x="36" y="128" width="48" height="32" rx="5"/>', 'Musculoskeletal — lumbar, paraspinal, straight leg raise'),
    hit('Extremities', '<rect class="hit" x="14" y="52" width="24" height="72" rx="8"/>', 'Extremities — left arm (posterior view)'),
    hit('Extremities', '<rect class="hit" x="82" y="52" width="24" height="72" rx="8"/>', 'Extremities — right arm (posterior view)'),
    hit('Extremities', '<rect class="hit" x="36" y="160" width="48" height="94" rx="10"/>', 'Extremities — posterior legs')
  ];
  return `<svg viewBox="0 0 120 258" role="group"
    aria-label="Body map, ${which === 'front' ? 'anterior' : 'posterior'} view. Each region is a button.">
    ${body}${zones.join('')}
  </svg>`;
}

function wireExamPanel(body){
  $$('[data-bmview]', body).forEach(b => { b.onclick = () => {
    room.view = b.dataset.bmview;
    $$('[data-bmview]', body).forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    $('#bodyMapHost', body).innerHTML = bodyMapSvg(room.view, performedByRegion());
    wireMapRegions(body);
    announce((room.view === 'front' ? 'Anterior' : 'Posterior') + ' view');
  }; });
  wireMapRegions(body);
  $$('#regionList .rbtn', body).forEach(b => { b.onclick = () => selectRegion(b.dataset.region, body); });
  $('#posSel', body).onchange = e => requestPosition(e.target.value,e.target);
  $('#instSel', body).onchange = e => { room.instrument = e.target.value; paintManList(body); };
  $('#manSearch', body).oninput = () => paintManList(body);
  paintManList(body);
  paintRunning(body);
}
function wireMapRegions(body){
  $$('.bm-region', body).forEach(g => {
    g.onclick = () => selectRegion(g.dataset.region, body);
    g.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault(); selectRegion(g.dataset.region, body); } };
  });
}
function selectRegion(region, body){
  room.showAll=!region;
  room.region = (!region || room.region === region) ? null : region;
  $$('.bm-region', body).forEach(g =>
    g.setAttribute('aria-pressed', String(g.dataset.region === room.region)));
  $$('#regionList .rbtn', body).forEach(b =>
    b.setAttribute('aria-pressed', String((b.dataset.region || null) === room.region)));
  paintManList(body);
  announce(room.region ? room.region + ' selected' : 'All regions');
}
function paintManList(body){
  const host = $('#manList', body); if (!host) return;
  const q = ($('#manSearch', body).value || '').trim().toLowerCase();
  const inst = INSTRUMENTS.filter(i => i[0] === room.instrument)[0];
  const methods = inst ? inst[2] : [];
  const performed = performedMap();
  if(!room.region&&!q&&!methods.length&&!room.showAll){host.innerHTML='<div class="exam-start"><h3>Choose a region or search an action</h3><p>The same examination catalog is available for every patient. Select the region, then the method and technique you intend to use.</p><button class="btn" id="showAllExams">Browse all examinations</button></div>';$('#showAllExams',host).onclick=()=>{room.showAll=true;paintManList(body);};return;}
  let n = 0;
  const html = catalog().map(g => {
    if (room.region && g.region !== room.region) return '';
    const mans = g.maneuvers.filter(m => {
      if (methods.length && methods.indexOf(m.method) < 0) return false;
      if (q && (m.label + ' ' + g.region + ' ' + (m.notes || '') + ' ' + m.components.join(' '))
          .toLowerCase().indexOf(q) < 0) return false;
      return true;
    });
    if (!mans.length) return '';
    n += mans.length;
    return `<h3 style="font-size:var(--fs-sm);margin-top:var(--sp-3)">${esc(g.region)}</h3>` +
      mans.map(m => {
        const rec = performed[m.id];
        const covered = rec ? (rec.components || []) : [];
        return `<div class="maneuver ${rec ? 'done' : ''}" data-m="${esc(m.id)}">
        <div class="man-head"><span class="m-label">${esc(m.label)}</span>
          <span class="m-method">${esc(m.method)}</span>
          <span class="tiny muted">~${m.duration_s}s</span></div>
        ${m.notes ? `<div class="man-note">${esc(m.notes)}</div>` : ''}
        ${m.components.length ? `
          <div class="chips-label" id="cl-${esc(m.id)}">Site &amp; technique</div>
          <div class="chips" role="group" aria-labelledby="cl-${esc(m.id)}">
          ${m.components.map(c => `<label class="chip ${covered.indexOf(c) >= 0 ? 'on' : ''}">
            <input type="checkbox" value="${esc(c)}" ${covered.indexOf(c) >= 0 ? 'checked' : ''}>
            <span>${esc(c)}</span></label>`).join('')}</div>` : ''}
        <div class="row" style="margin-top:var(--sp-2)">
          <button class="btn sm primary" type="button" data-do="${esc(m.id)}">
            ${rec ? 'Repeat' : 'Perform'}</button>
          ${rec ? '<span class="badge b-ok">already performed</span>' : ''}
        </div></div>`;
      }).join('');
  }).join('');
  host.innerHTML = html || '<p class="small muted">Nothing matches that filter.</p>';
  $('#manCount', body).textContent = n + ' maneuver' + (n === 1 ? '' : 's');
  $$('.chip input', host).forEach(cb => { cb.onchange = () =>
    cb.closest('.chip').classList.toggle('on', cb.checked); });
  $$('button[data-do]', host).forEach(b => { b.onclick = () => startManeuver(b.dataset.do, body); });
  if (room.running) lockManeuverButtons(body, true);
}
function lockManeuverButtons(body, locked){
  $$('button[data-do]', body).forEach(b => {
    b.disabled = locked; b.setAttribute('aria-disabled', String(locked));
  });
}
async function startManeuver(mid, body){
  if (room.running || S.pending_exam) { toast('An examination is already running.'); return; }
  const box = $('.maneuver[data-m="' + mid + '"]', body);
  const comps = $$('.chips input:checked', box).map(i => i.value);
  const label = $('.m-label', box).textContent;
  const posName = (POSITIONS.filter(p => p[0] === recordedPosition())[0] || [])[1] || '';
  const source = 'Perform: ' + label + (comps.length ? ' (' + comps.join(', ') + ')' : '') +
                 (posName ? ' — patient ' + posName.toLowerCase() : '');
  lockManeuverButtons(body, true);
  const resp = await api(`/api/session/${S.id}/exam`, {
    maneuver_id: mid, components: comps, source_text: source });
  if (resp.error) { lockManeuverButtons(body, false);
    toast(resp.message || 'That examination could not be performed now.'); return; }
  if (resp.state) S = Object.assign({}, S, resp.state);
  (resp.events || []).forEach(deliverEvent);
  if(resp.state?.transcript)paintStream(S.transcript || []);
  lockManeuverButtons(body, !!S.pending_exam);
  paintExamProgress(); notifyPublicState();
  if(S.pending_exam){const host=$('#examRunning',body);if(host)host.innerHTML='<div class="callout" role="status">Examination in progress. Findings will appear in the encounter record when it finishes.</div>';}
  else {paintManList(body);toast('Action recorded: '+label);}
}

function paintRunning(body){
  const host = body ? $('#examRunning', body) : $('#examRunning');
  if (!host) return;
  if (!room.running) { host.innerHTML = ''; return; }
  const r = room.running;
  const elapsed = (Date.now() - r.started) / 1000;
  const left = Math.max(0, r.duration - elapsed);
  const pct = clamp(100 * elapsed / r.duration, 0, 100);
  host.innerHTML = `<div class="exam-running" role="status">
    <div class="er-title"><span>Examining — ${esc(r.label)}</span>
      <span class="er-time">${left.toFixed(0)}s</span></div>
    ${r.comps.length ? `<div class="tiny muted">${esc(r.comps.join(', '))}</div>` : ''}
    <div class="progressbar warn" style="margin-top:var(--sp-2)" role="progressbar"
      aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(pct)}"
      aria-label="Examination progress"><span style="width:${pct}%"></span></div>
    <p class="tiny muted" style="margin-top:var(--sp-2);margin-bottom:0">Nothing is
    released until the maneuver finishes, and it costs ${Math.round(r.duration)}s of your
    encounter either way.</p>
  </div>`;
}
function finishManeuver(){
  const r = room.running; if (!r) return;
  clearInterval(room.runTimer); room.runTimer = null;
  room.running = null;
  pushEvent(r.result);
  setPatientState('idle');
  paintExamProgress();
  const body = overlay ? $('#ovBody', overlay) : null;
  if (body) {
    const host = $('#examRunning', body); if (host) host.innerHTML = '';
    paintManList(body);
    paintExamSummary(body);
    lockManeuverButtons(body, false);
    const map = $('#bodyMapHost', body);
    if (map) { map.innerHTML = bodyMapSvg(room.view, performedByRegion()); wireMapRegions(body); }
  }
  announce('Finding released for ' + r.label + '. See the conversation.');
}
function cancelRunningExam(){
  clearPendingReveals();
  if (!room.running) return;
  clearInterval(room.runTimer); clearTimeout(room.runEnd);
  room.running = null;
}
function paintExamProgress(){
  // Refresh the open examination workspace when evidence arrives asynchronously.
  paintExamSummary();
  const el = $('#examProgressSub'); if (!el) return;
  const n = Object.keys(performedMap()).length;
  el.textContent = n ? (n + ' maneuver' + (n === 1 ? '' : 's') + ' performed · body map and technique')
                     : 'Body map, positioning, technique';
}

/* ======================================================================== */
/* 4. VOICE                                                                  */
/* ======================================================================== */
function probeVoice(){
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  voice.supported = !!SR;
  const chip = $('#voiceOk');
  if (chip) { chip.className = 'badge ' + (SR ? 'b-ok' : 'b-warn');
    chip.textContent = SR ? 'microphone available'
      : 'speech recognition not in this browser — typing works everywhere'; }
}
function voiceBar(html, isErr){
  const bar = $('#voiceBar'); if (!bar) return;
  bar.classList.toggle('hidden', !html);
  bar.classList.toggle('err', !!isErr);
  bar.innerHTML = html || '';
  if (html) { $$('button', bar).forEach(b => { b.onclick = () => {
    if (b.dataset.act === 'retry') { voice.failed = false; voiceBar(''); startListening(); }
    if (b.dataset.act === 'type')  { voiceBar(''); const el = $('#say'); if (el) el.focus(); }
  }; }); }
}
function setupVoice(){
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const btn = $('#btnMic');
  if (!SR) {
    voiceBar('Speech recognition is not available in this browser. Typed entry works ' +
             'exactly the same way. <button class="btn sm" data-act="type" type="button">Type instead</button>', true);
    if (btn) { btn.disabled = true; btn.setAttribute('aria-disabled', 'true'); }
    return;
  }
  if (!voice.rec) {
    const rec = new SR();
    rec.continuous = true; rec.interimResults = true; rec.lang = 'en-US';
    rec.onstart = () => { voice.recActive=true; voice.starting=false;
      if(!voice.wanted||voice.suppressed){try{rec.abort();}catch(e){}return;}
      voice.listening=true; voice.lastFinal=-1; setPatientState('listening');
      $('#btnMic')?.setAttribute('aria-pressed','true');
      voiceBar('Listening hands-free. Click the microphone to stop, or press Escape to cancel.'); };
    rec.onresult = e => {
      if(S?.phase!=='encounter'||voice.recSession!==S.id)return;
      // The patient's synthesized voice must never be transcribed back as the
      // student's own turn: anything heard while speech synthesis is speaking,
      // or in the short tail after it, is discarded.
      if (voice.suppressed || Date.now() < voice.muteUntil ||
          (window.speechSynthesis && window.speechSynthesis.speaking)) {
        // Audio captured while the patient is audible is the app's own voice.
        // Discarding the pending results is not enough on its own: a result
        // finalized here would otherwise be delivered again once the mute
        // window lapses, so the watermark is advanced past it as well.
        voice.lastFinal = Math.max(voice.lastFinal, e.results.length - 1);
        return;
      }
      let interim = '';
      // Start at the session watermark, not e.resultIndex: a continuous
      // session re-delivers earlier finals, and resultIndex alone re-submits
      // them. Each final index is spoken once and only once.
      for (let i = Math.max(e.resultIndex, voice.lastFinal + 1); i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) {
          voice.lastFinal = i;
          const c = r[0].confidence;
          const conf = (c === undefined || c === 0) ? null : c;
          const text = r[0].transcript.trim();
          if (!text) continue;
          if (conf !== null && conf < 0.65) stageUncertain(text, conf);
          else sendSay(text, conf);
        } else interim += r[0].transcript;
      }
      const el = $('#interim'); if (el) el.textContent = interim;
    };
    rec.onerror = ev => {
      if(ev.error==='aborted')return;
      if(ev.error==='no-speech'){voiceBar('Still listening. Speak when ready, or click the microphone to stop.');return;}
      voice.failed = true; voice.wanted=false; voice.hands_free=false;
      const msg = ({ 'not-allowed':'The browser blocked microphone access.',
        'service-not-allowed':'Speech recognition was refused by the browser.',
        'audio-capture':'No microphone was found.',
        'network':'Speech recognition lost its network connection.' })[ev.error] ||
        ('Microphone error: ' + ev.error + '.');
      voiceBar(esc(msg) + ' Nothing you have said is lost, and typing keeps working. ' +
        '<button class="btn sm" data-act="retry" type="button">Try the microphone again</button> ' +
        '<button class="btn sm" data-act="type" type="button">Type instead</button>', true);
      alertNow(msg + ' Typing still works.');
      if (S) api(`/api/session/${S.id}/interruption`,
        { kind:'speech', detail:'Speech recognition error: ' + ev.error });
      setPatientState('idle');
      if (btn) btn.setAttribute('aria-pressed', 'false');
      voice.listening = false;
    };
    rec.onend = () => {
      voice.recActive=false;voice.starting=false;voice.listening=false;
      $('#btnMic')?.setAttribute('aria-pressed','false');
      if(voice.wanted&&voice.hands_free&&!voice.failed) scheduleListening();
      else if(!voice.failed){setPatientState('idle');voiceBar('');}
    };
    voice.rec = rec;
  }
  if(btn){
    // Native click supports mouse, touch, Enter and Space without competing
    // press/release and double-click recognition sessions.
    btn.onclick=()=>{if(voice.wanted){voice.hands_free=false;stopListening();}
      else{voice.hands_free=true;startListening();}};
    btn.setAttribute('aria-label','Microphone: click to start or stop hands-free listening');
    btn.setAttribute('aria-pressed',String(!!voice.wanted));
  }
  voiceBar('Click the microphone to listen hands-free. Click again to stop.');
}
function scheduleListening(){
  clearTimeout(voice.restartTimer);
  voice.restartTimer=setTimeout(()=>{
    if(!voice.wanted||!voice.hands_free||voice.failed||S?.phase!=='encounter')return;
    if(voice.suppressed||voice.patientSpeaking||window.pcmNaturalBusy||Date.now()<voice.muteUntil){scheduleListening();return;}
    if(voice.recActive||voice.starting)return;
    voice.starting=true;voice.recSession=S.id;
    try{voice.rec.start();}catch(e){voice.starting=false;voice.listening=false;voice.wanted=false;voice.failed=true;
      $('#btnMic')?.setAttribute('aria-pressed','false');voiceBar('Microphone could not start. Click it to retry, or type your question.',true);}
  },400);
}

/* The patient is about to be audible. `abort()` is deliberate: `stop()` asks
   the recognizer to FINALIZE what it has buffered, which is then delivered
   through onresult once the mute window has lapsed -- that is how the
   patient's own greeting was reaching the transcript and being sent back as
   the student's turn. `abort()` discards it instead. */
function suppressListeningForPatient(){
  voice.suppressed = true;
  voice.patientSpeaking = true;
  if (voice.rec) { try { voice.rec.abort(); } catch(e){ try { voice.rec.stop(); } catch(e2){} } }
  const el = $('#interim'); if (el) el.textContent = '';
}
/* The patient has finished. Resume a FRESH recognition session after a short
   tail, so a room echo of the last word cannot open the next utterance. */
function resumeListeningAfterPatient(){
  voice.patientSpeaking = false;
  voice.muteUntil = Date.now() + 350;
  notifyPublicState();
  setPatientState('idle');
  setTimeout(()=>{voice.suppressed=false;if(voice.wanted&&voice.hands_free)scheduleListening();},400);
}

function startListening(){
  if(!voice.rec||S?.phase!=='encounter')return;
  voice.failed=false;voice.wanted=true;
  interruptPatient();
  scheduleListening();
  $('#btnMic')?.setAttribute('aria-pressed','true');
  voiceBar('Starting microphone… Click again to stop.');
}
function stopListening(){
  voice.wanted = false;clearTimeout(voice.restartTimer);
  if (!voice.rec) return;
  voice.listening = false;
  const btn = $('#btnMic'); if (btn) btn.setAttribute('aria-pressed', 'false');
  try { voice.rec.stop(); } catch(e){}
  const el = $('#interim'); if (el) el.textContent = '';
  setPatientState('idle');
}
/* A turn the recognizer was unsure about is not sent blind: it lands in the
   composer, marked, so it can be corrected before the patient ever hears it. */
function stageUncertain(text, conf){
  const el = $('#say'); if (!el) { sendSay(text, conf); return; }
  el.value = text; autogrow(el); el.focus(); el.select();
  const iv = $('#interim');
  if (iv) { iv.className = 'interim low';
    iv.textContent = 'Heard with low confidence (' + Math.round(conf * 100) +
      '%). Edit it if it is wrong, then press Enter — it is recorded as uncertain either way.'; }
  voice.pending = conf;
}
function interruptPatient(){
  window.pcmAIInterrupt?.();
  window.pcmNaturalVoice?.stop();voice.muteUntil=Date.now()+350;
  voice.patientSpeaking=false;voice.suppressed=false;voice.lastFinal=-1;
  setPatientState('idle');notifyPublicState();
  const speechStatus=$('#naturalVoiceStatus');if(speechStatus)speechStatus.textContent='Speech stopped.';
  try { if (window.speechSynthesis && window.speechSynthesis.speaking) {
    window.speechSynthesis.cancel();
    voice.muteUntil = Date.now() + 350;
    setPatientState('idle');
  } } catch(e){}
}
/* Stop patient audio for a PREFERENCE change. Deliberately narrower than
   interruptPatient(): it cancels local playback only and never signals a
   user-initiated delivery interruption, because turning the toggle off is not
   the learner cutting the patient off mid-sentence. It also leaves the
   clinician's microphone and hands-free preference untouched. */
function silencePatientAudio(){
  try{ window.speechSynthesis?.cancel(); }catch(e){}
  voice.patientSpeaking=false;
  setPatientState('idle');
  notifyPublicState();
  // Recognition was suspended for speech that is no longer playing; let it
  // resume on the normal path, but only if the user still had it listening.
  if(voice.suppressed) resumeListeningAfterPatient();
}
function stopVoice(){
  window.pcmNaturalVoice?.stop();voice.muteUntil=0;voice.patientSpeaking=false;
  voice.listening = false; voice.hands_free = false; voice.wanted = false; voice.suppressed = false;
  voice.lastFinal = -1; voice.lastSentText = ''; voice.lastSentAt = 0;
  // abort() discards anything buffered; stop() would finalize and deliver it
  // after the listener believes it has been switched off.
  try { if (voice.rec) voice.rec.abort(); } catch(e){ try { voice.rec.stop(); } catch(e2){} }
  try { window.speechSynthesis.cancel(); } catch(e){}
  const el = $('#interim'); if (el) el.textContent = '';
}
function patientIsListening(){
  return S?.phase==='encounter'&&!voice.patientSpeaking&&!window.pcmAISpeaking&&Boolean(voice.listening||window.pcmAIRecording||(document.activeElement===$('#say')&&$('#say')?.value));
}
function configurePatientSpeech(utterance){
  // The patient's sex comes from the case's AUTHORED presentation, never from
  // the name or the rendered model. `presentation.appearance()` is explicit
  // about not guessing, so this is the one field allowed to pick the voice.
  return window.pcmDeviceSpeech?.configure(utterance,
    {pace:S?.demeanor?.pace, sex:S?.appearance?.presentation}) || {available:false};
}
/* The fixed voice for this patient is missing from this runtime. The policy is
   two voices only, so nothing is substituted: the patient stays silent and the
   Voice control shows the shortfall once. Text is unaffected. */
let voiceUnavailableTold=false;
function reportVoiceUnavailable(info){
  const want=info?.required?.name;
  setPatientState('idle');
  window.dispatchEvent(new CustomEvent('pcm-voice-unavailable',{detail:info||{}}));
  if(voiceUnavailableTold)return;
  voiceUnavailableTold=true;
  toast(want ? 'The patient voice ('+want+') is not installed in this browser. The conversation still works in text.'
             : 'This browser has no speech voices available. The conversation still works in text.');
}
window.pcmConfigureSpeech=configurePatientSpeech;
/* Speak one delivered segment with the patient's fixed voice.
   Replaces the retired paid-provider player and keeps its callback contract
   (onstart/onend/onerror) so the delivery/acknowledgement flow is untouched.
   An unavailable voice reports through onerror rather than substituting. */
window.pcmSpeakSegment=(text,{onstart,onend,onerror}={})=>{
  if(!voice.speak){onerror?.();return;}   // the toggle governs every speech path
  if(!window.speechSynthesis){onerror?.();return;}
  try{
    const u=new SpeechSynthesisUtterance(text);
    const info=configurePatientSpeech(u);
    if(!info||!info.available){reportVoiceUnavailable(info);onerror?.();return;}
    u.onstart=()=>onstart?.();
    u.onend=()=>onend?.();
    u.onerror=()=>onerror?.();
    window.speechSynthesis.speak(u);
  }catch(e){onerror?.();}
};
window.pcmSpeechOptions={enabled:()=>voice.speak,phase:()=>S?.phase,setEnabled:value=>{voice.speak=!!value;LS.set('prefs',Object.assign({},LS.get('prefs')||{},{speak:voice.speak}));if(!voice.speak)silencePatientAudio();window.dispatchEvent(new Event('pcm-speech-preference'));}};
function speak(text){
  if (!voice.speak) return;                       // toggle is authoritative
  if (!window.speechSynthesis) { setPatientState('idle'); return; }
  try {
    const u = new SpeechSynthesisUtterance(text);
    const info = configurePatientSpeech(u);
    if (info && info.loading) {
      // Chrome delivers its voice list asynchronously. Wait for exactly one
      // voiceschanged, then decide once -- no polling, no growing queue.
      const retry = () => { window.speechSynthesis.removeEventListener('voiceschanged', retry); speak(text); };
      window.speechSynthesis.addEventListener('voiceschanged', retry, { once: true });
      return;
    }
    if (!info || !info.available) { reportVoiceUnavailable(info); return; }
    u.onstart = () => { notifyPublicState(); setPatientState('speaking'); };
    u.onend = () => { resumeListeningAfterPatient(); };
    u.onerror = () => { resumeListeningAfterPatient(); };
    // Suppress BEFORE speaking, not in onstart: onstart fires once audio is
    // already playing, leaving a window in which the microphone hears the
    // opening words of the patient's own reply.
    suppressListeningForPatient();
    voice.muteUntil = Date.now() + 60000;
    window.speechSynthesis.speak(u);
  } catch(e) { setPatientState('idle'); }
}

/* ======================================================================== */
/* 5a. ORGANIZATION INTERVAL                                                 */
/* ======================================================================== */
function renderOrganize(){
  recoverScratch();stopVoice(); cancelRunningExam();
  view.innerHTML = `<div class="wrap-narrow">
    <div class="center-stage">
      <div class="phase-chip org">Organization interval · practice modification</div>
      <div class="clock" role="timer" aria-label="Organization interval remaining">
        <span class="digits" data-clock>--:--</span></div>
      <p class="small muted" style="max-width:56ch">Organize your thinking. The encounter
      record is frozen. ${isUntimedAttempt()?'The untimed SOAP workspace opens':'The SOAP timer starts'} automatically when this ends. No new patient contact happens here.</p>
      <button class="btn primary" id="skip" type="button">Start the SOAP note now</button>
    </div>
    <div class="card"><div class="card-head">
      <h3>Scratchpad</h3><span class="badge b-mute">optional · never graded</span></div>
      <label class="sr-only" for="scratch">Scratchpad</label>
      <textarea class="scratch" id="scratch" placeholder="Jot your structure. This carries into the note phase and is never scored.">${esc(S.scratch || '')}</textarea><p id="scratchStatus" class="scratch-status" role="status">Your draft is saved as you type.</p>
    </div></div>`;
  const scratchSid=S.id;
  $('#scratch').oninput=e=>{clearTimeout(scratchSaveTimer);const value=e.target.value;S.scratch=value;const local=keepDraft('scratch',scratchSid,value);scratchNeedsSave=true;scratchProtected=local;scratchMessage(local?'Saved in this browser · syncing…':'Browser recovery storage unavailable. Keep this page open while saving.');scratchSaveTimer=setTimeout(()=>saveScratch(scratchSid,value),350);};
  $('#skip').onclick=async()=>{clearTimeout(scratchSaveTimer);const value=$('#scratch').value;keepDraft('scratch',scratchSid,value);const saved=await saveScratch(scratchSid,value);if(!saved.saved){toast('Your scratchpad is retained in this browser. Reconnect before continuing.');return;}const next=await post(`/api/session/${scratchSid}/skip_organize`);if(next.error){toast(next.message||'Could not start the note.');return;}S=next;renderPhase(true);};
  $('#scratch').focus();
}

/* ======================================================================== */
/* 5b. SOAP WORKSTATION                                                      */
/* ======================================================================== */
const NOTE_HINTS = {
  S: 'cc, HPI, PMH, PSH, Meds, SH, FH, Allergies, ROS',
  O: 'Vitals, General, systems examined, osteopathic structural exam'
};
function renderNote(){
  stopVoice(); cancelRunningExam();
  recoverScratch();const recoveredNote=draftValue('note',S.id);const n=recoveredNote||S.note||{};
  const A = (n.A || []).concat(['', '', '']).slice(0, 3);
  const Pn = (n.P || []).concat(['', '', '']).slice(0, 3);
  const exam = !mode().coach;
  const chart = S.station_chart || { vitals:{}, supplied_results:[] };
  view.innerHTML = `<div class="note-layout">
    <div>
      <div class="note-sheet">
        <div class="note-head">
          <span class="n-title">SOAP note</span>
          <span class="n-sub">${esc(S.patient_name || '')} · ${esc(stationTitle(S.case_id))}</span>
          <div class="spacer"></div>
          <span class="n-sub">time left</span>
          <span class="clock" style="font-size:var(--fs-md);padding:2px 8px"
            ><span class="digits" data-clock>--:--</span></span>
        </div>
        <div class="note-sec">
          <div class="sec-head"><span class="sec-letter">S</span>
            <span class="sec-name">Subjective</span>
            <span class="sec-hint">${exam ? '' : esc(NOTE_HINTS.S)}</span></div>
          <label class="sr-only" for="noteS">Subjective</label>
          <textarea id="noteS" spellcheck="true" autocomplete="off"
            placeholder="${exam ? '' : 'cc: chief complaint and duration\nHPI: age/sex, onset, setting, location, duration, character, alleviating/aggravating, radiation, associated symptoms\nPMH:   PSH:   Meds:   SH:   FH:   Allergies:   ROS:'}">${esc(n.S || '')}</textarea>
        </div>
        <div class="note-sec">
          <div class="sec-head"><span class="sec-letter">O</span>
            <span class="sec-name">Objective</span>
            <span class="sec-hint">${exam ? '' : esc(NOTE_HINTS.O)}</span></div>
          <label class="sr-only" for="noteO">Objective</label>
          <textarea id="noteO" spellcheck="true" autocomplete="off"
            placeholder="${exam ? '' : 'Vitals:\nGeneral:\nHeart:   Lungs:\n(area of concern — document the expanded exam)\nOsteopathic:'}">${esc(n.O || '')}</textarea>
        </div>
        <div class="note-sec" style="border-bottom:0">
          <div class="sec-head"><span class="sec-letter">A/P</span>
            <span class="sec-name">Assessment paired with its plan</span>
            <span class="sec-hint">numbered 1, 2, 3</span></div>
          ${[0, 1, 2].map(i => `
          <div class="ap-pair">
            <div class="pair-head"><span class="pair-no">${i + 1}</span>
              <span>Assessment ${i + 1} and its plan</span></div>
            <div class="ap-cols">
              <div><div class="ap-lab" id="alab${i}">Assessment ${i + 1}</div>
                <textarea id="noteA${i}" rows="2" aria-labelledby="alab${i}"
                  autocomplete="off" placeholder="Differential diagnosis ${i + 1}">${esc(A[i])}</textarea></div>
              <div><div class="ap-lab" id="plab${i}">Plan ${i + 1}</div>
                <textarea id="noteP${i}" rows="2" aria-labelledby="plab${i}"
                  autocomplete="off" placeholder="Plan for assessment ${i + 1}">${esc(Pn[i])}</textarea></div>
            </div>
          </div>`).join('')}
        </div>
      </div>
      <div class="savebar">
        <button class="btn primary" id="btnSubmit" type="button">Submit note</button>
        <span class="savestate" id="saveState" role="status">
          <span class="dot" aria-hidden="true"></span><span class="txt">Draft not yet saved</span></span>
        <div class="spacer" style="flex:1"></div>
        <span class="tiny muted">The numbers 1, 2 and 3 shown beside each pair are
        submitted with the note.</span>
      </div>
    </div>
    <div>
      <div class="card tight"><div class="card-head"><h3 style="font-size:var(--fs-md)">Chart</h3></div>
        ${chartHtml(chart)}</div>
      ${S.scratch ? `<div class="card tight"><div class="card-head">
        <h3 style="font-size:var(--fs-md)">Your scratchpad</h3></div>
        <pre class="note-out" style="margin:0">${esc(S.scratch)}</pre></div>` : ''}
      ${S.assisted ? `<div class="card tight"><div class="card-head">
        <h3 style="font-size:var(--fs-md)">Transcript</h3>
        <span class="badge b-warn">assisted mode</span></div>
        <div style="max-height:340px;overflow:auto">${(S.assisted_transcript || [])
          .filter(r => ['student_utterance','patient_reply','exam_finding','exam_refused','station_info'].indexOf(r.kind) >= 0)
          .map(r => `<div class="tx-row"><span class="tt">${esc(r.time)}</span>
            <span class="kk"><span class="badge b-mute">${esc(r.kind.replace(/_/g, ' '))}</span></span>
            <span>${esc(r.text)}</span></div>`).join('')}</div>
        <p class="tiny muted" style="margin-top:var(--sp-2)">This assistance is named on
        your results.</p></div>`
      : S.record
      // What you obtained, in the shape the note is scored in. The modes that
      // permit it now supply this; the rail used to say nothing was available
      // even then, so the summary sat in the payload unread.
      ? `<div class="card tight note-reference"><div class="note-ref-head"><h3>What you obtained</h3>
        <span class="tiny muted">Your own findings · nothing added</span></div>
        <nav class="note-ref-jump" aria-label="Jump to a part of your record">${
          (S.record.groups||[]).map((g,i)=>`<button type="button" data-ref-jump="${i}">${esc(g.label)}</button>`).join('')}</nav>
        <div class="note-ref-body">${(window.pcmRecordHtml ? window.pcmRecordHtml(S.record) : '')}</div></div>`
      : `<div class="card tight"><p class="small muted">No reference material, no transcript
      and no omission warnings — the syllabus allows none of it while the note is being
      written (p. 5). Everything is revealed after you submit.</p></div>`}
    </div></div>`;

  // The rail is a 1400px list inside a 720px box with nothing to say so. The
  // examination findings a student needs for Objective sat at the bottom of a
  // nested scroller they had no reason to think would scroll.
  (() => {
    const rail = document.querySelector('.note-reference'); if (!rail) return;
    const body = rail.querySelector('.note-ref-body'); if (!body) return;
    const groups = [...body.querySelectorAll('.ew-rec-group')];
    const chips = [...rail.querySelectorAll('[data-ref-jump]')];
    chips.forEach(b => b.onclick = () => {
      const target = groups[Number(b.dataset.refJump)]; if (!target) return;
      body.scrollTop = target.offsetTop - body.firstElementChild.offsetTop;
      chips.forEach(x => x.setAttribute('aria-current', String(x === b)));
    });
    const shade = () => {
      body.classList.toggle('has-more', body.scrollHeight - body.scrollTop - body.clientHeight > 6);
      body.classList.toggle('has-above', body.scrollTop > 6);
    };
    body.addEventListener('scroll', shade, {passive:true}); shade();
  })();

  ['noteS','noteO','noteA0','noteA1','noteA2','noteP0','noteP1','noteP2'].forEach(id => {
    const el = $('#' + id); if (!el) return;
    autogrow(el);
    el.oninput=()=>{autogrow(el);keepDraft('note',S.id,collectNote());setSaveState('unsaved');queueNoteSave();};
  });
  $('#btnSubmit').onclick = async () => {
    const sid=S.id; const frozenDraft=collectNote();
    if (!await confirmChoice('Your note locks when you submit it, and the debrief is revealed.',
        {title:'Submit your note?',confirm:'Submit note',cancel:'Keep writing'})) return;
    if(!S||S.id!==sid||S.phase!=='note')return;
    const r = await persistNote();
    if (!r.saved) {
      setSaveState('error', r.reason);
      if (!await confirmChoice('This draft was not stored — ' + r.reason,
          {title:'Submit without a stored draft?',confirm:'Submit anyway',cancel:'Keep writing'})) return;
    }
    if(!S||S.id!==sid||S.phase!=='note')return;
    clearTimeout(noteSaveTimer);
    const next = await api(`/api/session/${sid}/submit`, { note: frozenDraft });
    if (next.error) { toast(next.message || 'The note could not be submitted.'); return; }
    clearMatchingDraft('note',sid,frozenDraft);S = next; renderPhase(true);
  };
  if(recoveredNote)toast('Recovered your unsent note draft from this browser.');
  $('#noteS').focus();
  queueNoteSave();
}

// The A and P rows display their ordinal in a sibling span beside the box, so
// the number the student sees never lived in the input. The rubric condition
// "Must be numbered 1, 2, 3" is real, so submit the number the UI displays
// rather than denying credit for one the data model supplies structurally.
function numberedEntry(i, value) {
  const v = String(value || '').trim();
  if (!v) return '';
  return new RegExp('^\\s*' + (i + 1) + '\\s*[.):-]').test(v) ? v : (i + 1) + '. ' + v;
}

function collectNote(){
  const g = id => { const e = $('#' + id); return e ? e.value : ''; };
  return { S:g('noteS'), O:g('noteO'),
           A:[0,1,2].map(i => numberedEntry(i, g('noteA' + i))),
           P:[0,1,2].map(i => numberedEntry(i, g('noteP' + i))) };
}
/* A save that did not happen is never reported as one. The route answers
   {saved, phase, reason}; a false there is shown as its reason, never as
   "Saved." */
let noteWrite=Promise.resolve();
async function persistNote(){
  if (!S) return { saved:false, reason:'no station is open.' };
  if (S.phase !== 'note')
    return { saved:false, reason:'the note period is closed, so drafts are no longer stored.' };
  const sid=S.id,note=collectNote();keepDraft('note',sid,note);
  noteWrite=noteWrite.catch(()=>{}).then(async()=>{
  const r = await api(`/api/session/${sid}/note`, { note });
  if (r?.error === 'offline')
    return { saved:false, reason:'the local engine could not be reached, so this draft is only in this browser.' };
  if (!r || r.saved !== true)
    return { saved:false, reason:(r && r.reason) || 'the local engine rejected the save.' };
  clearMatchingDraft('note',sid,note);const newer=S?.id===sid&&S.phase==='note'&&JSON.stringify(collectNote())!==JSON.stringify(note);if(S?.id===sid&&!newer)S.note=note;
  return { saved:true,at:Date.now(),newer };
  });
  return noteWrite;
}
function setSaveState(state, reason){
  noteSave.state = state; noteSave.reason = reason || '';
  const el = $('#saveState'); if (!el) return;
  el.className = 'savestate ' + state;
  const txt = $('.txt', el);
  if (state === 'saving') txt.textContent = 'Saving…';
  else if (state === 'saved') txt.textContent = 'Saved ' + new Date(noteSave.at).toLocaleTimeString();
  else if (state === 'unsaved') txt.textContent = 'Unsaved changes';
  else if (state === 'error') {
    txt.textContent = 'Not saved — ' + reason;
    alertNow('Your note was not saved: ' + reason);
  } else txt.textContent = 'Draft not yet saved';
}
function queueNoteSave(){
  clearTimeout(noteSaveTimer);
  // "Saving…" belongs to a request that is actually running. Setting it here
  // made the chip say "Saving…" for the whole debounce -- restarting on every
  // keystroke -- so a student typing steadily never saw "Unsaved changes" and
  // never saw a "Saved <time>" confirmation either.
  noteSaveTimer = setTimeout(async () => {
    setSaveState('saving');
    const r = await persistNote();
    if (r.saved) {if(r.newer){queueNoteSave();return;}noteSave.at = r.at; setSaveState('saved');}
    else setSaveState('error', r.reason);
  }, 500);
}

/* ======================================================================== */
/* 6. DEBRIEF                                                                */
/* ======================================================================== */
async function renderDebrief(){
  stopVoice(); cancelRunningExam();
  if (tick) clearInterval(tick);
  if (poll) clearInterval(poll);
  clockEl.classList.add('hidden');
  if (!RESULTS || RESULTS.__for !== S.id) {
    view.innerHTML = '<div class="card"><h2>Grading…</h2><p class="small muted">Reading your ' +
      'note against your own encounter record.</p></div>';
    const d = await api(`/api/session/${S.id}/results`);
    if (d.error) { view.innerHTML = `<div class="card"><h2>Results unavailable</h2>
      <p class="small">${esc(d.message || d.error)}</p></div>`; return; }
    RESULTS = d; RESULTS.__for = S.id;
    activeTab = d.reader_versions?.is_regrade ? 'about' : 'lessons';
  }
  paintDebrief();
  window.pcmLearningRender?.(S);
}
function versionsTable(v){
  const rows = ['app','engine','rubric','case','schema'];
  const rec = v.recorded || {}, cur = v.current || {};
  return `<div class="table-scroll"><table class="rows">
    <thead><tr><th>Component</th><th>This attempt ran under</th><th>Running now</th></tr></thead>
    <tbody>${rows.map(k => `<tr>
      <td>${esc(k)}</td>
      <td class="pts">${rec[k] == null ? '<span class="badge b-warn">unknown</span>' : esc(String(rec[k]))}</td>
      <td class="pts">${cur[k] == null ? '—' : esc(String(cur[k]))}</td></tr>`).join('')}
    </tbody></table></div>`;
}
function paintDebrief(){
  const r = RESULTS.results;
  const recovery=draftValue('note',S.id);
  const historical=RESULTS.reader_versions?.is_regrade;
  const tabs = [['lessons','Three lessons'],['score','Score'],['timeline','Timeline'],
    ['audit','Documentation'],['checklist','Encounter checklist'],['comm','Communication'],
    ['notes','Note comparison'],['transcript','Transcript'],['practice','Deliberate practice'],
    ['about','About this case']];
  // Only the panel changes when a tab changes. Rebuilding the whole view threw
  // away an answered repair exercise, re-fetched /repair and /learning on every
  // tab click, and replaced the result card for no reason.
  const built = view.dataset.debriefFor === S.id && $('.tabs');
  if (built) {
    $$('.tabs button').forEach(b => { const on = b.dataset.t === activeTab;
      b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1; });
    $('#tabBody').setAttribute('aria-labelledby', 'tab-' + activeTab);
    return paintDebriefBody(r);
  }
  view.dataset.debriefFor = S.id;
  view.innerHTML = `${historical?'<div class="callout small"><b>Preserved historical result.</b> This note was graded under an earlier or unrecorded engine. Its score and feedback remain unchanged; earlier interpretation errors may still appear below. Use <b>Deliberate practice → Grade the revision</b> for a separate evaluation with the current grader.</div>':''}<div class="tabs" role="tablist" aria-label="Debrief sections">${
    tabs.map(pair => `<button role="tab" id="tab-${pair[0]}" data-t="${pair[0]}"
      aria-selected="${pair[0] === activeTab}" aria-controls="tabBody"
      tabindex="${pair[0] === activeTab ? '0' : '-1'}">${esc(pair[1])}</button>`).join('')}</div>
    <div id="tabBody" role="tabpanel" aria-labelledby="tab-${activeTab}" tabindex="0"></div>`;
  if(recovery)view.insertAdjacentHTML('beforeend',`<details class="card"><summary>Recovered local draft — separate from your submitted note</summary><p class="small">These edits remained in this browser when the note period closed. They have not changed your original submission or score.</p><pre class="note-out">${esc(JSON.stringify(recovery,null,2))}</pre></details>`);
  // The result, then the feedback, then what to do next. An exercise and a
  // "next practice" card between the score and the tabs pushed the first of
  // the three lessons 680px down the page.
  if(!historical&&S.case_id)view.insertAdjacentHTML('beforeend',`<div class="debrief-next"><div><b>Your next practice</b><span class="small muted">Repair one missed step, then try a fresh case.</span></div><a class="btn sm" href="#learn/${esc(S.case_id)}?variant=${encodeURIComponent(S.variant_id||'base')}">Read this case walkthrough →</a></div>`);
  // The result comes first. The page used to open on a repair exercise and a
  // "next practice" card, so the one thing the student came back for -- how did
  // I do -- was below the fold, under eleven tabs.
  {
    const rub = r.rubric || {}, earned = rub.total_earned, available = rub.total_available;
    const top = (RESULTS.results.feedback?.priority_errors || [])[0];
    const pct = (available ? Math.round(earned / available * 100) : null);
    view.insertAdjacentHTML('afterbegin', `<section class="debrief-result card">
      <div class="dr-score"><span class="dr-num">${esc(String(earned))}<span class="dr-of">/${esc(String(available))}</span></span>
        <span class="tiny muted">${pct===null?'':esc(pct + '%')} \u00b7 ${esc(rub.grade_kind || 'PCM 2026 SOAP rubric')}</span></div>
      <div class="dr-lead"><p class="eyebrow">${esc([S.learning_mode, RESULTS.results.assistance?.assisted ? 'assisted' : 'unassisted'].filter(Boolean).join(' \u00b7 '))}</p>
        ${top ? `<p class="dr-first"><b>Start here:</b> ${esc(top.title || '')}</p>` : ''}
        <p class="tiny muted">Every requirement, the evidence behind it and your note are in the tabs below.</p></div>
      <div class="dr-actions"><a class="btn sm primary" href="#practice">Start another encounter</a></div>
    </section>`);
  }
  const btns = $$('.tabs button');
  btns.forEach((b, i) => {
    b.onclick = () => { activeTab = b.dataset.t; paintDebrief(); $('#tab-' + activeTab).focus(); };
    b.onkeydown = e => {
      let j = null;
      if (e.key === 'ArrowRight') j = (i + 1) % btns.length;
      if (e.key === 'ArrowLeft')  j = (i - 1 + btns.length) % btns.length;
      if (e.key === 'Home') j = 0;
      if (e.key === 'End')  j = btns.length - 1;
      if (j === null) return;
      e.preventDefault(); activeTab = btns[j].dataset.t; paintDebrief(); $('#tab-' + activeTab).focus();
    };
  });
  paintDebriefBody(r);
  window.pcmLearningRender?.(S);
}
function paintDebriefBody(r){
  $('#tabBody').innerHTML = ({ lessons:tabLessons, score:tabScore, timeline:tabTimeline,
    audit:tabAudit, checklist:tabChecklist, comm:tabComm, notes:tabNotes,
    transcript:tabTranscript, practice:tabPractice, about:tabAbout }[activeTab] || tabLessons)(r);
  if (activeTab === 'practice') wirePractice(r);
  if (activeTab === 'lessons') wireLessons();
  if (activeTab === 'timeline' && tlFocus != null) {
    const el = $('.tl-row[data-seq="' + tlFocus + '"]');
    if (el) { el.classList.add('hilite'); el.scrollIntoView({ block:'center' }); }
    tlFocus = null;
  }
}

/* --- the three lessons ---------------------------------------------------- */
function lessonsFor(r){
  const out = (r.feedback.priority_errors || []).slice(0, 3).map(it => ({
    title: it.title, kind: it.kind, what: it.what_happened, passage: it.passage,
    evidence: it.evidence || [], why: it.why_it_matters, next: it.what_to_do,
    rule: courseRule(it, r)
  }));
  if (out.length < 3) {
    r.rubric.rows.filter(x => !x.earned).sort((a, b) => b.points_available - a.points_available)
      .forEach(row => {
        if (out.length >= 3) return;
        if (out.some(o => o.title === row.label)) return;
        out.push({ title: row.label + ' — ' + row.points_available + ' points not earned',
          kind:'rubric', what: row.why, passage: row.passage, evidence: row.evidence || [],
          why: 'This row is on the PCM 2026 SOAP note grading table and is worth ' +
               row.points_available + ' of 100.',
          next: 'Write the ' + row.category.toLowerCase() + ' content this row names, in ' +
                'the section it belongs to.',
          rule: 'PCM 2026 SOAP note grading table — ' + row.category + ' · ' +
                row.label + (row.conditions_applied && row.conditions_applied.length
                  ? ' · condition: ' + row.conditions_applied[0] : '') });
      });
  }
  return out;
}
function courseRule(it, r){
  if (it.kind === 'documentation') return (r.feedback.corrected_note || {}).rule || '';
  if (it.kind === 'communication')
    return (r.ips && r.ips.acir ? r.ips.acir.provenance : '') || '';
  const row = (r.rubric.rows || []).filter(x => it.title && it.title.indexOf(x.label) >= 0)[0];
  if (row) return 'PCM 2026 SOAP note grading table — ' + row.category + ' · ' +
    row.label + ' (' + row.points_available + ' points).';
  return 'PCM 2026 SOAP note grading table.';
}
function tabLessons(r){
  const L = lessonsFor(r);
  const rev = r.clinical_review || {}, d = drillOf();
  return `<div class="card">
    <div class="card-head"><h2>Three things to work on</h2><div class="spacer"></div>
      <span class="badge b-mute">${esc(r.label)}</span></div>
    <p class="small muted">Your exact action or wording, why it matters, and what to do
    instead next time. Everything else in this debrief is detail underneath these.</p>
  </div>
  ${!L.length ? '<div class="card"><p>Nothing was flagged as a priority. Work through the ' +
    'other tabs — the rubric rows and the documentation audit are the detail.</p></div>'
  : L.map((l, i) => `<div class="lesson ${l.kind === 'rubric' ? 'bad' : l.kind === 'documentation' ? 'warn' : 'info'}">
    <h3><span class="l-n" aria-hidden="true">${i + 1}</span><span>${esc(l.title)}</span></h3>
    <div class="l-block"><div class="l-key">What you did</div>
      <div class="small">${esc(l.what)}</div>
      ${l.passage ? `<div class="quote you">${esc(l.passage)}</div>` : ''}
      ${(l.evidence || []).slice(0, 2).map(e => `<div class="ev">
        <b>${esc(e.time || '')} ${esc((e.kind || '').replace(/_/g, ' '))}</b> — ${esc(e.text)}</div>`).join('')}
    </div>
    <div class="l-block"><div class="l-key">Why it matters</div>
      <div class="small">${esc(l.why)}</div></div>
    <div class="l-block"><div class="l-key">Better next attempt</div>
      <div class="small">${esc(l.next)}</div></div>
    <div class="l-links">
      ${(l.evidence || []).length && l.evidence[0].time
        ? `<button class="btn sm" type="button" data-jump="${esc(l.evidence[0].time)}">Show it on the timeline</button>` : ''}
      <button class="btn sm" type="button" data-goto="about">Clinical evidence for this case</button>
      <button class="btn sm ghost" type="button" data-rule="${esc(l.rule)}">Course rule</button>
      <button class="btn sm" type="button" data-branch="${esc(l.title)}"
        data-at="${esc((l.evidence || [])[0] ? l.evidence[0].time : '')}">Practice this moment</button>
    </div>
  </div>`).join('')}
  ${d ? drillCard(r, d) : ''}
  <div class="card">
    <div class="card-head"><h3>Review status for this case</h3>
      <span class="badge ${rev.status === 'not_reviewed' ? 'b-bad' : 'b-warn'}">${esc(rev.label || 'Not reviewed')}</span></div>
    <p class="small">${esc(rev.disclaimer || 'No licensed clinician has reviewed or approved any case in this app.')}</p>
    <button class="btn sm" type="button" data-goto="about">Sources and limits</button>
  </div>`;
}
function wireLessons(){
  $$('[data-jump]').forEach(b => { b.onclick = () => {
    tlFocus = seqForTime(b.dataset.jump); activeTab = 'timeline'; paintDebrief(); }; });
  $$('[data-goto]').forEach(b => { b.onclick = () => { activeTab = b.dataset.goto; paintDebrief(); }; });
  $$('[data-rule]').forEach(b => { b.onclick = () => toast(b.dataset.rule); });
  $$('[data-branch]').forEach(b => { b.onclick = () =>
    branchFrom(b.dataset.branch, seqForTime(b.dataset.at)); });
}
function seqForTime(t){
  const rows = RESULTS.transcript || [];
  if (!rows.length) return null;
  if (t) {
    const exact = rows.filter(r => r.time === t)[0];
    if (exact) return exact.seq;
    const parts = String(t).split(':');
    const lim = (parseInt(parts[0], 10) || 0) * 60000 + (parseInt(parts[1], 10) || 0) * 1000;
    let cand = null;
    rows.forEach(r => { if (r.t_ms <= lim) cand = r.seq; });
    if (cand != null) return cand;
  }
  return rows[rows.length - 1].seq;
}
function drillCard(r, d){
  const m = drillMeasure(r, d.key);
  return `<div class="card">
    <div class="card-head"><h3>Drill — ${esc(d.name)}</h3><div class="spacer"></div>
      <span class="badge ${m.tone}">${esc(m.verdict)}</span></div>
    <p class="small"><b>Goal.</b> ${esc(d.goal)}</p>
    <div class="small">${m.detail}</div>
    <p class="tiny muted" style="margin-top:var(--sp-2)">Measured from ${esc(d.measure)}
    A drill re-reads the same measurements the debrief already made; it adds no new score.</p>
  </div>`;
}
function drillMeasure(r, key){
  const sig = (r.ips && r.ips.signals) || {};
  const rel = ((r.ips || {}).relationship || {}).items || [];
  const acir = ((r.ips || {}).acir || {}).items || [];
  const find = (list, needle) => list.filter(i =>
    (i.name || i.label || '').toLowerCase().indexOf(needle) >= 0)[0];
  if (key === 'summary') {
    const a = find(acir, 'summar'), b = find(rel, 'summary');
    const ok = (sig.summary_items || 0) >= 3;
    return { tone: ok ? 'b-ok' : 'b-bad', verdict: ok ? 'met' : 'not met',
      detail: 'Summary items counted: <b>' + (sig.summary_items || 0) + '</b> (three needed). ' +
        'Verified with the patient: <b>' + (sig.summary_verified ? 'yes' : 'no') + '</b>.' +
        (a ? '<div class="small muted">ACIR: ' + esc(a.why || a.reason || '') + '</div>' : '') +
        (b ? '<div class="small muted">Relationship form: ' + esc(b.why || b.reason || '') + '</div>' : '') };
  }
  if (key === 'focused_exam') {
    const p = r.checklist.physical_score || { performed:0, total:0 };
    const ok = p.total && p.performed >= Math.ceil(p.total * 0.7);
    return { tone: ok ? 'b-ok' : 'b-warn', verdict: p.performed + ' of ' + p.total,
      detail: 'Checklist physical items performed: <b>' + p.performed + '/' + p.total + '</b>.' +
        ((r.feedback.missed_exams || []).length
          ? '<ul class="tight small">' + r.feedback.missed_exams.slice(0, 5)
              .map(m => '<li>' + esc(m.text) + ' — ' + esc(m.status) + '</li>').join('') + '</ul>'
          : '<div class="small">Nothing on the checklist was left incomplete.</div>') };
  }
  if (key === 'safety_net') {
    const parts = [['what you will do', sig.closure_self],
                   ['what the patient should do', sig.closure_patient],
                   ['when to come back', sig.closure_when]];
    const got = parts.filter(p => p[1]).length;
    return { tone: got >= 2 ? 'b-ok' : 'b-bad', verdict: got + ' of 3 elements',
      detail: parts.map(p => '<div class="small">' + (p[1] ? '✓ ' : '✗ ') + esc(p[0]) + '</div>').join('') };
  }
  const c = r.audit.counts || {};
  const bad = (c.unsupported || 0) + (c.contradicts || 0) + (c.overbroad || 0) + (c.misplaced || 0);
  return { tone: bad === 0 ? 'b-ok' : bad <= 2 ? 'b-warn' : 'b-bad',
    verdict: bad + ' flagged claim' + (bad === 1 ? '' : 's'),
    detail: 'Unsupported ' + (c.unsupported || 0) + ' · contradicts ' + (c.contradicts || 0) +
      ' · broader than examined ' + (c.overbroad || 0) + ' · wrong section ' +
      (c.misplaced || 0) + ' · obtained but never written down ' +
      ((r.audit.obtained_but_omitted || []).length) + '.' };
}

/* --- score ---------------------------------------------------------------- */
function tabScore(r){
  const g = r.rubric;
  const cats = ['Subjective','Objective','Assessment','Plan','Overall'];
  return `<div class="card">
    <div class="score-hero">
      <div><div class="score-big">${g.total_earned}<small>/${g.total_available}</small></div>
        <div class="small muted">rubric-based practice grade</div></div>
      <div class="catbars">${cats.map(c => {
        const v = g.categories[c] || { earned:0, available:0 };
        const pct = v.available ? 100 * v.earned / v.available : 0;
        return `<div class="catbar"><span>${esc(c)}</span>
          <span class="progressbar" role="img" aria-label="${esc(c)}: ${v.earned} of ${v.available}"
            ><span style="width:${pct}%"></span></span>
          <span class="num">${v.earned}/${v.available}</span></div>`; }).join('')}</div>
    </div>
    <div class="callout mute small" style="margin-top:var(--sp-4)">${esc(g.disclaimer)}
    ${r.assisted ? '<br><b>Assisted mode was on for this attempt</b> — the transcript was visible while writing.' : ''}</div>
    ${!r.integrity.clean ? `<div class="callout warn small"><b>Interruptions recorded.</b>
      ${r.integrity.events.map(e => esc(e.detail)).join(' ')} ${esc(r.integrity.note)}</div>` : ''}
  </div>
  <div class="card"><h2>Every row</h2>
    <div class="table-scroll"><table class="rows">
    <thead><tr><th>Row</th><th>Verdict</th><th class="pts">Pts</th></tr></thead><tbody>
    ${g.rows.map(row => `<tr class="${row.earned ? '' : 'miss'}">
      <td><b>${esc(row.label)}</b> <span class="tiny muted">${esc(row.category)}</span>
        <div class="small">${esc(row.why)}</div>
        ${row.passage ? `<div class="quote">${esc(row.passage)}</div>` : ''}
        ${(row.conditions_applied || []).map(c => `<div class="tiny"><span class="badge b-bad">condition</span> ${esc(c)}</div>`).join('')}
        ${(row.advisories || []).map(a => `<div class="tiny"><span class="badge b-warn">advisory</span> ${esc(a)}</div>`).join('')}
        ${row.uncertain ? `<div class="tiny"><span class="badge b-info">interpretation</span> ${esc(row.uncertain)}</div>` : ''}
        ${(row.evidence || []).map(e => `<div class="ev tiny"><b>${esc(e.time || '')} ${esc(e.kind || '')}</b> ${esc(e.text)}</div>`).join('')}
      </td><td>${row.earned ? '<span class="badge b-ok">earned</span>' : '<span class="badge b-bad">no credit</span>'}</td>
      <td class="pts">${row.points_earned}/${row.points_available}</td></tr>`).join('')}
    </tbody></table></div></div>
  <div class="card"><h2>Timing</h2>
    <p class="small">${esc(r.timing.preset)} — encounter ${mmss(r.timing.encounter_used_s * 1000)}
    ${r.timing.untimed ? 'elapsed, without a deadline; SOAP writing was also untimed.' : 'of '+mmss(r.timing.encounter_allowed_s * 1000)+' used; note '+mmss(r.timing.note_allowed_s * 1000)+'.'}
    Submitted: <b>${esc(r.timing.submit_reason || 'submitted')}</b>.
    Interaction mode: <b>${esc(S.interaction_mode)}</b> — ${S.interaction_mode === 'voice'
      ? 'recognition latency is inside every measured pause, so pacing is reported, not graded.'
      : 'pauses reflect typing speed, so pacing is reported, not graded as conversational rhythm.'}</p>
    ${r.timing.modified ? `<div class="callout warn small">${esc(r.timing.modification_note)}</div>` : ''}
    <div class="callout mute small">${esc(r.timing.carry_over_note)}</div>
    ${r.feedback.time_management.notes.map(n => `<div class="small">• ${esc(n)}</div>`).join('')}
  </div>`;
}

/* --- timeline -------------------------------------------------------------- */
function tabTimeline(r){
  const rows = RESULTS.transcript || [];
  const span = Math.max(1, rows.length ? rows[rows.length - 1].t_ms : 1);
  const kindClass = k => k === 'patient_reply' ? 'k-patient'
    : (k === 'exam_action' || k === 'exam_finding' || k === 'exam_refused') ? 'k-exam'
    : (k === 'system' || k === 'station_info') ? 'k-system' : '';
  return `<div class="card"><h2>${r.timing?.untimed ? 'Your untimed encounter timeline' : 'How your encounter time was used'}</h2>
    <p class="small muted">Every recorded event in order, with the bar showing how far into
    the encounter it happened. Examinations show start, completion and released findings. Duration is shown once, at completion; these milestones belong to one action.</p>
    <div class="row">${Object.keys(RESULTS.evidence_summary || {}).map(k =>
      `<span class="badge b-mute">${esc(k.replace(/_/g, ' '))}: ${RESULTS.evidence_summary[k]}</span>`).join('')}</div>
  </div>
  <div class="card"><ol class="timeline">
    ${rows.map(t => {
      const w = clamp(100 * t.t_ms / span, 1, 100);
      const dur = t.kind==='exam_action' && t.meta?.status!=='in_progress' ? t.meta?.duration_s : null;
      return `<li class="tl-row ${kindClass(t.kind)}" data-seq="${t.seq}">
        <span class="tl-t">${esc(t.time)}</span>
        <span class="tl-kind"><span class="badge b-mute">${esc(t.kind.replace(/_/g, ' '))}</span></span>
        <span class="tl-text">${esc(t.text)}
          ${dur ? `<span class="tiny muted"> · occupied ${dur}s</span>` : ''}
          ${t.meta && t.meta.uncertain ? ' <span class="badge b-warn">uncertain</span>' : ''}
          ${t.meta && t.meta.volunteered ? ' <span class="badge b-info">volunteered</span>' : ''}</span>
        <span class="tl-bar"><span style="width:${w}%"></span></span>
      </li>`; }).join('')}
  </ol></div>`;
}

/* --- documentation audit --------------------------------------------------- */
function tabAudit(r){
  const a = r.audit;
  const order = ['contradicts','unsupported','overbroad','misplaced',
    'counseling_unsupported','supported','supported_supplied','counseling_ok',
    'hypothesis','proposed','not_evaluated'];
  const label = { supported:['b-ok','supported'], supported_supplied:['b-ok','supported — supplied'],
    unsupported:['b-bad','unsupported'], contradicts:['b-bad','contradicts the encounter'],
    overbroad:['b-warn','broader than you examined'], misplaced:['b-warn','wrong section'],
    counseling_ok:['b-ok','discussion happened'],
    counseling_unsupported:['b-bad','discussion not recorded'],
    hypothesis:['b-info','hypothesis'], proposed:['b-info','proposed action'],
    not_evaluated:['b-mute','not evaluated'] };
  const claims = a.claims.slice().sort((x, y) => order.indexOf(x.verdict) - order.indexOf(y.verdict));
  return `<div class="card"><h2>Claim-by-claim documentation audit</h2>
    <p class="small muted">Every sentence checked against your own encounter record — not
    against the case. A fact being true of the patient does not make it documentable.</p>
    <div class="row">${Object.keys(a.counts).map(k =>
      `<span class="badge ${(label[k] || ['b-mute'])[0]}">${esc((label[k] || [0, k])[1])}: ${a.counts[k]}</span>`).join('')}</div></div>
  ${a.internal_contradictions.length ? `<div class="card"><h3>Your note contradicts itself</h3>
    ${a.internal_contradictions.map(ic => `<div class="item bad">
      <h4>${esc(ic.concept.replace(/_/g, ' '))}</h4>
      <div class="quote">${esc(ic.first_section)}: ${esc(ic.first)}</div>
      <div class="quote">${esc(ic.second_section)}: ${esc(ic.second)}</div>
      <div class="small">${esc(ic.explanation)}</div></div>`).join('')}</div>` : ''}
  ${a.obtained_but_omitted.length ? `<div class="card">
    <h3>You obtained these and did not document them <span class="badge b-warn">${a.obtained_but_omitted.length}</span></h3>
    <p class="small muted">This is the most common documentation failure in the published
    literature — students obtain about 87% of items but document barely half of the
    negatives.</p>
    ${a.obtained_but_omitted.map(o => `<div class="chk">
      <span class="st"><span class="badge b-warn">${esc(o.time)}</span></span>
      <span class="tx"><b>${esc(o.label)}</b> — ${esc(o.value)}
      <div class="tiny muted">&ldquo;${esc(o.quote)}&rdquo;</div></span></div>`).join('')}</div>` : ''}
  <div class="card"><h3>Claims</h3>${claims.map(c => {
    const pair = label[c.verdict] || ['b-mute', c.verdict];
    const tone = pair[0] === 'b-bad' ? 'bad' : pair[0] === 'b-warn' ? 'warn'
      : pair[0] === 'b-ok' ? 'ok' : pair[0] === 'b-info' ? 'info' : 'mute';
    return `<div class="item ${tone}"><h4><span class="badge ${pair[0]}">${esc(pair[1])}</span>
      <span class="tiny muted">${esc(c.section)}${c.header ? ' · ' + esc(c.header) : ''}</span></h4>
      <div class="quote">${esc(c.text)}</div>
      <div class="small">${esc(c.explanation)}</div>
      ${(c.evidence || []).map(e => `<div class="ev"><b>${esc(e.time || '')} ${esc(e.kind || '')}</b> — ${esc(e.text)}${e.value ? ' <i>(' + esc(e.value) + ')</i>' : ''}</div>`).join('')}
    </div>`; }).join('')}</div>`;
}

/* --- checklist ------------------------------------------------------------- */
function tabChecklist(r){
  const c = r.checklist;
  const st = s => ({ obtained:'b-ok', performed:'b-ok', partial:'b-warn', selected:'b-warn',
                     omitted:'b-bad' }[s] || 'b-mute');
  return `<div class="card"><h2>Case checklist</h2><p class="small muted">${esc(c.note)}</p>
    <div class="row"><span class="badge b-ok">history ${c.history_score.yes}/${c.history_score.total}</span>
    <span class="badge b-ok">physical ${c.physical_score.performed}/${c.physical_score.total}</span></div></div>
  <div class="card"><h3>History items</h3>${c.history.map(h => `<div class="chk">
    <span class="st"><span class="badge ${st(h.status)}">${esc(h.status)}</span></span>
    <span class="tx">${esc(h.text)}${h.quote ? `<div class="tiny muted">${esc(h.time)} — &ldquo;${esc(h.quote)}&rdquo;</div>` : ''}</span></div>`).join('')}</div>
  <div class="card"><h3>Physical examination items</h3>${c.physical.map(p => `<div class="chk">
    <span class="st"><span class="badge ${st(p.status)}">${esc(p.status)}</span></span>
    <span class="tx">${esc(p.text)}${p.detail ? `<div class="tiny muted">${esc(p.detail)}</div>` : ''}
    ${p.not_assessed ? `<div class="tiny"><span class="badge b-mute">not assessed</span> ${esc(p.not_assessed)}</div>` : ''}</span></div>`).join('')}</div>
  <div class="card"><h3>Not assessed in this format</h3>
    <ul class="tight small">${c.not_assessed.map(n => `<li>${esc(n)}</li>`).join('')}</ul></div>
  ${r.feedback.missed_questions.length ? `<div class="card"><h3>Questions you did not ask</h3>
    ${r.feedback.missed_questions.map(m => `<div class="chk">
      <span class="st"><span class="badge b-bad">missed</span></span>
      <span class="tx">${esc(m.text)}${m.example_question ? `<div class="q">Try: &ldquo;${esc(m.example_question)}&rdquo;</div>` : ''}</span></div>`).join('')}</div>` : ''}
  ${r.feedback.missed_exams.length ? `<div class="card"><h3>Examinations you did not complete</h3>
    ${r.feedback.missed_exams.map(m => `<div class="item warn">
      <h4>${esc(m.text)} <span class="badge b-warn">${esc(m.status)}</span></h4>
      ${m.detail ? `<div class="small">${esc(m.detail)}</div>` : ''}
      <div class="small"><b>How.</b> ${esc(m.how)}</div></div>`).join('')}</div>` : ''}`;
}

/* --- communication --------------------------------------------------------- */
function tabComm(r){
  const i = r.ips, ap = r.feedback.assessment_plan;
  const sc = v => v == null ? '<span class="badge b-mute">not assessed</span>'
    : `<span class="badge ${v >= 5 ? 'b-ok' : v >= 3 ? 'b-warn' : 'b-bad'}">${v}</span>`;
  const vin = BOOT.vindicate || {};
  return `<div class="card"><h2>Communication and interpersonal skills</h2>
    <p class="small muted">${esc(i.note)}</p>
    <p class="small"><b>Arizona Clinical Interview Rating Scale</b> — ${esc(i.acir.anchors)}.
    Mean of scored items: <b>${i.acir.mean == null ? '—' : i.acir.mean}</b>
    (${i.acir.scored_items} of ${i.acir.total_items} scored).</p>
    <div class="callout mute small">${esc(i.acir.provenance)}</div></div>
  <div class="card"><h3>ACIR items</h3>${i.acir.items.map(it => `
    <div class="item ${it.not_assessed ? 'mute' : it.score >= 5 ? 'ok' : it.score >= 3 ? 'warn' : 'bad'}">
      <h4>${it.number}. ${esc(it.name)} ${sc(it.score)}</h4>
      <div class="small">${esc(it.why || it.reason)}</div>
      ${(it.evidence || []).map(e => `<div class="quote">${esc(e.quote || '')}${e.time ? ` <span class="tiny">(${esc(e.time)})</span>` : ''}</div>`).join('')}
    </div>`).join('')}</div>
  <div class="card"><h3>Interpersonal Skills Relationship Form</h3>
    <p class="small muted">${esc(i.relationship.anchors)}</p>
    <div class="table-scroll"><table class="rows"><tbody>${i.relationship.items.map(it => `<tr>
      <td>${it.number}. ${esc(it.label)}<div class="small muted">${esc(it.why || it.reason)}</div>
      ${it.partially_assessed ? `<div class="tiny"><span class="badge b-mute">partial</span> ${esc(it.partially_assessed)}</div>` : ''}</td>
      <td class="pts">${sc(it.score)}</td></tr>`).join('')}</tbody></table></div></div>
  <div class="card"><h3>Signals measured</h3><div class="table-scroll"><table class="rows"><tbody>${Object.keys(i.signals)
    .map(k => `<tr><td>${esc(k.replace(/_/g, ' '))}</td><td class="pts">${esc(Array.isArray(i.signals[k]) ? i.signals[k].join(' → ') : i.signals[k])}</td></tr>`).join('')}</tbody></table></div></div>
  <div class="card"><h3>Assessment and plan</h3>
    ${ap.notes.length ? ap.notes.map(n => `<div class="item warn"><div class="small">${esc(n)}</div></div>`).join('')
      : '<p class="small">No structural problems found with your differential or plan elements.</p>'}
    <div class="small muted">VINDICATE elements you used: ${esc((ap.vindicate_used || [])
      .filter(Boolean).map(l => vin[l] || l).join(', ') || 'none matched')}</div>
    <div class="small muted">Acceptable differentials for this case:
      ${ap.case_acceptable_differentials.map(d => `${esc(d.name)} <span class="tiny">(${esc(vin[d.vindicate] || d.vindicate)}, rank ${d.rank})</span>`).join(' · ')}</div></div>
  <div class="card"><h3>Worked examples</h3>${(r.feedback.worked_examples || []).map(w => `
    <div class="item info"><h4>${esc(w.kind)}</h4>
      <div class="quote del">${esc(w.before)}</div>
      <div class="quote ins">${esc(w.after)}</div>
      <div class="small muted">${esc(w.note)}</div></div>`).join('')}</div>
  <div class="card"><h3>Not assessed</h3>
    <ul class="tight small">${(r.feedback.not_assessed || []).map(n => `<li>${esc(n)}</li>`).join('')}</ul></div>`;
}

/* --- note comparison ------------------------------------------------------- */
function tabNotes(r){
  const orig = r.note || {}, corr = r.feedback.corrected_note || {},
        ideal = (r.feedback.ideal || {}).model_note || {};
  const secs = [['S','Subjective'],['O','Objective'],['A','Assessment'],['P','Plan']];
  const txt = (obj, k) => Array.isArray(obj[k]) ? (obj[k] || []).join('\n') : (obj[k] || '');
  return `<div class="card"><h2>Your note, corrected, and the model</h2>
    <div class="callout">${esc(corr.rule || '')}</div>
    <div class="callout warn">${esc((r.feedback.ideal || {}).rule || '')}</div>
    ${(corr.removed || []).length ? `<h4>Removed — not supported by your encounter (${corr.removed.length})</h4>
      ${corr.removed.map(x => `<div class="quote del">${esc(x.section)}: ${esc(x.text)}</div>`).join('')}` : ''}
    ${(corr.added || []).length ? `<h4>Added — you obtained these and left them out (${corr.added.length})</h4>
      ${corr.added.map(x => `<div class="quote ins">${esc(x.section)}: ${esc(x.text)}</div>`).join('')}` : ''}
  </div>
  ${secs.map(pair => `<div class="card"><h3>${esc(pair[1])}</h3>
    <div class="compare">
      <div><div class="col-head orig">What you wrote</div>
        <pre class="note-out">${esc(txt(orig, pair[0])) || 'empty'}</pre></div>
      <div><div class="col-head corr">Corrected against your encounter</div>
        <pre class="note-out">${esc(txt(corr, pair[0]))}</pre></div>
      <div><div class="col-head ideal">Model note for this case</div>
        <pre class="note-out">${esc(txt(ideal, pair[0]))}</pre></div>
    </div></div>`).join('')}
  ${((r.feedback.ideal || {}).extra_questions || []).length ? `<div class="card">
    <h3>What you would have had to ask to write the model note</h3>
    <div class="table-scroll"><table class="rows">
    <thead><tr><th>Ask</th><th>You would have learned</th></tr></thead><tbody>
    ${r.feedback.ideal.extra_questions.map(q => `<tr><td class="small">${esc(q.would_have_asked)}</td>
      <td class="small">${esc(q.would_have_learned)}</td></tr>`).join('')}</tbody></table></div></div>` : ''}
  ${((r.feedback.ideal || {}).extra_exams || []).length ? `<div class="card">
    <h3>Examinations you would have had to perform</h3>
    ${r.feedback.ideal.extra_exams.map(e => `<div class="item ${e.key ? 'bad' : 'warn'}">
      <h4>${esc(e.maneuver)} ${e.key ? '<span class="badge b-bad">key finding</span>' : ''}</h4>
      <div class="small">${esc(e.would_have_found)}</div></div>`).join('')}</div>` : ''}
  ${((r.feedback.ideal || {}).coaching || []).length ? `<div class="card"><h3>Case-specific coaching</h3>
    <ul class="tight small">${r.feedback.ideal.coaching.map(c => `<li>${esc(c)}</li>`).join('')}</ul></div>` : ''}`;
}

/* --- transcript ------------------------------------------------------------ */
function tabTranscript(){
  const rows = RESULTS.transcript || [];
  return `<div class="card"><h2>Encounter evidence record</h2>
    <p class="small muted">Frozen at closure. This is the record every verdict in this
    debrief was checked against.</p>
    ${rows.map(t => `<div class="tx-row"><span class="tt">${esc(t.time)}</span>
      <span class="kk"><span class="badge ${t.kind === 'student_utterance' ? 'b-info' : t.kind === 'patient_reply' ? 'b-ok' : 'b-mute'}">${esc(t.kind.replace(/_/g, ' '))}</span></span>
      <span>${esc(t.text)}${t.meta && t.meta.volunteered ? ' <span class="badge b-info">volunteered</span>' : ''}${t.meta && t.meta.uncertain ? ' <span class="badge b-warn">uncertain</span>' : ''}</span>
    </div>`).join('')}</div>`;
}

/* --- deliberate practice --------------------------------------------------- */
function tabPractice(r){
  // One entry per moment, each carrying the wording that identifies it, so two
  // findings of the same type are not two identical-looking rows.
  const moments = [];
  (r.feedback.priority_errors || []).slice(0, 6).forEach(it => moments.push({
    label: it.title, quote: it.passage || '', why: it.what_to_do, kind: it.kind,
    at: (it.evidence || [])[0] ? it.evidence[0].time : '' }));
  (r.feedback.missed_questions || []).slice(0, 5).forEach(m => moments.push({
    label: 'Never asked: ' + m.text, quote: '',
    why: m.example_question ? 'Try: "' + m.example_question + '"' : '', kind:'history', at:'' }));
  (r.feedback.missed_exams || []).slice(0, 5).forEach(m => moments.push({
    label: 'Incomplete: ' + m.text, quote: '', why: m.how || '', kind:'exam', at:'' }));
  const revs = RESULTS.revisions || [];
  const n = r.note || {};
  const A = (n.A || []).concat(['', '', '']).slice(0, 3);
  const Pn = (n.P || []).concat(['', '', '']).slice(0, 3);
  return `<div class="card"><h2>Deliberate practice</h2>
    <p class="small muted">Your original submission and its score are kept exactly as
    they are. Everything started here is a <b>separate record</b> — a branch names the
    attempt and the moment it grew from, and never overwrites the attempt you just
    finished.</p>
    <div class="row">
      <button class="btn primary" id="btnRetry" type="button">Run the whole station again</button>
      ${revs.length ? `<span class="small">Revisions so far: ${revs.map(x =>
        `<span class="badge b-info">${esc(x.kind)} — ${x.results ? x.results.rubric.total_earned : '?'}/100</span>`).join(' ')}</span>` : ''}
    </div>
  </div>

  <div class="card"><h3>Retry from a missed moment</h3>
    <p class="small muted">Each one opens a fresh encounter on this same station that
    resumes at that moment. The patient retains information already delivered. Guided retries stay guided; other retries use coached assistance. All retries from a missed moment
    are untimed. The original attempt keeps its timing and score.
    The encounter timeline continues from the selected moment. It is a new attempt, scored on its own.</p>
    ${!moments.length ? '<p class="small">Nothing was flagged to retry.</p>'
      : moments.map((m, i) => `<div class="item ${m.kind === 'rubric' ? 'bad' : m.kind === 'exam' ? 'warn' : 'info'}">
      <h4>${esc(m.label)}</h4>
      ${m.quote ? `<div class="quote">${esc(m.quote)}</div>` : ''}
      ${m.why ? `<div class="small muted">${esc(m.why)}</div>` : ''}
      <div class="row" style="margin-top:var(--sp-2)">
        <button class="btn sm" type="button" data-moment="${i}" data-at="${esc(m.at)}"
          data-label="${esc(m.label)}">Practice this moment</button></div>
    </div>`).join('')}
  </div>

  <div class="card"><h3>Short drills</h3>
    <p class="small muted">Same station, one skill named before you enter and read back to
    you at the debrief from the measurements the engine already makes.</p>
    <div class="drill-grid">${Object.keys(DRILLS).map(k => `
      <div class="item info"><h4>${esc(DRILLS[k].name)}</h4>
        <div class="small">${esc(DRILLS[k].goal)}</div>
        <div class="row" style="margin-top:var(--sp-2)">
          <button class="btn sm" type="button" data-drill="${k}">Start this drill</button></div>
      </div>`).join('')}</div>
  </div>

  <div class="card"><h3>Revise the note against the same encounter</h3>
    <p class="small muted">Untimed, clearly labelled, kept as an extra record beside the
    original, and it cannot fix what you did not obtain in the room.</p>
    <div class="note-sheet">
      <div class="note-sec"><div class="sec-head"><span class="sec-letter">S</span>
        <span class="sec-name">Subjective</span></div>
        <label class="sr-only" for="rS">Revised subjective</label>
        <textarea id="rS">${esc(n.S || '')}</textarea></div>
      <div class="note-sec"><div class="sec-head"><span class="sec-letter">O</span>
        <span class="sec-name">Objective</span></div>
        <label class="sr-only" for="rO">Revised objective</label>
        <textarea id="rO">${esc(n.O || '')}</textarea></div>
      ${[0, 1, 2].map(i => `<div class="ap-pair">
        <div class="pair-head"><span class="pair-no">${i + 1}</span><span>Assessment and plan</span></div>
        <div class="ap-cols">
          <div><div class="ap-lab" id="ralab${i}">Assessment ${i + 1}</div>
            <textarea id="rA${i}" rows="2" aria-labelledby="ralab${i}">${esc(A[i])}</textarea></div>
          <div><div class="ap-lab" id="rplab${i}">Plan ${i + 1}</div>
            <textarea id="rP${i}" rows="2" aria-labelledby="rplab${i}">${esc(Pn[i])}</textarea></div>
        </div></div>`).join('')}
    </div>
    <div class="row" style="margin-top:var(--sp-3)">
      <button class="btn primary" id="btnRegrade" type="button">Grade the revision</button></div>
    <div id="revOut"></div>
  </div>`;
}
/* A branch is created by the engine's own retry route, so the parent attempt is
   read and never written, and the branch carries only the evidence the parent
   had produced by that moment. */
async function branchFrom(momentLabel, fromSeq, drill){
  const seq = fromSeq == null ? seqForTime('') : fromSeq;
  if (seq == null) { toast('There is no recorded moment to branch from.'); return; }
  const r = await api(`/api/session/${S.id}/retry`, {
    from_seq: seq, label: momentLabel || 'a missed moment' });
  if (r.error) { toast(r.message || r.error); return; }
  const b = r.branch;
  clearPendingReveals();
  const meta = uiMeta(S.id);
  setUiMeta(b.id, { ui_mode: drill ? 'drill' : (meta.ui_mode || 'practice'),
                    drill: drill || null });
  RESULTS = null;
  S = b; lastPhase = null;
  room = { view:'front', region:null, instrument:'', position:'seated',
           running:null, runTimer:null, runEnd:null, performed:{} };
  location.hash = '#/' + b.id;
  startPolling(); renderPhase(true);
  toast('Practice branch started. Your finished attempt is untouched.');
}
async function fullRetry(){
  const meta = uiMeta(S.id);
  RESULTS = null;
  await begin(false, { case_id: S.case_id, ui_mode: meta.ui_mode || 'practice',
    drill: meta.drill, mode: S.interaction_mode });
}
function wirePractice(r){
  $('#btnRetry').onclick = () => fullRetry();
  $$('[data-moment]').forEach(b => { b.onclick = () =>
    branchFrom(b.dataset.label, seqForTime(b.dataset.at)); });
  $$('[data-drill]').forEach(b => { b.onclick = () =>
    branchFrom(DRILLS[b.dataset.drill].name + ' drill', seqForTime(''), b.dataset.drill); });
  $('#btnRegrade').onclick = async () => {
    const g = id => { const e = $('#' + id); return e ? e.value : ''; };
    const note = { S:g('rS'), O:g('rO'),
      A:[0,1,2].map(i => numberedEntry(i, g('rA' + i))),
      P:[0,1,2].map(i => numberedEntry(i, g('rP' + i))) };
    $('#revOut').innerHTML = '<div class="card" style="margin-top:var(--sp-3)">Grading revision…</div>';
    const d = await api(`/api/session/${S.id}/revise`, { note });
    if (d.error) { $('#revOut').innerHTML = `<div class="card">${esc(d.message || d.error)}</div>`; return; }
    RESULTS.revisions = (RESULTS.revisions || []).concat([{ kind:'revision', results:d.results }]);
    const orig = RESULTS.results.rubric.total_earned;
    const got = d.results.rubric.total_earned;
    $('#revOut').innerHTML = `<div class="card" style="margin-top:var(--sp-3)">
      <div class="card-head"><h3>Revision score</h3>
        <span class="badge b-info">untimed practice</span></div>
      <div class="score-hero"><div><div class="score-big">${got}<small>/100</small></div>
      <div class="small muted">original timed submission: ${orig}/100 — unchanged</div></div></div>
      ${d.results.rubric.rows.filter(x => !x.earned).map(x => `<div class="item bad">
        <h4>${esc(x.label)} — still no credit</h4><div class="small">${esc(x.why)}</div></div>`).join('')}
      <div class="callout mute small">A revision cannot fix what you did not obtain in the
      room. Rows that still fail on evidence are telling you about the encounter, not the
      writing.</div></div>`;
    announce('Revision graded: ' + got + ' out of 100.');
  };
}

/* --- about this case ------------------------------------------------------- */
function tabAbout(r){
  const rev = r.clinical_review || {}, v = RESULTS.reader_versions || r.versions || {}, reveal = RESULTS.case_reveal || {};
  const sources = (rev.sources || []).map(s => typeof s === 'string' ? {url:s,title:s} : s);
  return `<div class="card">
    <div class="card-head"><h2>Clinical review status</h2><div class="spacer"></div>
      <span class="badge ${rev.status === 'not_reviewed' ? 'b-bad' : 'b-warn'}">${esc(rev.label || 'Not reviewed')}</span></div>
    <div class="callout bad">${esc(rev.disclaimer ||
      'No licensed clinician has reviewed or approved any case in this app.')}</div>
    ${rev.date ? `<div class="small muted">Reviewed: ${esc(rev.date)}</div>` : ''}
    ${rev.reviewer ? `<p class="small">${esc(rev.reviewer)}</p>` : ''}
    ${rev.method ? `<p class="small muted"><b>Method.</b> ${esc(rev.method)}</p>` : ''}
    ${rev.what_changed ? `<p class="small"><b>What changed.</b> ${esc(rev.what_changed)}</p>` : ''}
    ${rev.limits ? `<p class="small muted"><b>Limits.</b> ${esc(rev.limits)}</p>` : ''}
    <h3>Sources</h3>
    ${sources.length ? `<ul class="tight small">${sources.map(s =>
      `<li>${/^https?:\/\//i.test(s.url || '') ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title || s.url)}</a>`
        : esc(s.title || '')}</li>`).join('')}</ul>`
      : '<p class="small muted">No sources are recorded for this case.</p>'}
  </div>
  <div class="card"><h2>The case</h2>
    <p class="small"><b>${esc(reveal.title || '')}</b> — ${esc(reveal.system || '')}. ${esc(reveal.blurb || '')}</p>
    ${reveal.patient ? `<p class="small muted">${esc(reveal.patient.name || '')} · ${esc(String(reveal.patient.age || ''))} · ${esc(reveal.patient.sex || '')}</p>` : ''}
    <p class="tiny muted">${esc(reveal.curriculum_note || '')}</p></div>
  <div class="card"><h2>Versions this attempt ran under</h2>
    ${versionsTable(v)}
    ${v.notice ? `<div class="callout warn small">${esc(v.notice)}</div>` : ''}
    ${v.differs_from_current ? '<div class="callout warn small">This attempt is being read ' +
      'under a different version than it was recorded under.</div>' : ''}
    <p class="tiny muted">Case id: ${esc(v.case_id || S.case_id)}</p>
  </div>
  <div class="card"><h2>Assumptions behind this score</h2>${r.assumptions.map(a => `
    <div class="item ${a.status === 'provisional' ? 'warn' : 'mute'}">
      <h4>${esc(a.topic)} <span class="badge ${a.status === 'provisional' ? 'b-warn' : 'b-mute'}">${esc(a.status)}</span></h4>
      <div class="small"><b>${esc(a.value)}</b></div>
      <div class="small muted">${esc(a.detail)}</div></div>`).join('')}</div>
  <div class="card"><h2>Rubric conditions applied</h2>${Object.keys(r.rubric.conditions)
    .map(cat => `<h4>${esc(cat)}</h4><ul class="tight small">${r.rubric.conditions[cat]
      .map(c => `<li>${esc(c)}</li>`).join('')}</ul>`).join('')}</div>`;
}

/* The web app owns evidence; Unity receives public encounter state only. */
function unityCatalog(){return catalog().flatMap(group=>group.maneuvers?group.maneuvers.map(m=>({...m,region:group.region})): [group]);}
function notifyPublicState(){
  window.pcmEncounterWorkspaceState?.(S);
  if(S){room.position=recordedPosition();const pos=$('#posSel');if(pos&&!pos.disabled)pos.value=room.position;}
  window.pcmLearningState?.(S);
  window.pcmAIState?.(S);
  const frame=$('#unityFrame');if(!frame||!S)return;
  const transcript=S.transcript||[],lastPatient=transcript.filter(e=>e.kind==='patient_reply').slice(-1)[0];
  const busyMs=Math.max(0,Number(S.pending_exam?.due_at||0)-now());
  frame.contentWindow?.postMessage({type:'pcm-unity-state',state:{
    sessionId:S.id,caseId:S.case_id,phase:S.phase,mode:S.learning_mode||mode().key,
    respiratoryRate:Number.parseFloat((S.station_chart?.vitals||S.station?.vitals||{}).R)||null,visualDemo:S.visual_demo==='humgen-trial'?'humgen-trial':null,patientName:S.patient_name,patientReply:lastPatient?.text||'',posture:S.patient_posture||'seated',
    comparePrevious:false,appearance:S.appearance||{},affect:S.affect||{},gesture:S.gesture||{},demeanor:S.demeanor||{},listening:patientIsListening(),speaking:Boolean(window.pcmAISpeaking||voice.patientSpeaking),remainingMs:S.phase_ends_at?Math.max(0,S.phase_ends_at-now()):null,
    busyMs,assisted:!!S.assisted,eventSeq:S.event_seq||Math.max(0,...transcript.map(e=>e.seq||0)),
    reducedMotion:!!LS.get('reducedMotion')||window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    examCatalog:unityCatalog()
  }},location.origin);
}
window.addEventListener('message',event=>{
  const frame=$('#unityFrame');if(!frame||event.source!==frame.contentWindow||event.origin!==location.origin)return;const d=event.data||{};
  if(d.type==='pcm-unity-ready'||d.type==='pcm-room-ready'){roomFrameReady=true;if(S?.phase==='briefing'&&!entryPending)setEntryStatus('Ready when you are. The clock starts after you enter.');notifyPublicState();if(entryPending)dispatchEntrance();}
  if(d.type==='pcm-room-entered')completeEntrance(d.requestId);
  if(['pcm-trial-status','pcm-patient-status'].includes(d.type)&&S&&d.sessionId===S.id){patientDisplayStates.set(S.id,d.status);const b=$('#unityStatus');if(b)b.textContent=patientDisplayLabel();if(S.phase==='briefing'&&entryPending&&d.status==='loading')setEntryStatus('Preparing the detailed patient… Your encounter clock has not started.');}
  if(d.type==='pcm-motion-preference'&&S&&d.sessionId===S.id&&typeof d.reducedMotion==='boolean'){LS.set('reducedMotion',d.reducedMotion);if($('#entryReduced'))$('#entryReduced').checked=d.reducedMotion||window.matchMedia('(prefers-reduced-motion: reduce)').matches;notifyPublicState();}
  if(d.type==='pcm-unity-error'&&S?.phase==='briefing'){setEntryStatus('The 3D room is unavailable. Your timer has not started. Use accessible controls to continue.');}
});
const unityRequests=new Map();
window.addEventListener('message',async event=>{
  const frame=$('#unityFrame');if(!frame||event.source!==frame.contentWindow||event.origin!==location.origin)return;
  const data=event.data||{};
  if(data.type==='pcm-unity-ready'){const badge=$('#unityStatus');if(badge)badge.textContent=patientDisplayLabel();notifyPublicState();return;}
  if(data.type==='pcm-unity-error'){const badge=$('#unityStatus');if(badge)badge.textContent='Use accessible controls';toast('The 3D room is unavailable. Conversation and examination controls still work.');return;}
  if(data.type==='pcm-unity-teaching'&&S&&data.sessionId===S.id){
    const r=await api(`/api/session/${S.id}/room-lesson`,data);
    if(r.error)toast(r.message||r.error);
    return;
  }
  if(data.type!=='pcm-unity-action'||!S||data.sessionId!==S.id||typeof data.requestId!=='string'||data.requestId.length>100)return;
  const reply=ack=>{if(frame.isConnected)frame.contentWindow.postMessage({type:'pcm-unity-ack',requestId:data.requestId,...ack},location.origin);};
  if(S.phase!=='encounter'){reply({ok:false,error:'This encounter is closed.'});return;}
  if(data.action==='select_region'){room.region=data.region;announce('Selected '+data.region+'. Choose an examination and its components in the patient room.');}
  if(!['exam','courtesy','position','select_region'].includes(data.action)){reply({ok:false,error:'Unknown room action.'});return;}
  if(unityRequests.has(data.requestId)){reply(await unityRequests.get(data.requestId));return;}
  const sid=S.id;
  const operation=(async()=>{
    const response=await api(`/api/session/${sid}/room`,data);
    const ok=!response.error&&response.ok!==false;
    if(S?.id===sid){
      const oldPhase=S.phase;
      if(response.state)S=response.state;
      if(S.phase!==oldPhase)renderPhase(true);
      else if(S.phase==='encounter'){
        if(response.state?.transcript)paintStream(S.transcript||[]);
        else (response.events||[]).forEach(deliverEvent);
        (response.events||[]).filter(e=>e.kind==='courtesy').forEach(e=>markCourtesy(e.label));
        paintRapport();paintExamProgress();
        const started=(response.events||[]).find(e=>e.kind==='exam_started');
        if(started)setPatientState('examining',started.label||'Examination in progress');
      }
      notifyPublicState();
    }
    return {ok,error:response.message||response.error||'',events:response.events||[]};
  })();
  unityRequests.set(data.requestId,operation);
  if(unityRequests.size>300)unityRequests.delete(unityRequests.keys().next().value);
  reply(await operation);
});
/* Native HTML dialog preserves keyboard focus without browser JavaScript alerts.

   The heading and the two buttons NAME THE DECISION. One generic "Continue?"
   stood in front of four materially different choices -- leaving an attempt,
   ending the encounter, submitting the note, submitting an unstored draft --
   so the most consequential, irreversible action in the app was confirmed by a
   button that said nothing about what it would do. The confirmation itself is
   preserved; only its wording changed. */
function confirmChoice(message,options){
  const {title='Continue?',confirm='Continue',cancel='Keep working'}=options||{};
  return new Promise(resolve=>{
    const prior=document.activeElement,dialog=document.createElement('dialog');
    dialog.className='confirm-dialog';dialog.setAttribute('aria-labelledby','confirmTitle');
    dialog.innerHTML=`<form method="dialog"><h2 id="confirmTitle">${esc(title)}</h2><p>${esc(message)}</p><div class="row"><button class="btn" value="cancel" autofocus>${esc(cancel)}</button><button class="btn primary" value="confirm">${esc(confirm)}</button></div></form>`;
    document.body.appendChild(dialog);
    dialog.addEventListener('close',()=>{const accepted=dialog.returnValue==='confirm';dialog.remove();if(prior?.isConnected)prior.focus();resolve(accepted);},{once:true});
    dialog.addEventListener('click',e=>{if(e.target===dialog){const rect=dialog.getBoundingClientRect();if(e.clientX<rect.left||e.clientX>rect.right||e.clientY<rect.top||e.clientY>rect.bottom)dialog.close('cancel');}});
    dialog.showModal();
  });
}
window.pcmConfirmChoice=confirmChoice;
window.pcmActiveAttempt=()=>S?.phase!=='submitted'?S?.id:null;
window.pcmEnterWorkbench=async kind=>{
  if(S?.phase==='note'){const saved=await persistNote();if(!saved.saved){toast('Your draft could not be saved. Reconnect before leaving.');location.hash='#/'+S.id;return false;}}
  if(S?.phase==='organize'){const value=$('#scratch')?.value??S.scratch??'';keepDraft('scratch',S.id,value);const result=await saveScratch(S.id,value);if(!result.saved){toast('Your organization draft could not sync. Keep this page open and reconnect.');history.replaceState(null,'','#/'+S.id);return false;}}
  if(S)window.pcmLastAttempt=S.id;
  stopVoice();cancelRunningExam();closeOverlay(true);clearPendingReveals();
  if(poll)clearInterval(poll);if(tick)clearInterval(tick);S=null;lastPhase=null;document.body.dataset.phase=kind;positionRoomFrame();clockEl.classList.add('hidden');chipEl.classList.add('hidden');homeBtn.classList.add('hidden');window.scrollTo(0,0);return true;
};
window.pcmNavigate=destination=>{
  const target=['home','practice','learn','progress','scoring','voice'].includes(destination)?destination:'home';
  if(location.hash==='#'+target)route();else location.hash='#'+target;
};
window.pcmPortalCases=()=>BOOT?.cases||[];
window.pcmPortalMode=()=>{const mode=currentUiMode();return {mode,reveal:MODES[mode]?.reveal};};
window.pcmPortal?.setupNavigation();
window.pcmStart=begin;
window.pcmRefreshLobbyHistory=refreshLobbyHistory;

/* ======================================================================== */
/* boot                                                                      */
/* ======================================================================== */
homeBtn.onclick = () => window.pcmNavigate('home');
window.addEventListener('hashchange', route);
document.addEventListener('visibilitychange', () => { if (!document.hidden && S) refresh(); });
window.addEventListener('offline', () => {
  setNetDown(true);
  if (S && S.phase !== 'submitted') api(`/api/session/${S.id}/interruption`,
    { kind:'network', detail:'The browser went offline during the ' + S.phase + ' phase.' });
});
window.addEventListener('online', () => { if (S) refresh(); });
window.addEventListener('beforeunload', e => {
  if (S && ((S.phase === 'note' && noteSave.state !== 'saved')||(S.phase==='organize'&&scratchNeedsSave&&!scratchProtected))) { e.preventDefault(); e.returnValue = ''; }
});
/* Keyboard actions are scoped to the encounter; Space remains page scrolling.
   The focused microphone button owns its own Space/Enter hold behavior. */
view.addEventListener('keydown',e=>{
  if(!S||S.phase!=='encounter'||overlay||e.metaKey||e.ctrlKey||e.isComposing)return;
  // Alt+2 and Alt+3 type a character on macOS. Firing a navigation shortcut
  // from inside the composer or the note put the glyph in the box AND moved
  // the student somewhere else.
  const typing=/^(INPUT|TEXTAREA)$/.test(e.target?.tagName||'')||e.target?.isContentEditable;
  if(e.altKey&&!e.shiftKey&&!typing){const id={'1':'say','2':'toolExam','3':'toolChart'}[e.key];
    if(!id)return;e.preventDefault();if(id==='say')$('#say')?.focus();else $('#'+id)?.click();return;}
  if(e.key==='Escape'&&!e.altKey&&!e.shiftKey)interruptPatient();
});

(async function boot(){
  BOOT = await api('/api/bootstrap');
  if (BOOT.error) {
    view.innerHTML = '<div class="card"><h2>The local engine is not answering</h2>' +
      '<p class="small">' + esc(BOOT.message || BOOT.error || 'Close other app tabs, check browser storage, then reload.') + '</p><button class="btn" onclick="location.reload()">Try again</button></div>';
    return;
  }
  route();
})();
