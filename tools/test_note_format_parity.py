"""Equivalent layouts must retain identical row credit across every case path.

Reuses frozen demonstrated encounters as disposable evidence; transforms only
headings, whitespace, or Subjective section order. Does not demand a perfect
score, change case facts, or touch saved learner attempts.
"""
import copy,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pcmcse import cases,note,evidence,audit,grader
root=ROOT
report=[];failures=[]
for cid,base in cases.all_cases().items():
 for lesson in json.loads((root/'pcmcse/teaching/lessons'/f'{cid}.json').read_text())['walkthroughs']:
  case=cases.resolve(cid,lesson['variant_id']);ledger=evidence.Ledger(copy.deepcopy(lesson['ledger']))
  original=lesson['note'];baseline=None
  for style in ['colon','standalone','dash','markdown','multiline','reordered']:
   payload=copy.deepcopy(original)
   if style in ['standalone','dash','markdown']:
    for field,headers in [('S',note.S_HEADERS),('O',note.O_HEADERS)]:
     forms='|'.join(re.escape(f) for v in headers.values() for f in v)
     pattern=re.compile(r'^('+forms+r'):\s*',re.M|re.I)
     payload[field]=pattern.sub(lambda m:(m[1]+'\n' if style=='standalone' else m[1]+' — ' if style=='dash' else '**'+m[1]+':** '),payload[field])
   if style=='multiline':
    for field in ['A','P']:payload[field]=[re.sub(r'\. +(?=[A-Z])','.\n',t) for t in payload[field]]
   if style=='reordered':
    blocks,preamble=note.parse_headed_section(payload['S'],note.S_HEADERS)
    payload['S']=preamble+'\n'+'\n'.join(b['raw_header']+': '+b['body'] for b in reversed(blocks))
   parsed=note.parse(payload);checked=audit.audit_note(parsed,ledger,case);graded=grader.grade(parsed,ledger,case,checked)
   score={r['id']:r['points_earned'] for r in graded['rows']}
   if baseline is None:baseline=score
   differences={rid:(baseline[rid],pts) for rid,pts in score.items() if pts!=baseline[rid]}
   if differences:failures.append({'case':cid,'variant':lesson['variant_id'],'style':style,'differences':differences,'why':{r['id']:r['why'] for r in graded['rows'] if r['id'] in differences}})
   report.append({'case':cid,'variant':lesson['variant_id'],'style':style,'score':graded['total_earned']})
 print('Checked',cid,flush=True)
if '--report' in sys.argv:
 Path(sys.argv[sys.argv.index('--report')+1]).write_text(json.dumps({'results':report,'failures':failures},indent=2))
print(json.dumps({'checks':len(report),'failures':failures},indent=2))
assert not failures
