"""New mode timing contracts plus saved-attempt preservation; disposable SQLite only."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pcmcse import cases, config, db, engine, physexam


class LearningTimingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pcm-new-learning-timing-')
        self.old_db = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name, 'attempts.sqlite')
        db.init()
        self.clock = 2000000000000
        self.timer = patch.object(db, 'now_ms', lambda: self.clock)
        self.timer.start()

    def tearDown(self):
        self.timer.stop()
        db.DB_PATH = self.old_db
        self.temp.cleanup()

    def create(self, mode, preset=None, interactive=True):
        preset = preset or config.preset_for_learning_mode(mode)
        settings = copy.deepcopy(config.DEFAULT_SETTINGS)
        settings.update(preset=preset, learning_mode=mode)
        if interactive:
            settings['simulation_runtime'] = 'interactive'
        sid = db.create_session('renal-flank-pain', preset, 'type', mode == 'guided', settings)
        return engine.load(sid)

    def route_create(self, mode, requested='practice'):
        root = Path(engine.__file__).resolve().parents[1]
        if (root / 'offline_routes.py').exists():
            from offline_routes import Handler
        else:
            from server import Handler
        handler = object.__new__(Handler)
        handler.path = '/api/session'
        handler.headers = {'Host': 'localhost'}
        handler._body = lambda: {'case_id': 'renal-flank-pain', 'learning_mode': mode, 'preset': requested}
        handler._json = lambda payload, status=200: (status, payload)
        return handler.do_POST()

    def test_new_route_uses_each_mode_contract_even_with_old_or_wrong_requested_preset(self):
        for mode, preset in config.MODE_PRESETS.items():
            with self.subTest(mode=mode):
                status, state = self.route_create(mode, 'practice' if mode != 'coached' else 'course')
                self.assertEqual(status, 200)
                self.assertEqual(state['preset']['key'], preset)
                self.assertEqual(state['phase'], 'briefing')
                self.assertIsNone(state['phase_ends_at'])
                saved = db.get_session(state['id'])
                self.assertEqual(json.loads(saved['settings_json'])['preset'], preset)

    def test_guided_and_coached_are_untimed_through_reload_and_documentation(self):
        for mode in ('guided', 'coached'):
            with self.subTest(mode=mode):
                s = self.create(mode)
                s.start_encounter()
                self.assertIsNone(s.row['phase_ends_at'])
                self.assertIsNone(s.phase_duration_s())
                self.clock += 24 * 3600 * 1000
                s = engine.load(s.id)
                self.assertEqual(s.row['phase'], 'encounter')
                s.end_encounter_now()
                self.assertEqual(s.row['phase'], 'note')
                self.assertIsNone(s.row['phase_ends_at'])
                self.assertTrue(s.save_note({'S': 'A saved draft', 'O': '', 'A': [], 'P': []}))
                self.clock += 24 * 3600 * 1000
                s = engine.load(s.id)
                self.assertEqual(s.row['phase'], 'note')
                self.assertEqual(s.original_note()['S'], 'A saved draft')
                self.assertIsNone(s.timing_report()['note_allowed_s'])
                self.assertIsNone(s.timing_report()['encounter_allowed_s'])
                s.submit()
                original = db.get_session(s.id)['original_note_json']
                self.assertFalse(s.save_note({'S': 'late overwrite'}))
                self.assertEqual(db.get_session(s.id)['original_note_json'], original)

    def test_coached_exam_actions_still_take_full_time_and_cannot_overlap(self):
        s = self.create('coached')
        s.start_encounter()
        self.clock += 24 * 3600 * 1000  # Well past the former 14-minute cutoff.
        s = engine.load(s.id)
        components = list(physexam.CATALOG_BY_ID['general_inspect']['components'])
        started = s.perform_maneuver('general_inspect', components)
        self.assertEqual(started['kind'], 'exam_started')
        expected = physexam.action_time(physexam.CATALOG_BY_ID['general_inspect'], components, 1.0)
        self.assertEqual(started['duration_s'], expected)
        self.assertEqual(s.perform_maneuver('general_inspect', components)['kind'], 'exam_busy')
        self.clock = started['due_at']
        s = engine.load(s.id)
        self.assertEqual(s.row['phase'], 'encounter')
        self.assertFalse(s.row.get('pending_exam_json'))
        self.assertTrue(any(e.get('meta', {}).get('maneuver_id') == 'general_inspect'
                            and e.get('meta', {}).get('status') != 'interrupted' for e in s.ledger.events))

    def test_untimed_legacy_immediate_action_path_has_no_hidden_14_minute_cutoff(self):
        s = self.create('coached', interactive=False)
        s.start_encounter()
        self.clock += 3600 * 1000
        s = engine.load(s.id)
        result = s.perform_maneuver('general_inspect', ['appearance'])
        self.assertNotEqual(result['kind'], 'exam_interrupted')

    def test_independent_has_30_5_20_and_no_time_refund_on_reload(self):
        s = self.create('independent')
        s.start_encounter()
        started = self.clock
        self.assertEqual(s.row['phase_ends_at'], started + 1800000)
        self.clock = started + 1800000
        s = engine.load(s.id)
        self.assertEqual(s.row['phase'], 'organize')
        self.assertEqual(s.row['phase_started_at'], self.clock)
        self.assertEqual(s.row['phase_ends_at'], started + 2100000)
        self.clock = started + 2100000 + 100000
        s = engine.load(s.id)
        self.assertEqual(s.row['phase'], 'note')
        self.assertEqual(s.row['phase_started_at'], started + 2100000)
        self.assertEqual(s.row['phase_ends_at'], started + 3300000)
        self.assertEqual(s.remaining_ms(), 1100000)
        s.save_note({'S': 'Saved before deadline'})
        self.clock = started + 3600000
        s = engine.load(s.id)
        self.assertEqual(s.row['phase'], 'submitted')
        self.assertEqual(s.row['submitted_at'], started + 3300000)
        self.assertEqual(s.original_note()['S'], 'Saved before deadline')

    def test_rehearsal_uses_exact_course_timing_and_no_organization(self):
        s = self.create('rehearsal')
        s.start_encounter()
        started = self.clock
        self.assertEqual(s.row['phase_ends_at'], started + 840000)
        self.clock = started + 840000
        s = engine.load(s.id)
        self.assertEqual(s.row['phase'], 'note')
        self.assertEqual(s.row['phase_ends_at'], started + 1380000)
        self.assertEqual(s.phase_duration_s(), 540)
        self.assertFalse(s.timing_report()['modified'])

    def test_legacy_attempts_keep_their_original_deadlines_presets_notes_and_ledgers(self):
        for mode in ('coached', 'independent'):
            for preset in ('practice', 'course'):
                with self.subTest(mode=mode, preset=preset):
                    s = self.create(mode, preset=preset)
                    s.start_encounter()
                    s.save_scratch('Preserve this saved work')
                    before = copy.deepcopy(db.get_session(s.id))
                    reloaded = engine.load(s.id)
                    self.assertEqual(db.get_session(s.id), before)
                    self.assertEqual(reloaded.row['phase_ends_at'] - reloaded.row['phase_started_at'], 840000)
                    reloaded.end_encounter_now()
                    if preset == 'practice':
                        self.assertEqual(reloaded.row['phase'], 'organize')
                        self.assertEqual(reloaded.row['phase_ends_at'] - self.clock, 120000)
                        reloaded.skip_organize()
                    self.assertEqual(reloaded.row['phase_ends_at'] - self.clock, 540000)
                    self.assertEqual(reloaded.row['preset'], preset)

    def test_historical_guided_organization_retains_its_original_120_seconds(self):
        s = self.create('guided', preset='practice')
        s.start_encounter()
        self.assertIsNone(s.row['phase_ends_at'])
        s.end_encounter_now()
        self.assertEqual(s.row['phase'], 'organize')
        self.assertEqual(s.row['phase_ends_at'], self.clock + 120000)
        self.assertEqual(s.phase_duration_s(), 120)

    def test_new_retry_is_untimed_and_does_not_retime_parent(self):
        parent = self.create('independent')
        parent.start_encounter()
        parent.student_turn('What brings you in today?')
        before = copy.deepcopy(db.get_session(parent.id))
        seq = parent.ledger.events[-1]['seq']
        branch = engine.branch_from(parent.id, seq)
        self.assertEqual(branch.row['preset'], 'coached_untimed')
        self.assertIsNone(branch.row['phase_ends_at'])
        self.assertEqual(db.get_session(parent.id), before)
        self.clock += 3600000
        self.assertEqual(engine.load(branch.id).row['phase'], 'encounter')

    def test_preset_manifest_describes_untimed_without_zero_minute_countdown(self):
        for mode in ('guided', 'coached'):
            settings = dict(config.DEFAULT_SETTINGS, preset=config.preset_for_learning_mode(mode))
            detail = next(x['detail'] for x in config.assumption_manifest(settings) if x['topic'] == 'Timing preset')
            self.assertIn('Untimed', detail)
            self.assertNotIn('Encounter 0:00', detail)


if __name__ == '__main__':
    unittest.main(verbosity=2)
