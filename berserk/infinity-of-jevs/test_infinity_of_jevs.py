from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def signal(choice: str, score: float, noul: float, confidence: float = 0.90) -> JevSignals:
    return JevSignals(
        choice=choice,
        choice_confidence=confidence,
        score=score,
        score_confidence=confidence,
        noul=noul,
    )


def round_result(number: int, choice: str, score: float = 2.5, confidence: float = 0.90) -> object:
    roles = {role: signal("uphold", 2.0, 0.85) for role in DEMO.ROLE_QUESTIONS}
    return DEMO.RecursiveRound(number, roles, signal(choice, score, 0.90, confidence))


def assessment(*, converged: bool, cycle: bool = False, audit_choice: str = "uphold") -> object:
    return DEMO.InfinityAssessment(
        consensus=signal("focused_review", 2.8, 0.91),
        audit=signal(audit_choice, 3.6, 0.92),
        convergence=DEMO.Convergence(converged, cycle, 2),
        rounds_completed=2,
        calls_used=11,
        call_budget=16,
        minimum_confidence=0.72,
    )


def test_sixteen_dynamic_jev_stages_use_typed_contracts() -> None:
    assert len(DEMO.QUESTION_SETS) == 16
    for questions in DEMO.QUESTION_SETS.values():
        assert_question_contract(questions, DEMO.SIGNALS)
    assert len(DEMO.PROGRESS_STEPS) == 18


def test_stable_rounds_converge() -> None:
    rounds = [round_result(1, "focused_review", 2.6), round_result(2, "focused_review", 2.8)]
    result = DEMO.convergence(rounds, required=2, minimum_confidence=0.72)
    assert result.converged
    assert not result.cycle_detected
    assert result.stable_rounds == 2


def test_a_b_a_pattern_is_detected_as_a_cycle() -> None:
    rounds = [
        round_result(1, "routine_watch"),
        round_result(2, "focused_review"),
        round_result(3, "routine_watch"),
    ]
    result = DEMO.convergence(rounds, required=2, minimum_confidence=0.72)
    assert result.cycle_detected
    assert not result.converged


def test_nonconvergence_routes_to_human_reviewer() -> None:
    decision = DEMO.decide(assessment(converged=False))
    assert decision.fallback
    assert "configured bound" in decision.action


def test_cycle_routes_to_human_adjudication() -> None:
    decision = DEMO.decide(assessment(converged=False, cycle=True))
    assert decision.fallback
    assert "oscillating" in decision.action


def test_converged_audited_result_can_reach_bounded_recommendation() -> None:
    decision = DEMO.decide(assessment(converged=True))
    assert not decision.fallback
    assert "focused seismic review" in decision.action


def test_final_auditor_can_veto_convergence() -> None:
    decision = DEMO.decide(assessment(converged=True, audit_choice="revise"))
    assert decision.fallback
    assert "final audit" in decision.action


def test_semantic_limits_prevent_literal_infinity() -> None:
    state = {**DEMO.STATE, "max_rounds": 4, "call_budget": 100}
    state["guardrails"] = {**DEMO.STATE["guardrails"], "stop_on_cycle": False}
    errors = DEMO.validate_state(state)
    assert "$.max_rounds: must be between 1 and 3" in errors
    assert "$.call_budget: must cover 21 calls and cannot exceed 16" in errors
    assert "$.guardrails.stop_on_cycle: must remain true" in errors


def test_source_endpoint_is_fixed_and_not_editable() -> None:
    assert DEMO.USGS_URL.startswith("https://")
    assert DEMO.USGS_URL not in str(DEMO.STATE)
