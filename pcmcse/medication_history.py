"""Match medication details to explicitly authored drug histories."""
import re
from . import nlp
NAMES = {
 'acetaminophen': r'acetaminophen|tylenol|paracetamol', 'ibuprofen': r'ibuprofen|advil|motrin',
 'amlodipine': r'amlodipine|norvasc', 'lisinopril':r'lisinopril', 'atorvastatin':r'atorvastatin|lipitor',
 'hydrochlorothiazide':r'hydrochlorothiazide|hctz', 'furosemide':r'furosemide|lasix',
 'metformin':r'metformin', 'fenofibrate':r'fenofibrate', 'levothyroxine':r'levothyroxine|synthroid',
 'loratadine':r'loratadine|claritin', 'cetirizine':r'cetirizine|zyrtec', 'diphenhydramine':r'diphenhydramine|benadryl',
 'sumatriptan':r'sumatriptan|imitrex', 'hydrocortisone':r'hydrocortisone',
 'antacid':r'antacids?|calcium carbonate|tums', 'iron':r'iron', 'contraceptive':r'contraceptive|birth control',
}
def names(text):
 return [key for key,pattern in NAMES.items() if re.search(r'\b(?:'+pattern+r')\b',text,re.I)]
def request(utterance,facts,state):
 q=nlp.normalize(nlp.expand_contractions(utterance))
 if re.search(r'\b(?:mother|father|sister|brother|wife|husband|friend|partner|family|should|recommend|prescribe)\b|allerg|reaction|["“”]',q):return None
 dims=[]
 if re.search(r'\b(?:dose|dosage|strength|milligrams?|mg|micrograms?|mcg)\b|how much',q):dims.append('dose')
 if re.search(r'how many.*(?:tablets?|pills?|capsules?)|(?:tablet|pill|capsule) count',q):dims.append('tablets')
 if re.search(r'how often|times (?:a|per) day|frequency|every day|daily',q):dims.append('frequency')
 if re.search(r'last (?:take|took|dose)|taken.*today|take.*today',q):dims.append('last_dose')
 if not dims:return None
 ns=names(q)
 if not ns and state.get('last_subjects')==['medications']:
  ns=state.get('medication_context',[]) or list(dict.fromkeys(n for f in facts if f['id'] in state.get('last_facts',[]) for n in names(f.get('value',''))))
 if not ns:
  if not re.search(r'\b(?:medicines?|medications?|tablets?|pills?|capsules?|dosage|dose)\b',q):return None
  return {'names':[],'dimensions':dims}
 return {'names':ns,'dimensions':dims}
def select(facts,request):
 selected=[];missing=[];facts=list(facts)
 if not request['names']:return [],['which medicine you mean']
 for name in request['names']:
  candidates=[f for f in facts if f.get('category') in ('medications','treatment') and (name in f.get('medication_names',[]) or name in names(f.get('value','')))]
  for dim in request['dimensions']:
   pattern={'dose':r'\b(?:\d+|twenty|forty|eight hundred|four hundred)\s*(?:mg|mcg|milligrams?|micrograms?)|atorvastatin forty',
    'tablets':r'\b(?:one|two|three|\d+)\s+(?:(?:\d+)[ -]?(?:mg|milligram)\s+)?(?:tablets?|pills?|capsules?)',
    'frequency':r'daily|every morning|at night|twice|once|times|days? (?:per|a) month|when|as needed',
    'last_dose':r'today|yesterday|last night|this morning|this week'}[dim]
   matches=[f for f in candidates if dim in f.get('medication_dimensions',[]) or re.search(pattern,f.get('value',''),re.I)]
   matches.sort(key=lambda f: dim not in f.get('medication_dimensions',[]))
   if matches:
    if matches[0] not in selected:selected.append(matches[0])
   else:missing.append(dim.replace('_',' ')+' of '+name)
 return selected,missing
