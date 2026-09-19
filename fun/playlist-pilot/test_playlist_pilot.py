from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_focus_context_selects_instrumental_circuit() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "focus circuit" in decision.action
    assert "instrumental" in decision.action


def test_unclear_vibe_offers_samplers() -> None:
    assert DEMO.decide(DEMO.evaluate(scenario="uncertain")).fallback
