"""The partner-print key must stay inside the demonstrated encounter."""
import copy
import json
import unittest
from pathlib import Path

from pcmcse import cases
from pcmcse.teaching.partner_note import build_example_note, SUBJECTIVE_ORDER

LESSONS = Path(__file__).resolve().parents[1] / 'pcmcse' / 'teaching' / 'lessons'


def all_lessons():
    return [w for p in sorted(LESSONS.glob('*.json')) for w in json.loads(p.read_text())['walkthroughs']]


def example(cid, variant='base'):
    lesson = next(w for w in json.loads((LESSONS / (cid + '.json')).read_text())['walkthroughs'] if w['variant_id'] == variant)
    return build_example_note(cases.resolve(cid, variant), lesson)


def section(note, group, heading):
    return next(x['text'] for x in note[group] if x['heading'] == heading)


class PartnerNotesTests(unittest.TestCase):
    def test_all_paths_preserve_source_and_course_subjective_order(self):
        lessons = all_lessons()
        self.assertEqual(len(lessons), 82)
        for lesson in lessons:
            with self.subTest(case=lesson['case_id'], variant=lesson['variant_id']):
                case = cases.resolve(lesson['case_id'], lesson['variant_id'])
                before = copy.deepcopy((case, lesson))
                result = build_example_note(case, lesson)
                self.assertEqual((case, lesson), before)
                self.assertEqual([x['heading'] for x in result['subjective']], list(SUBJECTIVE_ORDER))
                self.assertEqual(result, build_example_note(case, lesson))
                self.assertEqual(result['source']['case_hash'], lesson['case_hash'])

    def test_every_obtained_examination_is_retained_without_new_normal_findings(self):
        total = 0
        for lesson in all_lessons():
            result = build_example_note(cases.resolve(lesson['case_id'], lesson['variant_id']), lesson)
            objective = '\n'.join(x['text'] for x in result['objective'])
            for turn in lesson['timeline']:
                if turn.get('finding'):
                    total += 1
                    self.assertIn(turn['finding'], objective)
            expected = []
            for line in lesson['note']['O'].splitlines():
                if not line.strip():
                    continue
                label, _, value = line.partition(':')
                if label.startswith('Supplied '):
                    value = label[len('Supplied '):] + ': ' + value.strip()
                expected.append(value.strip())
            self.assertEqual(sorted(expected), sorted(p for x in result['objective'] for p in x['paragraphs']))
        self.assertEqual(total, 762)  # 678 established findings + 84 reviewed new-case examinations.

    def test_unspoken_drug_specificity_and_subjective_pallor_are_removed(self):
        for variant in ('base', 'neuro-thunderclap-headache--clarification', 'neuro-thunderclap-headache--support'):
            note = example('neuro-thunderclap-headache', variant)
            meds = section(note, 'subjective', 'Medications')
            self.assertNotIn('100 mg', meds)
            self.assertIn('Sumatriptan as needed (dose not established)', meds)
            self.assertIn('ibuprofen 800 mg', meds)
            self.assertEqual(len(note['corrections']), 1)
        for variant in ('base', 'gi-epigastric-melena--clarification', 'gi-epigastric-melena--support'):
            note = example('gi-epigastric-melena', variant)
            subjective = '\n'.join(x['text'] for x in note['subjective'])
            self.assertNotIn('ferrous sulfate', subjective)
            self.assertNotIn('reported pallor', subjective)
            self.assertIn('preparation and dose not established', subjective)
            self.assertIn('Conjunctival pallor is present bilaterally.', section(note, 'objective', 'HEENT'))
            self.assertEqual(len(note['corrections']), 2)

    def test_compact_note_allergies_are_in_separate_clinical_section(self):
        expected = {'cardio-chest-pressure': 'No known drug allergies.',
                    'neuro-thunderclap-headache': 'No known drug allergies.',
                    'gi-epigastric-melena': 'Penicillin causes lip/facial swelling.',
                    'renal-flank-pain': 'Sulfonamides cause hives.'}
        for cid, text in expected.items():
            note = example(cid)
            self.assertEqual(section(note, 'subjective', 'Allergies'), text)
            self.assertNotIn(text, section(note, 'subjective', 'Medications'))

    def test_specific_unsupported_third_causes_are_gaps_not_forced_diagnoses(self):
        gaps = {'gi-diarrhea-dehydration', 'neuro-distal-neuropathy', 'neuro-recurrent-headache'}
        count = 0
        for lesson in all_lessons():
            note = build_example_note(cases.resolve(lesson['case_id'], lesson['variant_id']), lesson)
            if lesson['case_id'] in gaps:
                count += 1
                self.assertEqual([x['rank'] for x in note['assessment']], [1, 2])
                self.assertEqual([x['rank'] for x in note['plan']], [1, 2])
                self.assertEqual(len(note['omitted_authored_alternatives']), 1)
                self.assertTrue(any(x['kind'] == 'authoring_gap' for x in note['outside_note']))
            else:
                self.assertEqual([x['rank'] for x in note['assessment']], [1, 2, 3])
                self.assertEqual([x['rank'] for x in note['plan']], [1, 2, 3])
        self.assertEqual(count, 9)

    def test_supported_replacements_preserve_honest_course_category_gaps(self):
        names = {'gi-right-upper-pain': 'Peptic ulcer disease',
                 'renal-acute-retention': 'Nonrelaxing pelvic-floor voiding dysfunction',
                 'renal-luts-nocturia': 'Overactive bladder'}
        for cid, name in names.items():
            note = example(cid)
            self.assertEqual(note['assessment'][2]['text'], name)
            self.assertTrue(note['assessment'][2]['fact_ids'])
            self.assertEqual(note['omitted_authored_alternatives'], [])
            self.assertTrue(any('Course category review needed' in x['text'] for x in note['outside_note']))
        for cid in ['cardio-palpitations', 'renal-colicky-flank']:
            self.assertFalse(any(x['kind'] == 'authoring_gap' for x in example(cid)['outside_note']))

    def test_existing_recommended_and_conditional_plan_words_are_preserved(self):
        for lesson in all_lessons():
            note = build_example_note(cases.resolve(lesson['case_id'], lesson['variant_id']), lesson)
            for plan in note['plan']:
                self.assertEqual(str(plan['rank']) + '. ' + plan['text'], lesson['note']['P'][plan['rank'] - 1])
                self.assertEqual(plan['event_ids'], [])
        stroke = example('neuro-acute-focal-weakness')
        self.assertIn('Parallel urgent', stroke['plan'][1]['condition'])
        self.assertIn('Check bedside glucose immediately', stroke['plan'][1]['text'])

    def test_hidden_actor_facts_never_expand_the_example_encounter(self):
        lesson = next(w for w in all_lessons() if w['case_id'] == 'cardio-febrile-cough' and w['variant_id'] == 'base')
        case = cases.resolve(lesson['case_id'])
        before = build_example_note(case, lesson)
        case['facts'].append({'id': 'secret_new_fact', 'category': 'pmh', 'value': 'This was never asked.', 'sp_says': ['This was never asked.']})
        after = build_example_note(case, lesson)
        self.assertEqual(before, after)
        self.assertNotIn('secret_new_fact', after['source']['fact_ids'])

    def test_new_authored_family_paragraph_is_not_replaced_with_older_review(self):
        lesson = copy.deepcopy(next(w for w in all_lessons() if w['case_id'] == 'cardio-febrile-cough' and w['variant_id'] == 'base'))
        original = lesson['note']['S']
        start = original.index('FH:')
        end = original.index('\n\nROS:', start)
        lesson['note']['S'] = original[:start] + 'FH: New authored family history remains exactly here.' + original[end:]
        note = build_example_note(cases.resolve(lesson['case_id']), lesson)
        self.assertEqual(section(note, 'subjective', 'Family history'), 'New authored family history remains exactly here.')

    def test_wrong_patient_or_variant_is_rejected(self):
        lesson = next(w for w in all_lessons() if w['case_id'] == 'cardio-febrile-cough' and w['variant_id'] == 'base')
        with self.assertRaises(ValueError):
            build_example_note(cases.resolve('cardio-febrile-cough', 'cardio-febrile-cough--chronology'), lesson)
        case = cases.resolve('cardio-febrile-cough')
        case['patient']['name'] = 'Different patient'
        with self.assertRaises(ValueError):
            build_example_note(case, lesson)

    def test_neutral_relationship_language_and_uncertainty_are_preserved(self):
        note = example('renal-flank-pain')
        social = section(note, 'subjective', 'Social history')
        self.assertIn('husband', social)
        self.assertIn('One male sexual partner', social)
        self.assertNotIn('boyfriend', social)
        self.assertFalse(any(x['kind'] == 'source_conflict' for x in note['outside_note']))
        note = example('gi-progressive-dysphagia')
        self.assertIn('Hydrocortisone 1% cream', section(note, 'subjective', 'Medications'))
        self.assertIn('once daily for up to 1 week', section(note, 'subjective', 'Medications'))
        note = example('neuro-distal-neuropathy')
        self.assertIn('value not recalled', section(note, 'subjective', 'Past medical and surgical history'))


if __name__ == '__main__':
    unittest.main()
