"""Substitute authored patient-speech rewrites into case files, safely.

A fact's text is mirrored in several places -- `value`, every `sp_says` entry,
`concepts[*].value`, `delivery_contract.versions[*].text` plus that version's
own `concepts[*].value`, the checklist row, the model note, and each cohort
variant's patch. They must move together: the delivery contract credits a fact
only when its APPROVED text is what was actually spoken, so changing `sp_says`
alone would silently downgrade the evidence to an unverified legacy statement.

`concept_lexicon` is the one mirror that must NOT simply move. Its surfaces are
matched against the text the STUDENT writes (grader.py, feedback.py, audit.py),
and matching is conjunctive -- every content word of a surface must appear. A
conversational sentence is therefore almost unmatchable in a note, so replacing
the authored surface outright deletes a credit path. Where a concept has only
one surface ("no hereditary neuropathy known.") that is its ONLY credit path.
So inside a lexicon the new wording is ADDED ahead of the old one and the old
one is kept, which preserves the authoring convention (surface[0] mirrors the
fact text) without ever narrowing what a student may write.

Edits are made on the raw JSON so the files keep their formatting, then the
result is re-parsed to prove it is still valid, that no mirror kept the old
wording, and that no lexicon surface was lost.

    python3 tools/apply_fact_rewrites.py rewrites.json [--dry-run]

rewrites.json: [{"caseId": "...", "rewrites": [{"factId": ..., "oldText": ...,
                 "newText": ...}]}]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "pcmcse/cases"
KEY = '"concept_lexicon"'


def case_path(case_id):
    return CASES / (case_id.replace("-", "_") + ".json")


def lexicon_spans(raw):
    """Character spans of every concept_lexicon object, at any depth.

    Variants carry their own patched lexicons, so this cannot look only at the
    top level.
    """
    spans, at = [], raw.find(KEY)
    while at >= 0:
        start = raw.find("{", at + len(KEY))
        if start < 0:
            break
        depth, i, in_str, esc = 0, start, False, False
        while i < len(raw):
            ch = raw[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        spans.append((start, i + 1))
        at = raw.find(KEY, i + 1)
    return spans


def _split(raw):
    """Raw text as alternating (segment, is_lexicon) pieces."""
    pieces, prev = [], 0
    for start, end in lexicon_spans(raw):
        pieces.append((raw[prev:start], False))
        pieces.append((raw[start:end], True))
        prev = end
    pieces.append((raw[prev:], False))
    return pieces


def _surfaces(doc):
    """Every lexicon surface in the document, keyed by path, for the audit."""
    out = {}

    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "concept_lexicon" and isinstance(v, dict):
                    for cid, forms in v.items():
                        if isinstance(forms, list):
                            out["%s/%s" % (path, cid)] = [
                                f for f in forms if isinstance(f, str)]
                else:
                    walk(v, "%s/%s" % (path, k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, "%s/%d" % (path, i))

    walk(doc)
    return out


def apply_case(entry, dry_run=False):
    path = case_path(entry["caseId"])
    if not path.exists():
        return {"case": entry["caseId"], "error": "case file not found: %s" % path.name}
    raw = original = path.read_text()
    before = _surfaces(json.loads(raw))
    applied, missing = [], []

    for rewrite in entry.get("rewrites", []):
        old, new = rewrite.get("oldText", ""), rewrite.get("newText", "")
        if not old or not new:
            missing.append({"fact": rewrite.get("factId"), "why": "empty text"})
            continue
        # Compare in JSON-escaped form: that is how the text sits on disk.
        old_j, new_j = json.dumps(old)[1:-1], json.dumps(new)[1:-1]
        if old_j == new_j:
            missing.append({"fact": rewrite.get("factId"), "why": "text unchanged"})
            continue
        pieces, hits, kept = [], 0, 0
        for text, is_lex in _split(raw):
            if is_lex:
                # Keep the authored surface; add the spoken wording ahead of it.
                quoted = '"%s"' % old_j
                kept += text.count(quoted)
                text = text.replace(quoted, '"%s", "%s"' % (new_j, old_j))
            else:
                hits += text.count(old_j)
                text = text.replace(old_j, new_j)
            pieces.append(text)
        if not hits and not kept:
            missing.append({"fact": rewrite.get("factId"),
                            "why": "current text not found verbatim", "text": old[:70]})
            continue
        raw = "".join(pieces)
        applied.append({"fact": rewrite.get("factId"), "mirrors": hits,
                        "surfaces_kept": kept})

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"case": entry["caseId"], "error": "rewrite produced invalid JSON: %s" % exc}

    # Nothing outside a lexicon may keep the old wording.
    body = "".join(t for t, is_lex in _split(raw) if not is_lex)
    stale = [r.get("factId") for r in entry.get("rewrites", [])
             if r.get("oldText") and json.dumps(r["oldText"])[1:-1] in body]
    if stale:
        return {"case": entry["caseId"], "error": "old text still present for %s" % stale}

    # No student-facing surface may be lost.
    after = _surfaces(doc)
    lost = [(k, s) for k, forms in before.items()
            for s in forms if s not in after.get(k, [])]
    if lost:
        return {"case": entry["caseId"],
                "error": "lexicon surfaces lost: %s" % lost[:3]}

    if not dry_run and raw != original:
        path.write_text(raw)
    return {"case": entry["caseId"], "applied": applied, "skipped": missing,
            "changed": raw != original}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        print(__doc__)
        return 2
    entries = json.loads(Path(args[0]).read_text())
    results = [apply_case(e, dry) for e in entries]
    errors = [r for r in results if r.get("error")]
    skipped = [s for r in results for s in r.get("skipped", [])]
    total = sum(len(r.get("applied", [])) for r in results)
    mirrors = sum(a["mirrors"] for r in results for a in r.get("applied", []))
    kept = sum(a["surfaces_kept"] for r in results for a in r.get("applied", []))
    print("%s %d facts across %d cases (%d mirrored occurrences, "
          "%d lexicon surfaces preserved)"
          % ("Would rewrite" if dry else "Rewrote", total, len(results), mirrors, kept))
    for r in errors:
        print("  ERROR %s: %s" % (r["case"], r["error"]))
    for s in skipped:
        print("  SKIP  %s: %s %s" % (s.get("fact"), s.get("why"), s.get("text", "")))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
