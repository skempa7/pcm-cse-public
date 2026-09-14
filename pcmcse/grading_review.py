"""Expose recognition limits separately from verified documentation defects.

This report never changes points, student writing, or encounter evidence.
It is a review aid, not an estimate of the points an unfamiliar phrase deserves.
"""

import re


def describe(parsed, audit, rubric):
    unresolved = []
    for claim in audit.get("claims", []):
        if claim.get("verdict") != "not_evaluated":
            continue
        # An explicit declaration that no history/exam was obtained is a
        # limitation, not an attempted clinical claim the reader failed to map.
        # This does not award the missing criterion or hide any attached claim.
        if re.fullmatch(r"not (?:obtained|assessed|completed|examined|asked|recorded|documented)[.!]?", claim["text"].strip(), re.I):
            continue
        unresolved.append({
            "section": claim["section"], "header": claim.get("header"),
            "text": claim["text"],
            "reason": claim.get("explanation") or "This wording could not be verified automatically.",
            "evidence": claim.get("evidence", []),
        })
    limited_rows = [{"id": row["id"], "label": row["label"],
                     "text": row.get("passage", ""), "reason": row["why"]}
                    for row in rubric.get("rows", []) if row.get("recognition_limited")]
    return {
        "status": "needs_review" if unresolved or limited_rows else "automatic_review",
        "unverified_passages": unresolved,
        "unresolved_rows": limited_rows,
        "note": ("Some wording could not be verified automatically. Check the passages below before interpreting the score; unrecognized wording is not proof of an incorrect statement."
                 if unresolved or limited_rows else
                 "Automatic practice review against the course rubric and the recorded encounter. It does not establish a faculty grade."),
    }
