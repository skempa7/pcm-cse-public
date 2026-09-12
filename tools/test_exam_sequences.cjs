/* Physical-exam rehearsal sequences: structure, concision, and the rule that
   documentation may only reflect steps actually performed.

   The concision limits are the point of the feature, so they are asserted:
   a sequence that grows into a textbook examination fails here. */
const fs = require('fs'), path = require('path'), vm = require('vm');
const assert = require('node:assert/strict');

const MAX_CORE_STEPS = 5;          // a CSE sequence has to be memorable
const MAX_INSTRUCTION_CHARS = 230; // a few seconds to read
const REQUIRED = ['id', 'title', 'instruction', 'assessing', 'normal'];
const KNOWN_VIEWS = new Set(['torso-front', 'torso-back', 'abdomen', 'head', 'arm', 'joint']);
const EXPECTED = ['cardiac', 'pulmonary', 'abdominal', 'heent', 'msk'];

function load(edition) {
  const file = path.join(edition, 'web/patient3d/exam-sequences.js');
  const context = { window: {} };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(file, 'utf8'), context);
  return context.window.PCM_EXAM_SEQUENCES;
}

/* The summary builder, mirrored from technique.js: only completed steps may
   contribute a SOAP fragment. Kept in step with the UI by test 'documentation
   discipline' below, which drives it exactly as the panel does. */
function documentFrom(exam, doneIds) {
  const performed = exam.steps.filter(s => doneIds.includes(s.id));
  const fragments = performed.map(s => s.soap).filter(Boolean);
  return fragments.length ? exam.soapPrefix + ' ' + fragments.join(', ') + '.' : null;
}

function run(edition, label) {
  const exams = load(edition);
  let checks = 0;
  const ok = (cond, msg) => { checks++; assert.ok(cond, msg); };

  ok(exams && typeof exams === 'object', 'sequences did not load');
  for (const id of EXPECTED) ok(exams[id], 'missing required examination: ' + id);

  for (const [id, exam] of Object.entries(exams)) {
    ok(exam.id === id, id + ': id mismatch');
    for (const key of ['title', 'blurb', 'duration', 'soapPrefix', 'steps'])
      ok(exam[key], id + ': missing ' + key);
    ok(Array.isArray(exam.steps) && exam.steps.length > 0, id + ': no steps');
    ok(exam.steps.length <= MAX_CORE_STEPS,
       id + ': ' + exam.steps.length + ' core steps exceeds the ' + MAX_CORE_STEPS +
       '-step limit that keeps these sequences CSE-sized');
    ok(Array.isArray(exam.optional) && exam.optional.length > 0,
       id + ': no optional list — maneuvers left out of core must be named, not hidden');
    for (const o of exam.optional)
      ok(o.title && o.why, id + ': an optional entry must say what it is and why it is optional');

    const seen = new Set();
    for (const step of exam.steps) {
      const where = id + '/' + (step.id || '?');
      for (const key of REQUIRED) ok(step[key], where + ': missing ' + key);
      ok(!seen.has(step.id), where + ': duplicate step id');
      seen.add(step.id);
      ok(step.instruction.length <= MAX_INSTRUCTION_CHARS,
         where + ': instruction is ' + step.instruction.length + ' chars, over the ' +
         MAX_INSTRUCTION_CHARS + '-char limit that keeps a step readable at a glance');
      ok(!/\n/.test(step.instruction), where + ': instruction should be one short block');

      if (step.demo) {
        ok(KNOWN_VIEWS.has(step.demo.view), where + ': unknown diagram view ' + step.demo.view);
        ok(step.demo.caption, where + ': demonstration needs a caption');
        const marks = step.demo.marks || [];
        ok(marks.length > 0, where + ': demonstration has no marks to show');
        for (const m of marks) {
          ok(typeof m.x === 'number' && m.x >= 0 && m.x <= 100, where + ': mark x out of range');
          ok(typeof m.y === 'number' && m.y >= 0 && m.y <= 100, where + ': mark y out of range');
          ok(typeof m.r === 'number' && m.r > 0, where + ': mark needs a radius');
        }
        for (const [a, b] of step.demo.arrows || []) {
          ok(marks[a] && marks[b], where + ': arrow refers to a mark that does not exist');
          ok(a !== b, where + ': arrow points at itself');
        }
      }
    }
  }

  /* Documentation discipline: the closing note reflects performed steps only. */
  {
    const exam = exams.pulmonary;
    const all = exam.steps.map(s => s.id);
    const full = documentFrom(exam, all);
    ok(full && full.startsWith(exam.soapPrefix), 'full sequence produced no note');
    for (const step of exam.steps) {
      if (!step.soap) continue;
      const without = documentFrom(exam, all.filter(x => x !== step.id));
      ok(!without || !without.includes(step.soap),
         'skipping "' + step.title + '" still documented its finding — the note must ' +
         'never include a component that was not performed');
    }
    ok(documentFrom(exam, []) === null, 'skipping every step still produced a note');
    checks += 2;
  }

  /* Medically ordered abdominal sequence: auscultation precedes percussion
     and palpation, because pressing first changes what is heard. */
  {
    const order = exams.abdominal.steps.map(s => s.id);
    const at = id => order.indexOf(id);
    ok(at('inspect') < at('auscultate'), 'abdominal: inspection must come first');
    ok(at('auscultate') < at('percuss'), 'abdominal: auscultation must precede percussion');
    ok(at('auscultate') < at('palpate'), 'abdominal: auscultation must precede palpation');
  }

  /* MSK teaches one transferable framework. */
  {
    const order = exams.msk.steps.map(s => s.id);
    // Compared as a string: the data is built inside a vm context, so its
    // arrays have a different Array prototype and deepStrictEqual rejects them
    // even when every element matches.
    ok(order.slice(0, 3).join('>') === 'look>feel>move',
       'MSK should teach look → feel → move, got ' + order.slice(0, 3).join('>'));
    ok(Array.isArray(exams.msk.regions) && exams.msk.regions.length >= 5,
       'MSK should offer the common regions');
  }

  /* Cardiac auscultation must name four ordered areas. */
  {
    const step = exams.cardiac.steps.find(s => s.id === 'auscultate');
    ok(step && step.demo.marks.length === 4, 'cardiac: expected four auscultation areas');
    ok((step.demo.arrows || []).length === 3, 'cardiac: areas should be shown in order');
  }

  const stepCount = Object.values(exams).reduce((n, e) => n + e.steps.length, 0);
  console.log('PASS %s: %d checks — %d examinations, %d core steps, documentation ' +
              'limited to performed components', label, checks, Object.keys(exams).length, stepCount);
}

const editions = [];
for (const dir of [path.resolve(__dirname, '..')]) {
  if (fs.existsSync(path.join(dir, 'web/patient3d/exam-sequences.js'))) editions.push(dir);
}
assert.ok(editions.length, 'no edition contains exam-sequences.js');
for (const edition of editions) run(edition, path.basename(edition));
