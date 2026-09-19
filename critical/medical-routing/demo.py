"""Recommend an intake route without diagnosing or contacting services."""

from __future__ import annotations

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import (
    JevSignals,
    PolicyDecision,
    SignalNames,
    render_demo,
    require_live_api_key,
    signals_from_response,
)

TITLE = "Medical routing desk"
STATE = {
    "patient_age": 57,
    "reported_symptoms": ["central chest pressure", "sweating", "pain radiating to left arm"],
    "duration_minutes": 18,
    "known_conditions": ["hypertension"],
    "location": "at home with another adult present",
    "note": "Routing aid only; not a diagnosis.",
}
QUESTIONS: Questions = {
    "route": Choice(
        instructions="Choose the safest care route supported by the reported state.",
        criteria={
            "emergency": "Immediate emergency assessment may be needed.",
            "same_day": "Prompt same-day clinical assessment is appropriate.",
            "routine": "Routine appointment or self-care guidance may be appropriate.",
        },
    ),
    "urgency": Score(
        instructions="Score urgency based only on the reported symptoms.",
        criteria=["routine", "soon", "same day", "urgent", "immediate"],
    ),
    "red_flag": Noul(
        instructions="Are recognized time-sensitive warning features present in this report?",
        criteria={
            "true": "One or more time-sensitive warning features are present.",
            "false": "No clear warning feature is present.",
        },
    ),
}
SIGNALS = SignalNames(choice="route", score="urgency", noul="red_flag")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.80:
        return PolicyDecision(
            action="Connect the case to a licensed clinician for immediate routing review.",
            reason="The signals are too uncertain for automated guidance.",
            confidence=signals.confidence,
            fallback=True,
            owner="licensed triage clinician",
        )
    if signals.choice == "emergency" or signals.score >= 3.5 or signals.noul >= 0.85:
        return PolicyDecision(
            action="Display emergency-services guidance and offer a clinician handoff now.",
            reason="The conservative emergency threshold is crossed by the typed signals.",
            confidence=signals.confidence,
            fallback=False,
            owner="patient or licensed dispatcher",
        )
    if signals.choice == "same_day" or signals.score >= 2:
        return PolicyDecision(
            action="Recommend same-day assessment by a qualified clinician.",
            reason="Urgency is meaningful but does not cross the emergency threshold.",
            confidence=signals.confidence,
            fallback=False,
            owner="clinical scheduling team",
        )
    return PolicyDecision(
        action="Offer routine appointment options and standard safety-net guidance.",
        reason="All signals remain in the routine policy band.",
        confidence=signals.confidence,
        fallback=False,
        owner="clinical scheduling team",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="CRITICAL", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
