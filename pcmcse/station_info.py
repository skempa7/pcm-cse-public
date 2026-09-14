"""Student-facing station information; patient demographics stay authored."""


def doorway(case):
    """Withhold age from the posted brief without changing case facts.

    Only the canonical patient-identification line is changed. Symptom
    durations, vital signs, and station timing are not demographic ages.
    Historical snapshots and delivered transcripts remain immutable.
    """
    patient = case["patient"]
    original = "{name}, {age}-year-old {sex}.".format(**patient)
    displayed = "{name}, {sex}.".format(**patient)
    return [displayed if line.strip() == original else line
            for line in case["station"].get("doorway", [])]
