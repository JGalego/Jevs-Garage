"""Screen a payment case without releasing, rejecting, or reporting it."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

TITLE = "Compliance screening desk"
STATE = {
    "case_id": "cmp-10972",
    "payment_usd": 9800,
    "beneficiary": "Northstar Trading FZE",
    "beneficiary_country": "AE",
    "screening_hit": {"name_similarity": 0.91, "country_match": True, "date_of_birth_match": False},
    "account_history": "three prior low-value domestic payments",
    "purpose": "consulting retainer",
}
QUESTIONS: Questions = {
    "concern": Choice(
        instructions="Classify the primary compliance concern in this case.",
        criteria={
            "sanctions": "A sanctions-list identity may match the beneficiary.",
            "aml": "Transaction behavior may indicate money laundering.",
            "privacy": "Handling may create a privacy-compliance issue.",
            "none": "No material compliance concern is supported.",
        },
    ),
    "risk": Score(
        instructions="Score the need for compliance review.",
        criteria=["none", "low", "moderate", "high", "critical"],
    ),
    "likely_match": Noul(
        instructions="Is the screening hit likely to identify the same entity?",
        criteria={
            "true": "Available identity attributes materially align.",
            "false": "The hit appears to be a false positive.",
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
    concern = response.choices["concern"]
    risk = response.scores["risk"]
    match = response.nouls["likely_match"]
    confidence = min(concern.confidence, risk.confidence, abs(match.noul - 0.5) * 2)
    if confidence < 0.78:
        return PolicyDecision(
            action="Keep the payment pending and assign enhanced due diligence.",
            reason="Ambiguous identity evidence requires a human compliance decision.",
            confidence=confidence,
            fallback=True,
            owner="compliance analyst",
        )
    if concern.choice in {"sanctions", "aml"} and risk.score >= 3 and match.noul >= 0.75:
        return PolicyDecision(
            action="Recommend a compliance hold pending analyst adjudication.",
            reason="Concern, risk, and match probability cross the review threshold.",
            confidence=confidence,
            fallback=False,
            owner="compliance officer",
        )
    if concern.choice == "none" and risk.score < 1.5 and match.noul <= 0.20:
        return PolicyDecision(
            action="Recommend returning the payment to standard processing.",
            reason="All typed signals support a likely false positive.",
            confidence=confidence,
            fallback=False,
            owner="payment operations",
        )
    return PolicyDecision(
        action="Recommend standard compliance review before payment processing.",
        reason="The case is material but below the enhanced-review boundary.",
        confidence=confidence,
        fallback=False,
        owner="compliance analyst",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="CRITICAL", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
