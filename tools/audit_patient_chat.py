"""Adversarial sweep of the patient conversation.

Not a pass/fail suite -- a probe. It types a large set of realistic student
phrasings at every case and reports the turns that came back as a fallback,
a non-answer or an off-topic answer, so real coverage gaps surface instead of
hiding behind an average.

    python3 tools/audit_patient_chat.py            # summary
    python3 tools/audit_patient_chat.py --show     # every unresolved turn
    python3 tools/audit_patient_chat.py --case ID  # one case
"""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pcmcse import cases, nlp, patient  # noqa: E402

SHOW = "--show" in sys.argv
ONE = None
if "--case" in sys.argv:
    ONE = sys.argv[sys.argv.index("--case") + 1]

# Realistic student typing: shorthand, missing punctuation, run-ons, typos.
PROBES = [
    # identity and opening
    "hi im a student doctor whats your name",
    "whats ur name and why r u here", "name and age please",
    "can i get your name and date of birth", "how old are you",
    "what do you do for work", "who do you live with", "are you married",
    # chief complaint, many wordings
    "what brings you in", "why are you here", "whats going on",
    "what can i help you with today", "what seems to be the problem",
    "tell me what happened", "what made you come in", "what are you here for",
    "so what's been bothering you", "whats the reason for your visit",
    # HPI shorthand
    "when did it start", "how long has this been going on", "when did this begin",
    "where exactly", "where is it", "point to where it hurts",
    "how bad", "how bad is it", "rate it out of 10", "how severe",
    "what does it feel like", "describe the pain", "is it sharp or dull",
    "does it spread", "does it move anywhere", "does it radiate",
    "anything make it worse", "what makes it worse", "does anything bring it on",
    "anything make it better", "what helps", "does anything relieve it",
    "how often does it happen", "is it constant or does it come and go",
    "has it gotten worse", "has it changed", "ever happened before",
    "have you had this before", "did you take anything for it",
    "anything else going on", "any other symptoms",
    # compound
    "whats your name and what brings you in today",
    "when did it start and how bad is it",
    "when did this start, how bad is it, and does anything make it better",
    "where is it and does it spread",
    "any medical problems, surgeries, medications, or allergies",
    "do you smoke or drink, and do you use any recreational drugs",
    "meds allergies surgeries", "any smoking drinking drugs",
    "pmh psh meds allergies", "name age occupation",
    "tell me about the pain. where is it and how bad is it",
    "what medical problems do you have and what medications do you take",
    # PMH / meds / allergies / family / social
    "any medical problems", "do you have any medical conditions",
    "any chronic illnesses", "ever been in the hospital",
    "any surgeries", "have you had any operations",
    "what medications do you take", "are you on any meds",
    "do you take anything over the counter", "any allergies",
    "are you allergic to anything", "any drug allergies",
    "what about your family", "any family history",
    "mom or dad have anything like this", "does anything run in the family",
    "do you smoke", "how much do you smoke", "do you drink",
    "how much do you drink", "any recreational drugs", "do you use drugs",
    "do you exercise", "hows your diet", "have you travelled recently",
    # ROS-ish
    "any fever", "any chills", "any nausea", "any vomiting",
    "any weight loss", "any night sweats", "shortness of breath",
    "any chest pain", "any dizziness", "any headaches",
    "any numbness or tingling", "any trouble urinating", "any blood in your stool",
    # conversational
    "tell me more", "can you explain that", "what do you mean", "go on",
    "anything else", "sorry what was that", "could you repeat that",
    "im sorry to hear that", "that sounds difficult",
    # awkward / typo / punctuation
    "wher is teh pain", "HOW BAD IS IT", "how bad is it???",
    "when. did. it. start", "u smoke?", "any hx of surgery",
    "fhx?", "shx?", "when did the pain start!!!",
]

# A follow-up probe is a two-turn exchange: the anchor, then the bare ask.
FOLLOWUPS = [
    ("do you smoke", "how long"), ("do you smoke", "how much"),
    ("do you drink", "how much"), ("do you drink", "how often"),
    ("what medications do you take", "how often"),
    ("any allergies", "what happens"),
    ("where is the pain", "does it spread"),
    ("where is the pain", "how bad is it"),
    ("when did it start", "has it changed"),
    ("any family history", "what about your mother"),
]

FALLBACK_MARKERS = [
    "could you say that another way", "not sure what you mean",
    "don't know how to answer", "what do you mean exactly",
    "do not have an answer", "do not have information about",
    "nothing to tell you about that",
]


def is_unresolved(reply, meta):
    if not reply.strip():
        return True
    if meta.get("kind") in ("non_answer",):
        return True
    low = nlp.normalize(reply)
    return any(marker in low for marker in FALLBACK_MARKERS)


def main():
    ids = [ONE] if ONE else sorted(cases.all_cases())
    unresolved = collections.Counter()
    examples = collections.defaultdict(list)
    total = 0
    errors = []

    for cid in ids:
        case = cases.resolve(cid, "base")
        for probe in PROBES:
            engine, state = patient.PatientEngine(case), {}
            total += 1
            try:
                reply, meta = engine.respond(probe, state)
            except Exception as exc:  # noqa: BLE001
                errors.append("%s | %r raised %r" % (cid, probe, exc))
                continue
            if is_unresolved(reply or "", meta):
                unresolved[probe] += 1
                if len(examples[probe]) < 2:
                    examples[probe].append("%s -> %s" % (cid, (reply or "")[:90]))
        for anchor, follow in FOLLOWUPS:
            engine, state = patient.PatientEngine(case), {}
            total += 1
            try:
                engine.respond(anchor, state)
                reply, meta = engine.respond(follow, state)
            except Exception as exc:  # noqa: BLE001
                errors.append("%s | %r/%r raised %r" % (cid, anchor, follow, exc))
                continue
            key = "%s -> %s" % (anchor, follow)
            if is_unresolved(reply or "", meta):
                unresolved[key] += 1
                if len(examples[key]) < 2:
                    examples[key].append("%s -> %s" % (cid, (reply or "")[:90]))

    resolved = total - sum(unresolved.values()) - len(errors)
    print("Adversarial sweep: %d turns across %d cases" % (total, len(ids)))
    print("  resolved   : %d (%.1f%%)" % (resolved, 100.0 * resolved / max(1, total)))
    print("  unresolved : %d" % sum(unresolved.values()))
    print("  errors     : %d" % len(errors))
    for line in errors[:10]:
        print("    ERROR " + line)
    if unresolved:
        print("\nProbes unresolved in the most cases:")
        for probe, count in unresolved.most_common(None if SHOW else 25):
            print("  %3d/%-3d  %s" % (count, len(ids), probe))
            if SHOW:
                for sample in examples[probe]:
                    print("           " + sample)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
