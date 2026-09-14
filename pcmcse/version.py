"""Versions stamped onto every attempt.

An attempt is only interpretable against the content that produced it. When a
case is rewritten or the grading table changes, an old score stops meaning what
it meant, so each attempt records the versions it ran under and a snapshot of
its own case. Nothing regrades an old attempt under new content: a regrade is a
new record that names both versions.
"""

from __future__ import annotations

import hashlib
import json
import os

# Bumped by hand when behaviour changes in a way that makes scores
# incomparable with earlier attempts.
APP_VERSION = "4.2.0"

# The interpretation of the learner's turns, the examination lifecycle, the
# documentation audit and the interpersonal instruments.
ENGINE_VERSION = "4.2.0"

# The PCM 2026 SOAP note grading table as implemented.
RUBRIC_VERSION = "2026.1"

# The sessions table layout. Raise this when a migration is added.
SCHEMA_VERSION = 3

_HERE = os.path.dirname(os.path.abspath(__file__))


def case_version(case: dict) -> str:
    """A short content hash of one case.

    Two attempts on the same case id but different content are distinguishable,
    which is what makes "do not silently regrade old attempts" enforceable.
    """
    blob = json.dumps(case, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def case_library_version() -> str:
    """A hash over every case file, for the build artifact."""
    d = os.path.join(_HERE, "cases")
    h = hashlib.sha256()
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(d, name), "rb") as fh:
            h.update(name.encode("utf-8"))
            h.update(fh.read())
    return h.hexdigest()[:16]


def stamp() -> dict:
    return {
        "app": APP_VERSION,
        "engine": ENGINE_VERSION,
        "rubric": RUBRIC_VERSION,
        "schema": SCHEMA_VERSION,
        "case_library": case_library_version(),
    }


def banner() -> str:
    s = stamp()
    return "PCM CSE %s (engine %s, rubric %s, cases %s)" % (
        s["app"], s["engine"], s["rubric"], s["case_library"])
