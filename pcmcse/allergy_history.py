"""Scope allergy questions to authored information, without inventing denials.

Drug, food and environmental histories are different questions. This module
selects facts only; PatientEngine still delivers and credits their authored text.
"""
import re
from . import nlp

_SCOPE_PATTERNS = {
    'medication': r'\b(?:medications?|medicines?|drugs?|antibiotics?|nkda)\b',
    'food': r'\b(?:foods?|peanuts?|nuts?|shellfish|seafood|eggs?|milk|dairy|wheat|soy)\b',
    'environmental': r'\b(?:environmental|seasonal|pollen|dust|pets?|cats?|dogs?|mou?ld|hay fever)\b',
    'contact': r'\b(?:latex|nickel|contact)\b',
}
_TARGET_PATTERNS = {
    'penicillin': r'\bpenicillin\b', 'amoxicillin': r'\bamoxicillin\b',
    'codeine': r'\bcodeine\b', 'neomycin': r'\bneomycin\b',
    'naproxen': r'\bnaproxen\b', 'aspirin': r'\baspirin\b',
    'sulfa': r'\b(?:sulfa|sulfonamide|trimethoprim sulfamethoxazole|tmp smx|bactrim)\b',
    'pollen': r'\bpollen\b', 'dust': r'\bdust\b',
    'pets': r'\bpets?\b', 'cats': r'\bcats?\b', 'dogs': r'\bdogs?\b', 'mold': r'\bmou?ld\b',
    'peanuts': r'\bpeanuts?\b', 'shellfish': r'\b(?:shellfish|seafood)\b',
    'nuts': r'\bnuts?\b', 'milk': r'\b(?:milk|dairy)\b',
    'eggs': r'\beggs?\b', 'wheat': r'\bwheat\b', 'soy': r'\bsoy\b',
    'latex': r'\blatex\b', 'nickel': r'\bnickel\b',
}
_DRUG_TARGETS = {'penicillin', 'amoxicillin', 'codeine', 'neomycin', 'naproxen', 'aspirin', 'sulfa'}
_REACTION = re.compile(r"^(?:and )?(?:what (?:happens?|happened)(?: (?:when|if) you (?:take|eat|use|have|touch) (?:it|that|them))?|what (?:kind of )?reaction(?: (?:do|did) you (?:have|get))?|how (?:do|did) you react)(?: to (?:it|that|them))?$")


def scopes(text):
    return [scope for scope, pattern in _SCOPE_PATTERNS.items() if re.search(pattern, text)]


def request(utterance, previous=None):
    text = nlp.normalize(utterance).strip(' .?')
    explicit = bool(re.search(r'allerg|\bnkda\b|\bhay fever\b', text))
    followup = bool(previous and (_REACTION.fullmatch(text) or
                    re.fullmatch(r'(?:and |what about |how about )?(?:any )?(?:foods?|environmental|seasonal|medication|drug|pollen|dust|latex|pets|penicillin|amoxicillin|aspirin)(?: allergies)?', text)))
    if not explicit and not followup:
        return None
    selected = scopes(text)
    targets = [target for target, pattern in _TARGET_PATTERNS.items() if re.search(pattern, text)]
    if any(target in _DRUG_TARGETS for target in targets) and 'medication' not in selected:
        selected.insert(0, 'medication')
    if followup and not selected and not targets:
        return dict(previous)
    # A named allergen outside our vocabulary is unknown, not permission to
    # answer with an unrelated drug allergy. Keep the student's noun as scope.
    if not selected:
        named = re.search(r'allerg(?:ic|ies|y) to (.+)$', text)
        if named and not re.fullmatch(r'(?:anything|anything else|something)', named[1]):
            return {'scopes': ['named'], 'targets': [], 'label': named[1]}
        return None  # The established general-allergy route remains available.
    excluded_text = re.search(r'(?:other than|besides|apart from|except) (.+)$', text)
    excluded = [target for target, pattern in _TARGET_PATTERNS.items()
                if excluded_text and re.search(pattern, excluded_text[1])]
    return {'scopes': selected, 'targets': [t for t in targets if t not in excluded], 'excluded': excluded}


def scoped_list(utterance):
    """Keep allergy modifiers attached in single topics and shared-suffix lists."""
    text = nlp.normalize(utterance).strip(' .?')
    if re.fullmatch(r'(?:do you have |any |do you have any )?allergies to (?:any )?(?:food|foods|medicine|medicines|medications|drugs|pollen|dust|pets)(?: (?:or|and) (?:food|foods|medicine|medicines|medications|drugs|pollen|dust|pets))+', text):
        return True
    return bool(re.fullmatch(
        r'(?:do you have |have you had |any |do you have any )?'
        r'(?:drug|medication|food|environmental|seasonal|contact)'
        r'(?: allergies)?(?:,? (?:and |or )?(?:drug|medication|food|environmental|seasonal|contact)(?: allergies)?)*', text)
        and bool(scopes(text)) and 'allerg' in text)


def fact_scopes(fact):
    if fact.get('allergy_scopes'):
        return set(fact['allergy_scopes'])
    value = nlp.normalize(fact.get('value', ''))
    if fact.get('category') == 'allergies':
        # Questions and concepts disambiguate terse answers such as "None
        # that I know of", which belongs to NKDA in the authored case.
        source = ' '.join([value, *fact.get('example_questions', []),
                           *fact.get('concepts', {}).keys()]).lower()
        known = set(scopes(source))
        if any(re.search(_TARGET_PATTERNS[t], value) for t in _DRUG_TARGETS):
            known.add('medication')
        return known
    # A specific environmental response can be stored outside the drug
    # history. Do not disclose a bundled PMH answer containing other illness.
    if fact.get('category') in ('associated', 'aggravating', 'pmh') and re.search(
            r'\bpollen\b|\bdust\b|seasonal allerg|hay fever', value):
        if re.search(r'heartburn|other chronic|other illness', value):
            return set()
        if re.search(r'sneez|itch|nose runs|runny nose|seasonal allerg|hay fever', value):
            return {'environmental'}
    return set()


def _drug_negative(fact):
    value = nlp.normalize(fact.get('value', '')).strip(' .')
    return fact_scopes(fact) == {'medication'} and bool(re.search(
        r'no known (?:drug|medication|medicine) allergies|no (?:drug|medication|medicine) allergies|^none that i know of$|^nkda$', value))


def select(facts, asked):
    chosen, missing = [], []
    for scope in asked['scopes']:
        relevant = [f for f in facts if scope in fact_scopes(f)]
        excluded = asked.get('excluded', [])
        relevant = [f for f in relevant if not any(re.search(_TARGET_PATTERNS[t],
                    nlp.normalize(f.get('value', ''))) for t in excluded)]
        targets = [t for t in asked['targets'] if
                   (scope == 'medication' and t in _DRUG_TARGETS) or
                   (scope != 'medication' and scope in scopes(t))]
        if targets:
            # Each named target needs an answer; pollen does not cover cats,
            # and penicillin does not cover aspirin. NKDA covers named drugs.
            for target in targets:
                matches = [f for f in relevant if re.search(_TARGET_PATTERNS[target],
                           nlp.normalize(f.get('value', ''))) or (scope == 'medication' and _drug_negative(f))]
                chosen.extend(f for f in matches[:2] if f not in chosen)
                if not matches:
                    missing.append('allergy history for ' + target)
        elif relevant:
            chosen.extend(f for f in relevant[:2] if f not in chosen)
        else:
            missing.append('allergy history for ' + asked.get('label', '') if scope == 'named'
                           else ('other ' if excluded else '') + scope + ' allergies')
    return chosen, missing
