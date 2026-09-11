"""Learning assistance is a sidecar, never clinical evidence or SOAP completion."""
import json
import uuid
from . import db, evidence, cases, audit

MODES = ('guided', 'coached', 'independent', 'rehearsal')
STEPS = [
    {'id':'orient','label':'Understand','purpose':'Understand the complaint in the patient’s own words.','cue':'Start with the story.','question':'What brings you in today?','why':'An opening invitation gives the patient room to identify their main concern before you narrow the interview.'},
    {'id':'pattern','label':'Build a pattern','purpose':'Establish timing, location and change.','cue':'Time → place → character → change.','question':'When did this start, and how has it changed?','why':'Chronology separates a sudden event from a recurring or progressive problem. Ask one question, listen, then follow up.'},
    {'id':'discriminate','label':'Distinguish','purpose':'Ask a question that could change urgency or your next action.','cue':'What would make this more urgent?','question':'What other symptoms came with it?','why':'Compare plausible explanations using discriminating positives and negatives. A dangerous possibility deserves consideration even when less likely.'},
    {'id':'examine','label':'Examine','purpose':'Choose a region, method and specific components that test your working ideas.','cue':'What finding would change my next step?','question':'May I explain the examination I would like to do?','why':'Select the examination because of the clinical question it can answer. Region selection alone produces no findings.'},
    {'id':'interpret','label':'Interpret','purpose':'Connect the findings you actually obtained to plausible explanations.','cue':'What fits? What does not? What must I not miss?','question':'Which finding supports or weakens each possibility?','why':'A differential is an interpretation, not a confirmed diagnosis. Keep uncertainty visible and prioritize instability before routine tasks.'},
    {'id':'close','label':'Explain','purpose':'Explain your concern, next steps and safety plan, then check understanding.','cue':'Concern → plan → safety → check-back.','question':'What questions do you have about the next steps?','why':'A patient needs to understand what happens next and when to seek help. Invite concerns and use a respectful teach-back.'},
    {'id':'document','label':'Document','purpose':'Separate reported history, observations, interpretation and proposed actions.','cue':'Source → observation → interpretation → future action.','question':'Which encounter event supports this statement?','why':'Hidden case truth is not evidence that you obtained a fact. An unperformed examination cannot be documented as normal.'},
]

def record(sid, kind, payload):
    with db.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        previous = conn.execute('SELECT MAX(created_at) FROM learning_events WHERE session_id=?',(sid,)).fetchone()[0]
        # Millisecond ties must preserve navigation order rather than sorting
        # random UUIDs (for example, select → defer → restore).
        created_at = max(db.now_ms(), (previous + 1) if previous is not None else 0)
        conn.execute('INSERT INTO learning_events VALUES(?,?,?,?,?)',
                     (uuid.uuid4().hex, sid, created_at, kind, json.dumps(payload)))

def events(sid):
    with db.connect() as conn:
        return [dict(r, payload=json.loads(r['payload'])) for r in conn.execute(
            'SELECT * FROM learning_events WHERE session_id=? ORDER BY created_at,id', (sid,))]

def allowed(s):
    return s.settings.get('learning_mode') in ('guided','coached') and s.row['phase'] in ('encounter','organize','note')

def steps(s):
    authored={r['id']:r for r in s.case.get('teaching',{}).get('reasoning_steps',[])}
    return [dict(x, **{k:v for k,v in authored.get(x['id'],{}).items() if k in ('purpose','cue','question','why')}) for x in STEPS]

def summary(s):
    evs=events(s.id)
    hints=[e for e in evs if e['kind']=='hint']
    repairs=[e for e in evs if e['kind']=='repair']
    return {'mode':s.settings.get('learning_mode','legacy'), 'hints_used':len(hints),
            'highest_hint_level':max([e['payload']['level'] for e in hints] or [0]),
            'assisted':bool(hints) or bool(s.row['assisted']),
            'repair_attempts':len(repairs), 'repair_successes':sum(bool(e['payload'].get('correct')) for e in repairs),
            'comparison_note':'Assisted practice and retries are tracked separately from independent attempts.'}

def inferred_step(s):
    if s.row['phase'] in ('organize','note','submitted'):return 'document'
    evs=s.ledger.events
    if any(e['kind']==evidence.COUNSELING for e in evs):return 'close'
    if s.ledger.performed_maneuvers():return 'interpret'
    if s.row.get('pending_exam_json'):return 'examine'
    released=audit._delivered_ledger(s.ledger,s.case).released_facts()
    categories={f.get('category') for f in s.case['facts'] if f['id'] in released}
    if len(released)>=8 and len(categories & {'onset','location','chronology','quality','severity','timing'})>=2:return 'examine'
    if len(categories & {'onset','location','chronology','quality','severity','timing'})>=2:return 'discriminate'
    if released or s.pstate.get('opened'):return 'pattern'
    return 'orient'

# Changed scenarios, deliberately separate from the hidden patient. No clinical
# answer is inferred from the current case, and passing is not clinical credit.
TRANSFERS={
 'orient':('A new patient says, “There are two things worrying me.” What helps you establish an agenda?', ['Choose the first concern without asking.','Ask what both concerns are and agree which needs attention first.','List your diagnoses immediately.'],1,'Invite the concerns, then agree priorities; urgent symptoms still take precedence.'),
 'pattern':('In another encounter the patient has had dizziness for a week, with brief spells. Which question separates illness onset from spell duration?', ['How long does each spell last?','So each spell lasts a week?','Is your examination normal?'],0,'The time since the first symptom and the length of one episode answer different questions.'),
 'discriminate':('In a different case, a patient with back pain reports new difficulty emptying the bladder. What should you do next?', ['Ignore it because back pain is common.','Clarify the change, assess associated neurologic symptoms and prioritize urgent evaluation.','Assume a normal urinary examination.'],1,'A new bladder symptom changes urgency. Clarify it and assess related neurologic concerns rather than completing a routine checklist first.'),
 'examine':('You heard asymmetric breathlessness concerns in a new case. What makes an examination comparison useful?', ['Listen at one site and document both lungs.','Choose specific bilateral sites and compare corresponding regions.','Click the chest region to release all findings.'],1,'A selected region is only orientation. Specific comparison actions produce evidence.'),
 'interpret':('A different patient denies a symptom you expected. What does that negative do?', ['It proves the diagnosis is impossible.','It changes the weight of possibilities alongside the other findings.','It lets you document unrelated negatives.'],1,'A finding changes your reasoning in context; it does not automatically settle the diagnosis.'),
 'close':('You explain a next step to another patient, who looks uncertain. What checks communication?', ['Ask them to explain the plan in their own words, without making it a test.','Assume silence means agreement.','Repeat the same jargon more loudly.'],0,'A respectful teach-back helps you discover and repair misunderstandings.'),
 'document':('In another case you planned a lung examination but did not perform it. What can your note say?', ['Lungs clear because the case is usually normal.','Lung examination planned; findings not obtained.','No respiratory abnormality.'],1,'A proposed action belongs in Plan. Only released examination findings belong in Objective.'),
}

def transfer_item(step):
    stem,choices,answer,why=TRANSFERS.get(step,TRANSFERS['pattern'])
    return {'id':step,'stem':stem,'choices':choices}

def answer_transfer(s,body):
    if not allowed(s):raise PermissionError('Coaching is unavailable in this mode.')
    step=body.get('id')
    if step not in TRANSFERS:raise ValueError('Unknown transfer exercise')
    prior=[e for e in events(s.id) if e['kind']=='application' and e['payload']['step']==step]
    if not prior:raise ValueError('Apply the cue in your encounter before the transfer exercise.')
    stem,choices,answer,why=TRANSFERS[step]
    correct=body.get('choice')==answer
    record(s.id,'transfer',{'step':step,'correct':correct})
    s.set(assisted=1);s.save()
    return {'correct':correct,'explanation':why,'next':'Now lead the next encounter action without a cue. This exercise is practice, not independent clinical credit.'}

def _cue_applied(s, hint_event):
    later=[e for e in s.ledger.events if e['seq']>hint_event['payload'].get('after_seq',len(s.ledger.events))]
    step=hint_event['payload']['step']
    if step in ('examine','interpret'):return any(e['kind']==evidence.EXAM_FINDING for e in later)
    if step=='close':return any(e['kind']==evidence.COUNSELING for e in later)
    if step=='document':return False
    categories={f.get('category') for f in s.case['facts'] if any(f['id'] in e['meta'].get('facts_released',[]) for e in later)}
    if step=='orient':return any(e['kind']==evidence.PATIENT and not e['meta'].get('no_information') for e in later)
    if step=='pattern':return bool(categories & {'onset','location','chronology','quality','severity','timing'})
    return any(e['kind']==evidence.PATIENT and e['meta'].get('facts_released') for e in later)

def state(s):
    mode=s.settings.get('learning_mode','legacy')
    out={'mode':mode,'available':allowed(s),'summary':summary(s)}
    if not allowed(s):return out
    evs=events(s.id)
    selected=inferred_step(s)
    manual=next((e for e in reversed(evs) if e['kind']=='stage'),None)
    # A manual choice remains useful until the next clinical action. A hint is
    # never itself a phase selection; otherwise one opening hint locks the UI.
    if manual and manual['payload'].get('after_seq')==len(s.ledger.events):selected=manual['payload']['step']
    latest=next((e for e in reversed(evs) if e['kind']=='hint'),None)
    application=None
    if latest and _cue_applied(s,latest):
        found=next((e for e in evs if e['kind']=='application' and e['payload'].get('hint_id')==latest['id']),None)
        if not found:
            record(s.id,'application',{'hint_id':latest['id'],'step':latest['payload']['step'],'after_seq':len(s.ledger.events)})
        completed=any(e['kind']=='transfer' and e['created_at']>=latest['created_at'] and e['payload']['step']==latest['payload']['step'] and e['payload']['correct'] for e in evs)
        application={'text':'You used a cue and then obtained new encounter evidence. Try the same principle in a changed situation.','transfer':None if completed else transfer_item(latest['payload']['step'])}
        if completed:application['text']='Transfer exercise completed. Try your next action independently; cues remain available if needed.'
    out.update(steps=steps(s), selected=selected, inferred=True, application=application,
               timing=('Untimed encounter and note; examinations shortened for demonstration.' if mode=='guided' else 'Untimed encounter and note; examination actions keep their normal duration.') if s.preset.get('untimed') or mode=='guided' else ' → '.join(
                   '%d-minute %s' % (s.preset[key]//60,label) for key,label in
                   [('encounter_s','encounter'),('organize_s','organization'),('note_s','note')]
                   if s.preset[key]) + '.',
               reasoning_map=s.case.get('teaching',{}).get('reasoning_map',[]))
    out['hint_history'] = hint_history(s)
    from . import guide
    if mode == 'guided':
        out['case_guide'] = guide.state(s)
    elif mode == 'coached':
        # The step-by-step PLAN stays guided-only, by policy. But a coach whose
        # entire output is a focus dropdown and one line of general advice is
        # the stranding students report, so coached mode gets the single next
        # action -- one move, with its question and its reason -- and not the
        # rest of the plan.
        out['next_action'] = guide.next_action(s)
    return out

def hint(s, step_id=None, level=None):
    if not allowed(s):
        raise PermissionError('Coaching is unavailable in independent practice and exam rehearsal.')
    step_id = step_id or state(s).get('selected','orient')
    choices = {x['id']:x for x in steps(s)}
    if step_id not in choices:
        raise ValueError('Unknown cue step.')
    step = choices[step_id]
    prior = [e for e in events(s.id) if e['kind']=='hint' and e['payload']['step']==step_id]
    highest = max([e['payload']['level'] for e in prior] or [0])
    if level is not None and (type(level) is not int or not 1 <= level <= 3):
        raise ValueError('Choose cue 1, 2, or 3.')
    requested = level if level is not None else min(3,highest+1)
    if requested > highest+1:
        raise ValueError('Unlock the preceding cue first.')
    replay = requested <= highest
    if not replay and prior and db.now_ms()-prior[-1]['created_at']<5000:
        return {'wait':True,'step':step_id,'unlocked':highest,
                'wait_ms':max(0,5000-(db.now_ms()-prior[-1]['created_at'])),
                'text':'Take a breath and choose one next action. A stronger cue is available after five seconds.'}
    result = cue_payload(s,step,requested)
    if not replay:
        record(s.id,'hint',{'step':step_id,'level':requested,'after_seq':len(s.ledger.events)})
        s.set(assisted=1);s.save()
    result.update(replay=replay,unlocked=max(highest,requested),
                  wait_ms=0 if max(highest,requested)>=3 else
                  max(0,5000-(db.now_ms()-prior[-1]['created_at'])) if replay and prior else 5000)
    return result


def cue_payload(s,step,level):
    facts=[{'seq':e['seq'],'text':e['text'],'kind':e['kind']} for e in s.ledger.events
           if e['kind'] in (evidence.PATIENT,evidence.EXAM_FINDING,evidence.STATION_INFO,evidence.EXAM_REFUSED)][-5:]
    result={'step':step['id'],'level':level,'phase':s.row['phase'],'purpose':step['purpose'],
            'routine':['Pause: one slow breath.','Place: name this phase.','Purpose: what am I trying to learn?','Proceed: choose just one relevant action.'],
            'cue':step['cue'],'obtained':facts,'text':step['cue']}
    if level>=2:result.update(question=step['question'],text=step['question'])
    if level>=3:result.update(why=step['why'],text=step['why'])
    return result


def hint_history(s):
    if not allowed(s):return {}
    evs=events(s.id)
    out={}
    for step in steps(s):
        prior=[e for e in evs if e['kind']=='hint' and e['payload']['step']==step['id']]
        highest=max([e['payload']['level'] for e in prior] or [0])
        out[step['id']]={'unlocked':highest,
            'wait_ms':max(0,5000-(db.now_ms()-prior[-1]['created_at'])) if prior and highest<3 else 0,
            'cues':[cue_payload(s,step,level) for level in range(1,highest+1)]}
    return out

def repair(s):
    """Known evidence is the entire exercise; hidden findings never enter its stem."""
    if s.row['phase']!='submitted':
        raise PermissionError('Finish the encounter before its repair exercise.')
    performed=s.ledger.performed_maneuvers()
    obtained=[e for e in s.ledger.events if e['kind'] in (evidence.PATIENT,evidence.EXAM_FINDING)]
    if not performed:
        return {'id':'unsupported_exam','title':'Repair: evidence before documentation','stem':'You did not complete a physical examination in this attempt. Which Objective statement is defensible?',
                'choices':['Physical examination normal.','No physical examination findings were obtained.','Heart and lungs normal because the hidden case says so.'],
                'answer':1,'explanation':'An examination finding requires an actually completed action. State the limitation accurately; plan the examination separately.', 'skill':'evidence-based-soap'}
    stored=json.loads(s.row.get('results_json') or '{}')
    fb=stored.get('feedback',{})
    unsupported=fb.get('unsupported') or []
    if unsupported:
        severity={'contradicts':0,'unsupported':1,'overbroad':2,'counseling_unsupported':3,'misplaced':4}
        target=sorted(unsupported,key=lambda x:severity.get(x.get('verdict'),5))[0]
        return {'id':'repair_actual_claim','title':'Repair: support the statement you wrote',
                'stem':'Your submitted note says: “'+target.get('text','')+'” The audit found: '+target.get('explanation','Evidence was insufficient.')+' What is the defensible repair?',
                'choices':['Keep the statement because it fits the likely diagnosis.','Remove or qualify the unsupported claim; obtain the needed information in a retry before documenting it.','Copy the ideal full-case answer into this attempt.'],
                'answer':1,'explanation':'Preserve the original attempt. A correction must use its own evidence. A new question or examination in a retry creates new evidence for that separate attempt.','skill':'evidence-based-soap'}
    if not fb.get('unsupported'):
        missing=fb.get('missed_questions') or []
        # A question not explicitly asked may overlap information volunteered
        # in the opening. Choose a repair outside concepts already supported
        # in the submitted note; do not teach redundant questioning or erase
        # valid evidence. The separate course checklist remains unchanged.
        documented=set((stored.get('audit') or {}).get('documented_concepts',[]))
        def unresolved(item):
            facts=[f for f in s.case.get('facts',[]) if f.get('checklist')==item.get('id')]
            concepts={cid for f in facts for cid in f.get('concepts',{})}
            return not concepts or not concepts<=documented
        missing=[item for item in missing if unresolved(item)]
        if missing:
            target=missing[0]
            label=target.get('item') or target.get('text') or target.get('question') or target.get('label') or 'a pertinent history item'
            if isinstance(label,dict):label=str(label.get('text','a pertinent history item'))
            return {'id':'missed_history','title':'Repair: recover the missing question',
                    'stem':'Your debrief identified an omission: '+str(label)+'. What makes the best next attempt?',
                    'choices':['Add the expected answer to the SOAP note from memory.', 'Ask the relevant question, listen to the answer, then document what was actually said.', 'Document a negative because it was not volunteered.'],
                    'answer':1,'explanation':'A missed question is repaired in the encounter, not by guessing in the note. Retry that moment, ask the question in your own words, and use its answer to guide your next action.','skill':'history-sequencing'}
    if obtained:
        ev=obtained[-1]
        patient=ev['kind']==evidence.PATIENT
        return {'id':'source_section','title':'Repair: put the evidence in its place',
                'stem':'Your encounter event #%s: “%s” Where does this information belong?'%(ev['seq'],ev['text']),
                'choices':['Subjective: patient-reported history.','Objective: examination observation.','Assessment: confirmed diagnosis.'],
                'answer':0 if patient else 1,'explanation':'Identify how you learned it before choosing its SOAP section. Interpretation belongs in Assessment, and planned actions in Plan.','skill':'evidence-based-soap','source_seq':ev['seq']}
    return {'id':'first_minute','title':'Repair: recover the first minute','stem':'You enter the station and go blank. What is the most useful next step?',
            'choices':['List diagnoses aloud before hearing the complaint.','Pause, introduce yourself, establish the patient’s concern, then clarify the story.','Perform every examination immediately.'],
            'answer':1,'explanation':'Reorient to the purpose of this phase and choose one action. Learn the story before narrowing it.','skill':'history-sequencing'}

def public_repair(s):
    if s.row['phase']!='submitted':
        raise PermissionError('Repair feedback is available after submission.')
    if s.versions()['is_regrade']:
        return {'id':'historical_feedback','requires_current_review':True,
                'title':'Review this older attempt with the current grader',
                'stem':'The original note and score are preserved. This build corrects earlier grading interpretations, so its old feedback is not used for a new repair lesson. Open Deliberate practice and grade a separate revision to compare current feedback.',
                'choices':[]}
    return {k:v for k,v in repair(s).items() if k not in ('answer','explanation')}

def answer_repair(s, body):
    if s.versions()['is_regrade']:
        raise ValueError('Review this historical note with the current grader in a separate revision first.')
    item=repair(s)
    if body.get('id')!=item['id']:
        raise ValueError('This exercise changed. Reload its current question.')
    correct=body.get('choice')==item['answer']
    record(s.id,'repair',{'id':item['id'],'correct':correct,'skill':item['skill']})
    return {'correct':correct,'explanation':item['explanation'],'retry_prompt':'Apply this rule in a different presentation. Choose another case below, or retry an earlier encounter moment.',
            'recommended_cases':[c['id'] for c in cases.index() if c['id']!=s.case['id'] and item['skill'] in c['skills']][:4]}

def progress():
    with db.connect() as conn:
        rows=[dict(r) for r in conn.execute("SELECT id,case_id,assisted,phase,settings_json,results_json,parent_session_id FROM sessions")]
    weak={};mode_counts={};completed=[]; independent_success={}; conditions={"assisted":0,"independent":0,"branches":0}
    for row in rows:
        mode=json.loads(row['settings_json'] or '{}').get('learning_mode','legacy')
        mode_counts[mode]=mode_counts.get(mode,0)+int(row['phase']=='submitted')
        if row['phase']!='submitted':continue
        completed.append(row['case_id'])
        results=json.loads(row['results_json'] or '{}')
        conditions['branches' if row['parent_session_id'] else 'assisted' if row['assisted'] else 'independent']+=1
        if not row['assisted'] and not row['parent_session_id'] and results.get('rubric',{}).get('total_earned',0)>=80:
            independent_success[mode]=independent_success.get(mode,0)+1
        fb=results.get('feedback',{})
        for field,skill in [('missed_questions','history-sequencing'),('missed_exams','focused-examination'),('unsupported','evidence-based-soap')]:
            if fb.get(field):weak[skill]=weak.get(skill,0)+1
    return {'attempted_cases':sorted(set(r['case_id'] for r in rows)), 'completed_cases':sorted(set(completed)),
            'completed_by_mode':mode_counts, 'weaknesses':[{'skill':k,'attempts':v} for k,v in sorted(weak.items(),key=lambda kv:-kv[1])],
            'conditions':conditions,
            'next_mode':'rehearsal' if independent_success.get('independent',0)>=2 else 'independent' if independent_success.get('coached',0)>=2 else 'coached',
            'fading_note':'Try less support after two unassisted attempts at 80 or above. This is a practice suggestion, not a course readiness prediction.',
            'presentation_count':len(cases.all_cases()),'variant_count':sum(len(c.get('variants',[])) for c in cases.all_cases().values())}
