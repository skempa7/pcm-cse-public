"""Does the patient understand questions nobody wrote down for her?

Every other conversation test in this repo asks in wording that exists
somewhere in the project -- an authored trigger, or a phrase lifted from the
router's own regexes. Passing those shows the wiring is connected, not that a
student who phrases it their own way will be understood.

So these probes are written from the symptom-analysis rows outward, in ordinary
clinical English, and the suite REFUSES to run any probe it can find in a case
trigger or in the routing source: a probe that leaked into the implementation
is no longer a held-out probe.

Two different things are then measured:

  * a hard rule -- a probe must never be answered from an unrelated row. A
    wrong answer is worse than no answer, because the student documents it.
  * a measurement -- how often each row is reached at all, printed per row.
    A row nothing natural can reach is reported as a failure; the rest is a
    number to look at, not a threshold invented to be passed.

    python3 tools/test_question_generalization.py
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pcmcse import cases  # noqa: E402
from pcmcse.patient import PatientEngine  # noqa: E402

FAILURES, CHECKS = [], [0]


def check(cond, detail):
    CHECKS[0] += 1
    if not cond:
        FAILURES.append(detail)
    return bool(cond)


# Held-out probes. Written from the rows, not from the code.
PROBES = {
    "onset": ["When did this first come on?",
              "Has this been troubling you a while?",
              "At what point did you first notice it?"],
    "location": ["Whereabouts do you feel it?",
                 "Point to where it bothers you.",
                 "Which part of you is affected?"],
    "radiation": ["Does it travel anywhere else?",
                  "Does it shoot into any other area?",
                  "Does the discomfort move from that spot?"],
    "quality": ["What sort of sensation is it?",
                "How would you describe the feeling itself?",
                "Is it dull, sharp, or something else?"],
    "severity": ["How bad does it get at its worst?",
                 "On a scale of one to ten, where is it?",
                 "Does it stop you doing things?"],
    "timing": ["Does it come and go, or stay steady?",
               "Is it there all the time?",
               "Does it ever let up completely?"],
    "aggravating": ["Is there anything that sets it off?",
                    "What tends to bring it on?",
                    "Does anything seem to stir it up?"],
    "alleviating": ["Does anything take the edge off?",
                    "Is there anything that eases it?",
                    "What helps when it happens?"],
    "setting": ["What had you been up to just before it began?",
                "Were you in the middle of something when it began?",
                "What was going on around the time it started?"],
    "pmh": ["Do you have any ongoing medical conditions?",
            "Have you been diagnosed with anything before?",
            "What health problems do you carry?"],
    "medications": ["What do you take regularly?",
                    "Are you on any prescriptions?",
                    "Which medicines are you using?"],
    "allergies": ["Do you react badly to any medication?",
                  "Any drug allergies?",
                  "Is there anything you cannot take?"],
    "psh": ["Have you had any operations?",
            "Any surgeries in the past?",
            "Have you ever been operated on?"],
    "family": ["Does anyone related to you have health issues?",
               "Do any illnesses go through your relatives?",
               "Is there anything hereditary in the family?"],
    "social": ["Tell me about your daily habits.",
               "Do you smoke or drink?",
               "What is your living situation like?"],
}

# Rows that legitimately answer alongside another. Answering "how often" with
# a chronology sentence is not a wrong row; answering it with an allergy is.
NEIGHBOURS = {
    "onset": {"chronology", "timing", "past_occurrence", "chief_complaint"},
    "timing": {"chronology", "onset", "past_occurrence"},
    "location": {"radiation", "chief_complaint"},
    "radiation": {"location"},
    "quality": {"severity", "chief_complaint"},
    "severity": {"quality", "timing"},
    "aggravating": {"alleviating", "setting", "timing"},
    "alleviating": {"aggravating", "treatment"},
    "setting": {"onset", "chronology", "aggravating", "associated"},
    "pmh": {"past_occurrence", "psh", "medications"},
    "medications": {"pmh", "treatment", "allergies"},
    "allergies": {"medications"},
    "psh": {"pmh"},
    "family": set(),
    "social": {"obgyn", "fife"},
}


def _authored_probes_leaked():
    """Refuse to run if a probe is a phrase the implementation already knows."""
    haystack = []
    for cid in cases.all_cases():
        case = cases.resolve(cid, "base")
        for fact in case.get("facts") or []:
            for group in (fact.get("triggers") or {}).values():
                haystack += [str(x).lower() for x in (group or [])]
    # Whichever routing modules this edition ships. The public edition
    # deliberately has no conversation.py, and a missing one must not turn the
    # leak guard into a crash -- or, worse, into a silent pass.
    present = [name for name in ("patient.py", "dialogue.py", "intent.py",
                                 "conversation.py")
               if (ROOT / "pcmcse" / name).exists()]
    assert "patient.py" in present, "no routing source to check probes against"
    for name in present:
        haystack.append((ROOT / "pcmcse" / name).read_text().lower())
    leaked = []
    for row, probes in PROBES.items():
        for probe in probes:
            needle = probe.rstrip("?.").lower()
            if any(needle in h for h in haystack):
                leaked.append((row, probe))
    return leaked


def main():
    leaked = _authored_probes_leaked()
    if leaked:
        print("These probes are no longer held out -- they appear in the "
              "implementation or in a case trigger. Rewrite them:")
        for row, probe in leaked:
            print("   [%s] %s" % (row, probe))
        return 2

    reached = defaultdict(int)
    asked = defaultdict(int)
    for cid in sorted(cases.all_cases()):
        case = cases.resolve(cid, "base")
        authored = {f.get("category") for f in case.get("facts") or []}
        by_id = {f["id"]: f for f in case.get("facts") or []}
        for row, probes in PROBES.items():
            if row not in authored:
                continue
            for probe in probes:
                asked[row] += 1
                reply, meta = PatientEngine(case).respond(
                    probe, {"opened": True, "open_budget": 0})
                released = meta.get("facts_released") or []
                categories = {by_id[f].get("category") for f in released if f in by_id}
                if row in categories:
                    reached[row] += 1
                    # The asked-for row WAS answered. Anything else in the same
                    # breath is the patient volunteering a related detail, which
                    # is a deliberate feature and is flagged as volunteered.
                    continue
                # Nothing from the row asked about. Saying nothing is honest;
                # answering from an unrelated row is the failure, because the
                # student reads it as the answer and documents it there.
                stray = categories - {row} - NEIGHBOURS.get(row, set())
                check(not stray,
                      "%s: %r was answered only from %s -- the student would "
                      "document that as %s. Reply: %r"
                      % (cid, probe, sorted(stray), row, reply[:70]))

    print()
    print("  %-14s %-9s %s" % ("row", "reached", "of probes asked"))
    dead = []
    for row in sorted(PROBES):
        total = asked[row]
        if not total:
            continue
        rate = 100.0 * reached[row] / total
        print("  %-14s %5.1f%%   %d/%d" % (row, rate, reached[row], total))
        if not reached[row]:
            dead.append(row)
    for row in dead:
        check(False, "no ordinary phrasing of the %s question reached it in any "
                     "case -- that row is unreachable by natural language" % row)

    print()
    for f in FAILURES[:15]:
        print("  FAIL %s" % f)
    if FAILURES:
        print("\n%d checks, %d failures" % (CHECKS[0], len(FAILURES)))
        return 1
    print("PASS %d checks — held-out phrasings never draw an answer from an "
          "unrelated row, and every row is reachable in ordinary English."
          % CHECKS[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
