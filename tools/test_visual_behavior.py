import sys,copy,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pcmcse import presentation,evidence,cases
ledger=evidence.Ledger();case={'station':{'doorway':['A patient with stomach pain.']},'patient':{}}
a=presentation.gesture(case,ledger);assert a['region']=='abdomen' and not a['clinical_evidence'];assert not ledger.events
hidden=copy.deepcopy(case);hidden['exam_findings']={'heart':[{'text':'secret left chest pain'}]};hidden['diagnosis']='secret';assert presentation.gesture(hidden,ledger)==a
ledger.add(evidence.STUDENT,'I have pain in my left shoulder');assert presentation.gesture(case,ledger)==a
ledger.add(evidence.PATIENT,'My left shoulder hurts',meta={'uncertain':True});assert presentation.gesture(case,ledger)==a
ledger.add(evidence.PATIENT,'My left shoulder hurts',meta={'no_information':True});assert presentation.gesture(case,ledger)==a
ledger.add(evidence.PATIENT,'My left shoulder hurts right now.');assert presentation.gesture(case,ledger)['side']=='left';assert presentation.gesture(case,ledger)['region']=='shoulder'
neutral={'station':{'doorway':['Medication review.']},'patient':{}};assert presentation.gesture(neutral,evidence.Ledger())['region']=='none'
for c in cases.all_cases().values():
 l=evidence.Ledger();before=l.to_json();v=presentation.gesture(c,l);assert l.to_json()==before;assert set(v)<=set(['version','region','side','disclosed','source_seq','clinical_evidence','meaning']);changed=copy.deepcopy(c);changed['exam_findings']={};changed['facts']={};assert presentation.gesture(changed,l)==v
print(json.dumps({'passed':True,'cases':len(cases.all_cases()),'checks':['no ledger mutation','no hidden finding dependence','ignore student and uncertain replies','disclosed laterality','neutral complaint remains neutral']}))
