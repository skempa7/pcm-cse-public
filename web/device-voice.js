/* Fixed patient-voice policy. There is no user voice selection any more.

   The patient's voice is decided by the case's authored presentation, never by
   the learner and never inferred from the patient's name or appearance:

       female  ->  "Google US English"       (en-US)
       male    ->  "Google UK English Male"  (en-GB)

   This module is the ONLY place a voice is applied to an utterance, so both
   editions cannot drift. `configure()` is the single choke point.

   AVAILABILITY IS HANDLED HONESTLY. If the required voice is not present in
   this runtime the patient does not speak with some other voice: no voice is
   set, `configure()` reports the shortfall, and the caller shows an
   unavailable state. Substituting a different voice would misrepresent the
   patient, and silently falling back is exactly what the policy forbids.

   Chrome returns an EMPTY voice list until it fires `voiceschanged`, so the
   list is re-read on that event and immediately before each use. */
(() => {
  'use strict';
  const REQUIRED = {
    female: { name: 'Google US English', lang: 'en-US' },
    male: { name: 'Google UK English Male', lang: 'en-GB' },
  };
  // Retired user-selection keys. They are removed once so a voice chosen under
  // the old settings screen cannot override the fixed mapping, and so the
  // obsolete value does not sit in storage forever. Nothing else is touched.
  for (const stale of ['pcmcse.device-voice.v1', 'pcmcse.natural-voice.v1']) {
    try { localStorage.removeItem(stale); } catch (e) { /* private mode */ }
  }

  const synth = window.speechSynthesis;
  let voices = [];
  const listeners = new Set();

  function refresh() {
    voices = (synth && synth.getVoices && synth.getVoices()) || [];
    for (const fn of listeners) { try { fn(state()); } catch (e) { /* isolated */ } }
    return state();
  }

  /* Exact name first. A trailing-space or case variant of the same Google
     voice is accepted, because that is the same voice; a DIFFERENT voice never
     is. Language alone is never enough -- "en-US" would match dozens. */
  function find(spec) {
    if (!spec) return null;
    const want = spec.name.toLowerCase();
    return voices.find(v => v.name === spec.name)
        || voices.find(v => String(v.name || '').trim().toLowerCase() === want)
        || null;
  }

  function specFor(sex) {
    return REQUIRED[String(sex || '').toLowerCase()] || null;
  }

  function state(sex) {
    const spec = specFor(sex);
    const voice = spec ? find(spec) : null;
    return {
      supported: !!synth,
      // `loading` distinguishes "Chrome has not delivered the list yet" from
      // "this runtime does not have the voice", so the UI can stay quiet
      // during startup instead of announcing a failure that is not real.
      loading: !!synth && voices.length === 0,
      required: spec,
      resolved: voice ? { name: voice.name, lang: voice.lang } : null,
      available: !!voice,
    };
  }

  /* Apply the patient's voice to an utterance.
     `sex` comes from the session's authored appearance (S.appearance.presentation).
     Returns the state so the caller can report an unavailable voice. */
  function configure(utterance, { pace, sex } = {}) {
    refresh();
    const info = state(sex);
    if (info.available) {
      const voice = find(info.required);
      utterance.voice = voice;
      utterance.lang = voice.lang || info.required.lang;
    }
    // When unavailable, neither voice nor lang is set. The utterance is not
    // spoken by the caller in that case; leaving them unset means nothing here
    // can quietly pick a substitute.
    const rates = { measured: .94, conversational: .98, slightly_hesitant: .94,
                    direct: 1, unhurried: .92, deliberate: .94 };
    utterance.rate = rates[pace] || 1;
    utterance.pitch = 1;
    return info;
  }

  function subscribe(fn) {
    listeners.add(fn);
    try { fn(state()); } catch (e) { /* isolated */ }
    return () => listeners.delete(fn);
  }

  if (synth && 'onvoiceschanged' in synth) synth.onvoiceschanged = refresh;
  window.addEventListener('focus', refresh);
  refresh();

  window.pcmDeviceSpeech = { state, refresh, configure, subscribe, REQUIRED };
})();
