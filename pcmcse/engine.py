"""Session state machine: phases, timers, and the encounter turn processor.

Phases run briefing -> encounter -> organize (practice preset only) -> note ->
submitted.  Deadlines are stored as absolute times, so the remaining clock
survives a refresh, a new tab, or a restarted server.

Unused encounter time is *not* transferred into the note period.  No course
rule supports carry-over, so the note always gets its own nine minutes.
"""

from __future__ import annotations

import json
import re

from . import audit as audit_mod
from . import cases, checklist, config, db, evidence, feedback, grader, ips
from . import note as note_mod
from . import intent as intent_mod
from . import nlp, patient, physexam, presentation, historical_cases
from . import version as version_mod

PHASES = ["briefing", "encounter", "organize", "note", "submitted"]
PATIENT_POSITIONS = ("seated", "supine", "standing", "prone")

# --- utterance classification ----------------------------------------------

_OPEN_STARTS = ["what", "how", "tell me", "describe", "walk me", "can you tell",
                "could you tell", "in your own words", "why", "talk to me about"]
_CLOSED_STARTS = ["do ", "does ", "did ", "are ", "is ", "was ", "were ", "have ",
                  "has ", "had ", "any ", "can ", "could ", "will ", "would ",
                  "should ", "if ", "so "]

_TRANSITION_MARKERS = [
    "now i'm going to", "now im going to", "i'd like to ask", "id like to ask",
    "i would like to ask", "now i would like to", "i am going to ask",
    "now i am going to ask", "i'm going to ask", "im going to ask",
    "next i would like", "now i'd like to", "now id like to",
    "next i'll", "next ill", "let me ask you about", "i want to ask about",
    "switching", "moving on", "now let's talk", "now lets talk",
    "i'm going to change", "im going to change", "before we move on",
    "i'm going to shift", "im going to shift", "let's turn to", "lets turn to",
]
_TRANSITION_REASON = ["because", "so that", "since", "this helps", "it helps",
                      "we find that", "the reason", "to make sure", "so i can"]

_SUMMARY_MARKERS = [
    "let me make sure i have this", "so what i'm hearing", "so what im hearing",
    "let me summarize", "let me summarise", "to recap", "so to review",
    "if i understand correctly", "let me repeat back", "just to summarize",
    "let me see if i got", "so to summarize", "so if i've got this right",
]
_CLOSURE_MARKERS = [
    "any questions", "questions for me", "any concerns", "any comments",
    "anything you'd like to ask", "anything you would like to ask",
    "what questions do you have", "anything else you want to ask",
    "does that make sense", "anything on your mind",
]
_EMPATHY_MARKERS = [
    "that must", "i'm sorry", "im sorry", "sounds difficult", "sounds hard",
    "that sounds", "i can imagine", "i understand", "must be frustrating",
    "must be scary", "must be worrying", "thank you for sharing",
    "i appreciate you", "that's a lot", "thats a lot", "i can tell",
]
_PLAN_MARKERS = [
    "i'd like to", "i would like to", "we're going to", "we are going to",
    "the plan is", "what i'd recommend", "what i recommend", "next step",
    "i'm going to order", "im going to order", "i want to check", "we'll get",
    "we will get", "i'll prescribe", "ill prescribe", "you should",
    "i want you to", "come back", "follow up", "if it gets worse", "return to",
    "i'm going to send", "im going to send", "let's get", "lets get",
    "i'll write you", "ill write you", "watch out for", "call me if",
    "go to the emergency", "return precaution",
    "i am concerned", "i'm concerned", "im concerned", "we need",
    "i recommend", "i am recommending", "i suggest", "we can discuss", "i will ask", "we can keep", "i will arrange", "i will explain", "please do not",
    "please avoid", "we should", "i will order", "i am going to order",
]

_COUNSEL_TOPICS = {
    "return precaution": ["come back if", "return if", "call me if", "go to the er if",
                          "go to the emergency", "if it gets worse", "warning sign",
                          "red flag", "watch out for", "return precaution"],
    "hydration": ["drink", "fluids", "hydrat", "water"],
    "medication": ["take the", "prescribe", "antibiotic", "medication", "full course",
                   "finish the", "side effect"],
    "diet": ["diet", "eat", "salt", "food"],
    "follow up": ["follow up", "come back in", "see me in", "return in", "recheck"],
    "hygiene": ["hygiene", "wipe", "voiding", "urinate after"],
    "diagnosis explanation": ["i think what's going on", "i think whats going on",
                              "what i think is happening", "this looks like",
                              "my concern is", "what this could be",
                              "i am concerned", "i'm concerned", "im concerned"],
    "diagnostic evaluation": ["blood test", "blood work", "ultrasound",
                              "urine test", "urine culture", "imaging",
                              "electrocardiogram", "ecg", "urgent evaluation"],
}


def _classify(text):
    t = nlp.normalize(text)
    tags = {}
    if not t:
        return tags
    if t.endswith("?") or any(t.startswith(s) for s in _OPEN_STARTS):
        tags["open_question"] = any(t.startswith(s) for s in _OPEN_STARTS)
    if not tags.get("open_question") and any(t.startswith(s) for s in _CLOSED_STARTS):
        tags["closed_question"] = True
    if any(m in t for m in _TRANSITION_MARKERS):
        tags["transition"] = True
        tags["transition_explained"] = any(r in t for r in _TRANSITION_REASON)
    if any(m in t for m in _SUMMARY_MARKERS):
        tags["summary"] = True
    if any(m in t for m in _CLOSURE_MARKERS):
        tags["closure"] = True
    if any(m in t for m in _EMPATHY_MARKERS):
        tags["empathy"] = True
    if any(m in t for m in _PLAN_MARKERS) and not _is_question(text):
        tags["plan_talk"] = True
    return tags


def _counsel_topics(text):
    t = nlp.normalize(text)
    return [topic for topic, cues in _COUNSEL_TOPICS.items()
            if any(c in t for c in cues)]


_EXAM_VERBS = ["auscultate", "palpate", "percuss", "inspect", "examine",
               "listen to", "look in", "look at", "check for", "assess",
               "otoscop", "range of motion", "straight leg", "i will feel"]


_QUESTION_STARTS = ["what", "when", "where", "why", "how", "who", "which",
                    "do ", "does ", "did ", "are ", "is ", "was ", "were ",
                    "have ", "has ", "had ", "any ", "can ", "could ", "would ",
                    "will ", "tell me", "describe"]


def _is_question(text):
    t = nlp.normalize(text)
    raw = (text or "").strip()
    if raw.endswith("?"):
        return True
    # A trailing clause can carry the question: "...habits. Do you smoke?"
    for part in re.split(r"[.;]\s*", raw):
        pt = nlp.normalize(part)
        if pt and any(pt.startswith(q) for q in _QUESTION_STARTS):
            return True
    return False


def _has_exam_verb(text):
    t = nlp.normalize(text)
    # A passive disposition ("until assessed") does not instruct the learner
    # to perform a maneuver. Keep the deliberate otoscope stem, but require
    # complete words for the ordinary action verbs.
    return any(re.search(r"(?<![a-z])" + re.escape(v) +
                         (r"[a-z]*\b" if v == "otoscop" else r"\b"), t)
               for v in _EXAM_VERBS)


def _courtesy_hits(text):
    """Courtesy actions the learner actually performed.

    A trigger word is not the action. "I have no hand sanitizer available"
    contains the hand-hygiene trigger and is the opposite of doing it, so an
    absence or a negation scoped to the trigger earns nothing.
    """
    t = nlp.normalize(text)
    if intent_mod.describes_absence(text):
        return []
    out = []
    for c in physexam.COURTESY:
        for trig in c["triggers"]:
            if nlp.normalize(trig) in t:
                if intent_mod.courtesy_is_negated(text, trig):
                    break
                out.append(c)
                break
    return out


# ---------------------------------------------------------------------------
# Session wrapper
# ---------------------------------------------------------------------------

class Session:
    def __init__(self, row):
        self.row = row
        self.id = row["id"]
        self.case = historical_cases.for_attempt(row)
        self.ledger = evidence.Ledger.from_json(row["ledger_json"])
        self.pstate = json.loads(row["patient_state"] or "{}")
        self.settings = json.loads(row["settings_json"] or "{}")
        self.preset = config.PRESETS[row["preset"]]
        self.integrity = json.loads(row["integrity_json"] or "{}")
        self._dirty = {}

    # -- persistence ------------------------------------------------------
    def save(self):
        context = getattr(self, "bridge_context", None)
        if context:
            for event in self.ledger.events:
                if event["seq"] > context["after_seq"]:
                    event["meta"].update(source=context.get("renderer","unity"), request_id=context["request_id"])
        self._dirty["ledger_json"] = self.ledger.to_json()
        self._dirty["patient_state"] = json.dumps(self.pstate)
        self._dirty["integrity_json"] = json.dumps(self.integrity)
        db.update_session(self.id, **self._dirty)
        self._dirty = {}

    def set(self, **kw):
        self.row.update(kw)
        self._dirty.update(kw)

    # -- timing -----------------------------------------------------------
    def wall_elapsed_ms(self):
        started = self.row["phase_started_at"]
        return max(0, db.now_ms() - started) if started else 0

    def elapsed_ms(self):
        """Encounter time used, counting examinations as the time they take.

        An examination occupies its configured duration, so the clock cannot be
        behind the end of the examination that is running. Taking the MAXIMUM of
        wall time and the examination's completion time charges that duration
        exactly once -- it is not added on top of the seconds that really
        elapsed -- and it makes examinations serial by construction, which is
        what stops two of them overlapping.
        """
        wall = self.wall_elapsed_ms()
        if self.row["phase"] != "encounter":
            return wall
        if self.settings.get("simulation_runtime") == "interactive":
            return getattr(self, "_completion_elapsed", wall)
        return max(wall, self.row["exam_busy_until"] or 0)

    def remaining_ms(self):
        ends = self.row["phase_ends_at"]
        if not ends:
            return None
        return max(0, ends - db.now_ms())

    def is_untimed_phase(self, phase=None):
        phase = phase or self.row["phase"]
        # Additive preset keys keep every historical coached/independent row's
        # timing intact. Historical guided encounters/notes were already
        # untimed; their old organization interval remains unchanged.
        return bool(self.preset.get("untimed")) or (
            self.settings.get("learning_mode") == "guided"
            and phase in ("encounter", "note"))

    def phase_duration_s(self):
        if self.row["phase"] in ("encounter", "organize", "note") and self.is_untimed_phase():
            return None
        return {
            "encounter": self.preset["encounter_s"],
            "organize": self.preset["organize_s"],
            "note": self.preset["note_s"],
        }.get(self.row["phase"], 0)

    # -- phase transitions ------------------------------------------------
    def advance_if_expired(self):
        """Called on every request; the clock is the server's, not the page's."""
        changed = False
        while True:
            phase = self.row["phase"]
            ends = self.row["phase_ends_at"]
            if phase not in ("encounter", "organize", "note") or not ends:
                break
            if db.now_ms() < ends:
                break
            # Chain from the deadline that expired, NOT from the time of the
            # request that noticed it. Returning an hour late used to start a
            # fresh two-minute organization period and a fresh nine-minute note
            # period, handing back time the clock had already spent.
            if phase == "encounter":
                self._end_encounter("time_expired", at_ms=ends)
            elif phase == "organize":
                self._start_note(at_ms=ends)
            elif phase == "note":
                self._submit("time_expired", at_ms=ends)
            changed = True
        if changed:
            self.save()
        return changed

    def start_encounter(self):
        if self.row["phase"] != "briefing":
            return
        now = db.now_ms()
        self.set(phase="encounter", phase_started_at=now,
                 phase_ends_at=None if self.is_untimed_phase("encounter")
                 else now + self.preset["encounter_s"] * 1000)
        self.ledger.add(evidence.SYSTEM, "Encounter started.", t_ms=0,
                        phase="encounter", meta={"event": "phase_start"})
        # Authorized station information enters the record as evidence.
        self.ledger.add(evidence.STATION_INFO,
                        " ".join(self.case["station"]["doorway"]), t_ms=0,
                        phase="encounter", meta={"doorway": True})
        vitals = self.case["station"]["vitals"]
        self.ledger.add(
            evidence.STATION_INFO,
            "Vital signs supplied on the chart: " +
            ", ".join("%s %s" % kv for kv in vitals.items()),
            t_ms=0, phase="encounter",
            meta={"vitals": True,
                  "concepts": {"vitals": {"polarity": "positive",
                                          "value": json.dumps(vitals)}}})
        for res in self.case["station"].get("supplied_results", []):
            self.ledger.add(
                evidence.STATION_INFO, res["label"] + ": " + res["value"],
                t_ms=0, phase="encounter",
                meta={"supplied_id": res["id"], "concepts": res.get("concepts", {})})
        self.save()

    def _end_encounter(self, reason, at_ms=None):
        self.finish_pending(cancel=True)
        expired = at_ms is not None
        if expired:
            used = max(0, at_ms - (self.row["phase_started_at"] or at_ms))
        else:
            used = self.elapsed_ms()
        self.set(encounter_used_ms=used)
        self.ledger.add(evidence.SYSTEM,
                        "Encounter closed (%s). The encounter record is frozen; "
                        "no further information can be obtained." % reason,
                        t_ms=used, phase="encounter",
                        meta={"event": "encounter_closed", "reason": reason,
                              "ended_by": "deadline" if expired else "student"})
        now = at_ms if expired else db.now_ms()
        if self.preset["organize_s"] > 0:
            self.set(phase="organize", phase_started_at=now,
                     phase_ends_at=None if self.is_untimed_phase("organize") else now + self.preset["organize_s"] * 1000)
        else:
            self._start_note(at_ms=at_ms)

    def _start_note(self, at_ms=None):
        now = at_ms if at_ms is not None else db.now_ms()
        self.set(phase="note", phase_started_at=now,
                 phase_ends_at=None if self.is_untimed_phase("note")
                 else now + self.preset["note_s"] * 1000)

    def end_encounter_now(self):
        if self.row["phase"] != "encounter":
            return
        self._end_encounter("student ended early")
        self.save()

    def skip_organize(self):
        if self.row["phase"] != "organize":
            return
        self._start_note()
        self.save()

    def _submit(self, reason, at_ms=None):
        # Freeze the latest eligible draft in the same write that closes the
        # attempt, so nothing arriving afterwards can change what was handed in.
        frozen = self.row["original_note_json"] or (self.row["note_json"] or "{}")
        self.set(phase="submitted", submit_reason=reason,
                 submitted_at=at_ms if at_ms is not None else db.now_ms(),
                 phase_ends_at=None, original_note_json=frozen)

    def submit(self, reason="submitted"):
        if self.row["phase"] != "note":
            return
        self._submit(reason)
        self.save()

    # -- interruption transparency ---------------------------------------
    def record_interruption(self, kind, detail, ms=0):
        self.integrity.setdefault("events", []).append(
            {"kind": kind, "detail": detail, "at": db.now_ms(), "ms": ms})
        self.ledger.add(evidence.SYSTEM, detail, t_ms=self.elapsed_ms(),
                        phase=self.row["phase"],
                        meta={"interruption": True, "kind": kind})
        self.save()

    # -- the encounter turn ----------------------------------------------
    def student_turn(self, text, mode="type", confidence=None, uncertain_spans=None, response_override=None, defer_patient=False):
        if self.row["phase"] != "encounter":
            return {"error": "closed",
                    "message": "The encounter is closed. No further information "
                               "can be obtained from the patient."}
        text = (text or "").strip()
        if not text:
            return {"events": []}

        t = self.elapsed_ms()
        tags = _classify(text)
        low_conf = confidence is not None and confidence < 0.65

        meta = dict(tags)
        if getattr(self,"conversation_request",None):meta["conversation_request_id"]=self.conversation_request
        meta["mode"] = mode
        if confidence is not None:
            meta["asr_confidence"] = round(float(confidence), 2)
        if low_conf:
            meta["uncertain"] = True
        if uncertain_spans:
            meta["uncertain_spans"] = uncertain_spans

        topics = _counsel_topics(text) \
            if (tags.get("plan_talk") or tags.get("closure")) else []
        # A clearly stated future plan is still an explanation when its test
        # name falls outside the topic vocabulary. This is discussion evidence,
        # never a performed test, result, or proof of clinical appropriateness.
        if tags.get("plan_talk") and not topics and not _has_exam_verb(text):
            topics = ["plan discussion"]
        if patient.conversation_route(text)=='introduction':topics=[]
        if topics:
            meta["counseling_turn"] = True
        student_ev = self.ledger.add(evidence.STUDENT, text, t_ms=t,
                                     meta=meta)
        out = {"events": [], "student_seq": student_ev["seq"]}

        if low_conf:
            self.ledger.add(
                evidence.UNCERTAIN,
                "Speech recognition confidence was low for this turn. The text is "
                "preserved as heard and is not scored as a definite error.",
                t_ms=t, meta={"of_seq": student_ev["seq"],
                              "confidence": meta.get("asr_confidence")})
            out["uncertain"] = True

        # 1. Courtesy / technique statements
        courtesy = _courtesy_hits(text)
        for c in courtesy:
            self.ledger.add(evidence.COURTESY, text, t_ms=t,
                            meta={"courtesy_id": c["id"], "label": c["label"]})
            out["events"].append({"kind": "courtesy", "label": c["label"]})

        # 2. Counselling / plan discussion
        if topics:
            self.ledger.add(evidence.COUNSELING, text, t_ms=t,
                            meta={"topics": topics})
            out["events"].append({"kind": "counseling", "topics": topics})

        # Social introductions and explicit clarification must not be routed as
        # counseling or borrowed clinical history, including in AI delivery mode.
        if patient.conversation_route(text):
            reply,pmeta=patient.PatientEngine(self.case).respond(text,self.pstate)
            ev=self.ledger.add(evidence.PATIENT,reply,t_ms=self.elapsed_ms(),meta=pmeta)
            out['events'].append({'kind':'patient','text':reply,'seq':ev['seq']})
            self.save()
            return out

        # Exact authored education exchanges are communication, not a fresh
        # symptom question or an examination order. Preserve their specific
        # acknowledgment instead of a generic plan line or unrelated history.
        education_pair=next((p for p in self.case.get('patient',{}).get('education_responses',[])
                             if nlp.normalize(p['student']).strip(' .?')==nlp.normalize(text).strip(' .?')),None)
        if education_pair:
            reply,pmeta=patient.PatientEngine(self.case).respond(text,self.pstate)
            ev=self.ledger.add(evidence.PATIENT,reply,t_ms=self.elapsed_ms(),meta=pmeta)
            out['events'].append({'kind':'patient','text':reply,'seq':ev['seq']})
            self.save()
            return out

        # 3. Explaining the plan is not an examination instruction, even when
        #    it names a body part or a test -- but a *question* is always a
        #    question first, however it is phrased.
        plan_turn = bool(topics) and not _has_exam_verb(text) \
            and not _is_question(text)
        if plan_turn:
            engine = patient.PatientEngine(self.case)
            ack = engine.acknowledge_plan(self.pstate)
            ev = self.ledger.add(evidence.PATIENT, ack, t_ms=self.elapsed_ms(),
                                 meta={"kind": "plan_ack"})
            out["events"].append({"kind": "patient", "text": ack, "seq": ev["seq"]})
            self.save()
            return out

        # 4. Examination action?
        #
        # Decide the SPEECH ACT before touching examination state. A question,
        # a negation, a permission request, an offer, or a reference to work
        # already done must never release findings, however many anatomical
        # words it contains.
        reading = intent_mod.interpret(
            text, courtesy_ids=[c["id"] for c in courtesy], tags=tags)
        meta["intent"] = reading["intent"]
        student_ev["meta"]["intent"] = reading["intent"]

        if reading["intent"] in (intent_mod.NEGATED, intent_mod.PAST):
            self.ledger.add(evidence.EXAM_ACTION, text, t_ms=t,
                            meta={"status": "not_performed",
                                  "intent": reading["intent"],
                                  "reason": reading["reason"]})
            out["events"].append({"kind": "sim_note", "text": reading["reason"]})
            self.save()
            return out

        if reading["intent"] == intent_mod.CONSENT:
            asked = physexam.resolve(text)
            engine = patient.PatientEngine(self.case)
            reply = engine.grant_consent(self.pstate, asked.get("maneuver"))
            ev = self.ledger.add(evidence.PATIENT, reply, t_ms=self.elapsed_ms(),
                                 meta={"kind": "consent"})
            self.ledger.add(evidence.EXAM_ACTION, text, t_ms=t,
                            meta={"status": "consented",
                                  "maneuver": (asked.get("maneuver") or {}).get("id"),
                                  "reason": reading["reason"]})
            out["events"].append({"kind": "patient", "text": reply,
                                  "seq": ev["seq"]})
            out["events"].append({"kind": "sim_note", "text": reading["reason"]})
            self.save()
            return out

        resolved = physexam.resolve(text) if reading["may_examine"] \
            else {"status": "none", "maneuver": None, "components": [],
                  "reason": ""}

        # "Is it okay if I examine you now? Let me help you lie back" is a
        # courtesy, not an under-specified maneuver; do not scold the student
        # for it.
        if resolved["status"] == "vague" and courtesy:
            resolved = {"status": "none", "maneuver": None, "components": [],
                        "reason": ""}
        if resolved["status"] != "none":
            # Narrating a maneuver is a different speech act from interviewing.
            # Tagging it keeps organisation and jargon scoring honest.
            student_ev["meta"]["exam_turn"] = True
        if resolved["status"] != "none":
            out["events"].append(self._do_exam(resolved, text, t))
            # A performed maneuver, a refusal, or an under-specified action is a
            # complete turn. Falling through would make the patient answer an
            # examination instruction, which she has no reason to do.
            if resolved["status"] in ("performed", "refusable", "vague"):
                self.save()
                return out

        # 5. Otherwise the patient answers.
        engine = patient.PatientEngine(self.case)
        if response_override is not None:
            reply,pmeta=response_override['text'],response_override['meta']
        else:
            reply, pmeta = engine.respond(text, self.pstate)
        if defer_patient:
            out['patient_deferred']=True
            self.save()
            return out
        if pmeta.get("no_information") and topics and not courtesy:
            reply = patient.PatientEngine(self.case).acknowledge_plan(self.pstate)
            pmeta = {"facts_released": [], "concepts": {}, "volunteered": False,
                     "kind": "plan_ack"}
        elif pmeta.get("no_information") and courtesy:
            # An introduction or a courtesy statement deserves a human reply,
            # not "could you say that another way".
            reply = engine.acknowledge_courtesy(self.pstate,
                                                [c["id"] for c in courtesy])
            pmeta = {"facts_released": [], "concepts": {}, "volunteered": False,
                     "kind": "courtesy_ack"}
        if reply:
            pmeta["categories"] = [
                f.get("category") for f in self.case["facts"]
                if f["id"] in pmeta.get("facts_released", [])]
            ev = self.ledger.add(evidence.PATIENT, reply, t_ms=self.elapsed_ms(),
                                 meta=pmeta)
            out["events"].append({
                "kind": "patient", "text": reply, "seq": ev["seq"],
                "volunteered": pmeta.get("volunteered", False),
                "no_information": pmeta.get("no_information", False),
            })
        self.save()
        return out

    def position_patient(self, position):
        """Persist simulated positioning, without supplying examination findings.

        A pose is not evidence of normal balance, gait, strength, tolerance, or
        orthostatic measurements. Those still require their specific actions.
        """
        if not isinstance(position, str) or position not in PATIENT_POSITIONS:
            raise ValueError('Unknown position')
        self.finish_pending()
        self.advance_if_expired()
        if self.row['phase'] != 'encounter':
            raise ValueError('Encounter actions are locked in this phase.')
        if self.row.get('pending_exam_json'):
            raise ValueError('Wait for the examination to finish before repositioning.')
        rules = self.case.get('patient', {}).get('position_rules', {})
        spec = rules.get(position, {})
        rule_position = position
        # The authored orthopnea response explicitly refuses lying flat. Keep
        # that same refusal for face-down positioning rather than demonstrating
        # a newly tolerated flat position. An authored prone rule takes priority.
        # This conservative simulation rule releases only the existing reply.
        flat_rule = rules.get('supine', {})
        if (position == 'prone' and position not in rules
                and flat_rule.get('allowed') is False
                and 'symptom_position_intolerance' in flat_rule.get('fact_ids', [])):
            spec = flat_rule
            rule_position = 'supine'
        accepted = bool(spec.get('allowed', True))
        previous = self.pstate.get('posture', 'seated')
        meta = {'courtesy_id': 'position_help', 'position': position,
                'previous_position': previous, 'accepted': accepted,
                'simulated': True, 'no_finding': True}
        if rule_position != position:
            meta['position_rule'] = 'authored_flat_position_refusal'
            meta['rule_position'] = rule_position
        self.ledger.add(evidence.COURTESY,
                        'Offered assistance positioning the patient ' + position + '.',
                        t_ms=self.elapsed_ms(), meta=meta)
        if accepted:
            self.pstate['posture'] = position
        events = []
        if spec.get('reply'):
            reply, response_meta = patient.PatientEngine(self.case).behavior_response(spec, self.pstate)
            response_meta.update(position=position, position_accepted=accepted)
            if rule_position != position:
                response_meta.update(position_rule='authored_flat_position_refusal',
                                     rule_position=rule_position)
            ev = self.ledger.add(evidence.PATIENT, reply, t_ms=self.elapsed_ms(), meta=response_meta)
            events.append({'kind': 'patient', 'text': reply, 'seq': ev['seq'],
                           't_ms': ev['t_ms'], 'volunteered': True})
        self.save()
        return events

    def _do_exam(self, resolved, text, t):
        if resolved["status"] == "refusable":
            key = resolved["refusable"]
            spec = physexam.REFUSABLE[key]
            if key in self.case.get("refusals", []) or True:
                self.ledger.add(
                    evidence.EXAM_REFUSED,
                    "%s: the patient declines. \"I'd rather not have that done "
                    "today.\"" % spec["label"], t_ms=t,
                    meta={"refusable": key,
                          "proposed_properly": resolved["proposed_properly"],
                          "documented_as": spec["doc"]})
                self.save()
                return {
                    "kind": "refusal", "label": spec["label"],
                    "text": "%s — the patient refuses. Document \"%s\" in "
                            "Objective." % (spec["label"], spec["doc"]),
                    "documented_as": spec["doc"],
                    "proposed_properly": resolved["proposed_properly"],
                }

        if resolved["status"] == "vague":
            self.ledger.add(evidence.EXAM_ACTION, text, t_ms=t,
                            meta={"status": "vague", "reason": resolved["reason"]})
            self.save()
            return {"kind": "sim_note", "text": resolved["reason"]}

        man = resolved["maneuver"]
        return self.perform_maneuver(man["id"], resolved["components"], text)

    def finish_pending(self, cancel=False):
        raw = self.row.get("pending_exam_json")
        if not raw:
            return None
        pending = json.loads(raw)
        deadline = self.row["phase_ends_at"]
        due = pending["due_at"]
        if not cancel and db.now_ms() < due and (not deadline or db.now_ms() < deadline):
            return None
        if due <= db.now_ms() and (not deadline or due <= deadline) and self.row["phase"] == "encounter":
            previous = dict(self.settings.get("scoring", {}))
            self.settings["scoring"] = dict(previous, realtime_exam_durations=False)
            self._completion_elapsed = due - self.row["phase_started_at"]
            before = len(self.ledger.events)
            self.set(pending_exam_json="", exam_busy_until=self._completion_elapsed)
            result = self._perform_immediate(pending["maneuver_id"], pending["components"], pending["source_text"])
            for event in self.ledger.events[before:]:
                event["meta"].update(duration_s=pending["duration_s"], label=physexam.CATALOG_BY_ID[pending["maneuver_id"]]["label"], components=pending["components"], source=pending.get("source", "web"),
                                     request_id=pending.get("request_id", ""))
            self.settings["scoring"] = previous
            del self._completion_elapsed
            self.save()
            return result
        self.ledger.add(evidence.EXAM_ACTION, "Examination interrupted; no findings released.",
                        t_ms=self.elapsed_ms(), meta={"status":"interrupted", "maneuver_id":pending["maneuver_id"],
                        "components":pending["components"], "source":pending.get("source","web"),
                        "request_id":pending.get("request_id", "")})
        self.set(pending_exam_json="", exam_busy_until=self.elapsed_ms())
        self.save()
        return {"kind":"exam_interrupted", "text":"Examination interrupted; no findings released."}

    def perform_maneuver(self, maneuver_id, components, source_text=""):
        if self.settings.get("simulation_runtime") != "interactive":
            return self._perform_immediate(maneuver_id, components, source_text)
        self.finish_pending()
        if self.row["phase"] != "encounter":
            return {"kind":"closed", "text":"The encounter is closed."}
        if self.row.get("pending_exam_json"):
            return {"kind":"exam_busy", "text":"Complete the current examination before starting another."}
        man = physexam.CATALOG_BY_ID.get(maneuver_id)
        if not man:
            return {"kind":"sim_note", "text":"Unknown examination."}
        components = list(dict.fromkeys(c for c in (components or []) if c in man["components"]))
        if maneuver_id == "neuro_dix_hallpike" and "cervical_suitability" not in components:
            return {"kind":"no_result", "text":"Check cervical suitability before positional testing."}
        scale = .15 if self.settings.get("learning_mode") == "guided" else 1.0
        duration = physexam.action_time(man, components, scale)
        now = db.now_ms()
        pending = {"maneuver_id":maneuver_id, "components":components, "source_text":source_text,
                   "started_at":now, "due_at":now + duration*1000, "duration_s":duration}
        context = getattr(self, "bridge_context", None)
        if context:
            pending.update(source=context.get("renderer","unity"), request_id=context["request_id"])
        self.ledger.add(evidence.EXAM_ACTION, source_text or man["label"], t_ms=self.elapsed_ms(),
                        meta={"status":"in_progress", "maneuver_id":maneuver_id, "components":components,
                              "duration_s":duration})
        self.set(pending_exam_json=json.dumps(pending), exam_busy_until=self.elapsed_ms()+duration*1000)
        self.save()
        return {"kind":"exam_started", "label":man["label"], "text":"Examination in progress. Findings will appear when it finishes.",
                "duration_s":duration, "due_at":pending["due_at"]}

    def _perform_immediate(self, maneuver_id, components, source_text=""):
        """Carry out one examination, under a single authoritative lifecycle.

        requested -> (consented) -> in progress -> completed | interrupted

        An examination occupies its configured duration. Nothing is released
        until it completes, a second examination cannot start while one is
        running, and an examination that would run past the encounter deadline
        is recorded as interrupted with no findings. Every entry point --
        buttons, typed narration, voice, a reload, a direct call -- comes
        through here, so the rules cannot be walked around.
        """
        man = physexam.CATALOG_BY_ID.get(maneuver_id)
        if not man:
            return {"kind": "sim_note", "text": "Unknown examination."}
        components = [c for c in (components or []) if c in man["components"]]
        t = self.elapsed_ms()
        scoring = self.settings.get("scoring", config.SCORING_DEFAULTS)
        scale = float(scoring.get("exam_time_scale", 1.0))
        realtime = bool(scoring.get("realtime_exam_durations", True))
        duration = physexam.action_time(man, components, scale) if realtime else 0

        # Serialization comes from the clock: elapsed_ms() never runs behind
        # the examination in progress, so the next action starts after this one
        # finishes. The explicit guard below only catches a genuinely
        # concurrent call (two tabs racing the same session).
        busy_until = self.row["exam_busy_until"] or 0
        if realtime and busy_until > t:
            remaining = int(round((busy_until - t) / 1000.0))
            return {
                "kind": "exam_busy", "label": man["label"],
                "text": ("An examination is already in progress with about %d "
                         "second%s left. Examinations cannot overlap."
                         % (remaining, "" if remaining == 1 else "s")),
                "busy_for_s": remaining,
            }

        completed_at = t + duration * 1000

        # --- interrupted: the encounter ends before this examination does ---
        limit = None if self.is_untimed_phase("encounter") else self.preset["encounter_s"] * 1000
        if realtime and limit is not None and completed_at > limit:
            self.ledger.add(
                evidence.EXAM_ACTION, source_text or man["label"], t_ms=t,
                meta={"status": "interrupted", "maneuver_id": maneuver_id,
                      "label": man["label"], "method": man["method"],
                      "region": man["region"], "components": list(components),
                      "duration_s": duration,
                      "reason": "The encounter ended before this examination "
                                "could be completed."})
            self.set(exam_busy_until=limit)
            self.save()
            return {
                "kind": "exam_interrupted", "label": man["label"],
                "text": ("%s was started with %d seconds left and needs about "
                         "%d. It was interrupted, so it released no findings."
                         % (man["label"], max(0, (limit - t) // 1000), duration)),
                "duration_s": duration,
            }

        # --- what this case actually authors for this maneuver -------------
        findings = self.case.get("exam_findings", {}).get(maneuver_id, [])
        if not findings:
            # No authored content. Say so; do not invent a normal result and do
            # not record an examination finding, because a finding is evidence
            # and there is nothing to be evidence of.
            self.ledger.add(
                evidence.EXAM_ACTION, source_text or man["label"],
                t_ms=completed_at,
                meta={"status": "not_simulated", "maneuver_id": maneuver_id,
                      "label": man["label"], "method": man["method"],
                      "region": man["region"], "components": list(components),
                      "duration_s": duration})
            self.set(exam_busy_until=completed_at)
            self.save()
            return {
                "kind": "not_simulated", "label": man["label"],
                "text": ("%s is not available in this simulation: this case "
                         "does not author a result for it. Nothing was "
                         "recorded, and no credit was given."
                         % man["label"]),
                "duration_s": duration, "components": list(components),
            }

        released, texts, concepts, scopes = [], [], {}, []
        partial_notes, withheld = [], []
        for f in findings:
            covered = f.get("covered_by_components") or []
            if covered and all(c in components for c in covered):
                continue  # Its complete aggregate supplies these same findings once.
            need = f.get("requires_components") or []
            missing = [c for c in need if c not in components]
            if missing:
                withheld.append((f, missing))
                # Only explicitly released findings belong in the evidence ledger.
                continue
            released.append(f["id"])
            texts.append(f["text"])
            concepts.update(f.get("concepts") or {})
            scopes += f.get("scopes", [])

        self.ledger.add(
            evidence.EXAM_ACTION, source_text or man["label"], t_ms=completed_at,
            meta={"status": "completed", "maneuver_id": maneuver_id,
                  "label": man["label"], "method": man["method"],
                  "region": man["region"], "components": list(components),
                  "scopes": scopes, "duration_s": duration,
                  "withheld": [f["id"] for f, _ in withheld]})

        body = " ".join(texts) if texts else ""
        if not body:
            # Authored content exists, but none of it was unlocked by what was
            # actually done. NO finding is recorded: a finding is evidence, and
            # there is nothing here to be evidence of. The explanation goes back
            # to the learner instead -- and deliberately not into the ledger,
            # because naming the parts that were skipped ("rebound", "guarding")
            # inside an evidence sentence would let a note claiming exactly
            # those findings match against it.
            need = sorted({c for _, miss in withheld for c in miss})
            self.set(exam_busy_until=completed_at)
            self.save()
            return {
                "kind": "no_result", "label": man["label"],
                "text": ("%s released no result: the parts of it that carry a "
                         "finding were not performed, so nothing may be "
                         "documented from it." % man["label"]),
                # The names of what was skipped travel as data, not prose. Put
                # "rebound" or "guarding" into a sentence and a note claiming
                # exactly those findings can match against it.
                "missing_components": need if self.settings.get("learning_mode") in ("guided","coached") else [],
                "duration_s": duration, "components": list(components),
                "released": [], "completes_at_ms": completed_at,
                "assisted_timing": not realtime,
            }

        self.ledger.add(
            evidence.EXAM_FINDING, body, t_ms=completed_at,
            meta={"maneuver_id": maneuver_id, "finding_ids": released,
                  "concepts": concepts, "scopes": scopes})

        self.set(exam_busy_until=completed_at)
        self.save()
        return {
            "kind": "finding", "label": man["label"], "text": body,
            "duration_s": duration, "components": list(components),
            "released": released, "completes_at_ms": completed_at,
            "assisted_timing": not realtime,
        }

    # -- note -------------------------------------------------------------
    def save_note(self, payload):
        """Persist the working draft, or refuse honestly.

        A save is eligible only while the note phase is genuinely open. A
        pending autosave that fires after the deadline -- or after submission,
        when the editor has already gone -- used to be accepted and could
        overwrite the frozen note with whatever the disappearing editor last
        held, including nothing. It is now rejected, and the caller is told so
        rather than being shown "Saved."
        """
        now = db.now_ms()
        if not db.save_note_if_open(self.id, json.dumps(payload), now):
            return False
        # Keep this handle consistent with what the database now holds.
        self.row["note_json"] = json.dumps(payload)
        return True

    def note_draft(self):
        return json.loads(self.row["note_json"] or "{}")

    def original_note(self):
        """The note as submitted. Revisions and regrades never touch it."""
        frozen = self.row["original_note_json"]
        if frozen:
            return json.loads(frozen)
        return json.loads(self.row["note_json"] or "{}")

    def save_scratch(self, text):
        if self.row["phase"] not in ("organize", "note", "encounter"):
            return False
        self.set(scratch=text or "")
        self.save()
        return True

    # -- results ----------------------------------------------------------
    def compute_results(self, note_payload=None, label="timed submission"):
        if label == "timed submission" and self.is_untimed_phase("note"):
            label = "%s untimed submission" % self.settings.get("learning_mode", "practice")
        payload = note_payload if note_payload is not None \
            else self.original_note()
        parsed = note_mod.parse(payload)
        scoring_ledger = audit_mod._delivered_ledger(self.ledger, self.case)
        audit_result = audit_mod.audit_note(parsed, scoring_ledger, self.case)
        rubric = grader.grade(parsed, scoring_ledger, self.case, audit_result,
                              self.settings)
        chk = checklist.score(scoring_ledger, self.case)
        interp = ips.assess(scoring_ledger, self.case,
                            self.row["interaction_mode"])
        fb = feedback.build(parsed, scoring_ledger, self.case, audit_result,
                            rubric, chk, interp, self.settings, self)
        return {
            "label": label,
            "note": payload,
            "rubric": rubric,
            "audit": audit_result,
            "checklist": chk,
            "ips": interp,
            "feedback": fb,
            "assumptions": config.assumption_manifest(self.settings),
            "timing": self.timing_report(),
            "integrity": self.integrity_report(),
            "assisted": bool(self.row["assisted"]),
            "clinical_review": self.clinical_review(),
            "versions": self.versions(),
        }

    def clinical_review(self):
        """What review this case has actually had, stated on the results.

        The documentation used to promise a review status on the results screen
        that nothing in the schema supplied. An automated guideline retrieval is
        not clinician approval, and the two are named separately here.
        """
        rev = dict(self.case.get("clinical_review") or {})
        if not rev:
            rev = {
                "status": "not_reviewed",
                "label": "Not reviewed",
                "reviewer": "No review has been performed.",
                "sources": [],
                "limits": "This case's clinical content has not been checked "
                          "against any guideline or by any clinician.",
            }
        rev["clinician_approved"] = False
        rev["disclaimer"] = (
            "No licensed clinician has reviewed or approved any case in this "
            "app. Guideline retrieval is not clinical validation, and nothing "
            "here creates a course scoring rule.")
        return rev

    def versions(self):
        """What this attempt ran under, and what it is being read under.

        A score is only interpretable against the content that produced it. An
        attempt recorded before versions were stamped reports its own versions
        as UNKNOWN rather than borrowing today's, because claiming they match is
        the one answer that is certainly wrong.
        """
        now = version_mod.stamp()
        recorded = {
            "app": self.row["app_version"] or None,
            "engine": self.row["engine_version"] or None,
            "rubric": self.row["rubric_version"] or None,
            "case": self.row["case_version"] or None,
            "schema": self.row["schema_version"] or None,
        }
        current = {
            "app": now["app"], "engine": now["engine"], "rubric": now["rubric"],
            "case": version_mod.case_version(self.case),
            "schema": version_mod.SCHEMA_VERSION,
        }
        unknown = recorded["engine"] is None
        differs = (not unknown) and any(
            recorded[k] is not None and recorded[k] != current[k]
            for k in ("app", "engine", "rubric", "case"))
        if unknown:
            notice = ("This attempt was recorded before the app stamped versions "
                      "onto attempts. What it was graded under originally is not "
                      "known, so its score cannot be compared with a score from "
                      "this version.")
        elif differs:
            notice = ("This attempt was recorded under different content or "
                      "grading than the version now running. Its original result "
                      "stands; anything recomputed here is a regrade under "
                      "%s, not the score it was given." % version_mod.banner())
        else:
            notice = ""
        return {
            "case_id": self.case["id"],
            "recorded": recorded,
            "current": current,
            "recorded_unknown": unknown,
            "differs_from_current": differs,
            "is_regrade": unknown or differs,
            "notice": notice,
        }

    def timing_report(self):
        used = self.row["encounter_used_ms"] or 0
        return {
            "preset": self.preset["label"],
            "preset_key": self.preset["key"],
            "modified": self.preset["modified"],
            "modification_note": self.preset["modification_note"],
            "untimed": self.is_untimed_phase("encounter"),
            "encounter_allowed_s": None if self.is_untimed_phase("encounter") else self.preset["encounter_s"],
            "encounter_used_s": round(used / 1000),
            "organize_s": self.preset["organize_s"],
            "note_allowed_s": None if self.is_untimed_phase("note") else self.preset["note_s"],
            "submit_reason": self.row["submit_reason"],
            "carry_over": False,
            "carry_over_note": config.SCORING_DEFAULTS["carry_over_note"],
            "exam_timing": self.exam_timing_policy(),
        }

    def exam_timing_policy(self):
        """One time policy, stated plainly, and never charged twice.

        An examination occupies its configured duration out of the encounter
        clock. Shortening those durations is a legitimate way to practise, but
        it is a DIFFERENT condition from the timed station and a score under it
        is not comparable, so it is named here rather than left implicit.
        """
        scoring = self.settings.get("scoring", config.SCORING_DEFAULTS)
        realtime = bool(scoring.get("realtime_exam_durations", True))
        scale = float(scoring.get("exam_time_scale", 1.0))
        if not realtime:
            return {
                "condition": "assisted practice",
                "realtime": False,
                "scale": 0.0,
                "note": "Examinations took no encounter time in this attempt. "
                        "This is an assisted practice condition; the timed "
                        "station charges every examination its full duration, "
                        "so this score is not comparable with one from a timed "
                        "attempt.",
            }
        if abs(scale - 1.0) > 1e-9:
            return {
                "condition": "assisted practice",
                "realtime": True,
                "scale": scale,
                "note": "Examination durations were scaled to %g of their "
                        "configured length. This is an assisted practice "
                        "condition, not the timed station." % scale,
            }
        if self.is_untimed_phase("encounter"):
            return {
                "condition": "untimed practice", "realtime": True, "scale": 1.0,
                "note": "Each specific examination still takes its full configured duration and must finish before findings appear. The encounter itself has no deadline.",
            }
        return {
            "condition": "timed station",
            "realtime": True,
            "scale": 1.0,
            "note": "Each examination occupied its full configured duration out "
                    "of the encounter clock, counted once.",
        }

    def integrity_report(self):
        events = self.integrity.get("events", [])
        return {
            "events": events,
            "clean": not events,
            "note": ("Interruptions and technical events are listed so a score "
                     "is never compared against another attempt as though the "
                     "conditions were identical."
                     if events else
                     "No interruptions or technical events were recorded."),
        }


# ---------------------------------------------------------------------------

def branch_from(sid, from_seq, label=""):
    """Start a practice branch that resumes an attempt at one recorded moment.

    Section 11 of the review asks for "a retry from a missed moment that creates
    a SEPARATE practice branch". Separate is the point: the parent attempt is
    read and never written, the branch is its own record naming the attempt and
    the sequence number it grew from, and the branch carries only the evidence
    the parent had actually produced by then -- so a fact the learner obtained
    after that moment has to be obtained again.

    The new coached/guided retry keeps the recorded chronology but follows the
    current untimed learning preset. The original attempt's clock, preset,
    evidence, note and score remain unchanged.
    """
    parent = load(sid)
    if not any(e.get('seq') == int(from_seq) for e in parent.ledger.events):
        raise ValueError('Choose an existing encounter event to retry.')
    events = [e for e in parent.ledger.events if e.get("seq", 0) <= int(from_seq)]
    if not events:
        raise ValueError("nothing recorded at or before sequence %s" % from_seq)
    if events[-1].get('phase','encounter') != 'encounter':
        raise ValueError('Choose a moment within the patient encounter to retry.')
    # A derived attempt keeps the actual transcript and chronology, while
    # removing historical disclosure metadata unsupported by that speech.
    # The parent's ledger, submitted note and stored result are never edited.
    events = audit_mod._delivered_ledger(evidence.Ledger(events), parent.case).events

    # Rebuild what the patient had already said, so she does not repeat herself
    # as though the conversation had not happened.
    released, asked = [], {}
    fact_definitions = {f['id']:f for f in parent.case.get('facts',[])}
    for ev in events:
        for fid in ((ev.get("meta") or {}).get("facts_released") or []):
            # A new retry must not treat a richer historical opening bundle
            # as something already said. Keep the original event and parent
            # immutable; rebuild conversational memory from verified speech.
            fact = fact_definitions.get(fid,{})
            if fid not in patient.delivered_fact_metadata(fact,ev.get('text','')).get('facts_released',[]):
                continue
            if fid not in released:
                released.append(fid)
            asked[fid] = asked.get(fid, 0) + 1
    pstate = {"released": released, "asked_counts": asked, 'posture':'seated'}
    for ev in events:
        if ev['kind']==evidence.PATIENT:
            pstate['last_reply']=ev['text']
            if ev.get('meta',{}).get('kind') in ('opening','answer'):
                pstate['opened']=True
        elif ev['kind']==evidence.STUDENT:
            pstate['last_question']=ev['text']
        elif ev['kind']==evidence.COURTESY and ev.get('meta',{}).get('accepted'):
            pstate['posture']=ev['meta'].get('position',pstate['posture'])

    at_ms = events[-1].get("t_ms", 0)
    # This is a new learning attempt, never a retiming of the parent. New
    # coached/guided retries use their current untimed mode contract.
    mode = 'guided' if parent.settings.get('learning_mode') == 'guided' else 'coached'
    branch_settings = dict(parent.settings, learning_mode=mode,
                           preset=config.preset_for_learning_mode(mode))
    branch_settings['scoring'] = dict(parent.settings.get('scoring',{}),
        realtime_exam_durations=True, exam_time_scale=.15 if mode=='guided' else 1.0)
    remaining = 0  # The new preset is untimed; the branch keeps elapsed history.
    timing_text = ('Guided retry is untimed.' if mode=='guided' else
                   'Coached retry is untimed. The original attempt retains its timing and score.')

    marker = dict(events[-1])
    branch_ledger = events + [{
        "seq": marker.get("seq", 0) + 1,
        "t_ms": at_ms,
        "phase": "encounter",
        "kind": evidence.SYSTEM,
        "text": "Practice branch: this encounter resumes an earlier attempt at "
                "%d:%02d. %s It is a separate record and does not change the attempt it grew from."
                % (at_ms // 60000, (at_ms // 1000) % 60, timing_text),
        "meta": {"branch": True, "parent_session_id": sid,
                 "from_seq": int(from_seq)},
    }]

    new_sid = db.create_branch(
        parent.row, json.dumps(branch_ledger), pstate, branch_settings,
        parent.case, from_seq,
        label or ("Retry from %d:%02d" % (at_ms // 60000, (at_ms // 1000) % 60)),
        remaining, elapsed_ms=at_ms)
    return load(new_sid)


def load(sid):
    row = db.get_session(sid)
    if not row:
        return None
    s = Session(row)
    s.finish_pending()
    s.advance_if_expired()
    return s


def state_payload(s):
    remaining = s.remaining_ms()
    row = s.row
    payload = {
        "id": s.id,
        "phase": row["phase"],
        "case_id": row["case_id"],
        "preset": s.preset,
        "interaction_mode": row["interaction_mode"],
        "learning_mode": s.settings.get("learning_mode", "coached" if row["assisted"] else "independent"),
        "variant_id": s.case.get("variant_id", "base"),
        "patient_posture": s.pstate.get("posture", "seated"),
        "patient_name": s.case["patient"]["name"],
        "appearance": presentation.appearance(s.case),
        "visual_demo": "humgen-trial" if s.settings.get("visual_demo") == "humgen-trial"
                       and s.case["id"] == "renal-colicky-flank"
                       and presentation.appearance(s.case)["presentation"] == "male" else None,
        "affect": presentation.affect(s.case, s.ledger),
        "gesture": presentation.gesture(s.case, s.ledger),
        "demeanor": presentation.demeanor(s.case, s.ledger),
        "ai_patient_enabled": bool(s.settings.get("ai_patient_enabled")),
        # UI activity only: never expose withheld fact IDs or create new evidence.
        "examination_activity": [
            {"seq": ev["seq"], "kind": ev["kind"], "text": "", "meta": {
                key: ev.get("meta", {}).get(key) for key in
                ("status", "maneuver_id", "label", "components", "duration_s")}}
            for ev in s.ledger.events if ev["kind"] == evidence.EXAM_ACTION
        ],
        "pending_exam": json.loads(row.get("pending_exam_json") or "null"),
        "exam_busy_until": row["exam_busy_until"],
        "assisted": bool(row["assisted"]),
        "remaining_ms": remaining,
        "phase_duration_s": s.phase_duration_s(),
        "server_now": db.now_ms(),
        "phase_ends_at": row["phase_ends_at"],
        "phase_started_at": row["phase_started_at"],
        "elapsed_ms": s.elapsed_ms(),
        "note": json.loads(row["note_json"] or "{}"),
        "scratch": row["scratch"] or "",
        "submit_reason": row["submit_reason"],
        "encounter_used_ms": row["encounter_used_ms"],
        "integrity": s.integrity_report(),
        "branch": {
            "is_branch": bool(row["parent_session_id"]),
            "parent_session_id": row["parent_session_id"] or None,
            "from_seq": row["branch_from_seq"] or None,
            "label": row["branch_label"] or None,
        },
    }
    if row["phase"] == "briefing":
        payload["station"] = {
            "doorway": s.case["station"]["doorway"],
            "vitals": dict(s.case["station"]["vitals"]),
            "vitals_source": "Supplied doorway information",
            "hidden_label": s.case.get("hidden_label", "Station"),
        }
    if row["phase"] in ("encounter", "organize", "note", "submitted"):
        payload["station_chart"] = {
            "vitals": s.case["station"]["vitals"],
            "supplied_results": [
                {"label": r["label"], "value": r["value"]}
                for r in s.case["station"].get("supplied_results", [])],
            "doorway": s.case["station"]["doorway"],
        }
    if row["phase"] == "encounter":
        payload["exam_catalog"] = physexam.catalog_for_ui()
        payload["transcript"] = [
            {"seq": e["seq"], "kind": e["kind"], "text": e["text"], "t_ms": e["t_ms"],
             "time": "%d:%02d" % (e["t_ms"] // 60000, (e["t_ms"] // 1000) % 60),
             "meta": {k: v for k, v in e["meta"].items()
                      if k in ("volunteered", "uncertain", "label", "documented_as",
                               "no_information", "maneuver_id", "components", "source", "request_id")}}
            for e in s.ledger.events
            if e["kind"] in (evidence.STUDENT, evidence.PATIENT,
                             evidence.EXAM_FINDING, evidence.EXAM_REFUSED,
                             evidence.SIM, evidence.STATION_INFO)
        ]
    if row["phase"] in ("note", "submitted") and bool(row["assisted"]):
        payload["assisted_transcript"] = s.ledger.transcript()
    return payload
