"""Recommend a vehicle maneuver without controlling an autonomous system."""

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

TITLE = "Autonomy safety rig"
STATE = {
    "vehicle": "sidewalk-delivery-17",
    "speed_kph": 11.2,
    "path": "shared pedestrian crossing",
    "perception": ["child entering path at 9 m", "parked van limits lateral visibility"],
    "lidar_confidence": 0.94,
    "camera_confidence": 0.88,
    "braking_distance_m": 4.1,
}
QUESTIONS: Questions = {
    "maneuver": Choice(
        instructions="Choose the safest candidate maneuver from the observed state.",
        criteria={
            "continue": "Continue on the current trajectory.",
            "slow": "Reduce speed while maintaining the path.",
            "stop": "Enter a controlled minimal-risk stop.",
            "handoff": "Request human supervisory control.",
        },
    ),
    "collision_risk": Score(
        instructions="Score near-term collision risk if the current trajectory continues.",
        criteria=["negligible", "low", "meaningful", "high", "imminent"],
    ),
    "sensor_agreement": Noul(
        instructions="Do independent sensors agree on the obstacle and its location?",
        criteria={
            "true": "Independent sensors are materially consistent.",
            "false": "Sensor observations conflict or are incomplete.",
        },
    ),
}
SIGNALS = SignalNames(choice="maneuver", score="collision_risk", noul="sensor_agreement")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.85 or signals.noul < 0.70:
        return PolicyDecision(
            action="Recommend a minimal-risk stop and request human takeover.",
            reason="Uncertain perception cannot authorize continued autonomous motion.",
            confidence=signals.confidence,
            fallback=True,
            owner="remote safety supervisor",
        )
    if signals.choice in {"stop", "handoff"} or signals.score >= 3:
        return PolicyDecision(
            action="Recommend a controlled stop within the certified motion envelope.",
            reason="The high-confidence risk assessment crosses the stop threshold.",
            confidence=signals.confidence,
            fallback=False,
            owner="certified motion controller",
        )
    if signals.choice == "slow" or signals.score >= 1.5:
        return PolicyDecision(
            action="Recommend reduced speed and repeat perception before proceeding.",
            reason="Risk is elevated but remains below the mandatory stop boundary.",
            confidence=signals.confidence,
            fallback=False,
            owner="certified motion controller",
        )
    return PolicyDecision(
        action="Recommend continuing inside the certified operating envelope.",
        reason="All typed signals remain in the low-risk policy band.",
        confidence=signals.confidence,
        fallback=False,
        owner="certified motion controller",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="CRITICAL", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
