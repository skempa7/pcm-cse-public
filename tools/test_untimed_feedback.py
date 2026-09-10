import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pcmcse import feedback,evidence
for mode,allowed in [('coached',0),('guided',0),('independent',1800),('rehearsal',840)]:
 ledger=evidence.Ledger();ledger.add(evidence.EXAM_ACTION,'General appearance',t_ms=12500)
 session=SimpleNamespace(row={'encounter_used_ms':40000,'submit_reason':'manual'},preset={'encounter_s':allowed},settings={'learning_mode':mode,'simulation_runtime':'interactive'},is_untimed_phase=lambda phase:allowed==0)
 result=feedback._time_feedback(ledger,session,None)
 assert result['untimed']==(allowed==0)
 assert result['encounter_allowed_s']==(allowed or None)
 if allowed==0:assert not any('buzzer' in n or '% of the way' in n for n in result['notes'])
 print(mode,'PASS')
