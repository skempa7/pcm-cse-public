"""Bounded statement equivalences for actual delivered opening speech.

These authored language mappings describe symptoms, not confirmed diagnoses.
A source must match the actual opening event before a summary is supported.
They confer only opening evidence, never the hidden full-HPI attributes.
"""

PARAPHRASES = [{'id': 'cardio-chest-pressure',
  'source': "I've been getting this pressure in my chest when I push myself at work. It goes away when I "
            'stop. My wife made me come in.',
  'summaries': ['Exertional chest pressure relieved by rest',
                'Chest pressure at work that goes away when she stops',
                'Chest pressure when exerting herself at work',
                'Chest pressure with exertion at work',
                'Exertional chest pressure',
                'Chest pressure with exertion',
                'Relieved by stopping',
                'Relieved by rest']},
 {'id': 'cardio-febrile-cough',
  'source': 'I have had fever and a bad cough, and now it hurts when I breathe deeply.',
  'summaries': ['Fever with cough and pain on deep inspiration',
                'Fever and a bad cough with pain when breathing deeply']},
 {'id': 'cardio-orthopnea-edema',
  'source': 'I cannot catch my breath when I lie down, and my ankles have become swollen.',
  'summaries': ['Shortness of breath when lying down with swollen ankles', 'Orthopnea with ankle swelling']},
 {'id': 'cardio-palpitations',
  'source': 'My heart keeps fluttering and racing. This episode has not stopped.',
  'summaries': ['Persistent palpitations', 'Fluttering and racing heartbeat that has not stopped']},
 {'id': 'cardio-pleuritic-dyspnea',
  'source': 'I suddenly got short of breath this morning. It hurts on the right when I take a deep breath.',
  'summaries': ['Sudden shortness of breath this morning with right-sided pain on deep inspiration',
                'Sudden dyspnea this morning with right pleuritic pain']},
 {'id': 'cardio-presyncope',
  'source': 'I keep feeling like I might faint when I stand up.',
  'summaries': ['Lightheadedness when standing',
                'Feeling as if she might faint when standing',
                'Feeling faint on standing',
                'Presyncope on standing']},
 {'id': 'gi-diarrhea-dehydration',
  'source': 'I have had diarrhea all night, and I feel dried out.',
  'summaries': ['Diarrhea all night with feeling dehydrated', 'Diarrhea overnight and feeling dried out']},
 {'id': 'gi-epigastric-back-pain',
  'source': 'I have awful pain high in my stomach that goes straight through to my back.',
  'summaries': ['Severe upper abdominal pain radiating to the back',
                'Epigastric pain going through to the back']},
 {'id': 'gi-epigastric-melena',
  'source': "I've had this burning pain in the top of my stomach for about six weeks. It's been worse the "
            'last few days.',
  'summaries': ['Burning upper abdominal pain for about six weeks',
                'Burning epigastric pain for approximately 6 weeks']},
 {'id': 'gi-progressive-dysphagia',
  'source': 'Food is getting stuck when I swallow, and I am losing weight.',
  'summaries': ['Food gets stuck when swallowing with weight loss',
                'Difficulty swallowing food with weight loss']},
 {'id': 'gi-right-lower-pain',
  'source': 'My stomach started hurting around the middle, but now the pain is low on the right.',
  'summaries': ['Abdominal pain migrating from the middle to the right lower abdomen',
                'Central abdominal pain that is now in the right lower quadrant']},
 {'id': 'gi-right-upper-pain',
  'source': 'The pain under my right ribs has not gone away since dinner.',
  'summaries': ['Right upper abdominal pain since dinner',
                'Pain under the right ribs that has persisted since dinner']},
 {'id': 'neuro-acute-focal-weakness',
  'source': 'My right arm suddenly got weak, and my words are not coming out right.',
  'summaries': ['Sudden right arm weakness with difficulty speaking',
                'Right arm suddenly became weak and words are not coming out right']},
 {'id': 'neuro-back-bladder-redflags',
  'source': 'My back pain is worse, and now I am having trouble passing urine.',
  'summaries': ['Worsening back pain with new difficulty passing urine',
                'Back pain has worsened and she is now having trouble urinating']},
 {'id': 'neuro-distal-neuropathy',
  'source': 'My toes feel numb and burn at night. It is happening in both feet.',
  'summaries': ['Numbness and burning in the toes of both feet at night',
                'Bilateral toe numbness and burning at night']},
 {'id': 'neuro-positional-vertigo',
  'source': 'The room spins for a few seconds when I roll over in bed.',
  'summaries': ['Room spinning for a few seconds when rolling over in bed',
                'Brief vertigo when turning over in bed']},
 {'id': 'neuro-recurrent-headache',
  'source': 'I have another throbbing headache, and the lights are making it worse.',
  'summaries': ['Recurrent throbbing headache worsened by light',
                'Another throbbing headache made worse by bright lights']},
 {'id': 'neuro-thunderclap-headache',
  'source': 'I got this headache about six hours ago and it came on like someone hit me. I get migraines, '
            'but this is not my migraine.',
  'summaries': ['Sudden headache about six hours ago unlike her migraines',
                'Abrupt headache about 6 hours ago different from her usual migraine']},
 {'id': 'renal-acute-retention',
  'source': 'I desperately need to pee, but nothing will come out.',
  'summaries': ['Unable to urinate despite a strong urge', 'Unable to urinate', 'Strong urge to pee but no urine comes out', 'Strong urge to pee', 'No urine comes out']},
 {'id': 'renal-colicky-flank',
  'source': 'The pain in my side comes in terrible waves and I cannot get comfortable.',
  'summaries': ['Pain in her side coming in waves with inability to get comfortable',
                'Colicky pain in the side with restlessness']},
 {'id': 'renal-dysuria',
  'source': 'It burns when I pee and I keep needing to go.',
  'summaries': ['Burning urination with frequent need to urinate', 'Dysuria with urinary frequency', 'Burning urination and frequency', 'Burning when urinating and needing to go often', 'Dysuria', 'Urinary frequency']},
 {'id': 'renal-flank-pain',
  'source': "I've had this burning when I pee for a couple of days, and since yesterday my back has been "
            "hurting on the right side. I've been feeling really lousy — I think I have a fever.",
  'summaries': ['Burning urination for a couple of days with right back pain since yesterday and feeling '
                'feverish',
                'Dysuria for about two days and right-sided back pain since yesterday with subjective '
                'fever']},
 {'id': 'renal-luts-nocturia',
  'source': 'I keep needing to pee at night, and my bladder feels uncomfortable as it fills.',
  'summaries': ['Frequent nighttime urination with discomfort as the bladder fills',
                'Nocturia with bladder discomfort during filling']},
 {'id': 'renal-painless-hematuria',
  'source': 'My urine has looked red twice this week, but nothing hurts.',
  'summaries': ['Painless red urine twice this week',
                'Painless red urine on two occasions this week']}]


# Only grammatical variation, applied during an exact opening-summary match.
# These do not discard negation, severity, dates, laterality or other content.
SUMMARY_GRAMMAR = [
    (r"\b(?:feeling|feels?) (?:like|as if)\b", "feeling as if"),
    (r"\bmay faint\b", "might faint"),
    (r"\bafter standing\b", "when standing"),
    (r"\bwhen she stands up\b", "when standing"),
    (r"\bwhen i stand up\b", "when standing"),
]

def summary_text(text):
    import re
    from . import nlp
    text=nlp.normalize(text).replace('-', ' ')
    for pattern,replacement in SUMMARY_GRAMMAR:text=re.sub(pattern,replacement,text)
    return re.sub(r'[^a-z0-9 ]','',text).strip()
