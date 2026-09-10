"""Private, evidence-linked written teaching. Never served as a static asset."""
from pathlib import Path
import json
from .. import cases, db, engine, evidence, learning
ROOT=Path(__file__).parent

def blockers():
    with db.connect() as conn:
        rows=conn.execute("SELECT id,case_id,phase,assisted,settings_json FROM sessions WHERE phase != 'submitted' AND assisted=0").fetchall()
    return [{'id':r['id'],'station':cases.get(r['case_id']).get('hidden_label','Station'),'phase':r['phase']} for r in rows if json.loads(r['settings_json']).get('learning_mode') in ('rehearsal','independent')]

def allow_solutions(ids):
    pending=blockers()
    if set(ids)!=set(r['id'] for r in pending):raise ValueError('Active attempts changed. Review the confirmation again.')
    for item in pending:
        s=engine.load(item['id'])
        if s.row['phase']=='submitted':continue
        settings=dict(s.settings)
        settings['original_learning_mode']=settings.get('original_learning_mode',settings.get('learning_mode'))
        settings['learning_mode']='coached'
        settings['solution_access']=True
        s.settings=settings
        s.set(assisted=1,settings_json=json.dumps(settings))
        s.ledger.add(evidence.SYSTEM,'Written solution access: changed to assisted practice; original deadlines retained.',t_ms=s.elapsed_ms(),phase=s.row['phase'],meta={'event':'solution_access','previous_mode':settings['original_learning_mode']})
        s.save();learning.record(s.id,'solution_access',{'timing_changed':False})
    return pending

def index():
    rows=[]
    for c in cases.index():
        path=ROOT/'lessons'/(c['id']+'.json')
        if not path.exists():continue
        lesson=json.loads(path.read_text())
        rows.append({**c,'teaching_status':lesson['review_status'],'walkthroughs':[{'id':x['variant_id'],'label':x['variant_label'],'words':x['note_words']} for x in lesson['walkthroughs']]})
    return rows

def read(cid,variant='base'):
    if not cases.get(cid):raise ValueError('Unknown presentation')
    lesson=json.loads((ROOT/'lessons'/(cid+'.json')).read_text())
    return next((x for x in lesson['walkthroughs'] if x['variant_id']==variant),None)

def progress():
    with db.connect() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS study_progress (case_id TEXT, variant_id TEXT, updated_at INTEGER, recall_json TEXT, PRIMARY KEY(case_id,variant_id))')
        return [dict(r) for r in conn.execute('SELECT * FROM study_progress ORDER BY updated_at DESC')]

def save_progress(cid,variant,answers):
    lesson=read(cid,variant)
    if not lesson:raise ValueError('Unknown walkthrough')
    if not isinstance(answers,list) or len(answers)!=len(lesson['recall']) or any(not isinstance(a,str) or len(a)>2000 for a in answers):raise ValueError('Enter a response for each recall prompt (maximum 2000 characters each).')
    progress()
    with db.connect() as conn:
        conn.execute('INSERT OR REPLACE INTO study_progress VALUES(?,?,?,?)',(cid,variant,db.now_ms(),json.dumps(answers)))
    return {'saved':True,'message':'Reflection saved separately from examination scores.'}
