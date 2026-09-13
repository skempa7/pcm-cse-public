/* Physical-exam rehearsal: an instructional step-through, not a quiz.
 *
 * WHAT CHANGED AND WHY
 * The previous version asked a multiple-choice question after each step. That
 * tests recall of trivia about a sequence rather than teaching the sequence,
 * and it made the feature slow to use for its actual purpose: reminding a
 * student what to physically do shortly before a CSE. Every step now answers
 * three questions -- what do I do, what am I checking, what can I write -- and
 * the student clicks forward through them.
 *
 * DOCUMENTATION DISCIPLINE
 * The closing screen assembles a SOAP line from the steps the student actually
 * completed. A step that was skipped contributes nothing. This is deliberate:
 * a rehearsal tool should distinguish examples from findings obtained in the
 * encounter. Reading a step never establishes a normal finding.
 *
 * ENCOUNTER SAFETY
 * This overlay reads nothing from the case and writes nothing back. It does not
 * call an examination, change posture, or create evidence, and it no longer
 * disables the encounter controls or moves the patient, so opening it mid
 * encounter costs nothing.
 */
(() => {
  const EXAMS = window.PCM_EXAM_SEQUENCES || {};
  let examId = null, step = 0, done = [], mode = 'learn', priorFocus = null;
  let guideSession = null, showingMenu = true, completeReported = false, savedScroll = 0;
  function savePlace() {
    if (!guideSession) return;
    try { localStorage.setItem('pcm-exam-guide:' + guideSession,
      JSON.stringify({examId, step, done, mode, showingMenu, completeReported, scroll: savedScroll})); }
    catch (_) { /* In-memory navigation remains usable when storage is unavailable. */ }
  }
  function receiveSession() {
    if (guideSession === state.sessionId) return;
    guideSession = state.sessionId; examId = null; step = 0; done = [];
    mode = 'learn'; showingMenu = true; completeReported = false; savedScroll = 0;
    panel.hidden = true; document.body.classList.remove('technique-open');
    if (!guideSession) return;
    try {
      const saved = JSON.parse(localStorage.getItem('pcm-exam-guide:' + guideSession) || 'null');
      const exam = saved && EXAMS[saved.examId];
      if (!exam) return;
      examId = saved.examId; step = Math.max(0, Math.min(exam.steps.length, Number(saved.step) || 0));
      done = (Array.isArray(saved.done) ? saved.done : []).filter(id => exam.steps.some(item => item.id === id));
      mode = saved.mode === 'quick' ? 'quick' : 'learn'; showingMenu = !!saved.showingMenu;
      completeReported = !!saved.completeReported; savedScroll = Math.max(0, Number(saved.scroll) || 0);
    } catch (_) { /* An invalid saved place falls back to the sequence chooser. */ }
  }
  function showPanel() {
    panel.hidden = false; document.body.classList.add('technique-open');
    try { send({type:'pcm-technique-visibility', sessionId:state.sessionId, open:true}); } catch (_) {}
  }

  const launch = document.createElement('button');
  launch.id = 'techniqueLaunch';
  launch.type = 'button';
  launch.textContent = 'Exam guide';
  launch.title = 'Rehearse a basic physical examination sequence';
  launch.hidden = true;
  document.querySelector('#room').append(launch);

  const panel = document.createElement('section');
  panel.id = 'techniquePanel';
  panel.hidden = true;
  panel.setAttribute('aria-label', 'Physical examination rehearsal');
  document.querySelector('#room').append(panel);

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  window.pcmTechniqueNotice = message => {
    const el = panel.querySelector('.tech-note');
    if (el) el.textContent = message;
  };

  function report(event, extra = {}) {
    try {
      send({ type: 'pcm-unity-teaching', sessionId: state.sessionId, lessonId: examId, step, event, ...extra });
    } catch (e) { /* telemetry is never load-bearing */ }
  }

  function close() {
    savedScroll = panel.scrollTop; savePlace(); panel.hidden = true;
    document.body.classList.remove('technique-open');
    try { send({type:'pcm-technique-visibility', sessionId:state.sessionId, open:false}); } catch (_) {}
    apply();
    priorFocus?.focus();
  }

  /* ---------- demonstration diagrams ---------------------------------- */
  /* Simple, legible schematics. Clarity is the goal, not anatomical
     realism: numbered placements, left/right pairing and direction of travel
     are what a student needs in order to remember a sequence. */
  const BODY = {
    'torso-front': '<path d="M32 14 q18 -8 36 0 l6 16 -10 5 2 52 q-16 6 -32 0 l2 -52 -10 -5z" class="tb"/>' +
                   '<line x1="50" y1="24" x2="50" y2="85" class="tm"/>',
    'torso-back': '<path d="M32 14 q18 -8 36 0 l6 16 -10 5 2 52 q-16 6 -32 0 l2 -52 -10 -5z" class="tb"/>' +
                  '<line x1="50" y1="20" x2="50" y2="85" class="tm"/>',
    abdomen: '<rect x="24" y="22" width="52" height="56" rx="16" class="tb"/>',
    head: '<ellipse cx="50" cy="42" rx="24" ry="29" class="tb"/><path d="M38 72 h24 l4 14 h-32z" class="tb"/>',
    arm: '<path d="M18 30 q30 6 62 34" class="tb tl"/><circle cx="82" cy="68" r="7" class="tb"/>',
    joint: '<path d="M20 28 v18 q0 10 12 10 h36 q12 0 12 -10 v-18" class="tb tl"/>' +
           '<path d="M20 68 v-4" class="tb tl"/><path d="M80 68 v-4" class="tb tl"/>',
  };

  function diagram(demo) {
    if (!demo) return '';
    const marks = demo.marks || [];
    const shapes = marks.map(m => {
      const cls = 'mk mk-' + (m.kind || 'zone');
      const title = m.title ? '<title>' + esc(m.title) + '</title>' : '';
      // Long words do not fit small hand markers. Keep those labels above
      // the hotspot in dark text; white overflow vanished into the background.
      const outside = String(m.label || '').length > 3 && m.r < 14;
      const label = m.label ? '<text x="' + m.x + '" y="' + (outside ? m.y-m.r-4 : m.y+2.6) + '" class="mkl' + (outside?' mkl-outside':'') + '">' + esc(m.label) + '</text>' : '';
      return '<g>' + title + '<circle cx="' + m.x + '" cy="' + m.y + '" r="' + m.r + '" class="' + cls + '"/>' + label + '</g>';
    }).join('');
    const arrows = (demo.arrows || []).map(([a, b, style]) => {
      const from = marks[a], to = marks[b];
      if (!from || !to) return '';
      const cls = style === 'compare' ? 'ar ar-compare' : style === 'apart' ? 'ar ar-apart' : 'ar';
      return '<line x1="' + from.x + '" y1="' + from.y + '" x2="' + to.x + '" y2="' + to.y +
             '" class="' + cls + '" marker-end="url(#tri)"' +
             (style === 'compare' ? ' marker-start="url(#tri)"' : '') + '/>';
    }).join('');
    const quads = demo.quadrants
      ? '<line x1="50" y1="22" x2="50" y2="78" class="tq"/><line x1="24" y1="50" x2="76" y2="50" class="tq"/>' : '';
    const path = demo.path === 'H'
      ? '<path d="M36 46 v10 M36 51 h28 M64 46 v10" class="tp"/>'
      : demo.path === 'arc' ? '<path d="M30 60 q20 -26 40 0" class="tp"/>' : '';
    // Cropped viewBox: the schematics occupy the middle of the 0-100 space, so
    // a full-square view letterboxes them into a small figure inside a wide
    // panel. Mark coordinates stay in the same 0-100 space.
    // The wrist lies at x=82; the torso crop cut off its radial label and hand.
    const viewBox=demo.view==='arm'?'0 2 104 96':'14 2 72 96';
    return '<figure class="tech-demo"><svg viewBox="' + viewBox + '" role="img" aria-label="' +
      esc(demo.caption || 'Examination diagram') + '">' +
      '<defs><marker id="tri" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="5" markerHeight="5" orient="auto">' +
      '<path d="M0 0 L8 4 L0 8z" class="arh"/></marker></defs>' +
      (BODY[demo.view] || '') + quads + path + arrows + shapes + '</svg>' +
      '<figcaption>' + esc(demo.caption || '') + '</figcaption></figure>';
  }

  /* ---------- screens -------------------------------------------------- */
  function head(label) {
    return '<button class="tech-close" type="button" aria-label="Close the examination guide">×</button>' +
           '<small>' + esc(label) + '</small>';
  }

  function menu() {
    if(panel.hidden)priorFocus = document.activeElement;
    showingMenu = true; savedScroll = 0; savePlace();
    showPanel(); panel.className = 'tech-menu';
    panel.innerHTML = head('PHYSICAL EXAM REHEARSAL') +
      '<h2>Choose an examination</h2>' +
      '<p class="tech-sub">Short, CSE-sized sequences. What to do, what to check, what to write.</p>' +
      (EXAMS[examId] ? '<button type="button" class="exam-choice tech-resume" id="techResume"><span class="ex-title">Resume ' + esc(EXAMS[examId].title) + '</span><span class="ex-time">' + (mode==='quick'?'Quick reference':step>=EXAMS[examId].steps.length?'Rehearsal summary':'Step '+(step+1)+' of '+EXAMS[examId].steps.length) + '</span></button>' : '') +
      Object.values(EXAMS).map(e =>
        '<button class="exam-choice" type="button" data-exam="' + e.id + '">' +
        '<span class="ex-title">' + esc(e.title) + '</span>' +
        '<span class="ex-blurb">' + esc(e.blurb) + '</span>' +
        '<span class="ex-time">' + esc(e.duration) + ' · ' + e.steps.length + ' steps</span>' +
        '</button>').join('') +
      '<p class="tech-limit">Rehearsal only — no findings or examination credit are recorded. Opening a sequence records this attempt as assisted practice.</p>';
    wire();
    panel.querySelectorAll('[data-exam]').forEach(b => {
      b.onclick = () => {
        // Reading the taught sequence is instructional assistance and is
        // recorded as such. Say so BEFORE showing any of it, and leave the
        // encounter exactly as it was if the student would rather not.
        if (!state.assisted && !window.confirm(
            'This guide teaches the examination sequence step by step.\n\n'
            + 'Opening it records this attempt as assisted practice. Your findings, '
            + 'notes and timing are not affected, and no examination credit is given '
            + 'for reading it.\n\nOpen the guide?')) return;
        examId = b.dataset.exam; step = 0; done = []; mode = 'learn'; completeReported = false;
        report('start'); render();
      };
    });
    panel.querySelector('#techResume')?.addEventListener('click',()=>render());
    panel.scrollTop=0;focusHeading();
  }

  function render() {
    const exam = EXAMS[examId];
    if (!exam) return menu();
    showingMenu=false; savedScroll=0; savePlace();
    if (mode === 'quick') return quick();
    if (step >= exam.steps.length) return summary();
    const item = exam.steps[step];
    const total = exam.steps.length;
    showPanel();panel.className = 'tech-step';
    panel.innerHTML = head(exam.title.toUpperCase() + ' · STEP ' + (step + 1) + ' OF ' + total) +
      '<div class="tech-bar" role="progressbar" aria-valuemin="1" aria-valuemax="' + total +
      '" aria-valuenow="' + (step + 1) + '">' +
      exam.steps.map((s, i) => '<span class="' + (i < step ? 'done' : i === step ? 'now' : '') + '"></span>').join('') +
      '</div>' +
      '<h2>' + esc(item.title) + '</h2>' +
      diagram(item.demo) +
      '<p class="tech-do">' + esc(item.instruction) + '</p>' +
      '<dl class="tech-facts">' +
      '<dt>Checking for</dt><dd>' + esc(item.assessing) + '</dd>' +
      '<dt>Normal example</dt><dd>' + esc(item.normal) + '</dd>' +
      '</dl>' +
      (item.soap ? '<p class="tech-soap"><span>SOAP</span>' + esc(item.soap) + '</p>' : '') +
      '<p class="tech-note" role="status"></p>' +
      '<div class="tech-nav">' +
      '<button type="button" id="techBack"' + (step === 0 ? ' disabled' : '') + '>← Back</button>' +
      // Skipping is a real option, and the closing note reflects it. Without
      // this the sequence could only ever be completed in full, and the
      // documentation discipline would never actually be exercised.
      '<button type="button" id="techSkip" class="ghost" title="Advance without including this step in the rehearsal example">Skip</button>' +
      '<button type="button" id="techNext" class="primary">' +
      (step === total - 1 ? 'Review summary' : 'Next →') + '</button>' +
      '</div>' +
      (step === 0 && exam.position ? '<p class="tech-pos">' + esc(exam.position) + '</p>' : '') +
      '<button type="button" class="tech-link" id="techMenu">← All examinations</button>';
    wire();
    panel.querySelector('#techMenu').onclick=menu;
    panel.querySelector('#techBack').onclick = () => { if (step > 0) { step--; render(); } };
    panel.querySelector('#techNext').onclick = () => {
      if (!done.includes(item.id)) done.push(item.id);
      step++; report('step'); render();
    };
    panel.querySelector('#techSkip').onclick = () => {
      done = done.filter(id => id !== item.id);
      step++; report('skip'); render();
    };
    panel.scrollTop=0;focusHeading();
  }

  function summary() {
    const exam = EXAMS[examId];
    // Only the steps actually completed may contribute to the note.
    const performed = exam.steps.filter(s => done.includes(s.id));
    const fragments = performed.map(s => s.soap).filter(Boolean);
    const line = fragments.length
      ? exam.soapPrefix + ' ' + fragments.join(', ').replace(/\s+/g, ' ') + '.'
      : null;
    const skipped = exam.steps.filter(s => !done.includes(s.id));
    showPanel();panel.className = 'tech-done';
    panel.innerHTML = head(exam.title.toUpperCase() + ' · COMPLETE') +
      '<h2>Rehearsal complete</h2>' +
      '<p class="tech-warn">These are practice examples, not this patient’s findings. Perform actions in Physical Exam and use the findings saved in Notes.</p>' +
      '<ul class="tech-checks">' +
      performed.map(s => '<li class="yes">' + esc(s.title) + '</li>').join('') +
      skipped.map(s => '<li class="no">' + esc(s.title) + ' — not rehearsed</li>').join('') +
      '</ul>' +
      (line ? '<p class="tech-soap-label">Example wording if these findings were obtained:</p><pre class="tech-note-out">' + esc(line) + '</pre>'
            : '<p class="tech-sub">You skipped every step, so no example note is shown.</p>') +
      (skipped.length
        ? '<p class="tech-warn">Only the steps you rehearsed contribute to this example. Reading the guide does not perform an examination.</p>'
        : '') +
      (exam.optional && exam.optional.length
        ? '<h3>Optional, if relevant</h3><ul class="tech-opt">' +
          exam.optional.map(o => '<li><b>' + esc(o.title) + '</b> — ' + esc(o.why) + '</li>').join('') + '</ul>'
        : '') +
      '<div class="tech-nav">' +
      '<button type="button" id="techAgain">Rehearse again</button>' +
      '<button type="button" id="techQuick" class="primary">Quick reference</button>' +
      '</div>' +
      '<button type="button" class="tech-link" id="techMenu">← All examinations</button>';
    wire();
    panel.querySelector('#techAgain').onclick = () => { step = 0; done = []; mode = 'learn'; completeReported = false;render(); };
    panel.querySelector('#techQuick').onclick = () => { mode = 'quick'; render(); };
    panel.querySelector('#techMenu').onclick = menu;
    if(!completeReported){report('complete', { performed: performed.length, skipped: skipped.length });completeReported=true;savePlace();}
    panel.scrollTop=0;focusHeading();
  }

  function quick() {
    const exam = EXAMS[examId];
    const line = exam.soapPrefix + ' ' + exam.steps.map(s => s.soap).filter(Boolean).join(', ') + '.';
    showPanel();panel.className = 'tech-quick';
    panel.innerHTML = head(exam.title.toUpperCase() + ' · QUICK SEQUENCE') +
      '<h2>' + esc(exam.title) + '</h2>' +
      '<p class="tech-sub">' + esc(exam.duration) + '</p>' +
      '<ol class="tech-seq">' + exam.steps.map(s =>
        '<li><b>' + esc(s.title) + '</b><span>' + esc(s.instruction.split('.')[0]) + '</span></li>').join('') +
      '</ol>' +
      '<p class="tech-soap-label">If entirely normal:</p>' +
      '<pre class="tech-note-out">' + esc(line) + '</pre>' +
      '<p class="tech-warn">Example only. Document the findings you actually obtained through Physical Exam and saved in Notes.</p>' +
      '<div class="tech-nav">' +
      '<button type="button" id="techLearn">Step-by-step</button>' +
      '<button type="button" id="techMenu2" class="primary">← All examinations</button>' +
      '</div>';
    wire();
    panel.querySelector('#techLearn').onclick = () => { mode = 'learn'; step = 0; done = []; completeReported=false;render(); };
    panel.querySelector('#techMenu2').onclick = menu;
    focusHeading();
  }

  function wire() {
    const close_ = panel.querySelector('.tech-close');
    if (close_) close_.onclick = close;
  }
  function focusHeading() {
    const h = panel.querySelector('h2');
    if (h) { h.tabIndex = -1; h.focus({ preventScroll: true }); }
  }

  panel.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); close(); } });
  launch.onclick = () => {
    receiveSession();
    if(!panel.hidden)return close();
    priorFocus=document.activeElement;
    if(examId&&!showingMenu){const top=savedScroll;render();panel.scrollTop=top;}
    else menu();
  };

  /* The guide is available whenever the student is with the patient IN A MODE
     THAT TEACHES. It reads nothing from the case and changes nothing, so there
     is no reason to take the encounter away -- but the server only records a
     lesson in guided and coached practice (learning.allowed), so outside those
     it used to open anyway: it taught the whole sequence, and a documentation
     line with it, during Independent practice and Exam rehearsal, told the
     student "opening it records this attempt as assisted practice" when the
     server had in fact refused, and returned an error on every Next and Skip.
     The gate now matches the one the server enforces. */
  window.pcmTechniqueState = () => {
    receiveSession();
    const allowed = state.phase === 'encounter'
      && ['guided', 'coached'].includes(state.mode);
    launch.hidden = !allowed;
    if (!allowed && !panel.hidden) close();
  };
})();
