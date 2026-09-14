"""Public visual characterization, never a source of clinical evidence.

Only authored demographics, the doorway, and words already delivered to the
learner enter this adapter. Hidden findings, diagnoses, persona notes, and
planned/undelivered AI responses are deliberately not read. The animation is
an illustrative performance of the conversation, not a verified examination.
"""

from __future__ import annotations

import hashlib
import re

from . import evidence


def appearance(case):
    """Choose an explicitly authored adult presentation; never guess from names.

    Skin/hair palettes are arbitrary, stable art direction, not an inference
    about ethnicity. Future explicit appearance authoring can override them.
    """
    person = case.get("patient", {})
    authored = person.get("appearance", {})
    gender = str(authored.get("presentation") or person.get("gender") or
                 person.get("sex") or "").strip().lower()
    style = {"female": "female", "woman": "female", "male": "male",
             "man": "male"}.get(gender, "neutral")
    raw_age = person.get("age")
    age = raw_age if isinstance(raw_age, (int, float)) and not isinstance(raw_age, bool) else None
    if age is not None and not 0 <= age <= 120:
        age = None
    # A hash is cosmetic randomization only. It has no language/name semantics
    # and excludes case identifiers, chief complaints, diagnoses and findings.
    seed = hashlib.sha256(str(person.get("name", "patient")).encode("utf-8")).digest()
    def palette(key, count, fallback):
        value = authored.get(key)
        return value if type(value) is int and 0 <= value < count else fallback
    profile = {"presentation": style, "age": age,
            "skinTone": palette("skinTone", 5, seed[0] % 5),
            "hairTone": palette("hairTone", 4, seed[1] % 4)}
    # 2026-09-14: select the model explicitly authored for an adult, including
    # cases outside the original 18–30 cohort. Cohort is a legacy asset marker,
    # not a clinical age limit. Preserve the saved person's age and other facts;
    # never infer a model from a name or substitute an adult model for a child.
    authored_model = authored.get('model') == 'mpfb-public-patient'
    legacy_cohort = person.get('cohort') == 'public-adults-v1'
    if (authored_model or legacy_cohort) and style in ('female','male') and age is not None and 18 <= age <= 120:
        profile.update(model='mpfb-public-patient', cohort='public-adults-v1',
            skinTone=palette('skinTone',3,0), hairColor=authored.get('hairColor','brunette'),
            eyeColor='green' if authored.get('eyeColor')=='green' else 'blue',
            hairStyle='bald' if style=='male' else 'long-layered',
            outfit='fitted-casual' if style=='male' else 'fitted-casual',
            bodyBuild='standard' if style=='male' else authored.get('bodyBuild','standard'))
    return profile


def _normalize(text):
    return str(text or "").lower().replace("’", "'")


def _pain_region(text):
    """A broad, non-lateral gesture only for the spoken main complaint."""
    if re.search(r"\b(?:headache|head (?:hurts|pain))\b", text):
        return "head"
    if not re.search(r"\b(?:pain|hurts?|hurting|ache|aching|pressure)\b", text):
        return "none"
    if re.search(r"\b(?:stomach|abdomen|abdominal|belly|ribs)\b", text):
        return "abdomen"
    if re.search(r"\b(?:back|flank|side)\b", text):
        return "back"
    if re.search(r"\bchest\b", text):
        return "chest"
    return "none"


def _no_current_pain(text):
    return bool(re.search(
        r"\b(?:no (?:pain|pressure)(?: at all)? (?:right now|now|at the moment)|"
        r"(?:pain|pressure)(?: is|'s)? (?:gone|not there)|nothing hurts|"
        r"(?:don't|do not) have (?:any )?(?:chest |back |abdominal |head )?(?:pain|pressure) (?:right now|now)|"
        r"(?:not|isn't|is not) (?:hurting|painful)|pain[- ]free|"
        r"(?:feel|feeling) (?:well|fine|okay|ok) (?:right now|between))\b", text))


def affect(case, ledger):
    """Render a restrained cue from public complaints, not hidden severity.

    This is deliberately less detailed than the case. No neurologic deficits,
    abnormal respiratory rate, tenderness, laterality, photophobia or visible
    exam finding is synthesized. Numeric discomfort is animation strength,
    never a clinical pain score. Neutral remains neutral when current status
    is unknown, episodic, or explicitly resolved.
    """
    doorway = case.get("station", {}).get("doorway", [])
    main = " ".join(str(line) for line in doorway)
    delivered = [event for event in ledger.events
                 if event.get("kind") == evidence.PATIENT and
                 not event.get("meta", {}).get("no_information") and
                 not event.get("meta", {}).get("uncertain")]
    # Opening text is used only after its actual delivery. Do not consult the
    # patient's authored opening, which may still be hidden behind the door.
    openings = [event for event in delivered
                if event.get("meta", {}).get("kind") == "opening" or
                any(str(fid).startswith("opening_") for fid in
                    event.get("meta", {}).get("facts_released", []))]
    if openings:
        main += " " + openings[-1].get("text", "")
    main = _normalize(main)
    region = _pain_region(main)
    discomfort = 0.28 if region != "none" else 0.0
    # Exertional/intermittent history does not establish pain while seated.
    episodic = re.search(r"\b(?:when i push|when i exert|when i walk|when i climb|"
                         r"goes away when i stop|between spells|at night|when i roll)\b", main)
    if episodic or _no_current_pain(main) or region == "chest":
        discomfort = 0.0
    if discomfort and re.search(r"\b(?:awful|terrible|cannot get comfortable|has not gone away)\b", main):
        discomfort = 0.42
    concern = 0.0
    energy = "usual"
    # Later delivered statements can express concern, fatigue, or explicitly
    # update present pain. Historical severity alone cannot escalate a grimace.
    for event in delivered:
        text = _normalize(event.get("text", ""))
        if re.search(r"\b(?:i'm|i am|i've been|i have been) (?:really |a little |kind of )?"
                     r"(?:scared|afraid|worried|frightened)|\bit's frightening\b", text):
            concern = 0.3
        if re.search(r"\b(?:i feel|i'm feeling|i am feeling|i am|i'm) (?:really |very )?"
                     r"(?:tired|exhausted|worn out)\b", text):
            energy = "low"
        if _no_current_pain(text):
            described_region = _pain_region(text)
            if described_region in ("none", region):
                discomfort = 0.0
        elif re.search(r"\b(?:pain|pressure|ache)\b", text) and re.search(
                r"\b(?:right now|at the moment|still hurts|hurts now)\b", text):
            # Unknown answers such as 'I cannot say if it hurts right now'
            # must not become animation assertions.
            if not re.search(r"\b(?:don't know|do not know|cannot say|can't say|not sure|uncertain)\b", text):
                discomfort = 0.36
                region = _pain_region(text) if _pain_region(text) != "none" else region
    return {"discomfort": discomfort,
            "guardRegion": region if discomfort else "none",
            "energy": energy, "concern": concern}


# These are acting directions, not symptoms, mental-status findings or scoring.
# A profile is authored once in the case snapshot; no per-turn randomness.
_DEMEANOR = {
    "calm": {"tension": .12, "engagement": .65, "pace": "measured", "gaze": "attentive", "gesture": "small"},
    "friendly": {"tension": .10, "engagement": .82, "pace": "conversational", "gaze": "welcoming", "gesture": "open"},
    "anxious": {"tension": .44, "engagement": .62, "pace": "slightly_hesitant", "gaze": "checking_in", "gesture": "small"},
    "frustrated": {"tension": .38, "engagement": .57, "pace": "direct", "gaze": "direct", "gesture": "restrained"},
    "tired": {"tension": .16, "engagement": .58, "pace": "unhurried", "gaze": "attentive", "gesture": "minimal"},
    "guarded": {"tension": .28, "engagement": .48, "pace": "deliberate", "gaze": "intermittent", "gesture": "restrained"},
}
_SOCIAL = {
    "calm": {"thanks": ["Thank you for listening.", "I appreciate that."], "transition": ["Okay, go ahead.", "All right."], "plan": ["Thank you for explaining the next steps."], "clarify": ["Could you ask that another way?"]},
    "friendly": {"thanks": ["Thanks, I appreciate you listening.", "Thank you. I appreciate that."], "transition": ["Sure, go ahead.", "Of course."], "plan": ["Thanks for walking me through the next steps."], "clarify": ["Could you put that another way for me?"]},
    "anxious": {"thanks": ["Thank you for taking the time to listen.", "I appreciate you hearing me out."], "transition": ["Okay. Go ahead.", "All right, I'm listening."], "plan": ["Thank you for explaining what happens next."], "clarify": ["Could you explain what you mean by that question?"]},
    "frustrated": {"thanks": ["Thank you for hearing me out.", "I appreciate being listened to."], "transition": ["All right. Go ahead.", "Okay, I'm listening."], "plan": ["Thanks for being clear about the next steps."], "clarify": ["What exactly are you asking me?"]},
    "tired": {"thanks": ["Thank you. I appreciate you listening.", "Thanks for taking the time."], "transition": ["Okay.", "Yes, go ahead."], "plan": ["Thank you for going through the next steps."], "clarify": ["Could you say the question another way?"]},
    "guarded": {"thanks": ["I appreciate you listening.", "Thank you for hearing me out."], "transition": ["Go ahead.", "All right."], "plan": ["Thank you for explaining the plan."], "clarify": ["Could you be more specific about what you're asking?"]},
}


_COMMUNICATION_STYLES = {"warm": "friendly", "cooperative": "calm", "direct": "frustrated",
                         "reserved": "guarded", "measured": "tired"}
_EMOTIONAL_STATES = {"calm": .12, "worried": .44, "frustrated": .38, "cautious": .28}
_LEGACY_AXES = {"calm": ("cooperative", "calm"), "friendly": ("warm", "calm"),
                "anxious": ("cooperative", "worried"), "frustrated": ("direct", "frustrated"),
                "tired": ("measured", "calm"), "guarded": ("reserved", "cautious")}


def demeanor_profile(case):
    """Public whitelist; never send free-text persona or hidden concerns."""
    authored = case.get("patient", {}).get("demeanor", {})
    if not isinstance(authored, dict) or authored.get("version") != "demeanor-v1":
        authored = {}
    style = authored.get("style")
    if not isinstance(style, str) or style not in _DEMEANOR:
        style = "calm"
    default_communication, default_emotion = _LEGACY_AXES[style]
    communication = authored.get("communication_style", default_communication)
    emotion = authored.get("emotional_state", default_emotion)
    if not isinstance(communication, str) or communication not in _COMMUNICATION_STYLES:
        communication = default_communication
    if not isinstance(emotion, str) or emotion not in _EMOTIONAL_STATES:
        emotion = default_emotion
    return {"version": "demeanor-v1", "axes_version": "demeanor-axes-v1", "style": style,
            "communication_style": communication, "emotional_state": emotion,
            "baseline_emotional_state": emotion,
            "baseline_state": style, "pace": _DEMEANOR[style]["pace"],
            "authored": bool(authored), "clinical_evidence": False,
            "illustrative": True}


def social_reply(case, kind, index=0):
    """Safe social wording only; no symptoms, agreement or new disclosures."""
    profile = demeanor_profile(case)
    lines = _SOCIAL[_COMMUNICATION_STYLES[profile["communication_style"]]].get(kind, [])
    return lines[max(0, int(index)) % len(lines)] if lines else ""


def social_lines(case, kind=None):
    profile = demeanor_profile(case)
    groups = _SOCIAL[_COMMUNICATION_STYLES[profile["communication_style"]]]
    return set(groups.get(kind, [])) if kind else {line for lines in groups.values() for line in lines}


def demeanor(case, ledger):
    """Stable characterization plus small, evidence-triggered rapport changes.

    Deliberate speech interruptions require an explicit user marker. An exam
    interruption, timeout, reload or stopped audio alone is not interpersonal
    behavior. Reassurance changes social ease only, never symptom severity.
    """
    profile = demeanor_profile(case)
    baseline = _DEMEANOR[profile["style"]]
    rapport = 0
    acknowledgments = interruptions = 0
    seen = set()
    for ev in ledger.events:
        meta = ev.get("meta", {})
        identity = (meta.get("delivery_id"), meta.get("segment_index"))
        if identity[0]:
            # Interruption receipts have their own identity, distinct from speech.
            identity += (meta.get("event"),)
            if identity in seen:
                continue
            seen.add(identity)
        if ev.get("kind") == evidence.PATIENT and not meta.get("no_information") and not meta.get("uncertain"):
            social_ack = (not meta.get("facts_released") and ev.get("text") in social_lines(case, "thanks"))
            allowed_ack = social_lines(case, "thanks") | {"Thank you."}
            allowed_ack.update(case.get("patient", {}).get("empathy_replies", []))
            delivered_ack = any(ev.get("text", "").startswith(line) for line in allowed_ack if line)
            if (meta.get("ips_signal") == "empathy_received" and delivered_ack) or social_ack:
                acknowledgments += 1
                rapport = min(3, rapport + 1)
        elif (ev.get("kind") == evidence.SYSTEM and meta.get("event") == "speech_interrupted"
              and (meta.get("user_initiated") is True or meta.get("reason") == "user_interrupt")):
            interruptions += 1
            rapport = max(-3, rapport - 1)
    tension = round(max(.04, min(.65, _EMOTIONAL_STATES[profile["emotional_state"]] - .04 * rapport)), 2)
    communication = _DEMEANOR[_COMMUNICATION_STYLES[profile["communication_style"]]]
    engagement = round(max(.35, min(.90, communication["engagement"] + .03 * rapport)), 2)
    return dict(profile, current_state=("more_at_ease" if rapport >= 2 else "more_reserved" if rapport <= -2 else profile["baseline_state"]),
                rapport_level=rapport, tension=tension, engagement=engagement,
                behavior_intent={"gaze": communication["gaze"], "posture": "socially_relaxed" if rapport >= 2 else "neutral",
                                 "gesture": baseline["gesture"], "pace": baseline["pace"]},
                interaction_evidence={"acknowledgments": acknowledgments, "explicit_user_interruptions": interruptions},
                disclosure="Illustrative communication style; not a clinical finding or a measure of symptom change.")


def gesture(case, ledger):
    """Illustrate a disclosed complaint, never reveal an undisclosed finding.

    Region comes from the doorway/opening or an actually delivered affirmative
    patient statement. A location indication does not assert ongoing pain.
    """
    lines=case.get("station", {}).get("doorway", [])
    if isinstance(lines, str): lines=[lines]
    opening=" ".join(str(x) for x in lines)
    def region_of(text):
        text=_normalize(text)
        if re.search(r"\b(?:no|denies|without)\b", text): return "none"
        if re.search(r"\b(?:headache|migraine|head hurts)\b", text): return "head"
        if not re.search(r"\b(?:pain|hurts?|aching|ache|pressure|burning|sore)\b", text): return "none"
        for region, pattern in [("flank",r"flank|side"),("abdomen",r"abdom|stomach|belly"),("chest",r"chest"),("back",r"back"),("shoulder",r"shoulder"),("knee",r"knee")]:
            if re.search(pattern,text): return region
        return "none"
    region=region_of(opening);source_seq=None;side="unspecified";text=opening
    for ev in ledger.events:
        if ev.get("kind")!=evidence.PATIENT or ev.get("meta",{}).get("no_information") or ev.get("meta",{}).get("uncertain"): continue
        candidate=ev.get("text","");r=region_of(candidate)
        # Only personal affirmative symptom statements; not generic discussion.
        if r!="none" and re.search(r"\b(?:i|my|it|the pain|this pain)\b",_normalize(candidate)):
            region=r;text=candidate;source_seq=ev.get("seq")
    normalized=_normalize(text)
    if re.search(r"\bleft(?:[- ]sided)?\b",normalized):side="left"
    elif re.search(r"\bright(?:[- ]sided)? (?:side|flank|shoulder|knee|abdomen|chest|back)\b",normalized):side="right"
    return {"version":"disclosed-gesture-v1","region":region,"side":side,
            "disclosed":region!="none","source_seq":source_seq,"clinical_evidence":False,
            "meaning":"Illustrates the reported location; does not establish tenderness or a new finding."}
