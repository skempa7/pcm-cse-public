"""Small, deterministic text helpers for Scribbi.

Everything here is pure string work: splitting a note line into reviewable
sentences, finding the values a scribe can mishear (numbers, units, sides),
and reading spinal levels out of a structural-examination line.
"""

from __future__ import annotations

import re

from .. import nlp

# --------------------------------------------------------------------------
# Sentence chips
# --------------------------------------------------------------------------

# Abbreviations whose trailing period does not end a sentence.
_ABBREVIATIONS = [
    "y.o.", "yo.", "vs.", "approx.", "e.g.", "i.e.", "dr.", "mr.", "mrs.",
    "ms.", "st.", "no.", "q.d.", "b.i.d.", "t.i.d.", "q.i.d.", "p.r.n.",
    "a.m.", "p.m.", "etc.", "min.", "hr.", "hrs.", "wk.", "wks.", "mo.",
    "yr.", "yrs.", "ft.", "in.", "lb.", "lbs.", "oz.", "pt.",
]
_PLACEHOLDER = "⁣"  # invisible separator, never present in case text


def _protect(text: str) -> str:
    out = re.sub(r"(\d)\.(\d)", lambda m: m.group(1) + _PLACEHOLDER + m.group(2), text)
    lowered = out.lower()
    for abbr in _ABBREVIATIONS:
        start = 0
        while True:
            idx = lowered.find(abbr, start)
            if idx < 0:
                break
            before = lowered[idx - 1] if idx > 0 else " "
            if before.isalnum():
                start = idx + 1
                continue
            protected = out[idx:idx + len(abbr)].replace(".", _PLACEHOLDER)
            out = out[:idx] + protected + out[idx + len(abbr):]
            lowered = out.lower()
            start = idx + len(abbr)
    return out


def split_sentences(text: str) -> list:
    """Split prose into sentence-sized pieces, keeping their punctuation.

    A semicolon also ends a piece: clinical notes chain clauses with it, and
    each clause is a separate claim a reviewer may need to fix.
    """
    text = (text or "").strip()
    if not text:
        return []
    protected = _protect(text)
    pieces = re.split(r"(?<=[.!?])\s+(?=[\"'(\[A-Z0-9])|(?<=;)\s+", protected)
    out = []
    for piece in pieces:
        piece = piece.replace(_PLACEHOLDER, ".").strip()
        if piece:
            out.append(piece)
    return out


# --------------------------------------------------------------------------
# Line labels
# --------------------------------------------------------------------------

SUBJECTIVE_LABELS = {
    "cc": "CC", "chief complaint": "CC", "hpi": "HPI", "pmh": "PMH",
    "additional pmh": "Additional PMH", "psh": "PSH", "meds": "Meds",
    "medications": "Meds", "allergies": "Allergies", "sh": "SH",
    "social history": "SH", "fh": "FH", "family history": "FH", "ros": "ROS",
    "perspective": "Perspective", "patient perspective": "Perspective",
    "patient concern": "Patient concern", "care needs": "Care needs",
    "reproductive history": "Reproductive history", "pain pattern": "Pain pattern",
    "bowel history": "Bowel history", "urinary history": "Urinary history",
    "voided volume": "Voided volume", "ob/gyn": "OB/GYN",
}
OBJECTIVE_LABELS = {
    "vitals": "Vitals", "general": "General", "heent": "HEENT", "neck": "Neck",
    "heart": "Heart", "lungs": "Lungs", "chest wall": "Chest wall",
    "abdomen": "Abdomen", "abd": "Abdomen", "gu": "GU", "rectal": "Rectal",
    "pelvic": "Pelvic", "breast": "Breast", "skin": "Skin",
    "extremities": "Extremities", "ext": "Extremities", "exts": "Extremities",
    "musculoskeletal": "Musculoskeletal", "msk": "Musculoskeletal",
    "neurologic": "Neurologic", "neuro": "Neurologic", "lymphatic": "Lymphatic",
    "osteopathic": "Osteopathic", "labs": "Results", "results": "Results",
}
_LABEL_RE = re.compile(r"^([A-Za-z][A-Za-z /]{0,28}?)\s*:\s*(.*)$", re.S)


def split_label(line: str, table: dict):
    """('HPI', 'rest of line') when the line starts with a known label."""
    m = _LABEL_RE.match(line.strip())
    if not m:
        return None, line.strip()
    key = m.group(1).strip().lower()
    if key in table:
        return table[key], m.group(2).strip()
    return None, line.strip()


# --------------------------------------------------------------------------
# Patient voice
# --------------------------------------------------------------------------

# "I" is only first person in capitals; the possessives and objects can start
# a sentence ("My mother has asthma").
_FIRST_PERSON = re.compile(r"\b(I|I'm|I've|I'd|I'll|[Mm]y|[Mm]e|[Mm]ine|[Mm]yself|[Ww]e|[Oo]ur|[Uu]s)\b")


def has_first_person(text: str) -> bool:
    return bool(_FIRST_PERSON.search(text or ""))


def as_patient_quote(text: str, label: str = "", continued: bool = False) -> str:
    """Quote first-person wording so a scribe draft stays in chart voice.

    `continued` quotes a statement that follows another quoted one in the
    same line without repeating "Patient states"."""
    body = (text or "").strip().rstrip(";").strip()
    if not body:
        return body
    if body.startswith('"'):
        return body
    if label == "CC" or continued:
        return '"' + body + '"'
    verb = "asks" if body.endswith("?") else "states"
    return 'Patient %s, "%s"' % (verb, body)


def outside_quotes(text: str) -> str:
    """The text with every double-quoted passage removed."""
    return re.sub(r'"[^"]*"', " ", text or "")


# --------------------------------------------------------------------------
# Normalized matching
# --------------------------------------------------------------------------

def norm(text: str) -> str:
    return nlp.normalize(text or "")


def contains_any(text: str, patterns) -> bool:
    """True when any regex in `patterns` matches the normalized text."""
    t = norm(text)
    return any(re.search(p, t) for p in patterns)


def tokens(text: str) -> list:
    return re.findall(r"[a-z0-9]+(?:/[0-9]+)?", norm(text))


STOPWORDS = set("""
a an and are as at be been being but by for from had has have he her hers him his
i if in into is it its of on or our she so than that the their them then there
these they this those to was were which while who will with without would you your
patient reports states said says about also any after before because both each
very more most some such only other again one two three four five six seven eight
nine ten no not denies denied reported notes noted has had currently current
""".split())


def content_words(text: str) -> list:
    return [w for w in tokens(text) if w not in STOPWORDS and len(w) > 2 and not w.isdigit()]


def stem_pattern(word: str) -> str:
    """A forgiving prefix pattern: 'kidneys' and 'kidney' both match 'kidne'."""
    w = re.escape(word.lower())
    if len(word) > 6:
        w = re.escape(word.lower()[:max(5, len(word) - 3)])
    return r"\b" + w


# --------------------------------------------------------------------------
# Values a scribe can mishear
# --------------------------------------------------------------------------

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "a couple of": 2, "a couple": 2, "several": 3, "a few": 3,
}
_NUMBER = r"(\d+(?:\.\d+)?|" + "|".join(sorted((re.escape(k) for k in NUMBER_WORDS), key=len, reverse=True)) + r")"
DURATION_RE = re.compile(r"\b" + _NUMBER + r"(?:\s*|-)(hours?|days?|weeks?|months?|years?)\b", re.I)
RATING_RE = re.compile(r"\b(\d{1,2})\s*/\s*10\b")
DOSE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s?(mg|mcg|g|units?|mL)\b", re.I)
SIDE_RE = re.compile(r"\b(right|left|RIGHT|LEFT|Right|Left)\b")
AGE_RE = re.compile(r"\b(\d{2})(-year-old|\s*yo\b|\s*y/o\b)")
_UNIT_SWAP = {"hour": "day", "day": "week", "week": "month", "month": "year", "year": "month"}


def number_value(raw: str):
    raw = raw.lower().strip()
    if raw in NUMBER_WORDS:
        return NUMBER_WORDS[raw]
    try:
        return float(raw)
    except ValueError:
        return None


def swap_unit(unit: str) -> str:
    base = unit.lower().rstrip("s")
    new = _UNIT_SWAP.get(base, "week")
    plural = unit.lower().endswith("s")
    return new + ("s" if plural else "")


def swap_side(word: str) -> str:
    pairs = {"right": "left", "left": "right", "RIGHT": "LEFT", "LEFT": "RIGHT",
             "Right": "Left", "Left": "Right"}
    return pairs[word]


def side_is_laterality(text: str, start: int) -> bool:
    """'right flank' is a side; 'all right' and 'right away' are not."""
    before = text[max(0, start - 5):start].lower()
    after = text[start:start + 16].lower()
    if before.endswith("all "):
        return False
    if re.match(r"(right|left)\s+(away|now|then|after|before|here|there|over|behind|alone|off|out)\b", after):
        return False
    if re.match(r"left\s+(the|her|his|their|school|work|home|early|for)\b", after):
        return False
    return True


def sides_in(text: str) -> list:
    return [m.group(1).lower() for m in SIDE_RE.finditer(text or "")
            if side_is_laterality(text, m.start())]


def values_in(text: str) -> dict:
    """Every mishearable value in a sentence, normalized for comparison."""
    t = text or ""
    return {
        "durations": sorted("%s %s" % (number_value(m.group(1)), m.group(2).lower().rstrip("s"))
                            for m in DURATION_RE.finditer(t)),
        "ratings": sorted(m.group(1) for m in RATING_RE.finditer(t)),
        "doses": sorted("%s %s" % (m.group(1), m.group(2).lower()) for m in DOSE_RE.finditer(t)),
        "sides": sorted(sides_in(t)),
        "numbers": sorted(re.findall(r"\b\d+(?:\.\d+)?\b", t)),
    }


# --------------------------------------------------------------------------
# Spinal levels (structural examination)
# --------------------------------------------------------------------------

_SEGMENTS = (["occiput"] + ["C%d" % i for i in range(1, 8)] + ["T%d" % i for i in range(1, 13)]
             + ["L%d" % i for i in range(1, 6)] + ["sacrum"])
_INDEX = {name.lower(): i for i, name in enumerate(_SEGMENTS)}
# Bare "S1"/"S2" are heart sounds far more often than sacral segments in a
# note, so the sacrum is only recognized by name.
_LEVEL_TOKEN = re.compile(r"\b(occiput|OA|sacrum|sacral|[CTL]\s?-?\s?\d{1,2})\b", re.I)
_RANGE = re.compile(r"\b([CTL]\s?\d{1,2})\s*(?:-|–|—|to|through|thru)\s*([CTL]?\s?\d{1,2})\b", re.I)
DESCRIPTOR_PATTERNS = [
    r"tissue texture", r"\bttc\b", r"\btart\b", r"tender", r"hypertonic", r"\brotat",
    r"\brotated\b", r"side\s?bent", r"sidebend", r"restrict", r"asymmetr", r"boggy",
    r"\bropy\b", r"somatic dysfunction", r"\bsd\b", r"hypertonicity", r"spasm",
    r"\b[fe]rs[rl]\b", r"\bn[rs][rl]\b",
]


def _segment_index(token: str):
    t = re.sub(r"[\s-]", "", token).lower()
    if t in ("oa", "occiput"):
        return _INDEX["occiput"]
    if t.startswith("sacr"):
        return _INDEX["sacrum"]
    return _INDEX.get(t)


def levels_in(text: str) -> set:
    """Every spinal segment named in the text, ranges expanded."""
    out = set()
    raw = text or ""
    for m in _RANGE.finditer(raw):
        a = m.group(1)
        b = m.group(2)
        if not re.match(r"[CTL]", b.strip(), re.I):
            b = a.strip()[0] + b.strip()
        ia, ib = _segment_index(a), _segment_index(b)
        if ia is not None and ib is not None:
            lo, hi = sorted((ia, ib))
            out.update(range(lo, hi + 1))
    for m in _LEVEL_TOKEN.finditer(raw):
        idx = _segment_index(m.group(1))
        if idx is not None:
            out.add(idx)
    return out


def level_names(indices) -> list:
    return [_SEGMENTS[i] for i in sorted(indices)]


def has_descriptor(text: str) -> bool:
    t = norm(text)
    return any(re.search(p, t) for p in DESCRIPTOR_PATTERNS)


def expand_level_range(spec: str) -> set:
    """'T10-L1' -> indices of T10, T11, T12, L1."""
    return levels_in((spec or "").replace("-", " through "))
