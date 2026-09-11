"""The specific understanding failures this pass set out to fix, plus the
negatives that stop each fix from becoming a new over-disclosure.

Held-out generalisation is measured elsewhere (test_question_generalization).
THIS file is the opposite: it pins the exact wordings that were reported as
broken, so they cannot silently break again -- and, beside each one, the
near-identical wording in a different context that must NOT resolve the same
way. A fix that only makes the positives pass is not a fix.

    python3 tools/test_phrasing_acceptance.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pcmcse import cases, dialogue  # noqa: E402
from pcmcse.patient import PatientEngine  # noqa: E402

FAILURES, CHECKS = [], [0]


def check(cond, detail):
    CHECKS[0] += 1
    if not cond:
        FAILURES.append(detail)
    return bool(cond)


def ask(case_id, question, state=None):
    case = cases.resolve(case_id, "base")
    engine = PatientEngine(case)
    reply, meta = engine.respond(question, state if state is not None
                                 else {"opened": True, "open_budget": 0})
    by_id = {f["id"]: f for f in case.get("facts", [])}
    rows = {by_id[f].get("category") for f in (meta.get("facts_released") or [])
            if f in by_id}
    return reply, rows, (meta.get("facts_released") or [])


# --------------------------------------------------------------------------
# The reported failures.
# --------------------------------------------------------------------------

RESOLVES = [
    ("cardio-chest-pressure", "How intense would you call it?", "severity"),
    ("cardio-chest-pressure", "How far back does this go?", "onset"),
    ("gi-epigastric-melena", "How far back does this go?", "onset"),
    ("cardio-chest-pressure", "What sort of sensation is it?", "quality"),
    ("neuro-distal-neuropathy", "What sort of sensation is it?", "quality"),
    ("cardio-chest-pressure", "Does it ever let up completely?", "timing"),
]


def test_the_reported_phrasings_reach_the_right_row():
    for case_id, question, expected in RESOLVES:
        _reply, rows, released = ask(case_id, question)
        check(expected in rows,
              "%s: %r reached %s, not the %s row (facts: %s)"
              % (case_id, question, sorted(rows) or "nothing", expected, released))


# --------------------------------------------------------------------------
# The same words, a different subject. None of these may reach the symptom row.
# --------------------------------------------------------------------------

CONTEXT_NEGATIVES = [
    ("cardio-chest-pressure", "How intense is your exercise routine?", "severity",
     "asks about exercise intensity, not pain severity"),
    ("cardio-chest-pressure", "How intense is your work schedule?", "severity",
     "asks about work, not the symptom"),
    ("renal-flank-pain", "What sort of work do you do?", "quality",
     "'what sort of' about a job is not a question about symptom quality"),
]


def test_the_same_words_about_something_else_do_not_reach_the_symptom():
    for case_id, question, forbidden, why in CONTEXT_NEGATIVES:
        _reply, rows, released = ask(case_id, question)
        check(forbidden not in rows,
              "%s: %r reached the %s row, but it %s (facts: %s)"
              % (case_id, question, forbidden, why, released))


# --------------------------------------------------------------------------
# An ordinary English word must never be "repaired" into a clinical term.
# --------------------------------------------------------------------------

ORDINARY_WORDS = [
    "more", "hear", "wake", "change", "sort", "night", "far", "let", "through",
    "now", "will", "call", "ever", "back", "week", "deep", "walk", "listen",
    "heart", "rest", "move", "sore", "short", "fall", "all", "talk", "keep",
]


def test_ordinary_words_are_never_rewritten_into_clinical_terms():
    for case_id in sorted(cases.all_cases()):
        vocabulary = PatientEngine(cases.resolve(case_id, "base"))._question_vocabulary()
        for word in ORDINARY_WORDS:
            repaired = dialogue.repair_typos(word, vocabulary)
            check(repaired == word,
                  "%s: the ordinary word %r was rewritten to %r, so an "
                  "everyday question silently became a different one"
                  % (case_id, word, repaired))


def test_real_typos_are_still_repaired():
    """The guard must not have turned the repair off."""
    vocabulary = PatientEngine(cases.resolve("cardio-chest-pressure", "base"))._question_vocabulary()
    for typo, expected in [("wher", "where"), ("teh", "the"),
                           ("sevre", "severe"), ("symtoms", "symptoms"),
                           ("discomfrt", "discomfort")]:
        check(dialogue.repair_typos(typo, vocabulary) == expected,
              "the typo %r is no longer repaired to %r" % (typo, expected))


# --------------------------------------------------------------------------
# Understanding is separate from disclosure. The course's own checklist keeps
# Setting, Pertinent Positive and Contact apart; so must the app.
# --------------------------------------------------------------------------

ACTIVITY = "What were you doing when this started?"
ILLNESS = "Did you have any infection before this began?"
EXPOSURE = "Have you been around anyone who was unwell?"

# case -> the phrase that must appear ONLY for the matching question
SPECIFIC = [
    ("renal-painless-hematuria", ILLNESS, "sore throat"),
    ("cardio-febrile-cough", EXPOSURE, "coworker"),
    ("gi-diarrhea-dehydration", EXPOSURE, "household"),
    ("cardio-pleuritic-dyspnea", EXPOSURE, "flight"),
]


def test_the_matching_question_earns_the_fact():
    for case_id, question, phrase in SPECIFIC:
        reply, _rows, released = ask(case_id, question)
        check(phrase in reply.lower() and released,
              "%s: %r did not disclose the fact containing %r (got %r)"
              % (case_id, question, phrase, reply[:70]))


def test_a_generic_activity_question_does_not_hand_over_an_exposure():
    """The diagnostic link has to be asked for."""
    for case_id, _question, phrase in SPECIFIC:
        reply, _rows, _released = ask(case_id, ACTIVITY)
        check(phrase not in reply.lower(),
              "%s: %r handed over %r, which the course's checklist files under "
              "Pertinent Positive or Contact, not Setting"
              % (case_id, ACTIVITY, phrase))


def test_an_unauthored_dimension_says_so_instead_of_answering_another_row():
    """Being told 'this has never happened before' when you asked about a
    preceding infection is a false negative a student would write down."""
    for case_id in ["renal-flank-pain", "cardio-chest-pressure",
                    "neuro-thunderclap-headache", "gi-right-upper-pain"]:
        reply, rows, released = ask(case_id, ILLNESS)
        check(not released,
              "%s: %r was answered from the %s row with %r instead of saying "
              "the case does not carry it"
              % (case_id, ILLNESS, sorted(rows), reply[:60]))


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            before = len(FAILURES)
            fn()
            print("  %-62s %s" % (name, "ok" if len(FAILURES) == before else "FAIL"))
    print()
    for f in FAILURES[:15]:
        print("  FAIL %s" % f)
    if FAILURES:
        print("\n%d checks, %d failures" % (CHECKS[0], len(FAILURES)))
        return 1
    print("PASS %d checks — the reported phrasings resolve, the same words about "
          "something else do not, ordinary English is never rewritten, and a "
          "specific question earns its fact while a generic one does not."
          % CHECKS[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
