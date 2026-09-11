"""Negative cases for three guarantees nothing else in the suite was testing.

Each check here exists because a deliberate, disposable break of the guarantee
was applied to an isolated copy of the tree and the whole 747-test suite stayed
green. A guarantee no test can see broken is not protected, so these are written
as the break itself: forge the evidence, ask for the credit, and require the
refusal. Every negative is paired with the positive control it differs from, so
a check can never pass merely by refusing everything.

    python3 tools/test_evidence_guarantees.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pcmcse import cases, engine, evidence, grader, record  # noqa: E402

FAILURES, CHECKS = [], [0]


def check(cond, detail):
    CHECKS[0] += 1
    if not cond:
        FAILURES.append(detail)
    return bool(cond)


def _patient_event(text, fact_ids, seq=2):
    return {"seq": seq, "kind": evidence.PATIENT, "text": text,
            "meta": {"facts_released": list(fact_ids)}, "t_ms": 0}


def _listed(summary):
    return {it["fact_id"] for g in summary["groups"]
            for s in g["sections"] for it in s["items"]}


def _documentable_fact(case):
    """A fact Record has a row for, so a refusal is about authorisation only."""
    for fact in case.get("facts") or []:
        if record.SECTIONS and fact.get("category") in record._CATEGORY_SECTION:
            if (fact.get("value") or "").strip():
                return fact
    return None


# --------------------------------------------------------------------------
# Guarantee 1: Record credits a fact only when the APPROVED text was spoken.
# --------------------------------------------------------------------------

def test_record_refuses_a_fact_the_patient_did_not_actually_say():
    """A PATIENT event may CLAIM a fact id; only its wording can authorise it."""
    for cid in sorted(cases.all_cases()):
        case = cases.resolve(cid, "base")
        fact = _documentable_fact(case)
        if not fact:
            continue

        # Positive control: the approved wording is listed. Without this the
        # negative below would pass on a Record that shows nothing at all.
        allowed = _listed(record.summarize(
            case, [_patient_event(fact["value"], [fact["id"]])]))
        check(fact["id"] in allowed,
              "%s: Record dropped %s even though the patient spoke its approved "
              "text -- the negative case below proves nothing" % (cid, fact["id"]))

        # The break: same claim, wording the patient never said.
        forged = _listed(record.summarize(
            case, [_patient_event("We talked about the weather.", [fact["id"]])]))
        check(fact["id"] not in forged,
              "%s: Record credited %s from a reply that never contained it -- a "
              "fact can be documented that was never disclosed" % (cid, fact["id"]))


def test_record_will_not_let_one_answer_carry_another_fact():
    """Real wording for fact A must not authorise a claim on fact B."""
    for cid in sorted(cases.all_cases()):
        case = cases.resolve(cid, "base")
        documentable = [f for f in (case.get("facts") or [])
                        if f.get("category") in record._CATEGORY_SECTION
                        and (f.get("value") or "").strip()]
        if len(documentable) < 2:
            continue
        spoken, borrowed = documentable[0], documentable[1]
        if spoken["value"].strip() == borrowed["value"].strip():
            continue
        listed = _listed(record.summarize(
            case, [_patient_event(spoken["value"], [spoken["id"], borrowed["id"]])]))
        check(borrowed["id"] not in listed,
              "%s: an answer about %s also credited %s, which it never stated"
              % (cid, spoken["id"], borrowed["id"]))


# --------------------------------------------------------------------------
# Guarantee 2: a concept needs EVERY content word of one of its surfaces.
# --------------------------------------------------------------------------

def test_one_shared_word_does_not_name_a_concept():
    """"pain" alone is not "burning with urination"."""
    tried = 0
    for cid in sorted(cases.all_cases()):
        case = cases.resolve(cid, "base")
        for concept, surfaces in (case.get("concept_lexicon") or {}).items():
            for surface in surfaces or []:
                parts = [w for w in grader.nlp.normalize(surface).split()
                         if w not in grader._SURFACE_FILLER]
                if len(parts) < 2:
                    continue
                tried += 1
                # Positive control: the whole surface names the concept.
                check(grader._names_concept(surface, [surface]),
                      "%s/%s: the surface %r no longer names its own concept"
                      % (cid, concept, surface))
                # The break: any single word of it must not be enough.
                for word in parts:
                    check(not grader._names_concept(word, [surface]),
                          "%s/%s: the single word %r was read as %r -- a note "
                          "sharing one word would earn the concept"
                          % (cid, concept, word, surface))
                break
    check(tried > 0, "no multi-word surface was found to test; the check is vacuous")


# --------------------------------------------------------------------------
# Guarantee 3: courtesy credit is for performing it, not mentioning it.
# --------------------------------------------------------------------------

PERFORMED = [
    ("I washed my hands before coming in.", "hand_hygiene"),
    ("My name is Sam and I am a student doctor.", "introduce"),
    ("I will put on gloves now.", "gloves"),
]

# Split deliberately. A question about a courtesy is refused by the
# question check; a STATEMENT about somebody else is refused only by the
# performed-by-the-learner check. Testing just the questions leaves that second
# check invisible -- exactly how it went untested until a disposable break of it
# left the whole suite green.
NOT_PERFORMED_BECAUSE_ASKED = [
    ("Should I wash my hands first?", "hand_hygiene"),
    ("Would you like me to put on gloves?", "gloves"),
    ("Did your student doctor wash his hands?", "hand_hygiene"),
]

NOT_PERFORMED_BECAUSE_SOMEBODY_ELSE = [
    ("Your student doctor already washed my hands.", "hand_hygiene"),
    ("Your student doctor introduced myself to you earlier.", "introduce"),
    ("The nurse will drape you for the examination.", "drape"),
    ("The resident put on gloves before that.", "gloves"),
]

NOT_PERFORMED_BECAUSE_ABSENT = [
    ("I have no hand sanitizer available.", "hand_hygiene"),
]


def test_stating_a_courtesy_earns_it_and_asking_about_it_does_not():
    for text, cid in PERFORMED:
        hits = {h["id"] if isinstance(h, dict) else h for h in engine._courtesy_hits(text)}
        check(cid in hits,
              "performing a courtesy earned nothing: %r did not credit %s -- the "
              "refusals below prove nothing" % (text, cid))
    for group, why in ((NOT_PERFORMED_BECAUSE_ASKED, "a question, not the act"),
                       (NOT_PERFORMED_BECAUSE_SOMEBODY_ELSE, "somebody else doing it"),
                       (NOT_PERFORMED_BECAUSE_ABSENT, "an absence of it")):
        for text, cid in group:
            hits = {h["id"] if isinstance(h, dict) else h for h in engine._courtesy_hits(text)}
            check(cid not in hits, "%r earned %s, but it is %s" % (text, cid, why))


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            before = len(FAILURES)
            fn()
            print("  %-58s %s" % (name, "ok" if len(FAILURES) == before else "FAIL"))
    print()
    for f in FAILURES[:12]:
        print("  FAIL %s" % f)
    if FAILURES:
        print("\n%d checks, %d failures" % (CHECKS[0], len(FAILURES)))
        return 1
    print("PASS %d checks — Record refuses a fact the patient never said or that "
          "another answer tried to carry, one shared word never names a concept, "
          "and a courtesy is credited only when it was performed." % CHECKS[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
