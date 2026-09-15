"""Equivalent pain questions, partial timing knowledge, and evidence boundaries."""
import unittest
from pcmcse import cases, patient, evidence, record

class PainQuestionWordingTests(unittest.TestCase):
    def respond(self, cid, text, variant='base'):
        return patient.PatientEngine(cases.resolve(cid, variant)).respond(text, {})

    def test_radiation_noun_and_verb_reach_same_fact_on_all_paths(self):
        for cid, base in cases.all_cases().items():
            for variant in ['base']+[v['id'] for v in base.get('variants', [])]:
                c=cases.resolve(cid, variant)
                for q in ['Have you noticed any radiation of the pain?', 'Is the pain radiating anywhere?', 'Any radiation of the discomfort?']:
                    with self.subTest(case=cid, variant=variant, question=q):
                        _, expected=patient.PatientEngine(c).respond('Does the pain radiate?', {})
                        _, actual=patient.PatientEngine(c).respond(q, {})
                        self.assertEqual(actual.get('facts_released', []), expected.get('facts_released', []))
                        self.assertEqual(actual.get('concepts', {}), expected.get('concepts', {}))

    def test_noah_exact_sequence_and_notes(self):
        c=cases.resolve('cardio-febrile-cough'); p=patient.PatientEngine(c); state={}; ledger=evidence.Ledger()
        prompts=['have you noticed any radiation of the pain','does the pain radiate',
                 'is the pain constant or does it come and go','do you notice the pain only in the day or only at night']
        for i,q in enumerate(prompts):
            text,meta=p.respond(q,state)
            ledger.add(evidence.STUDENT,q);ledger.add(evidence.PATIENT,text,meta=meta)
            if i<2:
                self.assertIn('pain stays there',text.lower());self.assertEqual(meta['facts_released'],['hpi_radiation'])
            elif i==2:
                self.assertIn('sharp pain when I cough or breathe deeply',text)
                self.assertIn('whether it is constant or comes and goes',text)
                self.assertEqual(meta['facts_released'],['hpi_quality'])
                self.assertFalse(meta.get('checklist_hits'))
                self.assertEqual(meta['unavailable_dimensions'],['constancy'])
            else:
                self.assertIn('whether it varies between daytime and nighttime',text)
                self.assertFalse(meta['facts_released']);self.assertTrue(meta['no_information'])
        rows=[r for g in record.summarize(c,ledger.events)['groups'] for sec in g['sections'] for r in sec['items']]
        self.assertEqual({r['fact_id'] for r in rows if r.get('fact_id')},{'hpi_radiation','hpi_quality'})

    def test_noah_missing_pattern_is_not_fabricated_in_any_variant(self):
        base=cases.get('cardio-febrile-cough')
        for variant in ['base']+[v['id'] for v in base['variants']]:
            for q,dim in [('Is the pain constant or does it come and go?','constancy'),('Does the pain happen during the day or at night?','night_pattern')]:
                text,meta=self.respond(base['id'],q,variant)
                self.assertIn(dim,meta.get('unavailable_dimensions',[]))
                self.assertNotIn('hpi_timing',meta['facts_released'])
                self.assertNotRegex(text,r'only hurts|no pain between|pain is constant|pain comes and goes|pain is worse at night')

    def test_authored_night_patterns_remain_available(self):
        for cid,fid in [('gi-epigastric-melena','timing'),('cardio-orthopnea-edema','hpi_timing')]:
            for q in ['Does it bother you during the day or at night?', 'Is it worse at night?', 'What time of day do you notice it?']:
                text,meta=self.respond(cid,q)
                self.assertIn(fid,meta['facts_released'],(q,text))
                self.assertNotIn('night_pattern',meta.get('unavailable_dimensions',[]))

    def test_known_constancy_is_not_replaced_by_related_quality(self):
        text,meta=self.respond('cardio-palpitations','Is it constant or does it come and go?')
        self.assertTrue(meta['facts_released'],text)
        self.assertNotIn('constancy',meta.get('unavailable_dimensions',[]))
        self.assertNotIn('hpi_quality',meta['facts_released'])

    def test_timing_does_not_borrow_another_symptom(self):
        for cid,q in [('cardio-orthopnea-edema','Does the pain happen at night?'),
                      ('gi-epigastric-melena','Does the headache happen at night?'),
                      ('cardio-febrile-cough','Is the back pain constant or does it come and go?')]:
            text,meta=self.respond(cid,q)
            self.assertFalse(meta['facts_released'],(q,text,meta))

    def test_radiation_exposure_treatment_and_relatives_do_not_release_pain_history(self):
        for q in ['Have you had radiation therapy for pain?', 'Did your mother notice radiation of the pain?',
                  'Have you had radiation exposure?', 'What is radiation therapy?']:
            text,meta=self.respond('cardio-febrile-cough',q)
            self.assertNotIn('hpi_radiation',meta['facts_released'],(q,text))

    def test_compound_identity_and_radiation_keeps_both_answers(self):
        text,meta=self.respond('cardio-febrile-cough','What is your name and have you noticed any radiation of the pain?')
        self.assertIn('Noah Rivera',text)
        self.assertIn('hpi_radiation',meta['facts_released'])
        self.assertIn('name',meta['identity_fields'])

if __name__=='__main__':unittest.main()
