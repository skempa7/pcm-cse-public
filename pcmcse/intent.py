"""What the learner meant, decided before anything is allowed to happen.

The encounter used to hand every utterance straight to ``physexam.resolve``,
which looks for a body region and a method word.  That is a keyword test, not an
interpretation, and it produced the failures this module exists to stop:

    "Where exactly do you feel the pain in your back?"  -> performed palpation
    "Do you feel pain in your chest?"                   -> palpated the chest
    "Please do not let me palpate your abdomen yet."    -> palpated the abdomen
    "When was your last pap smear?"                     -> recorded a refusal
    "I have no hand sanitizer available."               -> awarded hand hygiene

Every one of those is a *speech act* error rather than a vocabulary error: the
words really are there, but the learner was asking a question, refusing, or
describing an absence.  So the engine now decides the speech act first, and only
one of them -- ``ACTION`` -- is allowed to change examination state.

The taxonomy is the one the course cares about:

``QUESTION``     asking the patient something; the patient answers, nothing is examined
``ACTION``       performing an examination now; the only intent that releases findings
``CONSENT``      asking permission to examine; the patient consents, nothing is examined yet
``PROPOSAL``     offering a future examination ("at this point I would do a rectal exam")
``PAST``         referring to an examination already done; never re-performs it
``NEGATED``      explicitly declining or preventing an action; performs nothing
``SUMMARY``      summarising back to the patient
``COUNSELING``   explaining the plan or educating
``COURTESY``     hygiene, draping, introduction, comfort
``AMBIGUOUS``    cannot be told apart; asks for clarification without releasing anything

Nothing here consults the hidden case.  It reads only the learner's words.
"""

from __future__ import annotations

import re

from . import nlp

QUESTION = "question"
ACTION = "action"
CONSENT = "consent"
PROPOSAL = "proposal"
PAST = "past"
NEGATED = "negated"
SUMMARY = "summary"
COUNSELING = "counseling"
COURTESY = "courtesy"
AMBIGUOUS = "ambiguous"

# Verbs that denote examining, in the forms students actually narrate.
_EXAM_VERBS = [
    "auscultate", "auscultating", "auscultation",
    "palpate", "palpating", "palpation", "palpated",
    "percuss", "percussing", "percussion", "percussed",
    "inspect", "inspecting", "inspection", "inspected",
    "examine", "examining", "exam of", "check", "checking",
    "listen to", "listening to", "listen for", "listened to",
    "feel for", "feeling for", "felt for", "press on", "pressing on",
    "pressed on", "push on", "pushing on", "look in", "looking in",
    "look at", "looking at", "assess", "assessing", "assessed",
    "test", "testing", "tested", "otoscope", "otoscopic",
    "range of motion", "straight leg raise", "perform", "performing",
    "do a", "doing a", "take a look", "have a look", "tap on", "tapping on",
    "measure", "measuring", "observe", "observing",
]

# A first-person actor: the learner is the one doing it.
_FIRST_PERSON = [
    "i ", "i'm", "im ", "i am", "i'll", "ill ", "i will", "i would", "i'd",
    "id ", "let me", "let's", "lets ", "we ", "we'll", "we will", "we're",
    "we are", "my ", "me ",
]

# Modal frames that ask permission rather than announce an action.
_CONSENT_FRAMES = [
    "may i", "can i", "could i", "would it be ok", "would it be okay",
    "would it be alright", "is it ok if i", "is it okay if i",
    "is it alright if i", "do you mind if i", "would you mind if i",
    "would that be ok", "would that be okay", "am i able to",
    "is that ok if i", "with your permission", "if you don't mind",
    "if you dont mind", "would you allow me", "may we", "can we",
    "would you be comfortable if i", "are you comfortable if i",
    "is now a good time for me to", "would you let me",
]

# Frames that offer rather than perform. The course's refusable-examination
# convention lives here: "At this point, I would do a (xxx) exam."
# Genuinely hypothetical framings. "I would like to auscultate the lungs" is
# NOT here: that is how students narrate an examination they are performing,
# and treating it as an offer silently stopped the encounter.  What belongs
# here is the course's own convention for an examination it will not let you
# do -- "At this point, I would do a (xxx) exam." -- and its relatives.
_PROPOSAL_FRAMES = [
    "at this point i would", "at this point i will", "normally i would",
    "ordinarily i would", "in a real encounter i would",
    "in an actual encounter i would", "if this were a real patient i would",
    "on a real patient i would", "i would normally", "i would ordinarily",
    "the next thing i would do", "i would want to do a",
]

# Frames that refer back to something already done.
_PAST_FRAMES = [
    "earlier i", "already", "as i mentioned", "like i said",
    "when i examined", "when i listened", "when i palpated", "a moment ago",
    "previously", "i have already", "i've already", "ive already",
    "i did that", "i just did", "as noted", "i had examined",
    "i have examined", "i've examined", "ive examined", "back when i",
]

# Immediate-action frames: future in form, present in effect.
_IMMEDIATE_FRAMES = [
    "i am going to", "i'm going to", "im going to", "going to",
    "i am now", "i'm now", "im now", "now i", "next i", "i will now",
    "let me", "i am about to", "i'm about to", "im about to",
]

_QUESTION_WORDS = [
    "what", "when", "where", "why", "how", "who", "whom", "whose", "which",
]
_QUESTION_AUX = [
    "do", "does", "did", "are", "is", "was", "were", "have", "has", "had",
    "can", "could", "would", "will", "should", "may", "might", "am",
]
# Second-person framings: the patient is the subject, so this is history.
_ASKS_PATIENT = [
    "do you", "did you", "does it", "did it", "have you", "has it", "had you",
    "are you", "is it", "was it", "were you", "can you", "could you",
    "would you say", "will you", "tell me", "describe", "how long",
    "how often", "how bad", "how much", "how many", "what makes", "what eases",
    "what helps", "what brings", "what brought", "where do you",
    "where is the", "where does", "when did", "when was", "when do",
    "who lives", "who else", "any ", "anything", "do any",
]

_NEGATION_CUES = [
    "do not", "don't", "dont", "do n't", "will not", "won't", "wont",
    "would not", "wouldn't", "wouldnt", "cannot", "can't", "cant",
    "not going to", "no need to", "without", "instead of", "rather than",
    "refuse to", "decline to", "skip", "omit", "avoid", "never",
    "am not", "i'm not", "im not", "not able to", "unable to",
    "no longer", "hold off on", "defer", "postpone", "wait on",
    # The past and perfect families. Without these, "I didn't introduce
    # myself" matched the introduction trigger and was credited AS an
    # introduction -- the learner saying they had NOT done it earned the
    # point for doing it.
    "did not", "didn't", "didnt", "have not", "haven't", "havent",
    "has not", "hasn't", "hasnt", "had not", "hadn't", "hadnt",
    "was not", "wasn't", "wasnt", "were not", "weren't", "werent",
    "forgot to", "failed to", "neglected to", "meant to", "should have",
    # Bare "not" carries the hortative: "Let's not palpate your abdomen yet."
    # It is safe because _negation_reaches is clause-bounded and stops at a
    # contrast word, so "I am not sure, but let me palpate" still examines.
    "not",
]
# "no X available" / "there is no X" -- an absence, not an action.
_ABSENCE_FRAMES = [
    "i have no", "i don't have", "i dont have", "there is no", "there's no",
    "theres no", "we have no", "no access to", "is not available",
    "isn't available", "isnt available", "are not available", "none available",
    "ran out of", "cannot find", "can't find", "cant find",
    "unavailable",
]


def _has(t, needles):
    return any(n in t for n in needles)


def _first(t, needles):
    """Earliest position at which any needle occurs, or -1."""
    best = -1
    for n in needles:
        i = t.find(n)
        if i >= 0 and (best < 0 or i < best):
            best = i
    return best


def _exam_verb_positions(t):
    out = []
    for v in _EXAM_VERBS:
        for m in re.finditer(r"(?<![a-z])" + re.escape(v), t):
            out.append((m.start(), v))
    return sorted(out)


def is_question(raw: str) -> bool:
    """Question by punctuation, by inversion, or by a wh-word opener."""
    raw = (raw or "").strip()
    if not raw:
        return False
    if raw.endswith("?"):
        return True
    for part in re.split(r"[.;!]\s*", raw):
        p = nlp.normalize(part).strip()
        if not p:
            continue
        head = p.split()
        if not head:
            continue
        if head[0] in _QUESTION_WORDS:
            return True
        # Auxiliary inversion: "did the pain start suddenly"
        if head[0] in _QUESTION_AUX and len(head) > 1:
            return True
        if _has(p, ["tell me", "describe"]):
            return True
    return False


def _negation_reaches(t, target_pos):
    """Is a negation cue positioned to scope over `target_pos`?

    Clause-bounded: a negation before a full stop or a contrasting conjunction
    does not carry into the next clause, so "I won't do a rectal exam, but I
    will palpate the abdomen" negates only the first.
    """
    for cue in _NEGATION_CUES:
        for m in re.finditer(r"(?<![a-z])" + re.escape(cue), t):
            if m.start() > target_pos:
                continue
            between = t[m.end():target_pos]
            if re.search(r"[.;]", between):
                continue
            if re.search(r"(?<![a-z])(but|however|although|though|instead i|"
                         r"then i|and then)(?![a-z])", between):
                continue
            # A long gap is usually a different thought.
            if len(between.split()) > 10:
                continue
            return True
    return False


def interpret(text: str, *, courtesy_ids=None, tags=None) -> dict:
    """Classify one learner utterance.

    ``tags`` is the engine's existing marker dictionary (summary / closure /
    plan_talk / empathy), used only to break ties -- the decision below never
    depends on the hidden case.
    """
    tags = tags or {}
    raw = (text or "").strip()
    t = nlp.normalize(raw)
    result = {
        "intent": AMBIGUOUS,
        "negated": False,
        "question": False,
        "exam_verb": None,
        "may_examine": False,
        "reason": "",
    }
    if not t:
        result["reason"] = "empty"
        return result

    question = is_question(raw)
    result["question"] = question
    verbs = _exam_verb_positions(t)
    verb_pos = verbs[0][0] if verbs else -1
    result["exam_verb"] = verbs[0][1] if verbs else None

    # --- 1. An absence is never an action, and never a courtesy ------------
    # These frames describe missing EQUIPMENT ("there is no otoscope"). A
    # question put to the patient is never that, and reading one as an absence
    # silences it: the bare bigram "out of" made "how bad is it out of ten?"
    # -- the commonest severity phrasing there is -- answer "you described
    # something you do not have" instead of releasing the severity fact.
    if not question and _has(t, _ABSENCE_FRAMES):
        result["intent"] = NEGATED
        result["negated"] = True
        result["reason"] = ("You described something you do not have. Nothing "
                            "was performed and no credit was recorded.")
        return result

    # --- 2. Explicit negation of the action --------------------------------
    if verbs and _negation_reaches(t, verb_pos):
        result["intent"] = NEGATED
        result["negated"] = True
        result["reason"] = ("You said you would not do this, so nothing was "
                            "performed.")
        return result
    if not verbs and _has(t, ["do not", "don't", "dont"]) and \
            _has(t, ["let me", "allow me"]):
        result["intent"] = NEGATED
        result["negated"] = True
        result["reason"] = "Nothing was performed."
        return result

    # --- 3. Consent: a permission frame with a first-person examiner -------
    consent_pos = _first(t, _CONSENT_FRAMES)
    if consent_pos >= 0 and verbs:
        result["intent"] = CONSENT
        result["reason"] = ("You asked permission. The patient answers; perform "
                            "the examination when you are ready.")
        return result

    # --- 4. A question is a question ---------------------------------------
    # The learner asking the PATIENT about a sensation, a location or a
    # history is interviewing, however many anatomical words it contains.
    if question:
        asks_patient = _has(t, _ASKS_PATIENT)
        first_person = _has(t, _FIRST_PERSON)
        # "Should I listen to your lungs now?" reads as a consent request even
        # without a canonical permission frame.
        if verbs and first_person and not asks_patient:
            result["intent"] = CONSENT
            result["reason"] = ("Read as asking permission rather than "
                                "performing.")
            return result
        result["intent"] = QUESTION
        result["reason"] = "A question to the patient obtains history."
        return result

    # --- 5. Referring back to work already done ----------------------------
    if verbs and _has(t, _PAST_FRAMES):
        result["intent"] = PAST
        result["reason"] = ("This refers to an examination you have already "
                            "described. It was not performed again.")
        return result

    # --- 6. Offering rather than performing --------------------------------
    proposal_pos = _first(t, _PROPOSAL_FRAMES)
    immediate_pos = _first(t, _IMMEDIATE_FRAMES)
    if verbs and proposal_pos >= 0 and (
            immediate_pos < 0 or proposal_pos < immediate_pos):
        result["intent"] = PROPOSAL
        # An ordinary examination named this way is still carried out; the
        # refusable-examination convention is handled by the caller.
        result["may_examine"] = True
        result["reason"] = ("Read as proposing the examination rather than "
                            "performing it.")
        return result

    # --- 7. Structured speech acts that are not examinations ---------------
    if tags.get("summary"):
        result["intent"] = SUMMARY
        result["reason"] = "Summarising back to the patient."
        return result

    # A plan can mention a test noun or another clinician's examination.
    # A first-person pronoun elsewhere in that paragraph is not an exam actor.
    if tags.get("plan_talk") and verbs:
        actor = r"\b(?:i(?:'d| would) like to|i(?: am|'m) going to|we(?:'d| would) like to|i|we|let me|let's)\s+(?:(?:will|shall|am|are)\s+)?(?:now\s+)?"
        if not re.search(actor + r"(?:" + "|".join(re.escape(v) for v in _EXAM_VERBS) + r")\b", t):
            result["intent"] = COUNSELING
            result["reason"] = "Discussing proposed care; no examination was performed."
            return result

    # --- 8. A performed examination ----------------------------------------
    if verbs and (_has(t, _FIRST_PERSON) or _has(t, _IMMEDIATE_FRAMES)):
        result["intent"] = ACTION
        result["may_examine"] = True
        result["reason"] = "Performing an examination."
        return result

    if tags.get("plan_talk") or tags.get("closure"):
        result["intent"] = COUNSELING
        result["reason"] = "Discussing the plan."
        return result
    if courtesy_ids:
        result["intent"] = COURTESY
        result["reason"] = "A courtesy or technique statement."
        return result

    # An exam verb with no actor at all -- "palpate abdomen" as a bare note.
    # Treat it as an action: it is how the action panel and terse narration
    # read, and there is no other plausible reading.
    if verbs:
        result["intent"] = ACTION
        result["may_examine"] = True
        result["reason"] = "Read as an examination instruction."
        return result

    result["intent"] = QUESTION
    result["reason"] = "Addressed to the patient."
    return result


def describes_absence(text: str) -> bool:
    """True when the learner is reporting that something is NOT available.

    Used to stop "I have no hand sanitizer available" awarding hand hygiene.
    """
    t = nlp.normalize(text or "")
    return _has(t, _ABSENCE_FRAMES) or _has(t, [
        "no hand sanitizer", "no gloves", "no soap", "no drape", "no gown",
        "without washing", "without gloves", "did not wash", "didn't wash",
        "didnt wash", "forgot to wash", "forgot to", "no sink",
    ])


def courtesy_is_negated(text: str, trigger: str) -> bool:
    """Does the utterance negate the courtesy its trigger words matched?"""
    t = nlp.normalize(text or "")
    trig = nlp.normalize(trigger or "")
    if not trig:
        return False
    pos = t.find(trig)
    if pos < 0:
        return False
    return describes_absence(text) or _negation_reaches(t, pos)
