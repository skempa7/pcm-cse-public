/* Fixed patient-voice policy.

   Two voices, chosen from the case's authored presentation, with no user
   selection anywhere. The rules that matter clinically: never substitute a
   different voice, never let a saved preference win, and never let the
   patient's audio preference touch the clinician's microphone.

   device-voice.js is byte-identical across editions, so both are exercised. */
const fs = require('fs'), path = require('path'), vm = require('vm');
const assert = require('node:assert/strict');

function boot(edition, voiceNames = []) {
  const src = fs.readFileSync(path.join(edition, 'web/device-voice.js'), 'utf8');
  const store = new Map();
  const voices = voiceNames.map(v => (typeof v === 'string'
    ? { name: v, lang: v.includes('UK') ? 'en-GB' : 'en-US', voiceURI: v }
    : v));
  const ctx = {
    console,
    localStorage: {
      getItem: k => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: k => store.delete(k),
    },
    window: { addEventListener() {} },
    speechSynthesis: { getVoices: () => voices, speaking: false, cancel() {} },
  };
  ctx.window.speechSynthesis = ctx.speechSynthesis;
  ctx.window.localStorage = ctx.localStorage;
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  return { api: ctx.window.pcmDeviceSpeech, store, ctx };
}

const FEMALE = 'Google US English';
const MALE = 'Google UK English Male';

function run(edition, label) {
  let n = 0;
  const ok = (cond, msg) => { n++; assert.ok(cond, msg); };

  // 1. The mapping is exactly the two required voices.
  {
    const { api } = boot(edition);
    assert.deepEqual(Object.keys(api.REQUIRED).sort(), ['female', 'male']);
    assert.equal(api.REQUIRED.female.name, FEMALE);
    assert.equal(api.REQUIRED.female.lang, 'en-US');
    assert.equal(api.REQUIRED.male.name, MALE);
    assert.equal(api.REQUIRED.male.lang, 'en-GB');
    n += 4;
  }

  // 2. No user-selection surface survives on the module.
  {
    const { api } = boot(edition);
    for (const gone of ['choose', 'list', 'preview']) {
      ok(!(gone in api), `${gone}() still exposed — voice selection must be gone`);
    }
  }

  // 3. The right voice is applied per sex, and the language with it.
  {
    const { api } = boot(edition, [FEMALE, MALE, 'Daniel', 'Samantha']);
    const f = {}; const fi = api.configure(f, { sex: 'female' });
    ok(f.voice && f.voice.name === FEMALE, 'female patient did not get the US voice');
    ok(f.lang === 'en-US', 'female utterance language wrong: ' + f.lang);
    ok(fi.available === true, 'female voice reported unavailable when present');
    const m = {}; const mi = api.configure(m, { sex: 'male' });
    ok(m.voice && m.voice.name === MALE, 'male patient did not get the UK male voice');
    ok(m.lang === 'en-GB', 'male utterance language wrong: ' + m.lang);
    ok(mi.available === true, 'male voice reported unavailable when present');
  }

  // 4. THE POLICY: an absent voice is never substituted.
  {
    const { api } = boot(edition, ['Daniel', 'Samantha', 'Alex']);
    const u = {}; const info = api.configure(u, { sex: 'female' });
    ok(info.available === false, 'reported available with no matching voice');
    ok(u.voice === undefined, 'substituted a different voice: ' + (u.voice && u.voice.name));
    ok(u.lang === undefined, 'set a language for a voice it does not have');
    ok(info.required.name === FEMALE, 'did not report which voice is required');
  }

  // 5. Chrome's async voice list is distinguished from a missing voice.
  {
    const { api } = boot(edition, []);          // getVoices() empty, as on first call
    const info = api.state('female');
    ok(info.loading === true, 'empty voice list not reported as still loading');
    ok(info.available === false, 'claimed availability from an empty list');
  }

  // 6. A previously saved user choice cannot override the mapping.
  {
    const src = fs.readFileSync(path.join(edition, 'web/device-voice.js'), 'utf8');
    ok(!/getItem\(\s*['"]pcmcse\.device-voice/.test(src),
       'the retired voice preference is still being READ');
    ok(/removeItem/.test(src), 'the retired voice preference is not cleared');
    const { store } = boot(edition, [FEMALE]);
    store.set('pcmcse.device-voice.v1', JSON.stringify({ name: 'Daniel', uri: 'Daniel' }));
    const again = boot(edition, [FEMALE]);
    const u = {}; again.api.configure(u, { sex: 'female' });
    ok(u.voice.name === FEMALE, 'a saved preference overrode the fixed mapping');
  }

  // 7. An unknown or missing sex does not guess a voice.
  {
    const { api } = boot(edition, [FEMALE, MALE]);
    for (const sex of [undefined, null, '', 'neutral', 'unknown']) {
      const u = {}; const info = api.configure(u, { sex });
      ok(info.available === false && u.voice === undefined,
         `sex ${JSON.stringify(sex)} guessed a voice`);
    }
  }

  // 8. Pace still shapes delivery, and never leaks a pitch change.
  {
    const { api } = boot(edition, [FEMALE]);
    const u = {}; api.configure(u, { sex: 'female', pace: 'unhurried' });
    ok(u.rate === 0.92, 'authored pace ignored: rate=' + u.rate);
    ok(u.pitch === 1, 'pitch was altered');
  }

  console.log('PASS %s: %d checks — two fixed voices, no selection surface, '
              + 'no substitution, saved preferences cannot override', label, n);
}

/* The toggle must govern patient OUTPUT only. Verified against app.js source:
   a preference change must not post delivery evidence, and must not stop the
   clinician's microphone or clear hands-free. */
function toggleContract(edition, label) {
  const src = fs.readFileSync(path.join(edition, 'web/app.js'), 'utf8');
  let n = 0;
  const ok = (c, m) => { n++; assert.ok(c, m); };
  const setEnabled = src.slice(src.indexOf('setEnabled:value=>'), src.indexOf('setEnabled:value=>') + 400);
  ok(/silencePatientAudio\(\)/.test(setEnabled),
     'the toggle does not use the narrow silence path');
  ok(!/interruptPatient\(\)/.test(setEnabled),
     'turning the toggle off still calls interruptPatient(), which reports a '
     + 'user-initiated delivery interruption to the server');
  const silence = src.slice(src.indexOf('function silencePatientAudio()'),
                            src.indexOf('function stopVoice()'));
  ok(!/hands_free\s*=/.test(silence), 'silencing patient audio changes hands-free');
  ok(!/rec\.(?:stop|abort)\(\)/.test(silence), 'silencing patient audio stops the microphone');
  ok(/speechSynthesis\?\.cancel\(\)/.test(silence), 'it does not cancel current speech');
  ok(/if \(!voice\.speak\) return;/.test(src.slice(src.indexOf('function speak('),
                                                   src.indexOf('function speak(') + 200)),
     'speak() does not honour the toggle');
  // No settings surface may survive anywhere.
  for (const dead of ['panelVoice', 'wireVoicePanel', 'btnVoicePanel', 'ewDeviceVoice',
                      'ewPreviewVoice', 'ewRefreshVoices']) {
    ok(!src.includes(dead), `retired voice UI still referenced in app.js: ${dead}`);
  }
  console.log('PASS %s: %d checks — toggle governs patient output only, writes no '
              + 'evidence, leaves the microphone alone', label, n);
}

const editions = [];
for (const dir of [path.resolve(__dirname, '..')]) {
  if (fs.existsSync(path.join(dir, 'web/device-voice.js'))) editions.push(dir);
}
for (const e of editions) { run(e, path.basename(e)); toggleContract(e, path.basename(e) + ' toggle'); }
