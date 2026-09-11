"""Is every authored thing in the library actually reachable by a learner?

A fact nobody can elicit is invisible: the student cannot obtain it, cannot
document it, and loses the credit it carries -- and nothing fails, because the
data is present and well formed. That is how half the library came to refuse
its own Setting row while every test passed. So this asks the questions the
schema cannot: ask each fact's OWN authored trigger through the real patient
engine and require the fact back; then check the authored answer keys point at
facts that exist.

    python3 tools/audit_case_library.py [--variants] [--case ID]

Exits non-zero when something authored cannot be reached.
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pcmcse import cases  # noqa: E402
from pcmcse.patient import PatientEngine  # noqa: E402


def _ask(case, question):
    engine = PatientEngine(case)
    reply, meta = engine.respond(question, {"opened": True, "open_budget": 0})
    return reply, (meta.get("facts_released") or [])


def _questions_for(fact):
    """The learner wordings this fact claims to answer."""
    triggers = fact.get("triggers") or {}
    out = []
    for key in ("any", "all"):
        for phrase in triggers.get(key) or []:
            phrase = (phrase or "").strip()
            if not phrase:
                continue
            # An authored full question is asked as written; a keyword is asked
            # the way a student would put it around that keyword.
            out.append(phrase if phrase.endswith("?")
                       else ("Can you tell me about %s?" % phrase
                             if len(phrase.split()) > 2 else "Any %s?" % phrase))
    return out


def audit(case):
    unreachable, weak = [], []
    for fact in case.get("facts") or []:
        questions = _questions_for(fact)
        if not questions:
            weak.append((fact["id"], "no authored trigger at all"))
            continue
        reached = False
        for question in questions:
            try:
                _reply, released = _ask(case, question)
            except Exception as exc:                      # noqa: BLE001
                weak.append((fact["id"], "engine raised %s" % type(exc).__name__))
                continue
            if fact["id"] in released:
                reached = True
                break
        if not reached:
            unreachable.append((fact["id"], fact.get("category"), questions[0][:62]))

    # A checklist row nothing can ever credit is a point the student cannot
    # earn however well they work. History rows are credited by a fact naming
    # the row; physical rows by a refusal, a courtesy, or a maneuver -- and a
    # maneuver row that demands a component its maneuver does not offer is
    # unearnable no matter how completely the examination is performed.
    from pcmcse import physexam
    catalog = {m["id"]: m for m in physexam.CATALOG}
    courtesies = {c["id"] for c in physexam.COURTESY}
    named = {f.get("checklist") for f in (case.get("facts") or []) if f.get("checklist")}

    checklist = case.get("checklist") or {}
    groups = checklist.items() if isinstance(checklist, dict) else [("", checklist)]
    dangling = []
    for group, rows in groups:
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            rid, text = row.get("id"), (row.get("text") or "")[:50]
            if group == "history" or rid in named:
                if rid not in named:
                    dangling.append((rid, text, "no fact names this row"))
                continue
            if row.get("refusal"):
                continue
            wanted = list(row.get("courtesy_all") or ([row["courtesy"]] if row.get("courtesy") else []))
            if wanted:
                unknown = [c for c in wanted if c not in courtesies]
                if unknown:
                    dangling.append((rid, text, "unknown courtesy %s" % unknown))
                continue
            mid = row.get("maneuver")
            if not mid:
                dangling.append((rid, text, "no maneuver, courtesy or refusal"))
                continue
            man = catalog.get(mid)
            if not man:
                dangling.append((rid, text, "maneuver %r is not in the catalog" % mid))
                continue
            offered = {c["id"] if isinstance(c, dict) else c for c in (man.get("components") or [])}
            missing = [c for c in (row.get("components") or []) if c not in offered]
            if missing:
                dangling.append((rid, text, "%s cannot supply component(s) %s" % (mid, missing)))
    return unreachable, weak, dangling


def main():
    want_variants = "--variants" in sys.argv
    only = None
    if "--case" in sys.argv:
        only = sys.argv[sys.argv.index("--case") + 1]

    rows, totals = [], defaultdict(int)
    for cid, base in sorted(cases.all_cases().items()):
        if only and cid != only:
            continue
        vids = ["base"] + ([v["id"] for v in base.get("variants") or []]
                           if want_variants else [])
        for vid in vids:
            case = cases.resolve(cid, vid)
            unreachable, weak, dangling = audit(case)
            totals["facts"] += len(case.get("facts") or [])
            totals["unreachable"] += len(unreachable)
            totals["weak"] += len(weak)
            totals["dangling"] += len(dangling)
            if unreachable or weak or dangling:
                rows.append((cid, vid, unreachable, weak, dangling))

    for cid, vid, unreachable, weak, dangling in rows:
        print("\n%s (%s)" % (cid, vid))
        for fid, category, question in unreachable:
            print("  UNREACHABLE  %-24s [%s] asked: %s" % (fid, category, question))
        for fid, why in weak:
            print("  WEAK         %-24s %s" % (fid, why))
        for rid, text, why in dangling:
            print("  NO CREDIT PATH  %-22s %-52s %s" % (rid, text, why))

    print("\n%d facts checked — %d unreachable, %d weak, %d checklist rows no fact can credit."
          % (totals["facts"], totals["unreachable"], totals["weak"], totals["dangling"]))
    return 1 if (totals["unreachable"] or totals["dangling"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
