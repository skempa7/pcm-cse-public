"""Render eligibility for the complete authored library, without changing facts."""
import copy
import unittest

from pcmcse import cases, presentation


class PatientRenderProfiles(unittest.TestCase):
    def test_all_82_authored_paths_have_supported_models(self):
        paths = []
        for base in cases.all_cases().values():
            for variant in ['base'] + [v['id'] for v in base.get('variants', [])]:
                case = cases.resolve(base['id'], variant)
                before = copy.deepcopy(case)
                profile = presentation.appearance(case)
                with self.subTest(case=base['id'], variant=variant):
                    self.assertEqual(profile.get('model'), 'mpfb-public-patient')
                    self.assertEqual(profile['age'], case['patient']['age'])
                    self.assertEqual(profile['presentation'], case['patient']['sex'])
                    self.assertIn(profile['bodyBuild'], ['short-slender', 'standard', 'tall-full'])
                    self.assertEqual(case, before, 'Visual adaptation cannot change saved case facts')
                paths.append((base['id'], variant))
        self.assertEqual(len(paths), 82)

    def test_explicit_adult_model_does_not_require_legacy_cohort(self):
        for age in [18, 24, 31, 38, 59, 120]:
            with self.subTest(age=age):
                case = {'patient': {'age': age, 'sex': 'female', 'appearance': {'model': 'mpfb-public-patient'}}}
                profile = presentation.appearance(case)
                self.assertEqual(profile.get('model'), 'mpfb-public-patient')
                self.assertEqual(profile['age'], age)

    def test_unassigned_child_unknown_and_invalid_ages_do_not_get_adult_model(self):
        for age in [None, '38', True, -1, 0, 17, 121]:
            with self.subTest(age=age):
                case = {'patient': {'age': age, 'sex': 'female', 'cohort': 'public-adults-v1', 'appearance': {'model': 'mpfb-public-patient'}}}
                self.assertNotIn('model', presentation.appearance(case))
        for patient in [
            {'name': 'Amina Reed', 'age': 38, 'sex': 'female'},
            {'name': 'Amina Reed', 'age': 38, 'appearance': {'model': 'mpfb-public-patient'}},
            {'age': 38, 'sex': 'female', 'appearance': {'model': 'unreviewed-model'}},
        ]:
            self.assertNotIn('model', presentation.appearance({'patient': patient}))

    def test_legacy_cohort_and_hidden_fact_independence(self):
        case = {'patient': {'age': 25, 'sex': 'male', 'cohort': 'public-adults-v1'}}
        expected = presentation.appearance(case)
        self.assertEqual(expected.get('model'), 'mpfb-public-patient')
        case.update(diagnosis='secret', facts=[{'response': 'hidden abnormal finding'}], exam_findings={'skin': 'secret'})
        self.assertEqual(presentation.appearance(case), expected)


if __name__ == '__main__':
    unittest.main()
