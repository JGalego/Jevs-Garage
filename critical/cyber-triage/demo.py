"""Triage an endpoint alert without automatically changing the host."""

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
SIGNALS = SignalNames(choice="incident_class", score="severity", noul="active_compromise")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.70 or signals.choice == "unknown":
        return PolicyDecision(
            action="Preserve telemetry and queue the alert for analyst triage.",
            reason="The evidence is not stable enough to recommend containment.",
            confidence=signals.confidence,
            fallback=True,
            owner="SOC analyst",
        )
    if signals.noul >= 0.75 and signals.score >= 3 and signals.choice != "benign_admin":
        return PolicyDecision(
            action="Recommend host isolation and paging the incident commander; await operator approval.",
            reason="Compromise, severity, and incident class cross the containment policy boundary.",
            confidence=signals.confidence,
            fallback=False,
            owner="incident commander",
        )
    if signals.choice == "benign_admin" and signals.score < 1.5 and signals.noul <= 0.20:
        return PolicyDecision(
            action="Send the alert to routine administrative validation.",
            reason="Typed signals consistently support expected administrative activity.",
            confidence=signals.confidence,
            fallback=False,
            owner="SOC queue",
        )
    return PolicyDecision(
        action="Prioritize an investigation without isolating the host.",
        reason="The alert is credible but remains below the containment threshold.",
        confidence=signals.confidence,
        fallback=False,
        owner="tier-two analyst",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="CRITICAL", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
