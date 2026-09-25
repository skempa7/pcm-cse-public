"""Scribbi: drafts, planted mistakes, grading, routes and persistence.

Every check here runs against a disposable database. The library-wide tests
build real drafts for every demonstrated visit, so a content change that
breaks a mistake generator shows up as a failing case, not a silent skip.
"""
import json
import os
import re
import tempfile
import unittest
from unittest.mock import patch

from pcmcse import cases, config, db, engine, evidence, scribbi
from pcmcse.scribbi import catalog as C
from pcmcse.scribbi import review as R
from pcmcse.scribbi import text as T
from pcmcse.scribbi import visit as V
import offline_routes


def perfect_state(lines, key):
    """What an ideal reviewer submits: every mistake fixed, nothing else touched."""
    chips, added = {}, []
    for err in key["errors"] + ([key["hands_on"]] if key["hands_on"] else []):
        kind = err["check"]["kind"]
        if kind == "inserted":
            chips[err["chip"]] = {"status": "removed"}
        elif kind in ("modified", "lead"):
            chips[err["chip"]] = {"status": "edited", "text": err["original"]}
            for other in err["check"].get("chips") or []:
                if other != err["chip"]:
                    chips[other] = {"status": "edited", "text": err["planted"]}
        elif kind == "omission":
            added.append({"id": "a%d" % (len(added) + 1), "section": "S", "text": err["original"]})
        elif kind == "structural":
            added.append({"id": "a%d" % (len(added) + 1), "section": "O", "text": err["correct"]})
    return {"chips": chips, "added": added}


def find_round(case_id, variant_id, mode, want_type, seeds=range(1, 600)):
    for seed in seeds:
        visit, lines, key = scribbi.build(case_id, variant_id, mode, seed)
        for err in key["errors"]:
            if err["type"] == want_type:
                return visit, lines, key, err
    raise AssertionError("no %s mistake found for %s" % (want_type, case_id))


def chip_text(lines, cid):
    return next(ch["text"] for ln in lines for ch in ln["chips"] if ch["id"] == cid)


def verdict_of(result, err_id):
    return next(it["verdict"] for it in result["items"] if it["error"]["id"] == err_id)


def replay_attempt(case_id, variant_id="base", talk_limit=None, exam_limit=None, submit=True):
    """A submitted Chat CSE attempt that asks the demonstration's questions.

    The written-example runtime completes examinations at once, exactly as the
    teaching library builds its demonstrations."""
    walk = V.load_walkthrough(case_id, variant_id)
    settings = config.load_settings()
    settings.update(learning_mode="coached", simulation_runtime="written-example")
    sid = db.create_session(case_id, "coached_untimed", "type", True, settings, case=cases.resolve(case_id, variant_id))
    s = engine.load(sid)
    s.start_encounter()
    ledger = {e["seq"]: e for e in walk["ledger"]}
    talks = [t for t in walk["timeline"] if t["kind"] == "dialogue"]
    exams = [t for t in walk["timeline"] if t.get("maneuver_id")]
    for t in talks[:talk_limit]:
        s.student_turn(t["student"])
    for t in exams[:exam_limit]:
        action = next((ledger[e] for e in t["event_ids"] if ledger.get(e, {}).get("kind") == evidence.EXAM_ACTION), None)
        comps = (action or {}).get("meta", {}).get("components", [])
        s.perform_maneuver(t["maneuver_id"], comps)
    s = engine.load(sid)
    s.end_encounter_now()
    s = engine.load(sid)
    if s.row["phase"] == "organize":
        s.skip_organize()
        s = engine.load(sid)
    if submit:
        s.save_note({"S": "cc: test", "O": "Vitals: see chart", "A": ["1. test"], "P": ["1. test"]})
        s.submit("submitted")
    return sid


class Isolated(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scribbi-")
        self.old_db = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name, "attempts.sqlite")
        db.init()

    def tearDown(self):
        db.DB_PATH = self.old_db
        self.temp.cleanup()

    def route(self, path, body=None, status=200):
        method = "GET" if body is None else "POST"
        out = json.loads(offline_routes.request(path, method, json.dumps(body or {})))
        self.assertEqual(out["status"], status, (path, out["body"]))
        return out["body"]


class LibraryWideTests(unittest.TestCase):
    """Every demonstrated visit, every mode, several seeds."""

    @classmethod
    def setUpClass(cls):
        cls.paths = V.library_paths()

    def test_every_visit_builds_and_grades_consistently(self):
        self.assertEqual(len(self.paths), 82)
        type_seen = set()
        for p in self.paths:
            for mode in C.MODES:
                for seed in (11, 23):
                    visit, lines, key = scribbi.build(p["case_id"], p["variant_id"], mode, seed)
                    ids = [ch["id"] for ln in lines for ch in ln["chips"]]
                    self.assertEqual(len(ids), len(set(ids)))
                    self.assertTrue(all(re.fullmatch(r"c\d+", i) for i in ids))
                    lo, hi = C.MODES[mode]["errors"]
                    self.assertLessEqual(len(key["errors"]), hi)
                    if mode != "solo":
                        self.assertGreaterEqual(len(key["errors"]), lo, (p, mode, seed))
                    for err in key["errors"]:
                        type_seen.add(err["type"])
                        self.assertIn(err["severity"], ("high", "medium", "low"))
                        self.assertTrue(err["note"])
                    perfect = R.evaluate(key, lines, visit, R.sanitize(perfect_state(lines, key), lines))
                    self.assertEqual(perfect["score"], 100, (p, mode, seed, perfect["items"]))
                    self.assertTrue(perfect["safe"])
                    self.assertEqual(perfect["false_alarms"], [])
                    self.assertEqual(perfect["unsupported"], [])
                    untouched = R.evaluate(key, lines, visit, R.sanitize({}, lines))
                    self.assertTrue(all(it["verdict"] == "missed" for it in untouched["items"]))
                    if key["errors"]:
                        self.assertEqual(untouched["score"], 0)
                    elif untouched["items"]:
                        # A clean draft signed as is loses only the missing structural findings.
                        self.assertEqual(untouched["score"], 75)
        self.assertEqual(type_seen, set(C.ERROR_TYPES) - {"hands_on"})

    def test_draft_stays_in_chart_voice(self):
        """First-person patient wording only ever appears inside quotation marks."""
        for p in self.paths:
            visit, lines, key = scribbi.build(p["case_id"], p["variant_id"], "coached", 3)
            for ln in lines:
                for ch in ln["chips"]:
                    self.assertFalse(T.has_first_person(T.outside_quotes(ch["text"])), (p, ln["label"], ch["text"]))
                    if ln["section"] == "S":  # O uses inch marks: Ht 5' 7"
                        self.assertEqual(ch["text"].count('"') % 2, 0, ch["text"])

    def test_structural_line_is_never_in_the_draft(self):
        for p in self.paths:
            visit, lines, key = scribbi.build(p["case_id"], p["variant_id"], "coached", 5)
            labels = [ln["label"] for ln in lines if ln["section"] == "O"]
            self.assertNotIn("Osteopathic", labels)
            felt = [t for t in visit["turns"] if t["kind"] == "exam" and t.get("felt")]
            self.assertEqual(bool(key["hands_on"]), bool(felt), p)

    def test_same_seed_same_draft(self):
        a = scribbi.build("renal-flank-pain", "base", "coached", 99)
        b = scribbi.build("renal-flank-pain", "base", "coached", 99)
        self.assertEqual(json.dumps(a[1], sort_keys=True), json.dumps(b[1], sort_keys=True))
        self.assertEqual(json.dumps(a[2], sort_keys=True), json.dumps(b[2], sort_keys=True))

    def test_invented_exams_only_for_regions_nobody_examined(self):
        for p in self.paths:
            for seed in range(1, 8):
                visit, lines, key = scribbi.build(p["case_id"], p["variant_id"], "solo", seed)
                examined = V.examined_regions(visit)
                for err in key["errors"]:
                    if err["type"] == "fabricated_exam":
                        self.assertNotIn(err["label"], examined, (p, err["label"]))


class MistakeTypeTests(unittest.TestCase):
    """Realistic student edits for each kind of mistake."""

    def test_flipped_finding(self):
        visit, lines, key, err = find_round("renal-flank-pain", "base", "coached", "flipped")
        original = err["original"]
        fixed = R.evaluate(key, lines, visit, R.sanitize({"chips": {err["chip"]: {"status": "edited", "text": original}}}, lines))
        self.assertEqual(verdict_of(fixed, err["id"]), "fixed")
        removed = R.evaluate(key, lines, visit, R.sanitize({"chips": {err["chip"]: {"status": "removed"}}}, lines))
        self.assertEqual(verdict_of(removed, err["id"]), "caught")
        still = R.evaluate(key, lines, visit, R.sanitize({"chips": {err["chip"]: {"status": "edited", "text": err["planted"] + " Confirmed."}}}, lines))
        self.assertEqual(verdict_of(still, err["id"]), "missed")

    def test_wrong_detail_values_and_rewording(self):
        found = {}
        for seed in range(1, 900):
            visit, lines, key = scribbi.build("renal-flank-pain", "base", "solo", seed)
            for err in key["errors"]:
                if err["type"] == "wrong_detail":
                    found.setdefault(err["check"]["mode"], (visit, lines, key, err))
            if {"vital", "side", "rating", "duration", "dose"} <= set(found):
                break
        self.assertTrue({"vital", "side", "rating"} <= set(found), found.keys())
        for mode, (visit, lines, key, err) in found.items():
            fixed = R.evaluate(key, lines, visit, R.sanitize({"chips": {err["chip"]: {"status": "edited", "text": err["original"]}}}, lines))
            self.assertEqual(verdict_of(fixed, err["id"]), "fixed", mode)
            kept = R.evaluate(key, lines, visit, R.sanitize({}, lines))
            self.assertEqual(verdict_of(kept, err["id"]), "missed", mode)
        if "duration" in found:
            visit, lines, key, err = found["duration"]
            words = re.sub(r"\b2 days\b", "two days", err["original"])
            if words != err["original"]:
                result = R.evaluate(key, lines, visit, R.sanitize({"chips": {err["chip"]: {"status": "edited", "text": words}}}, lines))
                self.assertEqual(verdict_of(result, err["id"]), "fixed")

    def test_invented_exam_can_be_deleted_or_marked_not_examined(self):
        visit, lines, key, err = find_round("renal-flank-pain", "base", "coached", "fabricated_exam")
        for edit in ({"status": "removed"}, {"status": "edited", "text": "Not examined."},
                     {"status": "edited", "text": "Deferred."}):
            result = R.evaluate(key, lines, visit, R.sanitize({"chips": {err["chip"]: edit}}, lines))
            self.assertEqual(verdict_of(result, err["id"]), "fixed", edit)
        reworded = R.evaluate(key, lines, visit, R.sanitize({"chips": {err["chip"]: {"status": "edited", "text": err["planted"].upper()}}}, lines))
        self.assertEqual(verdict_of(reworded, err["id"]), "missed")

    def test_wrong_person(self):
        visit, lines, key, err = find_round("renal-flank-pain", "base", "solo", "misattributed")
        moved = R.evaluate(key, lines, visit, R.sanitize({"chips": {err["chip"]: {"status": "edited",
                           "text": "Family history: " + err["planted"]}}}, lines))
        self.assertEqual(verdict_of(moved, err["id"]), "fixed")
        kept = R.evaluate(key, lines, visit, R.sanitize({}, lines))
        self.assertEqual(verdict_of(kept, err["id"]), "missed")
        # The note names the right relative: the one next to the condition.
        relative = re.search(r"patient's (\w+)", err["note"]).group(1)
        fh = " ".join(ch["text"] for ln in lines if ln["label"] == "FH" for ch in ln["chips"]).lower()
        self.assertIn(relative, fh)

    def test_left_out_items_are_matched_in_student_words(self):
        visit, lines, key, err = find_round("renal-flank-pain", "base", "solo", "dropped")
        state = {"added": [{"id": "a1", "section": "S", "text": err["original"]}]}
        self.assertEqual(verdict_of(R.evaluate(key, lines, visit, R.sanitize(state, lines)), err["id"]), "fixed")
        wrong_section = {"added": [{"id": "a1", "section": "P", "text": err["original"]}]}
        self.assertEqual(verdict_of(R.evaluate(key, lines, visit, R.sanitize(wrong_section, lines)), err["id"]), "missed")

    def test_anchored_assessment(self):
        visit, lines, key, err = find_round("renal-flank-pain", "base", "coached", "anchored_dx")
        result = R.evaluate(key, lines, visit, R.sanitize({"chips": {err["chip"]: {"status": "edited", "text": "Pyelonephritis"}}}, lines))
        self.assertEqual(verdict_of(result, err["id"]), "fixed")
        kept = R.evaluate(key, lines, visit, R.sanitize({}, lines))
        self.assertEqual(verdict_of(kept, err["id"]), "missed")
        # Removing the wrong lead lets the true leading diagnosis move up.
        if len(err["check"].get("chips") or []) == 2:
            removed = R.evaluate(key, lines, visit, R.sanitize({"chips": {err["chip"]: {"status": "removed"}}}, lines))
            self.assertEqual(verdict_of(removed, err["id"]), "fixed")

    def test_allergy_conflict(self):
        visit, lines, key, err = find_round("renal-flank-pain", "base", "coached", "allergy_conflict")
        avoided = R.evaluate(key, lines, visit, R.sanitize({"chips": {err["chip"]: {"status": "edited",
                             "text": "Avoid TMP-SMX given sulfa allergy; choose a non-sulfonamide antibiotic."}}}, lines))
        self.assertEqual(verdict_of(avoided, err["id"]), "fixed")
        swapped = R.evaluate(key, lines, visit, R.sanitize({"chips": {err["chip"]: {"status": "edited", "text": "Start Bactrim DS."}}}, lines))
        self.assertEqual(verdict_of(swapped, err["id"]), "missed")

    def test_structural_findings_level_and_side(self):
        visit, lines, key = scribbi.build("renal-flank-pain", "base", "coached", 3)
        h = key["hands_on"]
        self.assertIsNotNone(h)

        def verdict(text):
            res = R.evaluate(key, lines, visit, R.sanitize({"added": [{"id": "a1", "section": "O", "text": text}]}, lines))
            return verdict_of(res, "h1")
        self.assertEqual(verdict("Osteopathic: T10-L1 right paraspinal TTC, tenderness, hypertonicity; T11 RR."), "fixed")
        self.assertEqual(verdict("T11 rotated right with tissue texture change."), "fixed")
        self.assertEqual(verdict("C3 paraspinal tissue texture change on the right."), "caught")
        self.assertEqual(verdict("T11 tenderness on the left."), "caught")
        self.assertEqual(verdict("Osteopathic exam done."), "missed")


class FalseAlarmAndUnsupportedTests(unittest.TestCase):
    def setUp(self):
        self.visit, self.lines, self.key = scribbi.build("renal-flank-pain", "base", "coached", 7)
        planted = {e["chip"] for e in self.key["errors"] if e.get("chip")}
        for e in self.key["errors"]:
            planted.update(e["check"].get("chips") or [])
        self.accurate = [ch for ln in self.lines for ch in ln["chips"] if ch["id"] not in planted]

    def test_removing_a_correct_line_is_a_false_alarm(self):
        ch = self.accurate[0]
        res = R.evaluate(self.key, self.lines, self.visit, R.sanitize({"chips": {ch["id"]: {"status": "removed"}}}, self.lines))
        self.assertEqual([fa["chip"] for fa in res["false_alarms"]], [ch["id"]])

    def test_changing_a_correct_value_is_a_false_alarm_but_rewording_is_not(self):
        vital = next(ch for ch in self.accurate if ch["text"].startswith("P "))
        changed = R.evaluate(self.key, self.lines, self.visit,
                             R.sanitize({"chips": {vital["id"]: {"status": "edited", "text": "P 74 bpm"}}}, self.lines))
        self.assertEqual(len(changed["false_alarms"]), 1)
        reworded = R.evaluate(self.key, self.lines, self.visit,
                              R.sanitize({"chips": {vital["id"]: {"status": "edited", "text": "Pulse 104 bpm"}}}, self.lines))
        self.assertEqual(reworded["false_alarms"], [])

    def test_documenting_an_unexamined_region_is_unsupported(self):
        examined = V.examined_regions(self.visit)
        self.assertNotIn("Neurologic", examined)
        res = R.evaluate(self.key, self.lines, self.visit, R.sanitize(
            {"added": [{"id": "a1", "section": "O", "text": "Neuro: CN II-XII intact, strength 5/5 throughout."}]}, self.lines))
        self.assertEqual(len(res["unsupported"]), 1)
        self.assertFalse(res["safe"])
        ok = R.evaluate(self.key, self.lines, self.visit, R.sanitize(
            {"added": [{"id": "a1", "section": "O", "text": "Lungs clear to auscultation bilaterally."}]}, self.lines))
        self.assertEqual(ok["unsupported"], [])

    def test_history_topic_never_discussed_is_unsupported(self):
        said = self.key["_said"]
        topic = next(t for t in C.FABRICATED_HISTORY if not any(re.search(p, said) for p in t["detect"]))
        res = R.evaluate(self.key, self.lines, self.visit, R.sanitize(
            {"added": [{"id": "a1", "section": "S", "text": topic["text"]}]}, self.lines))
        self.assertEqual(len(res["unsupported"]), 1, topic)
        discussed = next(t for t in C.FABRICATED_HISTORY if any(re.search(p, said) for p in t["detect"]))
        res = R.evaluate(self.key, self.lines, self.visit, R.sanitize(
            {"added": [{"id": "a1", "section": "S", "text": discussed["text"]}]}, self.lines))
        self.assertEqual(res["unsupported"], [], discussed)

    def test_sanitize_rejects_unknown_and_oversize_input(self):
        ch = self.accurate[0]
        state = R.sanitize({"chips": {"nope": {"status": "removed"}, ch["id"]: {"status": "edited", "text": "x" * 5000},
                                      self.accurate[1]["id"]: {"status": "edited", "text": "   "},
                                      self.accurate[2]["id"]: {"status": "edited", "text": self.accurate[2]["text"]},
                                      self.accurate[3]["id"]: {"status": "bogus"}},
                            "added": [{"section": "Z", "text": "x"}] + [{"section": "S", "text": "t%d" % i} for i in range(60)]},
                           self.lines)
        self.assertNotIn("nope", state["chips"])
        self.assertEqual(len(state["chips"][ch["id"]]["text"]), R.MAX_TEXT)
        self.assertEqual(state["chips"][self.accurate[1]["id"]]["status"], "removed")
        self.assertEqual(state["chips"][self.accurate[2]["id"]]["status"], "kept")
        self.assertNotIn(self.accurate[3]["id"], state["chips"])
        self.assertLessEqual(len(state["added"]), R.MAX_ADDED)
        self.assertTrue(all(a["section"] in "SOAP" for a in state["added"]))


class TextHelperTests(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(T.level_names(T.levels_in("T10 through L1 on the right")), ["T10", "T11", "T12", "L1"])
        self.assertEqual(T.level_names(T.levels_in("T5-T9 bilaterally")), ["T5", "T6", "T7", "T8", "T9"])
        self.assertEqual(T.levels_in("S1 and S2 present"), set())
        self.assertEqual(T.levels_in("T 101.6 F oral"), set())

    def test_sentences_keep_decimals_and_abbreviations(self):
        self.assertEqual(T.split_sentences("T 101.6 F oral. Seen 2 p.m. today; no fever."),
                         ["T 101.6 F oral.", "Seen 2 p.m. today;", "no fever."])

    def test_sides_ignore_idioms(self):
        self.assertEqual(T.sides_in("all right, right flank pain, will call right away"), ["right"])


class RouteTests(Isolated):
    def test_full_round_lifecycle_in_each_mode(self):
        home = self.route("/api/scribbi")
        self.assertEqual(len(home["library"]), 82)
        self.assertFalse(home["locked"]["blocked"])
        for mode in ("learn", "coached", "solo"):
            rnd = self.route("/api/scribbi/rounds", {"case_id": "renal-flank-pain", "mode": mode})
            self.assertEqual(rnd["status"], "reviewing")
            payload = json.dumps(rnd)
            for secret in ("key_json", "\"origin\"", "\"check\"", "planted", "\"errors\""):
                self.assertNotIn(secret, payload, (mode, secret))
            has_sources = any("sources" in ch for s in rnd["draft"] for ln in s["lines"] for ch in ln["chips"])
            self.assertEqual(has_sources, mode == "learn")
            self.assertEqual("count" in rnd["expect"], mode != "solo")
            self.assertEqual("types" in rnd["expect"], mode == "learn")
            first = rnd["draft"][0]["lines"][0]["chips"][0]["id"]
            state = {"chips": {first: {"status": "removed"}}, "added": []}
            saved = self.route("/api/scribbi/rounds/%s/review" % rnd["id"], {"state": state})
            self.assertTrue(saved["saved"])
            self.assertEqual(("progress" in saved), mode == "learn")
            again = self.route("/api/scribbi/rounds/" + rnd["id"])
            self.assertEqual(again["review"]["chips"][first]["status"], "removed")
            if mode == "learn":
                check = self.route("/api/scribbi/rounds/%s/check" % rnd["id"], {"state": state, "target": {"chip": first}})
                self.assertIn(check["verdict"], ("fixed", "caught", "false_alarm", "still_wrong", "neutral", "unsupported"))
            else:
                self.route("/api/scribbi/rounds/%s/check" % rnd["id"], {"state": state, "target": {"chip": first}}, status=403)
            if mode == "coached":
                for i in range(3):
                    h = self.route("/api/scribbi/rounds/%s/hint" % rnd["id"], {"state": state})
                    self.assertEqual(h["used"], i + 1)
                self.route("/api/scribbi/rounds/%s/hint" % rnd["id"], {"state": state}, status=409)
            else:
                self.route("/api/scribbi/rounds/%s/hint" % rnd["id"], {"state": state}, status=403)
            signed = self.route("/api/scribbi/rounds/%s/sign" % rnd["id"], {"state": state})
            self.assertEqual(signed["status"], "signed")
            result = signed["result"]
            self.assertIn(result["stars"], (0, 1, 2, 3))
            self.assertTrue(0 <= result["score"] <= 100)
            self.assertTrue(result["final_note"])
            if mode == "coached":
                self.assertEqual(result["hints_used"], 3)
            # A signed note is frozen: later autosaves and signs change nothing.
            late = self.route("/api/scribbi/rounds/%s/review" % rnd["id"], {"state": {"chips": {}, "added": []}})
            self.assertFalse(late["saved"])
            resigned = self.route("/api/scribbi/rounds/%s/sign" % rnd["id"], {"state": {"chips": {}, "added": []}})
            self.assertEqual(resigned["result"]["score"], result["score"])
            self.assertEqual(resigned["review"]["chips"][first]["status"], "removed")
        stats = self.route("/api/scribbi")["stats"]
        self.assertEqual(stats["rounds"], 3)

    def test_errors_and_validation(self):
        self.route("/api/scribbi/rounds/doesnotexist", status=404)
        self.route("/api/scribbi/rounds", {"mode": "expert"}, status=400)
        self.route("/api/scribbi/rounds", {"case_id": "no-such-case", "mode": "learn"}, status=400)
        self.route("/api/scribbi/rounds", {"case_id": "renal-flank-pain", "variant_id": "nope", "mode": "learn"}, status=400)
        rnd = self.route("/api/scribbi/rounds", {"random": True, "mode": "coached", "system": cases.index()[0]["system"]})
        self.route("/api/scribbi/rounds/%s/unknown" % rnd["id"], {}, status=404)
        self.assertEqual(self.route("/api/scribbi/rounds/%s/delete" % rnd["id"], {})["deleted"], True)
        self.route("/api/scribbi/rounds/" + rnd["id"], status=404)

    def test_timed_round_signs_itself_when_time_runs_out(self):
        clock = [db.now_ms()]
        with patch.object(db, "now_ms", lambda: clock[0]):
            rnd = self.route("/api/scribbi/rounds", {"case_id": "renal-flank-pain", "mode": "solo", "timed": True})
            self.assertTrue(rnd["timed"])
            self.assertEqual(rnd["deadline"] - rnd["started_at"], C.MODES["solo"]["timer_s"] * 1000)
            clock[0] += C.MODES["solo"]["timer_s"] * 1000 + scribbi.TIME_GRACE_MS + 10
            later = self.route("/api/scribbi/rounds/" + rnd["id"])
            self.assertEqual(later["status"], "signed")
            self.assertTrue(later["result"]["timed_out"])
            self.assertEqual(later["result"]["elapsed_ms"], C.MODES["solo"]["timer_s"] * 1000)
        untimed = self.route("/api/scribbi/rounds", {"case_id": "renal-flank-pain", "mode": "learn", "timed": True})
        self.assertFalse(untimed["timed"])

    def test_locked_while_a_protected_attempt_is_open(self):
        settings = config.load_settings()
        settings.update(learning_mode="independent", simulation_runtime="interactive")
        db.create_session("renal-flank-pain", "independent_extended", "type", False, settings,
                          case=cases.resolve("renal-flank-pain", "base"))
        home = self.route("/api/scribbi")
        self.assertTrue(home["locked"]["blocked"])
        body = self.route("/api/scribbi/rounds", {"case_id": "renal-flank-pain", "mode": "learn"}, status=409)
        self.assertTrue(body["requires_assistance"])

    def test_progress_reset_clears_scribbi_history(self):
        a = self.route("/api/scribbi/rounds", {"case_id": "renal-flank-pain", "mode": "learn"})
        b = self.route("/api/scribbi/rounds", {"case_id": "gi-right-lower-pain", "mode": "learn"})
        preview = self.route("/api/progress/reset-preview", {"scope": "case", "case_id": "renal-flank-pain"})
        self.assertEqual(preview["scribbi_count"], 1)
        reset = self.route("/api/progress/reset", {"scope": "case", "case_id": "renal-flank-pain", "confirm": True})
        self.assertEqual(reset["deleted"]["scribbi_rounds"], 1)
        self.route("/api/scribbi/rounds/" + a["id"], status=404)
        self.route("/api/scribbi/rounds/" + b["id"])
        reset_all = self.route("/api/progress/reset", {"scope": "all", "confirm": True})
        self.assertEqual(reset_all["deleted"]["scribbi_rounds"], 1)

    def test_learn_mode_instant_feedback_on_a_real_mistake(self):
        rnd = self.route("/api/scribbi/rounds", {"case_id": "renal-flank-pain", "mode": "learn"})
        row = scribbi.store.get(rnd["id"])
        key = json.loads(row["key_json"])
        lines = json.loads(row["lines_json"])
        inserted = next((e for e in key["errors"] if e["check"]["kind"] == "inserted"), None)
        if inserted:
            state = {"chips": {inserted["chip"]: {"status": "removed"}}, "added": []}
            verdict = self.route("/api/scribbi/rounds/%s/check" % rnd["id"], {"state": state, "target": {"chip": inserted["chip"]}})
            self.assertEqual(verdict["verdict"], "fixed")
            self.assertEqual(verdict["progress"]["found"], 1)
        accurate = next(ch for ln in lines for ch in ln["chips"]
                        if all(ch["id"] != e.get("chip") and ch["id"] not in (e["check"].get("chips") or []) for e in key["errors"]))
        state = {"chips": {accurate["id"]: {"status": "removed"}}, "added": []}
        verdict = self.route("/api/scribbi/rounds/%s/check" % rnd["id"], {"state": state, "target": {"chip": accurate["id"]}})
        self.assertEqual(verdict["verdict"], "false_alarm")


class AttemptVisitTests(Isolated):
    """Scribbi drafting the student's own submitted encounter."""

    def test_full_encounter_matches_the_demonstration(self):
        sid = replay_attempt("renal-flank-pain")
        rnd = self.route("/api/scribbi/rounds", {"attempt_id": sid, "mode": "coached"})
        self.assertEqual(rnd["source"], "attempt")
        self.assertEqual(rnd["source_attempt_id"], sid)
        self.assertEqual(rnd["visit"]["source"], "attempt")
        row = scribbi.store.get(rnd["id"])
        key, lines, visit = json.loads(row["key_json"]), json.loads(row["lines_json"]), json.loads(row["visit_json"])
        self.assertGreaterEqual(len(key["errors"]), 3)
        self.assertIsNotNone(key["hands_on"])
        perfect = R.evaluate(key, lines, visit, R.sanitize(perfect_state(lines, key), lines))
        self.assertEqual(perfect["score"], 100, perfect["items"])
        turn_ids = {t["id"] for t in visit["turns"]}
        for ln in lines:
            for ch in ln["chips"]:
                for ref in ch.get("evidence", []):
                    self.assertTrue(ref in turn_ids or ref.startswith("chart:"), ref)

    def test_partial_encounter_only_drafts_what_was_obtained(self):
        full = replay_attempt("renal-flank-pain")
        part = replay_attempt("renal-flank-pain", talk_limit=22, exam_limit=5)
        with patch("random.SystemRandom.randrange", return_value=77):
            a = self.route("/api/scribbi/rounds", {"attempt_id": full, "mode": "solo"})
            b = self.route("/api/scribbi/rounds", {"attempt_id": part, "mode": "solo"})
        count = lambda r: sum(len(ln["chips"]) for s in r["draft"] for ln in s["lines"] if s["key"] in "SO")
        self.assertLess(count(b), count(a))
        row = scribbi.store.get(b["id"])
        lines = json.loads(row["lines_json"])
        key = json.loads(row["key_json"])
        planted = {e.get("chip") for e in key["errors"]}
        for e in key["errors"]:
            planted.update(e["check"].get("chips") or [])
        # Every statement Scribbi did not plant is backed by this attempt.
        for ln in lines:
            if ln["section"] not in "SO":
                continue
            for ch in ln["chips"]:
                if ch["id"] not in planted:
                    self.assertTrue(ch.get("evidence"), (ln["label"], ch["text"]))

    def test_attempt_rules(self):
        open_sid = replay_attempt("renal-flank-pain", talk_limit=3, exam_limit=0, submit=False)
        body = self.route("/api/scribbi/rounds", {"attempt_id": open_sid, "mode": "learn"}, status=409)
        self.assertIn("Submit your note first", body["error"])
        self.route("/api/scribbi/rounds", {"attempt_id": "nope", "mode": "learn"}, status=404)
        short = replay_attempt("renal-flank-pain", talk_limit=2, exam_limit=0)
        body = self.route("/api/scribbi/rounds", {"attempt_id": short, "mode": "learn"}, status=409)
        self.assertTrue(body["too_short"])


if __name__ == "__main__":
    unittest.main()
