"""Current supplementary taxonomy for separate regrades of older snapshots.

This adds an accepted hypothesis only. It changes neither the frozen case facts
nor old scores, and supplies no evidence of an etiology or examination result.
"""

SUPPLEMENTS = {'gi-right-upper-pain': {'alternatives': [{'rank': 4,
                                           'name': 'Peptic ulcer disease',
                                           'vindicate': 'I',
                                           'aliases': ['peptic ulcer disease',
                                                       'peptic ulcer',
                                                       'PUD',
                                                       'duodenal ulcer',
                                                       'gastric ulcer'],
                                           'supported_by': ['hpi_location',
                                                            'symptom_nausea',
                                                            'symptom_vomiting'],
                                           'teaching_context': 'Supplementary lower-likelihood '
                                                               'upper-abdominal differential. Category I '
                                                               'describes inflammatory mucosal disease; '
                                                               'neither H. pylori infection nor an NSAID '
                                                               'cause is established. This shares a category '
                                                               'with cholecystitis and does not supply a '
                                                               'third distinct VINDICATE category. '
                                                               'Persistent focal RUQ pain still requires '
                                                               'urgent evaluation for biliary and other '
                                                               'acute causes.',
                                           'review_status': 'author_source_checked_not_clinician_approved'}],
                         'source': {'title': 'NIDDK: Peptic ulcer symptoms, causes and diagnosis',
                                    'url': 'https://www.niddk.nih.gov/health-information/digestive-diseases/peptic-ulcers-stomach-ulcers',
                                    'kind': 'supplementary_clinical',
                                    'reviewed': '2026-09-09',
                                    'review_scope': 'Upper-abdominal symptom differential; possible H. '
                                                    'pylori/NSAID causes remain unconfirmed. No cause or '
                                                    'diagnosis is credited as an obtained patient fact.'}}}

def for_case(case):
    out=list(case.get('differentials',[]));names={d['name'].lower() for d in out}
    for d in SUPPLEMENTS.get(case.get('id'),{}).get('alternatives',[]):
        if d['name'].lower() not in names:out.append(d)
    return out
