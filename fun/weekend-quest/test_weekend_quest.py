from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_clear_day_selects_tram_wander() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "next tram" in decision.action
    assert not decision.fallback


def test_ambiguous_day_gets_coin_flip() -> None:
    assert DEMO.decide(DEMO.evaluate(scenario="uncertain")).fallback
