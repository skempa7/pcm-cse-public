"""Post-submission teaching output.

Two teaching resources are produced and kept clearly apart:

  1. **Corrected note** -- your note rewritten using *only* what your encounter
     actually produced.  Unsupported sentences are struck, and facts you
     obtained but left out are added.  Nothing from the hidden case is
     imported: if you never asked, it is not in here.

  2. **Ideal encounter comparison** -- the model note, plus the specific extra
     questions and examination actions that would have been needed to support
     it.  This one is allowed to reference the hidden case, and says so.
"""

from __future__ import annotations

import re

from . import claims as claims_mod
from . import evidence, lexicon, nlp, physexam, differential_supplements

_SEVERITY = {
    "contradicts": 100,
    "unsupported": 90,
    "overbroad": 80,
    "counseling_unsupported": 70,
    "misplaced": 60,
}


def build(parsed, ledger, case, audit_result, rubric, chk, interp, settings, session):
    priority = _priority_errors(audit_result, rubric, chk, case)
    return {
        "priority_errors": priority,
        "missed_questions": _missed_questions(chk, case),
        "missed_exams": _missed_exams(chk, ledger, case),
        "obtained_not_documented": audit_result["obtained_but_omitted"],
        "unsupported": [c for c in audit_result["claims"]
                        if c["verdict"] in ("unsupported", "contradicts",
                                            "overbroad", "misplaced",
                                            "counseling_unsupported")],
        "assessment_plan": _assessment_plan_feedback(rubric, case),
        "communication": _communication_feedback(interp, ledger),
        "time_management": _time_feedback(ledger, session, parsed),
        "corrected_note": corrected_note(parsed, ledger, case, audit_result),
        "ideal": ideal_comparison(case, ledger, chk),
        "worked_examples": _worked_examples(audit_result, chk, case, interp),
        "not_assessed": _not_assessed(session, chk, interp),
    }


# ---------------------------------------------------------------------------

def _priority_errors(audit_result, rubric, chk, case):
    items = []

    for row in rubric["rows"]:
        if row["earned"]:
            continue
        if row.get("recognition_limited"):
            items.append({
                "rank_score": row["points_available"] * 10,
                "kind": "recognition_review", "category": row["category"],
                "label": row["label"], "title": row["label"] + " — automated reading needs review",
                "what_happened": row["why"],
                "why_it_matters": "Unrecognized wording is not proof that the clinical statement is incorrect. This criterion did not receive automatic credit.",
                "what_to_do": "Compare your quoted wording with the criterion and the encounter. Do not add unsupported facts or change a valid diagnosis just to match a phrase.",
                "passage": row["passage"], "evidence": row["evidence"],
                "conditions": row["conditions_applied"], "points": 0,
            })
            continue
        items.append({
            "rank_score": row["points_available"] * 10,
            "kind": "rubric",
            "category": row["category"],
            "label": row["label"],
            "title": "%s (%s) — %d point%s lost" % (
                row["label"], row["category"], row["points_available"],
                "" if row["points_available"] == 1 else "s"),
            "what_happened": row["why"],
            "why_it_matters": _why_matters(row),
            "what_to_do": _what_to_do(row, case),
            "passage": row["passage"],
            "evidence": row["evidence"],
            "conditions": row["conditions_applied"],
            "points": row["points_available"],
        })

    for c in audit_result["claims"]:
        sev = _SEVERITY.get(c["verdict"])
        if not sev:
            continue
        items.append({
            "rank_score": sev,
            "kind": "documentation",
            "title": _doc_title(c),
            "what_happened": c["explanation"],
            "why_it_matters": _doc_why(c),
            "what_to_do": _doc_fix(c),
            "passage": c["text"],
            "evidence": c["evidence"],
            "section": c["section"],
            "points": 0,
        })

    for ic in audit_result["internal_contradictions"]:
        items.append({
            "rank_score": 105,
            "kind": "documentation",
            "title": "Your note contradicts itself about %s"
                     % ic["concept"].replace("_", " "),
            "what_happened": "%s says one thing; %s says the opposite."
                             % (ic["first_section"], ic["second_section"]),
            "why_it_matters": ("A reader cannot act on a note that says both. "
                               "The student manual's own sample note has exactly "
                               "this defect — it denies hemoptysis in the HPI and "
                               "admits it in the ROS — and it is a defect, not a "
                               "model to copy."),
            "what_to_do": "Decide which is true from the encounter and state it once.",
            "passage": "%s  ||  %s" % (ic["first"], ic["second"]),
            "evidence": [],
            "points": 0,
        })

    refusal_items = [p for p in chk["physical"]
                     if p["id"].startswith("p") and "refus" in p["text"].lower()]
    for r in refusal_items:
        if r["status"] != "performed":
            requested = next((x.get("refusal") for x in case.get("checklist",{}).get("physical",[]) if x.get("id")==r["id"]), None)
            refusal = physexam.REFUSABLE.get(requested, {})
            doc = refusal.get("doc", "the specifically proposed examination + refused")
            items.append({
                "rank_score": 75,
                "kind": "encounter",
                "title": "A refusable examination was never proposed",
                "what_happened": r["detail"],
                "why_it_matters": ("The syllabus requires documenting a warranted examination that was proposed and refused. "
                                   "The appropriate examination depends on the case; this is separate from the SOAP score."),
                "what_to_do": ("Review this case's authored checklist item: " + r["text"] +
                               ". If clinically warranted, propose that examination. After the actual refusal, document '" + doc +
                               "' in Objective. Do not claim it was performed or delay urgent care to complete a checklist."),
                "passage": "", "evidence": [], "points": 0,
            })

    # A rubric row is worth at most 5 points, so its rank_score topped out at
    # 50 while every documentation verdict scores 60-105. The debrief's landing
    # card shows the top three, so three "unsupported claim" notes pushed off a
    # whole section scoring zero -- the student read three nitpicks and never
    # saw that Objective earned nothing. Rank by the points actually at stake:
    # where a section has lost several rows together, say so once, scored by
    # what the section lost in total.
    by_category = {}
    for item in items:
        if item.get("kind") == "rubric" and item.get("category"):
            by_category.setdefault(item["category"], []).append(item)
    for category, rows in by_category.items():
        lost = sum(r.get("points") or 0 for r in rows)
        if len(rows) < 2 or lost < 6:
            continue
        labels = [r["label"] for r in rows if r.get("label")]
        items.append({
            "rank_score": lost * 10,
            "kind": "rubric_section",
            "category": category,
            "title": "%s — %d points lost across %d requirements"
                     % (category, lost, len(rows)),
            "what_happened": "Nothing was credited for: " + ", ".join(labels) + ".",
            "why_it_matters": rows[0].get("why_it_matters") or "",
            "what_to_do": ("This is the largest single loss in this attempt. "
                           "Work through these together rather than one at a "
                           "time: " + (rows[0].get("what_to_do") or "")),
            "passage": "", "evidence": [], "points": lost,
        })

    items.sort(key=lambda x: -x["rank_score"])
    return items[:18]


def _why_matters(row):
    cat = row["category"]
    if cat == "Objective":
        return ("Objective rows are worth 5 points each — a sixth of Objective and 5% of the note. "
                "The course's stated deductions for this section are almost all "
                "about specificity and headers, not about knowing more medicine.")
    if cat == "Assessment":
        return ("The assessment is where clinical reasoning is graded. A "
                "differential that does not correlate with the case earns "
                "nothing, however sound the rest of the note is.")
    if cat == "Plan":
        return ("Plans carry 25 of the 100 points, more than the assessment. "
                "The elements requirement is what turns a list of tests into a "
                "plan.")
    if cat == "Subjective":
        return ("Subjective is fourteen small rows. Losing several to one "
                "structural habit — a missing header, an unasked social "
                "question — costs more than any single clinical miss.")
    return "Style points are cheap to keep and cheap to lose."


def _what_to_do(row, case):
    rid = row["id"]
    fixes = {
        "vitals": "Open Objective with the vitals exactly as the chart gives them, "
                  "then move to General.",
        "osteopathic": 'First perform the relevant osteopathic structural examination. Document only the exact level, side and dysfunction actually released. A viscerosomatic reference range is a guide for examination, not an observed patient finding. If no finding was obtained, leave the finding out and identify the examination as still needed.',
        "social_history": "Tobacco, alcohol and drugs go in every note. Ask all "
                          "three in one transition and write all three.",
        "family_history": "Name the biological parents and the siblings, with "
                          "ages and conditions where you have them.",
        "ros": "Ask about three symptoms in each of three pertinent systems. "
               "Document only the positive and negative answers actually obtained.",
        "specific_follow_up": "State a specific follow-up interval or disposition in Plan 1 "
                              "that matches this patient's urgency. A needed emergency "
                              "transfer must not become a routine follow-up visit.",
        "specific_education": "Name the education topic, practical instructions and "
                              "return precautions relevant to your plan. Describe it "
                              "as proposed education unless you actually discussed it.",
        "most_relevant": "For the area of concern, document inspection, "
                         "auscultation, percussion and palpation, plus the "
                         "special test that discriminates the differential.",
        "heart_lungs": "Use the header words the course names: Heart and Lungs.",
        "cc_clear": "One line: the complaint in the patient's terms plus a "
                    "duration, and make it the same problem the HPI describes.",
        "age_sex": "Open the HPI '24 yo f with ...' — the manual's own examples "
                   "do exactly this.",
    }
    if rid in fixes:
        return fixes[rid]
    if rid.startswith("assessment"):
        return ("Name a specific diagnosis that the history and exam you obtained "
                "actually support, and make each of the three a different "
                "VINDICATE category.")
    if rid.startswith("plan"):
        return ("Give each plan at least three different kinds of action — a "
                "test, a treatment, and education or referral or follow-up — and "
                "make plan N address assessment N.")
    return "Re-read this row's condition in the grading table and write to it."


def _doc_title(c):
    titles = {
        "unsupported": "Unsupported claim in %s",
        "contradicts": "Contradicts the encounter (%s)",
        "overbroad": "Claims more than you examined (%s)",
        "misplaced": "Right fact, wrong section (%s)",
        "counseling_unsupported": "Documented a discussion that did not happen (%s)",
    }
    return titles.get(c["verdict"], "%s") % c["section"]


def _doc_why(c):
    if c["section"] == "O" and c["verdict"] == "unsupported":
        return 'Objective findings require a performed examination or an explicitly supplied measurement or result. A patient history answer does not establish a physical finding.'
    if c["verdict"] == "unsupported":
        return ("The lecture names this directly: 'SOAP NOTE FALSE DOCUMENTATION "
                "— underdocumenting, overdocumenting, ie CN I-XII intact.' A "
                "negative you never asked about reads to a grader exactly like a "
                "negative you invented.")
    if c["verdict"] == "contradicts":
        return ("A note that disagrees with the encounter is worse than a thin "
                "note, because a reader would act on it.")
    if c["verdict"] == "overbroad":
        return ("Scope is part of accuracy. 'Anterior and posterior' is a claim "
                "about where you put the stethoscope.")
    if c["verdict"] == "misplaced":
        return ("The lecture lists 'information in the wrong section; ie. Heart "
                "regular in the subjective' as its own deduction.")
    return ("Past tense asserts that something happened. Future intent is a "
            "different claim and should be worded as one.")


def _doc_fix(c):
    if c["section"] == "O" and c["verdict"] == "unsupported":
        return 'Perform the specific examination and document only the finding released, or use the explicitly supplied measurement or result. Otherwise leave this finding out.'
    if c["section"] == "O" and c["verdict"] == "contradicts":
        return 'Compare the linked examination finding or supplied chart or result, then correct the documented value, side, or finding.'
    if c["verdict"] == "unsupported":
        return ("Either ask the question in the encounter, or leave the line out. "
                "If you want the negative, you have to earn it.")
    if c["verdict"] == "contradicts":
        return "Check the transcript and write what the patient actually said."
    if c["verdict"] == "overbroad":
        return "Narrow the sentence to the fields or nerves you actually covered."
    if c["verdict"] == "misplaced":
        return "Move it to the other section."
    return "Write it as 'will educate the patient on ...' unless you discussed it."


# ---------------------------------------------------------------------------

def _missed_questions(chk, case):
    out = []
    for item in chk["history"]:
        if item["status"] == "obtained":
            continue
        fact = next((f for f in case["facts"] if f.get("checklist") == item["id"]), None)
        example = ""
        if fact:
            trig = (fact.get("triggers") or {}).get("any") or []
            if trig:
                example = _example_question(trig[0], fact)
        out.append({
            "id": item["id"], "text": item["text"],
            "example_question": example,
            "category": fact.get("category") if fact else "",
        })
    return out


_QUESTION_TEMPLATES = {
    "onset": "When did this start?",
    "location": "Can you point to exactly where it hurts?",
    "radiation": "Does the pain travel anywhere else?",
    "quality": "What does the pain feel like — sharp, dull, burning?",
    "severity": "On a scale of 0 to 10, how bad is it right now?",
    "chronology": "Since it started, has it been getting better, worse, or staying the same?",
    "timing": "Is it there all the time, or does it come and go?",
    "setting": "What were you doing when it started?",
    "alleviating": "Is there anything that makes it better?",
    "aggravating": "Is there anything that makes it worse?",
    "treatment": "Have you taken anything for it?",
    "past_occurrence": "Have you ever had anything like this before?",
    "associated": "Have you noticed anything else along with it?",
    "pertinent_negative": "Have you had any %s?",
    "pmh": "Do you have any ongoing medical problems?",
    "psh": "Have you had any surgeries or been in the hospital?",
    "medications": "What medications do you take, including anything over the counter?",
    "allergies": "Are you allergic to any medications? What happens when you take it?",
    "social": "Do you smoke, drink alcohol, or use any recreational drugs?",
    "obgyn": "When was your last menstrual period, and is there any chance you could be pregnant?",
    "family": "Are your parents living, and do you have brothers or sisters? Any health problems in the family?",
    "fife": "What do you think might be going on? Is there something in particular you are worried about?",
}


def _example_question(trigger_phrase, fact):
    examples = fact.get("example_questions") or []
    if examples:
        return examples[0]
    tpl = _QUESTION_TEMPLATES.get(fact.get("category"))
    if tpl and "%s" in tpl:
        # Never turn a declarative patient answer into a malformed question.
        subject = re.sub(r"^(?:no|denies|any)\s+", "", (trigger_phrase or "").strip(), flags=re.I)
        if subject and len(subject.split()) <= 5 and not re.search(r"\b(i|my|have|had|when|not)\b", subject, re.I):
            return "Have you experienced %s?" % subject.rstrip(".?!")
        return "Have you noticed any other symptoms?"
    return tpl or ("Ask about %s." % (fact.get("category") or "this"))


def _missed_exams(chk, ledger, case):
    out = []
    for item in chk["physical"]:
        if item["status"] in ("performed",):
            continue
        man = physexam.CATALOG_BY_ID.get(item.get("id") and "") or None
        out.append({
            "id": item["id"], "text": item["text"], "status": item["status"],
            "detail": item["detail"],
            "how": _exam_how(item, case),
        })
    return out


def _exam_how(item, case):
    text = item["text"].lower()
    if "costovertebral" in text or "cva" in text:
        return ("Say what you do and where: 'I'm going to tap gently over your "
                "kidneys on both sides — tell me if either side is tender.' "
                "Assess both sides so the comparison is real.")
    if "osteopathic" in text:
        return ("Screen the viscerosomatic level for the system involved — %s for "
                "this case — and name the tissue texture and the positional "
                "finding." % case.get("osteopathic", {}).get("levels", "the relevant level"))
    if "auscultat" in text and "lung" in text:
        return ("Six posterior fields, on skin, patient breathing through an open "
                "mouth, comparing side to side. The course lists all four of "
                "those as CSE-1 failures.")
    if "auscultat" in text and "heart" in text:
        return "Four posts minimum, on skin, not over the gown."
    if "before palpating" in text or "BEFORE" in item["text"]:
        return "Auscultate the abdomen first — palpation changes what you hear."
    if "refus" in text:
        return ("State the proposal out loud so the refusal is recorded and can "
                "be documented.")
    return "Name the region and the method, and cover the components."


# ---------------------------------------------------------------------------

def _assessment_plan_feedback(rubric, case):
    meta_a = rubric["assessment_meta"]
    meta_p = rubric["plan_meta"]
    notes = []
    distinct = meta_a.get("distinct_letters", 0)
    if distinct < 3:
        notes.append(
            "Your three differentials cover %d distinct VINDICATE element(s). The "
            "rubric requires three different ones. Choosing across categories is "
            "also just better differential practice — it stops three names for "
            "the same idea." % distinct)
    for i, els in enumerate(meta_p.get("elements", []), start=1):
        if not els:
            continue
        if len(els) < 3:
            notes.append(
                "Plan %d has %d element(s): %s. Add a different kind of action — "
                "if you already have tests and a medication, add education, a "
                "referral, OMT, or a return interval."
                % (i, len(els), ", ".join(els.keys())))
    return {
        "notes": notes,
        "vindicate_used": meta_a.get("letters", []),
        "matched_differentials": meta_a.get("matched", []),
        "motherr_per_plan": meta_p.get("elements", []),
        "case_acceptable_differentials": [
            {"name": d["name"], "vindicate": d["vindicate"], "rank": d["rank"]}
            for d in differential_supplements.for_case(case)],
    }


def _communication_feedback(interp, ledger):
    weak = [i for i in interp["acir"]["items"]
            if not i["not_assessed"] and i["score"] is not None and i["score"] <= 3]
    return {
        "weakest": sorted(weak, key=lambda i: i["score"])[:4],
        "signals": interp["signals"],
        "not_assessed": interp["not_assessed"],
    }


def _time_feedback(ledger, session, parsed):
    used = session.row["encounter_used_ms"] or 0
    allowed = session.preset["encounter_s"] * 1000
    turns = ledger.student_turns()
    exam_events = ledger.by_kind(evidence.EXAM_ACTION)
    first_exam = min((e["t_ms"] for e in exam_events), default=None)
    counsel = ledger.by_kind(evidence.COUNSELING)
    first_counsel = min((e["t_ms"] for e in counsel), default=None)

    untimed = allowed <= 0 or session.is_untimed_phase("encounter")
    notes = []
    if untimed:
        notes.append("This practice encounter was untimed. You spent %s practicing; speed is not scored in this mode." % _mmss(used))
    elif used >= allowed - 1500:
        notes.append("The encounter ran to the buzzer.")
    else:
        notes.append("You closed the encounter with %s left. Unused encounter "
                     "time is not added to the note period — no course rule "
                     "supports carry-over." % _mmss(allowed - used))
    if untimed:
        notes.append("No examination was performed." if first_exam is None else "Your first examination started at %s elapsed." % _mmss(first_exam))
    elif first_exam is None:
        notes.append("No examination was performed. The encounter allowance covers history, physical examination, and discussion.")
    else:
        pct = 100.0 * first_exam / allowed
        notes.append("You started examining at %s (%.0f%% of the way through). "
                     "Leave time for focused history, physical examination, and discussion." % (_mmss(first_exam), pct))
    if first_counsel is None:
        notes.append("No plan discussion was recorded. The course flags this: "
                     "'many students gave a closure and provided an assessment, "
                     "but no discussion of a plan'.")
    else:
        notes.append("You began discussing the plan at %s." % _mmss(first_counsel))

    if session.row["submit_reason"] == "time_expired":
        notes.append("The note was submitted automatically when its allotted time "
                     "expired. What is scored is exactly what was on screen at "
                     "that moment.")
    return {
        "encounter_used_s": round(used / 1000),
        "encounter_allowed_s": None if untimed else session.preset["encounter_s"],
        "untimed": untimed,
        "student_turns": len(turns),
        "first_exam_at": _mmss(first_exam) if first_exam is not None else None,
        "first_plan_talk_at": _mmss(first_counsel) if first_counsel is not None else None,
        "notes": notes,
    }


def _mmss(ms):
    if ms is None:
        return "-"
    s = int(ms // 1000)
    return "%d:%02d" % (s // 60, s % 60)


# ---------------------------------------------------------------------------
# Teaching resource 1: the corrected note
# ---------------------------------------------------------------------------
#
# The correction is made CLAUSE BY CLAUSE, not section by section. A note is not
# true or false as a block: "Right flank pain and no cough" is half obtained and
# half invented, and "Pyelonephritis confirmed by positive urine culture" is a
# defensible diagnosis welded to a test result that does not exist. Correcting at
# the level of the whole sentence forces a choice between deleting good reasoning
# and keeping a false claim, so every unit the audit judged is edited in place and
# only the offending fragment is struck.
#
# Three records are kept apart and all three stay retrievable: the ORIGINAL
# submission (never modified, also returned as results["note"]), this PROPOSED
# correction, and the IDEAL model note in `ideal_comparison` below. Only the ideal
# one may show the hidden case.

# Verdicts that say the encounter did not produce the assertion. These are claims
# about what happened in the room, and the room did not produce them, so they
# cannot stand in a note labelled "corrected against your own encounter".
_FALSE_VERDICTS = ("unsupported", "contradicts", "counseling_unsupported")

# A verdict that keeps the sentence but must not present it as verified: the
# claim is partly earned and reaches past what was actually examined.
_QUALIFY_VERDICTS = ("overbroad",)

# Marks a retained sentence the audit could not check either way. Without this
# the whole note reads as verified, which is the one thing a correction must
# never imply about a clause nobody evaluated.
_UNEVALUATED_FLAG = " [could not be evaluated against your encounter record]"

_OVERBROAD_FLAG = " [not supported by the examination you performed — narrow it]"

# An Assessment or Plan entry the audit rejected but whose offending fragment
# could not be isolated. The entry is flagged rather than deleted, because it may
# also hold a proposal or a diagnosis the student is entitled to keep.
_ENTRY_FLAG = (" [unsupported in part — see the change log for what your "
               "encounter does not back]")


class _Verdicts:
    """The audit's records, retrievable by the claim they belong to.

    The audit walks `parsed.claims()` in order, so a positional walk would work
    until the audit skips a claim -- which it does for anything that normalizes
    to nothing. Keying on (section, normalized text) and consuming each record
    once survives that, and keeps two identical sentences apart.
    """

    def __init__(self, records):
        self._queues = {}
        for rec in records:
            key = (rec["section"], nlp.normalize(rec["text"]))
            self._queues.setdefault(key, []).append(rec)

    def take(self, section, text):
        queue = self._queues.get((section, nlp.normalize(text)))
        if not queue:
            return None
        return queue.pop(0)


class _ChangeLog:
    """Every material change, with the reason that justifies it.

    A student told only that a sentence disappeared learns nothing. Each record
    names the section, the exact text, and why: either the evidence event that
    contradicts it, or the absence of any evidence for it.
    """

    def __init__(self):
        self.removed = []
        self.qualified = []
        self.added = []
        self.limitations = []

    def remove(self, section, text, reason, evidence_items=None):
        text = (text or "").strip()
        if not text:
            return
        self.removed.append({"section": section, "text": text, "reason": reason,
                             "evidence": list(evidence_items or [])})

    def qualify(self, section, text, reason, evidence_items=None):
        self.qualified.append({"section": section, "text": (text or "").strip(),
                               "reason": reason,
                               "evidence": list(evidence_items or [])})

    def add(self, section, text, concept, reason):
        self.added.append({"section": section, "text": text, "concept": concept,
                           "reason": reason})

    def limit(self, section, text, reason):
        self.limitations.append({"section": section, "text": (text or "").strip(),
                                 "reason": reason})


def corrected_note(parsed, ledger, case, audit_result):
    """Your note, rebuilt clause by clause from your own encounter.

    Nothing hidden is added: a fact being true of the patient is not a licence to
    document it, so only what your own encounter released can appear here.
    """
    verdicts = _Verdicts(audit_result["claims"])
    log = _ChangeLog()
    ev_index = claims_mod.evidence_index(ledger, case)
    counseled = ledger.counseling_topics()

    claims = parsed.claims()
    s_text = _correct_free_text(
        "S", parsed.s_text, [c for c in claims if c["section"] == "S"],
        verdicts, case, log)
    o_text = _correct_free_text(
        "O", parsed.o_text, [c for c in claims if c["section"] == "O"],
        verdicts, case, log)
    a_entries = _correct_entries(parsed.a_entries, "A", verdicts, ev_index,
                                 counseled, case, log)
    p_entries = _correct_entries(parsed.p_entries, "P", verdicts, ev_index,
                                 counseled, case, log)

    # Facts you obtained but did not write down are legitimately addable --
    # you have the evidence for them.
    additions = {"S": [], "O": []}
    for omit in audit_result["obtained_but_omitted"]:
        label, value = omit["label"], omit["value"]
        body = label if not value else (
            value if value.lower().startswith(label.lower()[:8]) else
            "%s: %s" % (label, value))
        line = "%s (obtained at %s)" % (body, omit["time"])
        section = "O" if _is_objective_concept(omit["concept"], ledger) else "S"
        additions[section].append(line)
        log.add(section, line, omit["concept"],
                "Your encounter released this at %s and your note leaves it out, "
                "so documenting it is earned." % omit["time"])

    if additions["S"]:
        s_text = s_text.rstrip() + "\n\n[Added from your encounter — you obtained " \
                                   "these but did not document them]\n" + \
                 "\n".join("- " + a for a in additions["S"])
    if additions["O"]:
        o_text = o_text.rstrip() + "\n\n[Added from your encounter — you obtained " \
                                   "these but did not document them]\n" + \
                 "\n".join("- " + a for a in additions["O"])

    refusals = ledger.refused_exams()
    for key, ev in refusals.items():
        doc = ev["meta"].get("documented_as", "")
        if doc and doc.lower() not in (o_text or "").lower():
            o_text = (o_text or "").rstrip() + "\n- " + doc + \
                     "  [you proposed this and the patient refused]"
            log.add("O", doc, "refusal:" + key,
                    "You proposed this examination and the patient declined, so "
                    "the refusal is yours to document.")

    return {
        "label": "Proposed corrected note — rebuilt from this encounter only",
        "S": s_text, "O": o_text,
        "A": a_entries, "P": p_entries,
        "original": {
            "label": "Original submitted note — kept exactly as you wrote it",
            "S": parsed.s_text, "O": parsed.o_text,
            "A": list(parsed.a_raw), "P": list(parsed.p_raw),
        },
        "removed": log.removed,
        "qualified": log.qualified,
        "added": log.added,
        "limitations": log.limitations,
        "rule": ("This version contains only what your encounter produced, and it "
                 "is corrected clause by clause: an unsupported fragment is struck "
                 "even when the sentence around it is sound, in all four sections. "
                 "Assessment and Plan are corrected too — a diagnosis you reason "
                 "your way to stays, a test result you never obtained does not. "
                 "Every change is listed with its reason, and anything the "
                 "encounter record cannot settle either way is listed as a "
                 "limitation rather than presented as verified. Nothing from the "
                 "hidden case has been imported: if you never asked, it is not "
                 "here. Three records are kept apart — your original submission "
                 "above, this proposed correction, and the ideal model note in the "
                 "next section, which is the only one allowed to show the case."),
    }


# ---------------------------------------------------------------------------
# Subjective and Objective: free text, edited at the offsets the audit judged
# ---------------------------------------------------------------------------

def _correct_free_text(section, text, claims, verdicts, case, log):
    """Rebuild one free-text section from its own clauses.

    Edits are applied by offset, back to front, so each surviving clause keeps
    the header and the wording the student wrote.
    """
    text = text or ""
    edits = []
    cursor = 0
    for claim in claims:
        span = _locate(text, claim, cursor)
        if span is None:
            continue
        cursor = span[1]
        rec = verdicts.take(section, claim["text"])
        if rec is None:
            continue
        verdict = rec["verdict"]
        body = text[span[0]:span[1]]

        if verdict in _FALSE_VERDICTS:
            log.remove(section, body, _reason_for(rec), rec.get("evidence"))
            edits.append((_widen_removal(text, span[0]), span[1], ""))
            continue

        partial = rec.get("partial_unsupported") or []
        if partial:
            kept, dropped = _excise(body, partial, case)
            if dropped:
                log.remove(section, dropped, _partial_reason(partial),
                           rec.get("evidence"))
                edits.append((span[0], span[1], kept))
            else:
                flag = " [unsupported: %s was never obtained in this encounter]" \
                       % _concept_phrase(partial[0])
                log.qualify(section, body, _partial_reason(partial),
                            rec.get("evidence"))
                edits.append((_widen_removal(text, span[0]), span[1], ""))
            continue

        if verdict in _QUALIFY_VERDICTS:
            log.qualify(section, body, _reason_for(rec), rec.get("evidence"))
            edits.append((_widen_removal(text, span[0]), span[1], ""))
            continue

        if verdict == "not_evaluated":
            log.limit(section, body,
                      "The audit could not resolve a checkable claim here, so it "
                      "is neither confirmed nor contradicted by your encounter "
                      "record. It has been moved out of the corrected note into this review list.")
            edits.append((_widen_removal(text, span[0]), span[1], ""))
            continue

    for start, end, replacement in sorted(edits, key=lambda e: -e[0]):
        text = text[:start] + replacement + text[end:]
    return _tidy(text)


# The join a struck clause leaves behind. "Right flank pain and no cough" loses
# its second half, and without this the corrected note ends "flank pain and" --
# which reads as a sentence the correction broke rather than one it repaired.
_DANGLING_JOIN = re.compile(
    r"(?:[,;]|\b(?:and|but|or|plus|with|as well as|along with)\b)\s*$", re.I)


def _widen_removal(text, start):
    """Move a removal's start back over the conjunction that introduced it.

    The search never crosses a line break: the words before a header are a
    different statement, and eating into them would delete a supported one.
    """
    line_start = text.rfind("\n", 0, start) + 1
    head = text[line_start:start].rstrip(" \t")
    while True:
        m = _DANGLING_JOIN.search(head)
        if not m:
            break
        head = head[:m.start()].rstrip(" \t")
    return line_start + len(head)


def _locate(text, claim, cursor):
    """The span of one claim inside its section text.

    A claim in a section's preamble carries offsets into the STRIPPED preamble
    rather than into the section, so a span that does not hold the claim text is
    re-found instead of trusted -- editing the wrong span would delete a sentence
    the student earned.
    """
    start, end = claim.get("start"), claim.get("end")
    if (isinstance(start, int) and isinstance(end, int)
            and 0 <= start < end <= len(text)
            and text[start:end] == claim["text"]):
        return start, end
    found = text.find(claim["text"], cursor)
    if found < 0:
        found = text.find(claim["text"])
    if found < 0:
        return None
    return found, found + len(claim["text"])


# Where one assertion ends and the next begins inside a single sentence. "and"
# and "but" are here because that is how a student bundles an obtained symptom
# with an invented denial: "Right flank pain and no cough".
_SEGMENT_SEP = re.compile(
    r"\s*(?:,|;|\band\b|\bbut\b|\bplus\b|\bas well as\b|\balong with\b)\s+",
    re.I)


def _segments(text):
    """(start, end) of each independently assertable piece of one sentence."""
    spans, pos = [], 0
    for m in _SEGMENT_SEP.finditer(text):
        spans.append((pos, m.start()))
        pos = m.end()
    spans.append((pos, len(text)))
    return [(a, b) for a, b in spans if text[a:b].strip()]


def _excise(text, concept_ids, case):
    """Drop the segments that carry an unsupported concept, keep the rest.

    Returns (kept_text, dropped_text). `dropped_text` is empty when the
    unsupported half could not be located, in which case the caller qualifies the
    sentence instead of cutting blindly.
    """
    surfaces = []
    for cid in concept_ids:
        surfaces.extend(_concept_surfaces(cid, case))
    spans = _segments(text)
    if len(spans) < 2:
        return text, ""
    keep, drop = [], []
    for a, b in spans:
        piece = text[a:b]
        norm = nlp.normalize(piece)
        if any(nlp.word_in(nlp.strip_negation_cue(s) or s, norm) for s in surfaces):
            drop.append(piece.strip())
        else:
            keep.append(piece.strip(" ,;"))
    if not drop or not keep:
        return text, ""
    kept = ", ".join(k for k in keep if k)
    if text.rstrip().endswith(".") and not kept.endswith("."):
        kept += "."
    return kept, " ".join(drop)


def _concept_surfaces(cid, case):
    """Every wording that releases one concept, from the live lexicon."""
    forms = list(lexicon.CORE_CONCEPTS.get(cid) or [])
    forms += list((case.get("concept_lexicon") or {}).get(cid) or [])
    return forms or [cid.replace("_", " ")]


def _concept_phrase(cid):
    return cid.replace("_", " ")


def _partial_reason(concept_ids):
    return ("Nothing in your encounter produced %s. The rest of the sentence is "
            "supported, so only this part is struck -- being asked nothing about "
            "a symptom is not the same as the patient denying it."
            % ", ".join(_concept_phrase(c) for c in concept_ids))


def _reason_for(rec):
    """Why one claim was struck or flagged, in the audit's own words."""
    explanation = (rec.get("explanation") or "").strip()
    if explanation:
        return explanation
    return ("Nothing in the encounter record supports this, so it cannot stay in "
            "a note corrected against your own encounter.")


# ---------------------------------------------------------------------------
# Assessment and Plan: reasoning survives, assertions about facts do not
# ---------------------------------------------------------------------------
#
# An Assessment entry is a hypothesis and a Plan entry is a proposal, and neither
# is a claim about what happened -- which is exactly why they used to be copied
# through untouched. But both can carry a claim about what happened, welded to the
# reasoning: "Pyelonephritis confirmed by positive urine culture" is a diagnosis
# plus a test result that does not exist. The reasoning is kept, the assertion is
# struck.

# The point in an entry where reasoning stops and a claim about evidence begins.
_EVIDENTIAL_CONNECTOR = re.compile(
    r"\b(?:confirmed (?:by|on|with)|established (?:by|with|on)|"
    r"diagnosed (?:by|on|with)|proven (?:by|on|with)|proved by|"
    r"documented (?:by|on)|based on|supported by|"
    r"as (?:shown|evidenced|demonstrated) by|evidenced by|"
    r"given (?:the|a|an|her|his) |"
    r"(?:which|that|and) (?:showed|shows|revealed|demonstrated|grew|"
    r"came back|was positive|was negative))\b", re.I)

# A fragment that has no subject of its own: it describes the result of whatever
# came before it, so it cannot outlive the clause it depends on.
_DEPENDENT_OPENER = re.compile(
    r"^(?:which|that|it|this|these|those|and|with results?|results?|"
    r"showing|revealing|demonstrating|"
    r"showed|shows|revealed|reveals|demonstrated|demonstrates|grew|"
    r"returned|resulted|came back|read as|reported as|was|were)\b", re.I)

# Wording that reports an action as already carried out.
_PAST_ACTION = re.compile(
    r"\b(?:completed|already|performed|resulted|came back|returned|"
    r"obtained|drawn|was done|were done|has been done|have been done)\b", re.I)

# Wording that asserts what an investigation showed.
_RESULT_CLAIM = re.compile(
    r"\b(?:confirmed|confirms|established|establishes|proven|proved|"
    r"diagnosed|documented as|showed|shows|showing|revealed|reveals|"
    r"demonstrated|grew|growing|positive|negative|resulted|came back|"
    r"read as|reported as)\b", re.I)

# Words that carry no clinical content on their own. A fragment made only of
# these is a stub, not a surviving diagnosis: "Acute pyelonephritis, diagnosis"
# is not a note, so the whole piece goes rather than its skeleton.
_STUB_WORDS = {
    "the", "a", "an", "of", "to", "in", "on", "and", "or", "is", "was", "with",
    "for", "at", "her", "his", "their", "she", "he", "patient", "about", "from",
    "that", "this", "these", "any", "has", "have", "had", "been", "it", "which",
    "diagnosis", "diagnoses", "dx", "impression", "assessment", "plan",
    "likely", "probable", "possible", "most", "confirmed", "established",
    "secondary", "due", "today",
}

# Claims that a discussion already took place.
_COUNSEL_PAST = re.compile(
    r"\b(?:discussed|counseled|counselled|educated|advised|instructed|"
    r"explained|reviewed with|informed|warned|went over|taught)\b", re.I)

# The same claim written without a verb of its own. A student documents a
# conversation as often in the nominal voice -- "smoking cessation counseling
# given today", "patient education provided regarding compliance" -- as in the
# active one, and reading only for the active verbs let those through untouched,
# so the corrected note went on asserting a discussion that never happened. The
# participle has to be the past/passive one: "education to be provided at
# discharge" is an intention and must survive.
_COUNSEL_PAST_NOMINAL = re.compile(
    r"\b(?:counsel(?:l)?ing|education|teaching|instructions?|advice|discussion|"
    r"precautions)\b(?:\s+\S+){0,4}?\s+(?:was|were)?\s*"
    r"(?:given|provided|done|completed|performed|delivered)\b"
    r"|\b(?:given|provided|delivered|completed)\b(?:\s+\S+){0,4}?\s+"
    r"\b(?:counsel(?:l)?ing|education|teaching|instructions?|advice)\b", re.I)

# Wording that keeps a nominal counseling phrase in the future. Without this
# "education to be provided before discharge" reads as past to the pattern above.
_COUNSEL_NOT_YET = re.compile(r"\bto be\b|\bpending\b|\bprior to\b|\bbefore\b", re.I)

_COUNSEL_FUTURE = re.compile(
    r"\b(?:will|plan to|planning to|would|intend to|going to|recommend|"
    r"should)\b", re.I)

# Generic counseling subjects, mirrored from the audit so a Plan entry can be
# matched against the topics the encounter actually recorded.
_COUNSEL_TOPICS = ["return precaution", "red flag", "warning sign", "hydration",
                   "diet", "medication", "smoking", "follow up", "side effect",
                   "full course", "hygiene"]


def _correct_entries(entries, section, verdicts, ev_index, counseled, case, log):
    """Correct one numbered section, dropping entries that survive as nothing."""
    out = []
    for entry in entries:
        rec = verdicts.take(section, entry["text"])
        kept, removals = _correct_clinical_entry(entry["text"], ev_index,
                                                 counseled, case)
        if not removals and rec is not None and rec["verdict"] in _FALSE_VERDICTS:
            # The audit found a defect this clause scan could not localize -- it
            # judges a whole entry, and "Obtain a urine culture; the UA already
            # resulted" is one entry holding a legitimate proposal and a false
            # report. Deleting it would throw away the plan along with the claim,
            # so the entry stays and is flagged where it stands.
            log.qualify(section, entry["text"], _reason_for(rec),
                        rec.get("evidence"))
            out.append(_renumber(entry, entry["text"] + _ENTRY_FLAG))
            continue
        for fragment, reason in removals:
            log.remove(section, fragment, reason,
                       rec.get("evidence") if rec else None)
        if kept.strip():
            out.append(_renumber(entry, kept.strip()))
    return out


def _renumber(entry, text):
    """Keep the student's own numbering on a corrected entry."""
    if entry.get("numbered") and entry.get("number") is not None:
        return "%d. %s" % (entry["number"], text)
    return text


def _correct_clinical_entry(text, ev_index, counseled, case):
    """Return (kept_text, [(removed_fragment, reason), ...]) for one A/P entry."""
    kept, removals = [], []
    orphaned = False
    for piece, sep in _entry_pieces_with_separators(text):
        if orphaned and _DEPENDENT_OPENER.match(nlp.normalize(piece)):
            removals.append((piece, "This describes the result of the claim "
                                    "removed immediately before it, and has no "
                                    "support of its own once that claim is gone."))
            continue
        head, dropped, reason = _correct_piece(piece, ev_index, counseled, case)
        if dropped:
            removals.append((dropped, reason))
        orphaned = bool(dropped) and not head.strip()
        if head.strip():
            kept.append((head.strip(), sep))
    if not kept:
        return "", removals
    rebuilt = ""
    for i, (piece, sep) in enumerate(kept):
        rebuilt += piece
        if i < len(kept) - 1:
            # Reuse the separator this piece actually had, so striking a
            # sentence out of the middle does not run two of them together --
            # and do not add a full stop to a piece that already ends in one.
            joiner = sep or ". "
            if piece.endswith((".", "!", "?")) and joiner.startswith("."):
                joiner = joiner[1:].lstrip() or " "
                joiner = " "
            rebuilt += joiner
    return rebuilt, removals


# A plan entry is usually several SENTENCES, not one comma-separated list:
# "CT abdomen completed and showed a tumor. Obtain a urine culture. Follow up in
# 2 days." Splitting only on commas made that one indivisible piece, so striking
# the fabricated CT result threw away the legitimate order and the follow-up
# interval with it.
_PIECE_SPLIT = re.compile(r"\s*[;,]\s+|(?<=[.!?])\s+(?=[A-Z(])")


def _entry_pieces(text):
    """One entry split into separately assertable pieces, keeping separators."""
    return [p for p, _ in _entry_pieces_with_separators(text)]


def _entry_pieces_with_separators(text):
    """(piece, separator that followed it) so a rebuilt entry still reads right."""
    out, pos = [], 0
    raw = text or ""
    for m in _PIECE_SPLIT.finditer(raw):
        piece = raw[pos:m.start()]
        if piece.strip():
            sep = m.group(0)
            out.append((piece, ". " if sep.strip() in ("", ".") or
                        piece.rstrip().endswith((".", "!", "?")) else ", "))
        pos = m.end()
    tail = raw[pos:]
    if tail.strip():
        out.append((tail, ""))
    return out


def _correct_piece(piece, ev_index, counseled, case):
    """Return (kept, dropped, reason) for one piece of an A/P entry."""
    reason = _piece_defect(piece, ev_index, counseled, case)
    if not reason:
        return piece, "", ""
    for cut in _cut_points(piece):
        head = piece[:cut].rstrip(" ,;:-—(")
        tail = piece[cut:].strip()
        if not head.strip() or not tail:
            continue
        if not _has_clinical_content(head):
            continue
        # The head has to be clean and the tail has to be where the defect
        # lives, or the cut would leave the false claim standing and throw away
        # the wrong half of the entry.
        if _piece_defect(head, ev_index, counseled, case):
            continue
        if not _piece_defect(tail, ev_index, counseled, case):
            continue
        return head, tail, reason
    return "", piece.strip(), reason


# Punctuation a student uses to weld a result onto a diagnosis when they do not
# reach for a connector: "Acute pyelonephritis - urine culture grew E. coli",
# "Acute pyelo: culture positive", "Acute pyelo (CT showed a stone)", and the
# plain sentence break. Cutting here keeps the reasoning the student earned.
_PUNCT_CUT = re.compile(r"\s+[-–—]\s+|\s*:\s+|\s+\(|(?<=[a-z0-9])\.\s+")


def _cut_points(piece):
    """Where an entry could be split so the reasoning survives the claim.

    The evidential connector is tried first because it is the most explicit
    boundary; punctuation is the fallback, earliest first, so the smallest
    defensible amount of the student's own text is struck.
    """
    points = []
    m = _EVIDENTIAL_CONNECTOR.search(piece)
    if m:
        points.append(m.start())
    for p in sorted(x.start() for x in _PUNCT_CUT.finditer(piece)):
        if p not in points:
            points.append(p)
    return points


def _has_clinical_content(text):
    """Does this fragment still say something clinical once the claim is cut?"""
    return any(len(t) > 2 and t not in _STUB_WORDS
               for t in nlp.normalize(text).split())


def _piece_defect(piece, ev_index, counseled, case):
    return (_investigation_defect(piece, ev_index)
            or _counseling_defect(piece, counseled, case))


# How a student actually writes an investigation, mapped to the canonical name
# the encounter record files it under. The shared claim reader knows the spelled
# out forms only, so "urine cx grew E. coli" named no investigation at all and a
# culture result that never existed survived into the corrected note unflagged.
# The value on the right must stay a name the evidence index uses, or a result
# the encounter really did produce would read as missing.
_INVESTIGATION_ABBREVIATIONS = {
    "urine cx": "urine culture", "ucx": "urine culture", "u cx": "urine culture",
    "blood cx": "blood culture", "bcx": "blood culture",
    "ua": "urinalysis", "cxr": "chest x-ray",
}


# Studies that are the same study under two names. A station that hands the
# student a urine dipstick result has produced the urinalysis they then document,
# so striking "UA showed pyuria" would delete accurate documentation of a result
# the encounter really did release.
_EQUIVALENT_INVESTIGATIONS = {
    "urinalysis": ("urine dipstick", "dipstick"),
    "urine dipstick": ("urinalysis",),
    "dipstick": ("urinalysis",),
}


def _investigations_named(text):
    """Every investigation this text names, abbreviations included."""
    found = list(claims_mod.investigations_mentioned(text))
    norm = nlp.normalize(text)
    for short, canonical in _INVESTIGATION_ABBREVIATIONS.items():
        if canonical not in found and nlp.word_in(short, norm):
            found.append(canonical)
    return found


def _was_produced(investigation, obtained):
    """Did the encounter produce this study, under this name or an equal one?"""
    if investigation in obtained:
        return True
    return any(alias in obtained
               for alias in _EQUIVALENT_INVESTIGATIONS.get(investigation, ()))


def _investigation_defect(text, ev_index):
    """Does this report a test, or a test result, the encounter never produced?

    Proposing an investigation is always legitimate -- "Obtain a urine culture"
    is what a plan is for. Saying it was done, or saying what it showed, is a
    claim about the encounter and has to be earned there.
    """
    mentioned = _investigations_named(text)
    if not mentioned:
        return ""
    reported_done = (claims_mod.action_status(text) == "done"
                     or bool(_PAST_ACTION.search(text)))
    asserts_result = (claims_mod.asserts_a_result(text)
                      or bool(_RESULT_CLAIM.search(text)))
    if not reported_done and not asserts_result:
        return ""
    obtained = ev_index.get("investigations") or set()
    missing = [inv for inv in mentioned if not _was_produced(inv, obtained)]
    if not missing:
        return ""
    return ("No %s result is in your encounter record, so this reports a test "
            "that was never done. Proposing the test is legitimate; reporting "
            "what it showed is not." % missing[0])


def _counseling_defect(text, counseled, case):
    """Does this say a discussion happened that the encounter never recorded?

    Only a claim with NO discussion behind it at all is struck here. When the
    encounter did record a plan discussion but under different topic labels, the
    mismatch is left to the entry-level audit, which flags the entry instead of
    deleting it: the labels the ledger keeps are coarser than the words a student
    writes -- "finish the full course of antibiotics" is filed under
    `medication` -- and deleting on a label mismatch would take a conversation
    that demonstrably happened out of the note.
    """
    if not _says_counseling_happened(text):
        return ""
    if _COUNSEL_FUTURE.search(text or ""):
        return ""
    if counseled:
        return ""
    subjects = _counseling_subjects(text, case)
    return ("Your encounter record contains no plan discussion at all%s, and "
            "this is written as something that already happened. Either have "
            "the conversation in the room, or word it as an intention."
            % (", including nothing about %s" % subjects[0] if subjects else ""))


def _says_counseling_happened(text):
    """Is this written as a conversation that already took place?

    The active voice and the nominal voice are the same claim, so both are read.
    The nominal one is only past when nothing in the phrase defers it: "return
    precautions to be given at discharge" is a plan, not a report.
    """
    text = text or ""
    if _COUNSEL_PAST.search(text):
        return True
    return (bool(_COUNSEL_PAST_NOMINAL.search(text))
            and not _COUNSEL_NOT_YET.search(text))


def _counseling_subjects(text, case):
    subjects = []
    for item in (case.get("plan_expectations") or {}).get("education", []):
        if nlp.matches_any(text, [item]):
            subjects.append(item)
    norm = nlp.normalize(text)
    for generic in _COUNSEL_TOPICS:
        if generic in norm:
            subjects.append(generic)
    return sorted(set(subjects))


def _is_objective_concept(concept, ledger):
    for ev in ledger.events:
        if concept in (ev["meta"].get("concepts") or {}):
            return ev["kind"] in (evidence.EXAM_FINDING, evidence.EXAM_ACTION)
    return False


# A header whose body was struck entirely: "Abd:" on its own is not a finding,
# and leaving it in reads as an examination that produced nothing.
_EMPTY_HEADER = re.compile(r"^[A-Za-z][A-Za-z /&']{0,34}:$")


def _tidy(text):
    lines = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped in (".", ";", ",", "") or _EMPTY_HEADER.match(stripped):
            if not lines or lines[-1] != "":
                lines.append("")
            continue
        stripped = re.sub(r"\s{2,}", " ", stripped)
        stripped = re.sub(r"\s+([.,;])", r"\1", stripped)
        stripped = re.sub(r"([:;,])\s*([.;,])", r"\1", stripped)
        # A struck clause can leave the conjunction that introduced it at the
        # start of what survives: "HPI: and right flank pain".
        stripped = re.sub(r"(?<=:)\s*(?:and|but|or|plus)\s+", " ", stripped,
                          flags=re.I)
        stripped = _DANGLING_JOIN.sub("", stripped)
        stripped = stripped.strip(" ;,")
        lines.append(stripped)
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Teaching resource 2: the ideal encounter
# ---------------------------------------------------------------------------

def ideal_comparison(case, ledger, chk):
    released = ledger.released_facts()
    performed = ledger.performed_maneuvers()

    extra_questions = []
    for fact in case["facts"]:
        if fact["id"] in released:
            continue
        extra_questions.append({
            "category": fact.get("category", ""),
            "would_have_asked": _example_question(
                ((fact.get("triggers") or {}).get("any") or [""])[0], fact),
            "would_have_learned": fact.get("value", ""),
        })

    extra_exams = []
    for mid, findings in case.get("exam_findings", {}).items():
        if mid in performed:
            continue
        man = physexam.CATALOG_BY_ID.get(mid)
        if not man:
            continue
        extra_exams.append({
            "maneuver": man["label"],
            "region": man["region"],
            "would_have_found": " ".join(f["text"] for f in findings)[:220],
            "key": any(f.get("key_finding") for f in findings),
        })

    return {
        "model_note": case["model_note"],
        "extra_questions": extra_questions,
        "extra_exams": extra_exams,
        "coaching": case.get("ideal_encounter_extras", []),
        "rule": ("This section is allowed to show the hidden case. It exists to "
                 "show what a complete encounter would have produced — it is NOT "
                 "what your note should have said, because you cannot document "
                 "what you did not obtain. Compare it with the corrected note "
                 "above: the gap between them is your encounter, not your "
                 "writing."),
    }


# ---------------------------------------------------------------------------

def _worked_examples(audit_result, chk, case, interp):
    ex = []
    unsupported = [c for c in audit_result["claims"] if c["verdict"] == "unsupported"]
    if unsupported:
        c = unsupported[0]
        ex.append({
            "kind": "documentation",
            "before": c["text"],
            "after": "(remove it, or ask the question in the encounter first)",
            "note": "A negative has to be earned in the room.",
        })
    for item in chk["history"]:
        if item["status"] == "omitted":
            fact = next((f for f in case["facts"]
                         if f.get("checklist") == item["id"]), None)
            if fact:
                ex.append({
                    "kind": "question",
                    "before": "(not asked)",
                    "after": _example_question("", fact),
                    "note": "Would have established: " + fact.get("value", ""),
                })
            break
    weak_transitions = next(
        (i for i in interp["acir"]["items"]
         if i["name"] == "Transitional statements" and (i["score"] or 5) < 5), None)
    if weak_transitions:
        ex.append({
            "kind": "transition",
            "before": "So, do you smoke?",
            "after": ("Now I'd like to ask about some habits — smoking, alcohol, "
                      "recreational drugs — because they change what I need to "
                      "worry about and what I can safely prescribe."),
            "note": "The manual's mastery anchor gives the reason, not just the topic.",
        })
    weak_summary = next(
        (i for i in interp["acir"]["items"]
         if i["name"].endswith("summarizing") and (i["score"] or 5) < 5), None)
    if weak_summary:
        ex.append({
            "kind": "summary",
            "before": "(no summary)",
            "after": ("Let me make sure I have this right: two days of burning "
                      "when you urinate, back pain on the right since yesterday, "
                      "with fever, chills and one episode of vomiting. Have I "
                      "missed anything?"),
            "note": "Three items, then a pause long enough for a correction.",
        })
    return ex


def _not_assessed(session, chk, interp):
    mode = session.row["interaction_mode"]
    items = list(chk.get("not_assessed", [])) + list(interp.get("not_assessed", []))
    items.append(
        "Hands-on technique of any kind. This app scores examination selection, "
        "sequence, stated technique, interpretation and documentation.")
    if mode == "type":
        items.append(
            "Pacing as a spoken quality, and anything carried by tone of voice — "
            "this attempt was typed, so pauses reflect typing speed rather than "
            "conversational rhythm.")
    return items
