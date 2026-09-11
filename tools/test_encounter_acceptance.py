"""Acceptance for the encounter experience: the behaviours this pass changed.

Each check is a thing a student does, with the failure written as what they
would have suffered. Run against the real engine and the real session, never a
stub, and always on a disposable database.

    python3 tools/test_encounter_acceptance.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pcmcse import db  # noqa: E402
db.DB_PATH = os.environ.get("PCM_CSE_DB") or os.path.join(
    tempfile.mkdtemp(prefix="pcmcse-accept-"), "a.db")

from pcmcse import cases, config, engine, evidence, guide, record  # noqa: E402
from pcmcse.patient import PatientEngine  # noqa: E402

db.init()
FAILURES, CHECKS = [], [0]


def check(cond, detail):
    CHECKS[0] += 1
    if not cond:
        FAILURES.append(detail)
    return bool(cond)


class Talk:
    """One patient, one conversation, state carried across turns."""

    def __init__(self, case_id, variant="base"):
        self.case = cases.resolve(case_id, variant)
        self.engine = PatientEngine(self.case)
        self.state = {"opened": True, "open_budget": 1}
        self.by_id = {f["id"]: f for f in self.case.get("facts") or []}

    def say(self, text):
        reply, meta = self.engine.respond(text, self.state)
        rows = {self.by_id[f].get("category") for f in (meta.get("facts_released") or [])
                if f in self.by_id}
        return reply, rows, (meta.get("facts_released") or [])


def session(case_id, mode, preset):
    case = cases.get(case_id)
    sid = db.create_session(case["id"], preset, "type", mode == "guided",
                            dict(config.load_settings(), learning_mode=mode),
                            case=case)
    s = engine.load(sid)
    s.start_encounter()
    s.settings["learning_mode"] = mode
    return s


# --------------------------------------------------------------------------
# Conversation
# --------------------------------------------------------------------------

def test_a_second_symptom_keeps_its_own_timeline():
    """The worst failure: a confidently wrong acuity, stated as a confirmation."""
    talk = Talk("gi-epigastric-melena")
    talk.say("What brings you in today?")
    talk.say("Have you noticed any change in your bowel movements?")
    reply, _rows, _ids = talk.say("How long has the black stool been going on?")
    check("two days" in reply.lower(),
          "the black stool began two days ago, but the patient answered %r -- "
          "the stomach pain's timeline, which the student would write into the "
          "note as the bleeding's duration" % reply[:80])
    reply, _rows, _ids = talk.say("And how long has the stomach pain been going on?")
    check("six weeks" in reply.lower() or "6 weeks" in reply.lower(),
          "the pain's own timeline was lost too: %r" % reply[:80])


def test_a_lead_in_does_not_produce_a_confused_tail():
    for opener in ["Thanks for telling me all that. ",
                   "I hear you. That must be exhausting. ",
                   "Before you go, "]:
        talk = Talk("gi-epigastric-back-pain")
        reply, _rows, ids = talk.say(opener + "What makes it worse?")
        check(ids, "%r reached no fact at all" % (opener + "What makes it worse?"))
        check("what do you mean" not in reply.lower()
              and "don't know how to answer" not in reply.lower()
              and "do not have an answer" not in reply.lower(),
              "a correct answer had a confusion line stapled to it after the "
              "lead-in %r: %r" % (opener.strip(), reply[:110]))


def test_a_correction_is_resolved_not_restarted():
    talk = Talk("neuro-recurrent-headache")
    talk.say("How long has this been going on?")
    reply, rows, _ids = talk.say("No, I meant how long each headache lasts.")
    check("timing" in rows or "12" in reply,
          "a plain correction was not resolved; the patient said %r" % reply[:80])
    talk2 = Talk("neuro-recurrent-headache")
    talk2.say("Have you ever been diagnosed with anything before?")
    reply, _rows, ids = talk2.say("I am asking about your mother, not you.")
    check(any(talk2.by_id[f].get("category") == "family" for f in ids if f in talk2.by_id),
          "'not you' did not move the answer to the mother: %r" % reply[:80])


def test_a_follow_up_about_the_symptom_is_not_answered_from_a_detour():
    talk = Talk("neuro-recurrent-headache")
    talk.say("Whereabouts in your head do you feel it?")
    talk.say("Are you on any medicines?")
    reply, rows, _ids = talk.say("How bad is it?")
    check("severity" in rows,
          "after a detour to medications, 'how bad is it?' was answered from "
          "%s -- the student writes the drug dose as the pain score. Got %r"
          % (sorted(rows) or "nothing", reply[:70]))


def test_a_bare_follow_up_still_continues_the_topic():
    """The other half: the anchor must not be thrown away."""
    talk = Talk("neuro-recurrent-headache")
    talk.say("Do you smoke?")
    _reply, rows, _ids = talk.say("How long?")
    check("social" in rows,
          "'How long?' after a smoking question left the topic and answered "
          "from %s" % (sorted(rows) or "nothing"))


# --------------------------------------------------------------------------
# Record
# --------------------------------------------------------------------------

def test_record_reads_as_notes_not_as_dialogue():
    talk = Talk("cardio-chest-pressure")
    events, seq = [], 0
    for question in ["What brings you in today?", "When did this start?",
                     "Where exactly do you feel it?", "How bad does it get?",
                     "Do you smoke?"]:
        seq += 1
        events.append({"seq": seq, "kind": evidence.STUDENT, "text": question,
                       "meta": {}, "t_ms": 0})
        reply, _rows, _ids = talk.say(question)
        seq += 1
        events.append({"seq": seq, "kind": evidence.PATIENT, "text": reply,
                       "meta": talk.engine.respond and {}, "t_ms": 0})
    # Rebuild with real meta so the authorisation gate is exercised properly.
    talk = Talk("cardio-chest-pressure")
    events, seq = [], 0
    for question in ["What brings you in today?", "When did this start?",
                     "Where exactly do you feel it?", "How bad does it get?",
                     "Do you smoke?"]:
        seq += 1
        events.append({"seq": seq, "kind": evidence.STUDENT, "text": question,
                       "meta": {}, "t_ms": 0})
        reply, meta = talk.engine.respond(question, talk.state)
        seq += 1
        events.append({"seq": seq, "kind": evidence.PATIENT, "text": reply,
                       "meta": meta, "t_ms": 0})
    summary = record.summarize(talk.case, events)
    rows = [item for g in summary["groups"] for s in g["sections"]
            for item in s["items"]]
    check(rows, "the Record was empty after five answered questions")
    for item in rows:
        check(not item["text"].lower().startswith(("i have been ", "i've been ",
                                                   "yeah, ", "well, ")),
              "a Record row still opens like dialogue: %r" % item["text"][:70])
        if item["text_full"]:
            check(item["text_full"] in "".join(e["text"] for e in events),
                  "the row's 'Said:' wording is not something the patient said: "
                  "%r" % item["text_full"][:70])


def test_condensation_never_loses_the_side_or_the_denial():
    for value, must_keep in [
            ("My stomach started hurting around the middle, but now the pain is low on the right.", "right"),
            ("I breathe more comfortably sitting upright.", "upright"),
            ("I have never had this before.", "never"),
            ("There is no clear trigger.", "no"),
            ("Maybe a six out of ten when it is bad.", "maybe")]:
        short = record.condense(value)
        check(must_keep.lower() in short.lower(),
              "condensing %r lost %r: %r" % (value[:50], must_keep, short))


# --------------------------------------------------------------------------
# Coach
# --------------------------------------------------------------------------

def test_the_coach_moves_forward_through_the_encounter():
    s = session("cardio-chest-pressure", "coached", "coached_untimed")
    seen = []
    seen.append((guide.next_action(s) or {}).get("title"))
    s.student_turn("Hello, my name is Sam, I'm a student doctor. I'll wash my hands.")
    s.student_turn("Can you confirm your name for me?")
    seen.append((guide.next_action(s) or {}).get("title"))
    s.student_turn("What brings you in today?")
    for question in ["When did this start?", "Where is it?", "Does it spread?",
                     "What does it feel like?", "How bad is it?",
                     "Is it constant?", "What makes it worse?",
                     "What makes it better?", "Have you had this before?",
                     "Any other symptoms?", "What medical problems do you have?",
                     "What medicines do you take?", "Any allergies?",
                     "Any surgeries?", "Does anything run in your family?",
                     "Do you smoke or drink?", "What worries you most?"]:
        s.student_turn(question)
    seen.append((guide.next_action(s) or {}).get("title"))
    check(seen[0] and "ntroduce" in seen[0],
          "the coach did not open with the introduction; it said %r" % seen[0])
    check(len(set(x for x in seen if x)) == len(seen),
          "the coach repeated itself instead of progressing: %s" % seen)


def test_the_coach_is_silent_in_unassisted_modes():
    for mode, preset in [("independent", "independent_extended"),
                         ("rehearsal", "course")]:
        s = session("cardio-chest-pressure", mode, preset)
        check(guide.next_action(s) is None,
              "%s practice was given a coaching move" % mode)


# --------------------------------------------------------------------------
# Writing the note
# --------------------------------------------------------------------------

def test_what_you_can_consult_while_writing_matches_the_mode():
    expected = {"guided": True, "coached": True,
                "independent": False, "rehearsal": False}
    presets = {"guided": "guided_untimed", "coached": "coached_untimed",
               "independent": "independent_extended", "rehearsal": "course"}
    for mode, should_have in expected.items():
        s = session("renal-dysuria", mode, presets[mode])
        s.student_turn("What brings you in today?")
        s.end_encounter_now()
        if s.row["phase"] == "organize":
            s.skip_organize()
        payload = engine.state_payload(engine.load(s.id))
        has = "record" in payload
        check(has == should_have,
              "%s practice %s the Record while writing the note"
              % (mode, "lost" if should_have else "was given"))


def test_the_biggest_loss_leads_the_debrief():
    s = session("renal-dysuria", "rehearsal", "course")
    for question in ["Hello, I'm a student doctor.", "What brings you in today?",
                     "When did this start?", "Any fever?"]:
        s.student_turn(question)
    s.end_encounter_now()
    if s.row["phase"] == "organize":
        s.skip_organize()
    s.save_note({"S": "cc: burning with urination\nHPI: 29 yo f with 2 days of burning.",
                 "O": "", "A": ["1. Cystitis"], "P": ["1. Urine culture"]})
    s.submit()
    results = engine.load(s.id).compute_results()
    top = (results["feedback"].get("priority_errors") or [])[:3]
    check(top, "the debrief produced nothing to work on")
    if top:
        check(top[0].get("points", 0) >= 6,
              "the debrief still leads with a %d-point item (%r) while whole "
              "sections scored nothing"
              % (top[0].get("points", 0), top[0].get("title", "")[:60]))


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            before = len(FAILURES)
            try:
                fn()
            except Exception as exc:                      # noqa: BLE001
                FAILURES.append("%s raised %s: %s" % (name, type(exc).__name__, exc))
            print("  %-58s %s" % (name, "ok" if len(FAILURES) == before else "FAIL"))
    print()
    for failure in FAILURES[:15]:
        print("  FAIL %s" % failure)
    if FAILURES:
        print("\n%d checks, %d failures" % (CHECKS[0], len(FAILURES)))
        return 1
    print("PASS %d checks — a second symptom keeps its own timeline, a lead-in "
          "does not confuse the patient, a correction is resolved, Record reads "
          "as notes without losing a side or a denial, the coach moves forward "
          "and stays silent when unassisted, and the debrief leads with the "
          "largest loss." % CHECKS[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
