from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_shared_preferences_pick_light_mystery() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "mystery" in decision.action
    assert not decision.fallback


def test_split_group_gets_ranked_vote() -> None:
    decision = DEMO.decide(DEMO.evaluate(scenario="uncertain"))
    assert decision.fallback
    assert "ranked vote" in decision.action
