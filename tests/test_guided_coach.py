"""Guided practice: source-bound steps, actual evidence, protected modes, replayable cues."""
import copy
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pcmcse import cases, config, db, engine, evidence, guide, learning


class GuidedCoachTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pcm-guided-coach-')
        self.old = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name,'attempts.sqlite')
        db.init()
        self.now = 1789000000000
        self.clock = patch('pcmcse.db.now_ms',side_effect=lambda:self.now)
        self.clock.start()

    def tearDown(self):
        self.clock.stop();db.DB_PATH=self.old;self.temp.cleanup()

    def session(self,cid='renal-flank-pain',variant='base',mode='guided'):
        c=cases.resolve(cid,variant);settings=config.load_settings();preset=config.preset_for_learning_mode(mode)
        settings.update(learning_mode=mode,simulation_runtime='interactive',preset=preset)
        sid=db.create_session(cid,preset,'type',mode=='guided',settings,case=c)
        s=engine.load(sid);s.start_encounter();return s

    def exam(self,s,mid,components):
        action=s.perform_maneuver(mid,components)
        self.assertEqual(action['kind'],'exam_started')
        self.now=action['due_at'];return engine.load(s.id)

    def route(self,s,action,body):
        root=Path(engine.__file__).resolve().parents[1]
        if (root/'offline_routes.py').exists():
            from offline_routes import Handler
        else:
            from server import Handler
        h=object.__new__(Handler);h.path='/api/session/'+s.id+'/'+action;h.headers={'Host':'localhost'}
        h._body=lambda:body;h._json=lambda data,status=200:(status,data)
        return h.do_POST()

    def test_new_mode_station_brief_and_supplied_record_match_actual_timing(self):
        source = copy.deepcopy(cases.resolve('renal-flank-pain','base'))
        for mode in ('guided','coached','independent','rehearsal'):
            s = self.session(mode=mode)
            doorway = ' '.join(s.case['station']['doorway'])
            event = next(e for e in s.ledger.by_kind(evidence.STATION_INFO)
                         if e['meta'].get('doorway'))
            self.assertEqual(event['text'],doorway)
            if mode in ('guided','coached'):
                self.assertIn('untimed',doorway)
                self.assertNotIn('14 minutes',doorway)
            elif mode == 'independent':
                self.assertIn('30 minutes',doorway)
                self.assertIn('5 minutes',doorway)
                self.assertIn('20 minutes',doorway)
                self.assertNotIn('14 minutes',doorway)
            else:
                self.assertIn('14 minutes',doorway)
            original = s.ledger.to_json()
            self.assertEqual(engine.load(s.id).ledger.to_json(),original)
        self.assertEqual(cases.resolve('renal-flank-pain','base'),source)
        legacy_settings=config.load_settings();legacy_settings.update(learning_mode='coached')
        legacy=db.create_session('renal-flank-pain','practice','type',False,legacy_settings,case=source)
        old=engine.load(legacy);old.start_encounter()
        self.assertIn('14 minutes',next(e for e in old.ledger.by_kind(evidence.STATION_INFO) if e['meta'].get('doorway'))['text'])
        snapshot=db.get_session(legacy)['case_snapshot']
        self.session(mode='coached')
        self.assertEqual(db.get_session(legacy)['case_snapshot'],snapshot)

    def test_first_moves_are_visible_in_order_and_advance_only_from_real_courtesy_and_reply(self):
        s=self.session();data=learning.state(s)
        self.assertEqual(data['case_guide']['selected'],'connect.introduce')
        before=s.ledger.to_json()
        guide.navigate(s,{'step':'connect.name','action':'select'})
        self.assertEqual(s.ledger.to_json(),before)
        self.assertEqual(next(t for t in guide.state(s)['tasks'] if t['id']=='connect.name')['status'],'next')
        for ident in ('connect.introduce','connect.name','connect.hands','history.opening_disclosure'):
            task=next(t for t in guide.state(s)['tasks'] if t['id']==ident)
            s.student_turn(task['question']);s=engine.load(s.id)
            self.assertEqual(next(t for t in guide.state(s)['tasks']if t['id']==ident)['status'],'obtained')
        self.assertNotEqual(guide.state(s)['recommended'],'connect.introduce')
        self.assertIsNone(s.row['phase_ends_at'])

    def test_all_82_variants_have_real_authored_case_paths_without_answers_in_task_payload(self):
        count=0;paths={}
        for base in cases.all_cases().values():
            for variant in ['base']+[v['id'] for v in base.get('variants',[])]:
                s=self.session(base['id'],variant);before=s.ledger.to_json()
                result=guide.state(s);tasks=result['tasks'];fids={f['id'] for f in s.case['facts']}
                self.assertGreater(len(tasks),20)
                self.assertEqual(len({t['id']for t in tasks}),len(tasks))
                self.assertTrue(any(t['kind']=='exam'for t in tasks))
                self.assertTrue(any(t.get('checkpoint')=='history'for t in tasks))
                for task in tasks:
                    self.assertTrue(set(task.get('facts',[]))<=fids)
                    self.assertFalse({'patient','finding','note','answer'} & set(task))
                self.assertEqual(s.ledger.to_json(),before)
                paths.setdefault(base['system'],set()).add(tuple(t['question']for t in tasks if t['group']=='pattern'))
                count+=1
        self.assertEqual(count,82)
        self.assertGreaterEqual(len(paths),4)
        self.assertGreater(len(set(next(iter(v))for v in paths.values())),1)

    def test_independent_exam_and_coached_do_not_receive_case_solution_path(self):
        for mode in ('coached','independent','rehearsal'):
            s=self.session(mode=mode);before=s.ledger.to_json()
            self.assertNotIn('case_guide',learning.state(s))
            with self.assertRaises(PermissionError):guide.state(s)
            self.assertEqual(self.route(s,'guide',{'step':'connect.introduce','action':'defer'})[0],403)
            if mode!='coached':
                self.assertNotIn('hint_history',learning.state(s))
                self.assertEqual(self.route(s,'hint',{'step':'pattern','level':1})[0],403)
            self.assertEqual(s.ledger.to_json(),before)

    def test_manual_defer_and_restore_never_grant_facts_or_checklist_credit(self):
        s=self.session();before=s.ledger.to_json();summary=s.ledger.summary_counts()
        result=guide.navigate(s,{'step':'connect.introduce','action':'defer'})
        self.assertEqual(result['deferred'],1)
        self.assertEqual(result['recommended'],'connect.name')
        self.assertEqual(result['completed'],0)
        self.assertEqual(s.ledger.to_json(),before)
        self.assertEqual(s.ledger.summary_counts(),summary)
        result=guide.navigate(engine.load(s.id),{'step':'connect.introduce','action':'restore'})
        self.assertEqual(result['recommended'],'connect.introduce')
        self.assertEqual(result['deferred'],0)

    def test_examination_selection_pending_and_partial_components_do_not_complete_step(self):
        s=self.session();guide.navigate(s,{'step':'exam.heart_auscultate','action':'select'})
        def task(s):return next(x for x in guide.state(s)['tasks'] if x['id']=='exam.heart_auscultate')
        self.assertEqual(task(s)['status'],'next');self.assertFalse(s.ledger.by_kind(evidence.EXAM_FINDING))
        action=s.perform_maneuver('heart_auscultate',['aortic','on skin'])
        self.assertEqual(task(s)['status'],'next')
        self.now=action['due_at'];s=engine.load(s.id)
        self.assertEqual(task(s)['status'],'next')
        s=self.exam(s,'heart_auscultate',task(s)['components'])
        self.assertEqual(task(s)['status'],'obtained')

    def test_heart_and_lung_findings_do_not_complete_neurologic_or_abdominal_focus(self):
        for cid in ('neuro-positional-vertigo','renal-flank-pain'):
            s=self.session(cid)
            for mid in ('general_inspect','heart_auscultate','lungs_auscultate'):
                t=next(t for t in guide.state(s)['tasks']if t.get('maneuver_id')==mid)
                s=self.exam(s,mid,t['components'])
            focus=next(x for x in guide.state(s)['coverage']['objective']if x['label']=='Focused system findings')
            self.assertFalse(focus['obtained'])

    def test_unlocked_cues_replay_both_directions_after_reload_without_new_assistance_or_wait(self):
        s=self.session(mode='coached');before=s.ledger.to_json()
        self.assertEqual(learning.hint(s,'pattern')['level'],1)
        self.assertTrue(learning.hint(s,'pattern')['wait'])
        self.now+=5100;self.assertEqual(learning.hint(s,'pattern')['level'],2)
        prior=copy.deepcopy(learning.events(s.id));self.now+=10
        cue1=learning.hint(engine.load(s.id),'pattern',1)
        cue2=learning.hint(engine.load(s.id),'pattern',2)
        self.assertTrue(cue1['replay']);self.assertTrue(cue2['replay'])
        self.assertEqual(learning.events(s.id),prior)
        self.assertGreater(cue2['wait_ms'],0)
        self.now+=5100;self.assertEqual(learning.hint(s,'pattern',3)['level'],3)
        for level in (2,1,3,1):self.assertTrue(learning.hint(engine.load(s.id),'pattern',level)['replay'])
        self.assertEqual(learning.summary(s)['hints_used'],3)
        self.assertEqual([c['level']for c in learning.state(s)['hint_history']['pattern']['cues']],[1,2,3])
        self.assertEqual(s.ledger.to_json(),before)

    def test_cue_level_step_and_navigation_validation(self):
        s=self.session()
        for step,level in [('nonsense',1),('pattern',True),('pattern',4),('pattern',3),('pattern','1')]:
            self.assertEqual(self.route(s,'hint',{'step':step,'level':level})[0],400)
        for body in ({'step':'missing','action':'select'},{'step':'connect.introduce','action':'complete'}, {'step':'connect.introduce','action':'defer','credited':True}):
            self.assertEqual(self.route(s,'guide',body)[0],400)
        self.assertEqual(learning.summary(s)['hints_used'],0)

    def test_differently_worded_closing_uses_recorded_communication_not_exact_script(self):
        s=self.session()
        s.student_turn('I recommend discussing treatment and follow up with my supervising clinician.')
        s.student_turn('Do you have any questions for me?')
        result=guide.state(s)
        counsel=[x for x in result['tasks']if x.get('match')=='counsel']
        closure=[x for x in result['tasks']if x.get('match')=='closure']
        self.assertTrue(counsel);self.assertTrue(closure)
        self.assertTrue(all(t['status']=='obtained'for t in counsel))
        self.assertTrue(all(t['status']=='obtained'for t in closure))

    def test_coverage_uncertainty_does_not_trap_the_next_action(self):
        s=self.session();result=guide.state(s)
        checkpoint=next(t for t in result['tasks']if t['id']=='checkpoint.history')
        self.assertEqual(checkpoint['status'],'review')
        self.assertNotEqual(result['recommended'],'checkpoint.history')
        self.assertIn('do not block',result['checkpoint_note'])

    def test_urgency_flag_prompts_review_without_asserting_emergency_or_credit(self):
        s=self.session('renal-flank-pain');g=guide.state(s)
        decisions=[t for t in g['tasks']if t['kind']=='decision']
        self.assertTrue(decisions)
        self.assertFalse(decisions[0]['question'])
        self.assertIn('does not by itself',decisions[0]['decision_note'])
        before=s.ledger.to_json()
        guide.navigate(s,{'step':decisions[0]['id'],'action':'defer'})
        self.assertEqual(s.ledger.to_json(),before)
        self.assertFalse(s.ledger.by_kind(evidence.COUNSELING))

    def test_draft_button_only_populates_unsent_input(self):
        node=Path(os.environ.get('PCM_NODE_BINARY') or shutil.which('node') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'))
        if not node.exists():self.skipTest('Node runtime unavailable')
        js=(Path(engine.__file__).resolve().parents[1]/'web/learning.js').read_text()
        function=js[js.index('  function draftQuestion('):js.index('  const mentalStep=')]
        program="const assert=require('assert');let events=0,focused=false;const input={value:'',dispatchEvent(){events++},focus(){focused=true}};const document={getElementById(){return input}};const window={confirm(){return false}};const Event=function(){};global.fetch=()=>{throw Error('Draft must never call API')};"+function+"draftQuestion('What brings you in today?',null);assert.equal(input.value,'What brings you in today?');assert.equal(events,1);assert(focused);input.value='My existing unsent draft';draftQuestion('Replacement',null);assert.equal(input.value,'My existing unsent draft');"
        result=subprocess.run([str(node),'-e',program],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
