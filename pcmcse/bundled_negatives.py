"""Answer one member of a bundled pertinent negative without the rest.

Some cases author several negatives as one statement ("No, I haven't passed
out. No fluttering. I sleep flat, no problem. My ankles look normal."). A
question about one of them must hear that one: reciting the bundle discloses
answers the student never asked for and credits a checklist item for a
screen the student did not perform.

Each member is an approved focused clause in the fact's delivery contract,
exactly like the reproductive clauses (see reproductive_history.scoped_fact):
`complete_fact` is false, so a clause never releases the bundled fact or earns
its checklist item. A clause carries only its OWN member's authored concept,
never another member's, so documenting that one negative is supported and
nothing else is. A member the bundle authors no concept for is recorded as the
delivered text. The exact authored compound question, or a question naming
every member, still receives the complete statement.

Recognition below names symptom topics in a question. It never supplies an
answer: the words come only from the authored bundle.
"""
import re

from . import nlp

# Symptom topics as a student names them. Where one topic's phrase contains
# another's word ("coughing up blood"), the specific topic is listed in
# _NARROWER and removes its phrase before the broader one is tested.
TOPICS = {
    'syncope': r"\bfaint(?:ed|ing|s)?\b|\bpass(?:ed|es|ing)? out\b|\bblack(?:ed|ing)? out\b"
               r"|\b(?:lose|lost|losing|loss of) consciousness\b|\bsyncop\w*",
    'palpitations': r"\bpalpitations?\b|\bflutter\w*|\bracing heart\b|\bskipped beats?\b"
                    r"|\bheart\w* (?:(?:ever|been|is|was) )?(?:racing|race|races|pounding|pounds|skipping|skips|flip\w*|flutter\w*)\b",
    'orthopnea': r"\borthopnea\b|\b(?:lie|lying|lay|laying|sleep|sleeping) (?:down )?flat\b|\bflat (?:in bed|to sleep|at night)\b"
                 r"|\bpillows?\b|\bwak\w* up (?:at night )?(?:short of breath|breathless|gasping|unable to breathe|struggling to breathe)\b"
                 r"|\b(?:short of breath|breathless\w*|winded|trouble breathing)\b[^.?!]*\b(?:flat|lying down|lie down|at night|in bed)\b",
    'leg_swelling': r"\b(?:swell\w*|swollen|edema|oedema|puff\w*)\b[^.?!]*\b(?:legs?|ankles?|feet|foot|calf|calves|shins?)\b"
                    r"|\b(?:legs?|ankles?|feet|foot|calf|calves|shins?)\b[^.?!]*\b(?:swell\w*|swollen|edema|oedema|puff\w*)\b|\bedema\b",
    'hemoptysis': r"\bcough\w* (?:up )?(?:any )?blood\w*|\bblood\w* (?:when|while|if) (?:you )?cough\w*|\bhemoptysis\b"
                  r"|\bblood\w* (?:in (?:your |the )?)?(?:sputum|phlegm|mucus)\b",
    'cough': r"\bcough\w*",
    'wheezing': r"\bwheez\w*",
    'fever': r"\bfevers?\b|\bfeverish\b|\bfebrile\b|\btemperatures?\b",
    'chills': r"\bchills?\b|\bshiver\w*|\brigors?\b",
    'leg_pain': r"\b(?:legs?|calf|calves|shins?)\b[^.?!]*\b(?:pain\w*|hurt\w*|ache\w*|aching|sore\w*|tender\w*|cramp\w*)\b"
                r"|\b(?:pain\w*|hurt\w*|ache\w*|aching|soreness|tender\w*|cramp\w*)\b[^.?!]*\b(?:legs?|calf|calves)\b|\bclots?\b|\bdvt\b",
    'heartburn': r"\bheartburn\b|\breflux\b|\bindigestion\b|\bacid\b",
    'hematemesis': r"\b(?:vomit\w*|throw\w* up|threw up)\b[^.?!]*\bblood\w*|\bblood\w*[^.?!]*\b(?:vomit\w*|throw\w* up|threw up)\b"
                   r"|\bcoffee.?grounds?\b|\bhematemesis\b",
    'vomiting': r"\bvomit\w*|\bthrow\w* up\b|\bthrew up\b|\bemesis\b",
    'abdominal_pain': r"\b(?:belly|stomach|abdom\w*|tummy)\b[^.?!]*\b(?:pain\w*|ache\w*|aching|hurt\w*|discomfort|cramp\w*|sore\w*)\b"
                      r"|\b(?:pain\w*|ache\w*|hurt\w*|discomfort|cramp\w*)\b[^.?!]*\b(?:belly|stomach|abdom\w*|tummy)\b"
                      r"|\bstomach ?aches?\b|\bbelly ?aches?\b",
    'weight_change': r"\bweight\b|\b(?:lost|lose|losing|gained|gain|gaining|put on) (?:any |some )?(?:weight|pounds|lbs)\b",
    'dysphagia': r"\bswallow\w*|\bdysphagia\b",
    'jaundice': r"\byellow\w*|\bjaundice\w*|\bicter\w*",
    'diarrhea': r"\bdiarrh\w*|\bloose (?:stools?|bowel\w*)\b|\bwatery stools?\b",
    'chest_pain': r"\bchest\b[^.?!]*\b(?:pain\w*|pressure|discomfort|tight\w*|hurt\w*|ache\w*)\b"
                  r"|\b(?:pain|pressure|discomfort|tightness)\b[^.?!]*\bchest\b",
    'bruising': r"\bbruis\w*",
    'gum_bleeding': r"\bgums?\b[^.?!]*\bbleed\w*|\bbleed\w*[^.?!]*\bgums?\b",
    'epistaxis': r"\bnose ?bleeds?\b|\bbloody nose\b|\bnose\b[^.?!]*\bbleed\w*|\bbleed\w* (?:from|out of) (?:your |the )?nose\b|\bepistaxis\b",
    'weakness': r"\bweak\w*",
    'numbness': r"\bnumb\w*|\bpins and needles\b|\btingl\w*",
    'speech': r"\bspeech\b|\bslurr\w*|\baphasi\w*|\b(?:trouble|difficulty|problems?|changes?) (?:with )?(?:your )?(?:speaking|talking|finding (?:the )?words)\b"
              r"|\bspeak\w* (?:clearly|normally|properly)\b",
    'vision': r"\bvision\b|\bvisual\b|\beyesight\b|\bsight\b|\bdouble vision\b|\bblurr\w*|\bsee(?:ing)? (?:clearly|properly|normally|double|well)\b",
    'seizure': r"\bseizures?\b|\bfits?\b|\bconvuls\w*",
    'rash': r"\brash\w*|\bhives\b",
    'night_sweats': r"\bnight ?sweats?\b|\bsweat\w*[^.?!]*\bnight\b",
    'sick_contacts': r"\bsick contacts?\b|\b(?:anyone|anybody|someone|somebody|people)\b[^.?!]*\b(?:sick|ill|unwell)\b",
    'dyspnea': r"\bshort(?:ness)? of breath\b|\bbreathless\w*|\b(?:trouble|difficulty|problems?) (?:with )?(?:breathing|catching your breath)\b"
               r"|\bhard to breathe\b|\bwinded\b|\bdyspnea\b",
    'headache': r"\bheadaches?\b|\bhead (?:pain|hurt\w*|ache\w*)\b|\bmigraines?\b",
}
_TOPIC_RES = {topic: re.compile(pattern) for topic, pattern in TOPICS.items()}
# (narrower, broader): a match of the narrower removes its words first.
_NARROWER = [('hemoptysis', 'cough'), ('hematemesis', 'vomiting')]

# Labels for the Notes panel, where a partial answer is shown on its own.
LABELS = {
    'syncope': 'Fainting', 'palpitations': 'Palpitations', 'orthopnea': 'Breathing when lying flat',
    'leg_swelling': 'Leg swelling', 'hemoptysis': 'Coughing up blood', 'cough': 'Cough',
    'wheezing': 'Wheezing', 'fever': 'Fever', 'chills': 'Chills', 'leg_pain': 'Leg symptoms',
    'heartburn': 'Heartburn', 'hematemesis': 'Vomiting blood', 'vomiting': 'Vomiting',
    'abdominal_pain': 'Abdominal pain', 'weight_change': 'Weight change', 'dysphagia': 'Swallowing',
    'jaundice': 'Jaundice', 'diarrhea': 'Diarrhea', 'chest_pain': 'Chest pain',
    'bruising': 'Bruising', 'gum_bleeding': 'Gum bleeding', 'epistaxis': 'Nosebleeds',
    'weakness': 'Weakness', 'numbness': 'Numbness', 'speech': 'Speech', 'vision': 'Vision',
    'seizure': 'Seizures', 'rash': 'Rash', 'night_sweats': 'Night sweats',
    'sick_contacts': 'Sick contacts', 'dyspnea': 'Breathing', 'headache': 'Headache',
}

# The authored bundles, keyed by their complete approved text: each member's
# clause (in the bundle's own words), the topics it answers, and the member's
# own authored concept. `whole` lists topics only the complete statement
# answers ("have you vomited blood?" is answered by "I haven't thrown up at
# all, and definitely nothing bloody").
_FOCUS = {
    "No, I haven't passed out. No fluttering. I sleep flat, no problem. My ankles look normal.": {
        'clauses': [("No, I haven't passed out.", ['syncope'], ['no_syncope']),
                    ("No fluttering.", ['palpitations'], ['no_palpitations']),
                    ("I sleep flat, no problem.", ['orthopnea'], ['no_orthopnea']),
                    ("My ankles look normal.", ['leg_swelling'], ['no_leg_swelling'])]},
    "No cough, no coughing up blood, no wheezing. No fever. My legs feel fine.": {
        'clauses': [("No cough.", ['cough'], ['no_cough']),
                    ("No coughing up blood.", ['hemoptysis'], ['no_hemoptysis']),
                    ("No wheezing.", ['wheezing'], ['no_wheezing']),
                    ("No fever.", ['fever'], []),
                    ("My legs feel fine.", ['leg_pain'], [])]},
    "No heartburn. I haven't thrown up, and my belly doesn't hurt.": {
        'clauses': [("No heartburn.", ['heartburn'], ['no_reflux']),
                    ("I haven't thrown up.", ['vomiting'], ['no_vomiting']),
                    ("My belly doesn't hurt.", ['abdominal_pain'], ['no_abdominal_pain'])]},
    "No, I haven't thrown up at all, and definitely nothing bloody.": {
        'clauses': [("No, I haven't thrown up at all.", ['vomiting'], ['no_vomiting'])],
        'whole': ['hematemesis']},
    "My weight's about the same. No trouble swallowing, no fevers, and nobody's said I look yellow.": {
        'clauses': [("My weight's about the same.", ['weight_change'], ['no_weight_loss']),
                    ("No trouble swallowing.", ['dysphagia'], ['no_dysphagia']),
                    ("No fevers.", ['fever'], ['no_fever']),
                    ("Nobody's said I look yellow.", ['jaundice'], ['no_jaundice'])]},
    "No diarrhea. No chest pain either.": {
        'clauses': [("No diarrhea.", ['diarrhea'], ['no_diarrhea']),
                    ("No chest pain.", ['chest_pain'], ['no_chest_pain'])]},
    "No, I don't bruise easily. My gums don't bleed and I don't get nosebleeds.": {
        'clauses': [("No, I don't bruise easily.", ['bruising'], ['no_easy_bruising']),
                    ("My gums don't bleed.", ['gum_bleeding'], ['no_bleeding_gums']),
                    ("I don't get nosebleeds.", ['epistaxis'], ['no_epistaxis'])]},
    "No weakness, nothing numb, my speech is fine. My vision's normal apart from the light hurting. No seizures.": {
        'clauses': [("No weakness.", ['weakness'], ['no_focal_weakness']),
                    ("Nothing's numb.", ['numbness'], []),
                    ("My speech is fine.", ['speech'], []),
                    ("My vision's normal apart from the light hurting.", ['vision'], ['no_vision_change']),
                    ("No seizures.", ['seizure'], ['no_seizure'])]},
    "No fever, no chills. No rash. No night sweats, and my weight is the same. Nobody around me has been sick.": {
        'clauses': [("No fever.", ['fever'], ['no_fever']),
                    ("No chills.", ['chills'], []),
                    ("No rash.", ['rash'], ['no_rash']),
                    ("No night sweats.", ['night_sweats'], ['no_night_sweats']),
                    ("My weight is the same.", ['weight_change'], ['no_weight_loss']),
                    ("Nobody around me has been sick.", ['sick_contacts'], [])]},
    "No cough, no trouble breathing, no chest pain.": {
        'clauses': [("No cough.", ['cough'], ['cough']),
                    ("No trouble breathing.", ['dyspnea'], ['sob']),
                    ("No chest pain.", ['chest_pain'], ['chest_pain'])]},
    "No rash anywhere, and no headache. My weight is the same and I haven't had night sweats.": {
        'clauses': [("No rash anywhere.", ['rash'], ['rash']),
                    ("No headache.", ['headache'], ['headache']),
                    ("My weight is the same.", ['weight_change'], ['no_weight_loss']),
                    ("I haven't had night sweats.", ['night_sweats'], ['no_night_sweats'])]},
}


def topics(question):
    """The symptom topics a question names, in the order of TOPICS."""
    text = nlp.normalize(question)
    masked = text
    for narrow, _ in _NARROWER:
        if _TOPIC_RES[narrow].search(masked):
            masked = _TOPIC_RES[narrow].sub(' ', masked)
    broader = {broad for _, broad in _NARROWER}
    return [topic for topic, pattern in _TOPIC_RES.items()
            if pattern.search(masked if topic in broader else text)]


def _bundle(fact):
    if fact.get('category') != 'pertinent_negative':
        return None
    return _FOCUS.get(fact.get('value'))


def scoped_fact(fact):
    """Return a copy with each member's approved focused clause; never mutates."""
    bundle = _bundle(fact)
    if not bundle:
        return fact
    contract = fact.get('delivery_contract', {})
    versions = list(contract.get('versions', []))
    original = next((v for v in versions if v.get('complete_fact') and v.get('text') == fact['value']), None)
    if original is None:
        return fact  # An unverified legacy row cannot acquire richer metadata.
    for text, symptom_topics, concepts in bundle['clauses']:
        if any(v.get('text') == text and v.get('symptom_topics') == symptom_topics for v in versions):
            continue
        versions.append({'text': text,
                         'concepts': {cid: dict(original['concepts'][cid], value=text)
                                      for cid in concepts if cid in original.get('concepts', {})},
                         'complete_fact': False, 'symptom_topics': symptom_topics})
    return dict(fact, delivery_contract=dict(contract, versions=versions))


def members(fact):
    """Every topic this bundle answers, focused or only as a whole."""
    bundle = _bundle(fact)
    if not bundle:
        return set()
    return {t for _, ts, _ in bundle['clauses'] for t in ts} | set(bundle.get('whole', []))


def focus(fact, question):
    """The clauses to say for this question, or None for the complete statement.

    None when the fact is no bundle, when the question names no member, a
    member only the whole statement answers, or every member, and when it is
    the case's own authored compound ask. An authored example that names a
    single member ("have you vomited?") is a question about that member.
    """
    bundle = _bundle(fact)
    if not bundle or not question:
        return None
    asked = set(topics(question))
    named = asked & members(fact)
    asked_text = nlp.normalize(question).strip(' .?')
    if len(asked) != 1 and any(nlp.normalize(q).strip(' .?') == asked_text
                               for q in fact.get('example_questions') or []):
        return None
    chosen = [text for text, ts, _ in bundle['clauses'] if named & set(ts)]
    if not chosen or named & set(bundle.get('whole', [])) or named == members(fact):
        return None
    return chosen
