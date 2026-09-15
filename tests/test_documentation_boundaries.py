"""Regression tests for evidence scoping and truthful post-encounter lessons."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from pcmcse import audit, cases, config, db, engine, evidence, feedback, learning, note, physexam, record, checklist


class DocumentationBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pcm-documentation-')
        self.old = db.DB_PATH
        db.DB_PATH = str(Path(self.temp.name) / 'a.sqlite')
        db.init()
        self.case = cases.resolve('renal-flank-pain')
        settings = dict(config.load_settings(), learning_mode='guided')
        settings['scoring'] = dict(settings['scoring'], realtime_exam_durations=False)
        sid = db.create_session(self.case['id'], 'guided_untimed', 'type', True, settings, case=self.case)
        self.session = engine.load(sid)
        self.session.start_encounter()
        self.session.perform_maneuver('heart_auscultate', physexam.CATALOG_BY_ID['heart_auscultate']['components'])

    def tearDown(self):
        db.DB_PATH = self.old
        self.temp.cleanup()

    def verdicts(self, text):
        parsed = note.parse({'S': '', 'O': 'Heart: ' + text, 'A': [], 'P': []})
        return [c['verdict'] for c in audit.audit_note(parsed, self.session.ledger, self.case)['claims']]

    def test_comma_does_not_remove_inherited_negation(self):
        self.assertEqual(self.verdicts('No murmurs, rubs or gallops.'), ['supported'])
        self.assertNotIn('supported', self.verdicts('Rubs or gallops.'))
        self.assertIsNone(audit._verbatim_obtained(
            {'section': 'O', 'text': 'Rubs or gallops.', 'header': 'heart'}, self.session.ledger))

    def test_negation_does_not_cross_complete_sentence_boundaries(self):
        ledger = evidence.Ledger()
        ledger.add(evidence.EXAM_FINDING,
                   'Comfortable at rest, in no acute distress. Alert and oriented. Breathing easily.',
                   meta={'maneuver_id': 'general_inspect'})
        self.assertIsNotNone(audit._verbatim_obtained(
            {'section': 'O', 'text': 'Alert and oriented.', 'header': 'general'}, ledger))
        self.assertIsNotNone(audit._verbatim_obtained(
            {'section': 'O', 'text': 'Breathing easily.', 'header': 'general'}, ledger))

    def test_literal_reflex_findings_bypass_only_uncertain_component_parsing(self):
        case = cases.resolve('neuro-back-bladder-redflags')
        ledger = evidence.Ledger()
        ledger.add(evidence.EXAM_FINDING,
                   'Achilles reflexes reduced bilaterally; patellar reflexes preserved.',
                   meta={'maneuver_id': 'neuro_reflexes', 'concepts': {}})
        def verdicts(text):
            return [c['verdict'] for c in audit.audit_note(
                note.parse({'O': 'Neurologic: ' + text}), ledger, case)['claims']]
        self.assertEqual(verdicts('Achilles reflexes reduced bilaterally; patellar reflexes preserved.'),
                         ['supported', 'supported'])
        for text in ['Achilles reflexes absent bilaterally.', 'Biceps reflexes reduced bilaterally.',
                     'Achilles reflexes 2+ bilaterally.', 'No Achilles reflexes reduced bilaterally.']:
            self.assertNotIn('supported', verdicts(text), text)

    def test_concise_social_history_preserves_occupation_household_and_qualifiers(self):
        case = cases.resolve('cardio-palpitations')
        facts = [f for f in case['facts'] if f['category'] == 'social']
        ledger = evidence.Ledger()
        for f in facts:
            ledger.add(evidence.PATIENT, f['value'], meta={'facts_released': [f['id']], 'concepts': f['concepts']})
        def match(text, header='sh', source=ledger):
            return audit._literal_social_history({'section': 'S', 'header': header, 'text': text}, case, source)
        for text in ['Software analyst;', 'lives with husband;', 'Software analyst, lives with husband.']:
            self.assertEqual(match(text)['verdict'], 'supported')
        for text in ['Software engineer.', 'lives with wife.', 'lives with husband and child.',
                     'Former software analyst.', 'No software analyst.', 'Software analyst, roommate.']:
            self.assertIsNone(match(text), text)
        self.assertIsNone(match('Software analyst.', header='fh'))
        self.assertIsNone(match('Software analyst.', source=evidence.Ledger()))
        # A relative's job, undisclosed fact IDs, or tentative wording is never
        # collapsed into a definite statement about the patient.
        for text in ['My husband is a software analyst.', 'I might be a software analyst.',
                     'I am not a software analyst.', 'I used to be a software analyst.']:
            forged = evidence.Ledger()
            forged.add(evidence.PATIENT, text, meta={'facts_released': [f['id'] for f in facts]})
            self.assertIsNone(match('Software analyst.', source=forged), text)

    def test_repair_uses_findings_instead_of_a_social_acknowledgment(self):
        last_finding = self.session.ledger.by_kind(evidence.EXAM_FINDING)[-1]
        self.session.ledger.add(evidence.PATIENT, 'Thank you for listening.', meta={})
        self.session.row.update(phase='submitted', results_json=json.dumps({'feedback': {}}))
        repair = learning.repair(self.session)
        self.assertEqual(repair['id'], 'source_section')
        self.assertEqual(repair['source_seq'], last_finding['seq'])
        self.assertEqual(repair['answer'], 1)
        self.assertNotIn('Thank you', repair['stem'])

    def test_direct_ros_denials_are_visible_once_and_require_real_question_and_reply(self):
        case = cases.resolve('cardio-chest-pressure')
        settings = dict(config.load_settings(), learning_mode='guided')
        sid = db.create_session(case['id'], 'guided_untimed', 'type', True, settings, case=case)
        session = engine.load(sid)
        session.start_encounter()
        session.student_turn('Have you had a rash?')
        session.student_turn('Have you had a rash?')
        before = session.ledger.to_json()
        summary = record.summarize(case, session.ledger.events)
        rows = [i for g in summary['groups'] for sec in g['sections'] for i in sec['items']]
        self.assertEqual(len([r for r in rows if r.get('fact_id') == 'expanded_ros_rash']), 1)
        self.assertEqual(session.ledger.to_json(), before)
        # Forging either the question, answer or an allowed topic must not add a denial.
        question = {'kind': evidence.STUDENT, 'seq': 1, 'text': 'Have you had a rash?', 'meta': {}}
        reply = {'kind': evidence.PATIENT, 'seq': 2, 'text': 'No.', 'meta': {
            'kind': 'denial', 'concepts': {'rash': {'polarity': 'negative', 'value': 'denied on direct questioning'}}}}
        for q, r in [(dict(question, text='How are you?'), reply),
                     (question, dict(reply, text='I am not sure.')),
                     (question, dict(reply, meta=dict(reply['meta'], no_information=True)))]:
            self.assertEqual(record.summarize(case, [q, r])['facts'], 0)
        withheld = copy.deepcopy(case)
        withheld['supersedes_core'].append('rash')
        self.assertEqual(record.summarize(withheld, [question, reply])['facts'], 0)

    def test_interrupted_exam_is_not_described_as_an_unspecific_request(self):
        ledger = evidence.Ledger()
        ledger.add(evidence.EXAM_ACTION, 'Examination started.', meta={'maneuver_id': 'heart_auscultate', 'status': 'in_progress'})
        ledger.add(evidence.EXAM_ACTION, 'Examination interrupted.', meta={'maneuver_id': 'heart_auscultate', 'status': 'interrupted'})
        item = {'id': 'heart', 'text': 'Auscultate heart', 'maneuver': 'heart_auscultate'}
        result = checklist._score_physical(item, {}, checklist._attempted_maneuvers(ledger), {}, set(), ledger)
        self.assertEqual(result['status'], 'selected')
        self.assertIn('interrupted', result['detail'])
        self.assertNotIn('did not specify', result['detail'])

    def test_feedback_does_not_prescribe_the_same_follow_up_or_education_for_every_case(self):
        urgent = cases.resolve('neuro-thunderclap-headache')
        followup = feedback._what_to_do({'id': 'specific_follow_up'}, urgent)
        education = feedback._what_to_do({'id': 'specific_education'}, urgent)
        self.assertNotIn('48-72', followup)
        self.assertIn('emergency', followup)
        self.assertNotIn('antibiotic', education)
        self.assertIn('unless you actually discussed', education)
        self.assertIn('5% of the note', feedback._why_matters({'category': 'Objective'}))


if __name__ == '__main__':
    unittest.main()
