"""Deliberately sparse pre-expansion fixtures for non-fabrication regressions.

Current cases now have explicit supplemental answers. Tests of missing information
must remove those additions rather than require the current app to omit them.
The expanded library is exercised separately by test_complete_case_content.
"""
import copy
from pcmcse import cases

def without_supplemental_content(case):
    c=copy.deepcopy(case)
    c['facts']=[f for f in c['facts'] if not f.get('authoring',{}).get('kind')=='user_requested_fictional_case_expansion']
    for f in c['facts']:f.pop('ros_topics',None)
    c['exam_findings']={k:[f for f in rows if not f.get('authoring',{}).get('kind')=='user_requested_fictional_case_expansion'] for k,rows in c['exam_findings'].items()}
    c['exam_findings']={k:v for k,v in c['exam_findings'].items() if v}
    c['concept_lexicon']={k:v for k,v in c['concept_lexicon'].items() if not k.startswith('expanded_')}
    for k in ('practice_expansion','exam_limitations'):c.pop(k,None)
    return c

def resolve(*args,**kwargs):return without_supplemental_content(cases.resolve(*args,**kwargs))
