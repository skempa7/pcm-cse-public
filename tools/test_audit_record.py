"""Record UI metadata must describe delivered events, without exposing hidden facts."""
import os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as tmp:
 os.environ['PCM_CSE_DB']=str(Path(tmp)/'attempts.sqlite')
 os.environ['PCM_CSE_SETTINGS']=str(Path(tmp)/'settings.json')
 from pcmcse import cases,config,db,engine
 db.init()
 c=cases.resolve('renal-flank-pain','base');settings=dict(config.DEFAULT_SETTINGS,learning_mode='coached',simulation_runtime='interactive');preset=config.preset_for_learning_mode('coached')
 sid=db.create_session(c['id'],preset,'type',True,settings,case=c);s=engine.load(sid);s.start_encounter();s.student_turn('Hello, I am a medical student.')
 data=engine.state_payload(s);replies=[e for e in data['transcript'] if e['kind']=='patient_reply'];assert replies[-1]['meta']['has_clinical_information'] is False
 supplied={e['meta']['supplied_kind']for e in data['transcript'] if e['kind']=='station_info'};assert {'vitals','doorway','result'}<=supplied
 s.student_turn('What brings you in today?');before=s.ledger.to_json();data=engine.state_payload(s)
 assert [e for e in data['transcript'] if e['kind']=='patient_reply'][-1]['meta']['has_clinical_information'] is True
 assert all('facts_released' not in e['meta'] and 'concepts' not in e['meta'] for e in data['transcript'])
 assert before==s.ledger.to_json()
 print('PASS: greeting is communication; opening is clinical history; doorway/vitals/results distinct; no hidden IDs; ledger unchanged')
