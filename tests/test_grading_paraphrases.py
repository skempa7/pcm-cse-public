"""Equivalent clinical wording keeps content credit without relaxing the rubric."""
import copy
import unittest
from pcmcse import cases, config, evidence, grader, note


class GradingParaphraseTests(unittest.TestCase):
    def setUp(self):
        self.case = cases.resolve('cardio-palpitations')
        self.scoring = config.load_settings()['scoring']

    def test_common_diagnosis_spellings_match_the_same_authored_alternative(self):
        for phrasing in ('AFib', 'A-fib', 'A fib', 'AFib with rapid ventricular response'):
            with self.subTest(phrasing=phrasing):
                letter, matched = grader._vindicate_of(phrasing, self.case)
                self.assertEqual((letter, matched['name']), ('V', 'Atrial fibrillation'))
        for phrasing in ('Overactive thyroid', 'Thyroid overactivity', 'Hyperthyroid state'):
            letter, matched = grader._vindicate_of(phrasing, self.case)
            self.assertEqual((letter, matched['name']), ('E', 'Hyperthyroidism'))

    def test_explanation_and_excluded_diagnoses_do_not_replace_the_asserted_subject(self):
        for phrasing in ('AF (stimulant-associated tachycardia less likely)',
                         'AF. No stimulant-associated tachycardia.',
                         'Most likely AF given irregular pulse. Hyperthyroidism less likely.',
                         'Atrial fibrillation; hyperthyroidism is an alternative.'):
            with self.subTest(phrasing=phrasing):
                self.assertEqual(grader._vindicate_of(phrasing, self.case)[1]['name'], 'Atrial fibrillation')
        self.assertEqual(grader._vindicate_of('No atrial fibrillation; likely stimulant-related palpitations.', self.case)[1]['name'], 'Stimulant-associated tachycardia')
        self.assertIsNone(grader._vindicate_of('Atrial fibrillation ruled out.', self.case)[1])
        self.assertIsNone(grader._vindicate_of('Myxoma most likely. Atrial fibrillation is less likely.', self.case)[1])
        self.assertIsNone(grader._vindicate_of('Unmapped syndrome; AF is an alternative.', self.case)[1])

    def test_full_test_names_and_ordinary_order_verbs_equal_acronyms(self):
        for phrasing in ('Obtain an electrocardiogram.', 'Order a 12-lead electrocardiogram.',
                         'Get an ECG.', 'Check a complete blood count.',
                         'Check thyroid function tests.', 'Obtain thyroid tests.'):
            with self.subTest(phrasing=phrasing):
                self.assertIn('T', grader._motherr_elements(phrasing))
        for phrasing in ('Do not get an ECG.', 'An ECG was obtained.',
                         'The electrocardiogram was normal.', 'ECG has yet to be performed.',
                         'No complete blood count was obtained.'):
            self.assertNotIn('T', grader._motherr_elements(phrasing), phrasing)

    def test_specific_selfcare_instructions_do_not_require_a_magic_education_verb(self):
        for phrasing in ('Stop energy drinks.', 'Recommend avoiding caffeine.',
                         'Reduce alcohol intake.', 'Counsel about cutting down on alcohol.'):
            with self.subTest(phrasing=phrasing):
                self.assertTrue({'H', 'E'}.issubset(grader._motherr_elements(phrasing)))
                self.assertTrue(grader._education_is_specific(phrasing))
        self.assertTrue(grader._education_is_specific('Explain that caffeine may trigger a fast heartbeat.'))
        for phrasing in ('Caffeine.', 'The patient reduced alcohol last year.',
                         'Do not reduce alcohol.', 'No counseling provided.'):
            self.assertFalse(grader._education_is_specific(phrasing), phrasing)

    def test_numbered_equivalent_differentials_preserve_score_and_unresolved_is_labeled(self):
        original = note.parse(self.case['model_note'])
        rewritten = copy.deepcopy(self.case['model_note'])
        rewritten['A'] = ['1. AFib given the irregular pulse.', '2. Caffeine-induced palpitations', '3. Overactive thyroid']
        before, _ = grader._grade_assessment(original, self.case, self.scoring)
        after, _ = grader._grade_assessment(note.parse(rewritten), self.case, self.scoring)
        self.assertEqual([r.points_earned for r in before], [r.points_earned for r in after])
        unknown = note.parse({'A': ['1. Unmapped plausible hypothesis']})
        rows, _ = grader._grade_assessment(unknown, self.case, self.scoring)
        self.assertTrue(rows[0].to_dict()['recognition_limited'])
        self.assertFalse(rows[1].to_dict()['recognition_limited'])
        self.assertEqual(rows[0].points_earned, 0)

    def test_course_numbering_diversity_and_plan_action_count_remain_required(self):
        rows, _ = grader._grade_assessment(note.parse({'A': ['AFib', 'Caffeine-induced tachycardia', 'Overactive thyroid']}), self.case, self.scoring)
        self.assertFalse(any(r.earned for r in rows))
        rows, _ = grader._grade_assessment(note.parse({'A': ['1. AFib', '2. AFib', '3. Overactive thyroid']}), self.case, self.scoring)
        self.assertFalse(rows[1].earned)
        payload = {'A': ['1. AFib'], 'P': ['1. Get an ECG.']}
        rows, _ = grader._grade_plan(note.parse(payload), self.case, evidence.Ledger([]), {'claims': []}, self.scoring)
        self.assertFalse(rows[0].earned)
        self.assertIn('at least three', rows[0].why)


if __name__ == '__main__':
    unittest.main()
