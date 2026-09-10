"""Multi-turn continuity: the patient remembers what it just said.

The failure this exists to prevent: the patient asks the clinician a question,
the clinician answers it, and the patient treats that answer as an
unrecognized medical question.

These are CONVERSATION tests, not single-message intent tests. Each case drives
a real sequence through one PatientEngine and asserts on both the visible reply
and the resulting state. Meaning is asserted, never one exact sentence.

    python3 tools/test_conversation_continuity.py [--verbose]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pcmcse import cases, dialogue, nlp, patient  # noqa: E402

VERBOSE = "--verbose" in sys.argv
FAILURES = []
CHECKS = [0]

FALLBACKS = ("could you say that another way", "not sure what you mean",
             "don't know how to answer", "what do you mean exactly",
             "do not have an answer", "nothing to tell you about that")


def check(group, cond, detail):
    CHECKS[0] += 1
    if not cond:
        FAILURES.append((group, detail))
    return bool(cond)


class Conversation:
    """One encounter, driven turn by turn."""

    def __init__(self, case_id, variant="base"):
        self.case = cases.resolve(case_id, variant)
        self.engine = patient.PatientEngine(self.case)
        self.state = {}
        self.turns = []

    def say(self, text):
        reply, meta = self.engine.respond(text, self.state)
        self.turns.append((text, reply or "", meta))
        return reply or "", meta

    @property
    def pending(self):
        return self.state.get("pending_question")

    def transcript(self):
        return "\n".join(f"    Dr: {t}\n    Pt: {r}" for t, r, _ in self.turns)


def is_fallback(reply):
    low = nlp.normalize(reply)
    return not reply.strip() or any(f in low for f in FALLBACKS)


def concern_cases(limit=None):
    """Cases whose concern is phrased as a question to the clinician."""
    out = []
    for cid, case in sorted(cases.all_cases().items()):
        fact = next((f for f in case["facts"] if f["id"] == "patient_concern"), None)
        if not fact:
            continue
        line = (fact.get("sp_says") or [fact.get("value", "")])[0]
        if dialogue.is_question_to_clinician(line):
            out.append((cid, line))
    return out[:limit] if limit else out


CONCERN_ASK = "What worries you most about these symptoms?"


# ==========================================================================
# A. The exact screenshot, across every case that asks such a question
# ==========================================================================
def test_a_screenshot():
    group = "A:answers-patient-question"
    targets = concern_cases()
    check(group, len(targets) >= 10, f"only {len(targets)} cases ask the clinician a question")
    for cid, line in targets:
        c = Conversation(cid)
        first, _ = c.say(CONCERN_ASK)
        if not dialogue.is_question_to_clinician(first):
            continue  # this case answered with something else; not this test
        reply, meta = c.say("no")
        check(group, not is_fallback(reply),
              f"{cid}: 'no' after the patient's own question fell back: {reply!r}\n{c.transcript()}")
        check(group, meta.get("kind") == "concern_acknowledged",
              f"{cid}: expected concern_acknowledged, got {meta.get('kind')!r}")
        check(group, not meta.get("facts_released"),
              f"{cid}: reassurance released clinical facts {meta.get('facts_released')}")
        check(group, c.pending and c.pending.get("open") is False,
              f"{cid}: question not marked resolved")


# ==========================================================================
# B. Paraphrases - meaning, not exact strings
# ==========================================================================
def test_b_paraphrases():
    group = "B:paraphrased-answers"
    phrasings = ["no", "Nope", "Of course not", "Not at all", "No, I'm here to help",
                 "I'm not here to judge", "No judgement at all", "Absolutely not"]
    for cid, _ in concern_cases(6):
        for phrase in phrasings:
            c = Conversation(cid)
            first, _ = c.say(CONCERN_ASK)
            if not dialogue.is_question_to_clinician(first):
                continue
            reply, meta = c.say(phrase)
            check(group, not is_fallback(reply),
                  f"{cid}: {phrase!r} fell back: {reply!r}")
            check(group, not meta.get("facts_released"),
                  f"{cid}: {phrase!r} released facts {meta.get('facts_released')}")


# ==========================================================================
# C. Answer + a new clinical question in one turn
# ==========================================================================
def test_c_answer_plus_question():
    group = "C:answer-plus-question"
    for cid, _ in concern_cases(8):
        case = cases.resolve(cid, "base")
        alcohol = [f for f in case["facts"]
                   if patient.PatientEngine(case)._fact_subjects(f) == {"alcohol"}]
        if not alcohol:
            continue
        lines = [nlp.normalize(l) for f in alcohol
                 for l in (f.get("sp_says") or [f.get("value", "")]) if l]
        c = Conversation(cid)
        first, _ = c.say(CONCERN_ASK)
        if not dialogue.is_question_to_clinician(first):
            continue
        reply, meta = c.say("No, I'm not judging you. How much do you drink?")
        low = nlp.normalize(reply)
        check(group, any(l in low for l in lines),
              f"{cid}: compound turn did not answer the alcohol question: {reply!r}")
        check(group, not is_fallback(reply), f"{cid}: compound fell back: {reply!r}")


# ==========================================================================
# D. Opposite polarity is not silently read as reassurance
# ==========================================================================
def test_d_polarity():
    group = "D:polarity"
    for cid, _ in concern_cases(6):
        c = Conversation(cid)
        first, _ = c.say(CONCERN_ASK)
        if not dialogue.is_question_to_clinician(first):
            continue
        reply, meta = c.say("yes")
        check(group, not meta.get("facts_released"),
              f"{cid}: an affirmative answer released facts {meta.get('facts_released')}")
        pending = c.pending or {}
        frame = pending.get("frame")
        # The polarity flip only applies where "yes" confirms the bad outcome.
        # For a PERMISSION question ("could I just go home?") an affirmative
        # genuinely does reassure, and for an unclassifiable framing the honest
        # result is None - acknowledge without claiming to have reassured.
        if frame == "worry":
            check(group, pending.get("reassuring") is False,
                  f"{cid}: 'yes' confirming a worry was recorded as reassuring")
        else:
            check(group, pending.get("reassuring") is not None or frame == "other",
                  f"{cid}: {frame!r} question left an unclassified outcome")
        check(group, len(reply) < 120,
              f"{cid}: disproportionate reaction to a blunt answer: {reply!r}")


# ==========================================================================
# F. No valid antecedent - do not invent one
# ==========================================================================
def test_f_no_antecedent():
    group = "F:no-antecedent"
    for cid, _ in concern_cases(8):
        c = Conversation(cid)
        reply, meta = c.say("no")
        check(group, not meta.get("facts_released"),
              f"{cid}: bare 'no' released facts {meta.get('facts_released')}")
        check(group, meta.get("kind") != "concern_acknowledged",
              f"{cid}: bare 'no' invented a preceding patient question")
        check(group, c.pending is None,
              f"{cid}: bare 'no' created a pending question")


# ==========================================================================
# G/H. Topic change supersedes; a later short reply does not rebind
# ==========================================================================
def test_g_topic_change():
    group = "G:topic-change"
    for cid, _ in concern_cases(8):
        c = Conversation(cid)
        first, _ = c.say(CONCERN_ASK)
        if not dialogue.is_question_to_clinician(first):
            continue
        onset, ometa = c.say("When did the pain start?")
        check(group, ometa.get("kind") != "concern_acknowledged",
              f"{cid}: the open question hijacked an unrelated clinical turn")
        # After the clinician moved on, a later "no" must not rebind.
        reply, meta = c.say("no")
        check(group, meta.get("kind") != "concern_acknowledged",
              f"{cid}: a later 'no' rebound to an already-superseded question")
        check(group, not meta.get("facts_released"),
              f"{cid}: later 'no' released facts {meta.get('facts_released')}")


def test_h_resolved_once():
    group = "H:resolved-once"
    for cid, _ in concern_cases(8):
        c = Conversation(cid)
        first, _ = c.say(CONCERN_ASK)
        if not dialogue.is_question_to_clinician(first):
            continue
        c.say("no")
        again, meta = c.say("no")
        check(group, meta.get("kind") != "concern_acknowledged",
              f"{cid}: the same question was answered twice")
        check(group, not meta.get("facts_released"),
              f"{cid}: second 'no' released facts {meta.get('facts_released')}")


# ==========================================================================
# I. Pronouns and short follow-ups still resolve
# ==========================================================================
def test_i_followups():
    group = "I:short-followups"
    pairs = [("Do you drink alcohol?", "How much?", "alcohol"),
             ("Do you smoke?", "How long?", "tobacco"),
             ("Where is the pain?", "Does it spread anywhere?", None)]
    for cid, _ in concern_cases(8):
        case = cases.resolve(cid, "base")
        engine = patient.PatientEngine(case)
        for first, second, subject in pairs:
            if subject:
                facts = [f for f in case["facts"] if engine._fact_subjects(f) == {subject}]
                if not facts:
                    continue
                lines = [nlp.normalize(l) for f in facts
                         for l in (f.get("sp_says") or [f.get("value", "")]) if l]
            c = Conversation(cid)
            c.say(first)
            reply, _ = c.say(second)
            check(group, not is_fallback(reply),
                  f"{cid}: {first!r} then {second!r} fell back: {reply!r}")
            if subject:
                check(group, any(l in nlp.normalize(reply) for l in lines),
                      f"{cid}: {second!r} answered off-subject: {reply!r}")


# ==========================================================================
# J. Fact integrity - the clinician cannot rewrite the case
# ==========================================================================
def test_j_fact_integrity():
    group = "J:fact-integrity"
    assertions = ["So you don't take any medications?",
                  "You don't drink, correct?",
                  "You have no allergies then."]
    for cid, _ in concern_cases(8):
        case = cases.resolve(cid, "base")
        for text in assertions:
            c = Conversation(cid)
            before = [f["id"] for f in case["facts"]]
            reply, meta = c.say(text)
            after = [f["id"] for f in c.case["facts"]]
            check(group, before == after, f"{cid}: case facts mutated by {text!r}")
            # Whatever it answers, it may only speak authored content.
            for fid in meta.get("facts_released") or []:
                fact = next(f for f in case["facts"] if f["id"] == fid)
                lines = [nlp.normalize(l) for l in
                         (fact.get("sp_says") or [fact.get("value", "")]) if l]
                check(group, any(l in nlp.normalize(reply) for l in lines),
                      f"{cid}: released {fid} without speaking its authored text")


# ==========================================================================
# K. Encounter lifecycle - no bleed between encounters
# ==========================================================================
def test_k_lifecycle():
    group = "K:lifecycle"
    targets = concern_cases(4)
    for cid, _ in targets:
        first = Conversation(cid)
        opening, _ = first.say(CONCERN_ASK)
        if not dialogue.is_question_to_clinician(opening):
            continue
        check(group, first.pending and first.pending.get("open"),
              f"{cid}: no pending question recorded")
        # A NEW encounter starts with clean state.
        second = Conversation(cid)
        reply, meta = second.say("no")
        check(group, meta.get("kind") != "concern_acknowledged",
              f"{cid}: pending question leaked into a fresh encounter")
        check(group, second.pending is None,
              f"{cid}: fresh encounter began with a pending question")


# ==========================================================================
# L. Input parity - the same text behaves the same however it arrived
# ==========================================================================
def test_l_input_parity():
    group = "L:input-parity"
    for cid, _ in concern_cases(5):
        base = Conversation(cid)
        opening, _ = base.say(CONCERN_ASK)
        if not dialogue.is_question_to_clinician(opening):
            continue
        typed, tmeta = base.say("no")
        # Speech and suggested-phrase input reach the same engine entry point;
        # the difference is only capitalization/punctuation from a recognizer.
        for variant in ["No.", "no ", "NO"]:
            c = Conversation(cid)
            c.say(CONCERN_ASK)
            reply, meta = c.say(variant)
            check(group, meta.get("kind") == tmeta.get("kind"),
                  f"{cid}: {variant!r} handled differently from typed 'no' "
                  f"({meta.get('kind')} vs {tmeta.get('kind')})")


# ==========================================================================
# Longer conversation - continuity must not decay
# ==========================================================================
def test_long_conversation():
    group = "long-conversation"
    for cid, _ in concern_cases(4):
        c = Conversation(cid)
        script = [
            "Hello, I'm a student doctor.",
            "What brings you in today?",
            "When did this start?",
            "How bad is it?",
            CONCERN_ASK,
            "no",
            "Do you drink alcohol?",
            "How much?",
            "Any medical problems or surgeries?",
            "Tell me more.",
            "Thank you for telling me.",
            "Is there anything else you're worried about?",
        ]
        for text in script:
            reply, meta = c.say(text)
            check(group, isinstance(reply, str) and reply.strip(),
                  f"{cid}: empty reply to {text!r}")
        fallbacks = sum(1 for _, r, _ in c.turns if is_fallback(r))
        check(group, fallbacks <= 2,
              f"{cid}: {fallbacks} of {len(script)} turns fell back over a long "
              f"conversation\n{c.transcript()}")



# ==========================================================================
# M. Clinician STATEMENTS are not history questions
# ==========================================================================
# The failure: "I'm going to wash my hands before we start." was answered with
# a symptom history, because "start" and "before" are trigger words on the
# onset and past-episode facts. A turn that narrates the clinician's own action
# must never be routed into the clinical matcher.
BEDSIDE_STATEMENTS = [
    "Hello, my name is Sebastian, I'm a student doctor and I'll be seeing you today.",
    'Can you confirm your name for me, and how would you like to be addressed?',
    "I'm going to wash my hands before we start.",
    'Is it okay if I examine you now?',
    "I'm going to put on gloves before I examine you.",
    "I'm going to drape you so you stay covered.",
    'Let me help you with your gown.',
    'Let me help you lie back on the table.',
    'Are you comfortable? Let me know if anything I do hurts.',
    "This might be cold \u2014 let me warm my hands first.",
]


def test_m_statements_are_not_questions():
    group = "M:statements-not-questions"
    for cid in sorted(cases.all_cases()):
        case = cases.resolve(cid, "base")
        # A case may AUTHOR a comfort reply that deliberately discloses a fact;
        # that is reviewed content, not a keyword accident.
        allowed = set((case["patient"].get("comfort_response") or {}).get("fact_ids") or [])
        for text in BEDSIDE_STATEMENTS:
            c = Conversation(cid)
            reply, meta = c.say(text)
            got = set(meta.get("facts_released") or [])
            authored = got and got <= allowed and meta.get("kind") == "behavior"
            check(group, not got or authored,
                  f"{cid}: bedside statement {text[:44]!r} released clinical history "
                  f"{sorted(got)} -> {reply[:80]!r}")
            check(group, bool(reply.strip()),
                  f"{cid}: bedside statement {text[:44]!r} got no reply at all")


def test_m_questions_still_answered():
    """The guard must not swallow real questions."""
    group = "M:questions-still-work"
    probes = [('When did the pain start?', 'onset'),
              ('Where is the pain?', 'location'),
              ('Do you have any allergies?', 'allergies')]
    for cid in sorted(cases.all_cases()):
        case = cases.resolve(cid, "base")
        for question, category in probes:
            facts = [f for f in case["facts"] if f.get("category") == category]
            if not facts:
                continue
            lines = [nlp.normalize(l) for f in facts
                     for l in (f.get("sp_says") or [f.get("value", "")]) if l]
            c = Conversation(cid)
            reply, _ = c.say(question)
            check(group, any(l in nlp.normalize(reply) for l in lines),
                  f"{cid}: {question!r} stopped being answered: {reply[:80]!r}")

def main():
    groups = [test_a_screenshot, test_b_paraphrases, test_c_answer_plus_question,
              test_d_polarity, test_f_no_antecedent, test_g_topic_change,
              test_h_resolved_once, test_i_followups, test_j_fact_integrity,
              test_k_lifecycle, test_l_input_parity, test_long_conversation,
              test_m_statements_are_not_questions, test_m_questions_still_answered]
    for g in groups:
        before = len(FAILURES)
        g()
        print("  %-34s %s" % (g.__name__, "ok" if len(FAILURES) == before
                              else "%d FAILED" % (len(FAILURES) - before)))
    print()
    if not FAILURES:
        print("PASS %d checks — patient questions tracked and resolved once, short "
              "answers read in context, clinical facts never rewritten by conversation."
              % CHECKS[0])
        return 0
    by = {}
    for grp, detail in FAILURES:
        by.setdefault(grp, []).append(detail)
    print("FAIL %d of %d checks" % (len(FAILURES), CHECKS[0]))
    for grp, details in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print("  %-28s %d" % (grp, len(details)))
        for d in details[: (None if VERBOSE else 2)]:
            print("      " + d[:400])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
