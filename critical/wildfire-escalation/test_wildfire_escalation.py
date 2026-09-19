from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_extreme_spread_recommends_authorized_warning_review() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "authorized incident command" in decision.action
    assert not decision.fallback


def test_uncertain_spread_goes_to_incident_commander() -> None:
    decision = DEMO.decide(DEMO.evaluate(scenario="uncertain"))
    assert decision.fallback
    assert decision.owner == "incident commander"
