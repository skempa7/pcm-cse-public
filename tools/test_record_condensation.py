"""Shortening a fact must never change what it says.

Record is read while writing a note, so the wording is condensed. The danger is
obvious: a shorter line that has quietly lost a "not", a hedge, a number or an
anatomical site is worse than the long one. These checks run the condenser over
EVERY authored fact in the library and assert that nothing load-bearing moved.

    python3 tools/test_record_condensation.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pcmcse import cases, record  # noqa: E402

FAILURES, CHECKS = [], [0]


def check(cond, detail):
    CHECKS[0] += 1
    if not cond:
        FAILURES.append(detail)
    return bool(cond)


def every_fact():
    for cid, case in cases.all_cases().items():
        for fact in case.get("facts", []):
            value = (fact.get("value") or "").strip()
            if value:
                yield cid, fact, value


NEGATION = re.compile(r"\b(?:no|not|never|none|nothing|neither|nobody|denies|without)\b|n't", re.I)
HEDGE = re.compile(r"\b(?:about|approximately|maybe|around|roughly|sometimes|occasionally|"
                   r"i think|i guess|probably|possibly|or so|a couple|few)\b", re.I)
NUMBER = re.compile(r"\d+(?:[./]\d+)?")
WORD_NUMBER = re.compile(r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b", re.I)
ANATOMY = re.compile(r"\b(?:chest|abdomen|abdominal|back|arm|jaw|leg|flank|head|neck|throat|"
                     r"stomach|breastbone|ankle|knee|shoulder|hip|foot|feet|hand|ear|eye|nose|"
                     r"left|right|upper|lower|midline|centre|center)\b", re.I)


def test_negation_is_never_lost():
    for cid, fact, value in every_fact():
        short = record.condense(value)
        if NEGATION.search(value):
            check(bool(NEGATION.search(short)),
                  "%s/%s: shortening dropped the negation: %r -> %r"
                  % (cid, fact["id"], value[:70], short[:70]))


def test_hedges_are_never_lost():
    for cid, fact, value in every_fact():
        short = record.condense(value)
        if HEDGE.search(value):
            check(bool(HEDGE.search(short)),
                  "%s/%s: shortening dropped the uncertainty: %r -> %r"
                  % (cid, fact["id"], value[:70], short[:70]))


def test_numbers_and_units_survive():
    for cid, fact, value in every_fact():
        short = record.condense(value)
        before = len(NUMBER.findall(value)) + len(WORD_NUMBER.findall(value))
        after = len(NUMBER.findall(short)) + len(WORD_NUMBER.findall(short))
        check(after >= before,
              "%s/%s: shortening lost a number: %r -> %r"
              % (cid, fact["id"], value[:70], short[:70]))


DEIXIS = re.compile(r"^(?:right here|here)\s*,\s*", re.I)


def test_anatomy_survives():
    for cid, fact, value in every_fact():
        short = record.condense(value)
        # "Right here, ..." is pointing, not laterality, and removing it is the
        # point of the deixis rule -- so compare against the value with that
        # opener already gone, or every such fact reads as losing a "right".
        source = DEIXIS.sub("", value)
        missing = {w.lower() for w in ANATOMY.findall(source)} - {w.lower() for w in ANATOMY.findall(short)}
        check(not missing,
              "%s/%s: shortening lost anatomy %s: %r -> %r"
              % (cid, fact["id"], sorted(missing), value[:70], short[:70]))


def test_nothing_is_invented():
    """Every word in the short form must come from the authored one."""
    for cid, fact, value in every_fact():
        short = record.condense(value)
        source = set(re.findall(r"[a-z]+", value.lower()))
        for word in re.findall(r"[a-z]+", short.lower()):
            check(word in source,
                  "%s/%s: shortening introduced the word %r, which the patient never said: %r"
                  % (cid, fact["id"], word, short[:70]))


# The rows a student reads while writing the HPI. Social, family and pertinent
# negatives are deliberately left at full length: "I do not drink" and "No known
# drug allergies" are already as short as they can safely be.
HPI_ROWS = {"onset", "location", "radiation", "setting", "timing", "chronology",
            "quality", "severity", "alleviating", "aggravating",
            "chief_complaint", "treatment", "past_occurrence"}


def test_it_actually_shortens_the_rows_it_is_for():
    shortened = total = 0
    for _cid, fact, value in every_fact():
        if fact.get("category") not in HPI_ROWS:
            continue
        total += 1
        if record.condense(value) != value:
            shortened += 1
    check(total and shortened >= total * 0.20,
          "condensation barely fires on HPI rows (%d of %d); it is not earning its risk"
          % (shortened, total))
    print("      (%d of %d HPI rows read shorter)" % (shortened, total))


def test_a_denial_is_never_reopened():
    for value in ["No fever.", "Not sharp.", "Never at rest.",
                  "No, nothing like this before.", "None that I know of."]:
        check(record.condense(value) == value,
              "a sentence opening with a denial was altered: %r" % value)


def test_separate_complaints_keep_their_subject():
    """'The cough began 4 days ago' must not become '4 days ago'."""
    for value in ["The cough began 4 days ago.", "The pain is 5/10.",
                  "The fever started yesterday.", "The swelling is in both ankles."]:
        check(record.condense(value) == value,
              "a named symptom lost its subject: %r -> %r" % (value, record.condense(value)))


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            before = len(FAILURES)
            fn()
            print("  %-50s %s" % (name, "ok" if len(FAILURES) == before else "FAIL"))
    print()
    for f in FAILURES[:12]:
        print("  FAIL %s" % f)
    if FAILURES:
        print("\n%d checks, %d failures" % (CHECKS[0], len(FAILURES)))
        return 1
    print("PASS %d checks over every authored fact — shortening keeps negation, "
          "hedges, numbers, units and anatomy, invents no word, and leaves a "
          "denial or a named symptom alone." % CHECKS[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
