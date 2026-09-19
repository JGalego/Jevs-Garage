"""Assess wildfire escalation without issuing public alerts or orders."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

TITLE = "Wildfire escalation map"
STATE = {
    "incident": "Cedar Ridge 14",
    "observed_acres": 620,
    "growth_last_hour_percent": 38,
    "wind_kph": 46,
    "relative_humidity_percent": 14,
    "observations": ["spot fires 800 m ahead", "crown fire in eastern flank"],
    "nearest_settlement_km": 4.7,
    "evacuation_authority": "county incident commander",
}
QUESTIONS: Questions = {
    "spread_behavior": Choice(
        instructions="Classify the dominant wildfire spread behavior.",
        criteria={
            "contained": "Spread is static or held within control lines.",
            "surface": "Primarily surface spread without major spotting.",
            "crown": "Sustained crown-fire behavior is present.",
            "extreme": "Rapid, erratic spread or long-range spotting is present.",
        },
    ),
    "threat_level": Score(
        instructions="Score near-term threat to people and critical assets.",
        criteria=["minimal", "guarded", "elevated", "severe", "extreme"],
    ),
    "settlement_threat": Noul(
        instructions="Could current spread plausibly threaten the nearby settlement soon?",
        criteria={
            "true": "Observed behavior and conditions support near-term exposure.",
            "false": "The settlement is not plausibly exposed soon.",
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
    spread = response.choices["spread_behavior"]
    threat = response.scores["threat_level"]
    settlement = response.nouls["settlement_threat"]
    confidence = min(spread.confidence, threat.confidence, abs(settlement.noul - 0.5) * 2)
    if confidence < 0.80:
        return PolicyDecision(
            action="Escalate the observations to the incident commander for immediate interpretation.",
            reason="Uncertain fire behavior cannot support a public-action recommendation.",
            confidence=confidence,
            fallback=True,
            owner="incident commander",
        )
    if spread.choice in {"crown", "extreme"} and threat.score >= 3 and settlement.noul >= 0.80:
        return PolicyDecision(
            action="Recommend evacuation-warning review by the authorized incident command.",
            reason="Spread, threat, and exposure all cross the escalation threshold.",
            confidence=confidence,
            fallback=False,
            owner="county incident commander",
        )
    if threat.score >= 2:
        return PolicyDecision(
            action="Recommend increased field observation and resource-readiness review.",
            reason="Conditions are elevated but below the public-warning threshold.",
            confidence=confidence,
            fallback=False,
            owner="operations section chief",
        )
    return PolicyDecision(
        action="Continue routine monitoring under the current incident plan.",
        reason="The typed result remains below escalation thresholds.",
        confidence=confidence,
        fallback=False,
        owner="planning section",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="CRITICAL", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
