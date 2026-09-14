"""Children and reproductive history stay separate from current pregnancy status."""
import copy
import unittest

from pcmcse import audit, cases, evidence, note, patient, record


class ReproductiveHistoryScopeTests(unittest.TestCase):
    def ready(self, case_id='cardio-palpitations', variant='base'):
        case = cases.resolve(case_id, variant)
        return case, patient.PatientEngine(case), {}

    def mara_variants(self):
        return ['base'] + [v['id'] for v in cases.get('cardio-palpitations')['variants']]

    def assert_scope(self, case, reply, meta, allowed, required=()):
        released = set(meta.get('facts_released', []))
        self.assertLessEqual(released, set(allowed), (reply, meta))
        self.assertGreaterEqual(released, set(required), (reply, meta))
        self.assertFalse(meta.get('volunteered'), (reply, meta))
        definitions = {f['id']: f for f in case['facts']}
        allowed_concepts = {key for fid in allowed for key in definitions[fid].get('concepts', {})}
        self.assertLessEqual(set(meta.get('concepts', {})), allowed_concepts, (reply, meta))
        for fid in released:
            delivered = patient.delivered_fact_metadata(definitions[fid], reply) or {}
            self.assertIn(fid, delivered.get('facts_released', []), (reply, meta))

    def assert_unavailable(self, case, reply, meta, topic):
        self.assert_scope(case, reply, meta, set())
        self.assertTrue(meta.get('no_information'), (reply, meta))
        self.assertRegex(reply.lower(), topic)
        self.assertRegex(reply.lower(), r'unavailable|unspecified|not (?:specif|provid|know)|no (?:information|details)|don.t know|cannot|can.t|not sure')
        self.assertFalse(meta.get('checklist_hits'), (reply, meta))
        self.assertNotRegex(reply.lower(), r'(?:i (?:have|have had) (?:no|zero)|i.ve never|i have never|never been pregnant|no prior pregnancies|no miscarriages|g0p0|g2p2)')

    def assert_no_current_pregnancy_leak(self, reply):
        self.assertNotRegex(reply.lower(), r'(?:do not|don.t) think i am pregnant|have not taken a pregnancy test|this episode is continuous|last period was')

    def add_reply(self, engine, state, ledger, question):
        reply, meta = engine.respond(question, state)
        ledger.add(evidence.STUDENT, question)
        ledger.add(evidence.PATIENT, reply, meta=meta)
        return reply, meta

    def summary_ids(self, case, ledger):
        summary = record.summarize(case, ledger.events)
        return {row['fact_id'] for group in summary['groups']
                for section in group['sections'] for row in section['items'] if row.get('fact_id')}

    def test_mara_children_questions_are_explicitly_unavailable_in_all_variants(self):
        questions = ['Do you have kids?', 'Do you have any children?', 'Any kids?', 'Have you ever had children?',
                     'Are you a parent?', 'How many children do you have?']
        for variant in self.mara_variants():
            for question in questions:
                with self.subTest(variant=variant, question=question):
                    case, engine, state = self.ready(variant=variant)
                    reply, meta = engine.respond(question, state)
                    self.assert_unavailable(case, reply, meta, r'child|kid|parent')
                    self.assert_no_current_pregnancy_leak(reply)

    def test_mara_prior_pregnancy_questions_do_not_answer_current_pregnancy(self):
        questions = ['Have you ever been pregnant?', 'Have you been pregnant before?',
                     'Have you ever been pregnant before?', 'Any previous pregnancies?',
                     'What is your pregnancy history?', 'How many times have you been pregnant?']
        for variant in self.mara_variants():
            for question in questions:
                with self.subTest(variant=variant, question=question):
                    case, engine, state = self.ready(variant=variant)
                    reply, meta = engine.respond(question, state)
                    self.assert_unavailable(case, reply, meta, r'pregnan|obstetric|gravidity')
                    self.assert_no_current_pregnancy_leak(reply)

    def test_mara_delivery_loss_and_gravidity_parity_are_not_invented(self):
        questions = [('Have you given birth before?', r'birth|deliver|parity'),
                     ('How many deliveries have you had?', r'birth|deliver|parity'),
                     ('Have you had any miscarriages?', r'miscarriage|loss'),
                     ('Have you ever had an abortion?', r'abortion|termination|loss'),
                     ('What is your gravidity and parity?', r'gravidity|parity|pregnan|deliver'),
                     ('How many pregnancies and live births have you had?', r'pregnan|birth|deliver')]
        for question, topic in questions:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                reply, meta = engine.respond(question, state)
                self.assert_unavailable(case, reply, meta, topic)
                self.assert_no_current_pregnancy_leak(reply)

    def test_no_authored_female_case_path_is_assumed_to_have_zero_pregnancy_losses(self):
        paths = 0
        for cid, base in cases.all_cases().items():
            for variant in ['base'] + [v['id'] for v in base.get('variants', [])]:
                case = cases.resolve(cid, variant)
                if case['patient']['sex'] != 'female':
                    continue
                with self.subTest(case=cid, variant=variant):
                    reply, meta = patient.PatientEngine(case).respond('Have you had any miscarriages?', {})
                    self.assert_unavailable(case, reply, meta, r'miscarriage|loss')
                paths += 1
        self.assertEqual(paths, 59)

    def test_current_pregnancy_possibility_remains_answerable_in_all_mara_variants(self):
        for variant in self.mara_variants():
            for question in ['Is there any chance you could be pregnant?', 'Could you be pregnant now?',
                             'Do you think you are currently pregnant?']:
                with self.subTest(variant=variant, question=question):
                    case, engine, state = self.ready(variant=variant)
                    reply, meta = engine.respond(question, state)
                    self.assert_scope(case, reply, meta, {'history_pregnancy'}, {'history_pregnancy'})
                    self.assertRegex(reply.lower(), r'not think i am pregnant')
                    self.assertRegex(reply.lower(), r'not taken a pregnancy test')
                    self.assertNotRegex(reply.lower(), r'continuous|last period|children|deliveries')

    def test_last_menstrual_period_remains_a_separate_authored_answer(self):
        for variant in self.mara_variants():
            for question in ['When was your last period?', 'When was your last menstrual period?']:
                with self.subTest(variant=variant, question=question):
                    case, engine, state = self.ready(variant=variant)
                    reply, meta = engine.respond(question, state)
                    self.assert_scope(case, reply, meta, {'history_menstrual'}, {'history_menstrual'})
                    self.assertRegex(reply.lower(), r'2 weeks|two weeks')
                    self.assertNotRegex(reply.lower(), r'pregnancy test|children|deliveries')

    def test_compound_prior_and_current_pregnancy_questions_address_both_scopes(self):
        questions = ['Have you been pregnant before, and could you be pregnant now?',
                     'Could you be pregnant now? Have you ever been pregnant before?']
        for question in questions:
            with self.subTest(question=question):
                case, engine, state = self.ready()
                reply, meta = engine.respond(question, state)
                self.assert_scope(case, reply, meta, {'history_pregnancy'}, {'history_pregnancy'})
                self.assertRegex(reply.lower(), r'not think i am pregnant')
                self.assertRegex(reply.lower(), r'prior|previous|past|pregnancy history')
                self.assertRegex(reply.lower(), r'unavailable|not specif|not provid|no information')
                self.assertNotRegex(reply.lower(), r'never been pregnant|no prior pregnancies')

    def test_current_to_prior_to_how_many_retains_the_prior_pregnancy_scope(self):
        case, engine, state = self.ready()
        engine.respond('Is there any chance you could be pregnant?', state)
        for question in ['Have you been pregnant before?', 'How many?']:
            reply, meta = engine.respond(question, state)
            self.assert_unavailable(case, reply, meta, r'pregnan|gravidity')
            self.assert_no_current_pregnancy_leak(reply)

    def test_children_followup_count_does_not_become_pregnancy_count(self):
        case, engine, state = self.ready()
        engine.respond('Do you have any children?', state)
        reply, meta = engine.respond('How many?', state)
        self.assert_unavailable(case, reply, meta, r'child|kid')
        self.assert_no_current_pregnancy_leak(reply)

    def test_authored_children_can_be_answered_without_work_or_surgery_disclosure(self):
        fixtures = [('gi-epigastric-melena', 'history_household', r'two children'),
                    ('heent-sore-throat', 'history_home', r'daughter'),
                    ('msk-shoulder-overuse', 'history_home', r'son'),
                    ('msk-hand-stiffness', 'history_support', r'toddler'),
                    ('pulm-chronic-productive-cough', 'history_home_and_access', r'daughter'),
                    ('gi-diarrhea-dehydration', 'history_household', r'child')]
        for cid, fid, topic in fixtures:
            with self.subTest(case=cid):
                case, engine, state = self.ready(cid)
                reply, meta = engine.respond('Do you have any children?', state)
                if cid in {'msk-hand-stiffness', 'pulm-chronic-productive-cough'}:
                    self.assertEqual(meta.get('facts_released', []), [])
                    self.assertFalse(meta.get('checklist_hits'), (reply, meta))
                    self.assertEqual(set(meta.get('concepts', {})), {'delivered_text_' + fid})
                    self.assertNotRegex(reply.lower(), r'work|appointment|pay|drive|live alone')
                else:
                    self.assert_scope(case, reply, meta, {fid}, {fid})
                self.assertRegex(reply.lower(), topic)
                self.assertNotRegex(reply.lower(), r'gallbladder|cesarean|daycare|food containers|g[0-9]+p[0-9]+')

    def test_household_daughter_does_not_establish_a_prior_pregnancy_or_total_parity(self):
        case, engine, state = self.ready('heent-sore-throat')
        engine.respond('Do you have children?', state)
        for question in ['Have you been pregnant before?', 'How many deliveries have you had?']:
            reply, meta = engine.respond(question, state)
            self.assert_unavailable(case, reply, meta, r'pregnan|deliver|parity|birth')
            self.assertNotRegex(reply.lower(), r'(?:one|1) (?:pregnancy|delivery|birth)|g1p1')

    def test_authored_cesarean_delivery_is_available_without_inventing_total_counts(self):
        for cid, fid in [('gi-right-upper-pain', 'history_psh_1'),
                         ('msk-shoulder-overuse', 'history_surgery')]:
            with self.subTest(case=cid):
                case, engine, state = self.ready(cid)
                reply, meta = engine.respond('Have you had any deliveries?', state)
                self.assert_scope(case, reply, meta, {fid}, {fid})
                self.assertRegex(reply.lower(), r'cesarean')
                self.assertNotRegex(reply.lower(), r'only (?:one|1)|g1p1|no miscarriages|no other pregnancies')

    def test_bundled_prior_delivery_answer_does_not_release_gallbladder_history(self):
        case, engine, state = self.ready('gi-epigastric-melena')
        reply, meta = engine.respond('Have you had any deliveries?', state)
        self.assertRegex(reply.lower(), r'two children|two.*deliver|2.*deliver')
        self.assertRegex(reply.lower(), r'normal deliveries')
        self.assertNotRegex(reply.lower(), r'gallbladder|cholecystectomy|twenty.five')
        self.assertNotIn('psh_cholecystectomy', meta.get('concepts', {}))
        self.assertNotIn('psh', meta.get('facts_released', []))
        self.assertFalse(meta.get('checklist_hits'), (reply, meta))
        self.assertEqual(set(meta.get('concepts', {})), {'obstetric_history'})
        for concept in meta['concepts'].values():
            self.assertNotRegex(concept['value'].lower(), r'gallbladder|cholecystectomy|twenty.five')
        reply, meta = engine.respond('Have you had any surgeries?', state)
        self.assert_scope(case, reply, meta, {'psh'}, {'psh'})
        self.assertRegex(reply.lower(), r'gallbladder.*twenty.five')
        self.assertIn('psh_cholecystectomy', meta['concepts'])
        self.assertTrue(meta.get('checklist_hits'), (reply, meta))

    def test_short_shared_list_addresses_both_missing_history_topics(self):
        case, engine, state = self.ready()
        reply, meta = engine.respond('Any pregnancies or children?', state)
        self.assert_unavailable(case, reply, meta, r'children')
        self.assertRegex(reply.lower(), r'previous pregnancies|prior pregnancies|pregnancy history')
        self.assert_no_current_pregnancy_leak(reply)

    def test_pregnancy_test_clause_does_not_disclose_unasked_menstrual_or_contraception_details(self):
        case, engine, state = self.ready('msk-hand-stiffness')
        reply, meta = engine.respond('Have you taken a pregnancy test?', state)
        self.assertRegex(reply.lower(), r'not done a pregnancy test')
        self.assertNotRegex(reply.lower(), r'period|week|condom')
        self.assertEqual(meta.get('facts_released', []), [])
        self.assertFalse(meta.get('checklist_hits'), (reply, meta))
        self.assertFalse(meta.get('delivery_limits'), (reply, meta))
        self.assertEqual(set(meta.get('concepts', {})), {'delivered_text_history_pregnancy'})
        for concept in meta['concepts'].values():
            self.assertRegex(concept['value'].lower(), r'not done a pregnancy test')
            self.assertNotRegex(concept['value'].lower(), r'period|week|condom')

    def test_current_pregnancy_clause_does_not_disclose_unasked_lmp_or_iud(self):
        case, engine, state = self.ready('pulm-episodic-wheeze')
        reply, meta = engine.respond('Could you be pregnant now?', state)
        self.assertRegex(reply.lower(), r'not think i am pregnant')
        self.assertNotRegex(reply.lower(), r'period|week|iud|test')
        self.assertEqual(meta.get('facts_released', []), [])
        self.assertFalse(meta.get('checklist_hits'), (reply, meta))
        self.assertFalse(meta.get('delivery_limits'), (reply, meta))
        self.assertEqual(set(meta.get('concepts', {})), {'delivered_text_history_pregnancy_possibility'})
        for concept in meta['concepts'].values():
            self.assertRegex(concept['value'].lower(), r'not think i am pregnant')
            self.assertNotRegex(concept['value'].lower(), r'period|week|iud|test')

    def test_prior_deliveries_do_not_establish_total_gravidity_or_absence_of_losses(self):
        case, engine, state = self.ready('gi-epigastric-melena')
        engine.respond('Have you had any deliveries?', state)
        for question in ['How many total pregnancies have you had?', 'Have you had any miscarriages?']:
            reply, meta = engine.respond(question, state)
            self.assert_unavailable(case, reply, meta, r'pregnan|gravidity|miscarriage|loss')
            self.assertNotRegex(reply.lower(), r'exactly two|only two|g2p2|no miscarriages')

    def test_current_pregnancy_belief_does_not_imply_an_unprovided_test_history(self):
        case, engine, state = self.ready('gi-right-upper-pain')
        reply, meta = engine.respond('Have you taken a pregnancy test?', state)
        self.assert_unavailable(case, reply, meta, r'pregnancy test|testing')
        self.assertNotRegex(reply.lower(), r'i have not taken|i took|i haven.t taken|(?:positive|negative) test')

    def test_authored_unperformed_pregnancy_test_can_be_reported(self):
        case, engine, state = self.ready()
        reply, meta = engine.respond('Have you taken a pregnancy test?', state)
        self.assert_scope(case, reply, meta, {'history_pregnancy'}, {'history_pregnancy'})
        self.assertRegex(reply.lower(), r'not taken a pregnancy test')
        self.assertNotRegex(reply.lower(), r'negative test|test was negative|test was positive')

    def test_children_and_prior_pregnancy_questions_do_not_create_current_pregnancy_evidence(self):
        case, engine, state = self.ready()
        ledger = evidence.Ledger()
        for question in ['Do you have kids?', 'Have you been pregnant before?', 'How many?',
                         'Have you had any miscarriages?']:
            self.add_reply(engine, state, ledger, question)
        self.assertEqual(ledger.released_facts(), {})
        self.assertEqual(ledger.released_concepts(), {})
        self.assertEqual(self.summary_ids(case, ledger), set())
        parsed = note.ParsedNote('PMH: Does not think she is pregnant and has not taken a pregnancy test.', '', [], [])
        checked = audit.audit_note(parsed, ledger, case)
        self.assertTrue(checked['claims'])
        self.assertFalse(any(c['verdict'] in {'supported', 'supported_supplied'} for c in checked['claims']))

    def test_current_question_adds_only_its_own_evidence_and_later_unknown_history_preserves_it(self):
        case, engine, state = self.ready()
        ledger = evidence.Ledger()
        self.add_reply(engine, state, ledger, 'Do you have children?')
        self.add_reply(engine, state, ledger, 'Is there any chance you could be pregnant?')
        self.add_reply(engine, state, ledger, 'Have you been pregnant before?')
        self.add_reply(engine, state, ledger, 'How many?')
        self.assertEqual(self.summary_ids(case, ledger), {'history_pregnancy'})
        self.assertEqual(set(ledger.released_facts()), {'history_pregnancy'})
        self.assertEqual(set(ledger.released_concepts()), {'history_pregnancy'})

    def test_authored_child_count_and_age_remain_available_without_inferred_mara_values(self):
        for cid, question, fid, wording in [
                ('gi-epigastric-melena', 'How many children do you have?', 'history_household', r'two children'),
                ('heent-sore-throat', 'How old is your daughter?', 'history_home', r'six.year.old')]:
            with self.subTest(case=cid, question=question):
                case, engine, state = self.ready(cid)
                reply, meta = engine.respond(question, state)
                self.assert_scope(case, reply, meta, {fid}, {fid})
                self.assertRegex(reply.lower(), wording)
        for question in ['How many children do you have?', 'How old are your children?']:
            with self.subTest(case='cardio-palpitations', question=question):
                case, engine, state = self.ready()
                reply, meta = engine.respond(question, state)
                self.assert_unavailable(case, reply, meta, r'child')

    def test_questions_about_childrens_illness_do_not_return_the_patients_own_history(self):
        for cid in ['cardio-palpitations', 'heent-sore-throat']:
            for question in ['Do your children have food allergies?', 'What is your daughter allergic to?',
                             'Do you have children with asthma?']:
                with self.subTest(case=cid, question=question):
                    case, engine, state = self.ready(cid)
                    reply, meta = engine.respond(question, state)
                    self.assert_scope(case, reply, meta, set())
                    self.assertFalse(meta.get('checklist_hits'), (reply, meta))
                    self.assertNotRegex(reply.lower(), r'penicillin|no known|pollen|six.year.old|cesarean')

    def test_notes_show_only_approved_scoped_partial_answers(self):
        examples = [('gi-epigastric-melena', 'Have you had any deliveries?', 'psh', r'normal deliveries', r'gallbladder|cholecystectomy|twenty.five'),
                    ('msk-hand-stiffness', 'Have you taken a pregnancy test?', 'history_pregnancy', r'not done a pregnancy test', r'period|week|condom'),
                    ('pulm-episodic-wheeze', 'Could you be pregnant now?', 'history_pregnancy_possibility', r'not think i am pregnant', r'period|week|iud|test'),
                    ('msk-hand-stiffness', 'Do you have any children?', 'history_support', r'toddler', r'work|appointment'),
                    ('pulm-chronic-productive-cough', 'Do you have any children?', 'history_home_and_access', r'daughter', r'pay|drive|live alone')]
        for cid, question, source_id, expected, forbidden in examples:
            with self.subTest(case=cid):
                case, engine, state = self.ready(cid)
                ledger = evidence.Ledger()
                self.add_reply(engine, state, ledger, question)
                before_case, before_ledger = copy.deepcopy(case), ledger.to_json()
                summary = record.summarize(case, ledger.events)
                rows = [row for group in summary['groups'] for section in group['sections'] for row in section['items']]
                self.assertEqual(len(rows), 1, summary)
                row = rows[0]
                self.assertTrue(row.get('partial'), row)
                self.assertTrue(row['fact_id'].startswith('partial:'))
                self.assertEqual(row['source_fact_id'], source_id)
                self.assertEqual(row['section'], 'social' if source_id in {'history_support', 'history_home_and_access'} else 'obgyn')
                self.assertEqual(row['seqs'], [2])
                self.assertRegex(row['text'].lower(), expected)
                self.assertNotRegex((row['text'] + ' ' + row['text_full']).lower(), forbidden)
                self.assertEqual(ledger.released_facts(), {})
                self.assertEqual(case, before_case)
                self.assertEqual(ledger.to_json(), before_ledger)

    def test_notes_partial_projection_rejects_unspoken_forged_or_unapproved_details(self):
        case, engine, state = self.ready('msk-hand-stiffness')
        reply, meta = engine.respond('Have you taken a pregnancy test?', state)
        valid = {'seq': 2, 'kind': evidence.PATIENT, 'text': reply, 'meta': meta}
        wrong_value = copy.deepcopy(valid)
        wrong_value['meta']['concepts']['delivered_text_history_pregnancy']['value'] += ' My period was one week ago.'
        wrong_polarity = copy.deepcopy(valid)
        wrong_polarity['meta']['concepts']['delivered_text_history_pregnancy']['polarity'] = 'negative'
        examples = [dict(valid, text='We discussed something else.'), dict(valid, meta={}),
                    dict(valid, kind=evidence.STUDENT), wrong_value, wrong_polarity,
                    dict(valid, meta=dict(meta, no_information=True)),
                    dict(valid, meta=dict(meta, interrupted=True))]
        for event in examples:
            with self.subTest(event=event):
                self.assertEqual(record.summarize(case, [event])['groups'], [])
        unapproved = copy.deepcopy(case)
        fact = next(f for f in unapproved['facts'] if f['id'] == 'history_pregnancy')
        fact['delivery_contract']['versions'] = []
        self.assertEqual(record.summarize(unapproved, [valid])['groups'], [])

    def test_legacy_snapshots_obtain_scoped_statements_without_mutating_their_facts(self):
        examples = [('gi-epigastric-melena', 'Have you had any deliveries?', r'normal deliveries', r'gallbladder|twenty.five'),
                    ('msk-hand-stiffness', 'Have you taken a pregnancy test?', r'not done a pregnancy test', r'period|week|condom'),
                    ('pulm-episodic-wheeze', 'Could you be pregnant now?', r'not think i am pregnant', r'period|week|iud|test'),
                    ('msk-hand-stiffness', 'Do you have any children?', r'toddler', r'work|appointment'),
                    ('pulm-chronic-productive-cough', 'Do you have any children?', r'daughter', r'pay|drive|live alone')]
        for cid, question, expected, forbidden in examples:
            with self.subTest(case=cid, question=question):
                case = copy.deepcopy(cases.resolve(cid))
                for fact in case['facts']:
                    contract = fact.get('delivery_contract', {})
                    contract['versions'] = [v for v in contract.get('versions', []) if not v.get('history_dimensions')]
                original = copy.deepcopy(case)
                engine, state, ledger = patient.PatientEngine(case), {}, evidence.Ledger()
                reply, meta = self.add_reply(engine, state, ledger, question)
                self.assertRegex(reply.lower(), expected)
                self.assertNotRegex(reply.lower(), forbidden)
                self.assertEqual(meta.get('facts_released', []), [])
                self.assertFalse(meta.get('checklist_hits'), (reply, meta))
                self.assertNotRegex(str(meta.get('concepts', {})).lower(), forbidden)
                rows = [row for group in record.summarize(case, ledger.events)['groups'] for section in group['sections'] for row in section['items']]
                self.assertEqual(len(rows), 1)
                self.assertTrue(rows[0].get('partial'))
                self.assertRegex(rows[0]['text'].lower(), expected)
                self.assertNotRegex((rows[0]['text'] + rows[0]['text_full']).lower(), forbidden)
                self.assertEqual(case, original)

    def test_partial_notes_deduplicate_then_consolidate_after_full_history_is_obtained(self):
        case, engine, state = self.ready('gi-epigastric-melena')
        ledger = evidence.Ledger()
        self.add_reply(engine, state, ledger, 'Have you had any deliveries?')
        self.add_reply(engine, state, ledger, 'Have you had any deliveries?')
        rows = [row for group in record.summarize(case, ledger.events)['groups'] for section in group['sections'] for row in section['items']]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['seqs'], [2, 4])
        self.assertNotIn('gallbladder', rows[0]['text'].lower())
        self.add_reply(engine, state, ledger, 'Have you had any surgeries?')
        rows = [row for group in record.summarize(case, ledger.events)['groups'] for section in group['sections'] for row in section['items']]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['fact_id'], 'psh')
        self.assertFalse(rows[0].get('partial'))
        self.assertEqual(rows[0]['seqs'], [6])
        self.assertIn('gallbladder', rows[0]['text'].lower())
        self.add_reply(engine, state, ledger, 'Have you had any deliveries?')
        rows = [row for group in record.summarize(case, ledger.events)['groups'] for section in group['sections'] for row in section['items']]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['fact_id'], 'psh')
        self.assertEqual(rows[0]['seqs'], [6])

    def test_sick_children_question_retains_contact_history_instead_of_parenthood(self):
        case, engine, state = self.ready('gi-diarrhea-dehydration')
        reply, meta = engine.respond('Have any children around you been sick?', state)
        self.assert_scope(case, reply, meta, {'hpi_setting'}, {'hpi_setting'})
        self.assertRegex(reply.lower(), r'child.*similar symptoms')
        self.assertNotIn('history_household', meta.get('facts_released', []))

    def test_relatives_reproductive_history_does_not_release_the_patients_own_history(self):
        for question in ['Have your children had any pregnancies?',
                         'How many children does your sister have?']:
            with self.subTest(question=question):
                case, engine, state = self.ready('gi-epigastric-melena')
                reply, meta = engine.respond(question, state)
                self.assert_scope(case, reply, meta, set())
                self.assertFalse(meta.get('checklist_hits'), (reply, meta))
                self.assertNotRegex(reply.lower(), r'normal deliveries|gallbladder|two children')

    def test_miscarriage_qualified_pregnancy_question_does_not_release_prior_deliveries(self):
        for question in ['Have you ever had a pregnancy that ended in miscarriage?',
                         'Have any of your pregnancies ended in miscarriage?']:
            with self.subTest(question=question):
                case, engine, state = self.ready('gi-epigastric-melena')
                reply, meta = engine.respond(question, state)
                self.assert_unavailable(case, reply, meta, r'miscarriage|loss|termination')
                self.assertNotRegex(reply.lower(), r'normal deliveries|gallbladder|two children')

    def test_scoped_interview_does_not_modify_case_source_facts(self):
        case, engine, state = self.ready()
        original = copy.deepcopy(case)
        for question in ['Do you have kids?', 'Have you ever been pregnant?', 'Could you be pregnant now?',
                         'When was your last period?', 'Have you had miscarriages?']:
            engine.respond(question, state)
        self.assertEqual(case, original)


if __name__ == '__main__':
    unittest.main()
