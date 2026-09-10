"""Case-specific guided practice: authored actions, completion from delivered evidence.

This is a learning path, not a replacement rubric or a claim of hands-on skill.
The authored walkthrough supplies questions and examination selections; its
patient answers and example findings never enter the live coach payload.
"""
import json
import re
from . import audit, evidence, physexam, lexicon, nlp

GROUPS = [('connect','Meet the patient'), ('opening','Hear the concern'),
          ('pattern','Build the symptom story'), ('discriminate','Ask what changes the picture'),
          ('background','Medical background'), ('context','Life and family'),
          ('perspective','Understand their perspective'), ('ros','Check your history coverage'),
          ('prepare','Explain and prepare'), ('examine','Focused examination'),
          ('close','Explain and close'), ('document','Build your SOAP from evidence')]
GROUP_OF = {'Listen to the opening':'opening','Recognize urgency':'opening',
            'Build the symptom pattern':'pattern','Discriminate the possibilities':'discriminate',
            'Relevant background':'background','Medicines and reactions':'background',
            'Life and context':'context','The patient’s perspective':'perspective',
            'Explain next steps':'close','Close and check understanding':'close',
            'Address the patient’s question':'close'}
WHY = {'opening':'Hear the complaint in the patient’s words before narrowing the story.',
       'pattern':'Capture time, place, quality, severity, modifiers and change; these support the HPI.',
       'discriminate':'A positive or negative answer can change urgency and the next useful question.',
       'background':'Past illness, surgery, medicines and allergy reactions change what is safe and plausible.',
       'context':'Document tobacco, alcohol and drugs, relevant life context, and biological parents and siblings.',
       'perspective':'Learn what this means to the patient. FIFE: feelings, ideas, function and expectations.',
       'close':'Explain your working concern and next steps, then check questions and understanding.'}


def allowed(s):
    return s.settings.get('learning_mode') == 'guided' and s.row['phase'] in ('encounter','organize','note')


def _task(ident, group, title, question='', why='', **extra):
    return dict(id=ident, group=group, title=title, question=question, why=why,
                kind='question', **extra)


def plan(s):
    from . import teaching
    lesson = teaching.read(s.case['id'], s.case.get('variant_id','base'))
    if not lesson:
        raise ValueError('This case variation has no authored walkthrough available.')
    facts = {f['id']:f for f in s.case.get('facts',[])}
    tasks = [
        _task('connect.introduce','connect','Introduce yourself and your role',
              'Hello, I am a student doctor. I will listen to your concerns and discuss the next steps with you.',
              'A clear role and agenda make the opening predictable and respectful.', courtesy='introduce'),
        _task('connect.name','connect','Confirm how to address the patient',
              'Can you confirm your name, and what would you like me to call you?',
              'Confirm identity and the patient’s preferred form of address.', courtesy='confirm_name'),
        _task('connect.hands','connect','Clean your hands', 'I sanitize my hands.',
              'State this action in the simulator; real hand hygiene remains a hands-on skill.', courtesy='hand_hygiene')]
    planned = set()
    symptom_concepts = set()
    closings = []
    for index, row in enumerate(lesson.get('timeline',[])):
        if row.get('kind') != 'dialogue':
            continue
        section = row.get('section','')
        if section in ('Connect','Explain and ask permission','Acknowledge'):
            continue
        group = GROUP_OF.get(section)
        if not group:
            continue
        fids = [fid for fid in row.get('fact_ids',[]) if fid in facts]
        if group == 'close':
            fids = []  # Closing is a communication act, even if an answer repeats history.
        if row.get('fact_ids') and not fids and group != 'close':
            continue
        # Avoid asking a broad symptom bundle and its redundant single-symptom
        # examples merely to match a script. HPI time/context facts remain distinct.
        symptom = fids and all(facts[fid].get('category') in ('associated','pertinent_negative') for fid in fids)
        concepts = {cid for fid in fids for cid in facts[fid].get('concepts',{})}
        if fids and set(fids) <= planned:
            continue
        if symptom and concepts and concepts <= symptom_concepts:
            continue
        if symptom:
            symptom_concepts.update(concepts)
        planned.update(fids)
        ident = 'history.' + '.'.join(fids) if fids else 'dialogue.' + str(index)
        item = _task(ident, group, row.get('student','').strip(), row.get('student','').strip(),
                     row.get('why') or WHY.get(group,''), facts=fids)
        if section == 'Recognize urgency':
            item.update(kind='decision', title='Check whether urgent help is needed', question='',
                        why=lesson.get('plan',{}).get('notice','Review the current complaint and supplied vital signs.'),
                        decision_note='Review the current symptoms and supplied vital signs. If they suggest a time-sensitive emergency, explain your concern and escalate promptly. A flagged teaching case does not by itself mean every patient needs emergency transfer. Do not delay needed care for this learning path.')
        elif not fids:
            item['match'] = 'urgent' if section=='Recognize urgency' else 'education' if section=='Address the patient’s question' else 'counsel' if section=='Explain next steps' else 'closure'
        if group == 'close':
            closings.append(item)
        else:
            tasks.append(item)
    # Review the *obtained* history before examination; this is not an auto-filled note.
    tasks.append(dict(id='checkpoint.history', group='ros', title='Review the Subjective evidence you have gathered',
                      kind='checkpoint', question='', why='The course ROS requirement is three symptoms from each of three pertinent systems. History already obtained can be organized under ROS; you need not ask the same symptom twice.', checkpoint='history'))
    tasks.extend([
        _task('prepare.consent','prepare','Explain the examination and ask permission',
              'With your permission, I would like to examine you. I will explain each step. Is that okay with you?',
              'Permission is a conversation, not a completed examination.', courtesy='consent_exam'),
        _task('prepare.gloves','prepare','Prepare gloves and draping',
              'I put on gloves and drape the patient, keeping you covered except for the area being examined.',
              'State comfort and privacy actions; the simulation cannot verify actual contact or draping.', courtesies=['gloves','drape']),
        _task('prepare.comfort','prepare','Check comfort before touching',
              'Are you comfortable? Let me know if this hurts or if you need me to stop.',
              'Check before changing position and during uncomfortable maneuvers.', courtesy='comfort_check')])
    source_events = {e['seq']:e for e in lesson.get('ledger',[])}
    seen_exams = set()
    for row in lesson.get('timeline',[]):
        mid = row.get('maneuver_id')
        if not mid or mid in seen_exams or mid not in physexam.CATALOG_BY_ID:
            continue
        seen_exams.add(mid)
        man = physexam.CATALOG_BY_ID[mid]
        actions = [source_events[n] for n in row.get('event_ids',[]) if n in source_events and source_events[n]['kind']==evidence.EXAM_ACTION]
        components = list(dict.fromkeys(c for e in actions for c in e.get('meta',{}).get('components',[])))
        # A selected key special test is sufficient for this learning path;
        # optional tests remain available in the ordinary universal catalog.
        key_findings = [f for f in s.case.get('exam_findings',{}).get(mid,[]) if f.get('key_finding') and f.get('requires_components')]
        focused = man['method']=='special' and key_findings
        if focused:
            components = list(dict.fromkeys(c for f in key_findings for c in f['requires_components']))
        components = [c for c in components if c in man['components']]
        if mid == 'neuro_dix_hallpike' and 'cervical_suitability' not in components:
            components.insert(0,'cervical_suitability')
        tasks.append(dict(id='exam.'+mid, group='examine', title=man['label'], kind='exam', question='',
                          why=(lesson.get('plan',{}).get('exam','') if man['method']=='special' else
                               'Obtain the relevant observation with specific sites and technique. Document only findings the examination actually releases.'),
                          maneuver_id=mid, components=components, region=man['region'],
                          technique=man.get('notes',''), source='Authored variant walkthrough',
                          focused_subset=bool(focused)))
    # Some older written examples omit the course structural-screen row. The
    # current case already authors this examination; add its existing selection
    # as conditional practice without inventing an observation or delaying care.
    if 'osteo_screen' not in seen_exams and s.case.get('exam_findings',{}).get('osteo_screen'):
        man = physexam.CATALOG_BY_ID['osteo_screen']
        components = list(dict.fromkeys(c for f in s.case['exam_findings']['osteo_screen'] for c in f.get('requires_components',[]) if c in man['components']))
        tasks.append(dict(id='exam.osteo_screen',group='examine',title=man['label'],kind='exam',question='',
                          why='The course includes an osteopathic structural observation. Practice this authored screen only when appropriate and care permits; never delay urgent escalation or perform an unsafe examination for a checklist.',
                          maneuver_id='osteo_screen',components=components,region=man['region'],technique=man.get('notes',''),
                          source='Existing case examination definition and course structural-screen row',focused_subset=True))
    tasks.extend(closings)
    tasks.append(dict(id='checkpoint.objective',group='document',title='Check the evidence for Objective',kind='checkpoint',question='',
                      why='Vitals first, then general appearance, heart/lungs, the focused system, another system and osteopathic findings. An animation or selected body region supplies no finding.',checkpoint='objective'))
    tasks.append(dict(id='document.transition',group='document',title='Leave the encounter and organize your note',kind='document',question='',
                      why='When ready, use Finish encounter. Subjective is reported history; Objective is supplied results and observed findings; Assessment is your interpretation; Plan is what you propose next. Nothing here writes your note.'))
    return tasks, lesson


def _ros(s, released):
    """Count authored ROS mappings first; conservatively label older unmapped topics."""
    systems = s.case.get('ros_pertinent_systems',[])[:3]
    out = {name:set() for name in systems}
    labels = dict(lexicon.CORE_CONCEPTS); labels.update(s.case.get('concept_lexicon',{}))
    generic = {'general','constitutional','respiratory','pulmonary','lungs','cardiovascular','cardiac','heart',
               'gastrointestinal','gi','urinary','genitourinary','gu','neurologic','neuro','heent','head','eyes',
               'ears','nose','throat','skin','integumentary','neck','hematologic','endocrine','psychiatric','musculoskeletal','msk'}
    for fact in s.case.get('facts',[]):
        if fact['id'] not in released or fact.get('category') not in ('chief_complaint','onset','location','quality','severity','timing','chronology','associated','pertinent_negative'):
            continue
        for cid in fact.get('concepts',{}):
            explicit = fact.get('ros_system')
            if explicit in out:
                topic = re.sub(r'^(?:symptom_|assoc_|no_)','',cid).replace('_',' ')
                out[explicit].add(topic)
                continue
            aliases = labels.get(cid,[])
            surface = ' '.join(aliases) if isinstance(aliases,list) else ''
            surface = nlp.normalize(cid.replace('_',' ')+' '+surface)
            matches=[]
            canonical = nlp.normalize(cid.replace('_',' '))
            for system in systems:
                for term in lexicon.ROS_SYSTEMS.get(system,[]):
                    if term in generic:continue
                    suffix = r'\w*' if term in ('wheez','urinat','palpitation') else r's?'
                    expression = r'\b'+re.escape(nlp.normalize(term))+suffix+r'\b'
                    if re.search(expression,surface):
                        matches.append((bool(re.search(expression,canonical)),len(term),system,term))
            if matches:
                _,_,system,term=max(matches)
                out[system].add(term)
    return [{'system':system,'obtained':len(topics),'target':3,'topics':sorted(topics)} for system,topics in out.items()]


def coverage(s, verified, tasks):
    released = verified.released_facts()
    categories = {f.get('category') for f in s.case.get('facts',[]) if f['id'] in released}
    groups = [('Complaint / opening',('chief_complaint',)),('Onset and location',('onset','location')),
              ('Quality and severity',('quality','severity')),('Timing / progression',('timing',)),
              ('Better / worse',('alleviating','aggravating')),('Prior episodes and treatments',('past_occurrence','treatment')),
              ('PMH and PSH',('pmh','psh')),('Medicines and allergies',('medications','allergies')),
              ('Social and family history',('social','family'))]
    history = [{'label':label,'obtained':all(c in categories for c in cats)} for label,cats in groups]
    social = [f for f in s.case.get('facts',[]) if f.get('category')=='social' and any(token in f['id'] for token in ('tobacco','alcohol','drug'))]
    family = [f for f in s.case.get('facts',[]) if f.get('category')=='family']
    history[3]['obtained'] = bool(categories & {'timing','chronology'})
    history[-1]['obtained'] = bool(social) and all(f['id'] in released for f in social+family)
    ros = _ros(s,released)
    findings = verified.by_kind(evidence.EXAM_FINDING)
    mids = {e['meta'].get('maneuver_id') for e in findings}
    regions = {physexam.CATALOG_BY_ID[mid]['region'] for mid in mids if mid in physexam.CATALOG_BY_ID}
    system = s.case.get('area_of_concern',{}).get('system','').lower()
    main_regions = ({'Abdomen'} if any(x in system for x in ('gastro','abdomen','genitourinary')) else
                    {'Neurologic','Musculoskeletal','Neck'} if 'neuro' in system else
                    {'Heart','Lungs'} if 'pulmonary' in system else {'Heart','Musculoskeletal'})
    main_tasks = [t for t in tasks if t['kind']=='exam' and t['region'] in main_regions]
    performed = verified.performed_maneuvers()
    focused_done = bool(main_tasks) and all(t['maneuver_id'] in mids and
        set(t['components']) <= set(performed.get(t['maneuver_id'],{}).get('components',[])) for t in main_tasks)
    objective = [{'label':'Supplied doorway vitals','obtained':any(e['meta'].get('vitals') for e in verified.by_kind(evidence.STATION_INFO))},
                 {'label':'General appearance','obtained':'general_inspect' in mids},
                 {'label':'Heart and lungs','obtained':{'heart_auscultate','lungs_auscultate'}<=mids},
                 {'label':'Focused system findings','obtained':focused_done},
                 {'label':'Another system','obtained':bool(regions-main_regions-{'General','Osteopathic'})},
                 {'label':'Osteopathic observation','obtained':'Osteopathic' in regions}]
    return {'history':history,'ros':ros,'objective':objective,
            'history_ready':all(x['obtained'] for x in history) and len(ros)==3 and all(x['obtained']>=3 for x in ros),
            'objective_ready':all(x['obtained'] for x in objective),
            'note':'Coverage of obtained information, not a SOAP score. ROS topic matching is conservative; inspect the actual replies. Specificity, placement and unsupported claims are assessed after writing.'}


def state(s):
    if not allowed(s):
        raise PermissionError('The step-by-step case coach is available only in guided practice.')
    from . import learning
    tasks, lesson = plan(s)
    verified = audit._delivered_ledger(s.ledger,s.case)
    released = verified.released_facts()
    courtesies = s.ledger.courtesy_done()
    performed = verified.performed_maneuvers()
    cover = coverage(s,verified,tasks)
    changes = [e for e in learning.events(s.id) if e['kind']=='guide_navigation']
    deferred = set()
    for change in changes:
        if change['payload']['action']=='defer':deferred.add(change['payload']['step'])
        elif change['payload']['action']=='restore':deferred.discard(change['payload']['step'])
    for item in tasks:
        done = False
        sources = []
        if item.get('facts'):
            done = all(fid in released for fid in item['facts'])
            sources = sorted({released[fid]['seq'] for fid in item['facts'] if fid in released})
        elif item.get('courtesy') or item.get('courtesies'):
            needed = set(item.get('courtesies') or [item['courtesy']])
            done = needed <= courtesies
            sources = [e['seq'] for e in s.ledger.by_kind(evidence.COURTESY) if e['meta'].get('courtesy_id') in needed]
        elif item['kind']=='exam':
            rec = performed.get(item['maneuver_id'],{})
            findings = [e for e in verified.by_kind(evidence.EXAM_FINDING) if e['meta'].get('maneuver_id')==item['maneuver_id']]
            done = bool(findings) and set(item['components']) <= set(rec.get('components',[]))
            sources = [e['seq'] for e in findings]
        elif item.get('match'):
            # Flexible communication completion uses the existing engine's
            # recorded speech acts; it does not require copying the model line.
            if item['match'] in ('counsel','urgent'):
                acts = s.ledger.by_kind(evidence.COUNSELING)
                if item['match']=='urgent':
                    acts = [e for e in acts if re.search(r'urgent|emergency|immediate|right now|without delay', e['text'], re.I)]
                done = bool(acts)
                sources = [e['seq'] for e in acts]
            elif item['match']=='education':
                closures = [e['seq'] for e in s.ledger.by_kind(evidence.PATIENT) if e['meta'].get('kind')=='closure_response']
                acts = [e for e in s.ledger.by_kind(evidence.PATIENT) if closures and e['seq']>max(closures) and e['meta'].get('kind') in ('education_response','plan_ack')]
                done = bool(acts)
                sources = [e['seq'] for e in acts]
            else:
                acts = [e for e in s.ledger.by_kind(evidence.PATIENT) if e['meta'].get('kind')=='closure_response']
                done = bool(acts)
                sources = [e['seq'] for e in acts]
        elif item.get('checkpoint'):
            done = cover[item['checkpoint']+'_ready']
        elif item['kind']=='document':
            done = s.row['phase'] in ('organize','note')
        item.update(status='obtained' if done else 'deferred' if item['id'] in deferred else 'review' if item.get('checkpoint') else 'next', evidence_ids=sources)
    next_task = next((x for x in tasks if x['status']=='next'),tasks[-1])
    if s.row['phase'] in ('organize','note'):
        next_task = next(x for x in tasks if x['id']=='checkpoint.objective')
    selected = next_task['id']
    manual = changes[-1] if changes and changes[-1]['payload']['action']=='select' else None
    if manual and manual['payload'].get('after_seq')==len(s.ledger.events) and any(t['id']==manual['payload']['step'] for t in tasks):
        selected = manual['payload']['step']
    return {'available':True,'selected':selected,'recommended':next_task['id'],'tasks':tasks,
            'groups':[{'id':k,'label':v} for k,v in GROUPS if any(t['group']==k for t in tasks)],
            'coverage':cover,'completed':sum(t['status']=='obtained' for t in tasks),
            'deferred':sum(t['status']=='deferred' for t in tasks),'total':len(tasks),
            'variant_label':lesson.get('variant_label',''),'title':lesson.get('title',''),
            'notice':lesson.get('plan',{}).get('notice',''),
            'checkpoint_note':'Coverage checkpoints flag gaps for review and do not block the encounter. They are not graded completion checks.',
            'urgent':bool(lesson.get('plan',{}).get('urgent')),
            'source_note':'One defensible path adapted from this variant’s authored walkthrough. Alternative wording and sensible ordering are welcome; skipped steps are not evidence.',
            'limits':'The coach recognizes authored disclosures and completed simulator actions; it cannot certify hands-on technique or guarantee the final note score.'}


def navigate(s,body):
    if not allowed(s):raise PermissionError('The case coach is available only in guided practice.')
    if not isinstance(body,dict) or set(body)-{'step','action'} or body.get('action') not in ('select','defer','restore'):
        raise ValueError('Invalid guided navigation action.')
    tasks,_ = plan(s)
    if body.get('step') not in [t['id'] for t in tasks]:raise ValueError('Unknown guided step.')
    from . import learning
    learning.record(s.id,'guide_navigation',dict(body,after_seq=len(s.ledger.events)))
    return state(s)
