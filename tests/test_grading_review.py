"""Grading recognition and immutable original-note rechecks."""
import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pcmcse import cases, config, db, engine, grading_review, note
from offline_routes import request


class GradingReviewTests(unittest.TestCase):
    def test_unknown_wording_is_separate_from_proven_errors_and_never_changes_points(self):
        parsed=note.parse({"S": "HPI: An unfamiliar description."})
        audit={"claims": [
            {"section": "S", "header": "hpi", "text": "An unfamiliar description.", "verdict": "not_evaluated", "explanation": "Could not map.", "evidence": []},
            {"section": "O", "header": "heart", "text": "Wrong finding.", "verdict": "contradicts"}]}
        rubric={"total_earned": 7, "rows": [{"id":"a", "label":"Diagnosis", "why":"Mapping unresolved.", "passage":"An alternative.", "recognition_limited":True}]}
        before=copy.deepcopy((audit,rubric,parsed.to_dict()))
        review=grading_review.describe(parsed,audit,rubric)
        self.assertEqual(review["status"],"needs_review")
        self.assertEqual(len(review["unverified_passages"]),1)
        self.assertEqual(len(review["unresolved_rows"]),1)
        self.assertEqual((audit,rubric,parsed.to_dict()),before)

    def test_explicit_not_obtained_is_not_reported_as_a_language_failure(self):
        claims=[{"section":"S", "text":text,"verdict":"not_evaluated"}
                for text in ["Not obtained.","Not assessed.","Not obtained. An unfamiliar symptom."]]
        report=grading_review.describe(note.parse({}),{"claims":claims},{"rows":[]})
        self.assertEqual([r["text"] for r in report["unverified_passages"]], ["Not obtained. An unfamiliar symptom."])

    def test_no_unknown_wording_does_not_claim_complete_clinical_validation(self):
        review=grading_review.describe(note.parse({}),{"claims":[]},{"rows":[]})
        self.assertEqual(review["status"],"automatic_review")
        self.assertIn("does not establish a faculty grade",review["note"])


class OriginalNoteRecheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="cse-recheck-")
        self.old=db.DB_PATH
        db.DB_PATH=os.path.join(self.tmp.name,"attempts.sqlite")
        db.init()
        case=cases.resolve("cardio-palpitations")
        settings=copy.deepcopy(config.DEFAULT_SETTINGS)
        settings.update(learning_mode="guided")
        self.sid=db.create_session(case["id"],"guided_untimed","type",True,settings,case=case)
        session=engine.load(self.sid)
        session.start_encounter()
        session.student_turn("What brings you in today?")
        self.original={"S":"CC: Racing heartbeat.\nHPI: Heart keeps fluttering and racing.","O":"", "A":["1. Atrial fibrillation.\nMost likely."],"P":["1. Obtain an ECG.\nRefer to cardiology."]}
        db.update_session(self.sid,phase="submitted",original_note_json=json.dumps(self.original),note_json=json.dumps(self.original),results_json=json.dumps({"rubric":{"total_earned":7,"total_available":100},"note":self.original}),engine_version="4.1.0")

    def tearDown(self):
        db.DB_PATH=self.old
        self.tmp.cleanup()

    def call(self,action,body=None):
        return json.loads(request(f"/api/session/{self.sid}/{action}","POST",json.dumps(body or {})))

    def test_recheck_uses_frozen_original_and_saves_separate_result(self):
        before=copy.deepcopy(db.get_session(self.sid))
        ledger=engine.load(self.sid).ledger.to_json()
        reply=self.call("recheck",{"note":{"S":"Attempted replacement"}})
        self.assertEqual(reply["status"],200,reply)
        result=reply["body"]["results"]
        self.assertEqual(result["note"],self.original)
        self.assertIn("grading_review",result)
        self.assertIn("original note recheck",result["label"])
        self.assertEqual(db.get_session(self.sid),before)
        self.assertEqual(engine.load(self.sid).ledger.to_json(),ledger)
        revisions=db.list_revisions(self.sid)
        self.assertEqual(len(revisions),1)
        self.assertEqual(revisions[0]["kind"],"recheck")
        self.assertEqual(revisions[0]["note"],self.original)
        self.assertEqual(revisions[0]["results"],result)

    def test_retry_reuses_same_completed_recheck_without_duplicating_it(self):
        first=self.call("recheck")
        with patch.object(engine.Session,"compute_results",side_effect=AssertionError("must reuse")):
            second=self.call("recheck")
        self.assertEqual(first,second)
        self.assertEqual(len(db.list_revisions(self.sid)),1)

    def test_unsubmitted_attempt_cannot_be_rechecked(self):
        db.update_session(self.sid,phase="note")
        before=db.get_session(self.sid)
        self.assertEqual(self.call("recheck")["status"],409)
        self.assertEqual(db.get_session(self.sid),before)
        self.assertEqual(db.list_revisions(self.sid),[])

    def test_failed_recheck_creates_no_revision_or_original_change(self):
        before=db.get_session(self.sid)
        with patch.object(engine.Session,"compute_results",side_effect=RuntimeError("test unavailable")):
            reply=self.call("recheck")
        self.assertEqual(reply["status"],500)
        self.assertEqual(db.get_session(self.sid),before)
        self.assertEqual(db.list_revisions(self.sid),[])

    def test_revision_still_accepts_edited_writing_separately(self):
        edited=dict(self.original,S="CC: Fluttering heartbeat.")
        reply=self.call("revise",{"note":edited})
        self.assertEqual(reply["status"],200)
        self.assertEqual(reply["body"]["results"]["note"],edited)
        self.assertEqual(engine.load(self.sid).original_note(),self.original)
        self.assertEqual(db.list_revisions(self.sid)[0]["kind"],"revision")

if __name__=="__main__":unittest.main()
