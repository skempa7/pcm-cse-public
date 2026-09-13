"""Chosen coach stage must change the suggestion without creating evidence."""
import os
import tempfile
import unittest
from pcmcse import cases, config, db, engine, guide, learning


class CoachStageSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cse-stage-selection-')
        self.old = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmp.name, 'attempts.sqlite')
        db.init()
        settings = config.load_settings()
        preset = config.preset_for_learning_mode('coached')
        settings.update(learning_mode='coached', simulation_runtime='interactive', preset=preset)
        case = cases.resolve('cardio-febrile-cough', 'base')
        sid = db.create_session('cardio-febrile-cough', preset, 'type', False, settings, case=case)
        self.s = engine.load(sid)
        self.s.start_encounter()

    def tearDown(self):
        db.DB_PATH = self.old
        self.tmp.cleanup()

    def select(self, stage):
        learning.record(self.s.id, 'stage', {'step': stage, 'after_seq': len(self.s.ledger.events)})
        return learning.state(self.s)

    def test_visible_stage_and_move_agree_without_evidence_credit(self):
        before = self.s.ledger.to_json()
        self.assertEqual(guide.next_action(self.s)['group'], 'connect')
        data = self.select('pattern')
        self.assertEqual(data['selected'], 'pattern')
        self.assertEqual(data['next_action']['group'], 'pattern')
        self.assertRegex(data['next_action']['question'], r'(?i)when|how long')
        data = self.select('examine')
        self.assertEqual(data['selected'], 'examine')
        self.assertEqual(data['next_action']['kind'], 'exam')
        self.assertEqual(self.s.ledger.to_json(), before)
        self.assertEqual(learning.summary(self.s)['hints_used'], 0)
        self.assertNotIn('case_guide', data)

    def test_new_evidence_recommends_normally_after_explicit_choice(self):
        self.select('examine')
        self.s.student_turn('When did the cough start?')
        self.s = engine.load(self.s.id)
        data = learning.state(self.s)
        self.assertEqual(data['selected'], learning.inferred_step(self.s))
        self.assertNotEqual(data['next_action']['kind'], 'exam')
        self.assertEqual(data['next_action']['group'], 'pattern')


if __name__ == '__main__':
    unittest.main()
