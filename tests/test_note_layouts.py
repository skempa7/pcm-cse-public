"""Organization variants preserve clinical text, section boundaries and source spans."""
import unittest

from pcmcse import audit, cases, evidence, note


class NoteLayoutTests(unittest.TestCase):
    def parsed(self, subjective="", objective="", assessment=(), plan=()):
        return note.ParsedNote(subjective, objective, assessment, plan)

    def assert_source_spans(self, parsed):
        for claim in parsed.claims():
            if claim["section"] in ("S", "O"):
                source = parsed.s_text if claim["section"] == "S" else parsed.o_text
                self.assertEqual(source[claim["start"]:claim["end"]], claim["text"], claim)

    def test_heading_punctuation_and_typography_do_not_change_the_body(self):
        forms = ("HPI: Three days of pain.", "HPI — Three days of pain.",
                 "HPI – Three days of pain.", "HPI - Three days of pain.",
                 "HPI\nThree days of pain.", "## HPI\nThree days of pain.",
                 "**HPI:** Three days of pain.", "**HPI**: Three days of pain.",
                 "**HPI** Three days of pain.", "__HPI:__ Three days of pain.",
                 "- HPI: Three days of pain.", "• HPI: Three days of pain.",
                 "1. HPI: Three days of pain.")
        for text in forms:
            with self.subTest(text=text):
                parsed = self.parsed(text)
                self.assertEqual(parsed.s_header("hpi")["body"], "Three days of pain.")
                self.assertEqual(parsed.s_headers_present(), {"hpi"})
                self.assert_source_spans(parsed)

    def test_common_history_abbreviations_are_exact_aliases(self):
        parsed = self.parsed("PMHx: Asthma.\nPSHx: Appendectomy.\nFHx: Mother healthy.\nSHx: No tobacco.")
        self.assertEqual(parsed.s_headers_present(), {"pmh", "psh", "fh", "sh"})
        self.assertEqual(parsed.s_header("psh")["body"], "Appendectomy.")
        self.assert_source_spans(parsed)
        self.assertIsNone(self.parsed("SHout: No tobacco.").s_header("sh"))
        self.assertIsNone(self.parsed(objective="VitalsXYZ: BP 120/80.").o_header("vitals"))

    def test_unheaded_prose_stays_unheaded(self):
        text = "The patient has pain and no fever. She reports no tobacco use."
        parsed = self.parsed(text)
        self.assertEqual(parsed.s_headers_present(), set())
        self.assertEqual(parsed.s_preamble, text)
        self.assertTrue(all(c["header"] is None for c in parsed.claims()))
        self.assert_source_spans(parsed)

    def test_repeated_history_is_aggregated_without_moving_claims(self):
        source = "  A brief introduction.\n\nFHx:\n  Mother has hypertension.\nHPI — Pain for three days.\nFHx\n Father is healthy.\n**Family history:** Sister is healthy."
        parsed = self.parsed(source)
        family = parsed.s_header("fh")
        self.assertEqual(family["body"], "Mother has hypertension.\nFather is healthy.\nSister is healthy.")
        self.assertEqual(len(family["source_spans"]), 3)
        self.assertEqual(len([b for b in parsed.s_blocks if b["canonical"] == "fh"]), 3)
        self.assertEqual(len([c for c in parsed.claims() if c["header"] == "fh"]), 3)
        self.assert_source_spans(parsed)

    def test_nested_ros_system_labels_retain_subjective_scope(self):
        source = "ROS\nGeneral: No fever.\n- Respiratory: No cough.\n**Skin:** No rash.\nNeurologic\nNo dizziness.\nPMHx: Asthma."
        parsed = self.parsed(source)
        self.assertEqual(parsed.s_headers_present(), {"ros", "pmh"})
        ros = parsed.s_header("ros")["body"]
        for phrase in ("No fever", "No cough", "No rash", "No dizziness"):
            self.assertIn(phrase, ros)
            self.assertEqual(next(c["header"] for c in parsed.claims() if phrase in c["text"]), "ros")
        self.assertNotIn("Asthma", ros)
        self.assert_source_spans(parsed)

    def test_oldcarts_labels_stay_in_hpi(self):
        parsed = self.parsed("HPI\nOnset: Yesterday.\nLocation: Left shoulder.\nDuration: Intermittent.\nSeverity: Six out of ten.\nROS: No cough.")
        self.assertEqual(parsed.s_headers_present(), {"hpi", "ros"})
        self.assertIn("Left shoulder", parsed.s_header("hpi")["body"])
        self.assertTrue(all(c["header"] == "hpi" for c in parsed.claims() if "No cough" not in c["text"]))
        self.assert_source_spans(parsed)

    def test_family_and_medication_labels_remain_under_their_history(self):
        source = ("FHx\nFather: Hearing loss.\nYounger sister: Hypertension.\n"
                  "Allergies\nNeomycin: Pruritic rash.\nAmoxicillin: Hives.\n"
                  "Trimethoprim-sulfamethoxazole: Hives.\n"
                  "Meds\nAmlodipine: 5 mg daily.\nSHx: No tobacco.")
        parsed = self.parsed(source)
        self.assertEqual(parsed.s_headers_present(), {"fh", "allergies", "meds", "sh"})
        self.assertIn("Younger sister: Hypertension", parsed.s_header("fh")["body"])
        self.assertIn("Amoxicillin: Hives", parsed.s_header("allergies")["body"])
        self.assertIn("Trimethoprim-sulfamethoxazole: Hives", parsed.s_header("allergies")["body"])
        self.assertEqual(parsed.s_header("meds")["body"], "Amlodipine: 5 mg daily.")
        self.assert_source_spans(parsed)

    def test_standalone_nkda_remains_an_allergy_statement(self):
        parsed = self.parsed("Allergies\nNKDA\nPMHx\nAsthma.")
        self.assertEqual(parsed.s_header("allergies")["body"], "NKDA")
        self.assertEqual(parsed.claims()[0]["header"], "allergies")
        self.assertEqual(parsed.claims()[0]["text"], "NKDA")
        self.assert_source_spans(parsed)
        self.assertEqual(self.parsed("NKDA: No known drug allergies.").s_header("allergies")["body"],
                         "No known drug allergies.")

    def test_anatomical_location_labels_preserve_the_exam_section(self):
        parsed = self.parsed(objective=("Skin\nVolar left wrist: Erythematous scaly plaque.\n"
                                      "Right hand: No rash.\nMSK\nLeft knee: Tender.\n"
                                      "Heart: Regular rhythm."))
        self.assertEqual(parsed.o_headers_present(), {"skin", "msk", "heart"})
        self.assertIn("Volar left wrist", parsed.o_header("skin")["body"])
        self.assertIn("Right hand: No rash", parsed.o_header("skin")["body"])
        self.assertEqual(parsed.o_header("msk")["body"], "Left knee: Tender.")
        self.assertEqual(parsed.o_header("heart")["body"], "Regular rhythm.")
        self.assert_source_spans(parsed)

    def test_subordinate_labels_do_not_make_arbitrary_headings_authoritative(self):
        for header, body in (("FH", "Father: Hearing loss."),
                             ("Allergies", "Penicillin: Hives."),
                             ("Meds", "Lisinopril: 20 mg daily.")):
            with self.subTest(header=header):
                parsed = self.parsed(header + "\n" + body + "\nOther details: Unsupported assertion.")
                self.assertIsNone(parsed.claims()[-1]["header"])
                self.assert_source_spans(parsed)
        parsed = self.parsed(objective="Skin\nVolar left wrist: Rash.\nOther findings: Clear lungs.")
        self.assertIsNone(parsed.claims()[-1]["header"])
        self.assert_source_spans(parsed)
        for section in ("Vitals", "Heart"):
            parsed = self.parsed(objective=section + "\nVolar left wrist: Rash.")
            self.assertIsNone(parsed.claims()[-1]["header"])

    def test_unknown_headers_end_the_preceding_authority(self):
        for unknown in ("Other findings:", "Other findings —", "**Other findings**", "## Other findings"):
            with self.subTest(unknown=unknown):
                parsed = self.parsed(objective="Vitals: BP 120/80.\n" + unknown + "\nLungs are clear.\nHeart: Regular rhythm.")
                self.assertEqual(parsed.o_header("vitals")["body"], "BP 120/80.")
                lungs = next(c for c in parsed.claims() if "Lungs are clear" in c["text"])
                self.assertIsNone(lungs["header"])
                self.assertEqual(parsed.o_header("heart")["body"], "Regular rhythm.")
                self.assert_source_spans(parsed)

    def test_inline_and_repeated_objective_headers_keep_their_own_findings(self):
        source = "Vitals: BP 120/80. **Heart:** Regular rhythm. Lungs — Clear bilaterally.\nHeart\nNo murmurs."
        parsed = self.parsed(objective=source)
        self.assertEqual(parsed.o_header("vitals")["body"], "BP 120/80.")
        self.assertEqual(parsed.o_header("heart")["body"], "Regular rhythm.\nNo murmurs.")
        self.assertEqual(parsed.o_header("lungs")["body"], "Clear bilaterally.")
        self.assert_source_spans(parsed)

    def test_serial_measurements_stay_together_and_end_at_the_next_exam_header(self):
        source = "Vitals\nBP: 120/80.\nPulse: 72 bpm.\nOrthostatic vitals\nSupine: BP 120/80, pulse 72; standing at 1 minute BP 100/70, pulse 90; at 3 minutes BP 98/68, pulse 92.\nHeart: Regular rhythm."
        parsed = self.parsed(objective=source)
        series = [c for c in parsed.claims() if c["header"] == "orthostatic"]
        self.assertEqual(len(series), 1)
        self.assertIn("standing at 1 minute", series[0]["text"])
        self.assertIn("at 3 minutes", series[0]["text"])
        self.assertNotIn("Regular rhythm", series[0]["text"])
        self.assertIn("Pulse: 72", parsed.o_header("vitals")["body"])
        self.assert_source_spans(parsed)

    def test_heading_style_does_not_supply_an_unperformed_examination(self):
        case = cases.resolve("cardio-palpitations")
        ledger = evidence.Ledger()
        ledger.add(evidence.STATION_INFO, "Mara Lee, female.", meta={"doorway": True})
        ledger.add(evidence.STATION_INFO, "Supplied chart.", meta={"vitals": True})
        for heading in ("Lungs:", "## Lungs", "**Lungs**", "Lungs —"):
            with self.subTest(heading=heading):
                parsed = self.parsed(objective=heading + "\nClear to auscultation bilaterally.")
                claims = audit.audit_note(parsed, ledger, case)["claims"]
                self.assertTrue(claims)
                self.assertTrue(all(c["verdict"] not in ("supported", "supported_supplied") for c in claims))

    def test_section_wrappers_do_not_hide_first_actual_objective_heading(self):
        for wrapper in ("Objective", "Objective:", "## Objective", "**Objective**", "O:"):
            with self.subTest(wrapper=wrapper):
                parsed = self.parsed(objective=wrapper + "\nVitals\nBP 120/80.\nHeart\nRegular rhythm.")
                self.assertEqual(parsed.first_o_header()["canonical"], "vitals")
                self.assert_source_spans(parsed)
        parsed = self.parsed("Subjective\nThe patient has pain.")
        self.assertEqual(parsed.s_headers_present(), set())

    def test_multiline_numbered_assessment_and_plan_preserve_every_line(self):
        assessment = "\n  1. Atrial fibrillation\nSupported by an irregular pulse.\nConsider reversible triggers."
        plan = "2) Obtain ECG;\nadvise stopping energy drinks;\ncounsel about warning symptoms."
        parsed = self.parsed(assessment=[assessment], plan=[plan])
        self.assertTrue(parsed.a_entries[0]["numbered"])
        self.assertEqual(parsed.a_entries[0]["number"], 1)
        self.assertEqual(parsed.a_entries[0]["text"], "Atrial fibrillation\nSupported by an irregular pulse.\nConsider reversible triggers.")
        self.assertTrue(parsed.p_entries[0]["numbered"])
        self.assertEqual(parsed.p_entries[0]["number"], 2)
        self.assertIn("warning symptoms", parsed.p_entries[0]["text"])
        self.assertEqual(parsed.to_dict()["A"], [assessment])
        self.assertFalse(self.parsed(plan=["Obtain ECG.\nArrange follow-up."]).p_entries[0]["numbered"])

    def test_single_string_entry_is_not_split_into_characters_or_invented_entries(self):
        parsed = self.parsed(assessment="1. Asthma\nSymptoms support this possibility.")
        self.assertEqual(len(parsed.a_entries), 1)
        self.assertEqual(parsed.a_entries[0]["number"], 1)
        self.assertIn("Symptoms support", parsed.a_entries[0]["text"])


if __name__ == "__main__":
    unittest.main()
