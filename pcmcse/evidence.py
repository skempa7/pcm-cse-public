"""The encounter evidence record.

This is the foundation of the grader and it is kept strictly separate from the
hidden case.  A fact being true of the patient does **not** put it in here.
Only things that actually happened during the encounter are recorded:

  * what the student asked and what the patient answered
  * what the patient volunteered
  * authorized station information (doorway text, supplied vitals/results)
  * examination actions and the findings actually released
  * refused or under-specified examinations
  * counselling and plans actually discussed
  * uncertain or interrupted interactions

`released_concepts()` is the only thing the documentation audit may consult.
"""

from __future__ import annotations

import json

# Event kinds
STATION_INFO = "station_info"
STUDENT = "student_utterance"
PATIENT = "patient_reply"
SIM = "simulator"
EXAM_ACTION = "exam_action"
EXAM_FINDING = "exam_finding"
EXAM_REFUSED = "exam_refused"
COUNSELING = "counseling"
COURTESY = "courtesy"
UNCERTAIN = "uncertain"
SYSTEM = "system"


class Ledger:
    def __init__(self, events=None):
        self.events = list(events or [])

    # -- writing ----------------------------------------------------------
    def add(self, kind, text="", *, t_ms=0, phase="encounter", meta=None):
        ev = {
            "seq": len(self.events) + 1,
            "t_ms": int(t_ms),
            "phase": phase,
            "kind": kind,
            "text": text,
            "meta": meta or {},
        }
        self.events.append(ev)
        return ev

    # -- reading ----------------------------------------------------------
    def by_kind(self, *kinds):
        return [e for e in self.events if e["kind"] in kinds]

    def to_json(self):
        return json.dumps(self.events)

    @classmethod
    def from_json(cls, raw):
        try:
            return cls(json.loads(raw) if raw else [])
        except ValueError:
            return cls([])

    # -- derived views ----------------------------------------------------
    def released_facts(self) -> dict:
        """fact_id -> the event that released it."""
        out = {}
        for ev in self.events:
            for fid in ev["meta"].get("facts_released", []):
                out.setdefault(fid, ev)
        return out

    def released_concepts(self) -> dict:
        """concept id -> support record.

        A concept lands here only when the encounter actually produced it.
        Each record carries the polarity the encounter established, the
        source kind, and the timestamp -- everything the audit needs to show
        its work.
        """
        out = {}
        for ev in self.events:
            for concept, spec in (ev["meta"].get("concepts") or {}).items():
                if isinstance(spec, str):
                    spec = {"polarity": "positive", "value": spec}
                rec = {
                    "concept": concept,
                    "polarity": spec.get("polarity", "positive"),
                    "value": spec.get("value", ""),
                    "scope": spec.get("scope", []),
                    "source_kind": ev["kind"],
                    "source_seq": ev["seq"],
                    "t_ms": ev["t_ms"],
                    "quote": ev["text"],
                    "authorized": ev["kind"] == STATION_INFO,
                    "volunteered": bool(ev["meta"].get("volunteered")),
                }
                prev = out.get(concept)
                # Keep the earliest support, but let a later positive answer
                # override a placeholder.
                if prev is None or (prev["polarity"] != rec["polarity"]
                                    and rec["source_kind"] == PATIENT
                                    and prev["source_kind"] != PATIENT):
                    out[concept] = rec
        return out

    def performed_maneuvers(self) -> dict:
        """maneuver_id -> {'components': set, 'scopes': set, 'events': [...]}"""
        out = {}
        for ev in self.by_kind(EXAM_ACTION):
            mid = ev["meta"].get("maneuver_id")
            # "completed" is the examination lifecycle's terminal state;
            # "performed" is the older name, kept so an attempt recorded before
            # the lifecycle existed still reads correctly.
            if not mid or ev["meta"].get("status") not in ("completed",
                                                           "performed"):
                continue
            rec = out.setdefault(mid, {"components": set(), "scopes": set(),
                                       "events": [], "label": ev["meta"].get("label", mid)})
            rec["components"].update(ev["meta"].get("components", []))
            rec["scopes"].update(ev["meta"].get("scopes", []))
            rec["events"].append(ev["seq"])
        return out

    def refused_exams(self) -> dict:
        out = {}
        for ev in self.by_kind(EXAM_REFUSED):
            key = ev["meta"].get("refusable")
            if key:
                out[key] = ev
        return out

    def courtesy_done(self) -> set:
        done = set()
        for ev in self.by_kind(COURTESY):
            cid = ev["meta"].get("courtesy_id")
            if cid:
                done.add(cid)
        return done

    def counseling_topics(self) -> dict:
        out = {}
        for ev in self.by_kind(COUNSELING):
            for topic in ev["meta"].get("topics", []):
                out.setdefault(topic, ev)
        return out

    def student_turns(self):
        return self.by_kind(STUDENT)

    def uncertain_segments(self):
        return [e for e in self.events
                if e["kind"] == UNCERTAIN or e["meta"].get("uncertain")]

    def interruptions(self):
        return [e for e in self.by_kind(SYSTEM)
                if e["meta"].get("interruption")]

    def summary_counts(self):
        return {
            "student_turns": len(self.student_turns()),
            "patient_replies": len(self.by_kind(PATIENT)),
            "facts_released": len(self.released_facts()),
            "volunteered": len([e for e in self.by_kind(PATIENT)
                                if e["meta"].get("volunteered")]),
            "exam_actions": len([e for e in self.by_kind(EXAM_ACTION) if e["meta"].get("status") != "in_progress"]),
            "maneuvers_performed": len(self.performed_maneuvers()),
            "refusals": len(self.refused_exams()),
            "uncertain": len(self.uncertain_segments()),
            "interruptions": len(self.interruptions()),
        }

    def transcript(self):
        """Human-readable transcript for the post-submission review."""
        rows = []
        for ev in self.events:
            rows.append({
                "seq": ev["seq"],
                "time": _fmt(ev["t_ms"]),
                "t_ms": ev["t_ms"],
                "kind": ev["kind"],
                "text": ev["text"],
                "meta": ev["meta"],
            })
        return rows


def _fmt(ms):
    s = max(0, int(ms // 1000))
    return "%d:%02d" % (s // 60, s % 60)
