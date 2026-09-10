"""History reset tests: disposable data, atomic scope, and explicit unfinished-work consent."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from pcmcse import cases, config, db, engine, learning, teaching


class ProgressResetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pcm-progress-reset-')
        self.old_db = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name, 'attempts.sqlite')
        db.init()
        self.cid = 'renal-flank-pain'
        self.other = next(cid for cid in cases.all_cases() if cid != self.cid)
        self.variant = cases.get(self.cid)['variants'][0]['id']
        teaching.progress()
        with db.connect() as c:
            c.execute('CREATE TABLE patient_deliveries (id TEXT PRIMARY KEY, session_id TEXT, status TEXT)')
            # A cost record is never study progress, even if legacy data co-locates it.
            c.execute('CREATE TABLE ai_usage (id TEXT PRIMARY KEY, session_id TEXT, charged_nano INTEGER)')
            c.execute("INSERT INTO ai_usage VALUES ('do-not-reset', 'billing', 123456)")

    def tearDown(self):
        db.DB_PATH = self.old_db
        self.temp.cleanup()

    def seed(self, cid=None, variant='base', phase='submitted', parent=''):
        cid = cid or self.cid
        settings = config.load_settings()
        settings.update(learning_mode='coached', simulation_runtime='interactive')
        case = cases.resolve(cid, variant)
        sid = db.create_session(cid, 'practice', 'type', True, settings, case=case)
        db.update_session(sid, phase=phase, parent_session_id=parent,
                          patient_state=json.dumps({'posture': 'prone'}),
                          scratch='preserve or explicitly reset this work',
                          note_json='{"S":"a saved note"}',
                          original_note_json='{"S":"an original submission"}' if phase == 'submitted' else '',
                          results_json=json.dumps({'feedback': {'missed_questions': ['example']}}) if phase == 'submitted' else None)
        with db.connect() as c:
            c.execute('INSERT INTO revisions VALUES (?,?,?,?,?,?)',
                      (db.new_id(), sid, db.now_ms(), 'revision', '{}', '{}'))
            c.execute('INSERT INTO learning_events VALUES (?,?,?,?,?)',
                      (db.new_id(), sid, db.now_ms(), 'repair', '{"skill":"history-sequencing"}'))
            c.execute('INSERT INTO bridge_requests VALUES (?,?,?)', (sid, 'old-request', '{}'))
            c.execute('INSERT INTO patient_deliveries VALUES (?,?,?)', (db.new_id(), sid, 'delivered'))
            c.execute('INSERT OR REPLACE INTO study_progress VALUES (?,?,?,?)', (cid, variant, db.now_ms(), '["saved recall"]'))
        return sid

    def snapshot(self):
        with db.connect() as c:
            return {t: [tuple(r) for r in c.execute('SELECT * FROM ' + t + ' ORDER BY rowid')]
                    for t in ('sessions', 'revisions', 'learning_events', 'bridge_requests',
                              'patient_deliveries', 'study_progress', 'ai_usage')}

    def route(self, body, path='/api/progress/reset', method='POST'):
        root = Path(engine.__file__).resolve().parents[1]
        if (root / 'offline_routes.py').exists():
            from offline_routes import Handler
        else:
            from server import Handler
        h = object.__new__(Handler)
        h.path = path
        h.headers = {'Host': 'localhost'}
        h._body = lambda: body
        h._json = lambda payload, status=200: (status, payload)
        return h.do_POST() if method == 'POST' else h.do_GET()

    def test_case_reset_includes_all_variants_and_branches_but_preserves_other_case(self):
        parent = self.seed()
        variant = self.seed(variant=self.variant)
        branch = self.seed(parent=parent)
        other = self.seed(self.other)
        other_before = copy.deepcopy(db.get_session(other))
        before_ai = self.snapshot()['ai_usage']
        result = db.reset_progress('case', self.cid, confirmed=True)
        self.assertEqual(result['deleted'], {'attempts': 3, 'unfinished_attempts': 0,
                                            'revisions': 3, 'learning_events': 3, 'bridge_requests': 3,
                                            'patient_deliveries': 3, 'study_progress': 2})
        self.assertEqual(set(result['deleted_attempt_ids']), {parent, variant, branch})
        for sid in (parent, variant, branch):
            self.assertIsNone(db.get_session(sid))
        self.assertEqual(db.get_session(other), other_before)
        self.assertEqual(self.snapshot()['ai_usage'], before_ai)
        self.assertEqual(learning.progress()['attempted_cases'], [self.other])
        self.assertEqual(learning.progress()['completed_cases'], [self.other])
        self.assertEqual(learning.progress()['weaknesses'][0]['attempts'], 1)
        self.assertEqual({p['case_id'] for p in teaching.progress()}, {self.other})

    def test_all_reset_clears_beyond_the_past_attempts_display_limit(self):
        for _ in range(43):
            self.seed()
        self.seed(self.other)
        self.assertEqual(len(db.list_sessions()), 40)
        before = self.snapshot()
        preview_status, preview = self.route({'scope': 'all'}, '/api/progress/reset-preview')
        self.assertEqual(preview_status, 200)
        self.assertEqual(preview['attempt_count'], 44)
        self.assertEqual(preview['unfinished_count'], 0)
        self.assertEqual(preview['study_progress_count'], 2)
        self.assertEqual(self.snapshot(), before)
        status, result = self.route({'scope': 'all', 'confirm': True})
        self.assertEqual(status, 200)
        self.assertEqual(result['deleted']['attempts'], 44)
        self.assertEqual(len(set(result['deleted_attempt_ids'])), 44)
        self.assertEqual(result['sessions'], [])
        self.assertEqual(result['progress']['attempted_cases'], [])
        self.assertEqual(result['progress']['completed_cases'], [])
        self.assertEqual(result['progress']['weaknesses'], [])
        self.assertEqual(result['progress']['conditions'], {'assisted': 0, 'independent': 0, 'branches': 0})
        self.assertEqual(teaching.progress(), [])
        self.assertEqual(self.snapshot()['ai_usage'], [('do-not-reset', 'billing', 123456)])
        self.assertEqual(self.route({'scope': 'all', 'confirm': True})[1]['deleted']['attempts'], 0)

    def test_each_unfinished_phase_blocks_reset_without_any_partial_deletion(self):
        for phase in ('briefing', 'encounter', 'organize', 'note'):
            with self.subTest(phase=phase):
                completed = self.seed()
                active = self.seed(phase=phase, parent=completed)
                before = self.snapshot()
                status, result = self.route({'scope': 'case', 'case_id': self.cid, 'confirm': True})
                self.assertEqual(status, 409)
                self.assertFalse(result['reset'])
                self.assertIn({'id': active, 'case_id': self.cid, 'phase': phase}, result['active_attempts'])
                self.assertEqual(self.snapshot(), before)
                db.reset_progress('all', confirmed=True, include_in_progress=True)

    def test_explicit_option_removes_unfinished_work_and_stale_tab_fails_gracefully(self):
        submitted = self.seed()
        active = self.seed(phase='encounter')
        note = self.seed(phase='note')
        old_active = engine.load(active)
        status, result = self.route({'scope': 'case', 'case_id': self.cid,
                                    'confirm': True, 'include_in_progress': True})
        self.assertEqual(status, 200)
        self.assertEqual(result['deleted']['attempts'], 3)
        self.assertEqual(result['deleted']['unfinished_attempts'], 2)
        self.assertEqual(set(result['deleted_attempt_ids']), {submitted, active, note})
        for sid in (submitted, active, note):
            self.assertEqual(self.route({}, '/api/session/' + sid, 'GET')[0], 404)
        self.assertEqual(self.route({'note': {'S': 'late autosave'}}, '/api/session/' + note + '/note')[0], 404)
        self.assertEqual(self.route({'text': 'late turn'}, '/api/session/' + active + '/say')[0], 404)
        old_active.save()
        self.assertIsNone(db.get_session(active))
        self.assertEqual(db.list_sessions(), [])

    def test_unfinished_other_case_does_not_block_selected_case(self):
        self.seed()
        other = self.seed(self.other, phase='note')
        before = copy.deepcopy(db.get_session(other))
        status, result = self.route({'scope': 'case', 'case_id': self.cid, 'confirm': True})
        self.assertEqual(status, 200)
        self.assertEqual(result['deleted']['attempts'], 1)
        self.assertEqual(db.get_session(other), before)

    def test_strict_scope_confirmation_and_types_have_no_side_effects(self):
        self.seed()
        before = self.snapshot()
        bad = [None, [], 'all', {}, {'scope': 'all'}, {'scope': 'all', 'confirm': 1},
               {'scope': 'all', 'confirm': 'true'}, {'scope': 'everything', 'confirm': True},
               {'scope': [], 'confirm': True}, {'scope': 'case', 'confirm': True},
               {'scope': 'case', 'case_id': {}, 'confirm': True},
               {'scope': 'case', 'case_id': 'not-a-case', 'confirm': True},
               {'scope': 'all', 'case_id': self.cid, 'confirm': True},
               {'scope': 'all', 'case_id': None, 'confirm': True},
               {'scope': 'all', 'variant_id': 'base', 'confirm': True},
               {'scope': 'all', 'include_in_progress': 'true', 'confirm': True},
               {'scope': 'all', 'include_in_progress': 1, 'confirm': True}]
        for body in bad:
            with self.subTest(body=body):
                self.assertEqual(self.route(body)[0], 400)
                self.assertEqual(self.snapshot(), before)

    def test_preview_case_counts_all_variants_and_unfinished_without_writing(self):
        self.seed()
        self.seed(variant=self.variant, phase='note')
        self.seed(self.other, phase='encounter')
        before = self.snapshot()
        status, result = self.route({'scope': 'case', 'case_id': self.cid}, '/api/progress/reset-preview')
        self.assertEqual(status, 200)
        self.assertEqual(result, {'scope': 'case', 'case_id': self.cid, 'attempt_count': 2,
                                  'unfinished_count': 1, 'study_progress_count': 2})
        for body in (None, [], {}, {'scope': 'case'}, {'scope': 'case', 'case_id': []},
                     {'scope': 'all', 'confirm': True}, {'scope': 'all', 'case_id': None}):
            self.assertEqual(self.route(body, '/api/progress/reset-preview')[0], 400)
        self.assertEqual(self.snapshot(), before)

    def test_storage_boundary_also_requires_confirmation_and_boolean_option(self):
        self.seed()
        before = self.snapshot()
        for kwargs in ({}, {'confirmed': 1}, {'confirmed': True, 'include_in_progress': 1}):
            with self.assertRaises(ValueError):
                db.reset_progress('all', **kwargs)
            self.assertEqual(self.snapshot(), before)

    def test_failure_halfway_rolls_back_children_and_attempts_together(self):
        self.seed()
        before = self.snapshot()
        with db.connect() as c:
            c.execute("CREATE TRIGGER refuse_history_delete BEFORE DELETE ON sessions BEGIN SELECT RAISE(ABORT, 'simulated storage failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            db.reset_progress('all', confirmed=True)
        self.assertEqual(self.snapshot(), before)
        status, error = self.route({'scope': 'all', 'confirm': True})
        self.assertEqual(status, 503)
        self.assertIn('rolled back', error['error'])
        self.assertEqual(self.snapshot(), before)

    def test_reset_works_before_optional_progress_or_delivery_tables_exist(self):
        with db.connect() as c:
            c.execute('DROP TABLE study_progress')
            c.execute('DROP TABLE patient_deliveries')
        result = db.reset_progress('all', confirmed=True)
        self.assertEqual(result['deleted']['attempts'], 0)
        self.assertEqual(result['deleted']['patient_deliveries'], 0)
        self.assertEqual(result['deleted']['study_progress'], 0)

    def test_standalone_recall_without_attempt_is_reset_for_case_only(self):
        with db.connect() as c:
            for cid in (self.cid, self.other):
                c.execute('INSERT INTO study_progress VALUES (?,?,?,?)', (cid, 'base', db.now_ms(), '[]'))
        result = db.reset_progress('case', self.cid, confirmed=True)
        self.assertEqual(result['deleted']['attempts'], 0)
        self.assertEqual(result['deleted']['study_progress'], 1)
        self.assertEqual({r['case_id'] for r in teaching.progress()}, {self.other})


if __name__ == '__main__':
    unittest.main()
