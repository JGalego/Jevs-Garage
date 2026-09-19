"""Prioritize an emergency call without dispatching any resources."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

TITLE = "Emergency dispatch board"
STATE = {
    "call_id": "CAD-88421",
    "transcript": "Smoke is filling the second-floor hallway. Two residents may still be upstairs.",
    "location": "four-unit apartment building, 18 Harbor Lane",
    "caller_status": "outside, coughing, able to speak",
    "known_hazards": ["residents unaccounted for", "dense indoor smoke"],
}
QUESTIONS: Questions = {
    "incident_type": Choice(
        instructions="Classify the primary incident described by the caller.",
        criteria={
            "structure_fire": "Fire or smoke inside an occupied structure.",
            "medical": "Primarily a medical emergency.",
            "hazardous_material": "A hazardous substance is the primary threat.",
            "unknown": "The incident cannot yet be classified reliably.",
        },
    ),
    "response_priority": Score(
        instructions="Score urgency for dispatcher review.",
        criteria=["routine", "prompt", "urgent", "emergency", "immediate life threat"],
    ),
    "immediate_threat": Noul(
        instructions="Does the call describe an immediate threat to human life?",
        criteria={
            "true": "A person may be exposed to imminent serious harm.",
            "false": "No immediate life threat is described.",
        },
    ),
}
FIXTURES = Path(__file__).with_name("fixtures.json")


def evaluate(*, live: bool = False, scenario: str = "confident") -> SystemOneResponse:
    if not live:
        return fixture_response(FIXTURES, scenario)
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(response: SystemOneResponse) -> PolicyDecision:
    incident = response.choices["incident_type"]
    priority = response.scores["response_priority"]
    threat = response.nouls["immediate_threat"]
    confidence = min(incident.confidence, priority.confidence, abs(threat.noul - 0.5) * 2)
    if confidence < 0.82 or incident.choice == "unknown":
        return PolicyDecision(
            action="Keep the caller connected and transfer classification to a certified dispatcher.",
            reason="Uncertain incident data cannot drive a resource recommendation.",
            confidence=confidence,
            fallback=True,
            owner="certified dispatcher",
        )
    if threat.noul >= 0.85 and priority.score >= 3:
        return PolicyDecision(
            action="Present a Priority 1 response recommendation to the dispatcher; do not auto-dispatch.",
            reason="Incident, priority, and immediate-threat signals agree at high confidence.",
            confidence=confidence,
            fallback=False,
            owner="certified dispatcher",
        )
    if priority.score >= 2:
        return PolicyDecision(
            action="Present an urgent response recommendation for dispatcher confirmation.",
            reason="The report crosses the urgent review threshold but not Priority 1.",
            confidence=confidence,
            fallback=False,
            owner="certified dispatcher",
        )
    return PolicyDecision(
        action="Place the call in the standard dispatch review queue.",
        reason="The typed signals remain below urgent policy thresholds.",
        confidence=confidence,
        fallback=False,
        owner="dispatch queue",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="CRITICAL", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
