"""Non-answer-bearing material for preparation and blank-note printing.

The allowlist is intentional: no clinical facts, findings, notes, or hidden
patient biography cross this route. Answer editions keep the teaching guard.
"""
from copy import deepcopy
from .. import cases, physexam, station_info


def index():
    return [{'id': c['id'], 'title': c['title'], 'system': c['system'],
             'variants': [{'id': 'base', 'label': 'Core presentation'}, *c['variants']]}
            for c in cases.index()]


def doorway(case_id, variant='base'):
    case = cases.resolve(case_id, variant)
    labels = {v['id']: v.get('label', v['id']) for v in cases.get(case_id).get('variants', [])}
    return {'case_id': case_id, 'variant_id': variant,
            'variant_label': labels.get(variant, 'Core presentation'),
            'patient': {k: case['patient'][k] for k in ('name', 'sex')},
            'doorway': {k: (station_info.doorway(case) if k == 'doorway' else deepcopy(case['station'].get(k, [] if k != 'vitals' else {})))
                        for k in ('doorway', 'vitals', 'supplied_results')},
            'title': case['title'], 'timeline': []}


def examinations(case, lesson):
    systems = {'Heart': 'Cardiovascular', 'Lungs': 'Respiratory', 'HEENT': 'HEENT & neck',
               'Neck': 'HEENT & neck', 'Neurologic': 'Neurological'}
    catalog = {m['id']: m for m in physexam.CATALOG}
    additions = case.get('print_additional_exams', {})
    return [{**turn, 'system': case.get('print_exam_systems', {}).get(turn['maneuver_id'],
                 systems.get(catalog[turn['maneuver_id']]['region'], catalog[turn['maneuver_id']]['region'])),
             'condition': additions.get(turn['maneuver_id'], '')}
            for turn in lesson['timeline'] if turn.get('maneuver_id') in catalog]
