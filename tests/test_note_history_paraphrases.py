"""Clinical wording earns only the attributes and source actually obtained."""
import copy
import json
from pathlib import Path
import unittest
from pcmcse import audit, cases, evidence, grader, note, patient


class NoteHistoryParaphraseTests(unittest.TestCase):
    def setUp(self):
        self.case = cases.resolve('cardio-palpitations')

    def obtained(self, *questions):
        pe, state, ledger = patient.PatientEngine(self.case), {}, evidence.Ledger()
        for question in questions:
            ledger.add(evidence.STUDENT, question)
            reply, meta = pe.respond(question, state)
            ledger.add(evidence.PATIENT, reply, meta=meta)
        return ledger

    def check_claim(self, text, ledger, header='HPI'):
        results = audit.audit_note(note.parse({'S': header + ': ' + text}), ledger, self.case)['claims']
        self.assertEqual(len(results), 1, results)
        return results[0]

    def test_quality_and_functional_severity_accept_clinical_paraphrases(self):
        ledger = self.obtained('What does it feel like?', 'How bad are the symptoms?')
        for text, expected in [('Rapid irregular heartbeat.', 'hpi_quality'),
                               ('Fast uneven fluttering.', 'hpi_quality'),
                               ('Discomfort with ordinary walking.', 'hpi_severity'),
                               ('Normal walking is uncomfortable.', 'hpi_severity'),
                               ('Usual walking causes discomfort.', 'hpi_severity')]:
            with self.subTest(text=text):
                result = self.check_claim(text, ledger)
                self.assertEqual(result['verdict'], 'supported', result)
                self.assertIn(expected, result['concepts'])

    def test_quality_and_severity_cannot_come_from_undisclosed_facts(self):
        for text in ['Rapid irregular heartbeat.', 'Discomfort with ordinary walking.']:
            result = self.check_claim(text, evidence.Ledger())
            self.assertNotIn(result['verdict'], ('supported', 'supported_supplied'))
        ledger = self.obtained('What does it feel like?', 'How bad are the symptoms?')
        for text in ['Slow regular heartbeat.', 'No discomfort with ordinary walking.',
                     'Severe discomfort with ordinary walking.']:
            self.assertNotEqual(self.check_claim(text, ledger)['verdict'], 'supported', text)
        # Another system's rate does not become the heartbeat rate.
        self.assertEqual(audit._heartbeat_quality('Rapid breathing and regular heartbeat.', True),
                         {'rhythm': 'regular'})
        self.assertEqual(audit._heartbeat_quality('Fast RR and regular heartbeat.', True),
                         {'rhythm': 'regular'})

    def test_energy_drinks_cannot_borrow_alcohol_history(self):
        ledger = self.obtained('Do you drink alcohol?')
        for text in ['Energy drinks appear to trigger episodes.',
                     'Energy drinks never trigger episodes.', 'No energy drinks.',
                     'Drinks water.', 'Drinks coffee.']:
            result = self.check_claim(text, ledger)
            self.assertNotEqual(result['verdict'], 'supported', (text, result))
            self.assertNotIn('alcohol_use', result['concepts'])
        self.assertEqual(self.check_claim('Two beers most evenings.', ledger, 'SH')['verdict'], 'supported')

    def test_trigger_proof_preserves_beverage_polarity_and_uncertainty(self):
        ledger = self.obtained('What brings on the episodes?')
        good = self.check_claim('Energy drinks appear to trigger episodes.', ledger)
        self.assertEqual(good['verdict'], 'supported', good)
        self.assertEqual(good['concepts'], ['hpi_aggravating'])
        self.assertIn('Energy drinks', good['evidence'][0]['text'])
        for text in ['Energy drinks never trigger episodes.', 'Energy drinks trigger episodes.',
                     'Coffee appears to trigger episodes.', 'Alcohol appears to trigger episodes.']:
            self.assertNotEqual(self.check_claim(text, ledger)['verdict'], 'supported', text)

    def test_complete_demonstrated_note_credits_paraphrased_quality_and_severity(self):
        path = Path(__file__).resolve().parents[1] / 'pcmcse/teaching/lessons/cardio-palpitations.json'
        lesson = json.loads(path.read_text())['walkthroughs'][0]
        ledger = evidence.Ledger(copy.deepcopy(lesson['ledger']))
        before = ledger.to_json()
        parsed = note.parse(lesson['note'])
        checked = audit.audit_note(parsed, ledger, self.case)
        result = grader.grade(parsed, ledger, self.case, checked)
        rows = {row['id']: row for row in result['rows']}
        for key in ('character_quality', 'severity_quantity'):
            self.assertEqual(rows[key]['points_earned'], 2, rows[key])
        trigger = next(c for c in checked['claims'] if c['text'] == 'Energy drinks appear to trigger episodes.')
        self.assertEqual(trigger['concepts'], ['hpi_aggravating'])
        self.assertEqual(ledger.to_json(), before)


if __name__ == '__main__':
    unittest.main()
