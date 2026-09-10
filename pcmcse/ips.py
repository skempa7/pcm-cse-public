"""Interpersonal and professional skills.

Two instruments, kept separate because the course keeps them separate:

  A. The **Arizona Clinical Interview Rating Scale** as printed in the student
     manual -- ten items, anchored Mastery (5) / Average (3) / Poor (1).  The
     original Stillman 1977 instrument has fourteen items; the syllabus says
     the form "has been modified to meet the criteria expected of a second year
     medical student", so the manual's ten govern here.

  B. The **Interpersonal Skills Relationship Form** -- fifteen items,
     1 Failed / 2 Poor / 3 Good / 4 Very Good / 5 Excellent.

Items that this format cannot observe are returned as NOT ASSESSED with the
reason, and are excluded from any average rather than silently scored.
"""

from __future__ import annotations

import re

from . import claims, evidence, nlp

# ---------------------------------------------------------------------------
# Signals harvested from the encounter
# ---------------------------------------------------------------------------

_SECTION_CUES = {
    "hpi": ["pain", "symptom", "when did", "how long", "describe", "scale",
            "worse", "better", "radiate", "started"],
    "pmh": ["medical problem", "medical condition", "medical history",
            "surgery", "hospitaliz", "diagnosed"],
    "meds": ["medication", "meds", "taking any", "prescription", "pills"],
    "allergies": ["allerg"],
    "social": ["smoke", "tobacco", "alcohol", "drink", "drug", "work", "job",
               "live with", "occupation", "sexually"],
    "family": ["family history", "parents", "mother", "father", "sibling",
               "brother", "sister"],
    "ros": ["any fever", "any chills", "cough", "chest pain", "headache",
            "rash", "nausea", "diarrhea", "shortness of breath", "review"],
}

_JARGON = [
    "dysuria", "hematuria", "nocturia", "hemoptysis", "dyspnea", "orthopnea",
    "myalgia", "arthralgia", "paresthesia", "syncope", "diaphoresis",
    "auscultate", "palpate", "percuss", "edema", "erythema", "pruritus",
    "hepatomegaly", "splenomegaly", "afebrile", "febrile", "emesis",
    "odynophagia", "dysphagia", "claudication", "somatic dysfunction",
    "viscerosomatic", "costovertebral", "epigastric", "differential diagnosis",
    "etiology", "idiopathic", "prognosis", "contraindicated", "bilateral",
    "anterior", "posterior", "lateral", "palpation", "auscultation",
]

_JARGON_EXPLAINED = ["which means", "that means", "in other words", "basically",
                     "put another way", "what i mean by that", "or "]

_PLAN_TALK = ["i'd like to", "i would like to", "we're going to", "we are going to",
              "the plan is", "what i'd recommend", "what i recommend", "next step",
              "i'm going to order", "i want to check", "we'll get", "we will get",
              "i'll prescribe", "you should", "i want you to", "come back",
              "follow up", "if it gets worse", "return"]

_ACK_PAIN = ["painful", "sorry you're", "sorry youre", "must hurt",
             "uncomfortable", "in pain", "get you comfortable", "it hurts",
             "hurting", "miserable", "rough", "difficult", "unpleasant",
             "sounds awful", "that's a lot", "thats a lot"]

# ACIR item 5's Mastery anchor is "summarizes the data AND SEEKS VERIFICATION
# or assures no important data is missing".  Three accurate items on their own
# is the Average anchor.
_VERIFICATION_CUES = [
    "have i missed anything", "did i miss anything", "am i missing anything",
    "is that right", "does that sound right", "did i get that right",
    "is that correct", "anything i left out", "anything else i should know",
    "have i got that right", "correct me if", "does that match",
    "is that accurate", "did i understand", "did i get everything",
    "anything i missed", "does that cover", "is there anything else",
]

# What opens a summary.  The failure this replaced matched a fixed list of
# stock phrases, so "Let me make sure I understand: ..." -- an opener students
# really use -- was scored "no summary detected" at the Poor anchor.  What all
# of these share is a first-person announcement that the next words are the
# patient's own story played back, so that is what is matched: a recap verb
# ("summarize", "recap", "go over", "play back") or a comprehension check
# ("make sure I understand", "if I've got this right", "what I'm hearing").
#
# The opener is therefore assembled from its parts rather than listed as whole
# phrases, because a phrase list only moves the boundary instead of removing
# it: written out in full, "Let me make sure I HAVE this right" was a summary
# and "Let me make sure I'VE GOT this right" -- the same sentence, one
# contraction apart -- was "no summary detected" at the Poor anchor.
_SUMMARY_SUBJECT = r"(?:i|we)(?:'ve|'m|'re|'d|'ll)?"

# What the student claims to have done with the story.  The bare verbs
# ("understand", "heard") stand alone; "have"/"got" need an object, because
# "so I have a few more questions" is a transition, not a summary.
_SUMMARY_GRASP = (
    r"(?:understand\w*|understood|heard|hear|on the same page"
    r"|(?:have|had|has|got|gotten|get)\s+"
    r"(?:it|this|that|these|everything|things|the (?:story|picture|timeline|"
    r"sequence|order)))")

_SUMMARY_OPENER_RE = re.compile(
    r"(?<![a-z])("
    # The student names the act outright.  "summary" belongs here as much as
    # "summarize" does: "In summary, ..." is the phrase students reach for
    # most, and matching only the verb form scored it as no summary at all.
    r"summariz\w*|summaris\w*|summary|recap\w*"
    r"|sum(?:ming)?\s+(?:that\s+|this\s+|it\s+)?up"
    # A comprehension check: "let me make sure I understand", "just so I have
    # it straight", "to make sure we're on the same page".
    r"|(?:make sure|makes sure|see if|check|confirm|so)\s+(?:that\s+)?"
    + _SUMMARY_SUBJECT + r"\s*" + _SUMMARY_GRASP +
    r"|if\s+" + _SUMMARY_SUBJECT + r"\s*" + _SUMMARY_GRASP +
    # Reporting back the story just heard.
    r"|what\s+i(?:'m|'ve)?\s*(?:am\s+)?(?:hearing|heard|understand|understood)"
    r"|what\s+you(?:'ve|'re)?\s+(?:told|said|have told|are telling|telling)\s+me"
    r"|the story so far"
    r"|put(?:ting)?\s+(?:that|this|it|everything)\s+(?:all\s+)?together"
    # Playing the story back to the patient.
    r"|(?:play|read|repeat|run|go|walk|reflect)\s+(?:that|this|it)\s+back"
    r"|(?:repeat|play|read|reflect)\s+back"
    r"|(?:review|go over|run through|walk through)\s+(?:what|the)"
    r")")

# What may sit between the opener and the first finding: a closing word of the
# opener ("...this right"), a connector, and the punctuation around them.  It
# is an explicit short list rather than "anything up to the next comma",
# because a greedy tail eats the first finding whenever the student writes no
# colon -- the same three-item summary then scored 5/5 with a colon after the
# opener and 2/5 without one.
_OPENER_TAIL_RE = re.compile(
    r"^[\s,:;\u2013\u2014-]*"
    r"(?:(?:this|that|it|everything|things)\s+)?"
    r"(?:right|correct|correctly|straight|clear|so far)?"
    r"[\s,:;\u2013\u2014-]*"
    r"(?:so|and|then|okay|ok|well)?"
    r"[\s,:;\u2013\u2014-]*"
    r"(?:that\s+)?")

# How far past the opener a colon may sit and still be the colon that
# introduces the list, rather than one inside the findings themselves.
_OPENER_COLON_WINDOW = 40

# Words that carry no clinical content of their own.  A summary item has to be
# about the patient, so a segment whose only recognisable words are function
# words or the station's own boilerplate ("the patient", "the plan", "the
# chart") is not a clinical proposition and is never counted as one.
_NON_CLINICAL_WORDS = {
    "a", "an", "and", "also", "about", "after", "again", "all", "along",
    "am", "any", "are", "around", "as", "at", "back", "be", "because",
    "been", "before", "being", "both", "but", "by", "can", "could", "did",
    "do", "does", "for", "from", "get", "getting", "go", "going", "got",
    "had", "has", "have", "having", "her", "here", "his", "how", "i", "if",
    "in", "into", "is", "it", "its", "just", "like", "me", "more", "most",
    "much", "my", "no", "not", "now", "of", "off", "on", "one", "only",
    "or", "other", "our", "out", "over", "own", "said", "same", "say",
    "she", "should", "since", "so", "some", "still", "such", "than",
    "that", "the", "their", "them", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "up", "us", "very", "was",
    "we", "well", "were", "what", "when", "where", "which", "while", "who",
    "why", "will", "with", "would", "yes", "you", "your",
    # Station and encounter furniture: present in every doorway sheet, so
    # matching one of them says nothing about the patient's history.
    "assistant", "care", "chart", "clinic", "discuss", "encounter",
    "entered", "examination", "history", "medical", "medicine", "minutes",
    "patient", "perform", "physical", "plan", "point", "result", "results",
    "room", "signs", "station", "today",
}

# Suffix rules just deep enough to let a summary paraphrase reach the words the
# encounter used: "urination" in the chart has to match "urinate" in the
# summary.  Deliberately conservative -- over-stemming is what makes a scorer
# credit nonsense, so "clouds" must not reach "cloudy" and "cars" must not
# reach "care".
_SUFFIX_RULES = (
    ("ations", "ate"), ("ation", "ate"),
    ("ities", "ity"), ("ies", "y"),
    ("sses", "ss"), ("ches", "ch"), ("shes", "sh"), ("xes", "x"), ("zes", "z"),
    ("ingly", ""), ("ing", ""),
    ("edly", ""), ("ed", ""),
    ("s", ""),
)
# The suffixes that can swallow a silent "e": "sided" -> "sid" has to reach
# "side", and "urinating" -> "urinat" has to reach "urinate".
_RESTORE_E = {"ingly", "ing", "edly", "ed"}
_VOWELS = "aeiou"


def _ends_cvc(stem):
    """Porter's consonant-vowel-consonant test for restoring a silent 'e'."""
    if len(stem) < 3:
        return False
    a, b, c = stem[-3], stem[-2], stem[-1]
    return (a not in _VOWELS and b in _VOWELS and c not in _VOWELS
            and c not in "wxy")


def _stem(word):
    """A crude morphological key shared by a word and its inflections."""
    for suffix, replacement in _SUFFIX_RULES:
        if not word.endswith(suffix):
            continue
        if suffix == "s" and word.endswith("ss"):
            continue
        stem = word[:len(word) - len(suffix)] + replacement
        if len(stem) < 3:
            continue
        if suffix in _RESTORE_E and _ends_cvc(stem):
            stem += "e"
        return stem
    return word


_WORD_RE = re.compile(r"[a-z][a-z']*|\d+(?:\.\d+)?")


def _words(text):
    return _WORD_RE.findall(nlp.normalize(text).replace("-", " "))


def _content_tokens(text):
    """The stems of the words in `text` that could be about the patient."""
    return [_stem(w) for w in _words(text)
            if w not in _NON_CLINICAL_WORDS and len(w) > 1]


# A charted temperature is the evidence for the word "fever": the chart never
# writes "fever", so a summary that says "you have had a fever" would look
# unsupported and the student would be marked down for reading the chart
# correctly.  The threshold is the ordinary clinical one, not a course anchor.
_FEVER_F = 100.4
_TEMPERATURE_RE = re.compile(r"(?<![a-z0-9])t\W{0,4}(\d{2,3}(?:\.\d)?)")


def _evidence_sources(ledger, case):
    """Every text the frozen encounter record produced.

    `claims.evidence_index` supplies the concept attributes; the patient's own
    replies are added here because a summary is a play-back of exactly those,
    and the index's own text blob does not carry them.
    """
    index = claims.evidence_index(ledger, case)
    sources = [index.get("blob", "")]
    sources.extend(str(v) for v in (index.get("values") or {}).values())
    sources.extend(str(q) for q in (index.get("quotes") or {}).values())
    for ev in ledger.by_kind(evidence.PATIENT, evidence.EXAM_FINDING,
                             evidence.STATION_INFO):
        sources.append(ev.get("text") or "")
    return sources


def _evidence_vocabulary(ledger, case):
    """The word stems the encounter affirmed, and the ones it explicitly denied.

    Polarity has to travel with the words.  A patient who answers "no cough, no
    chest pain" puts those words into the record without making either one a
    finding, so a summary that plays them back as findings is inaccurate.
    Matching on the words alone credited exactly that.
    """
    affirmed, denied = set(), set()
    sources = _evidence_sources(ledger, case)
    for text in sources:
        normalized = nlp.normalize(text)
        # Hyphens are replaced one-for-one so the offsets still line up with
        # the negation spans, which are measured on the normalized text.
        flat = normalized.replace("-", " ")
        spans = nlp.negation_scope(text)
        for match in _WORD_RE.finditer(flat):
            stem = _stem(match.group(0))
            if any(a <= match.start() < b for a, b in spans):
                denied.add(stem)
            else:
                affirmed.add(stem)

    for text in sources:
        match = _TEMPERATURE_RE.search(nlp.normalize(text))
        if match and float(match.group(1)) >= _FEVER_F:
            affirmed.update((_stem("fever"), _stem("febrile"),
                             _stem("temperature")))
            break
    return affirmed, denied


def _flatten(raw):
    """Lower-case a turn without moving a single character offset.

    Summaries are read on the raw text, because normalization throws away the
    commas that separate the items and the question marks that mark the
    verification; every replacement here is one character for one, so an offset
    found in the flattened text still points at the same place in the original.
    """
    return (raw or "").lower().replace("\u2019", "'").replace("\u2018", "'")


# Split on the RAW text: normalization drops the commas that separate the items.
_SEGMENT_SPLIT = re.compile(r"[,;]|\band also\b|\band\b|\bplus\b", re.I)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _summary_body(raw):
    """The part of a summary turn that is supposed to carry the findings.

    The opener and the verification question are stripped, because neither is
    a clinical proposition: "Let me summarize. Is that correct?" has to come
    out of here empty, which is the whole point of the item.
    """
    match = _SUMMARY_OPENER_RE.search(_flatten(raw))
    if not match:
        return ""
    # A colon just after the opener introduces the list.  Without one the
    # findings start where the opening phrase and its closing words end, which
    # is why the tail is stripped rather than swallowed by the opener match.
    colon = raw.find(":", match.start())
    if 0 <= colon <= match.end() + _OPENER_COLON_WINDOW:
        body = raw[colon + 1:]
    else:
        body = _OPENER_TAIL_RE.sub("", raw[match.end():], count=1)
    keep = []
    for sentence in _SENTENCE_SPLIT.split(body):
        stripped = sentence.strip()
        if not stripped or stripped.endswith("?"):
            continue
        keep.append(stripped)
    return " ".join(keep)


def _propositions(raw):
    """Candidate clinical propositions listed in one summary turn."""
    out = []
    for segment in _SEGMENT_SPLIT.split(_summary_body(raw)):
        tokens = _content_tokens(segment)
        if tokens:
            out.append({"text": " ".join(segment.split()), "tokens": tokens})
    return out


def _score_propositions(raw_turns, affirmed, denied):
    """Sort the summarized propositions into supported and contradicted ones.

    A proposition is supported when the encounter actually produced what it is
    about: at least one of its content words, and at least half of them, are in
    the evidence of the polarity the proposition asserts.  Half rather than
    all, because a summary is a paraphrase -- "the flank pain" is a fair
    play-back of "right-sided back pain" -- and at least one, because that is
    what separates a finding from a list of nouns the patient never mentioned.

    A proposition that asserts something the encounter explicitly denied is
    contradicted however many of its other words match, because summarizing
    "chest pain" to a patient who has just denied chest pain is not an
    accurate summary of anything.
    """
    supported, contradicted, seen = [], [], set()
    for raw in raw_turns:
        for prop in _propositions(raw):
            negative = nlp.surface_is_negative(prop["text"])
            wanted, opposite = ((denied, affirmed) if negative
                                else (affirmed, denied))
            key = frozenset(prop["tokens"])
            if key in seen:
                continue
            seen.add(key)
            wrong = [t for t in prop["tokens"]
                     if t in opposite and t not in wanted]
            if wrong:
                prop["contradicted_by"] = wrong
                contradicted.append(prop)
                continue
            matched = [t for t in prop["tokens"] if t in wanted]
            if matched and len(matched) * 2 >= len(prop["tokens"]):
                supported.append(prop)
    return supported, contradicted


# ACIR item 10's Mastery anchor names three components explicitly: "what the
# interviewer will do, what the patient should do, the time of the next
# communication".  Each one is looked for separately, sentence by sentence, and
# each has to carry real content.  The failure this replaced credited the shape
# of a plan instead of a plan: "I will order nothing.  You should do nothing.
# Today is Tuesday." scored all three, and "I will order a urine culture today"
# scored a next-contact time because a time word appeared anywhere in the turn.
_PLAN_SUBJECT = (r"(?:i'?m going to|i am going to|i'?ll|i will|i'?d like to|"
                 r"i would like to|i want to|i need to|i'?d recommend|"
                 r"i recommend|we'?re going to|we are going to|"
                 r"we'?ll|we will|we should|we can|we need to|"
                 r"let me|let'?s|lets|i plan to|"
                 r"(?:my|the) plan is to)")
_PLAN_VERB = (r"(?:order|check|send|prescribe|start|refer|run|get|obtain|"
              r"draw|admit|treat|give|write|arrange|schedule|do|put you on|"
              r"set you up|call in|swab|culture|book)")
_SELF_PLAN_RE = re.compile(_PLAN_SUBJECT + r"\s+" + _PLAN_VERB + r"(?![a-z])")

_PATIENT_DIRECTIVE_RE = re.compile(
    r"(?<![a-z])(?:you should|you'?ll need to|you will need to|you need to|"
    r"you must|you have to|you'?ll want to|i want you to|i'?d like you to|"
    r"i would like you to|i need you to|i'?ll need you to|"
    r"i will need you to|we need you to|it'?s important that you|"
    r"make sure you|make sure to|be sure to|be sure you|"
    r"keep taking|stop taking|"
    r"please take|please drink|please finish|please continue|please rest|"
    r"please avoid|try to)(?![a-z])")

# A complement that promises nothing.  "You should do nothing at all" has the
# grammar of an instruction and the content of none.
_NULL_COMPLEMENT_RE = re.compile(
    r"^\s*(?:up|off|out|on)?\s*(?:to\s+)?"
    r"(?:do|take|get|have|need|change|order|start|use|make)?\s*"
    r"(?:any|a|an|the)?\s*"
    r"(?:nothing|none|no tests?|no medications?|no labs?|no workup)"
    r"(?:\s+(?:at all|for now|right now|today|at this time|else|further|"
    r"more|yet))*"
    # Normalization keeps the sentence's own full stop, so the complement can
    # legitimately end on one.
    r"[\s.!?,;]*$")

# A next contact is a promise to communicate again, so the time has to be bound
# to a contact: "a urine culture today" is when the culture is sent, not when
# the patient will next hear from anyone.
_CONTACT_RE = re.compile(
    r"(?<![a-z])(?:come back|coming back|come in|see you|see me|seeing you|"
    r"see each other again|see one another again|"
    r"follow up|follow-up|followup|return|returning|recheck|re-check|"
    r"check in with you|check back|check on you|"
    r"call you|call the office|give you a call|give the office a call|"
    r"reach out|"
    r"be in touch|in touch|get back to you|get you back in|bring you back|"
    r"have you back|book you|hear from me|hear from us|touch base|"
    r"let you know|send you the results|visit|appointment|"
    r"speak again|talk again|meet again)(?![a-z])")

_TIME_RE = re.compile(
    r"(?<![a-z])(?:"
    r"in (?:about |around |roughly )?"
    r"(?:a|an|one|two|three|four|five|six|seven|eight|ten|twelve|\d+)"
    r"[\s-]?(?:hour|hours|day|days|week|weeks|month|months)"
    r"|within (?:the next )?(?:a|an|one|two|three|\d+)[\s-]?"
    r"(?:hour|hours|day|days|week|weeks)"
    r"|in (?:a|an) (?:couple|few)(?: of)?[\s-]?"
    r"(?:hours|days|weeks|months)"
    r"|(?:a|an|one|two|three|four|five|six|\d+)[\s-]?"
    r"(?:hour|hours|day|days|week|weeks|month|months) from now"
    r"|tomorrow|tonight|later today|first thing"
    r"|this (?:afternoon|evening|morning|week)"
    r"|next (?:week|month|visit|appointment|time)"
    r"|on (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"|when (?:the |your )?(?:results|culture|labs|lab)"
    r"|once (?:the |your )?(?:results|culture|labs|lab)"
    r"|as soon as|before you leave|right away|straight away"
    r"|today|right now|immediately"
    r")(?![a-z])")

# How far apart a contact and its time may sit and still be the same promise.
_BINDING_CHARS = 24


def _sentences(raw):
    """One turn split where its own punctuation ends a thought.

    Closure is decided sentence by sentence so that the three components of the
    anchor need three separate statements behind them.
    """
    return [s for s in _SENTENCE_SPLIT.split(raw or "") if s.strip()]


def _states_own_action(sentence):
    """Does this normalized sentence promise something the interviewer will do?"""
    match = _SELF_PLAN_RE.search(sentence)
    if not match:
        return False
    return not _NULL_COMPLEMENT_RE.match(sentence[match.end():])


def _states_patient_action(sentence):
    """Does this normalized sentence ask the patient to do something?"""
    match = _PATIENT_DIRECTIVE_RE.search(sentence)
    if not match:
        return False
    return not _NULL_COMPLEMENT_RE.match(sentence[match.end():])


def _states_next_contact(sentence):
    """Is a time expression bound to an actual next contact in this sentence?

    Proximity is the binding test: "see you back in 48 hours" schedules the
    next contact, while "order a urine culture today" puts the same kind of
    time word on the order instead, which is what used to be credited.
    """
    contacts = list(_CONTACT_RE.finditer(sentence))
    if not contacts:
        return False
    for time_match in _TIME_RE.finditer(sentence):
        for contact in contacts:
            if 0 <= time_match.start() - contact.end() <= _BINDING_CHARS:
                return True
            if 0 <= contact.start() - time_match.end() <= _BINDING_CHARS:
                return True
    return False


_CLOSURE_TESTS = (
    ("self", _states_own_action),
    ("patient", _states_patient_action),
    ("when", _states_next_contact),
)


def _signals(ledger, case):
    turns = ledger.student_turns()
    sig = {
        "turns": len(turns),
        "sections": [],
        "revisits": 0,
        "transitions": [],
        "transitions_explained": 0,
        "open_questions": 0,
        "closed_questions": 0,
        "empathy": [],
        "summary": [],
        "summary_items": 0,
        "summary_props": [],
        "summary_wrong": [],
        "summary_verified": False,
        "closure_parts": {},
        "closure": [],
        "closure_items": 0,
        "jargon": [],
        "plan_discussed": [],
        "ack_pain": [],
        "fife": [],
        "interruptions": 0,
        "longest_gap_ms": 0,
        "first_word_ms": None,
        "last_word_ms": 0,
        "chronology": set(),
    }

    seen_sections = []
    prev_t = None
    for ev in turns:
        text = ev["text"]
        t = nlp.normalize(text)
        m0 = ev["meta"] or {}
        # Narrating an examination, summarising, or explaining the plan is not
        # "returning to a section already concluded".
        is_summary = bool(m0.get("summary")) or bool(
            _SUMMARY_OPENER_RE.search(_flatten(text)))
        structural = bool(m0.get("exam_turn") or m0.get("counseling_turn")
                          or is_summary or m0.get("closure"))
        if sig["first_word_ms"] is None:
            sig["first_word_ms"] = ev["t_ms"]
        sig["last_word_ms"] = max(sig["last_word_ms"], ev["t_ms"])
        if prev_t is not None:
            sig["longest_gap_ms"] = max(sig["longest_gap_ms"], ev["t_ms"] - prev_t)
        prev_t = ev["t_ms"]

        for section, cues in ([] if structural else _SECTION_CUES.items()):
            if any(c in t for c in cues):
                if seen_sections and seen_sections[-1] != section:
                    if section in seen_sections[:-1]:
                        sig["revisits"] += 1
                if not seen_sections or seen_sections[-1] != section:
                    seen_sections.append(section)
                break

        meta = ev["meta"] or {}
        if meta.get("transition"):
            sig["transitions"].append(text)
            if meta.get("transition_explained"):
                sig["transitions_explained"] += 1
        if meta.get("empathy"):
            sig["empathy"].append(text)
        if is_summary:
            sig["summary"].append(text)
            if any(c in t for c in _VERIFICATION_CUES):
                sig["summary_verified"] = True
        if meta.get("closure"):
            sig["closure"].append(text)
            sig["closure_items"] = max(sig["closure_items"], _count_closure(text))
        if meta.get("open_question"):
            sig["open_questions"] += 1
        elif meta.get("closed_question"):
            sig["closed_questions"] += 1

        # Examination narration is necessarily technical -- the app requires
        # it -- so it is excluded from the jargon item rather than penalised.
        if not m0.get("exam_turn"):
            for j in _JARGON:
                if re.search(r"\b" + re.escape(j), t):
                    explained = any(x in t for x in _JARGON_EXPLAINED)
                    sig["jargon"].append({"term": j, "explained": explained,
                                          "quote": text, "time": _t(ev)})
        if any(p in t for p in _PLAN_TALK):
            sig["plan_discussed"].append({"quote": text, "time": _t(ev)})
        if any(p in t for p in _ACK_PAIN):
            sig["ack_pain"].append({"quote": text, "time": _t(ev)})
        for cue, key in _CHRONOLOGY_CUES:
            if cue in t:
                sig["chronology"].add(key)
        # ACIR item 10 components.  Narrating an examination is not a statement
        # of future plans, so those turns are not scanned.  Each component is
        # decided sentence by sentence and keeps the sentence that supports it,
        # so the three parts of the anchor cannot be carried by one phrase.
        if not m0.get("exam_turn"):
            for sentence in _sentences(text):
                clause = nlp.normalize(sentence)
                for key, test in _CLOSURE_TESTS:
                    if key not in sig["closure_parts"] and test(clause):
                        sig["closure_parts"][key] = sentence.strip()

    _affirmed, _denied = _evidence_vocabulary(ledger, case)
    sig["summary_props"], sig["summary_wrong"] = _score_propositions(
        sig["summary"], _affirmed, _denied)
    sig["summary_items"] = len(sig["summary_props"])
    sig["sections"] = seen_sections
    sig["fife"] = [e for e in ledger.by_kind(evidence.PATIENT)
                   if "fife" in str(e["meta"].get("categories", ""))
                   or e["meta"].get("emotion")]
    sig["interruptions"] = len(ledger.interruptions())
    return sig


def _t(ev):
    return "%d:%02d" % (ev["t_ms"] // 60000, (ev["t_ms"] // 1000) % 60)


# ACIR item 2 asks for the chronological sequence of the illness.  It used to be
# hard-wired to the Mastery anchor -- an encounter with no student turns at all
# scored 5 -- so it now reads the question types the student actually asked.
_CHRONOLOGY_CUES = [
    ("when did", "onset"), ("when do", "onset"), ("when does", "onset"),
    ("how long", "onset"), ("start", "onset"), ("began", "onset"),
    ("begin", "onset"), ("onset", "onset"), ("first notice", "onset"),
    ("first time", "onset"),
    ("getting worse", "course"), ("gotten worse", "course"),
    ("since then", "course"), ("changed", "course"), ("changing", "course"),
    ("come and go", "course"), ("comes and goes", "course"),
    ("constant", "course"), ("progress", "course"), ("over time", "course"),
    ("better or worse", "course"), ("worse or better", "course"),
    ("each day", "course"), ("every day", "course"),
    ("right now", "current"), ("how is it now", "current"),
    ("currently", "current"), ("at the moment", "current"),
    ("how bad", "current"), ("feeling now", "current"),
    ("scale of 1 to 10", "current"), ("scale of one to ten", "current"),
]


def _count_closure(text):
    t = nlp.normalize(text)
    hits = 0
    for word in ["question", "comment", "concern", "worry", "anything else"]:
        if word in t:
            hits += 1
    return hits


# ---------------------------------------------------------------------------
# A. Arizona Clinical Interview Rating Scale (manual's 10-item version)
# ---------------------------------------------------------------------------

def _acir(sig, ledger, case):
    items = []

    def add(num, name, score, why, evidence_list=None, not_assessed=False, reason=""):
        items.append({
            "number": num, "name": name,
            "score": None if not_assessed else score,
            "not_assessed": not_assessed, "reason": reason,
            "why": why, "evidence": evidence_list or [],
        })

    # 1 Organization
    revisits = sig["revisits"]
    if sig["turns"] == 0:
        add(1, "Organization", 0, "", not_assessed=True,
            reason=("The encounter contains no student turns, so there is no "
                    "interview to judge the organization of."))
    elif revisits == 0 and len(sig["sections"]) >= 4:
        add(1, "Organization", 5,
            "You moved through %d history sections without returning to a "
            "section you had already closed: %s."
            % (len(sig["sections"]), " -> ".join(sig["sections"])))
    elif revisits <= 2:
        add(1, "Organization", 3,
            "You returned to an already-closed section %d time(s). Order visited: "
            "%s." % (revisits, " -> ".join(sig["sections"]) or "none detected"))
    else:
        add(1, "Organization", 1,
            "You jumped between sections %d times. The course names this as the "
            "top CSE-1 failure: 'Encounters lacked organization -- jumping "
            "around from one section to another.'" % revisits)

    # 2 Timeline.  Chronology is demonstrated behavior: it is established by
    # asking when the illness began, how it has behaved since, and where it
    # stands now.  The item used to be hard-wired to 5, so an encounter in
    # which nothing at all was said mastered it.
    _chron = sig["chronology"]
    _asked = ", ".join(sorted(_chron)) or "none"
    if sig["turns"] == 0:
        add(2, "Timeline", 0, "", not_assessed=True,
            reason=("The encounter contains no student turns, so no "
                    "chronology could be established either way."))
    elif len(_chron) >= 3:
        add(2, "Timeline", 5,
            "You established onset, course and current state, which is the "
            "chronological sequence the item asks for.")
    elif _chron:
        add(2, "Timeline", 3,
            "You established %s. A full chronology also needs the parts you "
            "did not ask about: %s."
            % (_asked, ", ".join(sorted({"onset", "course", "current"} - _chron))))
    else:
        add(2, "Timeline", 1,
            "No question established when the problem began, how it has "
            "changed, or where it stands now, so the illness has no timeline.")

    # 3 Transitional statements
    n_tr, n_ex = len(sig["transitions"]), sig["transitions_explained"]
    if n_tr >= 3 and n_ex >= 2:
        add(3, "Transitional statements", 5,
            "%d transitions, %d of which explained why you were asking."
            % (n_tr, n_ex), [{"quote": t} for t in sig["transitions"][:3]])
    elif n_tr >= 1:
        add(3, "Transitional statements", 3,
            "%d transition(s), %d explained. The manual's mastery example gives "
            "the reason: 'Now I'm going to ask you some questions about your "
            "family because we find that there are certain diseases that occur "
            "among blood relatives...'" % (n_tr, n_ex),
            [{"quote": t} for t in sig["transitions"][:3]])
    else:
        add(3, "Transitional statements", 1,
            "No transitional statements detected. The patient is left uncertain "
            "why the questions are changing direction.")

    # 4 Pacing
    gap_s = sig["longest_gap_ms"] / 1000.0
    if sig["turns"] == 0:
        add(4, "Pacing of interview", 1, "No student turns recorded.")
    elif gap_s > 45:
        add(4, "Pacing of interview", 3,
            "Longest silence was %.0f seconds. The course flags 'lots of "
            "silence' as a CSE-1 problem." % gap_s)
    else:
        add(4, "Pacing of interview", 5,
            "%d turns with no silence longer than %.0f seconds."
            % (sig["turns"], gap_s))

    # 5 Summarizing.  The manual's anchors, exactly: Mastery(5) "summarizes the
    # data and SEEKS VERIFICATION or assures no important data is missing";
    # Average(3) "summarizes three items accurately"; Poor(1) "fails to
    # summarize any data".  Accuracy is measured against the encounter record,
    # not against the number of commas: a summary that lists three things this
    # patient never mentioned has summarized no data at all.  Verification is
    # an ADDITIONAL requirement on top of an accurate summary, never a
    # substitute for one, so it cannot lift an empty summary anywhere.
    _accurate = sig["summary_items"]
    _wrong = sig["summary_wrong"]
    _evidence = ([{"quote": p["text"]} for p in sig["summary_props"][:3]]
                 or ([{"quote": sig["summary"][0]}] if sig["summary"] else []))
    _wrong_note = ("" if not _wrong else
                   " These parts of the summary say something the encounter "
                   "did not obtain: %s."
                   % "; ".join('\u201c%s\u201d' % w["text"] for w in _wrong[:3]))
    if _accurate >= 3 and sig["summary_verified"] and not _wrong:
        add(5, "Questioning skills - summarizing", 5,
            "You summarized %d findings the encounter had actually obtained "
            "and asked the patient to verify them. Seeking verification is "
            "what the manual's Mastery anchor requires on top of an accurate "
            "summary." % _accurate, _evidence)
    elif _accurate >= 3:
        add(5, "Questioning skills - summarizing", 3,
            "You summarized %d findings the encounter had obtained, which is "
            "the manual's Average anchor (\u201csummarizes three items "
            "accurately\u201d).%s" % (_accurate, _wrong_note or
             " Mastery also needs you to seek verification \u2014 end with "
             "something like \u201cHave I missed anything?\u201d so the patient "
             "can correct you."), _evidence)
    elif _accurate:
        add(5, "Questioning skills - summarizing", 2,
            "You summarized %d finding(s) the encounter had obtained. The "
            "Average anchor is three accurate items, and Mastery also requires "
            "seeking verification.%s" % (_accurate, _wrong_note), _evidence)
    elif sig["summary"]:
        add(5, "Questioning skills - summarizing", 1,
            "You announced a summary but stated nothing the encounter had "
            "obtained, so no data was summarized. Asking the patient to "
            "confirm cannot stand in for the findings themselves.%s"
            % _wrong_note, [{"quote": sig["summary"][0]}])
    else:
        add(5, "Questioning skills - summarizing", 1,
            "No summary detected. The course lists 'lack of summarizing' as a "
            "CSE-1 failure (IPS p. 26).")

    # 6 Lack of jargon
    unexplained = [j for j in sig["jargon"] if not j["explained"]]
    if sig["turns"] == 0:
        add(6, "Questioning skills - lack of jargon", 0, "", not_assessed=True,
            reason=("Nothing was said to the patient, so there is no language "
                    "to judge as plain or technical."))
    elif not sig["jargon"]:
        add(6, "Questioning skills - lack of jargon", 5,
            "No medical jargon detected in what you said to the patient. "
            "Examination narration is excluded -- naming a maneuver has to be "
            "technical, and this app requires you to name it.")
    elif len(unexplained) <= 2:
        add(6, "Questioning skills - lack of jargon", 3,
            "Used %d technical term(s) without defining them: %s."
            % (len(unexplained), ", ".join(j["term"] for j in unexplained)),
            [{"quote": j["quote"], "time": j["time"]} for j in unexplained[:3]])
    else:
        add(6, "Questioning skills - lack of jargon", 1,
            "Used %d technical terms without defining them: %s."
            % (len(unexplained), ", ".join(j["term"] for j in unexplained[:6])),
            [{"quote": j["quote"], "time": j["time"]} for j in unexplained[:3]])

    # 7 Facilitative behaviour -- partly unobservable
    add(7, "Facilitative behavior", 0, "", not_assessed=True,
        reason=("This item scores encouraging gestures, body language, eye "
                "contact and appropriate physical contact. None of that is "
                "observable in a typed or spoken-only encounter."))

    # 8 Rapport / positive verbal reinforcement
    if sig["empathy"] and sig["ack_pain"]:
        add(8, "Rapport - positive verbal reinforcement", 5,
            "You acknowledged the patient's discomfort and offered empathic "
            "responses.", [{"quote": e} for e in sig["empathy"][:2]])
    elif sig["empathy"] or sig["ack_pain"]:
        add(8, "Rapport - positive verbal reinforcement", 3,
            "Some empathic language, but the course flags 'overlooked that the "
            "patient was in pain' as a CSE-1 failure -- acknowledge the "
            "complaint explicitly.",
            [{"quote": e} for e in (sig["empathy"] or [x["quote"] for x in sig["ack_pain"]])[:2]])
    else:
        add(8, "Rapport - positive verbal reinforcement", 1,
            "No empathic acknowledgement detected.")

    # 9 Patient expectations and education
    fife_asked = any(f for f in case.get("facts", [])
                     if f.get("category") == "fife"
                     and f["id"] in ledger.released_facts())
    if fife_asked and sig["plan_discussed"]:
        add(9, "Patient expectations and education", 5,
            "You addressed the patient's own concern and discussed a plan.",
            [{"quote": sig["plan_discussed"][0]["quote"],
              "time": sig["plan_discussed"][0]["time"]}])
    elif sig["plan_discussed"] or fife_asked:
        add(9, "Patient expectations and education", 3,
            "You addressed %s, but not both. Mastery needs the chief complaint, "
            "the patient's concerns and their questions."
            % ("the plan" if sig["plan_discussed"] else "the patient's concern"))
    else:
        add(9, "Patient expectations and education", 1,
            "Neither the patient's own concern nor a plan was addressed.")

    # 10 Closure.  The manual's Mastery anchor is about FUTURE PLANS and names
    # three components: what the interviewer will do, what the patient should
    # do, and the time of the next communication.  Each one is credited only
    # from its own supporting sentence, and only when that sentence promises
    # something: "I will order nothing" is not an investigation, and "today" in
    # "I will order a urine culture today" is when the culture is sent, not
    # when the patient will next hear from anyone.  Inviting questions,
    # comments and concerns is the RELATIONSHIP FORM's item 15, a different
    # instrument, and is scored separately below.
    _parts = [("what you will do", "self"),
              ("what the patient should do", "patient"),
              ("when the next contact happens", "when")]
    _found = sig["closure_parts"]
    _have = [name for name, key in _parts if key in _found]
    _missing = [name for name, key in _parts if key not in _found]
    _support = [{"quote": _found[key], "shows": name}
                for name, key in _parts if key in _found]
    if len(_have) == 3:
        add(10, "Closure of the interview", 5,
            "You specified all three parts of a future plan: what you will do, "
            "what the patient should do, and when the next contact happens. "
            "Each is quoted from the sentence that stated it.", _support)
    elif _have:
        add(10, "Closure of the interview", 3,
            "Partial closure. You covered %s, but not %s. The manual's Mastery "
            "anchor names all three."
            % (" and ".join(_have), " or ".join(_missing)), _support)
    else:
        add(10, "Closure of the interview", 1,
            "No future plan was specified. The patient leaves without knowing "
            "what you will do, what they should do, or when anyone will be in "
            "touch.")

    return items


# ---------------------------------------------------------------------------
# B. Interpersonal Skills Relationship Form (15 items)
# ---------------------------------------------------------------------------

_RELATIONSHIP_ITEMS = [
    (1, "Greeting you warmly; friendly, never crabby or rude"),
    (2, "Treating you like an equal; never lecturing or talking down; non-judgmental"),
    (3, "Letting you tell your story; listening carefully; no interruption"),
    (4, "Showing interest by using eye contact"),
    (5, "Using appropriate body language and/or positioning"),
    (6, "Using easily understood words; free of medical terms and jargon"),
    (7, "Addressing one of the aspects of F.I.F.E."),
    (8, "Making you comfortable (draping; addressing you appropriately; physical contact)"),
    (9, "Facilitation of interview"),
    (10, "Open ended questions"),
    (11, "Closed ended questions"),
    (12, "Transitional statements"),
    (13, "Organization (systematic approach)"),
    (14, "Summary (at least 3 items)"),
    (15, "Closure (at least 2) questions, comments, or concerns"),
]

_NOT_OBSERVABLE = {
    4: "Eye contact cannot be observed in this interaction mode.",
    5: "Body language and physical positioning cannot be observed here.",
}


def _copy(item, source):
    """Carry an ACIR item across to the relationship form it shares wording with.

    The scores travel together, and so does "not assessed": an item the ACIR
    could not observe is not one this form observed either.
    """
    item["score"] = source["score"]
    item["why"] = source["why"]
    if source["not_assessed"]:
        item["not_assessed"] = True
        item["reason"] = source["reason"]
    return item


def _relationship(sig, ledger, case, acir, mode):
    courtesy = ledger.courtesy_done()
    by_name = {i["name"]: i for i in acir}
    out = []
    for num, label in _RELATIONSHIP_ITEMS:
        item = {"number": num, "label": label, "score": None,
                "not_assessed": False, "reason": "", "why": ""}

        if num in _NOT_OBSERVABLE:
            item["not_assessed"] = True
            item["reason"] = _NOT_OBSERVABLE[num]
            out.append(item)
            continue

        if num == 1:
            done = "introduce" in courtesy
            item["score"] = 4 if done else 2
            item["why"] = ("Introduced yourself as a student doctor."
                           if done else "No introduction detected.")
            if "confirm_name" in courtesy:
                item["score"] = 5
                item["why"] += " You also asked how the patient wished to be addressed."
        elif num == 2:
            unexplained = [j for j in sig["jargon"] if not j["explained"]]
            item["score"] = 5 if not unexplained else 3
            item["why"] = ("No lecturing or undefined terminology detected."
                           if not unexplained
                           else "Undefined technical terms can read as talking past "
                                "the patient.")
        elif num == 3:
            item["score"] = 5 if sig["open_questions"] >= 2 else 3
            item["why"] = ("%d open questions gave the patient room to tell the "
                           "story." % sig["open_questions"])
        elif num == 6:
            _copy(item, by_name["Questioning skills - lack of jargon"])
        elif num == 7:
            asked = any(f for f in case.get("facts", [])
                        if f.get("category") == "fife"
                        and f["id"] in ledger.released_facts())
            item["score"] = 5 if asked else 1
            item["why"] = ("You asked what the patient thought was going on or "
                           "what worried them." if asked else
                           "F.I.F.E. was not addressed. The manual lists it as its "
                           "own scored item.")
        elif num == 8:
            comfort = [c for c in ("drape", "gown_help", "position_help",
                                   "comfort_check", "warn_cold") if c in courtesy]
            item["score"] = min(5, 2 + len(comfort))
            item["why"] = ("Comfort behaviors stated: %s."
                           % (", ".join(comfort) or "none"))
            item["partially_assessed"] = (
                "Only what you said is assessed. Whether draping was actually "
                "adequate cannot be observed.")
        elif num == 9:
            item["score"] = 5 if sig["open_questions"] + sig["closed_questions"] >= 8 else 3
            item["why"] = ("%d questions asked in total."
                           % (sig["open_questions"] + sig["closed_questions"]))
        elif num == 10:
            n = sig["open_questions"]
            item["score"] = 5 if n >= 4 else (3 if n >= 1 else 1)
            item["why"] = "%d open-ended questions." % n
        elif num == 11:
            n = sig["closed_questions"]
            item["score"] = 5 if n >= 8 else (3 if n >= 3 else 1)
            item["why"] = "%d focused (closed-ended) questions." % n
        elif num == 12:
            _copy(item, by_name["Transitional statements"])
        elif num == 13:
            _copy(item, by_name["Organization"])
        elif num == 14:
            # This form asks only for three items, and has no verification
            # criterion of its own -- that belongs to the ACIR.  What it does
            # share is what counts as an item: a finding the encounter
            # obtained, not a comma.
            accurate = sig["summary_items"]
            item["score"] = 5 if accurate >= 3 else (
                3 if accurate else (2 if sig["summary"] else 1))
            if accurate:
                item["why"] = ("Summary played back %d finding(s) the encounter "
                               "had obtained; the form asks for at least 3."
                               % accurate)
            elif sig["summary"]:
                item["why"] = ("A summary was announced but it stated nothing "
                               "the encounter had obtained, so it summarized no "
                               "items.")
            else:
                item["why"] = "No summary was given."
        elif num == 15:
            item["score"] = 5 if sig["closure_items"] >= 2 else (
                3 if sig["closure_items"] == 1 else 1)
            item["why"] = ("Invited %d of questions / comments / concerns; the "
                           "form asks for at least 2." % sig["closure_items"])
        out.append(item)
    return out


# ---------------------------------------------------------------------------

def assess(ledger, case, mode="type"):
    sig = _signals(ledger, case)
    acir = _acir(sig, ledger, case)
    relationship = _relationship(sig, ledger, case, acir, mode)

    scored = [i["score"] for i in acir if not i["not_assessed"] and i["score"]]
    rel_scored = [i["score"] for i in relationship
                  if not i["not_assessed"] and i["score"]]

    return {
        "acir": {
            "items": acir,
            "scored_items": len(scored),
            "total_items": len(acir),
            "mean": round(sum(scored) / len(scored), 2) if scored else None,
            "anchors": "Mastery (5) / Average (3) / Poor (1)",
            "provenance": (
                "The student manual's 10-item modified form. The original "
                "Stillman 1977 instrument has 14 items; the syllabus states the "
                "form was modified for second-year students, so the manual's "
                "version governs."),
        },
        "relationship": {
            "items": relationship,
            "scored_items": len(rel_scored),
            "total_items": len(relationship),
            "mean": round(sum(rel_scored) / len(rel_scored), 2) if rel_scored else None,
            "anchors": "1 Failed / 2 Poor / 3 Good / 4 Very Good / 5 Excellent",
        },
        "interaction_mode": mode,
        "signals": {
            "turns": sig["turns"],
            "open_questions": sig["open_questions"],
            "closed_questions": sig["closed_questions"],
            "transitions": len(sig["transitions"]),
            "summary_items": sig["summary_items"],
            "closure_items": sig["closure_items"],
            "longest_silence_s": round(sig["longest_gap_ms"] / 1000.0),
            "sections_visited": sig["sections"],
            "section_revisits": sig["revisits"],
        },
        "not_assessed": [
            "Eye contact (relationship form item 4; ACIR item 7).",
            "Body language and physical positioning (relationship form item 5).",
            "Tone of voice and whether empathy sounded genuine -- the course "
            "notes 'empathy was not genuine, sounded robotic' as a CSE-1 "
            "failure, and text cannot capture that.",
            "Whether draping was physically adequate (only the statement is "
            "assessed).",
        ],
        "note": ("This assessment is separate from the SOAP note score and from "
                 "the case checklist. The course does not state how the three "
                 "combine, so no composite is computed."),
    }
