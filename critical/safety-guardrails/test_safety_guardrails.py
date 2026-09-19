from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_unsafe_draft_is_suppressed_by_policy() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert decision.action.startswith("Suppress the draft")
    assert not decision.fallback


def test_ambiguous_draft_is_withheld_for_review() -> None:
    decision = DEMO.decide(DEMO.evaluate(scenario="uncertain"))
    assert decision.fallback
    assert "review" in decision.action.lower()
