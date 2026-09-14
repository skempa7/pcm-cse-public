"""Printable clinical-note adapter for the complete demonstrated encounter.

This is presentation-only: it never changes a saved attempt, authored lesson,
case facts, grading or a documentation verdict. Source event references identify
where to review the demonstrated history; they are not a semantic validator.
"""
from __future__ import annotations

import re
from collections import OrderedDict


SUBJECTIVE_ORDER = (
    'Chief complaint', 'History of present illness',
    'Past medical and surgical history', 'Medications', 'Social history',
    'Family history', 'Allergies', 'Review of systems',
)

# Each replacement removes specificity that the demonstrated dialogue did not
# supply. The source lessons remain unchanged for replay and audit comparison.
_EVIDENCE_CORRECTIONS = {
    'neuro-thunderclap-headache': [
        ('Sumatriptan 100 mg PRN', 'Sumatriptan as needed (dose not established)',
         'The patient named sumatriptan but did not supply a dose.', 'medications'),
    ],
    'gi-epigastric-melena': [
        ('ferrous sulfate for 1 week', 'oral iron for 1 week (preparation and dose not established)',
         'The patient reported borrowed iron pills, not a named iron formulation.', 'medications'),
        ('lightheadedness and reported pallor', 'lightheadedness',
         'Pallor was observed on examination; it was not a patient-reported symptom.', 'associated'),
    ],
}

# Existing lower alternatives are not silently promoted into clinically supported
# answers. These require a distinct, source-supported third differential before
# the document can be called a complete three-differential model answer.
_DIFFERENTIAL_GAPS = {
    'gi-diarrhea-dehydration': (
        'Medication-associated diarrhea',
        'No culprit medicine was reported; the patient reported no daily medicine and no antibiotics in the previous 3 months.'),
    'gi-right-upper-pain': (
        'Medication-related gastritis',
        'No causative medicine exposure was established. The reported single antacid dose does not supply that missing exposure.'),
    'neuro-distal-neuropathy': (
        'Medication-associated neuropathy',
        'No separate neurotoxic exposure was obtained. A possible metformin-related B12 pathway overlaps the second differential rather than supplying a distinct third cause.'),
    'neuro-recurrent-headache': (
        'Medication-overuse headache',
        'The demonstrated pattern is about two headaches per month and acetaminophen on only 2–3 days per month, which does not support medication-overuse headache.'),
    'renal-acute-retention': (
        'Neurogenic bladder due to multiple sclerosis',
        'Urinary retention alone, without obtained evidence of prior neurologic episodes or focal neurologic disease, does not support attributing the bladder problem to multiple sclerosis.'),
    'renal-luts-nocturia': (
        'Diabetes mellitus with osmotic diuresis',
        'The patient described small-volume voids. No glucose result or established osmotic polyuria was obtained; family history alone does not supply those findings.'),
}

# Authored family facts, translated into ordinary note style. These retain the
# patient's qualifications and never turn a relative's disease into the patient's.
_FAMILY_PROSE = {
    'cardio-febrile-cough': 'Mother, 52, has asthma. Father, 55, has hypertension. Sister, 27, is healthy.',
    'cardio-orthopnea-edema': 'Mother, 58, has hypertension. Father died at 72 after a myocardial infarction. Brother, 34, has hypertension.',
    'cardio-palpitations': 'Mother, 54, has hypertension. Father, 57, has atrial fibrillation. Sister, 24, is healthy. No known sudden death in the family before age 50.',
    'cardio-pleuritic-dyspnea': 'Mother, 54, has hypertension. Father, 56, and sister, 29, have no known major illness. No known inherited clotting disorder in the family.',
    'cardio-presyncope': 'Mother, 62, has hypertension. Father died of pneumonia at 80. Brother, 32, is healthy.',
    'gi-diarrhea-dehydration': 'Mother, 52, and father, 55, have no major disease. Brother, 23, is healthy. No family history of inflammatory bowel disease.',
    'gi-epigastric-back-pain': 'Mother, 56, has diabetes. Father, 58, has hyperlipidemia. Sister, 25, is healthy.',
    'gi-progressive-dysphagia': 'Mother is living and had a stroke at 78. Father died of lung cancer at 70. One sister is healthy.',
    'gi-right-lower-pain': 'Mother, 56, has hypertension. Father, 58, and sister are healthy.',
    'gi-right-upper-pain': 'Mother, 54, underwent gallbladder surgery. Father, 56, has diabetes. Brother, 31, is healthy.',
    'neuro-acute-focal-weakness': 'Mother, 72, had a stroke at 70. Father, 64, has diabetes. Brother, 34, has hypertension.',
    'neuro-back-bladder-redflags': 'Mother, 53, has hypertension. Father, 56, and brother, 30, are healthy. No known inherited neurologic illness in the family.',
    'neuro-distal-neuropathy': 'Mother, 52, has diabetes. Father, 55, has hypertension. Brother, 31, is healthy. No known family history of similar nerve problems.',
    'neuro-positional-vertigo': 'Mother, 51, has hypertension. Father, 54, has diabetes. One sister is healthy.',
    'neuro-recurrent-headache': 'Mother, 52, has migraines. Father, 55, has hypertension. Brother, 29, is healthy.',
    'renal-acute-retention': 'Father, 58, has an enlarged prostate. Mother, 56, has hypertension. Brother, 29, is healthy.',
    'renal-colicky-flank': 'Father, 56, has recurrent kidney stones. Mother, 54, has hypertension. One sister is healthy.',
    'renal-dysuria': 'Mother, 56, has hypertension. Father, 58, and brother, 32, are healthy.',
    'renal-luts-nocturia': 'Father, 55, has hypertension. Mother, 53, has diabetes. Brother, 22, is healthy.',
    'renal-painless-hematuria': 'Mother, 62, has hypertension. Father died of a stroke at 76. Sister, 32, is healthy. No known family history of kidney disease.',
}

_FAMILY_ORIGINAL = {'cardio-febrile-cough': 'My mother is fifty-two and she has asthma.; My father is fifty-five '
                         "and he has high blood pressure.; I have one sister, she's twenty-seven "
                         "and she's healthy.",
 'cardio-orthopnea-edema': 'My mother is fifty-eight and she has high blood pressure.; My father '
                           'died at seventy-two, after a heart attack.; My brother is '
                           'thirty-four and he has high blood pressure.',
 'cardio-palpitations': 'My mother is fifty-four and she has high blood pressure.; My father is '
                        'fifty-seven and he has atrial fibrillation.; My sister is twenty-four '
                        "and she's healthy.; Nobody in my family has died suddenly before the "
                        'age of fifty, as far as I know.',
 'cardio-pleuritic-dyspnea': "My mom is fifty-four and she has high blood pressure.; My dad's "
                             "fifty-six and I have one sister who's twenty-nine, and neither of "
                             "them has any major illness that I know of.; There's no inherited "
                             'clotting disorder in the family that I know of.',
 'cardio-presyncope': 'My mother is sixty-two and she has high blood pressure.; My father died '
                      "of pneumonia when he was eighty.; I have one brother, he's thirty-two and "
                      "he's healthy.",
 'gi-diarrhea-dehydration': 'My mom is fifty-two and my dad is fifty-five, and neither of them '
                            "has any major disease.; I have a brother who's twenty-three and "
                            "he's healthy.; No one in my family has inflammatory bowel disease.",
 'gi-epigastric-back-pain': 'My mom is fifty-six and she has diabetes.; My dad is fifty-eight '
                            'and he has hyperlipidemia, the high fats in his blood.; I have a '
                            "sister who's twenty-five and she's healthy.",
 'gi-progressive-dysphagia': 'My mother is still alive, and she had a stroke when she was '
                             'seventy-eight.; My father died of lung cancer when he was '
                             'seventy.; I have one sister and she is healthy.',
 'gi-right-lower-pain': "My mom is fifty-six and she has high blood pressure.; My dad's "
                        "fifty-eight and he's healthy, and my sister's healthy too.",
 'gi-right-upper-pain': 'My mother is fifty-four and she had gallbladder surgery.; My father is '
                        "fifty-six and he has diabetes.; My brother is thirty-one and he's "
                        'healthy.',
 'neuro-acute-focal-weakness': 'My mother is seventy-two and she had a stroke when she was '
                               'seventy.; My father is sixty-four and he has diabetes.; My '
                               'brother is thirty-four and he has high blood pressure.',
 'neuro-back-bladder-redflags': 'My mom is fifty-three and she has high blood pressure.; My dad '
                                "is fifty-six and he's healthy.; My brother is thirty and he's "
                                'healthy.; No one in my family has an inherited neurologic '
                                'illness that I know of.',
 'neuro-distal-neuropathy': "My mother is fifty-two and she has diabetes.; My father's "
                            "fifty-five and he has high blood pressure.; I have a brother who's "
                            "thirty-one, and he's healthy.; As far as I know, nerve problems "
                            "like this don't run in my family.",
 'neuro-positional-vertigo': 'My mom is fifty-one and she has high blood pressure.; My dad is '
                             "fifty-four and he has diabetes.; I have one sister and she's "
                             'healthy.',
 'neuro-recurrent-headache': 'My mom is fifty-two and she gets migraines.; My dad is fifty-five '
                             "and he has high blood pressure.; I have one brother, he's "
                             "twenty-nine and he's healthy.",
 'renal-acute-retention': "My dad is fifty-eight and he's had an enlarged prostate.; My mom is "
                          "fifty-six and she has high blood pressure.; I have one brother, he's "
                          "twenty-nine and he's healthy.",
 'renal-colicky-flank': "My dad is fifty-six and he's had kidney stones over and over.; My mom "
                        'is fifty-four and she has high blood pressure.; I have one sister and '
                        "she's healthy.",
 'renal-dysuria': "My mom is fifty-six and she has high blood pressure.; My dad's fifty-eight "
                  "and he's healthy, and I have one brother who's thirty-two and doing fine.",
 'renal-luts-nocturia': 'My dad is fifty-five and he has high blood pressure.; My mom is '
                        "fifty-three and she's had diabetes.; I have one brother, he's "
                        "twenty-two and he's healthy.",
 'renal-painless-hematuria': 'My mother is sixty-two and she has high blood pressure.; My father '
                             'died of a stroke when he was seventy-six.; I have one sister, '
                             "she's thirty-two and she's healthy.; Kidney disease doesn't run in "
                             'my family as far as I know.'}

_LABELS = (
    'Reproductive history', 'Additional PMH', 'Patient concern', 'Urinary history',
    'Voided volume', 'Pain pattern', 'Bowel history', 'Care needs', 'PSH/admissions',
    'Perspective', 'Allergies', 'Meds', 'PMH', 'PSH', 'HPI', 'ROS', 'SH', 'FH', 'CC',
)
_LABEL_RE = re.compile(r'(?<!\w)(' + '|'.join(map(re.escape, _LABELS)) + r')\s*:', re.I)
_GROUP_CATEGORIES = {
    'Chief complaint': {'chief_complaint'},
    'History of present illness': {'chief_complaint', 'onset', 'chronology', 'location', 'radiation', 'quality', 'severity', 'timing', 'setting', 'alleviating', 'aggravating', 'treatment', 'past_occurrence', 'associated', 'pertinent_negative', 'fife'},
    'Past medical and surgical history': {'pmh', 'psh'},
    'Medications': {'medications', 'treatment'},
    'Social history': {'social', 'obgyn', 'fife'},
    'Family history': {'family'},
    'Allergies': {'allergies'},
    'Review of systems': {'associated', 'pertinent_negative', 'obgyn'},
}


def _clean(text):
    return re.sub(r'[ \t]+', ' ', str(text)).strip()


def _history_chunks(text):
    matches = list(_LABEL_RE.finditer(text))
    chunks = []
    if not matches:
        return [('hpi', _clean(text))] if text.strip() else []
    if text[:matches[0].start()].strip():
        chunks.append(('hpi', _clean(text[:matches[0].start()])))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunks.append((match.group(1).lower(), _clean(text[match.end():end])))
    return chunks


def _history_sources(case, lesson, categories):
    fact_map = {f['id']: f for f in case.get('facts', [])}
    event_ids, fact_ids = set(), set()
    for turn in lesson.get('timeline', []):
        if turn.get('kind') != 'dialogue':
            continue
        relevant = {f for f in turn.get('fact_ids', []) if fact_map.get(f, {}).get('category') in categories}
        if relevant:
            fact_ids.update(relevant)
            event_ids.update(turn.get('event_ids', []))
    return {'event_ids': sorted(event_ids), 'fact_ids': sorted(fact_ids),
            'trace_scope': 'Delivered history topics for review; not an automatic statement-level semantic verdict.'}


def _clinical_ros(content):
    """Condense explicit reported/denied ROS statements without adding normals."""
    matches = list(re.finditer(r'([A-Z][a-z]+) - ', content))
    if not matches or content[:matches[0].start()].strip():
        return content
    result = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[match.end():end].strip()
        statements = list(re.finditer(r'(Reports|Denies) ([^.]+)\.', body))
        if not statements or re.sub(r'(Reports|Denies) [^.]+\.\s*', '', body):
            return content
        positive = [x.group(2) for x in statements if x.group(1) == 'Reports']
        negative = [x.group(2) for x in statements if x.group(1) == 'Denies']
        positive = [('paroxysmal nocturnal dyspnea' if x == 'pnd' else x) for x in positive]
        def join(values):
            return ', '.join(values[:-1]) + ' and ' + values[-1] if len(values) > 1 else values[0]
        clauses = ([join(positive)] if positive else []) + (['no ' + join(negative)] if negative else [])
        sentence = '; '.join(clauses)
        result.append(match.group(1) + ': ' + sentence[:1].upper() + sentence[1:] + '.')
    return '\n\n'.join(result)


_CLINICAL_HISTORY_PHRASES = {
    'I do not think I am pregnant, but I have not taken a pregnancy test.': 'Pregnancy not suspected by patient; patient has not taken a pregnancy test.',
    'My last period was 2 weeks ago.': 'LMP 2 weeks ago.',
    'I have had eczema since childhood.': 'Eczema since childhood.',
    'I am still able to pass urine.': 'Continues to pass urine.',
    'I pass small amounts each time, not large volumes.': 'Small amounts with each void; no large-volume urination.',
    'The pain is constant.': 'Pain is constant.',
    'My bowel movements have been usual. I have not had diarrhea or constipation.': 'Usual bowel pattern; no diarrhea or constipation.',
}


def _subjective(case, lesson, corrections):
    text = lesson['note']['S']
    for old, new, reason, category in _EVIDENCE_CORRECTIONS.get(lesson['case_id'], []):
        if old in text:
            text = text.replace(old, new)
            corrections.append({'original': old, 'replacement': new, 'reason': reason,
                                **_history_sources(case, lesson, {category})})
    grouped = {heading: [] for heading in SUBJECTIVE_ORDER}
    clinical_labels = {
        'cc': 'Chief complaint', 'hpi': 'History of present illness',
        'pmh': 'Past medical and surgical history', 'psh': 'Past medical and surgical history',
        'psh/admissions': 'Past medical and surgical history', 'additional pmh': 'Past medical and surgical history',
        'meds': 'Medications', 'sh': 'Social history', 'fh': 'Family history',
        'allergies': 'Allergies', 'ros': 'Review of systems',
        'reproductive history': 'Review of systems',
        'perspective': 'History of present illness', 'patient concern': 'History of present illness',
        'care needs': 'History of present illness', 'urinary history': 'History of present illness',
        'voided volume': 'History of present illness', 'pain pattern': 'History of present illness',
        'bowel history': 'History of present illness',
    }
    prefixes = {'pmh': 'Medical: ', 'additional pmh': 'Additional medical history: ',
                'psh': 'Surgical/procedural: ', 'psh/admissions': 'Surgical/admissions: ',
                'reproductive history': 'Reproductive: ', 'perspective': 'Patient concern: ',
                'patient concern': 'Patient concern: ', 'care needs': 'Care needs: ',
                'urinary history': 'Urinary history: ', 'voided volume': 'Voided volume: ',
                'pain pattern': 'Pain pattern: ', 'bowel history': 'Bowel history: '}
    for label, content in _history_chunks(text):
        if label == 'meds':
            # The four compact source notes put their allergy at the end of the
            # medicines line. Move the exact existing statement, not an inference.
            m = re.search(r'\s+(NKDA\.|Penicillin causes lip/facial swelling\.|Sulfonamides cause hives\.)\s*$', content)
            if m:
                allergy = 'No known drug allergies.' if m.group(1) == 'NKDA.' else m.group(1)
                grouped['Allergies'].append(allergy)
                content = content[:m.start()].strip()
        if label == 'fh' and content == _FAMILY_ORIGINAL.get(case['id']):
            content = _FAMILY_PROSE[case['id']]
        if label == 'pmh' and content == "Type 2 diabetes — they diagnosed me at 18, about ten years ago; and my last A1c was high, though I don't remember the number.":
            content = 'Type 2 diabetes diagnosed at age 18, approximately 10 years ago. Most recent A1c reportedly high; value not recalled.'
        if label == 'ros':
            if case['id'] == 'gi-diarrhea-dehydration':
                content = content.replace('Reports urine output.', 'Reports reduced urine output.')
            content = _clinical_ros(content)
        if label in ('reproductive history', 'additional pmh', 'urinary history', 'voided volume', 'pain pattern', 'bowel history'):
            content = _CLINICAL_HISTORY_PHRASES.get(content, content)
        if label == 'sh':
            content = content.replace('lives with my husband', 'lives with husband')
        if content:
            grouped[clinical_labels[label]].append(prefixes.get(label, '') + content)
    return [{'heading': heading, 'text': '\n\n'.join(grouped[heading]),
             **_history_sources(case, lesson, _GROUP_CATEGORIES[heading])}
            for heading in SUBJECTIVE_ORDER if grouped[heading]]


def _objective(lesson):
    # Preserve complete observed/supplied strings. Grouping repeated system names
    # changes layout only; a normal finding is never synthesized here.
    sections = OrderedDict()
    for line in lesson['note']['O'].splitlines():
        line = line.strip()
        if not line:
            continue
        heading, sep, content = line.partition(':')
        if not sep:
            heading, content = 'Examination', line
        supplied = heading == 'Vitals' or heading.startswith('Supplied ')
        if heading.startswith('Supplied '):
            content = heading[len('Supplied '):] + ': ' + content.strip()
            heading = 'Supplied results'
        elif heading == 'Vitals':
            heading = 'Supplied vital signs'
        bucket = sections.setdefault(heading, {'heading': heading, 'paragraphs': [], 'event_ids': set(),
                                                'source_type': 'supplied' if supplied else 'examined'})
        bucket['paragraphs'].append(content.strip())
        if supplied:
            for event in lesson.get('ledger', []):
                if event.get('kind') == 'station_info':
                    bucket['event_ids'].add(event['seq'])
        else:
            for turn in lesson.get('timeline', []):
                if turn.get('finding') and turn['finding'] == content.strip():
                    bucket['event_ids'].update(turn.get('event_ids', []))
    return [{**section, 'text': '\n\n'.join(section['paragraphs']), 'event_ids': sorted(section['event_ids'])}
            for section in sections.values()]


def build_example_note(case, lesson):
    """Return a print-only clinical note from this exact demonstrated lesson.

    Caller must pass the resolved case variation. Content outside the demonstrated
    note is not imported merely because it is visible in the actor reference.
    """
    if case.get('id') != lesson.get('case_id') or case.get('variant_id', 'base') != lesson.get('variant_id', 'base'):
        raise ValueError('The example note requires its matching resolved case and variation.')
    if any(case.get('patient', {}).get(k) != lesson.get('patient', {}).get(k) for k in ('name', 'age', 'sex')):
        raise ValueError('The example note and resolved patient identity do not match.')
    note = lesson['note']
    corrections = []
    subjective = _subjective(case, lesson, corrections)
    objective = _objective(lesson)
    timeline = lesson.get('timeline', [])
    facts = sorted({f for t in timeline for f in t.get('fact_ids', [])})
    assessment, plans, omitted = [], [], []
    gaps = _DIFFERENTIAL_GAPS.get(case['id'])
    for i, item in enumerate(note['A'], 1):
        diagnosis = re.sub(r'^\d+\.\s*', '', item).strip()
        raw_plan = note['P'][i - 1] if i - 1 < len(note['P']) else ''
        plan_text = re.sub(r'^\d+\.\s*', '', raw_plan).strip()
        authored = next((x for x in lesson.get('differentials', []) if x.get('name') == diagnosis), {})
        support = [f for f in authored.get('supported_by', []) if f in facts]
        source_events = sorted({e for t in timeline if set(t.get('fact_ids', [])) & set(support) for e in t.get('event_ids', [])})
        if gaps and diagnosis == gaps[0]:
            omitted.append({'rank': i, 'diagnosis': diagnosis, 'reason': gaps[1],
                            'original_assessment': item, 'original_plan': raw_plan})
            continue
        assessment.append({'rank': i, 'text': diagnosis, 'fact_ids': support,
                           'event_ids': source_events,
                           'status': 'working differential' if i == 1 else 'lower-ranked differential',
                           'trace_scope': 'Authored differential tied to the complete demonstrated history and examination; diagnosis not confirmed.'})
        condition = 'Recommended initial assessment and management' if i == 1 else 'Conditional alternative; directed by the assessment and test results'
        if i == 2 and case['id'] in ('neuro-acute-focal-weakness', 'gi-right-lower-pain'):
            condition = 'Parallel urgent assessment; do not defer while evaluating the leading diagnosis'
        plans.append({'rank': i, 'diagnosis': diagnosis, 'text': plan_text,
                      'condition': condition, 'event_ids': [],
                      'source_type': 'proposed management; not a completed action or obtained finding'})
    outside = [
        {'kind': 'scope', 'text': 'Example for the complete demonstrated encounter. This note uses the supplied information and the history and examinations in that example. Your own submitted note must reflect only what you actually obtained during your attempt.'},
        {'kind': 'plan', 'text': 'Plan numbers correspond to the ranked differentials. Alternative treatment or referral branches apply only if their clinical conditions are met; shared diagnostic tests need not be ordered twice. Urgent parallel assessments are identified separately.'},
    ]
    if omitted:
        outside.append({'kind': 'authoring_gap', 'text': 'This case needs additional authoring for a third supported differential. The unsupported entry has been left out of the clinical note rather than invented: ' + ' '.join(x['diagnosis'] + ' — ' + x['reason'] for x in omitted)})
    if case['id'] == 'renal-colicky-flank':
        outside.append({'kind': 'authoring_gap', 'text': 'Course-format limitation: the leading plan says prompt follow-up without a specific routine interval. The third plan also lacks a clearly distinct third MOTHERR element. Clarify these with the instructor; the print edition does not invent an interval or add unnecessary treatment to fill the rubric.'})
    if case['id'] == 'cardio-palpitations':
        outside.append({'kind': 'authoring_gap', 'text': 'Course-format limitation: the third plan supplies testing and referral but does not establish a third distinct MOTHERR element. The second plan also needs clarification of how its existing components are classified. The clinical alternatives are retained without adding unnecessary care to fill the rubric.'})
    if case['id'] == 'renal-flank-pain':
        outside.append({'kind': 'source_conflict', 'text': 'The source dialogue alternates between husband and boyfriend. The example note preserves the obtained household history and the neutral phrase one male sexual partner without inventing an explanation for that relationship-label conflict.'})
    return {'schema_version': 1, 'label': 'Example for the complete demonstrated encounter',
            'encounter_definition': {'history_turns': sum(t.get('kind') == 'dialogue' for t in timeline),
                                     'examination_results': sum(bool(t.get('finding')) for t in timeline),
                                     'supplied_vitals': bool(lesson.get('doorway', {}).get('vitals')),
                                     'evidence_rule': 'Actor reference facts are not automatically obtained evidence.'},
            'subjective': subjective, 'objective': objective, 'assessment': assessment,
            'plan': plans, 'outside_note': outside, 'corrections': corrections,
            'omitted_authored_alternatives': omitted,
            'source': {'case_id': lesson['case_id'], 'variant_id': lesson['variant_id'],
                       'case_hash': lesson.get('case_hash'), 'fact_ids': facts,
                       'event_ids': [e['seq'] for e in lesson.get('ledger', [])],
                       'legacy_not_evaluated_statements': lesson.get('documentation_audit', {}).get('unresolved_count', 0),
                       'clinical_review': 'Source-based synthetic teaching example; not faculty approved.'}}
