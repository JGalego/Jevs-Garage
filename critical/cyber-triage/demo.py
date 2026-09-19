"""Triage an endpoint alert without automatically changing the host."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

TITLE = "Cyber triage console"
STATE = {
    "alert_id": "edr-20418",
    "host": "FIN-WS-044",
    "process": "powershell.exe",
    "parent": "winword.exe",
    "observations": [
        "encoded command line",
        "credential store access",
        "outbound connection to a newly registered domain",
    ],
    "user_context": "finance contractor",
    "asset_criticality": "high",
}
QUESTIONS: Questions = {
    "incident_class": Choice(
        instructions="Classify the most plausible explanation for this endpoint alert.",
        criteria={
            "credential_attack": "Activity aimed at stealing or abusing credentials.",
            "malware": "Malicious code execution without clear credential targeting.",
            "benign_admin": "Expected administrative or automation activity.",
            "unknown": "Evidence does not support a stable classification.",
        },
    ),
    "severity": Score(
        instructions="Score the potential operational impact.",
        criteria=["informational", "low", "moderate", "high", "critical"],
    ),
    "active_compromise": Noul(
        instructions="Does the evidence indicate an active compromise rather than an isolated suspicious event?",
        criteria={
            "true": "Multiple observations form a coherent attack chain.",
            "false": "Evidence is benign or isolated.",
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
    incident = response.choices["incident_class"]
    severity = response.scores["severity"]
    compromise = response.nouls["active_compromise"]
    confidence = min(incident.confidence, severity.confidence, abs(compromise.noul - 0.5) * 2)
    if confidence < 0.70 or incident.choice == "unknown":
        return PolicyDecision(
            action="Preserve telemetry and queue the alert for analyst triage.",
            reason="The evidence is not stable enough to recommend containment.",
            confidence=confidence,
            fallback=True,
            owner="SOC analyst",
        )
    if compromise.noul >= 0.75 and severity.score >= 3 and incident.choice != "benign_admin":
        return PolicyDecision(
            action="Recommend host isolation and paging the incident commander; await operator approval.",
            reason="Compromise, severity, and incident class cross the containment policy boundary.",
            confidence=confidence,
            fallback=False,
            owner="incident commander",
        )
    if incident.choice == "benign_admin" and severity.score < 1.5 and compromise.noul <= 0.20:
        return PolicyDecision(
            action="Send the alert to routine administrative validation.",
            reason="Typed signals consistently support expected administrative activity.",
            confidence=confidence,
            fallback=False,
            owner="SOC queue",
        )
    return PolicyDecision(
        action="Prioritize an investigation without isolating the host.",
        reason="The alert is credible but remains below the containment threshold.",
        confidence=confidence,
        fallback=False,
        owner="tier-two analyst",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="CRITICAL", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
