"""Derive every ?v= cache tag from the bytes of the file it points at.

A hand-written tag drifts, and the failure is always the same shape: the file
is fixed, the tag is not, the browser keeps the copy it already has, and the
fix looks like it never shipped. It has now happened three times in this
project -- web/engine.zip, web/patient3d/dist/room.js, and web/learning.js --
so the tags are derived rather than remembered.

Content-derived means unchanged files keep their tag and are not re-downloaded
for nothing, while any real change always produces a new URL.

    python3 tools/stamp_cache_tags.py           # rewrite the tags
    python3 tools/stamp_cache_tags.py --check   # non-zero if any tag is stale
"""
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = (ROOT / "web/index.html", ROOT / "web/patient3d/index.html")
REFERENCE = re.compile(r'((?:src|href)=")([A-Za-z0-9._/-]+)(\?v=)([A-Za-z0-9._-]+)(")')


def main():
    check = "--check" in sys.argv
    stale, missing, scanned = [], [], 0
    for page in PAGES:
        if not page.exists():
            continue
        text = page.read_text()
        updated = text

        def stamp(match):
            nonlocal scanned
            prefix, name, marker, current, suffix = match.groups()
            target = (page.parent / name).resolve()
            if not target.exists():
                missing.append("%s -> %s" % (page.name, name))
                return match.group(0)
            scanned += 1
            digest = hashlib.sha256(target.read_bytes()).hexdigest()[:10]
            if digest != current:
                stale.append("%s: %s %s -> %s" % (page.name, name, current, digest))
            return prefix + name + marker + digest + suffix

        updated = REFERENCE.sub(stamp, updated)
        if updated != text and not check:
            page.write_text(updated)

    for item in missing:
        print("  missing file for cache tag: %s" % item)
    if check:
        for item in stale:
            print("  STALE %s" % item)
        print("%d references checked, %d stale" % (scanned, len(stale)))
        return 1 if stale or missing else 0
    for item in stale:
        print("  stamped %s" % item)
    print("%d references checked, %d restamped" % (scanned, len(stale)))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
