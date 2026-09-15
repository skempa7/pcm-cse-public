"""The virtual physical examination.

The catalog is deliberately **universal**: every case exposes the same
maneuvers in the same order, so the action list can never leak which
examination this particular case rewards.  What differs per case is only which
findings a maneuver releases.

Findings are released only when the student's action is specific enough --
naming a body region *and* an examination method, and, where the maneuver has
components, covering them.  "I do a physical exam" resolves to nothing.

Durations are the app's own realism device, not a course rule: a maneuver
occupies encounter time, so a complete examination cannot be performed
instantly.  See docs/requirements-map.md section 9.
"""

from __future__ import annotations

import re
import json
from pathlib import Path
from copy import deepcopy

from . import nlp

# Natural phrasings for maneuver components, so "costovertebral angle
# tenderness" ticks the component written as "cva tenderness".
COMPONENT_ALIASES = {
    "cva tenderness": ["cva tenderness", "costovertebral angle tenderness",
                       "costovertebral tenderness", "cva tender", "kidney punch",
                       "murphy punch", "cva"],
    "murphy": ["murphy", "murphy sign", "murphy's sign"],
    "mcburney": ["mcburney", "mcburney point", "mcburney's point"],
    "four quadrants": ["four quadrants", "4 quadrants", "all four quadrants",
                       "all quadrants", "each quadrant"],
    "all four quadrants": ["all four quadrants", "four quadrants", "4 quadrants",
                           "all quadrants"],
    "one quadrant": ["one quadrant", "a single quadrant"],
    "on skin": ["on skin", "on the skin", "directly on skin", "skin to skin",
                "under the gown", "against the skin", "bare skin"],
    "mouth open": ["mouth open", "open mouth", "breathe through your mouth",
                   "breathing through the mouth", "open your mouth"],
    "compare side to side": ["compare side to side", "side to side", "comparing sides",
                             "both sides", "side by side", "bilaterally"],
    "aortic": ["aortic", "second right", "2nd right"],
    "pulmonic": ["pulmonic", "second left", "2nd left"],
    "tricuspid": ["tricuspid", "lower left sternal"],
    "mitral": ["mitral", "apex", "apical"],
    "anterior": ["anterior", "front", "in front"],
    "posterior": ["posterior", "back", "from behind"],
    "lateral": ["lateral", "side", "axilla"],
    "thoracic": ["thoracic", "t-spine", "tspine", "mid back", "upper back",
                 "t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9", "t10",
                 "t11", "t12"],
    "lumbar": ["lumbar", "l-spine", "lspine", "low back", "lower back",
               "l1", "l2", "l3", "l4", "l5"],
    "cervical": ["cervical", "c-spine", "cspine", "neck"],
    "ask patient to swallow": ["swallow", "sip of water", "take a sip"],
    "light": ["light", "lightly", "superficial"],
    "deep": ["deep", "deeply"],
    "rebound": ["rebound", "rebound tenderness"],
    "guarding": ["guarding"],
}

# Method vocabulary -----------------------------------------------------------
METHODS = {
    "inspect": ["inspect", "look at", "look in", "observe", "examine visually",
                "visualize", "view", "check the appearance", "eyeball"],
    "palpate": ["palpate", "palpation", "feel", "press on", "push on",
                "check for tenderness"],
    "percuss": ["percuss", "percussion", "tap on"],
    "auscultate": ["auscultate", "auscultation", "listen to", "listen for",
                   "stethoscope on"],
    # "check" alone is far too loose -- "check a pregnancy test" is a plan,
    # not an examination -- so the special-test cues all name an object.
    "special": ["check for", "check the", "check your", "assess", "elicit",
                "maneuver", "test for", "special test", "sign", "range of motion"],
}


def _m(mid, region, method, label, components, duration, claim, scope, notes=""):
    return {
        "id": mid,
        "region": region,
        "method": method,
        "label": label,
        "components": components,
        "duration_s": duration,
        "claim_concept": claim,
        "scope": scope,
        "notes": notes,
    }


# --------------------------------------------------------------------------
# Courtesy, consent and technique actions.  Assessed as *stated* behavior.
# --------------------------------------------------------------------------
COURTESY = [
    {"id": "introduce", "label": "Introduce yourself as a student doctor",
     "duration_s": 8, "triggers": ["my name is", "i am a student doctor",
     "i'm a student doctor", "student doctor", "introduce myself", "introduced myself",
     # Plain role phrases, because a name usually sits between the pronoun and
     # the role: "I'm Sam, a medical student" never matched "i'm a medical
     # student", and the coach then asked for an introduction all encounter.
     # A question ("are you a medical student?") and a third-party sentence
     # ("your medical student saw me") are refused by the courtesy guards.
     "medical student", "year student", "year medical student",
     "i'll be seeing you", "my name's", "i am a medical student", "i'm a medical student",
     "medical student working with"]},
    {"id": "confirm_name", "label": "Confirm patient name / preferred address",
   "duration_s": 6,
   # This item has TWO components. The learner may do either independently and
   # in their own words, so the triggers cover ordinary phrasings, and the
   # components are tracked separately: asking the name does not establish that
   # the preferred form of address was asked. The completion rule for scoring
   # is unchanged -- any trigger still records the courtesy -- but the
   # components let the checklist and the coach say what is actually
   # outstanding instead of showing the whole item as undone.
   "components": {
     "name": ["can you confirm your name", "your full name", "what is your name",
              "what's your name", "whats your name", "may i have your name",
              "could i get your name", "can you tell me your name",
              "tell me your name", "state your name", "your name for me",
              "confirm your name", "who am i speaking", "who am i talking"],
     "preferred_address": ["how would you like to be addressed",
              # Declarative order and contracted forms: "what you'd like me to
              # call you" reads naturally and matched none of the authored
              # interrogative phrasings.
              "like me to call you", "like to be called", "prefer to be addressed",
              "what would you like me to call you", "what should i call you",
              "how should i address you", "is it alright if i call you",
              "may i call you", "what do you prefer to be called",
              "what would you prefer i call you", "preferred name",
              "how do you like to be addressed"],
   },
   "triggers": ["how would you like to be addressed", "what would you like me to call you",
                "can you confirm your name", "is it alright if i call you", "may i call you",
                "your full name", "what is your name", "what's your name", "whats your name",
                "may i have your name", "could i get your name", "can you tell me your name",
                "tell me your name", "state your name", "your name for me",
                "confirm your name", "what should i call you", "how should i address you",
                "who am i speaking", "who am i talking", "preferred name"]},
    {"id": "hand_hygiene", "label": "Wash or sanitize hands",
     "duration_s": 12, "triggers": ["wash my hands", "washing my hands",
     "washed my hands", "sanitize my hands", "sanitized my hands", "hand sanitizer",
     "hand hygiene", "clean my hands", "cleaned my hands", "foam in", "gel my hands"]},
    {"id": "gloves", "label": "Apply gloves before the physical exam",
     "duration_s": 8, "triggers": ["put on gloves", "apply gloves", "glove up",
     "donning gloves", "i'll glove"]},
    {"id": "consent_exam", "label": "Explain the exam and ask permission",
     "duration_s": 8, "triggers": ["is it okay if i examine", "may i examine",
     "would it be alright if i", "i'd like to examine you", "with your permission",
     "do i have your permission", "is that okay with you", "if you don't mind"]},
    {"id": "drape", "label": "Drape the patient",
     "duration_s": 10, "triggers": ["drape", "cover you with", "keep you covered",
     "place a sheet", "gown back down"]},
    {"id": "gown_help", "label": "Offer help with the gown",
     "duration_s": 6, "triggers": ["help you with your gown", "lower your gown",
     "open your gown", "untie your gown", "let me help you with the gown"]},
    {"id": "position_help", "label": "Offer help lying down or sitting up",
     "duration_s": 8, "triggers": ["help you lie", "help you lay", "help you sit up",
     "let me help you down", "let me help you up", "lie back for me",
     "can you lie down"]},
    {"id": "comfort_check", "label": "Check the patient's comfort",
     "duration_s": 6, "triggers": ["are you comfortable", "let me know if this hurts",
     "tell me if this is uncomfortable", "is this okay", "am i hurting you",
     "let me know if anything is tender"]},
    {"id": "warn_cold", "label": "Warn before touching (stethoscope/hands)",
     "duration_s": 5, "triggers": ["this may be cold", "this might be cold",
     "going to be a little cold", "warm my hands", "warm up the stethoscope"]},
]

# Where a courtesy declares sub-components, its trigger list is derived from
# them. Maintaining two parallel lists let them drift: the component list knew
# "what would you prefer i call you" while the trigger list did not, so the
# turn earned nothing at all.
for _entry in COURTESY:
    _components = _entry.get("components")
    if _components:
        _merged = list(_entry.get("triggers") or [])
        for _phrases in _components.values():
            for _phrase in _phrases:
                if _phrase not in _merged:
                    _merged.append(_phrase)
        _entry["triggers"] = _merged


COURTESY_BY_ID = {c["id"]: c for c in COURTESY}


# --------------------------------------------------------------------------
# The universal maneuver catalog.
# --------------------------------------------------------------------------
CATALOG = [
    # --- General -----------------------------------------------------------
    _m("general_inspect", "General", "inspect", "General appearance",
       [], 10, "general_appearance", ["general"],
       "Overall appearance, distress, position, colour, work of breathing."),
    _m("vitals_review", "General", "special", "Review the vital signs provided",
       [], 8, "vitals", ["vitals"],
       "Station vitals are supplied; reviewing them is not the same as taking them."),

    # --- HEENT -------------------------------------------------------------
    _m("heent_eyes", "HEENT", "inspect", "Inspect eyes / pupils",
       ["pupils", "conjunctivae", "sclerae", "cornea", "extraocular movements", "fundoscopic"],
       25, "heent_eyes", ["heent.eyes"]),
    _m("heent_ears", "HEENT", "inspect", "Otoscopic exam of ears",
       ["right ear", "left ear"], 30, "heent_ears", ["heent.ears"]),
    _m("heent_nose", "HEENT", "inspect", "Inspect nose with light source",
       ["right naris", "left naris"], 20, "heent_nose", ["heent.nose"]),
    _m("heent_throat", "HEENT", "inspect", "Inspect mouth and throat with light",
       ["tongue blade", "oropharynx", "tonsils"], 25, "heent_oropharynx",
       ["heent.throat"]),
    _m("heent_sinuses", "HEENT", "palpate", "Palpate / percuss sinuses",
       ["frontal", "maxillary"], 20, "heent_sinuses", ["heent.sinuses"]),
    _m("lymph_nodes", "HEENT", "palpate", "Palpate lymph nodes",
       ["cervical", "submandibular", "supraclavicular", "axillary"],
       30, "lymph_nodes", ["lymph"]),
    _m("thyroid", "Neck", "palpate", "Palpate thyroid",
       ["ask patient to swallow"], 25, "thyroid", ["thyroid"],
       "Anterior or posterior approach; the patient must be asked to swallow."),
    _m("neck_rom", "Neck", "special", "Neck range of motion / meningeal signs",
       ["flexion", "rotation", "brudzinski", "kernig"], 25, "msk_rom", ["neck"]),

    # --- Heart -------------------------------------------------------------
    _m("heart_auscultate", "Heart", "auscultate", "Auscultate heart",
       ["aortic", "pulmonic", "tricuspid", "mitral", "on skin"],
       40, "heart_auscultation", ["heart"],
       "The course expects at least four listening posts, on skin."),
    _m("heart_inspect_palpate", "Heart", "palpate", "Inspect / palpate precordium, PMI",
       ["pmi", "thrills", "heaves"], 20, "heart_auscultation", ["heart.precordium"]),
    _m("jvd", "Heart", "inspect", "Assess jugular venous distention",
       [], 15, "heart_auscultation", ["heart.jvd"]),
    _m("peripheral_pulses", "Heart", "palpate", "Palpate peripheral pulses",
       ["radial", "dorsalis pedis", "posterior tibial", "carotid"],
       25, "extremities", ["extremities.pulses"]),
    # A bruit is a sound. It used to be reported by the pulse PALPATION, which
    # let a note claim an auscultatory finding from an examination that never
    # put a stethoscope on the neck.
    _m("carotid_auscultate", "Heart", "auscultate", "Auscultate carotid arteries",
       ["right", "left"], 20, "carotids", ["heart.carotids"]),

    # --- Lungs -------------------------------------------------------------
    _m("lungs_auscultate", "Lungs", "auscultate", "Auscultate lungs",
       ["anterior", "posterior", "lateral", "mouth open", "on skin",
        "compare side to side"],
       50, "lungs_auscultation", ["lungs"],
       "The course expects six posterior fields, mouth open, on skin, "
       "comparing sides."),
    _m("lungs_percuss", "Lungs", "percuss", "Percuss lung fields",
       ["anterior", "posterior", "compare side to side"],
       30, "lungs_percussion", ["lungs.percussion"]),
    _m("lungs_fremitus", "Lungs", "palpate", "Assess tactile fremitus",
       ["compare side to side"], 25, "lungs_fremitus", ["lungs.fremitus"]),
    _m("chest_inspect", "Lungs", "inspect", "Inspect chest wall",
       ["symmetry", "scars", "accessory muscle use"],
       15, "lungs_auscultation", ["lungs.inspection"]),
    _m("chest_wall_palpate", "Lungs", "palpate", "Palpate chest wall",
       ["costochondral junctions", "ribs"], 20, "msk_palpation",
       ["chest_wall"]),

    # --- Abdomen -----------------------------------------------------------
    _m("abd_inspect", "Abdomen", "inspect", "Inspect abdomen",
       ["contour", "scars", "distention", "pulsation"], 12, "abdomen_palpation",
       ["abdomen.inspection"]),
    _m("abd_auscultate", "Abdomen", "auscultate", "Auscultate abdomen",
       ["all four quadrants", "one quadrant", "bruits"],
       25, "abdomen_auscultation", ["abdomen.auscultation"],
       "Auscultation precedes palpation and percussion."),
    _m("abd_percuss", "Abdomen", "percuss", "Percuss abdomen",
       ["four quadrants", "liver span", "shifting dullness"],
       30, "abdomen_percussion", ["abdomen.percussion"]),
    _m("abd_palpate", "Abdomen", "palpate", "Palpate abdomen",
       ["light", "deep", "four quadrants", "rebound", "guarding"],
       40, "abdomen_palpation", ["abdomen.palpation"]),
    _m("abd_special", "Abdomen", "special", "Abdominal special tests",
       ["murphy", "mcburney", "rovsing", "psoas", "obturator", "cva tenderness"],
       30, "abdomen_palpation", ["abdomen.special"]),

    # --- Musculoskeletal ---------------------------------------------------
    _m("msk_inspect", "Musculoskeletal", "inspect", "Inspect the affected area",
       ["swelling", "deformity", "erythema"], 12, "msk_palpation", ["msk.inspection"]),
    _m("msk_palpate", "Musculoskeletal", "palpate", "Palpate the affected area",
       ["point tenderness", "paraspinal musculature", "midline spine"],
       25, "msk_palpation", ["msk.palpation"]),
    _m("msk_rom", "Musculoskeletal", "special", "Range of motion",
       ["flexion", "extension", "side bending", "rotation"],
       30, "msk_rom", ["msk.rom"]),
    _m("msk_strength", "Musculoskeletal", "special", "Muscle strength testing",
       ["upper extremity", "lower extremity", "pronator drift"], 30, "neuro_motor", ["neuro.motor"]),
    _m("msk_slr", "Musculoskeletal", "special", "Straight leg raise",
       ["seated", "supine", "right", "left"], 25, "special_slr", ["msk.slr"]),
    _m("gait", "Musculoskeletal", "special", "Observe gait",
       [], 20, "neuro_gait", ["neuro.gait"]),

    # --- Neurologic --------------------------------------------------------
    _m("neuro_cn", "Neurologic", "special", "Cranial nerve examination",
       ["cn ii", "cn iii-iv-vi", "cn v", "cn vii", "cn viii", "cn ix-x",
        "cn xi", "cn xii"], 60, "neuro_cranial_nerves", ["neuro.cn"],
       "Cranial nerve I is not routinely tested; document only what you test."),
    _m("neuro_sensory", "Neurologic", "special", "Sensory examination",
       ["light touch", "pinprick", "vibration", "proprioception"],
       35, "neuro_sensory", ["neuro.sensory"]),
    _m("neuro_reflexes", "Neurologic", "special", "Deep tendon reflexes",
       ["biceps", "triceps", "patellar", "achilles", "babinski"],
       35, "neuro_reflexes", ["neuro.reflexes"]),
    _m("neuro_coordination", "Neurologic", "special", "Coordination / cerebellar",
       ["finger to nose", "heel to shin", "romberg", "rapid alternating"],
       30, "neuro_gait", ["neuro.coordination"]),
    _m("mental_status", "Neurologic", "special", "Mental status / orientation",
       ["orientation", "memory", "attention", "naming"], 25, "general_appearance",
       ["neuro.mental"]),

    # --- Skin / extremities ------------------------------------------------
    _m("skin_inspect", "Skin", "inspect", "Inspect skin",
       ["chest", "back", "arms", "legs", "palms", "soles"],
       35, "skin_inspection", ["skin"]),
    _m("skin_palpate", "Skin", "palpate", "Palpate the skin concern",
       ["tenderness", "warmth", "induration", "fluctuance"],
       25, "skin_palpation", ["skin.palpation"]),
    _m("extremities", "Extremities", "inspect", "Inspect / palpate extremities",
       ["edema", "capillary refill", "clubbing", "cyanosis", "calf tenderness", "calf symmetry", "nail beds"],
       25, "extremities", ["extremities"]),

    # --- Osteopathic structural exam --------------------------------------
    _m("osteo_screen", "Osteopathic", "palpate", "Osteopathic structural screen",
       ["cervical", "thoracic", "lumbar", "sacrum", "ribs"],
       45, "osteopathic", ["osteopathic"],
       "Name the level examined; findings are released by region."),
]

CATALOG += [
    _m("orthostatic_vitals", "General", "special", "Orthostatic vital signs",
       ["supine", "standing_1min", "standing_3min"], 180, "orthostatic_vitals", ["vitals.orthostatic"],
       "Obtain supine baseline after 5 minutes resting, then standing at 1 and 3 minutes. The full demonstration includes the resting interval; help the patient stand and stop if unsafe."),
    _m("neuro_dix_hallpike", "Neurologic", "special", "Dix–Hallpike positioning test",
       ["cervical_suitability", "right", "left"], 60, "positional_nystagmus", ["neuro.positional"],
       "Check cervical suitability and explain positioning first. Select sides assessed. This illustrates selection and stated technique; it cannot verify hands-on proficiency."),
]

CATALOG_BY_ID = {m["id"]: m for m in CATALOG}

REGION_ORDER = ["General", "HEENT", "Neck", "Heart", "Lungs", "Abdomen",
                "Musculoskeletal", "Neurologic", "Skin", "Extremities",
                "Osteopathic"]


# --------------------------------------------------------------------------
# Examinations the standardized patient refuses (syllabus guideline 7).
# --------------------------------------------------------------------------
# `strong` triggers name a procedure and fire on their own.  `weak` triggers
# name only a body region, so they fire only alongside an examination intent --
# otherwise "any vaginal discharge?" (a history question) would be misread as a
# proposal to perform a pelvic examination.
REFUSABLE = {
    "rectal": {
        "label": "Rectal examination",
        "strong": ["digital rectal", "dre", "prostate exam", "rectal exam",
                   "guaiac", "hemoccult"],
        "weak": ["rectal", "rectum", "prostate", "anus", "anal"],
        "doc": "Rectal exam refused",
    },
    "genital": {
        "label": "Genital examination",
        "strong": ["genital exam", "male exam", "testicular exam", "scrotal exam",
                   "hernia exam", "penile exam"],
        "weak": ["genital", "penile", "penis", "testicular", "testicle",
                 "scrotal", "scrotum"],
        "doc": "Genital exam refused",
    },
    "gyn": {
        "label": "Gynecological / pelvic examination",
        "strong": ["pelvic exam", "speculum", "bimanual", "female exam",
                   "pap smear", "gynecologic exam", "gynecological exam",
                   "internal exam"],
        "weak": ["pelvic", "gynecolog", "vaginal", "vagina", "cervix", "adnexa"],
        "doc": "Pelvic exam refused",
    },
    "breast": {
        "label": "Breast examination",
        "strong": ["breast exam", "clinical breast examination"],
        "weak": ["breast"],
        "doc": "Breast exam refused",
    },
    "corneal": {
        "label": "Corneal reflex",
        "strong": ["corneal reflex"],
        "weak": ["cornea"],
        "doc": "Corneal reflex refused",
    },
}

# Words that mark an utterance as proposing an examination rather than asking a
# history question.
_EXAM_INTENT = [
    "exam", "examine", "examination", "inspect", "perform", "palpate",
    "do a ", "do the ", "do an ", "would do", "check your", "check the",
    "check for", "look at", "assess", "i would like to do",
    "at this point i would", "i need to do", "indicated",
    # Unambiguous declarations of a maneuver. Bare "test" is deliberately
    # excluded -- "check a pregnancy test" is a plan, not an examination.
    "i will test", "i'll test", "let me test", "i am going to test",
    "i'm going to test", "im going to test", "i will elicit", "i will observe",
    "i will listen", "i will feel", "i will look",
]


def _has_exam_intent(text: str) -> bool:
    return any(nlp.normalize(c) in text for c in _EXAM_INTENT)

# The syllabus form: "At this point, I would do a (xxx) exam."
_PROPOSE_CUES = [
    "at this point i would", "i would do a", "i would perform", "i would like to perform",
    "i would like to do", "normally i would", "i would examine", "i would check",
    "i would need to do", "would be indicated", "i would want to do",
]


def detect_refusable(utterance: str):
    """Return (key, proposed_properly) when a refusable exam is *proposed*.

    A history question that merely mentions the body region -- "any vaginal
    discharge?", "any blood in your stool?" -- is not a proposal and must not
    trigger a refusal.
    """
    text = nlp.normalize(utterance)
    intent = _has_exam_intent(text)
    proposed = any(nlp.normalize(c) in text for c in _PROPOSE_CUES)
    for key, spec in REFUSABLE.items():
        for trig in spec["strong"]:
            if _word_in(trig, text):
                return key, proposed
    if not intent:
        return None, False
    for key, spec in REFUSABLE.items():
        for trig in spec["weak"]:
            if _word_in(trig, text):
                return key, proposed
    return None, False


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------

_GENERIC_EXAM_PHRASES = [
    "physical exam", "physical examination", "examine the patient", "exam the patient",
    "do an exam", "perform an exam", "full exam", "complete exam", "head to toe",
    "i examine you", "i'll examine you", "let me examine you", "general exam",
    "check you out", "look you over",
]


def _region_terms(region: str):
    base = {
        "General": ["general", "appearance", "overall"],
        "HEENT": ["heent", "head", "eye", "ear", "nose", "throat", "mouth",
                  "sinus", "oropharynx", "tonsil", "lymph", "conjunctiva",
                  "sclera", "pupil", "fundus", "fundoscop", "otoscop",
                  "tympanic membrane", "naris", "nares", "pharyn", "uvula",
                  "turbinate", "canal", "node"],
        "Neck": ["neck", "thyroid", "cervical"],
        "Heart": ["heart", "cardiac", "precordium", "pmi", "jvd", "pulse",
                  "cardiovascular"],
        "Lungs": ["lung", "chest", "respiratory", "breath sound", "thorax",
                  "pulmonary", "fremitus", "chest wall"],
        "Abdomen": ["abdomen", "abdominal", "belly", "stomach", "bowel",
                    "quadrant", "epigastr", "murphy", "mcburney", "cva",
                    "costovertebral", "kidney", "flank", "rovsing", "psoas",
                    "obturator", "rebound", "guarding"],
        "Musculoskeletal": ["back", "spine", "joint", "muscle", "knee", "ankle",
                            "shoulder", "hip", "range of motion", "strength",
                            "straight leg", "gait", "extremity motion"],
        "Neurologic": ["neuro", "cranial nerve", "reflex", "sensation", "sensory",
                       "coordination", "romberg", "mental status", "orientation",
                       "babinski"],
        "Skin": ["skin", "rash", "lesion", "dermat"],
        "Extremities": ["extremit", "leg", "arm", "edema", "capillary refill",
                        "clubbing", "cyanosis", "peripheral pulse"],
        "Osteopathic": ["osteopathic", "structural", "somatic", "paraspinal",
                        "tart", "tissue texture", "t-spine", "tspine", "lspine",
                        "thoracic spine", "lumbar spine"],
    }
    return base.get(region, [region.lower()])


def _word_in(term: str, text: str) -> bool:
    """Word-start matching, shared with the rest of the app (see nlp.word_in)."""
    return nlp.word_in(term, text)


def _component_named(component: str, text: str) -> bool:
    for form in COMPONENT_ALIASES.get(component, [component]):
        form = nlp.normalize(form)
        if form and (form in text or _word_in(form, text)):
            return True
    return False


# Explicit claims of complete coverage, mapped to the components each one
# actually covers.
#
# Two rules learned the hard way. The phrases are WORD-BOUNDED, because
# "carefully" contains "full" and used to earn every component of a heart
# examination including "on skin". And adverbs of manner -- "thoroughly",
# "completely", "carefully" -- are not coverage claims at all: the rubric wants
# the components named, not the effort described.
_SITE_WORDS = ("anterior", "posterior", "lateral", "quadrant", "post",
               "aortic", "pulmonic", "tricuspid", "mitral", "field",
               "right", "left", "cervical", "thoracic", "lumbar", "sacrum")


def _is_site(comp):
    c = comp.lower()
    return any(w in c for w in _SITE_WORDS)


_COVERAGE_CLAIMS = [
    # Heart: the four auscultatory posts.
    (["all four posts", "four posts", "all four areas", "all four valve areas",
      "all four auscultatory areas", "aortic pulmonic tricuspid and mitral"],
     lambda c: c in ("aortic", "pulmonic", "tricuspid", "mitral")),
    # Lungs: the fields.
    (["all lung fields", "all fields", "all of the lung fields",
      "every lung field"],
     lambda c: c in ("anterior", "posterior", "lateral")),
    (["anterior and posterior", "front and back", "back and front"],
     lambda c: c in ("anterior", "posterior")),
    # Abdomen: the quadrants.
    (["all four quadrants", "four quadrants", "all quadrants",
      "every quadrant", "each quadrant", "in all 4 quadrants"],
     lambda c: "quadrant" in c.lower()),
    # Side-to-side comparison is its own component.
    (["compare side to side", "comparing side to side", "side to side",
      "comparing both sides", "compare both sides"],
     lambda c: "side to side" in c.lower()),
    (["bilaterally", "both sides", "on both sides", "right and left"],
     lambda c: c.lower() in ("right", "left") or "side to side" in c.lower()
     or c.lower().startswith("right ") or c.lower().startswith("left ")),
    # A genuine whole-maneuver claim, in the words a student would use.
    (["all of the components", "every component", "the complete examination",
      "a complete examination of", "in full"],
     lambda c: True),
]


def resolve(utterance: str):
    """Map a free-text examination instruction to a catalog maneuver.

    Returns a dict:
      {"status": "performed"|"vague"|"refusable"|"none",
       "maneuver": <catalog entry or None>,
       "components": [...],          # components the student actually named
       "reason": str}
    """
    text = nlp.normalize(utterance)
    if not text:
        return {"status": "none", "maneuver": None, "components": [], "reason": ""}

    key, proposed = detect_refusable(utterance)
    if key:
        return {"status": "refusable", "maneuver": None, "components": [],
                "refusable": key, "proposed_properly": proposed,
                "reason": "Refusable examination named."}

    # Which method was named?
    method = None
    for m, cues in METHODS.items():
        if any(_word_in(c, text) for c in cues):
            method = m
            break

    # Which region was named?  Word-boundary matching, or "tart" (a palpation
    # acronym) fires on "start" and every question about onset resolves to the
    # osteopathic exam.
    regions = [r for r in REGION_ORDER
               if any(_word_in(t, text) for t in _region_terms(r))]

    # A history question that merely names a body region ("any cough, shortness
    # of breath or chest pain?") is not an examination instruction.  Require a
    # method word or an explicit examination intent before treating it as one.
    if not method and not _has_exam_intent(text) \
            and not any(nlp.normalize(p) in text for p in _GENERIC_EXAM_PHRASES):
        return {"status": "none", "maneuver": None, "components": [], "reason": ""}

    if not regions:
        if any(nlp.normalize(p) in text for p in _GENERIC_EXAM_PHRASES):
            return {
                "status": "vague", "maneuver": None, "components": [],
                "reason": "No body region named. Name a region and an "
                          "examination method (for example, 'auscultate the "
                          "lungs posteriorly').",
            }
        return {"status": "none", "maneuver": None, "components": [], "reason": ""}

    # Score candidate maneuvers.
    best, best_score = None, 0.0
    for man in CATALOG:
        if man["region"] not in regions:
            continue
        score = 1.0
        if method and man["method"] == method:
            score += 2.0
        elif method:
            score -= 0.5
        label_terms = nlp.normalize(man["label"]).split()
        score += 0.35 * sum(1 for t in label_terms if len(t) > 3 and _word_in(t, text))
        for comp in man["components"]:
            if _component_named(comp, text):
                score += 0.8
        if score > best_score:
            best, best_score = man, score

    if best is None:
        return {"status": "vague", "maneuver": None, "components": [],
                "reason": "Region recognised but no maneuver matched."}

    if not method and best_score < 2.0:
        return {
            "status": "vague", "maneuver": None, "components": [],
            "reason": "No examination method named for the %s. Say what you do "
                      "(inspect, palpate, percuss, auscultate, or a named test)."
                      % regions[0].lower(),
        }

    components = [c for c in best["components"] if _component_named(c, text)]
    for phrases, covers in _COVERAGE_CLAIMS:
        if not any(nlp.word_in(w, text) for w in phrases):
            continue
        # A coverage claim adds only the components it actually covers. Saying
        # "anterior and posterior" is a claim about WHERE the stethoscope went;
        # it buys the sites, not the technique components such as "mouth open".
        for comp in best["components"]:
            if covers(comp) and comp not in components:
                components.append(comp)

    return {"status": "performed", "maneuver": best, "components": components,
            "reason": ""}


# 2026-09-15: one authored sequence owns action labels, component selection,
# readable duration and visual stages. Case findings never enter this file.
DEMONSTRATIONS = json.loads(Path(__file__).with_name("exam_demonstrations.json").read_text())


def demonstration(maneuver_id, components):
    requested = set(components or [])
    options = [v for v in DEMONSTRATIONS.values() if v["maneuver_id"] == maneuver_id]
    exact = next((v for v in options if set(v["components"]) == requested), None)
    if exact:
        return deepcopy(exact)
    # Partial coach/typed requests retain the same clinical/evidence semantics.
    # Modifiers describe technique; they must never select additional body sites.
    modifiers = {"on skin", "mouth open", "compare side to side", "four quadrants",
                 "right", "left", "supine", "seated", "cervical_suitability"}
    if maneuver_id in ("carotid_auscultate", "heent_ears", "orthostatic_vitals"):
        modifiers -= {"right", "left", "supine", "seated"}
    if maneuver_id == "msk_slr":
        modifiers -= {"right", "left"}
    target = requested - modifiers
    steps, chosen, covered = [], [], set()
    for option in options:
        option_set = set(option["components"])
        if not target or not (option_set & target):
            continue
        # Side/position alternatives must not be silently combined.
        if maneuver_id == "msk_slr" and not ((option_set & {"supine", "seated"}) <= requested):
            continue
        option_steps = []
        for stage in option["steps"]:
            belongs = set(stage.get("covers", option["components"])) - modifiers
            if belongs & target:
                option_steps.append(deepcopy(stage))
                covered |= belongs & target
        if option_steps:
            chosen.append(option)
            steps.extend(option_steps)
            covered |= (option_set & target) if not any("covers" in x for x in option["steps"]) else set()
    if maneuver_id == "abd_auscultate" and requested == {"one quadrant"}:
        chosen = [DEMONSTRATIONS["abd_auscultate:sounds"]]
        steps = [deepcopy(chosen[0]["steps"][0])]
        covered = target
    if steps and covered == target:
        return {"key": maneuver_id + ":selected", "maneuver_id": maneuver_id,
                "label": CATALOG_BY_ID[maneuver_id]["label"], "components": list(components),
                "position": " / ".join(dict.fromkeys(v["position"] for v in chosen)),
                "steps": steps, "duration_s": sum(stage["seconds"] for stage in steps),
                "sources": list(dict.fromkeys(x for v in chosen for x in v["sources"]))}
    return None


def action_time(maneuver: dict, components, scale: float = 1.0) -> int:
    """Authored sequence duration; legacy noninteractive replay keeps its scale."""
    plan = demonstration(maneuver["id"], components)
    if plan:
        return max(4, int(round(plan["duration_s"] * scale)))
    base = maneuver["duration_s"]
    total = len(maneuver["components"])
    if total and components:
        base *= 0.45 + 0.55 * (len(components) / total)
    elif total:
        base *= 0.5
    return max(4, int(round(base * scale)))


def catalog_for_ui():
    """Grouped catalog for the action panel. Identical for every case."""
    groups = []
    for region in REGION_ORDER:
        items = [{
            "id": m["id"], "label": m["label"], "method": m["method"],
            "components": m["components"], "duration_s": max(
                (v["duration_s"] for v in DEMONSTRATIONS.values() if v["maneuver_id"] == m["id"]),
                default=m["duration_s"]),
            "notes": m["notes"],
            "actions": [deepcopy(v) for v in DEMONSTRATIONS.values() if v["maneuver_id"] == m["id"]],
        } for m in CATALOG if m["region"] == region and m["id"] != "vitals_review"]
        if items:
            groups.append({"region": region, "maneuvers": items})
    return groups
