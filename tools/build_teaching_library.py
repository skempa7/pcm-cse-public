#!/usr/bin/env python3
"""Rebuild written examples through the actual deterministic encounter engine.
Uses only an isolated temporary DB. Never copies its attempts into learner history.
"""
import sys,os,json,re,copy,tempfile,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pcmcse import cases,config,db,engine,evidence,physexam,patient,audit,version,note as note_module
ROOT=Path(__file__).resolve().parents[1]
PLANS=json.loads((ROOT/'pcmcse/teaching/plans.json').read_text())
CATEGORIES=['chief_complaint','current_status','onset','chronology','location','radiation','quality','severity','timing','setting','alleviating','aggravating','treatment','past_occurrence','associated','pertinent_negative','pmh','psh','medications','allergies','social','family','obgyn','fife','concern']
GROUPS={'chief_complaint':'Listen to the opening','associated':'Discriminate the possibilities','pertinent_negative':'Discriminate the possibilities','pmh':'Relevant background','psh':'Relevant background','medications':'Medicines and reactions','allergies':'Medicines and reactions','social':'Life and context','family':'Life and context','obgyn':'Life and context','fife':'The patient’s perspective','concern':'The patient’s perspective'}
COMPACT=json.loads((ROOT/'pcmcse/teaching/compact-notes.json').read_text())
CLOSINGS=json.loads((ROOT/'pcmcse/teaching/closing-dialogue.json').read_text())
HPI=json.loads((ROOT/'pcmcse/teaching/hpi-prose.json').read_text())
BARRIERS=json.loads((ROOT/'pcmcse/teaching/care-barrier-dialogue.json').read_text())
CONCERNS=json.loads((ROOT/'pcmcse/teaching/concern-responses.json').read_text())
OMIT_EXAMS={'cardio-chest-pressure':{'osteo_screen','skin_inspect','heent_eyes','carotid_auscultate'},'renal-flank-pain':{'heent_throat','lungs_percuss','msk_palpate','extremities'},'neuro-thunderclap-headache':{'gait','osteo_screen','neuro_coordination'}}
COURSE=[{'label':'PCM syllabus: 14-minute encounter / 9-minute SOAP; invasive SP examinations refused','locator':'PCM syllabus.pdf pp. 4–5'},{'label':'SOAP rubric: S 28 / O 30 / A 15 / P 25 / style 2','locator':'2026 FALL M2 ILG - STUDENT MANUAL update.docx, SOAP evaluation table'},{'label':'FIFE and patient perspective; purposeful transitions','locator':'PCM syllabus.pdf p. 13; Interpersonal Skills lecture'}]

def build(c,variantmeta):
    plan=PLANS.get(c['id']) or c.get('teaching',{}).get('lesson_plan')
    if not plan:raise ValueError('Missing authored lesson plan for '+c['id'])
    settings=config.load_settings();settings.update(learning_mode='guided',simulation_runtime='written-example')
    settings['scoring']=dict(settings['scoring'],realtime_exam_durations=True,exam_time_scale=1)
    sid=db.create_session(c['id'],config.DEFAULT_PRESET,'type',True,settings,case=c);s=engine.load(sid);s.start_encounter()
    timeline=[];spoken=0
    def say(q,section,why=''):
        nonlocal spoken
        before=len(s.ledger.events);s.student_turn(q)
        ev=s.ledger.events[before:];replies=[e for e in ev if e['kind']==evidence.PATIENT]
        timeline.append({'kind':'dialogue','section':section,'student':q,'patient':' '.join(e['text'] for e in replies),'why':why,'event_ids':[e['seq'] for e in ev],'fact_ids':list(dict.fromkeys(fid for e in replies for fid in e['meta'].get('facts_released',[])))})
        spoken+=len(q.split())+sum(len(e['text'].split()) for e in replies)
    say('Hello, I am a medical student. I will listen to your concerns, examine you with your permission, and discuss the next steps.','Connect')
    say('What brings you in today?','Listen to the opening',plan['notice'])
    if plan.get('urgent'):
        say('I will arrange urgent help from my supervising clinician now. We will not delay emergency care to finish routine questions.','Recognize urgency','Stated escalation in a simulation. Continue the remaining example only while care permits; do not delay transfer or stabilization for nonurgent checklist items.')
    facts=sorted(c['facts'],key=lambda f:(-1 if 'current_status' in f.get('question_dimensions',[]) else CATEGORIES.index(f['category']) if f['category'] in CATEGORIES else 20))
    missing=[]
    for f in facts:
        if c['id']=='neuro-positional-vertigo' and f['id']=='hpi_radiation':continue  # Spinning is not a pain-radiation complaint.
        if f['id'] in s.ledger.released_facts():continue
        qs=f.get('example_questions',[])
        if not qs:missing.append(f['id']);continue
        for q in qs:
            say(q,GROUPS.get(f['category'],'Build the symptom pattern'),plan['pivot'] if f['category']=='onset' else {'chronology':'Change over time can change urgency even when the symptom is familiar.','timing':'Separate time since onset from duration of one episode and from continuity.','quality':'Use the patient’s words before translating them into a clinical description.','severity':'Intensity and functional effect are distinct; record only the dimension answered.','radiation':'Spread of discomfort can connect an apparent local complaint with another system.','alleviating':'Relief changes probability, but is not proof that a serious cause is excluded.','aggravating':'Compare triggers with the chronology; one trigger does not establish a diagnosis.','medications':'Name, dose and frequency matter; do not fill in missing details.','allergies':'Distinguish the substance and reaction from a blanket allergy label.','family':'Record which relative and the condition; do not infer a family history from patient worry.','obgyn':'A reported possibility or menstrual date is not a pregnancy-test result.','fife':'FIFE helps connect the clinical plan with this patient’s concern and circumstances.','associated':'Use this answer to weigh the possibilities described in the reasoning section.','pertinent_negative':'A targeted negative changes probability; it does not justify unrelated normal statements.'}.get(f['category'],''))
            if f['id'] in s.ledger.released_facts():break
        if f['id'] not in s.ledger.released_facts():missing.append(f['id'])
    say('Thank you for explaining that. I can understand why this is concerning.','Acknowledge')
    say('May I have your permission to examine you?','Explain and ask permission')
    timeline.append({'kind':'action','section':'Prepare the examination','action':'Clean hands, provide privacy and appropriate draping, explain the selected examination and help the patient into a comfortable position.','why':'These are stated actions in this written example. A visual avatar does not verify hand hygiene, consent or hands-on technique.','event_ids':[]})
    examsecs=0
    mids=[m for m in c['exam_findings'] if m!='vitals_review' and m not in OMIT_EXAMS.get(c['id'],set())]
    order={'general_inspect':0,'heart_auscultate':1,'lungs_auscultate':2,'abd_inspect':3,'abd_auscultate':4,'abd_percuss':5,'abd_palpate':6,'abd_special':7}
    mids.sort(key=lambda m:order.get(m,8))
    for mid in mids:
        man=physexam.CATALOG_BY_ID.get(mid)
        if not man:continue
        required=list(dict.fromkeys(x for f in c['exam_findings'][mid] for x in f.get('requires_components',[])))
        components=required or man['components']
        # Safety component is required even when it does not itself release a finding.
        if mid=='neuro_dix_hallpike' and 'cervical_suitability' not in components:components=['cervical_suitability']+components
        desired='supine' if mid.startswith('abd_') else 'seated' if mid in ('osteo_screen','lungs_percuss','msk_palpate') else s.pstate.get('posture','seated')
        if desired!=s.pstate.get('posture','seated'):
            before=len(s.ledger.events);s.position_patient(desired);ev=s.ledger.events[before:]
            timeline.append({'kind':'action','section':'Position with permission','action':'Offer help into the '+desired+' position.','finding':' '.join(e['text'] for e in ev if e['kind']==evidence.PATIENT),'why':'Respect the patient’s response; a position change is not a clinical finding by itself.','event_ids':[e['seq'] for e in ev]})
        before=len(s.ledger.events);result=s.perform_maneuver(mid,components)
        ev=s.ledger.events[before:];findings=[e for e in ev if e['kind']==evidence.EXAM_FINDING]
        examsecs+=result.get('duration_s',0)
        timeline.append({'kind':'action','section':'Focused examination','action':man['label']+(' — '+', '.join(components) if components else ''),'finding':' '.join(e['text'] for e in findings),'why':plan['exam'] if mid in ('general_inspect','abd_special','neuro_dix_hallpike') else man.get('notes','') or 'This specific action releases only the finding shown here. Interpret it with the history; it does not confirm a diagnosis by itself.','event_ids':[e['seq'] for e in ev],'maneuver_id':mid,'duration_s':result.get('duration_s',0)})
    # Use the case's paired plans as the authored discussion; they describe future care.
    selected_note=copy.deepcopy(COMPACT.get(c['id'],c['model_note']))
    selected_note.setdefault('A',copy.deepcopy(c['model_note']['A']))
    if c['id'] in HPI:
        values={f['id']:f['value'] for f in c['facts']}
        def interval(fid):
            match=re.search(r'\b(\d+(?:\.\d+)?\s+(?:seconds?|minutes?|hours?|days?|weeks?|months?)\s+ago)\b',values.get(fid,''),re.I)
            if not match:raise ValueError('No authored onset interval for '+c['id']+'/'+fid)
            return match.group(1)
        parts={'age':c['patient']['age']}
        for placeholder,fid in [('onset','hpi_onset'),('current_onset','hpi_current_episode_onset'),('urinary_onset','hpi_urinary_onset')]:
            if '{'+placeholder+'}' in HPI[c['id']]:parts[placeholder]=interval(fid)
        selected_note['S']=re.sub(r'HPI:.*?(?=\n\n)',lambda m:'HPI: '+HPI[c['id']].format(**parts),selected_note['S'],count=1,flags=re.S)
    barrier=next((f for f in c['facts'] if f['id']=='care_barrier'),None)
    if barrier and c['id'] in COMPACT:
        selected_note['S']+='\nCare needs: '+barrier['value']
        selected_note['P'][0]+=' Use one step at a time with teach-back.' if 'clarification' in c['variant_id'] else ' Confirm transport and a practical contact for deterioration.'
    closings=CLOSINGS.get(c['id']) or c.get('teaching',{}).get('closing_dialogue')
    if not closings:raise ValueError('Missing authored closing dialogue for '+c['id'])
    for i,p in enumerate(closings[:1]):
        say(re.sub(r'^\d+[.)]\s*','',p),'Explain next steps','Proposed care, not a record of tests or treatment already completed.' if i==0 else '')
    say('What questions do you have about the next steps?','Close and check understanding')
    response=(BARRIERS.get(c['id']) or ('I will explain one step at a time and ask you to tell me what is clear and what needs another explanation.' if 'clarification' in c['variant_id'] else 'I recommend telling the care team about this practical barrier so we can arrange a safe transport and contact plan with you.')) if barrier else (CONCERNS.get(c['id']) or c.get('teaching',{}).get('concern_response'))
    if not response:raise ValueError('Missing authored concern response for '+c['id'])
    say(response,'Address the patient’s question','Answer the concern that was just expressed. Give a defensible recommendation and explain uncertainty; do not promise a diagnosis or recovery before the evidence supports it.')
    # O is assembled only from actual released findings, never copied from a hidden full-case O.
    vitals=c['station']['vitals'];note=selected_note
    findings=s.ledger.by_kind(evidence.EXAM_FINDING)
    note['O']='Vitals: '+', '.join(k+' '+v for k,v in vitals.items())+'\n\n'+'\n'.join(c.get('print_exam_systems',{}).get(e['meta']['maneuver_id'],physexam.CATALOG_BY_ID[e['meta']['maneuver_id']]['region'])+': '+e['text'] for e in findings)
    for r in c['station'].get('supplied_results',[]):note['O']+='\nSupplied '+r['label']+': '+r['value']
    note['S']=note['S'].replace('Patient reports: ','').replace('Patient perspective:','Perspective:').replace('Cesarean delivery5','Cesarean delivery 5')
    links=[]
    checked=audit.audit_note(note_module.parse(note),s.ledger,c)
    for claim in checked['claims']:
        if claim['section'] not in ('S','O'):continue
        ids=[e['seq'] for e in claim.get('evidence',[]) if e.get('seq')]
        if not ids:
            words=set(re.findall(r'[a-z]{3,}',claim['text'].lower()))-{'patient','reports','with','the','and','has','she','her','for','from','that','this','are','was','not'}
            ids=[e['seq'] for e in s.ledger.by_kind(evidence.PATIENT,evidence.STATION_INFO,evidence.EXAM_FINDING) if len(words & set(re.findall(r'[a-z]{3,}',e['text'].lower())))>=min(2,len(words)) and words]
        links.append({'section':claim['section'],'statement':claim['text'],'event_ids':list(dict.fromkeys(ids)),'classification':'reported / supplied history' if claim['section']=='S' else 'supplied / examined finding','trace_method':'grader-linked delivered evidence' if claim.get('evidence') else 'related delivered quotations; not a semantic verification','audit_verdict':claim['verdict']})
    secs=round(spoken/150*60+examsecs+55);words=len((' '.join([note['S'],note['O']]+note['A']+note['P'])).split())
    differences=[]
    if c['variant_id']!='base':
        base=cases.resolve(c['id']);basefacts={f['id']:f for f in base['facts']}
        for f in c['facts']:
            if f.get('value')!=basefacts.get(f['id'],{}).get('value'):differences.append({'topic':f['id'],'base':basefacts.get(f['id'],{}).get('value','Not authored'),'current':f.get('value','')})
    return {'case_id':c['id'],'variant_id':c['variant_id'],'variant_label':variantmeta.get('label','Core presentation'),'title':c['title'],'patient':{k:c['patient'][k] for k in ('name','age','sex')},'system':c['system'],'doorway':c['station'],'plan':plan,'goals':c.get('teaching',{}).get('goals',[]),'variant_guidance':variantmeta.get('teaching_difference','Use this core presentation to learn the sequence before transferring to a variation.'),'differences':differences,'timeline':timeline,'note':note,'note_links':links,'ledger':s.ledger.events,'note_words':words,'estimated_encounter_s':secs,'estimate_method':'150 spoken words/minute plus the full simulation examination durations and 55 seconds for introductions and transitions; explanatory commentary excluded. This is a planning estimate, not a measured student performance.','missing_example_facts':missing,'documentation_audit':{'unsupported':[x['text'] for x in checked['claims'] if x['verdict'] in ('unsupported','contradicts','contradicted','contradictory')],'unresolved_count':sum(x['verdict']=='not_evaluated' for x in checked['claims'])},'reasoning':c.get('teaching',{}).get('reasoning_map',[]),'differentials':c.get('differentials',[]),'omissions':c.get('teaching',{}).get('common_omissions',[]),'recall':[{'prompt':'Before naming a diagnosis, what is the key distinction in this presentation?','answer':plan['pivot']},{'prompt':'Which specific examination or safety step changes what you can document?','answer':plan['exam']},{'prompt':'Name one tempting documentation or reasoning error and how you will prevent it.','answer':plan['avoid']}],'course_sources':COURSE,'sources':c.get('sources',[]),'review_status':'Source-linked authored lesson; all variants checked through the deterministic engine. Not faculty-approved. Timing and clinical review status are reported separately.','case_hash':hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest(),'engine_version':version.ENGINE_VERSION}

def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, help='Optional local verification report path.')
    parser.add_argument('--case', action='append', dest='case_ids', help='Build selected cases only; repeat for a controlled subset.')
    args = parser.parse_args()
    out=ROOT/'pcmcse/teaching/lessons'
    original=db.DB_PATH
    built={};report=[]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            db.DB_PATH=str(Path(tmp)/'examples.sqlite');db.init()
            for cid,base in cases.all_cases().items():
                if args.case_ids and cid not in args.case_ids:continue
                lessons=[build(cases.resolve(cid,v.get('id','base')),v) for v in [{}]+base.get('variants',[])]
                built[cid]={'case_id':cid,'review_status':lessons[0]['review_status'],'walkthroughs':lessons}
                report.extend({k:l[k] for k in ('case_id','variant_id','note_words','estimated_encounter_s','missing_example_facts','case_hash','engine_version')} for l in lessons)
    finally:
        db.DB_PATH=original
    missing=[(r['case_id'],r['variant_id'],r['missing_example_facts']) for r in report if r['missing_example_facts']]
    over_time=[(r['case_id'],r['variant_id'],r['estimated_encounter_s'],r['note_words']) for r in report if r['estimated_encounter_s']>840 or r['note_words']>550]
    # Build and validate the entire library before replacing any published lesson.
    # A failed dialogue must not leave the library half regenerated.
    if missing or over_time:
        raise ValueError(json.dumps({'missing':missing,'over_time':over_time}))
    out.mkdir(exist_ok=True)
    for cid,payload in built.items():
        (out/(cid+'.json')).write_text(json.dumps(payload,indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2))
    print(json.dumps({'presentations':len(built),'walkthroughs':len(report),'missing':missing,'over_time':over_time},indent=2))
if __name__=='__main__':main()
