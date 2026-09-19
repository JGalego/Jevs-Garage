"""Stage and challenge a global payment-incident recommendation without executing it."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from typesafe_sdk import Choice, Noul, Questions, Score, TypeSafeClient

from jevs_garage.operations import AuditEvent, OperationRun, OperationStage, render_operation, state_fingerprint
from jevs_garage.runtime import JevSignals, PolicyDecision, SignalNames, require_live_api_key, signals_from_response

TITLE = "Global payment incident command"
POLICY_VERSION = "payments-incident/v3.2"
STATE = {
    "incident_id": "PAY-2026-0919-047",
    "state_version": 17,
    "observed_at": "2026-09-19T02:14:00Z",
    "idempotency_key": "PAY-2026-0919-047:17",
    "services": ["payment-intent", "authorization-router", "ledger-writer"],
    "regions": {
        "eu-west": {"error_rate": 0.287, "p99_ms": 6200, "traffic_share": 0.42},
        "us-east": {"error_rate": 0.091, "p99_ms": 2800, "traffic_share": 0.38},
        "ap-south": {"error_rate": 0.034, "p99_ms": 1100, "traffic_share": 0.20},
    },
    "business": {
        "authorization_decline_delta": 0.19,
        "estimated_revenue_at_risk_usd_per_minute": 184000,
        "duplicate_capture_reports": 0,
    },
    "changes": [
        {"id": "rel-8421", "service": "authorization-router", "percent": 35, "started_at": "02:02Z"},
        {"id": "cfg-211", "component": "provider-timeout", "from_ms": 3500, "to_ms": 1800, "at": "01:58Z"},
    ],
    "dependencies": {
        "provider_alpha": {"timeouts": 0.41, "status_page": "degraded"},
        "provider_beta": {"timeouts": 0.03, "capacity_headroom": 0.22},
        "ledger": {"lag_seconds": 2, "write_errors": 0.001},
    },
    "safety": {
        "automated_mutations_enabled": False,
        "required_approvals": ["incident_commander", "payments_sre"],
        "rollback_runbook": "RB-PAY-17",
    },
}
SITUATION_QUESTIONS: Questions = {
    "failure_domain": Choice(
        instructions="Identify the dominant failure domain supported by the complete incident snapshot.",
        criteria={
            "application_release": "The active application release is the primary causal factor.",
            "payment_provider": "An external payment provider is the primary causal factor.",
            "routing_configuration": "Routing or timeout configuration is the primary causal factor.",
            "capacity": "Internal capacity exhaustion is the primary causal factor.",
            "multi_factor": "Several coupled causes prevent a single dominant attribution.",
            "unknown": "Evidence is insufficient for stable attribution.",
        },
    ),
    "customer_impact": Score(
        instructions="Score current customer and financial impact.",
        criteria=["contained", "minor", "material", "major", "systemic"],
    ),
    "systemic_outage": Noul(
        instructions="Is this a multi-region, customer-visible payment outage requiring incident command?",
        criteria={
            "true": "Core payment completion is materially impaired across more than one region or segment.",
            "false": "Impact is local, transient, or not customer-visible.",
        },
    ),
}
SITUATION_SIGNALS = SignalNames(choice="failure_domain", score="customer_impact", noul="systemic_outage")
INTERVENTIONS = {
    "rollback_release": "Recommend rolling back rel-8421 under the approved runbook.",
    "restore_timeout": "Recommend restoring the prior provider timeout configuration.",
    "shift_provider": "Recommend a bounded traffic shift to provider beta.",
    "shed_noncritical": "Recommend shedding noncritical payment features.",
    "freeze_and_observe": "Make no mutation; preserve evidence and continue incident review.",
}
INTERVENTION_QUESTIONS: Questions = {
    "intervention": Choice(
        instructions="Choose the lowest-risk reversible intervention consistent with the evidence and controls.",
        criteria=INTERVENTIONS,
    ),
    "change_risk": Score(
        instructions="Score the blast radius and reversibility risk of the selected intervention.",
        criteria=["minimal", "low", "moderate", "high", "unacceptable"],
    ),
    "evidence_sufficient": Noul(
        instructions="Is the evidence sufficient for operators to consider the selected intervention now?",
        criteria={
            "true": "Telemetry, timing, and dependencies coherently support the intervention.",
            "false": "Important evidence is missing, contradictory, or stale.",
        },
    ),
}
INTERVENTION_SIGNALS = SignalNames(choice="intervention", score="change_risk", noul="evidence_sufficient")
QUESTION_SETS = {"situation": SITUATION_QUESTIONS, "intervention": INTERVENTION_QUESTIONS}


@dataclass(frozen=True, slots=True)
class PaymentAssessment:
    situation: JevSignals
    intervention: JevSignals


def decide(assessment: PaymentAssessment) -> PolicyDecision:
    situation = assessment.situation
    intervention = assessment.intervention
    confidence = min(situation.confidence, intervention.confidence)

    if confidence < 0.78 or intervention.noul < 0.78 or situation.choice in {"multi_factor", "unknown"}:
        return PolicyDecision(
            action="Freeze mutating automation, preserve evidence, and convene the incident command channel.",
            reason="Attribution or intervention evidence is not strong enough for an operational recommendation.",
            confidence=confidence,
            fallback=True,
            owner="incident commander",
        )

    expected_interventions = {
        "application_release": "rollback_release",
        "payment_provider": "shift_provider",
        "routing_configuration": "restore_timeout",
        "capacity": "shed_noncritical",
    }
    if expected_interventions.get(situation.choice) != intervention.choice:
        return PolicyDecision(
            action="Hold all changes and require a senior SRE to reconcile the causal and intervention signals.",
            reason="The proposed intervention does not target the diagnosed failure domain.",
            confidence=confidence,
            fallback=True,
            owner="payments SRE lead",
        )

    if intervention.score >= 3:
        return PolicyDecision(
            action="Reject automated execution and escalate the high-blast-radius option for architecture review.",
            reason="The proposed intervention exceeds the maximum permitted change-risk score.",
            confidence=confidence,
            fallback=True,
            owner="incident commander",
        )

    if situation.noul >= 0.80 and situation.score >= 3:
        return PolicyDecision(
            action=(
                f"Recommend {intervention.choice.replace('_', ' ')} under RB-PAY-17; require both named approvals "
                "and a five-minute rollback checkpoint."
            ),
            reason="Both Jev stages agree, evidence is sufficient, and intervention risk is within policy limits.",
            confidence=confidence,
            fallback=False,
            owner="incident commander + payments SRE",
        )

    return PolicyDecision(
        action="Continue enhanced monitoring and prepare the intervention without opening the execution gate.",
        reason="The intervention is coherent, but incident impact has not crossed the production change threshold.",
        confidence=confidence,
        fallback=False,
        owner="payments SRE",
    )


def execute() -> OperationRun:
    require_live_api_key()
    fingerprint = state_fingerprint(STATE)
    with TypeSafeClient(timeout=30) as client:
        situation_response = client.system_one(state=STATE, questions=SITUATION_QUESTIONS)
        situation = signals_from_response(situation_response, SITUATION_SIGNALS)
        intervention_state = {
            "incident_snapshot": STATE,
            "snapshot_fingerprint": fingerprint,
            "stage_one": asdict(situation),
            "allowed_actions": list(INTERVENTIONS),
            "hard_constraints": [
                "No automatic mutations",
                "Only reversible actions may be recommended",
                "Dual approval is mandatory",
            ],
        }
        intervention_response = client.system_one(state=intervention_state, questions=INTERVENTION_QUESTIONS)
        intervention = signals_from_response(intervention_response, INTERVENTION_SIGNALS)

    decision = decide(PaymentAssessment(situation=situation, intervention=intervention))
    return OperationRun(
        correlation_id=STATE["incident_id"],
        policy_version=POLICY_VERSION,
        state_fingerprint=fingerprint,
        stages=(
            OperationStage("situation", "Stage 1 / situation assessment", SITUATION_QUESTIONS, situation_response),
            OperationStage(
                "intervention",
                "Stage 2 / intervention challenge",
                INTERVENTION_QUESTIONS,
                intervention_response,
            ),
        ),
        decision=decision,
        controls=(
            "The TypeSafe client has no production mutation credentials.",
            "Every recommendation is bound to the immutable state fingerprint and idempotency key.",
            "Execution requires incident commander and payments SRE approval outside this process.",
            "Only reversible runbook actions may pass the policy gate.",
        ),
        audit=(
            AuditEvent(1, "snapshot.accepted", f"version=17 fingerprint={fingerprint}"),
            AuditEvent(2, "jev.situation.completed", f"model={situation_response.model}"),
            AuditEvent(3, "jev.intervention.completed", f"model={intervention_response.model}"),
            AuditEvent(4, "policy.evaluated", f"version={POLICY_VERSION} fallback={decision.fallback}"),
            AuditEvent(5, "execution.blocked", "recommendation emitted; no production mutation attempted"),
        ),
    )


def main() -> None:
    render_operation(title=TITLE, state=STATE, run=execute())


if __name__ == "__main__":
    main()
