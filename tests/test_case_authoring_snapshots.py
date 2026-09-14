"""Case authoring must change new practice without rewriting saved patients."""
import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from pcmcse import cases, config, db, engine, evidence, historical_cases
from pcmcse.patient import PatientEngine


class CaseAuthoringSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cse-case-authoring-')
        self.old_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmp.name, 'disposable.sqlite')
        db.init()
        self.now = 1789000000000
        self.clock = patch('pcmcse.db.now_ms', side_effect=lambda: self.now)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        db.DB_PATH = self.old_path
        self.tmp.cleanup()

    def create(self, case):
        settings = config.load_settings()
        settings.update(learning_mode='coached', simulation_runtime='interactive')
        sid = db.create_session(case['id'], 'coached_untimed', 'type', False, settings, case=case)
        session = engine.load(sid)
        session.start_encounter()
        return session

    def test_old_snapshot_replies_note_and_deadline_survive_new_library(self):
        old = historical_cases.for_attempt({'case_id': 'cardio-febrile-cough', 'case_snapshot': ''})
        session = self.create(old)
        before_snapshot = db.get_session(session.id)['case_snapshot']
        before_version = db.get_session(session.id)['case_version']
        session.student_turn('Do you have any medication allergies?')
        reply = session.ledger.by_kind(evidence.PATIENT)[-1]['text']
        self.assertIn('no', reply.lower())
        self.assertNotIn('Amoxicillin', reply)
        # Set up an interrupted note; the public save route uses this engine method.
        db.update_session(session.id, phase='note', phase_ends_at=self.now + 90000)
        session = engine.load(session.id)
        writing = {'S': 'My own unfinished history', 'O': 'My examination notes', 'A': [], 'P': []}
        session.save_note(writing)
        recorded = db.get_session(session.id)
        resumed = engine.load(session.id)
        self.assertEqual(resumed.case['patient'], old['patient'])
        self.assertEqual(resumed.row['phase_ends_at'], self.now + 90000)
        self.assertEqual(resumed.row['note_json'], recorded['note_json'])
        self.assertEqual(resumed.row['ledger_json'], recorded['ledger_json'])
        self.assertEqual(resumed.row['case_snapshot'], before_snapshot)
        self.assertEqual(resumed.row['case_version'], before_version)
        newer = self.create(cases.resolve('cardio-febrile-cough'))
        newer.student_turn('Do you have any medication allergies?')
        self.assertIn('Amoxicillin', newer.ledger.by_kind(evidence.PATIENT)[-1]['text'])
        self.assertNotEqual(newer.row['case_version'], before_version)
        self.assertEqual(db.get_session(session.id), recorded)

    def test_pre_snapshot_attempt_uses_immutable_archive_and_is_not_backfilled(self):
        old = historical_cases.for_attempt({'case_id': 'cardio-febrile-cough', 'case_snapshot': ''})
        session = self.create(old)
        db.update_session(session.id, case_snapshot='', scratch='Keep my older attempt')
        session = engine.load(session.id)
        self.assertEqual(session.case, old)
        session.student_turn('Do you have any medication allergies?')
        row = db.get_session(session.id)
        self.assertEqual(row['case_snapshot'], '')
        self.assertEqual(row['scratch'], 'Keep my older attempt')
        self.assertNotIn('Amoxicillin', session.ledger.by_kind(evidence.PATIENT)[-1]['text'])
        session.case['patient']['name'] = 'Local disposable mutation'
        self.assertEqual(engine.load(session.id).case['patient']['name'], old['patient']['name'])

    def test_unknown_historical_source_fails_without_replacing_saved_data(self):
        session = self.create(cases.resolve('cardio-febrile-cough'))
        db.update_session(session.id, case_id='unknown-historical-patient', case_snapshot='', scratch='Recoverable notes')
        before = db.get_session(session.id)
        with self.assertRaisesRegex(ValueError, 'original data has been preserved'):
            engine.load(session.id)
        self.assertEqual(db.get_session(session.id), before)

    def test_revised_histories_are_reachable_out_of_order_in_every_variant(self):
        questions = {
            'cardio-febrile-cough': [('Who do you live with?', 'history_household', 'roommate'), ('Do you have any medication allergies, and what reaction did you have?', 'history_allergies_1', 'hives'), ('Do you drink alcohol?', 'alcohol_use', 'do not drink')],
            'cardio-presyncope': [('Have you ever smoked?', 'tobacco_use', '7 years'), ('What operations have you had?', 'history_psh_1', 'right knee'), ('Who do you live with?', 'history_household', 'brother')],
            'renal-painless-hematuria': [('What do you do for work?', 'history_context_1', 'solvents'), ('Do you smoke or have you in the past?', 'tobacco_use', 'half a pack')],
            'gi-progressive-dysphagia': [('What medicines do you take?', 'history_medications_1', 'hydrocortisone 1%')],
            'renal-colicky-flank': [('Have you had any surgery?', 'history_psh_1', 'stent'), ('Have you had a stone before?', 'hpi_past_occurrence', '5 years')],
            'gi-diarrhea-dehydration': [('Do you drink alcohol?', 'alcohol_use', 'do not drink'), ('What do you do for work?', 'history_context_1', 'toilet')],
            'neuro-recurrent-headache': [('Who do you live with?', 'history_household', 'drive'), ('Do you drink alcohol?', 'alcohol_use', 'do not drink')],
            'neuro-distal-neuropathy': [('Do you ever miss medication doses?', 'history_medications_2', 'shift runs late'), ('What do you do for work?', 'history_context_1', '8-hour')],
            'renal-flank-pain': [('How many sexual partners do you have?', 'history_sexual_partners', 'husband')],
        }
        for cid, prompts in questions.items():
            for vid in ['base'] + [v['id'] for v in cases.get(cid)['variants']]:
                c = cases.resolve(cid, vid)
                for question, fid, text in prompts:
                    with self.subTest(case=cid, variant=vid, question=question):
                        reply, meta = PatientEngine(c).respond(question, {'opened': True, 'open_budget': 0})
                        self.assertIn(fid, meta.get('facts_released', []))
                        self.assertIn(text.lower(), reply.lower())
                        fact = next(f for f in c['facts'] if f['id'] == fid)
                        delivered = next(v for v in fact['delivery_contract']['versions'] if v['text'] == fact['sp_says'][0])
                        self.assertEqual(delivered['concepts'], fact['concepts'])
                        self.assertTrue(delivered['complete_fact'])
                        self.assertEqual(next(x for x in c['checklist']['history'] if x['id'] == fact['checklist'])['text'], fact['value'])


if __name__ == '__main__':
    unittest.main()
