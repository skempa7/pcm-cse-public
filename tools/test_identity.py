import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pcmcse import patient,cases
count=0
for cid,c in cases.all_cases().items():
 for variant in ['base']+[v['id'] for v in c.get('variants',[])]:
  case=cases.resolve(cid,variant);p=patient.PatientEngine(case);s={};name=case['patient']['name'];age=str(case['patient']['age'])
  for question in ["what's your name and how old are you",'Can you confirm your full name and age?', 'Please tell me your name and your age.']:
   reply,meta=p.respond(question,s)
   assert name in reply and age+' years old' in reply,(cid,question,reply)
   assert meta['kind']=='identity_response' and not meta['facts_released'] and not meta['concepts']
  reply,_=p.respond('How old are you?',s);assert name not in reply and age in reply
  reply,_=p.respond('What should I call you?',s);assert name in reply
  for question in ['What do you do for work?','How old were you when this started?', 'How old is your mother?']:
   assert patient.conversation_route(question)!='identity'
  count+=1
try:
 from pcmcse import ai_patient
 from types import SimpleNamespace
 provider=object.__new__(ai_patient.PatientProvider);provider.config=SimpleNamespace(enabled=True)
 result=provider.prepare_reply(case,"what's your name and how old are you",{},'identity-test')
 assert result['use_scripted'] and result['fallback_reason']=='scripted_conversation_route'
except ImportError:pass
print('PASS identity questions across',count,'case variants; no unrelated clinical credit; AI uses the same identity route')
