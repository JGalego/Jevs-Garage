from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_active_compromise_recommends_operator_containment() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "await operator approval" in decision.action
    assert not decision.fallback


def test_uncertain_alert_preserves_evidence_for_human() -> None:
    response = DEMO.evaluate(scenario="uncertain")
    assert DEMO.decide(response) == DEMO.decide(response)
    assert DEMO.decide(response).fallback
