"""2026-09-13: source-bound printable actor reference, separate from live evidence.

This adapter reorganizes resolved authored facts. It never discloses facts into
an attempt and never changes the patient engine or the demonstrated lesson.
"""
from __future__ import annotations

import re

VERSION = "partner-script-v1"
UNKNOWN_RULE = ("Actor instruction: if the script does not supply a detail, say outside the patient role, "
                "'That information is not provided in this case.' Do not turn it into a denial, a guessed value, "
                "or a claim that the patient cannot remember.")
SECTION_SPEC = (
    ("surgical", "S", "Surgical history"),
    ("medications", "M", "Medications"),
    ("allergies", "A", "Allergies and reactions"),
    ("social", "S", "Social history"),
    ("history", "H", "History of present illness"),
    ("family", "F", "Family history"),
    ("medical", "M", "Past medical history"),
    ("ros", "R", "Review of systems"),
)
CATEGORY_SECTION = {"psh": "surgical", "medications": "medications", "allergies": "allergies",
                    "social": "social", "family": "family", "pmh": "medical",
                    "pertinent_negative": "ros", "associated": "ros"}
CATEGORY_TITLE = {
    "onset": "When it began", "chronology": "How it has changed", "location": "Where it is",
    "radiation": "Whether it spreads", "quality": "What it feels like", "severity": "How bad it is",
    "timing": "Duration and timing", "setting": "What was happening at the start",
    "alleviating": "What helps", "aggravating": "What makes it worse",
    "treatment": "What I have tried", "past_occurrence": "Similar episodes before",
    "psh": "Operations and hospital stays", "medications": "Medicines used",
    "allergies": "Medication allergies and reactions", "pmh": "Conditions diagnosed before",
    "family": "Family health", "fife": "Worries, expectations, and practical concerns",
    "concern": "What worries me",
    "obgyn": "Menstrual and pregnancy history", "social": "Home and daily life",
}
HPI_ORDER = ["onset", "location", "radiation", "timing", "chronology", "quality", "severity", "setting",
             "aggravating", "alleviating", "treatment", "past_occurrence", "obgyn", "fife", "concern"]
ROS_LABELS = {"general": "General symptoms", "cardiovascular": "Heart and circulation",
              "respiratory": "Breathing and chest", "gastrointestinal": "Stomach and bowels",
              "urinary": "Urinary symptoms", "genital": "Genital symptoms", "neurologic": "Nerves and balance",
              "heent": "Head, eyes, ears, nose, and throat", "ears": "Ears and hearing", "skin": "Skin",
              "musculoskeletal": "Muscles and joints", "hematologic": "Bleeding and bruising",
              "multiple": "Other symptom checks"}
TOPIC_TITLES = {
    "symptom_myalgia": "Muscle aches",
    "onset_dysuria": "When the urinary burning began", "onset_flank": "When the back pain began",
    "hpi_current_episode_onset": "When this current episode began", "hpi_episode_duration": "Length of each episode",
    "hpi_urinary_onset": "When the urinary symptoms began", "hpi_stool_quantity": "Amount and frequency of diarrhea",
    "timing_constancy": "Constant symptoms versus episodes", "hpi_constancy": "Constant symptoms versus episodes",
    "social_tobacco": "Smoking and tobacco", "tobacco_use": "Smoking and tobacco",
    "social_alcohol": "Alcohol", "alcohol_use": "Alcohol", "social_drugs": "Recreational drugs",
    "drug_use": "Recreational drugs", "social_occupation": "Work or school", "social_life": "Work or school",
    "history_context_1": "Work or school", "sexual_history": "Sexual activity",
    "history_family_1": "Mother", "history_family_2": "Father", "history_family_3": "Siblings",
    "history_family_4": "Other relatives", "history_admissions": "Hospital admissions",
    "history_eczema": "Eczema", "menstrual": "Last period", "history_menstrual": "Last period",
    "care_barrier": "What could make care difficult", "patient_concern": "What worries me",
    "concern_kidneys": "Concern about kidneys", "concern_cancer": "Concern about cancer",
    "concern_different": "Why this feels different", "concern_father": "Concern about my father’s illness",
    "concern_exam": "School concern", "concern_work": "Work concern",
    "current_chest_pressure": "Whether chest pressure is present now", "current_vertigo": "Whether spinning is present now",
    "neg_cardiac": "Fainting, palpitations, breathing while lying down, and swelling",
    "neg_resp": "Cough, breathing, and other chest symptoms", "neg_gi": "Other stomach and bowel symptoms",
    "neg_infectious": "Infection symptoms", "neg_focal": "Weakness, numbness, and speech or vision changes",
    "neg_alarm": "Additional warning symptoms", "neg_bleeding": "Other bleeding",
    "neg_other": "Other associated symptoms", "neg_skin_neuro": "Rash, headache, and constitutional symptoms",
    "neg_bowel": "Bowel changes", "neg_vaginal_discharge": "Vaginal discharge and itching",
    "brief_loc": "Loss of consciousness", "melena": "Black stool", "comfort_still": "Comfort while still",
    "comfort_upright": "Comfort while sitting upright",
}
PLAIN_SYMPTOMS = {
    "dyspnea": "Shortness of breath", "hemoptysis": "Coughing up blood", "syncope": "Fainting",
    "presyncope": "Feeling faint", "orthopnea": "Breathing when lying flat", "pnd": "Waking at night short of breath",
    "edema": "Swelling", "diaphoresis": "Sweating", "nausea": "Nausea", "vomiting": "Vomiting",
    "dysuria": "Burning when urinating", "frequency": "Urinating more often", "urgency": "Sudden urge to urinate",
    "nocturia": "Waking to urinate", "hematuria": "Blood in urine", "retention": "Trouble passing urine",
    "hesitancy": "Delay starting urine", "incomplete_emptying": "Feeling incompletely empty",
    "urine_output": "How much urine", "flank_pain": "Side or back pain", "fever_subjective": "Feeling feverish",
    "fever": "Fever", "chills": "Chills", "fatigue": "Tiredness", "weight_gain": "Weight gain",
    "weight_loss": "Weight loss", "dysphagia": "Trouble swallowing", "odynophagia": "Pain on swallowing",
    "regurgitation": "Food coming back up", "melena": "Black stools", "hematemesis": "Blood in vomit",
    "jaundice": "Yellow skin or eyes", "anorexia": "Loss of appetite", "vertigo": "Spinning sensation",
    "paresthesia": "Tingling", "photophobia": "Light sensitivity", "diplopia": "Double vision",
    "focal_weakness": "Weakness on one side", "saddle_numbness": "Numbness around the groin or buttocks",
    "speech_change": "Speech changes", "thunderclap": "Sudden worst headache", "neck_safety": "Neck symptoms",
    "polydipsia": "Unusual thirst", "pleuritic_pain": "Pain with a deep breath",
    "position_intolerance": "Position and breathing", "urine_appearance": "Urine appearance and smell",
}
BROAD_QUESTIONS = {"surgical": "Have you had any operations or hospital stays?",
                   "medications": "What medicines do you take?", "allergies": "Any medicine allergies?",
                   "social": "Tell me a little about your daily life.", "history": "What brings you in today?",
                   "family": "What health problems run in your family?", "medical": "What health problems have you had?",
                   "ros": "Have you noticed any other symptoms?"}

# Exact source-string edits add patient voice without adding clinical facts.
_VOICE_REWRITES = {'Appendectomy at age 16': 'I had my appendix removed when I was 16.',
 'Appendectomy at age 18': 'I had my appendix removed when I was 18.',
 'Cesarean delivery 5 years ago.': 'I had a cesarean delivery 5 years ago.',
 'Cholecystectomy at age 22.': 'I had my gallbladder removed when I was 22.',
 'Codeine causes severe nausea, without rash or breathing problems.': 'Codeine makes me very nauseated. I do '
                                                                      'not get a rash or breathing problems '
                                                                      'with it.',
 'Dilated cardiomyopathy with heart failure diagnosed last year after a viral illness': 'I was diagnosed '
                                                                                        'with dilated '
                                                                                        'cardiomyopathy and '
                                                                                        'heart failure last '
                                                                                        'year, after a viral '
                                                                                        'illness.',
 'Episodes of difficulty relaxing to urinate for 2 years, never previously assessed': 'For 2 years, I have '
                                                                                      'had episodes when I '
                                                                                      'have trouble relaxing '
                                                                                      'enough to pee. I have '
                                                                                      'never had that '
                                                                                      'checked.',
 'Gallbladder out at twenty-five. And two children, both normal deliveries.': 'I had my gallbladder removed '
                                                                              'when I was twenty-five. I '
                                                                              'have two children; both were '
                                                                              'normal deliveries.',
 'Hernia repair at age 20.': 'I had a hernia repaired when I was 20.',
 'High triglycerides diagnosed 2 years ago': 'I was told my triglycerides were high 2 years ago.',
 'Hypertension': 'I have high blood pressure.',
 'Hypertension and type 2 diabetes diagnosed at age 19': 'I was diagnosed with high blood pressure and type '
                                                         '2 diabetes when I was 19.',
 'Longstanding reflux': 'I have had acid reflux for a long time.',
 'Never smoked tobacco.': 'I have never smoked tobacco.',
 'No abdominal surgeries.': 'I have not had any surgery on my abdomen.',
 'No abdominal surgery or hospitalizations.': 'I have not had abdominal surgery or been hospitalized.',
 'No alcohol in the past year.': 'I have not had alcohol in the past year.',
 'No chronic illnesses or previous blood clots.': 'I do not have any long-term illnesses, and I have not had '
                                                  'blood clots before.',
 'No chronic illnesses.': 'I do not have any long-term illnesses.',
 'No chronic lung or heart disease': 'I do not have any long-term lung or heart disease.',
 'No chronic medical conditions': 'I do not have any long-term medical conditions.',
 'No cocaine or other recreational drugs.': 'I do not use cocaine or other recreational drugs.',
 'No cocaine, amphetamines or other recreational drugs.': 'I do not use cocaine, amphetamines, or other '
                                                          'recreational drugs.',
 'No diabetes, kidney disease or immunosuppression.': 'I do not have diabetes, kidney disease, or a '
                                                      'suppressed immune system.',
 'No inflammatory bowel disease or immunosuppression.': 'I do not have inflammatory bowel disease or a '
                                                        'suppressed immune system.',
 'No injection or other recreational drug use.': 'I do not inject drugs or use other recreational drugs.',
 'No known drug allergies.': 'I do not know of any allergies to medicines.',
 'No known gallstones or chronic disease.': 'I do not know of any gallstones or long-term disease.',
 'No operations or prior hospital admissions.': 'I have never had an operation or been admitted to the '
                                                'hospital.',
 'No pelvic surgery or catheterization history.': 'I have not had pelvic surgery or a urinary catheter '
                                                  'before.',
 'No recent surgery or bleeding.': 'I have not had surgery or bleeding recently.',
 'No recreational drugs.': 'I do not use recreational drugs.',
 'No spine surgery or recent procedures.': 'I have not had spine surgery or any recent procedures.',
 'No stroke, migraine or cervical spine disease.': 'I have not had a stroke, migraines, or disease of the '
                                                   'spine in my neck.',
 'No surgeries or admissions.': 'I have never had surgery or been admitted to the hospital.',
 'No surgeries or hospitalizations.': 'I have never had surgery or been hospitalized.',
 'No surgery or admissions except the prior stone visit.': 'I have not had surgery or hospital admissions '
                                                           'apart from that earlier kidney stone visit.',
 'No surgery or admissions.': 'I have never had surgery or been admitted to the hospital.',
 'No surgery or hospitalizations.': 'I have never had surgery or been hospitalized.',
 'No urinary procedures or surgery.': 'I have not had urinary procedures or surgery.',
 'One alcoholic drink monthly.': 'I have one alcoholic drink a month.',
 'One alcoholic drink weekly.': 'I have one alcoholic drink a week.',
 'One alcoholic drink weekly; none during this illness.': 'I usually have one alcoholic drink a week, but I '
                                                          'have not had any while I have been sick.',
 'One beer with dinner most evenings.': 'I have one beer with dinner most evenings.',
 'One glass of wine monthly.': 'I have one glass of wine a month.',
 'One glass of wine weekly.': 'I have one glass of wine a week.',
 'One prior calcium kidney stone': 'I have had one calcium kidney stone before.',
 'Penicillin causes hives.': 'I get hives from penicillin.',
 'Previous mechanical back pain': 'I have had mechanical back pain before.',
 'Previously diagnosed migraine': 'I have been diagnosed with migraines before.',
 'Quit tobacco 2 years ago after 3 pack-years.': 'I stopped smoking 2 years ago. My total smoking history '
                                                 'was 3 pack-years.',
 'Smokes 5 cigarettes daily for 5 years.': 'I smoke 5 cigarettes a day and have for 5 years.',
 'Smokes 5 cigarettes daily for 8 years.': 'I smoke 5 cigarettes a day and have for 8 years.',
 'Sulfonamide antibiotic caused hives.': 'I got hives from a sulfonamide antibiotic.',
 'Two alcoholic drinks weekly.': 'I have two alcoholic drinks a week.',
 'Two beers most evenings.': 'I have two beers most evenings.',
 'Usually 3 beers nightly; 6 drinks at a gathering 2 days ago.': 'I usually have 3 beers a night. I had 6 '
                                                                 'drinks at a gathering 2 days ago.',
 'has two kidneys': 'I have two kidneys.',
 'no cancer, diabetes or immune suppression.': 'I do not have cancer, diabetes, or a suppressed immune '
                                               'system.',
 'no diabetes or prior urinary diagnosis.': 'I do not have diabetes and have never been diagnosed with a '
                                            'urinary condition.',
 'no heart disease or diabetes.': 'I do not have heart disease or diabetes.',
 'no kidney disease.': 'I do not have kidney disease.',
 'no kidney stones or prior urinary disease.': 'I have not had kidney stones or urinary disease before.',
 'no known gallstones.': 'I do not know of any gallstones.',
 'no known prior heart attack.': 'I have not had a heart attack that I know of.',
 'no known thyroid or structural heart disease.': 'I do not know of any thyroid disease or problems with the '
                                                  'structure of my heart.',
 'no malignancy or immunosuppression.': 'I do not have cancer or a suppressed immune system.',
 'no neurologic disease.': 'I do not have a neurologic disease.',
 'no previous stroke.': 'I have never had a stroke.',
 'no prior endoscopy.': 'I have never had an endoscopy.',
 'no recent surgery.': 'I have not had surgery recently.',
 'no urinary procedures.': 'I have not had any urinary procedures.',
 'vaccines not reviewed recently.': 'I have not reviewed my vaccinations recently.'}


# These authored categories mix different dimensions. Aliases are attached to
# the actual question rather than the category (exposure is not onset activity;
# frequency/continuity are not episode length).
QUESTION_ALIASES = {
    "Have you been around anyone who was ill?": ["Any sick contacts?", "Has anyone near you been sick recently?"],
    "Have there been any recent changes in your diet?": ["Have you been eating differently lately?", "Has your usual diet changed?"],
    "Have you had any recent long trips or periods of immobility?": ["Any long travel or time spent unable to move around?", "Have you been sitting still for a long trip recently?"],
    "Have there been any recent changes to your medicines?": ["Has a medicine or dose changed recently?", "Are you taking your medicines differently than before?"],
    "Has anyone around you had similar symptoms?": ["Is anyone close to you sick with something similar?", "Any contacts with similar symptoms?"],
    "Have you had heartburn or reflux before?": ["Have you had acid reflux in the past?", "Any history of heartburn?"],
    "Did the pain begin before or after the vomiting, and was there an injury?": ["Which started first, the pain or vomiting? Any injury?", "Did you get hurt, and did the pain or vomiting come first?"],
    "Was there an injury before these symptoms?": ["Did you get hurt before this began?", "Did an injury precede the symptoms?"],
    "Have you started any medicines recently, including cold medicines?": ["Any new medicines or cold remedies?", "Did you recently begin taking something for a cold?"],
    "Was there an injury or any trigger you noticed?": ["Did you get hurt or notice a trigger?", "Any injury or clear trigger before it began?"],
    "Was there a sudden trigger for these symptoms?": ["Did anything suddenly bring this on?", "Was there a clear sudden trigger?"],
    "Have you recently been ill, exercised strenuously, or had an injury or procedure?": ["Any recent illness, heavy exercise, injury, or procedure?", "Were you sick or doing strenuous exercise before this? Any injury or procedure?"],
    "What were you doing when this started?": ["What was happening when the symptoms began?", "What activity were you doing at the start?"],
    "Does the chest pressure occur at rest?": ["Does it happen when you are resting?", "Any chest pressure while sitting still?"],
    "How have the breathing symptoms changed over time?": ["Is your breathing getting better or worse over time?", "How has the breathing problem progressed?"],
    "Has this current episode stopped at any point?": ["Has this episode let up?", "Has the current episode been continuous?"],
    "Is the breathlessness constant or does it come and go?": ["Does the trouble breathing stay there or come in spells?", "Has the breathlessness let up at all?"],
    "Does the lightheadedness settle after the spell?": ["Does the faint feeling go away after each spell?", "Do you recover between the lightheaded spells?"],
    "Do the cramps ease between bowel movements?": ["Do the cramps settle after you pass stool?", "Are the cramps better between trips to the bathroom?"],
    "Has the pain let up, and how has it changed?": ["Has there been any relief, or is the pain continuing?", "Is the pain still there, and has it worsened?"],
    "Is the pain worse when your stomach is empty or at night?": ["Does an empty stomach or nighttime make the pain worse?", "Is there a pattern related to an empty stomach or nighttime?"],
    "Is the pain there constantly or does it come and go?": ["Does the pain stay there all the time?", "Is the pain continuous or intermittent?"],
    "Has the pain stayed constant or does it come and go?": ["Has the pain been continuous?", "Does it stay there or ease off and return?"],
    "When did the leg symptoms and bladder trouble appear?": ["When did the leg and urinary symptoms begin?", "How recently did the leg and bladder problems develop?"],
    "How has the numbness spread, and how often is it present?": ["Has the area of numbness changed, and how often do you feel it?", "Is the numbness spreading, and is it happening regularly?"],
    "Do you feel well between the spinning spells?": ["How do you feel between spinning episodes?", "Do the spinning symptoms go away between spells?"],
    "How often do you have similar headaches?": ["How frequently do these headaches happen?", "How many similar attacks do you get?"],
    "Has the headache let up at any point?": ["Has the headache stopped at all?", "Has it been continuous since it began?"],
    "Does the pain ease between the waves?": ["Is there any relief between waves of pain?", "Does the pain lessen between waves?"],
    "Does the burning happen with every urination?": ["Do you feel burning every time you pee?", "Is every trip to urinate painful?"],
    "Is the back ache constant, and when does the burning happen?": ["Does your back hurt all the time, and when do you get burning?", "Is the back pain always there while the burning happens at particular times?"],
    "Does the bleeding stop between episodes?": ["Does the urine return to normal between episodes of bleeding?", "Is there a break in the bleeding between episodes?"],
    "How long does each episode last?": ["How long is one spell?", "How long do the individual episodes continue?"],
    "How long did your earlier episodes last?": ["How long were the previous spells?", "How long did each earlier episode continue?"],
}

QUESTION_ALIASES.update({
    "Have you had recent surgery?": ["Any operations recently?", "Have you had surgery in the recent past?"],
    "Have you been hospitalized since your appendectomy?": ["Any hospital stays since your appendix operation?", "Have you needed hospital admission after the appendectomy?"],
    "Have you had any surgeries or hospital admissions?": ["What operations or hospital stays have you had?", "Have you ever had surgery or been admitted to the hospital?"],
    "What medical conditions have you been diagnosed with?": ["What health conditions have you had before?"],
    "What medicines do you take, including prescriptions, over-the-counter products, and supplements?": ["What prescription medicines, OTC products, or supplements do you use?"],
    "Do you have any medication allergies, and what reaction do you have?": ["Are you allergic to any medicines? What happens when you take them?"],
    "Do you use tobacco or smoke?": ["Do you smoke?", "Do you use tobacco?"],
    "Do you drink alcohol, and how much?": ["How much alcohol do you drink?", "How often do you have a drink, and how much?"],
    "Do you use any recreational drugs?": ["Do you use recreational substances?", "Any recreational drug use?"],
    "What do you do for work?": ["What do you do for work or school?", "What is your occupation?"],
    "What health problems run in your family?": ["What illnesses have affected your relatives?"],
    "What worries you most about these symptoms?": ["What is your main worry about this?", "What concerns you most about the symptoms?"],
    "How is this affecting your work?": ["What effect has this had on your job?", "How has it affected you at work?"],
    "How is this affecting your school work?": ["How have your studies been affected?", "What effect has this had on school?"],
    "What might make the care plan difficult for you to follow?": ["What could get in the way of following the plan?", "What help would you need to follow the care plan?"],
    "How much exercise do you get?": ["What exercise do you do?", "How physically active are you?"],
    "What is your usual diet like?": ["What do you usually eat?", "Tell me about your usual meals."],
    "Is there any chance you could be pregnant?": ["Could you be pregnant?", "Is pregnancy possible?"],
    "When was your last period?": ["When did your last menstrual period start?"],
    "What health problems has your mother had?": ["How is your mother's health?", "Has your mother had any illnesses?"],
    "What health problems has your father had?": ["How is your father's health?", "Has your father had any illnesses?"],
    "What health problems have your siblings had?": ["How is the health of your brothers or sisters?", "Do any of your siblings have medical conditions?"],
    "Who do you live with?": ["Who lives with you?", "What is your living situation?"],
    "Have you traveled recently?": ["Any recent trips?", "Have you traveled lately?"],
    "Have you recently been immobilized or on bed rest?": ["Have you recently been on bed rest?", "Have you recently been unable to move around?"],
    "Who could help you at home?": ["Who is available to help you at home?", "Do you have support at home?"],
    "Has anyone in your family died suddenly before age 50?": ["Any sudden deaths in relatives younger than fifty?"],
    "Do you drink coffee or energy drinks? How much?": ["How much coffee or energy drink do you use?"],
    "Does an inherited clotting disorder run in your family?": ["Any inherited blood-clotting conditions in your relatives?"],
    "How much water do you drink, and can you take water breaks?": ["Tell me about your water intake and access to water breaks."],
    "Are there any other inherited illnesses in your family?": ["Any other hereditary conditions in your relatives?"],
    "Have you drunk any untreated water?": ["Any untreated-water exposure?"],
    "Have you had eczema?": ["Any history of eczema?"],
    "Are you sexually active?": ["Are you currently sexually active?"],
    "What do you use for birth control?": ["What contraception do you use?"],
    "Was anyone with you who witnessed the onset?": ["Did anybody see the symptoms begin?", "Was anyone there when this started?"],
    "Does neuropathy run in your family?": ["Do nerve problems like this run in your family?"],
    "Are your periods regular?": ["How regular is your menstrual cycle?"],
    "How many sexual partners do you have, and have you had a new partner?": ["Can you tell me the number of sexual partners and whether any are new?"],
    "Does hereditary kidney disease run in your family?": ["Any inherited kidney disease in your relatives?"],
    "What have you tried for this, and did it help?": ["Have you taken or done anything for it? Did it help?", "What have you tried so far, and what effect did it have?"],
    "What does it feel like?": ["How would you describe the feeling?"],
    "Where do you feel the symptoms?": ["Can you point to where you feel it?"],
    "Does the discomfort spread anywhere else?": ["Does it move or travel to another area?"],
    "What makes it better?": ["Does anything ease it?", "What helps you feel better?"],
    "What makes it worse?": ["Does anything worsen it?", "What makes it more bothersome?"],
    "Have you had anything like this before?": ["Have you ever felt like this before?", "Has this happened previously?"],
    "How have your symptoms changed since they started?": ["Have the symptoms been getting better or worse?"],
})


def _sentence(text):
    text = str(text or "").strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text[:1].upper() + text[1:]


def _voice(text):
    return _sentence(_VOICE_REWRITES.get(str(text or "").strip(), str(text or "").strip()))


def _parts(text):
    # Decimal values, abbreviations and medication units stay with their sentence.
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text) if x.strip()]


def _ros_system(fact):
    if fact.get("ros_system"):
        return fact["ros_system"]
    fid = fact["id"]
    explicit = {"neg_resp": "respiratory", "neg_cardiac": "cardiovascular", "neg_gi": "gastrointestinal",
                "neg_bowel": "gastrointestinal", "neg_skin_neuro": "multiple", "neg_focal": "neurologic",
                "neg_infectious": "general", "neg_bleeding": "hematologic", "neg_other": "multiple",
                "neg_alarm": "multiple", "brief_loc": "neurologic", "melena": "gastrointestinal",
                "current_chest_pressure": "cardiovascular", "current_vertigo": "neurologic"}
    if fid in explicit:
        return explicit[fid]
    for pattern, system in [(r"fever|chill|sweat|fatigue|weight", "general"),
                            (r"nausea|vomit|bowel|diarrhea|constipation|saliva|swallow", "gastrointestinal"),
                            (r"urine|frequency|urgency|voided", "urinary"), (r"vaginal", "genital"),
                            (r"dyspnea|resp", "respiratory"), (r"neck|lightheaded", "neurologic")]:
        if re.search(pattern, fid):
            return system
    return "multiple"


def _title(fact):
    if fact.get("print_label"):
        return fact["print_label"]
    fid = fact["id"]
    if fact["category"] == "family":
        question = fact.get("example_questions", [""])[0].lower()
        for fragment, label in [("mother", "Mother"), ("father", "Father"), ("siblings", "Siblings"),
                                ("clotting", "Inherited clotting conditions"), ("died suddenly", "Sudden deaths in the family"),
                                ("neuropathy", "Family history of nerve problems"), ("kidney disease", "Hereditary kidney disease"),
                                ("other inherited", "Other inherited conditions")]:
            if fragment in question:
                return label
        return "Family health"
    if fact["category"] == "setting":
        question = fact.get("example_questions", [""])[0].lower()
        for fragment, label in [("anyone who was ill", "Sick contacts"), ("similar symptoms", "Sick contacts"),
                                ("changes in your diet", "Recent dietary changes"), ("long trips", "Travel and immobility"),
                                ("changes to your medicines", "Recent medication changes"), ("started any medicines", "New medicines and cold remedies"),
                                ("heartburn or reflux", "Earlier heartburn or reflux"), ("before or after the vomiting", "Pain, vomiting, and injury chronology"),
                                ("injury", "Injury and other recent circumstances")]:
            if fragment in question:
                return label
    if fid in TOPIC_TITLES:
        return TOPIC_TITLES[fid]
    if fact.get("history_topic"):
        return fact["history_topic"].replace("_", " ").capitalize()
    if fid.startswith(("symptom_", "assoc_", "neg_")):
        key = re.sub(r"^(symptom|assoc|neg)_", "", fid)
        return PLAIN_SYMPTOMS.get(key, key.replace("_", " ").capitalize())
    text = fact["sp_says"][0].lower()
    if fact["category"] == "medications" and re.search(r"miss|refill|ran out", text):
        return "Missed doses and refills"
    if fact["category"] == "medications" and re.search(r"do not|no |not take", text):
        return "Other medicines and products"
    if fact["category"] == "pmh" and "vaccin" in text:
        return "Vaccinations"
    if fact["category"] == "pmh" and "endoscop" in text:
        return "Previous endoscopy"
    if fact["category"] == "pmh" and "a1c" in text:
        return "Previous diabetes blood test"
    if fact["category"] == "pmh" and re.match(r"no |has two", text):
        return "Other relevant medical history"
    return CATEGORY_TITLE.get(fact["category"], "Additional history")


def _questions(fact, title):
    authored = list(fact.get("example_questions", []))
    # A category and an ID suffix are not a question's meaning: history_family_3
    # may concern siblings, clotting, or inflammatory bowel disease. Only exact
    # authored questions receive reviewed aliases. One sound prompt is sufficient.
    precise = {
        "Missed doses and refills": ["Have you missed any doses or had trouble getting refills?",
                                    "Have you been able to take the medicine as prescribed?"],
        "Vaccinations": ["Have your vaccines been reviewed recently?", "Have you checked your vaccination record recently?"],
        "Previous endoscopy": ["Have you ever had an endoscopy?", "Have you had a camera examination of your upper digestive tract?"],
        "Previous diabetes blood test": ["What was your last A1c result?", "Do you remember your most recent A1c?"],
    }
    if title in precise:
        return precise[title]
    if not authored:
        return [title]
    aliases = QUESTION_ALIASES.get(authored[0], [])
    return list(dict.fromkeys(authored + aliases))[:3]


def _relationship_conflict(case):
    values = " ".join(str(f.get("value", "")).lower() for f in case.get("facts", []) if f.get("id") in {"history_household", "history_sexual_partners"})
    return case.get("id") == "renal-flank-pain" and "husband" in values and "boyfriend" in values


def _topic(fact, case_id, relationship_conflict=False):
    title = _title(fact)
    text = _voice(fact["sp_says"][0])
    note = ""
    if relationship_conflict and fact["id"] == "history_household":
        text = "I live off campus."
        note = "Relationship label is inconsistent in the source. Give the off-campus detail; do not invent whether the partner is a spouse or boyfriend."
    if relationship_conflict and fact["id"] == "history_sexual_partners":
        text = "I have one male partner and no new partners."
        note = "Relationship label is inconsistent in the source. Retain one male partner and no new partners; do not choose a relationship label."
    pieces = _parts(text)
    if len(pieces) > 1 and len(pieces[0].split()) <= 2 and pieces[0].endswith("?"):
        # "Honestly?" is a discourse marker, not an answer to a concern question.
        pieces = [pieces[0] + " " + pieces[1]] + pieces[2:]
    # For broad multipart source answers, keep a concise initial reply and place
    # authored remaining sentences below. No new answer is inferred from an alias.
    split = fact["category"] in {"pmh", "psh", "allergies", "family", "social", "fife"} and len(pieces) > 1
    answer = pieces[0] if split else text
    followups = []
    if split:
        follow_question = "If asked for more detail about this topic"
        if fact["category"] == "allergies":
            follow_question = "What reaction did you have?"
        elif fact["category"] == "medications":
            follow_question = "Any other medicines, dose details, or missed doses?"
        elif fact["category"] == "family":
            follow_question = "What about other family members?"
        elif fact["category"] == "psh":
            follow_question = "Any other procedures or hospital stays?"
        followups = [{"question": follow_question, "answer": " ".join(pieces[1:])}]
    return {"id": fact["id"], "title": title, "questions": _questions(fact, title), "answer": answer,
            "followups": followups, "actor_note": (note + (" If the question asks about both the main topic and a follow-up detail, give both parts of the answer together." if followups else "")).strip(), "crossrefs": [], "source_fact_ids": [fact["id"]],
            "system": _ros_system(fact) if fact["category"] in {"associated", "pertinent_negative"} else None,
            "category": fact["category"]}


def _briefing(case):
    patient = case["patient"]
    persona = patient.get("persona", "").strip()
    # Persona text is explicitly actor-only. Many legacy affect fields are
    # patient questions; never use them as unsolicited greeting dialogue.
    affect = patient.get("affect", "").strip()
    acting = [persona] if persona else []
    if affect and "?" not in affect and not re.match(r"^(I |My |Can |Could |Will |Does |Do |Are |Is |It stopped)", affect):
        acting.append(affect)
    opening_ids = [f["id"] for f in case["facts"] if f["category"] == "chief_complaint"]
    return {"name": patient["name"], "age": patient["age"], "sex": patient["sex"],
            "background": persona.split(". ")[0] if persona else "",
            "acting_directions": acting, "communication_style": patient.get("communication_style", ""), "opening": patient["opening"],
            "volunteer_rule": "Begin with the opening statement only. Match the meaning of questions, not exact wording. Answer every part of a compound question: include the matching follow-up answer immediately when that detail is asked, without making the student ask twice. For a broad invitation, give the initial response and pause. For a focused question, give only the relevant facts, even when a printed reply bundles several symptoms. Do not turn an unasked bundled symptom into a volunteered denial. Do not announce a diagnosis or read out examination findings.",
            "unknown_rule": UNKNOWN_RULE, "source_fact_ids": opening_ids}


def build_patient_script(case, lesson):
    """Return a deterministic, JSON-ready print reference for a resolved case.

    `lesson` identifies the demonstrated encounter; extra actor facts stay marked
    in the internal audit and never enter that encounter's example SOAP note.
    """
    sections = [{"id": sid, "letter": letter, "title": title, "topics": [], "entry": None}
                for sid, letter, title in SECTION_SPEC]
    lookup = {s["id"]: s for s in sections}
    facts = case["facts"]
    unknown_categories = []
    for fact in facts:
        if fact["category"] == "chief_complaint":
            continue
        if fact["category"] not in CATEGORY_SECTION and fact["category"] not in HPI_ORDER:
            unknown_categories.append(fact["id"])
            continue
        sid = CATEGORY_SECTION.get(fact["category"], "history")
        lookup[sid]["topics"].append(_topic(fact, case["id"], _relationship_conflict(case)))
    lookup["history"]["topics"].sort(key=lambda t: HPI_ORDER.index(t["category"]))
    ros_order = list(ROS_LABELS)
    lookup["ros"]["topics"].sort(key=lambda t: (ros_order.index(t["system"]) if t["system"] in ros_order else 99))
    for topic in lookup["ros"]["topics"]:
        topic["system_label"] = ROS_LABELS.get(topic["system"], "Other symptom checks")
    # Cross references use existing topic IDs instead of duplicating answers.
    for topic in lookup["history"]["topics"]:
        if topic["category"] == "past_occurrence" and lookup["medical"]["topics"]:
            first = lookup["medical"]["topics"][0]
            topic["crossrefs"].append({"section_id": "medical", "topic_id": first["id"], "label": "Other diagnosed medical conditions"})
        if topic["category"] == "treatment" and lookup["medications"]["topics"]:
            first = lookup["medications"]["topics"][0]
            topic["crossrefs"].append({"section_id": "medications", "topic_id": first["id"], "label": "Medication list and dosing details"})
    treatment_topics = [t for t in lookup["history"]["topics"] if t["category"] == "treatment"]
    for topic in lookup["medications"]["topics"]:
        for treatment in treatment_topics:
            topic["crossrefs"].append({"section_id": "history", "topic_id": treatment["id"],
                                       "label": "What has been tried for this illness; any supplied medication details"})
        topic["actor_note"] = (topic["actor_note"] + " For a complete medication question, include the other medicine topics and the linked treatments tried for this illness. Report only names, doses, and use details actually supplied there.").strip()
    all_topics = [t for s in sections for t in s["topics"]]
    for section in sections:
        topics = section["topics"]
        if section["id"] == "history":
            entry_answer = case["patient"]["opening"]
            entry_ids = []
        elif section["id"] == "ros":
            # There is no authored global 'everything else is normal' answer.
            positive = next((t for t in topics if t["category"] == "associated"), None)
            entry_answer = positive["answer"] if positive else ""
            entry_ids = [positive["id"]] if positive else []
        else:
            # A general social invitation begins with work/home, not sexual history.
            first = next((t for t in topics if t["id"] in {"social_occupation", "social_life", "history_context_1"}), topics[0] if topics else None) if section["id"] == "social" else (topics[0] if topics else None)
            entry_answer = first["answer"] if first else ""
            entry_ids = [first["id"]] if first else []
        section["entry"] = {"question": BROAD_QUESTIONS[section["id"]], "answer": entry_answer,
                            "topic_ids": entry_ids,
                            "actor_note": ("For a broad invitation, give this initial response, then pause. Use the focused topics for additional questions." if entry_answer else UNKNOWN_RULE)}
    actor_notes = []
    conflicts = []
    if _relationship_conflict(case):
        conflicts = [{"id": "relationship-label", "source_fact_ids": ["history_household", "history_sexual_partners"],
                      "detail": "Source calls the partner both husband and boyfriend. Relationship label is withheld pending author clarification; off-campus residence, one male partner, and no new partners are retained."}]
        actor_notes.append({"title": "Source detail needing clarification", "text": conflicts[0]["detail"], "source_fact_ids": conflicts[0]["source_fact_ids"]})
    refusal_labels = {"gyn": "pelvic examination", "rectal": "rectal examination", "corneal": "corneal reflex test"}
    for refusal in case.get("refusals", []):
        actor_notes.append({"title": "If this examination is proposed", "text": "Actor instruction: decline the " + refusal_labels.get(refusal, refusal) + ". The source establishes this refusal; no reason is specified. Do not supply a finding for a refused examination.", "source_fact_ids": [], "source_refusal": refusal})
    for position, rule in case["patient"].get("position_rules", {}).items():
        if rule.get("allowed") is False:
            label = {"supine": "lie flat on your back", "prone": "lie face down"}.get(position, position)
            reply = rule.get("reply", "")
            actor_notes.append({"title": "If asked to " + label,
                                "text": "Actor instruction: this position is not supported for this patient. " + ("Patient response: “" + reply + "”" if reply else "Do not invent a reason."),
                                "source_fact_ids": list(rule.get("fact_ids", [])), "source_position": position})
    actor_notes.append({"title": "When an examination is performed", "text": "Keep spoken history separate from simulated examination findings. Release only the corresponding supplied finding after the student performs or explicitly describes that examination. Do not portray an unlisted maneuver as normal.", "source_fact_ids": []})
    covered = set(_briefing(case)["source_fact_ids"]) | {fid for t in all_topics for fid in t["source_fact_ids"]}
    demonstrated = {fid for t in lesson.get("timeline", []) for fid in t.get("fact_ids", [])}
    return {"version": VERSION, "briefing": _briefing(case), "sections": sections,
            "quick_reference": [{"title": t["title"], "section_id": s["id"], "topic_id": t["id"]}
                                for s in sections for t in s["topics"]],
            "actor_notes": actor_notes,
            "audit": {"case_id": case["id"], "variant_id": case.get("variant_id", "base"),
                      "fact_ids": [f["id"] for f in facts], "covered_fact_ids": sorted(covered),
                      "unresolved_fact_ids": unknown_categories, "known_conflicts": conflicts,
                      "not_in_demonstrated_encounter": sorted(covered - demonstrated),
                      "clinical_scope": "Print presentation of authored case facts; not a new clinical review or a change to attempt evidence."}}
