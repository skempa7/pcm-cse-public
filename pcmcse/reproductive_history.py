"""Keep parenthood, past pregnancies and current pregnancy questions distinct.

Only authored history is selected. Living arrangements and delivery events
never confer a complete gravidity/parity or a negative pregnancy-loss history.
"""
import re
from . import nlp

LABELS = {
    'children': 'whether the patient has children',
    'children_count': 'the total number of children',
    'child_age': "the children's ages",
    'pregnancy_history': 'previous pregnancies',
    'pregnancy_count': 'the total number of pregnancies',
    'deliveries': 'previous deliveries',
    'parity': 'the complete obstetric history and parity',
    'losses': 'pregnancy losses or terminations',
    'current_pregnancy': 'current pregnancy possibility',
    'pregnancy_test': 'pregnancy testing',
}


def request(utterance, previous=None):
    q = nlp.normalize(utterance).strip(' .?')
    # A child's illness is family history, not a parenthood-count question.
    if re.search(r'(?:children|kids|son|daughter) (?:with|who (?:have|has)) ', q):
        return None
    found = []
    if re.search(r'how old (?:are|is) (?:your )?(?:kids|children|son|daughter)|what are (?:your children.s|their) ages', q):
        found.append('child_age')
    elif (re.search(r'(?:do you have|have you got|have you (?:ever )?had) (?:any )?(?:kids|children)\b|how many (?:kids|children)|are you a parent', q)
          or re.fullmatch(r'(?:any )?(?:kids|children)', q)
          or (protected_question(q) and re.search(r'\b(?:kids|children)\b', q))):
        found.append('children_count' if 'how many' in q else 'children')
    if re.search(r'\bmiscarri|pregnancy losses|lost (?:a |any )?(?:pregnancies|pregnancy|babies|baby)|stillbirth|termination|abortion', q):
        found.append('losses')
    if re.search(r'\bparity\b|gravida.*para|\bg\s*\d+\s*p\s*\d+', q):
        found.append('parity')
    elif re.search(r'\b(?:gravida|gravidity)\b|how many (?:total )?(?:times[^.!?]*pregnant|pregnancies)', q):
        found.append('pregnancy_count')
    elif re.search(r'(?:have you|had you) (?:ever )?(?:been pregnant|had (?:any |a )?pregnancies|had (?:any |a )?pregnancy)'
                   r'|(?:prior|previous|past|earlier|last) pregnan|pregnant (?:before|previously)|ever (?:been )?pregnant|obstetric history|pregnancy history|\bany pregnancies\b', q):
        found.append('pregnancy_history')
    if 'losses' in found and re.search(r'pregnanc(?:y|ies) (?:that |which )?(?:ended in|resulted in)', q):
        found = [d for d in found if d not in ('pregnancy_history', 'pregnancy_count')]
    if re.search(r'given birth|give birth|had (?:a |any )?(?:babies|baby)|(?:previous|past|any|had) deliveries|how many (?:births|deliveries)|delivered (?:a |any )?(?:babies|baby)', q):
        found.append('deliveries')
    if re.search(r'pregnancy test|tested for pregnancy', q):
        found.append('pregnancy_test')
    if re.search(r'(?:are|could|might|can) you (?:possibly |currently |be )?pregnant|chance[^.!?]*pregnan'
                 r'|pregnant (?:now|right now|currently)|currently pregnant|think you (?:are|might be|could be) pregnant', q):
        found.append('current_pregnancy')
    if not found and previous:
        if re.fullmatch(r'how many(?: times)?|how many have you had', q):
            found = ['children_count' if any(d.startswith('child') for d in previous)
                     else 'pregnancy_count' if 'pregnancy_history' in previous else previous[-1]]
        elif re.fullmatch(r'how old (?:are|is) (?:they|she|he|your children|your kids)|what are their ages', q) and any(d.startswith('child') for d in previous):
            found = ['child_age']
        elif re.fullmatch(r'when|when was that|how long ago|what about before|and before', q):
            found = ['pregnancy_history'] if 'before' in q and 'current_pregnancy' in previous else list(previous)
    return list(dict.fromkeys(found)) or None


def protected_question(utterance):
    q = nlp.normalize(utterance).strip(' .?')
    # A shared short list must not become a generic period question.
    return bool(re.fullmatch(r'(?:any |do you have any )?(?:prior |previous )?(?:pregnancies|children|kids)(?: (?:or|and) (?:prior |previous )?(?:pregnancies|children|kids))+', q))



# Exact authored statements from earlier saved cases. This narrow compatibility
# map gives their focused clauses the same contract as newly generated cases;
# it never changes the saved case or manufactures a clinical negative.
_SCOPED_SPEECH = {
    'Gallbladder out at twenty-five. And two children, both normal deliveries.': [
        ('And two children, both normal deliveries.', ['pregnancy_history', 'deliveries'], ['obstetric_history'])],
    'My period was one week ago. I use condoms and have not done a pregnancy test.': [
        ('I have not done a pregnancy test.', ['pregnancy_test'], [])],
    'My period was two weeks ago. I use an IUD and do not think I am pregnant.': [
        ('I do not think I am pregnant.', ['current_pregnancy'], [])],
    'My partner helps with our toddler, but missing work for appointments is difficult.': [
        ('I have a toddler.', ['children', 'child_age'], [])],
    'I live alone. My daughter can drive me, but I lose pay for weekday visits.': [
        ('I have a daughter.', ['children'], [])],
}


def scoped_fact(fact):
    """Return a copy with approved focused speech; preserve saved source facts."""
    clauses = _SCOPED_SPEECH.get(fact.get('value'))
    if not clauses:
        return fact
    contract = fact.get('delivery_contract', {})
    versions = list(contract.get('versions', []))
    original = next((v for v in versions if v.get('complete_fact')
                     and v.get('text') == fact['value']), None)
    if original is None:
        return fact  # An unverified legacy row cannot acquire richer metadata.
    for text, dimensions, concepts in clauses:
        if any(v.get('text') == text and v.get('history_dimensions') == dimensions for v in versions):
            continue
        versions.append({'text': text,
                         'concepts': {cid: dict(original['concepts'][cid], value=text)
                                      for cid in concepts if cid in original.get('concepts', {})},
                         'complete_fact': False, 'history_dimensions': dimensions})
    return dict(fact, delivery_contract=dict(contract, versions=versions))


def dimensions(fact):
    text = nlp.normalize(fact.get('value', ''))
    found = set()
    if fact.get('category') == 'social' and re.search(
            r'\b(?:my|our) (?:[a-z-]+ ){0,3}(?:children|child|kids|son|daughter|toddler)\b'
            r'|live with my (?:husband|wife|partner) and (?:a |one |two |three )?(?:child|children|kids)', text):
        found.add('children')
        if re.search(r'\b(?:one|two|three|four|five|\d+) (?:children|kids)\b', text):
            found.add('children_count')
        if re.search(r'(?:years?[ -]old|teenage|toddler)', text):
            found.add('child_age')
    if fact.get('category') in ('psh', 'obgyn') and re.search(r'cesarean|normal deliveries|gave birth|given birth', text):
        found.update(('pregnancy_history', 'deliveries'))
    if fact.get('category') == 'obgyn':
        if fact.get('history_topic') == 'pregnancy' or re.search(r'(?:am|be) pregnant|pregnancy is possible', text):
            found.add('current_pregnancy')
        if re.search(r'pregnancy test', text):
            found.add('pregnancy_test')
    for version in fact.get('delivery_contract', {}).get('versions', []):
        found.update(version.get('history_dimensions', []))
    return found


def select(facts, asked):
    selected, missing = [], []
    facts = [scoped_fact(f) for f in facts]
    for dimension in asked:
        # A birth or a child is not a complete count of all pregnancies or
        # proof that there were no losses. Totals require explicit authoring.
        matches = [f for f in facts if dimension in dimensions(f)]
        if not matches:
            missing.append(LABELS[dimension])
            continue
        # Prefer the household answer for parenthood, not clinical exposure
        # or unrelated childcare work. The authored qualifiers stay intact.
        for fact in matches[:1]:
            versions = [v for v in fact.get('delivery_contract', {}).get('versions', [])
                        if dimension in v.get('history_dimensions', [])]
            if versions:
                spoken = dict(fact, sp_says=[versions[0]['text']])
            else:
                spoken = fact
            if not any(f['id'] == spoken['id'] and f.get('sp_says') == spoken.get('sp_says') for f in selected):
                selected.append(spoken)
    return selected, missing
