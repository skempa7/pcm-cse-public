"""Text handling shared by the patient engine, the exam resolver and the grader.

Deliberately deterministic: the same note always produces the same score, and
every match is explainable by pointing at the surface form that fired.
"""

from __future__ import annotations

import functools
import re
import unicodedata

from . import lexicon

# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

_PUNCT = re.compile(r"[^\w\s/+\-.']")
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lower-case, strip accents and collapse whitespace, keeping / and - ."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("–", "-").replace("—", "-")
    text = _PUNCT.sub(" ", text)
    return _WS.sub(" ", text).strip()


# Abbreviations that are also ordinary English words. Expanding these turns
# "anything else at all?" into a question about allergies, so they are left
# alone; the literal form still matches wherever it genuinely appears.
AMBIGUOUS_ABBREVIATIONS = {"all", "us", "pt", "no", "is", "as", "at", "it", "or",
                           "on", "in", "to", "be", "so", "we", "he"}


@functools.lru_cache(maxsize=4096)
def expand_abbreviations(text: str) -> str:
    """Expand approved abbreviations so 'SOB' and 'shortness of breath' match."""
    out = []
    for token in normalize(text).split():
        key = token.strip(".")
        expansion = lexicon.ALL_APPROVED.get(key)
        # Single letters, and abbreviations that double as English words, are
        # far too ambiguous to expand blindly.
        if expansion and len(key) > 1 and key not in AMBIGUOUS_ABBREVIATIONS:
            out.append(expansion)
        else:
            out.append(token)
    return " ".join(out)


@functools.lru_cache(maxsize=8192)
def _term_re(term: str):
    suffix = r"(?:s|es)?" if len(term) <= 4 else r"[a-z]{0,4}"
    return re.compile(r"(?<![a-z0-9])" + re.escape(term) + suffix + r"(?![a-z0-9])")


@functools.lru_cache(maxsize=8192)
def _norm_cached(text: str) -> str:
    return normalize(text)


@functools.lru_cache(maxsize=8192)
def _prefix_re(term: str):
    return re.compile(r"(?<![a-z0-9])" + re.escape(term))


def word_start_in(term: str, text: str) -> bool:
    """Substring match anchored to a word start.

    Trigger lists are written as word prefixes -- "smok" is meant to reach
    "smoking", "medic" to reach "medications" -- so a plain substring test is
    the natural reading of them. Unanchored, though, it also matches INSIDE a
    word: the trigger "where" fires on "any-where-", so "does it move
    anywhere?" reaches the location fact and the patient answers where the
    pain is instead of whether it radiates. Anchoring the left edge keeps
    every intended prefix match and removes the infix and suffix ones.
    """
    term = _norm_cached(term)
    if not term:
        return False
    return _prefix_re(term).search(text) is not None


def word_in(term: str, text: str) -> bool:
    """Match a term at a word start, allowing inflections but not infixes.

    Plain substring matching is unusable on clinical text: "ua" hides inside
    "guarding", "dre" inside "addressed", "tart" inside "start". Short terms
    take only a plural so "ear" does not reach "earlier"; longer stems may take
    a short suffix so "urinat" reaches "urinating".
    """
    term = _norm_cached(term)
    if not term:
        return False
    return _term_re(term).search(text) is not None


def find_term(term: str, text: str):
    """Position of a word-bounded match, or -1."""
    term = _norm_cached(term)
    if not term:
        return -1
    m = _term_re(term).search(text)
    return m.start() if m else -1


def searchable(text: str) -> str:
    """Both the literal and the expanded form, so either surface matches."""
    return normalize(text) + " || " + expand_abbreviations(text)


# --------------------------------------------------------------------------
# Negation
# --------------------------------------------------------------------------

# NegEx-style pseudo-negations: phrases that start with a negation word but do
# not negate what follows.  "No relief from sumatriptan" says the drug did not
# work, not that she is not taking it.
PSEUDO_NEGATIONS = [
    "no relief", "no improvement", "no change", "no better", "no benefit",
    "no response", "no effect", "not relieved", "not improved", "no help",
    "not helped", "no significant change", "no increase", "no decrease",
    "not only", "no further", "no longer",
]

NEGATION_CUES = [
    "denies", "denied", "deny", "no ", "not ", "without", "negative for",
    "absent", "never", "none", "free of", "rules out", "ruled out",
    "unremarkable for", "non", "lacks", "nothing", "don't", "doesn't", "didn't", "cannot", "can't",
]

# Cues that end a negation's scope: "no fever but has cough" -- cough is not
# negated.  "with" and "has" are deliberately absent: they are far too common
# in ordinary clinical prose to mark a contrast.
_TERMINATORS = re.compile(
    r"\b(but|however|although|though|except|admits?|reports?|positive for|"
    r"endorses?|complains? of|does have|yes|presents?|presenting|states?|"
    r"c/o|describes?|notes?)\b"
)

# Standard NegEx practice: a negation reaches a few words, not the rest of the
# sentence.  Without this, "no chronic medical conditions presents to clinic
# c/o burning with urination" reads the burning as denied.
# A real ROS line denies several things after one cue -- "denies vaginal
# discharge, cough, chest pain, rash, headache" -- so the window has to
# span a list. The terminators above stop it running into a new clause.
NEGATION_WINDOW_TOKENS = 12

# Words that make a phrase a negative assertion even without a preceding cue:
# "Murphy sign negative", "abdomen non-distended", "McBurney point non-tender".
# NB: "clear" and "intact" are deliberately absent. They describe a normal
# finding, not a negated one -- "CTA bilaterally" is a positive assertion about
# what was heard.
_POSTPOSITIVE_NEGATIVES = [
    "negative", "non-tender", "nontender", "non-distended", "nondistended",
    "non-focal", "nonfocal", "absent", "unremarkable", "denies", "without",
    "never", "none",
]
_POSTPOSITIVE_TOKENS = {"no", "not", "non"}


def negation_scope(text: str) -> list:
    """Return (start, end) spans of normalized text that fall under negation."""
    norm = normalize(text)
    spans = []
    for cue in NEGATION_CUES:
        start = 0
        while True:
            idx = norm.find(cue, start)
            if idx < 0:
                break
            # 'no ' must be a whole word
            if cue.strip() in ("no", "not", "non") and idx > 0 and norm[idx - 1].isalnum():
                start = idx + 1
                continue
            scope_start = idx + len(cue)
            if any(norm.startswith(pn, idx) for pn in PSEUDO_NEGATIONS):
                start = idx + len(cue)
                continue
            # A morphological prefix negates its own adjective, not later symptoms.
            if cue == "non" and scope_start < len(norm) and (norm[scope_start].isalpha() or norm[scope_start] == "-"):
                word = re.match(r"-?[a-z]+", norm[scope_start:])
                spans.append((scope_start, scope_start + (word.end() if word else 0)))
                start = scope_start
                continue
            tail = norm[scope_start:]
            term = _TERMINATORS.search(tail)
            stop = scope_start + (term.start() if term else len(tail))
            # Cap the reach at a few words.
            words = 0
            capped = scope_start
            for m in re.finditer(r"\S+", norm[scope_start:stop]):
                words += 1
                capped = scope_start + m.end()
                if words >= NEGATION_WINDOW_TOKENS:
                    break
            spans.append((scope_start, max(capped, scope_start)))
            start = idx + len(cue)
    return spans


def polarity_mode(surfaces) -> str:
    """How a concept's polarity should be compared.

    A concept whose every surface form is a negative assertion ("no chronic
    medical conditions", "Murphy sign negative") is inherently negative, and
    both the encounter and the note must be read that way.  A concept whose
    surfaces mix the two -- "clear to auscultation" alongside "no rales" -- is
    the *same* finding said two ways, so polarity carries no information and is
    not compared at all.
    """
    surfaces = [s for s in (surfaces or []) if str(s).strip()]
    if not surfaces:
        return "unchecked"
    negs = [surface_is_negative(s) for s in surfaces]
    if all(negs):
        return "strict_negative"
    if not any(negs):
        return "strict_positive"
    return "unchecked"


# Words that negate by their own morphology: no cue word precedes them, but
# they assert the absence of the thing they name. "Sclerae anicteric" and
# "denies jaundice" are the same claim.
_MORPHOLOGICAL_NEGATIVES = [
    "anicteric", "afebrile", "atraumatic", "acyanotic", "aphasic",
    "asymptomatic", "nontender", "non-tender", "nondistended",
    "non-distended", "nonlabored", "non-labored", "nontoxic", "non-toxic",
    "nonfocal", "non-focal", "unlabored", "unremarkable", "euvolemic",
    "normocephalic", "nonicteric", "non-icteric", "nonsmoker", "non-smoker",
    "nondrinker", "non-drinker", "nonpalpable", "non-palpable",
]


def surface_is_negative(surface: str) -> bool:
    """True when the phrase itself asserts a negative, with no cue in front."""
    s = normalize(surface)
    if any(word_in(n, s) for n in _MORPHOLOGICAL_NEGATIVES):
        return True
    if any(n in s for n in _POSTPOSITIVE_NEGATIVES):
        return True
    return bool(_POSTPOSITIVE_TOKENS & set(s.split()))


_LEADING_CUES = ["no ", "not ", "never ", "denies ", "denied ", "denying ",
                 "without ", "negative for ", "absent ", "free of ", "neg ",
                 "no evidence of ", "ruled out "]


def strip_negation_cue(surface: str) -> str:
    """The thing a surface is about, with any leading negation cue removed.

    "no murmur" -> "murmur";  "denies tobacco" -> "tobacco".
    """
    s = normalize(surface)
    changed = True
    while changed:
        changed = False
        for cue in _LEADING_CUES:
            if s.startswith(cue):
                s = s[len(cue):].strip()
                changed = True
    return s


def term_polarity(text: str, term: str):
    """How `text` asserts `term`: 'negative', 'positive', or None if absent.

    Used to compare a note and the encounter record on the SAME term, which is
    the only sound comparison for a concept whose surfaces mix polarities --
    "no murmur" is how a normal heart is described, so the concept's own
    polarity says nothing about how any one sentence used it.
    """
    norm = normalize(text)
    core = strip_negation_cue(term)
    if not core or not word_in(core, norm):
        return None
    # Judge the term inside its own clause. An earlier clause's negation is not
    # this term's: "no acute distress, overweight" records that the patient IS
    # overweight, and "RRR with S4, no murmur" does not deny the S4.
    # Split the RAW text: normalize() removes the punctuation the clause
    # boundary is made of.
    segment = norm
    for piece in re.split(r"[,;]", text or ""):
        piece = normalize(piece)
        if word_in(core, piece):
            segment = piece
            break
    if is_negated(segment, core):
        return "negative"
    norm = segment
    m = _term_re(_norm_cached(core)).search(norm)
    if m is None:
        return None
    pos, end = m.start(), m.end()
    # Only the words IMMEDIATELY before the term. A wider window reads an
    # unrelated negation as this term's: "RRR with S4, no murmur" does not
    # negate the S4, and "no acute distress, overweight" does not negate
    # "overweight".
    window = norm[max(0, pos - 16):pos]
    if any(window.rstrip().endswith(c.strip()) for c in _LEADING_CUES):
        return "negative"
    # Postpositive form: laboratory results are written "glucose negative",
    # "leukocyte esterase negative", with the polarity AFTER the analyte.
    # From the END OF THE MATCH, so an inflection does not shift the window:
    # "nitrites negative" matches the stem "nitrite" and the polarity word is
    # one letter further on than len(core) suggests.
    after = norm[end:end + 16].strip()
    first = (after.split()[0] if after.split() else "").strip(".,;:()")
    if first in ("negative", "neg", "absent", "none", "nil", "nonreactive",
                 "non-reactive", "normal"):
        return "negative"
    if surface_is_negative(core):
        return "negative"
    return "positive"


def is_negated(text: str, surface: str) -> bool:
    """True when `surface` occurs inside a negation scope in `text`."""
    norm = normalize(text)
    surf = normalize(surface)
    if not surf:
        return False
    spans = negation_scope(text)
    if not spans:
        return False
    pos = find_term(surf, norm)
    if pos < 0:
        return False
    for lo, hi in spans:
        if lo <= pos < hi:
            return True
    return False


# --------------------------------------------------------------------------
# Concept detection
# --------------------------------------------------------------------------

def dehyphenate(text: str) -> str:
    """"non-tender" and "nontender" are the same finding."""
    return re.sub(r"(?<=[a-z])-(?=[a-z])", "", text)


_STOP = {"the", "a", "an", "of", "to", "in", "on", "and", "or", "is", "was",
         "with", "for", "at", "her", "his", "their", "she", "he", "patient",
         "about", "from", "that", "this", "any", "has", "have", "had", "been"}


def _all_tokens_present(surface: str, text: str) -> int:
    """Position of the first token when every significant token is present.

    Surface lists cannot enumerate every word order and every interposed word
    ("McBurney point non-tender" vs "mcburney nontender"), so a multi-word
    surface also matches when all of its content words appear.
    """
    tokens = [t for t in surface.split() if len(t) > 2 and t not in _STOP]
    if len(tokens) < 2:
        return -1
    first = -1
    for t in tokens:
        pos = find_term(t, text)
        if pos < 0:
            return -1
        if first < 0 or pos < first:
            first = pos
    return first


def find_concepts(text: str, concept_map: dict) -> dict:
    """Map concept id -> {'surface', 'negated', 'pos'} for concepts present."""
    hay = normalize(text)
    expanded = expand_abbreviations(text)
    hay_dh = dehyphenate(hay)
    found = {}
    for concept, surfaces in concept_map.items():
        for surface in surfaces:
            s = normalize(surface)
            if not s:
                continue
            pos = find_term(s, hay)
            src = hay
            if pos < 0:
                pos = find_term(s, expanded)
                src = expanded
            if pos < 0:
                pos = find_term(dehyphenate(s), hay_dh)
                src = hay_dh
            if pos < 0:
                pos = _all_tokens_present(dehyphenate(s), hay_dh)
                src = hay_dh
            if pos < 0:
                continue
            found[concept] = {
                "surface": surface,
                # A phrase can be negative because something negates it, or
                # because the phrase itself is the negative finding.
                "negated": is_negated(src, s) or surface_is_negative(surface),
                "pos": pos,
            }
            break
    return found


def matches_any(text: str, surfaces) -> bool:
    hay = normalize(text)
    exp = expand_abbreviations(text)
    for s in surfaces:
        s = normalize(s)
        if s and (word_in(s, hay) or word_in(s, exp)):
            return True
    return False


def match_regex_any(text: str, patterns) -> str:
    hay = normalize(text)
    for pat in patterns:
        m = re.search(pat, hay)
        if m:
            return m.group(0)
    return ""


# --------------------------------------------------------------------------
# Trigger matching for patient question intents
# --------------------------------------------------------------------------

# Contractions break literal triggers. "What you'd like me to call you" never
# matched the authored "what would you like me to call you", so the coach kept
# asking for a preferred name the student had already asked for. Expanded only
# where triggers are MATCHED; the negation cues elsewhere still see the
# original contracted forms.
_CONTRACTIONS = [
    (re.compile(r"\b(what|who|where|when|why|how|that|there|here|it|he|she)'s\b", re.I), r"\1 is"),
    (re.compile(r"\b(i|you|we|they|he|she|it|that|who)'d\b", re.I), r"\1 would"),
    (re.compile(r"\b(i|you|we|they|he|she|it|who)'ll\b", re.I), r"\1 will"),
    (re.compile(r"\b(i|you|we|they)'ve\b", re.I), r"\1 have"),
    (re.compile(r"\b(you|we|they)'re\b", re.I), r"\1 are"),
    (re.compile(r"\bi'm\b", re.I), "i am"),
    (re.compile(r"\blet's\b", re.I), "let us"),
    (re.compile(r"\bcan't\b", re.I), "cannot"),
    (re.compile(r"\bwon't\b", re.I), "will not"),
    (re.compile(r"\b(\w+)n't\b", re.I), r"\1 not"),
]


def expand_contractions(text: str) -> str:
    """Write contractions out, for literal trigger comparison only."""
    out = text or ""
    for pattern, replacement in _CONTRACTIONS:
        out = pattern.sub(replacement, out)
    return out


def trigger_score(utterance: str, trigger: dict) -> float:
    """Score how well an utterance matches a fact's trigger spec.

    trigger = {"any": [...], "all": [...], "not": [...], "weight": 1.0}
    Returns 0.0 when the trigger does not fire.
    """
    if not trigger:
        return 0.0
    hay = normalize(expand_contractions(utterance))
    exp = expand_abbreviations(expand_contractions(utterance))

    def present(phrase: str) -> bool:
        p = normalize(phrase)
        if not p:
            return False
        # Word-start substring first (how trigger lists are written: "smok"
        # reaches "smoker"), then the inflection-aware match. The substring is
        # anchored so a trigger cannot fire from inside a longer word.
        return (word_start_in(p, hay) or word_start_in(p, exp)
                or word_in(p, hay) or word_in(p, exp))

    for phrase in trigger.get("not", []):
        if present(phrase):
            return 0.0

    all_terms = trigger.get("all", [])
    if all_terms and not all(present(p) for p in all_terms):
        return 0.0

    any_terms = trigger.get("any", [])
    hits = [p for p in any_terms if present(p)]
    if any_terms and not hits:
        return 0.0

    # Longer matched phrases are stronger evidence of intent.
    specificity = max((len(normalize(p)) for p in hits), default=0)
    base = 1.0 + specificity / 40.0
    if all_terms:
        base += 0.5
    return base * float(trigger.get("weight", 1.0))


# --------------------------------------------------------------------------
# Sentence / claim splitting for the note audit
# --------------------------------------------------------------------------

_CLAUSE_SPLIT = re.compile(r"(?<=[.;])\s+|\n+")


_LEADING_NEG = ["denies any", "denies", "no known", "no", "not", "without",
                "negative for", "never"]


def leading_negation(text: str) -> str:
    """The negation cue a clause opens with, if any."""
    t = normalize(text)
    for cue in _LEADING_NEG:
        if t.startswith(cue + " "):
            return cue + " "
    # "General - denies fever, chills" : the cue can follow a system label.
    m = re.match(r"^[a-z/ ]{2,26}?[-:]\s*(denies|no|without|negative for)\s",
                 t)
    if m:
        return m.group(1) + " "
    return ""


def split_claims(text: str) -> list:
    """Split a note section into claim-sized units, preserving offsets.

    Each claim carries `eval_text`, which is what the audit reads.  When a long
    comma-separated list is split, the clause's leading negation cue is carried
    onto every piece -- otherwise "denies fever, chills, rash" becomes three
    positive assertions the moment it is split.
    """
    claims = []
    pos = 0
    for chunk in _CLAUSE_SPLIT.split(text):
        if chunk is None:
            continue
        start = text.find(chunk, pos)
        if start < 0:
            start = pos
        pos = start + len(chunk)
        stripped = chunk.strip()
        if not stripped:
            continue
        if stripped.count(",") >= 1 and len(stripped) > 60:
            lead = leading_negation(stripped)
            sub_pos = start
            for piece in stripped.split(","):
                p = piece.strip()
                if not p:
                    continue
                s_ = text.find(p, sub_pos)
                if s_ < 0:
                    s_ = sub_pos
                sub_pos = s_ + len(p)
                ev = p
                if lead and not leading_negation(p):
                    ev = lead + re.sub(r"^(and|or)\s+", "", p, flags=re.I)
                claims.append({"text": p, "eval_text": ev,
                               "start": s_, "end": s_ + len(p)})
        else:
            for piece in _split_polarity_switch(stripped):
                s_ = text.find(piece, start)
                if s_ < 0:
                    s_ = start
                claims.append({"text": piece, "eval_text": piece,
                               "start": s_, "end": s_ + len(piece)})
    return claims


# "and", "but" or "with" followed by a negation cue joins two INDEPENDENT
# assertions of opposite polarity.
_POLARITY_SWITCH = re.compile(
    r"\s*(?:,\s*)?\b(?:and|but|although|though|while|with|however)\b\s+"
    r"(?=(?:she|he|the patient|patient|they)?\s*"
    r"(?:no|not|denies|denied|denying|without|negative for|never)\b)",
    re.I)


def _split_polarity_switch(sentence: str) -> list:
    """Separate a positive assertion from a negative one sharing a sentence.

    "Right flank pain and no cough" is two claims, and only one of them was
    obtained. Auditing it whole produced a single "supported" verdict that
    quietly credited the half the encounter never established. Splitting only
    where the polarity switches keeps ordinary phrases such as "right upper
    quadrant and right flank" intact.
    """
    parts = [p.strip(" ,;") for p in _POLARITY_SWITCH.split(sentence)]
    parts = [p for p in parts if len(p) > 2]
    return parts if len(parts) > 1 else [sentence]


# --------------------------------------------------------------------------
# Spelling / style (rubric row: Spelling/Style, 2 points)
# --------------------------------------------------------------------------

_COMMON_MISSPELLINGS = {
    "abdomon": "abdomen", "diarhea": "diarrhea",
    "diarrhoea": "diarrhea (US spelling)", "nausia": "nausea",
    "vomitting": "vomiting", "recieve": "receive", "seperate": "separate",
    "occured": "occurred", "sympotms": "symptoms", "symtoms": "symptoms",
    "tenderess": "tenderness", "auscultaion": "auscultation",
    "ausculation": "auscultation", "palpitation of the abdomen": "palpation",
    "medicaiton": "medication", "prescibed": "prescribed",
    "hypertention": "hypertension", "diabetis": "diabetes",
    "pnemonia": "pneumonia", "pnuemonia": "pneumonia", "asthama": "asthma",
    "wheazing": "wheezing", "shortnes": "shortness", "breif": "brief",
    "radiatiing": "radiating", "assesment": "assessment",
    "assessement": "assessment", "diagosis": "diagnosis", "diagnosos": "diagnosis",
    "diffrential": "differential", "differental": "differential",
    "osteopatic": "osteopathic", "osteopathis": "osteopathic",
    "dysfuntion": "dysfunction", "dysfucntion": "dysfunction",
    "follwo": "follow", "folow": "follow", "aleviating": "alleviating",
    "allevating": "alleviating", "agravating": "aggravating",
    "aggrivating": "aggravating", "assoicated": "associated",
    "assocated": "associated", "familly": "family", "histroy": "history",
    "hisotry": "history", "alergies": "allergies", "allergys": "allergies",
    "colour": "color (US spelling)", "oedema": "edema (US spelling)",
    "haemoptysis": "hemoptysis (US spelling)", "anaemia": "anemia (US spelling)",
    "diarrheoa": "diarrhea (US spelling)", "paediatric": "pediatric (US spelling)",
}

# British spellings -- Sebastian sits US board-style exams.
_BRITISH = {
    "haemo": "hemo", "oedema": "edema", "oesophag": "esophag",
    "diarrhoea": "diarrhea", "anaemi": "anemi", "paediatr": "pediatr",
    "leukaemi": "leukemi", "colour": "color", "behaviour": "behavior",
    "centre": "center", "litre": "liter", "fibre": "fiber",
    "ischaemi": "ischemi", "gynaecolog": "gynecolog", "orthopaedic": "orthopedic",
    "tumour": "tumor", "catheterise": "catheterize", "hospitalise": "hospitalize",
}


def spelling_issues(text: str) -> list:
    issues = []
    norm = normalize(text)
    for wrong, right in _COMMON_MISSPELLINGS.items():
        if right and re.search(r"\b" + re.escape(wrong) + r"\b", norm):
            issues.append({"found": wrong, "suggest": right, "kind": "spelling"})
    for brit, us in _BRITISH.items():
        # A left word boundary is required. These entries are STEMS, and a bare
        # substring test reports "gastroesophageal" as the British
        # "oesophageal" because the stem sits inside the combining form.
        if re.search(r"(?<![a-z])" + re.escape(brit), norm):
            issues.append({"found": brit, "suggest": us, "kind": "us-english"})
    return issues


_ABBR_TOKEN = re.compile(r"\b([a-zA-Z]{1,6}(?:/[a-zA-Z]{1,6})?)\b")


def unapproved_abbreviations(text: str) -> list:
    """Uppercase-looking short tokens not on the manual's approved surface."""
    out = []
    seen = set()
    for m in re.finditer(r"\b[A-Za-z][A-Za-z/]{1,5}\b", text or ""):
        raw = m.group(0)
        # Only consider tokens written in caps -- that is how abbreviations
        # appear.  Ordinary words in a sentence are not flagged.
        letters = [c for c in raw if c.isalpha()]
        if not letters or not all(c.isupper() for c in letters):
            continue
        key = raw.lower()
        if key in lexicon.ALL_APPROVED or key in seen:
            continue
        if len(letters) < 2:
            continue
        # "CN II-XII" contains numerals, not abbreviations.
        if re.fullmatch(r"[IVXLC]+", raw):
            continue
        seen.add(key)
        out.append({"abbrev": raw, "pos": m.start()})
    return out
