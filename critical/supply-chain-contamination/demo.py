"""Assess a cold-chain anomaly without acting on physical inventory."""

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
SIGNALS = SignalNames(choice="hazard", score="severity", noul="lot_affected")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.78 or signals.choice == "sensor_fault":
        return PolicyDecision(
            action="Keep the lot segregated and request logger validation plus lab review.",
            reason="Uncertain evidence cannot support release or disposal.",
            confidence=signals.confidence,
            fallback=True,
            owner="quality assurance lead",
        )
    if signals.noul >= 0.80 and signals.score >= 3:
        return PolicyDecision(
            action="Recommend quarantining the lot pending laboratory disposition.",
            reason="Hazard, severity, and lot-impact signals cross the quarantine threshold.",
            confidence=signals.confidence,
            fallback=False,
            owner="quality assurance lead",
        )
    if signals.score >= 2:
        return PolicyDecision(
            action="Recommend representative sampling before any release decision.",
            reason="The excursion is material but below the direct quarantine threshold.",
            confidence=signals.confidence,
            fallback=False,
            owner="quality laboratory",
        )
    return PolicyDecision(
        action="Recommend release through the standard quality sign-off.",
        reason="All typed signals remain within the release policy band.",
        confidence=signals.confidence,
        fallback=False,
        owner="quality assurance lead",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="CRITICAL", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
