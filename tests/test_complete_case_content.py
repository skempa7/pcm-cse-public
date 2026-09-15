"""Current authored coverage, clinical contrasts and release boundaries.

Sparse-fixture tests elsewhere still protect genuinely missing information.
This suite intentionally exercises the expanded current library.
"""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from pcmcse import cases,patient,ros_history,physexam,config,db,engine,evidence,record

def paths():
 for cid,base in cases.all_cases().items():
  for vid in ['base']+[v['id'] for v in base.get('variants',[])]:yield cases.resolve(cid,vid)

def actions(m):
 cs=m['components'];mid=m['id']
 groups={'heent_eyes':[['pupils','conjunctivae','sclerae','cornea'],['extraocular movements'],['fundoscopic']],
 'neck_rom':[['flexion','rotation'],['brudzinski'],['kernig']], 'abd_auscultate':[['all four quadrants'],['bruits']],
 'abd_percuss':[['four quadrants'],['liver span'],['shifting dullness']], 'abd_palpate':[['light','four quadrants','guarding'],['deep','four quadrants'],['rebound']],
 'msk_slr':[['supine','right','left'],['seated','right','left']], 'neuro_reflexes':[['biceps','triceps','patellar','achilles'],['babinski']],
 'neuro_dix_hallpike':[['cervical_suitability'],['cervical_suitability','right'],['cervical_suitability','left']]}
 if mid in groups:return groups[mid]
 if mid in ('abd_special','msk_palpate','msk_strength','neuro_cn','neuro_sensory','neuro_coordination','skin_inspect','osteo_screen'):return [[x] for x in cs]
 return [cs]

class CompleteCaseContentTests(unittest.TestCase):
 def test_every_case_answers_every_screen_with_exact_authored_evidence(self):
  count=0
  for c in paths():
   p=patient.PatientEngine(c);state={};byid={f['id']:f for f in c['facts']}
   for topic,(_,_,label) in ros_history.TOPICS.items():
    expected=ros_history.select(c['facts'],topic)
    self.assertTrue(expected,(c['id'],topic))
    for q in ['Have you noticed any '+label+'?','Have you had any '+label+'?','Any '+label+'?']:
     text,meta=p.respond(q,state)
     self.assertEqual(meta.get('facts_released'),[f['id'] for f in expected],(c['id'],topic,q,text))
     self.assertFalse(meta.get('no_information'),(c['id'],q,text))
     self.assertFalse(meta.get('unavailable_topics'),(c['id'],q,text))
     for fid in meta['facts_released']:self.assertIn(byid[fid]['sp_says'][0],text)
     count+=1
  self.assertEqual(count,82*len(ros_history.TOPICS)*3)
 def test_sore_throat_paraphrases_and_positive_case(self):
  for c in paths():
   for q in ['Does your throat hurt?','Is your throat sore?','Any pain in your throat?']:
    text,meta=patient.PatientEngine(c).respond(q,{})
    self.assertTrue(meta['facts_released'],(c['id'],q,text))
    self.assertFalse(meta.get('unavailable_topics'))
    if c['id']=='heent-sore-throat':self.assertIn('scratchy',text)
 def test_noah_reported_sequence_and_tablet_followup(self):
  p=patient.PatientEngine(cases.resolve('cardio-febrile-cough'));s={}
  prompts=[('How is your diet?','cereal'),('Do you take any medications?','acetaminophen'),
   ("What is the dose of acetaminophen you're taking?",'500 mg'),('How many tablets do you take when you take it?','one 500 mg'),
   ('Do you have any allergies like any food allergies?','no known food'),('Do you have any environmental allergies?','not had seasonal'),
   ('Do you have any medication allergies?','Amoxicillin'),('Any cramping?','not had cramps'),('Any fever?','101.5'),
   ('Is the pain constant or does it come and go?','eases between'),('Does the pain happen during the day or at night?','not limited')]
  for q,expected in prompts:
   text,meta=p.respond(q,s);self.assertIn(expected,text,(q,text));self.assertTrue(meta['facts_released']);self.assertFalse(meta.get('no_information'))
  text,meta=p.respond('Is the back pain constant or does it come and go?',{})
  self.assertNotIn('expanded_pain_constancy',meta['facts_released'])
 def test_supplements_do_not_match_unrelated_questions(self):
  for c in paths():
   for q in ['What medications do you take?','What is your job?','What operations have you had?']:
    text,meta=patient.PatientEngine(c).respond(q,{})
    self.assertFalse(any(fid.startswith('expanded_ros_') for fid in meta['facts_released']),(c['id'],q,text))
 def test_every_visible_action_releases_result_or_explicit_safe_deferral(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(db,'DB_PATH',str(Path(tmp)/'attempts.sqlite')):
   db.init();count=0
   for c in paths():
    settings=copy.deepcopy(config.DEFAULT_SETTINGS)
    settings.update(learning_mode='coached',simulation_runtime='text')
    settings['scoring']=dict(settings.get('scoring',{}),realtime_exam_durations=False)
    sid=db.create_session(c['id'],'coached_untimed','type',False,settings,case=c)
    s=engine.load(sid);s.start_encounter()
    for m in physexam.CATALOG:
     for cs in actions(m):
      before=len(s.ledger.by_kind(evidence.EXAM_FINDING))
      result=s.perform_maneuver(m['id'],cs)
      limited=m['id'] in c.get('exam_limitations',{}) and cs!=['cervical_suitability']
      self.assertEqual(result['kind'],'no_result' if limited else 'finding',(c['id'],m['id'],cs,result))
      if limited:self.assertEqual(len(s.ledger.by_kind(evidence.EXAM_FINDING)),before)
      else:
       self.assertTrue(result['released'])
       if m['id']=='neuro_dix_hallpike' and cs!=['cervical_suitability']:
        self.assertIn('nystagmus',result['text'].lower(),(c['id'],cs,result))
        self.assertIn(cs[-1],result['text'].lower(),(c['id'],cs,result))
       self.assertEqual(len(s.ledger.by_kind(evidence.EXAM_FINDING)),before+1)
      count+=1
   self.assertEqual(count,82*sum(len(actions(m)) for m in physexam.CATALOG))
 def test_deficits_and_abnormal_findings_survive_component_actions(self):
  expected=[('skin-contact-rash','skin_inspect',['arms'],'erythematous'),('neuro-acute-focal-weakness','msk_strength',['upper extremity'],'3/5'),('neuro-distal-neuropathy','neuro_sensory',['vibration'],'reduced'),('gi-epigastric-melena','abd_auscultate',['all four quadrants'],'Hyperactive'),('renal-flank-pain','osteo_screen',['thoracic'],'T11')]
  for cid,mid,cs,word in expected:
   rows=cases.resolve(cid)['exam_findings'][mid]
   text=' '.join(f['text'] for f in rows if set(f.get('requires_components',[]))<=set(cs))
   self.assertIn(word,text,(cid,mid,text))
 def test_current_background_allergy_and_medication_answers_keep_their_scope(self):
  from pcmcse import allergy_history
  for c in paths():
   p=patient.PatientEngine(c);state={};byid={f['id']:f for f in c['facts']}
   for question in ['How is your diet?', 'Do you get enough sleep?']:
    text,meta=p.respond(question,state)
    self.assertTrue(meta['facts_released'],(c['id'],question,text))
    self.assertFalse(meta.get('no_information'),(c['id'],question,text))
   for scope in ['food','environmental','medication']:
    text,meta=p.respond('Do you have any '+scope+' allergies?',state)
    self.assertTrue(meta['facts_released'],(c['id'],scope,text))
    self.assertFalse(meta.get('no_information'),(c['id'],scope,text))
    if scope in ('food','environmental'):
     self.assertFalse(any(fid.startswith('history_allerg') for fid in meta['facts_released']),(c['id'],scope,text))
   for f in c['facts']:
    if not f.get('medication_dimensions'):continue
    drug=f['medication_names'][0]
    for dimension,prompt in [('dose','What dose of '+drug+' do you take?'),('tablets','How many '+drug+' tablets do you take?'),('frequency','How often do you take '+drug+'?')]:
     if dimension not in f['medication_dimensions']:continue
     text,meta=p.respond(prompt,state)
     self.assertIn(f['id'],meta['facts_released'],(c['id'],prompt,text))
     self.assertFalse(meta.get('no_information'),(c['id'],prompt,text))
 def test_new_facts_enter_notes_only_after_the_corresponding_question(self):
  c=cases.resolve('cardio-febrile-cough');p=patient.PatientEngine(c);state={};ledger=evidence.Ledger()
  for q in ['Any sore throat?', 'Any food allergies?', 'Any nausea?']:
   text,meta=p.respond(q,state)
   ledger.add(evidence.STUDENT,q);ledger.add(evidence.PATIENT,text,meta=meta)
  result=record.summarize(c,ledger.events)
  ids={i['fact_id'] for g in result['groups'] for sec in g['sections'] for i in sec['items']}
  self.assertEqual(ids,{'expanded_ros_sore_throat','expanded_allergy_food','expanded_ros_nausea'})
 def test_case_additions_are_not_automatically_in_notes(self):
  for c in paths():
   summary=record.summarize(c,[])
   self.assertNotIn('expanded_',json.dumps(summary))
   ids=[f['id'] for f in c['facts']];self.assertEqual(len(ids),len(set(ids)))
   for f in c['facts']:
    if f.get('authoring'):
     self.assertFalse(f.get('checklist'));self.assertNotEqual(f.get('triggers'),{'any':[]})
     self.assertEqual(f['delivery_contract']['versions'][0]['concepts'],f['concepts'])
if __name__=='__main__':unittest.main()
