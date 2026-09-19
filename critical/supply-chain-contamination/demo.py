"""Assess a cold-chain anomaly without acting on physical inventory."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

TITLE = "Cold-chain inspection bay"
STATE = {
    "lot": "D-2026-09-117",
    "product": "pasteurized soft cheese",
    "target_temperature_c": "2-5",
    "logger": {"peak_temperature_c": 11.8, "hours_above_5c": 7.2, "data_gaps_minutes": 0},
    "inspection": ["one outer seal torn", "no visible leakage", "delivery delayed 9 hours"],
}
QUESTIONS: Questions = {
    "hazard": Choice(
        instructions="Classify the primary quality hazard supported by the shipment data.",
        criteria={
            "microbial": "Conditions may permit unsafe microbial growth.",
            "chemical": "Chemical contamination is the primary concern.",
            "temperature_abuse": "Cold-chain excursion is the primary concern.",
            "sensor_fault": "The evidence is more consistent with logger failure.",
        },
    ),
    "severity": Score(
        instructions="Score potential consumer-safety impact if the lot is released.",
        criteria=["none", "minor", "moderate", "high", "critical"],
    ),
    "lot_affected": Noul(
        instructions="Is there sufficient evidence that the lot may be affected?",
        criteria={
            "true": "The excursion plausibly affects product safety or quality.",
            "false": "The lot remains demonstrably within specification.",
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
    hazard = response.choices["hazard"]
    severity = response.scores["severity"]
    affected = response.nouls["lot_affected"]
    confidence = min(hazard.confidence, severity.confidence, abs(affected.noul - 0.5) * 2)
    if confidence < 0.78 or hazard.choice == "sensor_fault":
        return PolicyDecision(
            action="Keep the lot segregated and request logger validation plus lab review.",
            reason="Uncertain evidence cannot support release or disposal.",
            confidence=confidence,
            fallback=True,
            owner="quality assurance lead",
        )
    if affected.noul >= 0.80 and severity.score >= 3:
        return PolicyDecision(
            action="Recommend quarantining the lot pending laboratory disposition.",
            reason="Hazard, severity, and lot-impact signals cross the quarantine threshold.",
            confidence=confidence,
            fallback=False,
            owner="quality assurance lead",
        )
    if severity.score >= 2:
        return PolicyDecision(
            action="Recommend representative sampling before any release decision.",
            reason="The excursion is material but below the direct quarantine threshold.",
            confidence=confidence,
            fallback=False,
            owner="quality laboratory",
        )
    return PolicyDecision(
        action="Recommend release through the standard quality sign-off.",
        reason="All typed signals remain within the release policy band.",
        confidence=confidence,
        fallback=False,
        owner="quality assurance lead",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="CRITICAL", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
