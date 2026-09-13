"""Derive release cache tags from actual bytes, including nested JS URLs.

Run after packaging Python and rebuilding the 3D bundle. Dependencies are
stamped before their parents, so one run updates the full browser load chain.
Use --check to reject stale or missing references without writing anything.
"""
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY_FILES = (
    'web/index.html', 'web/patient3d/index.html', 'web/app.js',
    'web/public-runtime.js', 'web/engine-worker.mjs', 'web/study.js',
    'web/walkthrough-print.js',
)
REFERENCE = re.compile(r'''(["'])([A-Za-z0-9._/-]+)(\?v=)([A-Za-z0-9._-]+)(["'])''')


def stamp_tree(root=ROOT, check=False):
    entries = {(root / name).resolve() for name in ENTRY_FILES}
    stale, missing, rendered, visiting = [], [], {}, set()
    scanned = 0

    def render(page):
        nonlocal scanned
        if page in rendered:
            return rendered[page]
        if page in visiting:
            raise ValueError('Circular cache dependency: ' + str(page))
        visiting.add(page)

        def stamp(match):
            nonlocal scanned
            prefix, name, marker, current, suffix = match.groups()
            target = (page.parent / name).resolve()
            if not target.is_file():
                missing.append('%s -> %s' % (page.name, name))
                return match.group(0)
            scanned += 1
            data = render(target) if target in entries else target.read_bytes()
            digest = hashlib.sha256(data).hexdigest()[:10]
            if digest != current:
                stale.append('%s: %s %s -> %s' % (page.name, name, current, digest))
            return prefix + name + marker + digest + suffix

        rendered[page] = REFERENCE.sub(stamp, page.read_text()).encode()
        visiting.remove(page)
        return rendered[page]

    for page in sorted(entries):
        if not page.is_file():
            missing.append(str(page.relative_to(root)))
        else:
            render(page)
    if not check and not missing:
        for page, data in rendered.items():
            if data != page.read_bytes():
                page.write_bytes(data)
    for item in missing:
        print('  missing file for cache tag: ' + item)
    for item in stale:
        print('  %s %s' % ('STALE' if check else 'stamped', item))
    print('%d references checked, %d %s' % (scanned, len(stale), 'stale' if check else 'restamped'))
    return int(bool(missing or (check and stale)))


if __name__ == '__main__':
    raise SystemExit(stamp_tree(check='--check' in sys.argv))
