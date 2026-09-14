"""Bounded everyday history and closing speech acts; no clinical content."""
import re
from . import nlp


def normalized(text):
    q = nlp.normalize(nlp.expand_contractions(text)).strip(' .?')
    return re.sub(r'^(?:(?:okay|ok|and|so|now|next|well) )+', '', q)


def diet_request(text):
    q = normalized(text)
    topic = r'(?:your |the )?(?:(?:usual|typical|daily|normal) )?(?:diet|eating habits|meals)'
    forms = [r'(?:how (?:would|do|could) you describe|describe|tell me about) ' + topic,
             r'what (?:is|are) ' + topic + r'(?: like)?',
             r'how (?:is|are) ' + topic,
             r'what do you (?:(?:usually|typically|normally) )?eat(?: (?:on|in) a (?:typical|normal|usual) day| for meals)?',
             r'what (?:does|would) a (?:typical|usual|normal) day of (?:eating|meals) look like(?: for you)?',
             r'how (?:would|do|could) you describe what you eat',
             r'(?:can|could|would) you (?:describe|tell me about) ' + topic]
    return any(re.fullmatch(pattern, q) for pattern in forms)


def closing_invitation(text):
    q = normalized(text)
    # A clinician's plans after this invitation do not change what was asked.
    q = re.sub(r' before (?:i (?:go |leave|speak|talk|discuss|report|check)|we (?:finish|wrap up)).*$', '', q)
    forms = [r'(?:is there )?(?:anything|something) (?:else )?(?:you (?:would like|want|need) (?:for )?me to know|you (?:would like|want) to (?:add|tell me|mention|discuss))',
             r'(?:do you have |have you got |are there )?any (?:other |more |further )?(?:questions|concerns|comments)(?: for me| about (?:this|the plan|your care))?',
             r'what (?:other )?questions do you have(?: for me)?',
             r'(?:is there )?anything (?:else )?you (?:would like|want) to ask(?: me)?',
             r'is there anything you are worried about',
             r'does that make sense']
    return any(re.fullmatch(pattern, q) for pattern in forms)


def handoff_statement(text):
    """A plain announcement, not consent, a question, or an encounter action."""
    q = normalized(text)
    start = r'i (?:am going to|will|would like to|need to) '
    clinician = r'(?:my|the|our) (?:attending(?: physician)?|supervising (?:doctor|physician|clinician)|supervisor)'
    task = (r'(?:let ' + clinician + r' know|(?:speak|talk|check) (?:to|with) ' + clinician +
            r'|update ' + clinician + r'|(?:discuss|review|go over|share) (?:this|your case|the case|everything|what we discussed|my findings) with ' + clinician + ')')
    ending = r'(?: and (?:i )?(?:will |am going to )?(?:be|come) (?:right |straight )?back(?: (?:soon|shortly|in a (?:moment|minute)))?)?'
    return bool(re.fullmatch(start + task + ending, q) or re.fullmatch(
        r'i (?:will|am going to) (?:be|come) (?:right |straight )?back(?: (?:soon|shortly|in a (?:moment|minute)))?', q))


def handoff_preface(text):
    return normalized(text) in ('before i go', 'before i leave')


def diet_detail(text, active=False):
    q = normalized(text)
    meal = re.fullmatch(r'(?:what about |how about |what do you (?:usually |normally )?eat for |what is (?:your )?)(breakfast|lunch|dinner|supper|snacks)(?: like)?', q)
    if meal:
        return meal[1]
    if active and re.fullmatch(r'how long(?: have you (?:eaten|been eating) (?:that|this) way)?|how often|how many (?:meals|calories)|how much(?: do you eat)?', q):
        return 'that detail about eating habits'
    return None
