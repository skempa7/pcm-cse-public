"""Social-history qualifiers require separate, actually delivered evidence."""
import copy
import unittest
from pcmcse import audit, cases, evidence, note


class SocialHistoryEvidenceTests(unittest.TestCase):
    def ledger(self, case, values):
        out = evidence.Ledger()
        for fid, speech in values.items():
            fact = next(f for f in case['facts'] if f['id'] == fid)
            out.add(evidence.PATIENT, speech, meta={'facts_released': [fid], 'concepts': copy.deepcopy(fact['concepts'])})
        return out

    def audit(self, case, ledger, text, section='S', header='SH'):
        result = audit.audit_note(note.parse({section: header + ': ' + text}), ledger, case)
        return result['claims']

    def test_former_smoking_is_not_a_denial_of_all_previous_smoking(self):
        case = cases.resolve('cardio-presyncope')
        source = next(f['value'] for f in case['facts'] if f['id'] == 'tobacco_use')
        ledger = self.ledger(case, {'tobacco_use': source})
        before = ledger.to_json()
        for text in ['Former smoker.', 'Former smoker, 5 cigarettes/day from ages 18–22.']:
            self.assertEqual([c['verdict'] for c in self.audit(case, ledger, text)], ['supported'])
        for text in ['Never smoker.', 'Current smoker.', 'Former smoker, 6 cigarettes/day from ages 18–22.',
                     'Former smoker, 5 cigarettes/day from ages 16–22.']:
            self.assertEqual(self.audit(case, ledger, text)[0]['verdict'], 'contradicts', text)
        self.assertEqual(ledger.to_json(), before)

    def test_unasked_or_uncertain_former_status_cannot_be_credited(self):
        case = cases.resolve('cardio-presyncope')
        self.assertEqual(self.audit(case, evidence.Ledger(), 'Former smoker.')[0]['verdict'], 'unsupported')
        for reply in ['I never smoked tobacco.', 'I smoke 5 cigarettes daily.',
                      'My brother used to smoke half a pack a day for 6 years. He quit 2 years ago.',
                      'I might have smoked, but I cannot remember.', 'Thank you for listening.']:
            ledger = self.ledger(case, {'tobacco_use': reply})
            self.assertNotEqual(self.audit(case, ledger, 'Former smoker.')[0]['verdict'], 'supported', reply)
        ledger = self.ledger(case, {'tobacco_use': 'I quit smoking 2 years ago after 3 pack-years.'})
        self.assertNotEqual(self.audit(case, ledger, 'Former smoker, 5 cigarettes/day from ages 18–22.')[0]['verdict'], 'supported')
        self.assertEqual(self.audit(case, ledger, 'Former smoker, no lung disease.')[0]['verdict'], 'not_evaluated')

    def test_topic_identifiers_and_explicit_pack_year_arithmetic(self):
        examples = [
            ('pulm-chronic-productive-cough', 'Former smoker: 32 pack-years, quit 2 years ago.', 32),
            ('msk-knee-injury', 'Former smoker: 5 pack-years, quit 15 years ago.', 5),
            ('skin-localized-redness', 'Former smoker: 6 pack-years, quit 5 years ago.', 6),
        ]
        for cid, text, pack_years in examples:
            case = cases.resolve(cid)
            fact = next(f for f in case['facts'] if f.get('history_topic') == 'tobacco')
            ledger = self.ledger(case, {fact['id']: fact['value']})
            self.assertEqual(self.audit(case, ledger, text)[0]['verdict'], 'supported', cid)
            self.assertEqual(self.audit(case, ledger, text.replace(str(pack_years)+' pack-years', '99 pack-years'))[0]['verdict'], 'contradicts', cid)
            self.assertEqual(self.audit(case, evidence.Ledger(), text)[0]['verdict'], 'unsupported', cid)
            self.assertEqual(self.audit(case, ledger, 'Former smoker: '+str(pack_years)+' pack-years, quit 100 years ago.')[0]['verdict'], 'contradicts', cid)
        case = cases.resolve('msk-knee-injury')
        for source in ['I quit smoking 15 years ago.', 'I smoked half a pack daily. I quit 15 years ago.',
                       'I smoked for 10 years. I quit 15 years ago.', 'My father smoked half a pack daily for 10 years and quit 15 years ago.']:
            ledger = self.ledger(case, {'history_smoking': source})
            self.assertNotEqual(self.audit(case, ledger, 'Former smoker: 5 pack-years.')[0]['verdict'], 'supported')

    def test_lifetime_never_needs_a_delivered_lifetime_reply(self):
        for cid in ['msk-hand-stiffness', 'msk-shoulder-overuse', 'pulm-episodic-wheeze']:
            case = cases.resolve(cid)
            fact = next(f for f in case['facts'] if f.get('history_topic') == 'tobacco')
            ledger = self.ledger(case, {fact['id']: fact['value']})
            self.assertEqual(self.audit(case, ledger, 'Never smoked.')[0]['verdict'], 'supported', cid)
            self.assertEqual(self.audit(case, evidence.Ledger(), 'Never smoked.')[0]['verdict'], 'unsupported', cid)
            self.assertNotEqual(self.audit(case, self.ledger(case, {fact['id']: 'I quit smoking 2 years ago after 3 pack-years.'}), 'Never smoked.')[0]['verdict'], 'supported', cid)

    def test_never_smoking_does_not_establish_never_vaping(self):
        case = cases.resolve('pulm-episodic-wheeze')
        only_smoking = self.ledger(case, {'history_smoking': 'I have never smoked.'})
        self.assertEqual(self.audit(case, only_smoking, 'Never smoked.')[0]['verdict'], 'supported')
        self.assertEqual(self.audit(case, only_smoking, 'Never smoked or vaped.')[0]['verdict'], 'unsupported')
        both = self.ledger(case, {'history_smoking': 'I have never smoked or vaped.'})
        self.assertEqual(self.audit(case, both, 'Never smoked or vaped.')[0]['verdict'], 'supported')

    def test_combined_condom_and_new_partner_summary_needs_both_replies(self):
        case = cases.resolve('renal-flank-pain')
        facts = {f['id']: f for f in case['facts']}
        values = {fid: facts[fid]['value'] for fid in ['history_contraception', 'history_sexual_partners']}
        text = 'Inconsistent condoms, no new partner.'
        ledger = self.ledger(case, values)
        before = ledger.to_json()
        result = self.audit(case, ledger, text)[0]
        self.assertEqual(result['verdict'], 'supported')
        self.assertEqual(len(result['evidence']), 2)
        self.assertEqual(ledger.to_json(), before)
        for fid in values:
            partial = self.ledger(case, {fid: values[fid]})
            self.assertEqual(self.audit(case, partial, text)[0]['verdict'], 'unsupported')
        self.assertEqual(self.audit(case, evidence.Ledger(), text)[0]['verdict'], 'unsupported')

    def test_sexual_history_cannot_reverse_qualifiers_or_borrow_extra_normals(self):
        case = cases.resolve('renal-flank-pain')
        values = {fid: next(f['value'] for f in case['facts'] if f['id'] == fid)
                  for fid in ['history_contraception', 'history_sexual_partners']}
        ledger = self.ledger(case, values)
        for text in ['Always uses condoms, no new partner.', 'No condom use, no new partner.', 'Inconsistent condoms, a new sexual partner.']:
            self.assertEqual(self.audit(case, ledger, text)[0]['verdict'], 'contradicts', text)
        # The note splitter may separate the extra negative; it must not borrow
        # support from either valid social-history clause.
        claims = self.audit(case, ledger, 'Inconsistent condoms, no new partner, no sexually transmitted infection.')
        infection = next(c for c in claims if 'infection' in c['text'])
        self.assertNotEqual(infection['verdict'], 'supported')
        conflict = self.audit(case, ledger, 'Always uses condoms and inconsistent condoms.')[0]
        self.assertNotEqual(conflict['verdict'], 'supported')
        changed = dict(values, history_sexual_partners='I have a new sexual partner.')
        self.assertEqual(self.audit(case, self.ledger(case, changed), 'No new partner.')[0]['verdict'], 'contradicts')
        relative = dict(values, history_sexual_partners='My brother has no new partners.')
        self.assertEqual(self.audit(case, self.ledger(case, relative), 'No new partner.')[0]['verdict'], 'unsupported')
        unknown = dict(values, history_sexual_partners='I am not sure whether my partner has new partners.')
        self.assertEqual(self.audit(case, self.ledger(case, unknown), 'No new partner.')[0]['verdict'], 'unsupported')


if __name__ == '__main__':
    unittest.main()
