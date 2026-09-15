"""Exact clock, evidence and idempotency tests for examination animation controls."""
import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pcmcse import config, db, engine, evidence, physexam, teaching

class ExamAnimationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=db.DB_PATH
        db.DB_PATH=os.path.join(self.tmp.name,'test.sqlite');db.init()
        self.clock=2000000000000
        self.mock=patch.object(db,'now_ms',lambda:self.clock);self.mock.start()
    def tearDown(self):
        self.mock.stop();db.DB_PATH=self.old;self.tmp.cleanup()
    def session(self,mode='rehearsal'):
        settings=copy.deepcopy(config.DEFAULT_SETTINGS)
        settings.update(simulation_runtime='interactive',learning_mode=mode)
        preset=config.preset_for_learning_mode(mode)
        sid=db.create_session('cardio-febrile-cough',preset,'type',mode=='guided',settings)
        s=engine.load(sid);s.start_encounter();return s
    def begin(self,s,mid='jvd',components=None):
        result=s.perform_maneuver(mid,components or [])
        self.assertEqual(result['kind'],'exam_started')
        return json.loads(s.row['pending_exam_json'])
    def findings(self,s):
        return [e for e in s.ledger.events if e['kind']==evidence.EXAM_FINDING]
    def test_immediate_and_partial_skips_charge_exact_unwatched_time_once(self):
        for elapsed in (0,5000,5371,14999):
            with self.subTest(elapsed=elapsed):
                s=self.session();p=self.begin(s);start=s.row['phase_started_at'];end=s.row['phase_ends_at']
                self.clock+=elapsed
                result=s.control_examination(p['id'],'skip')
                self.assertEqual(result['charged_ms'],15000-elapsed)
                self.assertEqual(s.elapsed_ms(),15000)
                self.assertEqual(s.row['phase_ends_at'],end-(15000-elapsed))
                self.assertEqual(s.remaining_ms(),840000-15000)
                self.assertEqual(len(self.findings(s)),1)
                snapshot=copy.deepcopy(db.get_session(s.id))
                again=s.control_examination(p['id'],'skip')
                self.assertEqual(again['charged_ms'],0)
                self.assertEqual(db.get_session(s.id),snapshot)
                s=engine.load(s.id);self.assertEqual(s.elapsed_ms(),15000)
                self.assertEqual(len(self.findings(s)),1)
    def test_watch_to_end_has_no_additional_clock_charge(self):
        s=self.session();p=self.begin(s);end=s.row['phase_ends_at']
        self.assertEqual(self.findings(s),[])
        self.clock=p['due_at']-1;s=engine.load(s.id);self.assertEqual(self.findings(s),[])
        self.clock+=1;s=engine.load(s.id)
        self.assertEqual(len(self.findings(s)),1)
        self.assertEqual(s.row['phase_ends_at'],end)
        self.assertEqual(s.control_examination(p['id'],'skip')['charged_ms'],0)
    def test_cancel_and_stale_skip_never_complete_a_different_examination(self):
        s=self.session();p=self.begin(s);self.clock+=2000
        s.control_examination(p['id'],'cancel');self.assertEqual(self.findings(s),[])
        p2=self.begin(s);end=s.row['phase_ends_at']
        s.control_examination(p['id'],'skip')
        self.assertEqual(json.loads(s.row['pending_exam_json'])['id'],p2['id'])
        self.assertEqual(s.row['phase_ends_at'],end)
        self.assertEqual(self.findings(s),[])
    def test_near_deadline_skip_cannot_award_ineligible_result(self):
        for remaining in (5000,15000,15001):
            with self.subTest(remaining=remaining):
                s=self.session();self.clock=s.row['phase_ends_at']-remaining;p=self.begin(s)
                r=s.control_examination(p['id'],'skip')
                self.assertEqual(r['charged_ms'],min(15000,remaining))
                self.assertEqual(len(self.findings(s)),int(remaining>=15000))
                self.assertEqual(s.row['phase'],'encounter' if remaining>15000 else 'note')
                self.assertGreaterEqual(s.remaining_ms(),0)
    def test_expiry_while_watching_and_leaving_cancel(self):
        s=self.session();self.clock=s.row['phase_ends_at']-1000;p=self.begin(s)
        self.clock+=1000;s=engine.load(s.id)
        self.assertEqual(s.row['phase'],'note');self.assertEqual(self.findings(s),[])
        self.assertEqual(s.control_examination(p['id'],'skip')['charged_ms'],0)
        s=self.session();self.begin(s);self.clock+=1000;s.end_encounter_now()
        self.assertEqual(self.findings(s),[])
    def test_untimed_skip_has_no_hidden_countdown_or_elapsed_penalty(self):
        for mode in ('guided','coached'):
            s=self.session(mode);p=self.begin(s);self.clock+=2345
            r=s.control_examination(p['id'],'skip')
            self.assertEqual(r['charged_ms'],0);self.assertIsNone(s.row['phase_ends_at'])
            self.assertEqual(s.elapsed_ms(),2345);self.assertEqual(len(self.findings(s)),1)
    def test_legacy_pending_gets_a_stable_control_identifier(self):
        s=self.session();p=self.begin(s);del p['id']
        s.row['pending_exam_json']=json.dumps(p);s.save()
        first=engine.state_payload(s)['pending_exam']['id']
        s=engine.load(s.id)
        self.assertEqual(engine.state_payload(s)['pending_exam']['id'],first)
        self.assertEqual(s.control_examination(first,'skip')['charged_ms'],15000)
        self.assertEqual(len(self.findings(s)),1)
    def test_partial_seated_slr_keeps_selected_side_and_position(self):
        p=physexam.demonstration('msk_slr',['seated','left'])
        self.assertEqual(p['duration_s'],10)
        self.assertEqual(len(p['steps']),1)
        self.assertTrue(p['steps'][0]['mirror'])
        self.assertEqual(p['steps'][0]['motion'],'slr-seated')
    def test_written_example_estimate_uses_current_plans_without_rewriting_evidence(self):
        path=teaching.ROOT/'lessons'/'cardio-presyncope.json'
        original=json.loads(path.read_text())['walkthroughs'][0]
        result=teaching.read('cardio-presyncope',original['variant_id'])
        self.assertEqual(result['ledger'],original['ledger'])
        self.assertEqual(result['timeline'],original['timeline'])
        self.assertEqual(result['estimated_encounter_s'],original['estimated_encounter_s'])
        delta=0
        for item in original['timeline']:
            if not item.get('maneuver_id'):continue
            event=next(e for e in original['ledger'] if e['seq'] in item['event_ids'] and e['kind']==evidence.EXAM_ACTION)
            plan=physexam.demonstration(item['maneuver_id'],event['meta']['components'])
            if plan:delta+=plan['duration_s']-item['duration_s']
        self.assertEqual(result['current_demonstration_estimate_s'],original['estimated_encounter_s']+delta)
        self.assertGreater(result['current_demonstration_estimate_s'],840)

    def test_every_selectable_action_naturally_completes_once(self):
        plans=[a for g in physexam.catalog_for_ui() for m in g['maneuvers'] for a in m['actions']]
        s=self.session('coached')
        for plan in plans:
            with self.subTest(action=plan['key']):
                before=len([x for x in s.ledger.events if x['kind']=='exam_action' and x.get('meta',{}).get('status')=='completed'])
                p=self.begin(s,plan['maneuver_id'],plan['components'])
                self.clock=p['due_at']-1;s=engine.load(s.id)
                self.assertTrue(s.row['pending_exam_json'])
                self.clock+=1;s=engine.load(s.id)
                self.assertFalse(s.row['pending_exam_json'])
                actions=[x for x in s.ledger.events if x['kind']=='exam_action' and x.get('meta',{}).get('status')=='completed']
                self.assertEqual(len(actions),before+1)
                self.assertEqual(actions[-1]['meta']['status'],'completed')
                self.assertEqual(actions[-1]['meta']['duration_s'],plan['duration_s'])
                count=len(s.ledger.events);s.control_examination(p['id'],'skip')
                self.assertEqual(len(s.ledger.events),count)

    def test_every_selectable_action_owns_its_animation_duration(self):
        plans=[a for g in physexam.catalog_for_ui() for m in g['maneuvers'] for a in m['actions']]
        self.assertEqual(len(plans),85)
        s=self.session('coached')
        for plan in plans:
            with self.subTest(action=plan['key']):
                self.assertEqual(sum(st['seconds'] for st in plan['steps']),plan['duration_s'])
                self.assertTrue(all(st['caption'] and st['view'] and st['action'] for st in plan['steps']))
                p=self.begin(s,plan['maneuver_id'],plan['components'])
                self.assertEqual(p['duration_s'],plan['duration_s'])
                self.assertEqual(p['due_at']-p['started_at'],plan['duration_s']*1000)
                self.assertEqual(engine.state_payload(s)['pending_exam']['demonstration']['key'],plan['key'])
                self.assertEqual(s.perform_maneuver('jvd',[])['kind'],'exam_busy')
                s.control_examination(p['id'],'cancel')
        self.assertEqual(self.findings(s),[])

if __name__=='__main__':unittest.main()
