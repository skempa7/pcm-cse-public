"""Scribbi visits: leading a visit yourself, and watching a demonstrated one.

A led visit is an untimed coached encounter tagged as Scribbi's: finishing it
hands the encounter to Scribbi, which drafts the note from what the student
actually obtained. It never counts as a Chat CSE attempt. A watched visit is a
library round whose review clock waits until the visit ends. Every check runs
against a disposable database.
"""
import json
import unittest
from unittest.mock import patch

from pcmcse import cases, db, engine, learning, scribbi
from pcmcse.scribbi import catalog as C
from pcmcse.scribbi import review as R
from pcmcse.scribbi import staging
from pcmcse.scribbi import visit as V
from test_scribbi import Isolated, perfect_state

LABELS = {"chief_complaint", "onset", "timing", "alleviating", "severity", "location", "quality", "aggravating",
          "setting", "treatment", "radiation", "chronology", "associated", "past_occurrence", "concern", "fife",
          "pmh", "psh", "medications", "allergies", "social", "obgyn", "family", "pertinent_negative"}


class LedVisit(Isolated):
    def led_visit(self, case_id="renal-flank-pain", variant_id="base", talks=8, exams=3, leave_running=False):
        """A student leading the visit: the demonstration's questions and exams, in order."""
        state = self.route("/api/session", {"case_id": case_id, "variant_id": variant_id,
                                            "learning_mode": "coached", "purpose": "scribbi"})
        sid = state["id"]
        self.route("/api/session/%s/start" % sid, {})
        walk = V.load_walkthrough(case_id, variant_id)
        ledger = {e["seq"]: e for e in walk["ledger"]}
        for t in [t for t in walk["timeline"] if t["kind"] == "dialogue" and t.get("student")][:talks]:
            self.route("/api/session/%s/say" % sid, {"text": t["student"]})
        done = 0
        for t in [t for t in walk["timeline"] if t.get("maneuver_id")]:
            if done >= exams:
                break
            action = next((ledger[e] for e in t["event_ids"] if ledger.get(e, {}).get("kind") == "exam_action"), None)
            comps = (action or {}).get("meta", {}).get("components", [])
            r = self.route("/api/session/%s/exam" % sid, {"maneuver_id": t["maneuver_id"], "components": comps,
                                                           "source_text": "Perform: " + t["action"]})
            ev = r["events"][0]
            if not ev.get("examination_id"):
                continue
            done += 1
            if leave_running and done == exams:
                break
            self.route("/api/session/%s/exam_control" % sid, {"examination_id": ev["examination_id"], "operation": "skip"})
        return sid

    def finish(self, sid, mode="learn", status=200, **extra):
        return self.route("/api/scribbi/rounds", dict({"attempt_id": sid, "mode": mode}, **extra), status=status)


class LedVisitTests(LedVisit):
    def test_a_scribbi_visit_is_an_untimed_coached_encounter(self):
        self.route("/api/session", {"case_id": "renal-flank-pain", "learning_mode": "independent", "purpose": "scribbi"}, status=400)
        self.route("/api/session", {"case_id": "renal-flank-pain", "learning_mode": "coached", "purpose": "other"}, status=400)
        state = self.route("/api/session", {"case_id": "renal-flank-pain", "learning_mode": "coached", "purpose": "scribbi"})
        self.assertEqual(state["purpose"], "scribbi")
        self.assertEqual(state["phase"], "briefing")
        started = self.route("/api/session/%s/start" % state["id"], {})
        self.assertIsNone(started["phase_ends_at"])
        plain = self.route("/api/session", {"case_id": "renal-flank-pain", "learning_mode": "coached"})
        self.assertIsNone(plain["purpose"])

    def test_a_short_visit_stays_open_and_says_what_is_missing(self):
        sid = self.led_visit(talks=2, exams=0)
        body = self.finish(sid, status=409)
        self.assertTrue(body["too_short"])
        self.assertEqual(body["need"], {"history": 4, "exams": 2})
        self.assertLess(body["have"]["exams"], 2)
        self.assertIn("examination", body["error"])
        self.assertNotIn("demonstrated visit", body["error"])
        self.assertEqual(self.route("/api/session/" + sid)["phase"], "encounter")

    def test_finishing_hands_the_visit_to_scribbi_and_keeps_it_out_of_chat_cse(self):
        sid = self.led_visit()
        rnd = self.finish(sid)
        self.assertEqual(rnd["source"], "visit")
        self.assertEqual(rnd["source_attempt_id"], sid)
        self.assertEqual(rnd["visit"]["source"], "attempt")
        state = self.route("/api/session/" + sid)
        self.assertEqual(state["phase"], "note")
        self.assertEqual(state["scribbi_round_id"], rnd["id"])
        # Finishing twice (a double click, a reload) returns the same draft.
        self.assertEqual(self.finish(sid)["id"], rnd["id"])
        again = self.finish(sid, mode="coached", again=True)
        self.assertNotEqual(again["id"], rnd["id"])
        self.assertEqual(again["source"], "visit")
        # Not a Chat CSE attempt: lists, progress and the reset gate leave it out.
        self.assertEqual(db.list_sessions(), [])
        self.assertEqual([s["id"] for s in db.list_sessions(include_scribbi=True)], [sid])
        self.assertEqual(learning.progress()["attempted_cases"], [])
        home = self.route("/api/scribbi")
        self.assertEqual(home["open_visits"], [])
        preview = self.route("/api/progress/reset-preview", {"scope": "all"})
        self.assertEqual((preview["attempt_count"], preview["unfinished_count"]), (0, 0))
        self.assertEqual((preview["scribbi_visit_count"], preview["scribbi_count"]), (1, 2))
        reset = self.route("/api/progress/reset", {"scope": "all", "confirm": True, "include_in_progress": False})
        self.assertEqual(reset["deleted"]["scribbi_visits"], 1)
        self.assertEqual(reset["deleted"]["attempts"], 0)

    def test_statements_about_exam_parts_never_done_are_left_out(self):
        """The CVA test doesn't put Murphy sign in the draft; palpating the neck doesn't put T10-L1 there."""
        state = self.route("/api/session", {"case_id": "renal-flank-pain", "variant_id": "base",
                                            "learning_mode": "coached", "purpose": "scribbi"})
        sid = state["id"]
        self.route("/api/session/%s/start" % sid, {})
        walk = V.load_walkthrough("renal-flank-pain", "base")
        for t in [t for t in walk["timeline"] if t["kind"] == "dialogue" and t.get("student")][:10]:
            self.route("/api/session/%s/say" % sid, {"text": t["student"]})
        for mid, comps in (("abd_special", ["cva tenderness"]), ("osteo_screen", ["cervical"]),
                           ("general_inspect", []), ("heart_auscultate", ["aortic", "pulmonic", "tricuspid", "mitral", "on skin"])):
            r = self.route("/api/session/%s/exam" % sid, {"maneuver_id": mid, "components": comps,
                                                           "source_text": "Perform: " + mid})
            ev = r["events"][0]
            if ev.get("examination_id"):
                self.route("/api/session/%s/exam_control" % sid, {"examination_id": ev["examination_id"], "operation": "skip"})
        plant_nothing = lambda b, ctx, mode, seed: ([], scribbi.P.hands_on(b, ctx))
        with patch.object(scribbi.P, "plant", side_effect=plant_nothing):
            rnd = self.finish(sid)
        row = scribbi.store.get(rnd["id"])
        drafted = " ".join(ch["text"] for ln in json.loads(row["lines_json"]) for ch in ln["chips"]).lower()
        for word in ("murphy", "mcburney", "psoas", "obturator"):
            self.assertNotIn(word, drafted)
        hands = json.loads(row["key_json"]).get("hands_on")
        if hands:
            self.assertNotRegex(hands["correct"], r"T10|L1\b")

    def test_an_unfinished_visit_waits_on_the_scribbi_home(self):
        sid = self.led_visit(talks=3, exams=0)
        visits = self.route("/api/scribbi")["open_visits"]
        self.assertEqual([v["id"] for v in visits], [sid])
        self.assertEqual(visits[0]["patient_name"], cases.resolve("renal-flank-pain", "base")["patient"]["name"])

    def test_an_examination_still_running_is_completed_not_lost(self):
        sid = self.led_visit(exams=3, leave_running=True)
        self.assertTrue(self.route("/api/session/" + sid)["pending_exam"])
        rnd = self.finish(sid)
        exams = [t for t in rnd["visit"]["turns"] if t["kind"] == "exam"]
        self.assertEqual(len(exams), 3)
        self.assertFalse(any(t.get("no_finding") for t in exams), exams)

    def test_everything_obtained_reaches_the_draft(self):
        """Each fact the patient told the student sits behind some history line."""
        plant_nothing = lambda b, ctx, mode, seed: ([], scribbi.P.hands_on(b, ctx))
        for case_id in ("renal-flank-pain", "cardio-chest-pressure", "gi-epigastric-melena",
                        "msk-shoulder-overuse", "heent-ear-pain"):
            sid = self.led_visit(case_id, talks=10, exams=3)
            with patch.object(scribbi.P, "plant", side_effect=plant_nothing):
                rnd = self.finish(sid)
            row = scribbi.store.get(rnd["id"])
            lines = json.loads(row["lines_json"])
            session = engine.load(sid)
            visit, e2r, _ = V.attempt_visit(session)
            facts = {f["id"]: f for f in session.case["facts"]}
            cited = {ref for ln in lines if ln["section"] == "S" for ch in ln["chips"] for ref in ch.get("evidence", [])}
            for fid, ev in session.ledger.released_facts().items():
                if facts.get(fid, {}).get("category") in LABELS:
                    self.assertIn(e2r.get(ev["seq"]), cited, (case_id, fid))
            replies = " ".join(t.get("patient", "") for t in visit["turns"] if t["kind"] == "talk")
            for ln in lines:
                for ch in ln["chips"]:
                    if ch.get("origin") == "visit" and ln["section"] == "S":
                        quoted = ch["text"].split('"')[1] if '"' in ch["text"] else ch["text"]
                        self.assertIn(quoted, replies, (case_id, ch["text"]))

    def test_a_led_draft_grades_like_the_library(self):
        sid = self.led_visit(talks=14, exams=5)
        first = True
        for mode in C.MODES:
            for seed in (5, 41):
                with patch("random.SystemRandom.randrange", return_value=seed):
                    rnd = self.finish(sid, mode=mode, again=not first)
                first = False
                row = scribbi.store.get(rnd["id"])
                key, lines, visit = json.loads(row["key_json"]), json.loads(row["lines_json"]), json.loads(row["visit_json"])
                if mode != "solo":
                    self.assertGreaterEqual(len(key["errors"]), C.MODES[mode]["errors"][0], (mode, seed))
                perfect = R.evaluate(key, lines, visit, R.sanitize(perfect_state(lines, key), lines))
                self.assertEqual(perfect["score"], 100, (mode, seed, perfect["items"]))
                self.assertEqual(perfect["false_alarms"], [])
                untouched = R.evaluate(key, lines, visit, R.sanitize({}, lines))
                self.assertTrue(all(it["verdict"] == "missed" for it in untouched["items"]))


class WatchedVisitTests(Isolated):
    def test_the_review_clock_waits_for_the_visit(self):
        body = {"case_id": "renal-flank-pain", "variant_id": "base", "mode": "solo", "timed": True, "watch": True}
        rnd = self.route("/api/scribbi/rounds", body)
        self.assertFalse(rnd["started"])
        self.assertIsNone(rnd["deadline"])
        later = db.now_ms() + 20 * 60 * 1000
        with patch.object(db, "now_ms", return_value=later):
            self.assertEqual(self.route("/api/scribbi/rounds/" + rnd["id"])["status"], "reviewing")
            begun = self.route("/api/scribbi/rounds/%s/begin" % rnd["id"], {})
        self.assertTrue(begun["started"])
        self.assertEqual(begun["deadline"], later + 300 * 1000)
        # Beginning twice never restarts the clock.
        with patch.object(db, "now_ms", return_value=later + 5000):
            self.assertEqual(self.route("/api/scribbi/rounds/%s/begin" % rnd["id"], {})["deadline"], later + 300 * 1000)
        plain = self.route("/api/scribbi/rounds", dict(body, watch=False))
        self.assertTrue(plain["started"])
        self.assertIsNotNone(plain["deadline"])

    def test_playback_stages_every_demonstrated_visit(self):
        unresolved = 0
        for p in V.library_paths():
            visit = V.library_visit(p["case_id"], p["variant_id"])[0]
            pb = staging.build(p["case_id"], p["variant_id"])
            self.assertEqual([t["id"] for t in pb["turns"]], [t["id"] for t in visit["turns"]], p)
            self.assertIn(pb["appearance"]["presentation"], ("female", "male"))
            for turn, stage in zip(visit["turns"], pb["turns"]):
                self.assertIn(stage["posture"], ("seated", "supine", "standing", "prone"))
                if turn["kind"] == "talk":
                    self.assertIsInstance(stage["gesture"], dict)
                    self.assertIsInstance(stage["affect"], dict)
                if turn["kind"] == "exam":
                    if stage.get("plan"):
                        self.assertTrue(stage["plan"]["steps"], (p, turn["label"]))
                        self.assertGreater(stage["plan"]["duration_s"], 0)
                    else:
                        unresolved += 1
        self.assertLessEqual(unresolved, 3)

    def test_only_demonstrated_visits_can_be_replayed(self):
        rnd = self.route("/api/scribbi/rounds", {"case_id": "renal-flank-pain", "variant_id": "base", "mode": "learn", "watch": True})
        pb = self.route("/api/scribbi/rounds/%s/playback" % rnd["id"])
        self.assertEqual(len(pb["turns"]), len(rnd["visit"]["turns"]))
        led = LedVisit.led_visit(self)
        own = self.route("/api/scribbi/rounds", {"attempt_id": led, "mode": "learn"})
        self.route("/api/scribbi/rounds/%s/playback" % own["id"], status=409)


if __name__ == "__main__":
    unittest.main()
