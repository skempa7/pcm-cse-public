"""Allergy questions preserve allergen scope and actually obtained evidence."""
import unittest

from pcmcse import audit, cases, evidence, note, patient, record


class AllergyScopeTests(unittest.TestCase):
    ENVIRONMENTAL = {
        'heent-sore-throat': ('hpi_aggravating', r'dust|pollen', r'sneez', r'itch'),
        'pulm-episodic-wheeze': ('symptom_rhinorrhea', r'pollen', r'nose', r'run'),
    }

    def ready(self, case_id='cardio-palpitations', variant='base'):
        case = cases.resolve(case_id, variant)
        return case, patient.PatientEngine(case), {}

    def all_paths(self):
        for cid, base in cases.all_cases().items():
            for variant in ['base'] + [v['id'] for v in base.get('variants', [])]:
                yield cid, variant, cases.resolve(cid, variant)

    def assert_scope(self, case, reply, meta, allowed, required=()):
        released = set(meta.get('facts_released', []))
        self.assertLessEqual(released, set(allowed), (reply, meta))
        self.assertGreaterEqual(released, set(required), (reply, meta))
        self.assertFalse(meta.get('volunteered'), (reply, meta))
        definitions = {f['id']: f for f in case['facts']}
        for fid in released:
            delivered = patient.delivered_fact_metadata(definitions[fid], reply) or {}
            self.assertIn(fid, delivered.get('facts_released', []), (reply, meta))
        allowed_concepts = {
            key for fid in allowed for key in definitions[fid].get('concepts', {})
        }
        self.assertLessEqual(set(meta.get('concepts', {})), allowed_concepts, (reply, meta))

    def assert_unavailable(self, case, reply, meta, scope):
        self.assert_scope(case, reply, meta, set())
        self.assertTrue(meta.get('no_information'), (reply, meta))
        self.assertRegex(reply.lower(), scope)
        self.assertRegex(reply.lower(), r'not (?:have|provided|available|know|specified)|no (?:information|details)|unavailable|unspecified|don.t (?:have|know)|cannot|can.t|not sure|case (?:does not|doesn.t)')
        self.assertNotRegex(reply.lower(), r'(?:i (?:have|have had|know of) no|i (?:do not|don.t) have any|no known) (?:food |environmental |pet |latex |peanut )?allerg')
        self.assertFalse(meta.get('checklist_hits'), (reply, meta))

    def add_reply(self, engine, state, ledger, question):
        reply, meta = engine.respond(question, state)
        ledger.add(evidence.STUDENT, question)
        ledger.add(evidence.PATIENT, reply, meta=meta)
        return reply, meta

    def summary_ids(self, case, ledger):
        summary = record.summarize(case, ledger.events)
        return {row['fact_id'] for group in summary['groups']
                for section in group['sections'] for row in section['items']}

    def test_food_allergy_is_unspecified_on_every_authored_case_path(self):
        paths = 0
        for cid, variant, case in self.all_paths():
            for question in ['Do you have any food allergies?', 'Are you allergic to any foods?']:
                with self.subTest(case=cid, variant=variant, question=question):
                    reply, meta = patient.PatientEngine(case).respond(question, {})
                    self.assert_unavailable(case, reply, meta, r'food')
            paths += 1
        self.assertEqual(paths, 82)

    def test_broad_and_medication_allergy_questions_still_obtain_authored_drug_history(self):
        for cid, variant, case in self.all_paths():
            drug_ids = {f['id'] for f in case['facts'] if f['category'] == 'allergies'}
            extra = {self.ENVIRONMENTAL[cid][0]} if cid in self.ENVIRONMENTAL else set()
            for question in ['Do you have any allergies?', 'Do you have any medication allergies?']:
                with self.subTest(case=cid, variant=variant, question=question):
                    reply, meta = patient.PatientEngine(case).respond(question, {})
                    self.assert_scope(case, reply, meta, drug_ids | extra, drug_ids)

    def test_reported_environmental_then_food_questions_do_not_release_penicillin(self):
        case, engine, state = self.ready()
        for question, scope in [('Do you have any environmental allergies?', r'environment|seasonal'),
                                ('Do you have any food allergies?', r'food'),
                                ('What happens?', r'food')]:
            reply, meta = engine.respond(question, state)
            self.assert_unavailable(case, reply, meta, scope)
            self.assertNotRegex(reply.lower(), r'penicillin|hives')

    def test_explicit_drug_reaction_and_its_followup_remain_answerable(self):
        for first in ['Do you have any drug allergies?', 'What reaction do you have to penicillin?']:
            with self.subTest(first=first):
                case, engine, state = self.ready()
                for question in [first, 'What happens?']:
                    reply, meta = engine.respond(question, state)
                    self.assert_scope(case, reply, meta, {'history_allergies_1'}, {'history_allergies_1'})
                    self.assertRegex(reply.lower(), r'penicillin.*hives')

    def test_authored_environmental_answers_release_only_the_related_symptom(self):
        for cid, (fid, *patterns) in self.ENVIRONMENTAL.items():
            for question in ['Do you have any environmental allergies?', 'Do you have seasonal allergies?',
                             'Are you allergic to pollen?']:
                with self.subTest(case=cid, question=question):
                    case, engine, state = self.ready(cid)
                    reply, meta = engine.respond(question, state)
                    self.assert_scope(case, reply, meta, {fid}, {fid})
                    for pattern in patterns:
                        self.assertRegex(reply.lower(), pattern)
                    self.assertNotRegex(reply.lower(), r'heartburn|reflux|antacid|cetirizine|no other chronic|no known|trimethoprim|sulfamethoxazole|rash when i was')

    def test_environmental_reaction_followup_keeps_the_environmental_fact(self):
        for cid, (fid, *_) in self.ENVIRONMENTAL.items():
            with self.subTest(case=cid):
                case, engine, state = self.ready(cid)
                engine.respond('Do you have any environmental allergies?', state)
                reply, meta = engine.respond('What happens?', state)
                self.assert_scope(case, reply, meta, {fid}, {fid})

    def test_food_and_environmental_compound_answers_each_scope_separately(self):
        for cid, (fid, *_) in self.ENVIRONMENTAL.items():
            for question in ['Do you have food or environmental allergies?',
                             'Any environmental allergies, and any food allergies?']:
                with self.subTest(case=cid, question=question):
                    case, engine, state = self.ready(cid)
                    reply, meta = engine.respond(question, state)
                    self.assert_scope(case, reply, meta, {fid}, {fid})
                    self.assertRegex(reply.lower(), r'food')
                    self.assertRegex(reply.lower(), r'information|unspecified|not provided|not sure|don.t know|do not know')
                    self.assertNotRegex(reply.lower(), r'no (?:known )?food allergies')

    def test_drug_and_food_compound_preserves_drug_fact_and_food_uncertainty(self):
        for question in ['Do you have any medication or food allergies?',
                         'Any food allergies, and what happens when you take penicillin?']:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                reply, meta = engine.respond(question, state)
                self.assert_scope(case, reply, meta, {'history_allergies_1'}, {'history_allergies_1'})
                self.assertRegex(reply.lower(), r'penicillin.*hives')
                self.assertRegex(reply.lower(), r'food')
                self.assertRegex(reply.lower(), r'information|unspecified|not provided|not sure|don.t know|do not know')
                self.assertNotRegex(reply.lower(), r'no (?:known )?food allergies')

    def test_unknown_food_replaces_previous_drug_followup_context(self):
        case, engine, state = self.ready()
        engine.respond('What medication allergies do you have?', state)
        for question in ['Any food allergies?', 'What happens?', 'What reaction do you get?']:
            reply, meta = engine.respond(question, state)
            self.assert_unavailable(case, reply, meta, r'food')
            self.assertNotRegex(reply.lower(), r'penicillin|hives')

    def test_unknown_food_replaces_previous_environmental_followup_context(self):
        case, engine, state = self.ready('heent-sore-throat')
        engine.respond('Any environmental allergies?', state)
        for question in ['Any food allergies?', 'What happens?']:
            reply, meta = engine.respond(question, state)
            self.assert_unavailable(case, reply, meta, r'food')
            self.assertNotRegex(reply.lower(), r'pollen|dust|sneeze|eyes itch')

    def test_specific_unprovided_allergens_do_not_borrow_other_allergy_answers(self):
        questions = [('Are you allergic to peanuts?', r'peanut|food'),
                     ('Do you have any pet allergies?', r'pet|cat|dog|environment'),
                     ('Are you allergic to cats or dogs?', r'pet|cat|dog|environment'),
                     ('Are you allergic to latex?', r'latex')]
        for cid in ['cardio-palpitations', 'heent-sore-throat', 'pulm-episodic-wheeze', 'skin-contact-rash']:
            for question, scope in questions:
                with self.subTest(case=cid, question=question):
                    case, engine, state = self.ready(cid)
                    reply, meta = engine.respond(question, state)
                    self.assert_unavailable(case, reply, meta, scope)

    def test_named_drug_uses_authored_universal_denial_without_borrowing_another_drug(self):
        for question in ['Are you allergic to aspirin?', 'Do you have an aspirin allergy?']:
            for cid in ['heent-sore-throat', 'skin-contact-rash']:
                with self.subTest(case=cid, question=question):
                    case, engine, state = self.ready(cid)
                    reply, meta = engine.respond(question, state)
                    self.assert_scope(case, reply, meta, {'history_drug_reactions'}, {'history_drug_reactions'})
                    self.assertRegex(reply.lower(), r'no known (?:drug|medication) allergies')
            with self.subTest(case='cardio-palpitations', question=question):
                case, engine, state = self.ready()
                reply, meta = engine.respond(question, state)
                self.assert_unavailable(case, reply, meta, r'aspirin')
                self.assertNotRegex(reply.lower(), r'penicillin|hives')

    def test_shared_allergy_prefix_does_not_turn_medicine_into_a_medication_list(self):
        case, engine, state = self.ready()
        reply, meta = engine.respond('Do you have allergies to food or medicine?', state)
        self.assert_scope(case, reply, meta, {'history_allergies_1'}, {'history_allergies_1'})
        self.assertRegex(reply.lower(), r'penicillin.*hives')
        self.assertRegex(reply.lower(), r'food allergies')
        self.assertRegex(reply.lower(), r'not specify|unavailable|no information')
        self.assertNotRegex(reply.lower(), r'amlodipine|multivitamin')

    def test_plural_food_followup_replaces_medication_allergy_scope(self):
        case, engine, state = self.ready()
        engine.respond('Do you have any medication allergies?', state)
        reply, meta = engine.respond('What about foods?', state)
        self.assert_unavailable(case, reply, meta, r'food')
        self.assertNotRegex(reply.lower(), r'penicillin|hives')

    def test_questions_about_another_person_do_not_release_the_patients_allergies(self):
        for cid in ['cardio-palpitations', 'heent-sore-throat']:
            with self.subTest(case=cid):
                case, engine, state = self.ready(cid)
                reply, meta = engine.respond('Does your husband have environmental allergies?', state)
                self.assert_scope(case, reply, meta, set())
                self.assertTrue(meta.get('no_information'), (reply, meta))
                self.assertNotRegex(reply.lower(), r'penicillin|pollen|sneez|eyes itch')

    def test_proposed_testing_or_diagnosis_does_not_confirm_environmental_history(self):
        for cid in ['cardio-palpitations', 'heent-sore-throat']:
            for question in ['We should test you for environmental allergies',
                             'You might have environmental allergies']:
                with self.subTest(case=cid, question=question):
                    case, engine, state = self.ready(cid)
                    reply, meta = engine.respond(question, state)
                    self.assert_scope(case, reply, meta, set())
                    self.assertFalse(meta.get('checklist_hits'), (reply, meta))
                    self.assertNotRegex(reply.lower(), r'penicillin|pollen|sneez|eyes itch')

    def test_other_allergies_question_does_not_repeat_the_explicitly_excluded_drug(self):
        case, engine, state = self.ready()
        engine.respond('What medication allergies do you have?', state)
        reply, meta = engine.respond('Any other drug allergies besides penicillin?', state)
        self.assert_unavailable(case, reply, meta, r'other.*(?:medication|drug).*allerg')
        self.assertNotRegex(reply.lower(), r'penicillin causes|hives')

    def test_mixed_named_known_and_unknown_allergens_are_both_addressed(self):
        examples = [('cardio-palpitations', 'Are you allergic to penicillin or aspirin?',
                     'history_allergies_1', r'penicillin.*hives', r'aspirin'),
                    ('heent-sore-throat', 'Are you allergic to pollen or cats?',
                     'hpi_aggravating', r'pollen.*sneez', r'pets|cats')]
        for cid, question, fid, known, unknown in examples:
            with self.subTest(case=cid, question=question):
                case, engine, state = self.ready(cid)
                reply, meta = engine.respond(question, state)
                self.assert_scope(case, reply, meta, {fid}, {fid})
                self.assertRegex(reply.lower(), known)
                self.assertRegex(reply.lower(), unknown)
                self.assertRegex(reply.lower(), r'not specify|unavailable|no information')

    def test_named_drug_followup_can_change_away_from_unavailable_food_history(self):
        case, engine, state = self.ready()
        engine.respond('Do you have any food allergies?', state)
        reply, meta = engine.respond('What about penicillin?', state)
        self.assert_scope(case, reply, meta, {'history_allergies_1'}, {'history_allergies_1'})
        self.assertRegex(reply.lower(), r'penicillin.*hives')
        self.assertNotRegex(reply.lower(), r'food')

    def test_food_triggered_pain_is_answered_as_a_symptom_not_a_food_allergy(self):
        case, engine, state = self.ready('gi-right-upper-pain')
        reply, meta = engine.respond('Does eating make the pain worse?', state)
        self.assert_scope(case, reply, meta, {'hpi_aggravating'}, {'hpi_aggravating'})
        self.assertRegex(reply.lower(), r'eating.*worsen')
        reply, meta = engine.respond('Does that mean you have a food allergy?', state)
        self.assert_unavailable(case, reply, meta, r'food')
        self.assertNotRegex(reply.lower(), r'codeine|nausea|eating worsen')

    def test_inhaled_flour_trigger_does_not_establish_food_allergy(self):
        case, engine, state = self.ready('pulm-episodic-wheeze')
        reply, meta = engine.respond('Are you allergic to wheat or flour in food?', state)
        self.assert_unavailable(case, reply, meta, r'food|wheat|flour')
        self.assertNotRegex(reply.lower(), r'bakery|sets it off|better during')

    def test_unprovided_allergy_questions_add_no_clinical_notes_or_drug_evidence(self):
        case, engine, state = self.ready()
        ledger = evidence.Ledger()
        for question in ['Do you have any food allergies?', 'Any environmental allergies?', 'What happens?']:
            self.add_reply(engine, state, ledger, question)
        self.assertEqual(ledger.released_facts(), {})
        self.assertEqual(ledger.released_concepts(), {})
        self.assertEqual(self.summary_ids(case, ledger), set())
        checked = audit.audit_note(note.ParsedNote('Allergies: Penicillin causes hives.', '', [], []), ledger, case)
        self.assertTrue(checked['claims'])
        self.assertFalse(any(c['verdict'] in {'supported', 'supported_supplied'} for c in checked['claims']))

    def test_environmental_notes_contain_only_obtained_environmental_detail(self):
        for cid, (fid, *_) in self.ENVIRONMENTAL.items():
            with self.subTest(case=cid):
                case, engine, state = self.ready(cid)
                ledger = evidence.Ledger()
                self.add_reply(engine, state, ledger, 'Do you have any environmental allergies?')
                self.add_reply(engine, state, ledger, 'Do you have food allergies?')
                self.assertEqual(set(ledger.released_facts()), {fid})
                self.assertEqual(self.summary_ids(case, ledger), {fid})

    def test_explicit_drug_question_still_creates_valid_drug_documentation_evidence(self):
        case, engine, state = self.ready()
        ledger = evidence.Ledger()
        self.add_reply(engine, state, ledger, 'Do you have any food allergies?')
        self.add_reply(engine, state, ledger, 'Do you have any medication allergies?')
        self.assertEqual(self.summary_ids(case, ledger), {'history_allergies_1'})
        checked = audit.audit_note(note.ParsedNote('Allergies: Penicillin causes hives.', '', [], []), ledger, case)
        self.assertTrue(checked['claims'])
        self.assertTrue(all(c['verdict'] == 'supported' for c in checked['claims']), checked['claims'])


if __name__ == '__main__':
    unittest.main()
