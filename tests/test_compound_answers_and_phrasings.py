"""Compound answers say each sentence once, and ordinary history wording is understood.

A two-part question can reach one authored statement twice (a focused clause and
the complete statement it comes from); the patient must still say it once, with
the evidence of both parts kept. Everyday wordings of the background history
questions reach their rows in every case that authors them, and never borrow an
unrelated row.
"""
import re
import unittest

from pcmcse import cases, dialogue, nlp, patient


def sentences(reply):
    return [nlp.normalize(s) for s in re.split(r'(?<=[.!?])\s+', reply) if s.strip()]


class CompoundAnswerTests(unittest.TestCase):
    def ask(self, case_id, question, variant='base', state=None):
        case = cases.resolve(case_id, variant)
        engine = patient.PatientEngine(case)
        reply, meta = engine.respond(question, {} if state is None else state)
        return case, reply, meta

    def assert_spoken_once(self, case, reply, meta):
        said = sentences(reply)
        self.assertEqual(len(said), len(set(said)), reply)
        facts = {f['id']: f for f in case['facts']}
        for fid in meta.get('facts_released', []):
            delivered = patient.delivered_fact_metadata(facts[fid], reply) or {}
            self.assertIn(fid, delivered.get('facts_released', []), (fid, reply))

    def test_a_focused_clause_and_its_complete_statement_are_said_once(self):
        for question in ('Have you had any surgeries, and have you ever been pregnant?',
                         'Have you ever been pregnant, and have you had any surgeries?',
                         'Any previous pregnancies or surgeries?'):
            with self.subTest(question=question):
                case, reply, meta = self.ask('gi-epigastric-melena', question)
                self.assert_spoken_once(case, reply, meta)
                self.assertEqual(reply, 'Gallbladder out at twenty-five. And two children, both normal deliveries.')
                self.assertIn('psh', meta['facts_released'])
        for case_id, fid, spoken in (
                ('msk-hand-stiffness', 'history_pregnancy',
                 'My period was one week ago. I use condoms and have not done a pregnancy test.'),
                ('pulm-episodic-wheeze', 'history_pregnancy_possibility',
                 'My period was two weeks ago. I use an IUD and do not think I am pregnant.')):
            for question in ('When was your last period, and could you be pregnant?',
                             'Could you be pregnant, and when was your last period?'):
                with self.subTest(case=case_id, question=question):
                    case, reply, meta = self.ask(case_id, question)
                    self.assert_spoken_once(case, reply, meta)
                    self.assertEqual(reply, spoken)
                    self.assertEqual(meta['facts_released'], [fid])
                    self.assertTrue(meta.get('checklist_hits'), meta)

    def test_a_fact_already_given_this_turn_is_not_repeated_with_like_i_said(self):
        case, reply, meta = self.ask(
            'skin-contact-rash',
            'Does anyone you live with have a rash, and any swelling of the lips or tongue or blisters in the mouth?')
        self.assert_spoken_once(case, reply, meta)
        self.assertEqual(reply.count('roommate'), 1, reply)
        self.assertNotRegex(reply, r'Right,|Like I said|As I mentioned')
        # The list was authored as one question; its answer is the authored one.
        self.assertIn('No swelling and no mouth blisters.', reply)
        self.assertEqual(set(meta['facts_released']),
                         {'history_home_and_contacts', 'history_severe_reaction_symptoms'})

    def test_a_named_site_does_not_borrow_the_last_topic(self):
        case = cases.resolve('skin-contact-rash', 'base')
        engine, state = patient.PatientEngine(case), {}
        engine.respond('Does anyone you live with have a rash?', state)
        reply, meta = engine.respond('Any swelling of the lips?', state)
        self.assertNotIn('roommate', reply)
        self.assertNotIn('history_home_and_contacts', meta.get('facts_released', []))

    def test_the_last_period_is_answerable_from_a_bundled_pregnancy_statement(self):
        for case_id, spoken in (('msk-hand-stiffness', 'My period was one week ago.'),
                                ('pulm-episodic-wheeze', 'My period was two weeks ago.')):
            for question in ('When was your last period?', 'When did your last period start?',
                             'What was the first day of your last menstrual period?'):
                with self.subTest(case=case_id, question=question):
                    case, reply, meta = self.ask(case_id, question)
                    self.assertEqual(reply, spoken)
                    # The period alone: contraception and pregnancy status stay unsaid,
                    # and the complete statement's checklist item is not credited.
                    self.assertNotRegex(reply.lower(), r'condom|iud|pregnan')
                    self.assertEqual(meta.get('facts_released', []), [])
                    self.assertFalse(meta.get('checklist_hits'), meta)
                    self.assertTrue(all(c['value'] == spoken for c in meta['concepts'].values()), meta)
        # A case that authors no period at all still says it does not know.
        case, reply, meta = self.ask('heent-sore-throat', 'When was your last period?')
        self.assertTrue(meta.get('no_information'), (reply, meta))

    def test_a_fever_question_is_answered_by_the_fever_statement_not_the_opening(self):
        for variant in ['base'] + [v['id'] for v in cases.get('renal-flank-pain')['variants']]:
            with self.subTest(variant=variant):
                case, reply, meta = self.ask('renal-flank-pain', 'Any fever?', variant,
                                             {'opened': True, 'open_budget': 0})
                self.assertEqual(meta['facts_released'], ['assoc_fever_subjective'])
                self.assertNotIn('burning when I pee', reply)


class ListSegmentationTests(unittest.TestCase):
    def test_a_bare_body_part_or_relative_keeps_the_phrase_it_belongs_to(self):
        cases_ = {
            'Any swelling of the lips or tongue or blisters in the mouth?':
                ['Any swelling of the lips', 'Any swelling of the tongue', 'Any blisters in the mouth'],
            'Any blood in your stool or urine?': ['Any blood in your stool', 'Any blood in your urine'],
            'Any pain in your arms, legs or back?': ['Any pain in your arms', 'Any pain in your legs', 'Any pain in your back'],
            'Any rash on your face or your hands?': ['Any rash on your face', 'Any rash on your hands'],
            # Symptoms are topics of their own and are not tied to a body part.
            'Any pain in your belly or nausea?': ['Any pain in your belly', 'Any nausea'],
            'Any nausea, vomiting, or diarrhea?': ['Any nausea', 'Any vomiting', 'Any diarrhea'],
        }
        for question, expected in cases_.items():
            with self.subTest(question=question):
                self.assertEqual(dialogue.segment(question), expected)

    def test_segment_groups_keep_each_list_beside_its_clause(self):
        groups = dialogue.segment_groups('Does anyone at home have a rash, and any swelling of the lips or tongue?')
        self.assertEqual(groups[1][0], 'any swelling of the lips or tongue')
        self.assertEqual(groups[1][1], ['any swelling of the lips', 'any swelling of the tongue'])
        self.assertEqual(dialogue.segment('How are you?'), ['How are you?'])


class HistoryPhrasingTests(unittest.TestCase):
    """Wordings outside the held-out test, checked in every case that authors the row."""
    PHRASINGS = {
        'medications': ['Are you on anything at the moment?', 'Is there anything you take on a regular basis?'],
        'psh': ['Any surgical history?', 'Have you ever gone under the knife?'],
        'allergies': ["Are there medicines that don't agree with you?", 'Is there any medication you have to avoid?'],
        'family': ['Any medical problems among your parents or siblings?'],
        'pmh': ['Any chronic illnesses?'],
    }

    def test_everyday_wordings_reach_their_row_in_every_case(self):
        for cid in sorted(cases.all_cases()):
            case = cases.resolve(cid, 'base')
            facts = {f['id']: f for f in case['facts']}
            authored = {f.get('category') for f in case['facts']}
            for row, questions in self.PHRASINGS.items():
                if row not in authored:
                    continue
                for question in questions:
                    with self.subTest(case=cid, question=question):
                        reply, meta = patient.PatientEngine(case).respond(question, {'opened': True, 'open_budget': 0})
                        rows = {facts[f].get('category') for f in meta.get('facts_released', []) if f in facts}
                        self.assertIn(row, rows, reply)

    def test_an_anything_question_is_not_an_open_invitation(self):
        case = cases.resolve('cardio-chest-pressure', 'base')
        reply, meta = patient.PatientEngine(case).respond(
            'Is there anything you take on a regular basis?', {'opened': True, 'open_budget': 0})
        self.assertNotRegex(reply, r"that's about it|Not that I can think of")
        self.assertIn('medications', {f['category'] for f in case['facts'] if f['id'] in meta['facts_released']})
        # A real invitation still reads as one.
        engine = patient.PatientEngine(case)
        self.assertTrue(engine._is_anything_else(nlp.normalize('Is there anything else you would like to tell me?')))
        self.assertFalse(engine._is_anything_else(nlp.normalize('Is it burning, stabbing, or something else?')))

    def test_a_named_history_domain_outranks_a_timeline_word(self):
        case = cases.resolve('cardio-exertional-leg-pain', 'base')
        reply, meta = patient.PatientEngine(case).respond('Any procedures done in the past?', {'opened': True, 'open_budget': 0})
        rows = {f['category'] for f in case['facts'] if f['id'] in meta['facts_released']}
        self.assertEqual(rows, {'psh'}, reply)

    def test_home_history_filed_under_a_broader_topic_still_answers(self):
        # "I live with my brother" is tagged as social context, not household.
        case = cases.resolve('heent-ear-pain', 'base')
        for question in ('Who do you live with?', 'What is your living situation like?', 'Do you live alone?'):
            with self.subTest(question=question):
                reply, meta = patient.PatientEngine(case).respond(question, {'opened': True, 'open_budget': 0})
                self.assertEqual(meta['facts_released'], ['history_home'], reply)
        # A case that never says who she lives with still does not know.
        case = cases.resolve('msk-hand-stiffness', 'base')
        reply, meta = patient.PatientEngine(case).respond('Who do you live with?', {'opened': True, 'open_budget': 0})
        self.assertTrue(meta.get('no_information'), reply)

    def test_a_bad_reaction_to_a_medicine_is_the_allergy_question(self):
        case = cases.resolve('cardio-chest-pressure', 'base')
        reply, meta = patient.PatientEngine(case).respond('Do you react badly to any medication?', {'opened': True, 'open_budget': 0})
        rows = {f['category'] for f in case['facts'] if f['id'] in meta['facts_released']}
        self.assertEqual(rows, {'allergies'}, reply)


if __name__ == '__main__':
    unittest.main()
