import sys,copy
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pcmcse import patient,cases
intro='Hello, I am a student doctor. I will listen to your concerns and discuss the next steps with you.'
count=0
for cid,c in cases.all_cases().items():
 for variant in ['base']+[v['id']for v in c.get('variants',[])]:
  case=cases.resolve(cid,variant);s={};p=patient.PatientEngine(case)
  for q in [intro,'Hello. I am your medical student.',"Hi, I'm a student doctor. I'll listen to your concerns."]:
   text,meta=p.respond(q,s);assert meta['kind']=='introduction_response',(cid,q,text);assert not meta['facts_released']
  text,meta=p.respond('What were you doing when this started?',s)
  if cid=='cardio-febrile-cough':assert not meta['facts_released'] and 'coworker'not in text.lower()
  for q in ["How do you know it's pneumonia?","You just said pneumonia. How do you know it's pneumonia?"]:
   text,meta=p.respond(q,s);assert meta['kind']=='diagnostic_uncertainty'and not meta['facts_released'],(cid,text)
  count+=1
c=cases.resolve('cardio-febrile-cough');p=patient.PatientEngine(c);s={}
text,meta=p.respond('Have you had anything like this before?',s);assert 'pneumonia'not in text.lower() and meta['facts_released']==['hpi_past_occurrence']
text,meta=p.respond('Have you been around anyone who was ill?',s);assert 'coworker'in text and meta['facts_released']==['hpi_setting']
legacy=copy.deepcopy(c)
f=next(f for f in legacy['facts']if f['id']=='hpi_past_occurrence');f['sp_says']=['I have not had pneumonia before.']
text,meta=patient.PatientEngine(legacy).respond('Have you had anything like this before?',{});assert not meta['facts_released'] and 'pneumonia'not in text
try:
 from pcmcse import ai_patient
except ImportError:pass
else:
 provider=object.__new__(ai_patient.PatientProvider);provider.config=SimpleNamespace(enabled=True)
 for q in [intro,'What were you doing when this started?',"How do you know it's pneumonia?"]:
  result=provider.prepare_reply(c,q,{},'offline-test');assert result['use_scripted'] and result['fallback_reason']=='scripted_conversation_route'
 cat=ai_patient._catalog(c,'Have you had anything like this before?',{})
 assert all('pneumonia'not in x.lower()for f in cat.values()if f['id']=='hpi_past_occurrence'for x in f['sp_says'])
 print('AI routing checked without network requests')
print('PASS',count,'case variants; introductions, onset scope, diagnosis clarification, legacy wording, exposure question')
