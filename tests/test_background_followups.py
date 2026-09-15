from sparse_case_fixtures import resolve as sparse_resolve
"""Background-history follow-ups retain their topic and authored certainty."""
import unittest

from pcmcse import cases, patient


class BackgroundFollowupTests(unittest.TestCase):
    def ready(self, variant='base', case_id='cardio-palpitations'):
        case = sparse_resolve(case_id, variant)
        return case, patient.PatientEngine(case), {}

    def assert_only_facts(self, case, reply, meta, allowed, required=()):
        released = set(meta.get('facts_released', []))
        self.assertLessEqual(released, set(allowed), (reply, meta))
        self.assertGreaterEqual(released, set(required), (reply, meta))
        self.assertFalse(meta.get('volunteered'), (reply, meta))
        definitions = {f['id']: f for f in case['facts']}
        for fid in released:
            delivered = patient.delivered_fact_metadata(definitions[fid], reply) or {}
            self.assertIn(fid, delivered.get('facts_released', []), (reply, meta))

    def assert_workday_scope(self, reply):
        self.assertRegex(reply.lower(), r'\b(?:3|three)\b.*\bworkdays?\b')
        self.assertNotRegex(reply.lower(), r'^(?:yes|right|correct|that.s right)[,.! ]')
        self.assertNotRegex(reply.lower(), r'(?:i (?:always )?drink.*every day|seven days|7 days|(?:only|just) (?:on )?workdays|none on (?:weekends|days off)|never on (?:weekends|days off)|not on (?:weekends|days off))')

    def test_reported_sleep_caffeine_daily_sequence_stays_on_background_history(self):
        for variant in ['base'] + [v['id'] for v in cases.get('cardio-palpitations')['variants']]:
            with self.subTest(variant=variant):
                case, engine, state = self.ready(variant)
                engine.respond('What brings you in today?', state)
                sleep, sleep_meta = engine.respond('so do you get enough sleep', state)
                self.assertTrue(sleep_meta.get('no_information'), (sleep, sleep_meta))
                self.assertRegex(sleep.lower(), r'sleep|rest')
                self.assert_only_facts(case, sleep, sleep_meta, {'care_barrier'})
                reply, meta = engine.respond('how many energy drinks do you typically drink', state)
                self.assert_only_facts(case, reply, meta, {'history_caffeine'}, {'history_caffeine'})
                budget = state['open_budget']
                reply, meta = engine.respond('do you do this every day', state)
                self.assert_only_facts(case, reply, meta, {'history_caffeine'}, {'history_caffeine'})
                self.assert_workday_scope(reply)
                self.assertNotRegex(reply.lower(), r'walking|less energy|uncomfortable')
                self.assertEqual(state['open_budget'], budget)

    def test_common_frequency_followups_use_the_last_caffeine_answer(self):
        for question in ['Every day?', 'Is that daily?', 'Do you do that every day?',
                         'How often?', 'How often do you drink them?', 'How many a day?']:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                engine.respond('How many energy drinks do you typically drink?', state)
                reply, meta = engine.respond(question, state)
                self.assert_only_facts(case, reply, meta, {'history_caffeine'}, {'history_caffeine'})
                self.assert_workday_scope(reply)

    def test_days_off_are_not_inferred_from_workday_consumption(self):
        for question in ['Do you also drink them on weekends?', 'How many on days off?',
                         'Do you avoid energy drinks when you are not working?']:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                engine.respond('How many energy drinks do you typically drink?', state)
                reply, meta = engine.respond(question, state)
                self.assertTrue(meta.get('no_information'), (reply, meta))
                self.assert_only_facts(case, reply, meta, {'history_caffeine'})
                self.assertNotRegex(reply.lower(), r'^(?:yes|no|right|correct)[,.! ]')
                self.assertNotRegex(reply.lower(), r'(?:never|none|zero|don.t drink|do not drink).*?(?:weekends|days off|not working)')

    def test_alcohol_frequency_preserves_most_evenings_without_blanket_daily_yes(self):
        for question in ['Do you do this every day?', 'Is that every day?', 'How often?', 'How much?']:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                engine.respond('Do you drink alcohol?', state)
                reply, meta = engine.respond(question, state)
                self.assert_only_facts(case, reply, meta, {'alcohol_use'}, {'alcohol_use'})
                self.assertRegex(reply.lower(), r'(?:two|2) beers most evenings')
                self.assertNotRegex(reply.lower(), r'^(?:yes|right|correct|that.s right)[,.! ]')
                self.assertNotRegex(reply.lower(), r'energy drinks|every (?:day|evening)|nightly')

    def test_medication_frequency_and_dose_followups_use_the_disclosed_medicine(self):
        for question in ['Do you take that every day?', 'How often do you take it?', 'How much do you take?']:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                _, previous = engine.respond('What medications do you take?', state)
                reply, meta = engine.respond(question, state)
                self.assert_only_facts(case, reply, meta, previous['facts_released'], {'history_medications_1'})
                self.assertRegex(reply.lower(), r'amlodipine\s+(?:5|five)\s*(?:mg|milligrams).*daily')
                self.assertNotRegex(reply.lower(), r'beers|energy drinks|walking|less energy')

    def test_explicit_background_topic_switch_replaces_the_followup_anchor(self):
        case, engine, state = self.ready()
        for question, expected in [('How many energy drinks do you drink?', 'history_caffeine'),
                                   ('Do you drink alcohol?', 'alcohol_use'),
                                   ('What medications do you take?', 'history_medications_1')]:
            _, prior = engine.respond(question, state)
            reply, meta = engine.respond('How often?', state)
            self.assert_only_facts(case, reply, meta, prior['facts_released'], {expected})

    def test_explicit_symptom_question_is_not_overridden_by_a_background_anchor(self):
        case, engine, state = self.ready()
        engine.respond('How many energy drinks do you drink?', state)
        reply, meta = engine.respond('Are the palpitations constant or do they come and go?', state)
        self.assert_only_facts(case, reply, meta, {'hpi_timing', 'hpi_episode_duration'}, {'hpi_timing'})
        self.assertIn('continuous', reply.lower())

    def test_unanchored_short_followups_clarify_instead_of_releasing_hpi(self):
        for question in ['Do you do this every day?', 'Is that daily?', 'How often?', 'How many?']:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                reply, meta = engine.respond(question, state)
                self.assert_only_facts(case, reply, meta, set())
                self.assertRegex(reply.lower(), r'clarif|mean|referring|which|what.*(?:often|many|ask)')

    def test_unknown_sleep_question_does_not_leave_a_stale_caffeine_anchor(self):
        case, engine, state = self.ready()
        engine.respond('How many energy drinks do you drink?', state)
        engine.respond('Do you get enough sleep?', state)
        reply, meta = engine.respond('Is that every day?', state)
        self.assert_only_facts(case, reply, meta, set())
        self.assertTrue(meta.get('no_information') or meta.get('kind') in {'clarification', 'non_answer'}, (reply, meta))
        self.assertNotRegex(reply.lower(), r'3 energy drinks|three energy drinks|walking|less energy')

    def test_sleep_quality_and_hours_are_not_invented_for_mara(self):
        for variant in ['base'] + [v['id'] for v in cases.get('cardio-palpitations')['variants']]:
            for question in ['Do you get enough sleep?', 'How many hours do you sleep?', 'Do you sleep well?']:
                with self.subTest(variant=variant, question=question):
                    case, engine, state = self.ready(variant)
                    reply, meta = engine.respond(question, state)
                    self.assertTrue(meta.get('no_information'), (reply, meta))
                    self.assertRegex(reply.lower(), r'sleep|rest')
                    self.assert_only_facts(case, reply, meta, {'care_barrier'})
                    self.assertNotRegex(reply.lower(), r'\b(?:\d+|six|seven|eight|nine|ten)\s*hours?\b')
                    self.assertNotRegex(reply.lower(), r'(?:i (?:do |usually )?get enough sleep|i sleep (?:well|fine|normally)|i (?:do not|don.t) have trouble sleeping)')

    def test_authored_sleep_habits_can_be_answered_without_inventing_hours(self):
        case, engine, state = self.ready(case_id='neuro-recurrent-headache')
        reply, meta = engine.respond('How are your sleep habits?', state)
        self.assert_only_facts(case, reply, meta, {'history_context_1'}, {'history_context_1'})
        self.assertIn('cut back on sleep', reply.lower())
        self.assertNotRegex(reply.lower(), r'\b(?:\d+|six|seven|eight|nine|ten)\s*hours?\b')

    def test_additional_daily_pronouns_keep_the_caffeine_reference(self):
        for question in ['Do you drink these every day?', 'Do you do this every single day?']:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                engine.respond('How many energy drinks do you drink?', state)
                reply, meta = engine.respond(question, state)
                self.assert_only_facts(case, reply, meta, {'history_caffeine'}, {'history_caffeine'})
                self.assert_workday_scope(reply)

    def test_habit_duration_is_unavailable_when_only_frequency_is_authored(self):
        case, engine, state = self.ready()
        engine.respond('How many energy drinks do you drink?', state)
        reply, meta = engine.respond('For how many years?', state)
        self.assert_only_facts(case, reply, meta, set())
        self.assertTrue(meta.get('no_information'), (reply, meta))
        self.assertRegex(reply.lower(), r'duration|how long|years')
        self.assertNotRegex(reply.lower(), r'\b(?:\d+|one|two|three|four|five)\s+years?\b')

    def test_restfulness_then_hours_does_not_reuse_the_caffeine_reference(self):
        case, engine, state = self.ready()
        engine.respond('How many energy drinks do you drink?', state)
        for question in ['Do you feel well rested?', 'How many hours?']:
            reply, meta = engine.respond(question, state)
            self.assert_only_facts(case, reply, meta, set())
            self.assertTrue(meta.get('no_information'), (question, reply, meta))
            self.assertRegex(reply.lower(), r'sleep|rest')

    def test_compound_sleep_questions_do_not_release_unrelated_clinical_evidence(self):
        for question in ['How many hours do you sleep and do you get enough sleep?',
                         'Do you get enough sleep? How many hours do you get?']:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                reply, meta = engine.respond(question, state)
                self.assert_only_facts(case, reply, meta, set())
                self.assertTrue(meta.get('no_information'), (reply, meta))
                self.assertRegex(reply.lower(), r'sleep.*(?:duration|hours)|(?:duration|hours).*sleep')
                self.assertRegex(reply.lower(), r'sufficient|enough|rested')
                self.assertNotRegex(reply.lower(), r'walking|less energy|energy drinks')

    def test_mixed_caffeine_sleep_question_preserves_the_last_asked_sleep_context(self):
        case, engine, state = self.ready()
        engine.respond('How many energy drinks do you drink?', state)
        reply, meta = engine.respond('Do you do this every day, and how is your sleep?', state)
        self.assert_only_facts(case, reply, meta, {'history_caffeine'}, {'history_caffeine'})
        self.assert_workday_scope(reply)
        self.assertRegex(reply.lower(), r'sleep')
        reply, meta = engine.respond('How many hours?', state)
        self.assert_only_facts(case, reply, meta, set())
        self.assertTrue(meta.get('no_information'), (reply, meta))
        self.assertRegex(reply.lower(), r'sleep.*(?:duration|hours)|(?:duration|hours).*sleep')
        self.assertNotRegex(reply.lower(), r'energy drinks|walking|less energy')

    def test_explicit_heart_question_clears_the_old_caffeine_frequency_reference(self):
        case, engine, state = self.ready()
        engine.respond('How many energy drinks do you drink?', state)
        for question in ['Does your heart race every day?', 'How often?']:
            reply, meta = engine.respond(question, state)
            self.assert_only_facts(case, reply, meta, {'hpi_timing', 'hpi_episode_duration'})
            self.assertNotIn('energy drinks', reply.lower())

    def test_sleep_position_question_retains_its_specific_clinical_route(self):
        case, engine, state = self.ready(case_id='cardio-orthopnea-edema')
        reply, meta = engine.respond('How many pillows do you need to sleep comfortably?', state)
        self.assert_only_facts(case, reply, meta, {'symptom_orthopnea'}, {'symptom_orthopnea'})
        self.assertIn('3 pillows', reply)


if __name__ == '__main__':
    unittest.main()
