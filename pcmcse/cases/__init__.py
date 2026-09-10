"""Case library loader."""

from __future__ import annotations

import json
import os
import copy

_DIR = os.path.dirname(__file__)
_cache = {}


def _load_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def all_cases():
    if not _cache:
        for name in sorted(os.listdir(_DIR)):
            if not name.endswith(".json"):
                continue
            case = _load_file(os.path.join(_DIR, name))
            _cache[case["id"]] = case
    return _cache


def get(case_id):
    return all_cases().get(case_id)


def resolve(case_id, variant_id=None):
    """Resolve a reviewed variation once, then freeze it in the attempt."""
    base = get(case_id)
    if base is None:
        raise ValueError("Unknown presentation")
    case = copy.deepcopy(base)
    variants = case.pop("variants", [])
    if variant_id and variant_id != "base":
        variant = next((v for v in variants if v["id"] == variant_id), None)
        if variant is None:
            raise ValueError("Unknown variation")
        def merge(target, patch):
            for key, value in patch.items():
                if isinstance(value, dict) and isinstance(target.get(key), dict):
                    merge(target[key], value)
                else:
                    target[key] = copy.deepcopy(value)
        merge(case, variant["patch"])
    case["id"] = case_id
    case["variant_id"] = variant_id or "base"
    return case


def index(reveal_titles=True):
    """Case list for the picker.

    During exam rehearsal the title is a giveaway, so it is withheld and only
    the neutral station label is shown.
    """
    out = []
    for case in all_cases().values():
        out.append({
            "id": case["id"],
            "system": case["system"],
            "station_label": case.get("hidden_label", "Station"),
            "level": case.get("level", "M2"),
            "title": case["title"] if reveal_titles else case.get("hidden_label", "Station"),
            "blurb": case.get("blurb", "") if reveal_titles else "",
            "revealed": reveal_titles,
            "complaint_family": case.get("complaint_family", case["system"]),
            "difficulty": case.get("difficulty", "intermediate"),
            "skills": case.get("teaching", {}).get("skills", []),
            "presentation_id": case.get("presentation_id", case["id"]),
            "review_status": case.get("review_status", "automated review; no clinician approval"),
            "variants": [{"id": v["id"], "label": v.get("label", v["id"])}
                         for v in case.get("variants", [])] if reveal_titles else [],
        })
    out.sort(key=lambda c: (c["system"], c["id"]))
    return out


def systems():
    return sorted({c["system"] for c in all_cases().values()})
