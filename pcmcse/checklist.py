"""The case-specific standardized-patient checklist.

Modeled on the four worked checklists PCM supplies (the "Joe Smith" list in the
student manual and the back pain / rash / malaise lists on the interpersonal
skills slides).  Syllabus, p.5: credit is for historical items that were *asked*
and physical components *performed correctly*.

Four states are kept distinct, because collapsing them hides where an encounter
actually went wrong:

  obtained     the question was asked and the patient answered
  asked_only   the question was asked but produced no information
  selected     the maneuver was named but not specific enough to perform
  omitted      never attempted
"""

from __future__ import annotations

from . import evidence, nlp, physexam


def score(ledger, case):
    facts_by_checklist = {}
    for fact in case.get("facts", []):
        if fact.get("checklist"):
            facts_by_checklist.setdefault(fact["checklist"], []).append(fact["id"])

    released = ledger.released_facts()
    performed = ledger.performed_maneuvers()
    refusals = ledger.refused_exams()
    courtesy = ledger.courtesy_done()
    attempted = _attempted_maneuvers(ledger)

    history = []
    for item in case["checklist"]["history"]:
        fids = facts_by_checklist.get(item["id"], [])
        hit = next((released[f] for f in fids if f in released), None)
        history.append({
            "id": item["id"], "text": item["text"],
            "status": "obtained" if hit else "omitted",
            "time": _t(hit) if hit else "",
            "quote": hit["text"] if hit else "",
        })

    physical = []
    for item in case["checklist"]["physical"]:
        physical.append(_score_physical(item, performed, attempted, refusals,
                                        courtesy, ledger))

    h_yes = sum(1 for h in history if h["status"] == "obtained")
    p_yes = sum(1 for p in physical if p["status"] == "performed")

    return {
        "history": history,
        "physical": physical,
        "history_score": {"yes": h_yes, "total": len(history)},
        "physical_score": {"performed": p_yes, "total": len(physical)},
        "note": ("This checklist is a separate instrument from the SOAP note "
                 "grading table. The course does not state how they combine, so "
                 "they are not added together."),
        "not_assessed": [
            "Whether a maneuver was performed with correct technique (hand "
            "placement, pressure, stethoscope contact on skin). A typed or "
            "spoken declaration cannot establish this.",
            "Whether the stethoscope was actually placed on skin rather than "
            "over the gown.",
            "Whether OMT was performed with correct technique.",
        ],
    }


def _t(ev):
    return "%d:%02d" % (ev["t_ms"] // 60000, (ev["t_ms"] // 1000) % 60)


def _attempted_maneuvers(ledger):
    """Maneuvers named but too vague to release findings."""
    out = {}
    for ev in ledger.by_kind(evidence.EXAM_ACTION):
        if ev["meta"].get("status") in ("completed", "performed"):
            continue
        out.setdefault(ev["meta"].get("maneuver_id") or "unresolved", []).append(ev)
    return out


def _score_physical(item, performed, attempted, refusals, courtesy, ledger):
    base = {"id": item["id"], "text": item["text"], "status": "omitted",
            "detail": "", "time": ""}

    if item.get("refusal"):
        ev = refusals.get(item["refusal"])
        if ev:
            base["status"] = "performed"
            base["detail"] = ("Proposed appropriately; the patient refused, which "
                              "is the expected outcome and is documentable in "
                              "Objective.")
            base["time"] = _t(ev)
        else:
            base["detail"] = ("Never proposed. The syllabus asks you to say 'At "
                              "this point, I would do a (xxx) exam.' so the "
                              "refusal goes on the record.")
        return base

    if item.get("courtesy_all"):
        missing = [c for c in item["courtesy_all"] if c not in courtesy]
        if not missing:
            base["status"] = "performed"
            base["detail"] = "All three components done."
        else:
            labels = [physexam.COURTESY_BY_ID[c]["label"] for c in missing]
            base["detail"] = ("Needs all three for credit. Missing: %s."
                              % ", ".join(labels))
        return base

    if item.get("courtesy"):
        if item["courtesy"] in courtesy:
            base["status"] = "performed"
            base["detail"] = "Stated during the encounter."
        else:
            base["detail"] = "Not stated during the encounter."
        base["not_assessed"] = "Whether it was done correctly cannot be observed here."
        return base

    mid = item.get("maneuver")
    if not mid:
        return base

    rec = performed.get(mid)
    if not rec:
        if mid in attempted:
            base["status"] = "selected"
            latest = attempted[mid][-1]
            status = latest["meta"].get("status")
            messages = {
                "interrupted": "This examination was interrupted before completion; it released no findings.",
                "in_progress": "This examination is still in progress; findings are not available yet.",
                "not_simulated": "This examination has no authored result in this simulation; no finding was released.",
            }
            base["detail"] = messages.get(status) or (
                "You named this examination but did not specify it enough to perform: %s"
                % latest["meta"].get("reason", ""))
        return base

    need = item.get("components") or []
    missing = [c for c in need if c not in rec["components"]]
    if missing:
        base["status"] = "partial"
        base["detail"] = "Performed, but not covering: %s." % ", ".join(missing)
        return base

    if item.get("order_before"):
        my_seq = min(rec["events"])
        later = []
        for other in item["order_before"]:
            orec = performed.get(other)
            if orec and min(orec["events"]) < my_seq:
                later.append(other)
        if later:
            base["status"] = "partial"
            base["detail"] = ("Performed, but after %s. The abdominal exam is "
                              "auscultated before it is palpated or percussed."
                              % ", ".join(later))
            return base

    base["status"] = "performed"
    base["detail"] = "Performed with the expected components."
    return base
