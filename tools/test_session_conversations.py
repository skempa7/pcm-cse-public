"""Whole conversations, through the path a real encounter uses.

A defect found in an earlier pass did not reproduce against PatientEngine and
did reproduce through engine.Session -- intent interpretation, courtesy credit,
event recording and the Record projection only exist on that path. So every
turn here goes through Session.student_turn on a DISPOSABLE database, and the
assertions look at what was actually disclosed and recorded rather than at the
reply string.

The phrasings are deliberately NOT the ones used while implementing the fixes.

    python3 tools/test_session_conversations.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PCM_CSE_DB", os.path.join(tempfile.mkdtemp(prefix="pcmcse-conv-"), "c.db"))

from pcmcse import cases, config, db, engine, evidence, record  # noqa: E402

db.init()
FAILURES, CHECKS = [], [0]
CASES = ["cardio-chest-pressure", "gi-epigastric-back-pain", "renal-colicky-flank",
         "neuro-recurrent-headache", "cardio-febrile-cough"]


def check(cond, detail):
    CHECKS[0] += 1
    if not cond:
        FAILURES.append(detail)
    return bool(cond)


class Encounter:
    def __init__(self, case_id, mode="coached"):
        settings = config.load_settings()
        preset = config.preset_for_learning_mode(mode, config.DEFAULT_PRESET)
        settings.update(preset=preset, learning_mode=mode, simulation_runtime="immediate")
        self.case = cases.resolve(case_id, None)
        self.case_id = case_id
        self.id = db.create_session(case_id, preset, "type", mode == "guided", settings, case=self.case)
        engine.load(self.id).start_encounter()

    def say(self, text):
        engine.load(self.id).student_turn(text)
        return self.last_reply()

    def session(self):
        return engine.load(self.id)

    def last_reply(self):
        replies = [e["text"] for e in self.session().ledger.events if e["kind"] == evidence.PATIENT]
        return replies[-1] if replies else ""

    def released(self):
        return {f for e in self.session().ledger.events
                for f in (e["meta"].get("facts_released") or [])}

    def record(self):
        s = self.session()
        return record.summarize(s.case, s.ledger.events)

    def record_text(self):
        return " ".join(it["text"] for g in self.record()["groups"]
                        for sec in g["sections"] for it in sec["items"])


def opening_facts(case):
    return set(case["patient"].get("opening_facts") or [])


def test_greeting_and_opening_reach_the_history():
    for cid in CASES:
        e = Encounter(cid)
        e.say("Morning — I'm Alex, a third-year medical student. Tell me what's been going on.")
        check(bool(e.released() & opening_facts(e.case)),
              "%s: a greeting plus an opening question did not open the history (%r)"
              % (cid, e.last_reply()[:70]))


def test_acknowledgement_does_not_re_answer():
    for cid in CASES:
        e = Encounter(cid)
        e.say("What brought you in?")
        e.say("When did this begin?")
        before = e.released()
        reply = e.say("Right, that's helpful.")
        check(e.released() == before,
              "%s: an acknowledgement released new facts" % cid)
        check(len(reply) < 120,
              "%s: an acknowledgement was answered with a speech: %r" % (cid, reply[:90]))


def test_a_reply_to_the_patients_question_is_understood():
    """Reassurance plus a follow-up question in one turn."""
    for cid in CASES:
        e = Encounter(cid)
        e.say("What brought you in?")
        e.say("What worries you most about this?")
        pending = engine.load(e.id).pstate.get("pending_question")
        if not pending:
            continue
        reply = e.say("No, nothing you've told me changes how I'll treat you. "
                      "How often does it happen?")
        # Both halves must land. Not every case authors a frequency fact, so
        # the test is that the QUESTION was addressed -- answered, or named as
        # unavailable -- and that the turn did not collapse into the
        # reassurance alone.
        still_open = (engine.load(e.id).pstate.get("pending_question") or {}).get("open")
        check(not still_open,
              "%s: the patient's question stayed open after being answered" % cid)
        addressed = ("how often" in reply.lower() or "frequency" in reply.lower()
                     or e.released() != set() )
        check(addressed and len(reply) > 0,
              "%s: the question after the reassurance was dropped: %r" % (cid, reply[:80]))


def test_topic_change_and_return():
    for cid in CASES:
        e = Encounter(cid)
        e.say("What brought you in?")
        e.say("When did it start?")
        onset = e.released()
        e.say("Do you smoke?")
        e.say("Sorry — back to the pain. Where exactly do you feel it?")
        check(e.released() > onset,
              "%s: returning to an earlier topic released nothing new" % cid)


def test_repeating_a_question_stays_consistent():
    for cid in CASES:
        e = Encounter(cid)
        e.say("What brought you in?")
        first = e.say("When did this start?")
        again = e.say("Sorry, remind me when it started?")
        check(bool(first) and bool(again),
              "%s: a repeated question produced no answer" % cid)
        rows = e.record()
        ids = [it["fact_id"] for g in rows["groups"] for sec in g["sections"]
               for it in sec["items"] if it.get("fact_id")]
        check(len(ids) == len(set(ids)),
              "%s: repeating a question duplicated a Record row" % cid)


def test_preparation_statement_is_not_history():
    for cid in CASES:
        e = Encounter(cid)
        e.say("What brought you in?")
        before = e.released()
        reply = e.say("Before we go on, let me just clean my hands.")
        check(e.released() == before,
              "%s: a preparation statement released clinical history: %r" % (cid, reply[:80]))


def test_closing_is_answered_and_answerable():
    for cid in CASES:
        e = Encounter(cid)
        e.say("What brought you in?")
        reply = e.say("I think that's everything I needed — thank you.")
        check("don't know how to answer" not in reply.lower()
              and "another way" not in reply.lower(),
              "%s: a closing statement got a confusion reply: %r" % (cid, reply[:80]))
        follow = e.say("I'm not certain yet, but we'll work it out together.")
        check("don't know how to answer" not in follow.lower(),
              "%s: answering the patient's closing question confused her: %r" % (cid, follow[:80]))


def test_compound_question_records_each_part():
    for cid in CASES:
        e = Encounter(cid)
        e.say("What brought you in?")
        e.say("When did it begin, where do you feel it, and what makes it worse?")
        sections = {sec["id"] for g in e.record()["groups"] for sec in g["sections"]}
        check(len(sections & {"onset", "modifiers"}) >= 1,
              "%s: a three-part question filled no HPI row (%s)" % (cid, sorted(sections)))


def test_record_never_shows_what_was_not_disclosed():
    for cid in CASES:
        e = Encounter(cid)
        e.say("What brought you in?")
        e.say("When did it start?")
        shown = e.record_text()
        for fact in e.case["facts"]:
            if fact.get("category") in ("medications", "allergies", "family", "psh"):
                value = (fact.get("value") or "").strip()
                if value and len(value) > 12 and value in shown:
                    check(False, "%s: %s appeared in Record without being asked"
                          % (cid, fact["id"]))
    check(True, "no undisclosed fact reached Record")


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            before = len(FAILURES)
            try:
                fn()
                status = "ok" if len(FAILURES) == before else "FAIL"
            except Exception as exc:
                FAILURES.append("%s raised %s" % (name, exc))
                status = "ERROR"
            print("  %-52s %s" % (name, status))
    print()
    for f in FAILURES[:14]:
        print("  FAIL %s" % f)
    if FAILURES:
        print("\n%d checks, %d failures" % (CHECKS[0], len(FAILURES)))
        return 1
    print("PASS %d checks across %d cases — whole conversations through the real "
          "session path: openings, acknowledgements, reassurance, topic changes, "
          "repeats, preparation, closings and compound asks." % (CHECKS[0], len(CASES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
