"""A symptom the patient states in her opening line counts as evidence.

Owner decision, 2026-09-11. Before it, the opening released one coarse concept,
so a student who wrote down -- in their own words -- something she had just
volunteered was graded UNSUPPORTED: 8 of 41 sentences of real opening content
were supported across the 24-case library, and two halves of one spoken
sentence could be graded differently.

The rule is CONTAINMENT, never inference: every content word of the claim must
have been spoken, and the meaning-bearing markers must match in both
directions. The three tests named `leak_` below each encode a real defect found
while building this -- each one graded a clinically wrong note as supported.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from pcmcse import audit, cases, config, db, engine, evidence, note, opening_evidence


class SaysRule(unittest.TestCase):
    """The matcher itself, on the wording that matters."""

    def says(self, claim, opening):
        return opening_evidence.says(claim, opening)[0]

    def test_her_own_words_are_evidence(self):
        opening = ("I've been getting this pressure in my chest when I push myself "
                   "at work. It goes away when I stop.")
        for claim in ["Chest pressure when she pushes herself at work.",
                      "The pressure goes away when she stops."]:
            with self.subTest(claim):
                self.assertTrue(self.says(claim, opening))

    def test_leak_modality_presyncope_is_not_syncope(self):
        # "might faint" must never become "fainted" -- the whole point of the
        # presyncope case. Bag-of-words containment alone graded this supported.
        opening = "I keep feeling like I might faint when I stand up."
        self.assertFalse(self.says("Fainted when standing.", opening))
        self.assertTrue(self.says("She keeps feeling like she might faint when she stands up.", opening))

    def test_leak_negation_scope(self):
        # She said the pain has NOT GONE AWAY. That is not "no pain".
        opening = "The pain under my right ribs has not gone away since dinner."
        self.assertFalse(self.says("No pain under the right ribs since dinner.", opening))

    def test_leak_aspect_a_history_is_not_a_current_state(self):
        # Exertional history is not a resting current state.
        opening = "I've been getting this pressure in my chest when I push myself at work."
        self.assertFalse(self.says("Chest pressure now.", opening))
        self.assertFalse(self.says("Chest pressure currently.", opening))

    def test_a_number_is_always_content(self):
        # Dropping short tokens once let a severity rating through an opening
        # that never gave one.
        opening = "My toes feel numb and burn at night."
        self.assertFalse(self.says("Burning is 5/10 at night.", opening))

    def test_nothing_unspoken_can_be_added(self):
        opening = "I've been getting this pressure in my chest when I push myself at work."
        for claim in ["Chest pressure radiating to the left arm.",
                      "Chest pressure with nausea and sweating.",
                      "Crushing substernal chest pain for three weeks.",
                      "Chest pressure relieved by nitroglycerin."]:
            with self.subTest(claim):
                self.assertFalse(self.says(claim, opening))

    def test_a_denial_cannot_become_a_finding(self):
        opening = "I have no chest pain at all, but my ankles are swollen and I cannot sleep flat."
        self.assertFalse(self.says("She has chest pain.", opening))
        self.assertTrue(self.says("She has no chest pain.", opening))
        self.assertTrue(self.says("Her ankles are swollen.", opening))

    def test_leak_a_negation_vocabulary_hole_inverted_the_complaint(self):
        """Found by an adversarial reviewer, reproduced end to end.

        "nothing" was missing from the negation vocabulary, so the retention
        case's opening -- "I desperately need to pee, but nothing will come
        out." -- graded "Pee will come out." as SUPPORTED. The exact opposite
        of what she said, in the case built around that symptom.
        """
        opening = "I desperately need to pee, but nothing will come out."
        self.assertFalse(self.says("Pee will come out.", opening))
        self.assertTrue(self.says("Nothing will come out.", opening))
        self.assertTrue(self.says("She desperately needs to pee.", opening))

    def test_every_negator_is_known(self):
        for word in ["nothing", "nobody", "neither", "unable", "hardly",
                     "cannot", "never", "none", "without"]:
            with self.subTest(word):
                opening = "I have %s pain in my chest." % word
                self.assertFalse(self.says("She has pain in her chest.", opening), word)

    def test_clauses_cannot_exchange_a_symptom_owner_or_timeline(self):
        self.assertFalse(self.says(
            "My husband has chest pressure when I push myself at work.",
            "I've been getting this pressure in my chest when I push myself at work. "
            "It goes away when I stop. My husband made me come in."))
        opening = "My stomach started hurting around the middle, but now the pain is low on the right."
        self.assertFalse(self.says("Pain started low on the right and is now around the middle.", opening))
        self.assertTrue(self.says("My stomach started hurting around the middle and is now low on the right.", opening))

    def test_a_fragment_is_not_a_match(self):
        self.assertFalse(self.says("Pain.", "My stomach is hurting badly today."))


class ThroughTheGrader(unittest.TestCase):
    """End to end: the verdict a student would actually receive."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pcm-opening-')
        self.old = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name, 'a.sqlite')
        db.init()
        self.clock = patch('pcmcse.db.now_ms', side_effect=lambda: 1789000000000)
        self.clock.start()

    def tearDown(self):
        self.clock.stop(); db.DB_PATH = self.old; self.temp.cleanup()

    def opened(self, cid):
        case = cases.resolve(cid, 'base')
        settings = config.load_settings()
        settings.update(learning_mode='independent', simulation_runtime='interactive',
                        preset=config.preset_for_learning_mode('independent'))
        sid = db.create_session(cid, settings['preset'], 'type', False, settings, case=case)
        s = engine.load(sid); s.start_encounter()
        s.student_turn("Hello, I'm a student doctor. What brings you in today?")
        return s, case

    def verdicts(self, cid, subjective):
        s, case = self.opened(cid)
        parsed = note.parse({'S': subjective, 'O': '', 'A': ['', '', ''], 'P': ['', '', '']})
        return [c['verdict'] for c in audit.audit_note(parsed, s.ledger, case)['claims']]

    def test_documenting_the_opening_is_supported(self):
        self.assertEqual(
            self.verdicts('gi-right-lower-pain',
                          'HPI: Her stomach started hurting around the middle and is now low on the right.'),
            ['supported'])

    def test_known_limit_a_clinical_synonym_is_not_credited_by_this_route(self):
        """The patient said "stomach"; the student wrote "abdominal".

        That is the correct way to document it, and this rule still refuses it,
        because crediting it means trusting a lay-to-clinical synonym map.
        The one the app has (grader._COMPLAINT_SIGNALS) treats "migraine" as
        "headache" -- which would let "I get migraines, but this is not my
        migraine" support a headache claim in the thunderclap case, destroying
        the distinction that case exists to teach. Whole-complaint translations
        stay with the clinician-authored opening_evidence.PARAPHRASES route.

        This test exists to state the limit, not to approve of it. If a vetted
        symptom-level synonym map is ever authored, delete it and widen the rule.
        """
        self.assertEqual(
            self.verdicts('gi-right-lower-pain',
                          'HPI: Abdominal pain that started around the middle.'),
            ['unsupported'])

    def test_reversed_migration_and_wrong_person_are_never_supported(self):
        for cid, statement in [
                ('gi-right-lower-pain', 'Pain started low on the right and is now around the middle.'),
                ('cardio-chest-pressure', 'My husband has chest pressure when I push myself at work.')]:
            with self.subTest(statement):
                self.assertTrue(all(v not in ('supported', 'supported_supplied')
                                    for v in self.verdicts(cid, 'HPI: ' + statement)))

    def test_both_halves_of_one_spoken_sentence_agree(self):
        # The defect that started this: "but now the pain is low on the right"
        # was supported while "her stomach started hurting around the middle"
        # -- the first half of the same sentence -- was not.
        got = self.verdicts('gi-right-lower-pain',
                            'HPI: Her stomach started hurting around the middle.\n'
                            'HPI: Now the pain is low on the right.')
        self.assertEqual(got, ['supported', 'supported'], got)

    def test_the_opening_still_cannot_support_an_examination_finding(self):
        # An opening is history. It is never an Objective finding.
        s, case = self.opened('cardio-chest-pressure')
        parsed = note.parse({'S': '', 'O': 'Chest pressure when she pushes herself at work.',
                             'A': ['', '', ''], 'P': ['', '', '']})
        for claim in audit.audit_note(parsed, s.ledger, case)['claims']:
            self.assertNotEqual(claim['verdict'], 'supported', claim)

    def test_verbatim_opening_also_respects_the_history_header(self):
        for header in ['FH', 'PMH', 'Meds', 'Allergies', 'ROS']:
            with self.subTest(header):
                self.assertTrue(all(v not in ('supported', 'supported_supplied') for v in
                    self.verdicts('gi-right-lower-pain', header + ': My stomach started hurting around the middle.')))

    def test_the_opening_cannot_be_laundered_into_another_header(self):
        """Pre-existing, and worth far more once the opening carries credit.

        "FHx: Chest pressure." graded SUPPORTED off the opening -- so did PMH,
        ROS, Meds and Social -- because _opening_paraphrase's alias branch had
        no header guard while its PARAPHRASES branch did.
        """
        said = 'Chest pressure when she pushes herself at work.'
        for header in ['FHx', 'PMH', 'ROS', 'Meds', 'Social', 'PSH']:
            with self.subTest(header):
                self.assertEqual(
                    self.verdicts('cardio-chest-pressure', '%s: %s' % (header, said)),
                    ['unsupported'])
        for header in ['CC', 'HPI']:
            with self.subTest(header):
                self.assertEqual(
                    self.verdicts('cardio-chest-pressure', '%s: %s' % (header, said)),
                    ['supported'])

    def test_an_unasked_attribute_is_still_unsupported(self):
        got = self.verdicts('cardio-chest-pressure',
                            'HPI: Chest pressure radiating to the left arm, 8/10.')
        self.assertNotIn('supported', got, got)


if __name__ == '__main__':
    unittest.main()
