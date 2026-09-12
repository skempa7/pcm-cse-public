/* The consolidated encounter toolbar: position buttons and the voice toggle.

   Driven through the real mount() extracted from web/encounter-workspace.js
   against a stub DOM, so it cannot drift from the shipped code and does not
   depend on requestAnimationFrame or a visible tab.

   The property that matters clinically is that the position control can never
   disagree with the patient: it is painted ONLY from the engine's recorded
   posture, including when the engine REFUSES a change. */
const fs = require('fs'), path = require('path'), vm = require('vm');
const assert = require('node:assert/strict');

const POSITIONS = [
  ['seated', 'Seated on the table'],
  ['supine', 'Supine · face up'],
  ['standing', 'Standing beside the table'],
  ['prone', 'Prone · face down'],
];

/* A DOM stub with just enough behavior for the toolbar: element creation,
   class/attribute state, id lookup and a working querySelector over ids,
   classes and [data-pos] / [aria-pressed] selectors. */
function makeDom() {
  const all = [];
  function el(tag = 'div') {
    const node = {
      tagName: tag.toUpperCase(), id: '', className: '', children: [], parent: null,
      dataset: {}, attrs: {}, disabled: false, hidden: false, textContent: '',
      type: '', onclick: null, onchange: null, tabIndex: 0,
      setAttribute(k, v) { this.attrs[k] = String(v); if (k.startsWith('data-')) this.dataset[k.slice(5)] = String(v); },
      getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
      removeAttribute(k) { delete this.attrs[k]; },
      append(...kids) { for (const k of kids) { if (!k) continue; k.parent = this; this.children.push(k); } },
      appendChild(k) { this.append(k); return k; },
      before() {}, replaceWith() {}, remove() {},
      focus() {}, click() { this.onclick && this.onclick({ target: this, currentTarget: this }); },
      classList: {
        _s: new Set(),
        add(...c) { c.forEach(x => this._s.add(x)); },
        remove(...c) { c.forEach(x => this._s.delete(x)); },
        toggle(c, on) { on === undefined ? (this._s.has(c) ? this._s.delete(c) : this._s.add(c)) : (on ? this._s.add(c) : this._s.delete(c)); },
        contains(c) { return this._s.has(c); },
      },
      get innerHTML() { return this._html || ''; },
      set innerHTML(v) {
        this._html = v; this.children = [];
        // Materialise <button ... data-pos="x"> so the toolbar's own query for
        // .ew-pos finds real nodes.
        for (const m of String(v).matchAll(/<button[^>]*class="([^"]*)"[^>]*data-pos="([^"]*)"[^>]*>/g)) {
          const b = el('button'); b.className = m[1]; b.dataset.pos = m[2];
          b.setAttribute('aria-pressed', 'false'); this.append(b); all.push(b);
        }
      },
    };
    node.classList._s = new Set();
    all.push(node);
    return node;
  }
  function matches(node, sel) {
    if (sel.startsWith('#')) return node.id === sel.slice(1);
    if (sel.startsWith('.')) {
      const [cls, rest] = [sel.slice(1).split('[')[0], sel.includes('[') ? sel.slice(sel.indexOf('[')) : ''];
      const hasCls = node.className.split(/\s+/).includes(cls) || node.classList.contains(cls);
      if (!hasCls) return false;
      if (!rest) return true;
      const m = rest.match(/\[([\w-]+)="([^"]*)"\]/);
      return m ? node.getAttribute(m[1]) === m[2] : true;
    }
    return false;
  }
  function descendants(root) {
    const out = [];
    (function walk(n) { for (const c of n.children) { out.push(c); walk(c); } })(root);
    return out;
  }
  return { el, matches, descendants, all };
}

function harness(edition) {
  const src = fs.readFileSync(path.join(edition, 'web/encounter-workspace.js'), 'utf8');
  const start = src.indexOf('const POSITION_GLYPH');
  const end = src.indexOf('function makeExam(');
  assert.ok(start > 0 && end > start, 'position helpers not found in ' + edition);
  const helpers = src.slice(start, end);

  // The position-control block from mount(), taken verbatim.
  const blockStart = src.indexOf(" const position=document.createElement('div');position.className='ew-position'");
  assert.ok(blockStart > 0, 'position block not found in ' + edition);
  const blockEnd = src.indexOf(" const view=button(", blockStart);
  assert.ok(blockEnd > blockStart, 'end of position block not found');
  const block = src.slice(blockStart, blockEnd);

  const dom = makeDom();
  const requested = [];
  const tools = dom.el('div');
  const ctx = {
    console, POSITIONS, Set, Array, String, Boolean, JSON, active:{},
    document: { createElement: t => dom.el(t) },
    E: s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    q: (sel, root) => (root ? dom.descendants(root) : dom.all).find(n => dom.matches(n, sel)) || null,
    qa: (sel, root) => (root ? dom.descendants(root) : dom.all).filter(n => dom.matches(n, sel)),
    tools,
    requestPosition: (pos, control) => { requested.push({ pos, control }); },
  };
  vm.createContext(ctx);
  vm.runInContext(helpers + '\n' + block, ctx);
  const group = tools.children[0];
  return { ctx, dom, group, requested, buttons: dom.descendants(group).filter(n => n.dataset.pos) };
}

function run(edition, label) {
  let n = 0;
  const ok = (c, m) => { n++; assert.ok(c, m); };
  const { ctx, group, requested, buttons } = harness(edition);

  // 1. Every supported position is directly clickable - no dropdown.
  ok(group.getAttribute('role') === 'group', 'position control is not a labelled group');
  ok(group.getAttribute('aria-label') === 'Patient position', 'group has no accessible name');
  assert.equal(buttons.map(b => b.dataset.pos).join(','), POSITIONS.map(p => p[0]).join(','));
  n++;
  ok(buttons.length === POSITIONS.length, 'not every position has a button');
  for (const b of buttons) {
    ok(b.tagName === 'BUTTON', 'a position is not a real button: ' + b.dataset.pos);
    ok(b.getAttribute('aria-pressed') !== null,
       'position button has no aria-pressed, so state relies on colour: ' + b.dataset.pos);
  }

  // 2. Selection is painted only from the engine's recorded posture.
  ctx.paintPosition('supine');
  ok(buttons.find(b => b.dataset.pos === 'supine').getAttribute('aria-pressed') === 'true',
     'painting supine did not select it');
  ok(buttons.filter(b => b.getAttribute('aria-pressed') === 'true').length === 1,
     'more than one position is selected at once');

  // 3. Clicking a different position goes through requestPosition, once.
  const standing = buttons.find(b => b.dataset.pos === 'standing');
  standing.click();
  ok(requested.length === 1 && requested[0].pos === 'standing',
     'clicking a position did not request it: ' + JSON.stringify(requested.map(r => r.pos)));

  // 4. Clicking the CURRENT position does nothing - no redundant round trip.
  ctx.paintPosition('standing');
  const before = requested.length;
  standing.click();
  ok(requested.length === before, 'clicking the already-selected position re-requested it');

  // 5. THE INVARIANT: on refusal, the engine's posture wins.
  //    requestPosition sets control.value = the RECORDED posture, which may
  //    differ from what was clicked.
  const control = requested[0].control;
  control.disabled = true;
  ok(buttons.every(b => b.disabled), 'the group is not disabled during a request');
  control.value = 'seated';                 // engine refused; patient stayed seated
  control.disabled = false;
  ok(buttons.find(b => b.dataset.pos === 'seated').getAttribute('aria-pressed') === 'true',
     'a refused position change left the button group showing the wrong posture');
  ok(buttons.find(b => b.dataset.pos === 'standing').getAttribute('aria-pressed') === 'false',
     'the refused position is still shown as selected');
  ok(control.value === 'seated', 'control.value does not report the painted posture');
  ok(buttons.every(b => !b.disabled), 'the group stayed disabled after the request');

  console.log('PASS %s: %d checks — every position one click, single selection, '
              + 'engine posture always wins', label, n);
}

/* The voice control is a toggle, not a menu, and says its state in words. */
function voiceToggle(edition, label) {
  const src = fs.readFileSync(path.join(edition, 'web/encounter-workspace.js'), 'utf8');
  let n = 0;
  const ok = (c, m) => { n++; assert.ok(c, m); };
  ok(!/audioSettings/.test(src), 'the voice settings modal still exists');
  ok(!/ewDeviceVoice|ewPreviewVoice|ewStopPreview|ewRefreshVoices/.test(src),
     'a voice picker/preview/refresh control survives in the toolbar');
  const paint = src.slice(src.indexOf('function paintVoiceToggle()'), src.indexOf('function toggleVoice()'));
  ok(/aria-pressed/.test(paint), 'the toggle does not expose aria-pressed');
  ok(/Voice on/.test(paint) && /Voice off/.test(paint),
     'the toggle does not state on/off in text, so it relies on colour alone');
  ok(/unavailable/.test(paint), 'the toggle has no unavailable state');
  const toggle = src.slice(src.indexOf('function toggleVoice()'), src.indexOf('function toggleVoice()') + 320);
  ok(/pcmSpeechOptions/.test(toggle), 'the toggle does not go through the shared speech preference');
  ok(!/hands_free|rec\./.test(toggle), 'the voice toggle touches the microphone');
  ok(!/sheet\(/.test(toggle), 'the toggle still opens a panel');
  console.log('PASS %s: %d checks — direct toggle, stateful label, microphone untouched', label, n);
}


/* Bedside: grouping, and the action-vs-suggestion distinction. Verified from
   source because the handlers are bound inside sheet(); the properties that
   matter are structural. */
function bedside(edition, label) {
  const src = fs.readFileSync(path.join(edition, 'web/encounter-workspace.js'), 'utf8');
  let n = 0;
  const ok = (c, m) => { n++; assert.ok(c, m); };
  const groups = src.slice(src.indexOf('function bedsideGroups()'), src.indexOf('function bedsideStatus('));
  const open = src.slice(src.indexOf('function openBedside()'), src.indexOf('function makeExam('));

  ok(/Preparation & comfort/.test(groups), 'no preparation/comfort group');
  ok(/Interview moves/.test(groups), 'no interview moves group');
  ok(/Wrapping up/.test(groups), 'no wrapping-up group');
  ok(/BEDSIDE/.test(groups), 'the real bedside actions are not used');
  ok(/INTERVIEW_PROMPTS/.test(groups), 'the real interview prompts are not used');

  // Assisted-only teaching content stays assisted-only.
  ok(/guided.*coached|coached.*guided/.test(groups),
     'interview moves are not gated to assisted modes');

  // An ACTION sends through the ordinary pipeline; a SUGGESTION does not send.
  ok(/dataset\.kind==='action'/.test(open), 'actions and suggestions are not distinguished');
  const actionBranch = open.slice(open.indexOf("dataset.kind==='action'"), open.indexOf('}else{'));
  const suggestBranch = open.slice(open.indexOf('}else{'));
  ok(/sendSay\(text\)/.test(actionBranch), 'an action does not go through sendSay');
  ok(!/sendSay/.test(suggestBranch), 'a SUGGESTION sends itself instead of reaching the composer');
  ok(/q\('#say'\)/.test(suggestBranch), 'a suggestion does not reach the composer');
  ok(/box\.value=text/.test(suggestBranch), 'the suggestion is not placed for review');

  // Opening the menu must not send or record anything.
  const opener = src.slice(src.indexOf("bedside.onclick=openBedside"), src.indexOf("bedside.onclick=openBedside") + 60);
  ok(/openBedside/.test(opener), 'the Bedside button does not open the menu');
  const beforeHandlers = open.slice(0, open.indexOf('qa(\'.ew-bs\''));
  ok(!/sendSay|api\(/.test(beforeHandlers), 'opening the Bedside menu performs an action');

  // A used action stays usable - repeating is sometimes correct.
  ok(!/disabled=true/.test(open) && !/\.disabled\s*=/.test(open),
     'a used bedside action is permanently disabled');
  ok(/classList\.add\('used'\)/.test(open), 'a completed action shows no state');
  console.log('PASS %s: %d checks — grouped, actions send, suggestions only reach the '
              + 'composer, opening records nothing', label, n);
}

const editions = [];
for (const dir of [path.resolve(__dirname, '..')]) {
  if (fs.existsSync(path.join(dir, 'web/encounter-workspace.js'))) editions.push(dir);
}
for (const e of editions) { run(e, path.basename(e)); voiceToggle(e, path.basename(e) + ' voice'); bedside(e, path.basename(e) + ' bedside'); }
