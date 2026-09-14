"""Age is asked during the interview, with immutable historical evidence."""
import copy
import json
import os
import tempfile
import unittest
from pcmcse import cases, config, db, engine, evidence, patient, record, station_info
from pcmcse.teaching import read, printables


class IdentityDisclosureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cse-identity-')
        self.old = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmp.name, 'attempts.sqlite')
        db.init()

    def tearDown(self):
        db.DB_PATH = self.old
        self.tmp.cleanup()

    def test_all_new_attempts_and_print_doorways_withhold_age(self):
        count = 0
        for cid, base in cases.all_cases().items():
            for variant in ['base'] + [v['id'] for v in base.get('variants', [])]:
                case = cases.resolve(cid, variant)
                original = copy.deepcopy(case)
                settings = {**copy.deepcopy(config.DEFAULT_SETTINGS), 'learning_mode': 'guided'}
                sid = db.create_session(cid, 'guided_untimed', 'type', True, settings, case)
                s = engine.load(sid)
                self.assertEqual(s.case['patient'], original['patient'])
                self.assertNotRegex(' '.join(s.case['station']['doorway']), r'\d+[- ]year[- ]old')
                s.start_encounter()
                delivered = next(e for e in s.ledger.events if e['meta'].get('doorway'))
                self.assertNotRegex(delivered['text'], r'\d+[- ]year[- ]old')
                safe = printables.doorway(cid, variant)
                self.assertNotIn('age', safe['patient'])
                self.assertEqual(safe['doorway']['doorway'], station_info.doorway(case))
                lesson = read(cid, variant)
                self.assertEqual(lesson['patient']['age'], original['patient']['age'])
                self.assertEqual(lesson['doorway']['doorway'], station_info.doorway(case))
                self.assertEqual(case, original)
                count += 1
        self.assertEqual(count, 82)

    def test_notes_adds_only_spoken_identity_and_merges_repeats(self):
        case = cases.resolve('cardio-palpitations')
        ledger = evidence.Ledger()
        ledger.add(evidence.STATION_INFO, ' '.join(station_info.doorway(case)), meta={'doorway': True})
        self.assertNotIn('27', json.dumps(record.summarize(case, ledger.events)))
        pe, state = patient.PatientEngine(case), {}
        for q in ["hi I'm student Dr Sebastian how may I address you today", "what's your name and age", "How old are you?"]:
            ledger.add(evidence.STUDENT, q)
            reply, meta = pe.respond(q, state)
            ledger.add(evidence.PATIENT, reply, meta=meta)
            summary = record.summarize(case, ledger.events)
            rows = [item for group in summary['groups'] for section in group['sections'] for item in section['items']]
            if 'address' in q:
                self.assertFalse(any(item.get('label') == 'Age' for item in rows))
        age = [item for item in rows if item.get('label') == 'Age']
        self.assertEqual(len(age), 1)
        self.assertEqual(age[0]['text'], '27 years old')
        self.assertEqual(len(age[0]['seqs']), 2)
        false_reply = evidence.Ledger()
        false_reply.add(evidence.PATIENT, 'I am a software analyst.', meta={'identity_fields': ['age']})
        self.assertFalse(record.summarize(case, false_reply.events)['groups'])

    def test_historical_records_are_not_rewritten_by_projection(self):
        case = cases.resolve('cardio-palpitations')
        ledger = evidence.Ledger()
        ledger.add(evidence.STATION_INFO, ' '.join(case['station']['doorway']), meta={'doorway': True})
        before = (copy.deepcopy(case), ledger.to_json())
        station_info.doorway(case)
        summary = record.summarize(case, ledger.events)
        self.assertIn('27-year-old', json.dumps(summary))
        self.assertEqual((case, ledger.to_json()), before)


if __name__ == '__main__':
    unittest.main()
