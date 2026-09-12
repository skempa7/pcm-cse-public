"""Multi-intent composition for the simulated patient.

WHY THIS MODULE EXISTS
----------------------
`patient.PatientEngine` resolves a turn through a long, carefully reviewed
chain of routes: authored example questions, posture/focused history grammars,
temporal dimensions, the case's own trigger phrases, and an ordinary-English
paraphrase layer. Each route is individually sound. The chain, however,
returned on the FIRST route that fired, so a turn that asked two things got one
answer:

    "What is your name and what brings you in today?"  ->  "My name is Raya."

This module does not replace that chain. It sits ABOVE it: it splits a turn
into the separate things that were actually asked, runs the existing chain once
per ask, and merges the answers in the order they were asked.

INVARIANTS THIS MODULE MUST NOT BREAK
-------------------------------------
1. Clinical text is never authored here. Every clinical sentence still comes
   from the case's own `sp_says` / `delivery_contract` through `_say()`. This
   module only contributes connective words ("and", "As for") and the
   non-clinical identity/uncertainty phrasings listed below. A fabricated
   symptom sentence would both lie to the learner and silently downgrade
   grading, because `delivered_fact_metadata` credits only approved text.
2. Evidence is granted only by `_say()`. Composition never adds a fact ID, a
   concept or a checklist hit of its own.
3. A single-ask turn takes exactly the path it took before this module
   existed. Segmentation must produce two or more asks before anything here
   changes behavior, so the reviewed single-question routes are untouched.
"""
import re

from . import nlp

# --------------------------------------------------------------------------
# Segmentation
# --------------------------------------------------------------------------
# Words that can begin a new, independent ask. Splitting on "and"/"," only
# happens in front of one of these, so clinical noun lists ("left arm and jaw")
# and comparisons ("sharp or dull") are not torn apart.
_STARTERS = (r"(?:what|whats|what's|when|where|why|how|who|which|is|are|was|were|do|does|did|"
             r"have|has|had|can|could|would|will|any|anything|tell|describe|show)")
_NEW_ASK = re.compile(r"[?;]|(?<!\d)\.(?=\s|$)|,\s*(?=" + _STARTERS + r"\b)"
                      r"|\s+and\s+(?=" + _STARTERS + r"\b)"
                      r"|\s*,\s*and\s+(?=" + _STARTERS + r"\b)", re.I)

# "Any medical problems, surgeries, medications, or allergies?" is one stem
# distributed over a list. Each item is its own ask; the stem is re-attached so
# the existing routes see a well-formed question.
_LIST_STEM = re.compile(
    r"^\s*(?P<stem>(?:and\s+)?(?:do you have|do you take|are you on|have you had|have you ever had|"
    r"do you use|do you drink|do you smoke|do you|any|anything|what|whats|what's)\b[^,]*?)\s+"
    r"(?P<items>[^?]*?(?:,|\s+or\s+)[^?]*)$", re.I)
_ITEM_SPLIT = re.compile(r",\s*(?:or\s+)?|\s+or\s+|\s*,\s*and\s+|\s+and\s+", re.I)

# A list item must read as a short topic noun phrase. Anything longer is a
# clause that the stem distributor would mangle.
_MAX_ITEM_WORDS = 4

# Comparisons and paired descriptors that are ONE question, never a list.
_NOT_A_LIST = re.compile(
    r"\b(?:sharp or dull|dull or sharp|better or worse|worse or better|constant or|"
    r"come and go|comes and goes|on and off|now or|more or less|men or women|"
    r"crampy or|burning or|stabbing or|day or night|up or down)\b", re.I)


# --------------------------------------------------------------------------
# Canonical topic vocabulary
# --------------------------------------------------------------------------
# One entry per topic a learner can ask about, each with the ordinary ways it
# gets said. This is a compact synonym table, deliberately NOT a corpus of
# whole sentences: it stays maintainable, and adding a phrasing is a one-line
# change. It is used for three jobs -- reading shorthand lists ("meds allergies
# surgeries?"), resolving a bare follow-up against what was just discussed, and
# naming a topic in a clarifying question. It never supplies a clinical answer;
# it only says WHAT was asked about. The answer always comes from case facts.
TOPIC_CUES = {
    "name":        [r"\bname\b", r"what (?:should|can|may) i call you", r"call you"],
    "age":         [r"\bage\b", r"how old"],
    "sex":         [r"\bsex\b", r"\bgender\b"],
    "occupation":  [r"\bjob\b", r"\bwork\b", r"occupation", r"employ", r"for a living"],
    "household":   [r"\blive\b", r"living situation", r"household", r"who.*with you", r"\bhome\b"],
    # "brought you in" is the commonest opening there is, and the past tense
    # was missing: with no topic detected in the remainder, a turn that also
    # introduced the clinician was read as pure courtesy and answered with the
    # patient's name instead of the presenting complaint.
    "chief_complaint": [r"brings you", r"bring you", r"brought you", r"why (?:are|r) you here", r"what happened",
                        r"what'?s (?:been )?going on", r"what has been going on",
                        r"why you are here", r"why you'?re here",
                        r"seems to be the problem", r"here for",
                        r"what can i (?:help|do)", r"reason for (?:your )?visit", r"came in",
                        r"come in today", r"made you (?:come|decide)", r"chief complaint"],
    "onset":       [r"\bonset\b", r"when did", r"how long (?:have|has|hav)", r"since when",
                    r"first (?:notice|start|began|begin)", r"start(?:ed)?\b", r"began\b"],
    "duration":    [r"how long (?:does|do|did)", r"how long.*last"],
    "location":    [r"\bwhere\b", r"what part", r"which (?:side|part)", r"point to", r"location",
                    r"where exactly", r"whereabouts"],
    "radiation":   [r"radiat", r"\bspread", r"travel", r"move (?:any|some)where",
                    r"go (?:any|some)where", r"shoot", r"\brefer\b"],
    "quality":     [r"feel like", r"what.*like", r"describe", r"sharp or dull", r"kind of pain",
                    r"type of pain", r"character"],
    "severity":    [r"how bad", r"how severe", r"out of (?:ten|10)", r"scale", r"rate (?:it|the)",
                    r"severity", r"how much does it hurt", r"how strong"],
    "timing":      [r"how often", r"how frequent", r"frequency", r"time of day", r"\btiming\b",
                    r"come and go", r"constant", r"intermittent"],
    "chronology":  [r"getting (?:worse|better)", r"changed since", r"progress", r"course of"],
    "aggravating": [r"make it worse", r"makes it worse", r"worse (?:with|when)", r"aggravat",
                    r"bring it on", r"trigger", r"set it off"],
    "alleviating": [r"make it better", r"makes it better", r"better (?:with|when)", r"reliev",
                    r"help(?:s)? (?:it|the pain)", r"takes? the edge off", r"ease"],
    "treatment":   [r"taken anything", r"tried anything", r"take for it", r"took for it",
                    r"treatment", r"tried to treat"],
    "associated":  [r"associated", r"other symptom", r"anything else going on", r"along with"],
    "past_occurrence": [r"happened before", r"had this before", r"ever had this",
                        r"previous episode", r"prior episode", r"first time"],
    "pmh":         [r"medical (?:problem|history|condition|issue)", r"\bpmh\b", r"chronic",
                    r"diagnos", r"health (?:problem|condition)", r"any illness",
                    r"hospitaliz", r"\bconditions?\b"],
    "psh":         [r"surger", r"\bsurgical\b", r"\bpsh\b", r"operation", r"\bprocedure",
                    r"been operated"],
    "medications": [r"medicat", r"\bmeds\b", r"\bmedicine", r"prescription", r"\bpills?\b",
                    r"supplement", r"taking anything", r"\bdrugs? (?:do|are) you tak"],
    "allergies":   [r"allerg", r"\breaction\b"],
    "family":      [r"family history", r"\bfamily\b", r"\bmother\b", r"\bfather\b", r"\bmom\b",
                    r"\bdad\b", r"\bparents?\b", r"sibling", r"\bbrother\b", r"\bsister\b",
                    r"runs in"],
    "tobacco":     [r"smok", r"cigarett", r"tobacco", r"\bvap", r"nicotine", r"\bpacks?\b"],
    "alcohol":     [r"alcohol", r"\bdrink", r"\bbeer\b", r"\bwine\b", r"liquor", r"\betoh\b"],
    "drugs":       [r"recreational", r"street drug", r"illicit", r"\bcocaine\b", r"\bheroin\b",
                    r"\bmarijuana\b", r"\bweed\b", r"inject", r"\bdrug use\b"],
    "diet":        [r"\bdiet\b", r"what do you eat", r"eating habits"],
    "exercise":    [r"exercis", r"physical activity", r"work out", r"\bgym\b"],
    "sexual":      [r"sexual", r"sexually active", r"\bpartners?\b", r"contracept",
                    r"birth control", r"\bcondom"],
    "obgyn":       [r"menstrua", r"\bperiods?\b", r"\blmp\b", r"pregnan"],
    "travel":      [r"\btravel", r"\btrip\b", r"been abroad", r"\bexposure"],
    "concern":     [r"worried", r"worries you", r"concern", r"what do you think"],
}
_TOPIC_RES = {name: [re.compile(p, re.I) for p in pats] for name, pats in TOPIC_CUES.items()}

# Shorthand list items: a bare topic word with no verb around it.
_SHORTHAND = {
    "meds": "medications", "med": "medications", "medications": "medications",
    "medication": "medications", "allergies": "allergies", "allergy": "allergies",
    "surgeries": "psh", "surgery": "psh", "surgical": "psh",
    "pmh": "pmh", "psh": "psh", "shx": "social", "fhx": "family",
    "smoking": "tobacco", "smoke": "tobacco", "tobacco": "tobacco",
    "drinking": "alcohol", "drink": "alcohol", "alcohol": "alcohol",
    "drugs": "drugs", "name": "name", "age": "age",
    "occupation": "occupation", "job": "occupation",
}
# The ordinary question each shorthand topic stands for. Re-expanding shorthand
# into a real question lets the existing reviewed routes answer it, instead of
# adding a second, parallel matcher that could disagree with them.
TOPIC_QUESTION = {
    "name": "what is your name", "age": "how old are you", "sex": "what is your sex",
    "occupation": "what do you do for work", "household": "who do you live with",
    "chief_complaint": "what brings you in today",
    "onset": "when did it start", "duration": "how long does it last",
    "location": "where is it", "radiation": "does it spread anywhere",
    "quality": "what does it feel like", "severity": "how bad is it",
    "timing": "how often does it happen", "chronology": "has it changed since it started",
    "aggravating": "does anything make it worse", "alleviating": "does anything make it better",
    "treatment": "have you taken anything for it", "associated": "any other symptoms",
    "past_occurrence": "has this happened before",
    "pmh": "do you have any medical problems", "psh": "have you had any surgeries",
    "medications": "what medications do you take", "allergies": "do you have any allergies",
    "family": "any family history", "tobacco": "do you smoke",
    "alcohol": "do you drink alcohol", "drugs": "do you use any recreational drugs",
    "diet": "what is your diet like", "exercise": "do you exercise",
    "sexual": "are you sexually active", "obgyn": "when was your last period",
    "travel": "have you travelled recently", "concern": "what worries you most",
}


# --------------------------------------------------------------------------
# Informal typing
# --------------------------------------------------------------------------
# Students type quickly. This rewrites casual forms into ordinary English so
# the existing matchers see a well-formed question. It is deliberately separate
# from `nlp.expand_abbreviations`, which governs CLINICAL abbreviations and has
# its own reviewed ambiguity rules that must not be disturbed.
#
# Rewriting the learner's wording cannot by itself put anything on the record:
# an answer still has to match a case fact, and evidence still comes only from
# `_say()`. The worst case for a bad rewrite is an unanswered question.
_CASUAL = [
    (r"\bur\b", "your"), (r"\bu\b", "you"), (r"\br\b", "are"),
    (r"\bthx\b", "thanks"), (r"\bplz\b", "please"), (r"\bpls\b", "please"),
    (r"\bcuz\b", "because"), (r"\bbc\b", "because"), (r"\bb/c\b", "because"),
    (r"\bw/\s*", "with "), (r"\bw/o\b", "without"),
    (r"\bhx\b", "history"), (r"\bfhx\b", "family history"),
    (r"\bshx\b", "social history"), (r"\bpmhx\b", "past medical history"),
    (r"\bpshx\b", "past surgical history"), (r"\bsx\b", "symptoms"),
    (r"\bmeds\b", "medications"), (r"\bwhats\b", "what is"),
    (r"\bhowd\b", "how did"), (r"\bwheres\b", "where is"),
    (r"\bwhens\b", "when is"), (r"\bdoesnt\b", "does not"),
    (r"\bdont\b", "do not"), (r"\bcant\b", "can not"), (r"\bive\b", "i have"),
    (r"\byoure\b", "you are"), (r"\byou'?re\b", "you are"),
    (r"\bany1\b", "anyone"),
    # Numerals are clinical information (age, dose, severity, duration), never
    # SMS shorthand: rewriting 2/4 made incorrect timelines look confirmed.
    # The same FIFE "ideas" question, asked the way people actually ask it.
    # Twenty of the twenty-four cases author the trigger as "think is
    # happening" and only four as "going on", so without this the commonest
    # phrasing of a standard CSE question reached no fact at all.
    (r"\bthink (?:is |may be |might be |could be )?going on\b", "think is happening"),
    (r"\bthink (?:is |may be |might be |could be )?causing (?:this|it|that)\b", "think is happening"),
]
_CASUAL_RES = [(re.compile(p, re.I), r) for p, r in _CASUAL]


# Discourse openers carry no clinical meaning but do block exact-form matching:
# "so what's been bothering you" is the same invitation as "what's been
# bothering you".
_DISCOURSE = re.compile(
    r"^(?:\s*(?:so|ok|okay|alright|right|well|now|and|umm?|uh|erm|hmm|"
    r"anyway|anyhow|just|then|also|actually|basically)\b[,\s]+)+", re.I)


def strip_discourse(text):
    if not text:
        return text
    stripped = _DISCOURSE.sub("", text).strip()
    # Never strip the turn down to nothing: "So?" is all discourse.
    return stripped or text


def _edits1(word):
    letters = "abcdefghijklmnopqrstuvwxyz"
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    out = set()
    for left, right in splits:
        if right:
            out.add(left + right[1:])                      # deletion
            if len(right) > 1:
                out.add(left + right[1] + right[0] + right[2:])  # transposition
            for c in letters:
                out.add(left + c + right[1:])              # substitution
        for c in letters:
            out.add(left + c + right)                      # insertion
    out.discard(word)
    return out


# Ordinary English. A word on this list is never "repaired", however close it
# sits to a clinical term in some case's trigger list.
#
# Without it the repair read any word the CURRENT case did not happen to use as
# a typo and rewrote it: "tell me more" became "tell me move" in 16 of 24 cases,
# "does it wake you at night" became "take you at right", "how far back" became
# "how far black", and "how intense would you CALL it" became "...CALF it",
# which matched a DVT pertinent-negative trigger and took checklist credit for
# a question the student never asked. Twenty-eight ordinary words were being
# rewritten into clinical terms this way.
#
# Being a real word is the test, not being in this case's triggers -- a case
# that happens to mention "calf" must not change what "call" means.
COMMON_ENGLISH = frozenset("""
a able about above across act actual actually add admit afraid after afternoon again against age ago
agree ahead all allow almost alone along already also although always among amount and another answer
any anybody anymore anyone anything anyway appear are area arm around arrive as ask asleep at ate
attack away baby back bad bag band bar bath be bear beat became because become bed been before began
begin behind being believe below bend beside best better between big bit bite black bleed blood blow
blue board boat body book both bother bottle bottom box boy break breath bring broad broke brother
brought brown build burn bus business busy but buy by call came can cannot car care carry case catch
caught cause certain chair chance change check chest child choose city class clean clear climb close
clothes cold come comfort common company complete concern condition control cook cool copy corner could
count couple course cover crack cross cry cup current cut dad daily damage dark date daughter day dead
deal dear decide deep degree describe desk detail did die difference different difficult dinner direct
dirty discuss do doctor does dog done door doubt down draw dream dress drink drive drop dry due during
each ear earlier early easier easy eat edge effect effort eight either else empty end enjoy enough enter
entire equal even evening event ever every everybody everyone everything exact except exercise expect
explain extra eye face fact fail fair fall family far farther fast father fear feel feet fell felt few
field fight fill final find fine finger finish fire first fit five fix flat floor flow fly follow food
foot for force forget form forward found four free fresh friend from front full fun further future gain
game gas gave general get girl give glad glass go god goes going gone good got great green grew ground
group grow guess had hair half hand hang happen happy hard has hat hate have he head hear heard heart
heat heavy held help her here herself hey high him himself his hit hold hole home hope horse hospital
hot hour house how however hurt husband ice idea if ill imagine important improve in inch include
increase indeed inside instead interest into is issue it its itself job join jump just keep kept key
kick kid kill kind knee knew know known lack lady land large last late later laugh lay lead learn least
leave led left leg length less let letter level lie life lift light like likely line list listen little
live local long look lose loss lost lot loud love low lunch machine made main major make man many mark
marry match matter may maybe me mean meant meet member memory men mention met middle might mile milk
mind mine minute miss mom moment money month moon more morning most mother mouth move movie much must
my myself name near nearly neck need neighbor neither never new news next nice night nine no nobody
none noon nor normal north nose not note nothing notice now number nurse of off offer office often oil
okay old on once one only open or order other otherwise ought our ours ourselves out outside over own
page pain pair paper parent part party pass past pay people perfect perhaps period person phone pick
picture piece place plain plan plant play please point poor position possible pour power practice
prefer prepare present press pretty prevent probably problem produce program promise protect prove
provide public pull push put question quick quiet quite race radio raise ran rate rather reach read
ready real realize really reason receive recent record red reduce refuse regular remain remember remove
repeat reply report require rest result return rich ride right ring rise risk road rock role roll room
round row rub rule run safe said sale salt same sat save saw say scale school science sea search season
seat second see seem seen self sell send sense sent serious serve service set settle seven several
shall shape share sharp she sheet ship shoe shop short should shoulder shout show shut sick side sign
silence similar simple since sing single sir sister sit site situation six size skin sky sleep slight
slow small smell smile smoke snow so social soft some somebody someone something sometime somewhat
somewhere son song soon sore sorry sort sound south space speak special speed spend spent spoke sport
spot spread spring stage stair stand standard star start state stay step stick still stomach stone stop
store story straight strange street stress stretch strike strong struck student study stuff subject
succeed such sudden suffer sugar suggest summer sun supply suppose sure surface surprise sweet swim
system table take taken talk tall taste teach team tear tell ten term test than thank that the their
them themselves then there these they thick thin thing think third this those though thought three
through throw thus tie tight time tiny tire to today together told tomorrow tone tonight too took top
total touch toward town track trade train travel treat tree trip trouble true trust truth try turn
twelve twenty twice two type unable under understand union unit unless until up upon upper us use
useful usual value various very view visit voice wait wake walk wall want war warm was wash watch water
way we wear week weight welcome well went were west what whatever when whenever where whether which
while white who whole whom whose why wide wife will win wind window wine wing winter wire wise wish
with within without woman women wonder wood word wore work world worry worse worst would write written
wrong wrote yard year yes yesterday yet you young your yours yourself
""".split())


def repair_typos(text, vocabulary):
    """Correct obvious single-character slips against a known vocabulary.

    "wher is teh pain" is an ordinary way for a student to type under time
    pressure. Correction is deliberately conservative -- one edit, words of
    four characters or more, and only when exactly ONE vocabulary word is a
    candidate, so an ambiguous slip is left alone rather than guessed into a
    different question. The caller applies this only after normal matching has
    already failed, so a repair can turn a miss into a hit but can never
    change an answer that was already working.
    """
    if not text or not vocabulary:
        return text
    out, changed = [], False
    for token in text.split():
        core = re.sub(r"[^a-z]", "", token.lower())
        if len(core) < 3 or core in vocabulary or core in COMMON_ENGLISH:
            out.append(token)
            continue
        candidates = _edits1(core) & vocabulary
        pick = _best_repair(core, candidates)
        if pick:
            out.append(pick)
            changed = True
        else:
            out.append(token)
    return " ".join(out) if changed else text


def _best_repair(word, candidates):
    """Choose a correction only when the intent is clear.

    Two typing slips are common and unambiguous enough to act on even when
    several vocabulary words are one edit away: a dropped letter, which leaves
    the typo as a PREFIX of the intended word ("wher" -> "where"), and a
    transposition ("hwo" -> "how"). Everything else must be a unique match, so
    an ambiguous slip is left alone rather than guessed into a different
    question.
    """
    if not candidates:
        return None
    prefix = sorted(c for c in candidates if c.startswith(word))
    if len(prefix) == 1:
        return prefix[0]
    swaps = sorted(c for c in candidates if sorted(c) == sorted(word) and c != word)
    if len(swaps) == 1:
        return swaps[0]
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def casual_expand(text):
    """Rewrite quick informal typing into ordinary words."""
    if not text:
        return text
    out = text
    for pattern, replacement in _CASUAL_RES:
        out = pattern.sub(replacement, out)
    return re.sub(r"\s+", " ", out).strip()


def expand_bare_topic(segment):
    """Turn a bare topic fragment ("age", "meds") into a real question.

    Only a fragment with no question structure of its own is expanded, so an
    actual question is never rewritten into a different one.
    """
    stripped = re.sub(r"^(?:please\s+)|(?:\s+please)$", "",
                      segment.strip(" ?.!,"), flags=re.I)
    words = re.findall(r"[a-z]+", stripped.lower())
    if not words or len(words) > 3:
        return segment
    if re.search(r"\b(?:what|when|where|why|how|who|which|is|are|do|does|did|have|has|can|could|tell)\b",
                 stripped, re.I):
        return segment
    direct = _SHORTHAND.get(" ".join(words)) or (_SHORTHAND.get(words[0]) if len(words) == 1 else None)
    if direct:
        return TOPIC_QUESTION[direct]
    found = topics_in(stripped)
    if len(found) == 1:
        return TOPIC_QUESTION[found[0]]
    return segment


# A SUBJECT topic can stand on its own: "do you smoke" names what it is about.
# An ATTRIBUTE topic cannot: "how much?" and "how long?" are questions about
# whatever was last being discussed. Separating the two is what stops a bare
# follow-up from being answered out of the wrong history -- "do you smoke?" /
# "how long?" must reach the smoking history, never the chest pain's onset.
SUBJECT_TOPICS = {
    "name", "age", "sex", "occupation", "household", "chief_complaint",
    "location", "radiation", "associated", "past_occurrence", "pmh", "psh",
    "medications", "allergies", "family", "tobacco", "alcohol", "drugs",
    "diet", "exercise", "sexual", "obgyn", "travel", "concern",
}
ATTRIBUTE_TOPICS = {
    "onset", "duration", "quality", "severity", "timing", "chronology",
    "aggravating", "alleviating", "treatment",
}
# Only these subjects anchor a bare follow-up. The HPI subjects are left out on
# purpose: every HPI attribute already shares one implicit subject -- the
# presenting symptom -- and the reviewed aspect matcher routes them correctly.
# Anchoring there would confine "how bad is it?" to the location fact that was
# just discussed. These subjects are the ones where the same attribute word
# genuinely collides across different histories ("how long" after smoking).
ANCHORABLE_SUBJECTS = {
    "tobacco", "alcohol", "drugs", "medications", "allergies", "pmh", "psh",
    "family", "occupation", "household", "diet", "exercise", "sexual",
    "obgyn", "travel",
}
# A fact's own authored category is a far better statement of what it is about
# than words that happen to appear in its text: the allergy answer "no
# allergies to any medicines" mentions medicines but is not medication history.
CATEGORY_TOPIC = {
    "medications": "medications", "allergies": "allergies", "pmh": "pmh",
    "psh": "psh", "family": "family", "obgyn": "obgyn",
    "chief_complaint": "chief_complaint", "location": "location",
    "radiation": "radiation", "past_occurrence": "past_occurrence",
}
# Social facts share one category, so they are separated by their fact id.
SOCIAL_ID_TOPIC = {
    "tobacco": "tobacco", "smok": "tobacco", "alcohol": "alcohol",
    "drink": "alcohol", "drug": "drugs", "occupation": "occupation",
    "work": "occupation", "household": "household", "live": "household",
    "diet": "diet", "exercise": "exercise", "sexual": "sexual",
    "travel": "travel", "caffeine": "diet",
}
# Bare attribute follow-ups that carry no topic word of their own.
BARE_FOLLOWUP = re.compile(
    r"^(?:and\s+|so\s+|ok(?:ay)?\s+)?(?:how (?:much|many|long|often|bad|severe|come)|"
    r"since when|what (?:kind|type|about it)|how'?s that|for how long|"
    r"anything else about (?:it|that)|what happens|when|where|why)\b[^?]{0,24}\??$", re.I)


# "Tell me more" is a question about whatever was just said. Answering it from
# the opening statement ignores the topic the learner is actually pursuing.
ELABORATION = re.compile(
    r"^(?:and\s+|so\s+|ok(?:ay)?[,\s]+)?(?:tell me more|say more|a bit more|"
    r"can you (?:tell me more|say more|explain|elaborate)|could you explain|"
    r"explain that|elaborate|go on|what do you mean|what does that mean|"
    r"more about (?:that|it)|anything (?:more|else) about (?:that|it))\b",
    re.I)


# The attributes of the presenting symptom. They elaborate one another: asked
# for more about the pain, another attribute of that same pain is genuinely
# more about it, whereas the smoking history is a change of subject.
HPI_FAMILY = {
    "chief_complaint", "onset", "chronology", "location", "radiation",
    "quality", "severity", "timing", "setting", "aggravating", "alleviating",
    "treatment", "associated", "past_occurrence",
}


def is_elaboration(text):
    return bool(text and ELABORATION.match(text.strip()))


def subjects_in(text):
    """Only the stand-alone topics named by this text."""
    return [t for t in topics_in(text) if t in SUBJECT_TOPICS]


def is_bare_followup(text):
    """A turn that asks about an attribute without naming its subject."""
    if not text or not text.strip():
        return False
    stripped = text.strip()
    if len(stripped.split()) > 7:
        return False
    if subjects_in(stripped):
        return False
    return bool(BARE_FOLLOWUP.match(stripped) or
                (topics_in(stripped) and not subjects_in(stripped)))


def topics_in(text):
    """Canonical topics this text mentions, in the order they appear."""
    if not text:
        return []
    found = []
    for name, patterns in _TOPIC_RES.items():
        position = None
        for pattern in patterns:
            match = pattern.search(text)
            if match and (position is None or match.start() < position):
                position = match.start()
        if position is not None:
            found.append((position, name))
    return [name for _, name in sorted(found)]


# Some shorthand names a GROUP of histories rather than one. "SHx?" asks for
# the social history, which is tobacco, alcohol and drugs.
SHORTHAND_GROUPS = {
    "shx": ["tobacco", "alcohol", "drugs"],
    "social history": ["tobacco", "alcohol", "drugs"],
    "social hx": ["tobacco", "alcohol", "drugs"],
}


def _shorthand_group(ask):
    key = re.sub(r"[^a-z ]", "", ask.lower()).strip()
    topics = SHORTHAND_GROUPS.get(key)
    return [TOPIC_QUESTION[t] for t in topics] if topics else None


def _shorthand_list(ask):
    """Read "meds allergies surgeries?" -- bare topic words, no verb."""
    words = re.findall(r"[a-z]+", ask.lower())
    words = [w for w in words if w not in ("any", "and", "or", "your", "you", "the", "please")]
    if not 2 <= len(words) <= 5:
        return None
    topics = []
    for word in words:
        topic = _SHORTHAND.get(word)
        if topic is None:
            return None
        if topic not in topics:
            topics.append(topic)
    if len(topics) < 2:
        return None
    return [TOPIC_QUESTION[t] for t in topics]


def _clean(part):
    part = part.strip().strip(",;")
    part = re.sub(r"^(?:and|also|then|so|plus)\s+", "", part, flags=re.I)
    return part.strip()


def _distribute_list(ask):
    """Turn "any X, Y, or Z" into ["any X", "any Y", "any Z"].

    Returns None when the ask is not a distributable list, which is the common
    case; the caller then keeps the ask whole.
    """
    if _NOT_A_LIST.search(ask):
        return None
    match = _LIST_STEM.match(ask)
    if not match:
        return None
    stem = match.group("stem").strip()
    items = [i.strip(" ?.") for i in _ITEM_SPLIT.split(match.group("items")) if i.strip(" ?.")]
    items = [i for i in items if i]
    if len(items) < 2:
        return None
    # Every item must be a short noun phrase, or this is a sentence that merely
    # contains a comma rather than a list of topics.
    if any(len(i.split()) > _MAX_ITEM_WORDS for i in items):
        return None
    # A stem ending in its own noun ("do you have chest pain") already carries a
    # topic; distributing it would duplicate that topic onto every item.
    return ["%s %s" % (stem, item) for item in items]


# --------------------------------------------------------------------------
# Conversational acts
# --------------------------------------------------------------------------
# A clinician turn is not always a request for clinical information. It may
# answer something the PATIENT asked, reassure, acknowledge, instruct, or move
# the interview along. Reading that FIRST is what stops "no" -- a direct answer
# to the patient's own question -- from being pushed into the clinical matcher
# and coming back as "I don't know how to answer that".
#
# These patterns identify the ACT only. What the act means depends entirely on
# the question it is answering, which is resolved in patient.py: "no" is
# reassurance after "will you judge me?" and permission-refused after "should I
# keep going?". Nothing here assigns a fixed meaning to a bare yes or no.
_ACTS = [
    ("reassure", r"^(?:no[,.\s]+)?(?:i'?m not here to judge|i'?m not judging|no one is judging|"
                 r"nobody is judging|there'?s nothing to be ashamed of|you'?ve done nothing wrong|"
                 r"you haven'?t done anything wrong|that'?s (?:okay|ok|alright|fine)|"
                 r"it'?s (?:okay|ok|alright|fine)|no judgement|no judgment|"
                 r"take your time|don'?t worry|please don'?t worry)\b"),
    ("deny",    r"^(?:no|nope|nah|not at all|of course not|certainly not|absolutely not|"
                r"definitely not|never|no way|not really)\b"),
    ("affirm",  r"^(?:yes|yeah|yep|yup|sure|of course|absolutely|certainly|definitely|"
                r"please do|go ahead|please|that'?s right|correct|okay|ok|alright)\b"),
    # An honest "I don't know yet" is a real answer to a patient's question and
    # one a student should be able to give. Without it the turn fell through to
    # the clinical matcher and the patient answered a question about her own
    # symptoms instead -- the worst possible response to a voiced fear.
    ("defer",   r"^(?:i (?:don'?t|do not) know(?: yet)?|i'?m not (?:sure|certain)(?: yet)?|"
                r"i am not sure(?: yet)?|that'?s what (?:we|i)'?(?:re| am) (?:going to )?(?:find out|figure out)|"
                r"we'?(?:ll| will) (?:find out|figure (?:it|that) out)|let'?s find out|"
                r"i can'?t say (?:yet|for sure)|too early to say|"
                r"that'?s what (?:the|these) tests? (?:are|is) for)\b"),
]
_ACT_RES = [(name, re.compile(p, re.I)) for name, p in _ACTS]

# A turn that is ONLY a conversational act - short, no clinical topic of its
# own. A longer turn that merely begins with "no" is handled by segmentation,
# so the clinical half is not lost.
_MAX_ACT_WORDS = 12


# A clinician narrating their OWN action is not asking for clinical history.
# "I'm going to wash my hands before we start." contains the words "start" and
# "before", which are trigger words on the onset and past-episode facts, so
# without this it is answered with a symptom history. What the turn is DOING
# has to be read before deciding what information it wants.
#
# Deliberately first-person and procedural. "Let me ask you about your
# medications" and "Let's talk about your allergies" are NOT matched: those are
# invitations to discuss a topic, and answering them is right.
_SELF_NARRATION = re.compile(
    r"^(?:\s*(?:ok(?:ay)?|alright|right|so|now|first|next)[,\s]+)*"
    r"(?:i'?m going to|i am going to|i'?m about to|i am about to|i'?ll|i will|"
    r"let me|i'?d like to|i would like to|i want to|i need to)\s+"
    r"(?!ask\b|talk\b|discuss\b|go over\b|review\b|hear\b|start by asking\b)",
    re.I)
# Procedural verbs that confirm the narration is an action, not a question in
# disguise. Keeps "I'll be honest with you" out.
_ACTION_VERB = re.compile(
    r"\b(?:wash|sanitiz|clean|glove|drape|cover|examine|exam|listen|auscultat|"
    r"palpat|press|feel|percuss|inspect|look at|check|measure|take your|"
    r"lower|raise|lift|position|help you|move|step out|step outside|"
    r"give you a moment|get a chaperone|wear|put on|warm)\b", re.I)


def is_self_narration(text):
    """Is this the clinician describing an action they are about to perform?

    A turn that also asks something is NOT self-narration: it is compound, and
    the question deserves its answer.
    """
    if not text:
        return False
    stripped = text.strip()
    if "?" in stripped:
        return False
    if re.search(r"\b(?:what|when|where|why|how|which|who|do you|did you|have you|"
                 r"are you|can you|could you|is there|any\b)", stripped, re.I):
        return False
    return bool(_SELF_NARRATION.match(stripped) and _ACTION_VERB.search(stripped))


# Signalling understanding between questions ("got it", "that makes sense") is
# a graded rapport behaviour, so students type it constantly. It asks for
# nothing: answering it by re-reading the last fact makes the patient sound as
# though the student had missed the answer.
_BACKCHANNEL = re.compile(
    r"^(?:i see|got it|gotcha|understood|noted|makes sense|that makes sense|"
    r"that'?s (?:helpful|good to know|useful)|that is helpful|good to know|"
    r"i appreciate (?:that|it|you (?:sharing|telling me))|"
    r"thank you(?: for (?:sharing|telling me|explaining))?|thanks(?: for that)?|"
    r"mm-?hmm|uh-?huh|fair enough|of course|sure)"
    r"[\s.,!]*$", re.I)

# The student DECLARING the interview over, as opposed to inviting questions
# ("do you have any questions for me?"), which _CLOSURE_CUES already reads.
_CLOSING_STATEMENT = re.compile(
    r"\b(?:that'?s all (?:of )?(?:my |the )?questions|that is all (?:my |the )?questions|"
    r"i think that'?s (?:all|everything|it)|that covers (?:it|everything)|"
    r"no (?:more|further|other) questions|nothing else (?:for now|from me)|"
    r"thank you for your time|thanks for your time|i'?m (?:all )?done(?: asking)?|"
    r"we'?re (?:all )?done|that'?s everything i needed|i have everything i need)\b", re.I)


_GREETING_ONLY = re.compile(
    r"^(?:good\s+)?(?:hello|hi|hey|morning|afternoon|evening|good morning|"
    r"good afternoon|good evening|greetings)\b[\s,.!\u2014-]*"
    r"(?:(?:mr|mrs|ms|dr|miss)\.?\s+[a-z'\-]+)?[\s,.!]*$", re.I)


def is_greeting_only(text):
    """A turn fragment that only says hello."""
    return bool(text) and bool(_GREETING_ONLY.match(text.strip()))


_CLARIFICATION_OPENER = re.compile(
    r"^\s*(?:no|nope|sorry|actually|well|um|uh|hang on|hold on|wait)?[,\s]*"
    r"(?:i\s+(?:mean|meant)|i\s*'?m\s+asking|i\s+was\s+asking|"
    r"what\s+i\s+mean(?:t)?\s+(?:is|was)|to\s+be\s+clear|let\s+me\s+rephrase)"
    r"[,:\s]*$", re.I)


_LEAD_IN = re.compile(
    r"^\s*(?:"
    r"(?:thanks|thank you)(?:\s+(?:for|so much|very much)\b.*)?"
    r"|that (?:must|has to|sounds like it must) be\b.*"
    r"|i (?:hear|understand|appreciate|can imagine|get)\s+(?:you|that|what)\b.*"
    r"|i(?:'|\u2019)?m? ?(?:am )?going to help\b.*"
    r"|i(?:'|\u2019)?ll help\b.*"
    r"|we(?:'|\u2019)?ll (?:sort|work) (?:this|it) out\b.*"
    r"|before (?:you go|we (?:finish|go|move on|wrap up))\b.*"
    r"|one (?:more|last) thing\b.*"
    r"|(?:so )?remind me\b.*"
    r"|just so i (?:have|get) (?:it|this) right\b.*"
    r"|(?:okay|ok|alright|right)(?:,)? (?:let(?:'|\u2019)?s|moving on|next)\b.*"
    r")[\s.,!?\u2014-]*$", re.I)


def is_lead_in(segment):
    """A courtesy, an empathic line or a transition -- it asks nothing.

    "Thanks for telling me all that. What makes it worse?" splits in two, and
    the first half was counted as an ask nobody answered, so a correct reply
    picked up "I'm not sure. What do you mean exactly?" -- and, in the worst
    case, a claim that an authored fact was unavailable.
    """
    return bool(_LEAD_IN.match((segment or "").strip()))


def is_clarification_opener(segment):
    """A fragment that only announces a correction and asks nothing itself.

    "I mean, how long each headache lasts?" splits into "I mean" and the real
    question. Treated as its own ask, the first half reaches nothing and the
    patient tacks a confusion line onto a perfectly good answer. The correction
    that follows is the question; this half is punctuation.
    """
    return bool(_CLARIFICATION_OPENER.match((segment or "").strip()))


def is_backchannel(text):
    """A turn that only signals understanding and asks for nothing."""
    return bool(text) and bool(_BACKCHANNEL.match(text.strip()))


def is_closing_statement(text):
    """The clinician saying the interview is finished."""
    return bool(text) and bool(_CLOSING_STATEMENT.search(text))


def read_act(text):
    """Name the conversational act a clinician turn performs, or None.

    Returns 'reassure', 'deny' or 'affirm'. The caller decides what that means
    against whatever question is actually open.
    """
    if not text:
        return None
    stripped = text.strip().strip('.!,')
    if len(stripped.split()) > _MAX_ACT_WORDS:
        return None
    for name, pattern in _ACT_RES:
        if pattern.match(stripped):
            return name
    return None


# What counts as a REASSURING answer depends on how the patient framed the
# question, and the framings genuinely differ in polarity:
#
#   worry       "Will I have to have surgery?"        reassured by NO
#   hope        "Will I be able to speak again?"      reassured by YES
#   permission  "Could I just go home?"               granted by YES
#   other       anything else                         acknowledged neutrally
#
# Getting this wrong would be worse than not answering, so an unclassifiable
# question is acknowledged without claiming to have reassured anyone.
_HOPE_QUESTION = re.compile(
    r"\b(?:be able to|able to|get better|getting better|recover|be okay|be ok|"
    r"be fine|be alright|go back to normal|back to normal|heal|improve|"
    r"still (?:work|drive|walk|play))\b", re.I)
_PERMISSION_QUESTION = re.compile(
    r"\b(?:should i|shall i|can i|may i|could i|could we|can we|"
    r"do you want me to|would you like me to|is it (?:okay|ok|alright) if|"
    r"do i need to|do i have to|just (?:go home|wait|rest))\b", re.I)
_WORRY_QUESTION = re.compile(
    r"\b(?:judge|judging|judgement|judgment|blame|blaming|think less of|look down|"
    r"disappointed|angry|upset|mad at|mind (?:that|if)|in trouble|my fault|"
    r"did i (?:do|cause)|too late|dying|going to die|cancer|heart attack|stroke|"
    r"tumou?r|infection|damage|lose|losing|serious|surgery|operation|catheter|"
    r"contagious|give this to|mean (?:i|that|this))\b", re.I)


def question_frame(text):
    """How a patient question is framed - this decides which answer reassures."""
    if not text:
        return "other"
    # Hope is checked first: "will I be able to walk again?" also contains
    # "lose"-adjacent worry vocabulary in some phrasings, but its reassuring
    # answer is yes.
    if _HOPE_QUESTION.search(text):
        return "hope"
    # Worry is checked BEFORE permission: "Could I give this to the people at
    # home?" is phrased as a permission question but is really a contagion
    # worry, and answering "yes" to it reassures nobody.
    if _WORRY_QUESTION.search(text):
        return "worry"
    if _PERMISSION_QUESTION.search(text):
        return "permission"
    return "other"


def answers_question(act, frame):
    """Does this act RESOLVE such a question, and was it reassuring?

    Returns (resolves, reassuring) where `reassuring` is True, False, or None
    when the framing does not let us say. None means: acknowledge, do not claim
    to have been reassured.
    """
    if act is None:
        return (False, None)
    # Honest uncertainty resolves the question -- the patient has been answered
    # -- but it is not reassurance and must not be scored as if it were.
    if act == "defer":
        return (True, None)
    positive = act == "affirm"
    negative = act in ("deny", "reassure")
    if frame == "worry":
        if act == "reassure" or negative:
            return (True, True)
        if positive:
            return (True, False)
    elif frame == "hope":
        if positive:
            return (True, True)
        if act == "reassure":
            return (True, True)
        if negative:
            return (True, False)
    elif frame == "permission":
        if positive:
            return (True, True)
        if negative:
            return (True, False)
    else:
        # Unclassifiable framing: an explicit reassurance still reassures;
        # a bare yes/no is acknowledged without assuming which way it lands.
        if act == "reassure":
            return (True, True)
        if positive or negative:
            return (True, None)
    return (False, None)


# A patient line becomes a PENDING QUESTION when it asks the clinician
# something answerable. Punctuation alone is not enough - it must actually put
# a question to the clinician, either in the second person ("are you going
# to...") or about the patient's own situation ("will I...", "does this
# mean..."), which is what these cases overwhelmingly do.
_ASKS_CLINICIAN = re.compile(
    r"\b(?:are|do|did|will|would|can|could|should|have|is|does|am)\s+(?:you|i|we|this|that|it|my)\b"
    r"|\byou\s+(?:going to|gonna|think|mind|want)\b"
    r"|\b(?:should|can|may|shall|could)\s+i\b"
    r"|\bwhat (?:should|do|happens) i?\b|\bdo you want me\b|\bwould you like me\b"
    r"|\bis (?:that|this|it) what\b", re.I)
# A question the patient answers themselves in the same breath is rhetorical.
_RHETORICAL = re.compile(r"\b(?:you know|right)\?\s*$", re.I)


def is_question_to_clinician(text):
    if not text:
        return False
    tail = text.strip()
    if not tail.endswith("?") or _RHETORICAL.search(tail):
        return False
    # Use the final sentence: "My father had cancer. Is that what this is?"
    last = re.split(r"(?<=[.!])\s+", tail)[-1]
    # An auxiliary-initial question ("Will a catheter hurt?", "Does needing to
    # pee at night mean cancer?") is being put to the clinician even though its
    # subject is neither "you" nor "I".
    if re.match(r"^\s*(?:will|does|do|did|is|are|am|can|could|should|would|have|has)\b",
                last, re.I):
        return True
    return bool(_ASKS_CLINICIAN.search(last))


def _topic_conjunction(ask):
    """Split "name and reason for visit" -- two topics joined by "and".

    The general splitter needs a question word after "and". This handles the
    noun-phrase form, and only when each half names a DIFFERENT topic, so
    "left arm and jaw" and "fever and chills" stay whole.
    """
    if " and " not in ask.lower() or _NOT_A_LIST.search(ask):
        return None
    halves = re.split(r"\s+and\s+", ask, maxsplit=1, flags=re.I)
    if len(halves) != 2:
        return None
    left, right = (h.strip(" ?.,") for h in halves)
    if not left or not right:
        return None
    if len(left.split()) > 4 or len(right.split()) > 5:
        return None
    left_topics, right_topics = topics_in(left), topics_in(right)
    if not left_topics or not right_topics:
        return None
    if set(left_topics) & set(right_topics):
        return None
    return [left, right]


# Titles and common abbreviations whose full stop is not a sentence boundary.
_ABBREVIATION = re.compile(
    r"\b(?:dr|mr|mrs|ms|prof|st|sr|jr|approx|vs|etc|e\.g|i\.e)\.", re.I)


def segment(utterance):
    """Split a turn into the separate things it asks, in the order asked.

    Always returns at least one segment. A single-ask turn returns exactly
    [utterance] so the caller can detect that nothing needs composing.
    """
    if not utterance or not utterance.strip():
        return [utterance]
    utterance = casual_expand(utterance)
    # A title's full stop is not a sentence boundary. "I'm working with Dr.
    # Lee. What brought you in?" used to split into "...with Dr", "Lee" and the
    # question, and the stray fragment cost the turn its opening.
    utterance = _ABBREVIATION.sub(lambda m: m.group(0)[:-1] + "\u2024", utterance)
    group = _shorthand_group(utterance)
    if group:
        return group
    raw = [_clean(p).replace("\u2024", ".") for p in _NEW_ASK.split(utterance)]
    parts = [p for p in raw if p]
    if not parts:
        return [utterance]

    if len(parts) == 1:
        joined = _topic_conjunction(parts[0])
        if joined:
            parts = joined

    expanded = []
    for part in parts:
        items = _shorthand_group(part) or _shorthand_list(part) or _distribute_list(part)
        expanded.extend(items if items else [part])

    # Drop fragments that carry no askable content of their own.
    expanded = [p for p in expanded if re.search(r"[a-z]", p, re.I)]
    if len(expanded) <= 1:
        return [utterance]
    return [expand_bare_topic(p) for p in expanded]


# --------------------------------------------------------------------------
# Joining answers
# --------------------------------------------------------------------------
_SENTENCE_END = re.compile(r"[.!?]\s*$")


def _terminate(text):
    text = text.strip()
    if not text:
        return text
    return text if _SENTENCE_END.search(text) else text + "."


def _dedupe(parts):
    """Drop repeats without reordering.

    Two asks can legitimately reach the same authored fact ("where is it and
    does it move?" when a case answers both from one sentence). Saying that
    sentence twice in one breath is the most obviously robotic failure mode.
    """
    seen, out = set(), []
    for part in parts:
        key = nlp.normalize(part).strip(" .")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(part)
    return out


def _is_continuation(previous, nxt):
    """Was `nxt` authored as the tail of `previous` rather than a new sentence?

    Many history facts are authored as deliberate pairs -- "Hypertension" plus
    "no known thyroid or structural heart disease." -- meant to read as one
    clause. Joined with a bare space they become an ungrammatical run-on:
    "Hypertension no known thyroid or structural heart disease."
    """
    if not previous or not nxt:
        return False
    if _SENTENCE_END.search(previous):
        return False
    first = nxt.lstrip()[:1]
    # A lowercase opener after an unterminated fragment continues it. A capital
    # letter starts a new sentence, and "I" is a sentence of its own.
    return bool(first) and first.islower()


def join_spoken(parts):
    """Join authored fact lines into one grammatical utterance.

    Each line is preserved VERBATIM. Only the separator between lines changes,
    so the delivery contract -- which matches a fact's approved text inside the
    line it was spoken in -- is completely unaffected.
    """
    parts = _dedupe([p.strip() for p in parts if p and p.strip()])
    if not parts:
        return ""
    out = parts[0]
    for nxt in parts[1:]:
        if _is_continuation(out, nxt):
            out += ", " + nxt
        else:
            out = _terminate(out) + " " + nxt
    return _terminate(out)


def join(parts):
    """Combine answered parts into one reply, in the order they were asked."""
    return join_spoken(parts)
