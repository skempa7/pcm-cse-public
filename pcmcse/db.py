"""SQLite persistence.

Timing is server-authoritative: the phase and its deadline live in the
database, so a refresh, a crash or a new tab all resume the same clock.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid

# The attempt database. PCM_CSE_DB redirects it, which is how a review or a
# demonstration runs against a disposable copy instead of the real attempts.
DB_PATH = os.environ.get("PCM_CSE_DB") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "pcm_cse.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id                TEXT PRIMARY KEY,
    created_at        INTEGER NOT NULL,
    updated_at        INTEGER NOT NULL,
    case_id           TEXT NOT NULL,
    preset            TEXT NOT NULL,
    interaction_mode  TEXT NOT NULL DEFAULT 'type',
    assisted          INTEGER NOT NULL DEFAULT 0,
    phase             TEXT NOT NULL,
    phase_started_at  INTEGER,
    phase_ends_at     INTEGER,
    encounter_used_ms INTEGER NOT NULL DEFAULT 0,
    settings_json     TEXT NOT NULL DEFAULT '{}',
    ledger_json       TEXT NOT NULL DEFAULT '[]',
    patient_state     TEXT NOT NULL DEFAULT '{}',
    note_json         TEXT NOT NULL DEFAULT '{}',
    scratch           TEXT NOT NULL DEFAULT '',
    submit_reason     TEXT,
    submitted_at      INTEGER,
    results_json      TEXT,
    integrity_json    TEXT NOT NULL DEFAULT '{}',
    exam_busy_until   INTEGER NOT NULL DEFAULT 0,
    app_version       TEXT NOT NULL DEFAULT '',
    rubric_version    TEXT NOT NULL DEFAULT '',
    engine_version    TEXT NOT NULL DEFAULT '',
    case_version      TEXT NOT NULL DEFAULT '',
    schema_version    INTEGER NOT NULL DEFAULT 1,
    case_snapshot     TEXT NOT NULL DEFAULT '',
    original_note_json TEXT NOT NULL DEFAULT '',
    parent_session_id TEXT NOT NULL DEFAULT '',
    branch_from_seq   INTEGER NOT NULL DEFAULT 0,
    branch_label      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS revisions (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    created_at   INTEGER NOT NULL,
    kind         TEXT NOT NULL,          -- 'revision' | 'retry'
    note_json    TEXT NOT NULL,
    results_json TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_rev_session ON revisions(session_id);

CREATE TABLE IF NOT EXISTS learning_events (
    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, created_at INTEGER NOT NULL,
    kind TEXT NOT NULL, payload TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_learning_session ON learning_events(session_id);
CREATE TABLE IF NOT EXISTS bridge_requests (
    session_id TEXT NOT NULL, request_id TEXT NOT NULL, response_json TEXT NOT NULL,
    PRIMARY KEY (session_id,request_id)
);
"""


def now_ms():
    return int(time.time() * 1000)


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# Columns added after the first release. CREATE TABLE IF NOT EXISTS will not
# add them to a database that already exists, and the user's real attempts live
# in one, so they are applied by migration instead of by recreating the table.
_MIGRATIONS = [
    ("sessions", "pending_exam_json", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "exam_busy_until", "INTEGER NOT NULL DEFAULT 0"),
    ("sessions", "app_version", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "rubric_version", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "engine_version", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "case_version", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "schema_version", "INTEGER NOT NULL DEFAULT 1"),
    ("sessions", "case_snapshot", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "original_note_json", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "parent_session_id", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "branch_from_seq", "INTEGER NOT NULL DEFAULT 0"),
    ("sessions", "branch_label", "TEXT NOT NULL DEFAULT ''"),
]


def _migrate(conn):
    """Add missing columns in place. Never drops or rewrites a row."""
    added = []
    for table, column, decl in _MIGRATIONS:
        have = {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)}
        if column not in have:
            conn.execute("ALTER TABLE %s ADD COLUMN %s %s"
                         % (table, column, decl))
            added.append("%s.%s" % (table, column))
    return added


def init():
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def new_id():
    return uuid.uuid4().hex[:16]


def save_note_if_open(sid, note_json, now):
    """Write the draft only if the note period is still open, atomically.

    The check has to happen in the database, not against a Session object's
    cached row. A debounced autosave holds a handle captured while the editor
    was alive; by the time it fires the deadline may have passed or the attempt
    may have been submitted, and a handle that trusts its own snapshot will
    happily overwrite a frozen note with whatever the torn-down editor last
    held. Returns True only if a row was actually updated.
    """
    conn = connect()
    try:
        cur = conn.execute(
            "UPDATE sessions SET note_json = ?, updated_at = ? "
            "WHERE id = ? AND phase = 'note' "
            "AND (phase_ends_at IS NULL OR phase_ends_at >= ?)",
            (note_json, now, sid, now))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def create_session(case_id, preset, interaction_mode, assisted, settings,
                   case=None):
    """Open an attempt, stamped with the versions and case content it runs on."""
    from . import version as version_mod
    # Every new attempt freezes its patient, even when an internal caller uses
    # the older shorthand API. Empty snapshots are reserved for legacy rows.
    if case is None:
        from . import cases
        case = cases.resolve(case_id)
    sid = new_id()
    ts = now_ms()
    stamp = version_mod.stamp()
    cver = version_mod.case_version(case) if case else ""
    snapshot = json.dumps(case, sort_keys=True) if case else ""
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO sessions (id, created_at, updated_at, case_id, preset, "
            "interaction_mode, assisted, phase, settings_json, app_version, "
            "rubric_version, engine_version, case_version, schema_version, "
            "case_snapshot) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, ts, ts, case_id, preset, interaction_mode,
             1 if assisted else 0, "briefing", json.dumps(settings),
             stamp["app"], stamp["rubric"], stamp["engine"], cver,
             stamp["schema"], snapshot))
        conn.commit()
    finally:
        conn.close()
    return sid


def get_session(sid):
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_session(sid, **fields):
    if not fields:
        return
    fields["updated_at"] = now_ms()
    cols = ", ".join("%s=?" % k for k in fields)
    conn = connect()
    try:
        conn.execute("UPDATE sessions SET %s WHERE id=?" % cols,
                     tuple(fields.values()) + (sid,))
        conn.commit()
    finally:
        conn.close()


def list_sessions(limit=40):
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, created_at, case_id, preset, phase, submitted_at, "
            "results_json IS NOT NULL AS graded, interaction_mode, assisted, settings_json, case_snapshot "
            "FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["graded"] = bool(d["graded"])
            d["assisted"] = bool(d["assisted"])
            settings = json.loads(d.pop("settings_json") or "{}")
            snapshot = json.loads(d.pop("case_snapshot") or "{}")
            d["learning_mode"] = settings.get("learning_mode", "legacy")
            d["patient_name"] = snapshot.get("patient", {}).get("name", "Saved station")
            d["case_title"] = (snapshot.get("title", "") if d["phase"] == "submitted" or d["learning_mode"] != "rehearsal" or d["assisted"] else "Exam rehearsal")
            out.append(d)
        return out
    finally:
        conn.close()


def create_branch(parent_row, ledger_json, patient_state, settings, case,
                  from_seq, label, remaining_ms, elapsed_ms=0):
    """Open a practice branch that resumes a finished attempt at one moment.

    The parent attempt is never opened for writing. A branch is a NEW record
    that names the attempt and the moment it grew from, so the original timed
    submission stays exactly what it was and a retry can never be mistaken for
    it.
    """
    from . import version as version_mod
    sid = new_id()
    ts = now_ms()
    stamp = version_mod.stamp()
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO sessions (id, created_at, updated_at, case_id, preset, "
            "interaction_mode, assisted, phase, phase_started_at, phase_ends_at, "
            "settings_json, ledger_json, patient_state, app_version, "
            "rubric_version, engine_version, case_version, schema_version, "
            "case_snapshot, parent_session_id, branch_from_seq, branch_label) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, ts, ts, parent_row["case_id"], parent_row["preset"],
             parent_row["interaction_mode"], 1,
             "encounter", ts - max(0, int(elapsed_ms)),
             None if settings.get('learning_mode') == 'guided' else ts + max(0, int(remaining_ms)),
             json.dumps(settings), ledger_json, json.dumps(patient_state),
             stamp["app"], stamp["rubric"], stamp["engine"],
             version_mod.case_version(case), stamp["schema"],
             json.dumps(case, sort_keys=True), parent_row["id"], int(from_seq),
             label))
        conn.commit()
    finally:
        conn.close()
    return sid


def list_branches(session_id):
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, created_at, branch_from_seq, branch_label, phase "
            "FROM sessions WHERE parent_session_id = ? ORDER BY created_at",
            (session_id,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def add_revision(session_id, kind, note_json, results_json):
    rid = new_id()
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO revisions (id, session_id, created_at, kind, note_json, "
            "results_json) VALUES (?,?,?,?,?,?)",
            (rid, session_id, now_ms(), kind, json.dumps(note_json),
             json.dumps(results_json) if results_json is not None else None))
        conn.commit()
    finally:
        conn.close()
    return rid


def list_revisions(session_id):
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, created_at, kind, note_json, results_json FROM revisions "
            "WHERE session_id=? ORDER BY created_at ASC", (session_id,)).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r["id"], "created_at": r["created_at"], "kind": r["kind"],
                "note": json.loads(r["note_json"]),
                "results": json.loads(r["results_json"]) if r["results_json"] else None,
            })
        return out
    finally:
        conn.close()


def delete_session(sid):
    conn = connect()
    try:
        conn.execute("DELETE FROM learning_events WHERE session_id=?", (sid,))
        conn.execute("DELETE FROM bridge_requests WHERE session_id=?", (sid,))
        conn.execute("DELETE FROM revisions WHERE session_id=?", (sid,))
        conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
        conn.commit()
    finally:
        conn.close()
