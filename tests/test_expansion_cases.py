"""Reviewed new-case inventory, source/evidence contracts and interview regressions.

These checks prove authored consistency and measured engine behavior, not faculty
approval, clinical validation, or support for arbitrary unreviewed paraphrases.
"""
import copy
import json
import unittest
from collections import Counter
from pathlib import Path

from pcmcse import audit, cases, dialogue, evidence, grader, note, physexam, teaching
from pcmcse.patient import PatientEngine
from tools.build_expansion_cases import CASES, build_case

ROOT = Path(__file__).resolve().parents[1]
# This explicit inventory is independent of discovery and protects against omission.
EXPECTED = {
    'cardio-exertional-leg-pain': ('Cardiovascular', 'male', 37, 10),
    'pulm-episodic-wheeze': ('Respiratory', 'female', 34, 7),
    'pulm-chronic-productive-cough': ('Respiratory', 'male', 33, 7),
    'msk-shoulder-overuse': ('Musculoskeletal', 'female', 34, 10),
    'msk-knee-injury': ('Musculoskeletal', 'male', 34, 10),
    'msk-hand-stiffness': ('Musculoskeletal', 'female', 34, 9),
    'heent-ear-pain': ('HEENT', 'male', 33, 8),
    'heent-sore-throat': ('HEENT', 'female', 34, 8),
    'skin-contact-rash': ('Skin', 'female', 34, 7),
    'skin-localized-redness': ('Skin', 'male', 34, 8),
}


def raw_case(cid):
    return json.loads((ROOT/'pcmcse'/'cases'/(cid.replace('-', '_')+'.json')).read_text())


def reply_ledger(case, ids):
    ledger = evidence.Ledger()
    for fid in ids:
        fact = next(f for f in case['facts'] if f['id'] == fid)
        ledger.add(evidence.PATIENT, fact['value'], meta={
            'facts_released': [fid], 'concepts': copy.deepcopy(fact['concepts'])})
    return ledger


def verdicts(case, ledger, text):
    return [c['verdict'] for c in audit.audit_note(note.parse({'S': 'HPI: '+text}), ledger, case)['claims']]


class ExpansionInventoryTests(unittest.TestCase):
    def test_exact_ten_new_presentations_with_reviewed_fact_and_exam_counts(self):
        self.assertEqual({s['cid'] for s in CASES}, set(EXPECTED))
        self.assertEqual(len(CASES), 10)
        totals = Counter()
        for cid, (system, sex, facts, exams) in EXPECTED.items():
            c = raw_case(cid)
            self.assertEqual(c['id'], cid)
            self.assertEqual(c['system'], system)
            self.assertEqual(c['patient']['sex'], sex)
            self.assertEqual(len(c['facts']), facts)
            self.assertEqual(len(c['exam_findings']), exams)
            self.assertFalse(c.get('variants'))
            package = json.loads((ROOT/'pcmcse'/'teaching'/'lessons'/(cid+'.json')).read_text())
            self.assertEqual([w['variant_id'] for w in package['walkthroughs']], ['base'])
            totals.update({sex: 1, 'facts': facts, 'exams': exams})
        self.assertEqual(totals, Counter(female=5, male=5, facts=341, exams=84))

    def test_serializer_round_trip_does_not_depend_on_existing_case_templates(self):
        for index, spec in enumerate(CASES):
            with self.subTest(case=spec['cid']):
                original = copy.deepcopy(spec)
                self.assertEqual(build_case(spec, index), raw_case(spec['cid']))
                self.assertEqual(spec, original)

    def test_every_history_and_reviewed_positive_negative_has_a_delivery_contract(self):
        for cid in EXPECTED:
            c = raw_case(cid)
            categories = {f['category'] for f in c['facts']}
            self.assertTrue({'chief_complaint','onset','location','quality','severity','timing','pmh','psh','medications','allergies','social','family'} <= categories, cid)
            ros = Counter(f.get('ros_system') for f in c['facts'] if f.get('ros_system'))
            self.assertEqual(len(ros), 3, cid)
            self.assertTrue(all(n >= 3 for n in ros.values()), cid)
            checklist = {x['id'] for x in c['checklist']['history']}
            for f in c['facts']:
                self.assertIn(f['checklist'], checklist)
                self.assertTrue(f['example_questions'])
                self.assertTrue(f['authored_note'])
                contract = f['delivery_contract']['versions']
                self.assertTrue(any(v['text'] == f['value'] and v['concepts'] == f['concepts'] and v['complete_fact'] for v in contract))
            clinical = [s for s in c['sources'] if s.get('kind') == 'supplementary_clinical']
            self.assertTrue(clinical, cid)
            self.assertTrue(all(s['url'].startswith('https://') and s.get('reviewed') for s in clinical))

    def test_supported_distinct_differentials_and_system_specific_methods(self):
        for cid in EXPECTED:
            c = cases.resolve(cid)
            self.assertEqual([d['rank'] for d in c['differentials']], [1,2,3])
            self.assertEqual(len({d['vindicate'] for d in c['differentials']}), 3)
            available = {f['id'] for f in c['facts']} | {r['id'] for rows in c['exam_findings'].values() for r in rows}
            for d in c['differentials']:
                self.assertTrue(d['supported_by'])
                self.assertLessEqual(set(d['supported_by']), available)
                self.assertTrue(d['teaching_context'])
            l = teaching.read(cid)
            parsed = note.parse(l['note'])
            ledger = evidence.Ledger(l['ledger'])
            result = grader.grade(parsed, ledger, c, audit.audit_note(parsed, ledger, c))
            self.assertEqual(result['assessment_meta']['distinct_letters'], 3, cid)
            self.assertEqual(len(result['assessment_meta']['matched']), 3, cid)
            if c['system'] in ('Skin','Musculoskeletal'):
                self.assertNotIn('auscultate', c['area_of_concern']['required_methods'])
            if c['system'] == 'Skin':
                self.assertIn('skin_palpate', c['exam_findings'])
                self.assertNotIn('msk_palpate', c['exam_findings'])
                self.assertEqual(physexam.CATALOG_BY_ID['skin_palpate']['region'], 'Skin')

    def test_complete_examples_release_history_and_all_eighty_four_actual_findings(self):
        total = 0
        for cid in EXPECTED:
            c = cases.resolve(cid)
            l = teaching.read(cid)
            self.assertEqual(l['missing_example_facts'], [], cid)
            self.assertLessEqual(l['estimated_encounter_s'], 840, cid)
            self.assertLessEqual(l['note_words'], 550, cid)
            events = {e['seq']: e for e in l['ledger']}
            released = {fid for e in events.values() if e['kind'] == evidence.PATIENT for fid in e['meta'].get('facts_released', [])}
            self.assertLessEqual({f['id'] for f in raw_case(cid)['facts']}, released, cid)
            actions = [r for r in l['timeline'] if r.get('maneuver_id')]
            self.assertEqual(len(actions), EXPECTED[cid][3])
            for row in actions:
                obtained = [events[seq] for seq in row['event_ids'] if events[seq]['kind'] == evidence.EXAM_FINDING]
                self.assertEqual(len(obtained), 1)
                self.assertEqual(row['finding'], obtained[0]['text'])
                self.assertIn(row['finding'], l['note']['O'])
                total += 1
            result = audit.audit_note(note.parse(l['note']), evidence.Ledger(l['ledger']), c)
            bad = [(x['text'],x['verdict']) for x in result['claims'] if x['verdict'] in ('unsupported','contradicts','overbroad','counseling_unsupported')]
            self.assertEqual(bad, [], cid)
        self.assertEqual(total, 84)


class InterviewQuestionRegressionTests(unittest.TestCase):
    def test_out_of_order_common_phrases_across_all_new_and_established_cases(self):
        for cid in list(EXPECTED) + ['cardio-chest-pressure','renal-flank-pain']:
            c = cases.resolve(cid)
            engine = PatientEngine(c)
            state = {'opened': True, 'open_budget': 0}
            response, _ = engine.respond('What is your name and how old are you?', state)
            self.assertIn(c['patient']['name'], response)
            self.assertIn(str(c['patient']['age']), response)
            for question, expected in [('Any operations?', {'psh'}),
                                       ('What do you take every day?', {'medications'}),
                                       ('Any allergies, and what happens?', {'allergies'})]:
                response, meta = engine.respond(question, state)
                spoken = [engine.facts[fid] for fid in meta['facts_released']]
                self.assertTrue(spoken, (cid,question,response))
                self.assertEqual({f['category'] for f in spoken}, expected, (cid,question,response))
            response, meta = engine.respond('How much do you smoke or drink?', state)
            topics = set().union(*(engine._fact_subjects(engine.facts[fid]) for fid in meta['facts_released']))
            self.assertEqual(topics, {'tobacco','alcohol'}, (cid,response))
            response, meta = engine.respond('When did this first start?', state)
            self.assertTrue(meta['facts_released'], (cid,response))
            self.assertEqual({engine.facts[fid]['category'] for fid in meta['facts_released']}, {'onset'}, (cid,response))

    def test_compound_knee_onset_releases_actual_injury_activity_without_borrowing_exposures(self):
        case=cases.resolve('msk-knee-injury');engine=PatientEngine(case)
        reply,meta=engine.respond('When did the knee pain start, and what were you doing?', {})
        self.assertEqual(set(meta['facts_released']), {'hpi_onset','hpi_setting'})
        self.assertIn('Three days ago.',reply)
        self.assertIn('I turned while carrying a box, with my right foot planted.',reply)
        self.assertNotIn('does not specify',reply)
        for cid in EXPECTED:
            if cid=='msk-knee-injury':continue
            engine=PatientEngine(cases.resolve(cid))
            reply,meta=engine.respond('What were you doing when this started?', {})
            self.assertEqual(meta['facts_released'], [], (cid,reply))
            self.assertTrue(meta.get('no_information'), (cid,reply))
        # Removing the authored activity flag must restore uncertainty, rather
        # than returning any generic setting row as an inferred onset mechanism.
        case=copy.deepcopy(case)
        next(f for f in case['facts'] if f['id']=='hpi_setting').pop('onset_activity')
        _,meta=PatientEngine(case).respond('What were you doing when this started?', {})
        self.assertEqual(meta['facts_released'], [])

    def test_initial_bare_duration_uses_only_the_unique_presenting_onset(self):
        for cid in EXPECTED:
            case = cases.resolve(cid)
            for prompt in ('how long', 'How long?'):
                engine = PatientEngine(case)
                reply, meta = engine.respond(prompt, {})
                self.assertEqual(meta['facts_released'], ['hpi_onset'], (cid, reply))
                self.assertIn(engine.facts['hpi_onset']['value'], reply)
            # Introductions establish identity, not a competing symptom duration.
            engine = PatientEngine(case); state = {}
            engine.respond('What is your name and age?', state)
            _, meta = engine.respond('How long?', state)
            self.assertEqual(meta['facts_released'], ['hpi_onset'], cid)
        case = cases.resolve('pulm-episodic-wheeze')
        case['facts'] = [f for f in case['facts'] if f['category'] != 'onset']
        _, meta = PatientEngine(case).respond('How long?', {})
        self.assertEqual(meta['facts_released'], [])

    def test_true_background_followups_keep_context_and_episode_duration_returns_to_hpi(self):
        for cid in ['cardio-chest-pressure','pulm-episodic-wheeze','cardio-exertional-leg-pain']:
            c = cases.resolve(cid); engine = PatientEngine(c); state = {'opened':True,'open_budget':0}
            engine.respond('Do you smoke?', state)
            _, meta = engine.respond('How long?', state)
            self.assertTrue(meta['facts_released'])
            self.assertEqual(set().union(*(engine._fact_subjects(engine.facts[f]) for f in meta['facts_released'])), {'tobacco'})
            reply, meta = engine.respond('How long does each episode last?', state)
            self.assertTrue(meta['facts_released'], (cid, reply))
            self.assertTrue(all(engine.facts[f].get('temporal_role') == 'episode_duration' for f in meta['facts_released']), (cid, reply))
            engine.respond('What medicines do you take?', state)
            _, meta = engine.respond('How often do you take that?', state)
            self.assertTrue(meta['facts_released'])
            self.assertEqual({engine.facts[f]['category'] for f in meta['facts_released']}, {'medications'})

    def test_compound_segment_context_is_local_without_altering_prior_turn_on_failure(self):
        c=cases.resolve('pulm-episodic-wheeze');p=PatientEngine(c);state={'opened':True,'open_budget':0}
        p.respond('Any operations?', state)
        reply,meta=p.respond('Any allergies, and what happens?',state)
        self.assertEqual(meta['facts_released'], ['history_drug_reactions'])
        self.assertNotIn('wisdom', reply.lower())
        self.assertEqual(reply.lower().count('rash'),1)
        for text in ['Is it sharp or dull?', 'Does pain go into the left arm and jaw?', 'Is it constant or intermittent?']:
            self.assertEqual(dialogue.segment(text), [text])
        self.assertEqual(len(dialogue.segment('How much do you drink or smoke?')),2)


class DeliveredEvidenceRegressionTests(unittest.TestCase):
    def test_numeric_out_of_ten_requires_delivered_severity_and_matching_rating(self):
        c=cases.resolve('cardio-exertional-leg-pain')
        ledger=reply_ledger(c,['hpi_severity']);before=ledger.to_json()
        self.assertEqual(verdicts(c,ledger,'Pain 6/10.'),['supported'])
        self.assertEqual(verdicts(c,ledger,'Pain 7/10.'),['contradicts'])
        self.assertNotIn('supported',verdicts(c,evidence.Ledger(),'Pain 6/10.'))
        unrelated=reply_ledger(c,['history_daily_medication'])
        self.assertNotIn('supported',verdicts(c,unrelated,'Pain 6/10.'))
        self.assertEqual(ledger.to_json(),before)

    def test_contact_symptom_and_modifier_require_matching_delivered_subject(self):
        c=cases.resolve('msk-hand-stiffness');ledger=reply_ledger(c,['hpi_setting']);before=ledger.to_json()
        text='Preceding mild respiratory illness and child exposure with slapped-cheek rash.'
        self.assertEqual(verdicts(c,ledger,text),['supported'])
        self.assertEqual(verdicts(c,evidence.Ledger(),text),['unsupported'])
        self.assertEqual(verdicts(c,ledger,text.replace('mild','severe')),['unsupported'])
        self.assertEqual(verdicts(c,ledger,text.replace('child','coworker')),['unsupported'])
        self.assertNotIn('supported',verdicts(c,ledger,'Patient has a slapped-cheek rash.'))
        self.assertNotIn('supported',verdicts(c,ledger,'Confirmed parvovirus infection.'))
        self.assertEqual(ledger.to_json(),before)
        for wrong in ['I had a mild cold just before it began. A coworker had a slapped-cheek rash.',
                      'I had a mild cold just before it began. A child did not have a slapped-cheek rash.',
                      'My child might have had a slapped-cheek rash. I am not sure.']:
            fake=evidence.Ledger();f=next(f for f in c['facts'] if f['id']=='hpi_setting')
            fake.add(evidence.PATIENT,wrong,meta={'facts_released':[f['id']],'concepts':f['concepts']})
            self.assertNotIn('supported',verdicts(c,fake,text))
            self.assertNotIn('supported',verdicts(c,fake,'Child exposure with slapped-cheek rash.'))


if __name__ == '__main__':
    unittest.main()
