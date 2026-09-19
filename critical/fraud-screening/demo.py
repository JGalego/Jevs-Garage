"""Screen one card transaction while keeping the final action deterministic."""

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

TITLE = "Fraud screening bay"
STATE = {
    "transaction_id": "txn_7K2M9",
    "amount_usd": 1840.00,
    "merchant": "Northline Camera Exchange",
    "card_country": "PT",
    "merchant_country": "US",
    "minutes_since_last_purchase": 3,
    "device": {"trusted": False, "account_age_days": 812},
    "signals": ["new device", "cross-border", "unusually high amount"],
}
QUESTIONS: Questions = {
    "risk_band": Choice(
        instructions="Classify the transaction's fraud risk.",
        criteria={
            "low": "Routine behavior with no meaningful anomaly.",
            "medium": "Some suspicious evidence, but legitimate use remains plausible.",
            "high": "Multiple coherent indicators of account misuse or fraud.",
        },
    ),
    "fraud_likelihood": Score(
        instructions="Score how strongly the evidence supports fraud.",
        criteria=["very unlikely", "unlikely", "unclear", "likely", "very likely"],
    ),
    "identity_anomaly": Noul(
        instructions="Does the behavior materially differ from the account holder's established pattern?",
        criteria={
            "true": "The transaction has multiple meaningful identity or behavior anomalies.",
            "false": "The transaction is consistent with established behavior.",
        },
    ),
}
SIGNALS = SignalNames(choice="risk_band", score="fraud_likelihood", noul="identity_anomaly")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.72 or 0.35 <= signals.noul <= 0.65:
        return PolicyDecision(
            action="Queue enhanced review; keep the transaction pending.",
            reason="At least one model signal is too uncertain for automatic routing.",
            confidence=signals.confidence,
            fallback=True,
            owner="fraud analyst",
        )
    if signals.choice == "high" and signals.score >= 3 and signals.noul >= 0.70:
        return PolicyDecision(
            action="Place a reversible authorization hold and request analyst review.",
            reason="All three typed signals cross the high-risk policy thresholds.",
            confidence=signals.confidence,
            fallback=False,
            owner="fraud operations",
        )
    if signals.choice == "low" and signals.score < 1.5 and signals.noul <= 0.25:
        return PolicyDecision(
            action="Continue through the standard authorization path.",
            reason="Risk, score, and identity signals all remain below policy limits.",
            confidence=signals.confidence,
            fallback=False,
            owner="payment authorization service",
        )
    return PolicyDecision(
        action="Request step-up verification before authorization.",
        reason="The evidence is credible but does not meet either automatic boundary.",
        confidence=signals.confidence,
        fallback=False,
        owner="cardholder verification flow",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="CRITICAL", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
