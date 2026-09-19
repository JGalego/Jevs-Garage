from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_scifi_plant_gets_ripley() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "Ripley" in decision.action
    assert not decision.fallback


def test_uncertain_style_gets_shortlist() -> None:
    assert DEMO.decide(DEMO.evaluate(scenario="uncertain")).fallback
