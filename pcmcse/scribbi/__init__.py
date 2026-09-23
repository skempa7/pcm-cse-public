"""Scribbi: review an AI scribe's draft note before you sign it.

Public API used by offline_routes:

  home()                         -> landing data: modes, library, stats, lock state
  create(body)                   -> start a round (returns the page payload)
  get(round_id)                  -> page payload (auto-signs an expired timed round)
  save(round_id, state)          -> autosave a review in progress
  check(round_id, state, target) -> Learn mode: instant feedback on one change
  hint(round_id, state)          -> Coached mode: the next hint
  sign(round_id, state)          -> grade, freeze, return the result
  delete(round_id)

The answer key is stored with the round and never sent to the page.
"""

from __future__ import annotations

import json
import uuid
import random
import re

from .. import cases, db, teaching, version
from . import catalog as C
from . import drafting as D
from . import planting as P
from . import review as R
from . import store
from . import text as T
from . import visit as V

TIME_GRACE_MS = 1500


class ScribbiError(ValueError):
    def __init__(self, message, status=400, extra=None):
        super().__init__(message)
        self.status = status
        self.extra = extra or {}


class Locked(ScribbiError):
    def __init__(self, attempts):
        super().__init__("Scribbi shows complete example visits and notes. Finish, leave, or convert your active "
                         "independent or exam rehearsal attempt to assisted practice first.", 409,
                         {"requires_assistance": True, "attempts": attempts})


def _guard():
    pending = teaching.blockers()
    if pending:
        raise Locked(pending)


# --------------------------------------------------------------------------
# Building a round
# --------------------------------------------------------------------------

def _turn_concepts(walkthrough, visit):
    ledger = {e["seq"]: e for e in walkthrough.get("ledger", [])}
    out = {}
    for turn, item in zip(visit["turns"], walkthrough.get("timeline", [])):
        concepts = set()
        for eid in item.get("event_ids", []):
            ev = ledger.get(eid)
            if ev:
                concepts |= set((ev.get("meta") or {}).get("concepts") or {})
        out[turn["id"]] = concepts
    return out


def _position(err, lines):
    flat = {}
    n = 0
    for ln in lines:
        for ch in ln["chips"]:
            flat[ch["id"]] = n
            n += 1
        flat["line:" + ln["id"]] = n - 0.5
    if err.get("chip") in flat:
        return flat[err["chip"]]
    if err.get("anchor_line") and "line:" + err["anchor_line"] in flat:
        return flat["line:" + err["anchor_line"]] + 0.25
    return n


def build(case_id, variant_id, mode, seed, timed=False):
    visit, walkthrough, case, e2r = V.library_visit(case_id, variant_id)
    b = D.true_note(walkthrough, e2r, visit["turns"])
    ctx = {"visit": visit, "case": case, "turn_concepts": _turn_concepts(walkthrough, visit)}
    errors, hands = P.plant(b, ctx, mode, seed)
    return _finish_build(visit, b, errors, hands, case_id, timed)


MIN_ATTEMPT_HISTORY = 4
MIN_ATTEMPT_EXAM = 2


def _walkthrough_needs(walkthrough):
    """event id -> (facts, maneuvers, chart refs) from the demonstration ledger."""
    out = {}
    for ev in walkthrough.get("ledger", []):
        meta = ev.get("meta") or {}
        facts = set(meta.get("facts_released") or [])
        mans = set()
        if ev.get("kind") in ("exam_finding", "exam_action") and meta.get("maneuver_id"):
            mans.add(meta["maneuver_id"])
        chart = set()
        if ev.get("kind") == "station_info":
            chart.add("chart:vitals" if meta.get("vitals") else
                      "chart:result:" + meta["supplied_id"] if meta.get("supplied_id") else "chart:doorway")
        out[ev["seq"]] = (facts, mans, chart)
    return out


def build_from_attempt(session, mode, seed, timed=False):
    """Scribbi drafts the student's own visit.

    The draft starts from the demonstrated example note for the same patient
    and keeps only the statements the student's own encounter supports: every
    fact behind a statement must have been released to this student, and every
    examination behind it must have been performed with a finding. Nothing the
    student didn't obtain can appear except what Scribbi plants on purpose."""
    case = session.case
    case_id, variant_id = session.row["case_id"], case.get("variant_id", "base")
    walkthrough = V.load_walkthrough(case_id, variant_id)
    if walkthrough is None:
        raise ScribbiError("Scribbi has no example note for this presentation yet.", 404)
    wvisit, _w, _c, we2r = V.library_visit(case_id, variant_id)
    b = D.true_note(walkthrough, we2r, wvisit["turns"])
    visit, e2r, turn_concepts = V.attempt_visit(session)
    released = session.ledger.released_facts()
    found_mans = {}
    for t in visit["turns"]:
        if t["kind"] == "exam" and not t.get("no_finding") and t.get("maneuver_id"):
            found_mans.setdefault(t["maneuver_id"], []).append(t["id"])
    needs = _walkthrough_needs(walkthrough)
    walk_turn_mid = {t["id"]: t.get("maneuver_id") for t in wvisit["turns"] if t["kind"] == "exam"}
    for ln in list(b.lines):
        if ln["section"] in ("A", "P"):
            continue
        kept = []
        for ch in ln["chips"]:
            facts, mans, chart = set(), set(), set()
            for eid in ch.get("events") or []:
                f, m, c = needs.get(eid, (set(), set(), set()))
                facts |= f
                mans |= m
                chart |= c
            if ln["label"] == "Vitals":
                chart.add("chart:vitals")
            if not (facts or mans or chart) and ln["section"] == "O":
                # Linked only to its examination region: it needs that exam.
                mans |= {walk_turn_mid[r] for r in ch.get("evidence", []) if walk_turn_mid.get(r)}
            if not (facts or mans or chart):
                continue
            if any(f not in released for f in facts) or any(m not in found_mans for m in mans):
                continue
            refs = []
            for f in facts:
                ref = e2r.get(released[f]["seq"])
                if ref and ref not in refs:
                    refs.append(ref)
            for m in mans:
                refs.extend(r for r in found_mans[m] if r not in refs)
            refs.extend(r for r in sorted(chart) if r not in refs)
            ch["evidence"] = refs
            ch["_facts"], ch["_mans"] = sorted(facts), sorted(mans)
            kept.append(ch)
        ln["chips"] = kept
        if not kept:
            b.lines.remove(ln)
    _add_obtained(b, session, visit, released, e2r)
    for ln in b.lines:
        for ch in ln["chips"]:
            ch.pop("_facts", None)
            ch.pop("_mans", None)
    history = sum(len(ln["chips"]) for ln in b.lines if ln["section"] == "S")
    exams = sum(len(ln["chips"]) for ln in b.lines if ln["section"] == "O" and ln["kind"] in ("exam", "structural"))
    if history < MIN_ATTEMPT_HISTORY or exams < MIN_ATTEMPT_EXAM:
        led = session.settings.get("purpose") == "scribbi"
        need = []
        if history < MIN_ATTEMPT_HISTORY:
            need.append("%d more history answer%s" % (MIN_ATTEMPT_HISTORY - history, "" if MIN_ATTEMPT_HISTORY - history == 1 else "s"))
        if exams < MIN_ATTEMPT_EXAM:
            need.append("%d more examination%s with a finding" % (MIN_ATTEMPT_EXAM - exams, "" if MIN_ATTEMPT_EXAM - exams == 1 else "s"))
        message = ("Scribbi needs a little more to write a useful note: " + " and ".join(need) + "." if led else
                   "Your visit didn't cover enough history and examination for Scribbi to draft a useful "
                   "note. Try Scribbi's draft of the full demonstrated visit instead.")
        raise ScribbiError(message, 409, {"too_short": True, "case_id": case_id, "variant_id": variant_id,
                                          "have": {"history": history, "exams": exams},
                                          "need": {"history": MIN_ATTEMPT_HISTORY, "exams": MIN_ATTEMPT_EXAM}})
    ctx = {"visit": visit, "case": case, "turn_concepts": turn_concepts}
    errors, hands = P.plant(b, ctx, mode, seed)
    return _finish_build(visit, b, errors, hands, case_id, timed)


# Where a scribe writes what the patient said, by the fact's category.
_CATEGORY_LABEL = {
    "chief_complaint": "CC", "onset": "HPI", "timing": "HPI", "alleviating": "HPI", "severity": "HPI",
    "location": "HPI", "quality": "HPI", "aggravating": "HPI", "setting": "HPI", "treatment": "HPI",
    "radiation": "HPI", "chronology": "HPI", "associated": "HPI", "past_occurrence": "HPI",
    "concern": "Patient concern", "fife": "Perspective", "pmh": "PMH", "psh": "PSH",
    "medications": "Meds", "allergies": "Allergies", "social": "SH", "obgyn": "OB/GYN",
    "family": "FH", "pertinent_negative": "ROS",
}
_S_ORDER = ["CC", "HPI", "Patient concern", "Perspective", "PMH", "Additional PMH", "PSH", "Meds",
            "Allergies", "SH", "OB/GYN", "Reproductive history", "FH", "ROS"]
_REGION_LABEL = {region: label for label, region in D.LABEL_REGION.items() if label not in ("Chest wall", "GU", "Lymphatic")}


def _add_obtained(b, session, visit, released, e2r):
    """Everything the student obtained reaches Scribbi's note.

    The example note's statements bundle several facts, so a short visit that
    covers part of a statement keeps none of it. Each fact the patient actually
    told this student that no kept statement already covers is written in her
    own words (a quotation, as scribes do), and each examination with a
    finding that no kept statement covers is written from that finding. Only
    obtained evidence is added; the answer key sees these as true lines."""
    covered_facts, covered_mans = set(), set()
    for ln in b.lines:
        for ch in ln["chips"]:
            covered_facts.update(ch.get("_facts") or [])
            covered_mans.update(ch.get("_mans") or [])
    facts = {f["id"]: f for f in session.case.get("facts", [])}
    order = {fid: ev["seq"] for fid, ev in released.items()}

    def line_for(section, label, kind):
        ln = next((x for x in b.lines if x["section"] == section and x["label"] == label), None)
        if ln:
            return ln
        ln = b.line(section, label, kind)
        b.lines.remove(ln)
        if section == "S":
            rank = _S_ORDER.index(label) if label in _S_ORDER else len(_S_ORDER)
            at = next((i for i, x in enumerate(b.lines) if x["section"] != "S" or
                       (_S_ORDER.index(x["label"]) if x["label"] in _S_ORDER else len(_S_ORDER)) > rank), len(b.lines))
        else:
            at = next((i for i, x in enumerate(b.lines) if x["section"] in ("A", "P") or x["label"] == "Results"), len(b.lines))
        b.lines.insert(at, ln)
        return ln

    for fid in sorted(released, key=lambda f: order[f]):
        fact = facts.get(fid)
        label = _CATEGORY_LABEL.get((fact or {}).get("category"))
        if not fact or not label or fid in covered_facts:
            continue
        spoken = released[fid].get("text") or ""
        words = next((v for v in (fact.get("sp_says") or []) if v and v in spoken), None) or \
            (fact.get("sp_says") or [fact.get("value", "")])[0]
        words = (words or "").strip()
        if not words:
            continue
        ln = line_for("S", label, "history")
        continued = bool(ln["chips"]) and ln["chips"][-1].get("quoted")
        text = T.as_patient_quote(words, label, continued=continued)
        ref = e2r.get(released[fid]["seq"])
        b.chip(ln, text, [ref] if ref else [], quoted=text != words, events=[], origin="visit")
        covered_facts.add(fid)

    for t in visit["turns"]:
        mid = t.get("maneuver_id")
        if t.get("kind") != "exam" or t.get("no_finding") or not mid or mid in covered_mans:
            continue
        label = _REGION_LABEL.get(t.get("region") or "")
        finding = (t.get("finding") or "").strip()
        if not label or not finding:
            continue
        ln = line_for("O", label, D._kind_for("O", label))
        for piece in T.split_sentences(finding):
            if piece.strip():
                b.chip(ln, piece.strip(), [t["id"]], events=[], origin="visit")
        covered_mans.add(mid)


def _capitalize_line_starts(lines, errors):
    """A dropped first sentence leaves the next one lowercase ("burning on
    voiding"); a scribe's draft still starts each line with a capital."""
    for ln in lines:
        if ln["section"] not in ("S", "O") or not ln["chips"]:
            continue
        ch = ln["chips"][0]
        text = ch["text"]
        if text[:1].islower():
            fixed = text[0].upper() + text[1:]
            for err in errors:
                if err.get("chip") == ch["id"] and err.get("planted") == text:
                    err["planted"] = fixed
            ch["text"] = fixed


def _finish_build(visit, b, errors, hands, case_id, timed):
    _capitalize_line_starts(b.lines, errors)
    D.renumber(b.lines, errors + ([hands] if hands else []))
    errors.sort(key=lambda e: _position(e, b.lines))
    for i, err in enumerate(errors, start=1):
        err["id"] = "e%d" % i
    if hands:
        hands["id"] = "h1"
    for ln in b.lines:
        for ch in ln["chips"]:
            ch.pop("events", None)
    s_text = " ".join(ch["text"] for ln in b.lines if ln["section"] == "S" for ch in ln["chips"])
    said = T.norm(V.visit_text(visit) + "\n" + s_text)
    avoid = []
    spec = C.ALLERGY_CONFLICTS.get(case_id)
    if spec and any(re.search(p, said) for p in spec["allergen"]):
        avoid.append({"avoid": spec["avoid"], "message": spec["message"]})
    key = {"errors": errors, "hands_on": hands, "_said": said, "_allergy_avoid": avoid, "timed": bool(timed)}
    return visit, b.lines, key


def _pick_case(body):
    paths = V.library_paths()
    if not paths:
        raise ScribbiError("No demonstrated visits are available.", 404)
    case_id = body.get("case_id")
    rng = random.SystemRandom()
    if body.get("random") or not case_id:
        system = body.get("system")
        pool = paths
        if system:
            ids = {c["id"] for c in cases.index() if c["system"] == system}
            pool = [p for p in paths if p["case_id"] in ids] or paths
        choice = rng.choice(pool)
        return choice["case_id"], choice["variant_id"]
    if not cases.get(case_id):
        raise ScribbiError("Unknown presentation.", 400)
    variants = [p["variant_id"] for p in paths if p["case_id"] == case_id]
    if not variants:
        raise ScribbiError("That presentation has no demonstrated visit yet.", 404)
    variant_id = body.get("variant_id") or "base"
    if variant_id == "random":
        variant_id = rng.choice(variants)
    if variant_id not in variants:
        raise ScribbiError("Unknown variation.", 400)
    return case_id, variant_id


def create(body):
    _guard()
    body = body if isinstance(body, dict) else {}
    mode = body.get("mode") or "coached"
    if mode not in C.MODES:
        raise ScribbiError("Unknown Scribbi mode.", 400)
    timed = bool(body.get("timed")) and mode == "solo"
    seed = random.SystemRandom().randrange(1, 2 ** 31)
    source, attempt_id, visit_session = "library", "", None
    if body.get("attempt_id"):
        from .. import engine
        attempt_id = str(body["attempt_id"])[:64]
        session = engine.load(attempt_id)
        if not session:
            raise ScribbiError("That Chat CSE attempt no longer exists.", 404)
        if session.settings.get("purpose") == "scribbi":
            # The student led this visit and Scribbi writes its note. Finishing
            # twice returns the same draft instead of a second one.
            done = session.settings.get("scribbi_round_id")
            if done and store.get(done) and not body.get("again"):
                return payload(store.get(done))
            _settle_pending_exam(session)
            visit_session = session
        elif session.row["phase"] != "submitted":
            raise ScribbiError("Submit your note first. Scribbi drafts your visit once the encounter is over.", 409)
        case_id, variant_id = session.row["case_id"], session.case.get("variant_id", "base")
        # A visit too short to draft from stays open, so the student can go on.
        visit, lines, key = build_from_attempt(session, mode, seed, timed)
        source = "visit" if visit_session else "attempt"
    else:
        case_id, variant_id = _pick_case(body)
        visit, lines, key = build(case_id, variant_id, mode, seed, timed)
    now = db.now_ms()
    rid = db.new_id()
    store.insert({
        "id": rid, "created_at": now, "updated_at": now, "case_id": case_id, "variant_id": variant_id,
        "source": source, "source_attempt_id": attempt_id, "mode": mode, "timed": 1 if timed else 0,
        "time_limit_s": C.MODES["solo"]["timer_s"] if timed else 0, "seed": seed,
        "generator_version": C.GENERATOR_VERSION, "engine_version": version.ENGINE_VERSION,
        "status": "reviewing", "visit_json": json.dumps(visit), "lines_json": json.dumps(lines),
        "key_json": json.dumps(key), "review_json": json.dumps({"chips": {}, "added": []}),
        # A watched visit comes before the review: its clock starts at begin().
        "started_at": NOT_STARTED if body.get("watch") else now, "hints_json": "[]",
    })
    if visit_session is not None:
        visit_session.end_encounter_now()
        if not visit_session.settings.get("scribbi_round_id"):
            settings = dict(visit_session.settings, scribbi_round_id=rid)
            visit_session.settings = settings
            visit_session.set(settings_json=json.dumps(settings))
            visit_session.save()
    return payload(store.get(rid))


def open_visits(limit=6):
    """Visits a student started leading and left before Scribbi wrote the note."""
    out = []
    with db.connect() as conn:
        rows = conn.execute("SELECT id, created_at, case_id, phase, settings_json, case_snapshot FROM sessions "
                            "WHERE phase IN ('briefing', 'encounter') ORDER BY created_at DESC").fetchall()
    for r in rows:
        settings = json.loads(r["settings_json"] or "{}")
        if settings.get("purpose") != "scribbi" or settings.get("scribbi_round_id"):
            continue
        snapshot = json.loads(r["case_snapshot"] or "{}")
        out.append({"id": r["id"], "case_id": r["case_id"], "phase": r["phase"], "created_at": r["created_at"],
                    "patient_name": (snapshot.get("patient") or {}).get("name", "Patient"),
                    "title": (cases.get(r["case_id"]) or {}).get("title", r["case_id"])})
        if len(out) >= limit:
            break
    return out


def _settle_pending_exam(session):
    """An examination still running when the student finishes is completed, not
    lost: in an untimed visit, skipping the animation costs nothing."""
    pending = json.loads(session.row.get("pending_exam_json") or "null")
    if not pending or session.row["phase"] != "encounter":
        return
    if not pending.get("id"):
        pending["id"] = uuid.uuid4().hex
        session.set(pending_exam_json=json.dumps(pending))
        session.save()
    session.control_examination(pending["id"], "skip")


# --------------------------------------------------------------------------
# Reading and writing a round
# --------------------------------------------------------------------------

def _load(round_id):
    row = store.get(round_id) if isinstance(round_id, str) else None
    if not row:
        raise ScribbiError("That Scribbi review no longer exists.", 404)
    return row


def _parts(row):
    return (json.loads(row["visit_json"]), json.loads(row["lines_json"]), json.loads(row["key_json"]),
            json.loads(row["review_json"] or "{}"), json.loads(row["hints_json"] or "[]"))


NOT_STARTED = -1


def _started(row):
    """When the review itself began; None while the student is still watching
    the visit, so a solo clock never runs during the visit."""
    if row["started_at"] is not None and row["started_at"] < 0:
        return None
    return row["started_at"] or row["created_at"]


def playback(round_id):
    """Staging for the visit player. Only demonstrated visits can be replayed:
    a visit the student led already happened live."""
    _guard()
    row = _load(round_id)
    visit = json.loads(row["visit_json"])
    if visit.get("source") != "library":
        raise ScribbiError("This was your own visit, so there is no recording to replay.", 409)
    from . import staging as PB
    try:
        return PB.build(row["case_id"], row["variant_id"])
    except ValueError as exc:
        raise ScribbiError(str(exc), 404)


def begin(round_id):
    """The student finished (or skipped) the visit: the review starts now."""
    row = _load(round_id)
    if row["status"] == "reviewing" and _started(row) is None:
        store.update(round_id, only_if_reviewing=True, started_at=db.now_ms())
    return payload(_load(round_id))


def _deadline(row):
    if not row["timed"] or not row["time_limit_s"]:
        return None
    started = _started(row)
    return None if started is None else started + row["time_limit_s"] * 1000


def _expire_if_due(row):
    deadline = _deadline(row)
    if row["status"] == "reviewing" and deadline and db.now_ms() > deadline + TIME_GRACE_MS:
        visit, lines, key, state, hints = _parts(row)
        _finish(row, R.sanitize(state, lines), timed_out=True)
        return store.get(row["id"])
    return row


def get(round_id):
    _guard()
    row = _expire_if_due(_load(round_id))
    return payload(row)


def save(round_id, state):
    _guard()
    row = _expire_if_due(_load(round_id))
    if row["status"] != "reviewing":
        return {"saved": False, "status": row["status"],
                "reason": "This note is already signed. Your review is frozen."}
    visit, lines, key, _old, hints = _parts(row)
    clean = R.sanitize(state, lines)
    changed = store.update(round_id, only_if_reviewing=True, review_json=json.dumps(clean))
    out = {"saved": bool(changed), "status": "reviewing", "updated_at": db.now_ms()}
    mode = C.MODES[row["mode"]]
    if mode["instant_feedback"]:
        out["progress"] = _progress(key, lines, visit, clean)
    return out


def _progress(key, lines, visit, state):
    result = R.evaluate(key, lines, visit, state)
    planted = [it for it in result["items"] if it["error"]["type"] != "hands_on"]
    found = [it for it in planted if it["verdict"] != "missed"]
    by_type = {}
    for it in planted:
        t = it["error"]["type"]
        slot = by_type.setdefault(t, {"type": t, "label": C.ERROR_TYPES[t]["label"], "total": 0, "found": 0})
        slot["total"] += 1
        slot["found"] += 1 if it["verdict"] != "missed" else 0
    hands = next((it for it in result["items"] if it["error"]["type"] == "hands_on"), None)
    return {"found": len(found), "total": len(planted), "types": list(by_type.values()),
            "hands_on": hands["verdict"] if hands else None,
            "false_alarms": len(result["false_alarms"]), "unsupported": len(result["unsupported"])}


def _turn_snapshots(visit, refs):
    out = []
    for ref in refs[:6]:
        turn = V.turn_by_id(visit, ref)
        if turn:
            out.append({k: turn[k] for k in ("id", "kind", "t", "student", "patient", "label", "finding", "text",
                                             "region", "felt") if k in turn})
    return out


def check(round_id, state, target):
    _guard()
    row = _expire_if_due(_load(round_id))
    if not C.MODES[row["mode"]]["instant_feedback"]:
        raise ScribbiError("Instant checks are part of Learn mode.", 403)
    if row["status"] != "reviewing":
        raise ScribbiError("This note is already signed.", 409)
    visit, lines, key, _old, hints = _parts(row)
    clean = R.sanitize(state, lines)
    store.update(round_id, only_if_reviewing=True, review_json=json.dumps(clean))
    result = R.evaluate(key, lines, visit, clean)
    target = target if isinstance(target, dict) else {}
    verdict = {"verdict": "neutral", "title": "", "message": ""}
    chip_id = target.get("chip")
    added_id = target.get("added")
    if chip_id:
        item = next((it for it in result["items"] if it["error"].get("chip") == chip_id), None)
        alarm = next((fa for fa in result["false_alarms"] if fa["chip"] == chip_id), None)
        unsup = next((u for u in result["unsupported"] if u["id"] == chip_id), None)
        if item:
            verdict = _instant(item)
        elif alarm:
            verdict = {"verdict": "false_alarm",
                       "title": "That line was right." if alarm["kind"] == "removed" else "Careful: that detail was right.",
                       "message": ("The visit supports it. Undo to put it back." if alarm["kind"] == "removed"
                                   else "Your edit changed a correct value. Check it against the visit."),
                       "evidence": _turn_snapshots(visit, alarm.get("evidence", []))}
        elif unsup:
            verdict = {"verdict": "unsupported", "title": "The visit doesn't support that.", "message": unsup["why"]}
    elif added_id:
        added = next((a for a in clean["added"] if a["id"] == added_id), None)
        if added:
            fixed = [it for it in result["items"] if it["student_text"] == added["text"] and it["verdict"] in ("fixed", "caught")
                     and it["error"]["check"]["kind"] in ("omission", "structural", "lead")]
            unsup = next((u for u in result["unsupported"] if u["id"] == added_id), None)
            if fixed:
                verdict = _instant(fixed[0])
            elif unsup:
                verdict = {"verdict": "unsupported", "title": "The visit doesn't support that.", "message": unsup["why"]}
    verdict["progress"] = _progress(key, lines, visit, clean)
    return verdict


def _instant(item):
    err = item["error"]
    info = C.ERROR_TYPES[err["type"]]
    base = {"type": err["type"], "type_label": info["label"]}
    if item["verdict"] == "fixed":
        title = "Hands-on finding added." if err["type"] == "hands_on" else "Caught it: " + info["label"].lower() + "."
        return dict(base, verdict="fixed", title=title, message=err["note"])
    if item["verdict"] == "caught":
        if err["type"] == "hands_on":
            return dict(base, verdict="caught", title="Almost: check the level and side.",
                        message="Your structural finding doesn't match what you palpated. Look at the exam in the visit.")
        return dict(base, verdict="caught", title="Good catch. Now fix it.",
                    message="The mistake is gone, but the right information isn't in the note yet. " + err["note"])
    return dict(base, verdict="still_wrong", title="Not quite yet.",
                message="This line still has Scribbi's mistake. " + info["habit"])


def hint(round_id, state):
    _guard()
    row = _expire_if_due(_load(round_id))
    mode = C.MODES[row["mode"]]
    if not mode["hints"]:
        raise ScribbiError("Hints aren't part of this mode.", 403)
    if row["status"] != "reviewing":
        raise ScribbiError("This note is already signed.", 409)
    visit, lines, key, _old, hints = _parts(row)
    if len(hints) >= mode["hints"]:
        raise ScribbiError("You've used all %d hints." % mode["hints"], 409)
    clean = R.sanitize(state, lines)
    result = R.evaluate(key, lines, visit, clean)
    open_items = [it for it in result["items"] if it["verdict"] == "missed"]
    open_items.sort(key=lambda it: (it["error"]["type"] == "hands_on",))
    if not open_items:
        return {"hint": {"text": "Nothing left to find. Sign when you're ready.", "level": 0},
                "used": len(hints), "left": mode["hints"] - len(hints)}
    err = open_items[0]["error"]
    level = 1 + sum(1 for h in hints if h.get("error") == err["id"])
    section = D.SECTION_TITLES.get(err["section"], "note")
    label = _line_label(err, lines)
    if err["type"] == "hands_on":
        text = ("Something you felt with your hands isn't in the Objective." if level == 1
                else "Scribbi can't feel. Your structural exam findings are missing. Check the exam in the visit.")
    elif err["check"]["kind"] == "omission":
        text = ("Something the patient said is missing from the %s." % section if level == 1
                else "Compare the %s line with the conversation. Something was left out." % (label or section))
    else:
        text = ("Look closely at the %s." % section if level == 1
                else "Check the %s line against the visit." % (label or section))
    hints.append({"error": err["id"], "level": level, "text": text, "at": db.now_ms()})
    store.update(round_id, only_if_reviewing=True, hints_json=json.dumps(hints), review_json=json.dumps(clean))
    return {"hint": {"text": text, "level": level, "section": err["section"]},
            "used": len(hints), "left": mode["hints"] - len(hints)}


def _line_label(err, lines):
    if err["type"] == "hands_on":
        return "Osteopathic"
    line_id = err.get("line") if err.get("chip") else err.get("anchor_line")
    ln = next((l for l in lines if l["id"] == line_id), None)
    if err["type"] == "dropped" and err.get("label"):
        return err["label"]
    if not ln:
        return err.get("label", "")
    if ln["section"] in ("A", "P"):
        return ("Assessment %s" if ln["section"] == "A" else "Plan %s") % ln["label"]
    return ln["label"]


def _finish(row, clean, timed_out=False):
    visit, lines, key, _old, hints = _parts(row)
    now = db.now_ms()
    started = _started(row) or now
    elapsed = now - started
    if row["timed"] and row["time_limit_s"]:
        elapsed = min(elapsed, row["time_limit_s"] * 1000)
    result = R.evaluate(key, lines, visit, clean, hints_used=len(hints), elapsed_ms=elapsed,
                        timed_out=timed_out, mode=row["mode"])
    view = result_view(result, visit, lines, key, clean, row)
    changed = store.update(row["id"], only_if_reviewing=True, status="signed", signed_at=now, elapsed_ms=elapsed,
                           review_json=json.dumps(clean), result_json=json.dumps(view),
                           score=view["score"], stars=view["stars"])
    return changed


def sign(round_id, state):
    _guard()
    row = _expire_if_due(_load(round_id))
    if row["status"] == "signed":
        return payload(row)
    visit, lines, key, _old, hints = _parts(row)
    clean = R.sanitize(state, lines)
    _finish(row, clean)
    return payload(store.get(round_id))


def delete(round_id):
    row = _load(round_id)
    store.delete(row["id"])
    return {"deleted": True}


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------

def _mode_view(key):
    m = C.MODES[key]
    return {"key": key, "label": m["label"], "tagline": m["tagline"], "detail": m["detail"],
            "show_count": m["show_count"], "show_types": m["show_types"], "hints": m["hints"],
            "instant_feedback": m["instant_feedback"], "sources": m["sources"], "timer_s": m["timer_s"]}


def payload(row):
    visit, lines, key, state, hints = _parts(row)
    mode = C.MODES[row["mode"]]
    planted = key["errors"]
    expect = {"hands_on": bool(key.get("hands_on")) and row["mode"] != "solo"}
    if mode["show_count"]:
        expect["count"] = len(planted)
    if mode["show_types"]:
        counts = {}
        for err in planted:
            counts[err["type"]] = counts.get(err["type"], 0) + 1
        expect["types"] = [{"type": t, "label": C.ERROR_TYPES[t]["label"], "short": C.ERROR_TYPES[t]["short"],
                            "count": n} for t, n in counts.items()]
    out = {
        "id": row["id"], "case_id": row["case_id"], "variant_id": row["variant_id"], "source": row["source"],
        "source_attempt_id": row["source_attempt_id"],
        "mode": _mode_view(row["mode"]), "status": row["status"], "timed": bool(row["timed"]),
        "time_limit_s": row["time_limit_s"], "started_at": row["started_at"], "started": _started(row) is not None, "deadline": _deadline(row),
        "server_now": db.now_ms(), "created_at": row["created_at"], "signed_at": row["signed_at"],
        "visit": visit,
        "draft": D.client_sections(lines, with_sources=mode["sources"] and row["status"] == "reviewing"),
        "review": state, "expect": expect,
        "hints": {"used": len(hints), "left": (mode["hints"] - len(hints)) if mode["hints"] else 0,
                  "history": [{"text": h["text"], "level": h["level"]} for h in hints]} if mode["hints"] else None,
        "generator_version": row["generator_version"],
    }
    if row["status"] == "reviewing" and mode["instant_feedback"]:
        out["progress"] = _progress(key, lines, visit, R.sanitize(state, lines))
    if row["status"] == "signed" and row["result_json"]:
        out["result"] = json.loads(row["result_json"])
    return out


def _chip_view(ln, ch, state, item_by_chip):
    st = state["chips"].get(ch["id"]) or {"status": "kept"}
    view = {"id": ch["id"], "text": ch["text"], "status": st["status"]}
    if st["status"] == "edited":
        view["edited"] = st["text"]
    if ch["id"] in item_by_chip:
        view["error"] = item_by_chip[ch["id"]]
    return view


_CORRECT_LABEL = {"flipped": "What the visit supports", "wrong_detail": "What the visit supports",
                  "anchored_dx": "What the visit supports", "misattributed": "What the visit supports",
                  "fabricated_exam": "What actually happened", "fabricated_history": "What actually happened",
                  "allergy_conflict": "The fix"}
_WORDS = {"1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven",
          "8": "eight", "9": "nine", "10": "ten"}


def _evidence_keys(err):
    """Words that make a moment of the visit the relevant proof for this mistake."""
    chk = err.get("check") or {}
    source = err.get("original") or err.get("correct") or ""
    keys = set()
    if chk.get("mode") in ("rating", "duration", "dose", "vital", "age"):
        for num in re.findall(r"\d+(?:\.\d+)?", source):
            keys.add(num)
            if num in _WORDS:
                keys.add(_WORDS[num])
    if chk.get("mode") == "side":
        keys.update(chk.get("sides") or [])
    if chk.get("mode") == "polarity" and chk.get("term"):
        keys.update(w for w in T.content_words(chk["term"]) if len(w) > 3)
    if not keys:
        keys.update(w for w in T.content_words(source) if len(w) > 3)
    return keys


def _rank_evidence(err, visit):
    refs = list(err.get("evidence") or [])
    keys = _evidence_keys(err)
    if not keys or len(refs) < 2:
        return refs

    def score(ref):
        turn = V.turn_by_id(visit, ref) or {}
        blob = T.norm(" ".join(str(turn.get(k, "")) for k in ("student", "patient", "label", "finding", "text")))
        return -sum(1 for k in keys if re.search(r"(?<![a-z0-9])" + re.escape(T.norm(k)) + r"(?![a-z0-9])", blob))
    order = {r: i for i, r in enumerate(refs)}
    return sorted(refs, key=lambda r: (score(r), order[r]))


def result_view(result, visit, lines, key, state, row):
    items = []
    item_by_chip = {}
    for it in result["items"]:
        err = it["error"]
        info = C.ERROR_TYPES[err["type"]]
        items.append({
            "id": err["id"], "type": err["type"], "type_label": info["label"], "short": info["short"],
            "icon": info["icon"], "severity": err["severity"],
            "severity_label": C.SEVERITY_LABELS.get(err["severity"], ""),
            "section": err["section"], "section_title": D.SECTION_TITLES.get(err["section"], ""),
            "label": _line_label(err, lines), "chip": err.get("chip"), "anchor_line": err.get("anchor_line"),
            "verdict": it["verdict"], "planted": err.get("planted"), "original": err.get("original"),
            "student_text": it["student_text"], "correct": err.get("correct") if err["type"] in _CORRECT_LABEL else "",
            "correct_label": _CORRECT_LABEL.get(err["type"], ""), "note": err.get("note"),
            "why": info["why"], "risk": info["risk"], "fix": info["fix"], "habit": info["habit"],
            "evidence": _turn_snapshots(visit, _rank_evidence(err, visit)),
        })
        if err.get("chip"):
            item_by_chip[err["chip"]] = {"id": err["id"], "verdict": it["verdict"]}
    alarms = []
    for fa in result["false_alarms"]:
        item_by_chip.setdefault(fa["chip"], {"id": None, "verdict": "false_alarm"})
        alarms.append(dict({k: fa[k] for k in ("chip", "label", "section", "text", "kind") if k in fa},
                           edited=fa.get("edited"), evidence=_turn_snapshots(visit, fa.get("evidence", []))))
    sections = []
    for sec in ("S", "O", "A", "P"):
        rows = []
        for ln in lines:
            if ln["section"] != sec:
                continue
            rows.append({"id": ln["id"], "label": ln["label"],
                         "chips": [_chip_view(ln, ch, state, item_by_chip) for ch in ln["chips"]]})
        added = [{"id": a["id"], "text": a["text"]} for a in state["added"] if a["section"] == sec]
        sections.append({"key": sec, "title": D.SECTION_TITLES[sec], "lines": rows, "added": added})
    return {
        "score": result["score"], "stars": result["stars"], "safe": result["safe"],
        "badges": [dict(C.BADGES[b], key=b) for b in result["badges"]],
        "counts": result["counts"], "items": items, "false_alarms": alarms,
        "unsupported": result["unsupported"], "hints_used": result["hints_used"],
        "elapsed_ms": result["elapsed_ms"], "timed_out": result["timed_out"], "final_note": sections,
    }


# --------------------------------------------------------------------------
# Home and stats
# --------------------------------------------------------------------------

def stats():
    rows = store.signed_results()
    totals = {t: {"type": t, "label": C.ERROR_TYPES[t]["label"], "planted": 0, "fixed": 0, "caught": 0}
              for t in C.ERROR_TYPES}
    false_alarms = 0
    badges = {}
    for r in rows:
        res = r["result"]
        for it in res.get("items", []):
            slot = totals.get(it["type"])
            if slot is None:
                continue
            slot["planted"] += 1
            if it["verdict"] == "fixed":
                slot["fixed"] += 1
            elif it["verdict"] == "caught":
                slot["caught"] += 1
        false_alarms += len(res.get("false_alarms", []))
        for b in res.get("badges", []):
            badges[b["key"]] = badges.get(b["key"], 0) + 1
    streak = 0
    for r in reversed(rows):
        if r["result"].get("safe"):
            streak += 1
        else:
            break
    scores = [r["score"] for r in rows if r["score"] is not None]
    planted = sum(v["planted"] for k, v in totals.items() if k != "hands_on")
    found = sum(v["fixed"] + v["caught"] for k, v in totals.items() if k != "hands_on")
    return {
        "rounds": len(rows),
        "average": round(sum(scores) / len(scores)) if scores else None,
        "best": max(scores) if scores else None,
        "catch_rate": round(100.0 * found / planted) if planted else None,
        "false_alarms": false_alarms,
        "safe_streak": streak,
        "by_type": [v for v in totals.values() if v["planted"]],
        "badges": [dict(C.BADGES[k], key=k, count=n) for k, n in badges.items()],
    }


def home():
    pending = teaching.blockers()
    index = {c["id"]: c for c in cases.index()}
    best = {}
    plays = {}
    for r in store.recent(limit=500):
        k = (r["case_id"], r["variant_id"])
        plays[k] = plays.get(k, 0) + 1
        if r["status"] == "signed" and r["score"] is not None:
            best[k] = max(best.get(k, 0), r["score"])
    library = []
    for p in V.library_paths():
        c = index.get(p["case_id"])
        if not c:
            continue
        k = (p["case_id"], p["variant_id"])
        library.append({"case_id": p["case_id"], "variant_id": p["variant_id"],
                        "variant_label": p["variant_label"], "title": c["title"], "system": c["system"],
                        "station_label": c["station_label"], "best": best.get(k), "plays": plays.get(k, 0)})
    recent = []
    for r in store.recent(limit=12):
        c = index.get(r["case_id"]) or {}
        recent.append({"id": r["id"], "case_id": r["case_id"], "variant_id": r["variant_id"], "source": r["source"],
                       "title": c.get("title", r["case_id"]), "system": c.get("system", ""),
                       "mode": r["mode"], "mode_label": C.MODES.get(r["mode"], {}).get("label", r["mode"]),
                       "status": r["status"], "score": r["score"], "stars": r["stars"],
                       "created_at": r["created_at"], "signed_at": r["signed_at"]})
    return {
        "open_visits": open_visits(),
        "modes": [_mode_view(k) for k in C.MODES],
        "types": [dict({"type": k}, **{f: v[f] for f in ("label", "short", "why", "risk", "fix", "habit", "icon", "severity")})
                  for k, v in C.ERROR_TYPES.items()],
        "research": C.RESEARCH,
        "badges": [dict(v, key=k) for k, v in C.BADGES.items()],
        "library": library,
        "systems": sorted({x["system"] for x in library}),
        "stats": stats(),
        "recent": recent,
        "locked": {"blocked": bool(pending), "attempts": pending},
        "generator_version": C.GENERATOR_VERSION,
    }
