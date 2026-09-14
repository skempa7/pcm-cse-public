"""ROS questions change topic explicitly and keep unsupported symptoms unknown."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pcmcse import cases, config, db, engine, evidence, patient, record, ros_history


class ROSTopicSwitchingTests(unittest.TestCase):
    def ready(self, case_id='cardio-palpitations', variant='base'):
        case = cases.resolve(case_id, variant)
        return case, patient.PatientEngine(case), {}

    def mara_variants(self):
        return ['base'] + [v['id'] for v in cases.get('cardio-palpitations')['variants']]

    def assert_scope(self, case, reply, meta, allowed, required=()):
        released = set(meta.get('facts_released', []))
        self.assertLessEqual(released, set(allowed), (reply, meta))
        self.assertGreaterEqual(released, set(required), (reply, meta))
        self.assertFalse(meta.get('volunteered'), (reply, meta))
        definitions = {f['id']: f for f in case['facts']}
        allowed_concepts = {key for fid in allowed for key in definitions[fid].get('concepts', {})}
        self.assertLessEqual(set(meta.get('concepts', {})), allowed_concepts, (reply, meta))
        for fid in released:
            delivered = patient.delivered_fact_metadata(definitions[fid], reply) or {}
            self.assertIn(fid, delivered.get('facts_released', []), (reply, meta))

    def assert_unavailable(self, case, reply, meta, topic):
        self.assert_scope(case, reply, meta, set())
        self.assertTrue(meta.get('no_information'), (reply, meta))
        self.assertFalse(meta.get('checklist_hits'), (reply, meta))
        self.assertRegex(reply.lower(), topic)
        self.assertRegex(reply.lower(), r'not sure|cannot|can.t|unavailable|unspecified|not (?:provid|specif|know)|no information|don.t know')
        self.assertNotRegex(reply.lower(), r'\bi (?:have no|have never had|do not have|don.t have|deny)\b')
        self.assertNotRegex(reply.lower(), r'\bno (?:headaches?|nausea|vomiting|dizziness|chills|muscle aches|ringing|depress)')

    def add_reply(self, engine, state, ledger, question):
        reply, meta = engine.respond(question, state)
        ledger.add(evidence.STUDENT, question)
        ledger.add(evidence.PATIENT, reply, meta=meta)
        return reply, meta

    def test_reported_ros_sequence_never_repeats_a_previous_topic(self):
        for variant in self.mara_variants():
            with self.subTest(variant=variant):
                case, engine, state = self.ready(variant=variant)
                engine.respond('Have you had this before?', state)
                questions = [
                    ('any depressed thoughts', None, r'depress|mood'),
                    ('any fever', 'symptom_fever', r'fever'),
                    ('any weight changes', 'symptom_weight_loss', r'weight'),
                    ('how about any headaches', None, r'headache'),
                    ('any nausea or vomiting', None, r'nausea.*vomit|vomit.*nausea'),
                    ('any dizziness', None, r'dizz|lightheaded'),
                    ('any chills', None, r'chill'),
                    ('any muscle aches', None, r'muscle|myalgia|body ache'),
                    ('any ringing in your ears', None, r'ringing|tinnitus|ears'),
                ]
                for question, fid, topic in questions:
                    with self.subTest(question=question):
                        reply, meta = engine.respond(question, state)
                        if fid:
                            self.assert_scope(case, reply, meta, {fid}, {fid})
                            self.assertEqual(meta['concepts'][fid]['polarity'], 'negative')
                        else:
                            self.assert_unavailable(case, reply, meta, topic)

    def test_mood_questions_are_not_a_repetition_of_previous_palpitations(self):
        for question in ['Any depressed thoughts?', 'Have you been feeling depressed?',
                         'Any low mood?', 'Have you been feeling down?',
                         'How has your mood been?']:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                engine.respond('Have you had this before?', state)
                reply, meta = engine.respond(question, state)
                self.assert_unavailable(case, reply, meta, r'depress|mood|feeling down')
                self.assertNotRegex(reply.lower(), r'palpitation|episode|flutter|racing')

    def test_weight_to_headache_rewordings_change_the_topic(self):
        for question in ['How about any headaches?', 'What about headaches?',
                         'Have you had a headache?', 'And headaches?',
                         'Do you ever get headaches?']:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                engine.respond('Any weight changes?', state)
                reply, meta = engine.respond(question, state)
                self.assert_unavailable(case, reply, meta, r'headache')
                self.assertNotIn('weight', reply.lower())

    def test_muscle_aches_and_clinical_synonym_do_not_reuse_a_weight_answer(self):
        for question in ['Any muscle aches?', 'Have you had any muscle aches?',
                         'What about body aches?', 'Any myalgias?']:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                engine.respond('Any weight changes?', state)
                reply, meta = engine.respond(question, state)
                self.assert_unavailable(case, reply, meta, r'muscle|myalgia|body ache')
                self.assertNotIn('weight', reply.lower())

    def test_unprovided_ros_topics_are_not_invented_denials(self):
        questions = [('Do you feel nauseated?', r'nausea|nauseated|queasy'),
                     ('Have you thrown up?', r'vomit|throw|thrown'),
                     ('Have you been dizzy?', r'dizz'),
                     ('Any lightheadedness?', r'lightheaded|dizz'),
                     ('Have you had chills?', r'chill'),
                     ('Any tinnitus?', r'tinnitus|ringing|ear'),
                     ('Any ringing in your ears?', r'tinnitus|ringing|ear')]
        for variant in self.mara_variants():
            for question, topic in questions:
                with self.subTest(variant=variant, question=question):
                    case, engine, state = self.ready(variant=variant)
                    reply, meta = engine.respond(question, state)
                    self.assert_unavailable(case, reply, meta, topic)

    def test_no_syncope_does_not_become_no_dizziness_or_lightheadedness(self):
        for question in ['Any dizziness?', 'Do you feel lightheaded?', 'Any spinning sensation?']:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                reply, meta = engine.respond('Have you passed out?', state)
                self.assert_scope(case, reply, meta, {'symptom_syncope'}, {'symptom_syncope'})
                reply, meta = engine.respond(question, state)
                self.assert_unavailable(case, reply, meta, r'dizz|lightheaded|spin|vertigo')
                self.assertNotRegex(reply.lower(), r'i (?:have |had |have had )?never (?:passed out|fainted)|no (?:fainting|syncope)|i (?:do not|don.t) (?:faint|pass out)')

    def test_known_mara_ros_facts_remain_available_after_unknown_topics(self):
        fixtures = [('Any fever?', 'symptom_fever', 'negative'),
                    ('Any weight changes?', 'symptom_weight_loss', 'negative'),
                    ('Any fatigue?', 'symptom_fatigue', 'positive'),
                    ('Any shortness of breath?', 'symptom_dyspnea', 'positive'),
                    ('Any chest pain?', 'symptom_chest_pain', 'negative'),
                    ('Any cough?', 'symptom_cough', 'negative')]
        for question, fid, polarity in fixtures:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                engine.respond('Any depressed thoughts?', state)
                engine.respond('What about headaches?', state)
                reply, meta = engine.respond(question, state)
                self.assert_scope(case, reply, meta, {fid}, {fid})
                self.assertEqual(meta['concepts'][fid]['polarity'], polarity)

    def test_authored_ros_positive_and_negative_answers_are_preserved(self):
        fixtures = [
            ('cardio-febrile-cough', 'Any chills?', 'symptom_chills', 'positive', r'shaking chills'),
            ('gi-diarrhea-dehydration', 'Any nausea?', 'symptom_nausea', 'positive', r'nauseat'),
            ('gi-diarrhea-dehydration', 'Have you vomited?', 'symptom_vomiting', 'positive', r'twice yesterday.*not today'),
            ('heent-ear-pain', 'Any dizziness?', 'symptom_dizziness', 'negative', r'no spinning or dizziness'),
            ('heent-ear-pain', 'Any headaches?', 'symptom_headache', 'negative', r'no headache'),
            ('neuro-acute-focal-weakness', 'Any headaches?', 'symptom_headache', 'negative', r'no sudden severe headache'),
            ('msk-knee-injury', 'Any muscle aches?', 'symptom_myalgia', 'negative', r'elsewhere'),
            ('neuro-positional-vertigo', 'Any ringing in the ears?', 'symptom_hearing_loss', 'negative', r'no new.*ringing'),
        ]
        for cid, question, fid, polarity, text in fixtures:
            with self.subTest(case=cid, question=question):
                case, engine, state = self.ready(cid)
                reply, meta = engine.respond(question, state)
                self.assert_scope(case, reply, meta, {fid}, {fid})
                self.assertEqual(meta['concepts'][fid]['polarity'], polarity)
                self.assertRegex(reply.lower(), text)

    def test_compound_known_and_unknown_symptoms_answer_each_asked_topic(self):
        for question, fid, missing in [
            ('Any fever or chills?', 'symptom_fever', r'chill'),
            ('Any weight changes or headaches?', 'symptom_weight_loss', r'headache'),
            ('Any depressed thoughts or fever?', 'symptom_fever', r'depress|mood'),
        ]:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                reply, meta = engine.respond(question, state)
                self.assert_scope(case, reply, meta, {fid}, {fid})
                self.assertRegex(reply.lower(), missing)
                self.assertRegex(reply.lower(), r'not sure|cannot|can.t|unavailable|not (?:provid|specif)|no information')
                self.assertNotRegex(reply.lower(), r'no (?:fever or chills|headaches|depressed thoughts)|neither')

    def test_compound_unknown_symptoms_do_not_disclose_old_known_topics(self):
        for question, topics in [
            ('Any nausea, vomiting, or dizziness?', [r'nausea', r'vomit', r'dizz']),
            ('Any headaches or muscle aches?', [r'headache', r'muscle|myalgia|body ache']),
            ('Any chills or ringing in the ears?', [r'chill', r'ringing|tinnitus|ear']),
        ]:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                engine.respond('Any weight changes?', state)
                reply, meta = engine.respond(question, state)
                self.assert_unavailable(case, reply, meta, topics[0])
                for topic in topics[1:]:
                    self.assertRegex(reply.lower(), topic)
                self.assertNotRegex(reply.lower(), r'weight|palpitation|walking|energy drinks')

    def test_authored_compound_nausea_vomiting_answers_preserve_both_polarities(self):
        case, engine, state = self.ready('neuro-recurrent-headache')
        reply, meta = engine.respond('Any nausea or vomiting?', state)
        self.assert_scope(case, reply, meta, {'symptom_nausea', 'symptom_vomiting'},
                          {'symptom_nausea', 'symptom_vomiting'})
        self.assertEqual(meta['concepts']['symptom_nausea']['polarity'], 'positive')
        self.assertEqual(meta['concepts']['symptom_vomiting']['polarity'], 'negative')

    def test_explicit_ros_topic_wins_after_habit_and_identity_interruptions(self):
        for interruption in ['How many energy drinks do you drink?', 'What is your name?',
                             'Have you had this before?']:
            with self.subTest(interruption=interruption):
                case, engine, state = self.ready()
                engine.respond('Any weight changes?', state)
                engine.respond(interruption, state)
                reply, meta = engine.respond('How about any headaches?', state)
                self.assert_unavailable(case, reply, meta, r'headache')
                self.assertNotRegex(reply.lower(), r'weight|energy drinks|mara|palpitation|episode')

    def test_unknown_ros_does_not_leave_old_weight_as_an_elliptical_anchor(self):
        case, engine, state = self.ready()
        engine.respond('Any weight changes?', state)
        engine.respond('Any depressed thoughts?', state)
        reply, meta = engine.respond('How long has that been going on?', state)
        self.assert_scope(case, reply, meta, set())
        self.assertTrue(meta.get('no_information') or meta.get('kind') == 'clarification', (reply, meta))
        self.assertNotRegex(reply.lower(), r'weight|palpitation|episode|weeks ago|hours ago')

    def test_ros_question_after_transition_lead_in_is_still_answered(self):
        case, engine, state = self.ready()
        engine.respond('Any weight changes?', state)
        reply, meta = engine.respond("Now I'll ask about a few other symptoms. Any headaches?", state)
        self.assert_unavailable(case, reply, meta, r'headache')
        self.assertNotIn('weight', reply.lower())

    def test_exam_transition_acknowledges_without_performing_or_granting_consent(self):
        for question in ["okay now let's move on to the physical exam",
                         "Now I'd like to move on to the physical examination.",
                         "Let's move on to the exam."]:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                engine.respond('Any weight changes?', state)
                previous_consents = state.get('consents', 0)
                reply, meta = engine.respond(question, state)
                self.assert_scope(case, reply, meta, set())
                self.assertFalse(meta.get('no_information'), (reply, meta))
                self.assertNotEqual(meta.get('kind'), 'consent')
                self.assertEqual(state.get('consents', 0), previous_consents)
                self.assertFalse(meta.get('checklist_hits'), (reply, meta))
                self.assertFalse(meta.get('maneuver') or meta.get('exam_action') or meta.get('exam_findings'), (reply, meta))
                self.assertRegex(reply.lower(), r'okay|\bok\b|understand|ready|all right|alright|sure')
                self.assertNotRegex(reply.lower(), r'what do you mean|not sure|consent|permission|examin.*(?:completed|normal)|normal (?:heart|lungs)')

    def test_broad_dizziness_screen_uses_the_authored_sensation(self):
        for cid, fid, words in [
            ('cardio-presyncope', 'symptom_presyncope', r'vision dims.*stand'),
            ('neuro-positional-vertigo', 'symptom_vertigo', r'turning my head.*brief spinning'),
        ]:
            with self.subTest(case=cid):
                case, patient_engine, state = self.ready(cid)
                reply, meta = patient_engine.respond('Any dizziness?', state)
                self.assert_scope(case, reply, meta, {fid}, {fid})
                self.assertEqual(meta['concepts'][fid]['polarity'], 'positive')
                self.assertRegex(reply.lower(), words)

    def test_authored_bundled_ros_responses_keep_their_existing_delivery_contracts(self):
        fixtures = [
            ('cardio-chest-pressure', 'Any vomiting?', 'neg_gi', r"haven.t thrown up"),
            ('cardio-chest-pressure', 'Any fever?', 'neg_resp', r'no fever'),
            ('gi-epigastric-melena', 'Any vomiting?', 'neg_hematemesis', r"haven.t thrown up at all"),
            ('neuro-thunderclap-headache', 'Any chills?', 'neg_infectious', r'no chills'),
        ]
        for cid, question, fid, words in fixtures:
            with self.subTest(case=cid, question=question):
                case, patient_engine, state = self.ready(cid)
                reply, meta = patient_engine.respond(question, state)
                self.assert_scope(case, reply, meta, {fid}, {fid})
                self.assertRegex(reply.lower(), words)
                fact = next(f for f in case['facts'] if f['id'] == fid)
                self.assertEqual(meta['concepts'], patient.delivered_fact_metadata(fact, reply)['concepts'])
                self.assertFalse(meta.get('no_information'), (reply, meta))

    def test_vomiting_with_absent_preceding_nausea_keeps_its_temporal_qualifier(self):
        for question in ['Any nausea?', 'Any vomiting?', 'Any nausea or vomiting?']:
            with self.subTest(question=question):
                case, patient_engine, state = self.ready('neuro-thunderclap-headache')
                reply, meta = patient_engine.respond(question, state)
                self.assert_scope(case, reply, meta, {'assoc_vomiting'}, {'assoc_vomiting'})
                self.assertRegex(reply.lower(), r'threw up twice')
                self.assertRegex(reply.lower(), r'wasn.t even nauseated first')
                self.assertEqual(meta['concepts']['assoc_vomiting']['polarity'], 'positive')
                self.assertEqual(meta['concepts']['assoc_nausea']['polarity'], 'negative')
                self.assertNotRegex(reply.lower(), r'i (?:have no|do not have|don.t have) nausea')

    def test_current_nausea_is_not_answered_from_a_codeine_reaction(self):
        case, patient_engine, state = self.ready('gi-right-upper-pain')
        reply, meta = patient_engine.respond('Any nausea?', state)
        self.assert_scope(case, reply, meta, {'symptom_nausea'}, {'symptom_nausea'})
        self.assertNotRegex(reply.lower(), r'codeine|rash|breathing problems')

    def test_causal_family_and_attribute_questions_are_not_presence_requests(self):
        for question in ['What causes your nausea?', 'When did your nausea start?',
                         'What makes your nausea worse?', 'Does your mother have nausea?',
                         'How long does each headache last?', 'What do you take for nausea?']:
            with self.subTest(question=question):
                self.assertIsNone(ros_history.request(question))

    def test_unprovided_secondary_symptom_attributes_do_not_borrow_the_pain_history(self):
        for question in ['What causes your nausea?', 'When did your nausea start?',
                         'What makes your nausea worse?', 'What do you take for nausea?']:
            with self.subTest(question=question):
                case, patient_engine, state = self.ready('gi-right-upper-pain')
                reply, meta = patient_engine.respond(question, state)
                self.assert_unavailable(case, reply, meta, r'nausea|nauseat')
                self.assertNotRegex(reply.lower(), r'10 hours|deep breath|eating worsen|codeine')

    def test_authored_symptom_duration_survives_presence_routing(self):
        case, patient_engine, state = self.ready('neuro-recurrent-headache')
        reply, meta = patient_engine.respond('How long does each headache last?', state)
        self.assert_scope(case, reply, meta, {'hpi_episode_duration'}, {'hpi_episode_duration'})
        self.assertRegex(reply.lower(), r'12.{0,3}24 hours')

    def test_family_ros_question_does_not_disclose_the_patients_own_symptom(self):
        for question in ['Does your mother have nausea?', 'Does your daughter get headaches?',
                         'Has your sister had any depressed thoughts?']:
            with self.subTest(question=question):
                case, patient_engine, state = self.ready('gi-right-upper-pain')
                reply, meta = patient_engine.respond(question, state)
                self.assert_scope(case, reply, meta, set())

    def test_session_exam_transition_keeps_its_phase_findings_and_permission_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='cse-ros-session-') as folder:
            with patch.object(db, 'DB_PATH', str(Path(folder) / 'attempts.db')):
                db.init()
                for mode in ['guided', 'coached', 'independent', 'rehearsal']:
                    with self.subTest(mode=mode):
                        case = cases.resolve('cardio-palpitations', 'base')
                        preset = config.preset_for_learning_mode(mode)
                        settings = dict(config.load_settings(), learning_mode=mode, preset=preset,
                                        simulation_runtime='immediate')
                        sid = db.create_session(case['id'], preset, 'type', mode == 'guided', settings, case=case)
                        session = engine.load(sid)
                        session.start_encounter()
                        session.student_turn('Any weight changes?')
                        session = engine.load(sid)
                        before_facts = session.ledger.released_facts()
                        before_concepts = session.ledger.released_concepts()
                        before_consents = session.pstate.get('consents', 0)
                        before_phase = session.row['phase']
                        after_seq = len(session.ledger.events)
                        session.student_turn("okay now let's move on to the physical exam")
                        session = engine.load(sid)
                        added = session.ledger.events[after_seq:]
                        self.assertEqual(session.row['phase'], before_phase)
                        self.assertEqual(session.pstate.get('consents', 0), before_consents)
                        self.assertEqual(session.ledger.released_facts(), before_facts)
                        self.assertEqual(session.ledger.released_concepts(), before_concepts)
                        self.assertFalse([ev for ev in added if ev['kind'] in
                                          (evidence.EXAM_ACTION, evidence.EXAM_FINDING, evidence.EXAM_REFUSED)])
                        replies = [ev for ev in added if ev['kind'] == evidence.PATIENT]
                        self.assertEqual(len(replies), 1)
                        self.assertFalse(replies[0]['meta'].get('no_information'))
                        self.assertNotEqual(replies[0]['meta'].get('kind'), 'consent')
                        self.assertRegex(replies[0]['text'].lower(), r'okay|\bok\b|understand|ready|all right|alright|sure')

    def test_unknown_ros_turns_do_not_pollute_notes_or_released_evidence(self):
        case, engine, state = self.ready()
        ledger = evidence.Ledger()
        for question in ['Any weight changes?', 'Any depressed thoughts?', 'Any headaches?',
                         'Any muscle aches?', 'Any nausea or vomiting?', 'Any ringing in your ears?']:
            self.add_reply(engine, state, ledger, question)
        self.assertEqual(set(ledger.released_facts()), {'symptom_weight_loss'})
        self.assertEqual(set(ledger.released_concepts()), {'symptom_weight_loss'})
        summary = record.summarize(case, ledger.events)
        rows = [row for group in summary['groups'] for section in group['sections'] for row in section['items']]
        self.assertEqual({row['fact_id'] for row in rows if row.get('fact_id')}, {'symptom_weight_loss'})


if __name__ == '__main__':
    unittest.main()
