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


def assessment(
    *,
    posture: str = "routine_watch",
    urgency: float = 1.0,
    coherent: float = 0.92,
    robust: float = 0.91,
    final_confidence: float = 0.90,
    source_count: int = 4,
) -> object:
    domains = {key: signal("routine", 1.0, 0.15) for key in ("earthquake", "weather", "cyber", "space_weather")}
    return DEMO.MetaAssessment(
        domain_signals=domains,
        calibration=signal("none", 3.8, 0.12),
        dependencies=signal("none", 1.0, 0.18),
        arbitration=signal(posture, urgency, coherent, final_confidence),
        stability=signal("none", 3.8, robust, final_confidence),
        source_count=source_count,
        minimum_source_success=4,
        minimum_final_confidence=0.72,
    )


def test_all_eight_jev_stages_use_typed_contracts() -> None:
    assert len(DEMO.QUESTION_SETS) == 8
    for key, questions in DEMO.QUESTION_SETS.items():
        if key in {"earthquake", "weather", "cyber", "space_weather"}:
            names = DEMO.DOMAIN_SIGNAL_NAMES
        else:
            names = {
                "calibration": DEMO.CALIBRATION_SIGNALS,
                "dependencies": DEMO.DEPENDENCY_SIGNALS,
                "arbitration": DEMO.ARBITRATION_SIGNALS,
                "stability": DEMO.STABILITY_SIGNALS,
            }[key]
        assert_question_contract(questions, names)


def test_source_urls_are_fixed_https_endpoints() -> None:
    urls = (DEMO.USGS_URL, DEMO.NWS_URL, DEMO.CISA_KEV_URL, DEMO.NOAA_KP_URL)
    assert all(url.startswith("https://") for url in urls)
    assert not any(url in str(DEMO.STATE) for url in urls)


def test_semantic_validation_protects_guardrails_and_ranges() -> None:
    state = {**DEMO.STATE, "minimum_source_success": 0}
    state["guardrails"] = {**DEMO.STATE["guardrails"], "advisory_only": False}
    errors = DEMO.validate_state(state)
    assert "$.minimum_source_success: must be between 1 and 4" in errors
    assert "$.guardrails.advisory_only: must remain true" in errors


def test_routine_stable_result_remains_routine() -> None:
    decision = DEMO.decide(assessment())
    assert not decision.fallback
    assert decision.action.startswith("Maintain routine watch")


def test_multi_domain_result_requires_human_approval() -> None:
    value = assessment(posture="multi_domain_coordination", urgency=3.4)
    decision = DEMO.decide(value)
    assert not decision.fallback
    assert "require human approval" in decision.action


def test_failed_source_quorum_forces_fallback() -> None:
    decision = DEMO.decide(assessment(source_count=3))
    assert decision.fallback
    assert decision.owner == "data operations lead"


def test_fragile_arbiter_result_forces_fallback() -> None:
    value = assessment(coherent=0.55, robust=0.54, final_confidence=0.60)
    first = DEMO.decide(value)
    second = DEMO.decide(value)
    assert first == second
    assert first.fallback
    assert "human situation lead" in first.action
