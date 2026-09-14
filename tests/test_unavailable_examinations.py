"""Unavailable examinations stay honest; authored JVD findings retain their evidence."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pcmcse import audit, cases, checklist, config, db, engine, evidence, note, physexam, record


class UnavailableExaminationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cse-unavailable-exam-')
        self.old_db = db.DB_PATH
        db.DB_PATH = str(Path(self.temp.name) / 'attempts.sqlite')
        db.init()
        self.now = 2000000000000
        self.clock = patch.object(db, 'now_ms', lambda: self.now)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        db.DB_PATH = self.old_db
        self.temp.cleanup()

    def session(self, cid, variant='base', mode='coached'):
        case = cases.resolve(cid, variant)
        settings = copy.deepcopy(config.DEFAULT_SETTINGS)
        preset = config.preset_for_learning_mode(mode)
        settings.update(learning_mode=mode, simulation_runtime='interactive', preset=preset)
        sid = db.create_session(cid, preset, 'type', mode == 'guided', settings, case=case)
        session = engine.load(sid)
        session.start_encounter()
        return session

    def complete(self, session):
        started = session.perform_maneuver('jvd', [], 'Assess jugular venous distention')
        self.assertEqual(started['kind'], 'exam_started')
        self.assertGreater(started['duration_s'], 0)
        self.now = started['due_at']
        result = session.finish_pending()
        return engine.load(session.id), result

    def test_missing_jvd_records_attempt_without_findings_or_credit_after_reload(self):
        cid = 'cardio-palpitations'
        variants = ['base'] + [v['id'] for v in cases.get(cid)['variants']]
        for variant in variants:
            with self.subTest(variant=variant):
                session = self.session(cid, variant)
                before_record = record.summarize(session.case, session.ledger.events)
                before_score = checklist.score(session.ledger, session.case)
                before_concepts = session.ledger.released_concepts()
                for _ in range(2):
                    session, result = self.complete(session)
                    self.assertEqual(result['kind'], 'not_simulated')
                    self.assertIn('attempt was recorded', result['text'])
                    self.assertNotIn('Nothing was recorded', result['text'])
                    self.assertEqual(session.ledger.by_kind(evidence.EXAM_FINDING), [])
                    self.assertNotIn('jvd', session.ledger.performed_maneuvers())
                    self.assertEqual(session.ledger.released_concepts(), before_concepts)
                    self.assertEqual(record.summarize(session.case, session.ledger.events), before_record)
                    self.assertEqual(checklist.score(session.ledger, session.case), before_score)
                    payload = engine.state_payload(session)
                    self.assertEqual(payload['examination_activity'][-1]['meta']['status'], 'not_simulated')
                    self.assertEqual(payload['examination_activity'][-1]['meta']['maneuver_id'], 'jvd')
                    self.assertEqual(payload['exam_catalog'], physexam.catalog_for_ui())
                claimed_normal = note.parse({'S': '', 'O': 'Heart: No jugular venous distention.', 'A': [], 'P': []})
                verdicts = [item['verdict'] for item in audit.audit_note(claimed_normal, session.ledger, session.case)['claims']]
                self.assertTrue(verdicts)
                self.assertNotIn('supported', verdicts)

    def test_existing_normal_and_abnormal_jvd_release_only_authored_findings(self):
        for cid in ('cardio-chest-pressure', 'cardio-orthopnea-edema'):
            variants = ['base'] + [v['id'] for v in cases.get(cid)['variants']]
            for variant in variants:
                with self.subTest(case=cid, variant=variant):
                    session = self.session(cid, variant)
                    expected = session.case['exam_findings']['jvd']
                    self.assertEqual(session.ledger.by_kind(evidence.EXAM_FINDING), [])
                    session, result = self.complete(session)
                    self.assertEqual(result['kind'], 'finding')
                    self.assertEqual(result['released'], [f['id'] for f in expected])
                    self.assertEqual(result['text'], ' '.join(f['text'] for f in expected))
                    events = session.ledger.by_kind(evidence.EXAM_FINDING)
                    self.assertEqual(len(events), 1)
                    self.assertEqual(events[0]['meta']['scopes'], ['heart.jvd'])
                    self.assertIn('jvd', session.ledger.performed_maneuvers())
                    rows = checklist.score(session.ledger, session.case)['physical']
                    for finding in expected:
                        self.assertEqual(next(r for r in rows if r['id'] == finding['checklist'])['status'], 'performed')
                    self.assertEqual(engine.state_payload(session)['examination_activity'][-1]['meta']['status'], 'completed')
                    self.assertIn(result['text'], json.dumps(record.summarize(session.case, session.ledger.events)))

    def test_unavailable_status_preserves_full_catalog_and_mode_timing(self):
        for mode, duration in (('guided', 4), ('coached', 15), ('independent', 15), ('rehearsal', 15)):
            with self.subTest(mode=mode):
                session = self.session('cardio-palpitations', mode=mode)
                before = engine.state_payload(session)
                session, result = self.complete(session)
                after = engine.state_payload(session)
                self.assertEqual(result['kind'], 'not_simulated')
                self.assertEqual(after['examination_activity'][-1]['meta']['duration_s'], duration)
                self.assertEqual(before['exam_catalog'], after['exam_catalog'])
                self.assertEqual(after['learning_mode'], mode)
                self.assertEqual(after['phase'], 'encounter')
                self.assertIsNone(after['pending_exam'])
                self.assertEqual(after['examination_activity'][-1]['meta']['status'], 'not_simulated')


if __name__ == '__main__':
    unittest.main()
