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
    "pmh": ["pmh", "past medical history", "pmh and psh", "pmh/psh", "medical history"],
    "psh": ["psh", "past surgical history", "surgical history"],
    "meds": ["meds", "medications", "medication", "med"],
    "sh": ["sh", "social history", "social"],
    "fh": ["fh", "family history", "family"],
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

_HEADER_RE = re.compile(r"^\s*([A-Za-z][A-Za-z /&']{0,34}?)\s*:\s*", re.MULTILINE)
_NUM_RE = re.compile(r"^\s*(\d+)\s*[.)\]-]?\s*(.*)$")


def _canonical(raw, table):
    key = nlp.normalize(raw)
    for canon, forms in table.items():
        if key in forms:
            return canon
    for canon, forms in table.items():
        for f in forms:
            if key.startswith(f) and (len(key) - len(f)) <= 3:
                return canon
    return None


def parse_headed_section(text, table):
    """Split a free-text section into {canonical_header: {...}} plus leftovers."""
    text = text or ""
    # An explicit inline section label has the same scope as a label at the
    # start of a line. Otherwise "Vitals: ... Lungs: ..." lends chart-vital
    # authority to everything that follows. Unknown line headers still form
    # unclassified blocks; an unfamiliar label never confers evidence.
    forms = sorted({f for forms in table.values() for f in forms}, key=len, reverse=True)
    inline = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(re.escape(f) for f in forms)
                        + r")\s*:\s*", re.I)
    matches = list(_HEADER_RE.finditer(text))
    for match in inline.finditer(text):
        if not any(m.start() <= match.start() < m.end() for m in matches):
            matches.append(match)
    matches.sort(key=lambda m: m.start())
    blocks = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw = m.group(1).strip()
        blocks.append({
            "raw_header": raw,
            "canonical": _canonical(raw, table),
            "body": text[start:end].strip(),
            "header_start": m.start(),
            "body_start": start,
            "body_end": end,
        })
    preamble = text[:matches[0].start()].strip() if matches else text.strip()
    return blocks, preamble


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
        self.a_raw = list(a_entries or [])
        self.p_raw = list(p_entries or [])

        self.s_blocks, self.s_preamble = parse_headed_section(self.s_text, S_HEADERS)
        self.o_blocks, self.o_preamble = parse_headed_section(self.o_text, O_HEADERS)
        self.a_entries = [_parse_numbered(x, i) for i, x in enumerate(self.a_raw)]
        self.p_entries = [_parse_numbered(x, i) for i, x in enumerate(self.p_raw)]

    # -- header helpers ---------------------------------------------------
    def s_header(self, canon):
        for b in self.s_blocks:
            if b["canonical"] == canon:
                return b
        return None

    def o_header(self, canon):
        for b in self.o_blocks:
            if b["canonical"] == canon:
                return b
        return None

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
                for c in _section_claims(preamble, section):
                    out.append({"section": section, "header": None,
                                "raw_header": None, "text": c["text"],
                                "eval_text": c["eval_text"],
                                "start": c["start"], "end": c["end"]})
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
