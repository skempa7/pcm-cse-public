"""Regressions reproduced during the independent September 2026 review.

Checks actual replies and disclosed facts across the complete case library,
including variants. Unknown symptoms must stay unknown; paraphrase coverage
must not come from manufacturing answers or widening evidence permissions.

    python3 tools/test_dialogue_review.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pcmcse import cases, dialogue, patient

checks = 0


def check(condition, detail):
    global checks
    checks += 1
    assert condition, detail


def ask(case, question, state=None):
    return patient.PatientEngine(case).respond(question, state if state is not None else {})


def run():
    count = 0
    for cid, raw in sorted(cases.all_cases().items()):
        for variant in ["base"] + [v["id"] for v in raw.get("variants", [])]:
            case = cases.resolve(cid, variant)
            count += 1
            for question in ("name and age please", "name, age, please", "name age please"):
                reply, meta = ask(case, question)
                check(case["patient"]["name"] in reply and
                      "%s years old" % case["patient"]["age"] in reply,
                      (cid, variant, question, reply))
                check(not meta["facts_released"] and not meta["concepts"],
                      (cid, "identity disclosed clinical history", meta))
            reply, meta = ask(case, "name age occupation")
            check(case["patient"]["name"] in reply and
                  "%s years old" % case["patient"]["age"] in reply,
                  (cid, "compound identity dropped", reply))
            _, occupation = ask(case, "What do you do for work?")
            check(set(occupation["facts_released"]) <= set(meta["facts_released"]),
                  (cid, "compound occupation dropped", reply))
            check(all(patient.conversation_route(q) != "identity" for q in
                      ("How old is your mother?", "How old were you when this started?")),
                  (cid, "relative or historical age became current identity"))

            _, severity = ask(case, "How severe is it?")
            reply, meta = ask(case, "What were you doing when this started and how severe is it?")
            check(set(severity["facts_released"]) <= set(meta["facts_released"]),
                  (cid, "activity route swallowed severity", reply))
            check(not any(f["id"] in meta["facts_released"] and
                          f.get("category") == "setting" and not f.get("onset_activity")
                          for f in case["facts"]),
                  (cid, "activity question disclosed exposure", reply))

            for fid, canonical, variants in (
                ("symptom_dyspnea", "Are you short of breath?",
                 ("Any shortness of breath?", "Have you felt breathless?")),
                ("symptom_nausea", "Have you had nausea?",
                 ("Have you been nauseated?", "Any queasiness?")),
                ("symptom_constipation", "Any constipation?",
                 ("Have you been constipated?",)),
                ("symptom_hematuria", "Any hematuria?",
                 ("Any blood in your urine?",)),
            ):
                if fid not in {f["id"] for f in case["facts"]}:
                    continue
                _, expected = ask(case, canonical)
                if fid not in expected["facts_released"]:
                    continue
                for question in variants:
                    reply, meta = ask(case, question)
                    check(fid in meta["facts_released"],
                          (cid, variant, question, "authored symptom omitted", reply))
                    check(set(meta["facts_released"]) == set(expected["facts_released"]),
                          (cid, question, "synonym gained unrelated facts", meta))

            for question in ("Does your mother have a cough?", "Has your father had nausea?",
                             "When did your mother get short of breath?",
                             "When did your mother have surgery?"):
                reply, meta = ask(case, question)
                check(not meta["facts_released"] and not meta["concepts"],
                      (cid, "unscripted relative detail borrowed case facts", question, reply, meta))

            e, state = patient.PatientEngine(case), {}
            spoken, meta = e.respond("When did this start?", state)
            reply, summary = e.respond("Let me summarize: " + spoken + " Is that right?", state)
            check(summary.get("summary_verdict") == "confirmed",
                  (cid, "literal accurate summary was not confirmed", reply))
            before = set(state["released"])
            for addition in ("and blue toenails", "and HIV", "which means you have cancer"):
                reply, summary = e.respond("Let me summarize: " + spoken.rstrip(".") +
                                           " " + addition + ". Is that right?", state)
                check(summary.get("summary_verdict") != "confirmed",
                      (cid, "invented addition was confirmed", addition, reply))
                check(set(state["released"]) == before and not summary["concepts"],
                      (cid, "summary laundered new evidence", summary))

    case = cases.resolve("cardio-febrile-cough", "base")
    e, state = patient.PatientEngine(case), {}
    e.respond("When did this start?", state)
    reply, meta = e.respond("Let me summarize: your cough began 2 days ago. Is that right?", state)
    check(meta.get("summary_verdict") == "corrected_timeline" and "4 days" in reply,
          ("numeric summary corruption", reply, meta))
    reply, meta = e.respond("Let me summarize: your cough began 4 days ago. Is that right?", state)
    check(meta.get("summary_verdict") == "confirmed", (reply, meta))
    for text in ("2 days", "4 days", "2/10", "4 mg", "2.4 mg", "4 times a day"):
        check(dialogue.casual_expand(text) == text, ("clinical number changed", text))

    # An undisclosed but authored timeline is not free confirmation through a
    # disguised summary; a summary should only confirm what was said.
    reply, meta = ask(case, "Let me summarize: your cough began 4 days ago. Is that right?")
    check(meta.get("summary_verdict") != "confirmed" and not meta["facts_released"],
          ("undisclosed timeline confirmed", reply, meta))
    urinary = cases.resolve("renal-dysuria", "base")
    reply, meta = ask(urinary, "Any trouble urinating?")
    check(set(meta["facts_released"]) == {"symptom_dysuria", "symptom_frequency", "symptom_urgency"},
          ("broad urinary ROS missed authored symptoms", reply, meta))
    # Missing ROS authoring must never become an affirmative or negative fact.
    for question in ("Have you had any muscle aches?", "Any shortness of breath?"):
        missing = cases.resolve("renal-dysuria", "base")
        reply, meta = ask(missing, question)
        check(bool(reply) and meta.get("no_information") and not meta["facts_released"]
              and not meta["concepts"], ("missing symptom invented", question, reply, meta))
    # A modifier changes the question: general dyspnea must not answer present
    # symptoms, nighttime symptoms, or somebody else's symptom history.
    e = patient.PatientEngine(case)
    for question in ("Any shortness of breath right now?", "Any shortness of breath at night?",
                     "Does your mother have shortness of breath?", "Could a medication cause shortness of breath?"):
        check(e._direct_ros_hits(question) is None, ("ROS qualifier discarded", question))
    print("PASS %d checks across %d case variants: compound identity, activity scope, ROS synonyms, "
          "numeric preservation, and conservative summary confirmation." % (checks, count))


if __name__ == "__main__":
    run()
