from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_major_outage_recommends_operator_approved_revert() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "for approval" in decision.action
    assert not decision.fallback


def test_unknown_domain_freezes_automation() -> None:
    decision = DEMO.decide(DEMO.evaluate(scenario="uncertain"))
    assert decision.fallback
    assert decision.action.startswith("Freeze automated remediation")
