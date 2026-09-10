"""Regenerate PUBLIC-MANIFEST.json for the published static edition.

The manifest records exactly what is tracked in this repository and asserts the
publishing boundaries. The boolean fields are COMPUTED here, not restated: this
script inspects the tracked files and reports what it actually finds, so a
manifest can never claim a boundary that the tree no longer honors.

    python3 tools/build_manifest.py          # rewrite the manifest
    python3 tools/build_manifest.py --check  # verify only; non-zero if stale

PUBLIC-MANIFEST.json is excluded from its own counts and hashes.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "PUBLIC-MANIFEST.json"

# Private-edition modules that must never be published. These implement paid
# provider routing and natural-voice synthesis; the public edition is scripted
# and provider-free.
PROVIDER_MODULES = {
    "pcmcse/ai_patient.py", "pcmcse/natural_voice.py",
    "web/ai-conversation.js", "web/natural-voice.js",
}
# A paid route is a call to a provider endpoint, not a mention of one. The
# public notices legitimately say the words "OpenAI" and "no paid services",
# so match on hosts and SDK entry points instead.
BILLABLE = re.compile(
    rb"api\.openai\.com|api\.anthropic\.com|openai\.(?:ChatCompletion|Audio|chat)"
    rb"|from\s+openai|import\s+openai|require\(['\"]openai|api\.stripe\.com",
    re.I,
)
CREDENTIAL = re.compile(
    rb"sk-[A-Za-z0-9]{20,}|sk-proj-[A-Za-z0-9_-]{20,}"
    rb"|OPENAI_API_KEY\s*[=:]\s*['\"][^'\"]+|ANTHROPIC_API_KEY\s*[=:]\s*['\"][^'\"]+",
)
# Files that legitimately contain a provider host as a NEGATIVE case. Each
# needs a stated reason and is reported on every run, so an exemption is always
# visible and can never become a silent hole. Anything not listed here fails.
ALLOWED_PROVIDER_MENTIONS = {
    "tools/test_runtime_recovery.cjs":
        "asserts that a request to a provider URL is REJECTED; the host string "
        "is the negative case the test proves, not a route the app can call",
}
COURSE_DOC = re.compile(r"\.(?:pdf|docx?|pptx?)$", re.I)
ATTEMPT_DB = re.compile(r"\.(?:db|sqlite3?)(?:-wal|-shm)?$", re.I)
# Text formats worth scanning for credentials and paid routes. Binary assets
# (.glb, images, engine.zip) are covered by the module/extension rules above.
SCANNED = {".py", ".js", ".mjs", ".cjs", ".html", ".css", ".json", ".md", ".txt", ".yml", ".yaml"}


def tracked_files():
    out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    return sorted(p for p in out.split("\n") if p and p != MANIFEST)


def build():
    files = tracked_files()
    provider, credentials, billable, course_docs, databases = [], [], [], [], []
    exempted = []
    total = 0
    digests = {}
    for rel in files:
        path = ROOT / rel
        data = path.read_bytes()
        total += len(data)
        digests[rel] = hashlib.sha256(data).hexdigest()
        if rel in PROVIDER_MODULES:
            provider.append(rel)
        if COURSE_DOC.search(rel):
            course_docs.append(rel)
        if ATTEMPT_DB.search(rel):
            databases.append(rel)
        if path.suffix.lower() in SCANNED:
            if CREDENTIAL.search(data):
                credentials.append(rel)
            if BILLABLE.search(data):
                if rel in ALLOWED_PROVIDER_MENTIONS:
                    exempted.append(rel)
                else:
                    billable.append(rel)

    attributes = ROOT / ".gitattributes"
    lfs = attributes.exists() and "filter=lfs" in attributes.read_text()

    manifest = {
        "files": len(files),
        "bytes": total,
        "provider_modules": bool(provider),
        "credentials": bool(credentials),
        "private_course_documents": bool(course_docs),
        "saved_attempt_databases": bool(databases),
        "billable_backend": bool(billable),
        "custom_workflows": (ROOT / ".github").exists(),
        "git_lfs": lfs,
        "sha256": digests,
    }
    findings = {
        "provider_modules": provider, "credentials": credentials,
        "private_course_documents": course_docs,
        "saved_attempt_databases": databases, "billable_backend": billable,
    }
    return manifest, findings, exempted


def main():
    manifest, findings, exempted = build()
    violations = {k: v for k, v in findings.items() if v}
    text = json.dumps(manifest, indent=2) + "\n"
    target = ROOT / MANIFEST
    check = "--check" in sys.argv

    # Report the boundaries FIRST. A newly added offending file is also a
    # staleness difference, so reporting staleness first would hide the far more
    # important finding exactly when it matters most.
    if violations:
        print("PUBLISHING BOUNDARY VIOLATION — do not push:")
        for key, hits in violations.items():
            print("  %s: %s" % (key, ", ".join(hits[:5])))
        if not check:
            print("\nRefusing to rewrite the manifest while the tree violates a "
                  "boundary; a manifest must never certify a tree like this.")
        return 2

    print("Boundaries verified: no provider modules, credentials, course "
          "documents, attempt databases, or paid routes in the tracked tree.")
    for rel in exempted:
        print("  stated exemption — %s: %s" % (rel, ALLOWED_PROVIDER_MENTIONS[rel]))

    if check:
        current = target.read_text() if target.exists() else ""
        if current != text:
            print("\nSTALE: PUBLIC-MANIFEST.json does not match the tracked tree.")
            print("Run: python3 tools/build_manifest.py")
            return 1
        print("Manifest matches the tracked tree (%d files, %d bytes)."
              % (manifest["files"], manifest["bytes"]))
    else:
        target.write_text(text)
        print("Wrote %s: %d files, %d bytes."
              % (MANIFEST, manifest["files"], manifest["bytes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
