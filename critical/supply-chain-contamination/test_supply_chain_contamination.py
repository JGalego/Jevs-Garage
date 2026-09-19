from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_temperature_excursion_recommends_quarantine() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "quarantining" in decision.action
    assert not decision.fallback


def test_sensor_uncertainty_routes_to_lab_review() -> None:
    decision = DEMO.decide(DEMO.evaluate(scenario="uncertain"))
    assert decision.fallback
    assert "lab review" in decision.action
