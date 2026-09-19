"""Interpret production telemetry without mutating infrastructure."""

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

TITLE = "Infrastructure monitoring wall"
STATE = {
    "service": "checkout-api",
    "region": "eu-west",
    "window_minutes": 12,
    "metrics": {"error_rate": 0.31, "p99_ms": 4800, "cpu_percent": 44, "db_pool_saturation": 0.98},
    "changes": ["database connection pool reduced from 80 to 30 at 14:02 UTC"],
    "symptoms": ["timeouts", "healthy pods", "database wait queue increasing"],
}
QUESTIONS: Questions = {
    "failure_domain": Choice(
        instructions="Classify the most likely primary failure domain.",
        criteria={
            "database": "Database access, locks, or connection capacity.",
            "network": "Routing, DNS, packet loss, or connectivity.",
            "application": "Application code or runtime behavior.",
            "capacity": "Compute or service capacity exhaustion.",
            "unknown": "Evidence does not support a stable domain.",
        },
    ),
    "customer_impact": Score(
        instructions="Score current customer impact.",
        criteria=["none", "minor", "degraded", "major", "widespread outage"],
    ),
    "active_outage": Noul(
        instructions="Do the metrics indicate an active customer-visible outage?",
        criteria={
            "true": "Customers are currently unable to complete core work.",
            "false": "Service remains functionally available.",
        },
    ),
}
SIGNALS = SignalNames(choice="failure_domain", score="customer_impact", noul="active_outage")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.72 or signals.choice == "unknown":
        return PolicyDecision(
            action="Freeze automated remediation and gather traces for the on-call engineer.",
            reason="The likely failure domain is not stable enough for a runbook recommendation.",
            confidence=signals.confidence,
            fallback=True,
            owner="on-call engineer",
        )
    if signals.noul >= 0.80 and signals.score >= 3:
        return PolicyDecision(
            action="Recommend reverting the pool change and paging the incident lead for approval.",
            reason="Impact and causal-domain signals cross the major-incident threshold.",
            confidence=signals.confidence,
            fallback=False,
            owner="incident lead",
        )
    if signals.score >= 2:
        return PolicyDecision(
            action="Open an incident channel and present the database runbook to the operator.",
            reason="Customer degradation is meaningful but below the rollback threshold.",
            confidence=signals.confidence,
            fallback=False,
            owner="on-call engineer",
        )
    return PolicyDecision(
        action="Continue monitoring and annotate the configuration change.",
        reason="The event remains below customer-impact policy thresholds.",
        confidence=signals.confidence,
        fallback=False,
        owner="observability service",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="CRITICAL", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
