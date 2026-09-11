"""Nothing in the published edition may be able to bill the owner.

This is the constraint the public edition exists under: a visitor must have no
way to spend the owner's money. `test_public_release.py` already proves the
paid ROUTES answer 404 and that the known provider modules are absent -- but a
deliberate test showed that a billable call added to `offline_routes.py`, or an
API key pasted into the shipped web bundle, both slipped past it untouched. A
list of filenames is not a boundary.

So this reads what actually ships -- the Python package, the web bundle, and
the contents of `web/engine.zip`, which is the file the browser downloads --
and fails on any paid-provider endpoint or credential, wherever it appears.

    python3 tools/check_provider_free.py [--verbose]
"""
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Hosts that bill per call. A published page that can reach one of these can
# spend the owner's money, whoever opens it.
PAID_ENDPOINT = re.compile(
    r"\b(?:api\.openai\.com|api\.anthropic\.com|api\.elevenlabs\.io"
    r"|generativelanguage\.googleapis\.com|speech\.googleapis\.com"
    r"|texttospeech\.googleapis\.com|api\.deepgram\.com|api\.assemblyai\.com"
    r"|api\.cohere\.ai|api\.replicate\.com|api\.together\.xyz|api\.groq\.com"
    r"|api\.mistral\.ai|api\.x\.ai|openrouter\.ai|api\.stripe\.com"
    r"|checkout\.stripe\.com|api\.paypal\.com|[\w.-]+\.cognitiveservices\.azure\.com"
    r"|bedrock[\w.-]*\.amazonaws\.com|[\w.-]+\.openai\.azure\.com)\b", re.I)

# A credential in a shipped file is spendable by anyone who views source.
CREDENTIAL = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{12,}|sk-ant-[A-Za-z0-9_-]{8,}|xai-[A-Za-z0-9]{12,}"
    r"|OPENAI_API_KEY|ANTHROPIC_API_KEY|ELEVENLABS_API_KEY|DEEPGRAM_API_KEY"
    r"|ASSEMBLYAI_API_KEY|STRIPE_SECRET_KEY|AWS_SECRET_ACCESS_KEY"
    r"|GOOGLE_APPLICATION_CREDENTIALS)\b")

# Provider modules the public edition must never carry.
FORBIDDEN_MODULES = ["ai_patient.py", "natural_voice.py", "conversation.py"]

SHIPPED = ["pcmcse", "web", "offline_routes.py", "index.html"]
TEXT_SUFFIXES = {".py", ".js", ".mjs", ".html", ".json", ".css", ".webmanifest"}
SKIP_DIRS = {"node_modules", "__pycache__", ".git", "verification-private", ".backups"}


def _shipped_files():
    for entry in SHIPPED:
        path = ROOT / entry
        if path.is_file():
            yield path
            continue
        stack = [path]
        while stack:
            here = stack.pop()
            if not here.exists():
                continue
            for child in here.iterdir():
                if child.is_dir():
                    if child.name not in SKIP_DIRS:
                        stack.append(child)
                elif child.suffix in TEXT_SUFFIXES:
                    yield child


def _scan(text, where, findings):
    for pattern, kind in ((PAID_ENDPOINT, "paid endpoint"), (CREDENTIAL, "credential")):
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append((where, line, kind, match.group(0)))


def main():
    findings, scanned = [], 0
    for path in _shipped_files():
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        scanned += 1
        _scan(text, str(path.relative_to(ROOT)), findings)

    # The browser downloads engine.zip, so its CONTENTS ship too.
    bundle = ROOT / "web/engine.zip"
    if bundle.exists():
        with zipfile.ZipFile(bundle) as archive:
            for name in archive.namelist():
                if not name.endswith(tuple(TEXT_SUFFIXES)):
                    continue
                scanned += 1
                _scan(archive.read(name).decode("utf-8", "ignore"),
                      "web/engine.zip!" + name, findings)
            for module in FORBIDDEN_MODULES:
                for name in archive.namelist():
                    if name.endswith("/" + module) or name == module:
                        findings.append((bundle.name, 0, "provider module", name))

    for module in FORBIDDEN_MODULES:
        if (ROOT / "pcmcse" / module).exists():
            findings.append(("pcmcse/" + module, 0, "provider module", module))

    if "--verbose" in sys.argv:
        print("scanned %d shipped files" % scanned)
    if findings:
        print("The published edition can reach a paid service or carries a credential:")
        for where, line, kind, text in findings:
            print("  %-52s :%-5s %-16s %s" % (where, line or "-", kind, text))
        print("\n%d finding(s). The public edition must have no way to bill the owner."
              % len(findings))
        return 1
    print("PASS %d shipped files (package, web bundle and engine.zip contents) — "
          "no paid-provider endpoint, no credential, no provider module." % scanned)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
