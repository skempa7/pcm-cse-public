"""Age documentation requires delivered identity; historical evidence stays valid."""
import copy
import unittest

from pcmcse import audit, cases, evidence, grader, identity_evidence, note


class IdentityEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.case = cases.resolve("cardio-palpitations")
        self.ledger = evidence.Ledger()
        self.ledger.add(evidence.STATION_INFO, "Mara Lee, female.", meta={"doorway": True})

    def reply(self, text="I am 27 years old.", fields=None, **meta):
        return self.ledger.add(evidence.PATIENT, text,
                               meta={"identity_fields": fields if fields is not None else ["age"], **meta})

    def grade(self, text):
        parsed = note.ParsedNote("HPI: " + text, "", [], [])
        result = audit.audit_note(parsed, self.ledger, self.case)
        row = next(r for r in grader.grade(parsed, self.ledger, self.case, result)["rows"]
                   if r["id"] == "age_sex")
        return result["claims"], row

    def test_truth_without_delivery_is_not_age_evidence(self):
        for text in ("27 yo f.", "27-year-old female.", "27F", "F/27",
                     "twenty-seven-year-old woman.", "Mara Lee is a 27-year-old woman."):
            with self.subTest(text=text):
                claims, row = self.grade(text)
                self.assertEqual(row["points_earned"], 0)
                self.assertEqual(claims[0]["verdict"], "unsupported")
        self.assertNotIn("age", identity_evidence.obtained(self.case, self.ledger))

    def test_patient_reply_enables_only_the_delivered_field(self):
        self.reply("My name is Mara Lee.", ["name"])
        self.assertNotIn("age", identity_evidence.obtained(self.case, self.ledger))
        answer = self.reply()
        for text in ("27 yo f.", "27-year-old female.", "27F", "F/27",
                     "twenty-seven-year-old woman.", "Mara Lee is a 27-year-old woman."):
            with self.subTest(text=text):
                claims, row = self.grade(text)
                self.assertEqual(row["points_earned"], 2)
                self.assertEqual(claims[0]["verdict"], "supported")
                self.assertIn(answer["seq"], [e["seq"] for e in row["evidence"]])
        self.assertEqual(self.ledger.released_concepts(), {})
        self.assertEqual(self.ledger.released_facts(), {})

    def test_metadata_cannot_invent_identity(self):
        for text in ("My mother is 27 years old.", "I am not 27 years old.",
                     "I am 28 years old.", "I take 27 milligrams.", "I do not know."):
            with self.subTest(text=text):
                self.ledger.events = self.ledger.events[:1]
                self.reply(text)
                self.assertNotIn("age", identity_evidence.obtained(self.case, self.ledger))
        self.ledger.events = self.ledger.events[:1]
        self.reply("I am 27 years old.", [])
        self.assertNotIn("age", identity_evidence.obtained(self.case, self.ledger))
        for flag in ("uncertain", "no_information", "interrupted"):
            self.ledger.events = self.ledger.events[:1]
            self.reply(**{flag: True})
            self.assertNotIn("age", identity_evidence.obtained(self.case, self.ledger))

    def test_wrong_documented_age_does_not_earn_credit(self):
        self.reply()
        claims, row = self.grade("28-year-old female.")
        self.assertEqual(row["points_earned"], 0)
        self.assertEqual(claims[0]["verdict"], "contradicts")

    def test_identity_and_symptom_each_require_evidence(self):
        self.ledger.add(evidence.PATIENT, self.case["patient"]["opening"], meta={"kind": "opening"})
        text = "Mara Lee, 27-year-old woman reports persistent palpitations."
        self.assertEqual(self.grade(text)[0][0]["verdict"], "unsupported")
        self.reply()
        claims, _ = self.grade(text)
        self.assertEqual(claims[0]["verdict"], "supported")
        self.assertEqual({e["seq"] for e in claims[0]["evidence"]}, {1, 2, 3})
        claims, _ = self.grade("27-year-old woman reports persistent palpitations and hemoptysis.")
        self.assertNotIn(claims[0]["verdict"], ("supported", "supported_supplied"))
        self.ledger.events = [self.ledger.events[0], self.ledger.events[-1]]
        self.assertNotIn(self.grade(text)[0][0]["verdict"], ("supported", "supported_supplied"))

    def test_preferred_name_does_not_assert_an_unspoken_full_name(self):
        self.case["patient"]["preferred_name"] = "Mari"
        self.ledger = evidence.Ledger()
        self.reply("You can call me Mari.", ["preferred_name"])
        known = identity_evidence.obtained(self.case, self.ledger)
        self.assertEqual(known["preferred_name"]["value"], "Mari")
        self.assertNotIn("name", known)
        self.reply("You can call me Mara Lee.", ["name"])
        self.assertEqual(identity_evidence.obtained(self.case, self.ledger)["name"]["value"], "Mara Lee")

    def test_repeated_identity_keeps_one_value_and_links_without_mutation(self):
        self.reply()
        self.reply("I'm twenty-seven years old.")
        original_case, original_events = copy.deepcopy(self.case), copy.deepcopy(self.ledger.events)
        known = identity_evidence.obtained(self.case, self.ledger.events)
        self.assertEqual(known["age"]["value"], 27)
        self.assertEqual(len(known["age"]["evidence"]), 2)
        self.assertEqual(self.case, original_case)
        self.assertEqual(self.ledger.events, original_events)

    def test_all_case_paths_retain_historical_supplied_age_support(self):
        paths = 0
        for cid, base in cases.all_cases().items():
            for vid in ["base"] + [v["id"] for v in base.get("variants", [])]:
                with self.subTest(case=cid, variant=vid):
                    case = cases.resolve(cid, vid)
                    ledger = evidence.Ledger()
                    ledger.add(evidence.STATION_INFO, " ".join(case["station"]["doorway"]), meta={"doorway": True})
                    before = ledger.to_json()
                    known = identity_evidence.obtained(case, ledger)
                    self.assertEqual(known["age"]["value"], case["patient"]["age"])
                    self.assertEqual(known["sex"]["value"], case["patient"]["sex"])
                    parsed = note.ParsedNote("HPI: %d-year-old %s." % (case["patient"]["age"], case["patient"]["sex"]), "", [], [])
                    checked = audit.audit_note(parsed, ledger, case)
                    row = grader.grade(parsed, ledger, case, checked)["rows"][0]
                    self.assertEqual(row["points_earned"], 2)
                    self.assertEqual(ledger.to_json(), before)
                    paths += 1
        self.assertEqual(paths, 82)


if __name__ == "__main__":
    unittest.main()
