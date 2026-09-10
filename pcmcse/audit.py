"""Claim-by-claim documentation audit.

Every factual sentence in the note is checked against the encounter evidence
record -- never against the hidden case.  A fact being true of the patient does
not make it documentable; the student has to have obtained it.

Verdicts
--------
supported      obtained during the encounter and documented accurately
supported_supplied  rests on authorized station information (vitals, results)
unsupported    nothing in the encounter produced this
contradicts    the encounter established the opposite
overbroad      broader than the examination or questions actually covered
misplaced      accurate, but filed in the wrong SOAP section
hypothesis     an Assessment entry: a clinical guess, not a claim about facts
proposed       a Plan entry: a future action, not a completed one
counseling_ok / counseling_unsupported  a claim that a discussion happened
not_evaluated  no concept could be resolved; reported honestly, never scored

The tone is deliberate.  The literature on this (Walling 2011) found that most
apparent over-documentation traces to imprecision or system error rather than
intent, so findings are phrased as documentation errors with the evidence
shown, never as accusations.
"""

from __future__ import annotations

import re
from . import evidence

from . import claims as claims_mod
from . import lexicon, nlp, physexam
from . import vital_evidence, opening_evidence
from . import scoped_claims

# Claims that assert a discussion took place.
# Past tense in any grammatical dress. A note that says "patient education
# provided regarding antibiotic compliance" asserts that a conversation
# happened just as plainly as "I educated the patient", and the nominal form is
# the one students actually write. Reading only the active verbs let every
# nominalised claim through unchecked.
_COUNSEL_PAST = [
    "discussed", "counseled", "counselled", "educated", "advised", "instructed",
    "explained", "reviewed with", "informed the patient", "warned",
    "went over", "taught",
    "education provided", "education given", "education was provided",
    "counseling provided", "counselling provided", "counseling given",
    "counselling given", "counseling was", "counselling was",
    "advice given", "advice provided", "instructions given",
    "instructions provided", "reassurance provided", "reassurance given",
    "teaching provided", "teaching given", "verbalized understanding",
    "verbalised understanding", "questions answered", "consent obtained",
]
_COUNSEL_FUTURE = [
    "will discuss", "will educate", "will advise", "plan to discuss",
    "educate the patient", "advise the patient", "counsel the patient",
    "provide education", "discuss return precautions", "instruct the patient",
]

# Objective-flavoured content that does not belong in Subjective, and vice
# versa (INTRO p. 24: "Information in the wrong section; ie. Heart regular
# in the subjective").
_OBJECTIVE_MARKERS = [
    "regular rate and rhythm", "rrr", "clear to auscultation", "cta",
    "bowel sounds", "murmur", "tenderness to palpation", "no rebound",
    "guarding", "tympanitic", "percussion", "auscultation", "s1 and s2",
    "pupils equal", "perla", "cva tenderness", "nondistended", "non-distended",
    "tissue texture", "somatic dysfunction", "capillary refill",
]
_SUBJECTIVE_MARKERS = [
    "denies", "complains of", "c/o", "reports", "states that", "admits to",
    "patient says", "she says", "he says", "no known drug allergies",
    "family history", "lives with", "occupation", "worried that",
]

# Assertions that reach further than the maneuver actually performed.
OVERBREADTH_RULES = [
    {
        "pattern": r"\bcn\s*(i|1)\s*[-–to]+\s*(xii|12)\b|\bcranial nerves?\s*(i|1)\s*[-–to]+\s*(xii|12)\b",
        "maneuver": "neuro_cn",
        "requires": None,
        "message": "Cranial nerve I (olfaction) is not part of the cranial nerve "
                   "screen you performed. Document the nerves you actually tested.",
        "always_overbroad": True,
    },
    {
        "pattern": r"\bcn\s*(ii|2)\s*[-–to]+\s*(xii|12)\b|\bcranial nerves?\s*(ii|2)\s*[-–to]+\s*(xii|12)\b|\bcranial nerves? intact\b",
        "maneuver": "neuro_cn",
        "requires": ["cn ii", "cn iii-iv-vi", "cn v", "cn vii", "cn viii",
                     "cn ix-x", "cn xi", "cn xii"],
        "message": "A claim about the full cranial nerve set needs the full "
                   "screen. Document only the nerves you tested.",
    },
    {
        "pattern": r"\banterior and posterior\b|\ball (lung )?fields\b|\bsix (lung )?fields\b",
        "maneuver": "lungs_auscultate",
        "requires": ["anterior", "posterior"],
        "message": "You documented anterior and posterior lung fields. The "
                   "auscultation you performed did not cover both.",
    },
    {
        "pattern": r"\bfour quadrants\b|\b4 quadrants\b|\ball quadrants\b",
        "maneuver": "abd_palpate",
        "requires": ["four quadrants"],
        "message": "A four-quadrant claim needs a four-quadrant examination.",
        "alt_maneuvers": ["abd_percuss", "abd_auscultate"],
    },
    {
        "pattern": r"\bbilateral(ly)? cva\b|\bcva tenderness bilateral",
        "maneuver": "abd_special",
        "requires": ["cva tenderness"],
        "message": "A bilateral CVA statement needs both sides assessed.",
    },
    {
        "pattern": r"\b(5/5|full) strength (in all|throughout|all extremities)\b",
        "maneuver": "msk_strength",
        "requires": ["upper extremity", "lower extremity"],
        "message": "Strength in all extremities needs upper and lower "
                   "extremities tested.",
    },
    {
        "pattern": r"\bdtrs? 2\+ throughout\b|\breflexes 2\+ throughout\b",
        "maneuver": "neuro_reflexes",
        "requires": ["biceps", "triceps", "patellar", "achilles"],
        "message": "'Throughout' asserts every reflex you list. Document the "
                   "ones you elicited.",
    },
]

_VITALS_TERMS = ["bp", "blood pressure", "hr", "heart rate", "pulse", "temp",
                 "temperature", "rr", "respiratory rate", "pulse ox", "spo2",
                 "o2 sat", "weight", "height", "bmi", "vitals", "afebrile",
                 "febrile"]


def _concept_map(case):
    """Core concepts plus the case's own, with duplicates removed.

    A case that models "fever" as `fever_subjective` must switch off the core
    `fever` concept, or one patient answer produces two concept ids and the
    audit reports a phantom omission (or worse, a phantom contradiction).
    """
    m = dict(lexicon.CORE_CONCEPTS)
    for cid in case.get("supersedes_core", []):
        m.pop(cid, None)
    case_lex = case.get("concept_lexicon") or {}
    # Safety net for the commonest authoring hazard: a case that models a
    # pertinent negative as `no_cough` leaves the core `cough` concept live, so
    # one sentence releases two concept ids and the audit reports a phantom
    # contradiction. A core concept is superseded when one of its surfaces is
    # contained in a case surface -- "cough" inside "no cough".
    case_surfaces = [nlp.normalize(x) for forms in case_lex.values() for x in forms]
    for cid in list(m):
        if cid in case_lex:
            continue
        core_surfaces = [nlp.normalize(x) for x in m[cid]]
        if any(len(cs) >= 4 and any(cs in xs for xs in case_surfaces)
               for cs in core_surfaces):
            m.pop(cid, None)
    for cid, forms in case_lex.items():
        if cid in m:
            merged = list(m[cid])
            merged += [f for f in forms if f not in merged]
            m[cid] = merged
        else:
            m[cid] = list(forms)
    return m


def _claim_polarity(text, surface):
    return "negative" if nlp.is_negated(text, surface) else "positive"


def _is_counseling(text):
    t = nlp.normalize(text)
    if any(c in t for c in _COUNSEL_FUTURE):
        return "future"
    if any(re.search(r"\b" + re.escape(c), t) for c in _COUNSEL_PAST):
        return "past"
    return None


def _counsel_topics(text, case):
    """Which plan topics a counselling claim refers to."""
    topics = []
    edu = (case.get("plan_expectations") or {}).get("education", [])
    for item in edu:
        if nlp.matches_any(text, [item]):
            topics.append(item)
    for generic in ["return precaution", "red flag", "warning sign", "hydration",
                    "diet", "medication", "smoking", "follow up", "side effect",
                    "full course", "hygiene"]:
        if generic in nlp.normalize(text):
            topics.append(generic)
    return sorted(set(topics))



# Family comparisons bind an entire spoken clause to the same relative.
# Numeric age, disease, death and negation tokens are retained.
_FAMILY_ONES = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19}
_FAMILY_TENS = {'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90}
_FAMILY_FORMS = [('\\b(?:heart attack|myocardial infarction|mi)\\b', 'infarction'), ('\\b(?:high blood pressure|htn)\\b', 'hypertension'), ('\\bdm\\b', 'diabetes'), ('\\b(?:deceased|died)\\b', 'died'), ('\\bmom\\b', 'mother'), ('\\bdad\\b', 'father')]
_FAMILY_FILL = set(['my', 'is', 'has', 'have', 'with', 'a', 'an', 'and', 'at', 'age', 'aged', 'years', 'old', 'of', 'the', 'was'])
def _family_clause(text):
    t = nlp.normalize(text)
    for word,value in _FAMILY_TENS.items():
        t=re.sub(r'\b'+word+r'(?:[- ]('+ '|'.join(list(_FAMILY_ONES)[1:10])+r'))?\b',lambda m:str(value+_FAMILY_ONES.get(m.group(1),0)),t)
    t=re.sub(r'\b(?:'+'|'.join(_FAMILY_ONES)+r')\b',lambda m:str(_FAMILY_ONES[m.group()]),t)
    for pattern,replacement in _FAMILY_FORMS:t=re.sub(pattern,replacement,t)
    return [w for w in re.findall(r'[a-z0-9]+',t) if w not in _FAMILY_FILL]

def _family_evidence(claim,ledger):
    if claim.get('section')!='S' or claim.get('header')!='fh':return None
    target=_family_clause(claim['text'])
    relatives=[w for w in target if w in ('mother','father','brother','sister')]
    if len(relatives)!=1:return None
    owner=relatives[0];candidates=[]
    for ev in ledger.by_kind(evidence.PATIENT):
        ids=[cid for cid in ev.get('meta',{}).get('concepts',{}) if cid.startswith('fh_'+owner+'_')]
        if not ids:continue
        for clause in re.split(r'[.;!?]',ev['text']):
            source=_family_clause(clause)
            if source and source[0]==owner:candidates.append((source,ev,ids))
    for source,ev,ids in candidates:
        if target==source or (not any(w.isdigit() for w in target) and target==[w for w in source if not w.isdigit()]):
            return {'verdict':'supported','concepts':ids,'evidence':[_ev(ev)],'explanation':'The relative, age and health information match the actual patient answer.'}
    for source,ev,ids in candidates:
        if [w for w in target if not w.isdigit()]==[w for w in source if not w.isdigit()]:
            return {'verdict':'contradicts','concepts':[],'evidence':[_ev(ev)],'explanation':'The documented age disagrees with the actual answer for this relative.'}
    return None


def _verbatim_obtained(claim, ledger):
    """Exact complete evidence clauses outrank lossy topic/polarity aliases.

    Require a clause boundary on both sides and preserve inherited negation.
    A substring such as 'fever' inside 'denies fever' is deliberately rejected.
    Source kind remains section-specific. No hidden case definition is read.
    """
    def normalize_clause(value):
        if claim['section']=='O':
            value=re.sub(r"\b([ctl]\d{1,2})\s*(?:through|to|[-–—])\s*([ctl]\d{1,2})\b",r"\1-\2",value,flags=re.I)
        return nlp.normalize(value)
    allowed = (evidence.PATIENT,) if claim["section"] == "S" else (evidence.EXAM_FINDING, evidence.STATION_INFO)
    target = normalize_clause(claim.get("eval_text") or claim["text"]).strip(" .;,:")
    if len(target.split()) < 2:
        return None
    for ev in ledger.events:
        if ev["kind"] not in allowed:
            continue
        raw = ev["text"]
        # Join complete independently punctuated findings without changing their
        # wording or polarity. Commas are deliberately excluded: 'no rebound,
        # guarding' can inherit negation and must not become 'with guarding'.
        if claim['section'] == 'O':
            clauses=[normalize_clause(x).strip(' .') for x in re.split(r';|(?<!\d)\.(?!\d)',raw) if nlp.normalize(x)]
            if len(clauses)==2 and all(len(x.split())>=2 for x in clauses):
                if target in [join.join(clauses) for join in (' with ',' and ')]:
                    return ev
        boundaries = [0] + [m.end() for m in re.finditer(r"[;,!?]|(?<!\d)\.|\.(?!\d)", raw)] + [len(raw)]
        for i,start in enumerate(boundaries[:-1]):
            for end in boundaries[i+1:i+6]:
                source = normalize_clause(raw[start:end]).strip(" .;,:!?")
                if target.strip("!?") == source:
                    return ev
    return None


# 2026-09-08: bounded clinical paraphrases. These identify asserted attributes;
# only released evidence can authorize them. Case definitions supply categories,
# never a substitute for the patient's actual answer.
_TIME_VALUE = re.compile(r"\b(\d+(?:\.\d+)?)\s*[- ]?\s*(seconds?|secs?|s|minutes?|mins?|min|hours?|hrs?|h|days?|d|weeks?|wks?|wk|months?|mos?)\b")
_TIME_UNITS = {'s':'second','sec':'second','second':'second','min':'minute','minute':'minute','h':'hour','hr':'hour','hour':'hour','d':'day','day':'day','wk':'week','week':'week','mo':'month','month':'month'}
_LOCATION_FORMS = {
 'right lower abdomen': r'\brlq\b|\bright lower (?:abdom\w*|quadrant|side)\b|\blow on the right\b',
 'left lower abdomen': r'\bllq\b|\bleft lower (?:abdom\w*|quadrant|side)\b|\blow on the left\b',
 'right upper abdomen': r'\bruq\b|\bright upper (?:abdom\w*|quadrant|side)\b|\b(?:under (?:my |the )?)?right (?:ribs|costal margin)\b',
 'left upper abdomen': r'\bluq\b|\bleft upper (?:abdom\w*|quadrant|side)\b|\b(?:under (?:my |the )?)?left (?:ribs|costal margin)\b',
 'lower midline abdomen': r'\bsuprapubic\b|\blower (?:central|midline) abdom\w*\b|\blow in the center of (?:my |the )?abdomen\b|\bcenter of (?:my |the )?lower abdomen\b',
 'central abdomen': r'\bperiumbilical\b|\bcentrally\b|\baround (?:my |the )?(?:belly button|umbilicus|middle)\b|\bcentral (?:abdom\w*|pain)\b',
 'left flank':r'\bleft (?:flank|side of (?:my |the )?back)\b',
 'right flank':r'\bright (?:flank|side of (?:my |the )?back)\b',
 'substernal chest':r'\bsubsternal\b|\bbehind (?:my |the )?breastbone\b|\bcenter of (?:my |the )?chest\b',
}

def _times(text):
    out=[]
    for m in _TIME_VALUE.finditer(nlp.normalize(text)):
        unit=m.group(2) if m.group(2) in _TIME_UNITS else m.group(2).rstrip('s')
        out.append((m.group(1),_TIME_UNITS.get(unit,unit)))
    return out

def _locations(text):
    t=nlp.normalize(text)
    found=[key for key,pattern in _LOCATION_FORMS.items() if re.search(pattern,t)]
    if "lower midline abdomen" in found and "central abdomen" in found: found.remove("central abdomen")
    return found


_MODIFIER_TRIGGERS = {
 'breathing':r'\b(?:deep (?:breath\w*|inspiration)|inspir\w*|breath\w*)\b',
 'eating':r'\b(?:eat\w*|meals?|food)\b',
 'position':r'\b(?:position\w*|postur\w*)\b',
 'movement':r'\b(?:movement|moving|bending)\b',
 'exertion':r'\b(?:exertion|exert\w*|exercise|exercising)\b',
 'rest':r'\brest(?:ing)?\b',
 'urination':r'\b(?:urination|urinating|voiding)\b',
}
_PATTERN_FORMS = {'constant':r'\b(?:constant|continuous|persistent|all the time)\b',
                  'intermittent':r'\b(?:intermittent|comes? and goes?|episodic)\b'}
_RADIATION_FORMS = {'right scapula':r'\bright (?:scapul\w*|shoulder blade)\b',
                   'left scapula':r'\bleft (?:scapul\w*|shoulder blade)\b'}
def _modifier_atoms(text):
    out={};clauses=[]
    for part in re.split(r'[;.,]|\bbut\b',text):
        part=nlp.normalize(part)
        effects=re.findall(r'\b(?:worsen\w*|aggravat\w*|exacerbat\w*|improv\w*|reliev\w*|relief|helps?|helped|eas\w*)\b',part)
        clauses.extend(re.split(r'\band\b',part) if len(effects)>1 else [part])
    for clause in clauses:
        m=re.search(r'\b(?:worsen\w*|aggravat\w*|exacerbat\w*|improv\w*|reliev\w*|relief|helps?|helped|eas\w*)\b',clause)
        if not m:continue
        effect='aggravates' if re.match(r'worsen|aggravat|exacerbat',m.group()) else 'relieves'
        if nlp.is_negated(clause,m.group()) or re.search(r'\bno (?:\w+ ){0,3}$',clause[:m.start()]):effect='not_'+effect
        for k,pattern in _MODIFIER_TRIGGERS.items():
            if re.search(pattern,clause):out[k]=effect
    return out

# Atomic examination attributes are intentionally small and compositional.
# Positive support requires every meaningful word to be accounted for. A
# generic maneuver or a shared adjective never authorizes an extra finding.
_EXAM_ATOM_PATTERNS = {
 'distention':r'\b(?:non[ -]?distended|not distended|no disten(?:tion|sion)|distended|disten(?:tion|sion))\b',
 'scar':r'\bscars?\b',
 'murphy':r'\b(?:(?:positive|negative) murphy(?:s)?(?: sign| maneuver)?|(?:(?:no|without) )?inspiratory arrest)\b',
 'rhythm':r'\b(?:irregular|regular) (?:cardiac |heart )?(?:rate and )?rhythm\b',
 'murmur':r'\bmurmurs?\b', 'wheeze':r'\bwheez(?:e|es|ing)\b',
 'crackles':r'\b(?:crackles|rales)\b', 'edema':r'\b(?:edema|swelling)\b',
}
_EXAM_FILLERS = set('during subcostal palpation murphy maneuver sign a an the is are was were with and of to on in without no not absent present noted heard seen auscultated detected abdomen abdominal heart cardiac lungs lung skin extremities lower extremity upper examination exam inspection auscultation rate breath sounds normal'.split())
def _exam_atoms(text):
    t=nlp.normalize(text);atoms={};used=[]
    for key,pattern in _EXAM_ATOM_PATTERNS.items():
        for m in re.finditer(pattern,t):
            used.append(m.span());v=m.group()
            if key=='rhythm':value='irregular' if v.startswith('irregular') else 'regular'
            else:value='absent' if v.startswith(('non','not ','no ','without ','negative ')) or re.search(r'\b(?:no|not|without|absent)(?:\s+\w+){0,3}\s*$',t[max(0,m.start()-45):m.start()]) else 'present'
            if key=='murphy' and key in atoms and atoms[key]!=value:value='inconsistent'
            atoms[key]=value
            if key=='scar' and value=='present':
                window=t[max(0,m.start()-70):m.end()]
                for name,pattern2 in {'state':r'\b(?:healed|fresh|open|unhealed)\b','vertical':r'\b(?:lower|upper)\b','side':r'\b(?:right|left|midline|central)\b'}.items():
                    mm=list(re.finditer(pattern2,window))
                    if mm:
                        x=mm[-1];atoms['scar_'+name]=x.group();offset=max(0,m.start()-70);used.append((offset+x.start(),offset+x.end()))
    # Negation and laterality cannot be discarded as generic filler.
    for key in ['murmur','wheeze','crackles','edema','murphy']:
        if key in atoms:
            for m in re.finditer(r'\b(?:bilateral(?:ly)?|right|left)\b',t):
                atoms[key+'_side']='bilateral' if m.group().startswith('bilateral') else m.group();used.append(m.span())
    residue=''.join(' ' if any(a<=i<b for a,b in used) else ch for i,ch in enumerate(t))
    unknown=[w for w in re.findall(r'[a-z0-9]+',residue) if w not in _EXAM_FILLERS]
    return atoms,not unknown

def _relevant_exam_events(claim,ledger):
    header=claim.get('header');regions={'abdomen':'Abdomen','heart':'Heart','lungs':'Lungs','skin':'Skin','msk':'Musculoskeletal','neuro':'Neurologic','heent':'HEENT'}
    region=regions.get(header);out=[]
    families=set(nlp.find_concepts(claim.get('eval_text') or claim['text'],lexicon.EXAM_CLAIM_CONCEPTS))
    if not region:return out
    for ev in ledger.by_kind(evidence.EXAM_FINDING):
        man=physexam.CATALOG_BY_ID.get(ev['meta'].get('maneuver_id'),{})
        if man.get('region')==region and ev['meta'].get('concepts') and (not families or man.get('claim_concept') in families):out.append(ev)
    return out

def _atomic_exam(claim,ledger):
    if claim['section']!='O':return None
    atoms,complete=_exam_atoms(claim.get('eval_text') or claim['text'])
    if not atoms:return None
    sources=_relevant_exam_events(claim,ledger)
    if not sources:return {'verdict':'unsupported','concepts':[],'evidence':[], 'explanation':'No corresponding finding was released during this encounter. An examination action alone does not establish its result.'}
    available={};links={}
    for ev in sources:
        actual,_=_exam_atoms(ev['text'])
        for k,v in actual.items():available[k]=v;links[k]=ev
    disagreements=[k for k,v in atoms.items() if k in available and available[k]!=v]
    if disagreements:
        return {'verdict':'contradicts','concepts':[], 'evidence':[_ev(links[k]) for k in disagreements], 'explanation':'The documented examination attribute differs from the released finding: '+', '.join(disagreements)+'.'}
    if complete and all(k in available for k in atoms):
        evs={links[k]['seq']:links[k] for k in atoms};concepts=sorted({cid for ev in evs.values() for cid in ev['meta'].get('concepts',{})})
        return {'verdict':'supported','concepts':concepts,'evidence':[_ev(ev) for ev in evs.values()], 'explanation':'Every documented examination attribute matches a finding actually released during this encounter.'}
    return {'verdict':'not_evaluated','concepts':[],'evidence':[_ev(ev) for ev in sources[-3:]], 'explanation':'Relevant findings were released, but this wording could not be fully resolved. Compare it with the linked evidence; this is not a proven false statement and receives no automatic credit.'}

def _daily_medication_history(claim, case, ledger):
    if claim['section'] != 'S' or claim.get('header') != 'meds':
        return None
    grammar = r"(?:(?:i|she|he|the patient) )?(?:no|takes? no|do not take|does not take) daily (?:medication|medications|medicine|medicines|meds)"
    canonical = lambda t: nlp.normalize(t).strip(' .')
    if not re.fullmatch(grammar, canonical(claim['text'])):
        return None
    ids = {cid for fact in case.get('facts', []) if fact.get('category') == 'medications' for cid in fact.get('concepts', {})}
    for ev in ledger.by_kind(evidence.PATIENT):
        for cid, spec in ev['meta'].get('concepts', {}).items():
            value = spec if isinstance(spec, str) else spec.get('value', '')
            # Both the scoped released concept and the actual spoken clause
            # must state daily non-use. PRN/OTC use is a separate history item.
            if cid in ids and re.fullmatch(grammar, canonical(value)) and any(re.fullmatch(grammar, canonical(part)) for part in re.split(r'[.;!?]', ev['text'])):
                return {'verdict': 'supported', 'concepts': [cid], 'evidence': [_ev(ev)], 'explanation': 'The patient explicitly reported no daily medication. This does not establish absence of occasional, over-the-counter, or prior medication use.'}
    return {'verdict': 'unsupported', 'concepts': [], 'evidence': [], 'explanation': 'No delivered answer establishes absence of daily medication. Ask about medication use before documenting this negative.'}


def _current_symptom_state(text):
    """Complete present-state sentence, not a lifetime or exertional history.

    An explicit current-time anchor is required. Additional duration, score,
    radiation, triggers, or other symptoms deliberately fall outside this grammar.
    """
    t = nlp.normalize(text).strip(" .")
    t = re.sub(r"^(?:the patient |patient |she |he |i )", "", t)
    t = re.sub(r"^reports (?:having )?", "", t)
    t = re.sub(r"^currently (.+)$", r"\1 currently", t)
    t = re.sub(r"\bat rest (?:during this encounter|right now|now|currently|at this moment)\b", "now while resting here", t)
    t = re.sub(r"\b(?:during this encounter|right now|now|currently|at this moment) at rest\b", "now while resting here", t)
    vertigo = re.fullmatch(
        r"(?P<state>no|denies(?: having)?|do not have|does not have|am not having|is not having|free of|is free of|have|has|having|am having|is having) "
        r"(?:vertigo|spinning|room spinning) (?P<time>right now|now|currently|at this moment)"
        r"(?P<rest> while (?:(?:i am|she is|he is|the patient is) )?keeping (?:my|her|his|the) head still)?", t)
    room = re.fullmatch(r"(?:the )?room is (?P<neg>not )?spinning (?:right now|now|currently|at this moment)(?P<rest> while (?:(?:i am|she is|he is) )?keeping (?:my|her|his) head still)?", t)
    if vertigo or room:
        present = (vertigo.group('state') in ('have','has','having','am having','is having')) if vertigo else not bool(room.group('neg'))
        return {'subject': 'vertigo', 'present': present, 'rest': bool((vertigo or room).group('rest'))}
    m = re.fullmatch(
        r"(?P<state>no|denies(?: having)?|do not have|does not have|"
        r"am not having|is not having|free of|is free of|have|has|having|am having|is having) "
        r"chest (?:pain|pressure) (?P<time>right now|now|currently|at this moment)"
        r"(?P<rest> while (?:(?:i am|she is|he is|the patient is) )?resting(?: here)?)?", t)
    if not m:
        return None
    return {"subject": "chest_pain", "present": m.group('state') in ('have', 'has', 'having', 'am having', 'is having'),
            "rest": bool(m.group('rest'))}


def _current_status_history(claim, case, ledger):
    if claim['section'] != 'S' or claim.get('header') not in ('cc', 'hpi', 'ros', None):
        return None
    target = _current_symptom_state(claim['text'])
    if target is None:
        return None
    eligible = []
    for fact in case.get('facts', []):
        if not fact.get('requires_current_status_question') or 'current_status' not in fact.get('question_dimensions', []) or target['subject'] not in fact.get('current_status_subjects', []):
            continue
        for ev in ledger.by_kind(evidence.PATIENT):
            ids = [cid for cid in fact.get('concepts', {}) if cid in ev['meta'].get('concepts', {})]
            actual = _current_symptom_state(ev['text'])
            if ids and actual is not None and actual['subject'] == target['subject']:
                eligible.append((actual, ev, ids))
    if not eligible:
        return {'verdict': 'unsupported', 'concepts': [], 'evidence': [],
                'explanation': 'The current symptom state was not obtained. A historical pattern does not establish what the patient is experiencing now.'}
    matches = [item for item in eligible if item[0]['present'] == target['present'] and (not target['rest'] or item[0]['rest'])]
    if not matches:
        contradiction = all(item[0]['present'] != target['present'] for item in eligible)
        return {'verdict': 'contradicts' if contradiction else 'unsupported', 'concepts': [], 'evidence': [_ev(item[1]) for item in eligible],
                'explanation': 'This current-state statement differs from the answer actually delivered; check its polarity and stated context.'}
    actual, ev, ids = matches[-1]
    return {'verdict': 'supported', 'concepts': ids, 'evidence': [_ev(ev)],
            'explanation': 'This matches the current symptom state actually reported. It does not document an unasked historical onset, severity, exertional trigger, or response to rest.'}


def _postural_relief(text):
    """Complete position-to-relief statements; no unmentioned extra attributes."""
    t=nlp.normalize(text).strip(' .')
    m=re.fullmatch(r'(?P<first>sitting|lying down|standing)(?: (?:or|and) (?P<second>sitting|lying down|standing))? '
                  r'(?:(?P<neg>does not|do not) )?(?:stops?|ends?|makes? (?:it|the symptoms) stop)'
                  r'(?: (?:the |my )?(?:symptoms|lightheadedness|episode))?',t)
    if not m:return None
    return {'positions':{p for p in (m.group('first'),m.group('second')) if p},'relieves':not bool(m.group('neg'))}


def _short_obtained_history(claim, case, ledger):
    """Complete, bounded rating/operative-history statements, actual speech only."""
    if claim['section'] != 'S': return None
    def canonical(text):
        t=nlp.normalize(text)
        t=re.sub(r'(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])',' ',t)
        return re.sub(r'\s+',' ',t).strip(' .')
    t=canonical(claim['text']);header=claim.get('header');wanted=[]
    score=re.fullmatch(r'(?:the )?(?:pain |it )?(?:(?:is|was|rated|rated as|severity) )?(\d{1,2})\s*(?:/|out of)\s*10',t)
    compound=re.fullmatch(r'(?:the )?pain has persisted for hours and is (\d{1,2})\s*(?:/|out of)\s*10',t)
    if header in ('hpi',None) and (score or compound):
        wanted=[('severity',(score or compound).group(1))]
        if compound:wanted.append(('timing','constant_hours'))
    elif header=='psh':
        operation=re.fullmatch(r'(?:cesarean (?:delivery|section)|c[ -]?section) (\d+) years? ago',t)
        if operation:wanted=[('psh',operation.group(1))]
    if not wanted and header in ('hpi',None):
        relief=_postural_relief(t)
        if relief:wanted=[('alleviating',relief)]
    if not wanted:return None
    links={};concepts=[]
    for category,value in wanted:
        candidates=[f for f in case.get('facts',[]) if f.get('category')==category]
        eligible=[]
        for f in candidates:
            for ev in ledger.by_kind(evidence.PATIENT):
                ids=set(f.get('concepts',{})) & set(ev['meta'].get('concepts',{}))
                if not ids:continue
                spoken=canonical(ev['text'])
                if category=='severity':
                    numbers={'zero':'0','one':'1','two':'2','three':'3','four':'4','five':'5','six':'6','seven':'7','eight':'8','nine':'9','ten':'10'}
                    # Convert only an explicitly spoken rating, never an unrelated
                    # duration, dose, or bare number in a bundled answer.
                    rated=re.sub(r'\b('+'|'.join(numbers)+r') out of (?:ten|10)\b', lambda m:numbers[m.group(1)]+'/10', spoken)
                    actual=claims_mod.ratings(rated);valid=value in actual
                elif category=='timing':
                    actual=['constant_hours'] if re.search(r'\b(?:constant|continuous|persistent|persisted)\b.*\bfor hours\b',spoken) else []
                    valid=bool(actual)
                elif category=='alleviating':
                    actual=_postural_relief(spoken)
                    valid=bool(actual and value['positions']<=actual['positions'] and value['relieves']==actual['relieves'])
                else:
                    m=re.search(r'\b(?:cesarean (?:delivery|section)|c[ -]?section) (\d+) years? ago\b',spoken)
                    actual=[m.group(1)] if m else [];valid=value in actual
                if actual:eligible.append((valid,ev,ids))
        if not eligible:
            return {'verdict':'unsupported','concepts':[],'evidence':[], 'explanation':'This specific history attribute was not delivered in the encounter. Ask and obtain the answer before documenting it.'}
        match=next((x for x in eligible if x[0]),None)
        if not match:
            return {'verdict':'contradicts','concepts':[],'evidence':[_ev(x[1]) for x in eligible], 'explanation':'The documented value differs from the history actually delivered.'}
        links[match[1]['seq']]=match[1];concepts.extend(match[2])
    return {'verdict':'supported','concepts':sorted(set(concepts)),'evidence':[_ev(e) for e in links.values()], 'explanation':'Each attribute in this statement matches the history actually delivered during the encounter.'}


def _semantic_history(text, claim, case, released, ledger):
    if claim['section'] != 'S': return {}, ''
    t=nlp.normalize(text); hits={}; defect=''
    facts=case.get('facts',[])
    fact_events=ledger.released_facts()
    def supports_for(fact):
        event=fact_events.get(fact['id'])
        out=[]
        for cid in fact.get('concepts',{}):
            if cid not in released: continue
            support=dict(released[cid])
            if event and event['kind']==evidence.PATIENT:
                spec=event['meta'].get('concepts',{}).get(cid)
                if isinstance(spec,dict):
                    support.update(value=spec.get('value',''),polarity=spec.get('polarity','positive'),source_seq=event['seq'],t_ms=event['t_ms'],quote=event['text'])
            out.append(support)
        return out
    def register(fact, valid, reason=''):
        nonlocal defect
        for cid in fact.get('concepts',{}):
            hits[cid]={'surface':text,'negated':False,'semantic_verified':bool(valid and cid in released), 'semantic_support':next((r for r in supports_for(fact) if r['concept']==cid),None)}
            if cid not in released and not valid:
                defect='UNSUPPORTED: The documented attribute was not delivered during this encounter.'
            elif cid in released and not valid:
                defect=reason or 'This attribute does not match the answer obtained in this encounter.'
    # A temporal claim in HPI is bound to onset or episode duration. LMP,
    # medication courses and follow-up intervals are deliberately excluded.
    times=_times(t)
    def time_subjects(value):
        v=nlp.normalize(value)
        return {key for key,pattern in {'weight':r'\b(?:weight loss|loss of \d+|lost (?:about )?\d+)\b','respiratory_illness':r'\b(?:sore throat|cold)\b','fatigue':r'\b(?:fatigue|tired\w*)\b'}.items() if re.search(pattern,v)}
    def time_relation(value):
        v=nlp.normalize(value)
        return 'before' if re.search(r'\b(?:before|preceded)\b',v) else 'after' if re.search(r'\b(?:after|following)\b',v) else None
    secondary_subjects=time_subjects(t)
    if times and claim.get('header') in ('hpi',None) and not re.search(r'\b(menstrual|period|lmp|take|took|medication|taken|tablets?|mg|follow|mother|father)\b',t):
        episode=bool(re.search(r'\b(each|per) (?:episode|spell|attack)|\blast\w* (?:about |roughly )?\d',t))
        temporal=[]
        candidates=[f for f in facts if f.get('category')=='onset' or f.get('temporal_role') in ('episode_duration','prior_episode_duration')]
        if secondary_subjects:candidates=[f for f in facts if time_subjects(f.get('value','')) & secondary_subjects and _times(f.get('value',''))]
        for f in candidates:
            role=f.get('temporal_role','')
            if secondary_subjects:
                relevant=True
            elif episode:
                relevant=role in ('episode_duration','prior_episode_duration')
            elif role=='first_episode_onset':
                relevant=bool(re.search(r'\b(first|initial|began experiencing|episodes began)\b',t))
            elif role=='current_episode_onset':
                relevant=bool(re.search(r'\b(current|this (?:continuous )?episode|continuous episode)\b',t))
            elif role=='urinary_symptom_onset':
                relevant=bool(re.search(r'\b(urinar\w*|bladder|void\w*)\b',t))
            elif role=='back_pain_onset':
                relevant='back' in t and not re.search(r'\b(urinar\w*|bladder|void\w*)\b',t)
            else:
                relevant=f.get('category')=='onset' and len([x for x in candidates if x.get('category')=='onset'])==1
            if relevant and not episode and not secondary_subjects:
                # Bind a duration to the symptom whose onset it describes.
                # An associated black stool or fatigue has its own chronology.
                focus=set(re.findall(r'\b(pain|pressure|burning|headache|spinning|dizz\w*|palpitat\w*|breath\w*|cough|urinar\w*|void\w*)\b',nlp.normalize(f.get('value',''))))
                if focus and not any(re.search(r'\b'+re.escape(w)+r'\b',t) for w in focus):
                    relevant=False
            if relevant: temporal.append(f)
        # Multiple times in one clause need relation binding beyond this bounded
        # parser. Keep ordinary concept audit, without guessing which owns which.
        if len(times)==1:
            for f in temporal:
                supports=supports_for(f)
                support=next((r for r in supports if _times(r.get('value',''))),None)
                actual=_times(support.get('value','')) if support else []
                if supports and not actual: continue
                relation_ok=not secondary_subjects or time_relation(t)==time_relation(support.get('value','') if support else '')
                register(f, bool(actual and all(x in actual for x in times) and relation_ok),
                         'The documented time differs from the answer you obtained: '+(support.get('value','') if support else ''))
    locs=_locations(t)
    if locs and claim.get('header') in ('hpi',None):
        # Current location is the destination in a migration sentence.
        migration=re.search(r'\b(?:migrat\w*|mov\w*|travel\w*)\b',t)
        destination=t[migration.end():] if migration else t
        dest_locs=_locations(destination)
        for f in facts:
            if f.get('category')!='location': continue
            support=next(iter(supports_for(f)),None)
            actual=_locations(support.get('value','')) if support else []
            if support and not actual:
                # Failure to parse the obtained phrase is not a contradiction.
                # Leave it unresolved for ordinary concept audit instead.
                continue
            location_negative = any(nlp.is_negated(destination, m.group(0)) for pattern in _LOCATION_FORMS.values() for m in re.finditer(pattern, destination))
            register(f,bool(actual and set(actual).issubset(dest_locs) and not location_negative),
                     'The documented location or side differs from the answer you obtained: '+(support.get('value','') if support else ''))
        # A migration is earned only when a released answer explicitly has
        # both the same origin and destination. No hidden chronology is used.
        if migration and len(locs)>=2:
            migration_matched=False
            for cid,support in released.items():
                value=support.get('value',''); source_locs=_locations(value)
                if set(locs)==set(source_locs) and re.search(r'\b(mov\w*|migrat\w*|but now|started.*now)\b',nlp.normalize(value)):
                    source_motion=re.search(r'\b(mov\w*|migrat\w*|but now|now)\b',nlp.normalize(value))
                    source_destination=_locations(nlp.normalize(value)[source_motion.end():]) if source_motion else []
                    if source_destination and set(dest_locs)==set(source_destination):
                        hits[cid]={'surface':text,'negated':False,'semantic_verified':True}
                        migration_matched=True
            if not migration_matched:
                hits['history_assertion:migration']={'surface':'migration','negated':False}
    if claim.get('header') in ('hpi',None):
        def progress(value):
            v=nlp.normalize(value)
            direction='worse' if re.search(r'\b(?:worsen\w*|worse)\b',v) else 'better' if re.search(r'\b(?:improv\w*|better)\b',v) else 'unchanged' if re.search(r'\b(?:unchanged|stayed the same)\b',v) else None
            if direction:
                matched=re.search(r'\b(?:worsen\w*|worse|improv\w*|better|unchanged|stayed the same)\b',v)
                if matched and nlp.is_negated(v,matched.group(0)):direction='not:'+direction
            return direction
        direction=progress(t)
        if direction and not re.search(r'\b(?:sitting|standing|upright|lying|supine|eating|walking|bending|coughing|inspiration)\b',t):
            for f in facts:
                if f.get('temporal_role') not in ('pattern_or_progression','progression'):continue
                support=next(iter(supports_for(f)),None)
                if not support:continue
                actual=progress(support.get('value',''))
                if actual:
                    if _times(t) and not all(x in _times(support.get('value','')) for x in _times(t)):
                        continue
                    register(f,direction==actual,'The documented progression differs from the answer you obtained: '+support.get('value',''))
    if claim.get('header') in ('hpi',None):
        modifiers=_modifier_atoms(t)
        for f in facts:
            category=f.get('category')
            source=next(iter(supports_for(f)),None)
            if category in ('aggravating','alleviating') and modifiers:
                actual=_modifier_atoms(source.get('value','')) if source else _modifier_atoms(f.get('value',''))
                shared=set(modifiers)&set(actual)
                if shared:
                    valid=bool(source) and all(modifiers[k]==actual[k] for k in shared)
                    register(f,valid,'The documented trigger or relieving effect differs from the answer you obtained: '+(source.get('value','') if source else ''))
            elif category=='timing':
                # Do not compare an associated visual/neurologic symptom's duration
                # with the chief complaint's timing.
                qualified=re.findall(r'\b(?:visual|vision|speech|numbness|weakness)\b',t)
                if qualified and not any(re.search(r'\b'+w+r'\b',nlp.normalize(source.get('value','') if source else '')) for w in qualified): continue
                requested={k for k,p in _PATTERN_FORMS.items() if re.search(p,t)}
                actual={k for k,p in _PATTERN_FORMS.items() if re.search(p,source.get('value','') if source else '')}
                if requested and actual:
                    register(f,requested==actual and not any(nlp.is_negated(t,re.search(_PATTERN_FORMS[k],t).group()) for k in requested),'The documented symptom pattern differs from the answer you obtained: '+source.get('value',''))
            elif category=='radiation':
                requested={k for k,p in _RADIATION_FORMS.items() if re.search(p,t)}
                actual={k for k,p in _RADIATION_FORMS.items() if re.search(p,source.get('value','') if source else '')}
                if requested:
                    register(f,bool(source) and requested==actual and not any(nlp.is_negated(t,re.search(_RADIATION_FORMS[k],t).group()) for k in requested),'The documented radiation or side differs from the answer you obtained: '+(source.get('value','') if source else ''))
    if re.search(r'\b(?:prn|as needed|when needed|only when needed)\b',t):
        for f in facts:
            if f.get('category')!='medications':continue
            # Bind the qualifier to the medication actually named in this
            # statement, not a different medicine elsewhere in the reply.
            matched=nlp.find_concepts(t,{cid:case.get('concept_lexicon',{}).get(cid,[]) for cid in f.get('concepts',{})})
            if not matched:continue
            sources=supports_for(f);valid=False
            for source in sources:
                for piece in re.split(r'[.;]|\band\b',source.get('value','')):
                    if any(nlp.matches_any(piece,[hit['surface']]) for hit in matched.values()) and re.search(r'\b(?:prn|as needed|when needed|only when needed)\b',nlp.normalize(piece)):
                        valid=True
            register(f,valid,'UNSUPPORTED: As-needed medication use was not established in the answer you obtained. Document the frequency actually stated.')
    # Explicit negatives are checkable statements even if their exact wording
    # was not authored as a concept alias. A denial cannot establish testing.
    for topic,pattern in [('allergies',r'\b(?:no (?:known )?(?:(?:drug|medication) )?allergies|denies (?:any )?allergies|nkda)\b'),('pregnancy',r'\b(?:denies pregnancy|not pregnant|no (?:chance|possibility) of pregnancy)\b')]:
        if not re.search(pattern,t): continue
        relevant=[f for f in facts if (f.get('category')=='allergies' if topic=='allergies' else f.get('history_topic')=='pregnancy')]
        if not relevant:
            hits['history_assertion:'+topic]={'surface':topic,'negated':True}
        for f in relevant:
            support=next(iter(supports_for(f)),None)
            value=nlp.normalize(support.get('value','')) if support else ''
            valid=bool(re.search(r'\b(no|never|not|denies|nkda|none)\b',value))
            if topic=='pregnancy' and re.search(r'\b(possible|could|might|unsure|uncertain)\b',value): valid=False
            register(f,valid,'This negative is not what the patient reported: '+(support.get('value','') if support else ''))
            if topic=='allergies' and support and not re.search(r'\b(drug|medication|nkda)\b',t) and re.search(r'\b(drug|medication)\b',value):
                defect='OVERBROAD: The encounter established medication allergies only. Document NKDA or no known medication allergies; do not broaden it to all allergies.'
    return hits,defect

def _lung_technique_claim(claim, ledger):
    """A narrowly worded action description is not itself a clinical finding."""
    if claim['section'] != 'O': return None
    t=nlp.normalize(claim.get('eval_text') or claim['text']).replace('-', ' ')
    tokens=set(re.findall(r'[a-z]+',t))
    allowed=set('anterior posterior lateral lung lungs pulmonary auscultation with mouth open on skin and compare side to comparison performed was were the'.split())
    if 'auscultation' not in tokens or not tokens.intersection({'lung','lungs','pulmonary'}) or not tokens.issubset(allowed): return None
    required={x for x in ('anterior','posterior','lateral','mouth open','on skin') if x in t}
    if 'side to side' in t: required.add('compare side to side')
    performed=ledger.performed_maneuvers().get('lungs_auscultate')
    if not performed or not required.issubset(performed['components']):
        return {'verdict':'unsupported','evidence':[], 'explanation':'This technique statement includes a lung examination or component that was not completed in the encounter.'}
    events=[e for e in ledger.events if e['seq'] in performed['events']]
    return {'verdict':'supported','evidence':[_ev(e) for e in events], 'explanation':'The completed examination record supports this technique description. It does not establish any unrecorded clinical finding.'}

def _delivered_ledger(ledger, case=None):
    """Read old metadata conservatively without changing original records.

    A duration in a concept payload must also occur in the delivered reply.
    Old openings bundled hidden onset facts with a complaint. Reject that
    payload rather than treating metadata as proof of audible/displayed facts.
    """
    def speech_times(text):
        numbers={'one':'1','two':'2','three':'3','four':'4','five':'5','six':'6','seven':'7','eight':'8','nine':'9','ten':'10','eleven':'11','twelve':'12'}
        text=re.sub(r'\b(?:'+ '|'.join(numbers)+r')\b',lambda m:numbers[m.group()],nlp.normalize(text))
        return _times(text)
    events=[]
    for ev in ledger.events:
        if ev['kind']!=evidence.PATIENT:
            events.append(ev);continue
        if case and ev['meta'].get('kind')=='opening':
            from .patient import delivered_fact_metadata
            factmap={f['id']:f for f in case.get('facts',[])}
            approved={'facts_released':[],'concepts':{},'checklist_hits':[],'categories':[]}
            for fid in case.get('patient',{}).get('opening_facts',[]):
                fact=factmap.get(fid)
                if not fact:continue
                actual_meta=delivered_fact_metadata(fact,ev['text'])
                approved['concepts'].update(actual_meta['concepts'])
                approved['facts_released'].extend(actual_meta['facts_released'])
                approved['checklist_hits'].extend(actual_meta['checklist_hits'])
                if actual_meta['facts_released']:approved['categories'].append(fact.get('category'))
            if not approved['concepts']:
                approved['concepts']={'opening_delivered_text':{'polarity':'positive','value':ev['text']}}
                approved['delivery_limits']=['Historical opening metadata cannot be verified; only the actual delivered opening text is evidence.']
            events.append(dict(ev,meta=dict(ev['meta'],**approved)))
            continue
        actual=speech_times(ev['text']);concepts={}
        for cid,spec in ev['meta'].get('concepts',{}).items():
            value=spec if isinstance(spec,str) else spec.get('value','')
            if all(t in actual for t in speech_times(value)):concepts[cid]=spec
        meta=dict(ev['meta'],concepts=concepts)
        if case:
            factmap={f['id']:f for f in case.get('facts',[])}
            oldfacts=meta.get('facts_released',[])
            removed={fid for fid in oldfacts if fid in factmap and factmap[fid].get('concepts') and not any(cid in concepts for cid in factmap[fid]['concepts'])}
            meta['facts_released']=[fid for fid in oldfacts if fid not in removed]
            removed_checks={factmap[fid].get('checklist') for fid in removed}
            meta['checklist_hits']=[hit for hit in meta.get('checklist_hits',[]) if hit not in removed_checks]
        events.append(dict(ev,meta=meta))
    return evidence.Ledger(events)

def _spoken_rating_values(ledger,case):
    ids={cid for f in case.get('facts',[]) if f.get('category')=='severity' for cid in f.get('concepts',{})}
    numbers={'zero':'0','one':'1','two':'2','three':'3','four':'4','five':'5','six':'6','seven':'7','eight':'8','nine':'9','ten':'10'}
    out=set()
    for ev in ledger.by_kind(evidence.PATIENT):
        if not ids.intersection(ev['meta'].get('concepts',{})):continue
        raw=nlp.normalize(ev['text'])
        for m in re.finditer(r'\b(?:'+ '|'.join(numbers)+r')\b',raw):
            if re.match(r'\s+(?:years?|months?|weeks?|days?|hours?|minutes?|tablets?|mg|times?)\b',raw[m.end():]):continue
            out.add(numbers[m.group()])
    return out

def _opening_complaint_summary(text):
    """Bounded positive pain summary, with only an explicitly spoken anchor.

    'Has not gone away since dinner' permits a brief 'pain ... since dinner'.
    It does not establish a numeric duration, a first onset at dinner, constant
    intensity, or the fuller history behind the opening. Unknown words remain
    outside this matcher instead of disappearing in a bag-of-words comparison.
    """
    text = nlp.normalize(text).strip(' .;,:!?')
    text = re.sub(r'\b(?:that )?(?:has|have) not gone away\b|\b(?:that )?has persisted\b', 'persistent', text)
    ongoing = bool(re.search(r'\b(?:persistent|ongoing)\b', text))
    text = re.sub(r'\b(?:persistent|ongoing)\b', ' ', text)
    anchor = re.search(r'\bsince (dinner|breakfast|lunch|last night|this morning|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', text)
    relative = anchor.group(1) if anchor else None
    if anchor:
        text = text[:anchor.start()] + ' ' + text[anchor.end():]
    locations = []
    for location, pattern in _LOCATION_FORMS.items():
        if re.search(pattern, text):
            locations.append(location)
            text = re.sub(pattern, ' ', text)
    if len(locations) != 1 or len(re.findall(r'\bpain\b', text)) != 1:
        return None
    text = re.sub(r'\bpain\b', ' ', text)
    text = re.sub(r'^(?:i have|i am having|i\'m having)\b', ' ', text.strip())
    text = re.sub(r'\b(?:the|my|her|his|under|beneath|in|at)\b', ' ', text)
    if re.search(r'[a-z0-9]', text):
        return None
    return {'location': locations[0], 'relative': relative, 'ongoing': ongoing}


def _opening_summary_target(claim,ledger):
    """Strip only a demographic introduction verified by the actual doorway."""
    text=claim.get('eval_text') or claim['text']
    prefix=re.match(r'^(?:([A-Za-z]+(?: [A-Za-z]+){1,3})(?: is a |,\s*))?(\d{1,3})[- ]year[- ]old (woman|female|man|male),?\s+(?:(?:who )?(?:reports|is reporting)|reporting|with|who(?= feels?\b))\s+',text,re.I)
    if not prefix:
        return re.sub(r'^(?:(?:the patient|patient|she|he)\s+)?(?:reports|reported|is reporting)\s+','',text,flags=re.I),[]
    name,age,sex=prefix.group(1,2,3);sex={'woman':'female','man':'male'}.get(sex.lower(),sex.lower())
    canonical=lambda x:re.sub(r'\s+',' ',nlp.normalize(x).replace('-',' ')).strip()
    expected=canonical((name+' ' if name else '')+age+' year old '+sex)
    sources=[ev for ev in ledger.by_kind(evidence.STATION_INFO) if ev.get('meta',{}).get('doorway') and re.search(r'(?<![a-z0-9])'+re.escape(expected)+r'(?![a-z0-9])',canonical(ev['text']))]
    return (text[prefix.end():],sources[:1]) if sources else (text,[])


def _opening_paraphrase(claim,ledger,concept_map):
    if claim['section']!='S':return None
    norm=lambda text:re.sub(r'[^a-z0-9 ]','',nlp.normalize(text).replace('-',' ')).strip()
    target=norm(claim.get('eval_text') or claim['text'])
    for ev in ledger.by_kind(evidence.PATIENT):
        if ev['meta'].get('kind')!='opening':continue
        summary_text, demographic_sources = _opening_summary_target(claim,ledger)
        for mapping in opening_evidence.PARAPHRASES:
            if claim.get('header') in ('cc','hpi',None) and norm(ev['text'])==norm(mapping['source']) and any(opening_evidence.summary_text(summary_text)==opening_evidence.summary_text(example) for example in mapping['summaries']):
                return {'verdict':'supported','concepts':[cid for cid in ev['meta'].get('concepts',{}) if cid in ('opening_complaint','opening_delivered_text')] or ['opening_delivered_summary'],'evidence':[_ev(e) for e in demographic_sources]+[_ev(ev)],'explanation':'This symptom summary matches the actual spoken opening. It supplies only opening evidence, not an unasked detailed history or a confirmed diagnosis.'}
        if claim.get('header') in ('cc','hpi',None):
            summary_text, demographic_sources = _opening_summary_target(claim,ledger)
            summary = _opening_complaint_summary(summary_text)
            actual = _opening_complaint_summary(ev['text'])
            if summary and actual and summary['location'] == actual['location'] \
                    and (not summary['relative'] or summary['relative'] == actual['relative']) \
                    and (not summary['ongoing'] or actual['ongoing']):
                generic = [cid for cid in ev['meta'].get('concepts',{})
                           if cid in ('opening_complaint','opening_delivered_text')]
                return {'verdict':'supported','concepts':generic or ['opening_delivered_summary'],
                        'evidence':[_ev(e) for e in demographic_sources]+[_ev(ev)], 'explanation':'This brief chief complaint is supported by the actual spoken opening, including only the relative time anchor the patient stated. It does not establish any unasked detailed HPI attribute or numeric duration.'}
        for cid in ev['meta'].get('concepts',{}):
            if any(target==norm(alias) for alias in concept_map.get(cid,[])):
                return {'verdict':'supported','concepts':[cid],'evidence':[_ev(ev)],'explanation':'This complete paraphrase matches the approved meaning of the actual delivered opening statement.'}
    return None

def _historical_clause_context(text):
    """Time/condition context prevents treating distinct clinical states as opposites."""
    t=scoped_claims.canonical_prior(text)[0]
    prior=bool(re.search(r'\b(?:earlier|previous|previously|prior|before this|before the current|before these past|before the past)\b',t))
    present=bool(re.search(r'\b(?:right now|currently|at this moment|during this encounter|at present|now)\b',t))
    condition='exertion' if re.search(r'\b(?:exertional|with exertion|when exerting|when i push|when walking|while walking)\b',t) else 'rest' if re.search(r'\b(?:at rest|while resting|head still)\b',t) else 'unspecified'
    return ('prior' if prior else 'current' if present else 'usual',condition)

def _prior_episode_history(claim, case, ledger):
    """Bounded previous-history clauses, independently from today's complaint.

    Both identity and content must match an actually delivered past-history fact.
    Extra symptoms, numeric duration and wrong polarity cannot borrow this path.
    """
    if claim['section']!='S' or claim.get('header') not in ('hpi','pmh',None):return None
    t,first_episode=scoped_claims.canonical_prior(claim['text'])
    symptom=r'(?P<symptom>palpitations|(?:complete )?(?:urinary )?retention)'
    untimed=re.fullmatch(r'(?:no|denies) (?:previous|prior|earlier) (?:(?:episodes? of|history of) )?'+symptom,t)
    timed=re.fullmatch(r'(?:no|denies) '+symptom+r' before (?:(?:this|the current) (?:illness|episode)|(?:these )?past (?P<time>\d+(?:\.\d+)? (?:days?|weeks?|months?)))',t)
    stream=re.fullmatch(r'(?:weak|poor) (?:urinary )?stream (?:for|over) (?P<interval>(?:\d+ )?(?:months?|weeks?|days?))',t)
    match=untimed or timed
    if not match and not stream:
        raw=nlp.normalize(claim['text'])
        if re.search(r'\b(?:first|never|history of|before today)\b',raw) and re.search(r'\b(?:retention|unable to urinate|unable to pass urine|palpitations)\b',raw):
            return {'verdict':'not_evaluated','concepts':[],'evidence':[], 'explanation':'This prior-history wording was not fully resolved. Current symptoms alone cannot establish whether this is a first episode; compare the actual prior-history answer. No automatic credit is assigned.'}
        return None
    subject='stream' if stream else 'retention' if 'retention' in match['symptom'] else 'palpitations'
    topic={'stream':r'\bweak (?:urinary )?stream\b','retention':r'\b(?:retention|complete blockage|completely blocked)\b','palpitations':r'\bpalpitations\b'}[subject]
    negative=r'\b(?:never (?:had )?complete blockage|no (?:previous |prior |earlier )?(?:complete )?(?:urinary )?retention|no (?:previous |prior |earlier )?(?:history of )?palpitations|no (?:previous |prior |earlier )?episodes? of palpitations)\b'
    candidates=[]
    for f in case.get('facts',[]):
        if f.get('category')!='past_occurrence':continue
        for ev in ledger.by_kind(evidence.PATIENT):
            ids=set(f.get('concepts',{})) & set(ev['meta'].get('concepts',{}))
            spoken=nlp.normalize(ev['text'])
            if ids and f['id'] in ev['meta'].get('facts_released',[]) and re.search(topic,spoken):candidates.append((spoken,ev,ids))
    if not candidates:return {'verdict':'unsupported','concepts':[],'evidence':[],'explanation':'The relevant prior history was not delivered. Today’s symptoms do not establish previous episodes or their duration.'}
    if stream:
        found=next((x for x in candidates if stream['interval']=='months' and re.search(r'\bfor months\b.*\b(?:had|have) (?:a )?weak stream\b',x[0]) and not re.search(r'\b(?:no|not|never)\b.*\bweak stream\b',x[0])),None)
        if not found:return {'verdict':'unsupported','concepts':[],'evidence':[_ev(x[1]) for x in candidates],'explanation':'The stream and duration must match the delivered history. An imprecise duration of months does not establish a particular number of months or a different interval.'}
    else:
        found=next((x for x in candidates if re.search(negative,x[0])),None)
        if not found:return {'verdict':'contradicts','concepts':[],'evidence':[_ev(x[1]) for x in candidates],'explanation':'This previous-history negative does not match the earlier history actually reported.'}
    links=[_ev(found[1])];ids=set(found[2])
    if first_episode:
        current=[]
        prior_ids={f['id'] for f in case.get('facts',[]) if f.get('category')=='past_occurrence'}
        for ev in ledger.by_kind(evidence.PATIENT):
            if set(ev['meta'].get('facts_released',[])) & prior_ids:continue
            spoken=nlp.normalize(ev['text'])
            pattern=r'\b(?:nothing (?:will )?come(?:s)? out|cannot (?:urinate|pass urine)|unable to (?:urinate|pass urine)|can\'t (?:urinate|pass urine)|no urine comes out)\b' if subject=='retention' else r'\b(?:fluttering|racing|palpitations)\b'
            if re.search(pattern,spoken) and not re.search(r'\b(?:never|no palpitations|no fluttering)\b',spoken):current.append(ev)
        if not current:return {'verdict':'unsupported','concepts':[],'evidence':links, 'explanation':'The earlier history was obtained, but calling this a first episode also needs evidence of the current symptom.'}
        links.append(_ev(current[-1]));ids.update(current[-1]['meta'].get('concepts',{}))
    if timed and timed['time']:
        expected=_times(timed['time']);onset=[]
        for f in case.get('facts',[]):
            if f.get('temporal_role')!='first_episode_onset':continue
            for ev in ledger.by_kind(evidence.PATIENT):
                actualids=set(f.get('concepts',{})) & set(ev['meta'].get('concepts',{}))
                if actualids and f['id'] in ev['meta'].get('facts_released',[]):onset.append((ev,actualids))
        aligned=next((x for x in onset if expected==_times(x[0]['text'])),None)
        if not aligned:return {'verdict':'contradicts' if onset else 'unsupported','concepts':[],'evidence':[_ev(x[0]) for x in onset],'explanation':'The earlier-history time boundary must match the first onset actually obtained.'}
        links.append(_ev(aligned[0]));ids.update(aligned[1])
    return {'verdict':'supported','concepts':sorted(ids),'evidence':links,'explanation':'This matches the prior history actually reported. It is evaluated separately from the patient’s current symptom.'}


def audit_note(parsed, ledger, case):
    """Return the full claim-by-claim audit."""
    ledger = _delivered_ledger(ledger,case)
    concept_map = _concept_map(case)
    ev_index = claims_mod.evidence_index(ledger, case)
    ev_index["spoken_ratings"] = _spoken_rating_values(ledger,case)
    released = ledger.released_concepts()
    performed = ledger.performed_maneuvers()
    refusals = ledger.refused_exams()
    counseled = ledger.counseling_topics()

    findings = []
    documented_concepts = set()

    for claim in parsed.claims():
        text = claim["text"]
        # `eval_text` restores a negation cue that comma-splitting removed.
        etext = claim.get("eval_text") or text
        if not nlp.normalize(text):
            continue
        rec = {
            "section": claim["section"],
            "header": claim["header"],
            "raw_header": claim.get("raw_header"),
            "text": text,
            "index": claim.get("index"),
            "verdict": "not_evaluated",
            "concepts": [],
            "evidence": [],
            "explanation": "",
        }

        # Completed results are factual in every section, including mixed Plan
        # paragraphs with counseling or legitimate future actions.
        result_text = text
        if claim.get('raw_header') and claims_mod.investigations_mentioned(claim['raw_header']):
            result_text = claim['raw_header'] + ': ' + text
        result_defect = _asserted_result_defect(result_text, ev_index)
        if result_defect:
            rec.update(verdict="unsupported", explanation=result_defect)
            findings.append(rec)
            continue

        if claim['section'] in ('A','P') and claims_mod.asserted_investigations(text):
            supplied_events=[ev for ev in ledger.by_kind(evidence.STATION_INFO) if ev['meta'].get('supplied_id') and set(claims_mod.investigations_mentioned(ev['text'])) & set(claims_mod.asserted_investigations(text))]
            normalize_result=lambda value:nlp.normalize(value).strip(' .')
            exact=any(normalize_result(text)==normalize_result(ev['text']) for ev in supplied_events)
            rec.update(verdict='supported_supplied' if exact else 'not_evaluated', evidence=[_ev(ev) for ev in supplied_events],
                       explanation='This completed result matches the supplied encounter record; it is not a future test order.' if exact else 'This reports a completed investigation. A supplied test is recorded, but this result wording was not fully verified. Compare the linked result; it is not automatically accepted as a hypothesis or future test order.')
            findings.append(rec)
            continue

        daily_medication = _daily_medication_history(claim, case, ledger)
        if daily_medication:
            rec.update(daily_medication)
            if rec['verdict'] == 'supported':
                documented_concepts.update(rec['concepts'])
            findings.append(rec)
            continue

        prior_history = _prior_episode_history(claim, case, ledger)
        if prior_history:
            rec.update(prior_history)
            if rec["verdict"] == "supported":documented_concepts.update(rec["concepts"])
            findings.append(rec)
            continue

        current_status = _current_status_history(claim, case, ledger)
        if current_status:
            rec.update(current_status)
            if rec['verdict'] == 'supported':
                documented_concepts.update(rec['concepts'])
            findings.append(rec)
            continue

        short_history = _short_obtained_history(claim, case, ledger)
        if short_history:
            rec.update(short_history)
            if rec['verdict']=='supported':documented_concepts.update(rec['concepts'])
            findings.append(rec)
            continue

        scoped = scoped_claims.evaluate(claim,case,ledger,_opening_summary_target)
        if scoped:
            scoped['evidence']=[_ev(ev) for ev in scoped.pop('events')]
            rec.update(scoped)
            if rec['verdict']=='supported':documented_concepts.update(rec['concepts'])
            findings.append(rec)
            continue

        # --- Assessment: a hypothesis, but not a licence to assert facts --
        if claim["section"] == "A":
            defect = _asserted_result_defect(text, ev_index)
            if defect:
                rec["verdict"] = "unsupported"
                rec["explanation"] = defect
                findings.append(rec)
                continue
            rec["verdict"] = "hypothesis"
            rec["explanation"] = ("An Assessment entry is a clinical hypothesis. "
                                  "It is graded against the rubric, not against "
                                  "the evidence record.")
            findings.append(rec)
            continue

        # --- Plan: proposed action, or a claim that a discussion happened -
        if claim["section"] == "P":
            kind = _is_counseling(text)
            if kind == "past":
                topics = _counsel_topics(text, case)
                matched = [t for t in topics if t in counseled]
                # The topic must be the one discussed. Generic return
                # precautions are not evidence that smoking cessation or
                # cancer screening was covered.
                if matched or (not topics and any(counseled)):
                    rec["verdict"] = "counseling_ok"
                    ev = counseled.get(matched[0]) if matched else list(counseled.values())[0]
                    rec["evidence"] = [_ev(ev)]
                    rec["explanation"] = ("You discussed this with the patient "
                                          "during the encounter, so past tense is "
                                          "accurate.")
                else:
                    rec["verdict"] = "counseling_unsupported"
                    rec["explanation"] = (
                        "This is written as something that already happened, but "
                        "no discussion of it is in the encounter record. Either "
                        "discuss it in the room, or word it as an intention "
                        "(\"will educate the patient on...\").")
            else:
                defect = _asserted_result_defect(text, ev_index)
                if defect:
                    rec["verdict"] = "unsupported"
                    rec["explanation"] = defect
                else:
                    rec["verdict"] = "proposed"
                    rec["explanation"] = ("A Plan entry proposes a future action. "
                                          "It is not a claim that anything was "
                                          "done.")
            findings.append(rec)
            continue

        # --- Subjective / Objective: factual claims ----------------------
        found = nlp.find_concepts(etext, concept_map)
        if claim.get('header')=='meds' and not re.search(r'\b(?:help\w*|relie\w*|improv\w*|worsen\w*|effective|ineffective)\b',nlp.normalize(etext)):
            med_ids={cid for f in case.get('facts',[]) if f.get('category')=='medications' for cid in f.get('concepts',{})}
            med_surfaces={hit['surface'] for cid,hit in found.items() if cid in med_ids and cid in released}
            # A bare drug-name overlap does not add an independent claim
            # about a bundled treatments-tried history.
            found={cid:hit for cid,hit in found.items() if cid in released or hit['surface'] not in med_surfaces}
        semantic, semantic_defect = _semantic_history(etext, claim, case, released, ledger)
        found.update(semantic)
        exam_family = nlp.find_concepts(etext, lexicon.EXAM_CLAIM_CONCEPTS)

        family = _family_evidence(claim, ledger)
        if family:
            rec.update(family)
            if rec['verdict']=='supported':documented_concepts.update(rec['concepts'])
            findings.append(rec);continue

        vital = vital_evidence.serial_claim(claim, ledger)
        if vital is None:
            vital = vital_evidence.station_claim(claim, ledger, case)
        if vital is not None:
            rec.update(vital)
            if rec['verdict'] in ('supported', 'supported_supplied'):
                documented_concepts.update(rec['concepts'])
            findings.append(rec)
            continue

        if claim['section'] == 'S':
            allergy_ids = {cid for fact in case.get('facts', []) if fact.get('category') == 'allergies' for cid in fact.get('concepts', {})}
            if claim.get('header') == 'allergies' or (allergy_ids.intersection(found) and re.search(r'\b(?:causes?|reaction)\b', nlp.normalize(text))):
                found = {cid: hit for cid, hit in found.items() if cid in allergy_ids}

        exact = _verbatim_obtained(claim, ledger)
        if exact:
            rec["verdict"] = "supported_supplied" if exact["kind"] == evidence.STATION_INFO else "supported"
            rec["concepts"] = list(found)
            rec["evidence"] = [_ev(exact)]
            rec["explanation"] = "This complete statement matches information actually released during this encounter."
            documented_concepts.update(found)
            findings.append(rec)
            continue

        opening = _opening_paraphrase(claim,ledger,concept_map)
        if opening:
            rec.update(opening);documented_concepts.update(rec['concepts'])
            findings.append(rec);continue

        if claim['section'] == 'O':
            defect = _asserted_result_defect(text, ev_index)
            if defect:
                rec.update(verdict='unsupported', explanation=defect)
                findings.append(rec)
                continue

        atomic = _atomic_exam(claim, ledger)
        if atomic:
            rec.update(atomic)
            if rec['verdict']=='supported':documented_concepts.update(rec['concepts'])
            findings.append(rec)
            continue

        technique = _lung_technique_claim(claim, ledger)
        if technique:
            rec.update(technique)
            findings.append(rec)
            continue

        # Attributes first. A claim can be on exactly the right topic and wrong
        # in the value, the dose or the polarity, and topic matching alone
        # called all of those "supported".
        attr = semantic_defect or _attribute_defect(text, etext, ev_index, found)
        if attr:
            rec["verdict"] = "unsupported" if attr.startswith("UNSUPPORTED:") else "overbroad" if attr.startswith("OVERBROAD:") else "contradicts"
            rec["explanation"] = attr.removeprefix("OVERBROAD: ").removeprefix("UNSUPPORTED: ")
            semantic_sources = [h["semantic_support"] for h in semantic.values() if h.get("semantic_support")]
            rec["evidence"] = [_ev_from_support(x) for x in semantic_sources] if semantic_defect and semantic_sources else _attribute_evidence(found, ev_index)
            findings.append(rec)
            continue

        # Refusal documentation. The organ is often only in the header:
        # "Rectal: Refused at this time."
        if "refused" in nlp.normalize(text):
            key = _refusal_key((claim.get("raw_header") or "") + " " + text)
            if key and key in refusals:
                rec["verdict"] = "supported"
                rec["evidence"] = [_ev(refusals[key])]
                rec["explanation"] = ("You proposed this examination and the "
                                      "patient refused. Documenting the refusal "
                                      "in Objective is exactly what the syllabus "
                                      "asks for.")
                documented_concepts.add("refusal:" + key)
            else:
                rec["verdict"] = "unsupported"
                rec["explanation"] = ("No refusal was recorded during the "
                                      "encounter. A refusal can only be "
                                      "documented if you proposed the "
                                      "examination and the patient declined.")
            findings.append(rec)
            continue

        # Supplied results (labs / imaging given at the station).
        supplied = _supplied_hit(text, case, ledger)
        if supplied:
            bad_analytes = claims_mod.analyte_mismatches(text, ev_index)
            if bad_analytes:
                rec["verdict"] = "contradicts"
                rec["evidence"] = [supplied]
                rec["explanation"] = (
                    "The result supplied at the station says the opposite: "
                    + "; ".join("%s documented as %s, supplied as %s"
                                % (b["analyte"], b["claimed"], b["actual"])
                                for b in bad_analytes) + ".")
                findings.append(rec)
                documented_concepts.add("supplied_result")
                continue
            rec["verdict"] = "supported_supplied"
            rec["evidence"] = [supplied]
            rec["explanation"] = ("Supported by a result supplied at the station. "
                                  "The syllabus asks you to document results you "
                                  "are given.")
            documented_concepts.add("supplied_result")
            findings.append(rec)
            continue

        # Over-breadth: does the sentence reach further than the exam did?
        over = _overbroad(text, performed)
        if over:
            rec["verdict"] = "overbroad"
            rec["explanation"] = over["message"]
            rec["evidence"] = over["evidence"]
            findings.append(rec)
            continue

        # Section placement
        misplaced = _misplaced(claim["section"], text)

        # Concept support
        supported_hits, unsupported_hits, contradicted_hits = [], [], []
        for cid, hit in found.items():
            mode = nlp.polarity_mode(concept_map.get(cid))
            # Decide the claim's polarity from the SURFACE that matched, not
            # from the concept as a whole. A concept like tobacco_use lists
            # both "smokes" and "never smoked", which made the whole concept
            # "unchecked" and let "Smokes 6 packs daily" pass against a patient
            # who has never smoked. The surface that actually appeared in the
            # note is what carries the polarity.
            claim_pol = "negative" if hit["negated"] else "positive"
            support = hit.get("semantic_support") or released.get(cid)
            if support is None:
                unsupported_hits.append((cid, hit, claim_pol))
                continue
            if hit.get("semantic_verified"):
                supported_hits.append((cid, hit, support))
                documented_concepts.add(cid)
                continue
            support_pol = support["polarity"]
            if mode == "strict_negative":
                claim_pol = support_pol = "negative"
            elif mode == "unchecked":
                # A concept listing both "smokes" and "never smoked" cannot be
                # judged from the concept's declared polarity: "no murmur" is
                # how a NORMAL heart is described, so the concept being
                # "positive" says nothing about how any one sentence used it.
                # The only sound comparison is the SAME TERM in both places.
                # If the encounter's own wording does not contain the term, we
                # have nothing to compare and say so rather than guessing.
                surface = hit.get("surface") or ""
                value = support.get("value") or ""
                ev_pol = nlp.term_polarity(value, surface)
                if nlp.normalize(surface) in ('frequency','urinary frequency','frequent urination') and re.search(r'\bno (?:increased )?(?:urinary )?frequency\b',nlp.normalize(value)):
                    ev_pol = 'negative' 
                if ev_pol is None:
                    claim_pol = support_pol = "n/a"
                else:
                    claim_pol = "negative" if (
                        hit["negated"] or nlp.surface_is_negative(surface)
                    ) else "positive"
                    support_pol = ev_pol
            if support_pol != claim_pol:
                contradicted_hits.append((cid, hit, claim_pol, support))
            else:
                supported_hits.append((cid, hit, support))
                documented_concepts.add(cid)

        # An Objective sentence also needs the maneuver to have happened.
        if claim["section"] == "O" and exam_family and not found:
            fam = "osteopathic" if claim.get("header") == "osteopathic" else list(exam_family.keys())[0]
            man_ok, man_ev = _maneuver_backs(fam, performed, claim)
            relevant = _relevant_exam_events(claim,ledger)
            if relevant:
                rec["verdict"] = "not_evaluated"
                rec["evidence"] = [_ev(ev) for ev in relevant[-3:]]
                rec["explanation"] = "Relevant findings were released, but this wording could not be resolved. Compare the linked evidence; this is not a proven false statement and receives no automatic credit."
            elif man_ok:
                rec["verdict"] = "unsupported"
                rec["evidence"] = man_ev
                rec["explanation"] = ("The examination was performed, but no corresponding finding was released. Performing an examination does not support every possible result.")
            else:
                rec["verdict"] = "unsupported"
                rec["explanation"] = (
                    "This describes a finding from an examination that does not "
                    "appear in the encounter record. Only document what you "
                    "performed and what the simulator released.")
                rec["concepts"] = [fam]
            findings.append(rec)
            continue

        if contradicted_hits:
            cid, hit, claim_pol, support = contradicted_hits[0]
            rec["verdict"] = "contradicts"
            rec["concepts"] = [cid]
            rec["evidence"] = [_ev_from_support(support)]
            rec["explanation"] = (
                "You documented this as %s, but the encounter established the "
                "opposite." % ("a negative" if claim_pol == "negative" else "present"))
        elif unsupported_hits and not supported_hits:
            cid, hit, claim_pol = unsupported_hits[0]
            rec["verdict"] = "unsupported"
            rec["concepts"] = [c for c, _, _ in unsupported_hits]
            if claim_pol == "negative":
                rec["explanation"] = (
                    "Nothing in the encounter supports this negative. The patient "
                    "never being asked about it, and never mentioning it, is not "
                    "the same as the patient denying it.")
            else:
                rec["explanation"] = (
                    "Nothing in the encounter produced this. It may well be true "
                    "of the patient, but you did not obtain it.")
        elif supported_hits:
            rec["verdict"] = "supported"
            rec["concepts"] = [c for c, _, _ in supported_hits]
            rec["evidence"] = [_ev_from_support(s) for _, _, s in supported_hits[:3]]
            rec["explanation"] = "Obtained during the encounter and documented accurately."
            if unsupported_hits:
                rec["verdict"] = "unsupported"
                rec["explanation"] = "Part of this statement was obtained, but the whole statement is not supported."
                rec["partial_unsupported"] = [c for c, _, _ in unsupported_hits]
                rec["explanation"] += (" Part of this sentence (%s) has no support."
                                       % ", ".join(c for c, _, _ in unsupported_hits))
        else:
            rec["verdict"] = "not_evaluated"
            rec["explanation"] = ("No specific claim could be resolved from this "
                                  "sentence, so it is reported rather than scored.")

        if misplaced and rec["verdict"] in ("supported", "supported_supplied"):
            rec["verdict"] = "misplaced"
            rec["explanation"] = misplaced

        findings.append(rec)

    internal = _internal_contradictions(parsed, concept_map)
    omitted = _omitted(released, documented_concepts, ledger, case)

    return {
        "claims": findings,
        "internal_contradictions": internal,
        "obtained_but_omitted": omitted,
        "documented_concepts": sorted(documented_concepts),
        "counts": _counts(findings),
    }


# ---------------------------------------------------------------------------

_RATING_IN_VALUE = re.compile(r"(?<![0-9/])(\d{1,2})\s*/\s*10(?![0-9])")


def _attribute_evidence(found, ev_index):
    out = []
    for cid in found:
        val = ev_index["values"].get(cid)
        if val:
            out.append({"kind": "evidence", "text": "%s: %s" % (cid, val),
                        "time": ""})
    return out[:3]


def _attribute_defect(text, etext, ev_index, found):
    """Wrong value, wrong dose, or wrong result on an otherwise correct topic."""
    # 1. A laboratory analyte documented with the opposite result.
    bad = claims_mod.analyte_mismatches(text, ev_index)
    if bad:
        return ("The result recorded during the encounter says the opposite: "
                + "; ".join("%s documented as %s, obtained as %s"
                            % (b["analyte"], b["claimed"], b["actual"])
                            for b in bad) + ".")

    # 2. A number attached to a concept whose obtained value carries a
    #    different number -- a severity, a dose, an amount.
    claim_ratings = claims_mod.ratings(text)
    claim_quants = claims_mod.quantities(text)
    if not claim_ratings and not claim_quants:
        return ""
    # A severity is a value, and the encounter produced a definite set of them.
    # Documenting 1/10 when the patient said 7/10 is wrong even though "flank
    # pain" is exactly the right topic -- and the severity lives on a different
    # concept from the symptom, so it must be checked against all of them.
    if claim_ratings:
        obtained = set(ev_index.get("spoken_ratings",[]))
        for value in ev_index["values"].values():
            for m in _RATING_IN_VALUE.finditer(value or ""):
                obtained.add(m.group(1))
        if obtained:
            wrong = [r for r in claim_ratings if r not in obtained]
            if wrong and len(wrong) == len(claim_ratings):
                return ("You documented %s/10. The severities the patient gave "
                        "you were %s. Document the number you obtained."
                        % ("/10, ".join(wrong),
                           ", ".join("%s/10" % o for o in sorted(obtained))))
        else:
            # No severity was obtained AT ALL. The symptom may be well
            # supported and the number still invented: a pain score you never
            # asked for is not a fact about this patient.
            return ("You documented a severity of %s/10, but you never asked "
                    "the patient to rate it. The symptom is supported; the "
                    "number is not."
                    % "/10, ".join(claim_ratings))

    for cid in found:
        value = ev_index["values"].get(cid) or ""
        for spelled,abbreviation in [('milligrams','mg'),('milligram','mg'),('micrograms','mcg'),('microgram','mcg'),('milliliters','ml'),('milliliter','ml')]:
            value=re.sub(r'\b'+spelled+r'\b',abbreviation,value,flags=re.I)
        if not value:
            continue
        import re as _re
        have = _re.findall(r"\d+(?:\.\d+)?", value)
        if not have:
            continue
        for q in claim_quants:
            # Only compare a quantity to a value carrying the same unit,
            # otherwise "2 tablets" is checked against "7/10".
            if q["unit"] not in value.lower():
                continue
            if q["value"] not in have:
                return ("You documented %s %s, but what the encounter produced "
                        "was %s." % (q["value"], q["unit"], value))
    return ""


def _asserted_result_defect(text, ev_index):
    """Is this entry asserting an investigation result the encounter never got?

    "Consider pyelonephritis" is an inference and is fine anywhere. "Confirmed
    by a positive urine culture" additionally asserts a test result, and "CT
    abdomen completed and showed a tumor" asserts a past action. Neither is a
    hypothesis, and neither is exempt from the evidence record just because it
    was written under Assessment or Plan.
    """
    mentioned = claims_mod.asserted_investigations(text)
    if not mentioned:
        return ""
    asserts = claims_mod.asserts_a_result(text)
    obtained = ev_index["investigations"]
    missing = [inv for inv in mentioned if inv not in obtained]
    if not missing:
        return ""
    what = missing[0]
    if asserts:
        return ("This asserts a result for %s, but no %s result is in the "
                "encounter record. Proposing the test (\"obtain %s\") is "
                "legitimate; reporting what it showed is not."
                % (what, what, what))
    return ("This is written as something already done, but no %s appears in "
            "the encounter record. Word it as a proposal instead."
            % what)


def _counts(findings):
    out = {}
    for f in findings:
        out[f["verdict"]] = out.get(f["verdict"], 0) + 1
    return out


def _ev(event):
    return {
        "kind": event["kind"],
        "text": event["text"],
        "time": "%d:%02d" % (event["t_ms"] // 60000, (event["t_ms"] // 1000) % 60),
        "seq": event["seq"],
    }


def _ev_from_support(support):
    return {
        "kind": support["source_kind"],
        "text": support["quote"],
        "time": "%d:%02d" % (support["t_ms"] // 60000, (support["t_ms"] // 1000) % 60),
        "seq": support["source_seq"],
        "value": support.get("value", ""),
    }


def _refusal_key(text):
    t = nlp.normalize(text)
    for key, spec in physexam.REFUSABLE.items():
        for trig in spec["strong"] + spec["weak"]:
            if nlp.normalize(trig) in t:
                return key
    return None


def _vitals_seen(ledger):
    for ev in ledger.by_kind("station_info"):
        if ev["meta"].get("vitals"):
            return True
    return False


def _vitals_text(case):
    v = case["station"]["vitals"]
    return ", ".join("%s %s" % (k, val) for k, val in v.items())


_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _vitals_accurate(text, case):
    """Each vital must carry the value supplied FOR ITS OWN LABEL.

    Set membership over the numbers is not a check: "P 18, R 104, BP 70/112"
    reuses every number the chart supplies and is wrong about all three.
    """
    return not claims_mod.vital_mismatches(text, case)


def _vital_mismatch_text(text, case):
    bad = claims_mod.vital_mismatches(text, case)
    if not bad:
        return ""
    return "; ".join("%s documented as %s, supplied as %s"
                     % (b["label"], b["claimed"], b["supplied"]) for b in bad)


def _supplied_hit(text, case, ledger):
    seen = {ev["meta"].get("supplied_id") for ev in ledger.by_kind("station_info")}
    for res in case["station"].get("supplied_results", []):
        if res["id"] not in seen:
            continue
        if nlp.matches_any(text, [res["label"]] + res["value"].split(", ")[:3]
                           + ["urine dip", "urinalysis", "dipstick"]):
            return {"kind": "station_info", "text": res["label"] + ": " + res["value"],
                    "time": "0:00"}
    return None


def _overbroad(text, performed):
    for rule in OVERBREADTH_RULES:
        if not re.search(rule["pattern"], nlp.normalize(text)):
            continue
        if rule.get("always_overbroad"):
            return {"message": rule["message"], "evidence": []}
        mans = [rule["maneuver"]] + rule.get("alt_maneuvers", [])
        covered = set()
        evidence = []
        for mid in mans:
            rec = performed.get(mid)
            if rec:
                covered |= set(rec["components"])
                evidence.append({"kind": "exam_action", "text": rec["label"],
                                 "time": "", "seq": rec["events"][0]})
        if not evidence:
            return {"message": rule["message"] + " That examination was not "
                                                 "performed at all.",
                    "evidence": []}
        missing = [c for c in (rule["requires"] or []) if c not in covered]
        if missing:
            return {"message": rule["message"] + " Not covered: " +
                               ", ".join(missing) + ".",
                    "evidence": evidence}
    return None


def _misplaced(section, text):
    t = nlp.normalize(text)
    if section == "S" and any(m in t for m in _OBJECTIVE_MARKERS):
        return ("This is a physical examination finding. It belongs in Objective, "
                "not Subjective.")
    if section == "O" and any(m in t for m in _SUBJECTIVE_MARKERS):
        return ("This is history the patient told you. It belongs in Subjective, "
                "not Objective.")
    return None


def _maneuver_backs(family, performed, claim=None):
    """Which performed maneuver, if any, could produce a claim of this family."""
    evidence = []
    regions = {'abdomen': 'Abdomen', 'heart': 'Heart', 'lungs': 'Lungs', 'osteopathic': 'Osteopathic', 'msk': 'Musculoskeletal', 'neuro': 'Neurologic', 'heent': 'HEENT', 'skin': 'Skin'}
    region = regions.get((claim or {}).get('header'))
    for mid, rec in performed.items():
        man = physexam.CATALOG_BY_ID.get(mid)
        if man and man["claim_concept"] == family and (not region or man.get("region") == region):
            evidence.append({"kind": "exam_action", "text": rec["label"],
                             "time": "", "seq": rec["events"][0]})
    return bool(evidence), evidence


def _internal_contradictions(parsed, concept_map):
    """Same concept asserted both ways inside the note (see the manual's own
    sample note, which denies and admits hemoptysis in the same note)."""
    seen = {}
    out = []
    for claim in parsed.claims():
        if claim["section"] not in ("S", "O"):
            continue
        etext = claim.get("eval_text") or claim["text"]
        etext = scoped_claims.canonical_prior(etext)[0]
        for cid, hit in nlp.find_concepts(etext, concept_map).items():
            if nlp.polarity_mode(concept_map.get(cid)) != "strict_positive":
                # Inherently-negative and mixed concepts cannot contradict
                # themselves; "CTA" and "no rales" are the same finding.
                continue
            pol = "negative" if hit["negated"] else "positive"
            # Patient report, examination observation, prior episodes and
            # contralateral maneuvers can legitimately differ. Compare the
            # same context; HPI and ROS remain comparable within Subjective.
            normalized = nlp.normalize(etext)
            temporal = _historical_clause_context(etext)
            side = "left" if re.search(r"\bleft\b", normalized) else "right" if re.search(r"\bright\b", normalized) else "unspecified"
            owner = "family" if claim.get("header") == "fh" else "patient"
            context = (cid, claim["section"], temporal, side, owner)
            prev = seen.get(context)
            if prev and prev["polarity"] != pol:
                out.append({
                    "concept": cid,
                    "first": prev["text"], "first_section": prev["section"],
                    "second": claim["text"], "second_section": claim["section"],
                    "explanation": ("Your note states this both ways. Whichever is "
                                    "correct, a reader cannot tell which to "
                                    "believe."),
                })
            elif not prev:
                seen[context] = {"polarity": pol, "text": claim["text"],
                             "section": claim["section"]}
    return out


_OMIT_LABELS = {
    "tobacco_use": "tobacco use", "alcohol_use": "alcohol use",
    "drug_use": "illicit drug use", "allergy_sulfa": "the sulfa allergy",
}


def _omitted(released, documented, ledger, case):
    """Information obtained during the encounter but left out of the note.

    The literature (Szauter et al.) finds this is the commonest real-world
    documentation failure, so it gets its own section rather than a footnote.
    """
    out = []
    for cid, support in released.items():
        if cid in documented:
            continue
        if support["source_kind"] == "station_info":
            continue
        out.append({
            "concept": cid,
            "label": _OMIT_LABELS.get(cid, cid.replace("_", " ")),
            "value": support.get("value") or support.get("quote", "")[:120],
            "quote": support.get("quote", "")[:200],
            "time": "%d:%02d" % (support["t_ms"] // 60000,
                                 (support["t_ms"] // 1000) % 60),
            "polarity": support["polarity"],
        })
    out.sort(key=lambda x: x["time"])
    return out
