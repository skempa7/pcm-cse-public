"""What the visit player needs to stage a demonstrated visit.

The review's visit record (visit.py) is the answer key and stays lean. This
builds the staging for the same visit on demand: the patient's appearance
and speaking pace, her posture and gestures as the visit unfolds, and the
technique demonstration for every examination. Turn ids match the visit's
(`v1`, `v2`, ... in timeline order), so the player and the review always
agree on which moment is which.
"""

from __future__ import annotations

from .. import cases, evidence, physexam, presentation
from . import visit as V

_POSTURES = ("seated", "supine", "standing", "prone")


def _position(item, ledger):
    """A posture change the demonstrated clinician helped with, if any."""
    for eid in item.get("event_ids", []):
        meta = (ledger.get(eid) or {}).get("meta") or {}
        if meta.get("position") in _POSTURES:
            return meta["position"]
    return None


def _components(item, ledger):
    for eid in item.get("event_ids", []):
        ev = ledger.get(eid) or {}
        if ev.get("kind") == "exam_action":
            return list((ev.get("meta") or {}).get("components") or [])
    return []


def build(case_id: str, variant_id: str):
    walkthrough = V.load_walkthrough(case_id, variant_id)
    if walkthrough is None:
        raise ValueError("No demonstrated visit exists for that presentation.")
    case = cases.resolve(case_id, variant_id)
    events = walkthrough.get("ledger", [])
    ledger = {e["seq"]: e for e in events}
    posture = "seated"
    turns = []
    for i, item in enumerate(walkthrough.get("timeline", [])):
        entry = {"id": "v%d" % (i + 1)}
        moved = _position(item, ledger)
        if moved:
            posture = moved
        if item.get("kind") == "dialogue":
            entry["why"] = item.get("why", "")
            # What she has said so far decides whether she indicates where it hurts.
            last = max(item.get("event_ids") or [0])
            seen = evidence.Ledger([e for e in events if e["seq"] <= last])
            entry["affect"] = presentation.affect(case, seen)
            entry["gesture"] = presentation.gesture(case, seen)
        elif item.get("maneuver_id"):
            components = _components(item, ledger)
            plan = physexam.demonstration(item["maneuver_id"], components)
            entry.update(components=components, plan=plan, why=item.get("why", ""))
        else:
            entry["why"] = item.get("why", "")
        entry["posture"] = posture
        turns.append(entry)
    opening = evidence.Ledger([])
    return {
        "case_id": case_id,
        "variant_id": variant_id,
        "appearance": presentation.appearance(case),
        "demeanor": presentation.demeanor(case, opening),
        "affect": presentation.affect(case, opening),
        "gesture": presentation.gesture(case, opening),
        "respiratory_rate": _respiratory_rate(walkthrough),
        "turns": turns,
    }


def _respiratory_rate(walkthrough):
    vitals = (walkthrough.get("doorway") or {}).get("vitals") or {}
    try:
        rate = int(str(vitals.get("R") or vitals.get("rr") or "16").split()[0])
    except ValueError:
        return 16
    return rate if 4 <= rate <= 60 else 16
