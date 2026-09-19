from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_life_threat_is_presented_to_dispatcher() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "do not auto-dispatch" in decision.action
    assert not decision.fallback


def test_uncertain_call_stays_with_human() -> None:
    decision = DEMO.decide(DEMO.evaluate(scenario="uncertain"))
    assert decision.fallback
    assert decision.owner == "certified dispatcher"
