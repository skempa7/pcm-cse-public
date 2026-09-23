"""What Scribbi can get wrong, and how each mistake is taught.

Every error type carries the words a student sees: a short name, why ambient
scribes make this kind of mistake, what it risks, how to fix it, and a habit
that catches it next time. The severity is the default for the type; a planted
instance may raise it (a flipped red-flag symptom is worse than a flipped
routine negative).
"""

from __future__ import annotations

GENERATOR_VERSION = "scribbi-1.0"

MODES = {
    "learn": {
        "label": "Learn",
        "tagline": "Scribbi coaches you line by line.",
        "detail": "See how many mistakes to find and what kinds, check any line against the visit, and get instant feedback on every change.",
        "errors": (3, 3),
        "hints": None,           # unlimited, free
        "show_count": True,
        "show_types": True,
        "instant_feedback": True,
        "sources": True,
        "timer_s": None,
    },
    "coached": {
        "label": "Coached",
        "tagline": "You lead. Hints when you need them.",
        "detail": "Scribbi tells you how many mistakes it made. Up to three hints point you to a section, then a line. Feedback comes when you sign.",
        "errors": (3, 4),
        "hints": 3,
        "show_count": True,
        "show_types": False,
        "instant_feedback": False,
        "sources": False,
        "timer_s": None,
    },
    "solo": {
        "label": "On your own",
        "tagline": "Like clinic: nobody tells you what's wrong.",
        "detail": "No count, no hints. The draft might have five mistakes, or none. Add a five-minute clock if you want the pressure.",
        "errors": (0, 5),
        "hints": 0,
        "show_count": False,
        "show_types": False,
        "instant_feedback": False,
        "sources": False,
        "timer_s": 300,
    },
}

HINT_COST = 5

# Relative frequency when choosing which mistakes to plant. Omissions and
# invented content are the most common scribe errors in published reviews, so
# they are weighted most heavily.
TYPE_WEIGHTS = {
    "dropped": 3.0,
    "fabricated_exam": 3.0,
    "fabricated_history": 2.0,
    "flipped": 2.5,
    "wrong_detail": 2.5,
    "misattributed": 2.0,
    "anchored_dx": 1.6,
    "unsupported_dx": 1.5,
    "allergy_conflict": 3.0,
}

ERROR_TYPES = {
    "fabricated_exam": {
        "label": "Invented exam",
        "short": "An exam that never happened",
        "icon": "stethoscope",
        "severity": "high",
        "why": "Scribes learn from thousands of notes where a normal exam is written out in full. When a system isn't examined, the familiar normal template can appear anyway.",
        "risk": "A normal finding nobody checked hides disease from the next clinician, and it's false documentation: the chart says you did something you didn't.",
        "fix": "Delete it, or write that the system wasn't examined.",
        "habit": "For every exam line, ask: did I actually look, listen, or touch?",
    },
    "fabricated_history": {
        "label": "Invented history",
        "short": "A question nobody asked",
        "icon": "question",
        "severity": "medium",
        "why": "Scribes pattern-match to note templates and can add routine negatives or details that never came up in the conversation.",
        "risk": "An invented answer closes a question that is still open, so nobody asks it again.",
        "fix": "Delete it. If it matters, ask the patient.",
        "habit": "Every 'denies' needs a question behind it.",
    },
    "flipped": {
        "label": "Flipped finding",
        "short": "A yes recorded as a no, or a no as a yes",
        "icon": "flip",
        "severity": "high",
        "why": "Negation is easy to lose. “No, not really… well, actually yes” can be summarized the wrong way, and so can a negative exam maneuver.",
        "risk": "A flipped symptom or sign sends the reasoning the wrong way: a red flag disappears, or a problem appears that the patient doesn't have.",
        "fix": "Correct it to what the patient said or what the exam showed.",
        "habit": "Check every 'denies', 'reports', 'positive' and 'negative' against the visit.",
    },
    "wrong_detail": {
        "label": "Wrong detail",
        "short": "A number, side, or dose that changed",
        "icon": "hash",
        "severity": "high",
        "why": "Numbers and sides are small words in a long conversation. “Fifteen” becomes “fifty,” days become weeks, right becomes left.",
        "risk": "A wrong side, dose, duration, or vital sign can change the diagnosis, the procedure site, or the prescription.",
        "fix": "Correct the value.",
        "habit": "Numbers, units, and left/right always get a second look.",
    },
    "misattributed": {
        "label": "Wrong person",
        "short": "A relative's history recorded as the patient's",
        "icon": "people",
        "severity": "medium",
        "why": "Visits mention family members. A scribe can attach a relative's diagnosis to the patient.",
        "risk": "It gives the patient a diagnosis they don't have, and it follows them into every future chart and insurance form.",
        "fix": "Remove it from the patient's own history. It belongs in family history.",
        "habit": "For every diagnosis in the history, ask: whose is this?",
    },
    "dropped": {
        "label": "Left out",
        "short": "Something important the patient said is missing",
        "icon": "gap",
        "severity": "medium",
        "why": "Omissions are the most common scribe error. Summaries compress, and what gets cut is often the patient's own worry, an allergy, or a key symptom.",
        "risk": "The next clinician never learns it: the patient's concern goes unanswered, or an allergy or red flag is lost.",
        "fix": "Add it back.",
        "habit": "Before signing, recall what mattered most to the patient. Is it in the note?",
    },
    "hands_on": {
        "label": "Hands-on finding",
        "short": "Scribbi can't feel",
        "icon": "hand",
        "severity": "medium",
        "why": "An ambient scribe only hears. Findings you palpated but didn't say out loud never reach the draft.",
        "risk": "Your structural exam, often the finding that links the spine to the organ, disappears from the record.",
        "fix": "Add your structural findings: the spinal level and what you felt.",
        "habit": "Palpatory findings are yours to document. Scribbi will never have them.",
    },
    "anchored_dx": {
        "label": "Anchored assessment",
        "short": "The wrong diagnosis leads",
        "icon": "anchor",
        "severity": "high",
        "why": "Suggested assessments can latch onto the most common explanation and underweight the red flags in the history and exam.",
        "risk": "Leading with the wrong diagnosis drives the wrong workup and the wrong treatment.",
        "fix": "Put the diagnosis the evidence best supports first.",
        "habit": "Does your leading diagnosis explain the red flags?",
    },
    "unsupported_dx": {
        "label": "Unsupported diagnosis",
        "short": "A diagnosis nothing in the visit supports",
        "icon": "ghost",
        "severity": "medium",
        "why": "Suggested differentials can include diagnoses that sound related but have no support in this patient's story or exam.",
        "risk": "Unsupported diagnoses clutter the chart and can trigger tests or labels the patient doesn't need.",
        "fix": "Remove it.",
        "habit": "Every diagnosis you list should be one you can defend from this visit.",
    },
    "allergy_conflict": {
        "label": "Allergy conflict",
        "short": "A plan that ignores a known allergy",
        "icon": "alert",
        "severity": "high",
        "why": "A suggested plan can follow the usual first-line treatment without checking what the patient told you about reactions.",
        "risk": "Prescribing a drug the patient reacted to can cause a serious allergic reaction.",
        "fix": "Remove the drug. The treatment choice has to account for the allergy.",
        "habit": "Read the plan against the allergy list, every time.",
    },
}

SEVERITY_LABELS = {"high": "Could change care", "medium": "Misleading", "low": "Minor"}

# --------------------------------------------------------------------------
# Invented examinations: a normal exam for a region the visit never examined.
# `claim` patterns say the exam is still being claimed after an edit.
# --------------------------------------------------------------------------
FABRICATED_EXAMS = {
    "HEENT": {
        "text": "Normocephalic, atraumatic, PERRLA, EOMI, TMs pearly gray bilaterally, oropharynx clear.",
        "claim": [r"perrl", r"\beomi\b", r"\btms?\b", r"tympanic", r"oropharyn", r"normocephalic", r"atraumatic", r"pupil"],
    },
    "Neck": {
        "text": "Supple, no lymphadenopathy, no thyromegaly, no JVD.",
        "claim": [r"supple", r"lymphadenopath", r"thyromegal", r"\bjvd\b", r"jugular"],
    },
    "Heart": {
        "text": "Regular rate and rhythm, no murmurs, rubs or gallops.",
        "claim": [r"regular rate", r"\brrr\b", r"murmur", r"gallop", r"\brubs?\b"],
    },
    "Lungs": {
        "text": "Clear to auscultation bilaterally, no wheezes, rales or rhonchi.",
        "claim": [r"clear to auscultation", r"\bcta", r"wheez", r"\brales\b", r"rhonch", r"crackle", r"breath sounds"],
    },
    "Abdomen": {
        "text": "Soft, non-tender, non-distended, normoactive bowel sounds, no hepatosplenomegaly.",
        "claim": [r"\bsoft\b", r"non ?-?tender", r"non ?-?distended", r"bowel sounds", r"hepatosplenomegal", r"organomegal"],
    },
    "Neurologic": {
        "text": "CN II–XII grossly intact, strength 5/5 and sensation intact throughout, DTRs 2+ and symmetric.",
        "claim": [r"\bcn\b", r"cranial nerve", r"strength", r"5/5", r"sensation", r"\bdtrs?\b", r"reflex"],
    },
    "Extremities": {
        "text": "No edema, cyanosis or clubbing, distal pulses 2+ bilaterally.",
        "claim": [r"edema", r"cyanosis", r"clubbing", r"pulses", r"2\+"],
    },
    "Musculoskeletal": {
        "text": "Full range of motion in all joints without tenderness or deformity.",
        "claim": [r"range of motion", r"\brom\b", r"deformit", r"joints?"],
    },
    "Skin": {
        "text": "Warm and dry, no rashes or lesions.",
        "claim": [r"warm", r"\bdry\b", r"rash", r"lesion"],
    },
}
# Sensitive examinations are never simply "not done": they need a proposal and
# consent. A scribe that documents one as normal is especially dangerous.
FABRICATED_SENSITIVE = {
    "gyn": ("Pelvic", "Normal external genitalia, no cervical motion tenderness, no adnexal tenderness or masses.",
            [r"genitalia", r"cervical motion", r"adnexa", r"pelvic", r"\bcmt\b", r"speculum", r"bimanual"]),
    "rectal": ("Rectal", "Normal sphincter tone, no masses, stool guaiac negative.",
               [r"sphincter", r"guaiac", r"rectal", r"\bmass"]),
    "genital": ("GU", "Normal external genitalia, no testicular masses or tenderness, no inguinal hernia.",
                [r"genitalia", r"testic", r"hernia", r"scrot"]),
    "breast": ("Breast", "No masses, skin changes or nipple discharge bilaterally.",
               [r"\bmass", r"nipple", r"breast"]),
}
NOT_EXAMINED = [r"\bnot (examined|performed|assessed|done|evaluated|tested|checked)\b",
                r"\bdeferred\b", r"\bdeclined\b", r"\brefused\b", r"\bwas not\b.*\bexam",
                r"\bno exam\b", r"\bnot obtained\b", r"\bomitted\b"]

# --------------------------------------------------------------------------
# Invented history: a topic the visit never touched.
# --------------------------------------------------------------------------
FABRICATED_HISTORY = [
    {"key": "travel", "label": "SH", "text": "Denies recent travel.",
     "detect": [r"travel", r"\btrip\b", r"abroad", r"flight", r"vacation", r"cruise"]},
    {"key": "sick_contacts", "label": "HPI", "text": "No sick contacts at home or work.",
     "detect": [r"sick contact", r"anyone .{0,20}sick", r"around .{0,20}sick", r"exposed", r"exposure"]},
    {"key": "vaccines", "label": "PMH", "text": "Immunizations are up to date.",
     "detect": [r"vaccin", r"immuniz", r"\bshots?\b", r"booster", r"flu shot"]},
    {"key": "trauma", "label": "HPI", "text": "Denies recent trauma or falls.",
     "detect": [r"trauma", r"\bfall", r"\bfell\b", r"injur", r"accident", r"\bhit\b", r"lifting"]},
    {"key": "weight", "label": "ROS", "text": "Denies recent weight change.",
     "detect": [r"weight"]},
    {"key": "sleep", "label": "SH", "text": "Sleeping well at night.",
     "detect": [r"sleep", r"insomnia", r"\bwake", r"waking", r"\bnight"]},
    {"key": "mood", "label": "ROS", "text": "Denies depressed mood or anxiety.",
     "detect": [r"\bmood", r"depress", r"anxi", r"stress", r"\bsad\b", r"worried", r"\bdown\b"]},
    {"key": "diet", "label": "SH", "text": "Eats a balanced diet.",
     "detect": [r"\bdiet", r"\beat", r"\bfood", r"\bmeals?\b"]},
    {"key": "exercise", "label": "SH", "text": "Exercises three times a week.",
     "detect": [r"exercis", r"workout", r"\bgym\b", r"\bactive\b", r"\brun", r"\bwalk"]},
    {"key": "caffeine", "label": "SH", "text": "Drinks two cups of coffee daily.",
     "detect": [r"caffein", r"coffee", r"\btea\b", r"energy drink", r"\bsoda"]},
    {"key": "fh_cancer", "label": "FH", "text": "No family history of cancer.",
     "detect": [r"cancer", r"tumou?r", r"malignan"]},
    {"key": "tobacco", "label": "SH", "text": "Denies tobacco or vaping.",
     "detect": [r"smok", r"tobacco", r"cigar", r"\bvap", r"nicotine", r"\bchew"]},
    {"key": "alcohol", "label": "SH", "text": "Denies alcohol use.",
     "detect": [r"alcohol", r"\bdrinks?\b", r"\bbeer", r"\bwine", r"liquor"]},
    {"key": "drugs", "label": "SH", "text": "Denies recreational drug use.",
     "detect": [r"\bdrugs?\b", r"marijuana", r"cannabis", r"cocaine", r"recreational", r"substance"]},
]

# --------------------------------------------------------------------------
# Family conditions a scribe can move into the patient's own history.
# --------------------------------------------------------------------------
FAMILY_CONDITIONS = [
    ("hypertension", [r"\bhtn\b", r"hypertension", r"high blood pressure"]),
    ("type 2 diabetes", [r"diabetes", r"\bdm\b", r"\bt2dm\b", r"high blood sugar"]),
    ("asthma", [r"asthma"]),
    ("myocardial infarction", [r"\bmi\b", r"heart attack", r"myocardial infarction"]),
    ("coronary artery disease", [r"\bcad\b", r"coronary", r"heart disease"]),
    ("stroke", [r"stroke", r"\bcva\b"]),
    ("breast cancer", [r"breast cancer"]),
    ("colon cancer", [r"colon cancer", r"colorectal cancer"]),
    ("lung cancer", [r"lung cancer"]),
    ("prostate cancer", [r"prostate cancer"]),
    ("kidney disease requiring dialysis", [r"dialysis"]),
    ("kidney stones", [r"kidney stones?", r"nephrolithiasis"]),
    ("hyperlipidemia", [r"high cholesterol", r"hyperlipid", r"\bhld\b"]),
    ("migraine", [r"migraine"]),
    ("thyroid disease", [r"thyroid"]),
    ("venous thromboembolism", [r"blood clot", r"\bdvt\b", r"pulmonary embol"]),
    ("depression", [r"depression"]),
    ("COPD", [r"\bcopd\b", r"emphysema"]),
    ("rheumatoid arthritis", [r"rheumatoid"]),
    ("seizure disorder", [r"seizure", r"epilep"]),
    ("peptic ulcer disease", [r"peptic ulcer", r"stomach ulcer"]),
    ("gallstones", [r"gallstone"]),
    ("Alzheimer disease", [r"alzheimer", r"dementia"]),
    ("Parkinson disease", [r"parkinson"]),
    ("glaucoma", [r"glaucoma"]),
]
RELATIVE_WORDS = [r"\bmother", r"\bmom\b", r"\bfather", r"\bdad\b", r"\bsister", r"\bbrother",
                  r"\baunt", r"\buncle", r"\bgrand", r"\bcousin", r"\bfamily", r"\bfh\b",
                  r"\bparent", r"\bsibling", r"\bson\b", r"\bdaughter", r"\bmaternal", r"\bpaternal"]

# --------------------------------------------------------------------------
# Allergy conflicts, reviewed per presentation. A drug is planted only where
# it is a realistic first-line suggestion for this patient's problem AND the
# visit established the allergy.
# --------------------------------------------------------------------------
ALLERGY_CONFLICTS = {
    "renal-flank-pain": {
        "allergen": [r"sulfa", r"sulfonamide"],
        "plan": "Start trimethoprim-sulfamethoxazole twice daily for 14 days.",
        "avoid": [r"sulfa", r"sulfamethoxazole", r"bactrim", r"tmp-?smx", r"septra"],
        "message": "The patient told you sulfa drugs caused hives. Trimethoprim-sulfamethoxazole is a sulfonamide.",
    },
    "gi-epigastric-melena": {
        "allergen": [r"penicillin"],
        "plan": "Start H. pylori triple therapy with amoxicillin, clarithromycin and a proton pump inhibitor.",
        "avoid": [r"amoxicillin", r"augmentin", r"ampicillin", r"penicillin"],
        "message": "The patient's lips and face swelled with penicillin. Amoxicillin is a penicillin, so standard triple therapy needs a penicillin-free regimen.",
    },
    "msk-shoulder-overuse": {
        "allergen": [r"naproxen", r"anti-?inflammator", r"nsaid"],
        "plan": "Start naproxen 500 mg twice daily with food for two weeks.",
        "avoid": [r"naproxen", r"ibuprofen", r"\bnsaids?\b", r"aleve", r"motrin", r"advil", r"diclofenac", r"meloxicam"],
        "message": "The patient told you naproxen caused hives and lip swelling. Naproxen is the drug they reacted to.",
    },
    "heent-ear-pain": {
        "allergen": [r"neomycin"],
        "plan": "Start neomycin-polymyxin B-hydrocortisone ear drops, 4 drops four times daily for 7 days.",
        "avoid": [r"neomycin", r"cortisporin"],
        "message": "The patient told you neomycin ointment made their skin red and itchy. These drops contain neomycin.",
    },
}

# --------------------------------------------------------------------------
# Why this matters (shown on the Scribbi home page, with sources).
# --------------------------------------------------------------------------
RESEARCH = [
    {"stat": "2.5 million",
     "text": "AI scribe uses in one large medical group's first year.",
     "cite": "Tierney et al., NEJM Catalyst 2025", "doi": "10.1056/CAT.25.0040"},
    {"stat": "18% · 11.5%",
     "text": "of 356 reviewed AI-drafted notes had omissions and hallucinations; 5% had errors rated as serious risk.",
     "cite": "Taylor et al., JMIR Med Inform 2026", "doi": "10.2196/86474"},
    {"stat": "15%",
     "text": "of AI drafts in that health system were left entirely unedited.",
     "cite": "Taylor et al., JMIR Med Inform 2026", "doi": "10.2196/86474"},
    {"stat": "3 per case",
     "text": "errors with potential for moderate-to-severe harm across five scribe platforms tested on simulated visits.",
     "cite": "Anderson et al., Mayo Clin Proc Digit Health 2025", "doi": "10.1016/j.mcpdig.2025.100292"},
]

BADGES = {
    "eagle_eye": {"label": "Eagle eye", "text": "Fixed every mistake Scribbi planted.", "icon": "eye"},
    "clean_hands": {"label": "Steady hand", "text": "No false alarms and nothing unsupported added.", "icon": "check"},
    "hands_on": {"label": "Hands-on DO", "text": "Added the structural findings Scribbi couldn't feel.", "icon": "hand"},
    "safety_net": {"label": "Safety net", "text": "Caught every mistake that could change care.", "icon": "shield"},
    "trust_but_verify": {"label": "Trust, but verify", "text": "Signed a clean draft without breaking anything that was right.", "icon": "seal"},
    "clinic_pace": {"label": "Clinic pace", "text": "Finished a timed review with a score of 80 or more.", "icon": "clock"},
}
