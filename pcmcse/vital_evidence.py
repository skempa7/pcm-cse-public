"""Conservative, claim-local vital evidence. Headers never supply findings.

Serial readings are compared with the released examination, retaining position
and elapsed standing time. This module does not read hidden examination data.
"""
import re
from . import claims, evidence, nlp


def _ev(event):
    return {"kind": event["kind"], "text": event["text"],
            "time": "%d:%02d" % (event.get("t_ms", 0) // 60000,
                                    event.get("t_ms", 0) // 1000 % 60),
            "seq": event["seq"]}


def _result(verdict, explanation, events=(), concepts=()):
    return {"verdict": verdict, "explanation": explanation,
            "evidence": [_ev(e) for e in events], "concepts": list(concepts),
            "credit_blocked": verdict == "not_evaluated"}


def _atoms(text):
    return [(claims._LABEL_LOOKUP[m.group(1).lower()],
             claims._norm_value(m.group(2)), m) for m in
            claims.vital_matches(nlp.normalize(text))]


def _canonical_unit(label, unit):
    unit = re.sub(r"\s+", " ", (unit or "").lower()).strip().replace('lbs', 'lb')
    if unit in ('pound','pounds'):unit='lb'
    if label == 'R' and re.fullmatch(r"(?:breaths?\s*)?(?:/\s*|per\s+)(?:minutes?|mins?)", unit):
        return 'rpm'
    return unit


_HEIGHT_PAIR_RE = re.compile(r"\b(?:ht|height)\s*:?\s*(\d+)\s*(?:ft\b|feet\b|foot\b|')\s*(\d+)\s*(?:inches\b|inch\b|in\b|\")")


def station_claim(claim, ledger, case):
    if claim["section"] != "O":
        return None
    text = nlp.normalize(claim["text"])
    atoms = _atoms(text)
    if not atoms:
        return None  # A Vitals heading alone cannot validate a sentence.
    events = [e for e in ledger.by_kind(evidence.STATION_INFO)
              if e.get("meta", {}).get("vitals")]
    if not events:
        return _result("unsupported", "No supplied vital signs appear in the encounter record.")
    # Feet/inches spelling may vary, but both numbers must match in order.
    height_text = claim['text'].lower().replace('’', "'").replace('′', "'").replace('″', '"')
    height_pairs = list(_HEIGHT_PAIR_RE.finditer(height_text))
    if height_pairs:
        source_height = _HEIGHT_PAIR_RE.search('height ' + str(case.get('station', {}).get('vitals', {}).get('Ht', '')).lower().replace('′', "'").replace('″', '"'))
        if not source_height:
            return _result('not_evaluated', 'The height units could not be matched to the supplied chart. No unit conversion was established.', events)
        if any(m.groups() != source_height.groups() for m in height_pairs):
            return _result('contradicts', 'The documented feet and inches disagree with the supplied height.', events)
        text = nlp.normalize(_HEIGHT_PAIR_RE.sub(lambda m: 'ht ' + m.group(1), height_text))
        atoms = _atoms(text)
    # Validate the complete statement, not just its first recognizable number.
    residue = text
    for _, _, match in reversed(atoms):
        residue = residue[:match.start()] + ' ' + residue[match.end():]
    residue = re.sub(r"\b(?:vitals|vital signs|was|were|is|are|and)\b", " ", residue)
    chart = " ".join(str(v) for v in case.get("station", {}).get("vitals", {}).values()).lower()
    allowed = set(re.findall(r"[a-z]+", chart))
    extra = [w for w in re.findall(r"[a-z]+", residue) if w not in allowed]
    if extra or re.search(r"\d", residue):
        return _result("not_evaluated", "This statement includes wording beyond the matched vital signs. The whole claim receives no automatic support; compare the supplied chart and document other findings separately.", events)
    supplied = claims.supplied_vitals(case)
    for label, value, match in atoms:
        if label not in supplied:
            return _result("unsupported", "This measurement was not supplied at the station.", events)
        if value != supplied[label]:
            return _result("contradicts", "%s documented as %s, supplied as %s." % (label, value, supplied[label]), events)
        unit = _canonical_unit(label, match.group(3))
        source_match = claims._VITAL_RE.search(label.lower() + ' ' + str(case['station']['vitals'][label]).lower())
        source_unit = _canonical_unit(label, source_match.group(3) if source_match else '')
        if unit and unit != source_unit:
            return _result('not_evaluated', 'The stated measurement unit does not match the supplied unit. No unit conversion was established; this claim receives no automatic credit.', events)
    return _result("supported_supplied", "Every measurement in this claim matches its own supplied vital sign. These values were supplied at the doorway, not measured by you.", events, ["vitals"])


def _serial_rows(text):
    """Parse bounded BP/pulse clauses; retain omitted repeated standing subject."""
    rows, position = [], None
    for raw in re.split(r"[;\n]|(?<=\.)\s+", text):
        chunk = nlp.normalize(raw).strip(" .")
        if not chunk:
            continue
        named = re.findall(r"\b(supine|standing|seated|sitting)\b", chunk)
        if len(set(named)) > 1:
            return None
        if named:
            position = "seated" if named[0] == "sitting" else named[0]
        minute = re.findall(r"\b(\d+)\s*(?:minute|minutes|min|mins)\b", chunk)
        if len(minute) > 1:
            return None
        # An unlabeled second BP is conventional only in this serial context.
        chunk = re.sub(r"(?<![\w/])(\d{2,3}\s*/\s*\d{2,3})(?![\w/])",
                       lambda m: m.group(0) if re.search(r"(?:bp|blood pressure)\s*$", chunk[:m.start()]) else "bp " + m.group(0), chunk)
        atoms = _atoms(chunk)
        if not atoms or any(a[0] not in ("BP", "P") for a in atoms):
            return None
        if len({a[0] for a in atoms}) != len(atoms):
            return None
        if any(a[2].group(3) and a[2].group(3).lower() != {'BP':'mmhg','P':'bpm'}[a[0]] for a in atoms):
            return None
        residual = claims._VITAL_RE.sub(" ", chunk)
        residual = re.sub(r"\b\d+\s*(?:minute|minutes|min|mins)\b", " ", residual)
        symptom = None
        if re.search(r"\blightheadedness\b", residual):
            symptom = not bool(re.search(r"\b(?:no|without|denies)\s+lightheadedness\b", residual))
        residual = re.sub(r"\b(?:orthostatic|vitals|vital|signs|supine|standing|seated|sitting|at|after|for|the|then|and|with|without|no|denies|lightheadedness|was|were|is|are|rest|resting)\b", " ", residual)
        if re.search(r"[a-z0-9]", residual):
            return None
        rows.append({"position": position, "minute": int(minute[0]) if minute else None,
                     "values": {label: value for label, value, _ in atoms}, "symptom": symptom})
    return rows or None


def serial_claim(claim, ledger):
    if claim["section"] != "O":
        return None
    text = claim["text"]
    if claim.get("header") != "orthostatic" and not (
            re.search(r"\b(?:supine|standing|orthostatic)\b", text, re.I)
            and re.search(r"\b(?:bp|blood pressure)\b", text, re.I)):
        return None
    completed = ledger.performed_maneuvers()
    events = [e for e in ledger.by_kind(evidence.EXAM_FINDING)
              if e.get("meta", {}).get("maneuver_id") == "orthostatic_vitals"
              and "orthostatic_vitals" in completed
              and e.get("meta", {}).get("concepts")]
    if not events:
        return _result("unsupported", "No completed orthostatic measurement with released readings appears in the encounter record. A seated doorway pressure does not supply standing readings.")
    claimed = _serial_rows(text)
    observed = [(r, e) for e in events for r in (_serial_rows(e["text"]) or [])]
    if not claimed or not observed:
        return _result("not_evaluated", "The position, time, or full wording of this serial measurement could not be resolved. It receives no automatic credit and is not a proven contradiction; compare the released series.", events)
    covered = set()
    for row in claimed:
        candidates = [(i, r, e) for i, (r, e) in enumerate(observed)
                      if (row["position"] is None or row["position"] == r["position"])
                      and (row["minute"] is None or row["minute"] == r["minute"])]
        matched = [(i, r, e) for i, r, e in candidates
                   if all(r["values"].get(k) == v for k, v in row["values"].items())
                   and (row["symptom"] is None or row["symptom"] == r["symptom"])]
        if not matched:
            if len(candidates) == 1:
                return _result("contradicts", "This reading disagrees with the released measurement for the stated position and time; compare that reading, not the seated doorway baseline.", [candidates[0][2]])
            return _result("not_evaluated", "The stated position/time and measured values could not be matched uniquely to the obtained series. This is uncredited uncertainty, not a confirmed false finding.", events)
        for i, actual, _ in matched:
            contextual = row['position'] is not None and (row['position'] != 'standing' or row['minute'] is not None)
            if contextual and row["values"] == actual["values"] and row["symptom"] == actual["symptom"]:
                covered.add(i)
    # A single accurate reading is supportable, but does not document the
    # entire multi-reading examination concept or erase its omission cue.
    concepts = list({cid for e in events for cid in e["meta"]["concepts"]}) if len(covered) == len(observed) else []
    return _result("supported", "These values match the orthostatic readings actually released for the documented position and time.", events, concepts)
