"""Interpret pump telemetry without sending control commands."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

TITLE = "Industrial fault panel"
STATE = {
    "asset": "coolant-pump-P204",
    "rpm": 2870,
    "vibration_mm_s": 12.8,
    "bearing_temperature_c": 96.4,
    "discharge_pressure_bar": 2.1,
    "baseline": {"vibration_mm_s": 3.2, "bearing_temperature_c": 64.0, "pressure_bar": 4.8},
    "maintenance": "bearing inspection overdue by 19 days",
}
QUESTIONS: Questions = {
    "fault_class": Choice(
        instructions="Classify the most likely fault pattern in the telemetry.",
        criteria={
            "bearing_failure": "Heat and vibration indicate bearing degradation.",
            "cavitation": "Pressure and vibration indicate vapor bubble collapse.",
            "sensor_fault": "Measurements are inconsistent with a physical fault.",
            "normal_variation": "Telemetry remains within expected operating variation.",
        },
    ),
    "severity": Score(
        instructions="Score risk of equipment damage if operation continues.",
        criteria=["normal", "watch", "degraded", "dangerous", "imminent failure"],
    ),
    "unsafe_operation": Noul(
        instructions="Is continued operation outside the documented safe envelope?",
        criteria={
            "true": "One or more safety limits are materially exceeded.",
            "false": "Operation remains inside documented limits.",
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
    fault = response.choices["fault_class"]
    severity = response.scores["severity"]
    unsafe = response.nouls["unsafe_operation"]
    confidence = min(fault.confidence, severity.confidence, abs(unsafe.noul - 0.5) * 2)
    if confidence < 0.75 or fault.choice == "sensor_fault":
        return PolicyDecision(
            action="Hold the recommendation and request instrument plus operator inspection.",
            reason="Fault identity or operating risk is not sufficiently certain.",
            confidence=confidence,
            fallback=True,
            owner="shift engineer",
        )
    if unsafe.noul >= 0.80 and severity.score >= 3:
        return PolicyDecision(
            action="Recommend a controlled shutdown; require operator confirmation.",
            reason="Independent typed signals exceed the shutdown recommendation threshold.",
            confidence=confidence,
            fallback=False,
            owner="control-room operator",
        )
    if severity.score >= 2:
        return PolicyDecision(
            action="Reduce load within the approved envelope and schedule urgent inspection.",
            reason="The fault appears degraded but remains below the shutdown boundary.",
            confidence=confidence,
            fallback=False,
            owner="shift engineer",
        )
    return PolicyDecision(
        action="Continue monitored operation under the existing procedure.",
        reason="The typed result stays within the monitoring policy band.",
        confidence=confidence,
        fallback=False,
        owner="control-room operator",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="CRITICAL", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
