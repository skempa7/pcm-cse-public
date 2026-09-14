"""Pain presence is a new clinical question, not a repeat of prior quality."""
import copy
import unittest
from pcmcse import cases, evidence, patient, record


class PainQuestionTests(unittest.TestCase):
    prompts = ['Is there any pain associated with that?', 'Do you feel any pain?',
               'Do you have any pain?', 'Does it hurt?', 'Is it painful?', 'Any pain?']

    def reply_after_quality(self, case, question):
        pe, state = patient.PatientEngine(case), {}
        pe.respond('What brings you in today?', state)
        pe.respond('What does it feel like?', state)
        return pe.respond(question, state)

    def test_exact_screenshot_sequence_across_palpitations_variants(self):
        for variant in ['base'] + [v['id'] for v in cases.get('cardio-palpitations').get('variants', [])]:
            case = cases.resolve('cardio-palpitations', variant)
            pe, state, ledger = patient.PatientEngine(case), {}, evidence.Ledger()
            for q in [
                'What brings you in today?',
                "and you said your heart feels fast and uneven is there any other way you can describe this sensation you're feeling",
                'is there any pain associated with that', 'do you feel any pain',
            ]:
                reply, meta = pe.respond(q, state)
                ledger.add(evidence.STUDENT, q)
                ledger.add(evidence.PATIENT, reply, meta=meta)
                if 'pain' in q:
                    self.assertIn('I do not have chest pain.', reply)
                    self.assertEqual(meta['facts_released'], ['symptom_chest_pain'])
                    self.assertFalse(meta.get('no_information'))
                    self.assertNotIn('hpi_quality', meta['concepts'])
            rows = [i for g in record.summarize(case, ledger.events)['groups'] for sec in g['sections'] for i in sec['items']]
            denial = [i for i in rows if i.get('fact_id') == 'symptom_chest_pain']
            self.assertEqual(len(denial), 1)
            self.assertTrue(denial[0]['reported_negative'])
            self.assertEqual(len(denial[0]['seqs']), 2)

    def test_primary_pain_cannot_be_replaced_by_another_regions_negative(self):
        examples = {
            'cardio-exertional-leg-pain': ['hpi_quality'],
            'renal-acute-retention': ['hpi_quality'],
            'renal-dysuria': ['hpi_quality', 'symptom_dysuria'],
            'skin-localized-redness': ['hpi_quality', 'symptom_pruritus'],
            'skin-contact-rash': ['hpi_quality', 'symptom_pruritus'],
            'msk-knee-injury': ['hpi_quality', 'symptom_joint_pain'],
        }
        for cid, allowed in examples.items():
            case = cases.resolve(cid)
            for question in self.prompts:
                with self.subTest(case=cid, question=question):
                    reply, meta = self.reply_after_quality(case, question)
                    self.assertTrue(set(meta['facts_released']) & set(allowed), reply)
                    self.assertFalse(set(meta['facts_released']) & {'symptom_chest_pain', 'symptom_flank_pain', 'symptom_back_pain'})
                    self.assertFalse(meta.get('no_information'), reply)

    def test_painless_and_scoped_negative_answers(self):
        for cid, expected in [('cardio-palpitations', 'I do not have chest pain.'),
                              ('gi-progressive-dysphagia', 'Swallowing itself is not painful.'),
                              ('renal-painless-hematuria', 'nothing hurts')]:
            case = cases.resolve(cid)
            for question in self.prompts:
                with self.subTest(case=cid, question=question):
                    reply, meta = self.reply_after_quality(case, question)
                    self.assertIn(expected, reply)
                    self.assertFalse(meta.get('no_information'))

    def test_missing_pain_information_does_not_become_a_denial_or_old_quality(self):
        for cid in ['cardio-orthopnea-edema', 'pulm-episodic-wheeze', 'neuro-positional-vertigo']:
            case = cases.resolve(cid)
            for question in self.prompts:
                with self.subTest(case=cid, question=question):
                    reply, meta = self.reply_after_quality(case, question)
                    self.assertFalse(meta['facts_released'], reply)
                    self.assertFalse(meta['concepts'], reply)
                    self.assertTrue(meta.get('no_information'), reply)

    def test_pain_attributes_and_explicit_regions_keep_their_own_routes(self):
        case = cases.resolve('cardio-palpitations')
        for question, expected in [('What does it feel like?', 'hpi_quality'),
                                    ('Does the discomfort spread anywhere else?', 'hpi_radiation')]:
            reply, meta = self.reply_after_quality(case, question)
            self.assertIn(expected, meta['facts_released'], reply)
        case = cases.resolve('renal-dysuria')
        reply, meta = self.reply_after_quality(case, 'Do you have flank pain?')
        self.assertIn('symptom_flank_pain', meta['facts_released'], reply)
        self.assertNotIn('hpi_quality', meta['facts_released'])

    def test_fresh_named_symptom_does_not_inherit_previous_quality(self):
        case = cases.resolve('cardio-palpitations')
        for question in ['Is there any nausea with that?', 'Do you get a rash with that?', 'Any vomiting with that?']:
            reply, meta = self.reply_after_quality(case, question)
            self.assertNotIn('hpi_quality', meta['facts_released'], (question, reply))

    def test_named_pain_and_combined_symptoms_do_not_repeat_palpitations(self):
        case = cases.resolve('cardio-palpitations')
        for question in ['Are you in pain?', 'Are the palpitations painful?',
                         'Is there pain with the racing heartbeat?']:
            reply, meta = self.reply_after_quality(case, question)
            self.assertIn('I do not have chest pain.', reply)
            self.assertEqual(meta['facts_released'], ['symptom_chest_pain'])
        reply, meta = self.reply_after_quality(case, 'Is there any pain and are you short of breath?')
        self.assertEqual(set(meta['facts_released']), {'symptom_chest_pain', 'symptom_dyspnea'})
        pe, state = patient.PatientEngine(case), {}
        pe.respond('Are you short of breath?', state)
        reply, meta = pe.respond('Any pain anywhere?', state)
        self.assertNotIn('symptom_dyspnea', meta['facts_released'], reply)
        self.assertNotRegex(reply.lower(), r"no pain anywhere|no pain at all|nothing hurts")

    def test_immediate_followup_keeps_the_specific_pain_region(self):
        case = cases.resolve('cardio-exertional-leg-pain')
        pe, state = patient.PatientEngine(case), {}
        pe.respond('What does it feel like?', state)
        reply, meta = pe.respond('Do you have chest pain?', state)
        self.assertIn('symptom_chest_pain', meta['facts_released'])
        reply, meta = pe.respond('Does it hurt?', state)
        self.assertIn('symptom_chest_pain', meta['facts_released'], reply)
        self.assertNotIn('hpi_quality', meta['facts_released'])

    def test_all_paths_only_deliver_their_authored_information(self):
        count = 0
        for cid, base in cases.all_cases().items():
            for variant in ['base'] + [v['id'] for v in base.get('variants', [])]:
                case = cases.resolve(cid, variant)
                before = copy.deepcopy(case)
                for question in self.prompts:
                    reply, meta = self.reply_after_quality(case, question)
                    definitions = {f['id']: f for f in case['facts']}
                    for fid in meta['facts_released']:
                        if fid == 'opening_complaint':
                            self.assertIn(case['patient']['opening'].lower(), reply.lower())
                        else:
                            self.assertIn(fid, definitions)
                            self.assertIn(fid, (patient.delivered_fact_metadata(definitions[fid], reply) or {}).get('facts_released', []), (cid, variant, question, reply))
                self.assertEqual(case, before)
                count += 1
        self.assertEqual(count, 82)


if __name__ == '__main__':
    unittest.main()
