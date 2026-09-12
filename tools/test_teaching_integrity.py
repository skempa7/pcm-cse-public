"""Check current lesson identity and actual dialogue/examination evidence links.

This is a content/engine consistency check. Unresolved note wording is reported
separately; passing is not faculty review or clinical validation.
"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pcmcse import audit, cases, evidence, note, teaching, version


def main():
    checked = Counter()
    for cid, base in cases.all_cases().items():
        for vid in ['base'] + [v['id'] for v in base.get('variants', [])]:
            case = cases.resolve(cid, vid)
            lesson = teaching.read(cid, vid)
            context = cid + '/' + vid
            assert lesson['case_hash'] == hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest(), context + ': stale case source'
            assert lesson.get('engine_version') == version.ENGINE_VERSION, context + ': stale engine; regenerate lessons'
            assert not lesson['missing_example_facts'], context + ': unelicited lesson facts'
            assert lesson['estimated_encounter_s'] <= 840 and lesson['note_words'] <= 550, context + ': lesson exceeds authored scope'
            events = {e['seq']: e for e in lesson['ledger']}
            assert list(events) == list(range(1, len(events) + 1)), context + ': broken event ordering'
            for row in lesson['timeline']:
                selected = [events[seq] for seq in row['event_ids']]
                if row['kind'] == 'dialogue':
                    replies = [e for e in selected if e['kind'] == evidence.PATIENT]
                    assert row['patient'] == ' '.join(e['text'] for e in replies), context + ': displayed reply differs from delivered speech'
                    assert set(row['fact_ids']) == {f for e in replies for f in e['meta'].get('facts_released', [])}, context + ': broken reply fact links'
                    checked['dialogue_turns'] += 1
                elif row.get('maneuver_id'):
                    actual = [e for e in selected if e['kind'] == evidence.EXAM_FINDING]
                    assert row['finding'] == ' '.join(e['text'] for e in actual), context + ': displayed finding differs from performed examination'
                    checked['exam_actions'] += 1
            for link in lesson['note_links']:
                assert all(seq in events for seq in link['event_ids']), context + ': note refers to missing evidence'
            result = audit.audit_note(note.parse(lesson['note']), evidence.Ledger(lesson['ledger']), case)
            failures = [c for c in result['claims'] if c['verdict'] in ('unsupported', 'contradicts', 'overbroad', 'counseling_unsupported')]
            assert not failures, context + ': ' + json.dumps([(c['text'], c['verdict']) for c in failures])
            unresolved = sum(c['verdict'] == 'not_evaluated' for c in result['claims'])
            assert lesson['documentation_audit']['unresolved_count'] == unresolved, context + ': stale cached note audit'
            assert not lesson['documentation_audit']['unsupported'], context + ': stale or failing cached note audit'
            checked['unresolved_note_statements'] += unresolved
            checked['lessons'] += 1
    assert checked['lessons'] == 72
    print(json.dumps({'result': 'PASS', **checked,
                      'limits': 'Current sources and delivered-event consistency; unresolved wording receives no automatic credit. Not clinical validation.'}, indent=2))


if __name__ == '__main__':
    main()
