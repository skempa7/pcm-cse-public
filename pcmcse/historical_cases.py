"""Compatibility case source for attempts predating per-attempt snapshots.

The archive is the exact 24-case library present in the user's preview before
the young-adult cohort revision. Reading it never modifies a saved attempt.
New attempts always have a snapshot and cannot enter this compatibility path.
"""

import copy
import json
from pathlib import Path

_archive = None


def for_attempt(row):
    if row.get("case_snapshot"):
        return json.loads(row["case_snapshot"])
    global _archive
    if _archive is None:
        path = Path(__file__).with_name("archive") / "pre-young-adult-cohort.json"
        _archive = json.loads(path.read_text(encoding="utf-8"))
    case = _archive.get(row["case_id"])
    if case is None:
        raise ValueError("This historical attempt has no saved case definition. "
                         "Its original data has been preserved; restore its original case source.")
    return copy.deepcopy(case)
