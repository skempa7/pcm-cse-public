"""Attributes of a documented claim, and the evidence to check them against.

The audit used to ask "is this claim about a topic the encounter touched?" That
is why every one of these passed as supported:

    patient never smoked          ->  "Smokes 6 packs daily."
    pain is 7/10                  ->  "Right flank pain 1/10."
    ibuprofen 400 mg as needed    ->  "Ibuprofen 4000 mg daily."
    P 104, R 18, BP 112/70        ->  "P 18, R 104, BP 70/112"
    dipstick LE+ and nitrite+     ->  "leukocyte esterase and nitrites negative"

Each one is on the right topic and wrong in the attribute that matters. So a
claim is decomposed into the attributes a reader would check -- what is being
measured, its value, its unit, its polarity, whose it is, and whether it is
being reported as done or proposed -- and each attribute is compared with the
frozen encounter evidence.

Nothing here reads the hidden case directly. It reads the evidence ledger, which
contains only what the encounter actually produced.
"""

from __future__ import annotations

import re

from . import nlp

# --------------------------------------------------------------------------
# Vital signs, matched by label
# --------------------------------------------------------------------------

# Canonical vital labels and the surfaces students write for them.
VITAL_LABELS = {
    "T": ["t", "temp", "temperature", "tmax"],
    "P": ["p", "hr", "pulse", "heart rate"],
    "BP": ["bp", "blood pressure"],
    "R": ["r", "rr", "resp", "respirations", "respiratory rate"],
    "Pulse Ox": ["pulse ox", "spo2", "sao2", "o2 sat", "oxygen saturation",
                 "sat", "pox"],
    "Ht": ["ht", "height"],
    "Wt": ["wt", "weight"],
}

_LABEL_LOOKUP = {}
for _canon, _surfaces in VITAL_LABELS.items():
    for _s in _surfaces:
        _LABEL_LOOKUP[_s] = _canon

# "BP 112/70", "P 104 bpm", "T 101.6 F", "Pulse Ox 99% on room air"
_VITAL_RE = re.compile(
    r"(?<![a-z0-9])(" + "|".join(
        sorted((re.escape(s) for s in _LABEL_LOOKUP), key=len, reverse=True))
    + r")\s*[:=]?\s*(\d{1,3}(?:\.\d+)?(?:\s*/\s*\d{1,3}(?:\.\d+)?)?)"
    r"\s*((?:breaths?\s*)?(?:/\s*|per\s+)(?:minutes?|mins?)|%|bpm|rpm|mmhg|f|c|kg|lbs?|pounds?|in|cm)?",
    re.I)

_NUM = r"\d+(?:\.\d+)?"


def _norm_value(v):
    return re.sub(r"\s+", "", (v or "")).lower()


def vital_matches(text):
    """Exclude explicit spinal notation, never an implausible temperature."""
    spinal = list(re.finditer(r"\bt\s*(?:1[0-2]|[1-9])\s*(?:-|to|through)\s*t\s*(?:1[0-2]|[1-9])\b(?!\s*(?:degrees?\s*)?[fc]\b)", text, re.I))
    spinal += list(re.finditer(r"\bt\s*(?:1[0-2]|[1-9])\s+(?:sidebent|rotated|flexed|extended|paraspinal|vertebra|segment|somatic|tissue texture)\b", text, re.I))
    return [m for m in _VITAL_RE.finditer(text)
            if not any(r.start() <= m.start() < r.end() for r in spinal)]


def vitals_in(text: str) -> dict:
    """Labelled vital signs written in a note: {canonical label: value}."""
    out = {}
    t = " " + nlp.normalize(text) + " "
    for m in vital_matches(t):
        label = _LABEL_LOOKUP.get(m.group(1).strip().lower())
        if not label:
            continue
        out.setdefault(label, _norm_value(m.group(2)))
    return out


def supplied_vitals(case: dict) -> dict:
    """The station's vitals, reduced to label -> numeric value."""
    out = {}
    for label, raw in (case.get("station", {}).get("vitals") or {}).items():
        m = re.search(_NUM + r"(?:\s*/\s*" + _NUM + r")?", str(raw))
        if m:
            out[label] = _norm_value(m.group(0))
    return out


def vital_mismatches(text: str, case: dict) -> list:
    """Vitals written with the wrong value for their own label.

    Set membership is not enough: "P 18, R 104, BP 70/112" reuses every number
    the chart supplies and is wrong about all three.
    """
    supplied = supplied_vitals(case)
    out = []
    for label, value in vitals_in(text).items():
        if label not in supplied:
            continue
        if value != supplied[label]:
            out.append({"label": label, "claimed": value,
                        "supplied": supplied[label]})
    return out


# --------------------------------------------------------------------------
# Quantities: doses, pack-years, amounts
# --------------------------------------------------------------------------

_UNITS = ["mg", "mcg", "g", "gram", "grams", "ml", "l", "units", "unit",
          "tabs", "tab", "tablets", "tablet", "packs", "pack", "ppd",
          "puffs", "puff", "drinks", "drink", "beers", "beer", "cups", "cup",
          "mg/kg", "meq", "iu"]

_QUANT_RE = re.compile(
    r"(?<![a-z0-9])(" + _NUM + r")\s*(" +
    "|".join(sorted((re.escape(u) for u in _UNITS), key=len, reverse=True)) +
    r")(?![a-z])", re.I)


def quantities(text: str) -> list:
    """Every number-with-unit in a claim, with the word it follows/precedes."""
    t = nlp.normalize(text)
    out = []
    for m in _QUANT_RE.finditer(t):
        before = t[max(0, m.start() - 40):m.start()].strip()
        after = t[m.end():m.end() + 30].strip()
        head = before.split()[-1] if before.split() else ""
        out.append({"value": m.group(1), "unit": m.group(2).lower(),
                    "head": head, "before": before, "after": after,
                    "raw": m.group(0)})
    return out


_RATING_RE = re.compile(r"(?<![0-9/])(\d{1,2})\s*(?:/|out of)\s*10(?![0-9])")


def ratings(text: str) -> list:
    """Severity ratings written as N/10."""
    return [m.group(1) for m in _RATING_RE.finditer(nlp.normalize(text))]


# --------------------------------------------------------------------------
# Action status: reported as done, or proposed
# --------------------------------------------------------------------------

_DONE_MARKERS = [
    "completed", "was completed", "performed", "was performed", "obtained",
    "was obtained", "resulted", "showed", "showed a", "revealed", "demonstrated",
    "came back", "returned", "confirmed by", "confirmed on", "was done",
    "done today", "we did", "i did", "results show", "result showed",
    "reported as", "read as", "noted on", "grew", "grows", "isolated",
    "yielded", "cultured", "no growth", "significant for", "notable for",
    "came back with", "results are", "result is", "was normal", "were normal",
    "unremarkable on",
]
_PROPOSE_MARKERS = [
    "obtain", "order", "will order", "check", "send", "consider", "plan to",
    "recommend", "would obtain", "will obtain", "to be obtained", "arrange",
    "schedule", "refer for", "start", "begin", "initiate", "prescribe",
    "we will", "i will", "follow up with", "repeat in",
]
# Investigations whose result a note can wrongly assert.
_INVESTIGATIONS = [
    "urine culture", "blood culture", "culture", "ct", "ct scan", "cat scan",
    "ultrasound", "x-ray", "xray", "radiograph", "mri", "echocardiogram", "echocardiography",
    "echo", "ekg", "ecg", "electrocardiogram", "cbc", "bmp", "cmp",
    "troponin", "lipase", "amylase", "biopsy", "endoscopy", "colonoscopy", "urinalysis",
    "urine dipstick", "dipstick", "lipid panel", "hemoglobin a1c", "a1c",
    "chest x-ray", "kub", "renal ultrasound", "stress test", "d-dimer",
    "lumbar puncture", "spinal tap", "h pylori", "stool antigen",
    # The abbreviations a note is actually written in. Without these,
    # "urine cx grew E. coli" asserted a culture result that no check could see.
    "urine cx", "blood cx", "wound cx", "cxr", "kub", "u/a", "lp", "cta",
    "abg", "bnp", "hgb", "hct", "lfts", "tsh", "esr", "crp", "pt/inr", "inr",
    "ua micro", "urine micro", "ct head", "ct abd", "ct abdomen", "ct chest",
    "renal us", "pelvic us", "abdominal us", "doppler", "eeg", "emg",
]

_RESULT_ASSERTION = re.compile(
    r"\b(?:confirmed(?: by| on| with)?|confirms|showed|shows|revealed|reveals|"
    r"demonstrated|demonstrates|positive for|negative for|came back|resulted|"
    r"(?:was|were|is|are) (?:not )?(?:positive|negative|normal|abnormal)|read as|reported as|grew|grows|isolated|"
    r"yielded|no growth|significant for|notable for|consistent with|compatible with|suggested|suggests|indicated|indicates|showing|identified|detected|found|seen on|visualized|"
    r"excludes?|excluded|rules? (?:out|in)|ruled (?:out|in)|no evidence of|(?:was|were|is|are) without|absent|"
    r"there (?:was|were|is|are) (?:no|a|an)|(?:no|multiple) [a-z ]{1,60} (?:on|by) (?:the )?(?:ultrasound|ct|mri|xray|x-ray)|"
    r"(?:ultrasound|ct|mri|xray|x-ray) (?:is|was|looks|appears) clear)\b")


def _result_clauses(text):
    """Retain an explicit named-test result label before normalization.

    'Ultrasound: no stones' reports a negative result despite having no verb.
    A colon in an order or conditional sentence is not a completed result.
    """
    for clause in re.split(r'[;!?\n]|(?<!\d)\.(?!\d)', text or ''):
        if ':' in clause:
            label, value = clause.split(':', 1)
            if investigations_mentioned(label) and not re.search(
                    r'\b(?:if|unless|whether|until|will|would|could|may|might|should|can|obtain|order|check|consider|request|arrange|recommend|plan)\b', label, re.I) \
                    and re.match(r'\s*(?:no|without|positive|negative|normal|abnormal|unremarkable|absent)\b', value, re.I):
                clause = label + ' results show ' + value
        yield clause


def _reported_predicates(text, pattern):
    """Actual-result predicates, excluding scoped future/conditional language.

    A later proposal cannot erase an earlier result assertion. Conversely,
    'if the ultrasound confirms' and 'will be confirmed' assert no result.
    Sentence/semicolon boundaries keep those scopes local.
    """
    for clause in _result_clauses(text):
        t = nlp.normalize(clause)
        for match in pattern.finditer(t):
            prefix = t[:match.start()]
            # Future predicates and conditional test outcomes are not evidence
            # claims. A completed past result before a later plan still counts.
            if re.search(r'\b(?:if|unless|whether|until)\b', prefix):
                continue
            if match.group(0) == 'indicated' and re.search(r'\b(?:as|when)\s+$', prefix):
                continue
            if match.group(0).startswith('confirmed') and re.search(r'\b(?:treat|manage|correct)\s+(?:a|any)\s+$', prefix):
                continue
            if re.search(r'\b(?:will|would|could|may|might|should|must|can|cannot|to be|to)\s+(?:not |have been |be |have |already |then )*$', prefix):
                continue
            if re.search(r"\b(?:not|never|hasnt|hasn't|wasnt|wasn't|isnt|isn't)\s+(?:yet |been |be |already )*$", prefix):
                # A negative interpretation still asserts a result ('did not
                # exclude a stone'). Negated performance asserts no test.
                if pattern is not _RESULT_ASSERTION:
                    continue
            if re.search(r'\b(?:performed|obtained|completed|done)\b', match.group(0)) and re.match(r'^no\b', prefix):
                continue
            yield match.group(0)


def investigations_mentioned(text: str) -> list:
    t = nlp.normalize(text)
    found = []
    for inv in _INVESTIGATIONS:
        if nlp.word_in(inv, t):
            found.append(inv)
    # Keep the most specific surface only: "urine culture" beats "culture".
    out = []
    for inv in sorted(found, key=len, reverse=True):
        if not any(inv != other and inv in other for other in out):
            out.append(inv)
    return out


def action_status(text: str) -> str:
    """'done', 'proposed' or 'unclear', with completed claims taking priority."""
    if asserts_a_result(text):
        return "done"
    done = re.compile(r"\b(?:" + "|".join(re.escape(x) for x in _DONE_MARKERS) + r")\b")
    if any(_reported_predicates(text, done)):
        return "done"
    t = nlp.normalize(text)
    if any(re.search(r"\b" + re.escape(m) + r"\b", t) for m in _PROPOSE_MARKERS):
        return "proposed"
    return "unclear"


def asserts_a_result(text: str) -> bool:
    return any(_reported_predicates(text, _RESULT_ASSERTION))


def proposed_test(text: str) -> bool:
    """Require an order or a bounded test noun phrase, not any mention in Plan.

    A result predicate can never become an order merely because this reader
    does not recognize its wording. Bare 'CBC; RUQ ultrasound' is legitimate
    shorthand, while 'ultrasound has yet to be performed' proposes nothing.
    Call on one investigation clause, not on an entire numbered plan.
    """
    t = nlp.normalize(text)
    if action_status(text) == 'done':
        return False
    if re.search(r'\b(?:has|have|is|was|are|were)\s+yet\s+to\b', t):
        return False
    if re.search(r'\b(?:not|never|no)\s+(?:yet |been |was |were |is )*(?:performed|obtained|completed|done)\b', t):
        return False
    actions = r'\b(?:obtain|order|check|test|measure|assess|evaluate|perform|repeat|consider|arrange|request|review|screen|monitor|schedule|use)\b'
    for m in re.finditer(actions, t):
        before = t[max(0, m.start()-45):m.start()]
        if not re.search(r'\b(?:no|not|never|dont|don.t|without|avoid|decline|declined)\b[^,;.!?]{0,30}$', before):
            return True
    if re.search(r'\b(?:will|would|should|to)\s+be\s+(?:obtained|ordered|performed|scheduled)\b', t):
        return not re.search(r'\b(?:not|no|never)\b', t)
    if ',' in text and not re.match(r'^(?:no|not|never|avoid|decline)\b',t):
        return any(proposed_test(part.strip()) for part in text.split(','))
    t=re.split(r'\s+(?:if|when)\s+',t)[0]
    nouns = _INVESTIGATIONS + ['imaging','microscopy','troponins','glucose','blood tests','urine testing','urine microscopy','urine protein','ferritin','reticulocyte','hemoglobin','bilirubin','creatinine','electrolytes','serum sodium','serum potassium','blood urea nitrogen','positional assessment','dix hallpike','endoscopic assessment','prostate testing']
    remainder = t
    matched = False
    for noun in sorted(nouns, key=len, reverse=True):
        remainder, count = re.subn(r'(?<![a-z0-9])'+re.escape(noun)+r'(?![a-z0-9])', ' ', remainder)
        matched = matched or bool(count)
    # Only location, modality and scheduling qualifiers survive a bare order.
    allowed = set('the a an and or of with without contrast right left upper lower quadrant ruq luq rlq llq abdominal pelvic head brain spine chest renal bladder bedside serum urine blood noncontrast urgent emergent emergency immediately today tomorrow now repeat fasting labs tests imaging bilateral lumbar cervical thoracic sensitivities sensitivity'.split())
    words = re.findall(r'[a-z0-9]+', remainder)
    return matched and all(w in allowed for w in words)


def investigation_clauses(text: str) -> list:
    """Separate a new named test/order from a preceding result clause."""
    inv = '|'.join(re.escape(x) for x in sorted(_INVESTIGATIONS, key=len, reverse=True))
    starters = r'(?:obtain|order|check|request|arrange|repeat|consider)\b|(?:(?:the|right|left|upper|lower|quadrant|abdominal|pelvic|head|chest)\s+){0,5}(?:' + inv + r')\b'
    out=[]
    for sentence in re.split(r'[;!?\n]|(?<!\d)\.(?!\d)|,(?=\s*(?:obtain|order|check|request|arrange|repeat|consider)\b)', text or '', flags=re.I):
        if re.search(r'\b(?:if|unless|whether|until)\b',sentence,re.I):
            out.append(sentence)
        else:
            start=0
            for boundary in re.finditer(r'\b(?:and|but)\s+(?='+starters+r')',sentence,re.I):
                before=sentence[start:boundary.start()];after=sentence[boundary.end():]
                explicit_order=re.match(r'(?:obtain|order|check|request|arrange|repeat|consider)\b',after,re.I)
                # Keep coordinated noun lists under their original negation.
                # A distinct order or actual result starts its own scope.
                if boundary.group(0).lower().startswith('but') or explicit_order or action_status(before)=='done' or action_status(after)=='done':
                    out.append(before);start=boundary.end()
            out.append(sentence[start:])
    return out


def asserted_investigations(text: str) -> list:
    """Investigations actually reported done; proposals elsewhere do not count."""
    out = []
    for clause in investigation_clauses(text):
        if action_status(clause) != "done":
            continue
        for inv in investigations_mentioned(clause):
            if inv not in out:
                out.append(inv)
    return out


# --------------------------------------------------------------------------
# What the encounter actually produced, as attributes
# --------------------------------------------------------------------------

def evidence_index(ledger, case) -> dict:
    """Attributes obtainable from the frozen encounter record.

    Built from the ledger's own released concepts, which already carry the
    polarity, the value and the quote that released them -- so the audit checks
    a claim against what the encounter produced, never against the hidden case.

    ``values``         concept id -> released value string
    ``polarity``       concept id -> 'positive' | 'negative'
    ``quotes``         concept id -> the sentence that released it
    ``investigations`` investigations the encounter produced a result for
    """
    values, polarity, quotes = {}, {}, {}
    for cid, rec in (ledger.released_concepts() or {}).items():
        values[cid] = str(rec.get("value") or "")
        polarity[cid] = rec.get("polarity") or "positive"
        quotes[cid] = rec.get("quote") or ""

    texts = []
    for kind in ("patient", "exam_finding", "station_info"):
        for ev in ledger.by_kind(kind):
            texts.append((ev.get("text") or "").lower())

    investigations = set()
    for ev in ledger.by_kind("station_info"):
        if (ev.get("meta") or {}).get("supplied_id"):
            for inv in investigations_mentioned(ev.get("text") or ""):
                investigations.add(inv)

    return {
        "values": values,
        "polarity": polarity,
        "quotes": quotes,
        "texts": texts,
        "investigations": investigations,
        "blob": " || ".join(texts),
    }


def analyte_polarity(blob: str, analyte: str):
    """Was an analyte reported positive or negative?

    Delegates to the shared term-level reader, which scopes the negation to the
    analyte's own clause. A hand-rolled window did not reach the cue in "the
    urine dipstick was negative for both leukocyte esterase and nitrites",
    where one cue governs two analytes several words away.
    """
    return nlp.term_polarity(blob, analyte)


ANALYTES = ["leukocyte esterase", "leukocytes", "nitrite", "nitrites", "blood",
            "protein", "glucose", "ketones", "bilirubin", "urobilinogen",
            "specific gravity", "white blood cells", "red blood cells",
            "bacteria", "occult blood"]


def analyte_mismatches(text: str, evidence: dict) -> list:
    """Analytes documented with the opposite result to the one supplied."""
    out = []
    for analyte in ANALYTES:
        claimed = analyte_polarity(text, analyte)
        if claimed is None:
            continue
        actual = analyte_polarity(evidence["blob"], analyte)
        if actual is None:
            continue
        if claimed != actual:
            out.append({"analyte": analyte, "claimed": claimed,
                        "actual": actual})
    return out


def numeric_mismatch(claim_value: str, evidence_value: str) -> bool:
    """Do two values disagree on the number they carry?"""
    a = re.findall(_NUM, claim_value or "")
    b = re.findall(_NUM, evidence_value or "")
    if not a or not b:
        return False
    return a[0] not in b
