"""One member of a bundled pertinent negative is answered without the rest.

Several cases author a screen of negatives as one statement. A question about
one member hears that member's approved clause: the bundled fact is not
released, its checklist item is not credited, and only that member's own
concept is recorded. The case's authored compound question, or a question
naming every member, still hears the complete statement.
"""
import re
import unittest

import json
from unittest.mock import patch

from pcmcse import audit, bundled_negatives, cases, evidence, nlp, note, patient, record, scribbi
from pcmcse.scribbi import visit as V
from test_scribbi import Isolated

OPEN = {'opened': True, 'open_budget': 0}

# One question per member, per bundle, and the clause it must hear.
MEMBERS = {
    ('cardio-chest-pressure', 'neg_cardiac'): [
        ('Have you fainted?', "No, I haven't passed out.", 'no_syncope'),
        ('Any palpitations?', 'No fluttering.', 'no_palpitations'),
        ('Can you lie flat to sleep?', 'I sleep flat, no problem.', 'no_orthopnea'),
        ('Any swelling in your ankles?', 'My ankles look normal.', 'no_leg_swelling')],
    ('cardio-chest-pressure', 'neg_resp'): [
        ('Any cough?', 'No cough.', 'no_cough'),
        ('Have you coughed up blood?', 'No coughing up blood.', 'no_hemoptysis'),
        ('Any wheezing?', 'No wheezing.', 'no_wheezing'),
        ('Any fever?', 'No fever.', None),
        ('Any pain in your calves?', 'My legs feel fine.', None)],
    ('cardio-chest-pressure', 'neg_gi'): [
        ('Any heartburn?', 'No heartburn.', 'no_reflux'),
        ('Have you vomited?', "I haven't thrown up.", 'no_vomiting'),
        ('Any belly pain?', "My belly doesn't hurt.", 'no_abdominal_pain')],
    ('gi-epigastric-melena', 'neg_hematemesis'): [
        ('Have you vomited?', "No, I haven't thrown up at all.", 'no_vomiting')],
    ('gi-epigastric-melena', 'neg_alarm'): [
        ('Any weight loss?', "My weight's about the same.", 'no_weight_loss'),
        ('Any trouble swallowing?', 'No trouble swallowing.', 'no_dysphagia'),
        ('Any fevers?', 'No fevers.', 'no_fever'),
        ('Has anyone said you look yellow?', "Nobody's said I look yellow.", 'no_jaundice')],
    ('gi-epigastric-melena', 'neg_other'): [
        ('Any diarrhea?', 'No diarrhea.', 'no_diarrhea'),
        ('Any chest pain?', 'No chest pain.', 'no_chest_pain')],
    ('gi-epigastric-melena', 'neg_bleeding'): [
        ('Do you bruise easily?', "No, I don't bruise easily.", 'no_easy_bruising'),
        ('Do your gums bleed?', "My gums don't bleed.", 'no_bleeding_gums'),
        ('Any nosebleeds?', "I don't get nosebleeds.", 'no_epistaxis')],
    ('neuro-thunderclap-headache', 'neg_focal'): [
        ('Any weakness?', 'No weakness.', 'no_focal_weakness'),
        ('Any numbness?', "Nothing's numb.", None),
        ('Any trouble speaking?', 'My speech is fine.', None),
        ('Any vision changes?', "My vision's normal apart from the light hurting.", 'no_vision_change'),
        ('Any seizures?', 'No seizures.', 'no_seizure')],
    ('neuro-thunderclap-headache', 'neg_infectious'): [
        ('Any fever?', 'No fever.', 'no_fever'),
        ('Any chills?', 'No chills.', None),
        ('Any rash?', 'No rash.', 'no_rash'),
        ('Any night sweats?', 'No night sweats.', 'no_night_sweats'),
        ('Any weight loss?', 'My weight is the same.', 'no_weight_loss'),
        ('Has anyone around you been sick?', 'Nobody around me has been sick.', None)],
    ('renal-flank-pain', 'neg_resp'): [
        ('Any cough?', 'No cough.', 'cough'),
        ('Any trouble breathing?', 'No trouble breathing.', 'sob'),
        ('Any chest pain?', 'No chest pain.', 'chest_pain')],
    ('renal-flank-pain', 'neg_skin_neuro'): [
        ('Any rash?', 'No rash anywhere.', 'rash'),
        ('Any headache?', 'No headache.', 'headache'),
        ('Any weight loss?', 'My weight is the same.', 'no_weight_loss'),
        ('Any night sweats?', "I haven't had night sweats.", 'no_night_sweats')],
}


def variants(case_id):
    return ['base'] + [v['id'] for v in cases.get(case_id).get('variants', [])]


def ask(case, question, state=None):
    return patient.PatientEngine(case).respond(question, dict(OPEN) if state is None else state)


class BundledNegativeTests(unittest.TestCase):
    def test_every_bundled_negative_in_the_library_has_approved_member_clauses(self):
        bundles = set()
        for cid in cases.all_cases():
            for vid in variants(cid):
                for fact in cases.resolve(cid, vid)['facts']:
                    if fact.get('category') == 'pertinent_negative' and len(fact.get('concepts', {})) > 1:
                        bundles.add((cid, fact['id']))
                        scoped = bundled_negatives.scoped_fact(fact)
                        clauses = [v for v in scoped['delivery_contract']['versions'] if v.get('complete_fact') is False]
                        self.assertTrue(clauses, (cid, vid, fact['id']))
                        texts = [nlp.normalize(v['text']).strip() for v in clauses]
                        for version in clauses:
                            # A clause records only its own member's authored concept.
                            self.assertLessEqual(len(version['concepts']), 1, version)
                            self.assertLessEqual(set(version['concepts']), set(fact['concepts']), version)
                            self.assertTrue(version['symptom_topics'], version)
                            # No clause is found inside another: each is its own evidence.
                            mine = nlp.normalize(version['text']).strip()
                            for other in texts:
                                if other != mine:
                                    self.assertNotRegex(other, r'(?<!\w)' + re.escape(mine) + r'(?!\w)')
                        # The table names every authored concept of the bundle,
                        # except a member only the whole statement answers.
                        named = {cid_ for v in clauses for cid_ in v['concepts']}
                        whole = bundled_negatives.members(fact) - {t for v in clauses for t in v['symptom_topics']}
                        if whole:
                            self.assertLess(named, set(fact['concepts']), (cid, fact['id']))
                        else:
                            self.assertEqual(named, set(fact['concepts']), (cid, fact['id']))
                        # Scoping returns a copy; the case's own fact is untouched.
                        self.assertNotIn('symptom_topics', str(fact.get('delivery_contract')))
        self.assertEqual(bundles, set(MEMBERS))

    def test_a_member_question_hears_only_that_member(self):
        for (cid, fid), members in MEMBERS.items():
            for vid in variants(cid):
                case = cases.resolve(cid, vid)
                for question, clause, concept in members:
                    with self.subTest(case=cid, variant=vid, question=question):
                        reply, meta = ask(case, question)
                        self.assertEqual(reply, clause)
                        self.assertEqual(meta['facts_released'], [])
                        self.assertFalse(meta.get('checklist_hits'), meta)
                        expected = {concept} if concept else {'delivered_text_' + fid}
                        self.assertEqual(set(meta['concepts']), expected)
                        self.assertTrue(all(c['value'] == clause for c in meta['concepts'].values()), meta)
                        if concept:
                            self.assertEqual(meta['concepts'][concept]['polarity'], 'negative')

    def test_the_authored_compound_question_still_releases_the_whole_statement(self):
        for (cid, fid) in MEMBERS:
            for vid in variants(cid):
                case = cases.resolve(cid, vid)
                fact = next(f for f in case['facts'] if f['id'] == fid)
                with self.subTest(case=cid, variant=vid, fact=fid):
                    reply, meta = ask(case, fact['example_questions'][0])
                    self.assertIn(fact['value'], reply)
                    self.assertIn(fid, meta['facts_released'])
                    self.assertEqual(set(fact['concepts']) & set(meta['concepts']), set(fact['concepts']))
                    if fact.get('checklist'):
                        self.assertIn(fact['checklist'], meta.get('checklist_hits', []))

    def test_every_member_in_other_words_is_the_whole_screen(self):
        case = cases.resolve('cardio-chest-pressure', 'base')
        reply, meta = ask(case, 'Any fainting, palpitations, trouble lying flat, or leg swelling?')
        self.assertEqual(reply, "No, I haven't passed out. No fluttering. I sleep flat, no problem. My ankles look normal.")
        self.assertEqual(meta['facts_released'], ['neg_cardiac'])
        self.assertEqual(meta['checklist_hits'], ['h16'])

    def test_several_members_hear_their_clauses_and_nothing_else(self):
        for cid, question, reply_expected, concepts in [
                ('cardio-chest-pressure', 'Any palpitations or leg swelling?',
                 'No fluttering. My ankles look normal.', {'no_palpitations', 'no_leg_swelling'}),
                ('neuro-thunderclap-headache', 'Any fever, chills, or rash?',
                 'No fever. No chills. No rash.', {'no_fever', 'no_rash', 'delivered_text_neg_infectious'}),
                ('gi-epigastric-melena', 'Any weight loss or fevers?',
                 "My weight's about the same. No fevers.", {'no_weight_loss', 'no_fever'})]:
            with self.subTest(case=cid, question=question):
                reply, meta = ask(cases.resolve(cid, 'base'), question)
                self.assertEqual(reply, reply_expected)
                self.assertEqual(meta['facts_released'], [])
                self.assertFalse(meta.get('checklist_hits'))
                self.assertEqual(set(meta['concepts']), concepts)

    def test_clauses_without_a_concept_keep_every_delivered_word(self):
        case = cases.resolve('neuro-thunderclap-headache', 'base')
        reply, meta = ask(case, 'Any numbness or trouble speaking?')
        self.assertEqual(reply, "Nothing's numb. My speech is fine.")
        self.assertEqual(meta['concepts'], {'delivered_text_neg_focal': {
            'polarity': 'positive', 'value': "Nothing's numb. My speech is fine."}})
        ledger = evidence.Ledger()
        ledger.add(evidence.STUDENT, 'Any numbness or trouble speaking?')
        ledger.add(evidence.PATIENT, reply, meta=meta)
        rows = [item for group in record.summarize(case, ledger.events)['groups']
                for section in group['sections'] for item in section['items']]
        self.assertEqual([(r['label'], r['text']) for r in rows],
                         [('Numbness', "Nothing's numb."), ('Speech', 'My speech is fine.')])

    def test_no_generic_denial_is_added_to_a_member_clause(self):
        case = cases.resolve('cardio-chest-pressure', 'base')
        for question, clause in [('Any swelling in your ankles?', 'My ankles look normal.'),
                                 ('Any belly pain?', "My belly doesn't hurt.")]:
            with self.subTest(question=question):
                reply, meta = ask(case, question)
                self.assertEqual(reply, clause)
                self.assertNotIn('denied on direct questioning', str(meta['concepts']))

    def test_notes_show_the_member_and_consolidate_after_the_whole_screen(self):
        case = cases.resolve('cardio-chest-pressure', 'base')
        engine, state, ledger = patient.PatientEngine(case), dict(OPEN), evidence.Ledger()

        def say(question):
            reply, meta = engine.respond(question, state)
            ledger.add(evidence.STUDENT, question)
            ledger.add(evidence.PATIENT, reply, meta=meta)

        def rows():
            return [(item['label'], item['text'], bool(item.get('partial')))
                    for group in record.summarize(case, ledger.events)['groups']
                    for section in group['sections'] for item in section['items']
                    if (item.get('source_fact_id') or item.get('fact_id')) == 'neg_cardiac']
        say('Any palpitations?')
        self.assertEqual(rows(), [('Palpitations', 'No fluttering.', True)])
        say('Have you had fainting, palpitations, breathlessness when flat or at night, or leg swelling?')
        self.assertEqual([r[2] for r in rows()], [False])

    def test_documentation_is_supported_only_for_the_member_asked(self):
        case = cases.resolve('cardio-chest-pressure', 'base')

        def verdicts(questions, text):
            engine, state, ledger = patient.PatientEngine(case), dict(OPEN), evidence.Ledger()
            for question in questions:
                reply, meta = engine.respond(question, state)
                ledger.add(evidence.STUDENT, question)
                ledger.add(evidence.PATIENT, reply, meta=meta)
            return [c['verdict'] for c in audit.audit_note(note.ParsedNote(text, '', [], []), ledger, case)['claims']]
        self.assertEqual(verdicts(['Any palpitations?'], 'ROS: Denies palpitations.'), ['supported'])
        # Asking about palpitations no longer supports the rest of the bundle.
        self.assertEqual(verdicts(['Any palpitations?'], 'ROS: Denies syncope.'), ['unsupported'])
        self.assertEqual(verdicts(
            ['Have you had fainting, palpitations, breathlessness when flat or at night, or leg swelling?'],
            'ROS: Denies syncope, palpitations, orthopnea, and leg swelling.'), ['supported'])

    def test_a_question_naming_no_member_is_unchanged(self):
        # Reached through another word of the bundle's trigger, the answer
        # stays the authored statement it always was.
        case = cases.resolve('cardio-chest-pressure', 'base')
        fact = next(f for f in case['facts'] if f['id'] == 'neg_resp')
        self.assertIsNone(bundled_negatives.focus(fact, 'Any recent travel?'))
        self.assertIsNone(bundled_negatives.focus(fact, fact['example_questions'][0]))


class ScribbiPartialAnswerTests(Isolated):
    def test_a_led_visit_draft_quotes_the_member_answers_the_student_heard(self):
        cid = 'cardio-chest-pressure'
        state = self.route('/api/session', {'case_id': cid, 'variant_id': 'base',
                                            'learning_mode': 'coached', 'purpose': 'scribbi'})
        sid = state['id']
        self.route('/api/session/%s/start' % sid, {})
        for question in ['Hi, I am a student doctor. What brings you in today?', 'When did it start?',
                         'Does it go anywhere?', 'How bad is it from 0 to 10?',
                         'Any palpitations?', 'Any swelling in your ankles?']:
            self.route('/api/session/%s/say' % sid, {'text': question})
        walk = V.load_walkthrough(cid, 'base')
        ledger = {e['seq']: e for e in walk['ledger']}
        done = 0
        for turn in [t for t in walk['timeline'] if t.get('maneuver_id')]:
            if done >= 2:
                break
            action = next((ledger[e] for e in turn['event_ids'] if ledger.get(e, {}).get('kind') == 'exam_action'), None)
            result = self.route('/api/session/%s/exam' % sid, {
                'maneuver_id': turn['maneuver_id'], 'components': (action or {}).get('meta', {}).get('components', []),
                'source_text': 'Perform: ' + turn['action']})
            event = result['events'][0]
            if event.get('examination_id'):
                done += 1
                self.route('/api/session/%s/exam_control' % sid,
                           {'examination_id': event['examination_id'], 'operation': 'skip'})
        with patch.object(scribbi.P, 'plant', side_effect=lambda b, ctx, mode, seed: ([], scribbi.P.hands_on(b, ctx))):
            rnd = self.route('/api/scribbi/rounds', {'attempt_id': sid, 'mode': 'learn'})
        lines = json.loads(scribbi.store.get(rnd['id'])['lines_json'])
        ros = ' '.join(chip['text'] for line in lines if line['label'] == 'ROS' for chip in line['chips'])
        self.assertIn('No fluttering.', ros)
        self.assertIn('My ankles look normal.', ros)
        # Only what she said: the rest of the bundle was never asked.
        self.assertNotIn('passed out', ros)
        self.assertNotIn('sleep flat', ros)


if __name__ == '__main__':
    unittest.main()
