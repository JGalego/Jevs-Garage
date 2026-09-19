from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_craving_maps_to_miso_popcorn() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "miso-lime popcorn" in decision.action
    assert not decision.fallback


def test_indecisive_craving_gets_tasting_flight() -> None:
    decision = DEMO.decide(DEMO.evaluate(scenario="uncertain"))
    assert decision.fallback
    assert "tasting flight" in decision.action
