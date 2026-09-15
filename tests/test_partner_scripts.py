"""Print actor-reference coverage and disclosure checks, independent of live chat."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from pcmcse.cases import all_cases, resolve
from sparse_case_fixtures import without_supplemental_content
from pcmcse.teaching.partner import build_patient_script

LESSONS = Path(__file__).resolve().parents[1] / 'pcmcse' / 'teaching' / 'lessons'


def fixture(cid, variant='base'):
    lesson = next(l for l in json.loads((LESSONS / (cid + '.json')).read_text())['walkthroughs'] if l['variant_id'] == variant)
    case = resolve(cid, variant)
    return case, lesson, build_patient_script(case, lesson)


def topics(script):
    return {t['id']: t for s in script['sections'] for t in s['topics']}


def response(topic):
    return ' '.join([topic['answer']] + [f['answer'] for f in topic['followups']])


class PartnerScriptTests(unittest.TestCase):
    def test_every_case_fact_is_covered_once_and_inputs_are_unchanged(self):
        count = fact_count = original_fact_count = 0
        for cid in all_cases():
            for lesson in json.loads((LESSONS / (cid + '.json')).read_text())['walkthroughs']:
                case = resolve(cid, lesson['variant_id'])
                case_before, lesson_before = copy.deepcopy(case), copy.deepcopy(lesson)
                script = build_patient_script(case, lesson)
                with self.subTest(case=cid, variant=lesson['variant_id']):
                    expected = {f['id'] for f in case['facts']}
                    covered = script['briefing']['source_fact_ids'] + [fid for t in topics(script).values() for fid in t['source_fact_ids']]
                    self.assertEqual(expected, set(covered))
                    self.assertEqual(len(covered), len(set(covered)))
                    self.assertEqual(script['audit']['unresolved_fact_ids'], [])
                    self.assertEqual(case, case_before)
                    self.assertEqual(lesson, lesson_before)
                    self.assertEqual(build_patient_script(case, lesson), script)
                    self.assertEqual(len(script['sections']), 8)
                    self.assertEqual([s['letter'] for s in script['sections']], list('SMASHFMR'))
                    for topic in topics(script).values():
                        self.assertGreaterEqual(len(topic['questions']), 1)
                        self.assertLessEqual(len(topic['questions']), 3)
                count += 1
                fact_count += len(expected)
                original_fact_count += len(without_supplemental_content(case)["facts"])
        self.assertEqual(count, 82)
        self.assertEqual(original_fact_count, 3168)  # Original source inventory is preserved.
        self.assertGreater(fact_count, original_fact_count)

    def test_clinical_variation_uses_resolved_patient_answers(self):
        _, _, base = fixture('cardio-palpitations')
        _, _, longer = fixture('cardio-palpitations', 'cardio-palpitations--chronology')
        self.assertIn('6 hours', topics(base)['hpi_current_episode_onset']['answer'])
        self.assertIn('30 hours', topics(longer)['hpi_current_episode_onset']['answer'])
        self.assertNotIn('6 hours', topics(longer)['hpi_current_episode_onset']['answer'])

    def test_broad_medication_reply_does_not_release_adherence_automatically(self):
        _, _, script = fixture('cardio-orthopnea-edema')
        section = next(s for s in script['sections'] if s['id'] == 'medications')
        self.assertIn('lisinopril 10 mg daily', section['entry']['answer'])
        self.assertIn('furosemide 20 mg daily', section['entry']['answer'])
        self.assertNotIn('4 days', section['entry']['answer'])
        focused = topics(script)['history_medications_2']
        self.assertEqual(focused['title'], 'Missed doses and refills')
        self.assertIn('4 days', focused['answer'])
        self.assertIn('missed', focused['questions'][0])

    def test_allergy_trigger_and_reaction_remain_together_but_separately_released(self):
        _, _, script = fixture('renal-flank-pain')
        allergy = topics(script)['allergies']
        self.assertIn('sulfa', allergy['answer'])
        self.assertNotIn('hives', allergy['answer'])
        self.assertEqual(allergy['followups'][0]['question'], 'What reaction did you have?')
        self.assertIn('hives', allergy['followups'][0]['answer'])

    def test_unsupported_information_is_an_actor_instruction_not_a_patient_denial(self):
        case, lesson, _ = fixture('cardio-febrile-cough')
        script = build_patient_script(without_supplemental_content(case), lesson)
        self.assertIn('outside the patient role', script['briefing']['unknown_rule'])
        self.assertIn('not provided', script['briefing']['unknown_rule'])
        self.assertIn('not turn it into a denial', script['briefing']['unknown_rule'])
        med = response(topics(script)['history_medications_1'])
        self.assertEqual(med, 'I took acetaminophen.')
        self.assertNotRegex(med, r'\d+\s*(mg|milligram)')
        dialogue = ' '.join(response(t) for t in topics(script).values())
        self.assertNotIn('muscle aches', dialogue.lower())
        self.assertNotIn('not provided in this case', dialogue)

    def test_affect_that_is_a_concern_is_not_used_as_a_greeting_direction(self):
        _, _, script = fixture('cardio-febrile-cough')
        concern = 'Could I give this to the people at home?'
        self.assertNotIn(concern, script['briefing']['acting_directions'])
        self.assertNotIn(concern, script['briefing']['opening'])
        self.assertEqual(topics(script)['patient_concern']['answer'], concern)
        self.assertNotIn('pneumonia', ' '.join(response(t) for t in topics(script).values()).lower())

    def test_known_history_is_not_mistaken_for_diagnosis_leakage(self):
        _, _, script = fixture('cardio-orthopnea-edema')
        self.assertIn('heart failure last year', response(topics(script)['history_pmh_1']))
        self.assertNotIn('acute decompensated', json.dumps(script).lower())

    def test_unresolved_relationship_label_is_not_invented(self):
        case, lesson, _ = fixture('renal-flank-pain')
        # Preserve the old-source safeguard after the new authored relationship is clarified.
        old = next(f for f in case['facts'] if f['id'] == 'history_sexual_partners')
        old['value'] = old['sp_says'][0] = 'I have one male partner, my boyfriend, and no new partners.'
        script = build_patient_script(case, lesson)
        home = topics(script)['history_household']
        partner = topics(script)['history_sexual_partners']
        self.assertEqual(home['answer'], 'I live off campus.')
        self.assertEqual(partner['answer'], 'I have one male partner and no new partners.')
        self.assertTrue(script['audit']['known_conflicts'])
        self.assertIn('inconsistent', home['actor_note'])
        self.assertNotRegex(home['answer'] + partner['answer'], 'husband|boyfriend')


    def test_current_authored_relationship_keeps_supplied_husband_label(self):
        _, _, script = fixture('renal-flank-pain')
        self.assertIn('husband', response(topics(script)['history_household']))
        self.assertIn('husband', response(topics(script)['history_sexual_partners']))
        self.assertFalse(script['audit']['known_conflicts'])

    def test_actor_script_does_not_add_observed_exam_findings_to_dialogue(self):
        case, _, script = fixture('renal-flank-pain')
        dialogue = ' '.join(response(t) for t in topics(script).values())
        for finding in case['exam_findings']['heart_auscultate']:
            self.assertNotIn(finding['text'], dialogue)
        refused = next(n for n in script['actor_notes'] if n.get('source_refusal') == 'gyn')
        self.assertIn('decline', refused['text'])
        self.assertIn('Do not supply a finding', refused['text'])

    def test_additional_actor_fact_is_not_marked_as_demonstrated_evidence(self):
        case, lesson, script = fixture('neuro-positional-vertigo')
        added = {f['id'] for f in case['facts'] if f.get('authoring')}
        self.assertEqual(set(script['audit']['not_in_demonstrated_encounter']), added | {'hpi_radiation'})
        self.assertIn('hpi_radiation', topics(script))
        self.assertNotIn('hpi_radiation', [fid for t in lesson['timeline'] for fid in t.get('fact_ids', [])])

    def test_exposure_question_does_not_claim_activity_at_onset(self):
        _, _, cough = fixture('cardio-febrile-cough')
        exposure = topics(cough)['hpi_setting']
        self.assertEqual(exposure['title'], 'Sick contacts')
        self.assertTrue(any('sick contacts' in q.lower() for q in exposure['questions']))
        self.assertFalse(any('doing' in q.lower() or 'activity' in q.lower() for q in exposure['questions']))
        _, _, breathing = fixture('cardio-orthopnea-edema')
        diet = topics(breathing)['hpi_setting']
        self.assertEqual(diet['title'], 'Recent dietary changes')
        self.assertTrue(all('diet' in q.lower() or 'eating' in q.lower() for q in diet['questions']))

    def test_timing_aliases_do_not_invent_episode_duration(self):
        for cid, fid in [('cardio-orthopnea-edema', 'hpi_timing'), ('gi-epigastric-melena', 'timing'),
                         ('neuro-positional-vertigo', 'hpi_timing')]:
            _, _, script = fixture(cid)
            with self.subTest(case=cid):
                self.assertFalse(any('how long' in q.lower() for q in topics(script)[fid]['questions']))
        _, _, spinning = fixture('neuro-positional-vertigo')
        duration = topics(spinning)['hpi_episode_duration']
        self.assertTrue(any('how long' in q.lower() for q in duration['questions']))
        self.assertIn('20 seconds', duration['answer'])

    def test_discourse_question_is_not_a_standalone_concern_response(self):
        _, _, script = fixture('renal-flank-pain')
        concern = topics(script)['concern_kidneys']
        self.assertIn("scared it's my kidneys", concern['answer'])
        self.assertNotEqual(concern['answer'], 'Honestly?')
        self.assertIn('aunt', concern['followups'][0]['answer'])

    def test_full_medicine_question_keeps_names_and_links_other_doses(self):
        _, _, gi = fixture('gi-epigastric-melena')
        medication = topics(gi)['medications']
        self.assertIn('Ibuprofen', medication['answer'])
        self.assertIn('iron pills', medication['answer'])
        treatment_ref = next(r for r in medication['crossrefs'] if r['section_id'] == 'history')
        self.assertIn('antacids', response(topics(gi)[treatment_ref['topic_id']]))
        _, _, cough = fixture('cardio-febrile-cough')
        medication = topics(cough)['history_medications_1']
        treatment_ref = next(r for r in medication['crossrefs'] if r['section_id'] == 'history')
        self.assertIn('500 mg twice yesterday', response(topics(cough)[treatment_ref['topic_id']]))
        self.assertIn('complete medication question', medication['actor_note'])

    def test_compound_questions_release_requested_followups_without_reasking(self):
        _, _, script = fixture('gi-epigastric-melena')
        self.assertIn('Answer every part of a compound question', script['briefing']['volunteer_rule'])
        self.assertIn('without making the student ask twice', script['briefing']['volunteer_rule'])
        self.assertIn('unasked bundled symptom', script['briefing']['volunteer_rule'])
        allergy = topics(script)['allergies']
        self.assertIn('give both parts', allergy['actor_note'])
        self.assertIn('swelled', allergy['followups'][0]['answer'])

    def test_source_supported_position_refusal_is_available_to_actor(self):
        _, _, script = fixture('cardio-orthopnea-edema')
        note = next(n for n in script['actor_notes'] if n.get('source_position') == 'supine')
        self.assertIn('Lying flat makes it hard to breathe. Can I stay sitting up?', note['text'])
        self.assertEqual(note['source_fact_ids'], ['symptom_position_intolerance'])

    def test_recent_procedure_alias_preserves_recent_qualifier(self):
        _, _, script = fixture('cardio-febrile-cough')
        recent = topics(script)['history_recent_surgery']
        self.assertTrue(all('recent' in q.lower() for q in recent['questions']))
        earlier = topics(script)['history_psh_1']
        self.assertIn('20', earlier['answer'])
        self.assertNotEqual(recent['questions'], earlier['questions'])

    def test_vaccination_and_eczematous_history_do_not_get_generic_pmh_aliases(self):
        _, _, cough = fixture('cardio-febrile-cough')
        vaccines = topics(cough)['history_pmh_2']
        self.assertTrue(all('vaccine' in q.lower() or 'vaccination' in q.lower() for q in vaccines['questions']))
        _, _, swallowing = fixture('gi-progressive-dysphagia')
        eczema = topics(swallowing)['history_eczema']
        self.assertTrue(all('eczema' in q.lower() for q in eczema['questions']))
        endoscopy = topics(swallowing)['history_pmh_2']
        self.assertTrue(all('endoscop' in q.lower() or 'camera examination' in q.lower() for q in endoscopy['questions']))

    def test_family_fact_number_does_not_imply_siblings(self):
        _, _, script = fixture('cardio-pleuritic-dyspnea')
        clotting = topics(script)['history_family_3']
        self.assertEqual(clotting['title'], 'Inherited clotting conditions')
        self.assertTrue(all('clotting' in q.lower() for q in clotting['questions']))
        self.assertFalse(any('sibling' in q.lower() for q in clotting['questions']))
        _, _, diarrhea = fixture('gi-diarrhea-dehydration')
        inherited = topics(diarrhea)['history_family_3']
        self.assertEqual(inherited['title'], 'Other inherited conditions')
        self.assertFalse(any('sibling' in q.lower() for q in inherited['questions']))

    def test_focused_topics_have_only_semantically_matching_prompts(self):
        _, _, heart = fixture('cardio-chest-pressure')
        exercise = topics(heart)['history_exercise']
        self.assertTrue(all('exercise' in q.lower() or 'active' in q.lower() for q in exercise['questions']))
        admission = topics(heart)['history_admissions']
        self.assertTrue(all('append' in q.lower() for q in admission['questions']))
        _, _, orthopnea = fixture('cardio-orthopnea-edema')
        missed = topics(orthopnea)['history_medications_2']
        self.assertFalse(any(q.startswith('What medicines') for q in missed['questions']))
        self.assertTrue(all('missed' in q or 'prescribed' in q for q in missed['questions']))

    def test_unknown_focused_question_does_not_gain_generic_alias(self):
        case, lesson, _ = fixture('cardio-febrile-cough')
        target = next(f for f in case['facts'] if f['id'] == 'history_recent_surgery')
        target['example_questions'] = ['Any procedures in the last fortnight?']
        script = build_patient_script(case, lesson)
        self.assertEqual(topics(script)['history_recent_surgery']['questions'], ['Any procedures in the last fortnight?'])

    def test_related_subjects_have_consistent_references(self):
        _, _, script = fixture('renal-flank-pain')
        by_id = topics(script)
        for topic in by_id.values():
            for ref in topic['crossrefs']:
                self.assertIn(ref['topic_id'], by_id)
        self.assertEqual(by_id['treatments_tried']['crossrefs'][0]['section_id'], 'medications')
        self.assertEqual(by_id['past_occurrence']['crossrefs'][0]['section_id'], 'medical')
        self.assertIn('What do you do for work', by_id['social_occupation']['questions'][1])


if __name__ == '__main__':
    unittest.main()
