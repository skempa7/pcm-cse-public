"""Grade a reviewed draft against the answer key.

The student's review is a small, explicit state: for every chip, kept, edited
(with new text) or removed; plus lines they added to a section. Each planted
mistake has its own check, written for exactly the change that was planted,
so a verdict never depends on general-purpose note parsing:

  fixed   the mistake is gone and the right information is there
  caught  the mistake is gone but the right information is not (half credit)
  missed  the mistake would reach the chart

A kept, correct line is never penalized. Removing or changing a correct line
is a false alarm. A line the student adds that documents an exam or a history
topic the visit never touched is flagged as unsupported.
"""

from __future__ import annotations

import re

from .. import nlp
from . import catalog as C
from . import text as T
from . import visit as V

MAX_TEXT = 2000
MAX_ADDED = 40


def _light(s: str) -> str:
    s = (s or "").lower().replace("–", "-").replace("—", "-").replace("‑", "-")
    return re.sub(r"\s+", " ", s).strip()


def sanitize(state, draft_lines):
    """Validate a client review state; unknown ids and oversize text are dropped."""
    chips = {}
    known = {ch["id"]: ch for ln in draft_lines for ch in ln["chips"]}
    raw = (state or {}).get("chips") or {}
    if isinstance(raw, dict):
        for cid, spec in raw.items():
            if cid not in known or not isinstance(spec, dict):
                continue
            status = spec.get("status")
            if status not in ("kept", "edited", "removed"):
                continue
            text = spec.get("text") if status == "edited" else None
            if status == "edited":
                if not isinstance(text, str):
                    continue
                text = text.strip()[:MAX_TEXT]
                if not text:
                    status = "removed"
                    text = None
                elif text == known[cid]["text"]:
                    status, text = "kept", None
            entry = {"status": status}
            if text is not None:
                entry["text"] = text
            if spec.get("verified") is True and status == "kept":
                entry["verified"] = True
            chips[cid] = entry
    added = []
    raw_added = (state or {}).get("added") or []
    if isinstance(raw_added, list):
        for item in raw_added[:MAX_ADDED]:
            if not isinstance(item, dict):
                continue
            section = item.get("section")
            text = item.get("text")
            if section not in ("S", "O", "A", "P") or not isinstance(text, str) or not text.strip():
                continue
            aid = str(item.get("id") or "")[:24] or "a%d" % (len(added) + 1)
            added.append({"id": aid, "section": section, "text": text.strip()[:MAX_TEXT]})
    return {"chips": chips, "added": added}


def _chip_state(state, cid):
    return state["chips"].get(cid) or {"status": "kept"}


def _chip_final_text(state, ch):
    st = _chip_state(state, ch["id"])
    if st["status"] == "removed":
        return None
    return st.get("text") if st["status"] == "edited" else ch["text"]


def _student_texts(state, lines, section=None):
    """Everything the student wrote themselves: added lines and edited chips."""
    out = []
    for item in state["added"]:
        if section is None or item["section"] == section:
            out.append(item["text"])
    for ln in lines:
        if section is not None and ln["section"] != section:
            continue
        for ch in ln["chips"]:
            st = _chip_state(state, ch["id"])
            if st["status"] == "edited":
                out.append(st["text"])
    return out


def _matches(patterns, text, light=False):
    t = _light(text) if light else T.norm(text)
    return any(re.search(p, t) for p in patterns)


# --------------------------------------------------------------------------
# Per-mistake checks
# --------------------------------------------------------------------------

def _judge_inserted(err, state):
    st = _chip_state(state, err["chip"])
    chk = err["check"]
    if st["status"] == "removed":
        return "fixed", None
    if st["status"] == "kept":
        return "missed", None
    text = st["text"]
    if chk.get("neutral") and _matches(chk["neutral"], text):
        return "fixed", text
    if _matches(chk["claim"], text):
        return "missed", text
    return "fixed", text


def _judge_polarity(err, text):
    truth = err["check"]["true"]
    terms = [err["check"]["term"]] + list(err["check"].get("synonyms") or [])
    for term in terms:
        pol = nlp.term_polarity(text, term)
        if pol is None:
            continue
        return "fixed" if pol == truth else "missed"
    # The student rewrote the line without the finding at all: the wrong
    # claim is gone, but the correct one is not documented either.
    return "caught"


def _judge_value(err, text):
    chk = err["check"]
    if chk["mode"] == "side":
        sides = T.sides_in(text)
        if not sides:
            return "caught"
        return "fixed" if sorted(set(sides)) == sorted(set(chk["sides"])) else "missed"
    right = any(re.search(p, _light(text)) for p in chk.get("right", []))
    wrong = any(re.search(p, _light(text)) for p in chk.get("wrong", []))
    if wrong and not right:
        return "missed"
    if right and not wrong:
        return "fixed"
    if wrong and right:
        return "missed"
    return "caught"


def _judge_modified(err, state):
    st = _chip_state(state, err["chip"])
    if st["status"] == "kept":
        return "missed", None
    if st["status"] == "removed":
        return "caught", None
    text = st["text"]
    if err["check"]["mode"] == "polarity":
        return _judge_polarity(err, text), text
    return _judge_value(err, text), text


def _final_assessments(state, lines):
    items = []
    for ln in lines:
        if ln["section"] != "A":
            continue
        for ch in ln["chips"]:
            text = _chip_final_text(state, ch)
            if text:
                items.append(text)
    for item in state["added"]:
        if item["section"] == "A":
            for piece in re.split(r"\n+", item["text"]):
                piece = re.sub(r"^\s*\d+\s*[.)]\s*", "", piece).strip()
                if piece:
                    items.append(piece)
    return items


def _judge_lead(err, state, lines):
    chk = err["check"]
    items = _final_assessments(state, lines)
    lead = items[0] if items else ""
    st = _chip_state(state, err["chip"])
    text = st.get("text") if st["status"] == "edited" else None
    if lead and _matches(chk["right"], lead) and not _matches(chk["wrong"], lead):
        return "fixed", text or lead
    if not lead or not _matches(chk["wrong"], lead):
        return "caught", text
    return "missed", text


def _judge_omission(err, state, lines):
    chk = err["check"]
    texts = _student_texts(state, lines, chk.get("section"))
    for text in texts:
        norm_text = T.norm(text)
        matched = 0
        for group in chk["groups"]:
            if any(re.search(p, norm_text) for p in group):
                matched += 1
        if matched >= chk.get("min", len(chk["groups"])):
            if chk.get("positive") and re.match(r"^(no|denies|without)\b", norm_text):
                continue
            return "fixed", text
    return "missed", None


def _judge_structural(err, state, lines):
    chk = err["check"]
    allowed = set(chk["levels"])
    best, best_text = "missed", None
    for text in _student_texts(state, lines, "O"):
        if not T.has_descriptor(text):
            continue
        levels = T.levels_in(text)
        if levels and levels & allowed:
            sides = T.sides_in(text)
            if sides and chk.get("sides") and not set(sides) & set(chk["sides"]):
                best, best_text = "caught", text
                continue
            return "fixed", text
        if best == "missed":
            best, best_text = "caught", text
    return best, best_text


def judge(err, state, lines):
    kind = err["check"]["kind"]
    if kind == "inserted":
        return _judge_inserted(err, state)
    if kind == "modified":
        return _judge_modified(err, state)
    if kind == "lead":
        return _judge_lead(err, state, lines)
    if kind == "omission":
        return _judge_omission(err, state, lines)
    if kind == "structural":
        return _judge_structural(err, state, lines)
    return "missed", None


# --------------------------------------------------------------------------
# False alarms and unsupported additions
# --------------------------------------------------------------------------

def _changed_detail(original, edited):
    """True when an edit changes a value, side, or polarity of a correct line."""
    a, b = T.values_in(original), T.values_in(edited)
    for key in ("durations", "ratings", "doses", "sides"):
        if a[key] and a[key] != b[key] and b[key]:
            return True
    if a["numbers"] and b["numbers"] and set(b["numbers"]) - set(a["numbers"]) and not set(a["numbers"]) <= set(b["numbers"]):
        return True
    for word in T.content_words(original)[:6]:
        if len(word) < 4:
            continue
        pa, pb = nlp.term_polarity(original, word), nlp.term_polarity(edited, word)
        if pa and pb and pa != pb:
            return True
    return False


def _unsupported(text, section, visit, examined, key):
    """Why a line the student wrote isn't supported by the visit, or None."""
    t = T.norm(text)
    if _matches(C.NOT_EXAMINED, text):
        return None
    if section in ("O", "S"):
        for region, spec in C.FABRICATED_EXAMS.items():
            if region in examined:
                continue
            named = re.search(r"\b" + re.escape(region.lower()), t) or (
                region == "Neurologic" and re.search(r"\bneuro", t)) or (
                region == "Extremities" and re.search(r"\bextremit", t))
            claims = sum(1 for p in spec["claim"] if re.search(p, t))
            if (named and claims) or claims >= 2:
                return "No %s examination happened in this visit." % (region if region == "HEENT" else region.lower())
        for key_s, (label, _s, claim) in C.FABRICATED_SENSITIVE.items():
            if sum(1 for p in claim if re.search(p, t)) >= 2:
                return "No %s examination happened in this visit." % label.lower()
    if section == "S":
        said = key.get("_said") or ""
        for topic in C.FABRICATED_HISTORY:
            if any(re.search(p, t) for p in topic["detect"]) and not any(re.search(p, said) for p in topic["detect"]):
                return "Nobody asked about %s in this visit." % topic["key"].replace("_", " ")
    if section == "P":
        # Only a plan can prescribe. Documenting the allergy in the history
        # ("penicillin causes swelling") is exactly what should be there.
        for spec in key.get("_allergy_avoid") or []:
            if any(re.search(p, t) for p in spec["avoid"]) and not re.search(r"\bavoid|allerg|contraindicat", t):
                return spec["message"]
    return None


def evaluate(key, lines, visit, state, *, hints_used=0, elapsed_ms=0, timed_out=False, mode="coached"):
    """The full result for a signed (or hypothetical) review."""
    examined = V.examined_regions(visit) | {ln.get("region") for ln in lines if ln.get("region")}
    planted_chips = set()
    for e in key["errors"]:
        if e.get("chip"):
            planted_chips.add(e["chip"])
        planted_chips.update(e["check"].get("chips") or [])
    items = []
    all_items = list(key["errors"]) + ([key["hands_on"]] if key.get("hands_on") else [])
    for err in all_items:
        verdict, student_text = judge(err, state, lines)
        items.append({"error": err, "verdict": verdict, "student_text": student_text})

    false_alarms = []
    for ln in lines:
        for ch in ln["chips"]:
            if ch["id"] in planted_chips:
                continue
            st = _chip_state(state, ch["id"])
            if st["status"] == "removed":
                false_alarms.append({"chip": ch["id"], "line": ln["id"], "label": ln["label"],
                                     "section": ln["section"], "text": ch["text"], "kind": "removed",
                                     "evidence": ch.get("evidence", [])})
            elif st["status"] == "edited" and _changed_detail(ch["text"], st["text"]):
                false_alarms.append({"chip": ch["id"], "line": ln["id"], "label": ln["label"],
                                     "section": ln["section"], "text": ch["text"], "edited": st["text"],
                                     "kind": "changed", "evidence": ch.get("evidence", [])})

    unsupported = []
    fixes_text = {id(it["student_text"]) for it in items if it["student_text"]}
    for item in state["added"]:
        why = _unsupported(item["text"], item["section"], visit, examined, key)
        if why:
            unsupported.append({"id": item["id"], "section": item["section"], "text": item["text"], "why": why})
    for ln in lines:
        for ch in ln["chips"]:
            if ch["id"] in planted_chips:
                continue
            st = _chip_state(state, ch["id"])
            if st["status"] == "edited":
                why = _unsupported(st["text"], ln["section"], visit, examined, key)
                if why and not _unsupported(ch["text"], ln["section"], visit, examined, key):
                    unsupported.append({"id": ch["id"], "section": ln["section"], "text": st["text"], "why": why})

    credit = sum(1.0 if it["verdict"] == "fixed" else 0.5 if it["verdict"] == "caught" else 0.0 for it in items)
    total = len(items)
    penalty = 0.5 * (len(false_alarms) + len(unsupported))
    planted_n = sum(1 for it in items if it["error"]["type"] != "hands_on")
    if total and planted_n:
        score = 100.0 * max(0.0, credit - penalty) / total
    else:
        # Nothing was planted: signing the draft as it stands is mostly right, so
        # missing structural findings cost a quarter of the score, not all of it.
        hands = {"fixed": 0.0, "caught": 12.5, "missed": 25.0}
        score = (100.0 - 20.0 * (len(false_alarms) + len(unsupported))
                 - sum(hands[it["verdict"]] for it in items))
    score -= C.HINT_COST * hints_used
    score = int(round(max(0.0, min(100.0, score))))

    high_missed = [it for it in items if it["verdict"] == "missed" and it["error"]["severity"] == "high"]
    safe = not high_missed and not unsupported
    stars = 3 if (score >= 90 and safe) else 2 if score >= 70 else 1 if score >= 40 else 0

    planted = [it for it in items if it["error"]["type"] != "hands_on"]
    badges = []
    if planted and len(planted) >= 2 and all(it["verdict"] == "fixed" for it in planted):
        badges.append("eagle_eye")
    found = sum(1 for it in planted if it["verdict"] != "missed")
    if (not false_alarms and not unsupported and (state["chips"] or state["added"])
            and (not planted or found * 2 >= len(planted))):
        badges.append("clean_hands")
    if key.get("hands_on") and any(it["error"]["type"] == "hands_on" and it["verdict"] == "fixed" for it in items):
        badges.append("hands_on")
    highs = [it for it in planted if it["error"]["severity"] == "high"]
    # Badges never contradict the headline: none of these on a note that isn't safe to sign.
    if safe and highs and all(it["verdict"] != "missed" for it in highs):
        badges.append("safety_net")
    hands_done = not key.get("hands_on") or any(it["error"]["type"] == "hands_on" and it["verdict"] == "fixed" for it in items)
    if not planted and not false_alarms and not unsupported and hands_done:
        badges.append("trust_but_verify")
    if mode == "solo" and key.get("timed") and not timed_out and score >= 80:
        badges.append("clinic_pace")

    return {
        "score": score,
        "stars": stars,
        "safe": safe,
        "items": items,
        "false_alarms": false_alarms,
        "unsupported": unsupported,
        "badges": badges,
        "counts": {
            "planted": len(planted),
            "fixed": sum(1 for it in planted if it["verdict"] == "fixed"),
            "caught": sum(1 for it in planted if it["verdict"] == "caught"),
            "missed": sum(1 for it in planted if it["verdict"] == "missed"),
            "hands_on": (next((it["verdict"] for it in items if it["error"]["type"] == "hands_on"), None)),
            "false_alarms": len(false_alarms),
            "unsupported": len(unsupported),
            "edits": sum(1 for s in state["chips"].values() if s["status"] == "edited"),
            "removals": sum(1 for s in state["chips"].values() if s["status"] == "removed"),
            "additions": len(state["added"]),
        },
        "hints_used": hints_used,
        "elapsed_ms": elapsed_ms,
        "timed_out": timed_out,
    }
