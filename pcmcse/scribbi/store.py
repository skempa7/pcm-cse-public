"""Scribbi rounds in the same SQLite file as the attempts.

The table is created by db.init() (see db.SCHEMA) and cleared by the progress
reset, so Scribbi history follows the same rules as every other saved work.
"""

from __future__ import annotations

import json

from .. import db

_COLUMNS = ("id", "created_at", "updated_at", "case_id", "variant_id", "source", "source_attempt_id",
            "mode", "timed", "time_limit_s", "seed", "generator_version", "engine_version", "status",
            "visit_json", "lines_json", "key_json", "review_json", "result_json", "started_at",
            "signed_at", "elapsed_ms", "hints_json", "score", "stars")


def insert(row: dict):
    cols = [c for c in _COLUMNS if c in row]
    conn = db.connect()
    try:
        conn.execute("INSERT INTO scribbi_rounds (%s) VALUES (%s)" % (",".join(cols), ",".join("?" * len(cols))),
                     tuple(row[c] for c in cols))
        conn.commit()
    finally:
        conn.close()


def get(round_id: str):
    conn = db.connect()
    try:
        r = conn.execute("SELECT * FROM scribbi_rounds WHERE id = ?", (round_id,)).fetchone()
    finally:
        conn.close()
    return dict(r) if r else None


def update(round_id: str, *, only_if_reviewing=False, **fields):
    """Returns True when a row changed. `only_if_reviewing` makes a write to a
    signed round a no-op, so a late autosave can never alter a signed note."""
    if not fields:
        return False
    fields["updated_at"] = db.now_ms()
    sets = ", ".join("%s = ?" % k for k in fields)
    sql = "UPDATE scribbi_rounds SET " + sets + " WHERE id = ?"
    params = list(fields.values()) + [round_id]
    if only_if_reviewing:
        sql += " AND status = 'reviewing'"
    conn = db.connect()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete(round_id: str) -> bool:
    conn = db.connect()
    try:
        cur = conn.execute("DELETE FROM scribbi_rounds WHERE id = ?", (round_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def recent(limit=30):
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT id, created_at, updated_at, case_id, variant_id, source, source_attempt_id, mode, timed, "
            "status, score, stars, signed_at, elapsed_ms FROM scribbi_rounds ORDER BY created_at DESC LIMIT ?",
            (int(limit),)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def signed_results():
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT id, created_at, signed_at, case_id, variant_id, mode, timed, score, stars, result_json "
            "FROM scribbi_rounds WHERE status = 'signed' ORDER BY signed_at ASC").fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["result"] = json.loads(d.pop("result_json") or "{}")
        except ValueError:
            d["result"] = {}
        out.append(d)
    return out
