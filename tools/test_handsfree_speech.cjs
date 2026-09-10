/* Hands-free speech: one spoken utterance must produce exactly one message.

   The real defect this reproduces: with continuous recognition the results
   array is cumulative and the patient's own text-to-speech is audible to the
   microphone. Suppressing with stop() FINALIZED the buffered audio and
   delivered it after the mute window lapsed, so the patient's greeting came
   back as the student's next turn.

   The recognition handlers are extracted from web/app.js so this test cannot
   drift away from the shipped code. */
const fs = require('fs'), path = require('path'), vm = require('vm');
const assert = require('node:assert/strict');

function harness(edition) {
  const source = fs.readFileSync(path.join(edition, 'web/app.js'), 'utf8');
  const start = source.indexOf('  if (!voice.rec) {');
  const end = source.indexOf('    voice.rec = rec;', start);
  assert.ok(start > 0 && end > start, 'recognition block not found in ' + edition);
  const block = source.slice(start, end)
    .replace(/^\s*if \(!voice\.rec\) \{/, '')
    .replace(/const rec = new SR\(\);/, 'rec = new SR();');

  const helpersStart = source.indexOf('function suppressListeningForPatient(){');
  const helpersEnd = source.indexOf('function startListening(){');
  assert.ok(helpersStart > 0 && helpersEnd > helpersStart, 'suppression helpers not found');
  const helpers = source.slice(helpersStart, helpersEnd);

  const sent = [];
  const context = {
    console, Date, Math, Error, Promise, setTimeout, String, Number,
    S: { id: 's1', phase: 'encounter' },
    voice: {
      rec: null, listening: true, hands_free: true, speak: true, supported: true,
      muteUntil: 0, failed: false, pending: null, lastFinal: -1, suppressed: false,
      lastSentText: '', lastSentAt: 0, patientSpeaking: false,
    },
    window: { speechSynthesis: { speaking: false, cancel() {} }, pcmNaturalBusy: false },
    $: () => ({ textContent: '', value: '', setAttribute() {}, focus() {}, select() {} }),
    setPatientState() {}, voiceBar() {}, notifyPublicState() {}, alertNow() {},
    toast() {}, esc: s => String(s), api: async () => ({}),
    stageUncertain: (text, conf) => sent.push({ text, conf, staged: true }),
    // The send path's own duplicate guard is part of what is under test.
    sendSay: (text, conf) => {
      const now = Date.now();
      if (text === context.voice.lastSentText && now - context.voice.lastSentAt < 1200) return;
      context.voice.lastSentText = text; context.voice.lastSentAt = now;
      sent.push({ text, conf });
    },
  };
  context.window.window = context.window;
  vm.createContext(context);

  // A stand-in recognizer with the behavior the real API has: a cumulative
  // results array, start/stop/abort, and onend firing after stop or abort.
  const recognizer = {
    continuous: false, interimResults: false, lang: '', running: false,
    results: [], starts: 0, aborts: 0, stops: 0,
    start() { if (this.running) throw new Error('already started'); this.running = true; this.starts++; this.results = []; this.onstart && this.onstart(); },
    stop() { this.stops++; if (!this.running) return; this.running = false; this.onend && this.onend(); },
    abort() { this.aborts++; this.results = []; if (!this.running) return; this.running = false; this.onend && this.onend(); },
  };
  context.SR = function () { return recognizer; };
  vm.runInContext('var rec;' + block + '\nvoice.rec = rec;\n' + helpers, context);

  // Deliver a recognition event the way the browser does: append to the
  // cumulative results array, then report the index of the first change.
  function emit(chunks) {
    const resultIndex = recognizer.results.length;
    for (const chunk of chunks) {
      recognizer.results.push(Object.assign([{ transcript: chunk.text, confidence: chunk.conf ?? 0.9 }],
        { isFinal: chunk.final !== false }));
    }
    recognizer.onresult({ resultIndex, results: recognizer.results });
  }
  // Some engines re-fire with resultIndex 0 over the whole array.
  function reemitAll() {
    recognizer.onresult({ resultIndex: 0, results: recognizer.results });
  }
  return { context, recognizer, sent, emit, reemitAll, helpers };
}

function run(edition, label) {
  const checks = [];
  const ok = (name, fn) => { fn(); checks.push(name); };

  // 1. One utterance -> one message.
  {
    const h = harness(edition);
    h.recognizer.start();
    h.emit([{ text: 'hello' }]);
    ok('one utterance sends once', () => assert.equal(h.sent.length, 1));
    ok('correct text', () => assert.equal(h.sent[0].text, 'hello'));
  }

  // 2. A re-fired event over the cumulative array must not resend.
  {
    const h = harness(edition);
    h.recognizer.start();
    h.emit([{ text: 'hello' }]);
    h.reemitAll(); h.reemitAll(); h.reemitAll();
    ok('cumulative re-delivery does not resend', () => assert.equal(h.sent.length, 1));
  }

  // 3. Interim results never send; only the final does.
  {
    const h = harness(edition);
    h.recognizer.start();
    h.recognizer.results.push(Object.assign([{ transcript: 'hel', confidence: 0.9 }], { isFinal: false }));
    h.recognizer.onresult({ resultIndex: 0, results: h.recognizer.results });
    ok('interim does not send', () => assert.equal(h.sent.length, 0));
    h.recognizer.results[0].isFinal = true;
    h.recognizer.results[0][0].transcript = 'hello';
    h.recognizer.onresult({ resultIndex: 0, results: h.recognizer.results });
    ok('final sends once', () => assert.equal(h.sent.length, 1));
  }

  // 4. Two different utterances -> two messages.
  {
    const h = harness(edition);
    h.recognizer.start();
    h.emit([{ text: 'hello' }]);
    h.emit([{ text: 'how are you' }]);
    ok('two utterances send twice', () => assert.equal(h.sent.length, 2));
  }

  // 5. THE REPORTED BUG: patient speech must not be transcribed back.
  {
    const h = harness(edition);
    h.recognizer.start();
    h.emit([{ text: 'hello' }]);
    assert.equal(h.sent.length, 1);
    // The patient begins speaking: suppression runs BEFORE audio is audible.
    vm.runInContext('suppressListeningForPatient()', h.context);
    ok('suppression aborts rather than finalizes',
       () => assert.ok(h.recognizer.aborts >= 1, 'expected abort(), got stops=' + h.recognizer.stops));
    // The microphone hears the patient's reply while suppressed.
    h.context.window.speechSynthesis.speaking = true;
    h.recognizer.running = true;
    h.emit([{ text: 'hello thank you for introducing yourself I am ready to talk' }]);
    h.context.window.speechSynthesis.speaking = false;
    ok('patient speech is not sent', () => assert.equal(h.sent.length, 1));
    // And it must not be re-delivered once the mute window lapses.
    h.context.voice.muteUntil = 0;
    h.context.voice.suppressed = false;
    h.reemitAll();
    ok('patient speech is not replayed after the mute window',
       () => assert.deepEqual(h.sent.map(s => s.text), ['hello']));
  }

  // 6. onend must not resume while the patient is still audible.
  {
    const h = harness(edition);
    h.recognizer.start();
    const before = h.recognizer.starts;
    vm.runInContext('suppressListeningForPatient()', h.context);
    ok('no restart while the patient speaks',
       () => assert.equal(h.recognizer.starts, before));
  }

  // 7. A deliberate repeat, spoken later, is a separate message.
  {
    const h = harness(edition);
    h.recognizer.start();
    h.emit([{ text: 'hello' }]);
    h.context.voice.lastSentAt = Date.now() - 5000;   // several seconds pass
    h.emit([{ text: 'hello' }]);
    ok('deliberate repeat is allowed', () => assert.equal(h.sent.length, 2));
  }

  // 8. A duplicated event within milliseconds is suppressed.
  {
    const h = harness(edition);
    h.recognizer.start();
    h.emit([{ text: 'hello' }]);
    h.context.voice.lastFinal = -1;                   // simulate a lost watermark
    h.reemitAll();
    ok('rapid duplicate is suppressed by the send guard',
       () => assert.equal(h.sent.length, 1));
  }

  // 9. A new session resets the watermark, so later speech still works.
  {
    const h = harness(edition);
    h.recognizer.start();
    h.emit([{ text: 'hello' }]);
    const startsBefore = h.recognizer.starts;
    h.recognizer.stop();   // onend auto-restarts while hands-free is on
    ok('hands-free resumes automatically after a natural end',
       () => assert.equal(h.recognizer.starts, startsBefore + 1));
    ok('the resumed session starts with a clean watermark',
       () => assert.equal(h.context.voice.lastFinal, -1));
    h.context.voice.lastSentAt = Date.now() - 5000;
    h.emit([{ text: 'what brings you in today' }]);
    ok('speech after a restart still sends', () => assert.equal(h.sent.length, 2));
  }

  // 10. Silence produces nothing.
  {
    const h = harness(edition);
    h.recognizer.start();
    h.reemitAll(); h.reemitAll();
    ok('silence sends nothing', () => assert.equal(h.sent.length, 0));
  }

  // 11. Low confidence is staged for correction, not sent blind.
  {
    const h = harness(edition);
    h.recognizer.start();
    h.emit([{ text: 'mumble', conf: 0.4 }]);
    ok('low confidence is staged', () => assert.ok(h.sent[0] && h.sent[0].staged));
  }

  // 12. A long utterance arrives as one message, not fragments.
  {
    const h = harness(edition);
    h.recognizer.start();
    h.recognizer.results.push(Object.assign([{ transcript: 'what is your name', confidence: 0.9 }], { isFinal: false }));
    h.recognizer.onresult({ resultIndex: 0, results: h.recognizer.results });
    h.recognizer.results[0][0].transcript = 'what is your name and what brings you in today';
    h.recognizer.results[0].isFinal = true;
    h.recognizer.onresult({ resultIndex: 0, results: h.recognizer.results });
    ok('long utterance is one message', () => assert.equal(h.sent.length, 1));
    ok('long utterance is complete',
       () => assert.equal(h.sent[0].text, 'what is your name and what brings you in today'));
  }

  console.log('PASS %s: %d checks — %s', label, checks.length,
              'one utterance one message; patient audio never transcribed; repeats preserved');
}

const editions = [];
for (const dir of [path.resolve(__dirname, '..'), path.resolve(__dirname, '../../pcm-cse-public')]) {
  if (fs.existsSync(path.join(dir, 'web/app.js'))) editions.push(dir);
}
for (const edition of editions) run(edition, path.basename(edition));
