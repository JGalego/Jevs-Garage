from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def signals(choice: str, score: float, noul: float, confidence: float = 0.94) -> JevSignals:
    return JevSignals(
        choice=choice,
        choice_confidence=confidence,
        score=score,
        score_confidence=confidence,
        noul=noul,
    )


def test_both_stages_use_typed_sdk_contracts() -> None:
    assert_question_contract(DEMO.SITUATION_QUESTIONS, DEMO.SITUATION_SIGNALS)
    assert_question_contract(DEMO.INTERVENTION_QUESTIONS, DEMO.INTERVENTION_SIGNALS)


def test_matching_low_risk_intervention_reaches_dual_approval_gate() -> None:
    assessment = DEMO.PaymentAssessment(
        situation=signals("application_release", 3.7, 0.94),
        intervention=signals("rollback_release", 1.4, 0.95),
    )
    decision = DEMO.decide(assessment)
    assert not decision.fallback
    assert "both named approvals" in decision.action


def test_conflicting_intervention_is_held() -> None:
    assessment = DEMO.PaymentAssessment(
        situation=signals("payment_provider", 3.4, 0.91),
        intervention=signals("rollback_release", 1.2, 0.93),
    )
    decision = DEMO.decide(assessment)
    assert decision.fallback
    assert "reconcile" in decision.action


def test_high_blast_radius_is_rejected() -> None:
    assessment = DEMO.PaymentAssessment(
        situation=signals("payment_provider", 3.8, 0.95),
        intervention=signals("shift_provider", 3.4, 0.93),
    )
    decision = DEMO.decide(assessment)
    assert decision.fallback
    assert decision.action.startswith("Reject automated execution")


def test_uncertain_attribution_freezes_automation_deterministically() -> None:
    assessment = DEMO.PaymentAssessment(
        situation=signals("multi_factor", 3.5, 0.71, confidence=0.60),
        intervention=signals("freeze_and_observe", 0.8, 0.58, confidence=0.55),
    )
    first = DEMO.decide(assessment)
    second = DEMO.decide(assessment)
    assert first == second
    assert first.fallback
    assert first.owner == "incident commander"


def test_state_disables_mutating_automation() -> None:
    assert DEMO.STATE["safety"]["automated_mutations_enabled"] is False
    assert len(DEMO.STATE["safety"]["required_approvals"]) == 2
