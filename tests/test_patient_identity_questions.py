"""Identity questions use supplied patient details and preserve other asks."""
import copy
import unittest

from pcmcse import cases, dialogue, engine, nlp, patient


class PatientIdentityQuestionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = [cases.resolve(cid, vid) for cid, authored in cases.all_cases().items()
                     for vid in ['base'] + [v['id'] for v in authored.get('variants', [])]]

    def test_preferred_address_paraphrases_across_every_path(self):
        prompts = [
            "hi I'm student Dr Sebastian how may I address you today",
            'How would you like me to address you?',
            'How should I refer to you?', 'How do I address you?',
            'What should I call you?', "What would you prefer I call you?",
            'What name do you go by?', 'What name should I use?',
            'Do you have a preferred name?', 'What is your preferred form of address?',
            'How do you like to be addressed?', 'What would you like to be called?',
            'May I ask what you prefer to be called?',
        ]
        for case in self.paths:
            for question in prompts:
                with self.subTest(case=case['id'], question=question):
                    reply, meta = patient.PatientEngine(case).respond(question, {})
                    self.assertIn(case['patient']['name'], reply)
                    self.assertEqual(meta['identity_fields'], ['name'])
                    self.assertEqual(meta['kind'], 'identity_response')
                    self.assertEqual(meta['facts_released'], [])
                    self.assertEqual(meta['concepts'], {})
                    self.assertNotIn('years old', reply)
                    self.assertFalse(meta.get('checklist_hits'))

    def test_name_age_and_compound_opening_across_every_path(self):
        for case in self.paths:
            for question in [
                'What is your name and how old are you?',
                'Can you confirm your full name and age?',
                "Hello, I'm Dr Sebastian. How may I address you and how old are you?",
            ]:
                with self.subTest(case=case['id'], question=question):
                    reply, meta = patient.PatientEngine(case).respond(question, {})
                    self.assertIn(case['patient']['name'], reply)
                    self.assertIn(f"{case['patient']['age']} years old", reply)
                    self.assertEqual(set(meta['identity_fields']), {'name', 'age'})
                    self.assertEqual(meta['facts_released'], [])
                    self.assertEqual(meta['concepts'], {})
            for question in [
                "Hi I'm Dr Sebastian how may I address you and how old are you and what brings you in today?",
                'May I ask your name, age, and reason for visit?',
                'Could you tell me your full name, age, and reason for your visit?',
                'What is your name how old are you what brings you in today?',
            ]:
                with self.subTest(case=case['id'], question=question):
                    reply, meta = patient.PatientEngine(case).respond(question, {})
                    self.assertIn(case['patient']['name'], reply)
                    self.assertIn(f"{case['patient']['age']} years old", reply)
                    self.assertIn(case['patient']['opening'], reply)
                    self.assertEqual(set(meta['identity_fields']), {'name', 'age'})
                    _, opening_meta = patient.PatientEngine(case).respond('What brings you in today?', {})
                    self.assertEqual(set(meta['facts_released']), set(opening_meta['facts_released']))
                    self.assertEqual(meta['concepts'], opening_meta['concepts'])
                    self.assertFalse(meta.get('unanswered_asks'))

    def test_age_paraphrases_are_current_patient_age(self):
        for case in self.paths:
            for question in ['How old are you?', 'Could you tell me how old you are?',
                             'What age are you?', 'May I know your age?',
                             'Can you confirm your current age?', 'Your age?']:
                with self.subTest(case=case['id'], question=question):
                    reply, meta = patient.PatientEngine(case).respond(question, {})
                    self.assertEqual(reply, f"I am {case['patient']['age']} years old.")
                    self.assertEqual(meta['identity_fields'], ['age'])

    def test_other_topics_are_not_patient_identity(self):
        for question in [
            'How old is your mother?', 'How old were you when this started?',
            'How old are you when the pain starts?', 'What is your age at the onset?',
            'What is your address?', 'Where do you live?', 'Who are you living with?',
            'How should I address your pain?', 'What is the name of your medication?',
            "What is your mother's name?", 'At your age do you exercise?',
            'How long have you had this?', 'How old is the scar?',
        ]:
            with self.subTest(question=question):
                self.assertNotEqual(patient.conversation_route(question), 'identity')
                self.assertNotIn('age', dialogue.subjects_in(question))

    def test_other_history_in_compound_is_preserved(self):
        case = cases.resolve('cardio-palpitations', 'base')
        for topic in ['what medications do you take', 'do you have any allergies',
                      'what do you do for work', 'when did the symptoms start']:
            question = 'How may I address you, and ' + topic + '?'
            with self.subTest(question=question):
                reply, meta = patient.PatientEngine(case).respond(question, {})
                alone, alone_meta = patient.PatientEngine(case).respond(topic + '?', {})
                self.assertIn(case['patient']['name'], reply)
                self.assertIn(alone, reply)
                self.assertEqual(meta['facts_released'], alone_meta['facts_released'])
                self.assertEqual(meta['concepts'], alone_meta['concepts'])
                self.assertEqual(meta['identity_fields'], ['name'])

    def test_courtesy_components_follow_the_actual_identity_questions(self):
        for ending in ['', '?']:
            question = "hi I'm student Dr Sebastian how may I address you today" + ending
            hits = {h['id']: h['matched_components'] for h in engine._courtesy_hits(question)}
            self.assertIn('introduce', hits)
            self.assertEqual(hits['confirm_name'], ['preferred_address'])
        for question, components in [
            ('How would you like me to address you?', ['preferred_address']),
            ('Can you confirm your name?', ['name']),
            ('What is your name and what name do you go by?', ['name', 'preferred_address']),
        ]:
            with self.subTest(question=question):
                hits = {h['id']: h['matched_components'] for h in engine._courtesy_hits(question)}
                self.assertEqual(hits['confirm_name'], components)
        for question in ['How old are you?', 'What is your address?',
                         "I will not ask your name", "I will not ask how you would like to be addressed",
                         'Did your student Dr introduce himself?', 'Are you a student doctor?']:
            with self.subTest(question=question):
                hits = {h['id'] for h in engine._courtesy_hits(question)}
                self.assertFalse(hits & {'confirm_name', 'introduce'})

    def test_missing_or_preferred_demographics_are_not_invented(self):
        case = copy.deepcopy(self.paths[0])
        case['patient'].pop('age')
        reply, meta = patient.PatientEngine(case).respond('How old are you?', {})
        self.assertNotIn('years old', reply)
        self.assertEqual(meta['identity_fields'], [])
        self.assertTrue(meta['no_information'])
        case['patient']['preferred_name'] = 'Rae'
        reply, meta = patient.PatientEngine(case).respond('How should I address you?', {})
        self.assertEqual(reply, 'You can call me Rae.')
        self.assertEqual(meta['identity_fields'], ['preferred_name'])
        self.assertNotIn(case['patient']['name'], reply)


if __name__ == '__main__':
    unittest.main()
