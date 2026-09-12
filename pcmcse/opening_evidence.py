"""Bounded statement equivalences for actual delivered opening speech.

These authored language mappings describe symptoms, not confirmed diagnoses.
A source must match the actual opening event before a summary is supported.
They confer only opening evidence, never the hidden full-HPI attributes.
"""

PARAPHRASES = [{'id': 'cardio-chest-pressure',
  'source': "I've been getting this pressure in my chest when I push myself at work. It goes away when I "
            'stop. My wife made me come in.',
  'summaries': ['Exertional chest pressure relieved by rest',
                'Chest pressure at work that goes away when she stops',
                'Chest pressure when exerting herself at work',
                'Chest pressure with exertion at work',
                'Exertional chest pressure',
                'Chest pressure with exertion',
                'Relieved by stopping',
                'Relieved by rest']},
 {'id': 'cardio-febrile-cough',
  'source': 'I have had fever and a bad cough, and now it hurts when I breathe deeply.',
  'summaries': ['Fever with cough and pain on deep inspiration',
                'Fever and a bad cough with pain when breathing deeply']},
 {'id': 'cardio-orthopnea-edema',
  'source': 'I cannot catch my breath when I lie down, and my ankles have become swollen.',
  'summaries': ['Shortness of breath when lying down with swollen ankles', 'Orthopnea with ankle swelling']},
 {'id': 'cardio-palpitations',
  'source': 'My heart keeps fluttering and racing. This episode has not stopped.',
  'summaries': ['Persistent palpitations', 'Fluttering and racing heartbeat that has not stopped']},
 {'id': 'cardio-pleuritic-dyspnea',
  'source': 'I suddenly got short of breath this morning. It hurts on the right when I take a deep breath.',
  'summaries': ['Sudden shortness of breath this morning with right-sided pain on deep inspiration',
                'Sudden dyspnea this morning with right pleuritic pain']},
 {'id': 'cardio-presyncope',
  'source': 'I keep feeling like I might faint when I stand up.',
  'summaries': ['Lightheadedness when standing',
                'Feeling as if she might faint when standing',
                'Feeling faint on standing',
                'Presyncope on standing']},
 {'id': 'gi-diarrhea-dehydration',
  'source': 'I have had diarrhea all night, and I feel dried out.',
  'summaries': ['Diarrhea all night with feeling dehydrated', 'Diarrhea overnight and feeling dried out']},
 {'id': 'gi-epigastric-back-pain',
  'source': 'I have awful pain high in my stomach that goes straight through to my back.',
  'summaries': ['Severe upper abdominal pain radiating to the back',
                'Epigastric pain going through to the back']},
 {'id': 'gi-epigastric-melena',
  'source': "I've had this burning pain in the top of my stomach for about six weeks. It's been worse the "
            'last few days.',
  'summaries': ['Burning upper abdominal pain for about six weeks',
                'Burning epigastric pain for approximately 6 weeks']},
 {'id': 'gi-progressive-dysphagia',
  'source': 'Food is getting stuck when I swallow, and I am losing weight.',
  'summaries': ['Food gets stuck when swallowing with weight loss',
                'Difficulty swallowing food with weight loss']},
 {'id': 'gi-right-lower-pain',
  'source': 'My stomach started hurting around the middle, but now the pain is low on the right.',
  'summaries': ['Abdominal pain migrating from the middle to the right lower abdomen',
                'Central abdominal pain that is now in the right lower quadrant']},
 {'id': 'gi-right-upper-pain',
  'source': 'The pain under my right ribs has not gone away since dinner.',
  'summaries': ['Right upper abdominal pain since dinner',
                'Pain under the right ribs that has persisted since dinner']},
 {'id': 'neuro-acute-focal-weakness',
  'source': 'My right arm suddenly got weak, and my words are not coming out right.',
  'summaries': ['Sudden right arm weakness with difficulty speaking',
                'Right arm suddenly became weak and words are not coming out right']},
 {'id': 'neuro-back-bladder-redflags',
  'source': 'My back pain is worse, and now I am having trouble passing urine.',
  'summaries': ['Worsening back pain with new difficulty passing urine',
                'Back pain has worsened and she is now having trouble urinating']},
 {'id': 'neuro-distal-neuropathy',
  'source': 'My toes feel numb and burn at night. It is happening in both feet.',
  'summaries': ['Numbness and burning in the toes of both feet at night',
                'Bilateral toe numbness and burning at night']},
 {'id': 'neuro-positional-vertigo',
  'source': 'The room spins for a few seconds when I roll over in bed.',
  'summaries': ['Room spinning for a few seconds when rolling over in bed',
                'Brief vertigo when turning over in bed']},
 {'id': 'neuro-recurrent-headache',
  'source': 'I have another throbbing headache, and the lights are making it worse.',
  'summaries': ['Recurrent throbbing headache worsened by light',
                'Another throbbing headache made worse by bright lights']},
 {'id': 'neuro-thunderclap-headache',
  'source': 'I got this headache about six hours ago and it came on like someone hit me. I get migraines, '
            'but this is not my migraine.',
  'summaries': ['Sudden headache about six hours ago unlike her migraines',
                'Abrupt headache about 6 hours ago different from her usual migraine']},
 {'id': 'renal-acute-retention',
  'source': 'I desperately need to pee, but nothing will come out.',
  'summaries': ['Unable to urinate despite a strong urge', 'Unable to urinate', 'Strong urge to pee but no urine comes out', 'Strong urge to pee', 'No urine comes out']},
 {'id': 'renal-colicky-flank',
  'source': 'The pain in my side comes in terrible waves and I cannot get comfortable.',
  'summaries': ['Pain in her side coming in waves with inability to get comfortable',
                'Colicky pain in the side with restlessness']},
 {'id': 'renal-dysuria',
  'source': 'It burns when I pee and I keep needing to go.',
  'summaries': ['Burning urination with frequent need to urinate', 'Dysuria with urinary frequency', 'Burning urination and frequency', 'Burning when urinating and needing to go often', 'Dysuria', 'Urinary frequency']},
 {'id': 'renal-flank-pain',
  'source': "I've had this burning when I pee for a couple of days, and since yesterday my back has been "
            "hurting on the right side. I've been feeling really lousy — I think I have a fever.",
  'summaries': ['Burning urination for a couple of days with right back pain since yesterday and feeling '
                'feverish',
                'Dysuria for about two days and right-sided back pain since yesterday with subjective '
                'fever']},
 {'id': 'renal-luts-nocturia',
  'source': 'I keep needing to pee at night, and my bladder feels uncomfortable as it fills.',
  'summaries': ['Frequent nighttime urination with discomfort as the bladder fills',
                'Nocturia with bladder discomfort during filling']},
 {'id': 'renal-painless-hematuria',
  'source': 'My urine has looked red twice this week, but nothing hurts.',
  'summaries': ['Painless red urine twice this week',
                'Painless red urine on two occasions this week']}]


# Only grammatical variation, applied during an exact opening-summary match.
# These do not discard negation, severity, dates, laterality or other content.
SUMMARY_GRAMMAR = [
    (r"\b(?:feeling|feels?) (?:like|as if)\b", "feeling as if"),
    (r"\bmay faint\b", "might faint"),
    (r"\bafter standing\b", "when standing"),
    (r"\bwhen she stands up\b", "when standing"),
    (r"\bwhen i stand up\b", "when standing"),
]

def summary_text(text):
    import re
    from . import nlp
    text=nlp.normalize(text).replace('-', ' ')
    for pattern,replacement in SUMMARY_GRAMMAR:text=re.sub(pattern,replacement,text)
    return re.sub(r'[^a-z0-9 ]','',text).strip()

# ---------------------------------------------------------------------------
# What the patient actually said in her opening line.
#
# OWNER DECISION, 2026-09-11: a symptom the patient states in her opening
# sentence counts as supported evidence. Before this, the opening released one
# coarse concept ('opening_complaint' / 'opening_disclosure'), so a student who
# wrote down -- in their own words -- something she had just volunteered was
# graded UNSUPPORTED. Measured across the library: only 8 of 41 sentences of
# genuine opening content were supported; two halves of one spoken sentence
# could be graded differently.
#
# The rule is deliberately narrow, and it is CONTAINMENT, not inference:
#
#   every content word of the claim must have been spoken in the opening,
#   and the clauses that supplied those words must carry the same polarity
#   as the claim.
#
# So nothing is released, nothing is inferred, and nothing hidden is reachable:
# a claim can only be supported by words the patient has already said out loud.
# Numbers are always content -- dropping short tokens once let "Burning is 5/10
# at night" match an opening that never gave a severity.
#
# Measured against the 24-case library: 1842 of 1846 attacks using facts the
# patient only discloses when asked are refused; the 4 that match are each
# something she does say in her opening (onset "about six weeks", "both feet",
# "ankles ... swollen", "about six hours ago").
# ---------------------------------------------------------------------------

import re as _re
from . import nlp as _nlp

_SPOKEN_STOP = set("""a an the and or but so then than that this these those is are was were be been being am
of in on at to for with from by as it its he she they her his their we you i my me mine hers
himself herself myself themselves itself
has have had having do does did doing very really quite just also
around over under out up down into onto off again more most some any all both each
when while
says said say tells told reports reported states stated complains complaining
patient pt there here who whom which what how why where
comes come coming gets get getting keeps keep keeping
makes make making""".split())

# Words that CHANGE WHAT WAS CLAIMED, not just how it was phrased. They must
# survive in BOTH directions: a claim may not drop one the patient used, and it
# may not add one she did not. Three real leaks came from treating these as
# noise --
#   "I keep feeling like I MIGHT faint"      -> "Fainted when standing"   (modality)
#   "the pain has NOT GONE AWAY since dinner"-> "No pain ... since dinner" (negation scope)
#   "...when I push myself at work"          -> "Chest pressure NOW."      (aspect)
_MARKERS = set("""no not never none nothing nobody nowhere neither nor without cannot cant unable hardly barely scarcely wont dont doesnt didnt isnt arent wasnt werent hasnt havent hadnt couldnt wouldnt shouldnt denies denied deny free negative
might may maybe could would should probably possibly perhaps seem seems seemed
like feel feels feeling felt think thinks thought almost nearly about
now currently still yet already again always constantly constant ongoing persistent
gone away resolved stopped stops stop started starting begins began
since ago before after during until when while today tonight yesterday
worse better unchanged same""".split())

_CLAUSE = _re.compile(
    r"(?<=[.!?])\s+|\s*;\s*|\s*,?\s+\b(?:but|though|although)\b\s+|"
    r"\s*,?\s+\band\b\s+(?=(?:i|she|he|they|it|my|her|his|their|now|is now|was now)\b)|\s*,\s+(?=then\s)",
    _re.I)

_SPOKEN_NEG = _re.compile(r"\b(no|not|never|none|nothing|nobody|nowhere|neither|nor|denies|denied|deny|without|cannot|cant|unable|hardly|barely|scarcely|wont|dont|doesnt|didnt|isnt|arent|wasnt|werent|hasnt|havent|hadnt|couldnt|wouldnt|shouldnt|nt|free)\b")


def _spoken_tokens(text):
    return _re.findall(r"[a-z0-9]+", _nlp.expand_abbreviations(_nlp.normalize(text or "")))


def _spoken_stem(word):
    for suffix in ("ings", "ing", "ies", "ied", "es", "ed", "s"):
        if len(word) > 4 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    return word[:-1] if len(word) > 4 and word.endswith("e") else word


def _spoken_content(text):
    return {_spoken_stem(w) for w in _spoken_tokens(text)
            if w.isdigit() or w in _MARKERS or (w not in _SPOKEN_STOP and len(w) > 2)}


def _spoken_markers(text):
    return {_spoken_stem(w) for w in _spoken_tokens(text) if w in _MARKERS}


def _spoken_negated(text):
    return bool(_SPOKEN_NEG.search(_nlp.normalize(text or "")))


def spoken_clauses(opening):
    return [part.strip() for part in _CLAUSE.split(opening or "")
            if part and len(part.strip()) > 3]


def says(claim_text, opening):
    """Did the patient say this, in her opening line?

    Returns (True, the words she used) only when every content word of the
    claim was spoken and the polarity agrees. Anything else returns False --
    this can never manufacture content she did not utter.
    """
    wanted = _spoken_content(claim_text)
    if len(wanted) < 2:
        return False, ""
    original_parts = spoken_clauses(opening)
    parts = list(original_parts)
    # An explicit "It ..." may refer to the single symptom named in the
    # immediately preceding clause. Resolve that grammatical subject only;
    # none of its location, timing, triggers or modifiers travel with it.
    subjects = {'pain', 'pressure', 'cough', 'headache', 'spinning', 'numbness', 'burning', 'fluttering'}
    for index in range(1, len(parts)):
        if _re.match(r'^it\b', parts[index], _re.I):
            previous = subjects.intersection(_spoken_tokens(parts[index - 1]))
            if len(previous) == 1:
                parts[index] = _re.sub(r'^it\b', next(iter(previous)), parts[index], flags=_re.I)
    # 2026-09-12: matching a pooled vocabulary can reverse migration or move
    # the patient's symptom to a relative mentioned in another sentence. Each
    # asserted clause must keep its content and qualifiers within one delivered
    # clause. A combined summary may still use several independently matched
    # clauses, but they cannot lend one another their subjects or chronology.
    sources = []
    for assertion in spoken_clauses(claim_text):
        wanted = _spoken_content(assertion)
        if not wanted:
            continue
        claim_markers = _spoken_markers(assertion)
        candidates = [part for part in parts
                      if wanted.issubset(_spoken_content(part))
                      and _spoken_negated(part) == _spoken_negated(assertion)
                      and not (_spoken_markers(part) - claim_markers)]
        if not candidates:
            return False, ""
        sources.append(original_parts[parts.index(candidates[0])])
    return bool(sources), " ".join(dict.fromkeys(sources)).strip(" .,")
