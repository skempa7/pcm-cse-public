from sparse_case_fixtures import resolve as sparse_resolve
"""Broad symptom questions must not become concern or work-history invitations."""
import copy
import unittest
from pcmcse import cases, evidence, patient, record


class AssociatedSymptomQuestionTests(unittest.TestCase):
    prompts = [
        'and and have you noticed any other symptoms that go along with the racing and heart going fast and fluttering',
        'Have you noticed any other associated symptoms?',
        'Any other symptoms?',
        'What other symptoms have you noticed?',
        'Do you have any symptoms along with that?',
        'Does anything else happen when your heart is racing?',
    ]

    def ready(self, case):
        pe, state = patient.PatientEngine(case), {}
        pe.respond('What brings you in today?', state)
        pe.respond('What does it feel like?', state)
        return pe, state

    def test_mara_paraphrases_answer_additional_symptoms_in_all_variants(self):
        for variant in ['base'] + [v['id'] for v in cases.get('cardio-palpitations').get('variants', [])]:
            case = sparse_resolve('cardio-palpitations', variant)
            for question in self.prompts:
                with self.subTest(variant=variant, question=question):
                    pe, state = self.ready(case)
                    before = state['open_budget']
                    reply, meta = pe.respond(question, state)
                    self.assertEqual(set(meta['facts_released']), {'symptom_dyspnea', 'symptom_fatigue'}, reply)
                    self.assertIn('short of breath', reply)
                    self.assertIn('less energy', reply)
                    self.assertFalse(meta['volunteered'])
                    self.assertEqual(state['open_budget'], before)

    def test_exact_sequence_and_notes_dont_record_unrelated_history(self):
        case = sparse_resolve('cardio-palpitations')
        pe, state = self.ready(case)
        ledger = evidence.Ledger()
        for q in ['does it hurt at all', self.prompts[0], self.prompts[1]]:
            ledger.add(evidence.STUDENT, q)
            reply, meta = pe.respond(q, state)
            ledger.add(evidence.PATIENT, reply, meta=meta)
            if 'hurt' in q:
                self.assertIn('I do not have chest pain.', reply)
            else:
                self.assertNotRegex(reply, r'energy drinks|work nights|heart attack|heart feels fast and uneven')
                self.assertFalse(meta['volunteered'])
                self.assertFalse(set(meta['facts_released']) & {'patient_concern', 'symptom_palpitations'})
        rows = [i for g in record.summarize(case, ledger.events)['groups'] for s in g['sections'] for i in s['items']]
        for fid in ['symptom_chest_pain', 'symptom_dyspnea', 'symptom_fatigue']:
            self.assertEqual(sum(i.get('fact_id') == fid for i in rows), 1)

    def test_symptom_request_does_not_depend_on_volunteer_budget(self):
        pe, state = self.ready(sparse_resolve('cardio-palpitations'))
        state['open_budget'] = 0
        reply, meta = pe.respond('Have you noticed any other associated symptoms?', state)
        self.assertEqual(set(meta['facts_released']), {'symptom_dyspnea', 'symptom_fatigue'}, reply)
        self.assertEqual(state['open_budget'], 0)

    def test_narrow_symptom_requests_stay_narrow(self):
        pe, state = self.ready(sparse_resolve('cardio-palpitations'))
        for q, allowed in [('Is there any pain associated with that?', {'symptom_chest_pain'}),
                           ('Are you short of breath?', {'symptom_dyspnea'}),
                           ('Have you felt unusually tired or low in energy?', {'symptom_fatigue'})]:
            reply, meta = pe.respond(q, state)
            self.assertEqual(set(meta['facts_released']), allowed, reply)

    def test_general_invitation_keeps_its_existing_courtesy_behavior(self):
        pe, state = self.ready(sparse_resolve('cardio-palpitations'))
        reply, meta = pe.respond('Is there anything else you would like to tell me?', state)
        self.assertTrue(meta['volunteered'])
        self.assertEqual(meta['facts_released'], ['patient_concern'])

    def test_no_additional_authored_symptoms_does_not_repeat_primary_complaint(self):
        for cid in ['cardio-presyncope', 'renal-painless-hematuria', 'msk-knee-injury',
                    'skin-contact-rash', 'neuro-acute-focal-weakness']:
            pe, state = self.ready(sparse_resolve(cid))
            reply, meta = pe.respond('Have you noticed any other associated symptoms?', state)
            self.assertFalse(meta['facts_released'], (cid, reply))
            self.assertFalse(meta['volunteered'])
            self.assertTrue(meta.get('no_information'))

    def test_broad_symptom_questions_preserve_focused_disclosure_requirements(self):
        blocked = {
            'cardio-chest-pressure': {'current_chest_pressure'},
            'neuro-positional-vertigo': {'current_vertigo'},
            'gi-progressive-dysphagia': {'history_swallow_liquids', 'history_manage_saliva'},
            'gi-right-lower-pain': {'history_bowel_pattern'},
            'renal-colicky-flank': {'history_current_urine_output'},
            'renal-luts-nocturia': {'history_voided_volume'},
            'neuro-back-bladder-redflags': {'symptom_saddle_numbness'},
        }
        for cid, withheld in blocked.items():
            pe, state = self.ready(sparse_resolve(cid))
            for _ in range(5):
                reply, meta = pe.respond('Any other associated symptoms?', state)
                self.assertFalse(withheld & set(meta['facts_released']), (cid, reply, meta))

    def test_combined_identity_and_associated_question_answers_both(self):
        pe, state = self.ready(sparse_resolve('cardio-palpitations'))
        reply, meta = pe.respond('What is your name and have you noticed any other associated symptoms?', state)
        self.assertIn('Mara Lee', reply)
        self.assertEqual(set(meta['facts_released']), {'symptom_dyspnea', 'symptom_fatigue'})
        self.assertEqual(meta['identity_fields'], ['name'])
        self.assertFalse(meta['volunteered'])

    def test_symptom_question_can_be_asked_before_the_opening(self):
        reply, meta = patient.PatientEngine(sparse_resolve('cardio-palpitations')).respond('Any other associated symptoms?', {})
        self.assertEqual(set(meta['facts_released']), {'symptom_dyspnea', 'symptom_fatigue'}, reply)
        self.assertFalse(meta['volunteered'])

    def test_exclusions_and_prospective_questions_do_not_dump_symptom_list(self):
        pe, state = self.ready(sparse_resolve('cardio-palpitations'))
        reply, meta = pe.respond('What other symptoms besides shortness of breath have you noticed?', state)
        self.assertEqual(meta['facts_released'], ['symptom_fatigue'], reply)
        for q in ['What other symptoms should I look for?',
                  'Does your mother have any other symptoms?',
                  'Does nausea always occur at the same time as the palpitations?']:
            pe, state = self.ready(sparse_resolve('cardio-palpitations'))
            reply, meta = pe.respond(q, state)
            self.assertFalse(set(meta['facts_released']) & {'symptom_dyspnea', 'symptom_fatigue'}, (q, reply))

    def test_all_paths_stay_authored_bounded_and_do_not_invent_global_negatives(self):
        count = 0
        for cid, base in cases.all_cases().items():
            for variant in ['base'] + [v['id'] for v in base.get('variants', [])]:
                case = sparse_resolve(cid, variant)
                original = copy.deepcopy(case)
                definitions = {f['id']: f for f in case['facts']}
                pe, state = self.ready(case)
                budget = state['open_budget']
                for _ in range(4):
                    reply, meta = pe.respond('Have you noticed any other associated symptoms?', state)
                    self.assertFalse(meta['volunteered'], (cid, reply))
                    self.assertEqual(state['open_budget'], budget)
                    self.assertLessEqual(len(meta['facts_released']), 2)
                    self.assertNotRegex(reply.lower(), r'^no other symptoms|^no, i think that.s about it|^not that i can think of')
                    for fid in meta['facts_released']:
                        fact = definitions[fid]
                        self.assertEqual(fact['category'], 'associated', (cid, fid, reply))
                        approved = patient.delivered_fact_metadata(fact, reply) or {}
                        self.assertIn(fid, approved.get('facts_released', []), (cid, fid, reply))
                        self.assertFalse(fact.get('requires_current_status_question'))
                self.assertEqual(case, original)
                count += 1
        self.assertEqual(count, 82)


if __name__ == '__main__':
    unittest.main()
