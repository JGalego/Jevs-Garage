from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_red_flags_produce_emergency_guidance() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "emergency-services guidance" in decision.action
    assert not decision.fallback


def test_uncertainty_routes_to_licensed_clinician() -> None:
    decision = DEMO.decide(DEMO.evaluate(scenario="uncertain"))
    assert decision.fallback
    assert decision.owner == "licensed triage clinician"
