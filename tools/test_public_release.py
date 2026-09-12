import sys,os,json,tempfile,hashlib,zipfile,re,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['PCM_CSE_DB']=tempfile.mktemp(suffix='.sqlite');os.environ['PCM_CSE_SETTINGS']=tempfile.mktemp(suffix='.json')
from pcmcse import db,cases,teaching,engine,evidence
from offline_routes import request
db.init()
def call(path,body=None,status=200):
 r=json.loads(request(path,'GET' if body is None else 'POST',json.dumps(body or {})));assert r['status']==status,(path,r);return r['body']
rows=call('/api/bootstrap')['cases'];assert len(rows)==24
report=[]
for index,row in enumerate(rows):
 for variant in ['base']+[v['id'] for v in row['variants']]:
  c=cases.resolve(row['id'],variant);sex=c['patient']['sex'];s=call('/api/session',{'case_id':row['id'],'variant_id':variant,'learning_mode':'independent'});sid=s['id']
  loaded=engine.load(sid);assert loaded.row['phase']=='briefing' and not loaded.row['phase_ends_at']
  s=call('/api/session/'+sid+'/start',{});assert s['phase']=='encounter';assert any(e['kind']==evidence.STATION_INFO for e in engine.load(sid).ledger.events);deadline=engine.load(sid).row['phase_ends_at']
  call('/api/session/'+sid+'/say',{'text':'What brings you in today?'})
  fresh=call('/api/session/'+sid);assert engine.load(sid).row['phase_ends_at']==deadline
  assert any(e['kind']==evidence.PATIENT for e in engine.load(sid).ledger.events)
  lesson=teaching.read(row['id'],variant);assert lesson and not lesson['missing_example_facts'];assert lesson['estimated_encounter_s']<=840
  if sex=='male':
   assert not any(f.get('history_topic') in ('pregnancy','menstrual') for f in c['facts'])
  s=call('/api/session/'+sid+'/end_encounter',{});assert s['phase']=='organize';s=call('/api/session/'+sid+'/skip_organize',{});assert s['phase']=='note'
  original={'S':c['patient']['opening'],'O':'Supplied BP '+c['station']['vitals']['BP'],'A':'Differential remains broad.','P':'Discuss with the supervising clinician.'}
  assert call('/api/session/'+sid+'/note',{'note':original})['saved']
  call('/api/session/'+sid+'/submit',{'note':original});result=call('/api/session/'+sid+'/results');assert result['results']
  frozen=engine.load(sid).row['original_note_json'];assert not call('/api/session/'+sid+'/note',{'note':{'S':'overwrite'}})['saved'];assert frozen==engine.load(sid).row['original_note_json']
  report.append({'case_id':row['id'],'variant_id':variant,'sex':sex,'flow':'doorway/start/say/reload-model/organization/note/submit/locked-original','walkthrough':True})
assert sum(cases.get(x['id'])['patient']['sex']=='male' for x in rows)==6
# Ordinary UI solution gates survive the browser conversion.
s=call('/api/session',{'case_id':rows[0]['id'],'learning_mode':'rehearsal'});sid=s['id'];call('/api/teaching',status=409);call('/api/session/'+sid+'/start',{});deadline=engine.load(sid).row['phase_ends_at'];call('/api/teaching/access',{'confirm':True,'attempt_ids':[sid]});assert engine.load(sid).row['phase_ends_at']==deadline;assert engine.load(sid).row['assisted'];call('/api/teaching')
for path in ['/api/voice','/api/ai/status','/api/session/'+sid+'/ai-turn','/api/session/'+sid+'/transcribe']:
 call(path,{} if path.endswith(('ai-turn','transcribe','voice')) else None,status=404)
# Both wardrobe states share the original clinical skin material.
# Public artifacts are a closed, explicit runtime package, no provider modules.
for name in ['ai_patient.py','natural_voice.py','conversation.py']:assert not (ROOT/'pcmcse'/name).exists()
# A filename list is not the boundary: a billable call added to offline_routes.py,
# a key pasted into the web bundle, or a provider module tucked inside engine.zip
# all passed the check above untouched. Scan what actually ships.
import subprocess as _sp
_scan=_sp.run([sys.executable,str(ROOT/'tools/check_provider_free.py')],capture_output=True,text=True)
assert _scan.returncode==0,'published edition can reach a paid service:\n'+_scan.stdout+_scan.stderr
assets=[]
for p in (ROOT/'web/patient3d/assets').glob('public-*.glb'):
 data=p.read_bytes();n=struct.unpack_from('<I',data,12)[0];g=json.loads(data[20:20+n]);names={n.get('name') for n in g['nodes']};assert 'PCM_PublicBody' in names and 'PCM_AnatomicalBody' in names;assert not {'PCM_FemaleBody','PCM_FemaleBody_Source','PCM_FemaleBody_Covered'} & names;assert {'PCM_Seated','PCM_Supine','PCM_Standing','PCM_Prone'}<={a['name'] for a in g['animations']};assert {'PCM_PublicKnit','PCM_PublicTrousers','PCM_PublicShoes'}<=names
 anatomy=next(node for node in g['nodes'] if node.get('name')=='PCM_AnatomicalBody')
 assert all(g['materials'][p['material']]['name']=='PCM_Mat_Skin' for p in g['meshes'][anatomy['mesh']]['primitives'])
 assert not any(m.get('name')=='PCM_ClinicalManikin' for m in g['materials'])
 assets.append({'file':p.name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
assert len(assets)==4
out={'result':'PASS','playable_paths':len(report),'women':18,'men':6,'checks':report,'assets':assets,'limits':'Structural/route regression checks, not independent clinical validation. Symbolic SOAP grading is provisional; unrecognized wording receives no automatic credit.'}
(ROOT/'public-verification.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:out[k]for k in ('result','playable_paths','women','men','limits')}))
