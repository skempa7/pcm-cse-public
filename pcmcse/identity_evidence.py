"""Identity evidence from information actually delivered, never a hidden profile.

2026-09-14: age must be asked in new encounters. Historical station cards that
really supplied it remain valid evidence; their stored records are untouched.
"""
from __future__ import annotations

import re
from . import evidence, nlp

_SEX = {"f": "female", "female": "female", "woman": "female",
        "m": "male", "male": "male", "man": "male"}
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
            "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
            "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
            "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
            "ninety": 90}
_NUMBER = r"(?:\d{1,3}|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[ -](?:one|two|three|four|five|six|seven|eight|nine))?|" + "|".join(_NUMBERS) + r")"
_AGE = r"(?:years?[- ]old|yrs?[- ]old|y[ .]*o\.?|yrs?|years?)"


def _norm(value):
    return re.sub(r"\s+", " ", nlp.normalize(str(value))).strip(" .,!?")


def _number(value):
    return int(value) if value.isdigit() else sum(_NUMBERS.get(x, 0) for x in re.split(r"[ -]", value.lower()))


def _events(ledger):
    return ledger.events if hasattr(ledger, "events") else ledger or []


def _self_age(text):
    # A family member's age, disease duration, or a negated age is not identity.
    match = re.search(r"\b(?:i am|i'm|im|my age is)\s+(" + _NUMBER + r")[ -]+(?:years? old|yrs? old)\b", _norm(text))
    return _number(match.group(1)) if match else None


def obtained(case, ledger):
    """Return obtained field records, with original events as evidence links.

    Keys are name, preferred_name, age, sex, only when actually established.
    Each value is {value, evidence: [event, ...], source_kind}. Read-only.
    Patient metadata and audible/displayed wording must agree. The metadata
    carries identity separately, so it cannot release clinical history facts.
    """
    person = case.get("patient", {})
    out = {}
    def add(field, value, event):
        if field not in out:
            out[field] = {"value": value, "evidence": [], "source_kind": event["kind"]}
        if all(old.get("seq") != event.get("seq") for old in out[field]["evidence"]):
            out[field]["evidence"].append(event)
    for event in _events(ledger):
        meta = event.get("meta") or {}
        text = event.get("text", "")
        if event.get("kind") == evidence.STATION_INFO and meta.get("doorway"):
            # Restrict historical support to the patient's posted identity line.
            name = str(person.get("name", ""))
            match = re.match(r"^" + re.escape(name) + r",\s*(?:(\d{1,3})[- ]year[- ]old\s+)?(female|male)\b", text, re.I) if name else None
            if match and _norm(match.group(2)) == _norm(person.get("sex", "")):
                add("name", name, event)
                add("sex", _norm(match.group(2)), event)
                if match.group(1) and int(match.group(1)) == person.get("age"):
                    add("age", int(match.group(1)), event)
        elif event.get("kind") == evidence.PATIENT and not any(meta.get(k) for k in ("uncertain", "no_information", "interrupted")):
            fields = meta.get("identity_fields") or []
            if not isinstance(fields, (list, tuple)):
                continue
            if "age" in fields and _self_age(text) == person.get("age") and person.get("age") is not None:
                add("age", person["age"], event)
            for field in ("name", "preferred_name"):
                value = person.get(field)
                if field in fields and value and re.search(r"\b(?:my name is|i am|i'm|im|you can call me) " + re.escape(_norm(value)) + r"(?=$|[ .,!])", _norm(text)):
                    add(field, value, event)
            if "sex" in fields and re.search(r"\b(?:i am|i'm|im) (?:a )?" + re.escape(_norm(person.get("sex", ""))) + r"\b", _norm(text)):
                add("sex", _norm(person["sex"]), event)
    return out


def matching_events(fields, case, ledger):
    """Prove a demographic description without borrowing another field."""
    known = obtained(case, ledger)
    sources = []
    for key, value in fields.items():
        actual = known.get(key)
        if not actual or _norm(actual["value"]) != _norm(value):
            return []
        for event in actual["evidence"][:1]:
            if all(old.get("seq") != event.get("seq") for old in sources):
                sources.append(event)
    return sources


def demographic_prefix(text):
    """Bounded demographic phrase at the start of a Subjective sentence.

    Return (fields, unconsumed text). The remainder is deliberately kept: a
    supported age must never grant credit to an attached unasked symptom.
    """
    text = text.strip()
    name = r"(?:(?P<name>[A-Z][A-Za-z’' -]+?)(?:,\s*| is (?:a )?))?"
    age = r"(?P<age>" + _NUMBER + r")"
    sex = r"(?P<sex>female|woman|male|man|f|m)"
    pattern = name + age + r"(?:[ -]+" + _AGE + r")?[ /-]*" + sex + r"\b"
    match = re.match(pattern, text, re.I)
    if not match:
        match = re.match(name + sex + r"\s*[/ ]\s*" + age + r"\b", text, re.I)
    if not match:
        return None
    fields = {"age": _number(match.group("age")), "sex": _SEX[match.group("sex").lower()]}
    if match.groupdict().get("name"):
        given = match.group("name").strip()
        if given.lower() not in ("the patient", "patient", "she", "he"):
            fields["name"] = given
    return fields, text[match.end():].strip(" .,")


def demographic_claim(claim, case, ledger):
    """Audit identity alone or reject an unsupported prefix before clinical matching."""
    if claim.get("section") != "S" or claim.get("header") not in ("cc", "hpi", None):
        return None
    parsed = demographic_prefix(claim.get("eval_text") or claim.get("text", ""))
    if not parsed:
        return None
    fields, remainder = parsed
    sources = matching_events(fields, case, ledger)
    if not sources:
        known = obtained(case, ledger)
        wrong = any(k in known and _norm(known[k]["value"]) != _norm(v) for k, v in fields.items())
        links = [e for k in fields for e in known.get(k, {}).get("evidence", [])[:1]]
        return {"verdict": "contradicts" if wrong else "unsupported", "concepts": [],
                "events": links,
                "explanation": "The documented identity disagrees with information actually obtained." if wrong else
                "This demographic description includes information not obtained in this encounter. Ask the patient for their age before documenting it."}
    if remainder:
        return None
    return {"verdict": "supported_supplied" if all(e["kind"] == evidence.STATION_INFO for e in sources) else "supported",
            "concepts": [], "events": sources,
            "explanation": "The demographic description matches identity information actually supplied or answered during this encounter."}
