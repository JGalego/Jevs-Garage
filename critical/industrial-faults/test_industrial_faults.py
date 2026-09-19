from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_unsafe_pump_recommends_confirmed_shutdown() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "require operator confirmation" in decision.action
    assert not decision.fallback


def test_uncertain_sensor_state_requests_inspection() -> None:
    decision = DEMO.decide(DEMO.evaluate(scenario="uncertain"))
    assert decision.fallback
    assert decision.owner == "shift engineer"
