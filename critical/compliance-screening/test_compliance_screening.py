from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_likely_match_recommends_compliance_hold() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "pending analyst adjudication" in decision.action
    assert not decision.fallback


def test_ambiguous_match_gets_enhanced_review() -> None:
    decision = DEMO.decide(DEMO.evaluate(scenario="uncertain"))
    assert decision.fallback
    assert decision.owner == "compliance analyst"
