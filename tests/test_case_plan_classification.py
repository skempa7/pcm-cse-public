"""Clinically plausible but unclassified alternatives do not earn invented credit."""
import copy
import unittest
from pcmcse import cases, config, grader, note, historical_cases


class CasePlanClassificationTests(unittest.TestCase):
    def test_unassigned_alternatives_are_unresolved_not_crashes_or_guessed_credit(self):
        for cid in ['renal-acute-retention', 'renal-luts-nocturia']:
            case = cases.resolve(cid)
            source = copy.deepcopy(case)
            rows, meta = grader._grade_assessment(note.parse(case['model_note']), case, config.load_settings()['scoring'])
            self.assertIsNone(meta['letters'][2])
            self.assertIsNone(meta['matched'][2])
            self.assertEqual(rows[2].earned, 0)
            self.assertIn('unresolved', str(rows[2].__dict__).lower())
            self.assertEqual(case, source)
        case = cases.resolve('gi-right-upper-pain')
        rows, meta = grader._grade_assessment(note.parse(case['model_note']), case, config.load_settings()['scoring'])
        self.assertEqual(meta['letters'], ['I', 'V', 'I'])
        self.assertEqual(rows[2].earned, 0)
        self.assertIn('three different', str(rows[2].__dict__))

    def test_new_alternatives_reference_only_real_facts_and_do_not_rewrite_archives(self):
        for cid in ['gi-right-upper-pain', 'renal-acute-retention', 'renal-luts-nocturia']:
            old = historical_cases.for_attempt({'case_id': cid, 'case_snapshot': ''})
            before = copy.deepcopy(old)
            case = cases.resolve(cid)
            d = case['differentials'][2]
            self.assertTrue(d['supported_by'])
            self.assertTrue(set(d['supported_by']).issubset({f['id'] for f in case['facts']}))
            self.assertEqual(case['model_note']['A'][2], '3. '+d['name'])
            self.assertEqual(historical_cases.for_attempt({'case_id': cid, 'case_snapshot': ''}), before)
            self.assertNotEqual(old['model_note']['A'][2], case['model_note']['A'][2])

    def test_plan_conditions_and_original_clinical_priorities_remain(self):
        stone = cases.resolve('renal-colicky-flank')['model_note']['P']
        self.assertIn('urgent urology', stone[0])
        self.assertIn('48–72 hours', stone[0])
        self.assertIn('if stable for outpatient care', stone[0])
        self.assertIn('If a focal muscle strain is supported', stone[2])
        self.assertIn('earlier dose', stone[2])
        palp = cases.resolve('cardio-palpitations')['model_note']['P']
        self.assertIn('same-day emergency department', palp[0])
        self.assertIn('Review the ECG/rhythm findings', palp[1])
        self.assertIn('depends on confirming the cause', palp[2])
        self.assertTrue({'T', 'H', 'E'}.issubset(grader._motherr_elements(palp[1])))
        self.assertNotIn('follow-up', palp[1])


if __name__ == '__main__':
    unittest.main()
