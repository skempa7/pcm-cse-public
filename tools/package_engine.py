"""Bundle the provider-free browser engine and stamp its cache tag.

The tag in engine-worker.mjs is derived from the ZIP's CONTENT. A hand-managed
tag drifts: the engine was rebuilt with a real behaviour fix while the URL kept
its old ?v= value, so an already-open or installed client could keep running
the previous engine and the fix looked like it had not shipped. Deriving the
tag removes that failure mode entirely -- new bytes always mean a new URL.

The ZIP is written deterministically (fixed timestamps, sorted entries) so an
unchanged engine keeps its tag and clients are not forced to re-download.
"""
import hashlib
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "web/engine.zip"
WORKER = ROOT / "web/engine-worker.mjs"

members = [(ROOT / "offline_routes.py", "offline_routes.py")]
for path in sorted((ROOT / "pcmcse").rglob("*")):
    if path.is_file() and path.suffix in (".json", ".py"):
        members.append((path, str(path.relative_to(ROOT))))

with zipfile.ZipFile(BUNDLE, "w", zipfile.ZIP_DEFLATED) as bundle:
    for source, name in members:
        # A fixed timestamp keeps the archive byte-identical when the sources
        # are unchanged, so the derived tag is stable across rebuilds.
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        bundle.writestr(info, source.read_bytes())

digest = hashlib.sha256(BUNDLE.read_bytes()).hexdigest()[:10]
worker = WORKER.read_text()
updated, count = re.subn(r"engine\.zip\?v=[A-Za-z0-9._-]+",
                         "engine.zip?v=" + digest, worker)
if not count:
    raise SystemExit("engine.zip cache tag not found in %s" % WORKER.name)
if updated != worker:
    WORKER.write_text(updated)

print("Bundled provider-free browser engine (%d files, tag %s)" % (len(members), digest))
