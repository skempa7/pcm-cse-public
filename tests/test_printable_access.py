"""Safe student handouts must not reveal facts or change a scored attempt."""
import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pcmcse import cases, config, db, engine
from pcmcse.teaching import printables
from offline_routes import request

class PrintableAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cse-print-access-')
        self.old = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmp.name, 'attempts.sqlite')
        db.init()
        self.clock = patch.object(db, 'now_ms', lambda: 2000000000000)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        db.DB_PATH = self.old
        self.tmp.cleanup()

    def get(self, path):
        return json.loads(request(path, 'GET', '{}'))

    def test_safe_handout_allowlist_is_exact_for_every_case_path(self):
        for cid, base in cases.all_cases().items():
            for vid in ['base'] + [v['id'] for v in base.get('variants', [])]:
                with self.subTest(case=cid, variant=vid):
                    c = cases.resolve(cid, vid)
                    before = copy.deepcopy(c)
                    data = printables.doorway(cid, vid)
                    self.assertEqual(set(data), {'case_id','variant_id','variant_label','patient','doorway','title','timeline'})
                    self.assertEqual(data['patient'], {k:c['patient'][k] for k in ('name','age','sex')})
                    self.assertEqual(data['doorway'], {k:c['station'].get(k, {} if k=='vitals' else []) for k in ('doorway','vitals','supplied_results')})
                    self.assertEqual(data['timeline'], [])
                    self.assertEqual(c, before)
                    # Mutation of a consumer's safe payload must not alter canonical material.
                    data['doorway']['doorway'].append('temporary consumer annotation')
                    self.assertNotIn('temporary consumer annotation', printables.doorway(cid,vid)['doorway']['doorway'])

    def test_new_hidden_fields_cannot_leak_through_safe_route_or_index(self):
        c = cases.resolve('renal-flank-pain')
        c['patient']['secret_diagnosis'] = 'do not expose'
        c['station']['hidden_result'] = 'never observed'
        with patch.object(cases, 'resolve', return_value=c):
            data = self.get('/api/printables/renal-flank-pain')
        self.assertEqual(data['status'], 200)
        self.assertNotIn('do not expose', json.dumps(data))
        self.assertNotIn('never observed', json.dumps(data))
        rows = self.get('/api/printables')['body']['cases']
        self.assertEqual(len(rows), 34)
        for row in rows:
            self.assertEqual(set(row), {'id','title','system','variants'})
            self.assertTrue(all(set(v) == {'id','label'} for v in row['variants']))

    def test_safe_printing_preserves_scored_note_evidence_and_deadline(self):
        settings = copy.deepcopy(config.DEFAULT_SETTINGS)
        settings.update(learning_mode='rehearsal', preset='course', simulation_runtime='interactive')
        sid = db.create_session('renal-flank-pain', 'course', 'type', False, settings, case=cases.resolve('renal-flank-pain'))
        s = engine.load(sid)
        s.start_encounter()
        s.student_turn('When did the pain start?')
        db.update_session(sid, scratch='My own unfinished note')
        before = db.get_session(sid)
        self.assertEqual(self.get('/api/teaching/renal-flank-pain')['status'],409)
        for path in ('/api/printables','/api/printables/renal-flank-pain'):
            self.assertEqual(self.get(path)['status'],200)
        self.assertEqual(db.get_session(sid), before)
        self.assertEqual(self.get('/api/teaching/renal-flank-pain')['status'],409)
        self.assertFalse(db.get_session(sid)['assisted'])

    def test_unknown_case_variant_and_extra_segments_fail_closed(self):
        for path in ('/api/printables/no-such-case','/api/printables/renal-flank-pain?variant=unknown','/api/printables/renal-flank-pain/answers'):
            self.assertEqual(self.get(path)['status'],404,path)

if __name__ == '__main__': unittest.main()
