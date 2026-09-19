"""Interpret production telemetry without mutating infrastructure."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

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
FIXTURES = Path(__file__).with_name("fixtures.json")


def evaluate(*, live: bool = False, scenario: str = "confident") -> SystemOneResponse:
    if not live:
        return fixture_response(FIXTURES, scenario)
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(response: SystemOneResponse) -> PolicyDecision:
    domain = response.choices["failure_domain"]
    impact = response.scores["customer_impact"]
    outage = response.nouls["active_outage"]
    confidence = min(domain.confidence, impact.confidence, abs(outage.noul - 0.5) * 2)
    if confidence < 0.72 or domain.choice == "unknown":
        return PolicyDecision(
            action="Freeze automated remediation and gather traces for the on-call engineer.",
            reason="The likely failure domain is not stable enough for a runbook recommendation.",
            confidence=confidence,
            fallback=True,
            owner="on-call engineer",
        )
    if outage.noul >= 0.80 and impact.score >= 3:
        return PolicyDecision(
            action="Recommend reverting the pool change and paging the incident lead for approval.",
            reason="Impact and causal-domain signals cross the major-incident threshold.",
            confidence=confidence,
            fallback=False,
            owner="incident lead",
        )
    if impact.score >= 2:
        return PolicyDecision(
            action="Open an incident channel and present the database runbook to the operator.",
            reason="Customer degradation is meaningful but below the rollback threshold.",
            confidence=confidence,
            fallback=False,
            owner="on-call engineer",
        )
    return PolicyDecision(
        action="Continue monitoring and annotate the configuration change.",
        reason="The event remains below customer-impact policy thresholds.",
        confidence=confidence,
        fallback=False,
        owner="observability service",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="CRITICAL", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
