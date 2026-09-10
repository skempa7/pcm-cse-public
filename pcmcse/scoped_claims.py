"""Bounded, compositional documentation proofs over delivered text only.

2026-09-10: Ordinary combined summaries must not borrow an unreleased aggregate.
Unknown modifiers remain unscored. The case supplies topic/category identifiers;
only actual patient or examination events can establish their clinical content.
"""
import re
from . import nlp, evidence

NUMBERS = dict(zip('one two three four five six seven eight nine ten eleven twelve'.split(), map(str, range(1,13))))
UNITS = {'hour':3600, 'hr':3600, 'h':3600, 'minute':60, 'min':60, 'day':86400}


def intervals(text):
    t=nlp.normalize(text)
    t=re.sub(r'\b('+ '|'.join(NUMBERS)+r')(?=\s+(?:hours?|hrs?|minutes?|mins?|days?)\b)',lambda m:NUMBERS[m.group()],t)
    t=re.sub(r'\b(?:a )?couple of minutes\b','2 minutes',t)
    out=[]
    for m in re.finditer(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|days?)\b',t):
        out.append((float(m.group(1))*UNITS[m.group(2).rstrip('s')],m.span()))
    return out,t


def result(verdict,events,concepts,message):
    return {'verdict':verdict,'events':list({e['seq']:e for e in events}.values()),'concepts':sorted(set(concepts)), 'explanation':message}


def fact_events(case,ledger,category):
    for fact in case.get('facts',[]):
        if fact.get('category')!=category:continue
        for ev in ledger.by_kind(evidence.PATIENT):
            ids=set(fact.get('concepts',{})) & set(ev['meta'].get('concepts',{}))
            if ids and fact['id'] in ev['meta'].get('facts_released',[]):yield ev,ids


def neuro_atoms(text):
    t=nlp.normalize(text).strip(' .');atoms={};used=[]
    names={'biceps':'biceps','triceps':'triceps','patellar':'patellar','patellae':'patellar','achilles':'achilles'}
    sites=list(re.finditer(r'\b(?:biceps|triceps|patellar|patellae|achilles)\b',t))
    grades=list(re.finditer(r'(?<!\w)([0-4])\+(?!\d)',t))
    symmetry=list(re.finditer(r'\b(?:symmetric|symmetrical|asymmetric|asymmetrical)\b',t))
    if sites and len(grades)==1:
        used.extend(x.span() for x in sites+grades+symmetry)
        for site in sites:
            key='reflex_'+names[site.group()];atoms[key+'_grade']=int(grades[0].group(1))
            if len(symmetry)==1:atoms[key+'_symmetry']='asymmetric' if symmetry[0].group().startswith('a') else 'symmetric'
        residue=''.join(' ' if any(a<=i<b for a,b in used) else c for i,c in enumerate(t))
        fillers=set('and at the are is were was reflex reflexes dtr dtrs deep tendon bilateral bilaterally'.split())
        return atoms,not any(w not in fillers for w in re.findall(r'[a-z0-9]+',residue))
    for pattern,values in [
        (r'(?:marked )?resistance and pain (?:on|with|during) passive neck flexion',{'neck_flexion_resistance':'present','neck_flexion_pain':'present'}),
        (r'(?:nuchal rigidity|neck stiffness|resistance) (?:on|with|during) (?:passive )?(?:neck )?flexion',{'neck_flexion_resistance':'present'}),
        (r'(?:no|without) (?:nuchal rigidity|neck stiffness|resistance) (?:on|with|during) (?:passive )?(?:neck )?flexion',{'neck_flexion_resistance':'absent'}),
    ]:
        if re.fullmatch(pattern,t):return values,True
    return {},False


def component_exam(claim,ledger):
    if claim['section']!='O':return None
    text=claim.get('eval_text') or claim['text'];atoms,complete=neuro_atoms(text)
    family='neuro_reflexes' if re.search(r'\b(?:biceps|triceps|patell\w*|achilles)\b',nlp.normalize(text)) and re.search(r'\breflex\w*\b|\d\+',text,re.I) else 'neck_rom' if 'nuchal rigidity' in nlp.normalize(text) else None
    if not atoms and not family:return None
    sources=[ev for ev in ledger.by_kind(evidence.EXAM_FINDING) if ev['meta'].get('maneuver_id') in ('neuro_reflexes','neck_rom')]
    if not atoms:
        related=[ev for ev in sources if ev['meta'].get('maneuver_id')==family]
        # Do not send an unparsed numerical/side-qualified statement into an
        # old aggregate alias that ignores the additional grade or laterality.
        return result('not_evaluated' if related else 'unsupported',related,[], 'This specific wording needs comparison with the released findings; it receives no automatic credit.' if related else 'No corresponding examination finding was released.')
    available={};links={};parsed_sources=[]
    for ev in sources:
        for clause in re.split(r';|(?<!\d)\.(?!\d)',ev['text']):
            actual,known=neuro_atoms(clause)
            if not known:continue
            parsed_sources.append(ev)
            for key,value in actual.items():available[key]=value;links[key]=ev
    bad=[k for k in atoms if k in available and atoms[k]!=available[k]]
    if bad:return result('contradicts',[links[k] for k in bad],[], 'The documented site-specific grade or finding differs from the actual released examination.')
    if not complete:return result('not_evaluated',sources,[], 'Some attributes match, but the additional wording was not fully resolved. Compare the linked findings; this is not a proven false statement and receives no automatic credit.')
    missing=[k for k in atoms if k not in available]
    if missing:
        related=[e for e in sources if e['meta'].get('maneuver_id')==('neuro_reflexes' if any(k.startswith('reflex_') for k in atoms) else 'neck_rom')]
        unknown_source=related and not any(e in parsed_sources for e in related)
        return result('not_evaluated' if unknown_source else 'unsupported',related,[], 'The released wording could not be fully interpreted; compare it manually.' if unknown_source else 'The encounter did not release every site or attribute asserted here. Selected reflexes do not establish the untested reflexes.')
    events=[links[k] for k in atoms]
    return result('supported',events,[cid for ev in events for cid in ev['meta'].get('concepts',{})], 'Each named site, grade and finding is supported by the actual examination result. No untested component is inferred.')


def headache_summary(claim,case,ledger,summary_target):
    if claim['section']!='S' or claim.get('header') not in ('cc','hpi',None):return None
    text,demographics=summary_target(claim,ledger);matches,t=intervals(text);t=t.strip(' .')
    if len(re.findall(r'\bheadache\b',t))!=1 or len(matches)!=1:return None
    interval,span=matches[0];residue=t[:span[0]]+' '+t[span[1]:]
    severe=bool(re.search(r'\bsevere\b',residue));abrupt=bool(re.search(r'\b(?:sudden|suddenly|abrupt)\b',residue))
    residue=re.sub(r'\b(?:severe|sudden|suddenly|abrupt|headache)\b',' ',residue)
    fillers=set('a the with for beginning began starting started onset about approximately ago'.split())
    if any(w not in fillers for w in re.findall(r'[a-z0-9]+',residue)):return None
    openings=[]
    for ev in ledger.by_kind(evidence.PATIENT):
        if ev['meta'].get('kind')!='opening':continue
        for clause in re.split(r'[.!?]',ev['text']):
            times,spoken=intervals(clause)
            if re.search(r'\bheadache\b',spoken) and len(times)==1 and not re.search(r'\b(?:no headache|never|not had|used to|previous)\b',spoken):openings.append((ev,times[0][0],spoken))
    if not openings:return None
    found=next((x for x in openings if x[1]==interval),None)
    if not found:return result('contradicts',[x[0] for x in openings],[], 'The stated headache onset interval differs from the opening actually delivered.')
    events=[found[0]]+demographics;ids=list(found[0]['meta'].get('concepts',{}))
    if abrupt and not re.search(r'\b(?:sudden\w*|abrupt\w*|like someone hit me)\b',found[2]):return result('unsupported',events,[], 'This onset summary adds an abruptness that the delivered opening did not establish.')
    if severe:
        severity=next(((ev,cids) for ev,cids in fact_events(case,ledger,'severity') if re.search(r'^(?:(?:the )?pain (?:is )?)?(?:ten out of (?:ten|10)|10\s*/\s*10|severe|excruciating|terrible)\b',nlp.normalize(ev['text']))),None)
        if not severity:return result('not_evaluated',events,[], 'The onset was obtained, but this summary’s severity description was not fully verified. Compare the reported severity; no automatic credit is assigned to the combined claim.')
        events.append(severity[0]);ids.extend(severity[1])
    # Classify proven onset information for rubric rows without altering the
    # ledger or treating the rest of a bundled hidden fact as delivered.
    for f in case.get('facts',[]):
        if f.get('category')=='onset' and any(x[0]==interval for x in intervals(f.get('value',''))[0]):ids.extend(f.get('concepts',{}))
    return result('supported',events,ids,'The headache onset comes from the delivered opening; any severity description is separately grounded in the actual severity answer. This does not establish unasked features or constant intensity.')


def relief_parts(text,source=False):
    t=nlp.normalize(text).strip(' .');times,t=intervals(t)
    if len(times)>1:return None
    duration=times[0][0] if times else None
    if times:
        a,b=times[0][1];t=t[:a]+' '+t[b:]
    t=re.sub(r'\b(?:about|approximately|for)\b',' ',t);t=re.sub(r'\s+',' ',t).strip()
    if source:
        m=re.fullmatch(r'if i (.+) (?:it|the pressure|the pain) (?:goes away|resolves|disappears)',t)
        if not m:return None
        activity=m.group(1);symptom='context'
    else:
        m=re.fullmatch(r'(?:the )?(pressure|chest pressure|chest pain|pain|symptoms|it) (?:resolves|goes away|disappears|is relieved) (?:after|with|when) (.+)',t)
        if not m:return None
        symptom,activity=m.groups()
    activity=re.sub(r'\b(?:stopping|stopped)\b','stop',activity)
    activity=re.sub(r'\bstanding\b','stand',activity)
    activity=re.sub(r'\bresting\b','rest',activity)
    if activity not in ('stop','stop and stand still','stop and rest','rest'):return None
    return {'symptom':symptom,'duration':duration,'activity':'rest','resolution':True}


def relief_history(claim,case,ledger):
    if claim['section']!='S' or claim.get('header') not in ('hpi',None):return None
    target=relief_parts(claim.get('eval_text') or claim['text'])
    if not target:return None
    eligible=[]
    for ev,ids in fact_events(case,ledger,'alleviating'):
        actual=relief_parts(ev['text'],True)
        if actual:eligible.append((ev,ids,actual))
    if not eligible:return result('unsupported',[],[], 'The specific relief pattern and its timing were not delivered. A general opening about stopping does not establish an unasked relief interval.')
    # A named symptom cannot borrow another complaint’s pronoun-based reply.
    if target['symptom'] not in ('it','symptoms','pain') and not any(target['symptom'] in nlp.normalize(ev['text']) for ev in ledger.by_kind(evidence.PATIENT) if ev['meta'].get('kind')=='opening'):
        return result('not_evaluated',[x[0] for x in eligible],[], 'The relief was reported, but its connection to the named symptom needs manual comparison; it is not automatically credited.')
    match=next((x for x in eligible if target['duration'] is None or target['duration']==x[2]['duration']),None)
    if not match:return result('contradicts',[x[0] for x in eligible],[], 'The relief interval in the note differs from the interval the patient actually reported.')
    return result('supported',[match[0]],match[1], 'The actual answer establishes resolution with stopping/rest and the stated relief interval. This is a reported symptom pattern, not an observed result of treatment.')


def canonical_prior(text):
    t=nlp.normalize(text).strip(' .')
    first=re.fullmatch(r'(?:(?:this is |it is )?(?:her |his |the patient\'s )?|(?:she|he|the patient) (?:has|is having) (?:her |his |a )?)first(?: ever)? episode of (?P<s>(?:complete )?(?:urinary )?retention|palpitations)',t)
    if first:return 'no previous '+first['s'],True
    never=re.fullmatch(r'(?:(?:she|he|the patient) )?(?:had |has )?never (?:been unable to (?:urinate|pass urine)|had (?:complete )?(?:urinary )?retention) (?:before today|before this episode|before)',t)
    if never:return 'no previous complete urinary retention',False
    t=re.sub(r'^(?:(?:the )?patient |she |he )?(?:reports? )?','',t)
    t=re.sub(r'^(?:has |had )?no history of ((?:complete )?(?:urinary )?retention|palpitations)$',r'no previous \1',t)
    return t,False


def evaluate(claim,case,ledger,summary_target):
    return component_exam(claim,ledger) or headache_summary(claim,case,ledger,summary_target) or relief_history(claim,case,ledger)
