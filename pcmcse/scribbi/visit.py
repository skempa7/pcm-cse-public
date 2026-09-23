"""The visit Scribbi listened to.

A library visit is one of the demonstrated encounters that already ship with
the app (pcmcse/teaching/lessons). Each has the conversation, the examination
steps with their findings, and an example note whose statements are linked to
the exact moments in the visit. Scribbi drafts from that note, so every line
of the draft can be traced back to what happened.

The visit returned here is what the student sees: patient, chart, and an
ordered list of turns. Evidence references in the draft point at turn ids
("v12") or at the chart ("chart:vitals", "chart:result:ua_dip").
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .. import cases, physexam, station_info

_LESSONS = Path(__file__).resolve().parent.parent / "teaching" / "lessons"
_cache = {}


def load_walkthrough(case_id: str, variant_id: str = "base"):
    path = _LESSONS / (case_id + ".json")
    if not path.exists():
        return None
    key = (case_id, str(path.stat().st_mtime))
    if key not in _cache:
        if len(_cache) > 12:
            _cache.clear()
        _cache[key] = json.loads(path.read_text(encoding="utf-8"))
    lesson = _cache[key]
    return next((w for w in lesson.get("walkthroughs", []) if w.get("variant_id") == variant_id), None)


_paths_cache = {}


def library_paths() -> list:
    """Every (case, variant) with a demonstrated visit Scribbi can draft from.

    Reading every lesson file costs seconds in the browser engine, so the list
    is cached against the lesson files' modification times."""
    stamp = tuple(sorted((p.name, p.stat().st_mtime) for p in _LESSONS.glob("*.json")))
    if _paths_cache.get("stamp") != stamp:
        out = []
        for case in cases.index():
            path = _LESSONS / (case["id"] + ".json")
            if not path.exists():
                continue
            lesson = json.loads(path.read_text(encoding="utf-8"))
            for w in lesson.get("walkthroughs", []):
                out.append({"case_id": case["id"], "variant_id": w["variant_id"],
                            "variant_label": w.get("variant_label", "Base presentation")})
        _paths_cache.clear()
        _paths_cache.update(stamp=stamp, paths=out)
    return [dict(p) for p in _paths_cache["paths"]]


def _mmss(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    return "%d:%02d" % (s // 60, s % 60)


def _region(maneuver_id):
    m = physexam.CATALOG_BY_ID.get(maneuver_id or "")
    return m["region"] if m else ""


def _vitals_text(vitals: dict) -> str:
    order = ["T", "P", "BP", "R", "Pulse Ox", "Ht", "Wt"]
    keys = [k for k in order if k in vitals] + [k for k in vitals if k not in order]
    return ", ".join("%s %s" % (k, vitals[k]) for k in keys)


def library_visit(case_id: str, variant_id: str = "base"):
    """(visit, walkthrough, resolved case) for a library presentation."""
    walkthrough = load_walkthrough(case_id, variant_id)
    if walkthrough is None:
        raise ValueError("No demonstrated visit exists for that presentation.")
    case = cases.resolve(case_id, variant_id)
    ledger = {e["seq"]: e for e in walkthrough.get("ledger", [])}
    door = walkthrough.get("doorway", {})
    doorway_lines = [line for line in station_info.doorway(case)
                     if not re.search(r"\b\d+\s+minutes?\b", line)]

    turns = []
    event_to_ref = {}
    clock = 0.0
    for item in walkthrough.get("timeline", []):
        tid = "v%d" % (len(turns) + 1)
        base = {"id": tid, "section": item.get("section", ""), "t": _mmss(clock)}
        if item.get("kind") == "dialogue":
            turn = dict(base, kind="talk", student=item.get("student", ""),
                        patient=item.get("patient", ""))
            clock += 12 + min(40, len(item.get("patient", "")) / 9.0)
        elif item.get("maneuver_id") and item.get("finding"):
            region = _region(item["maneuver_id"])
            turn = dict(base, kind="exam", label=item.get("action", ""),
                        finding=item.get("finding", ""), region=region,
                        maneuver_id=item["maneuver_id"],
                        felt=region == "Osteopathic")
            clock += float(item.get("duration_s") or 20)
        elif item.get("finding"):
            turn = dict(base, kind="step", label=item.get("action", ""), detail=item.get("finding", ""))
            clock += 8
        else:
            turn = dict(base, kind="step", label=item.get("action", ""), detail="")
            clock += 8
        turns.append(turn)
        for eid in item.get("event_ids", []):
            event_to_ref.setdefault(eid, tid)

    supplied = [{"id": r.get("id", ""), "label": r.get("label", ""), "value": r.get("value", "")}
                for r in door.get("supplied_results", [])]
    for seq, ev in ledger.items():
        meta = ev.get("meta") or {}
        if ev.get("kind") != "station_info":
            continue
        if meta.get("vitals"):
            event_to_ref[seq] = "chart:vitals"
        elif meta.get("supplied_id"):
            event_to_ref[seq] = "chart:result:" + meta["supplied_id"]
        elif meta.get("doorway"):
            event_to_ref[seq] = "chart:doorway"

    patient = walkthrough.get("patient") or {}
    visit = {
        "source": "library",
        "case_id": case_id,
        "variant_id": variant_id,
        "variant_label": walkthrough.get("variant_label", ""),
        "title": case.get("title", ""),
        "system": case.get("system", ""),
        "station_label": case.get("hidden_label", "Station"),
        # Age is withheld from the posted brief everywhere in the app; it is
        # something the student learns by asking, so the header leaves it out.
        "patient": {"name": patient.get("name") or case["patient"].get("name", ""),
                    "sex": patient.get("sex") or case["patient"].get("sex", "")},
        "doorway": doorway_lines,
        "vitals": door.get("vitals") or {},
        "vitals_text": _vitals_text(door.get("vitals") or {}),
        "supplied": supplied,
        "turns": turns,
        "length": _mmss(clock),
        "counts": {"talk": sum(1 for t in turns if t["kind"] == "talk"),
                   "exam": sum(1 for t in turns if t["kind"] == "exam")},
    }
    return visit, walkthrough, case, event_to_ref


def examined_regions(visit) -> set:
    return {t["region"] for t in visit["turns"] if t["kind"] == "exam" and t.get("region")}


def visit_text(visit) -> str:
    """Everything said or found in the visit, for topic detection."""
    parts = list(visit.get("doorway", []))
    for t in visit["turns"]:
        if t["kind"] == "talk":
            parts += [t.get("student", ""), t.get("patient", "")]
        elif t["kind"] == "exam":
            parts += [t.get("label", ""), t.get("finding", "")]
        else:
            parts += [t.get("label", ""), t.get("detail", "")]
    parts += [r["label"] + " " + r["value"] for r in visit.get("supplied", [])]
    return "\n".join(p for p in parts if p)


def turn_by_id(visit, ref):
    if ref.startswith("chart:"):
        if ref == "chart:vitals":
            return {"id": ref, "kind": "chart", "label": "Vital signs", "text": visit.get("vitals_text", "")}
        if ref.startswith("chart:result:"):
            rid = ref.split(":", 2)[2]
            r = next((x for x in visit.get("supplied", []) if x["id"] == rid), None)
            if r:
                return {"id": ref, "kind": "chart", "label": r["label"], "text": r["value"]}
        return {"id": ref, "kind": "chart", "label": "Doorway information",
                "text": " ".join(visit.get("doorway", []))}
    return next((t for t in visit["turns"] if t["id"] == ref), None)


# --------------------------------------------------------------------------
# A student's own submitted Chat CSE attempt as the visit
# --------------------------------------------------------------------------

def attempt_visit(session):
    """(visit, event_to_ref, turn_concepts) from a submitted attempt's ledger.

    Only what happened in that attempt appears: the student's questions, the
    patient's replies, completed examinations with the findings they
    released, and the posted chart."""
    from .. import evidence as EV
    case = session.case
    turns, event_to_ref, concepts = [], {}, {}
    talk = None
    exam_by_mid = {}

    def add(turn, ev):
        turn["id"] = "v%d" % (len(turns) + 1)
        turns.append(turn)
        return turn

    for ev in session.ledger.events:
        kind, meta, seq = ev.get("kind"), ev.get("meta") or {}, ev.get("seq")
        t = _mmss((ev.get("t_ms") or 0) / 1000.0)
        if kind == EV.STUDENT:
            talk = add({"kind": "talk", "section": "", "t": t, "student": ev.get("text", ""), "patient": ""}, ev)
            event_to_ref[seq] = talk["id"]
        elif kind == EV.PATIENT:
            if talk is None:
                talk = add({"kind": "talk", "section": "", "t": t, "student": "", "patient": ""}, ev)
            talk["patient"] = (talk["patient"] + " " + (ev.get("text") or "")).strip()
            event_to_ref[seq] = talk["id"]
        elif kind == EV.EXAM_ACTION and meta.get("status") in ("completed", "performed"):
            mid = meta.get("maneuver_id")
            cat = physexam.CATALOG_BY_ID.get(mid or "", {})
            region = cat.get("region", "")
            turn = add({"kind": "exam", "section": "", "t": t, "label": meta.get("label") or cat.get("label", mid or "Examination"),
                        "finding": "", "region": region, "maneuver_id": mid, "felt": region == "Osteopathic"}, ev)
            if mid:
                exam_by_mid[mid] = turn
            event_to_ref[seq] = turn["id"]
            talk = None
        elif kind == EV.EXAM_FINDING:
            turn = exam_by_mid.get(meta.get("maneuver_id"))
            if turn is not None:
                turn["finding"] = (turn["finding"] + " " + (ev.get("text") or "")).strip()
                event_to_ref[seq] = turn["id"]
        elif kind == EV.EXAM_REFUSED:
            turn = add({"kind": "step", "section": "", "t": t, "label": "Sensitive examination proposed and declined",
                        "detail": ev.get("text", "")}, ev)
            event_to_ref[seq] = turn["id"]
            talk = None
        elif kind == EV.STATION_INFO:
            if meta.get("vitals"):
                event_to_ref[seq] = "chart:vitals"
            elif meta.get("supplied_id"):
                event_to_ref[seq] = "chart:result:" + meta["supplied_id"]
            elif meta.get("doorway"):
                event_to_ref[seq] = "chart:doorway"
        ref = event_to_ref.get(seq)
        if ref and not ref.startswith("chart:"):
            concepts.setdefault(ref, set()).update((meta.get("concepts") or {}).keys())

    # An examination that released nothing is not evidence of any finding.
    for turn in turns:
        if turn["kind"] == "exam" and not turn["finding"]:
            turn["finding"] = "(No finding was released for this action.)"
            turn["no_finding"] = True
    station = case.get("station") or {}
    vitals = station.get("vitals") or {}
    duration = max([e.get("t_ms") or 0 for e in session.ledger.events] + [0]) / 1000.0
    visit = {
        "source": "attempt",
        "case_id": case.get("id"),
        "variant_id": case.get("variant_id", "base"),
        "variant_label": "",
        "title": case.get("title", ""),
        "system": case.get("system", ""),
        "station_label": case.get("hidden_label", "Station"),
        "patient": {"name": case["patient"].get("name", ""), "sex": case["patient"].get("sex", "")},
        "doorway": [line for line in station_info.doorway(case) if not re.search(r"\b\d+\s+minutes?\b", line)],
        "vitals": vitals,
        "vitals_text": _vitals_text(vitals),
        "supplied": [{"id": r.get("id", ""), "label": r.get("label", ""), "value": r.get("value", "")}
                     for r in station.get("supplied_results", [])],
        "turns": turns,
        "length": _mmss(duration),
        "counts": {"talk": sum(1 for t in turns if t["kind"] == "talk"),
                   "exam": sum(1 for t in turns if t["kind"] == "exam" and not t.get("no_finding"))},
    }
    return visit, event_to_ref, concepts
