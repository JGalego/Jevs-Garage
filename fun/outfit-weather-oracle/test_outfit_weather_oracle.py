from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_wet_breezy_day_uses_yellow_shell() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "yellow shell" in decision.action
    assert "waterproof shoes" in decision.action


def test_uncertain_forecast_uses_packable_fallback() -> None:
    assert DEMO.decide(DEMO.evaluate(scenario="uncertain")).fallback
