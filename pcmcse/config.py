"""Configurable assumptions.

Everything in here is a place where the course materials do not settle a
question.  Each entry names the reason it is a default rather than a rule, and
the value is surfaced in the results screen so a scoring interpretation is
never invisible.  See docs/requirements-map.md section 5.
"""

from __future__ import annotations

import copy
import json
import os

# --------------------------------------------------------------------------
# Timing presets.  T1/T2 are confirmed (syllabus p.4).  The organization
# interval is Sebastian's requested practice modification -- no course
# document mentions any interval between the encounter and the note.
# --------------------------------------------------------------------------

PRESETS = {
    "practice": {
        "key": "practice",
        "label": "Practice format (default)",
        "encounter_s": 14 * 60,
        "organize_s": 2 * 60,
        "note_s": 9 * 60,
        "modified": True,
        "modification_note": (
            "The 2-minute organization interval is a practice modification "
            "requested by the student. No PCM course document describes any "
            "interval between the encounter and the SOAP note."
        ),
    },
    "course": {
        "key": "course",
        "label": "Course-timing rehearsal",
        "encounter_s": 14 * 60,
        "organize_s": 0,
        "note_s": 9 * 60,
        "modified": False,
        "modification_note": "",
    },
}

DEFAULT_PRESET = "practice"


# --------------------------------------------------------------------------
# Provisional mnemonic expansions.  U1 / U2 in the requirements map: the
# letters appear in the PCM 2026 grading table and are never expanded in any
# of the four course documents.
# --------------------------------------------------------------------------

VINDICATE = {
    "V": {
        "name": "Vascular",
        "hints": ["embolism", "infarct", "ischemi", "thrombo", "hemorrhage", "aneurysm",
                  "stenosis", "claudication", "varic", "vasculitis", "dissection",
                  "hypertensive", "stroke", "cva", "tia", "dvt", "pe ", "angina"],
    },
    "I": {
        "name": "Infectious / Inflammatory",
        "hints": ["infect", "itis", "pneumonia", "abscess", "cellulitis", "sepsis",
                  "viral", "bacterial", "fungal", "influenza", "uri", "pharyngitis",
                  "sinusitis", "bronchitis", "uti", "pyelonephritis", "gastroenteritis",
                  "cholecystitis", "appendicitis", "diverticulitis", "meningitis"],
    },
    "N": {
        "name": "Neoplastic",
        "hints": ["cancer", "carcinoma", "tumor", "malignan", "lymphoma", "leukemia",
                  "neoplas", "metasta", "sarcoma", "myeloma", "adenoma", "polyp",
                  "mass"],
    },
    "D": {
        "name": "Degenerative / Deficiency",
        "hints": ["degenerat", "osteoarthritis", "spondylosis", "dementia", "deficien",
                  "anemia", "malnutrition", "osteoporosis", "atroph", "b12", "iron def",
                  "sarcopenia", "disc disease", "copd"],
    },
    "I2": {
        "name": "Iatrogenic / Intoxication",
        "hints": ["drug", "medication", "side effect", "adverse", "iatrogenic",
                  "overdose", "toxic", "intoxicat", "withdrawal", "alcohol", "opioid",
                  "nsaid", "poisoning", "post-op", "postoperative", "induced"],
    },
    "C": {
        "name": "Congenital",
        "hints": ["congenital", "hereditary", "genetic", "inherited", "sickle cell",
                  "cystic fibrosis", "hemophilia", "familial", "birth defect"],
    },
    "A": {
        "name": "Autoimmune / Allergic",
        "hints": ["autoimmune", "lupus", "rheumatoid", "allerg", "anaphyla", "asthma",
                  "eczema", "psoriasis", "celiac", "crohn", "ulcerative colitis",
                  "thyroiditis", "urticaria", "contact dermatitis", "ibd", "ms ",
                  "multiple sclerosis", "myasthenia", "sarcoid"],
    },
    "T": {
        "name": "Traumatic",
        "hints": ["trauma", "fracture", "sprain", "strain", "injury", "contusion",
                  "laceration", "concussion", "musculoskeletal strain", "overuse",
                  "somatic dysfunction", "whiplash", "burn"],
    },
    "E": {
        "name": "Endocrine / Metabolic",
        "hints": ["diabet", "thyroid", "hypothyroid", "hyperthyroid", "adrenal",
                  "cushing", "addison", "electrolyte", "metabolic", "hypoglycem",
                  "hyperglycem", "dka", "hypercalcem", "hyponatrem", "obesity",
                  "menopause", "gout", "renal failure", "uremia", "acidosis"],
    },
}

MOTHERR = {
    "M": {
        "name": "Medications",
        "hints": ["mg", "po", "tab", "prescri", "start ", "antibiotic", "analgesi",
                  "nsaid", "ibuprofen", "acetaminophen", "tylenol", "naproxen",
                  "aspirin", "steroid", "prednisone", "inhaler", "albuterol",
                  "antihistamine", "ppi", "omeprazole", "diuretic", "furosemide",
                  "lisinopril", "metformin", "statin", "anticoagul", "heparin",
                  "azithromycin", "amoxicillin", "ceftriaxone", "doxycycline",
                  "ondansetron", "oxygen", "iv fluids", "fluoroquinolone",
                  "cephalosporin", "macrolide", "alpha blocker", "tamsulosin",
                  "nitroglycerin", "sumatriptan", "cyclobenzaprine", "muscle relaxant"],
    },
    "O": {
        "name": "OMT (osteopathic manipulative treatment)",
        "hints": ["omt", "omm", "osteopathic manipul", "muscle energy", "counterstrain",
                  "myofascial", "hvla", "rib raise", "soft tissue", "lymphatic pump",
                  "still technique", "balanced ligamentous", "facilitated positional",
                  "cranial", "manipulative treatment"],
    },
    "T": {
        "name": "Tests (labs, imaging, diagnostic procedures)",
        "hints": ["cbc", "bmp", "cmp", "lft", "tsh", "a1c", "lipid", "d-dimer", "bnp",
                  "troponin", "ekg", "ecg", "x-ray", "xray", "radiograph", "ct ", "mri",
                  "ultrasound", "us ", "echo", "urinalysis", "u/a", "urine culture",
                  "culture", "cxr", "kub", "psa", "esr", "crp", "blood culture",
                  "swab", "biopsy", "endoscopy", "colonoscopy", "spirometry",
                  "pulse ox", "stool", "guaiac", "labs", "imaging", "panel",
                  "monospot", "rapid strep", "pregnancy test", "lumbar puncture"],
    },
    "H": {
        "name": "Holistic / lifestyle / supportive care",
        "hints": ["rest", "elevate", "ice", "heat", "moist heat", "hydrat", "fluids",
                  "increase fluids", "diet", "low salt", "low sodium", "exercise",
                  "weight loss", "sleep", "humidifier", "salt water gargle",
                  "gargle", "smoking cessation", "stop smoking", "quit", "stress",
                  "physical therapy", "stretch", "compression", "splint", "brace",
                  "activity modification", "lifestyle"],
    },
    "E": {
        "name": "Education / counseling",
        "hints": ["educat", "counsel", "advise", "advis", "discuss", "instruct",
                  "teach", "explain", "return precaution", "red flag", "warning sign",
                  "handout", "reviewed with patient", "informed the patient"],
    },
    "R": {
        "name": "Referral / consultation",
        "hints": ["refer", "referral", "consult", "cardiology", "oncology", "surgery",
                  "gastroenterology", "urology", "neurology", "nephrology",
                  "pulmonology", "specialist", "attending", "ed ", "emergency depart",
                  "send to", "admit"],
    },
    "R2": {
        "name": "Return (follow-up) / disposition",
        "hints": ["follow up", "follow-up", "f/u", "return in", "recheck",
                  "reevaluate", "re-evaluate", "come back", "admit to", "discharge",
                  "observation", "next visit", "revisit", "see me in"],
    },
}

MNEMONIC_PROVENANCE = {
    "VINDICATE": (
        "PROVISIONAL. The PCM 2026 grading table requires '3 different elements "
        "of VINDICATE' but no PCM document expands the letters. This app uses "
        "the standard nine-element set."
    ),
    "MOTHERR": (
        "PROVISIONAL. The PCM 2026 grading table requires 'at least three "
        "different elements (of MOTHERR)' but no PCM document expands the "
        "letters. This expansion was chosen because it is the only one "
        "consistent with all six sample plans in the student manual."
    ),
}


# --------------------------------------------------------------------------
# Scoring policy.  Every switch here is an interpretation, not a course rule.
# --------------------------------------------------------------------------

SCORING_DEFAULTS = {
    "partial_credit": False,
    "partial_credit_note": (
        "The rubric prints one value per row and several 'no credit' "
        "conditions, and never describes partial credit. Rows are scored "
        "all-or-nothing."
    ),
    "carry_over_unused_encounter_time": False,
    "carry_over_note": (
        "No course rule supports moving unused encounter time into the note "
        "period. The two published limits are independent."
    ),
    "vitals_first_means": "first_content_in_objective",
    "ros_systems_required": 3,
    "ros_symptoms_per_system": 3,
    "require_assessment_numbering": True,
    "require_plan_numbering": True,
    "unapproved_abbreviation_is": "advisory",
    "unapproved_abbreviation_note": (
        "The manual's abbreviation table, reference card and sample notes are "
        "treated together as the approved surface. Anything outside it is "
        "reported as an advisory, never a silent deduction."
    ),
    "passing_cutoff": None,
    "passing_cutoff_note": (
        "PCM I is pass/fail on competencies, not on a note percentage. No "
        "source gives a numeric cutoff, so none is implemented."
    ),
    "realtime_exam_durations": True,
    "exam_time_scale": 1.0,
}


DEFAULT_SETTINGS = {
    "preset": DEFAULT_PRESET,
    "interaction_mode": "type",          # "type" | "voice"
    "patient_voice": True,
    "assisted_mode": False,              # transcript visible while writing
    "scoring": dict(SCORING_DEFAULTS),
}


_SETTINGS_PATH = os.environ.get("PCM_CSE_SETTINGS") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "settings.json")


def load_settings() -> dict:
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    if os.path.exists(_SETTINGS_PATH):
        try:
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            scoring = settings["scoring"]
            scoring.update(stored.pop("scoring", {}) or {})
            settings.update(stored)
            settings["scoring"] = scoring
        except (OSError, ValueError):
            pass
    return settings


def save_settings(settings: dict) -> None:
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)


def assumption_manifest(settings: dict) -> list:
    """The list printed on the results screen so no interpretation is hidden."""
    scoring = settings.get("scoring", SCORING_DEFAULTS)
    preset = PRESETS[settings.get("preset", DEFAULT_PRESET)]
    items = [
        {
            "topic": "How the patient understands you",
            "value": "Scripted standardized patient, not a language model",
            "detail": (
                "The patient answers from a fixed set of authored facts, matched "
                "by trigger phrases and by the topic under discussion. That is "
                "how a real standardized patient works, and it is why she never "
                "invents a symptom, a medication or a result. It also means she "
                "can miss an unusual phrasing, and that a question the case does "
                "not script has no answer to give. When that happens she says so "
                "rather than guessing. Nothing here is natural-language "
                "understanding, and no score should be read as though it were."),
            "status": "design-decision",
        },
        {
            "topic": "What an examination costs you",
            "value": "Its configured duration, out of the encounter clock, once",
            "detail": (
                "Examinations are serial and occupy real encounter time, so a "
                "complete examination cannot be performed in the last ten "
                "seconds. One begun too late to finish is recorded as "
                "interrupted and releases nothing. Shortened durations are an "
                "assisted practice condition and are labelled as such on the "
                "results."),
            "status": "design-decision",
        },
        {
            "topic": "Clinical review of the cases",
            "value": "No clinician has approved any case",
            "detail": (
                "Two cases have had their management direction checked against "
                "published guidelines during the build, one has had an internal "
                "consistency check, and one has had no review at all. Automated "
                "guideline retrieval is not clinical validation. The per-case "
                "status and its sources appear on the results screen."),
            "status": "limitation",
        },
        {
            "topic": "Timing preset",
            "value": preset["label"],
            "detail": "Encounter %d:%02d, organization %d:%02d, note %d:%02d." % (
                preset["encounter_s"] // 60, preset["encounter_s"] % 60,
                preset["organize_s"] // 60, preset["organize_s"] % 60,
                preset["note_s"] // 60, preset["note_s"] % 60,
            ) + ((" " + preset["modification_note"]) if preset["modified"] else ""),
            "status": "practice-mod" if preset["modified"] else "confirmed",
        },
        {
            "topic": "VINDICATE expansion",
            "value": ", ".join(v["name"] for v in VINDICATE.values()),
            "detail": MNEMONIC_PROVENANCE["VINDICATE"],
            "status": "provisional",
        },
        {
            "topic": "MOTHERR expansion",
            "value": ", ".join(v["name"] for v in MOTHERR.values()),
            "detail": MNEMONIC_PROVENANCE["MOTHERR"],
            "status": "provisional",
        },
        {
            "topic": "Partial credit",
            "value": "on" if scoring.get("partial_credit") else "off (all-or-nothing per row)",
            "detail": scoring.get("partial_credit_note", ""),
            "status": "assumption",
        },
        {
            "topic": "Unused encounter time",
            "value": "carried over" if scoring.get("carry_over_unused_encounter_time") else "not carried over",
            "detail": scoring.get("carry_over_note", ""),
            "status": "assumption",
        },
        {
            "topic": "Unapproved abbreviations",
            "value": scoring.get("unapproved_abbreviation_is", "advisory"),
            "detail": scoring.get("unapproved_abbreviation_note", ""),
            "status": "assumption",
        },
        {
            "topic": "Passing cutoff",
            "value": "none",
            "detail": scoring.get("passing_cutoff_note", ""),
            "status": "confirmed-absent",
        },
        {
            "topic": "ROS requirement",
            "value": "%d systems x %d symptoms" % (
                scoring.get("ros_systems_required", 3),
                scoring.get("ros_symptoms_per_system", 3)),
            "detail": "Grading table: '3 symptoms from 3 different pertinent "
                      "systems (Total of 9 symptoms)'. Which systems are "
                      "pertinent is set per case.",
            "status": "confirmed",
        },
    ]
    return items
