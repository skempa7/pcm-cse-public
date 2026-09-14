"""The encounter record: the useful patient information actually obtained.

This is deliberately NOT a second transcript. Talk already holds the
conversation; Record answers a different question -- "what have I learned, and
where does it go in my note?" -- so it is organised by the rows the PCM 2026
SOAP rubric actually scores (Student Manual, Table 4: Onset/Location,
Duration/Chronological, Character/Quality, Severity/Quantity,
Alleviating/Aggravating, Associated/Past/Treatments, PMH and PSH, Medications,
Social, Family, Allergies), not by an invented taxonomy.

Two rules decide what may appear, and both are about evidence rather than
presentation:

  * A fact is listed only when its APPROVED text was actually delivered.
    `patient.delivered_fact_metadata` is the same gate the ledger uses, so a
    hidden case fact, a merely-triggered fact, or a fact the simulator knows
    but never said can never reach the page.
  * A fact is listed once. The patient answering "it started three days ago"
    and later "I think it was Tuesday" refine ONE onset entry rather than
    accumulating two rows, because a note has one onset.

What the patient reported and what the clinician measured are kept apart:
"denies fever" is a reported negative and never becomes an observed vital.
"""
from __future__ import annotations

import re

from . import evidence, identity_evidence, lexicon, nlp, patient as _patient, reproductive_history

# Rubric row -> the authored fact categories that belong in it. Categories come
# from the case library's own `category` vocabulary, so nothing here invents a
# clinical grouping the cases do not already make.
SECTIONS = (
    ("identity",    "subjective", "Patient details",                 ()),
    ("concern",     "subjective", "Chief concern",                  ("chief_complaint",)),
    ("onset",       "hpi",        "Onset / location",               ("onset", "location", "radiation", "setting")),
    ("duration",    "hpi",        "Duration / chronology",          ("timing", "chronology")),
    ("quality",     "hpi",        "Character / quality",            ("quality",)),
    ("severity",    "hpi",        "Severity / quantity",            ("severity",)),
    ("modifiers",   "hpi",        "Alleviating / aggravating",      ("alleviating", "aggravating")),
    ("associated",  "hpi",        "Associated / past / treatments", ("associated", "past_occurrence", "treatment", "pertinent_negative")),
    ("pmh",         "other",      "Past medical & surgical",        ("pmh", "psh")),
    ("medications", "other",      "Medications",                    ("medications",)),
    ("allergies",   "other",      "Allergies",                      ("allergies",)),
    ("social",      "other",      "Social history",                 ("social",)),
    ("family",      "other",      "Family history",                 ("family",)),
    ("obgyn",       "other",      "OB/GYN history",                 ("obgyn",)),
    ("perspective", "other",      "Patient perspective",            ("fife",)),
    ("ros",         "other",      "Review of systems",              ("ros",)),
)
GROUPS = (
    ("subjective", "Patient & chief concern"),
    ("hpi",        "History of present illness"),
    ("other",      "Other history"),
    ("objective",  "Vitals & examination findings"),
)
_CATEGORY_SECTION = {cat: sid for sid, _g, _l, cats in SECTIONS for cat in cats}
_SECTION_GROUP = {sid: g for sid, g, _l, _c in SECTIONS}
_SECTION_LABEL = {sid: l for sid, _g, l, _c in SECTIONS}


# The short row label a fact carries inside its section. The case library's own
# category (and, for the many social facts sharing one category, its
# history_topic) already names the thing; nothing here re-interprets the fact.
_ITEM_LABEL = {
    "chief_complaint": "Reason for visit", "onset": "Onset", "location": "Location",
    "radiation": "Radiation", "setting": "Circumstances", "timing": "Timing",
    "chronology": "Course", "quality": "Quality", "severity": "Severity",
    "alleviating": "Relieved by", "aggravating": "Worsened by",
    "associated": "Associated", "pertinent_negative": "Denies",
    "past_occurrence": "Prior episodes", "treatment": "Tried",
    "pmh": "Medical", "psh": "Surgical", "medications": "Medications",
    "allergies": "Allergies", "social": "Social", "family": "Family",
    "obgyn": "OB/GYN", "fife": "Concern",
}


def _item_label(fact):
    topic = fact.get("history_topic")
    if topic:
        return str(topic).replace("_", " ").capitalize()
    return _ITEM_LABEL.get(fact.get("category"), "Reported")


# --- concise display -------------------------------------------------------
#
# Record is read while writing a note, so "It started about three weeks ago."
# should read "About 3 weeks ago." The shortening is mechanical and reversible,
# never generative: it removes scaffolding that carries no clinical meaning and
# leaves everything else exactly as authored.
#
# Only a PRONOUN subject is removed. "The cough began 4 days ago" keeps its
# subject, because when a case carries more than one complaint the subject is
# the thing that says which timeline this is.
_PRONOUN_OPENER = re.compile(
    r"^(?:it|this|that)(?:'s|\u2019s| is| was| has been| have been| started| began|"
    r" feels like| feels| seems| seemed)\s+", re.I)
# Pure deixis: pointing words that add nothing on a written line.
_DEIXIS_OPENER = re.compile(r"^(?:right here|here)\s*,\s*", re.I)
# Spelled numbers, so "three weeks" scans as "3 weeks". Same value, and any
# hedge in front of it ("about", "maybe") is untouched.
_NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11",
    "twelve": "12", "thirteen": "13", "fourteen": "14", "fifteen": "15",
    "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19",
    "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
    "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
}
_NUMBER_UNITS = ("second|minute|hour|day|week|month|year|time|episode|block|"
                 "flight|step|pack|drink|beer|pound|milligram|mg|cigarette|"
                 "tablet|pill|glass|ounce|mile|stool|puff|unit")
# One modifier may sit between the number and its unit ("two SHORTER episodes"),
# and a rating reads as a number on both sides of "out of".
#
# _signal() normalises through THIS SAME object, so the guard widens with the
# substitution. A separate, wider regex here would make every new conversion
# look like a lost number to the guard, and each one would be rejected.
_NUMBER_RE = re.compile(
    r"\b(%s)\b(?=\s+(?:\w+\s+)?(?:%s)s?\b|\s+out of\b)"
    r"|(?<=\bout of\s)(%s)\b"
    % ("|".join(_NUMBER_WORDS), _NUMBER_UNITS, "|".join(_NUMBER_WORDS)), re.I)


def _digits(match):
    """The matched number word, whichever side of 'out of' it sat on."""
    return _NUMBER_WORDS[(match.group(1) or match.group(2)).lower()]
# A sentence that OPENS with a denial must never lose its opening.
_LEADING_NEGATION = re.compile(r"^(?:no|not|never|none|nothing|neither|nobody)\b", re.I)

# The patient narrates in the first person; a note does not. Removing the
# subject and its auxiliary leaves the clinical content untouched -- every
# surviving word is still one she said. Longest alternative first, so
# "I have had a fever" reads "A fever" rather than "Had a fever". A denial
# keeps its opening, so "I have never had this" is left exactly as it is.
_SUBJECT_OPENER = re.compile(
    r"^(?:there\s+(?:is|are|was|were)"
    r"|i\s+have\s+been|i\s*['\u2019]ve\s+been|i\s+have\s+had|i\s+have"
    r"|i\s*['\u2019]ve|i\s+had|i\s+am|i\s*['\u2019]m|i\s+was"
    r"|i\s+feel|i\s+felt|i\s+get|i\s+keep|i\s+started|i\s+began)"
    r"\s+(?!not\b|no\b|never\b|nothing\b)", re.I)


# Discourse markers and conversational tails. These carry no clinical content
# at all, which is exactly why the Record should not print them: the student is
# scanning for what they obtained, not for how it was said. "yes" and "no" are
# deliberately absent -- to a yes/no question those ARE the answer.
_LEADING_FILLER = re.compile(
    r"^(?:yeah|yep|well|oh|um|uh|honestly|i mean|you know|hmm|sure|okay|ok|"
    r"look|see|right)\s*,\s*"
    # "Now that you mention it -" marks that the detail was volunteered on
    # prompting. The Record already carries that as a flag on the row, so the
    # phrase is discourse, not content.
    r"|^now that you mention it\s*[,\u2014-]\s*", re.I)
# \b matters here: without it this matched INSIDE words -- "sitting upright."
# lost its tail and became "sitting up", and "the pain is low on the right."
# lost the side it was on. "right" is gone from the list for good: as a tag
# question it is filler, but as anatomy it is the finding.
_TRAILING_FILLER = re.compile(
    r"(?:\s*\b(?:i know(?:,? i know)?|sorry|you know|"
    r"that'?s (?:it|about it)|i guess|anyway|that'?s all)\s*[.!?]\s*)+$", re.I)


def condense(value):
    """A shorter rendering of an authored fact, or the value unchanged.

    Everything clinically load-bearing survives verbatim -- negation, hedges,
    numbers, units, anatomy, timing and qualifiers -- because nothing is
    rewritten: the only edits are removing a leading pronoun-and-copula, a
    leading "right here," and spelling numerals as digits.
    """
    text = (value or "").strip()
    if not text or _LEADING_NEGATION.match(text):
        return text
    shortened = _LEADING_FILLER.sub("", text)
    shortened = _TRAILING_FILLER.sub("", shortened).strip()
    if not shortened:
        return text
    shortened = _DEIXIS_OPENER.sub("", shortened)
    shortened = _PRONOUN_OPENER.sub("", shortened)
    shortened = _SUBJECT_OPENER.sub("", shortened)
    shortened = _NUMBER_RE.sub(_digits, shortened)
    shortened = shortened.strip()
    if not shortened:
        return text
    # Never hand back something that lost a negation, a digit or a unit.
    if _signal(shortened) != _signal(text):
        return text
    if shortened is not text:
        shortened = shortened[0].upper() + shortened[1:]
    return shortened


_SIGNAL_RE = re.compile(
    r"\b(?:no|not|never|none|nothing|neither|nobody|n't|denies|without|"
    r"about|approximately|maybe|around|roughly|sometimes|occasionally|"
    r"mild|moderate|severe|worse|better)\b|\d+(?:[./]\d+)?", re.I)


def _signal(text):
    """The parts of a sentence that may not change when it is shortened.

    Spelled numbers count as their digits, so turning "three" into "3" is not
    read as losing a word.
    """
    expanded = _NUMBER_RE.sub(_digits, text)
    return sorted(m.group(0).lower() for m in _SIGNAL_RE.finditer(expanded))


def _negative(fact):
    """Whether this fact is a denial rather than a positive report."""
    if fact.get("category") == "pertinent_negative":
        return True
    concepts = fact.get("concepts") or {}
    polarities = {(c or {}).get("polarity") for c in concepts.values()}
    return bool(polarities) and polarities == {"negative"}


_IDENTITY = re.compile(r"^\s*([^.]*?\b\d{1,3}[- ]year[- ]old\b[^.]*)\.", re.I)


def _identity_line(text):
    """The "Amara Wilson, 28-year-old female" line out of a doorway brief."""
    found = _IDENTITY.search(text or "")
    return (found.group(1).strip() + ".") if found else ""


def hpi_gaps(summary):
    """Which HPI rows of the note are still empty.

    This is the useful half of a symptom-analysis mnemonic without asserting an
    expansion the course files do not settle: the rows are the PCM 2026 SOAP
    rubric's own (Onset/Location, Duration/Chronological, Character/Quality,
    Severity/Quantity, Alleviating/Aggravating, Associated/Past/Treatments), so
    naming an empty one is grounded in the approved scoring, not in a letter
    taken from a mnemonic whose wording is unverified here.
    """
    filled = {section["id"]
              for group in summary.get("groups", [])
              for section in group.get("sections", [])
              if section.get("items")}
    return [{"id": sid, "label": label}
            for sid, group, label, _cats in SECTIONS
            if group == "hpi" and sid not in filled]


def _as_spoken(fact, said, value):
    """The wording the patient actually used for this fact, if recoverable.

    A fact may author several `sp_says` variants; the Record used to keep the
    canonical `value` and the tile labelled it "Said:", so a row could quote a
    sentence the patient never uttered. Whichever variant appears in the
    delivered line IS what was said, and the authorisation gate has already
    established that one of them does.
    """
    spoken = (said or "")
    for variant in list(fact.get("sp_says") or []) + [value]:
        if variant and variant.strip() and variant.strip() in spoken:
            return variant.strip()
    return value


def _direct_denials(case, question, event):
    """Project existing direct-question denials, never infer one from silence.

    Some legacy cases explicitly allow the engine's bounded ROS denial route.
    It records concepts rather than authored fact IDs. Keep its actual question
    and answer associated; an unrelated answer or forged concept is not enough.
    This changes display only, not what the case can deny or what earns credit.
    """
    meta = event.get("meta") or {}
    if (meta.get("kind") != "denial" or meta.get("no_information")
            or not _patient._looks_like_a_symptom_question(nlp.normalize(question))):
        return []
    spoken = nlp.normalize(event.get("text", "")).strip(" .,!?")
    if spoken not in ("no nothing like that", "no i haven't had that", "no i havent had that", "no"):
        return []
    excluded = set(case.get("supersedes_core", [])) | set(case.get("concept_lexicon") or {})
    excluded.update(cid for fact in case.get("facts", []) for cid in fact.get("concepts", {}))
    asked = nlp.find_concepts(question, {cid: lexicon.CORE_CONCEPTS[cid]
        for cid in lexicon.DENIABLE_SYMPTOMS if cid in lexicon.CORE_CONCEPTS and cid not in excluded})
    return [cid for cid, spec in (meta.get("concepts") or {}).items()
            if cid in asked and isinstance(spec, dict) and spec.get("polarity") == "negative"
            and spec.get("value") == "denied on direct questioning"]


_PARTIAL_HISTORY_LABELS = {
    "children": "Children", "children_count": "Number of children",
    "child_age": "Children's ages", "pregnancy_history": "Previous pregnancies",
    "pregnancy_count": "Number of pregnancies", "deliveries": "Previous deliveries",
    "parity": "Obstetric history", "losses": "Pregnancy losses",
    "current_pregnancy": "Pregnancy possibility", "pregnancy_test": "Pregnancy testing",
}


def _approved_partial_entries(definitions, event):
    """Yield only scoped contract text that was spoken with matching metadata.

    A partial statement can be useful in Notes without conferring the bundled
    fact ID or checklist credit. Arbitrary delivered_text metadata is not an
    authoring contract and cannot expose hidden case text here.
    """
    meta = event.get("meta") or {}
    if meta.get("no_information") or meta.get("interrupted"):
        return
    claimed = meta.get("concepts") or {}
    spoken = nlp.normalize(event.get("text", "")).strip()
    for fid, fact in definitions.items():
        fact = reproductive_history.scoped_fact(fact)
        for index, version in enumerate(fact.get("delivery_contract", {}).get("versions", [])):
            if version.get("complete_fact") is not False:
                continue
            text = version.get("text", "").strip()
            normalized = nlp.normalize(text).strip()
            if not normalized or not re.search(r"(?<!\w)" + re.escape(normalized) + r"(?!\w)", spoken):
                continue
            expected = version.get("concepts") or {"delivered_text_" + fid: {"polarity": "positive"}}
            if not all(isinstance(claimed.get(cid), dict)
                       and claimed[cid].get("polarity", "positive") == spec.get("polarity", "positive")
                       and nlp.normalize(claimed[cid].get("value", "")).strip() == normalized
                       for cid, spec in expected.items()):
                continue
            dimensions = version.get("history_dimensions") or []
            dimension = next((d for d in dimensions if d in _PARTIAL_HISTORY_LABELS), None)
            category = ("social" if dimension and dimension.startswith("child") else "obgyn") if dimension else fact.get("category")
            section = _CATEGORY_SECTION.get(category)
            if not section:
                continue
            shortened = condense(text)
            yield fid, index, {
                "section": section, "category": category,
                "label": _PARTIAL_HISTORY_LABELS.get(dimension, _item_label(fact)),
                "text": shortened, "text_full": text if shortened != text else "",
                "reported_negative": _negative({"concepts": expected}),
            }


def summarize(case, events):
    """Project the ledger onto the note's rows. Read-only; never mutates."""
    definitions = {f["id"]: f for f in (case.get("facts") or [])}
    items, order = {}, []
    findings, chart, unanswered = [], [], []
    last_question = ""

    for event in events or []:
        meta = event.get("meta") or {}
        kind = event.get("kind")
        seq = event.get("seq")

        if kind == evidence.STUDENT:
            last_question = event.get("text", "")
        elif kind == evidence.PATIENT:
            # Identity is obtained dialogue, separate from clinical concepts.
            # Validate the words actually delivered before showing a detail.
            for field, detail in identity_evidence.obtained(case, [event]).items():
                fid = "identity:" + field
                if fid not in items:
                    order.append(fid)
                    items[fid] = {
                        "fact_id": fid, "section": "identity", "category": "identity",
                        "label": {"name": "Name", "preferred_name": "Address as",
                                  "age": "Age", "sex": "Sex"}[field],
                        "text": (str(detail["value"]) + " years old" if field == "age"
                                 else str(detail["value"])),
                        "text_full": event.get("text", ""),
                        "reported_negative": False, "volunteered": False,
                        "uncertain": False, "seqs": [],
                    }
                items[fid]["seqs"].append(seq)
            for cid in _direct_denials(case, last_question, event):
                fid = "ros:" + cid
                if fid not in items:
                    order.append(fid)
                    items[fid] = {
                        "fact_id": fid, "section": "ros", "category": "ros",
                        "label": cid.replace("_", " ").capitalize(),
                        "text": event.get("text", ""), "text_full": "",
                        "reported_negative": True, "volunteered": False,
                        "uncertain": False, "seqs": [],
                    }
                items[fid]["seqs"].append(seq)
                items[fid]["text"] = event.get("text", "")
            claimed = meta.get("facts_released") or []
            authorised = []
            for fid in claimed:
                fact = definitions.get(fid)
                if not fact:
                    continue
                # The same authorisation the evidence ledger applies: only text
                # the patient actually spoke may carry the fact's identity.
                approved = _patient.delivered_fact_metadata(fact, event.get("text", "")) or {}
                if fid in (approved.get("facts_released") or []):
                    authorised.append(fid)
            for source_id, version_index, detail in _approved_partial_entries(definitions, event):
                # A complete delivered statement already subsumes its clauses.
                if source_id in items or source_id in authorised:
                    continue
                partial_id = "partial:%s:%s" % (source_id, version_index)
                if partial_id in items:
                    items[partial_id]["seqs"].append(seq)
                    continue
                items[partial_id] = dict(
                    detail, fact_id=partial_id, source_fact_id=source_id, partial=True,
                    volunteered=bool(meta.get("volunteered")),
                    uncertain=bool(meta.get("uncertain")), seqs=[seq])
                order.append(partial_id)
            if not authorised:
                # An unanswered question is a gap, not a fact. Naming it keeps
                # "asked and refused" distinct from "never asked" without
                # inventing an "Unknown" row for every field.
                if meta.get("no_information"):
                    unanswered.append({"seq": seq, "text": event.get("text", "")})
                continue
            for fid in authorised:
                fact = definitions[fid]
                section = _CATEGORY_SECTION.get(fact.get("category"))
                if not section:
                    continue
                # Condense WHAT SHE SAID, not the fact's canonical wording.
                # A fact may author several variants; showing a row derived
                # from one while the patient spoke another puts words in her
                # mouth, and makes the row and its "Said:" tooltip disagree.
                said = _as_spoken(fact, event.get("text", ""),
                                  fact.get("value") or "")
                if fid in items:
                    entry = items[fid]
                    entry["seqs"].append(seq)
                    if said:
                        entry["text"] = condense(said)
                        entry["text_full"] = said if entry["text"] != said else ""
                    continue
                # Once the full statement is obtained, consolidate its earlier
                # partial rows at their original place without duplicate facts.
                partial_ids = [pid for pid in order if items[pid].get("source_fact_id") == fid]
                if partial_ids:
                    position = order.index(partial_ids[0])
                    for pid in partial_ids:
                        order.remove(pid)
                        del items[pid]
                    order.insert(position, fid)
                value = said
                shortened = condense(value)
                items[fid] = {
                    "fact_id": fid, "section": section,
                    "category": fact.get("category"),
                    "label": _item_label(fact),
                    "text": shortened,
                    # Kept so the exact disclosed wording is always recoverable;
                    # only present when shortening actually changed something.
                    "text_full": (lambda said: said if shortened != said else "")(
                        _as_spoken(fact, event.get("text", ""), value)),
                    "reported_negative": _negative(fact),
                    "volunteered": bool(meta.get("volunteered")),
                    "uncertain": bool(meta.get("uncertain")),
                    "seqs": [seq],
                }
                if fid not in order:
                    order.append(fid)

        elif kind == evidence.EXAM_FINDING:
            findings.append({
                "label": meta.get("label") or meta.get("maneuver_id") or "Examination",
                "text": event.get("text", ""),
                "documented_as": meta.get("documented_as") or "",
                "components": meta.get("components") or [],
                "seqs": [seq],
            })

        elif kind == evidence.EXAM_REFUSED:
            findings.append({
                "label": (meta.get("label") or "Examination") + " — declined",
                "text": event.get("text", ""), "documented_as": meta.get("documented_as") or "",
                "components": [], "declined": True, "seqs": [seq],
            })

        elif kind == evidence.STATION_INFO:
            text = event.get("text", "")
            if meta.get("vitals") or meta.get("result"):
                chart.append({
                    "label": meta.get("label") or ("Doorway vitals" if meta.get("vitals")
                                                   else "Supplied result"),
                    "text": text, "seqs": [seq],
                })
                continue
            # Posted demographics stay supplied information. Older attempts
            # may legitimately include age; new ones provide name and sex only.
            supplied = identity_evidence.obtained(case, [event])
            if supplied:
                identity = _identity_line(text) if "age" in supplied else (
                    str(supplied["name"]["value"]) + ", " + str(supplied["sex"]["value"]) + ".")
                chart.append({"label": "Patient details", "text": identity, "seqs": [seq]})

    sections = {}
    for fid in order:
        sections.setdefault(items[fid]["section"], []).append(items[fid])

    groups = []
    for gid, glabel in GROUPS:
        rows = []
        if gid == "objective":
            if chart:
                rows.append({"id": "chart", "label": "Supplied chart information", "items": chart})
            if findings:
                rows.append({"id": "exam", "label": "Examination findings", "items": findings})
        else:
            for sid, sgroup, slabel, _cats in SECTIONS:
                if sgroup != gid or not sections.get(sid):
                    continue
                rows.append({"id": sid, "label": slabel, "items": sections[sid]})
        if rows:
            groups.append({"id": gid, "label": glabel, "sections": rows})

    return {
        "groups": groups,
        "facts": len(order),
        "findings": len(findings),
        "unanswered": unanswered[-6:],
    }
