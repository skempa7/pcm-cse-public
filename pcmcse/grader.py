"""The PCM 2026 SOAP note grading table, implemented row by row.

Row labels, point values and conditions are transcribed from the student
manual's grading table (Table 4).  Every deduction carries the rubric row, the
note passage, the encounter evidence, an explanation and the points affected,
so a score can always be argued with.

Where the rubric leaves something unspecified, the interpretation is named in
`uncertain` on the row and echoed in the assumption manifest.  Nothing invents
a deduction, an automatic-failure rule, a partial-credit policy or a passing
cutoff that the materials do not provide.
"""

from __future__ import annotations

import re

from . import config, lexicon, nlp, differential_supplements
from . import claims as claims_mod

SUBJECTIVE_ROWS = [
    ("age_sex", "Age and Sex"),
    ("cc_clear", "Chief Complaint Clear"),
    ("onset_location", "Onset/Location"),
    ("duration_chronological", "Duration/Chronological"),
    ("character_quality", "Character/Quality"),
    ("severity_quantity", "Severity/Quantity"),
    ("alleviating_aggravating", "Alleviating/Aggravating"),
    ("associated_past_treatments", "Associated/Past/Treatments"),
    ("pmh_psh", "PMH and PSH"),
    ("medications", "Medications"),
    ("social_history", "Social History"),
    ("family_history", "Family History"),
    ("allergies", "Allergies"),
    ("ros", "ROS (must have min 3)"),
]

OBJECTIVE_ROWS = [
    ("vitals", "Vitals"),
    ("general", "General"),
    ("heart_lungs", "Heart and Lungs"),
    ("most_relevant", "Most relevant system"),
    ("other_systems", "Other system(s)"),
    ("osteopathic", "Osteopathic"),
]

SUBJECTIVE_CONDITIONS = [
    "No credit for inaccurate, unclear, or non-specific documentation",
    "No credit if headers not used",
    "Always include tobacco, alcohol, and drug use",
    "Biological parents and siblings",
    "3 symptoms from 3 different pertinent systems (Total of 9 symptoms)",
]

OBJECTIVE_CONDITIONS = [
    "Vitals must be documented first",
    "No credit for inappropriate abbreviation",
    'No credit for "Normal"',
    "No credit for inappropriate, unclear, or non-specific documentation; "
    "no credit if headers not used",
    "Must document level and dysfunction for credit",
]

ASSESSMENT_CONDITIONS = [
    "Differential Diagnosis #1 should be your most likely differential",
    "Require 3 different elements of VINDICATE",
    "No credit if diagnosis does not correlate with case",
    "Must be numbered 1, 2, 3",
]

PLAN_CONDITIONS = [
    "Must have at least three different elements (of MOTHERR) per plan",
    "Must be numbered 1, 2, 3 and correlate with respective assessment",
    "Be as specific as possible (ie, left ankle x-ray vs x-ray)",
]

# Which case fact categories feed each Subjective row.
ROW_CATEGORIES = {
    "onset_location": ["onset", "location"],
    "duration_chronological": ["chronology", "timing", "onset"],
    "character_quality": ["quality"],
    "severity_quantity": ["severity"],
    "alleviating_aggravating": ["alleviating", "aggravating"],
    "associated_past_treatments": ["associated", "past_occurrence", "treatment",
                                   "pertinent_negative"],
    "pmh_psh": ["pmh", "psh"],
    "medications": ["medications"],
    "social_history": ["social", "obgyn"],
    "family_history": ["family"],
    "allergies": ["allergies"],
}

# Sex as notes actually write it.  The old row compared the documented sex
# with the case's on the FIRST CHARACTER, so "woman" read as a mismatch
# against "female" while "man" and "male" both passed as "m"; these words are
# ordinary documentation of a sex, not synonyms to be guessed at letter by
# letter.
_SEX_TERMS = {
    "f": "female", "female": "female", "woman": "female", "women": "female",
    "girl": "female", "lady": "female",
    "m": "male", "male": "male", "man": "male", "men": "male", "boy": "male",
    "gentleman": "male",
}

# "24 yo", "24-year-old", "24 y.o.", "24 yrs old" and "24F" are one fact
# written five ways.  The separators are flattened before matching (see
# `_demographic_text`), so only the spellings themselves are listed here.
_AGE_UNIT = r"(?:years?\s*old|yrs?\s*old|y\s*o|yrs?|years?)"
_AGE_WITH_UNIT = re.compile(r"(?<![a-z0-9])(\d{1,3})\s+" + _AGE_UNIT + r"(?![a-z])")
_AGE_WITH_SEX = re.compile(
    r"(?<![a-z0-9])(\d{1,3})\s+(" +
    "|".join(sorted(_SEX_TERMS, key=len, reverse=True)) + r")(?![a-z])")

# How far from the age a sex word may sit and still belong to the same
# description.  "24 yo well-appearing female" is one phrase; a "she" a
# sentence later is not the demographic line.
_SEX_WINDOW = 4

_IMAGING = ["x-ray", "xray", "radiograph", "ct", "mri", "ultrasound",
            "us", "echo", "scan"]
_BODY_LOC = ["chest", "abdomen", "abdominal", "pelvis", "pelvic", "head", "left",
             "right", "renal", "kidney", "lumbar", "cervical", "thoracic", "knee",
             "ankle", "shoulder", "wrist", "hip", "spine", "neck", "sinus",
             "extremity", "foot", "hand", "bilateral", "brain", "cerebral",
             "intracranial", "venography", "angiography", "carotid", "rib",
             "kub", "cxr", "upper gi", "biliary", "liver", "gallbladder", "bladder"]


# Which note headers each row's content lives under.  Without this, a problem
# claim in one header can strip credit from an unrelated row that happens to
# share a few characters of text.
ROW_HEADERS = {
    "age_sex": ["hpi", "cc", None], "cc_clear": ["cc", "hpi"],
    "onset_location": ["hpi"], "duration_chronological": ["hpi"],
    "character_quality": ["hpi"], "severity_quantity": ["hpi"],
    "alleviating_aggravating": ["hpi"], "associated_past_treatments": ["hpi"],
    "pmh_psh": ["pmh", "psh"], "medications": ["meds"],
    "social_history": ["sh"], "family_history": ["fh"],
    "allergies": ["allergies"], "ros": ["ros"],
    "vitals": ["vitals"], "general": ["general"],
    "heart_lungs": ["heart", "lungs"],
    # most_relevant / other_systems are filled in per case, from the area of
    # concern -- a fixed list would let one bad sentence cost both rows.
    "most_relevant": [],
    "other_systems": [],
    "osteopathic": ["osteopathic"],
}


def _dedupe(evidence):
    """One line per source event; a row often matches the same quote twice."""
    out, seen = [], set()
    for e in evidence or []:
        key = (e.get("seq"), e.get("text"))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


class Row:
    def __init__(self, rid, label, category, points):
        self.id = rid
        self.label = label
        self.category = category
        self.headers = ROW_HEADERS.get(rid, [])
        self.points_available = points
        self.earned = False
        self.points_earned = 0
        self.why = ""
        self.passage = ""
        self.evidence = []
        self.conditions = []
        self.advisories = []
        self.uncertain = ""

    def award(self, why, passage="", evidence=None):
        self.earned = True
        self.points_earned = self.points_available
        self.why = why
        self.passage = passage
        self.evidence = _dedupe(evidence)
        return self

    def deny(self, why, passage="", evidence=None, condition=""):
        self.earned = False
        self.points_earned = 0
        self.why = why
        self.passage = passage
        self.evidence = _dedupe(evidence)
        if condition:
            self.conditions.append(condition)
        return self

    def to_dict(self):
        return {
            "id": self.id, "label": self.label, "category": self.category,
            "points_available": self.points_available,
            "points_earned": self.points_earned, "earned": self.earned,
            "why": self.why, "passage": self.passage, "evidence": self.evidence,
            "conditions_applied": self.conditions, "advisories": self.advisories,
            "uncertain": self.uncertain,
        }


def grade(parsed, ledger, case, audit_result, settings=None):
    settings = settings or config.load_settings()
    scoring = settings.get("scoring", config.SCORING_DEFAULTS)
    rows = []

    supported = _supported_index(audit_result)
    problems = _problem_index(audit_result)

    rows += _grade_subjective(parsed, case, supported, problems, scoring)
    rows += _grade_objective(parsed, ledger, case, supported, problems, scoring)
    a_rows, a_meta = _grade_assessment(parsed, case, scoring)
    rows += a_rows
    p_rows, p_meta = _grade_plan(parsed, case, ledger, audit_result, scoring)
    rows += p_rows
    rows.append(_grade_spelling(parsed))

    totals = {}
    for row in rows:
        c = totals.setdefault(row.category, {"earned": 0, "available": 0})
        c["earned"] += row.points_earned
        c["available"] += row.points_available

    total_earned = sum(r.points_earned for r in rows)
    total_available = sum(r.points_available for r in rows)

    return {
        "rows": [r.to_dict() for r in rows],
        "categories": totals,
        "total_earned": total_earned,
        "total_available": total_available,
        "percent": round(100.0 * total_earned / total_available, 1) if total_available else 0.0,
        "assessment_meta": a_meta,
        "plan_meta": p_meta,
        "conditions": {
            "Subjective": SUBJECTIVE_CONDITIONS,
            "Objective": OBJECTIVE_CONDITIONS,
            "Assessment": ASSESSMENT_CONDITIONS,
            "Plan": PLAN_CONDITIONS + [
                "Specific Education: must be documented in one of your plans; "
                "must be specific",
                "Specific Follow-Up: must be documented in Plan #1 only; "
                "disposition also acceptable if applicable",
            ],
        },
        "grade_kind": "rubric-based practice grade",
        "disclaimer": (
            "This is a rubric-based practice score computed from the PCM 2026 "
            "SOAP note grading table. It is not a prediction of a faculty "
            "grade, and PCM I is pass/fail on competencies rather than on a "
            "note percentage."),
    }


# ---------------------------------------------------------------------------
# Indices over the audit
# ---------------------------------------------------------------------------

def _supported_index(audit_result):
    """concept -> the supported claim that documented it."""
    out = {}
    for c in audit_result["claims"]:
        if c["verdict"] in ("supported", "supported_supplied"):
            for cid in c["concepts"]:
                out.setdefault(cid, c)
    return out


def _problem_index(audit_result):
    """section -> list of problem claims, for the accuracy conditions."""
    out = {"S": [], "O": [], "A": [], "P": []}
    for c in audit_result["claims"]:
        if c.get("credit_blocked") or c["verdict"] in ("unsupported", "contradicts", "overbroad", "misplaced",
                            "counseling_unsupported"):
            out.setdefault(c["section"], []).append(c)
    return out


def _facts_in_categories(case, cats):
    return [f for f in case.get("facts", []) if f.get("category") in cats]


def _row_concepts(case, cats):
    """concept id -> {'fact': ..., 'categories': {...}}.

    One concept id can be declared by several facts (a "constant ache" is both
    quality and timing), so categories accumulate rather than overwrite.
    """
    out = {}
    for f in _facts_in_categories(case, cats):
        for cid in (f.get("concepts") or {}):
            rec = out.setdefault(cid, {"fact": f, "categories": set()})
            rec["categories"].add(f.get("category"))
    return out


def _documented(concepts, supported):
    hits = [(cid, supported[cid]) for cid in concepts if cid in supported]
    return hits


def _block_problem(problems, section, header):
    """Problems inside a specific header block."""
    return [p for p in problems.get(section, []) if p.get("header") == header]


# ---------------------------------------------------------------------------
# Subjective
# ---------------------------------------------------------------------------

def _grade_subjective(parsed, case, supported, problems, scoring):
    rows = []
    headers = parsed.s_headers_present()
    header_ok = bool(headers)
    require_all = scoring.get("require_all_row_elements", False)

    for rid, label in SUBJECTIVE_ROWS:
        row = Row(rid, label, "Subjective", 2)

        if not header_ok:
            row.deny("No headers were used anywhere in the Subjective section.",
                     condition="No credit if headers not used")
            rows.append(row)
            continue

        if rid == "age_sex":
            _row_age_sex(row, parsed, case)
        elif rid == "cc_clear":
            _row_cc(row, parsed, case, headers)
        elif rid == "ros":
            _row_ros(row, parsed, case, supported, scoring)
        elif rid == "social_history":
            _row_social(row, parsed, case, supported, headers)
        elif rid == "family_history":
            _row_family(row, parsed, case, supported, headers)
        elif rid in ("pmh_psh", "medications", "allergies"):
            _row_headed(row, rid, parsed, case, supported, headers)
        else:
            _row_hpi_element(row, rid, parsed, case, supported, require_all)

        # Accuracy condition applies to every Subjective row.
        if row.earned:
            _apply_accuracy(row, problems, "S")
        rows.append(row)
    return rows


def _demographic_text(text):
    """The Subjective text with demographic punctuation flattened.

    "24-year-old", "24 y.o." and "24F" state the same thing as "24 yo f".
    Dropping the separators, and splitting digits off a letter that follows
    them, lets one pattern read every conventional spelling instead of the
    grader owning one literal alternative per spelling and failing on the
    rest.
    """
    t = nlp.normalize(text)
    t = re.sub(r"[./\-]", " ", t)
    t = re.sub(r"(?<=\d)(?=[a-z])", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _sex_beside(text, m):
    """The sex word written beside this age, with the phrase that carries it."""
    for i, tok in enumerate(re.finditer(r"\S+", text[m.end():])):
        if i >= _SEX_WINDOW:
            break
        if tok.group(0) in _SEX_TERMS:
            return _SEX_TERMS[tok.group(0)], text[m.start():m.end() + tok.end()]
    for tok in reversed(list(re.finditer(r"\S+", text[:m.start()]))[-3:]):
        if tok.group(0) in _SEX_TERMS:
            return _SEX_TERMS[tok.group(0)], text[tok.start():m.end()]
    return "", m.group(0)


# Ages written in words, and the sex-first "F/24" shorthand. Both are ordinary
# in a hand-written note and neither was read at all, so a correct line scored
# zero for a formatting reason rather than a clinical one.
_SPELLED_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
_TENS = {k: v for k, v in _SPELLED_NUMBERS.items() if v >= 20 and v % 10 == 0}
_ONES = {k: v for k, v in _SPELLED_NUMBERS.items() if 1 <= v <= 9}
_SPELLED_AGE = re.compile(
    r"(?<![a-z])((?:" + "|".join(_TENS) + r")(?:[\s-](?:" + "|".join(_ONES) +
    r"))?|" + "|".join(sorted(_SPELLED_NUMBERS, key=len, reverse=True)) +
    r")[\s-]" + _AGE_UNIT + r"(?![a-z])")


def _spelled_age(phrase):
    parts = re.split(r"[\s-]+", phrase.strip().lower())
    total = 0
    for part in parts:
        if part in _SPELLED_NUMBERS:
            total += _SPELLED_NUMBERS[part]
    return total or None


def _demographic_candidates(text):
    """Every (position, age, sex, passage) the section documents."""
    t = _demographic_text(text)
    out = []
    for m in _SPELLED_AGE.finditer(t):
        age = _spelled_age(m.group(1))
        if age:
            sex, passage = _sex_beside(t, m)
            out.append((m.start(), age, sex, passage))
    # "F/24", "M 62" -- the sex first.
    for m in re.finditer(r"(?<![a-z0-9])(" +
                         "|".join(sorted(_SEX_TERMS, key=len, reverse=True)) +
                         r")\s*[/ ]\s*(\d{1,3})(?![a-z0-9])", t):
        out.append((m.start(), int(m.group(2)), _SEX_TERMS[m.group(1)],
                    m.group(0)))
    for m in _AGE_WITH_UNIT.finditer(t):
        sex, passage = _sex_beside(t, m)
        out.append((m.start(), int(m.group(1)), sex, passage))
    for m in _AGE_WITH_SEX.finditer(t):
        out.append((m.start(), int(m.group(1)), _SEX_TERMS[m.group(2)], m.group(0)))
    out.sort(key=lambda c: c[0])
    return [(age, sex, passage) for _, age, sex, passage in out]


def _row_age_sex(row, parsed, case):
    candidates = _demographic_candidates(parsed.s_text)
    want_age = case["patient"]["age"]
    want_sex = case["patient"]["sex"].lower()
    condition = ("No credit for inaccurate, unclear, or non-specific "
                 "documentation")
    if not candidates:
        return row.deny(
            "Age and sex are not documented in a recognisable form. The manual's "
            "own examples open the HPI '67 yo f ...'.",
            condition=condition)
    for age, sex, passage in candidates:
        if age == want_age and sex == want_sex:
            return row.award("Age and sex documented accurately.", passage=passage)
    # Nothing documented both correctly; explain the most complete attempt.
    age, sex, passage = next((c for c in candidates if c[1]), candidates[0])
    if not sex:
        return row.deny(
            "An age is documented but the patient's sex is not stated with it. "
            "The manual's own examples open the HPI '67 yo f ...'.",
            passage=passage, condition=condition)
    if age != want_age:
        return row.deny(
            "Age documented as %d; the patient is %d." % (age, want_age),
            passage=passage, condition=condition)
    return row.deny(
        "Sex documented as %s; the patient is %s." % (sex, want_sex),
        passage=passage, condition=condition)


def _row_cc(row, parsed, case, headers):
    block = parsed.s_header("cc")
    if not block or not block["body"].strip():
        return row.deny("No chief complaint header with content.",
                        condition="No credit if headers not used")
    body = block["body"]
    if len(nlp.normalize(body).split()) < 2:
        return row.deny("The chief complaint is too brief to be clear.",
                        passage=body,
                        condition="No credit for inaccurate, unclear, or non-specific documentation")
    has_duration = bool(re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|several|few)\s*"
        r"(day|days|week|weeks|month|months|year|years|hour|hours)\b",
        nlp.normalize(body)))
    # The manual's blank form labels this "Chief complaint and duration".
    if not has_duration:
        row.advisories.append(
            "The manual's blank form labels this field 'Chief complaint and "
            "duration'. A duration makes the complaint specific.")
    # Consistency with the HPI -- the manual's own sample note fails this.
    hpi = parsed.s_header("hpi")
    agreement = _same_problem(body, hpi["body"], case) if hpi else True
    if agreement is None:
        row.uncertain = "The wording could not be mapped confidently; lack of lexical overlap is not evidence that two complaints conflict."
        return row.deny("Chief complaint/HPI equivalence is unresolved by this parser. Check that both clearly describe the same presenting problem.", passage=body + " || " + hpi["body"][:120],condition="No credit for unclear or non-specific documentation")
    if agreement is False:
        row.uncertain = (
            "Whether two passages describe the same problem is read from shared "
            "wording and from the surface forms this case lists for each "
            "concept. A complaint written in vocabulary neither the HPI nor the "
            "case uses can be marked inconsistent when it is not.")
        return row.deny(
            "The chief complaint and the HPI describe different problems. A "
            "reader cannot tell what the patient came in for.",
            passage=body + "  ||  " + hpi["body"][:120],
            condition="No credit for inaccurate, unclear, or non-specific documentation")
    return row.award("Chief complaint stated clearly.", passage=body.strip()[:200])


# Words inside a concept's surface form that carry no meaning of their own, so
# "burning with urination" and "burning urination" are one phrase, not two.
_SURFACE_FILLER = {"with", "the", "of", "on", "in", "a", "an", "and", "to",
                   "she", "he", "her", "his", "when", "while", "is", "are",
                   "has", "had", "for"}


def _names_concept(text, surfaces):
    """Whether the text states one of these surface forms of a concept.

    Full-phrase matching is too literal for a chief complaint: "burning
    urination" is "burning with urination" written the way a student writes a
    CC line. A surface counts when every word that carries meaning in it is
    present.
    """
    words = {_stem(w) for w in nlp.expand_abbreviations(text).split()}
    for surface in surfaces or []:
        # Expand the surface too. The text side is already expanded, so a
        # surface the case author wrote in abbreviated form ("right cva
        # tenderness") could never match the note it was written for: "CVA" in
        # the note became "costovertebral angle" while the surface still said
        # "cva". 71 authored surfaces were unreachable by their own wording.
        parts = [_stem(w) for w in nlp.expand_abbreviations(nlp.normalize(surface)).split()
                 if w not in _SURFACE_FILLER]
        if parts and all(p in words for p in parts):
            return True
    return False


_COMPLAINT_SIGNALS = {
 'presyncope':r'\b(?:lightheaded\w*|presyncope|feeling faint|might faint)\b',
 'retention':r'\b(?:unable|cannot|cant) (?:to )?(?:urinat\w*|void|pee)|\b(?:urinary retention|last (?:normal )?(?:urinat\w*|void\w*)|last passed urine)\b',
 'dysuria':r'\b(?:dysuria|burning (?:with |on )?urination|painful urination)\b',
 'chest':r'\b(?:chest (?:pain|pressure|discomfort)|angina|substernal)\b',
 'headache':r'\b(?:headache|migraine|cephalgia)\b',
 'abdominal':r'\b(?:abdom\w*|stomach|epigastr\w*|suprapubic)\b',
 'dyspnea':r'\b(?:dyspnea|breathless\w*|shortness of breath|short of breath)\b',
 'flank':r'\bflank\b',
 'vertigo':r'\b(?:vertigo|spinning)\b',
 'focal_weakness':r'\b(?:arm|hand|leg|face|facial)\b.{0,45}\bweak(?:ness)?\b',
 'speech':r'\b(?:difficulty speaking|trouble (?:speaking|finding (?:the right )?words)|speech (?:change|difficulty)|aphasia)\b',
}

def _complaint_signals(text):
    t=nlp.normalize(text)
    return {k for k,p in _COMPLAINT_SIGNALS.items() if re.search(p,t)}

def _same_problem(cc_body, hpi_body, case):
    """Whether the chief complaint and the HPI name the same problem.

    Comparing raw words alone fails a correctly written note: a student who
    writes the complaint as "burning with urination" and the HPI as "dysuria"
    has documented one problem in two registers, and the old check read that
    as two problems because no CC word longer than four characters appeared in
    the HPI. The case's own concept lexicon is the evidence that two different
    surfaces mean the same thing.
    """
    cc_signals,hpi_signals=_complaint_signals(cc_body),_complaint_signals(hpi_body)
    # An HPI can continue the single named pain complaint without repeating
    # its location. This is note coherence only, not evidence for that pain.
    if len(cc_signals)==1 and cc_signals <= {'abdominal','chest','flank','headache'} and not hpi_signals and re.fullmatch('^(?:\\d{1,3} year old (?:female|woman|male|man) )?(?:with |reports |has )?(?:\\d+ (?:hours?|days?|weeks?|months?) (?:of )?)?(?:(?:constant|intermittent|persistent|worsening) )?pain$',_demographic_text(hpi_body.split('.')[0]).strip()):
        return True
    if cc_signals & hpi_signals:return True
    if cc_signals and hpi_signals:return False
    cc_words = {_stem(w) for w in nlp.expand_abbreviations(cc_body).split()
                if len(w) > 4}
    if not cc_words:
        return True
    hpi_words = {_stem(w) for w in nlp.expand_abbreviations(hpi_body).split()}
    if cc_words & hpi_words:
        return True
    for surfaces in (case.get("concept_lexicon") or {}).values():
        if not (_names_concept(cc_body, surfaces)
                and _names_concept(hpi_body, surfaces)):
            continue
        # The shared concept has to be what the complaint is about. "Chest
        # pain for two days" and an HPI about dysuria share the duration
        # "two days", and that says nothing about the problem -- so every
        # word of the complaint the HPI does not repeat must belong to the
        # concept the two passages have in common.
        surface_words = set()
        for surface in surfaces:
            surface_words |= {_stem(w) for w in nlp.normalize(surface).split()}
        if all(w in hpi_words or w in surface_words for w in cc_words):
            return True
    return False if cc_signals and hpi_signals else None


def _row_hpi_element(row, rid, parsed, case, supported, require_all):
    cats = ROW_CATEGORIES.get(rid, [])
    concepts = _row_concepts(case, cats)
    hits = [(cid, claim) for cid, claim in _documented(concepts, supported)
            if claim.get('header') != 'allergies']
    if not hits:
        return row.deny(
            "Nothing documented for this element, or what is documented is not "
            "supported by the encounter.",
            condition="No credit for inaccurate, unclear, or non-specific documentation")

    # For two-part rows, note which half is missing.
    if len(cats) > 1:
        covered = set()
        for cid, _ in hits:
            covered |= concepts[cid]["categories"]
        missing = [c for c in cats if c not in covered
                   and _facts_in_categories(case, [c])]
        if missing:
            msg = ("Only the %s half of this row is documented; %s is not."
                   % ("/".join(sorted(covered)), "/".join(missing)))
            if require_all:
                return row.deny(msg, passage=hits[0][1]["text"],
                                condition="No credit for inaccurate, unclear, or "
                                          "non-specific documentation")
            row.advisories.append(msg + " The rubric does not say whether both "
                                        "halves are required; this row was "
                                        "credited on one.")
    claim = hits[0][1]
    return row.award("Documented and supported by the encounter.",
                     passage=claim["text"], evidence=claim["evidence"])


def _row_headed(row, rid, parsed, case, supported, headers):
    need = {"pmh_psh": ["pmh", "psh"], "medications": ["meds"],
            "allergies": ["allergies"]}[rid]
    present = [h for h in need if h in headers]
    if not present:
        return row.deny("The %s header is missing." % "/".join(h.upper() for h in need),
                        condition="No credit if headers not used")
    concepts = _row_concepts(case, ROW_CATEGORIES[rid])
    hits = _documented(concepts, supported)
    if not hits:
        block = parsed.s_header(present[0])
        body = (block["body"] if block else "").strip()
        if body:
            return row.deny(
                "The header is present but its content is not supported by the "
                "encounter.", passage=body[:200],
                condition="No credit for inaccurate, unclear, or non-specific documentation")
        return row.deny("The header is present but empty.",
                        condition="No credit for inaccurate, unclear, or non-specific documentation")
    if rid == "pmh_psh" and len(present) < 2:
        row.advisories.append(
            "The row is 'PMH and PSH'. Only %s is headed; the manual's blank form "
            "shows both." % present[0].upper())
    claim = hits[0][1]
    return row.award("Documented and supported.", passage=claim["text"],
                     evidence=claim["evidence"])


def _row_social(row, parsed, case, supported, headers):
    if "sh" not in headers:
        return row.deny("No social history header.",
                        condition="No credit if headers not used")
    block = parsed.s_header("sh")
    body = block["body"] if block else ""
    required = {"tobacco": ["tobacco_use"], "alcohol": ["alcohol_use"],
                "drug": ["drug_use"]}
    missing = []
    passages = []
    for label, cids in required.items():
        got = [c for c in cids if c in supported]
        if not got:
            # It may be written in the note without ever being asked -- that is
            # a support failure, which the audit already flags.
            in_text = nlp.matches_any(body, lexicon.CORE_CONCEPTS.get(
                label + "_use", [label]))
            missing.append(label + (" (written but never obtained)" if in_text else ""))
        else:
            passages.append(supported[got[0]]["text"])
    if missing:
        return row.deny(
            "The rubric requires tobacco, alcohol and drug use every time. "
            "Missing or unsupported: " + ", ".join(missing) + ".",
            passage=body.strip()[:200],
            condition="Always include tobacco, alcohol, and drug use")
    return row.award("Tobacco, alcohol and drug use all documented and supported.",
                     passage=" / ".join(passages)[:220])


def _row_family(row, parsed, case, supported, headers):
    if "fh" not in headers:
        return row.deny("No family history header.",
                        condition="No credit if headers not used")
    block = parsed.s_header("fh")
    body = nlp.normalize(block["body"] if block else "")
    fh_concepts = _row_concepts(case, ["family"])
    hits = _documented(fh_concepts, supported)
    if not hits:
        return row.deny("Family history is not supported by the encounter.",
                        passage=(block["body"] if block else "")[:200],
                        condition="No credit for inaccurate, unclear, or non-specific documentation")
    has_parents = any(w in body for w in ["mother", "mom", "father", "dad", "parent"])
    has_siblings = any(w in body for w in ["brother", "sister", "sibling",
                                           "no siblings", "only child"])
    if not (has_parents and has_siblings):
        gap = []
        if not has_parents:
            gap.append("biological parents")
        if not has_siblings:
            gap.append("siblings")
        return row.deny(
            "The rubric requires biological parents and siblings. Missing: "
            + ", ".join(gap) + ".",
            passage=(block["body"] if block else "")[:200],
            condition="Biological parents and siblings")
    return row.award("Biological parents and siblings documented.",
                     passage=(block["body"] if block else "")[:220],
                     evidence=hits[0][1]["evidence"])


_ROS_LABEL_ALIASES = {
    "general": ["general", "constitutional", "const"],
    "skin": ["skin", "integumentary", "derm", "dermatologic"],
    "heent": ["heent", "head", "eyes", "ears", "nose", "throat", "eent"],
    "neck": ["neck"],
    "breasts": ["breast", "breasts"],
    "respiratory": ["respiratory", "resp", "pulmonary", "lungs", "pulm"],
    "cardiovascular": ["cardiovascular", "cardiac", "cv", "heart"],
    "gastrointestinal": ["gastrointestinal", "gi", "abdominal", "abd"],
    "urinary": ["urinary", "genitourinary", "gu", "renal"],
    "genital": ["genital", "reproductive", "gyn", "gynecologic", "sexual"],
    "musculoskeletal": ["musculoskeletal", "msk", "ms"],
    "neurologic": ["neurologic", "neurological", "neuro"],
    "hematologic": ["hematologic", "heme", "hematology", "lymphatic"],
    "endocrine": ["endocrine", "endo"],
    "psychiatric": ["psychiatric", "psych", "mood"],
}

# "Neuro - admits headache, photophobia; denies weakness"
_ROS_SEGMENT = re.compile(
    r"(?:^|[.;\n])\s*([A-Za-z][A-Za-z/ ]{1,26}?)\s*[-–:]\s", re.MULTILINE)


def _ros_label_to_system(label):
    key = nlp.normalize(label)
    for system, aliases in _ROS_LABEL_ALIASES.items():
        if key in aliases:
            return system
    for system, aliases in _ROS_LABEL_ALIASES.items():
        if any(key.startswith(a) for a in aliases):
            return system
    return None


def _ros_segments(body):
    """Split an ROS body into (system, text) using the student's own labels."""
    marks = list(_ROS_SEGMENT.finditer(body))
    out = []
    for i, m in enumerate(marks):
        system = _ros_label_to_system(m.group(1))
        if not system:
            continue
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        out.append((system, body[start:end]))
    return out


def _row_ros(row, parsed, case, supported, scoring):
    need_sys = scoring.get("ros_systems_required", 3)
    need_sym = scoring.get("ros_symptoms_per_system", 3)
    block = parsed.s_header("ros")
    if not block or not block["body"].strip():
        return row.deny("No ROS header with content.",
                        condition="No credit if headers not used")
    body = block["body"]
    concept_map = dict(lexicon.CORE_CONCEPTS)
    for cid in case.get("supersedes_core", []):
        concept_map.pop(cid, None)
    concept_map.update(case.get("concept_lexicon") or {})

    by_system = {}
    unsupported = []
    labeled = _ros_segments(body)

    if labeled:
        # The student named the systems. Count within their own labels -- that
        # is how a reader marks it, and it is the only way "General - ... denies
        # rash" can be judged as the student intended.
        row.uncertain = ("Symptoms are counted under the system headings you "
                         "wrote. 'Pertinent' is not defined by the rubric; this "
                         "case treats %s as pertinent."
                         % ", ".join(case.get("ros_pertinent_systems", [])))
        for system, segment in labeled:
            for claim in nlp.split_claims(segment):
                for cid in nlp.find_concepts(claim["text"], concept_map):
                    if cid in supported:
                        by_system.setdefault(system, set()).add(cid)
                    else:
                        unsupported.append(cid)
    else:
        # No system labels: fall back to classifying each symptom.
        row.uncertain = ("No system headings were found in your ROS, so symptoms "
                         "were classified by name. Labelling the systems makes "
                         "this unambiguous.")
        for claim in nlp.split_claims(body):
            for cid, hit in nlp.find_concepts(claim["text"], concept_map).items():
                if cid not in supported:
                    unsupported.append(cid)
                    continue
                surf = nlp.normalize(hit["surface"])
                for sysname, terms in lexicon.ROS_SYSTEMS.items():
                    if any(nlp.normalize(t) in surf or surf in nlp.normalize(t)
                           for t in terms):
                        by_system.setdefault(sysname, set()).add(cid)
                        break

    qualifying = {s: c for s, c in by_system.items() if len(c) >= need_sym}

    if len(qualifying) >= need_sys:
        return row.award(
            "%d systems documented with at least %d supported symptoms each: %s."
            % (len(qualifying), need_sym, ", ".join(sorted(qualifying))),
            passage=body.strip()[:260])

    detail = ", ".join("%s (%d)" % (s, len(c)) for s, c in sorted(by_system.items())) or "none"
    msg = ("The rubric requires %d symptoms from each of %d different pertinent "
           "systems (%d symptoms total). Systems reaching %d supported symptoms: "
           "%d. Counted: %s."
           % (need_sym, need_sys, need_sys * need_sym, need_sym, len(qualifying), detail))
    if unsupported:
        msg += (" Not counted because the encounter never established them: %s."
                % ", ".join(sorted(set(unsupported))[:6]))
    return row.deny(msg, passage=body.strip()[:260],
                    condition="3 symptoms from 3 different pertinent systems "
                              "(Total of 9 symptoms)")


def _apply_accuracy(row, problems, section):
    """A row cannot be credited on content that the audit rejected.

    Scoped to the row's own headers, so a bad sentence in the ROS cannot strip
    credit from the family history.
    """
    if not row.passage:
        return
    for p in problems.get(section, []):
        if row.headers and p.get("header") not in row.headers:
            continue
        if p["text"] and p["text"][:40] in row.passage:
            row.deny(
                "Credited content fails the accuracy condition: %s" % p["explanation"],
                passage=p["text"], evidence=p["evidence"],
                condition="No credit for inaccurate, unclear, or non-specific documentation")
            return


# ---------------------------------------------------------------------------
# Objective
# ---------------------------------------------------------------------------

REGION_HEADERS = {
    "Abdomen": ["abdomen", "gu"], "Heart": ["heart", "chest_wall"],
    "Lungs": ["lungs", "chest_wall"],
    "Neurologic": ["neuro", "neck"], "Musculoskeletal": ["msk"], "Skin": ["skin"],
    "HEENT": ["heent"], "General": ["general"],
}

_CORE_O_HEADERS = {"vitals", "orthostatic", "general", "osteopathic", "heart", "lungs", "labs",
                   "chest_wall"}


def _aoc_headers(case):
    aoc = case.get("area_of_concern", {})
    declared = aoc.get("headers")
    if declared:
        return list(declared)
    out = []
    for region in _relevant_regions(aoc):
        out += REGION_HEADERS.get(region, [])
    return out or ["abdomen"]


def _grade_objective(parsed, ledger, case, supported, problems, scoring):
    rows = []
    headers = parsed.o_headers_present()
    first = parsed.first_o_header()
    vitals_first = bool(first and first["canonical"] == "vitals")
    aoc_headers = _aoc_headers(case)
    other_headers = [h for h in headers
                     if h not in _CORE_O_HEADERS and h not in aoc_headers]

    for rid, label in OBJECTIVE_ROWS:
        row = Row(rid, label, "Objective", 5)
        if not headers:
            row.deny("No headers were used anywhere in the Objective section.",
                     condition="No credit if headers not used")
            rows.append(row)
            continue

        if rid == "most_relevant":
            row.headers = list(aoc_headers)
        elif rid == "other_systems":
            row.headers = list(other_headers)

        if rid == "vitals":
            _o_vitals(row, parsed, case, ledger, vitals_first, first, scoring)
        elif rid == "general":
            _o_simple(row, parsed, "general", "General",
                      "General appearance", supported)
        elif rid == "heart_lungs":
            _o_heart_lungs(row, parsed, supported)
        elif rid == "most_relevant":
            _o_most_relevant(row, parsed, case, ledger, supported)
        elif rid == "other_systems":
            _o_other(row, parsed, case)
        elif rid == "osteopathic":
            _o_osteopathic(row, parsed, case, ledger, supported)

        if row.earned:
            _o_conditions(row, parsed, problems)
        rows.append(row)
    return rows


def _vague(text):
    return nlp.match_regex_any(text, lexicon.VAGUE_OBJECTIVE_PATTERNS)


def _normal_misuse(text):
    """The word 'normal' used as a vague summary, not as clinical vocabulary."""
    t = nlp.normalize(text)
    if "normal" not in t:
        return ""
    for safe in lexicon.NORMAL_SAFE_TERMS:
        t = t.replace(nlp.normalize(safe), " ")
    if "normal" not in t:
        return ""
    m = re.search(r"[^.;]*\bnormal\b[^.;]*", t)
    return m.group(0).strip() if m else "normal"


def _o_conditions(row, parsed, problems):
    vague = _vague(row.passage)
    if vague:
        return row.deny(
            "The rubric rejects vague documentation here: \"%s\"." % vague,
            passage=row.passage,
            condition="No credit for inappropriate, unclear, or non-specific documentation")
    misuse = _normal_misuse(row.passage)
    if misuse:
        return row.deny(
            "The rubric gives no credit for \"Normal\". Describe the finding: "
            "\"%s\"." % misuse,
            passage=row.passage, condition='No credit for "Normal"')
    _apply_accuracy(row, problems, "O")


def _o_vitals(row, parsed, case, ledger, vitals_first, first, scoring):
    block = parsed.o_header("vitals")
    if not block or not block["body"].strip():
        return row.deny("Vital signs are not documented.",
                        condition="Vitals must be documented first")
    if not vitals_first:
        row.uncertain = ("'Vitals must be documented first' is read as: vitals are "
                         "the first content in Objective. Configurable.")
        return row.deny(
            "Vitals are documented, but not first -- '%s' comes before them."
            % (first["raw_header"] if first else "other content"),
            passage=block["body"].strip()[:200],
            condition="Vitals must be documented first")
    supplied = case["station"]["vitals"]
    body = block["body"]
    missing = [k for k, v in supplied.items()
               if not _vital_present(body, k, v)]
    if missing:
        return row.deny(
            "Vitals must be documented as given. Missing or altered: %s."
            % ", ".join(missing),
            passage=body.strip()[:220],
            condition="No credit for inaccurate, unclear, or non-specific documentation")
    return row.award("All supplied vital signs documented first, as given.",
                     passage=body.strip()[:220],
                     evidence=[{"kind": "station_info",
                                "text": "Station vitals: " +
                                        ", ".join("%s %s" % kv for kv in supplied.items()),
                                "time": "0:00"}])


_VITAL_ALIASES = {
    "T": ["t", "temp", "temperature"], "P": ["p", "pulse", "hr", "heart rate"],
    "BP": ["bp", "blood pressure"], "R": ["r", "rr", "resp", "respiratory rate"],
    "Pulse Ox": ["pulse ox", "spo2", "o2 sat", "oxygen saturation", "sat"],
    "Ht": ["ht", "height"], "Wt": ["wt", "weight"],
}


def _vital_present(body, key, value):
    nums = re.findall(r"\d+(?:\.\d+)?", value)
    body_n = nlp.normalize(body)
    if nums and all(n in body_n for n in nums[:2]):
        return True
    for alias in _VITAL_ALIASES.get(key, [key.lower()]):
        if alias in body_n and nums and nums[0] in body_n:
            return True
    return False


def _o_simple(row, parsed, header, label, human, supported):
    block = parsed.o_header(header)
    if not block or not block["body"].strip():
        return row.deny("%s is not documented under its own header." % human,
                        condition="No credit if headers not used")
    body = block["body"].strip()
    if len(nlp.normalize(body).split()) < 3:
        return row.deny("%s is documented but not specific." % human,
                        passage=body,
                        condition="No credit for inappropriate, unclear, or non-specific documentation")
    return row.award("%s documented specifically." % human, passage=body[:220])


def _o_heart_lungs(row, parsed, supported):
    heart = parsed.o_header("heart")
    lungs = parsed.o_header("lungs")
    missing = []
    if not heart or not heart["body"].strip():
        missing.append("Heart")
    if not lungs or not lungs["body"].strip():
        missing.append("Lungs")
    if missing:
        return row.deny("Missing under its own header: %s." % ", ".join(missing),
                        condition="No credit if headers not used")
    passage = "Heart: %s | Lungs: %s" % (heart["body"].strip(), lungs["body"].strip())
    disc = parsed.discouraged_headers()
    if disc:
        names = ", ".join("'%s' should be '%s'" % (d["used"], d["expected"]) for d in disc)
        return row.deny(
            "The course names these header words specifically: %s." % names,
            passage=passage[:220],
            condition="No credit for inappropriate, unclear, or non-specific documentation")
    return row.award("Heart and Lungs both documented under correct headers.",
                     passage=passage[:260])


def _o_most_relevant(row, parsed, case, ledger, supported):
    aoc = case.get("area_of_concern", {})
    aoc_headers = _aoc_headers(case)
    required = aoc.get("required_methods", [])
    performed = ledger.performed_maneuvers()
    from . import physexam as _pe

    methods_done = set()
    for mid in performed:
        man = _pe.CATALOG_BY_ID.get(mid)
        if man and man["region"] in _relevant_regions(aoc):
            methods_done.add(man["method"])

    # What did the note actually document for the area of concern?
    body = ""
    for header in aoc_headers:
        b = parsed.o_header(header)
        if b and b["body"].strip():
            body += " " + b["body"]
    body = body.strip()
    if not body:
        return row.deny(
            "The area of concern (%s) is not documented under its own header."
            % aoc.get("system", "area of concern"),
            condition="No credit if headers not used")

    missing_methods = [m for m in required if m not in methods_done]
    documented_methods = _methods_in_text(body)
    missing_doc = [m for m in required if m not in documented_methods
                   and m not in ("special",)]

    if missing_doc:
        return row.deny(
            "For this case the area of concern (%s) should be documented across "
            "%s. Not documented: %s."
            % (aoc.get("system", "area of concern"),
               ", ".join(required) or "the relevant methods",
               ", ".join(missing_doc)),
            passage=body[:240],
            condition="No credit for inappropriate, unclear, or non-specific documentation")
    if missing_methods:
        row.advisories.append(
            "Documented, but these methods were never actually performed in the "
            "encounter: %s." % ", ".join(missing_methods))
    special = aoc.get("special_tests", [])
    if special and not any(nlp.matches_any(body, [s]) for s in special):
        row.advisories.append(
            "The discriminating special test for this case (%s) is not in the "
            "note." % ", ".join(special))
    return row.award("Area of concern documented across the expected methods.",
                     passage=body[:260])


def _relevant_regions(aoc):
    text = nlp.normalize(aoc.get("system", ""))
    regions = []
    if any(w in text for w in ["abdomen", "gastro", "gi", "genitourinary", "renal"]):
        regions += ["Abdomen"]
    if any(w in text for w in ["cardio", "heart"]):
        regions += ["Heart"]
    if any(w in text for w in ["pulmon", "resp", "lung"]):
        regions += ["Lungs"]
    if any(w in text for w in ["neuro"]):
        regions += ["Neurologic"]
    if any(w in text for w in ["musculo", "msk", "back"]):
        regions += ["Musculoskeletal"]
    if any(w in text for w in ["skin", "derm"]):
        regions += ["Skin"]
    return regions or ["Abdomen"]


_METHOD_WORDS = {
    "inspect": ["inspect", "appears", "no rash", "no lesion", "contour", "scar",
                "distend", "symmetric", "visible"],
    "palpate": ["palpat", "tender", "soft", "guarding", "rebound", "mass",
                "organomegal", "hypertonic", "tissue texture"],
    "percuss": ["percuss", "tympan", "dullness", "resonan", "shifting"],
    "auscultate": ["auscultat", "bowel sound", "cta", "clear to auscultation",
                   "breath sound", "murmur", "bruit", "rales", "crackles"],
    "special": ["murphy", "mcburney", "cva tenderness", "rovsing", "psoas",
                "obturator", "straight leg", "romberg", "sign"],
}


def _methods_in_text(text):
    t = nlp.normalize(text)
    return {m for m, words in _METHOD_WORDS.items() if any(w in t for w in words)}


def _o_other(row, parsed, case):
    core = {"vitals", "orthostatic", "general", "osteopathic"}
    aoc_headers = set(_aoc_headers(case))
    others = [b for b in parsed.o_blocks
              if b["canonical"] and b["canonical"] not in core
              and b["canonical"] not in aoc_headers
              and b["body"].strip()]
    if not others:
        return row.deny(
            "No system outside vitals, general, the area of concern and the "
            "osteopathic exam is documented.",
            condition="No credit if headers not used")
    labels = ", ".join(b["raw_header"] for b in others)
    joined = " ".join(b["body"] for b in others)
    if len(nlp.normalize(joined).split()) < 4:
        return row.deny("Other systems are listed but not described specifically.",
                        passage=joined[:200],
                        condition="No credit for inappropriate, unclear, or non-specific documentation")
    return row.award("Other systems documented: %s." % labels, passage=joined[:240])


def _o_osteopathic(row, parsed, case, ledger, supported):
    block = parsed.o_header("osteopathic")
    if not block or not block["body"].strip():
        return row.deny(
            "No osteopathic examination documented. The course flags this as a "
            "common CSE omission.",
            condition="No credit if headers not used")
    body = block["body"].strip()
    level = re.search(r"\b([ctl]\s*\d{1,2})\b", nlp.normalize(body)) or \
        re.search(r"\b(sacrum|sacral|innominate|occiput|oa|rib \d+)\b", nlp.normalize(body))
    dysfunction = nlp.matches_any(body, [
        "tissue texture", "somatic dysfunction", "tender", "hypertonic", "spasm",
        "rotated", "sidebent", "side bent", "flexed", "extended", "restricted",
        "asymmetry", "tart", "rot", "sb", "nsrrl", "boggy", "ropy"])
    if not level:
        return row.deny(
            "No spinal level documented. The rubric requires level and "
            "dysfunction for credit.",
            passage=body[:200],
            condition="Must document level and dysfunction for credit")
    if not dysfunction:
        return row.deny(
            "A level is documented but no dysfunction. The rubric requires both.",
            passage=body[:200],
            condition="Must document level and dysfunction for credit")
    expected = case.get("osteopathic", {}).get("levels", "")
    if expected and not _level_overlaps(body, expected):
        row.advisories.append(
            "The viscerosomatic level for this case is %s (%s). The level you "
            "documented is outside that range."
            % (expected, case.get("osteopathic", {}).get("viscerosomatic_source", "")))
    return row.award("Level and dysfunction both documented.", passage=body[:220])


def _level_overlaps(body, expected):
    def nums(s):
        out = []
        for m in re.finditer(r"\b([ctl])\s*(\d{1,2})\b", nlp.normalize(s)):
            region = {"c": 0, "t": 100, "l": 200}[m.group(1)]
            out.append(region + int(m.group(2)))
        return out
    want = nums(expected)
    got = nums(body)
    if not want or not got:
        return True
    lo, hi = min(want), max(want)
    return any(lo - 2 <= g <= hi + 2 for g in got)


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------

def _longest_match(text, surfaces):
    """Length of the longest surface that matches, or 0."""
    best = 0
    for surface in surfaces:
        if surface and (nlp.matches_any(text, [surface]) or nlp.matches_any(re.sub(r"[-–—]", " ", text), [re.sub(r"[-–—]", " ", surface)])):
            best = max(best, len(nlp.normalize(surface)))
    return best


def _etiology_compatible(text, differential):
    """Old snapshots can carry broad aliases: do not inherit an unstated cause."""
    title=re.sub(r'[-–—]', ' ', nlp.normalize(differential.get('name','')))
    t=re.sub(r'[-–—]', ' ', nlp.normalize(text))
    required=[]
    if re.search(r'\bdiabet\w*\b',title):required.append(r'\bdiabet\w*\b')
    if re.search(r'\b(?:medication|drug) (?:induced|precipitated|related)|\biatrogenic\b',title):
        required.append(r'\b(?:medication|drug|iatrogenic|diphenhydramine|anticholinergic)\b')
    for pattern in required:
        matches=list(re.finditer(pattern,t))
        if not any(not nlp.is_negated(t,m.group(0)) and not re.search(r'\bnon\s*$',t[max(0,m.start()-5):m.start()]) for m in matches):return False
    return True

def _acute_infarction_surface(text,differential):
    if 'acute coronary syndrome' not in nlp.normalize(differential.get('name','')):return 0
    t=nlp.normalize(text)
    for m in re.finditer(r'\b(?:myocardial infarction|mi|nstemi|stemi)\b',t):
        if nlp.is_negated(t,m.group()) or re.search(r'\b(?:old|prior|previous|remote|history of)\b',t[max(0,m.start()-35):m.start()]):continue
        if re.match(r'\s+(?:excluded|ruled out)\b',t[m.end():]):continue
        return len(m.group())
    return 0


def _vindicate_of(text, case):
    """Which VINDICATE element(s) a differential belongs to.

    The most SPECIFIC differential wins, not the first one in the list. Several
    differentials on a case legitimately share a generic surface -- "angina" sits
    inside both stable and unstable angina -- and taking list order would read
    "Unstable angina / acute coronary syndrome" as the stable-angina row and deny
    a correct answer.
    """
    best, best_len = None, 0
    for d in differential_supplements.for_case(case):
        if not _etiology_compatible(text,d):continue
        n = max(_longest_match(text, [d["name"]] + d.get("aliases", [])), _acute_infarction_surface(text,d))
        if n > best_len:
            best, best_len = d, n
    if best is not None:
        return best["vindicate"], best
    hits = []
    for letter, spec in config.VINDICATE.items():
        if nlp.matches_any(text, spec["hints"]):
            hits.append(letter)
    return (hits[0] if hits else None), None


def _grade_assessment(parsed, case, scoring):
    rows = []
    entries = parsed.a_entries
    meta = {"letters": [], "matched": [], "mode": scoring.get(
        "vindicate_diversity_mode", "per_row_duplicate")}
    seen_letters = []

    for i in range(3):
        row = Row("assessment_%d" % (i + 1), "Differential Diagnosis %d" % (i + 1),
                  "Assessment", 5)
        row.uncertain = config.MNEMONIC_PROVENANCE["VINDICATE"]
        entry = entries[i] if i < len(entries) else None

        if entry is None or not entry["text"].strip():
            row.deny("No differential documented in position %d. The course "
                     "requires a minimum of three." % (i + 1),
                     condition="Must be numbered 1, 2, 3")
            rows.append(row)
            meta["letters"].append(None)
            meta["matched"].append(None)
            continue

        text = entry["text"]
        if scoring.get("require_assessment_numbering", True) and not entry["numbered"]:
            row.deny("Assessments must be numbered 1, 2, 3.", passage=text,
                     condition="Must be numbered 1, 2, 3")
            rows.append(row)
            meta["letters"].append(None)
            meta["matched"].append(None)
            continue
        if entry["numbered"] and entry["number"] != i + 1:
            row.advisories.append("Numbered %d in position %d."
                                  % (entry["number"], i + 1))

        letter, matched = _vindicate_of(text, case)
        meta["letters"].append(letter if matched is not None else None)
        meta["matched"].append(matched["name"] if matched else None)

        implausible = _implausible(text, case)
        if implausible:
            row.deny("This does not correlate with the case. %s" % implausible,
                     passage=text, condition="No credit if diagnosis does not "
                                             "correlate with case")
            rows.append(row)
            seen_letters.append(None)
            continue
        if matched is None:
            row.uncertain += " Automated mapping is unresolved; faculty review may be needed for a plausible alternative outside the authored list."
            row.deny(
                "The stated diagnosis or cause could not be mapped confidently to a reviewed case alternative and VINDICATE element. This is unresolved, not proof that the diagnosis is unrelated. Specify the suspected cause when known; a broad syndrome cannot inherit an unasserted etiology.",
                passage=text,
                condition="No credit if diagnosis does not correlate with case")
            rows.append(row)
            seen_letters.append(None)
            continue

        if i == 0 and matched.get("rank", 9) != 1:
            why = matched.get("not_most_likely_because")
            row.deny(
                "Differential #1 must be your most likely diagnosis. '%s' is a "
                "reasonable consideration for this presentation but is not the "
                "most likely one given what the encounter established.%s"
                % (matched["name"], (" " + why) if why else ""),
                passage=text,
                condition="Differential Diagnosis #1 should be your most likely differential")
            rows.append(row)
            seen_letters.append(letter)
            continue

        if letter in seen_letters and meta["mode"] == "per_row_duplicate":
            row.deny(
                "The rubric requires three different elements of VINDICATE. "
                "'%s' is %s, which an earlier differential already covers."
                % (matched["name"], config.VINDICATE[letter]["name"]),
                passage=text, condition="Require 3 different elements of VINDICATE")
            row.uncertain = (
                "The rubric attaches the VINDICATE requirement to the Assessment "
                "block without saying which row loses credit when it is unmet. "
                "This app removes credit from the duplicate. Configurable.")
            rows.append(row)
            seen_letters.append(letter)
            continue

        seen_letters.append(letter)
        row.award(
            "Relevant to the case, correctly positioned, and adds the %s element "
            "of VINDICATE." % config.VINDICATE[letter]["name"], passage=text)
        rows.append(row)

    meta["distinct_letters"] = len({l for l in seen_letters if l})
    return rows, meta


def _implausible(text, case):
    for bad in case.get("implausible_differentials", []):
        if nlp.matches_any(text, [bad["name"]]):
            return bad["why"]
    return ""


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


# Deliberately permitted clinical stems; short acronyms remain whole words.
_PLAN_HINT_STEMS = {'prescri','analgesi','anticoagul','hydrat','educat','advis',
                    'osteopathic manipul','emergency depart','return precaution',
                    'warning sign','red flag','rib raise','stretch','consult','refer'}
_PLAN_ACTIONS = {
 'M':r'\b(?:prescrib\w*|start|give|administer|continue|consider|offer|take|use|stop|avoid|withhold|review|adjust|titrate)\b',
 'O':r'\b(?:perform|provide|offer|consider|use|apply|treat)\b',
 'T':r'\b(?:obtain|order|check|test|measure|assess|evaluate|perform|repeat|consider|arrange|request|review|screen|monitor|urgent)\b',
 'H':r'\b(?:encourage|recommend|advise|support|provide|use|apply|continue|consider|discuss|review|start|offer|limit|increase|avoid|maintain|elevate|rest)\b',
 'E':r'\b(?:educat\w*|counsel\w*|advis\w*|discuss\w*|instruct\w*|teach\w*|explain\w*|inform\w*)\b',
 'R':r'\b(?:refer\w*|consult\w*|send|sent|transfer|admit\w*|arrange|involve|contact|call|discuss|obtain|seek|activate|follow[ -]?up)\b',
}

def _plan_hint_pattern(hint):
    h=nlp.normalize(hint).replace('-',' ')
    pattern=re.escape(h).replace(r'\ ',r'\s+')
    return r'(?<![a-z0-9])'+pattern+(r'[a-z]*\b' if h in _PLAN_HINT_STEMS else r'(?:s)?(?![a-z0-9])')

def _motherr_elements(text):
    """Distinct documented plan actions, not fragments inside unrelated words."""
    out={}
    for raw in claims_mod.investigation_clauses(text):
        t=nlp.normalize(raw).replace('-',' ')
        expanded=nlp.expand_abbreviations(raw).replace('-',' ')
        for letter,spec in config.MOTHERR.items():
            if letter in out: continue
            hints=list(spec['hints'])
            if letter=='M': hints += ['diphenhydramine','anticholinergic medicine','anticholinergic medication','antimicrobial','pain control','nicotine replacement','oral contraceptive','oral iron','iron supplementation','ferrous sulfate','vitamin c']
            if letter=='T': hints += ['echocardiogram','echocardiography','echocardiographic','glucose','prostate testing','urine testing','ferritin','reticulocyte','hemoglobin','positional assessment','dix hallpike','endoscopic assessment','lipase','amylase','bilirubin','creatinine','electrolytes','serum sodium','serum potassium','blood urea nitrogen','urine microscopy','urine protein','blood tests']
            if letter=='H': hints += ['tobacco cessation','stopping energy drinks','reducing alcohol','activity restriction','no heavy exertion','no stair climbing']
            if letter=='R': hints += ['emergency evaluation','emergency assessment','emergency team','gynecology','clinician evaluation','ems','stroke pathway','urology input','stroke team evaluation']
            if letter=='R2': hints += ['reassess','reassessment','reevaluation','review in']
            for hint in hints:
                match=re.search(_plan_hint_pattern(hint),t)
                if not match:
                    match=re.search(_plan_hint_pattern(hint),expanded)
                    subject=expanded
                else: subject=t
                if not match: continue
                # Negation is evaluated around this actual action/term, never
                # across the entire paragraph. A medication avoidance order is
                # itself a management action, unlike an absent prescription.
                action=list(re.finditer(_PLAN_ACTIONS.get(letter,r'(?!)'),subject))
                if letter=='E':
                    if not action and not re.search(r'\b(?:return precautions?|patient education|counseling)\b',subject):continue
                    if action and all(_is_negated(subject,a.start(),a.end()) for a in action):continue
                if letter=='T' and action and all(_is_negated(subject,a.start(),a.end()) for a in action):continue
                if letter=='T' and not action and re.match(r'^(?:no|neither)\b',t):continue
                if letter=='R':
                    if not action and not re.search(r'\b(?:urgent|immediate|emergency)\b.*\b(?:assessment|evaluation|consultation)\b',subject):continue
                if letter=='R2':
                    read=_read_follow_up(raw)
                    if not (read['action'] or read['disposition']):continue
                # 'US' can also be a pronoun; educational discussion with us is
                # not an ultrasound order. A plan action + location or the
                # explicitly capitalized acronym is required.
                if nlp.normalize(hint)=='us' and not (re.search(r'\bUS\b',raw) or (action and any(re.search(r'\b'+re.escape(loc)+r'\b',subject) for loc in _BODY_LOC))):continue
                negated=_is_negated(subject,match.start(),match.end())
                med_avoid=letter=='M' and re.search(r'\b(?:avoid|stop|withhold)\b',subject) and not re.search(r'\b(?:do not|dont|no plan to)\s+(?:avoid|stop|withhold)\b',subject)
                if negated and not med_avoid:continue
                if re.search(r'\b(?:defer\w*|contraindicated|not indicated|not needed|not required)\b',subject) and letter in ('O','T','R'):continue
                # A result reported in past tense is not a future test order.
                if letter=='T' and (claims_mod.action_status(raw)=='done' or re.search(r'\b(?:not|never|no)\s+(?:yet |been |was |were |is )*(?:performed|obtained|completed|done)\b',subject)):continue
                if letter=='T' and not claims_mod.proposed_test(raw):continue
                # Named tests, medication prescriptions and supportive orders
                # are often written as noun phrases in a plan. Their exact
                # bounded term is sufficient unless negated or result-only.
                if letter=='O' and nlp.normalize(hint)=='cranial' and not re.search(r'\b(?:omt|omm|manipulat\w*|osteopath\w*|technique)\b',subject):continue
                if letter=='T' and nlp.normalize(hint)=='stool' and not re.search(r'\b(?:test\w*|culture|guaiac|calprotectin|obtain|order|sample)\b',subject):continue
                out[letter]=hint.strip();break
    return out


def _grade_plan(parsed, case, ledger, audit_result, scoring):
    rows = []
    entries = parsed.p_entries
    a_entries = parsed.a_entries
    meta = {"elements": []}

    for i in range(3):
        row = Row("plan_%d" % (i + 1), "Plan %d" % (i + 1), "Plan", 5)
        row.uncertain = config.MNEMONIC_PROVENANCE["MOTHERR"]
        entry = entries[i] if i < len(entries) else None
        if entry is None or not entry["text"].strip():
            row.deny("No plan documented in position %d. The course requires a "
                     "minimum of three." % (i + 1),
                     condition="Must be numbered 1, 2, 3 and correlate with "
                               "respective assessment")
            rows.append(row)
            meta["elements"].append({})
            continue

        text = entry["text"]
        if scoring.get("require_plan_numbering", True) and not entry["numbered"]:
            row.deny("Plans must be numbered 1, 2, 3.", passage=text,
                     condition="Must be numbered 1, 2, 3 and correlate with "
                               "respective assessment")
            rows.append(row)
            meta["elements"].append({})
            continue

        elements = _motherr_elements(text)
        meta["elements"].append({k: v for k, v in elements.items()})

        # Contradicts obtained history? (e.g. prescribing a known allergen)
        trap = _allergy_conflict(text, case, ledger)
        if trap:
            row.deny(trap, passage=text,
                     condition="Be as specific as possible (ie, left ankle x-ray "
                               "vs x-ray)")
            rows.append(row)
            continue

        # Correspondence with the matching assessment. The rubric requires the
        # numbers to correlate, so a plan for a different problem cannot earn
        # the row on element count alone -- but the reading is inferred from
        # wording, so the row says so rather than asserting it.
        if i < len(a_entries) and a_entries[i]["text"].strip():
            ok, mismatch = _corresponds(text, a_entries[i]["text"], case)
            if not ok:
                row.advisories.append(
                    "This plan does not obviously address Assessment #%d ('%s'). "
                    "The rubric requires the numbers to correlate."
                    % (i + 1, a_entries[i]["text"][:60]))
                row.uncertain = (row.uncertain + " " if row.uncertain else "") + (
                    "Correspondence is judged from wording: this plan names %s, "
                    "which this case never mentions, and it never names its own "
                    "assessment. If %s is genuinely part of this patient's "
                    "problem, the reading is wrong." % (mismatch, mismatch))
                row.deny(
                    "Assessment #%d is '%s', but this plan works up and treats "
                    "%s, which the case never mentions. The rubric requires each "
                    "plan to correlate with its own assessment."
                    % (i + 1, a_entries[i]["text"][:60], mismatch),
                    passage=text,
                    condition="Must be numbered 1, 2, 3 and correlate with "
                              "respective assessment")
                rows.append(row)
                continue

        vague_imaging = _imaging_without_location(text)
        if vague_imaging:
            row.deny(
                "Imaging must state the body location: \"%s\". The rubric's own "
                "example is 'left ankle x-ray vs x-ray'." % vague_imaging,
                passage=text,
                condition="Be as specific as possible (ie, left ankle x-ray vs x-ray)")
            rows.append(row)
            continue

        if len(elements) < 3:
            names = ", ".join("%s (%s)" % (config.MOTHERR[k]["name"], v)
                              for k, v in elements.items()) or "none"
            row.deny(
                "The rubric requires at least three different elements per plan. "
                "Found %d: %s." % (len(elements), names),
                passage=text,
                condition="Must have at least three different elements (of MOTHERR) per plan")
            rows.append(row)
            continue

        row.award(
            "%d different elements documented: %s."
            % (len(elements),
               ", ".join(config.MOTHERR[k]["name"] for k in elements)),
            passage=text)
        rows.append(row)

    rows.append(_plan_education(parsed, case, audit_result))
    rows.append(_plan_follow_up(parsed))
    return rows, meta


# "ciprofloxacin (sulfa allergy - avoid TMP-SMX)" names the drug in order to
# rule it out. That is good documentation, not a prescribing error.
_AVOIDANCE_CUES = ["avoid", "not ", "no ", "cannot", "can't", "contraindicat",
                   "allergy", "allergic", "instead of", "rather than",
                   "withhold", "do not", "don't", "hold ", "except"]


def _allergy_conflict(text, case, ledger):
    trap = (case.get("plan_expectations") or {}).get("allergy_trap")
    if not trap:
        return ""
    released = ledger.released_concepts()
    if trap["concept"] not in released:
        return ""
    t = nlp.normalize(text)
    for term in trap["avoid"]:
        pos = nlp.find_term(term, t)
        if pos < 0:
            continue
        window = t[max(0, pos - 70):pos + 40]
        if any(c in window for c in _AVOIDANCE_CUES):
            continue
        return trap["message"]
    return ""


# Words a plan uses to give an order rather than to name a problem. They are
# the same in a plan for any complaint, so they say nothing about whether this
# plan belongs to this assessment.
_PLAN_ADMIN_WORDS = set("""
a an the and or of for to in on with without her his their she he him them they
patient start started begin take takes taking give given order orders check
checks obtain get send sent refer referral referred consult consultation
educate education educating counsel counseling advise instruct discuss explain
encourage encouraged plan plans follow up f/u return returns recheck schedule
daily twice once three four times day days week weeks month months hour hours
today tomorrow tonight next now am pm po iv im prn bid tid qid mg mcg gram
grams ml unit units tab tabs tablet capsule dose doses if as needed also then
per about at is are be was were this that these those it its from by not no do
does done use using new mild moderate severe possible suspected persistent
ongoing full course results result labs lab test tests imaging study studies
acute chronic likely probable versus differential
""".split())

# The problem a plan aims at: what it says it is treating, who it sends the
# patient to, and what region it images.
_INDICATION_RE = re.compile(
    r"\b(?:for|to\s+treat|to\s+cover|due\s+to|secondary\s+to)\s+"
    r"((?:her\s+|his\s+|the\s+|a\s+|an\s+|possible\s+|suspected\s+|"
    r"persistent\s+|ongoing\s+|acute\s+|chronic\s+)*"
    r"[a-z][a-z'-]{2,}(?:\s+[a-z][a-z'-]{2,})?)")
_REFERRAL_RE = re.compile(
    r"\b(?:refer(?:ral)?(?:\s+her|\s+him|\s+them|\s+the\s+patient)?\s+to|"
    r"consult)\s+(?:the\s+)?([a-z]+)|\b([a-z]+)\s+(?:referral|consult(?:ation)?)")

# Suffixes that only inflect a word. "Urination" and "urinating" are the same
# complaint, and a note must not be marked wrong for choosing one of them.
_INFLECTIONS = ("ation", "ating", "ates", "ated", "ing", "ies", "es", "ion", "s")

_CASE_VOCABULARY = {}


def _stem(word):
    word = word.strip(".,-/'")
    for suffix in _INFLECTIONS:
        if len(word) - len(suffix) >= 4 and word.endswith(suffix):
            return word[:-len(suffix)]
    return word


def _case_vocabulary(case):
    """Every word the case record itself uses, stemmed.

    This is the evidence a correspondence judgment rests on: a plan written
    entirely in words this case never uses is not a plan for this patient.
    """
    key = case.get("id")
    if key and key in _CASE_VOCABULARY:
        return _CASE_VOCABULARY[key]
    strings = []

    def walk(node):
        if isinstance(node, str):
            strings.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)

    walk(case)
    vocab = set()
    for s in strings:
        vocab |= {_stem(w) for w in nlp.normalize(s).split()}
    if key:
        _CASE_VOCABULARY[key] = vocab
    return vocab


def _plan_topic_words(text):
    """The words in a plan that name something clinical."""
    out = []
    for word in nlp.normalize(text).split():
        word = word.strip(".,-/'")
        if len(word) > 2 and not word.replace(".", "").isdigit() \
                and word not in _PLAN_ADMIN_WORDS:
            out.append(word)
    return out


def _plan_targets(text):
    """What the plan aims at: stated indications, referrals, imaged regions."""
    t = nlp.normalize(text)
    out = []
    for m in _INDICATION_RE.finditer(t):
        out += [w.strip(".,'-") for w in m.group(1).split()
                if len(w) > 2 and w not in _PLAN_ADMIN_WORDS]
    for m in _REFERRAL_RE.finditer(t):
        for group in m.groups():
            if group and len(group) > 2 and group not in _PLAN_ADMIN_WORDS:
                out.append(group)
    for word in _IMAGING:
        for m in re.finditer(r"\b" + re.escape(word) + r"\b", t):
            window = t[max(0, m.start() - 45):m.end() + 45]
            out += [loc for loc in _BODY_LOC
                    if re.search(r"\b" + re.escape(loc) + r"\b", window)]
    return out


def _names_assessment(plan_text, assessment_text, case):
    """Whether the plan writes the assessment's own name for the problem."""
    a_stems = {_stem(w) for w in nlp.normalize(assessment_text).split()
               if len(w) > 3 and w not in _PLAN_ADMIN_WORDS}
    p_stems = {_stem(w) for w in nlp.normalize(plan_text).split()}
    if a_stems & p_stems:
        return True
    for d in differential_supplements.for_case(case):
        surfaces = [d["name"]] + list(d.get("aliases") or [])
        if nlp.matches_any(assessment_text, surfaces) \
                and nlp.matches_any(plan_text, surfaces):
            return True
    return False


def _corresponds(plan_text, assessment_text, case):
    """Whether this plan addresses this assessment. Returns (verdict, reason).

    The old check accepted any plan containing any item the case expected
    anywhere, so an eczema work-up passed on the word "CBC". It is replaced by
    a judgment that needs positive evidence before it calls a plan a mismatch:
    the plan never names its own assessment, MOST of what it names appears
    nowhere in this case at all, AND what it aims at -- the condition it
    treats, the specialty it refers to, the region it images -- is foreign to
    the case too. Any one of those alone is ordinary variation in wording; all
    three together is a plan written for a different problem.
    """
    if _names_assessment(plan_text, assessment_text, case):
        return True, ""
    vocab = _case_vocabulary(case)
    a_stems = {_stem(w) for w in nlp.normalize(assessment_text).split()}
    topic = _plan_topic_words(plan_text)
    foreign = [w for w in topic if _stem(w) not in vocab]
    targets = _plan_targets(plan_text)
    foreign_targets = [t for t in targets
                       if _stem(t) not in vocab and _stem(t) not in a_stems]
    if foreign_targets and len(foreign) * 2 > len(topic):
        seen, named = set(), []
        for t in foreign_targets:
            if t not in seen:
                seen.add(t)
                named.append(t)
        return False, ", ".join(named)
    return True, ""


def _imaging_without_location(text):
    t = (text or "").lower()
    for word in _IMAGING:
        for m in re.finditer(r"\b" + re.escape(word) + r"\b", t):
            left = max(t.rfind(".", 0, m.start()), t.rfind(";", 0, m.start())) + 1
            right_candidates = [x for x in (t.find(".", m.end()), t.find(";", m.end())) if x >= 0]
            right = min(right_candidates) if right_candidates else len(t)
            window = t[max(left, m.start() - 45):min(right, m.end() + 45)]
            clause=t[left:right]
            if re.search(_PLAN_ACTIONS['E'],clause) and not re.search(r'\b(?:obtain|order|perform|request|arrange|repeat|schedule)\b',clause):
                continue  # Explaining an imaging study is not a new order.
            if not any(loc in window for loc in _BODY_LOC):
                # A reference back to a specified study is not another order.
                prior = t[:m.start()]
                referential = re.search(r"\b(?:every|that|this|the|a)\s+(?:negative|positive|normal|abnormal)\s*$", prior)
                previous_named = re.search(r"\b" + re.escape(word) + r"\b", prior)
                if referential and previous_named and any(loc in prior[max(0, previous_named.start()-45):previous_named.end()+45] for loc in _BODY_LOC):
                    continue
                return t[max(0, m.start() - 20):m.end() + 20].strip()
    return ""


def _plan_education(parsed, case, audit_result):
    row = Row("specific_education", "Specific Education", "Plan", 5)
    exp = (case.get("plan_expectations") or {}).get("education", [])
    for entry in parsed.p_entries:
        text = entry["text"]
        if not _motherr_elements(text).get("E"):
            continue
        specific = _education_is_specific(text)
        if specific:
            return row.award(
                "Specific education documented in Plan %s."
                % (entry["number"] or entry["index"] + 1), passage=text)
        row.advisories.append(
            "Education appears in Plan %s but is not specific. The rubric's own "
            "contrast is 'rest and elevate' versus 'take care of ankle'."
            % (entry["number"] or entry["index"] + 1))
    if row.advisories:
        return row.deny("Education is mentioned but not specific.",
                        passage=parsed.p_entries[0]["text"][:200] if parsed.p_entries else "",
                        condition="Must be specific (rest and elevate vs take care of ankle)")
    return row.deny("No patient education documented in any plan.",
                    condition="Must be documented in one of your plans")


def _education_is_specific(text):
    # A named topic or a five-word sentence is not the actual instruction.
    # Keep this separate from MOTHERR's broader 'education was mentioned' test.
    topics=r'\b(?:nsaids?|ibuprofen|exertion|driving|drive|fluids?|water|rehydration|antibiotic\w*|medication\w*|prescribed|fever|faint\w*|syncope|vertigo|weakness|deficits?|gait|pain|breath\w*|dyspnea|vomit\w*|hematemesis|stools?|bleeding|urine|urinary|wounds?|feet|foot|meals?|sleep|tobacco|smoking|alcohol|chest|diabetes|anemia|clot|stroke|biliary|thunderclap|inflammation|compression|nerve\w*|imaging|scan|radiation|glucose|symptom\w*|diagnos\w*)\b'
    action=r'\b(?:avoid\w*|stop\w*|limit\w*|reduc\w*|take|taking|complete|drink\w*|sip\w*|use|using|keep|keeping|check\w*|inspect\w*|rise|rising|stand\w*|rest\w*|elevat\w*|wear\w*|seek|call|report\w*)\b'
    for raw in re.split(r'[;.!?\n]',text):
        t=nlp.normalize(raw)
        for cue in re.finditer(r'\b(?:educat\w*|counsel\w*|advis\w*|instruct\w*|discuss\w*|explain\w*)\b',t):
            if re.search(r'\b(?:not|no|never|without)\b[^,;]{0,30}$',t[:cue.start()]):continue
            tail=t[cue.end():]
            if re.search(topics,tail) and (re.search(action,tail) or re.search(r'\b(?:why|because|cannot|differs|means|represents|requires|contribute|accumulation|inflammation|compression|uncertainty|possibilities|purpose)\b',tail)):
                return True
            if re.search(r'\b(?:smoking cessation|tobacco cessation|hand hygiene|daily foot checks|protective footwear|urine straining|slow standing|regular meals|headache diary|fall(?:/driving)? precautions)\b',tail):return True
        # Explicit safety advice remains specific when it follows an education
        # sentence, rather than needing the word 'educate' repeated each time.
        if re.search(r'\b(?:seek|call|return|report)\b.*\b(?:for|if|with)\b',t) and re.search(topics,t) and not re.search(r'\b(?:do not|never|no need to)\s+(?:seek|call|return|report)\b',t):return True
    return False


# The follow-up row asks two questions, and each of them has to be read in
# context.  Is a follow-up (or a disposition) actually being arranged -- a
# sentence that rules one out arranges nothing -- and does the note say WHEN?
# A digit somewhere in the plan is not an answer to the second question: the
# 500 of "acetaminophen 500 mg" belongs to the drug, not to a return visit.

# The action itself.  Each pattern names the thing being arranged, so the
# negation and interval checks below have something concrete to attach to.
_FOLLOWUP_ACTIONS = [
    r"follow(?:ing|ed|s)?[ /\-]?up", r"f\s*/\s*u",
    r"re-?check\w*", r"re-?evaluat\w*", r"re-?assess\w*",
    # "return precautions" tell the patient when to worry; they are education,
    # not a scheduled return, and the rubric asks for an interval.
    r"return(?!\s+precaution)\w*", r"comes?\s+back",
    r"see\s+(?:her|him|them|you|the\s+patient)\s+(?:back|again|in)",
    r"see\s+me\s+in", r"next\s+visit", r"revisit", r"office\s+visit",
    # The passive is as ordinary as the active -- "she should be seen again in
    # two days" arranges the same visit as "see her again in two days" -- and
    # "RTC" is how the return itself is usually abbreviated.
    r"seen\s+(?:again|back|in)\b", r"\brtc\b",
]

# A disposition is an order to send the patient somewhere.  The name of a
# destination on its own ("the emergency department") is not one -- that is
# what let "Do not transfer to the emergency department" score full marks.
_DISPOSITION_ACTIONS = [
    r"admit\w*", r"admission", r"hospitaliz\w*", r"discharg\w*", r"transfer\w*",
    # The pronoun is optional AND separated by a space: "send to the ED" and
    # "send her to the ED" are the same disposition, and only the first used to
    # count because the optional group swallowed the space.
    r"sen[dt]\s+(?:her|him|them|the\s+patient)?\s*to\b",
    # "She needs to go to the emergency department" is an order to send her
    # there, written from the patient's side.
    r"(?:go|goes|going)\s+to\s+(?:the\s+)?(?:ed\b|er\b|emergency)",
    r"refer\w*\s+(?:her|him|them|the\s+patient)?\s*to\s+(?:the\s+)?(?:ed|er|emergency)",
    r"(?:place|placed|put)\s+(?:her|him|them)?\s*(?:in|on|under)\s+observation",
    r"observation\s+unit",
    r"(?:urgent|immediate|emergent)\s+emergency\s+(?:department\s+)?(?:evaluat|assess)\w*",
    r"emergency\s+(?:department\s+)?(?:evaluat|assess)\w*",
]

_TIME_UNIT = (r"(?:minutes?|mins?|hours?|hrs?|days?|weeks?|wks?|months?|mos?|"
              r"years?|yrs?)")
_TIME_NUMBER = (r"(?:\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|"
                r"eleven|twelve|twenty|thirty|forty|couple|few|several)")
# A number bound to a unit of time.  The leading boundary is what keeps the
# "6" of "q6h" and the "500" of "500 mg" out of this.
_NUMERIC_TIME = re.compile(
    r"(?<![a-z0-9])" + _TIME_NUMBER +
    r"(?:\s*(?:-|to|or)\s*" + _TIME_NUMBER + r")?\s*" + _TIME_UNIT + r"(?![a-z])")
# Times said in words. "Tomorrow" is every bit as specific as "in 24 hours".
_NAMED_TIME = re.compile(
    r"\b(?:tomorrow|today|tonight|this\s+(?:morning|afternoon|evening|week)|"
    r"in\s+the\s+(?:morning|afternoon|evening|a\s*m|p\s*m)|first\s+thing|"
    r"day\s+after\s+tomorrow|end\s+of\s+the\s+week|"
    r"next\s+(?:day|week|month|year)|immediately|right\s+away|"
    r"(?:on\s+|next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|"
    r"sunday))\b")

# Words that make a following statement negative.  "Do not delay" and friends
# are the exception: there the negation lands on the delay, and the action it
# is urging still stands.
_NEGATION_CUES = {"no", "not", "never", "without", "cannot", "cant", "dont",
                  "doesnt", "didnt", "wont", "isnt", "avoid", "unnecessary",
                  "unneeded", "declined", "deferred"}
_NEGATION_PASSTHROUGH = {"delay", "delayed", "hesitate", "wait", "miss",
                         "stop", "skip", "discontinue", "forget", "ignore"}
# How far back a negation reaches. "She does not need to follow up" is four
# words; a cue further away than this belongs to something else.
_NEGATION_WINDOW = 6

# Verbs and dose forms that claim a time expression for themselves: in
# "follow up as needed; take acetaminophen 500 mg for 3 days" the three days
# are the course of the drug, not the interval to the next visit.
_OTHER_ACTION_VERBS = {"take", "takes", "taking", "start", "started", "give",
                       "given", "prescribe", "prescribed", "continue", "apply",
                       "use", "administer", "dose", "treat"}
_DOSE_UNITS = {"mg", "mcg", "g", "gram", "grams", "ml", "cc", "unit", "units",
               "tab", "tabs", "tablet", "tablets", "capsule", "capsules"}

# Sentence and clause ends, minus the abbreviations that carry a period
# without ending a sentence ("follow up with Dr. Chen in two weeks" is one
# clause).  This is applied to the raw text because normalization drops the
# semicolon that separates one statement from the next.
_CLAUSE_SPLIT = re.compile(
    r"[;\n]+|(?<!\bdr)(?<!\bmr)(?<!\bmrs)(?<!\bms)(?<!\bpt)\.(?:\s+|$)")


def _clauses(text):
    """The plan split where one statement ends and the next begins.

    Binding matters: "Follow up as needed; take acetaminophen 500 mg" states
    no interval, and the only way to know that is to notice that the number
    lives in a different statement than the follow-up.

    Each clause comes back with the offsets where a comma stood, because a
    negation binds only inside the comma-separated item it was written in.
    Normalization deletes commas, and without them "Ceftriaxone 1 g IM, no
    NSAIDs, follow up in 2 days" read as a negated follow-up and threw away a
    correctly documented return visit.
    """
    out = []
    for part in _CLAUSE_SPLIT.split((text or "").lower()):
        if not part:
            continue
        clause, breaks = "", []
        for item in part.split(","):
            item = nlp.normalize(item)
            if not item:
                continue
            if clause:
                clause += " "
                breaks.append(len(clause))
            clause += item
        if clause:
            out.append((clause, tuple(breaks)))
    return out


def _action_spans(clause, patterns):
    """Where each of these actions is written in the clause, in order."""
    spans = []
    for pat in patterns:
        for m in re.finditer(pat, clause):
            spans.append((m.start(), m.end(), m.group(0)))
    spans.sort()
    return spans


# "Admission is not required" rules the admission out just as plainly as "no
# admission" does, and the cue sits after the action rather than before it.
_RULED_OUT = re.compile(
    r"^(?:[^a-z0-9]*(?:\w+\s+){0,3}?(?:is|are|was|were|will\s+be|would\s+be)?\s*"
    r"(?:not|no\s+longer)\s+(?:currently\s+)?"
    r"(?:required|needed|necessary|indicated|warranted|appropriate)\b|"
    r"\s*(?:(?:is|are|was|were|will\s+be|would\s+be)\s+)?(?:unnecessary|unneeded|deferred)\b)")


def _is_negated(clause, start, end=None, breaks=()):
    """Whether the action at this position is being ruled out.

    `breaks` are the comma positions from `_clauses`, and the reading stays
    inside the item the action was written in.  A note that rules something
    else out in an earlier item -- "no NSAIDs, follow up in 2 days" -- has
    still arranged the follow-up.
    """
    seg_start = max([0] + [b for b in breaks if b <= start])
    seg_end = min([len(clause)] + [b for b in breaks if b > start])
    if end is not None and _RULED_OUT.search(clause[end:min(seg_end, end + 60)]):
        return True
    before = [t.group(0) for t in
              re.finditer(r"[a-z0-9'/-]+", clause[seg_start:start])]
    for back in range(min(_NEGATION_WINDOW, len(before))):
        idx = len(before) - 1 - back
        if before[idx].strip("'") not in _NEGATION_CUES:
            continue
        after_cue = before[idx + 1:]
        # Adjectival negation binds its noun: "unnecessary NSAIDs and
        # follow-up" does not make the separate follow-up unnecessary.
        # Determiner/verb negation ("no CT and MRI") still scopes both.
        if before[idx] in {"unnecessary", "unneeded"} and len(after_cue) >= 2 and after_cue[-1] == "and":
            continue
        if after_cue and after_cue[0] in _NEGATION_PASSTHROUGH:
            # "do not delay transfer" urges the transfer rather than ruling
            # it out; the negation lands on the delay.
            continue
        return True
    return False


def _bound_interval(clause, action_end):
    """A time expression this action owns, or ''.

    The expression must follow the action with nothing in between that would
    claim it -- another action verb, or a drug dose.
    """
    for pattern in (_NUMERIC_TIME, _NAMED_TIME):
        for m in pattern.finditer(clause):
            if m.start() < action_end:
                continue
            between = [t.group(0) for t in
                       re.finditer(r"[a-z0-9'/-]+", clause[action_end:m.start()])]
            if any(w in _OTHER_ACTION_VERBS or w in _DOSE_UNITS for w in between):
                continue
            return m.group(0).strip()
    return ""


def _read_follow_up(text):
    """What a plan actually arranges: the action, whether it is negated, when.

    Returned as evidence rather than a verdict, so the row can explain which
    of the three questions the note answered.
    """
    out = {"interval": "", "disposition": "", "action": "", "negated": ""}
    for clause, breaks in _clauses(text):
        for start, end, phrase in _action_spans(clause, _FOLLOWUP_ACTIONS):
            if _is_negated(clause, start, end, breaks):
                out["negated"] = out["negated"] or phrase
                continue
            out["action"] = out["action"] or phrase
            interval = _bound_interval(clause, end)
            if interval and not out["interval"]:
                out["interval"] = interval
        for start, end, phrase in _action_spans(clause, _DISPOSITION_ACTIONS):
            if _is_negated(clause, start, end, breaks):
                out["negated"] = out["negated"] or phrase
                continue
            out["disposition"] = out["disposition"] or phrase
    return out


def _plan_follow_up(parsed):
    row = Row("specific_follow_up", "Specific Follow-Up", "Plan", 5)
    if not parsed.p_entries:
        return row.deny("No plans documented.",
                        condition="Must be documented in Plan #1 only")
    p1 = parsed.p_entries[0]["text"]
    read = _read_follow_up(p1)
    if read["interval"]:
        return row.award(
            "Specific follow-up interval documented in Plan 1: \"%s ... %s\"."
            % (read["action"], read["interval"]), passage=p1)
    if read["disposition"]:
        return row.award(
            "Disposition documented in Plan 1 (\"%s\"), which the rubric accepts "
            "in place of an interval." % read["disposition"], passage=p1)
    if read["action"]:
        return row.deny(
            "Follow-up is mentioned in Plan 1 (\"%s\") but no interval is bound "
            "to it. The rubric's example is 'follow up in 1 month'."
            % read["action"],
            passage=p1, condition="Must be documented in Plan #1 only "
                                  "(follow up in 1 month)")
    if read["negated"]:
        row.uncertain = (
            "Negation is read from the words around the action inside its own "
            "clause. A sentence that arranges a follow-up in some more indirect "
            "way, while carrying a negation next to it, can be read this way "
            "wrongly.")
        return row.deny(
            "Plan 1 rules this out rather than arranging it (\"%s\" is negated), "
            "so no follow-up interval and no disposition are documented."
            % read["negated"],
            passage=p1, condition="Must be documented in Plan #1 only")
    later = []
    for entry in parsed.p_entries[1:]:
        elsewhere = _read_follow_up(entry["text"])
        if elsewhere["action"] or elsewhere["disposition"]:
            later.append(entry)
    if later:
        return row.deny(
            "Follow-up appears in Plan %s. The rubric requires it in Plan #1."
            % (later[0]["number"] or later[0]["index"] + 1),
            passage=later[0]["text"],
            condition="Must be documented in Plan #1 only")
    return row.deny("No follow-up or disposition documented in Plan 1.",
                    passage=p1, condition="Must be documented in Plan #1 only")


# ---------------------------------------------------------------------------
# Spelling / style
# ---------------------------------------------------------------------------

def _grade_spelling(parsed):
    row = Row("spelling_style", "Spelling/Style", "Overall", 2)
    text = parsed.full_text()
    issues = nlp.spelling_issues(text)
    unapproved = nlp.unapproved_abbreviations(text)
    if unapproved:
        row.advisories.append(
            "Abbreviations not on the manual's approved list: %s. Reported as an "
            "advisory rather than a deduction, because the manual's own examples "
            "use forms outside its table."
            % ", ".join(u["abbrev"] for u in unapproved[:8]))
    if issues:
        return row.deny(
            "Spelling and style issues: %s."
            % "; ".join("'%s' -> %s" % (i["found"], i["suggest"]) for i in issues[:6]),
            passage="")
    return row.award("No spelling or style issues detected.")
