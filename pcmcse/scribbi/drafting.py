"""Turn a demonstrated visit's example note into reviewable lines.

A line is one labeled row of the note ("HPI:", "Lungs:", "1."). Each line
holds chips: sentence-sized statements the student can keep, edit, or remove.
Every chip remembers which moments of the visit support it, taken from the
note links the teaching library already verified against the ledger.
"""

from __future__ import annotations

import re

from . import text as T

SECTION_TITLES = {"S": "Subjective", "O": "Objective", "A": "Assessment", "P": "Plan"}

# Objective labels -> examination regions (physexam.REGION_ORDER names).
LABEL_REGION = {
    "General": "General", "HEENT": "HEENT", "Neck": "Neck", "Heart": "Heart",
    "Lungs": "Lungs", "Chest wall": "Musculoskeletal", "Abdomen": "Abdomen",
    "GU": "Abdomen", "Skin": "Skin", "Extremities": "Extremities",
    "Musculoskeletal": "Musculoskeletal", "Neurologic": "Neurologic",
    "Lymphatic": "Neck", "Osteopathic": "Osteopathic",
}


class Builder:
    def __init__(self):
        self.lines = []
        self._line_n = 0
        self._chip_n = 0

    def line(self, section, label, kind):
        self._line_n += 1
        ln = {"id": "tl%d" % self._line_n, "section": section, "label": label or "",
              "kind": kind, "chips": []}
        self.lines.append(ln)
        return ln

    def chip(self, ln, text, evidence=None, **extra):
        self._chip_n += 1
        ch = {"id": "tc%d" % self._chip_n, "text": text, "evidence": list(evidence or []),
              "origin": "note"}
        ch.update(extra)
        ln["chips"].append(ch)
        return ch

    def new_chip_id(self):
        self._chip_n += 1
        return "tc%d" % self._chip_n

    def new_line_id(self):
        self._line_n += 1
        return "tl%d" % self._line_n


def _links_by_section(walkthrough):
    """Only links the teaching audit verified. 'not_evaluated' links are
    related quotations, not proof ("T10" was once linked to the temperature)."""
    out = {"S": [], "O": []}
    for link in walkthrough.get("note_links", []):
        sec = link.get("section")
        if (sec in out and link.get("statement")
                and link.get("audit_verdict") in ("supported", "supported_supplied")):
            out[sec].append((T.norm(link["statement"]), link.get("event_ids", [])))
    return out


def _region_fallback(visit_turns, region):
    return [t["id"] for t in visit_turns if t.get("kind") == "exam" and t.get("region") == region]


def _evidence_for(chip_text, links, event_to_ref, events_out=None):
    norm_chip = T.norm(chip_text)
    refs = []
    if not norm_chip:
        return refs
    chip_tokens = set(norm_chip.split())
    for link_norm, event_ids in links:
        if not link_norm:
            continue
        hit = link_norm in norm_chip or (len(norm_chip) > 12 and norm_chip in link_norm)
        if not hit and len(link_norm.split()) >= 3:
            ltoks = set(link_norm.split())
            hit = len(ltoks & chip_tokens) >= 0.75 * len(ltoks)
        if not hit:
            continue
        for eid in event_ids:
            if events_out is not None and eid not in events_out:
                events_out.append(eid)
            ref = event_to_ref.get(eid)
            if ref and ref not in refs:
                refs.append(ref)
    return refs


def _kind_for(section, label):
    if section == "S":
        return "history"
    if section == "O":
        if label == "Vitals":
            return "vital"
        if label == "Results":
            return "result"
        if label == "Osteopathic":
            return "structural"
        return "exam"
    return "assessment" if section == "A" else "plan"


def _labeled_pieces(raw_text, table):
    """[(label, body)] for every labeled row, splitting inline labels too."""
    rows = []
    for raw in (raw_text or "").split("\n"):
        raw = raw.strip()
        if not raw:
            continue
        if raw.lower().startswith("supplied "):
            rows.append(("Results", raw[len("supplied "):].strip()))
            continue
        label, body = T.split_label(raw, table)
        # "PMH: No chronic conditions. PSH: Wisdom teeth at 18; no admission."
        pieces = T.split_sentences(body)
        current_label, current = label, []
        for piece in pieces:
            inline_label, rest = T.split_label(piece, table)
            if inline_label and current:
                rows.append((current_label, " ".join(current)))
                current_label, current = inline_label, [rest] if rest else []
            elif inline_label and not current:
                current_label, current = inline_label, [rest] if rest else []
            else:
                current.append(piece)
        if current:
            rows.append((current_label, " ".join(current)))
    # Merge rows that share a label (the examples repeat "Abdomen:" once per
    # examination step, sometimes with another region in between). The merged
    # row keeps the position of its first occurrence.
    merged, index = [], {}
    for label, body in rows:
        if label and label in index:
            i = index[label]
            merged[i] = (label, merged[i][1] + " " + body)
        else:
            if label:
                index[label] = len(merged)
            merged.append((label, body))
    return merged


def true_note(walkthrough, event_to_ref, visit_turns=()):
    """A Builder holding the example note as reviewable lines and chips."""
    b = Builder()
    note = walkthrough.get("note") or {}
    links = _links_by_section(walkthrough)
    for section, table in (("S", T.SUBJECTIVE_LABELS), ("O", T.OBJECTIVE_LABELS)):
        for label, body in _labeled_pieces(note.get(section, ""), table):
            ln = b.line(section, label, _kind_for(section, label))
            if label in ("Vitals",):
                pieces = [p.strip() for p in re.split(r",\s+(?=[A-Z])", body) if p.strip()]
            elif label == "Results":
                pieces = [body.strip()]
            else:
                pieces = T.split_sentences(body)
            prev_quoted = False
            for piece in pieces:
                shown = piece
                if section == "S" and T.has_first_person(piece):
                    shown = T.as_patient_quote(piece, label, continued=prev_quoted)
                prev_quoted = shown != piece
                events = []
                ev = _evidence_for(piece, links[section], event_to_ref, events)
                if label == "Vitals":
                    ev = ["chart:vitals"]
                elif section == "O":
                    ev = [r for r in ev if r != "chart:vitals"]
                    if not ev and label in LABEL_REGION:
                        ev = _region_fallback(visit_turns, LABEL_REGION[label])
                b.chip(ln, shown, ev, quoted=shown != piece, events=events)
            if not ln["chips"]:
                b.lines.remove(ln)
    for section in ("A", "P"):
        for i, item in enumerate(note.get(section) or [], start=1):
            m = re.match(r"^\s*(\d+)\s*[.)]\s*(.*)$", item or "", re.S)
            number, body = (m.group(1), m.group(2)) if m else (str(i), item or "")
            ln = b.line(section, number, _kind_for(section, number))
            pieces = [body.strip()] if section == "A" else T.split_sentences(body)
            for piece in pieces:
                if piece.strip():
                    b.chip(ln, piece.strip(), [])
            if not ln["chips"]:
                b.lines.remove(ln)
    return b


def region_of(line):
    return LABEL_REGION.get(line.get("label", ""), "")


def renumber(lines, errors):
    """Stable, display-ordered ids so nothing about an id hints at a planted line."""
    order = {"S": 0, "O": 1, "A": 2, "P": 3}
    lines.sort(key=lambda ln: order.get(ln["section"], 9))
    line_map, chip_map = {}, {}
    n_line = n_chip = 0
    for ln in lines:
        n_line += 1
        line_map[ln["id"]] = "L%d" % n_line
        ln["id"] = line_map.get(ln["id"])
        for ch in ln["chips"]:
            n_chip += 1
            chip_map[ch["id"]] = "c%d" % n_chip
            ch["id"] = chip_map[ch["id"]]
    for err in errors:
        if err.get("chip"):
            err["chip"] = chip_map.get(err["chip"], err["chip"])
        if err.get("line"):
            err["line"] = line_map.get(err["line"], err["line"])
        if err.get("anchor_line"):
            err["anchor_line"] = line_map.get(err["anchor_line"], err["anchor_line"])
    return line_map, chip_map


def client_sections(lines, *, with_sources=False):
    """What the page renders: sections, labeled lines, chips. No answers."""
    out = []
    for key in ("S", "O", "A", "P"):
        rows = []
        for ln in lines:
            if ln["section"] != key:
                continue
            rows.append({
                "id": ln["id"], "label": ln["label"], "kind": ln["kind"],
                "chips": [dict({"id": ch["id"], "text": ch["text"]},
                               **({"sources": ch.get("evidence", [])} if with_sources else {}))
                          for ch in ln["chips"]],
            })
        out.append({"key": key, "title": SECTION_TITLES[key], "lines": rows})
    return out


def all_chips(lines):
    lines = getattr(lines, "lines", lines)
    for ln in list(lines):
        for ch in ln["chips"]:
            yield ln, ch
