"""Verify actual PDF exports after test_partner_print_layout.cjs (requires PyMuPDF).

This checks exported content/geometry. It is not a clinical or human-usability verdict.
"""
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
import fitz

out = Path(sys.argv[1])
root = Path(__file__).resolve().parents[1]
manifest = json.loads((out / 'matrix.json').read_text())
for name, expected in manifest['source'].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name + ' changed after rendering'
lessons = {(l['case_id'], l['variant_id']): l for l in json.loads((out / 'lessons.json').read_text())}
def normalized(text):
    # Preserve authored hyphens while joining a physical line wrap after them.
    text = re.sub(r'(?<=\w)-[ \t]*\n[ \t]*(?=\w)', '-', text)
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text)).strip()
counts = {'files': 0, 'pages': 0, 'patient_responses': 0, 'note_paragraphs': 0}
issues = []
for item in manifest['results']:
    l = lessons[item['case_id'], item['variant_id']]
    name = f"{item['case_id']}--{item['variant_id']}--{item['edition']}.pdf"
    doc = fitz.open(out / name)
    assert len(doc) == item['pages'], (name, 'exported page count differs', len(doc), item['pages'])
    text = normalized(' '.join(p.get_text() for p in doc))
    assert '[object Object]' not in text and 'undefined' not in text, name
    for i, page in enumerate(doc):
        w, h = page.rect.width, page.rect.height
        assert (round(w), round(h)) in [(792, 612), (612, 792)], (name, 'not Letter', page.rect)
        assert normalized(f'{i+1} / {len(doc)}') in normalized(page.get_text()), (name, i, 'missing footer')
        for block in page.get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)['blocks']:
            for line in block.get('lines', []):
                for span in line['spans']:
                    x0,y0,x1,y1 = span['bbox']
                    if x0 < 15 or y0 < 15 or x1 > w-15 or y1 > h-15:
                        issues.append({'file':name,'page':i+1,'bounds':span['bbox'],'text':span['text']})
        assert page.get_text().strip(), (name, i, 'blank PDF page')
    if item['edition'] == 'blank':
        # Check the actual exported ruling, not a CSS gradient declaration.
        # Two useful writing groups per page; quarter-inch-plus line spacing.
        for i, page in enumerate(doc):
            first_heading = page.search_for('Subjective' if i == 0 else 'Assessment')
            assert len(first_heading) == 1, (name, i, 'missing writing heading')
            ys = sorted({round(d['rect'].y0, 2) for d in page.get_drawings()
                         if d['rect'].width > 480 and 0 < d['rect'].height <= 1.5
                         and first_heading[0].y1 < d['rect'].y0 < 720})
            groups = []
            for y in ys:
                if not groups or y - groups[-1][-1] > 25:
                    groups.append([y])
                else:
                    groups[-1].append(y)
            assert [len(g) for g in groups] == ([14, 9] if i == 0 else [9, 18]), (name, i, 'writing rules missing or clustered', groups)
            assert all(19 <= b-a <= 21 for g in groups for a,b in zip(g,g[1:])), (name, i, 'uneven writing rules')
    if item['edition'] in ('patient', 'study'):
        script = l['partner_script']
        for answer in [script['briefing']['opening']] + [value for s in script['sections'] for t in s['topics'] for value in [t['answer']] + [f['answer'] for f in t['followups']]]:
            assert normalized(answer) in text, (name, 'patient response missing', answer)
            counts['patient_responses'] += 1
    if item['edition'] in ('soap', 'study'):
        note = l['partner_note']
        for row in note['subjective'] + note['objective']:
            for paragraph in row['text'].split('\n\n'):
                assert normalized(paragraph) in text, (name, 'note paragraph missing', paragraph)
                counts['note_paragraphs'] += 1
        for row in note['assessment']:
            assert normalized(row['text']) in text, (name, row['text'])
        for row in note['plan']:
            assert normalized(row['text']) in text, (name, 'plan missing', row['text'])
    counts['files'] += 1
    counts['pages'] += len(doc)
    doc.close()
assert not issues, issues[:10]
result = {'result': 'PASS', **counts, 'geometry_issues': issues,
          'limits': 'Page count, Letter geometry, text bounds, printed source content, and build identity. Visual and clinical review are separate.'}
(out / 'pdf-verification.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result))
