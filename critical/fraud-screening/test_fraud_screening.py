from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_high_risk_transaction_gets_reversible_hold() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert decision.action.startswith("Place a reversible authorization hold")
    assert not decision.fallback


def test_uncertain_transaction_uses_safe_fallback() -> None:
    response = DEMO.evaluate(scenario="uncertain")
    first = DEMO.decide(response)
    second = DEMO.decide(response)
    assert first == second
    assert first.fallback
    assert "review" in first.action.lower()