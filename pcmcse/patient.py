"""The standardized patient.

Scripted, not generative -- which is how real standardized patients work.  The
case file is the single source of truth for what this person knows, and the
engine's job is to decide *whether a question earns a given fact*, never to
invent one.

Behaviour rules, and where they come from:

  * the opening statement is delivered verbatim when the student invites the
    story (ASPE / Vanderbilt SP handbook practice)
  * facts are released only in response to a question that reaches them
  * the question may be asked in ordinary English: a case file's triggers are
    literal phrases, so a paraphrase layer keyed to the fact CATEGORIES every
    case uses ("what eases the pain?" -> the alleviating fact) sits behind them
  * the conversation has a memory: the topic and the referents of the last turn
    are kept, so "did that help?" and "how about at night?" resolve against
    what was just discussed instead of falling through to a non-answer
  * a summary is answered on its CONTENT: a wrong age, a wrong timeline or a
    symptom she reported and the student denied all draw a correction, and a
    summary that says nothing is not confirmed
  * a proposed medication she is allergic to is recognized, and she says so
  * a small, capped amount of natural volunteering happens, so the patient
    does not read out the checklist
  * a topic revisited gives the same answer
  * an unmatched question produces a real non-answer -- and crucially, a
    non-answer is *not* a negative: nothing enters the evidence ledger
  * diagnostic labels, hidden findings, scoring criteria and coaching never
    appear in anything the patient says

Everything the patient says is assembled from the case file's own words.  No
branch in this module writes a symptom, a medication, a result or a piece of
history that the case does not already carry.
"""

from __future__ import annotations

import random
import re

from . import dialogue, lexicon, nlp
from . import physexam as _physexam

_ANYTHING_ELSE = [
    "anything else", "anything more", "is there anything", "something else",
    "other symptoms", "any other", "anything i missed", "anything you",
    "what else",
]

_EMPATHY_CUES = [
    "that must", "i'm sorry", "im sorry", "sounds difficult", "sounds hard",
    "that sounds", "i can imagine", "i understand", "must be frustrating",
    "must be scary", "must be worrying", "thank you for sharing",
    "i appreciate you", "that's a lot", "thats a lot",
]

_SUMMARY_CUES = [
    "let me make sure i have this", "so what i'm hearing", "so what im hearing",
    "let me summarize", "let me summarise", "to recap", "so to review",
    "if i understand correctly", "let me repeat back", "so you're telling me",
    "so youre telling me", "just to summarize", "let me see if i got",
]

_CLOSURE_CUES = [
    "any questions", "questions for me", "any concerns", "anything you'd like to ask",
    "anything you would like to ask", "any comments", "does that make sense",
    "is there anything you're worried", "what questions do you have",
    "anything else you want to ask", "any other concerns",
]

_TRANSITION_CUES = [
    "now i'm going to ask", "now im going to ask", "i'd like to ask you about",
    "id like to ask you about", "next i'll ask", "next ill ask",
    "switching gears", "moving on to", "now let's talk about",
    "now lets talk about", "i want to ask about", "let me ask you about",
    "i'm going to change", "im going to change",
]

# Two different situations, and running them together wasted the learner's
# clock. "Could you say that another way?" tells the learner they were unclear,
# which is right when the wording really was hard to follow -- and wrong, and
# expensive, when the question was perfectly clear and this case simply has no
# fact for it. In that second case the patient answers the way a standardized
# patient does: she declines to add anything, without inventing a symptom or a
# denial, and without sending the learner off to rephrase a good question.
_NON_ANSWERS = [
    "I'm sorry — I'm not sure what you mean.",
    "Could you say that another way?",
    "Hmm... I don't know how to answer that.",
    "I'm not sure. What do you mean exactly?",
]

_NOTHING_TO_ADD = [
    "I don't really have anything to tell you about that.",
    "Nothing comes to mind about that, sorry.",
    "I haven't noticed anything either way there.",
    "That one I couldn't say.",
]

# Ordinary question words a learner uses that need not appear in any trigger
# list. They give typo repair something correct to aim at.
_COMMON_QUESTION_WORDS = {
    "what", "when", "where", "which", "who", "why", "how", "does", "did", "do",
    "have", "has", "had", "are", "is", "was", "were", "can", "could", "would",
    "any", "anything", "tell", "describe", "your", "you", "the", "pain", "hurt",
    "hurts", "symptom", "symptoms", "feel", "feels", "start", "started", "begin",
    "began", "long", "bad", "worse", "better", "else", "there", "about", "take",
    "taking", "medication", "medications", "allergy", "allergies", "family",
    "surgery", "surgeries", "smoke", "drink", "drugs", "name", "old", "age",
    "spread", "radiate", "move", "often", "constant", "before", "again",
}

_REPEAT_PREFIXES = [
    "Like I said, ", "As I mentioned, ", "Right, ", "",
]

# A request to hear the last answer again.  Repeating what she already said is
# the honest reply; falling through to the matcher would answer a different
# question, or produce a non-answer to a perfectly ordinary human request.
_REPEAT_REQUESTS = [
    "say that again", "repeat that", "could you repeat", "can you repeat",
    "one more time", "didn't catch", "didnt catch", "come again",
    "what was that", "what did you say", "sorry what", "say it again",
    "i missed that", "could you say that again",
]

# The student is stating a plan, not asking a question.  These are the phrases
# that PROPOSE a drug; a proposal is answered as a proposal, because reading
# "I'm going to start you on amoxicillin" as a question about onset (it
# contains the word "start") tells the learner something they never asked.
_PRESCRIBING_CUES = [
    "start you on", "starting you on", "put you on", "putting you on",
    "prescribe", "prescribing", "treat you with", "treating you with",
    "give you a prescription", "we'll give you", "we will give you",
    "i'm going to give you", "im going to give you", "write you a prescription",
    "a course of", "get you started on", "started you on", "you started on",
]


# --------------------------------------------------------------------------
# The paraphrase layer
# --------------------------------------------------------------------------
# A case file's triggers are literal phrases -- precise, and narrow: "what
# eases the pain?" reaches none of the alleviating fact's triggers, and the
# learner gets "could you say that another way?" for an ordinary English
# question.  This table is the paraphrase layer.  It is keyed to the fact
# CATEGORIES the case files already share, so it carries no case content and
# works for every case; it only ever SELECTS a scripted fact, never writes one.
#
# It runs as a fallback, after the case's own triggers have been given the
# first chance, so a case that words a trigger precisely still wins.

# Relief and worsening are asked with everyday verbs.  Both need a referent --
# the complaint, or a pronoun standing for it -- or "how can I help you today?"
# would be read as a question about what relieves the pain.
_RELIEF_WORDS = {
    "ease", "eases", "eased", "easing", "easier", "relieve", "relieves",
    "relieved", "relief", "relieving", "alleviate", "alleviates",
    "alleviated", "alleviating", "help", "helps", "helped", "helping",
    "better", "improve", "improves", "improved", "improving", "soothe",
    "soothes", "soothed", "lessen", "lessens", "settle", "settles",
}

_WORSE_WORDS = {
    "worse", "worsen", "worsens", "worsened", "worsening", "aggravate",
    "aggravates", "aggravated", "aggravating", "exacerbate", "exacerbates",
    "exacerbated", "flare", "flares", "trigger", "triggers", "provoke",
    "provokes", "worst",
}

_REFERENTS = {
    "it", "that", "this", "them", "those", "they", "pain", "pains", "ache",
    "aches", "aching", "hurt", "hurts", "hurting", "burning", "symptom",
    "symptoms", "discomfort", "problem", "problems", "things", "everything",
    "anything", "pressure", "tightness", "headache", "breathing", "dizziness",
}

_ASPECTS = [
    {"id": "onset", "categories": ["onset"],
     "cues": ["when did", "when do", "how long have", "how long has",
              "how long ago", "since when", "first notice", "first started",
              "first began", "when it started", "when this started",
              "how many days"]},
    {"id": "chronology", "categories": ["chronology"],
     "cues": ["getting worse", "getting better", "changed since", "progress",
              "since it started", "how has it changed", "course of it",
              "gotten worse", "gotten better", "has it changed", "changed at all", "any change", "is it changing", "getting any worse", "any different", "better or worse since", "how has it been"]},
    {"id": "location", "categories": ["location"],
     "cues": ["where is", "where does", "where do you feel", "which side",
              "what part", "point to", "show me where", "where exactly",
              "location of", "whereabouts"]},
    {"id": "radiation", "categories": ["radiation"],
     "cues": ["radiate", "spread", "travel", "move anywhere", "go anywhere",
              "shoot", "anywhere else"]},
    {"id": "quality", "categories": ["quality"],
     "cues": ["what does it feel like", "what is it like", "what's it like",
              "describe the pain", "describe it", "sharp or dull",
              "kind of pain", "type of pain", "how would you describe", "what is the pain like", "how would you describe it"]},
    {"id": "severity", "categories": ["severity"],
     "cues": ["how bad", "how severe", "scale of", "out of ten", "out of 10",
              "rate the pain", "rate it", "severity", "how much does it hurt",
              "how strong"]},
    {"id": "timing", "categories": ["timing"],
     "cues": ["constant", "come and go", "comes and goes", "all the time",
              "how often", "intermittent", "does it stop", "at night",
              "time of day", "certain times", "how often does it happen", "how often does this happen", "how frequently", "how many times a day", "how many times a week", "does it happen often"]},
    {"id": "alleviating", "categories": ["alleviating"],
     "words": _RELIEF_WORDS, "needs_referent": True,
     "cues": ["edge off", "any relief", "calm it down", "calms it down",
              "settle it down", "more tolerable", "more comfortable", "what helps", "what makes it better", "anything help", "does anything help", "what relieves"]},
    {"id": "aggravating", "categories": ["aggravating"],
     "words": _WORSE_WORDS, "needs_referent": True,
     "cues": ["set it off", "sets it off", "bring it on", "brings it on",
              "brings on", "act up", "acts up", "more intense",
              "flare it up", "kick it off"]},
    {"id": "treatment", "categories": ["treatment"],
     "cues": ["tried anything", "taken anything", "taken for", "done for it",
              "over the counter", "any medicine for", "remedies", "treated it",
              "anything for the pain", "anything for it", "did you take anything", "have you taken anything", "tried anything for it"]},
    {"id": "past_occurrence", "categories": ["past_occurrence"],
     "cues": ["had this before", "happened before", "ever had", "first time",
              "anything like this before", "in the past", "similar episode"]},
    {"id": "pmh", "categories": ["pmh"],
     "cues": ["medical problem", "medical condition", "medical history",
              "health problem", "diagnosed with", "chronic condition",
              "other health", "any conditions"]},
    {"id": "psh", "categories": ["psh"],
     "cues": ["surgery", "surgeries", "operation", "hospitalized",
              "been in the hospital", "any procedures"]},
    {"id": "medications", "categories": ["medications"],
     "cues": ["medication", "medicine", "meds", "prescription", "pills",
              "taking anything", "supplements", "vitamins"]},
    {"id": "allergies", "categories": ["allergies"],
     "cues": ["allerg", "nkda", "react to any"]},
    {"id": "family", "categories": ["family"],
     "cues": ["family history", "runs in the family", "your parents",
              "your mother", "your father", "your mom", "your dad",
              "siblings", "brothers or sisters", "anyone in your family", "mom or dad", "mother or father", "run in the family", "runs in the family", "runs in your family", "about your family", "family have", "anyone in your family", "parents have", "family members"]},
    {"id": "tobacco", "categories": ["social"],
     "cues": ["smoke", "smoking", "tobacco", "cigarette", "vape", "nicotine"],
     "keywords": ["smoke", "smoked", "smoking", "tobacco", "cigarette",
                  "nicotine", "vape"]},
    {"id": "alcohol", "categories": ["social"],
     "cues": ["alcohol", "drink", "beer", "wine", "liquor"],
     "keywords": ["alcohol", "drink", "drinks", "beer", "wine", "liquor"]},
    {"id": "drugs", "categories": ["social"],
     "cues": ["recreational drug", "illicit", "street drug", "marijuana",
              "cocaine", "drug use", "any drugs"],
     "keywords": ["drug", "drugs", "marijuana", "cocaine"]},
    {"id": "household", "categories": ["social"],
     "cues": ["live with", "lives with", "living with", "live at home",
              "lives at home", "at home with you", "anyone at home",
              "anyone else at home", "who lives", "who do you live",
              "live alone", "lives alone", "living alone", "living situation",
              "living arrangement", "household", "who is at home",
              "who else is at home", "home life", "at home with",
              "roommate", "housemate", "by yourself", "on your own",
              "at the house", "who else lives", "share a place",
              "share an apartment", "anyone staying with"],
     "keywords": ["live", "lives", "living", "home", "alone", "roommate",
                  "housemate", "household", "apartment"]},
    {"id": "occupation", "categories": ["social"],
     "cues": ["what do you do", "for a living", "your job", "do you work",
              "are you working", "occupation", "are you in school",
              "still in school", "are you a student", "are you employed",
              "line of work"],
     "keywords": ["work", "working", "job", "student", "school", "occupation",
                  "graduate", "teacher", "administrator"]},
    {"id": "sexual", "categories": ["social", "obgyn"],
     "cues": ["sexually active", "sexual history", "sexual partner",
              "how many partners", "condom", "protection", "intercourse",
              "sexual activity"],
     "keywords": ["sexual", "partner", "partners", "condom"]},
    {"id": "obgyn", "categories": ["obgyn"],
     "cues": ["last menstrual", "your period", "menstrual", "pregnan",
              "your cycle", "lmp"]},
    {"id": "concern", "categories": ["fife"],
     "cues": ["what are you worried", "worried about", "what do you think is",
              "your concerns", "on your mind", "afraid", "scared",
              "what do you think is causing", "hoping", "what were you hoping",
              "expectations"],
     "keywords": ["worried", "scared", "afraid", "kidney", "cancer", "heart",
                  "stroke", "thinking"]},
    {"id": "impact", "categories": ["fife"],
     "cues": ["affecting your", "impact on your life", "interfering",
              "keeping you from", "affecting your work", "getting in the way"],
     "keywords": ["exam", "work", "school", "miss", "missing", "job"]},
]

# Short turns that lean on the turn before them.  "Did that help?" and "how
# about at night?" carry no topic of their own: the topic is whatever was just
# discussed, so the matcher is re-run with the previous question appended.
_ELLIPTIC_STARTS = ("and ", "how about", "what about", "any ", "or ", "so ",
                    "okay ", "ok ", "but ")
_ANAPHORS = {"that", "it", "this", "them", "those", "they", "these"}


# --------------------------------------------------------------------------
# Drug families, for recognizing a proposed medication she cannot take
# --------------------------------------------------------------------------
# A patient with a penicillin allergy knows amoxicillin is a penicillin -- it
# is the single most common thing a real standardized patient is briefed to
# raise.  The families are general pharmacology, not case content: WHICH
# allergy this patient has, and what it did to her, is read from her own case
# file, so nothing is invented here either.
_DRUG_FAMILIES = {
    "penicillin": {
        "label": "penicillin",
        "members": ["penicillin", "penicillins", "pcn", "amoxicillin", "amox",
                    "augmentin", "amoxicillin-clavulanate", "ampicillin",
                    "dicloxacillin", "nafcillin", "oxacillin", "piperacillin",
                    "unasyn", "zosyn"],
    },
    "sulfa": {
        "label": "sulfa drug",
        "members": ["sulfa", "sulfas", "sulfonamide", "sulfonamides",
                    "bactrim", "septra", "sulfamethoxazole", "smx-tmp",
                    "tmp-smx", "trimethoprim-sulfamethoxazole",
                    "sulfasalazine", "sulfadiazine"],
    },
    "cephalosporin": {
        "label": "cephalosporin",
        "members": ["cephalosporin", "cephalosporins", "cephalexin", "keflex",
                    "cefdinir", "ceftriaxone", "rocephin", "cefazolin",
                    "cefuroxime", "cefpodoxime"],
    },
    "nsaid": {
        "label": "anti-inflammatory",
        "members": ["nsaid", "nsaids", "ibuprofen", "motrin", "advil",
                    "naproxen", "aleve", "ketorolac", "toradol", "indomethacin",
                    "aspirin"],
    },
    "fluoroquinolone": {
        "label": "quinolone",
        "members": ["fluoroquinolone", "fluoroquinolones", "ciprofloxacin",
                    "cipro", "levofloxacin", "levaquin", "moxifloxacin"],
    },
    "macrolide": {
        "label": "macrolide",
        "members": ["macrolide", "macrolides", "azithromycin", "zithromax",
                    "z-pak", "clarithromycin", "erythromycin"],
    },
    "opioid": {
        "label": "narcotic",
        "members": ["opioid", "opioids", "morphine", "codeine", "oxycodone",
                    "percocet", "hydrocodone", "norco", "vicodin", "tramadol",
                    "dilaudid", "hydromorphone"],
    },
    "statin": {
        "label": "statin",
        "members": ["statin", "statins", "atorvastatin", "lipitor",
                    "simvastatin", "rosuvastatin", "crestor", "pravastatin"],
    },
}


# --------------------------------------------------------------------------
# Reading a summary
# --------------------------------------------------------------------------
# A summary is a claim about what the patient said, so it is answered on its
# content.  Confirming an empty summary hands out credit for saying nothing,
# and confirming a wrong one teaches the learner that a mis-heard age or
# timeline is fine.

_SUMMARY_TAILS = [
    "is that right", "is that correct", "is that all correct",
    "did i get that right", "did i get all that right", "does that sound right",
    "does that sound about right", "is that accurate", "have i got that right",
    "did i miss anything", "am i right", "is that everything", "is that it",
]

# Words that belong to the ACT of summarizing rather than to its content.
# "back" is deliberately absent: in this app it is nearly always a body part.
_VERIFY_WORDS = {
    "right", "correct", "accurate", "everything", "anything", "miss",
    "missed", "summarize", "summarise", "summary", "recap", "review",
    "hearing", "heard", "telling", "told", "understand", "understood",
    "repeat", "sure", "okay", "so", "just", "again", "let",
}

_CONTENT_STOP = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "for",
    "with", "from", "about", "as", "if", "then", "than", "that", "this",
    "these", "those", "there", "here", "is", "are", "was", "were", "be",
    "been", "being", "am", "i", "you", "he", "she", "it", "we", "they", "me",
    "my", "your", "his", "her", "their", "our", "do", "does", "did", "done",
    "have", "has", "had", "having", "not", "no", "so", "what", "when",
    "where", "which", "who", "whom", "how", "why", "can", "could", "would",
    "should", "will", "shall", "may", "might", "some", "any", "all", "also",
    "more", "most", "much", "many", "very", "quite", "still", "yet", "now",
    "today", "just", "really", "okay", "ok", "yes", "yeah", "sure", "well",
    "get", "got", "give", "gave", "make", "made", "makes", "going", "go",
    "went", "come", "came", "take", "takes", "taking", "taken", "been",
    "think", "thing", "things", "other", "another", "each", "every", "own",
    "like", "into", "over", "out", "up", "down", "off", "since", "because",
    "you've", "i've", "youve", "ive", "you're", "youre", "i'm", "im",
    "let", "see", "say", "said", "tell", "told", "hear", "hearing", "heard",
}
_CONTENT_STOP |= _VERIFY_WORDS

_AGE_PATTERNS = [
    re.compile(r"\b(\d{1,3})\s*-?\s*(?:year|yr)s?\s*-?\s*old\b"),
    re.compile(r"\byou\s*'?\s*re\s+(?:a\s+|an\s+)?(\d{1,3})\b"),
    re.compile(r"\byou\s+are\s+(?:a\s+|an\s+)?(\d{1,3})\b"),
]

_NUMBER_WORDS = {
    "a": "1", "an": "1", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "couple": "2", "few": "3",
    "several": "3",
}

_TIME_EXPR = re.compile(
    r"\b(?:(?:\d{1,3}|a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|couple|few|several)\s+(?:of\s+)?"
    r"(?:hour|day|week|month|year)s?"
    r"|yesterday|last night|this morning|this afternoon|this evening|"
    r"overnight|last week|last month|last year)\b")

# Ways of saying the same interval.  Without these, an accurate summary that
# says "for a day" where the case says "yesterday" would be corrected.
_TIME_EQUIVALENTS = {
    "yesterday": "1 day", "last night": "1 day", "overnight": "1 day",
    "24 hour": "1 day", "this morning": "1 day", "48 hour": "2 day",
    "last week": "1 week", "last month": "1 month", "last year": "1 year",
    "7 day": "1 week", "12 month": "1 year", "this afternoon": "1 day",
    "this evening": "1 day",
}


_QUESTION_STOPWORDS = {
    "any", "have", "has", "had", "you", "your", "yours", "the", "a", "an",
    "do", "does", "did", "is", "are", "was", "were", "been", "being", "be",
    "with", "and", "or", "but", "for", "from", "that", "this", "these",
    "those", "there", "here", "when", "what", "where", "why", "how", "who",
    "which", "can", "could", "would", "will", "shall", "should", "may",
    "might", "tell", "me", "about", "at", "in", "on", "to", "of", "it",
    "its", "not", "no", "yes", "please", "also", "some", "much", "many",
    "been", "get", "got", "like", "feel", "feels", "having",
}


def _reads_as_a_clear_question(text):
    """Was this a well-formed question, whatever the case has to say about it?

    A short well-formed question is the learner's problem only if the case has
    an answer; otherwise the honest reading is that the topic is simply not in
    this case.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    words = _tokens(raw)
    if len(words) < 3 or len(words) > 24:
        return False
    if raw.endswith("?"):
        return True
    lead = words[0].rstrip("'s").rstrip("s") if words[0] in (
        "hows", "how's", "whats", "what's", "wheres", "where's", "whens",
        "when's", "whos", "who's", "whys", "why's") else words[0]
    return lead in ("what", "when", "where", "why", "how", "who", "which",
                    "do", "does", "did", "are", "is", "was", "were", "have",
                    "has", "had", "any", "can", "could", "would", "tell",
                    "describe")


def _tokens(text):
    """Word tokens, without the sentence punctuation normalization keeps.

    nlp.normalize() preserves "." so that doses and abbreviations survive, so
    the last word of a sentence arrives as "bactrim." -- and a drug name that
    ends a sentence would never match the family list.
    """
    return [t for t in (w.strip(".'") for w in nlp.normalize(text).split()) if t]


def _content_tokens(text):
    """The words that carry meaning, for comparing a claim with the record."""
    return [t for t in _tokens(text)
            if len(t) >= 4 and t not in _CONTENT_STOP]


def _same_word(a, b):
    """True for two surface forms of the same word ("urinate" / "urinates")."""
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    return a.startswith(b) or b.startswith(a)


def _overlap(tokens, vocabulary):
    """How many of `tokens` the record already contains, in some form."""
    hits = 0
    for t in tokens:
        if any(_same_word(t, v) for v in vocabulary):
            hits += 1
    return hits


# "a few days" and "several weeks" name no particular number, so they cannot
# be checked against the record: she would be correcting "a few days ago" to
# "two days ago", which is not a correction a person makes.
_VAGUE_QUANTITIES = {"few", "several", "number"}


def _canonical_time(expr):
    """"about three weeks" and "3 weeks" are the same interval.

    Returns None for an interval too vague to be right or wrong.
    """
    expr = nlp.normalize(expr)
    if expr in _TIME_EQUIVALENTS:
        return _TIME_EQUIVALENTS[expr]
    parts = [p for p in expr.split() if p != "of"]
    if parts and parts[0] in _VAGUE_QUANTITIES:
        return None
    if len(parts) == 2:
        number, unit = parts
        number = _NUMBER_WORDS.get(number, number)
        unit = unit[:-1] if unit.endswith("s") else unit
        canonical = "%s %s" % (number, unit)
        return _TIME_EQUIVALENTS.get(canonical, canonical)
    return expr


def _time_expressions(text):
    """Every interval a passage names, canonicalized, ages excluded."""
    norm = nlp.normalize(text)
    out = []
    for m in _TIME_EXPR.finditer(norm):
        tail = norm[m.end():m.end() + 5]
        # "52 year old" is an age, not a duration.
        if tail.lstrip(" -").startswith("old"):
            continue
        canonical = _canonical_time(m.group(0))
        if canonical:
            out.append(canonical)
    return out


def examination_consent_request(text):
    """Recognize explicit permission to examine, not words in symptom history."""
    q=nlp.normalize(text)
    return bool(re.search(r"\b(?:do i have|may i have|can i have) your (?:permission|consent) to (?:examine you|perform (?:a |the )?(?:physical )?exam)",q))


def question_clauses(question):
    """Split explicit question clauses, preserving symptom lists and comparisons."""
    starters=r'(?:is|are|do|does|did|have|has|when|where|what|how|can|could|any)\b'
    return [part.strip() for part in re.split(r'[?;]|,\s*(?='+starters+r')|,?\s+and\s+(?='+starters+r')',question,flags=re.I) if part.strip()]


def temporal_question_dimensions(question):
    """Explicit temporal requests; progression never stands in for constancy."""
    q=nlp.normalize(question);dims=set()
    if re.search(r'constant|continuous|come and go|comes and goes|intermittent|all the time|(?:has|does|did).*stop|(?:has|have).*let up|between.*(?:spell|episode|wave|bowel movement)|feel well between|settle after|every urination',q):dims.add('constancy')
    if re.search(r'how (?:often|frequent)|how many times|frequency',q):dims.add('frequency')
    clauses=question_clauses(q)
    for clause in clauses:
        present_time=re.search(r'\bnow\b|at this moment|currently|(?:while|as) we (?:talk|speak)|still (?:having|hurting|feeling|experiencing)',clause)
        # Time is an adverb on an explicit attribute/history question, not a
        # request to replace that attribute with symptom presence or constancy.
        attribute=re.search(r'\bwhere\b|how (?:bad|severe|long|often)|severity|(?:rate|score).*pain|out of ten|what.*(?:feel like|quality)|when.*(?:start|began|begin)|medicin|medication|prescription|supplement|allerg|family|mother|father',clause)
        if present_time and not attribute:dims.add('current_status')
    if re.search(r'last (?:completely )?(?:normal|well)|last known well|last (?:felt|seen|feeling) (?:normal|well)',q):dims.add('last_known_well')
    if re.search(r'how.*changed|changed (?:since|over|through)|progression|getting (?:worse|better)|(?:has|have).*improved|spread.*how often',q):dims.add('progression')
    if re.search(r'(?:taking|take|medication|medicine|treatment|tablet|dose).*(?:help|improv)|(?:help|improv).*(?:taking|medication|medicine|treatment|dose)',q):dims.discard('progression')
    return dims


def authored_temporal_dimensions(fact):
    """Only authored metadata confers a temporal meaning on a history fact."""
    dims=set(fact.get('question_dimensions',[]))
    role=fact.get('temporal_role')
    if role in ('constancy','progression','frequency','last_known_well'):dims.add(role)
    if role in ('episode_duration','prior_episode_duration'):dims.add('duration')
    if role=='attack_frequency':dims.add('frequency')
    if fact.get('category')=='chronology' and not dims:dims.add('progression')
    return dims


def compound_history_domains(question):
    q=nlp.normalize(question)
    domains=[name for name,pattern in [('medications',r'medicin|medication|prescription|supplement|\bmeds\b'),('allergies',r'allerg|reaction.*(?:drug|medic)')] if re.search(pattern,q)]
    if 'allergies' in domains and 'medications' in domains:
        modifier=re.search(r'(?:medication|medicine|drug)\s+allerg|allerg.*(?:to|from).*(?:medic|drug)',q)
        separate_med_question=re.search(r'(?:what|which).*?(?:medicin|medication|meds)|(?:medicin|medication|meds).*?(?:take|taking)|(?:take|taking).*?(?:medicin|medication|meds)',q)
        if modifier and not separate_med_question:domains.remove('medications')
    return domains


def current_status_subject_matches(fact, clause):
    """A present-state question cannot borrow a different symptom's status."""
    if fact.get('current_status_condition')=='head_still' and not re.search(r'(?:head|sitting|sit|keeping).*still|sitting quietly|between.*(?:spell|episode)',clause,re.I):return False
    from_question=[name for name,pattern in [('vertigo',r'vertigo|dizz|spinning'),('abdominal_pain',r'abdom|stomach|belly'),('chest_pain',r'chest.*(?:pain|pressure)'),('headache',r'headache|head pain'),('back_pain',r'back.*pain|flank.*pain'),('urinary',r'urin|pee|bladder'),('weakness',r'weak|write'),('palpitations',r'palpitat|heart.*(?:rac|flutter)'),('breathing',r'breath|dyspnea')] if re.search(pattern,clause,re.I)]
    if from_question:return bool(set(from_question)&set(fact.get('current_status_subjects',[])))
    if re.search(r'\bpain\b|\bache\b',clause,re.I):return bool(set(fact.get('current_status_subjects',[]))&{'abdominal_pain','chest_pain','headache','back_pain'})
    return True

# Narrow language equivalences for history actually requested by the learner.
# Topic names select authored facts; they never supply clinical answers.
def _instruction_or_other_person(text):
    q=nlp.normalize(text)
    return bool(re.search(r"\b(?:do not|don't|dont|not asking|not to|phrase|quoted?|hidden findings|answer key|diagnosis)\b|\b(?:mother|father|family|partner|someone|somebody|friend|child|sister|brother)\b|\b(?:cause|caused|causes|medication|medicine|drug)\b",q) or re.search(r'["“”]|(?:^|\s)[‘\'][^‘\']+[’\'](?:$|\s|[.!?])',str(text)))


def opening_invitation(question, patient_name=''):
    """Accept a whole invitation clause, including a bounded known-name greeting."""
    if _instruction_or_other_person(question):return False
    names=[nlp.normalize(patient_name)]+nlp.normalize(patient_name).split()
    greeting=r'^(?:hello|hi|good morning|good afternoon|good evening)(?: (?:'+('|'.join(re.escape(n) for n in names if n) or r'(?!)')+r'))?\b\s*'
    parts=[]
    for raw in re.split(r'[.!?;]|,\s*(?=(?:is|are|do|does|did|have|has|when|where|what|how|can|could|would|please|tell|my|i)\b)',question,flags=re.I):
        q=nlp.normalize(raw).strip(' .')
        q=re.sub(greeting,'',q).strip()
        if not q:continue
        if re.fullmatch(r"(?:my name is [a-z]+(?: [a-z]+)?|(?:i'm|im|i am) (?:(?:[a-z]+,? )?(?:the |a |your )?)?(?:(?:first|second|third|fourth|1st|2nd|3rd|4th)[ -]year )?(?:medical )?student(?: doctor| clinician)?(?: working with you(?: today)?)?)",q):continue
        q=re.sub(r'^(?:(?:can|could|would) you (?:please )?|please )','',q)
        q=re.sub(r'^tell me(?: in your own words)? (?=what\b|why\b|how\b)','',q)
        parts.append(q)
    if len(parts)!=1:return False
    q=parts[0]
    tail=r'(?: today| right now| most| today most| most today)?'
    forms=[r"what(?: is|'s|s) (?:bothering you|troubling you|going on|the problem)"+tail,
           r'what (?:bothers|troubles) you'+tail,
           r'what seems to be (?:bothering you|troubling you|the problem)'+tail,
           r'what (?:brings|brought) you(?: in| here| to (?:the |this )?(?:office|clinic|hospital|doctor))?'+tail,
           r'(?:how can i help(?: you)?|what can i do for you|why are you here)'+tail,
           r"tell me about (?:what (?:brings|brought) you(?: in| here)?|what(?: is|'s|s) going on|your (?:symptoms|concerns|problem)|the problem)"+tail,
           r'(?:tell me more|go on|say more|in your own words|start from the beginning|walk me through what happened|reason for your visit|what happened today|what happened)',
           # Ordinary ways the same invitation gets said. These are additional
           # WORDINGS of "what brings you in", not new meanings: each still has
           # to be the whole clause, so a specific question is unaffected.
           r'what can i help(?: you)?(?: with)?'+tail,
           r'(?:what|how) can i help you with'+tail,
           r'why (?:did|do) you come(?: in| here)?'+tail,
           r'why (?:did|do) you decide to come(?: in| here)?'+tail,
           r'what (?:made|makes) you (?:come|decide to come)(?: in| here)?'+tail,
           r'what are you here for'+tail,
           r'what brings you to (?:the |this )?(?:er|ed|emergency (?:room|department)|urgent care|appointment|visit)'+tail,
           r'(?:whats|what is) the (?:reason|problem)(?: for (?:your |this )?visit)?'+tail,
           r'what(?: is|\'s|s) (?:been )?(?:going on|happening|the matter|wrong)(?: with you)?'+tail,
           r'(?:tell me|so tell me) what happened'+tail,
           r'what seems to be (?:wrong|the matter|the issue)'+tail,
           r'how (?:are you|can we help)(?: doing)?'+tail,
           r'what brings you'+tail,
           r'(?:whats|what is) (?:the )?(?:trouble|concern)'+tail,
           r"what(?: is|'s|s) (?:been )?bothering you"+tail,
           r'why (?:are|r|you are) you? ?here'+tail,
           r'why you are here'+tail]
    forms.append(r'tell me about (?:your|the|this) (?:pain(?: under (?:your|the) (?:right |left )?ribs)?|chest (?:pain|pressure)|dizziness|headache|breathing|shortness of breath|back pain|urinary symptoms|difficulty (?:swallowing|urinating)|palpitations|numbness|weakness|diarrhea)'+tail)
    return any(re.fullmatch(pattern,q) for pattern in forms)


_FOCUSED_FACT_IDS={
    'syncope':('symptom_syncope','brief_loc'),
    'presyncope':('symptom_presyncope','assoc_lightheaded','brief_loc'),
    'leg_weakness':('symptom_leg_weakness','symptom_weakness'),
    'saddle_numbness':('symptom_saddle_numbness',),
}
_FOCUSED_PATTERNS={
    'syncope':r'(?:(?:actually|ever) )*(?:(?:lose|lost|loss of) consciousness|(?:pass|passed|passing|black|blacked|blacking) out|faint(?:ed|ing)?|syncope)(?: with this| before| recently| at all)?',
    'presyncope':r'(?:(?:feel|felt|feeling) )?(?:lightheaded|faint|faint feeling)|(?:(?:feel|felt|feeling) )?(?:as if|as though|like)(?: you)?(?: might| may| could)? (?:faint|pass out|black out|lose consciousness)|(?:almost|nearly) (?:fainted|passed out|lost consciousness)',
    'leg_weakness':r'(?:leg|lower limb) weakness|weakness (?:in|of) (?:(?:your|the|both) )?(?:legs|lower limbs)|(?:(?:your|both|the) )?(?:legs|lower limbs) (?:(?:feel|felt|feeling|are|were|became|become) )?(?:weak|weaker)(?: than usual)?',
    'saddle_numbness':r'saddle (?:numbness|sensory loss)|(?:numbness|loss of sensation|reduced sensation|less feeling) (?:in|around|over) (?:(?:your|the) )?(?:groin|perineum|perineal area|saddle area)|(?:numbness|loss of sensation|reduced sensation) between (?:(?:your|the) )?legs|(?:(?:your|the) )?(?:groin|perineum|area between your legs) (?:(?:feels?|is) )?numb',
}

def exact_authored_compound_history(case, question):
    """Legacy bundled negatives require their entire authored multi-topic ask.

    A single fainting question cannot release every cardiac negative. The
    exact, reviewed compound example explicitly requests the whole bundle.
    """
    if _instruction_or_other_person(question):return []
    q=nlp.normalize(question).strip(' .')
    return [f for f in case.get('facts',[]) if f.get('category')=='pertinent_negative' and len(f.get('concepts',{}))>1
            and any(q==nlp.normalize(example).strip(' .') for example in f.get('example_questions',[]))]


def position_history_fact_topics(fact):
    topics=fact.get('position_history_topics',[])
    if topics:return topics
    # Original melena authoring already states this exact standing relationship;
    # route it without rewriting the case or asserting actual loss of awareness.
    if fact.get('id')=='assoc_lightheaded' and 'When I stand up fast I get a bit swimmy-headed.' in fact.get('sp_says',[]):return ['standing_trigger']
    return []


def posture_history_topics(question):
    """A symptom's standing trigger versus settling at rest, not an exam order.

    The recognized positions select metadata on authored history facts. Nothing
    in this grammar asserts orthostasis, syncope, or any measured response.
    """
    q=nlp.normalize(question).strip(' .')
    if not re.search(r'\bstand(?:ing)?|getting up|\bsit(?:ting)?|\bseated|\blying',q):return None
    stem=r'(?:(?:does|did) (?:it|this|that|(?:the |your )?(?:lightheadedness|dizziness|symptoms|faint feeling)) (?:happen|occur|start|come on)|do you (?:get|feel|become) (?:dizzy|lightheaded|faint)) '
    direct=q
    q=re.sub(r'^(?:can|could) you tell me (?:if|whether) ','',q)
    if q!=direct:
        q=re.sub(r'^(it|this|that) (happens|occurs|starts) ',lambda m:'does '+m.group(1)+' '+m.group(2)[:-1]+' ',q)
    match=re.fullmatch(stem+r'(.+)',q)
    if not match:return None
    if _instruction_or_other_person(question):return []
    topics=[]
    for component in re.split(r'\s+(?:or|and)\s+',match.group(1)):
        component=re.sub(r'^(?:even |only )+','',component)
        if re.fullmatch(r'(?:when|after|as) (?:you )?(?:stand(?: up)?|get up|rise|standing(?: up)?|getting up)',component):topic='standing_trigger'
        elif re.fullmatch(r'(?:while|when) (?:(?:you are|you\x27re|you|already) )?(?:sitting(?: down)?|seated|sit(?: down)?|lying(?: down)?)',component):topic='settles_at_rest'
        else:return []
        if topic not in topics:topics.append(topic)
    return topics


def focused_history_topics(question):
    """Actual loss of consciousness and two region-specific symptom questions.

    None means another route owns the turn; [] blocks unsupported equivalence.
    Full components prevent an unrelated symptom or attribute borrowing credit.
    """
    q=nlp.normalize(question).strip(' .')
    relevant=re.search(r'\bfaint(?:ed|ing)?\b|\b(?:pass|passed|passing|black|blacked|blacking) out\b|consciousness|\bsyncope\b|(?:weak|numb|sensation).*(?:legs?|lower limbs?|groin|perine|saddle)|(?:legs?|lower limbs?|groin|perine|saddle).*(?:weak|numb|sensation)',q)
    if not relevant:return None
    if _instruction_or_other_person(question):return []
    # A differential/proposed mechanism is not this patient's episode history.
    if re.search(r'could this be|might this be|is this|what if|\bwould\b',q):return []
    clauses=question_clauses(question);topics=[]
    for clause in clauses:
        c=nlp.normalize(clause).strip(' .')
        c=re.sub(r'^(?:can|could) you tell me (?:if|whether|about) (?:you )?','',c)
        c=re.sub(r'^(?:(?:do|did|have|had|are|were) you(?: (?:have|had|notice|noticed|experience|experienced|been having))?|any|what about)\s+','',c)
        c=re.sub(r'^(?:do|does|are|is) (?=your (?:legs|lower limbs|groin|perineum))','',c)
        c=re.sub(r'\s+or when wiping$','',c)
        # "or" between two actual-LOC synonyms remains one topic; between
        # weakness and saddle sensation it names exactly two requested facts.
        for component in re.split(r'\s+(?:or|and)\s+',c):
            component=re.sub(r'^(?:(?:any|new|recent|also) )+','',component).strip()
            found=[name for name,pattern in _FOCUSED_PATTERNS.items() if re.fullmatch(pattern,component)]
            if 'syncope' in found and component=='faint' and re.search(r'\bfeel',c):found=['presyncope']
            if not found:return []
            # A bare faint after a question lead asks whether it occurred.
            topic='syncope' if 'syncope' in found else found[0]
            if topic not in topics:topics.append(topic)
    return topics


def focused_fact_ids(question):
    topics=focused_history_topics(question)
    return None if topics is None else {fid for topic in topics for fid in _FOCUSED_FACT_IDS[topic]}


def regional_fact_allowed(fact,question):
    """A broad trigger cannot transfer leg/saddle history to another region."""
    q=nlp.normalize(question);fid=fact.get('id')
    if position_history_fact_topics(fact) and re.search(r'\bstand(?:ing)?|getting up|\bsit(?:ting)?|\bseated|\blying',q):
        positions=posture_history_topics(question)
        if positions is not None and not set(positions)&set(position_history_fact_topics(fact)):return False
        if _instruction_or_other_person(question) or re.search(r'chest pain|chest pressure|headache|abdominal pain|back pain|\b(?:will|going to) (?:check|measure)|blood pressure|orthostatic vitals',q):return False
    if fact.get('requires_current_status_question'):
        if _instruction_or_other_person(question) or 'current_status' not in temporal_question_dimensions(question):return False
        if not current_status_subject_matches(fact,question):return False
    if fid in ('symptom_leg_weakness','symptom_weakness') and re.search(r'\b(?:arms?|hands?|fingers?|face|upper limbs?)\b',q) and not re.search(r'\b(?:legs?|lower limbs?|feet)\b',q):return False
    if fid=='symptom_saddle_numbness':
        return bool(re.search(r'saddle|perine|between (?:your |the )?legs|groin',q) and re.search(r'numb|sensation|sensory|(?:less|reduced|lost|loss of) feeling|wiping',q))
    return True


def delivered_fact_metadata(fact, text):
    """Authorize metadata only for a complete approved speech version.

    Unknown legacy definitions may still be spoken, but cannot grant their
    richer hidden fact/concept/checklist IDs merely because the words differ.
    """
    normalized=nlp.normalize(text).strip()
    versions=fact.get('delivery_contract',{}).get('versions',[])
    for version in versions:
        spoken=nlp.normalize(version.get('text','')).strip()
        if spoken and re.search(r'(?<!\w)'+re.escape(spoken)+r'(?!\w)',normalized):
            return {'facts_released':[fact['id']] if version.get('complete_fact') else [],
                    'concepts':{cid:dict(spec,value=version['text']) for cid,spec in version.get('concepts',{}).items()},
                    'checklist_hits':[fact['checklist']] if version.get('complete_fact') and fact.get('checklist') else []}
    return {'facts_released':[],'concepts':{},'checklist_hits':[]}



def identity_fields(utterance):
    """Identity requests use supplied demographics, never lexical fact guesses."""
    text=nlp.normalize(utterance)
    name=bool(re.search(r"\b(?:your (?:full )?name|what (?:should|can|may) i call you|what would you like me to call you)\b",text))
    age=bool(re.search(r"\b(?:how old are you|your age|name and age|name and your age)\b",text))
    return name,age


def courtesy_statement(utterance):
    """Is this turn a bedside courtesy rather than a request for history?

    Uses the SAME trigger vocabulary the encounter engine credits courtesy
    with, so the two cannot disagree about what a courtesy is.

    A courtesy that also names a clinical topic ("are you comfortable, and when
    did the pain start?") is NOT pure courtesy: the question deserves its
    answer, and segmentation handles the compound.
    """
    text = nlp.normalize(utterance)
    if not text:
        return None
    hit = None
    for entry in _physexam.COURTESY:
        for trigger in entry["triggers"]:
            if nlp.normalize(trigger) in text:
                hit = entry
                break
        if hit:
            break
    if not hit:
        return None
    # Strip the courtesy wording, then see whether a clinical topic remains.
    remainder = text
    for trigger in hit["triggers"]:
        remainder = remainder.replace(nlp.normalize(trigger), " ")
    subjects = [t for t in dialogue.topics_in(remainder)
                if t not in ("name", "age", "sex")]
    return None if subjects else hit["id"]

def conversation_route(utterance):
    """High-confidence conversational acts take priority over keyword matching."""
    text=nlp.normalize(utterance)
    if any(identity_fields(utterance)):return 'identity'
    if re.search(r"\b(?:how do you know (?:it'?s|this is|that it|you have|that you have)|who diagnosed (?:this|the current)|why do you (?:think|say) (?:it'?s|this is)|how (?:can|could) you know (?:it'?s|this is))\b",text):
        return 'diagnostic_uncertainty'
    if re.search(r"\bwhat were you (?:doing|up to)|\bwhat (?:activity|were you doing).*?(?:start|began|onset)",text):
        return 'onset_activity'
    introduction=re.search(r"\b(?:hello|hi|good morning|good afternoon|good evening|i am (?:a |your )?(?:student|medical)|i'?m (?:a |your )?(?:student|medical))\b",text)
    question=re.search(r"\b(?:what|when|where|how|why|have you|do you|did you|are you|could you|can you|tell me|brings you)\b",text)
    if introduction and not question:return 'introduction'
    return None


class PatientEngine:
    def __init__(self, case: dict, rng=None):
        self.case = case
        self.rng = rng or random.Random(case.get("id", "case"))
        self.facts = {f["id"]: f for f in case.get("facts", [])}

    # ------------------------------------------------------------------
    def opening(self):
        return self.case["patient"]["opening"]

    # ------------------------------------------------------------------
    def respond(self, utterance: str, state: dict):
        """Return (reply_text, meta).

        `state` carries per-encounter memory:
          released:      [fact_id]
          open_budget:   int  -- how much unprompted volunteering is left
          opened:        bool -- has the opening statement been given
          asked_counts:  {fact_id: n}
          last_question: str  -- the turn a short follow-up refers back to
          last_reply:    str  -- what she last said, for "say that again"
        """
        state.setdefault("released", [])
        state.setdefault("open_budget", self.case["patient"].get("volunteer_budget", 3))
        state.setdefault("opened", False)
        state.setdefault("asked_counts", {})
        state.setdefault("denied", [])
        state.setdefault("last_question", "")
        state.setdefault("last_reply", "")
        state.setdefault("last_subjects", [])
        state.setdefault("pending_question", None)
        state["turn"] = state.get("turn", 0) + 1
        state.setdefault("last_facts", [])

        # Leading discourse markers block exact-form matching ("so what's been
        # bothering you"), but some whole-turn cues BEGIN with one: "so what
        # I'm hearing is..." is a summary, and stripping its "so" turns a
        # confirmation into a fresh question. Keep the turn intact when the
        # original wording already matches such a cue.
        original = nlp.normalize(utterance)
        if not any(c in original for c in _SUMMARY_CUES + _CLOSURE_CUES):
            utterance = dialogue.strip_discourse(utterance)
        text = nlp.normalize(utterance)
        # Informal forms ("fhx", "ur", "w/") were only being expanded inside
        # segmentation, so a one-part turn never saw them. Expand here too,
        # and only keep the rewrite when it actually changes the wording.
        casual = dialogue.casual_expand(utterance)
        if casual and nlp.normalize(casual) != text:
            utterance, text = casual, nlp.normalize(casual)
        meta = {"facts_released": [], "concepts": {}, "volunteered": False,
                "kind": "answer"}

        if not text:
            # Punctuation or an emoji alone normalizes to nothing, but the
            # learner did type something and a silent patient reads as a bug.
            # Truly empty input still returns silence.
            if utterance and utterance.strip():
                meta["kind"] = "non_answer"
                meta["no_information"] = True
                return self.rng.choice(_NON_ANSWERS), meta
            return "", meta

        reply = self._respond_inner(utterance, text, state, meta)

        # Last resort: a turn that reached nothing may simply be mistyped.
        # Retrying a typo-repaired copy can only convert a miss into a hit --
        # a turn that already matched never gets here.
        # Only a genuine "I did not recognize that" is retried. Several routes
        # set no_information deliberately -- a diagnostic-certainty challenge,
        # an unscripted topic -- and re-running those with a repaired copy
        # would replace a correct refusal with an unrelated clinical fact.
        if meta.get("kind") == "non_answer" and not meta.get("facts_released"):
            repaired = dialogue.repair_typos(text, self._question_vocabulary())
            if repaired != text:
                retry = {"facts_released": [], "concepts": {}, "volunteered": False,
                         "kind": "answer"}
                second = self._respond_inner(repaired, nlp.normalize(repaired),
                                             state, retry)
                if second and not retry.get("no_information"):
                    meta.clear()
                    meta.update(retry)
                    reply = second

        self._remember(utterance, text, state, meta, reply)
        return reply, meta

    def _question_vocabulary(self):
        """Words this case's own triggers and example questions are made of."""
        cached = getattr(self, "_vocab_cache", None)
        if cached is not None:
            return cached
        words = set()
        for fact in self.case.get("facts", []):
            phrases = list((fact.get("triggers") or {}).get("any") or [])
            phrases += list(fact.get("example_questions") or [])
            for phrase in phrases:
                words.update(re.findall(r"[a-z]{3,}", nlp.normalize(phrase)))
        words.update(_COMMON_QUESTION_WORDS)
        self._vocab_cache = words
        return words

    # ------------------------------------------------------------------
    # Multi-intent composition
    # ------------------------------------------------------------------
    # A turn that asks several things gets each of them resolved through the
    # single-ask chain below, then merged in the order they were asked. The
    # composed reply is used ONLY when it answers more than the single-ask path
    # would have, so this can add answers but never take one away.

    # Whole-turn routes that must see the complete utterance. Splitting a
    # summary or an authored bundled question would change what it means.
    def _claims_whole_turn(self, utterance, text):
        # Same gates the routes themselves use. `_summary_clauses` is only a
        # splitter and fires on any input, so it must not be used as a test.
        if any(c in text for c in _SUMMARY_CUES):
            return True
        if any(c in text for c in _CLOSURE_CUES):
            return True
        # An opening invitation is defined over the WHOLE turn, greeting and
        # self-introduction included: "Hello, my name is Sam. I'm a student
        # doctor. What brings you in?" is one invitation, not three asks.
        # Splitting it would release more than the authorized opening.
        if self._is_open_invitation(utterance):
            return True
        # These conversational acts are defined over the WHOLE turn. "You just
        # said pneumonia. How do you know it's pneumonia?" is one challenge,
        # not a statement plus a question, and splitting it lets the first half
        # reach a clinical fact. `identity` is deliberately absent: "what is
        # your name and what brings you in?" must still compose.
        if conversation_route(utterance) in ('introduction', 'diagnostic_uncertainty', 'onset_activity'):
            return True
        # An authored example question is a unit the case author declared.
        # "Have you had any surgeries or hospital admissions?" is written once
        # and deliberately releases BOTH surgical facts; splitting it on "or"
        # answers half of it and drops the other authored fact.
        asked = text.strip(' .?')
        for fact in self.case.get('facts', []):
            for example in fact.get('example_questions', []) or []:
                if nlp.normalize(example).strip(' .?') == asked:
                    return True
        if exact_authored_compound_history(self.case, utterance):
            return True
        if examination_consent_request(text):
            return True
        if posture_history_topics(utterance) is not None:
            return True
        if focused_history_topics(utterance) is not None:
            return True
        for pair in self.case.get('patient', {}).get('education_responses', []):
            if nlp.normalize(pair['student']).strip(' .?') == text.strip(' .?'):
                return True
        return False

    @staticmethod
    def _informative(part, sub):
        """Did this segment actually answer, rather than decline?"""
        if not part or not part.strip():
            return False
        if sub.get('no_information'):
            return False
        return bool(sub.get('facts_released') or sub.get('concepts')
                    or sub.get('kind') in ('identity_response', 'opening', 'answer',
                                           'repeat', 'volunteered', 'consent',
                                           'education_response',
                                           # Acknowledging the patient's own
                                           # question is a real contribution
                                           # even though it releases no fact.
                                           'concern_acknowledged'))

    def _respond_inner(self, utterance, text, state, meta):
        segments = dialogue.segment(utterance)
        if len(segments) < 2 or self._claims_whole_turn(utterance, text):
            return self._resolve_single(utterance, text, state, meta)

        # Resolve each ask against a private meta so one segment's outcome
        # cannot mislabel another's.
        spoken_ids, parts, subs, unanswered = set(), [], [], []
        for segment in segments:
            sub = {"facts_released": [], "concepts": {}, "volunteered": False,
                   "kind": "answer"}
            seg_text = nlp.normalize(segment)
            if not seg_text:
                continue
            try:
                part = self._resolve_single(segment, seg_text, state, sub)
            except Exception:
                # A segment is a fragment of real input; a grammar that expects
                # a whole turn may not fit it. Losing one segment must never
                # lose the turn.
                continue
            if self._informative(part, sub):
                released = [f for f in sub.get('facts_released', [])]
                if released and set(released) <= spoken_ids:
                    continue  # already said in this same breath
                spoken_ids.update(released)
                parts.append(part)
                subs.append(sub)
            else:
                unanswered.append(segment)

        # Composition earns the turn only by answering more than one thing.
        if len(parts) < 2:
            return self._resolve_single(utterance, text, state, meta)

        for sub in subs:
            for fid in sub.get('facts_released', []):
                if fid not in meta['facts_released']:
                    meta['facts_released'].append(fid)
            meta['concepts'].update(sub.get('concepts', {}))
            if sub.get('checklist_hits'):
                meta.setdefault('checklist_hits', []).extend(sub['checklist_hits'])
            if sub.get('delivery_limits'):
                meta.setdefault('delivery_limits', []).extend(sub['delivery_limits'])
            if sub.get('volunteered'):
                meta['volunteered'] = True
            if sub.get('emotion') and 'emotion' not in meta:
                meta['emotion'] = sub['emotion']
        # `kind` drives how Record files the turn (an identity answer belongs
        # in Communication, not clinical history). When every part agrees it
        # must survive composition; only a genuinely mixed turn becomes a
        # generic answer.
        kinds = {sub.get('kind') for sub in subs}
        meta['kind'] = kinds.pop() if len(kinds) == 1 else 'answer'
        meta['composed_asks'] = len(parts)
        # Some part of the turn was answered, so the turn is not a non-answer.
        # This matters beyond wording: the encounter engine REPLACES a reply
        # flagged no_information, which would throw away the answers above.
        meta.pop('no_information', None)

        reply = dialogue.join(parts)
        if unanswered:
            meta['unanswered_asks'] = unanswered
            reply = dialogue.join([reply, self._unavailable_tail(len(unanswered))])
        return reply

    # ------------------------------------------------------------------
    # Contextual follow-ups
    # ------------------------------------------------------------------
    def _fact_subjects(self, fact):
        """Which stand-alone topics a fact is about.

        The authored category and fact id decide this. Words inside the answer
        do not: "no allergies to any medicines" is allergy history, and reading
        its text would file it under medications as well.
        """
        category = fact.get('category')
        mapped = dialogue.CATEGORY_TOPIC.get(category)
        if mapped:
            return {mapped}
        topic = fact.get('history_topic') or ''
        fid = fact.get('id', '')
        for cue, name in dialogue.SOCIAL_ID_TOPIC.items():
            if cue in fid or cue in topic:
                return {name}
        return set()

    def _followup_hits(self, utterance, state):
        """Answer a bare follow-up out of the history just discussed.

        "Do you smoke?" / "How long?" must reach the smoking history. Without
        an anchor the bare attribute word "how long" matches the chief
        complaint's onset trigger, and the patient answers the wrong question
        with a real, confident, wrong fact. Restricting the candidates to the
        subject already on the table is what prevents that.

        Returns None when this is not a bare follow-up, so every other turn
        keeps its existing route.
        """
        if not dialogue.is_bare_followup(utterance):
            return None
        anchors = [s for s in (state.get('last_subjects') or [])
                   if s in dialogue.ANCHORABLE_SUBJECTS]
        if not anchors:
            return None
        candidates = [f for f in self.case.get('facts', [])
                      if self._fact_subjects(f) & set(anchors)
                      and regional_fact_allowed(f, utterance)]
        if not candidates:
            return None
        # Prefer a fact the anchoring turn did not already spend, so "how
        # much?" can add detail rather than only repeat.
        spoken = set(state.get('last_facts') or [])
        fresh = [f for f in candidates if f['id'] not in spoken]
        pool = fresh or candidates
        if len(pool) == 1:
            return [(pool[0], 3.0)]
        context = utterance + ' ' + (state.get('last_question') or '')
        scored = [(f, nlp.trigger_score(context, f.get('triggers'))) for f in pool]
        scored = [(f, s) for f, s in scored if s > 0] or [(f, 1.0) for f in pool[:1]]
        scored.sort(key=lambda x: -x[1])
        return scored[:2]

    # ------------------------------------------------------------------
    # Two-way conversation: questions the PATIENT asked
    # ------------------------------------------------------------------
    # The engine already remembered the clinician's last question. It had no
    # representation of a question the PATIENT asked, so a clinician answering
    # one ("no", to "are you going to judge me?") had no antecedent, fell
    # through every clinical matcher and reached the generic fallback. This is
    # a small explicit state record, not a dialogue framework: one open
    # question at a time, resolved once, aged out on a topic change.
    PENDING_TURNS = 3

    def _note_patient_question(self, line, fact, state):
        """Record a patient line that genuinely asks the clinician something."""
        if not dialogue.is_question_to_clinician(line):
            return
        state['pending_question'] = {
            'text': line,
            'fact_id': (fact or {}).get('id'),
            'frame': dialogue.question_frame(line),
            'asked_turn': state.get('turn', 0),
            'open': True,
        }

    def _resolve_pending_question(self, utterance, state, meta):
        """Interpret a clinician turn that answers the patient's own question.

        Returns a reply, or None when this turn is not such an answer. Nothing
        here releases a fact or touches a concept: the clinician saying "no"
        must never edit the patient's alcohol history, and an acknowledgement
        is conversational, not clinical.
        """
        pending = state.get('pending_question')
        if not pending or not pending.get('open'):
            return None
        # Age out, so an unanswered question cannot hijack the rest of the
        # encounter. The clinician moving on is a legitimate choice.
        if state.get('turn', 0) - pending.get('asked_turn', 0) > self.PENDING_TURNS:
            state['pending_question'] = None
            return None
        act = dialogue.read_act(utterance)
        if act is None:
            return None
        resolves, reassuring = dialogue.answers_question(act, pending.get('frame', 'other'))
        if not resolves:
            return None

        pending['open'] = False
        pending['resolved_turn'] = state.get('turn', 0)
        pending['reassuring'] = reassuring
        meta['kind'] = 'concern_acknowledged'
        meta['ips_signal'] = 'concern_addressed' if reassuring else 'concern_unmet'
        # Conversational reply only -- authored where the case provides one.
        pat = self.case.get('patient', {})
        if reassuring:
            if pat.get('demeanor', {}).get('version') == 'demeanor-v1':
                from .presentation import social_reply
                count = state.get('empathy_ack', 0)
                state['empathy_ack'] = count + 1
                return social_reply(self.case, 'thanks', count)
            replies = pat.get('empathy_replies') or []
            opener = self.rng.choice(['Okay. ', 'Thank you. ', ''])
            return (opener + self.rng.choice(replies)).strip() if replies else \
                self.rng.choice(['Okay. Thank you.', 'Okay, thank you for saying that.'])
        # A non-reassuring answer is acknowledged without drama and without
        # inventing a new feeling the case does not describe.
        return self.rng.choice([
            'Okay.', 'I see.', 'Alright.',
        ])

    def _elaborate(self, utterance, state, meta):
        """"Tell me more" means more about the topic just discussed.

        Falling through to the opening statement answers a question the
        learner did not ask and loses the thread they were following. This
        offers a fact related to the last one -- its authored `follow_on`
        first, then an unspoken fact of the same category -- and returns None
        when there is nothing related left, so the existing open-invitation
        and volunteer routes still handle a cold "tell me more".
        """
        if not dialogue.is_elaboration(utterance):
            return None
        recent = [self.facts[f] for f in (state.get('last_facts') or []) if f in self.facts]
        if not recent:
            return None
        anchor = recent[-1]
        follow = self.facts.get(anchor.get('follow_on') or '')
        if follow and follow['id'] not in state['released']:
            return self._say(follow, state, meta)
        # Social facts all share one category, so a same-category sibling of
        # the smoking history is the alcohol history. Where the anchor has a
        # distinct subject, siblings must share that subject instead.
        subject = self._fact_subjects(anchor)
        if anchor.get('category') in dialogue.HPI_FAMILY:
            # More about the presenting symptom means another of its
            # attributes, in the order a patient would naturally add them.
            siblings = [f for f in self.case.get('facts', [])
                        if f.get('category') in dialogue.HPI_FAMILY
                        and f['id'] not in state['released']]
        elif subject:
            siblings = [f for f in self.case.get('facts', [])
                        if self._fact_subjects(f) == subject
                        and f['id'] not in state['released']]
        else:
            siblings = [f for f in self.case.get('facts', [])
                        if f.get('category') == anchor.get('category')
                        and f['id'] not in state['released']]
        if siblings:
            return self._say(siblings[0], state, meta)
        # Nothing new about that topic. Say so plainly and stay consistent,
        # rather than changing the subject or inventing a detail.
        meta['kind'] = 'elaboration_exhausted'
        return self.rng.choice([
            "That's really all there is to it.",
            "I'm not sure what else to add about that.",
            "That's about all I can tell you on that.",
        ])

    # Pull the subject out of an authored example question, so a clarifying
    # question can name the real alternatives without inventing wording.
    _SUBJECT_OF = re.compile(
        r'^when did (?:you have )?(?:the |your |that )?(.+?)'
        r'(?:\s+(?:begin|began|start|started)\b.*|\s*\?*\s*$)', re.I)

    def _clarify_ambiguous(self, utterance, state, meta):
        """Ask which of two authored subjects a bare attribute question means.

        Some cases deliberately carry two separate onsets -- the first episode
        and the current one, the back pain and the urinary difficulty. A bare
        "how long?" with nothing to anchor it cannot be resolved, and guessing
        would state a real but wrong fact. Asking is the honest move, and the
        options come from the case's own example questions rather than from
        anything written here.
        """
        if state.get('last_subjects') or not dialogue.is_bare_followup(utterance):
            return None
        # An onset was just discussed, so the follow-up has a referent: restate
        # that same onset rather than asking which one is meant. Answering from
        # the fact keeps it consistent with what she has already said.
        recent = [self.facts[f] for f in (state.get('last_facts') or [])
                  if f in self.facts and self.facts[f].get('category') == 'onset']
        if recent:
            return self._say(recent[-1], state, meta)
        if not re.match(r'^\s*(?:how long|when|how old is it)\b', nlp.normalize(utterance)):
            return None
        subjects = []
        for fact in self.case.get('facts', []):
            if fact.get('category') != 'onset':
                continue
            for example in fact.get('example_questions', []) or []:
                match = self._SUBJECT_OF.match(example.strip())
                if match:
                    phrase = match.group(1).strip()
                    if phrase and phrase not in subjects:
                        subjects.append(phrase)
                    break
        if len(subjects) < 2:
            return None
        meta.update(kind='clarification', no_information=True)
        return "Sorry — do you mean %s, or %s?" % (subjects[0], subjects[1])

    def _unavailable_tail(self, count):
        """One collapsed note for the asks this case cannot answer.

        The wording keeps the established distinction between 'not scripted'
        and 'denied', which the record depends on, but says it once rather
        than once per unanswered ask.
        """
        subject = "that last part" if count == 1 else "the other parts"
        return ("I do not have an answer about %s in this simulated case. "
                "Please treat it as information unavailable, not as a denial." % subject)

    def _resolve_single(self, utterance, text, state, meta):
        """Resolve ONE ask through the reviewed route chain (unchanged).

        Everything below this line predates multi-intent composition and keeps
        its original behavior. `_respond_inner` now decides whether a turn is
        one ask or several; a single ask still arrives here exactly as before.
        """
        route=conversation_route(utterance)
        if route=='identity':
            name,age=identity_fields(utterance)
            pat=self.case['patient']
            meta['kind']='identity_response'
            parts=[]
            if name:parts.append("My name is %s." % pat['name'])
            if age:parts.append("I am %s years old." % pat['age'])
            return ' '.join(parts)
        if route=='introduction':
            meta['kind']='introduction_response'
            return 'Hello. Thank you for introducing yourself. I am ready to talk.'
        if route=='diagnostic_uncertainty':
            meta.update(kind='diagnostic_uncertainty',no_information=True)
            return "I do not know what is causing these symptoms. I am here to find out."
        if route=='onset_activity' and not _instruction_or_other_person(utterance):
            facts=[f for f in self.facts.values() if f.get('onset_activity') is True]
            if facts:return ' '.join(self._say(f,state,meta)for f in facts[:2])
            meta.update(kind='non_answer',no_information=True,unscripted_topic=True)
            return 'The case does not specify what I was doing at the moment it started.'
        if re.fullmatch(r'(?:may|can|could) i explain (?:the |this |a )?(?:physical )?(?:exam|examination)(?: i would like to do)?[ .?]*',text):
            meta['kind']='permission_to_explain'
            return 'Yes, please explain what you would like to do.'
        # A named history question cannot borrow a different past illness.
        named = re.search(r'\b(?:have you (?:ever )?had|any history of|previous)\s+(?:a |any )?(kidney stones?|renal stones?|gallstones?|stroke|heart attack)\b',text)
        if named and not _instruction_or_other_person(utterance):
            topic=named.group(1)
            pattern=r'(?:kidney|renal|ureteral)?\s*stones?' if 'stone' in topic and 'gall' not in topic else re.escape(topic).rstrip('s')+r's?'
            selected=[f for f in self.facts.values() if f.get('category') in ('pmh','past_occurrence') and re.search(pattern,self._fact_text(f),re.I)]
            if selected:return ' '.join(self._say(f,state,meta) for f in selected[:3])
            meta.update(kind='non_answer',no_information=True,unscripted_topic=True)
            return 'I do not have an answer about that past condition in this simulated case. Please treat it as unavailable, not as a denial.'
        if re.search(r'\bwhat (?:worries|concerns) you (?:the )?most\b|\bwhat are you (?:most )?worried about\b',text) and not _instruction_or_other_person(utterance):
            fact=self.facts.get('patient_concern')
            if fact:return self._say(fact,state,meta)
        if examination_consent_request(text):
            meta['kind']='consent'
            return self.grant_consent(state)
        comfort=self.case.get('patient',{}).get('comfort_response')
        if comfort and any(c in text for c in ('are you comfortable','is this comfortable','am i hurting you','let me know if this hurts')):
            reply,behavior=self.behavior_response(comfort,state)
            meta.update(behavior)
            return reply
        for pair in self.case.get('patient',{}).get('education_responses',[]):
            if nlp.normalize(pair['student']).strip(' .?') == text.strip(' .?'):
                meta['kind']='education_response'
                return pair['patient']
        # Authored single-fact example questions are an explicit disclosure route.
        # Ambiguous shared prompts still use the contextual matcher below.
        exact = [f for f in self.facts.values() if any(nlp.normalize(q).strip(' .?') == text.strip(' .?') for q in f.get('example_questions', []))]
        if len(exact) == 1 and exact[0].get('category') != 'chief_complaint' and not re.search(r'["“”]',utterance):
            return self._say(exact[0], state, meta)
        # 0. "Sorry, what was that?" -- she says her last line again rather
        #    than answering some other question or stalling.
        again = self._repeat_last_reply(text, state, meta)
        if again is not None:
            return again

        # 1. Moves that are complete replies in themselves.
        standalone = self._standalone_reply(utterance, text, state, meta)
        if standalone is not None:
            return standalone

        # 2. A medication proposed by name. If she cannot take it she says so;
        #    otherwise a proposal is acknowledged as a proposal, because it is
        #    a statement of the plan and not a question about her history.
        proposal = self._medication_turn(utterance, text, state, meta)
        if proposal is not None:
            return proposal

        complete=exact_authored_compound_history(self.case,utterance)
        if complete:return ' '.join(self._say(f,state,meta) for f in complete[:3])

        posture=posture_history_topics(utterance)
        if posture is not None:
            selected=[]
            for topic in posture:
                selected.extend(f for f in self.facts.values() if topic in position_history_fact_topics(f) and f not in selected)
            parts=[self._say(f,state,meta) for f in selected[:3]]
            missing=[topic for topic in posture if not any(topic in position_history_fact_topics(f) for f in selected)]
            if missing or not parts:parts.append('I do not have an answer to that in this simulated case. Please treat it as information unavailable, not as a denial.')
            if not selected:meta.update(kind='non_answer',no_information=True,unscripted_topic=True)
            if missing:meta['unavailable_topics']=missing
            return ' '.join(parts)

        focused=focused_history_topics(utterance)
        if focused is not None:
            selected=[]
            for topic in focused:
                selected.extend(f for f in self.facts.values() if f['id'] in _FOCUSED_FACT_IDS[topic] and f not in selected and regional_fact_allowed(f,utterance))
            parts=[self._say(f,state,meta) for f in selected[:3]]
            missing=[topic for topic in focused if not any(f['id'] in _FOCUSED_FACT_IDS[topic] for f in selected)]
            if missing or not parts:
                parts.append('I do not have an answer to that in this simulated case. Please treat it as information unavailable, not as a denial.')
            if not selected:meta.update(kind='non_answer',no_information=True,unscripted_topic=True)
            if missing:meta['unavailable_topics']=missing
            return ' '.join(parts)

        # 3. An acknowledgement can prefix a real answer rather than replace it.
        #    "That sounds uncomfortable. When did the burning start?" must still
        #    get the onset answered.
        ack = self._acknowledgement(text, state, meta)

        # 3a. Is the clinician narrating an action rather than asking anything?
        #     This MUST precede clinical matching. "I'm going to wash my hands
        #     before we start" contains the trigger words "start" and "before",
        #     so the matcher answers it with a symptom history. Reporting no
        #     information here hands the turn to engine.py's courtesy /
        #     plan-acknowledgement path, which replies in character AND records
        #     the bedside action.
        courtesy_only = courtesy_statement(utterance)
        if courtesy_only:
            # A bedside courtesy is not a history question. Without this the
            # clinical matcher answers "is it okay if I examine you now?" with
            # a current-symptom fact, because of the word "now".
            meta['kind'] = 'courtesy_statement'
            meta['no_information'] = True
            return self.rng.choice(['Okay.', 'That\'s fine.', 'Sure.', 'Of course.'])

        if dialogue.is_self_narration(utterance):
            meta['kind'] = 'action_narrated'
            meta['no_information'] = True
            return self.rng.choice(['Okay.', 'Alright.', 'Sure, go ahead.', 'That\'s fine.'])

        # 3b. Is this clinician turn ANSWERING the patient's own question?
        #     This must precede clinical matching: "no" is a complete answer to
        #     "are you going to judge me?", not an unrecognized medical question.
        answered = self._resolve_pending_question(utterance, state, meta)
        if answered is not None:
            return self._join(ack, answered)

        # 4a. "Tell me more" elaborates on the topic just discussed.
        more = self._elaborate(utterance, state, meta)
        if more is not None:
            return self._join(ack, more)

        # 4. The invitation to tell the story.
        if not state["opened"] and self._is_open_invitation(utterance):
            state["opened"] = True
            meta["kind"] = "opening"
            self._release_opening_facts(state, meta)
            return self._join(ack, self.opening())

        # 4b. A bare follow-up resolves against the subject already on the
        #     table before any general matcher gets to guess at its topic.
        followup = self._followup_hits(utterance, state)
        if followup:
            parts = [self._say(fact, state, meta) for fact, _ in followup[:2]]
            return self._join(ack, " ".join(p for p in parts if p))

        # 5. Direct questions: which facts does this reach?
        dimension_result = self._dimension_match(utterance, state)
        hits = dimension_result['hits'] if dimension_result is not None else self._match_facts(utterance, state)
        missing_dimensions = dimension_result['missing'] if dimension_result is not None else []

        if not hits and missing_dimensions:
            meta['no_information'] = True
            meta['unavailable_dimensions'] = missing_dimensions
            return 'I do not have information about '+', '.join({'current_status':'whether the symptom is present right now','last_known_well':'when I was last completely well'}.get(d,d) for d in missing_dimensions)+' in this simulated case.'

        if hits:
            if len(compound_history_domains(utterance))>1 and len(hits)>3:
                meta['no_information']=True
                return 'Please ask about my medicines and allergies separately so I can answer each fully.'
            parts = []
            for fact, _score in hits[:3]:
                parts.append(self._say(fact, state, meta))
            # A compound question -- "any night sweats or palpitations?" -- may
            # reach one scripted fact and one symptom this patient simply does
            # not have. Both halves deserve an answer.
            leftover = self._deny_unscripted(utterance, state, meta,
                                             matched=[f for f, _ in hits])
            if leftover:
                parts.append(leftover)
            if missing_dimensions:
                meta['unavailable_dimensions'] = missing_dimensions
                parts.append('I do not have information about '+', '.join({'current_status':'whether the symptom is present right now','last_known_well':'when I was last completely well'}.get(d,d) for d in missing_dimensions)+' in this simulated case.')
            self._maybe_follow_on(hits, state, meta, parts)
            return self._join(ack, " ".join(p for p in parts if p))

        # 6. A symptom this patient simply does not have.  The denial enters the
        #    record because the student ASKED -- silence still never becomes a
        #    negative.
        denial = self._deny_unscripted(utterance, state, meta)
        if denial:
            return self._join(ack, denial)

        # 7. Open "anything else?" -- gives a little, never the whole list.
        if self._is_anything_else(text) or self._is_open_invitation(utterance):
            fact = self._next_volunteer(state)
            if fact is not None and state["open_budget"] > 0:
                state["open_budget"] -= 1
                meta["volunteered"] = True
                meta["kind"] = "volunteered"
                return self._join(ack, self._say(fact, state, meta))
            return self._join(ack, self.rng.choice([
                "No, I think that's about it.",
                "Not that I can think of.",
                "That's all I can think of right now.",
            ]))

        if ack:
            return ack

        # 8. Nothing matched.  This is a non-answer, not a denial: no concept
        #    is recorded, so the note cannot claim a negative from it.
        #
        #    A clear question the case does not script gets an in-character
        #    "nothing to add" rather than "could you say that another way",
        #    which would send the learner rephrasing a question that was
        #    already fine and burn encounter time on it. Neither reply adds a
        #    fact, so neither can be documented.
        clarify = self._clarify_ambiguous(utterance, state, meta)
        if clarify is not None:
            return clarify

        meta["kind"] = "non_answer"
        meta["no_information"] = True
        already = self._already_said(text, state)
        if already is not None:
            # She has said this. Repeating it consistently is what a
            # standardized patient does; "nothing comes to mind" would
            # contradict her own history.
            meta["kind"] = "repeat"
            meta.pop("no_information", None)
            return self._say(already, state, meta, prefixed=True)
        if any(_reads_as_a_clear_question(part) for part in question_clauses(utterance)):
            meta["unscripted_topic"] = True
            return "I do not have an answer to that in this simulated case. Please treat it as information unavailable, not as a denial."
        return self.rng.choice(_NON_ANSWERS)

    def _already_said(self, text, state):
        """A fact she has already given whose own words answer this question.

        The trigger lists cannot cover every way of asking about something the
        patient volunteered in her opening statement -- no fact carries the
        trigger "burning when you urinate", because she says it unprompted --
        so a question that lands on the wording of something she has ALREADY
        said is answered from that fact rather than falling through.
        """
        asked = set(_tokens(text)) - _QUESTION_STOPWORDS
        asked = {w for w in asked if len(w) > 3}
        if not asked:
            return None
        best, best_hits = None, 0
        for fid in state.get("released") or []:
            fact = next((f for f in self.case["facts"] if f["id"] == fid), None)
            if not fact:
                continue
            words = set(_tokens(self._fact_text(fact)))
            hits = len([w for w in asked if any(
                w == o or (len(w) > 4 and w[:5] == o[:5]) for o in words)])
            if hits > best_hits:
                best, best_hits = fact, hits
        # At least half the content words of the question, and never on one
        # incidental word alone.
        if best is not None and best_hits >= 2 and best_hits * 2 >= len(asked):
            return best
        return None

    # ------------------------------------------------------------------
    def _remember(self, utterance, text, state, meta, reply):
        """Keep the topic, so the next short turn has something to resolve to.

        Only turns that actually carried a question become the remembered
        question: a non-answer or a courtesy is not a topic, and letting one
        overwrite the topic is what makes "did that help?" lose its referent.
        """
        if reply and not meta.get("no_information"):
            state["last_reply"] = reply
        if meta.get("facts_released"):
            state["last_question"] = text
        elif meta.get("kind") in ("opening", "volunteered"):
            state["last_question"] = text
        elif not meta.get("no_information") and len(_tokens(text)) > 3:
            state["last_question"] = text
        self._remember_subject(text, state, meta)

    def _remember_subject(self, text, state, meta):
        """Track what the last informative turn was ABOUT, for bare follow-ups.

        The subject comes from the facts actually spoken where there are any --
        what she said is a better anchor than what was asked -- and otherwise
        from the wording of the question. An uninformative turn leaves the
        previous subject standing rather than clearing it, so an aside between
        two related questions does not break the thread.
        """
        spoken = list(meta.get('facts_released') or [])
        subjects = set()
        for fid in spoken:
            fact = self.facts.get(fid)
            if fact:
                subjects |= self._fact_subjects(fact)
        # `last_facts` records what was just said, for elaboration; it is kept
        # for every informative turn, including HPI facts that carry no
        # anchoring subject of their own. `last_subjects` is the narrower
        # anchor used to confine a bare follow-up, so it only changes when a
        # real subject was named.
        if spoken:
            state['last_facts'] = spoken
            pending = state.get('pending_question')
            # The clinician changed the subject and got a clinical answer. The
            # concern is no longer awaiting a reply, so a later "no" belongs to
            # whatever is being discussed then, not to this question.
            if pending and pending.get('open') and pending.get('fact_id') not in spoken:
                pending['open'] = False
                pending['superseded'] = True
        if not subjects:
            subjects = set(dialogue.subjects_in(text))
        if subjects:
            state['last_subjects'] = sorted(subjects)

    @staticmethod
    def _join(ack, body):
        if ack and body:
            return ack + " " + body
        return body or ack or ""

    # ------------------------------------------------------------------
    def _repeat_last_reply(self, text, state, meta):
        """Say the previous answer again, word for word."""
        if not state.get("last_reply"):
            return None
        if len(_tokens(text)) > 10:
            return None
        asks_again = any(c in text for c in _REPEAT_REQUESTS) \
            or "what do you mean" in text
        if not asks_again:
            return None
        meta["kind"] = "repeat"
        return "Sorry — " + state["last_reply"]

    # ------------------------------------------------------------------
    def _deny_unscripted(self, utterance, state, meta, matched=None):
        """Deny a symptom the case does not carry, when it is actually asked.

        A word that appears only because it is part of a scripted fact's own
        trigger -- "does it get worse with coughing?" -- is asking about that
        fact, not about a cough. Denying it there would invent a negative the
        patient was never asked for.
        """
        text = nlp.normalize(utterance)
        if not _looks_like_a_symptom_question(text):
            return ""
        fired = []
        for fact in (matched or []):
            for phrase in (fact.get("triggers") or {}).get("any", []):
                p = nlp.normalize(phrase)
                if p and p in text:
                    fired.append(p)
        case_concepts = set(self.case.get("supersedes_core", []))
        case_concepts.update(self.case.get("concept_lexicon") or {})
        for fact in self.case.get("facts", []):
            case_concepts.update((fact.get("concepts") or {}).keys())

        found = nlp.find_concepts(utterance, {
            c: lexicon.CORE_CONCEPTS[c] for c in lexicon.DENIABLE_SYMPTOMS
            if c in lexicon.CORE_CONCEPTS})
        askable = []
        for cid in found:
            if cid in case_concepts:
                continue
            surf = nlp.normalize(found[cid]["surface"])
            if any(surf in phrase for phrase in fired):
                continue
            askable.append(cid)
        if not askable:
            return ""
        for cid in askable[:3]:
            meta["concepts"][cid] = {"polarity": "negative",
                                     "value": "denied on direct questioning"}
            if cid not in state["denied"]:
                state["denied"].append(cid)
        meta["kind"] = "denial"
        return self.rng.choice([
            "No, nothing like that.",
            "No, I haven't had that.",
            "No.",
        ])

    # ------------------------------------------------------------------
    def acknowledge_courtesy(self, state, ids):
        """An in-character reply to an introduction or a courtesy statement."""
        pat = self.case["patient"]
        if "introduce" in ids or "confirm_name" in ids:
            first = pat["name"].split()[0]
            return pat.get("greeting_reply",
                           "Hi, Doctor. Yes, I'm %s — %s is fine."
                           % (pat["name"], first))
        if "consent_exam" in ids or "position_help" in ids or "drape" in ids:
            return self.rng.choice(["That's fine.", "Okay, go ahead.",
                                    "Sure, thank you."])
        if "hand_hygiene" in ids or "gloves" in ids:
            return self.rng.choice(["Okay.", "Sure."])
        return "Okay."

    # ------------------------------------------------------------------
    def grant_consent(self, state, maneuver=None):
        """Answer a request for permission to examine.

        The reply consents and hands the turn back, because asking permission
        is not the same act as examining -- the learner still has to do it.
        """
        state.setdefault("consents", 0)
        state["consents"] += 1
        what = ""
        if maneuver and maneuver.get("label"):
            what = maneuver["label"][0].lower() + maneuver["label"][1:]
        lines = ["Yes, that's fine. Go ahead.",
                 "Sure, that's okay with me.",
                 "Yes, go ahead."]
        line = lines[(state["consents"] - 1) % len(lines)]
        if what and state["consents"] == 1:
            line = "Yes, that's fine — go ahead and %s." % what
        return line

    # ------------------------------------------------------------------
    def acknowledge_plan(self, state):
        """A short, in-character response to being told the plan."""
        state.setdefault("plan_acks", 0)
        lines = self.case["patient"].get("plan_acknowledgements") or [
            "Okay, that makes sense.",
            "Alright. Thank you for explaining that.",
            "Okay. I can do that.",
            "Got it.",
        ]
        line = lines[state["plan_acks"] % len(lines)]
        state["plan_acks"] += 1
        return line

    # ------------------------------------------------------------------
    def _standalone_reply(self, utterance, text, state, meta):
        """Replies that answer the move itself rather than a clinical question."""
        pat = self.case["patient"]

        if any(c in text for c in _SUMMARY_CUES):
            meta["kind"] = "summary_response"
            meta["ips_signal"] = "summary_offered"
            return self._answer_summary(utterance, state, meta)

        if any(c in text for c in _CLOSURE_CUES):
            meta["kind"] = "closure_response"
            meta["ips_signal"] = "closure_invited"
            concerns = pat.get("closing_questions") or []
            voiced = state.setdefault("concerns_voiced", [])
            unasked = [c for c in concerns if c not in voiced]
            if unasked:
                voiced.append(unasked[0])
                return unasked[0]
            return "No, I think you covered everything. Thank you."
        return None

    def _acknowledgement(self, text, state, meta):
        """An empathic or transitional opener the patient reacts to, briefly."""
        pat = self.case["patient"]
        if any(c in text for c in _EMPATHY_CUES):
            meta["ips_signal"] = "empathy_received"
            if state.get("empathy_ack", 0) < 3:
                state["empathy_ack"] = state.get("empathy_ack", 0) + 1
                if pat.get("demeanor", {}).get("version") == "demeanor-v1":
                    from .presentation import social_reply
                    return social_reply(self.case, "thanks", state["empathy_ack"] - 1)
                return self.rng.choice(pat.get("empathy_replies", [
                    "Thank you. It's been a rough few days.",
                    "I appreciate you saying that.",
                ]))
            return "Thank you."
        if any(c in text for c in _TRANSITION_CUES):
            meta["ips_signal"] = "transition_used"
            if pat.get("demeanor", {}).get("version") == "demeanor-v1":
                from .presentation import social_reply
                count = state.get("transition_ack", 0)
                state["transition_ack"] = count + 1
                return social_reply(self.case, "transition", count)
            return self.rng.choice(["Okay.", "Sure.", "Of course."])
        return None

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------
    def _answer_summary(self, utterance, state, meta):
        """Answer a summary on its content, not on the fact that it happened.

        Four things can be wrong with a summary, and each of them has to reach
        the learner while there is still time to fix it: it can say nothing at
        all, it can say something the patient never said, it can get a
        demographic wrong, or it can deny something she reported.
        """
        clauses = self._summary_clauses(utterance)
        content = " ".join(clauses)
        tokens = _content_tokens(content)
        if not tokens:
            meta["summary_verdict"] = "empty"
            return ("I'm not sure what you're checking — you didn't say "
                    "anything back to me. Could you go over it again?")

        wrong_age = self._summary_wrong_age(content)
        if wrong_age:
            meta["summary_verdict"] = "corrected_age"
            return wrong_age

        denied = self._summary_denies_reported(content, state, meta)
        if denied:
            meta["summary_verdict"] = "corrected_negation"
            return denied

        timeline = self._summary_wrong_timeline(clauses, state, meta)
        if timeline:
            meta["summary_verdict"] = "corrected_timeline"
            return timeline

        # Telling a learner they invented the whole thing is a serious thing
        # to say, so it is said only when the record recognizes nothing at
        # all -- or almost nothing in a long summary.  A short accurate
        # summary carries few words to match ("the pressure spreads into
        # your arm"), and accusing THAT of being made up is the same defect
        # as confirming a wrong summary, pointed the other way.
        recognized = _overlap(tokens, self._record_vocabulary())
        if recognized == 0 or (len(tokens) >= 4 and recognized <= 1):
            meta["summary_verdict"] = "unrecognized"
            return ("I'm sorry — that's not what I've been telling you. "
                    "Could you go over it again?")

        meta["summary_verdict"] = "confirmed"
        return self.rng.choice([
            "Yes, that's right.",
            "That's it, yes.",
            "Mostly - yes, that's what I've been dealing with.",
        ])

    @staticmethod
    def _summary_clauses(utterance):
        """The summary's own claims, one per clause, opener and tail removed.

        The RAW turn is used, not the normalized one: normalization strips the
        commas and full stops that separate one claim from the next, and a
        summary has to be checked claim by claim -- "three weeks" is true of
        her last period and false of her back pain.
        """
        low = (utterance or "").lower().replace("\u2019", "'")
        for cue in _SUMMARY_CUES + _SUMMARY_TAILS:
            low = low.replace(cue, " ")
        pieces = re.split(r"[,;.!?]|\band\b", low)
        return [p.strip() for p in pieces if p.strip()]

    def _summary_wrong_age(self, content):
        """Correct an age the case does not carry."""
        age = self.case["patient"].get("age")
        if not age:
            return ""
        for pattern in _AGE_PATTERNS:
            for m in pattern.finditer(content):
                claimed = int(m.group(1))
                if not 1 <= claimed <= 120:
                    continue
                if claimed == int(age):
                    continue
                return ("Actually, I'm %d, not %d — I think you have my age "
                        "wrong." % (int(age), claimed))
        return ""

    def _summary_denies_reported(self, content, state, meta):
        """Correct a symptom she reported that the summary says she denies."""
        positives = {}
        for fid in state["released"]:
            fact = self.facts.get(fid)
            if not fact:
                continue
            for cid, spec in (fact.get("concepts") or {}).items():
                if isinstance(spec, str):
                    spec = {"polarity": "positive", "value": spec}
                if spec.get("polarity") == "positive":
                    positives.setdefault(cid, fid)
        if not positives:
            return ""
        surfaces = self._concept_surfaces()
        concept_map = {cid: surfaces[cid] for cid in positives
                       if cid in surfaces}
        if not concept_map:
            return ""
        found = nlp.find_concepts(content, concept_map)
        for cid, hit in found.items():
            if not hit.get("negated"):
                continue
            fact = self.facts.get(positives[cid])
            if not fact:
                continue
            line = self._say(fact, state, meta, credit=False)
            return "Actually, that part isn't right — " + _lower_first(line)
        return ""

    def _summary_wrong_timeline(self, clauses, state, meta):
        """Correct an interval the case's own account contradicts.

        The comparison is topic by topic: this patient's story contains
        several intervals, and one of them being three weeks does not make
        "three weeks" a true answer about the back pain.
        """
        for clause in clauses:
            claimed = _time_expressions(clause)
            if not claimed:
                continue
            related = self._facts_about(clause)
            if not related:
                continue
            attested = set()
            for fact in related:
                attested.update(_time_expressions(self._fact_text(fact)))
            if not attested:
                continue
            wrong = [c for c in claimed if c not in attested]
            if not wrong:
                continue
            teller = self._timeline_fact(related)
            if teller is None:
                continue
            line = self._say(teller, state, meta, credit=False)
            return "That's not quite right — " + _lower_first(line)
        return ""

    def _facts_about(self, clause):
        """The facts whose own words this clause is talking about.

        The interval itself is removed before the comparison: "three weeks"
        would otherwise make the clause look like a question about the last
        menstrual period, which is the one fact in the case that mentions
        three weeks.

        Every fact that ties on the best score is kept, and a clause is only
        wrong when NONE of them attests the interval it claims -- which is why
        a single shared word ("the burning") is enough to look the claim up
        without turning an ambiguous match into a false correction.
        """
        tokens = _content_tokens(_TIME_EXPR.sub(" ", nlp.normalize(clause)))
        if not tokens:
            return []
        scored = []
        for fact in self.case.get("facts", []):
            score = _overlap(tokens, set(_content_tokens(self._fact_text(fact))))
            if score:
                scored.append((score, fact))
        if not scored:
            return []
        best = max(s for s, _ in scored)
        return [f for s, f in scored if s == best]

    @staticmethod
    def _timeline_fact(facts):
        """Whichever of these facts actually tells the story's timing."""
        for category in ("onset", "chronology", "timing"):
            for fact in facts:
                if fact.get("category") == category:
                    return fact
        return facts[0] if facts else None

    def _fact_text(self, fact):
        """Everything this fact says, including its concepts' own wording."""
        parts = [fact.get("value") or ""]
        parts.extend(fact.get("sp_says") or [])
        surfaces = self._concept_surfaces()
        for cid, spec in (fact.get("concepts") or {}).items():
            if isinstance(spec, str):
                parts.append(spec)
            else:
                parts.append(str(spec.get("value") or ""))
            parts.extend(surfaces.get(cid, []))
        return " ".join(p for p in parts if p)

    def _concept_surfaces(self):
        """Surface forms for this case's concepts, case wording first."""
        surfaces = {}
        for cid, forms in (self.case.get("concept_lexicon") or {}).items():
            surfaces[cid] = list(forms)
        for cid, forms in lexicon.CORE_CONCEPTS.items():
            surfaces.setdefault(cid, list(forms))
        return surfaces

    def _record_vocabulary(self):
        """Every word this patient's story is made of."""
        parts = [self.case["patient"].get("opening") or ""]
        for fact in self.case.get("facts", []):
            parts.append(self._fact_text(fact))
        return set(_content_tokens(" ".join(parts)))

    # ------------------------------------------------------------------
    # A medication proposed by name
    # ------------------------------------------------------------------
    def _medication_turn(self, utterance, text, state, meta):
        """Answer a proposed drug: as a hazard if she cannot take it."""
        alarm = self._allergy_alarm(utterance, text, state, meta)
        if alarm:
            return alarm
        if any(cue in text for cue in _PRESCRIBING_CUES) and "?" not in utterance:
            meta["kind"] = "plan_ack"
            return self.acknowledge_plan(state)
        return None

    def _allergy_alarm(self, utterance, text, state, meta):
        """Speak up when the drug on the table is one she reacts to.

        Only the family lookup is general knowledge; the allergy itself and
        the reaction she describes come from her own case file.
        """
        allergy_facts = [f for f in self.case.get("facts", [])
                         if f.get("category") == "allergies"]
        if not allergy_facts:
            return ""
        words = set(_tokens(text))
        for fact in allergy_facts:
            fact_words = set(_tokens(self._fact_text(fact)))
            for family in _DRUG_FAMILIES.values():
                allergen = next((m for m in family["members"]
                                 if m in fact_words), None)
                if not allergen:
                    continue
                proposed = next((m for m in family["members"]
                                 if m in words and m != allergen), None)
                # Naming the allergen itself only raises the alarm when the
                # student is PUTTING IT ON THE TABLE.  "Any allergies --
                # penicillin, sulfa, anything like that?" names it while
                # TAKING the history, and answering that with "wait, that's
                # the one I react to" answers a proposal nobody made and
                # drops her scripted allergy line out of its own question.
                named_directly = allergen in words and _proposes(utterance, text)
                if not proposed and not named_directly:
                    continue
                meta["kind"] = "allergy_concern"
                line = _drop_naming_sentence(
                    self._say(fact, state, meta, credit=False, prefixed=False),
                    allergen)
                if proposed:
                    return ("Wait — isn't %s a %s? I can't take those. %s"
                            % (_as_written(proposed, utterance),
                               family["label"], line))
                return "Wait — that's the one I react to. %s" % line
        return ""

    # ------------------------------------------------------------------
    def _is_open_invitation(self, text):
        return opening_invitation(text,self.case.get('patient',{}).get('name',''))

    def _is_anything_else(self, text):
        return any(c in text for c in _ANYTHING_ELSE)

    # ------------------------------------------------------------------
    def _dimension_match(self, utterance, state):
        # Split only explicit new question clauses, not clinical noun lists or
        # the "or" that belongs to a continuous/intermittent comparison.
        clauses=question_clauses(utterance)
        if not any(temporal_question_dimensions(p) for p in clauses):return None
        hits=[];missing=[]
        for clause in clauses:
            dims=temporal_question_dimensions(clause)
            if re.search(r'medicin|medication|supplement|alcohol|\bdrink\b|smok|cigarett|tobacco|exercise|\bwork\b|\bjob\b|family|mother|father|menstr|\bperiods?\b',clause,re.I):dims=set()
            if dims:
                # A specified organ's frequency is not automatically the
                # chief complaint's frequency; use authored lexical evidence.
                candidates=[f for f in self.facts.values() if authored_temporal_dimensions(f)&dims and regional_fact_allowed(f,clause)]
                if re.search(r'bowel|stool|urina|urine|void|burning',clause,re.I):
                    words=set(re.findall(r'bowel|stool|urina|urine|void|burning',clause.lower()))
                    candidates=[f for f in candidates if any(w in self._fact_text(f).lower() or w in f['id'] for w in words) or (self.case.get('id','').startswith('renal-') and f['id']=='hpi_timing')]
                exact=[f for f in candidates if any(nlp.normalize(q).rstrip('?')==nlp.normalize(clause).rstrip('?') for q in f.get('example_questions',[]))]
                if exact:candidates=exact
                if 'current_status' in dims:
                    candidates=[f for f in candidates if current_status_subject_matches(f,clause)]
                    if re.search(r'how (?:bad|severe)|severity|(?:rate|score).*pain|out of ten',clause,re.I):
                        candidates=[f for f in candidates if f.get('category')=='severity']
                hits.extend((f,3.0) for f in candidates)
                supported=set().union(*(authored_temporal_dimensions(f) for f in candidates)) if candidates else set()
                missing.extend(sorted(dims-supported))
            else:
                hits.extend(self._match_without_dimensions(clause,state))
        unique={f['id']:(f,score) for f,score in hits}
        return {'hits':list(unique.values()),'missing':list(dict.fromkeys(missing))}

    def _match_without_dimensions(self, utterance, state):
        precise=self._typed_question_hits(utterance)
        if precise is not None:return precise
        return self._trigger_hits(utterance,state) or self._aspect_hits(utterance)

    def _match_facts(self, utterance, state):
        """Which scripted facts this turn reaches, best first.

        Three chances, in order of how directly they read the question: the
        case's own trigger phrases, the ordinary-English paraphrase layer, and
        -- for a turn that carries no topic of its own -- the same two again
        with the previous question restored as context.
        """
        precise = self._typed_question_hits(utterance)
        if precise is not None:
            return precise
        hits = self._trigger_hits(utterance, state)
        if hits:
            return hits
        aspect = self._aspect_hits(utterance)
        if aspect:
            return aspect
        if self._is_elliptical(utterance) and state.get("last_question"):
            context = utterance + " " + state["last_question"]
            hits = self._trigger_hits(context, state)
            if hits:
                return hits
            return self._aspect_hits(context)
        return []

    def _typed_question_hits(self, utterance):
        """Resolve an explicit question dimension before broad trigger words.

        This routes to authored facts only. A known but unscripted dimension
        returns no facts instead of substituting onset for episode duration.
        """
        complete=exact_authored_compound_history(self.case,utterance)
        if complete:return [(f,3.0) for f in complete]
        posture=posture_history_topics(utterance)
        if posture is not None:return [(f,3.0) for f in self.facts.values() if set(posture)&set(position_history_fact_topics(f))]
        focused=focused_fact_ids(utterance)
        if focused is not None:return [(f,3.0) for f in self.facts.values() if f['id'] in focused and regional_fact_allowed(f,utterance)]
        text = nlp.normalize(utterance)
        domains=compound_history_domains(utterance)
        if len(domains)>1 or domains==['allergies']:
            return [(f,3.0) for f in self.facts.values() if f.get('category') in domains]
        if domains==['medications'] and re.search(r'how often|what.*(?:medicin|medication)|which|dosage|dose|take daily|over the counter',text) and not re.search(r'help|tried|for (?:the )?pain',text):
            return [(f,3.0) for f in self.facts.values() if f.get('category')=='medications']
        # Common tense forms refer to the same authored symptom, not a
        # fabricated denial. Bloody emesis, third-party history and causal or
        # medication questions retain their more specific existing routes.
        vomiting=re.search(r'\bvomit(?:ed|ing|s)?\b|\b(?:throw|threw|throwing|thrown) up\b|\bemesis\b',text)
        direct=re.match(r'^(?:have you|did you|do you|are you|were you|any|and have you|what about|vomit|throw|threw|emesis)',text)
        bloody=re.search(r'\bblood\b|bloody|coffee ground|hematemesis',text)
        excluded=re.search(r'mother|father|family|partner|child|medicin|medication|drug|allerg|cause|caused|could.*(?:make|cause)|can.*(?:make|cause)',text)
        if vomiting and excluded:return []
        if (vomiting or 'hematemesis' in text) and bloody:
            return [(f,3.0) for f in self.facts.values() if f.get('bloody_emesis_response')]
        if vomiting and direct and not re.search(r'\bnausea\b|\bfever\b|\bchills\b|\bdiarrhea\b',text):
            facts=[f for f in self.facts.values() if f.get('symptom_topic')=='vomiting']
            if facts:return [(f,3.0) for f in facts]
        if self.case.get('id') == 'gi-right-lower-pain':
            focused = [
                ('history_bowel_pattern', r'(?:bowel movements?|bowel habits?|stools?).*(?:change|usual|normal)|change.*(?:bowel movements?|bowel habits?)'),
                ('hpi_radiation', r'(?:begin|began|start|initial|first).*(?:same|different).*(?:place|location)|(?:same|different).*(?:place|location).*now|where.*pain.*start.*moved|pain.*migrat'),
            ]
            for fid, pattern in focused:
                if fid == 'history_bowel_pattern' and re.search(r'blood|black|diarrh|constipat|how often|how many', text):
                    continue
                if re.search(pattern, text):
                    fact = self.facts.get(fid)
                    return [(fact, 3.0)] if fact else []
        rules = [
            ('temporal_role', 'episode_duration', r'(?:each|an|one|individual) (?:episode|spell|attack)|how long (?:does|do|did).*last|how many (?:seconds|minutes).*last'),
            ('temporal_role', 'current_episode_onset', r'(?:this|current|latest) episode.*(?:start|begin)|when.*(?:this|current|latest) episode|how long (?:has|have).*(?:this|current) episode|how long.*(?:this|current) episode.*(?:last|going)'),
            ('history_topic', 'pregnancy', r'pregnan|chance.*(?:expecting|conceiv)'),
            ('history_topic', 'cycle_regularity', r'periods? regular|regular.*period|menstrual.*regular'),
            ('history_topic', 'menstrual', r'last (?:menstrual|period)|\b(?:lmp|periods|menstruat)\b'),
            ('history_topic', 'contraception', r'contracept|birth control|condom|protection.*sex'),
            ('history_topic', 'sexual_partners', r'how many.*partner|new sexual partner|partners.*(?:men|women)|sex.*(?:men or women)'),
            ('history_topic', 'sexual_activity', r'sexually active|having sex|sexual activity'),
            ('history_topic', 'occupation', r'what.*(?:work|living)|your (?:job|occupation)|employment'),
            # "Where do you live?" is a social question. Without this the bare
            # word "where" reaches the symptom-location aspect and the patient
            # answers with the site of her pain.
            ('history_topic', 'household', r'who.*live|live (?:alone|with)|living situation|household|where (?:do|are) you liv|where do you stay|do you live alone'),
            ('history_topic', 'caffeine', r'caffeine|coffee(?! grounds)|energy drink'),
            ('history_topic', 'urine_output', r'(?:able|can you|still).*?(?:pass urine|urinate|pee)|urine output|how much.*urine|stopped.*(?:urinating|peeing)'),
        ]
        matches=[]
        for key,value,pattern in rules:
            if value=='menstrual' and re.search(r'regular',text):continue
            if re.search(pattern,text):
                facts=[f for f in self.facts.values() if f.get(key)==value]
                if key=='temporal_role' and value=='episode_duration' and not facts:
                    prior=[f for f in self.facts.values() if f.get(key)=='prior_episode_duration']
                    if prior:
                        facts=prior
                        if not re.search(r'earlier|previous|prior|past',text):
                            facts += [f for f in self.facts.values() if f.get(key)=='current_episode_onset']
                # Older authored facts retain their established category route.
                if not facts and not any(key in f for f in self.facts.values()):
                    continue
                matches.extend((f,3.0) for f in facts)
                if not facts:
                    return []
        if matches:
            unique={f['id']:(f,score) for f,score in matches}
            return list(unique.values())
        return None

    def behavior_response(self, spec, state):
        """Release only explicitly authored behavior disclosures, without checklist credit."""
        state.setdefault('released',[]);state.setdefault('asked_counts',{})
        reply=spec.get('reply','')
        meta={'facts_released':[], 'concepts':{}, 'volunteered':True, 'kind':'behavior'}
        for fid in spec.get('fact_ids',[]):
            fact=self.facts.get(fid)
            if not fact:continue
            approved=delivered_fact_metadata(fact,reply)
            for actual in approved['facts_released']:
                if actual not in state['released']:state['released'].append(actual)
                if actual not in meta['facts_released']:meta['facts_released'].append(actual)
            meta['concepts'].update(approved['concepts'])
        state['last_reply']=reply
        return reply,meta

    def _trigger_hits(self, utterance, state):
        scored = []
        for fact in self.case.get("facts", []):
            if not regional_fact_allowed(fact,utterance):continue
            score = nlp.trigger_score(utterance, fact.get("triggers"))
            if score <= 0:
                continue
            # Already answered? Still matches -- consistency matters more than
            # novelty -- but new material outranks a repeat.
            if fact["id"] in state["released"]:
                score *= 0.55
            scored.append((fact, score))
        scored.sort(key=lambda x: -x[1])
        if not scored:
            return []
        top = scored[0][1]
        # Keep near-ties so a compound question ("fever, chills, nausea?") gets
        # each part answered. The floor never excludes the best match itself,
        # or a revisited topic would go unanswered instead of being repeated
        # consistently.
        floor = max(top * 0.7, min(0.8, top))
        return [(f, s) for f, s in scored if s >= floor]

    def _aspect_hits(self, utterance):
        """The paraphrase layer: an ordinary question, read by its aspect."""
        text = nlp.normalize(utterance)
        words = set(text.split())
        best = None
        for aspect in _ASPECTS:
            if not self._aspect_fires(aspect, text, words):
                continue
            candidates = self._aspect_facts(aspect, text)
            if not candidates:
                continue
            question_tokens = _content_tokens(text)
            ranked = []
            for fact in candidates:
                overlap = _overlap(question_tokens,
                                   set(_content_tokens(self._fact_text(fact))))
                ranked.append((overlap, fact))
            ranked.sort(key=lambda x: -x[0])
            top = ranked[0]
            # A more specific aspect -- one that narrowed a broad category by
            # its own keywords -- beats a general one on the same turn.
            weight = (2 if aspect.get("keywords") else 1, top[0])
            if best is None or weight > best[0]:
                best = (weight, top[1])
        if best is None:
            return []
        return [(best[1], 1.0)]

    @staticmethod
    def _aspect_fires(aspect, text, words):
        """Is this turn asking about this aspect at all?

        A multiword cue ("takes the edge off") names its own topic, so it
        stands alone.  A single everyday verb does not: "how can I help you
        today?" uses a relief verb and asks nothing about the pain, which is
        why an aspect built on bare words also demands a referent.
        """
        if any(cue in text for cue in aspect.get("cues", [])):
            return True
        if not words & set(aspect.get("words", ())):
            return False
        if aspect.get("needs_referent") and not (words & _REFERENTS):
            return False
        return True

    def _aspect_facts(self, aspect, text):
        """The facts in this aspect's categories, narrowed by its keywords.

        A fact's own "not" phrases veto here exactly as they do in the trigger
        matcher.  "Hi, I'm a student doctor" is why the occupation fact carries
        one: the paraphrase layer would otherwise hear the learner's
        introduction as a question about her job.
        """
        out = []
        keywords = aspect.get("keywords")
        for fact in self.case.get("facts", []):
            if not regional_fact_allowed(fact,text):continue
            if fact.get("category") not in aspect["categories"]:
                continue
            blocked = (fact.get("triggers") or {}).get("not") or []
            if any(nlp.normalize(phrase) in text for phrase in blocked):
                continue
            if keywords:
                fact_words = set(_tokens(self._fact_text(fact)))
                if not any(any(_same_word(k, w) for w in fact_words)
                           for k in keywords):
                    continue
            out.append(fact)
        return out

    @staticmethod
    def _is_elliptical(utterance):
        """A turn too short to carry its own topic ("did that help?")."""
        text = nlp.normalize(utterance)
        tokens = text.split()
        if len(tokens) > 8:
            return False
        if set(tokens) & _ANAPHORS:
            return True
        return any(text.startswith(s) for s in _ELLIPTIC_STARTS)

    # ------------------------------------------------------------------
    def _say(self, fact, state, meta, credit=True, prefixed=True):
        """Speak a scripted fact, and record what saying it put on the record.

        `credit` is withheld when she volunteers the fact to correct a mistake
        or to head off a drug she cannot take: what she said is true and
        belongs in the record, but the learner did not ask for it, and the
        history checklist may only credit questions that were actually asked.
        `prefixed` is dropped where a "like I said" opener would land in the
        middle of a sentence she is building.
        """
        repeat = fact['id'] in state['released']
        lines = fact.get('sp_says') or [fact.get('value','')]
        line = lines[0] if repeat else self.rng.choice(lines)
        if fact.get('category')=='past_occurrence' and line=='I have not had pneumonia before.':
            meta.update(kind='non_answer',no_information=True)
            return 'My earlier wording named a diagnosis that has not been established for this encounter. I do not know what is causing these symptoms.'
        approved=delivered_fact_metadata(fact,line)
        if approved['facts_released']:
            if fact['id'] not in state['released']:state['released'].append(fact['id'])
            state['asked_counts'][fact['id']]=state['asked_counts'].get(fact['id'],0)+1
            for fid in approved['facts_released']:
                if fid not in meta['facts_released']:meta['facts_released'].append(fid)
            meta['concepts'].update(approved['concepts'])
            if credit:meta.setdefault('checklist_hits',[]).extend(approved['checklist_hits'])
        else:
            # Actual text remains evidence; old rich metadata is not trusted.
            cid='delivered_text_'+fact['id']
            meta['concepts'][cid]={'polarity':'positive','value':line}
            meta.setdefault('delivery_limits',[]).append('Legacy statement has no verified atomic contract: '+fact['id'])
        if repeat and prefixed:
            prefix=self.rng.choice(_REPEAT_PREFIXES)
            if prefix:line=prefix+_lower_first(line)
        if fact.get('emotion'):meta['emotion']=fact['emotion']
        # A spoken line that asks the clinician something becomes the open
        # question, so the clinician's next turn can be read as its answer.
        self._note_patient_question(line, fact, state)
        return line

    # ------------------------------------------------------------------
    def _maybe_follow_on(self, hits, state, meta, parts):
        """A patient sometimes adds one related detail, unprompted."""
        if state["open_budget"] <= 0 or not hits:
            return
        fact = hits[0][0]
        follow_id = fact.get("follow_on")
        if not follow_id or follow_id in state["released"]:
            return
        follow = self.facts.get(follow_id)
        if not follow:
            return
        if self.rng.random() > float(fact.get("follow_on_prob", 0.5)):
            return
        state["open_budget"] -= 1
        line = self._say(follow, state, meta)
        meta["volunteered"] = True
        parts.append(line)

    # ------------------------------------------------------------------
    def _next_volunteer(self, state):
        """The next fact this patient would naturally offer, if any."""
        for fid in self.case["patient"].get("volunteer_order", []):
            if fid not in state["released"] and fid in self.facts:
                return self.facts[fid]
        return None

    # ------------------------------------------------------------------
    def release_opening(self, state, meta):
        self._release_opening_facts(state, meta)

    def _release_opening_facts(self, state, meta):
        opening=self.opening()
        for fid in self.case['patient'].get('opening_facts',[]):
            fact=self.facts.get(fid)
            if not fact:continue
            approved=delivered_fact_metadata(fact,opening)
            for actual in approved['facts_released']:
                if actual not in state['released']:state['released'].append(actual)
                if actual not in meta['facts_released']:meta['facts_released'].append(actual)
            meta['concepts'].update(approved['concepts'])
            meta.setdefault('checklist_hits',[]).extend(approved['checklist_hits'])
        if not meta['facts_released']:
            meta['concepts']['opening_delivered_text']={'polarity':'positive','value':opening}
            meta['delivery_limits']=['Legacy opening metadata withheld; only actual opening text is evidence.']


_QUESTION_STARTS = (
    "do you", "did you", "does", "have you", "has ", "had you", "are you",
    "is there", "any ", "what", "when", "where", "which", "who", "how",
    "would you", "will you", "can you", "could you", "were you", "was ",
    "you're not", "youre not", "you are not",
)


def _proposes(utterance, text):
    """Is this turn putting a drug on the table, rather than asking about one?

    A question is history taking, however the drug's name appears in it; a
    statement, or anything with an explicit prescribing phrase in it, is a
    plan the patient is entitled to react to.
    """
    if any(cue in text for cue in _PRESCRIBING_CUES):
        return True
    if "?" in (utterance or ""):
        return False
    return not text.startswith(_QUESTION_STARTS)


def _drop_naming_sentence(line, allergen):
    """Trim a scripted line that opens by naming the allergen.

    Her answer to "any allergies?" is "Penicillin. My lips and face swelled
    up." -- read back after "isn't amoxicillin a penicillin?", that first word
    is said twice, so only the part that carries new information is kept.
    """
    head, sep, tail = line.partition(".")
    if sep and tail.strip() and nlp.normalize(head) == nlp.normalize(allergen):
        return tail.strip()
    return line


def _as_written(word, utterance):
    """The drug name in the learner's own capitalization ("Bactrim")."""
    for token in re.findall(r"[A-Za-z][A-Za-z\-]*", utterance or ""):
        if token.lower().strip("-") == word:
            return token
    return word


def _lower_first(line):
    """Join a scripted line onto a correction without shouting mid-sentence.

    The first-person pronoun keeps its capital -- "as I mentioned, i've felt
    hot" is the sort of seam that makes a scripted patient read as a machine --
    but a word that merely starts with I, like "If", does not.
    """
    if line and line[0].isupper() and not re.match(r"I(?:$|['\s])", line):
        return line[0].lower() + line[1:]
    return line


_SYMPTOM_QUESTION_CUES = [
    "any ", "have you", "do you", "did you", "are you", "is there", "notice",
    "experienced", "been having", "complain", "having any", "problems with",
    "trouble with", "issues with", "suffer",
]


def _looks_like_a_symptom_question(text: str) -> bool:
    return any(c in text for c in _SYMPTOM_QUESTION_CUES)
