"""Parsing the submitted SOAP note into addressable pieces.

The structure mirrors the student manual's blank form: S and O are free text
carrying headers, A and P are numbered, paired entries.
"""

from __future__ import annotations

import re

from . import nlp

# Headers the manual's own form and sample notes use.
S_HEADERS = {
    "cc": ["cc", "chief complaint", "c/c"],
    "hpi": ["hpi", "history of present illness", "bpi"],
    "pmh": ["pmh", "pmhx", "past medical history", "past medical hx", "pmh and psh", "pmh/psh", "pmhx/pshx", "pmhx and pshx", "past medical and surgical history", "medical history"],
    "psh": ["psh", "pshx", "past surgical history", "past surgical hx", "surgical history", "surgical hx"],
    "meds": ["meds", "medications", "medication", "med"],
    "sh": ["sh", "shx", "social history", "social hx", "social"],
    "fh": ["fh", "fhx", "family history", "family hx", "family"],
    "allergies": ["allergies", "all", "allergy", "nkda"],
    "ros": ["ros", "review of systems"],
}

O_HEADERS = {
    "vitals": ['vitals', 'vital signs', 'vs', 'supplied doorway vitals', 'supplied vitals', 'doorway vitals', 'supplied doorway vital signs', 'supplied vital signs', 'doorway vital signs'],
    "orthostatic": ["orthostatic vitals", "orthostatic vital signs", "orthostatic measurements", "orthostatics"],
    "general": ["general", "gen", "general appearance"],
    "heent": ["heent", "head", "eyes", "ears", "nose", "throat"],
    "neck": ["neck", "cervical", "neck exam"],
    "heart": ["heart", "cardiac", "cardiovascular", "cv"],
    "chest_wall": ["chest wall", "chestwall", "chest wall exam"],
    "lungs": ["lungs", "lung", "chest", "respiratory", "pulmonary", "resp"],
    "abdomen": ["abd", "abdomen", "abdominal", "gi"],
    "gu": ["gu", "genitourinary", "renal", "back", "flank"],
    "skin": ["skin", "integumentary", "derm"],
    "neuro": ["neuro", "neurologic", "neurological", "cn", "cranial nerves"],
    "msk": ["msk", "musculoskeletal", "extremities", "exts", "ext"],
    "labs": ["labs", "lab", "results", "data", "imaging", "studies", "diagnostics"],
    "osteopathic": ["osteopathic", "osteo", "omt", "structural", "tspine", "lspine",
                    "cspine", "thoracic spine", "lumbar spine"],
}

# Headers the course explicitly names as wrong wording (IPS p. 33).
DISCOURAGED_HEADERS = {
    "cardiovascular": "Heart",
    "cv": "Heart",
    "pulmonary": "Lungs",
    "resp": "Lungs",
    "respiratory": "Lungs",
}

# 2026-09-14: headings describe organization, not one mandatory punctuation.
# Explicit unknown headings still end the preceding section's authority.
_NUM_RE = re.compile(r"^\s*(\d+)\s*[.)\]-]?\s*(.*)$", re.DOTALL)
_LINE_PREFIX = re.compile(r"^[ \t]*(?:(?:\#{1,6}|[-*+•]|\d+[.)])[ \t]+)?")
_LABEL = r"[A-Za-z][A-Za-z /&'().-]{0,64}?"
_ROS_SUBHEADERS = {
    "general", "constitutional", "const", "skin", "integumentary", "derm", "dermatologic",
    "heent", "head", "eyes", "ears", "nose", "throat", "eent", "neck", "breast", "breasts",
    "respiratory", "resp", "pulmonary", "lungs", "pulm", "cardiovascular", "cardiac", "cv", "heart",
    "gastrointestinal", "gi", "abdominal", "abd", "urinary", "genitourinary", "gu", "renal",
    "genital", "reproductive", "gyn", "gynecologic", "sexual", "musculoskeletal", "msk", "ms",
    "neurologic", "neurological", "neuro", "hematologic", "heme", "hematology", "lymphatic",
    "endocrine", "endo", "psychiatric", "psych", "mood", "allergic/immunologic", "allergic/immunological",
}
_HPI_SUBHEADERS = {
    "onset", "location", "duration", "character", "quality", "character/quality",
    "aggravating", "aggravating factors", "alleviating", "alleviating factors",
    "aggravating/alleviating", "aggravating and alleviating factors", "radiation", "timing", "severity",
    "associated symptoms", "pertinent negatives", "treatments tried", "previous episodes", "setting",
}
_VITAL_SUBHEADERS = {
    "bp", "blood pressure", "p", "pulse", "hr", "heart rate", "t", "temp", "temperature",
    "r", "respirations", "respiratory rate", "spo2", "oxygen saturation", "pulse ox",
    "wt", "weight", "ht", "height", "supine", "standing", "seated", "sitting",
}


# These subordinate labels preserve organization only. They never establish
# that a relative, medication, allergy or examination finding was obtained.
_FAMILY_LABEL = re.compile(
    r"(?:(?:biological|maternal|paternal|older|younger|elder|half|step)[ -])?"
    r"(?:mother|father|mom|dad|parents?|brothers?|sisters?|siblings?|"
    r"grandmother|grandfather|grandparents?|aunts?|uncles?|children|sons?|daughters?)")
_MEDICATION_LABELS = {
    "penicillin", "penicillins", "pcn", "amoxicillin", "amoxicillin-clavulanate", "ampicillin",
    "neomycin", "trimethoprim-sulfamethoxazole", "sulfamethoxazole", "tmp-smx", "smx-tmp",
    "sulfa", "sulfonamides", "bactrim", "septra", "cephalexin", "ceftriaxone", "azithromycin",
    "doxycycline", "aspirin", "ibuprofen", "naproxen", "acetaminophen", "paracetamol",
    "amlodipine", "lisinopril", "losartan", "hydrochlorothiazide", "metoprolol", "atorvastatin",
    "simvastatin", "metformin", "insulin", "albuterol", "fluticasone", "budesonide",
    "levothyroxine", "omeprazole", "cetirizine", "loratadine", "sertraline", "fluoxetine",
    "latex", "adhesive", "adhesives", "nickel", "peanut", "peanuts", "shellfish",
}
_SITE_LABEL = re.compile(
    r"(?:(?:volar|dorsal|palmar|plantar|anterior|posterior|medial|lateral|proximal|distal)[ -])?"
    r"(?:(?:left|right|bilateral)[ -])?"
    r"(?:wrist|hand|finger|thumb|forearm|elbow|arm|shoulder|knee|ankle|leg|shin|calf|foot|toe)s?")


def _nested_content_label(key, current, table, canonical):
    # A named body-system heading is still a transition, even when a location
    # could also occur in another system. Unknown arbitrary labels stay boundaries.
    if canonical is not None:
        return False
    if table is S_HEADERS:
        return ((current == "fh" and bool(_FAMILY_LABEL.fullmatch(key)))
                or (current in ("meds", "allergies") and key in _MEDICATION_LABELS))
    return current in ("skin", "msk") and bool(_SITE_LABEL.fullmatch(key))


def _canonical(raw, table):
    key = nlp.normalize(raw).strip(" .")
    for canon, forms in table.items():
        if key in forms:
            return canon
    return None


def _line_header(line, table, forms):
    """Return (raw label, consumed characters) for an explicitly labeled line."""
    prefix = _LINE_PREFIX.match(line).end()
    rest = line[prefix:]
    # A bold/underlined heading can put its colon inside or outside the marks.
    wrapped = re.match(r"^(\*\*|__)(.*?)\1", rest)
    if wrapped:
        label = wrapped.group(2).strip().rstrip(":–—- ")
        tail = rest[wrapped.end():]
        if _canonical(label, table) or not tail.strip() or re.match(r"^[ \t]*[:–—-]", tail) or wrapped.group(2).rstrip().endswith(":"):
            sep = re.match(r"^[ \t]*(?:[:–—-][ \t]*)?", tail).end()
            return label, prefix + wrapped.end() + sep
    # Ordinary standalone labels do not require a colon. Only known labels
    # qualify; a sentence without headers must remain unheaded.
    standalone = rest.strip().rstrip("# ")
    wrappers = {"s", "subjective"} if table is S_HEADERS else {"o", "objective"}
    # NKDA alone is a clinical statement beneath Allergies, not an empty
    # replacement heading. An explicitly punctuated NKDA: label still parses.
    standalone_key = nlp.normalize(standalone)
    if (_canonical(standalone, table) and standalone_key != "nkda") or standalone_key in wrappers:
        return standalone, len(line)
    match = re.match(r"^(" + forms + r")[ \t]*(?::|[–—]|[ \t]-[ \t])[ \t]*", rest, re.I)
    if not match:
        match = re.match(r"^(" + _LABEL + r")[ \t]*(?::|[ \t]+[-–—](?:[ \t]+|$))[ \t]*", rest)
    if match:
        return match.group(1).strip(), prefix + match.end()
    # An explicitly styled, unknown standalone heading is a boundary too.
    if re.match(r"^[ \t]*\#{1,6}[ \t]+", line) and re.fullmatch(_LABEL, standalone):
        return standalone, len(line)
    return None


def parse_headed_section(text, table):
    """Keep original blocks/spans; accept ordinary explicit heading layouts."""
    text = text or ""
    forms = "|".join(re.escape(f) for f in sorted({f for values in table.values() for f in values}, key=len, reverse=True))
    markers = []
    for line in re.finditer(r"[^\n]+", text):
        marked = _line_header(line.group(), table, forms)
        if marked:
            raw, consumed = marked
            markers.append({"start": line.start(), "end": line.start() + consumed, "raw": raw})
    # Preserve inline transitions such as Vitals: ... Heart: ... . Otherwise
    # findings could borrow supplied-vital authority from the preceding label.
    inline = re.compile(r"(?<![A-Za-z0-9])(?:\*\*|__)?(" + forms + r")[ \t]*(?::|[–—]|[ \t]-[ \t])[ \t]*(?:\*\*|__)?[ \t]*", re.I)
    for match in inline.finditer(text):
        if not any(m["start"] <= match.start() < m["end"] for m in markers):
            markers.append({"start": match.start(), "end": match.end(), "raw": match.group(1).strip()})
    markers.sort(key=lambda m: m["start"])
    selected = []
    current = None
    for marker in markers:
        raw = marker["raw"]
        canonical = _canonical(raw, table)
        key = nlp.normalize(raw).strip(" .")
        nested = ((table is S_HEADERS and current == "ros" and key in _ROS_SUBHEADERS)
                  or (table is S_HEADERS and current == "hpi" and key in _HPI_SUBHEADERS)
                  or (table is O_HEADERS and current in ("vitals", "orthostatic") and key in _VITAL_SUBHEADERS)
                  or _nested_content_label(key, current, table, canonical))
        if nested:
            continue
        marker["canonical"] = canonical
        selected.append(marker)
        current = canonical
    blocks = []
    for i, marker in enumerate(selected):
        start = marker["end"]
        end = selected[i + 1]["start"] if i + 1 < len(selected) else len(text)
        # Adjust actual bounds when trimming so claim highlights still point
        # to the exact words the student wrote, including repeated sections.
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        blocks.append({"raw_header": marker["raw"], "canonical": marker["canonical"],
                       "body": text[start:end], "header_start": marker["start"],
                       "body_start": start, "body_end": end})
    wrappers = {"s", "subjective"} if table is S_HEADERS else {"o", "objective"}
    blocks = [b for b in blocks if b["body"] or nlp.normalize(b["raw_header"]) not in wrappers]
    preamble = text[:selected[0]["start"]].strip() if selected else text.strip()
    return blocks, preamble


def _combined_header(blocks, canon):
    """Read all repeated sections; claims continue using their original blocks."""
    matches = [block for block in blocks if block["canonical"] == canon]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return dict(matches[0], body="\n".join(block["body"] for block in matches),
                source_spans=[{"start": block["body_start"], "end": block["body_end"]} for block in matches])


def _section_claims(text, section, header=None):
    serial = section == "O" and (header == "orthostatic" or
        (re.search(r"\b(?:supine|standing|orthostatic)\b", text, re.I)
         and re.search(r"\b(?:BP|blood pressure)\b", text, re.I)))
    if not serial:
        return nlp.split_claims(text)
    # Preserve a preceding non-vital sentence (e.g. cardiac rhythm) as its
    # own claim. Only the serial measurements share context.
    posture = re.search(r"\b(?:supine|standing|orthostatic)\b", text, re.I)
    start = text.rfind(". ", 0, posture.start()) + 2 if posture else 0
    if start == 1:
        start = 0
    pieces = nlp.split_claims(text[:start])
    series = text[start:].strip()
    if series:
        offset = text.find(series, start)
        pieces.append({"text": series, "eval_text": series, "start": offset,
                       "end": offset + len(series)})
    return pieces


class ParsedNote:
    def __init__(self, s_text, o_text, a_entries, p_entries):
        self.s_text = s_text or ""
        self.o_text = o_text or ""
        self.a_raw = [a_entries] if isinstance(a_entries, str) else list(a_entries or [])
        self.p_raw = [p_entries] if isinstance(p_entries, str) else list(p_entries or [])

        self.s_blocks, self.s_preamble = parse_headed_section(self.s_text, S_HEADERS)
        self.o_blocks, self.o_preamble = parse_headed_section(self.o_text, O_HEADERS)
        self.a_entries = [_parse_numbered(x, i) for i, x in enumerate(self.a_raw)]
        self.p_entries = [_parse_numbered(x, i) for i, x in enumerate(self.p_raw)]

    # -- header helpers ---------------------------------------------------
    def s_header(self, canon):
        return _combined_header(self.s_blocks, canon)

    def o_header(self, canon):
        return _combined_header(self.o_blocks, canon)

    def s_headers_present(self):
        return {b["canonical"] for b in self.s_blocks if b["canonical"]}

    def o_headers_present(self):
        return {b["canonical"] for b in self.o_blocks if b["canonical"]}

    def discouraged_headers(self):
        out = []
        for b in self.o_blocks:
            key = nlp.normalize(b["raw_header"])
            if key in DISCOURAGED_HEADERS:
                out.append({"used": b["raw_header"], "expected": DISCOURAGED_HEADERS[key],
                            "pos": b["header_start"]})
        return out

    def first_o_header(self):
        return self.o_blocks[0] if self.o_blocks else None

    # -- claims -----------------------------------------------------------
    def claims(self):
        """Every claim in the note, tagged with section and header."""
        out = []
        for section, blocks, preamble, text in (
                ("S", self.s_blocks, self.s_preamble, self.s_text),
                ("O", self.o_blocks, self.o_preamble, self.o_text)):
            if preamble:
                preamble_start = text.find(preamble)
                for c in _section_claims(preamble, section):
                    out.append({"section": section, "header": None,
                                "raw_header": None, "text": c["text"],
                                "eval_text": c["eval_text"],
                                "start": preamble_start + c["start"], "end": preamble_start + c["end"]})
            for b in blocks:
                # Serial measurements need their neighboring time and posture
                # context. Audit the entire series atom by atom instead of
                # losing "standing" when splitting a semicolon or comma.
                for c in _section_claims(b["body"], section, b["canonical"]):
                    out.append({
                        "section": section, "header": b["canonical"],
                        "raw_header": b["raw_header"], "text": c["text"],
                        "eval_text": c["eval_text"],
                        "start": b["body_start"] + c["start"],
                        "end": b["body_start"] + c["end"],
                    })
        for e in self.a_entries:
            out.append({"section": "A", "header": None, "raw_header": None,
                        "text": e["text"], "eval_text": e["text"],
                        "start": 0, "end": len(e["text"]), "index": e["index"]})
        for e in self.p_entries:
            out.append({"section": "P", "header": None, "raw_header": None,
                        "text": e["text"], "eval_text": e["text"],
                        "start": 0, "end": len(e["text"]), "index": e["index"]})
        return out

    def full_text(self):
        return "\n".join([self.s_text, self.o_text] + self.a_raw + self.p_raw)

    def is_empty(self):
        return not nlp.normalize(self.full_text())

    def to_dict(self):
        return {"S": self.s_text, "O": self.o_text, "A": self.a_raw, "P": self.p_raw}


def _parse_numbered(text, idx):
    text = (text or "").strip()
    m = _NUM_RE.match(text)
    if m:
        return {"index": idx, "number": int(m.group(1)), "text": m.group(2).strip(),
                "raw": text, "numbered": True}
    return {"index": idx, "number": None, "text": text, "raw": text,
            "numbered": False}


def parse(payload):
    return ParsedNote(payload.get("S", ""), payload.get("O", ""),
                      payload.get("A", []), payload.get("P", []))
