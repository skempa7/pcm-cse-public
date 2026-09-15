from sparse_case_fixtures import resolve as sparse_resolve
"""Dietary history and closing conversation respect the actual question and source."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pcmcse import cases, config, db, engine, evidence, patient, record


class SocialClosureTests(unittest.TestCase):
    def ready(self, case_id='cardio-palpitations', variant='base'):
        case = sparse_resolve(case_id, variant)
        return case, patient.PatientEngine(case), {}

    def mara_variants(self):
        return ['base'] + [v['id'] for v in cases.get('cardio-palpitations')['variants']]

    def assert_scope(self, case, reply, meta, allowed, required=()):
        released = set(meta.get('facts_released', []))
        self.assertLessEqual(released, set(allowed), (reply, meta))
        self.assertGreaterEqual(released, set(required), (reply, meta))
        definitions = {f['id']: f for f in case['facts']}
        allowed_concepts = {key for fid in allowed for key in definitions[fid].get('concepts', {})}
        self.assertLessEqual(set(meta.get('concepts', {})), allowed_concepts, (reply, meta))
        for fid in released:
            delivered = patient.delivered_fact_metadata(definitions[fid], reply) or {}
            self.assertIn(fid, delivered.get('facts_released', []), (reply, meta))

    def assert_diet_unavailable(self, case, reply, meta):
        self.assert_scope(case, reply, meta, set())
        unresolved_diet = any('diet' in ask.lower() or 'eat' in ask.lower() for ask in meta.get('unanswered_asks', []))
        self.assertTrue(meta.get('no_information') or unresolved_diet, (reply, meta))
        self.assertFalse(meta.get('checklist_hits'), (reply, meta))
        self.assertRegex(reply.lower(), r'diet|eating|food|meals|breakfast|lunch|dinner')
        self.assertRegex(reply.lower(), r'not sure|cannot|can.t|unavailable|unspecified|not (?:provid|specif|know)|no information|don.t know')
        self.assertNotRegex(reply.lower(), r'fast and irregular|palpitation|hard beat|3 energy drinks|three energy drinks')
        self.assertNotRegex(reply.lower(), r'i (?:eat|follow|have) (?:a )?(?:healthy|unhealthy|balanced|normal|unrestricted|vegetarian)|i skip|i avoid|\d+ calories')

    def assert_closure_exhausted(self, case, reply, meta):
        self.assert_scope(case, reply, meta, set())
        self.assertFalse(meta.get('checklist_hits'), (reply, meta))
        self.assertRegex(reply.lower(), r'additional|anything else|more|further')
        self.assertNotRegex(reply.lower(), r'\bno (?:other |more )?(?:concerns|questions|symptoms)|nothing (?:else )?wrong|all my (?:questions|concerns).*answered')
        self.assertNotRegex(reply.lower(), r'what do you mean|could you rephrase')

    def test_reported_diet_question_is_unavailable_on_all_mara_variants(self):
        for variant in self.mara_variants():
            with self.subTest(variant=variant):
                case, patient_engine, state = self.ready(variant=variant)
                reply, meta = patient_engine.respond('how would you describe your diet', state)
                self.assert_diet_unavailable(case, reply, meta)

    def test_common_diet_phrasings_do_not_trigger_symptom_character(self):
        questions = ['What is your diet like?', 'Tell me about your eating habits.',
                     'What do you normally eat?', 'How would you describe what you eat?',
                     'What does a typical day of meals look like?']
        for question in questions:
            with self.subTest(question=question):
                case, patient_engine, state = self.ready()
                patient_engine.respond('What do the palpitations feel like?', state)
                reply, meta = patient_engine.respond(question, state)
                self.assert_diet_unavailable(case, reply, meta)

    def test_diet_question_does_not_reuse_caffeine_as_a_complete_diet(self):
        case, patient_engine, state = self.ready()
        patient_engine.respond('How many energy drinks do you drink?', state)
        reply, meta = patient_engine.respond('How would you describe your diet?', state)
        self.assert_diet_unavailable(case, reply, meta)

    def test_unavailable_diet_followups_do_not_reuse_symptom_quality_or_timeline(self):
        for question in ['What do you usually eat for breakfast?', 'What about lunch?',
                         'How long?', 'How long have you eaten that way?']:
            with self.subTest(question=question):
                case, patient_engine, state = self.ready()
                patient_engine.respond('What do the palpitations feel like?', state)
                patient_engine.respond('When did the palpitations start?', state)
                patient_engine.respond('How would you describe your diet?', state)
                reply, meta = patient_engine.respond(question, state)
                self.assert_diet_unavailable(case, reply, meta)
                self.assertNotRegex(reply.lower(), r'2 weeks|two weeks|6 hours|six hours|continuous')

    def test_bare_anything_else_does_not_start_the_new_explicit_closing_queue(self):
        from pcmcse import social_history
        # This broad invitation retains the existing disclosure budget.
        self.assertFalse(social_history.closing_invitation('Anything else?'))

    def test_authored_diet_answers_remain_available_with_their_actual_scope(self):
        fixtures = [('cardio-chest-pressure', 'history_diet', r'takeout'),
                    ('neuro-distal-neuropathy', 'history_diet', r'unrestricted diet')]
        for cid, fid, wording in fixtures:
            for question in ['How would you describe your diet?', 'What is your diet like?']:
                with self.subTest(case=cid, question=question):
                    case, patient_engine, state = self.ready(cid)
                    reply, meta = patient_engine.respond(question, state)
                    self.assert_scope(case, reply, meta, {fid}, {fid})
                    self.assertRegex(reply.lower(), wording)
                    self.assertNotRegex(reply.lower(), r'\d+ calories|every (?:day|meal)|vegetarian|balanced diet')

    def test_food_trigger_question_keeps_the_authored_pain_aggravator(self):
        case, patient_engine, state = self.ready('gi-right-upper-pain')
        reply, meta = patient_engine.respond('Does eating make the pain worse?', state)
        self.assert_scope(case, reply, meta, {'hpi_aggravating'}, {'hpi_aggravating'})
        self.assertRegex(reply.lower(), r'eating.*worsen')
        self.assertNotRegex(reply.lower(), r'diet.*unavailable|diet.*not provided')

    def test_diet_question_plus_identity_answers_both_without_inventing_diet(self):
        case, patient_engine, state = self.ready()
        reply, meta = patient_engine.respond('What is your name, and how would you describe your diet?', state)
        self.assert_diet_unavailable(case, reply, meta)
        self.assertIn(case['patient']['name'], reply)
        self.assertIn('name', meta.get('identity_fields', []))

    def test_repeated_broad_closing_invites_advance_through_authored_concerns(self):
        for variant in self.mara_variants():
            with self.subTest(variant=variant):
                case, patient_engine, state = self.ready(variant=variant)
                concerns = case['patient']['closing_questions']
                replies = []
                for concern in concerns:
                    reply, meta = patient_engine.respond('Is there anything else you would like to discuss?', state)
                    self.assertIn(concern, reply)
                    self.assertNotIn(reply, replies)
                    replies.append(reply)
                reply, meta = patient_engine.respond('Is there anything else you would like to discuss?', state)
                self.assert_closure_exhausted(case, reply, meta)

    def test_alternate_closing_invites_share_the_same_progress(self):
        case, patient_engine, state = self.ready(variant='cardio-palpitations--communication')
        questions = ['Do you have any questions for me?', 'Any other concerns?',
                     'Is there anything else you want me to know?']
        for question, concern in zip(questions, case['patient']['closing_questions']):
            reply, meta = patient_engine.respond(question, state)
            self.assertIn(concern, reply)
        reply, meta = patient_engine.respond('Anything else you would like to ask?', state)
        self.assert_closure_exhausted(case, reply, meta)

    def test_already_delivered_barrier_is_not_repeated_by_a_broad_invitation(self):
        case, patient_engine, state = self.ready(variant='cardio-palpitations--communication')
        reply, meta = patient_engine.respond('What might make it hard to follow the plan?', state)
        self.assert_scope(case, reply, meta, {'care_barrier'}, {'care_barrier'})
        next_reply, next_meta = patient_engine.respond('Is there anything else you would like to discuss?', state)
        self.assertNotIn(reply, next_reply)
        self.assertIn(case['patient']['closing_questions'][1], next_reply)
        self.assertNotIn('care_barrier', next_meta.get('facts_released', []))

    def test_concerns_spoken_at_closing_receive_only_their_supported_evidence(self):
        case, patient_engine, state = self.ready(variant='cardio-palpitations--communication')
        ledger = evidence.Ledger()
        for expected in ['care_barrier', 'patient_concern']:
            question = 'Do you have any questions for me?'
            reply, meta = patient_engine.respond(question, state)
            self.assert_scope(case, reply, meta, {expected}, {expected})
            ledger.add(evidence.STUDENT, question)
            ledger.add(evidence.PATIENT, reply, meta=meta)
        self.assertEqual(set(ledger.released_facts()), {'care_barrier', 'patient_concern'})
        reply, meta = patient_engine.respond('Do you have any more questions for me?', state)
        self.assertIn(case['patient']['closing_questions'][2], reply)
        self.assert_scope(case, reply, meta, set())
        self.assertFalse(meta.get('checklist_hits'), (reply, meta))

    def test_specific_barrier_question_still_works_after_the_closing_invite(self):
        case, patient_engine, state = self.ready(variant='cardio-palpitations--communication')
        patient_engine.respond('Is there anything else you would like to discuss?', state)
        reply, meta = patient_engine.respond('What might make it hard to follow the plan?', state)
        self.assert_scope(case, reply, meta, {'care_barrier'}, {'care_barrier'})
        self.assertRegex(reply.lower(), r'work nights.*energy drinks')

    def test_attending_handoff_is_acknowledged_without_claiming_action_or_findings(self):
        announcements = ["okay now I'm going to let my attending physician know and will be right back",
                         "I'm going to discuss this with my attending and come right back.",
                         "I will update my attending physician. I'll be right back."]
        for announcement in announcements:
            with self.subTest(announcement=announcement):
                case, patient_engine, state = self.ready()
                patient_engine.respond('What do the palpitations feel like?', state)
                before_consents = state.get('consents', 0)
                reply, meta = patient_engine.respond(announcement, state)
                self.assert_scope(case, reply, meta, set())
                self.assertFalse(meta.get('checklist_hits'), (reply, meta))
                self.assertEqual(state.get('consents', 0), before_consents)
                self.assertNotEqual(meta.get('kind'), 'consent')
                self.assertRegex(reply.lower(), r'okay|\bok\b|understand|all right|alright|sure|thank')
                self.assertNotRegex(reply.lower(), r'what do you mean|not sure|rephrase|examin.*completed|attending (?:has |was )?(?:notified|updated)')

    def test_attending_announcement_does_not_swallow_a_question(self):
        case, patient_engine, state = self.ready()
        reply, meta = patient_engine.respond("I'm going to discuss this with my attending. Before I go, what medications do you take?", state)
        medication_ids = {f['id'] for f in case['facts'] if f['category'] == 'medications'}
        self.assert_scope(case, reply, meta, medication_ids, {'history_medications_1'})
        self.assertRegex(reply.lower(), r'amlodipine.*5 mg.*daily')
        self.assertRegex(reply.lower(), r'okay|\bok\b|understand|all right|alright|sure|thank')
        self.assertNotRegex(reply.lower(), r'what do you mean|attending (?:has been|was) notified')

    def test_question_then_attending_announcement_still_answers_the_question(self):
        case, patient_engine, state = self.ready('cardio-chest-pressure')
        reply, meta = patient_engine.respond("How would you describe your diet? I'm going to update my attending and be right back.", state)
        self.assert_scope(case, reply, meta, {'history_diet'}, {'history_diet'})
        self.assertIn('takeout', reply.lower())
        self.assertRegex(reply.lower(), r'okay|\bok\b|understand|all right|alright|sure|thank')
        self.assertNotRegex(reply.lower(), r'what do you mean|not sure')

    def test_session_handoff_does_not_end_pause_examine_or_change_evidence(self):
        with tempfile.TemporaryDirectory(prefix='cse-social-session-') as folder:
            with patch.object(db, 'DB_PATH', str(Path(folder) / 'attempts.db')):
                db.init()
                for mode in ['guided', 'coached', 'independent', 'rehearsal']:
                    with self.subTest(mode=mode):
                        case = sparse_resolve('cardio-palpitations', 'base')
                        preset = config.preset_for_learning_mode(mode)
                        settings = dict(config.load_settings(), learning_mode=mode, preset=preset,
                                        simulation_runtime='immediate')
                        sid = db.create_session(case['id'], preset, 'type', mode == 'guided', settings, case=case)
                        session = engine.load(sid)
                        session.start_encounter()
                        session.student_turn('Any weight changes?')
                        session = engine.load(sid)
                        before = (session.row['phase'], session.row['phase_started_at'], session.row['phase_ends_at'],
                                  session.pstate.get('consents', 0), session.ledger.released_concepts(),
                                  session.ledger.released_facts())
                        after_seq = len(session.ledger.events)
                        session.student_turn("okay now I'm going to let my attending physician know and will be right back")
                        session = engine.load(sid)
                        self.assertEqual((session.row['phase'], session.row['phase_started_at'], session.row['phase_ends_at'],
                                          session.pstate.get('consents', 0), session.ledger.released_concepts(),
                                          session.ledger.released_facts()), before)
                        added = session.ledger.events[after_seq:]
                        self.assertFalse([ev for ev in added if ev['kind'] in
                                          (evidence.EXAM_ACTION, evidence.EXAM_FINDING, evidence.EXAM_REFUSED)])
                        replies = [ev for ev in added if ev['kind'] == evidence.PATIENT]
                        self.assertEqual(len(replies), 1)
                        self.assertRegex(replies[0]['text'].lower(), r'okay|\bok\b|understand|all right|alright|sure|thank')
                        self.assertNotRegex(replies[0]['text'].lower(), r'what do you mean|not sure')


if __name__ == '__main__':
    unittest.main()
