"""Plant Scribbi's mistakes into a true note.

Each generator looks at the note, the visit and the case and proposes
candidate mistakes that are *verifiable from the visit*: an invented exam only
for a region nobody examined, a flipped finding only where the visit shows
the truth, an allergy conflict only where the allergy was actually obtained.
A candidate is applied by mutating the draft and returns the hidden answer
key entry that the review is graded against.
"""

from __future__ import annotations

import random
import re
from collections import Counter, defaultdict

from .. import nlp, physexam
from . import catalog as C
from . import drafting as D
from . import text as T
from . import visit as V


class Candidate:
    __slots__ = ("type", "touch", "section", "apply", "severity")

    def __init__(self, type_, touch, section, apply, severity=None):
        self.type = type_
        self.touch = set(touch)
        self.section = section
        self.apply = apply
        self.severity = severity or C.ERROR_TYPES[type_]["severity"]


def _lit(s: str) -> str:
    """A normalized, word-bounded literal pattern for `s`."""
    return r"(?<![a-z0-9])" + re.escape(T.norm(s)) + r"(?![a-z0-9])"


RED_FLAGS = [r"fever", r"chill", r"blood", r"bleed", r"hematuria", r"melena", r"black", r"chest pain",
             r"syncope", r"faint", r"weak", r"numb", r"vision", r"weight loss", r"night sweat",
             r"shortness of breath", r"dyspnea", r"vomit", r"headache", r"confus", r"incontinen",
             r"neck stiff", r"tender", r"guarding", r"rebound", r"murphy", r"mcburney", r"psoas",
             r"obturator", r"cva", r"costovertebral"]
_FLIP_EXCLUDE = re.compile(r"\b(known|prior|previous|chronic|history|significant|other|similar|new|further|change|"
                           r"acute distress|recent|admission|admissions|surgeries|surgery|hospital|partner|"
                           r"medications?|allerg|travel|problems?|issues?|complaints?)\b", re.I)


def _lines(b, section=None, label=None):
    return [ln for ln in b.lines if (section is None or ln["section"] == section)
            and (label is None or ln["label"] == label)]


def _first_line(b, section, label):
    found = _lines(b, section, label)
    return found[0] if found else None


def _insert_line(b, section, label, kind, text):
    """A new line placed where a clinician would expect it."""
    ln = {"id": b.new_line_id(), "section": section, "label": label, "kind": kind, "chips": []}
    cid = b.new_chip_id()
    ln["chips"].append({"id": cid, "text": text, "evidence": [], "origin": "planted"})
    if section == "O":
        order = physexam.REGION_ORDER
        rank = {r: i for i, r in enumerate(order)}
        mine = rank.get(D.LABEL_REGION.get(label, label), len(order) - 2)
        idx = None
        for i, other in enumerate(b.lines):
            if other["section"] != "O" or other["label"] == "Vitals":
                continue
            other_rank = rank.get(D.LABEL_REGION.get(other["label"], ""), len(order))
            if other["label"] in ("Osteopathic", "Results") or other_rank > mine:
                idx = i
                break
        if idx is None:
            last = max((i for i, o in enumerate(b.lines) if o["section"] == "O"), default=len(b.lines) - 1)
            idx = last + 1
        b.lines.insert(idx, ln)
    else:
        last = max((i for i, o in enumerate(b.lines) if o["section"] == section), default=len(b.lines) - 1)
        b.lines.insert(last + 1, ln)
    return ln, cid


def _append_chip(ln, b, text):
    cid = b.new_chip_id()
    ln["chips"].append({"id": cid, "text": text, "evidence": [], "origin": "planted"})
    return cid


def _error(type_, severity, ln, *, chip=None, op, original=None, planted=None, check, evidence=(),
           correct="", note="", anchor_line=None):
    return {
        "type": type_, "severity": severity, "section": ln["section"] if ln else "",
        "label": ln["label"] if ln else "", "op": op, "chip": chip,
        "line": ln["id"] if ln else None, "anchor_line": anchor_line,
        "original": original, "planted": planted, "check": check,
        "evidence": list(evidence), "correct": correct, "note": note,
    }


# --------------------------------------------------------------------------
# Generators
# --------------------------------------------------------------------------

def gen_fabricated_exam(b, ctx):
    visit, case = ctx["visit"], ctx["case"]
    examined = V.examined_regions(visit) | {D.region_of(ln) for ln in _lines(b, "O")}
    out = []
    for region, spec in C.FABRICATED_EXAMS.items():
        if region in examined:
            continue

        def apply(region=region, spec=spec):
            ln, cid = _insert_line(b, "O", region, "exam", spec["text"])
            return _error("fabricated_exam", "high", ln, chip=cid, op="insert", planted=spec["text"],
                          check={"kind": "inserted", "claim": spec["claim"], "neutral": C.NOT_EXAMINED},
                          correct="No %s examination was performed." % region.lower() if region != "HEENT"
                          else "No HEENT examination was performed.",
                          note="Nobody examined the %s in this visit, so there is no finding to document."
                          % (region if region == "HEENT" else region.lower()))
        out.append(Candidate("fabricated_exam", {"newline:O:" + region}, "O", apply))
    exam_labels = " ".join(T.norm(t.get("label", "")) for t in visit["turns"] if t["kind"] == "exam")
    for key in case.get("refusals") or []:
        if key not in C.FABRICATED_SENSITIVE:
            continue
        label, sentence, claim = C.FABRICATED_SENSITIVE[key]
        if T.norm(label) in exam_labels:
            continue

        def apply(label=label, sentence=sentence, claim=claim, key=key):
            ln, cid = _insert_line(b, "O", label, "exam", sentence)
            name = physexam.REFUSABLE.get(key, {}).get("label", label + " examination").lower()
            return _error("fabricated_exam", "high", ln, chip=cid, op="insert", planted=sentence,
                          check={"kind": "inserted", "claim": claim, "neutral": C.NOT_EXAMINED},
                          correct="No %s was performed." % name,
                          note="No %s happened in this visit. A sensitive exam needs a proposal and the "
                               "patient's consent; a scribe that documents one as normal is inventing an "
                               "intimate examination." % name)
        out.append(Candidate("fabricated_exam", {"newline:O:" + label}, "O", apply))
    return out


def gen_fabricated_history(b, ctx):
    visit = ctx["visit"]
    said = T.norm(V.visit_text(visit) + "\n" + " ".join(ch["text"] for ln in _lines(b, "S") for ch in ln["chips"]))
    out = []
    for topic in C.FABRICATED_HISTORY:
        if any(re.search(p, said) for p in topic["detect"]):
            continue
        ln = _first_line(b, "S", topic["label"])
        if ln is None:
            continue

        def apply(topic=topic, ln=ln):
            cid = _append_chip(ln, b, topic["text"])
            subject = {"sick_contacts": "sick contacts", "fh_cancer": "family history of cancer",
                       "vaccines": "immunizations"}.get(topic["key"], topic["key"].replace("_", " "))
            return _error("fabricated_history", "medium", ln, chip=cid, op="insert", planted=topic["text"],
                          check={"kind": "inserted", "claim": topic["detect"],
                                 "neutral": [r"not (asked|discussed|obtained|assessed|addressed)", r"\bunknown\b"]},
                          correct="Not discussed in this visit.",
                          note="Nobody asked about %s in this visit. The answer Scribbi wrote was never given."
                               % subject)
        out.append(Candidate("fabricated_history", {"ins:" + ln["id"]}, "S", apply))
    return out


_NEG_START = re.compile(r"^(?P<cue>Denies|denies|No|no)\s+(?P<term>[^,;.]+?)(?P<end>[.;]?)$")
_NEG_TAIL = re.compile(r"^(?P<pre>.+?,\s*)(?P<cue>no|denies)\s+(?P<term>[^,;.]+?)(?P<end>[.;]?)$")
_POS_START = re.compile(r"^(?P<cue>Reports|reports|Admits|admits|Endorses|endorses)\s+(?P<term>[^,;.]+?)(?P<end>[.;]?)$")
_O_NEGATIVE = re.compile(r"^(?P<term>[A-Z][^,;.]{2,40}?)\s+negative(?P<end>[.;]?)$")
_O_NO = re.compile(r"^No (?P<term>[a-z][^,;.]{2,40}?)(?P<end>[.;]?)$")


def _flip(chip_text, section):
    """(planted text, term, true polarity) or None when no safe flip exists."""
    t = chip_text.strip()
    if section == "S":
        m = _NEG_START.match(t)
        if m and len(m.group("term").split()) <= 5 and not _FLIP_EXCLUDE.search(m.group("term")):
            cue = "Reports " if m.group("cue")[0].isupper() else "reports "
            return cue + m.group("term") + m.group("end"), m.group("term"), "negative"
        m = _NEG_TAIL.match(t)
        if m and len(m.group("term").split()) <= 4 and not _FLIP_EXCLUDE.search(m.group("term")):
            return m.group("pre") + "reports " + m.group("term") + m.group("end"), m.group("term"), "negative"
        m = _POS_START.match(t)
        if m and len(m.group("term").split()) <= 5 and not _FLIP_EXCLUDE.search(m.group("term")):
            cue = "Denies " if m.group("cue")[0].isupper() else "denies "
            return cue + m.group("term") + m.group("end"), m.group("term"), "positive"
        return None
    m = _O_NEGATIVE.match(t)
    if m and " or " not in m.group("term"):
        return m.group("term") + " positive" + m.group("end"), m.group("term"), "negative"
    m = _O_NO.match(t)
    if m and " or " not in m.group("term") and " and " not in m.group("term"):
        term = m.group("term")
        return term[0].upper() + term[1:] + " present" + m.group("end"), term, "negative"
    if len(re.findall(r"\bnon-tender\b", t)) == 1:
        return re.sub(r"\bnon-tender\b", "tender", t), "tender", "negative"
    if len(re.findall(r"\bnon-distended\b", t)) == 1:
        return re.sub(r"\bnon-distended\b", "distended", t), "distended", "negative"
    return None


def _synonyms(case, term):
    """Other ways to say the flipped finding, from the case's own lexicon."""
    t = T.norm(term)
    out = []
    for surfaces in (case.get("concept_lexicon") or {}).values():
        cores = [nlp.strip_negation_cue(s) for s in surfaces if s]
        if t in cores or any(c and (c == t or (len(c) > 4 and re.search(_lit(c), t))) for c in cores):
            for c in cores:
                if c and c != t and len(c) > 3 and c not in out:
                    out.append(c)
    return out[:12]


def gen_flipped(b, ctx):
    out = []
    for ln, ch in D.all_chips(b):
        if ln["section"] not in ("S", "O") or ch.get("quoted") or not ch.get("evidence"):
            continue
        if ln["section"] == "S" and ln["label"] not in ("HPI", "ROS"):
            continue
        if ln["section"] == "O" and ln["kind"] != "exam":
            continue
        flipped = _flip(ch["text"], ln["section"])
        if not flipped:
            continue
        planted, term, truth = flipped
        severity = "high" if (ln["section"] == "O" or any(re.search(p, T.norm(term)) for p in RED_FLAGS)) else "medium"
        def apply(ln=ln, ch=ch, planted=planted, term=term, truth=truth, severity=severity):
            synonyms = _synonyms(ctx["case"], term)
            original = ch["text"]
            ch["text"] = planted
            ch["origin"] = "planted"
            return _error("flipped", severity, ln, chip=ch["id"], op="modify", original=original, planted=planted,
                          check={"kind": "modified", "mode": "polarity", "term": T.norm(term), "true": truth,
                                 "synonyms": synonyms},
                          evidence=ch["evidence"], correct=original,
                          note="The visit shows the opposite: %s." % original.rstrip(";.").strip())
        out.append(Candidate("flipped", {ch["id"]}, ln["section"], apply, severity))
    return out


def _vital_mutation(text):
    m = re.match(r"^T\s+(\d+(?:\.\d+)?)", text)
    if m:
        v = float(m.group(1))
        new = "98.6" if v >= 100.4 else "101.8"
        return text.replace(m.group(1), new, 1), m.group(1), new
    m = re.match(r"^P\s+(\d+)", text)
    if m:
        v = int(m.group(1))
        new = str(v - 30 if v > 100 else v + 32)
        return text.replace(m.group(1), new, 1), m.group(1), new
    m = re.match(r"^BP\s+(\d+)/(\d+)", text)
    if m:
        v = int(m.group(1))
        new = str(v + 36 if v < 140 else v - 36)
        return text.replace(m.group(1) + "/", new + "/", 1), m.group(1) + "/" + m.group(2), new + "/" + m.group(2)
    m = re.match(r"^Pulse Ox\s+(\d+)%", text)
    if m:
        v = int(m.group(1))
        new = "91" if v >= 95 else "98"
        return text.replace(m.group(1) + "%", new + "%", 1), m.group(1) + "%", new + "%"
    return None


_WORD_FOR = {1: "one|a|an", 2: "two|a couple of|a couple|couple of", 3: "three|a few|few", 4: "four", 5: "five",
             6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


def _number_alts(num: str) -> str:
    """'2' -> '(?:2|two|a couple of|...)' so a reworded fix still counts."""
    value = T.number_value(num)
    alts = [re.escape(num.lower())]
    if value is not None and float(value).is_integer():
        v = int(value)
        alts.append(str(v))
        alts.extend(_WORD_FOR.get(v, "").split("|"))
    alts = [a for a in dict.fromkeys(a for a in alts if a)]
    return "(?:" + "|".join(sorted(alts, key=len, reverse=True)) + ")"


def _value_pattern(value: str) -> str:
    return r"(?<![0-9.])" + re.escape(value) + r"(?![0-9])"


def gen_wrong_detail(b, ctx):
    out = []
    for ln, ch in D.all_chips(b):
        if ln["section"] not in ("S", "O") or ch.get("quoted") or not ch.get("evidence"):
            continue
        if ln["kind"] == "structural":
            # The structural line is never in Scribbi's draft ("Scribbi can't feel").
            continue
        text = ch["text"]
        options = []
        if ln["label"] == "Vitals":
            mut = _vital_mutation(text)
            if mut:
                planted, old, new = mut
                options.append(("vital", "high", planted, {"right": [_value_pattern(old)], "wrong": [_value_pattern(new)]},
                                "The chart reads %s." % text))
        if ln["section"] == "S" and ln["label"] in ("CC", "HPI", "Meds", "PMH"):
            m = T.DURATION_RE.search(text)
            if m:
                new_unit = T.swap_unit(m.group(2))
                planted = text[:m.start(2)] + new_unit + text[m.end(2):]
                num = m.group(1)
                right = [r"\b%s\s*-?\s*%s" % (_number_alts(num), re.escape(m.group(2).lower().rstrip("s")))]
                wrong = [r"\b%s\s*-?\s*%s" % (_number_alts(num), re.escape(new_unit.rstrip("s")))]
                options.append(("duration", "medium", planted, {"right": right, "wrong": wrong},
                                "The patient said %s %s." % (num, m.group(2))))
        m = T.RATING_RE.search(text)
        if m and ln["section"] == "S":
            n = int(m.group(1))
            new = n - 4 if n >= 6 else n + 4
            new = max(1, min(10, new))
            if abs(new - n) >= 3:
                planted = text[:m.start(1)] + str(new) + text[m.end(1):]
                options.append(("rating", "medium", planted,
                                {"right": [r"(?<![0-9])%d\s*/\s*10" % n], "wrong": [r"(?<![0-9])%d\s*/\s*10" % new]},
                                "The patient rated it %d/10." % n))
        m = T.DOSE_RE.search(text)
        if m and ln["label"] == "Meds":
            dose = float(m.group(1))
            new_dose = dose * 2 if dose <= 500 else dose / 2
            new_s = ("%g" % new_dose)
            planted = text[:m.start(1)] + new_s + text[m.end(1):]
            options.append(("dose", "high", planted,
                            {"right": [_value_pattern(m.group(1)) + r"\s?" + re.escape(m.group(2).lower())],
                             "wrong": [_value_pattern(new_s) + r"\s?" + re.escape(m.group(2).lower())]},
                            "The patient takes %s %s." % (m.group(1), m.group(2))))
        sides = [mm for mm in T.SIDE_RE.finditer(text) if T.side_is_laterality(text, mm.start())]
        if sides and ln["label"] not in ("Vitals", "Results"):
            planted = text
            for mm in reversed(sides):
                planted = planted[:mm.start()] + T.swap_side(mm.group(1)) + planted[mm.end():]
            options.append(("side", "high", planted, {"sides": T.sides_in(text)},
                            "The visit documents the %s side." % T.sides_in(text)[0]))
        m = T.AGE_RE.search(text)
        if m and ln["label"] == "HPI":
            age = m.group(1)
            new_age = age[::-1] if age[::-1] != age and not age[::-1].startswith("0") else str(int(age) + 20)
            planted = text[:m.start(1)] + new_age + text[m.end(1):]
            options.append(("age", "low", planted, {"right": [r"\b%s\b" % age], "wrong": [r"\b%s\b" % new_age]},
                            "The patient is %s." % age))
        for mode, severity, planted, check, note in options:
            def apply(ln=ln, ch=ch, mode=mode, severity=severity, planted=planted, check=check, note=note):
                original = ch["text"]
                ch["text"] = planted
                ch["origin"] = "planted"
                return _error("wrong_detail", severity, ln, chip=ch["id"], op="modify", original=original,
                              planted=planted, check=dict({"kind": "modified", "mode": mode}, **check),
                              evidence=ch["evidence"], correct=original, note=note)
            out.append(Candidate("wrong_detail", {ch["id"]}, ln["section"], apply, severity))
    return out


_RELATIVE_NAMES = {"mom": "mother", "dad": "father", "fh": "family", "grand": "grandparent",
                   "maternal": "maternal relative", "paternal": "paternal relative",
                   "parent": "parent", "sibling": "sibling", "family": "family"}


def _nearest_relative(chip_norm, pos):
    """The relative named closest before the condition ("Mother HTN, father diabetes")."""
    best, best_pos = None, -1
    for p in C.RELATIVE_WORDS:
        for m in re.finditer(p, chip_norm):
            if m.start() <= pos and m.start() > best_pos:
                best, best_pos = m, m.start()
    if best is None:
        for p in C.RELATIVE_WORDS:
            m = re.search(p, chip_norm)
            if m:
                best = m
                break
    if best is None:
        return "a relative"
    word = re.match(r"[a-z]+", chip_norm[best.start():].lstrip())
    word = word.group(0) if word else best.group(0).strip()
    return _RELATIVE_NAMES.get(word, word)


def gen_misattributed(b, ctx):
    out = []
    pmh = _first_line(b, "S", "PMH")
    if pmh is None:
        return out
    own = T.norm(" ".join(ch["text"] for ln in b.lines if ln["section"] == "S" and ln["label"] in ("PMH", "Additional PMH", "HPI", "CC", "Meds")
                          for ch in ln["chips"]))
    for ln in _lines(b, "S", "FH"):
        for ch in ln["chips"]:
            chip_norm = T.norm(ch["text"])
            for condition, patterns in C.FAMILY_CONDITIONS:
                hit = next((re.search(p, chip_norm) for p in patterns if re.search(p, chip_norm)), None)
                if not hit:
                    continue
                if nlp.term_polarity(ch["text"], hit.group(0)) == "negative":
                    continue
                if any(re.search(p, own) for p in patterns):
                    continue
                rel = _nearest_relative(chip_norm, hit.start())
                planted = "History of %s." % condition

                def apply(ch=ch, condition=condition, patterns=patterns, rel=rel, planted=planted):
                    cid = _append_chip(pmh, b, planted)
                    whose = "a relative" if rel == "a relative" else "the patient's " + rel
                    return _error("misattributed", "medium", pmh, chip=cid, op="insert", planted=planted,
                                  check={"kind": "inserted", "claim": patterns, "neutral": C.RELATIVE_WORDS},
                                  evidence=ch["evidence"], correct="Family history: %s" % ch["text"],
                                  note="In the visit, the %s belongs to %s, not to the patient."
                                       % (condition, whose))
                out.append(Candidate("misattributed", {"ins:" + pmh["id"], "fh:" + condition}, "S", apply))
                break
    return out


_CONCERN = re.compile(r"\b(concern|worr|afraid|scared|fear|anxious|nervous|wonder)", re.I)
_REACTION = {"hives", "rash", "swelling", "swelled", "swell", "cause", "causes", "caused", "allergy",
             "allergies", "allergic", "reaction", "reactions", "itchy", "anaphylaxis", "gave", "made",
             "known", "drug", "drugs", "medication", "medications", "lips", "face", "throat", "breathing",
             "trouble", "without", "teenager", "child", "adult", "skin", "red", "widespread", "blisters"}
_GENERIC = {"required", "requires", "needed", "needs", "started", "caused", "causing", "getting", "having",
            "taking", "making", "feeling", "happened", "happens", "wants", "wanted", "worse", "better",
            "concerned", "worried", "worry", "about", "states", "asks", "would", "could", "like", "want",
            "know", "going", "think", "because", "patient", "really", "maybe", "might", "something",
            "someone", "anything", "things", "thing", "that", "this", "what", "when", "will", "have",
            "been", "being", "does", "doing", "just", "make", "sure", "okay", "right", "left"}


def _distinctive(text, exclude=(), limit=3):
    words = []
    for w in T.content_words(text):
        if w in _GENERIC or w in exclude or len(w) < 4:
            continue
        if w not in words:
            words.append(w)
    words.sort(key=lambda w: -len(w))
    return words[:limit]


def gen_dropped(b, ctx):
    out = []
    case, turn_concepts = ctx["case"], ctx["turn_concepts"]
    rank1 = next((d for d in case.get("differentials", []) if d.get("rank") == 1), None)
    support = set(rank1.get("supported_by", [])) if rank1 else set()
    lexicon = case.get("concept_lexicon") or {}
    for ln, ch in D.all_chips(b):
        if ln["section"] != "S" or not ch.get("evidence") or ln["label"] == "CC":
            continue
        text = ch["text"]
        norm_text = T.norm(text)
        spec = None
        if ln["label"] in ("Perspective", "Patient concern", "Care needs") or (ln["label"] == "HPI" and _CONCERN.search(text)):
            words = _distinctive(text)
            if words:
                spec = ("concern", "medium", {"groups": [[T.stem_pattern(w) for w in words]], "min": 1},
                        "The patient's own concern is gone from the note.")
        elif ln["label"] == "Allergies" or (ln["label"] == "Meds" and re.search(r"allerg|hives|rash|reaction|swell|anaphyla", norm_text)):
            if re.search(r"\bnkda\b|no known|no (drug |medication )?allerg|none", norm_text):
                spec = ("allergy", "medium", {"groups": [[r"\bnkda\b", r"no known (drug |medication )?allerg",
                                                           r"no (drug |medication )?allerg", r"\bnone\b"]], "min": 1},
                        "The patient's allergy status is gone from the note.")
            else:
                words = _distinctive(text, exclude=_REACTION, limit=2)
                if words:
                    spec = ("allergy", "high", {"groups": [[T.stem_pattern(w) for w in words]], "min": 1},
                            "A drug allergy the patient told you about is gone from the note.")
        elif ln["label"] in ("HPI", "ROS") and support:
            concepts = set()
            for ref in ch.get("evidence", []):
                concepts |= turn_concepts.get(ref, set())
            polarity_ok = not re.match(r"^(no|denies|without)\b", norm_text)
            # Only concepts the sentence actually names: re-adding the
            # original sentence must always satisfy the check.
            groups = []
            for c in sorted(concepts & support):
                surfaces = [s for s in lexicon.get(c, []) if s and len(s) > 2
                            and not re.match(r"^(no|denies|without)\b", s, re.I)]
                present = [s for s in surfaces if re.search(_lit(s), norm_text)]
                if present:
                    alts = present + [s for s in surfaces if s not in present]
                    groups.append([_lit(s) for s in alts[:14]])
            if groups and polarity_ok and len(groups) <= 3:
                groups = groups[:2]
                spec = ("symptom", "high", {"groups": groups, "min": len(groups), "positive": True},
                        "A finding that supports the leading diagnosis is gone from the note.")
        elif ln["label"] == "Meds" and not re.search(r"\bnone\b|no (daily |regular )?medication", norm_text):
            words = _distinctive(text, exclude={"daily", "twice", "tablet", "tablets", "times", "day", "days",
                                                "couple", "needed", "every", "hours", "morning", "night"}, limit=1)
            if words:
                spec = ("medication", "medium", {"groups": [[T.stem_pattern(w) for w in words]], "min": 1},
                        "A medication the patient takes is gone from the note.")
        if not spec:
            continue
        kind, severity, check, note = spec

        def apply(ln=ln, ch=ch, kind=kind, severity=severity, check=check, note=note):
            original = ch["text"]
            ln["chips"].remove(ch)
            anchor = ln["id"]
            if not ln["chips"]:
                idx = b.lines.index(ln)
                b.lines.remove(ln)
                prev = next((o for o in reversed(b.lines[:idx]) if o["section"] == "S"), None)
                anchor = prev["id"] if prev else None
            return _error("dropped", severity, ln, chip=None, op="remove", original=original,
                          check=dict({"kind": "omission", "section": "S", "what": kind}, **check),
                          evidence=ch["evidence"], correct=original, note=note, anchor_line=anchor)
        out.append(Candidate("dropped", {ch["id"]}, "S", apply, severity))
    return out


def _dx_patterns(d):
    names = [d.get("name", "")] + list(d.get("aliases", []))
    pats = []
    for n in names:
        n = T.norm(n)
        if n and len(n) > 2:
            pats.append(_lit(n))
        # "Acute cystitis / lower urinary tract infection" -> each half too
        for part in re.split(r"\s*/\s*", n):
            if part and len(part) > 3 and _lit(part) not in pats:
                pats.append(_lit(part))
    return pats


def _concept_label(case, concept):
    surfaces = (case.get("concept_lexicon") or {}).get(concept) or []
    for s in surfaces:
        if s and not re.match(r"^(no|denies|without)\b", s, re.I) and len(s) > 3:
            return s
    return concept.replace("_", " ")


def _support_refs(ctx, concepts):
    refs = []
    for ref, cs in ctx["turn_concepts"].items():
        if cs & set(concepts):
            refs.append(ref)
    order = {t["id"]: i for i, t in enumerate(ctx["visit"]["turns"])}
    refs.sort(key=lambda r: order.get(r, 10 ** 6))
    return refs[:8]


def gen_anchored_dx(b, ctx):
    case = ctx["case"]
    a_lines = _lines(b, "A")
    diffs = [d for d in case.get("differentials", []) if d.get("name")]
    rank1 = next((d for d in diffs if d.get("rank") == 1), None)
    if not a_lines or not rank1 or not a_lines[0]["chips"]:
        return []
    lead_chip = a_lines[0]["chips"][0]
    lead_norm = T.norm(lead_chip["text"])
    if not any(re.search(p, lead_norm) for p in _dx_patterns(rank1)):
        return []
    listed = T.norm(" ".join(ch["text"] for ln in a_lines for ch in ln["chips"]))
    ranked = [d for d in diffs if (d.get("rank") or 9) >= 2 and not d.get("weak")]
    unlisted = [d for d in ranked if not any(re.search(p, listed) for p in _dx_patterns(d))]

    def reason_for(alt):
        findings = [_concept_label(case, c) for c in rank1.get("supported_by", [])][:5]
        if alt.get("not_most_likely_because"):
            return alt["not_most_likely_because"]
        if findings:
            return "The visit points to %s first: %s." % (rank1["name"], ", ".join(findings))
        return "The visit supports %s as the leading diagnosis." % rank1["name"]

    out = []
    if unlisted:
        best = min(d.get("rank") or 9 for d in unlisted)
        for alt in [d for d in unlisted if (d.get("rank") or 9) == best]:
            def apply(alt=alt):
                original = lead_chip["text"]
                planted = alt["name"]
                lead_chip["text"] = planted
                lead_chip["origin"] = "planted"
                return _error("anchored_dx", "high", a_lines[0], chip=lead_chip["id"], op="modify",
                              original=original, planted=planted,
                              check={"kind": "lead", "right": _dx_patterns(rank1), "wrong": _dx_patterns(alt),
                                     "chips": [lead_chip["id"]]},
                              evidence=_support_refs(ctx, rank1.get("supported_by", [])),
                              correct="1. " + original, note=reason_for(alt))
            out.append(Candidate("anchored_dx", {lead_chip["id"]}, "A", apply))
        return out
    # Every differential is already listed: Scribbi leads with the runner-up
    # and moves the leading diagnosis down.
    for other in a_lines[1:]:
        if not other["chips"]:
            continue
        other_chip = other["chips"][0]
        other_norm = T.norm(other_chip["text"])
        alt = next((d for d in ranked if any(re.search(p, other_norm) for p in _dx_patterns(d))), None)
        if alt is None:
            continue

        def apply(alt=alt, other=other, other_chip=other_chip):
            original, moved = lead_chip["text"], other_chip["text"]
            lead_chip["text"], other_chip["text"] = moved, original
            lead_chip["origin"] = other_chip["origin"] = "planted"
            return _error("anchored_dx", "high", a_lines[0], chip=lead_chip["id"], op="modify",
                          original=original, planted=moved,
                          check={"kind": "lead", "right": _dx_patterns(rank1), "wrong": _dx_patterns(alt),
                                 "chips": [lead_chip["id"], other_chip["id"]]},
                          evidence=_support_refs(ctx, rank1.get("supported_by", [])),
                          correct="1. %s (then %s)" % (original, moved), note=reason_for(alt))
        out.append(Candidate("anchored_dx", {lead_chip["id"], other_chip["id"]}, "A", apply))
        break
    return out


def gen_unsupported_dx(b, ctx):
    case = ctx["case"]
    a_lines = _lines(b, "A")
    if not a_lines:
        return []
    listed = T.norm(" ".join(ch["text"] for ln in a_lines for ch in ln["chips"]))
    out = []
    for item in case.get("implausible_differentials") or []:
        name = (item.get("name") or "").strip()
        if not name or len(name.split()) > 5 or re.search(_lit(name), listed):
            continue
        if name.lower() in ("cancer",):
            continue

        def apply(name=name, item=item):
            number = str(len(_lines(b, "A")) + 1)
            shown = name[0].upper() + name[1:]
            ln, cid = _insert_line(b, "A", number, "assessment", shown)
            return _error("unsupported_dx", "medium", ln, chip=cid, op="insert", planted=shown,
                          check={"kind": "inserted", "claim": [_lit(name)],
                                 "neutral": [r"\bunlikely\b", r"ruled out", r"not supported", r"no evidence"]},
                          correct="Remove it.", note=item.get("why") or "Nothing in this visit supports it.")
        out.append(Candidate("unsupported_dx", {"newline:A"}, "A", apply))
    return out


def gen_allergy_conflict(b, ctx):
    case = ctx["case"]
    spec = C.ALLERGY_CONFLICTS.get(case.get("id"))
    p1 = _first_line(b, "P", "1")
    if not spec or p1 is None:
        return []
    s_chips = [(ln, ch) for ln, ch in D.all_chips(b) if ln["section"] == "S"]
    allergen_chips = [ch for _ln, ch in s_chips if any(re.search(p, T.norm(ch["text"])) for p in spec["allergen"])]
    if not allergen_chips:
        return []
    plan_text = T.norm(" ".join(ch["text"] for ln in _lines(b, "P") for ch in ln["chips"]))

    def apply():
        cid = _append_chip(p1, b, spec["plan"])
        evidence = []
        for ch in allergen_chips:
            for r in ch.get("evidence", []):
                if r not in evidence:
                    evidence.append(r)
        return _error("allergy_conflict", "high", p1, chip=cid, op="insert", planted=spec["plan"],
                      check={"kind": "inserted", "claim": spec["avoid"],
                             "neutral": [r"\bavoid", r"allerg", r"contraindicat", r"\bdo not\b", r"\bdont\b",
                                         r"\bnot\b.{0,20}\b(use|give|start|prescribe)"]},
                      evidence=evidence, correct="Choose a treatment that avoids the allergen.",
                      note=spec["message"])
    if any(re.search(p, plan_text) for p in spec["avoid"]) and not re.search(r"\bavoid", plan_text):
        return []
    return [Candidate("allergy_conflict", {"ins:" + p1["id"]}, "P", apply)]


GENERATORS = {
    "fabricated_exam": gen_fabricated_exam,
    "fabricated_history": gen_fabricated_history,
    "flipped": gen_flipped,
    "wrong_detail": gen_wrong_detail,
    "misattributed": gen_misattributed,
    "dropped": gen_dropped,
    "anchored_dx": gen_anchored_dx,
    "unsupported_dx": gen_unsupported_dx,
    "allergy_conflict": gen_allergy_conflict,
}


def hands_on(b, ctx):
    """Scribbi never hears palpation: the structural line is always missing."""
    case = ctx["case"]
    lines = _lines(b, "O", "Osteopathic")
    if not lines:
        return None
    ln = lines[0]
    text = " ".join(ch["text"] for ch in ln["chips"])
    levels = T.levels_in(text) | T.expand_level_range((case.get("osteopathic") or {}).get("levels", ""))
    allowed = set()
    for i in levels:
        allowed.update({i - 1, i, i + 1})
    refs = [t["id"] for t in ctx["visit"]["turns"] if t.get("kind") == "exam" and t.get("region") == "Osteopathic"]
    idx = b.lines.index(ln)
    b.lines.remove(ln)
    prev = next((o for o in reversed(b.lines[:idx]) if o["section"] == "O"), None)
    return _error("hands_on", "medium", ln, chip=None, op="remove_line", original=text,
                  check={"kind": "structural", "levels": sorted(i for i in allowed if i >= 0),
                         "sides": T.sides_in(text)},
                  evidence=refs, correct="Osteopathic: " + text,
                  note="You palpated this. Scribbi only hears, so the finding never reached the draft.",
                  anchor_line=prev["id"] if prev else None)


def error_count(mode, rng):
    lo, hi = C.MODES[mode]["errors"]
    if mode == "solo":
        return rng.choices([0, 1, 2, 3, 4, 5], weights=[8, 12, 20, 25, 20, 15])[0]
    return rng.randint(lo, hi)


def choose(candidates, n, rng):
    by_type = defaultdict(list)
    for c in candidates:
        by_type[c.type].append(c)
    chosen, used = [], set()
    types_used, sections_used = Counter(), Counter()
    for _ in range(n):
        options = []
        for t, pool in by_type.items():
            free = [c for c in pool if c.touch.isdisjoint(used)]
            if free:
                options.append((t, free))
        if not options:
            break
        weights = []
        for t, free in options:
            w = C.TYPE_WEIGHTS.get(t, 1.0) * (0.2 ** types_used[t])
            sec = Counter(c.section for c in free).most_common(1)[0][0]
            w *= 0.55 ** sections_used[sec]
            weights.append(w)
        t, free = options[rng.choices(range(len(options)), weights=weights)[0]]
        pick = free[rng.randrange(len(free))]
        chosen.append(pick)
        used |= pick.touch
        types_used[t] += 1
        sections_used[pick.section] += 1
    return chosen


def plant(b, ctx, mode, seed):
    """Mutate the builder in place; return (errors, hands_on_item)."""
    rng = random.Random(seed)
    n = error_count(mode, rng)
    candidates = []
    for name, gen in GENERATORS.items():
        candidates.extend(gen(b, ctx))
    picks = choose(candidates, n, rng)
    # Removals go last: a removal can empty and delete a line, and an
    # insertion captured that line object when it was proposed.
    ordered = [c for c in picks if c.type != "dropped"] + [c for c in picks if c.type == "dropped"]
    errors = [c.apply() for c in ordered]
    hands = hands_on(b, ctx)
    return errors, hands
