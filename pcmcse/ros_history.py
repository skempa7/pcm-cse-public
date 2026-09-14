"""Recognize ROS presence questions separately from symptom attributes.

Vocabulary identifies the student's topic only. All answers come from authored
patient statements; recognition never licenses an improvised clinical denial.
"""
import re
from . import nlp

# Question forms, authored spoken signals, and readable unavailable labels.
TOPICS = {
    'depression': (r'depress(?:ed(?: thoughts)?|ion)|low mood|feeling (?:down|sad)|sadness', r'depress|low mood', 'depressed mood'),
    'suicidal_thoughts': (r'suicidal (?:thoughts|ideation)|thoughts (?:of|about) (?:suicide|harming yourself|hurting yourself|ending your life)', r'suicid|self.harm|ending my life', 'suicidal or self-harm thoughts'),
    'chills': (r'chills?|shaking chills|shivering', r'chills?|shivering', 'chills'),
    'fever': (r'fevers?|feeling feverish', r'fever|febrile', 'fever'),
    'weight_change': (r'weight (?:changes?|loss|gain)|changes? in (?:your )?weight', r'weight', 'weight changes'),
    'headache': (r'headaches?|head pain', r'headaches?|head pain', 'headaches'),
    'myalgia': (r'(?:muscle|body) aches?|myalgias?|sore muscles|muscle soreness|aching muscles', r'(?:muscle|body) aches?|myalgia|sore muscles|muscle soreness|muscles.{0,20}ache|aching.{0,25}muscles', 'muscle aches'),
    'nausea': (r'nausea|nauseous|nauseated|queasy|queasiness', r'nausea|nauseous|nauseated|queasy', 'nausea'),
    'vomiting': (r'vomit(?:ing|ed)?|throw(?:ing|n)? up|emesis', r'vomit|throw(?:ing|n)? up|threw up|emesis', 'vomiting'),
    'dizziness': (r'dizziness|dizzy', r'dizzi|dizzy|light[ -]?head|vision.{0,15}dims|spinning|vertigo', 'dizziness'),
    'lightheadedness': (r'light[ -]?headed(?:ness)?|feeling faint|near.fainting|presyncope', r'light[ -]?head|vision.{0,15}dims|presyncope|nearly (?:faint|pass)', 'lightheadedness or near-fainting'),
    'vertigo': (r'vertigo|(?:the )?room spinning|spinning (?:sensation|feeling)', r'spinning|vertigo|room.{0,10}spin', 'spinning dizziness'),
    'tinnitus': (r'tinnitus|ringing (?:in (?:the|your) ears|ears)|ear ringing', r'tinnitus|ringing', 'ringing in the ears'),
}


def named(text):
    q = nlp.normalize(text)
    return [key for key, (pattern, _, _) in TOPICS.items()
            if re.search(r'(?<!\w)(?:' + pattern + r')(?!\w)', q)]


def request(utterance):
    """A complete symptom-presence question, including short ROS lists."""
    q = nlp.normalize(nlp.expand_contractions(utterance).replace(',', ' or ')).strip(' .?')
    q = re.sub(r'^(?:(?:and|so|okay|ok|now) )+', '', q)
    q = re.sub(r'^(?:how about|what about) ', '', q)
    if re.fullmatch(r'how (?:has your mood been|is your mood)|how have you been feeling emotionally', q):
        return ['depression']
    q = re.sub(r'^(?:(?:have|do|did|are) you|is there)(?: (?:have|had|been|felt|feel|noticed|notice|experienced|experience|having|feeling|experiencing|ever|get|getting))* ', '', q)
    q = re.sub(r'^(?:any other|any|some|other|a|an) ', '', q)
    if q in ('down', 'sad'):
        return ['depression']
    q = re.sub(r' (?:at all|recently|lately|with (?:that|it|this)|along with (?:that|it|this))$', '', q)
    # Lists are recognized only if every clause is an actual symptom topic.
    # Timing, treatment, another person's symptoms and causal questions keep
    # their existing routes rather than being mistaken for presence screens.
    parts = [part for part in re.split(r'\s+(?:and|or)\s+', q) if part not in ('and', 'or')]
    found = []
    for part in parts:
        part = re.sub(r'^(?:any|some) ', '', part)
        key = next((key for key, (pattern, _, _) in TOPICS.items()
                    if re.fullmatch(pattern, part)), None)
        if key is None:
            return None
        if key not in found:
            found.append(key)
    return found or None


def select(facts, topic):
    """Match symptom statements, excluding drug reactions and hidden findings."""
    pattern, signals, _ = TOPICS[topic]
    found = []
    for fact in facts:
        if fact.get('category') not in ('associated', 'pertinent_negative', 'chief_complaint'):
            continue
        if fact.get('requires_current_status_question'):
            continue
        # A generic core concept can conflate dizziness/syncope or ringing/
        # hearing loss. Match authored words and triggers, not grading aliases.
        direct = any(re.fullmatch(pattern, nlp.normalize(t).strip(' .?'))
                     for t in fact.get('triggers', {}).get('any', []))
        # Loose triggers can mention a sibling symptom the answer never
        # discusses (e.g. nausea has a vomiting trigger). Every selectable
        # speech version must actually name the requested symptom. Preserve
        # existing authored bundles rather than falsely marking them absent.
        lines = [line for line in (fact.get('sp_says') or [fact.get('value', '')])
                 if re.search(signals, nlp.normalize(line))]
        if not lines:
            continue
        found.append((2 if direct else 1, dict(fact, sp_says=lines)))
    if not found:
        return []
    best = max(score for score, _ in found)
    candidates = [fact for score, fact in found if score == best]
    positive = [fact for fact in candidates if fact.get('category') != 'pertinent_negative']
    return (positive or candidates)[:1]


def exam_transition(utterance):
    q = nlp.normalize(nlp.expand_contractions(utterance)).strip(' .?')
    q = re.sub(r'^(?:(?:okay|ok|and|so|now|next) )+', '', q)
    return bool(re.fullmatch(
        r'(?:let us|i (?:would like to|want to|am going to|will)|we (?:will|can)) '
        r'(?:move on to|move to|start|begin|proceed (?:with|to)) '
        r'(?:the |your |a )?(?:physical )?(?:exam|examination)(?: now| next)?', q))


def history_transition(utterance):
    """Only an announcement of ROS questions, never an invitation to volunteer."""
    q = nlp.normalize(nlp.expand_contractions(utterance)).strip(' .?')
    q = re.sub(r'^(?:(?:okay|ok|and|so|now|next) )+', '', q)
    return bool(re.fullmatch(
        r'i (?:will|am going to|would like to) ask (?:you )?about '
        r'(?:a few |some )?(?:other symptoms|your (?:symptoms|review of systems))', q))


def attribute(utterance):
    """Bounded secondary-symptom attributes, not presence or general history."""
    q = nlp.normalize(utterance)
    for pattern, label, categories in [
        (r'when.*(?:start|begin|began)|how long (?:have|has).*had', 'onset', {'onset'}),
        (r'how long', 'duration', {'episode_duration', 'timing'}),
        (r'what (?:causes|caused)|why .* (?:get|have)', 'cause', {'cause'}),
        (r'what.*(?:makes?|make).*worse|what.*aggravat', 'aggravating factors', {'aggravating'}),
        (r'what.*(?:take|taking|treat)|what.*(?:helps?|reliev|better)', 'treatment or relief', {'treatment', 'relieving'}),
        (r'how (?:bad|severe)', 'severity', {'severity'}),
    ]:
        if re.search(pattern, q):
            return label, categories
    return None
