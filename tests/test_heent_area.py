"""HEENT findings belong to the examined area, not the abdominal fallback."""
import unittest
from pcmcse import cases, grader
class HeentAreaTests(unittest.TestCase):
    def test_authored_ear_and_throat_cases_use_heent_headers(self):
        for cid in ('heent-ear-pain','heent-sore-throat'):
            c=cases.resolve(cid)
            self.assertEqual(grader._relevant_regions(c['area_of_concern']), ['HEENT'])
            self.assertEqual(grader._aoc_headers(c), ['heent'])

    def test_explicit_heent_terms_not_unrelated_substrings(self):
        for term in ('HEENT','ENT','ear','eye','nose','throat'):
            self.assertEqual(grader._relevant_regions({'system':term}),['HEENT'])
        for term in ('Genitourinary','Gastrointestinal','Patient concern'):
            self.assertNotIn('HEENT',grader._relevant_regions({'system':term}))
        self.assertEqual(grader._relevant_regions({'system':'Cardiopulmonary'}),['Heart','Lungs'])

if __name__=='__main__': unittest.main()
