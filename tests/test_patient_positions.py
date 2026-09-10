"""Four-position regression checks using disposable attempts and a controlled clock."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pcmcse import cases, config, db, engine, evidence


class PatientPositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pcm-posture-test-')
        self.old_db = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name, 'attempts.sqlite')
        db.init()
        self.now = 1789000000000
        self.clock = patch('pcmcse.db.now_ms', side_effect=lambda: self.now)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        db.DB_PATH = self.old_db
        self.temp.cleanup()

    def session(self, cid='renal-flank-pain', variant='base', mode='independent', start=True):
        case = cases.resolve(cid, variant)
        settings = config.load_settings()
        settings.update(learning_mode=mode, simulation_runtime='interactive')
        sid = db.create_session(cid, 'course' if mode == 'rehearsal' else 'practice',
                                'type', mode in ('coached', 'guided'), settings, case=case)
        s = engine.load(sid)
        if start:
            s.start_encounter()
        return s

    def route(self, sid, position, request_id='position-test'):
        """Exercise the real route without HTTP, providers, or the user's DB."""
        root = Path(engine.__file__).resolve().parents[1]
        if (root / 'offline_routes.py').exists():
            import offline_routes
            handler_type = offline_routes.Handler
        else:
            import server
            handler_type = server.Handler
        h = object.__new__(handler_type)
        h.path = '/api/session/' + sid + '/room'
        h.headers = {'Host': 'localhost'}
        body = {'sessionId': sid, 'requestId': request_id, 'renderer': 'babylon',
                'action': 'position', 'position': position}
        h._body = lambda: body
        h._json = lambda payload, status=200: (status, payload)
        return h.do_POST()

    def test_every_transition_persists_without_finding_or_timer_change(self):
        # Exercise all 16 pairs, including same-position requests, with real DB reloads.
        for start in engine.PATIENT_POSITIONS:
            for target in engine.PATIENT_POSITIONS:
                with self.subTest(start=start, target=target):
                    s = self.session()
                    s.position_patient(start)
                    original_concepts = s.ledger.released_concepts()
                    original_facts = s.ledger.released_facts()
                    deadline = s.row['phase_ends_at']
                    started = s.row['phase_started_at']
                    self.now += 1300
                    s.bridge_context = {'request_id': 'step-' + start + '-' + target,
                                        'after_seq': len(s.ledger.events), 'renderer': 'babylon'}
                    s.position_patient(target)
                    s = engine.load(s.id)
                    self.assertEqual(engine.state_payload(s)['patient_posture'], target)
                    self.assertEqual(s.row['phase_ends_at'], deadline)
                    self.assertEqual(s.row['phase_started_at'], started)
                    self.assertEqual(s.remaining_ms(), deadline - self.now)
                    self.assertFalse(s.ledger.by_kind(evidence.EXAM_FINDING))
                    self.assertEqual(s.ledger.released_concepts(), original_concepts)
                    self.assertEqual(s.ledger.released_facts(), original_facts)
                    action = s.ledger.events[-1]
                    self.assertEqual(action['kind'], evidence.COURTESY)
                    self.assertEqual(action['meta']['previous_position'], start)
                    self.assertEqual(action['meta']['position'], target)
                    self.assertTrue(action['meta']['no_finding'])
                    self.assertEqual(action['meta']['source'], 'babylon')
                    self.assertEqual(action['meta']['request_id'], 'step-' + start + '-' + target)

    def test_all_cases_and_variants_can_use_new_positions_without_new_findings(self):
        count = 0
        for base in cases.all_cases().values():
            for variant in ['base'] + [v['id'] for v in base.get('variants', [])]:
                with self.subTest(case=base['id'], variant=variant):
                    s = self.session(base['id'], variant)
                    s.position_patient('standing')
                    self.assertEqual(engine.load(s.id).pstate['posture'], 'standing')
                    s.position_patient('seated')
                    events = s.position_patient('prone')
                    if base['id'] == 'cardio-orthopnea-edema':
                        self.assertEqual(engine.load(s.id).pstate['posture'], 'seated')
                        self.assertIn('Lying flat', events[0]['text'])
                    else:
                        self.assertEqual(engine.load(s.id).pstate['posture'], 'prone')
                        self.assertEqual(events, [])
                    self.assertFalse(s.ledger.by_kind(evidence.EXAM_FINDING))
                    count += 1
        self.assertEqual(count, 72)

    def test_prone_uses_existing_flat_refusal_and_exact_authored_fact_only(self):
        s = self.session('cardio-orthopnea-edema')
        spec = copy.deepcopy(s.case['patient']['position_rules']['supine'])
        reply = s.position_patient('prone')[0]
        s = engine.load(s.id)
        self.assertEqual(reply['text'], spec['reply'])
        self.assertEqual(s.pstate.get('posture', 'seated'), 'seated')
        action = s.ledger.by_kind(evidence.COURTESY)[-1]
        self.assertFalse(action['meta']['accepted'])
        self.assertEqual(action['meta']['position_rule'], 'authored_flat_position_refusal')
        event = s.ledger.by_kind(evidence.PATIENT)[-1]
        control = self.session('cardio-orthopnea-edema')
        control.position_patient('supine')
        control_event = control.ledger.by_kind(evidence.PATIENT)[-1]
        # Preserve the existing disclosure validator, including its conservative
        # handling of this authored paraphrase; a new pose must not broaden credit.
        self.assertEqual(event['meta'].get('facts_released'),
                         control_event['meta'].get('facts_released'))
        self.assertEqual(event['meta'].get('concepts'), control_event['meta'].get('concepts'))
        self.assertNotIn('symptom_orthopnea', event['meta'].get('facts_released', []))
        self.assertFalse(s.ledger.by_kind(evidence.EXAM_FINDING))
        self.assertEqual(s.case['patient']['position_rules']['supine'], spec)

    def test_explicit_prone_rule_has_priority_and_unrelated_supine_refusal_does_not_infer(self):
        s = self.session('cardio-orthopnea-edema')
        s.case['patient']['position_rules']['prone'] = {'allowed': True}
        s.position_patient('prone')
        self.assertEqual(s.pstate['posture'], 'prone')
        s = self.session()
        s.case['patient']['position_rules'] = {'supine': {'allowed': False}}
        s.position_patient('prone')
        self.assertEqual(s.pstate['posture'], 'prone')

    def test_invalid_values_are_rejected_without_mutation(self):
        s = self.session()
        for value in [None, '', 'sideways', 'Standing', [], {}, 1, True]:
            before = copy.deepcopy(db.get_session(s.id))
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'Unknown position'):
                    s.position_patient(value)
                self.assertEqual(db.get_session(s.id), before)
                status, payload = self.route(s.id, value, 'invalid-' + repr(value))
                self.assertEqual(status, 400)
                self.assertEqual(payload['error'], 'Unknown position')
                self.assertEqual(db.get_session(s.id), before)

    def test_route_new_positions_retries_once_and_preserves_assistance(self):
        for mode in ('guided', 'coached', 'independent', 'rehearsal'):
            s = self.session(mode=mode)
            old_assisted = s.row['assisted']
            deadline = s.row['phase_ends_at']
            for pos in ('standing', 'prone'):
                status, payload = self.route(s.id, pos, 'route-' + pos)
                self.assertEqual(status, 200)
                self.assertEqual(payload['state']['patient_posture'], pos)
                before = engine.load(s.id).ledger.to_json()
                status, duplicate = self.route(s.id, pos, 'route-' + pos)
                self.assertEqual(status, 200)
                self.assertTrue(duplicate['duplicate'])
                self.assertEqual(engine.load(s.id).ledger.to_json(), before)
                self.assertEqual(engine.load(s.id).row['assisted'], old_assisted)
                self.assertEqual(engine.load(s.id).row['phase_ends_at'], deadline)

    def test_pending_exam_blocks_positions_and_complete_exam_still_releases_specific_result(self):
        s = self.session()
        s.position_patient('prone')
        action = s.perform_maneuver('general_inspect', [])
        self.assertEqual(action['kind'], 'exam_started')
        with self.assertRaisesRegex(ValueError, 'Wait for the examination'):
            s.position_patient('standing')
        self.assertEqual(self.route(s.id, 'standing')[0], 409)
        self.assertFalse(engine.load(s.id).ledger.by_kind(evidence.EXAM_FINDING))
        self.now = action['due_at']
        s = engine.load(s.id)
        self.assertTrue(s.ledger.by_kind(evidence.EXAM_FINDING))
        self.assertEqual(s.pstate['posture'], 'prone')
        s.position_patient('standing')
        self.assertEqual(engine.load(s.id).pstate['posture'], 'standing')

    def test_actions_lock_before_start_at_deadline_and_after_note_transition(self):
        s = self.session(start=False)
        self.assertEqual(self.route(s.id, 'standing')[0], 409)
        with self.assertRaisesRegex(ValueError, 'locked'):
            s.position_patient('standing')
        s.start_encounter()
        deadline = s.row['phase_ends_at']
        self.now = deadline
        with self.assertRaisesRegex(ValueError, 'locked'):
            s.position_patient('prone')
        s = engine.load(s.id)
        self.assertEqual(s.row['phase'], 'organize')
        self.assertEqual(s.row['phase_ends_at'], deadline + 120000)
        self.assertFalse(s.ledger.by_kind(evidence.COURTESY))
        self.assertEqual(self.route(s.id, 'prone')[0], 409)
        self.now = deadline + 120000
        s = engine.load(s.id)
        self.assertEqual(s.row['phase'], 'note')
        self.assertEqual(s.row['phase_ends_at'], deadline + 120000 + 540000)
        self.assertEqual(self.route(s.id, 'standing')[0], 409)

    def test_retry_reconstructs_new_posture_and_keeps_parent_intact(self):
        for posture in ('standing', 'prone'):
            s = self.session(mode='coached')
            self.now += 3700
            s.position_patient(posture)
            at_seq = s.ledger.events[-1]['seq']
            s.position_patient('seated')
            before = copy.deepcopy(db.get_session(s.id))
            branch = engine.branch_from(s.id, at_seq)
            self.assertEqual(branch.pstate['posture'], posture)
            self.assertEqual(db.get_session(s.id), before)


if __name__ == '__main__':
    unittest.main()
