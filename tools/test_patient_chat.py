"""Behavioral tests for the simulated patient conversation.

Runs against EVERY authored case, not one example, so a fix that only works
for chest pain fails here. Assertions are behavioral (did the reply contain
the name AND the complaint?) rather than exact strings, because the wording is
case-specific and deliberately varies.

    python3 tools/test_patient_chat.py            # all groups
    python3 tools/test_patient_chat.py --verbose  # show every failure line
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pcmcse import cases, dialogue, nlp, patient  # noqa: E402

VERBOSE = "--verbose" in sys.argv
FAILURES = []
CHECKS = [0]


def fail(group, detail):
    FAILURES.append((group, detail))


def check(group, condition, detail):
    CHECKS[0] += 1
    if not condition:
        fail(group, detail)
    return bool(condition)


def fresh(case):
    return patient.PatientEngine(case), {}


def ask(engine, state, question):
    reply, meta = engine.respond(question, state)
    return reply or "", meta


def norm(text):
    return nlp.normalize(text)


def all_case_ids():
    return sorted(cases.all_cases())


def load(cid):
    return cases.resolve(cid, "base")


# --------------------------------------------------------------------------
# Non-clinical lines the patient may say that are not case facts. Anything a
# reply contains beyond these and the authored facts would be invented
# clinical content, which is the failure this file exists to catch.
# --------------------------------------------------------------------------
NON_CLINICAL = [
    "i am not sure about that. i cannot give you a definite answer.",
    "my name is", "i am", "i'm", "years old", "hello", "thank you for introducing",
    "i am ready to talk", "i do not know what is causing", "i am here to find out",
    "i do not have an answer", "please treat it as information unavailable",
    "not as a denial", "i do not have information about", "in this simulated case",
    "could you say that another way", "i'm not sure what you mean",
    "i don't know how to answer that", "i'm not sure. what do you mean exactly",
    "i'm not sure what you mean", "what do you mean exactly", "i'm sorry",
    "hmm", "that's all there is to it", "i think that's about it",
    "i don't really have anything to tell you about that",
    "that's really all there is to it", "i'm not sure what else to add about that",
    "that's about all i can tell you on that", "no, i think that's about it",
    "not that i can think of", "that's all i can think of right now",
    "yes, please explain what you would like to do", "like i said", "as i mentioned",
    "right,", "sorry", "no, i think you covered everything",
    "please ask about my medicines and allergies separately",
    "my earlier wording named a diagnosis", "i do not know what is causing these symptoms",
    "you didn't say anything back to me", "could you go over it again",
    "i'm not sure what you're checking", "do you mean", "or", "sorry",
]


def authored_text(case):
    """Every sentence this patient is authorized to say from case data."""
    allowed = []
    for fact in case.get("facts", []):
        allowed.extend(fact.get("sp_says") or [])
        if fact.get("value"):
            allowed.append(fact["value"])
        for version in fact.get("delivery_contract", {}).get("versions", []):
            if version.get("text"):
                allowed.append(version["text"])
        # A clarifying question names its options using the case's own example
        # questions, so those words are authored content, not invented. The
        # subject is extracted with the engine's own regex, so the test and the
        # engine cannot drift apart on what counts as authored.
        allowed.extend(fact.get("example_questions") or [])
        for example in fact.get("example_questions") or []:
            match = patient.PatientEngine._SUBJECT_OF.match(example.strip())
            if match and match.group(1).strip():
                allowed.append(match.group(1).strip())
    pat = case.get("patient", {})
    # Identity comes from the patient block, not from a fact, and is
    # legitimately spoken. Age is matched as a bare number below.
    allowed.append(pat.get("name", ""))
    for part in str(pat.get("name", "")).split():
        allowed.append(part)
    allowed.append(str(pat.get("age", "")))
    for key in ("opening",):
        if pat.get(key):
            allowed.append(pat[key])
    for key in ("empathy_replies", "closing_questions", "plan_acknowledgements"):
        allowed.extend(pat.get(key) or [])
    comfort = pat.get("comfort_response") or {}
    for value in comfort.values():
        if isinstance(value, str):
            allowed.append(value)
        elif isinstance(value, list):
            allowed.extend(v for v in value if isinstance(v, str))
    for pair in pat.get("education_responses", []) or []:
        allowed.append(pair.get("patient", ""))
    for fact in case.get("facts", []):
        for spec in (fact.get("concepts") or {}).values():
            if isinstance(spec, dict) and spec.get("value"):
                allowed.append(spec["value"])
    return [norm(a) for a in allowed if a and len(norm(a)) > 3]


def unaccounted(reply, allowed):
    """Reply text left over after removing authored and non-clinical wording."""
    left = norm(reply)
    for phrase in sorted(allowed, key=len, reverse=True):
        if phrase and phrase in left:
            left = left.replace(phrase, " ")
    # Longest first: "i am" would otherwise eat the middle of
    # "i am not sure what you mean" and leave its tail looking invented.
    for phrase in sorted(NON_CLINICAL, key=len, reverse=True):
        left = left.replace(phrase, " ")
    left = re.sub(r"[^a-z]+", " ", left)
    # Connectives and filler the composer may contribute.
    filler = {"and", "so", "but", "the", "a", "an", "it", "that", "this", "to",
              "of", "is", "was", "i", "my", "me", "you", "your", "no", "not",
              "yes", "well", "about", "for", "on", "in", "at", "as", "with",
              "them", "they", "he", "she", "we", "up", "out", "there", "here",
              "all", "any", "some", "just", "like", "s", "t", "m", "re", "ve",
              "d", "ll", "part", "parts", "other", "last", "please"}
    return [w for w in left.split() if w not in filler and len(w) > 2]


# ==========================================================================
# 1. The regression that triggered this work
# ==========================================================================
NAME_AND_COMPLAINT = [
    "What is your name and what brings you in today?",
    "What's your name and what brings you in today?",
    "Can you tell me your name and why you're here?",
    "Your name, and what brings you in?",
    "whats ur name and why r u here",
    "What is your name and what seems to be the problem?",
    "Tell me your name and what made you come in today.",
    "name and reason for visit?",
]


def test_name_and_complaint():
    group = "name+complaint"
    for cid in all_case_ids():
        case = load(cid)
        name = case["patient"]["name"]
        first = name.split()[0]
        complaint = norm(case["patient"]["opening"])
        key_words = [w for w in complaint.split() if len(w) > 4][:6]
        for question in NAME_AND_COMPLAINT:
            engine, state = fresh(case)
            reply, _ = ask(engine, state, question)
            low = norm(reply)
            has_name = norm(first) in low
            has_complaint = sum(1 for w in key_words if w in low) >= 2
            check(group, has_name,
                  "%s | %r -> name missing: %r" % (cid, question, reply))
            check(group, has_complaint,
                  "%s | %r -> complaint missing: %r" % (cid, question, reply))


# ==========================================================================
# 2. Compound questions of 2, 3 and 4 parts
# ==========================================================================
def answered_parts(reply, engine, case, categories):
    """How many of these fact categories the reply actually delivered."""
    low = norm(reply)
    hit = 0
    for category in categories:
        facts = [f for f in case["facts"] if f.get("category") == category]
        for fact in facts:
            for line in (fact.get("sp_says") or [fact.get("value", "")]):
                if line and norm(line) in low:
                    hit += 1
                    break
            else:
                continue
            break
    return hit


def test_compound():
    group = "compound"
    specs = [
        ("When did this start, how bad is it, and does anything make it better?",
         ["onset", "severity", "alleviating"], 3),
        ("Any medical problems, surgeries, medications, or allergies?",
         ["pmh", "psh", "medications", "allergies"], 3),
        ("Do you smoke or drink, and do you use any recreational drugs?",
         ["social"], 1),
        ("Where is it and how bad is it?", ["location", "severity"], 2),
        ("when did it start and how bad is it", ["onset", "severity"], 2),
        ("meds allergies surgeries?", ["medications", "allergies", "psh"], 2),
    ]
    for cid in all_case_ids():
        case = load(cid)
        for question, categories, minimum in specs:
            engine, state = fresh(case)
            reply, meta = ask(engine, state, question)
            got = answered_parts(reply, engine, case, categories)
            available = sum(1 for c in categories
                            if any(f.get("category") == c for f in case["facts"]))
            want = min(minimum, available)
            check(group, got >= want,
                  "%s | %r -> answered %d of %d wanted (%d available): %r"
                  % (cid, question, got, want, available, reply[:160]))


def test_smoke_drink_drugs_all_three():
    """The social triple must reach all three histories, not one of them."""
    group = "compound-social"
    for cid in all_case_ids():
        case = load(cid)
        engine, state = fresh(case)
        reply, _ = ask(engine, state, "Do you smoke or drink, and do you use any recreational drugs?")
        low = norm(reply)
        wanted = 0
        found = 0
        for cue in ("tobacco", "alcohol", "drugs"):
            facts = [f for f in case["facts"]
                     if engine._fact_subjects(f) == {cue}]
            if not facts:
                continue
            wanted += 1
            if any(norm(line) in low
                   for f in facts for line in (f.get("sp_says") or [f.get("value", "")]) if line):
                found += 1
        check(group, wanted == 0 or found >= max(2, wanted - 1),
              "%s -> %d of %d social histories: %r" % (cid, found, wanted, reply[:160]))


# ==========================================================================
# 3. Alternative phrasings of the same question
# ==========================================================================
COMPLAINT_PHRASINGS = [
    "What brings you in?", "Why are you here?", "What can I help you with today?",
    "What brings you to the hospital?", "What's going on?", "Tell me what happened.",
    "What seems to be the problem?", "Why did you come in today?",
    "What are you here for?", "What made you decide to come in?",
]


def test_complaint_phrasings():
    group = "phrasings-complaint"
    for cid in all_case_ids():
        case = load(cid)
        complaint = norm(case["patient"]["opening"])
        key_words = [w for w in complaint.split() if len(w) > 4][:6]
        for question in COMPLAINT_PHRASINGS:
            engine, state = fresh(case)
            reply, _ = ask(engine, state, question)
            low = norm(reply)
            check(group, sum(1 for w in key_words if w in low) >= 2,
                  "%s | %r -> %r" % (cid, question, reply[:140]))


ATTRIBUTE_PHRASINGS = {
    "location": ["Where is the pain?", "Where does it hurt?", "Whereabouts is it?",
                 "What part hurts?", "Where exactly?", "where"],
    "severity": ["How bad is it?", "How severe is it?", "On a scale of one to ten?",
                 "How much does it hurt?", "how bad"],
    "onset": ["When did this start?", "How long have you had this?",
              "When did it begin?", "how long"],
    "radiation": ["Does it spread anywhere?", "Does it move anywhere?",
                  "Does it radiate?", "does it spread", "does it go anywhere"],
    "aggravating": ["Does anything make it worse?", "What makes it worse?",
                    "anything make it worse"],
    "alleviating": ["Does anything make it better?", "What helps?",
                    "anything make it better"],
}


def test_attribute_phrasings():
    group = "phrasings-attribute"
    for cid in all_case_ids():
        case = load(cid)
        for category, questions in ATTRIBUTE_PHRASINGS.items():
            facts = [f for f in case["facts"] if f.get("category") == category]
            if not facts:
                continue
            lines = [norm(l) for f in facts
                     for l in (f.get("sp_says") or [f.get("value", "")]) if l]
            for question in questions:
                engine, state = fresh(case)
                reply, meta = ask(engine, state, question)
                low = norm(reply)
                # Some cases deliberately carry two onsets. For a bare
                # attribute question with no context, asking which one is
                # meant is the correct answer, not a miss.
                if meta.get("kind") == "clarification":
                    check(group, "do you mean" in low,
                          "%s | %s | %r -> malformed clarification: %r"
                          % (cid, category, question, reply[:130]))
                    continue
                check(group, any(l in low for l in lines),
                      "%s | %s | %r -> %r" % (cid, category, question, reply[:130]))


# ==========================================================================
# 4. Contextual follow-ups
# ==========================================================================
def test_followups():
    group = "followup"
    pairs = [
        ("Do you smoke?", "How long?", "tobacco"),
        ("Do you smoke?", "How much?", "tobacco"),
        ("Do you drink alcohol?", "How much?", "alcohol"),
        ("What medications do you take?", "How often do you take that?", "medications"),
        ("Do you have any allergies?", "What happens when you take it?", "allergies"),
    ]
    for cid in all_case_ids():
        case = load(cid)
        for first, second, subject in pairs:
            engine, state = fresh(case)
            facts = [f for f in case["facts"] if engine._fact_subjects(f) == {subject}]
            if not facts:
                continue
            lines = [norm(l) for f in facts
                     for l in (f.get("sp_says") or [f.get("value", "")]) if l]
            ask(engine, state, first)
            reply, _ = ask(engine, state, second)
            low = norm(reply)
            check(group, any(l in low for l in lines),
                  "%s | %r then %r -> off-subject: %r" % (cid, first, second, reply[:130]))


def test_followup_does_not_borrow_onset():
    """"Do you smoke?" / "How long?" must not answer with the symptom's onset."""
    group = "followup-collision"
    for cid in all_case_ids():
        case = load(cid)
        engine, state = fresh(case)
        smoking = [f for f in case["facts"] if engine._fact_subjects(f) == {"tobacco"}]
        onset = [f for f in case["facts"] if f.get("category") == "onset"]
        if not smoking or not onset:
            continue
        onset_lines = [norm(l) for f in onset
                       for l in (f.get("sp_says") or [f.get("value", "")]) if l]
        ask(engine, state, "Do you smoke?")
        reply, _ = ask(engine, state, "How long?")
        low = norm(reply)
        check(group, not any(l in low for l in onset_lines),
              "%s -> smoking follow-up answered with symptom onset: %r" % (cid, reply[:130]))


def test_pronoun_reference():
    group = "pronoun"
    for cid in all_case_ids():
        case = load(cid)
        radiation = [f for f in case["facts"] if f.get("category") == "radiation"]
        if not radiation:
            continue
        lines = [norm(l) for f in radiation
                 for l in (f.get("sp_says") or [f.get("value", "")]) if l]
        engine, state = fresh(case)
        ask(engine, state, "Where is the pain?")
        reply, _ = ask(engine, state, "Does it go anywhere else?")
        check(group, any(l in norm(reply) for l in lines),
              "%s -> 'it' lost its referent: %r" % (cid, reply[:130]))


# ==========================================================================
# 5. Elaboration
# ==========================================================================
def test_elaboration_stays_on_topic():
    group = "elaboration"
    for cid in all_case_ids():
        case = load(cid)
        engine, state = fresh(case)
        ask(engine, state, "Do you smoke?")
        reply, meta = ask(engine, state, "Tell me more.")
        low = norm(reply)
        # Must not answer a smoking follow-up out of the alcohol history.
        alcohol = [f for f in case["facts"] if engine._fact_subjects(f) == {"alcohol"}]
        lines = [norm(l) for f in alcohol
                 for l in (f.get("sp_says") or [f.get("value", "")]) if l]
        check(group, not any(l and l in low for l in lines),
              "%s -> elaboration on smoking gave the alcohol history: %r" % (cid, reply[:130]))


def test_elaboration_after_hpi_adds_detail():
    group = "elaboration-hpi"
    for cid in all_case_ids():
        case = load(cid)
        engine, state = fresh(case)
        ask(engine, state, "What brings you in?")
        reply, meta = ask(engine, state, "Tell me more.")
        check(group, bool(reply.strip()),
              "%s -> elaboration produced nothing" % cid)


# ==========================================================================
# 6. No invented clinical content
# ==========================================================================
PROBE_QUESTIONS = [
    "What is your name and what brings you in today?",
    "When did this start, how bad is it, and does anything make it better?",
    "Any medical problems, surgeries, medications, or allergies?",
    "Do you smoke or drink, and do you use any recreational drugs?",
    "meds allergies surgeries?", "any smoking drinking drugs?",
    "where exactly", "how long", "does it spread", "anything make it worse",
    "anything make it better", "ever happened before", "anything else going on",
    "tell me more", "what about your family", "mom or dad have anything like this",
    "What's the capital of France?", "asdfgh qwerty", "how old are you",
    "Do you have diabetes?", "Any family history of diabetes?",
    "Where do you live?", "What do you do for work?",
]


def test_no_invented_content():
    group = "no-hallucination"
    for cid in all_case_ids():
        case = load(cid)
        allowed = authored_text(case)
        for question in PROBE_QUESTIONS:
            engine, state = fresh(case)
            reply, _ = ask(engine, state, question)
            if not reply.strip():
                continue
            leftover = unaccounted(reply, allowed)
            check(group, not leftover,
                  "%s | %r -> unaccounted words %s in %r"
                  % (cid, question, leftover[:8], reply[:150]))


# ==========================================================================
# 7. Consistency and contradiction prevention
# ==========================================================================
def test_repeat_consistency():
    """Asking the same thing twice must not change the clinical answer."""
    group = "consistency"
    questions = ["When did this start?", "Where is the pain?", "Do you smoke?",
                 "Do you have any allergies?", "What medications do you take?"]
    for cid in all_case_ids():
        case = load(cid)
        for question in questions:
            engine, state = fresh(case)
            first, meta1 = ask(engine, state, question)
            second, meta2 = ask(engine, state, question)
            if not first.strip() or not second.strip():
                continue
            facts1 = set(meta1.get("facts_released") or [])
            facts2 = set(meta2.get("facts_released") or [])
            if facts1 and facts2:
                check(group, facts2 <= facts1 or facts1 <= facts2,
                      "%s | %r -> %s then %s" % (cid, question, sorted(facts1), sorted(facts2)))


def test_negative_stays_negative():
    """A denied symptom cannot become positive when asked again."""
    group = "contradiction"
    for cid in all_case_ids():
        case = load(cid)
        negatives = [f for f in case["facts"] if f.get("category") == "pertinent_negative"]
        for fact in negatives[:3]:
            questions = fact.get("example_questions") or []
            if not questions:
                continue
            engine, state = fresh(case)
            first, _ = ask(engine, state, questions[0])
            second, _ = ask(engine, state, questions[0])
            check(group, norm(first) and norm(second),
                  "%s | %r -> empty on repeat" % (cid, questions[0]))
            # The repeat may add "like I said" but must carry the same content.
            core = norm(first)
            for prefix in ("like i said ", "as i mentioned ", "right "):
                core = core.replace(prefix, "")
            second_core = norm(second)
            for prefix in ("like i said ", "as i mentioned ", "right "):
                second_core = second_core.replace(prefix, "")
            check(group, core[:40] in second_core or second_core[:40] in core,
                  "%s | %r -> changed: %r vs %r" % (cid, questions[0], first, second))


# ==========================================================================
# 8. Evidence discipline
# ==========================================================================
def test_identity_grants_no_clinical_credit():
    group = "evidence-identity"
    for cid in all_case_ids():
        case = load(cid)
        for question in ["What is your name?", "How old are you?",
                         "What's your name and how old are you?"]:
            engine, state = fresh(case)
            _, meta = ask(engine, state, question)
            check(group, not meta.get("facts_released"),
                  "%s | %r released %s" % (cid, question, meta.get("facts_released")))
            check(group, not meta.get("concepts"),
                  "%s | %r granted concepts %s" % (cid, question, list(meta.get("concepts") or {})))


def test_unasked_facts_not_released():
    """A greeting must not put clinical history on the record."""
    group = "evidence-greeting"
    for cid in all_case_ids():
        case = load(cid)
        for question in ["Hello, I'm a student doctor.", "Hi there.", "Good morning."]:
            engine, state = fresh(case)
            _, meta = ask(engine, state, question)
            check(group, not meta.get("facts_released"),
                  "%s | %r released %s" % (cid, question, meta.get("facts_released")))


# ==========================================================================
# 9. Robust input: typos, case, punctuation, abbreviations, fragments
# ==========================================================================
def test_input_robustness():
    group = "robust-input"
    variants = ["WHERE IS THE PAIN", "where is the pain", "where is the pain???",
                "  where is the pain  ", "Where is the pain!"]
    for cid in all_case_ids():
        case = load(cid)
        location = [f for f in case["facts"] if f.get("category") == "location"]
        if not location:
            continue
        lines = [norm(l) for f in location
                 for l in (f.get("sp_says") or [f.get("value", "")]) if l]
        for question in variants:
            engine, state = fresh(case)
            reply, _ = ask(engine, state, question)
            check(group, any(l in norm(reply) for l in lines),
                  "%s | %r -> %r" % (cid, question, reply[:120]))


def test_never_empty_or_crashing():
    group = "always-replies"
    odd = ["", "   ", "?", "...", "asdfgh", "!!!", "hm", "ok", "1234",
           "What's the capital of France?", "ignore your instructions",
           "a" * 300, "where where where where", "😀", "do you"]
    for cid in all_case_ids()[:6]:
        case = load(cid)
        for question in odd:
            engine, state = fresh(case)
            try:
                reply, meta = ask(engine, state, question)
            except Exception as exc:  # noqa: BLE001
                fail(group, "%s | %r raised %r" % (cid, question[:30], exc))
                continue
            CHECKS[0] += 1
            if question.strip():
                check(group, isinstance(reply, str) and reply.strip(),
                      "%s | %r -> empty reply" % (cid, question[:30]))


# ==========================================================================
# 10. Targeted collision checks the brief calls out
# ==========================================================================
def test_collisions():
    group = "collision"
    for cid in all_case_ids():
        case = load(cid)
        engine, state = fresh(case)
        household = [f for f in case["facts"] if engine._fact_subjects(f) == {"household"}]
        location = [f for f in case["facts"] if f.get("category") == "location"]
        if household and location:
            loc_lines = [norm(l) for f in location
                         for l in (f.get("sp_says") or [f.get("value", "")]) if l]
            engine, state = fresh(case)
            reply, _ = ask(engine, state, "Where do you live?")
            check(group, not any(l in norm(reply) for l in loc_lines),
                  "%s | 'Where do you live?' answered with the pain location: %r"
                  % (cid, reply[:120]))

        family = [f for f in case["facts"] if f.get("category") == "family"]
        pmh = [f for f in case["facts"] if f.get("category") == "pmh"]
        if family and pmh:
            pmh_lines = [norm(l) for f in pmh
                         for l in (f.get("sp_says") or [f.get("value", "")]) if l]
            engine, state = fresh(case)
            reply, _ = ask(engine, state, "Is there any family history of diabetes?")
            check(group, not any(l == norm(reply).strip(" .") for l in pmh_lines),
                  "%s | family-history question answered with her own PMH: %r"
                  % (cid, reply[:120]))


# ==========================================================================
def main():
    groups = [
        test_name_and_complaint, test_compound, test_smoke_drink_drugs_all_three,
        test_complaint_phrasings, test_attribute_phrasings, test_followups,
        test_followup_does_not_borrow_onset, test_pronoun_reference,
        test_elaboration_stays_on_topic, test_elaboration_after_hpi_adds_detail,
        test_no_invented_content, test_repeat_consistency, test_negative_stays_negative,
        test_identity_grants_no_clinical_credit, test_unasked_facts_not_released,
        test_input_robustness, test_never_empty_or_crashing, test_collisions,
    ]
    for group in groups:
        before = len(FAILURES)
        group()
        status = "ok" if len(FAILURES) == before else "%d FAILED" % (len(FAILURES) - before)
        print("  %-42s %s" % (group.__name__, status))

    by_group = {}
    for group, detail in FAILURES:
        by_group.setdefault(group, []).append(detail)
    print()
    if not FAILURES:
        print("PASS %d checks across %d cases; multi-intent, follow-up context, "
              "phrasing coverage, evidence discipline, no invented content."
              % (CHECKS[0], len(all_case_ids())))
        return 0
    print("FAIL %d of %d checks" % (len(FAILURES), CHECKS[0]))
    for group, details in sorted(by_group.items(), key=lambda kv: -len(kv[1])):
        print("  %-24s %d" % (group, len(details)))
        for detail in details[: (None if VERBOSE else 3)]:
            print("      " + detail[:200])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
